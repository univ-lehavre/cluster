# 0082 — Suivi de modèles via MLflow

## Contexte

Le socle DataOps a un orchestrateur ([ADR 0026](0026-orchestration-dagster.md),
Dagster) et un store de lineage
([ADR 0028](0028-orchestration-openlineage-marquez.md), Marquez), tous deux
backés par le PostgreSQL managé
([ADR 0024](0024-postgres-manage-cloudnative-pg.md)). Manque le **suivi
d'expériences et le registre de modèles** : où sont loggués les runs (params,
métriques), les artefacts (modèles, courbes), et où s'enregistrent les versions
de modèles promues. Le standard de fait est **MLflow** (tracking server + model
registry + artefact store). Le code ML vit côté `atlas` (Phase 2+) ; ici on
déploie le **serveur seul**, comme Dagster est livré vide (ADR 0026).

## Décision

**MLflow tracking server** sur Kubernetes (image officielle multi-arch
`ghcr.io/mlflow/mlflow`), dans `platform/mlflow/`, appliqué par le rôle Ansible
`platform-mlflow` comme les autres addons plateforme (manifeste figé appliqué
via `kubernetes.core.k8s`, ADR
[0033](0033-orchestration-ansible-platform-dataops.md)/[0049](0049-doctrine-choix-outil-par-action.md)
— pas Argo CD pour l'infra, frontière anti-bootstrap-circulaire ADR 0022).

- **Addon socle (vs côté atlas)** : MLflow est un service partagé
  multi-consommateur (comme Dagster/Marquez), géré par Ansible. Le namespace
  `mlflow` reste **destinataire Argo CD** (AppProject `atlas`) pour le futur
  code atlas, mais le serveur lui-même est posé par le socle.

- **Backend store = base CNPG dédiée `mlflow`** : cohérent avec
  `dagster`/`pgvector`/`marquez`.
  `--backend-store-uri postgresql://mlflow:<pwd>@pg-rw.postgres.svc:5432/mlflow`.
  La base est ajoutée au **cluster CNPG HA unique `pg`** (un seul cluster
  PostgreSQL porte toutes les bases applicatives). Le mot de passe vient d'un
  **Secret dérivé** `mlflow-pg-auth` (clé `postgresql-password`, alignée sur
  Dagster), recopié du Secret CNPG `pg-role-mlflow` — config locale non
  versionnée ([ADR 0023](0023-plateforme-exemple-generique.md)).

- **Artefact store = S3** via le rôle factorisé `platform-s3-bucket`
  ([ADR 0036](0036-backing-s3-unique-rgw.md)) :
  `--default-artifact-root s3://<bucket>/`, `MLFLOW_S3_ENDPOINT_URL` pointant le
  **backing actif** (RGW Ceph en prod / SeaweedFS au banc léger). Même chemin de
  code, backing paramétré ; le bucket OBC auto-nommé est résolu au runtime par
  le rôle (l'env `--default-artifact-root` est injectée à l'apply, comme Loki
  templise son endpoint S3). MLflow embarque `boto3` (artefact store S3
  fonctionnel).

- **InitContainer wait-for-db** (image `postgres` épinglée par digest d'index
  multi-arch, ADR 0006, réutilise le digest Marquez) : MLflow crée son schéma au
  premier démarrage (`mlflow db upgrade` implicite) → attendre que CNPG réponde.

- **Exposition de l'UI** via le Gateway Cilium + TLS interne
  ([ADR 0020](0020-exposition-reseau-tout-cilium.md)/[0021](0021-cert-manager-ca-interne.md)),
  **sans auth** : réseau privé de confiance mono-admin
  ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)), comme
  Dagster/Marquez. L'API/UI partagent le port 5000 (MLflow est un seul serveur).
  Les émetteurs (code atlas) la joignent par le Service ClusterIP
  `mlflow.mlflow.svc:5000` (variable `MLFLOW_TRACKING_URI`, pendant de
  `OPENLINEAGE_URL` pour Marquez).

