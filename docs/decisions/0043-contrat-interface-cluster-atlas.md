# 0043 — Contrat d'interface cluster → atlas

## Contexte

Le travail se répartit sur **deux dépôts** : `cluster` (ce dépôt — le **socle
d'infrastructure** générique : Kubernetes, stockage, plateforme DataOps) et
`atlas` (le dépôt **applicatif/métier** — pipelines, assets, code des
traitements). Leur frontière est posée par
[ADR 0023](0023-plateforme-exemple-generique.md) (le métier vit dans `atlas`,
jamais ici) et [ADR 0022](0022-argocd-gitops-applicatif.md) (Argo CD déploie
l'applicatif via l'`AppProject` `atlas`).

Mais l'**interface** entre les deux reste **implicite** : pour qu'un pipeline
`atlas` se connecte à Postgres, pousse une image, émette du lineage ou lise un
bucket S3, il doit connaître des **endpoints** (noms de Services, ports,
namespaces), des **StorageClasses** et des **conventions de secrets**. Ces faits
existent — dispersés dans les manifestes `platform/`, `storage/` et dans
[`docs/guide-dev-data.md`](../guide-dev-data.md) — mais ne sont **ni regroupés
ni machine-lisibles**. Un développeur `atlas` doit aujourd'hui les **deviner**
ou fouiller le dépôt `cluster`.

## Décision

**Le dépôt `cluster` publie un contrat d'interface explicite et machine-lisible
vers `atlas`** : ce que le socle s'engage à exposer (endpoints, StorageClasses,
namespaces, conventions de secrets), en **valeurs d'exemple génériques** (ADR
0023), sous [`contract/`](../../contract/).

1. **Trois artefacts versionnés** (`*.example.yaml`), source unique côté
   `cluster`, consommables par `atlas` :
   - [`contract/endpoints.example.yaml`](../../contract/endpoints.example.yaml)
     — Services exposés : nom, namespace, port, protocole, FQDN interne, auth.
   - [`contract/storage-classes.example.yaml`](../../contract/storage-classes.example.yaml)
     — StorageClasses disponibles **par profil** (Ceph / local-path) et la SC
     `default` de chacun.
   - [`contract/namespaces-secrets.example.yaml`](../../contract/namespaces-secrets.example.yaml)
     — namespaces de destination (alignés sur l'`AppProject` `atlas`) et
     **conventions de secrets** (rôles CNPG, dérivés Dagster/Marquez, OBC S3).

2. **Patron `.example`** (ADR 0023) : ces fichiers portent des **valeurs
   d'exemple concrètes et stables** (FQDN, ports, noms de SC réels — qui sont
   des briques que le dépôt propose, donc **conservées**), mais **aucune valeur
   réelle d'un déploiement** (pas de mot de passe, pas d'IP de prod, pas de
   creds S3). Les valeurs réelles vivent en config locale non versionnée.