- **Serveur livré configuré mais VIDE** : aucune expérience pré-créée ; `atlas`
  logue ses runs et enregistre ses modèles (précédent « orchestrateur vide »
  Dagster, ADR 0026).

### Image : multi-arch officielle (pas de build maison)

Contrairement à Marquez/Dagster (amd64-only en amont → build arm64 interne, ADR
0028), l'image `ghcr.io/mlflow/mlflow` est publiée en **index multi-arch**
(`MediaType: …image.index…`, `linux/amd64` **et** `linux/arm64` — vérifié sur
`v3.4.0`). On l'épingle donc **directement par digest d'index** (ADR 0006), sans
image maison ni Play de build : le banc arm64 et la prod x86 tirent la bonne
variante. C'est plus simple que ses jumeaux DataOps.

## Statut

Proposed (2026-06-17). **Validation banc différée** : le banc Ceph a été détruit
; la convergence réelle (`bootstrap/dataops.yaml --tags mlflow`) sera prouvée au
prochain montage Ceph multi-node — base `mlflow` créée, OBC RGW produisant le
bucket + creds, pod MLflow Ready, un run loggué depuis atlas persistant
params/métriques en base et artefacts en S3, UI répondant sur
`mlflow.cluster.lan` — à consigner dans l'historique des runs (honnêteté des
preuves, ADR 0052).

## Conséquences

**Bénéfices.**

- Suivi d'expériences + registre de modèles (MLflow, standard de fait), API +
  UI.
- Store HA/sauvegardé (base CNPG `mlflow`) + artefacts S3, pas d'infrastructure
  stateful supplémentaire (réutilise le cluster `pg` et le RGW datalake).
- Socle DataOps complet : orchestration (Dagster) + lineage (Marquez) + suivi de
  modèles (MLflow), les trois backés CNPG, le même pattern d'addon.
- **Pas d'image maison à maintenir** (multi-arch officielle) — contrairement à
  Marquez/Dagster ; un bump = repin du digest, sans rebuild arm64.

**Coûts assumés.**

- **API/UI sans auth** : acceptable sur réseau privé mono-admin ; à durcir si le
  cluster s'ouvre (oauth2-proxy en bordure).
- Le `--default-artifact-root` dépend du bucket OBC auto-nommé → résolu au
  runtime par le rôle Ansible (env injectée), pas figé dans le manifeste.

## Alternatives écartées

- **MLflow côté atlas (pas addon socle)** : MLflow est partagé
  multi-consommateur comme Dagster/Marquez ; le poser côté atlas le couplerait à
  un seul dépôt et recréerait la circularité bootstrap (ADR 0022). Addon socle
  retenu.
- **Schéma dans une base partagée** (plutôt qu'une base dédiée) : MLflow gère
  son historique de migrations par base ; une base dédiée `mlflow` (comme
  Marquez) isole proprement. Base dédiée retenue.
- **Un cluster CNPG dédié à MLflow** : doublerait l'infrastructure stateful HA
  pour un store modeste. Un seul cluster `pg` partagé (une base par appli)
  suffit.
- **Artefact store sur PVC (filesystem)** plutôt que S3 : ne survivrait pas à un
  reschedule sans RWX, et heurterait le pattern S3 factorisé (ADR 0036). S3
  (OBC) retenu, cohérent avec les backings du socle.
- **Image maison arm64 (comme Marquez)** : inutile — l'image officielle est
  multi-arch. On évite le build et la maintenance.

## À revoir

- Auth en bordure de l'UI (oauth2-proxy) si ouverture du cluster.
- Brancher un ServiceMonitor MLflow sur le monitoring (métriques du serveur).
- Politique de rétention des runs/artefacts à ajuster selon le volume réel.
- Si MLflow cesse de publier des images multi-arch : basculer sur image maison
  (le pattern Marquez reste disponible).