3. **Cohérence avec la doc existante** : le contrat **n'invente rien** — il
   formalise la table d'accès déjà décrite dans
   [`docs/guide-dev-data.md`](../guide-dev-data.md) (« Points d'accès ») et la
   rend requêtable. La prose reste la pédagogie ; le contrat, la donnée.

4. **Sens unique `cluster → atlas`** : ce contrat décrit ce que le socle
   **fournit**. Ce qu'`atlas` **attend en retour** (schémas de données, formats
   d'assets) relève du dépôt `atlas` (frontière ADR 0023). Le contrat liste une
   section « attendu par atlas » à titre indicatif, sans la normaliser ici.

## Statut

Accepted.

## Conséquences

- **Gain** : un développeur `atlas` lit **un seul endroit** pour se brancher —
  plus de devinette, plus de fouille du dépôt `cluster`. Le contrat est
  diff-able : tout changement d'endpoint/SC/secret côté socle est **visible** en
  revue et peut casser un test côté `atlas` de façon explicite.
- **Frontière préservée** (ADR 0023) : le contrat est de l'**INFRA** (ce que le
  socle expose) ; il ne contient aucun cas d'usage métier. Les namespaces
  applicatifs y figurent comme **cibles de déploiement** (déjà déclarées dans
  l'`AppProject` `atlas`), pas comme contenu métier.
- **Maintenance** : le contrat doit être tenu à jour quand un endpoint change.
  Il référence ses fichiers sources (manifestes) ; à terme, un test pourrait
  vérifier la cohérence contrat ↔ manifestes (hors périmètre de cet ADR).
- **Prix à payer** : une duplication assumée entre les manifestes (vérité
  d'exécution) et le contrat (vérité d'interface). Justifiée : `atlas` ne doit
  pas dépendre de la structure interne des manifestes `cluster`, seulement de
  l'interface stable.
- **Profils** : le contrat distingue explicitement **Ceph** (prod / preuve) et
  **local-path/SeaweedFS** (banc rapide) — un consommateur sait quel endpoint S3
  ou quelle SC viser selon le profil
  ([ADR 0035](0035-strategie-bancs-fidelite-vitesse.md),
  [ADR 0036](0036-backing-s3-unique-rgw.md)).

## Mises à jour

- **2026-07-07 — 3ᵉ consommateur du datalake objet : `pageviews`.** La
  code-location dataops `pageviews` (dépôt `atlas`, package `pageviews-dagster`,
  ADR atlas 0098 — prévision des vues Wikipédia des universités) instancie son
  **point de contact S3** sur le même mécanisme générique que
  `citation`/`mediawatch` : un `ObjectBucketClaim` `pageviews-datalake`
  (storageClass `rook-ceph-datalake`, ns `dagster`) → Rook génère un **Secret**
  (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`) et un **ConfigMap**
  (`BUCKET_HOST`/`BUCKET_PORT`/`BUCKET_NAME`, nom réel
  `pageviews-datalake-<uuid>`), consommés par `envFrom`, endpoint RGW
  path-style. Le contrat n'énumère **pas** un OBC par consommateur (il documente
  le _mécanisme_, ADR 0023) : aucun changement structurel de
  `contract/*.example.yaml` n'est requis, le bloc `object_bucket_claim` existant
  couvre ce cas. **Écart clé vs `citation` : aucune base Postgres/pgvector**
  (pas de Secret PG, pas de migration SQL, pas d'index vectoriel) — le contrat
  côté base n'est pas sollicité.
- **Garde-fou « même vague » (miroir atlas ADR 0033).** L'instanciation de ce
  point de contact déclenche la synchronisation de son miroir applicatif :
  l'**ADR atlas 0033** doit être mis à jour **dans la même vague de PR**
  (convention de bucket `pageviews`, mécanisme OBC, namespaces `pageviews`) —
  les deux faces du même contrat nomment le même bucket et les mêmes namespaces
  (c'est la divergence que le contrat bilatéral existe pour prévenir).
- **2026-07-12 — Curseur `persistence.mode` (ADR 0109).** Le canal
  `derive_run_params` (`profile.py`, transporté par les `-e` Ansible des phases)
  a gagné le champ `persistence_mode`. Son transport côté cluster est **câblé
  (#631)** mais **mord uniquement sur les briques d'infrastructure**
  (StorageClass, CNPG, Loki, Prometheus, datalake, volume-snapshots) : le
  curseur **s'arrête à CNPG** et **n'atteint pas** l'env du pod code-location
  `atlas` aujourd'hui. Le **versant applicatif** — le pipeline atlas réagissant
  au mode (bornes d'ingestion, cache) — est traité côté atlas
  ([ADR atlas 0102](https://github.com/univ-lehavre/atlas/blob/main/docs/src/content/docs/decisions/0102-cache-adaptatif-reaction-persistence-mode.md),
  volet différé cluster#630). Câbler la variable jusqu'au pod atlas est un
  **second geste** non encore fait (le défaut `full` garantit l'absence de
  régression tant qu'il ne l'est pas).
