# Se brancher sur la plateforme

Cette page est un **mode d'emploi** : comment, depuis votre code (pipelines,
jobs, requêtes), atteindre chaque brique de la plateforme — quel service
joindre, avec quel secret, quel paramétrage. Elle suppose que votre code tourne
**dans un pod du cluster**, dans un namespace autorisé par les NetworkPolicies.

> **Pour développer en local d'abord**, montez un banc et rejouez la boucle
> complète : voir le tutoriel [Monter le banc local](banc-local.md). Pour _ce
> que fait_ chaque brique et _pourquoi elle est là_, voir
> [composants](composants.md). Pour la liste de référence des endpoints (table +
> StorageClasses), voir [le guide du développeur data](guide-dev-data.md).
>
> **Frontière (ADR [0022](decisions/0022-argocd-gitops-applicatif.md) /
> [0023](decisions/0023-plateforme-exemple-generique.md)).** Ce dépôt fournit
> l'**infrastructure** (générique) ; le **code métier** vit dans le dépôt
> applicatif. Les exemples ci-dessous sont **génériques et jetables** — ils
> montrent le _comment se brancher_, pas la logique d'un projet. Les valeurs
> réelles (mots de passe, hostnames) viennent d'une config locale non
> versionnée.
>
> **Source de vérité des endpoints.** Les adresses, ports, conventions de
> secrets et StorageClasses sont publiés comme **contrat versionné** sous
> [`contract/`](../contract/) — diff-able et consommable par un script
> ([ADR 0043](decisions/0043-contrat-interface-cluster-atlas.md)). En cas
> d'écart, le contrat fait foi ; cette page en est la version pédagogique.

## Base de données — PostgreSQL (CloudNativePG)

Un cluster HA unique `pg` (namespace `postgres`) porte **quatre bases
logiques**, chacune avec son rôle propriétaire
([ADR 0024](decisions/0024-postgres-manage-cloudnative-pg.md)) : `dagster`
(event log de l'[orchestrateur](composants.md#dagster-orchestration)), `marquez`
(store de [lineage](composants.md#marquez-et-openlineage-lineage)), `pgvector`
(recherche sémantique), `mlflow` (backend store du
[suivi de modèles](composants.md#mlflow-suivi-de-modèles), ADR 0082).

**Connexion** : écrire sur le service primary
([`pg-rw`](glossaire.md#postgresql-cloudnativepg-cnpg)), lire sur le replica
(`pg-ro`). Le mot de passe d'un rôle est dans le Secret `pg-role-<rôle>` (clé
`password`, namespace `postgres`) — ne l'employez **jamais** en clair, lisez-le
du Secret :

```bash
# Exemple générique : récupérer le mot de passe du rôle dagster.
kubectl -n postgres get secret pg-role-dagster -o jsonpath='{.data.password}' | base64 -d
```

```python
# Exemple générique (psycopg) — depuis un pod, le pwd vient d'une var d'env
# injectée par un secretKeyRef (jamais en dur).
import os, psycopg
conn = psycopg.connect(
    host="pg-rw.postgres.svc.cluster.local", port=5432,
    dbname="pgvector", user="pgvector", password=os.environ["PG_PASSWORD"],
)
```

Pour la recherche sémantique, l'extension [pgvector](glossaire.md#pgvector) est
déjà activée par l'opérateur (`CREATE EXTENSION vector` fait) : utilisez le type
`vector(n)` dans vos tables.

**Prérequis réseau** : votre pod doit avoir une NetworkPolicy egress vers
`postgres:5432` (modèle :
`platform/network-policies/<app>/allow-postgres-egress.yaml`).

## Traçabilité — émettre du lineage vers Marquez

Émettez des événements
[OpenLineage](composants.md#marquez-et-openlineage-lineage) vers l'API Marquez ;
ils y sont ingérés et visualisés
([ADR 0028](decisions/0028-orchestration-openlineage-marquez.md)). Le client
OpenLineage standard lit ces variables d'environnement :

| Variable                | Valeur (intra-cluster)                           |
| ----------------------- | ------------------------------------------------ |
| `OPENLINEAGE_URL`       | `http://marquez.marquez.svc.cluster.local:5000`  |
| `OPENLINEAGE_ENDPOINT`  | `api/v1/lineage`                                 |
| `OPENLINEAGE_NAMESPACE` | le namespace logique de vos jobs (ex. `dagster`) |

Pour **requêter** le lineage (lecture), l'API REST Marquez — p. ex. lister les
jobs d'un namespace :

```bash
# Depuis un pod du cluster :
wget -qO- http://marquez.marquez.svc.cluster.local:5000/api/v1/namespaces/<ns>/jobs
```

> **Réseau** : Marquez n'accepte le POST de lineage que depuis un namespace
> autorisé (`allow-openlineage-ingress.yaml`) ; votre pod émetteur a besoin de
> l'egress correspondant (`allow-marquez-egress.yaml` côté Dagster en est le
> modèle — leçon du drift L19, cf.
> [leçons des runs](architecture/lecons-des-runs.md)).

## Suivi de modèles — logger avec MLflow

Loggez vos entraînements (paramètres, métriques, artefacts) vers le serveur
[MLflow](composants.md#mlflow-suivi-de-modèles) ; ils y sont enregistrés et
visualisables, et les modèles versionnés dans le registre
([ADR 0082](decisions/0082-suivi-modeles-mlflow.md)). Le serveur est livré
**vide** : c'est votre code (côté atlas) qui le peuple. Le client MLflow lit une
seule variable d'environnement (pendant de `OPENLINEAGE_URL`) :

| Variable              | Valeur (intra-cluster)                        |
| --------------------- | --------------------------------------------- |
| `MLFLOW_TRACKING_URI` | `http://mlflow.mlflow.svc.cluster.local:5000` |

```python
# Exemple générique — depuis un pod du cluster, l'URI vient d'une var d'env.
import os, mlflow

mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
mlflow.set_experiment("mon-experiment")

with mlflow.start_run():
    mlflow.log_param("epochs", 10)
    mlflow.log_metric("accuracy", 0.92)
    # mlflow.log_artifact(...) / mlflow.<saveur>.log_model(...) → artefact store S3
```

Le **backend store** (métadonnées des runs) est la base CNPG `mlflow` ;
l'**artefact store** (modèles, fichiers volumineux) est du S3
([ADR 0036](decisions/0036-backing-s3-unique-rgw.md)) — vous n'avez rien à
câbler, le serveur les porte. Pas d'authentification intra-cluster (réseau privé
mono-admin).

> **Réseau** : votre pod émetteur a besoin d'un egress vers `mlflow:5000`
> (modèle : `platform/network-policies/<app>/allow-mlflow-egress.yaml`).

## Orchestration — brancher une code-location Dagster

L'[orchestrateur](composants.md#dagster-orchestration) est livré **vide**
(aucune [code-location](glossaire.md#code-location)) : c'est le **socle**, votre
code (assets, jobs) s'y branche depuis le dépôt applicatif
([ADR 0026](decisions/0026-orchestration-dagster.md), frontière ADR 0022).

- **Storage** : Dagster persiste son event log dans la base `dagster` (déjà
  câblé via le Secret `dagster-pg-auth`).
- **Exécution** : [`K8sRunLauncher`](glossaire.md#k8srunlauncher) — chaque run
  devient un Job Kubernetes.

Le socle monte un [ConfigMap](glossaire.md#configmap) `dagster-workspace` (clé
`workspace.yaml`) avec `load_from: []` — **zéro location** : un orchestrateur
sans code-location doit quand même recevoir un workspace, sinon le
webserver/daemon échouent. Pour brancher votre code, **deux objets à pousser**
(par GitOps, jamais `kubectl apply` — frontière ADR 0022) :

1. **Un Deployment + Service gRPC** dans le ns `dagster`, qui sert votre image
   de code-location (`dagster api grpc -h 0.0.0.0 -p 4000 -m <votre_module>`).
   Référencez votre image en `registry:80/<repo>:<tag>` et injectez-y
   `OPENLINEAGE_URL` pour que vos runs émettent le lineage.
2. **Le branchement dans le workspace** : surchargez le ConfigMap
   `dagster-workspace` par un **patch GitOps** (kustomize/Argo CD) plutôt que de
   le réécrire :

   ```yaml
   # workspace.yaml côté code-location (exemple générique) :
   load_from:
     - grpc_server:
         host: <votre-code-location>.dagster.svc.cluster.local
         port: 4000
         location_name: <votre-code-location>
   ```

   Après réconciliation Argo CD, la location apparaît dans l'UI.

> **Accès Internet sortant (sync d'un snapshot ouvert).** Sous default-deny
> ([ADR 0019](decisions/0019-durcissement-reseau-cilium.md)), le ns `dagster`
> n'a d'egress que vers DNS / api-server / Postgres / registry / Marquez. Un run
> qui **synchronise un snapshot de données ouvert** depuis un store objet public
> a besoin d'un egress Internet : le socle le fournit par
> [`allow-internet-egress.yaml`](../platform/network-policies/dagster/allow-internet-egress.yaml)
> (ports 443/80). Côté applicatif, **bornez le volume** par config : c'est une
> décision métier, pas d'infra.

## Images — pousser dans le registry interne

Vos images applicatives (code-location, jobs) se poussent dans le **registry
interne** ([ADR 0011](decisions/0011-registry-http-sans-auth.md)) :

- Référencez-les en `registry:80/<repo>:<tag>` dans vos manifestes/CR.
- Les nœuds tirent ce registry en HTTP (config containerd posée par la
  plateforme : `use_local_image_pull`, drifts L9/L13).
- **arm64** : sur le banc, les images maison sont buildées en interne ; en prod
  x86, les images officielles sont re-taguées
  ([ADR 0006](decisions/0006-matrice-de-versions-et-politique-de-bump.md)).

## Stockage — réclamer du bloc ou de l'objet

**Bloc ([PVC](glossaire.md#pvc-persistentvolumeclaim))** — bases, état
applicatif. StorageClasses disponibles (défaut = `rook-ceph-block-replicated`,
RBD ×3, [ADR 0001](decisions/0001-replication-x3-pour-workloads-bloc.md)) :

```yaml
# PVC générique :
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: rook-ceph-block-replicated
  resources: { requests: { storage: 10Gi } }
```

**Objet ([S3](glossaire.md#rgw-rados-gateway))** — datalake, artefacts. Demandez
un bucket via un [ObjectBucketClaim](glossaire.md#obc-objectbucketclaim) (Rook
provisionne le bucket + un Secret de creds dans votre namespace) :

```yaml
apiVersion: objectbucket.io/v1alpha1
kind: ObjectBucketClaim
metadata: { name: mon-bucket, namespace: <votre-ns> }
spec:
  generateBucketName: mon-bucket
  storageClassName: rook-ceph-datalake
```

Le Secret généré (même nom que l'OBC) porte `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` ; l'endpoint S3 est
`http://rook-ceph-rgw-datalake.rook-ceph:80` (path-style, HTTP intra-cluster).
Détail :
[`storage/ceph/storageClass/datalake/`](../storage/ceph/storageClass/datalake/).

## Exposer une UI hors cluster

Pour exposer une UI, ajoutez un `HTTPRoute` rattaché au
[Gateway Cilium](composants.md#exposition-tout-cilium-lb-ipam-annonce-l2-gateway-api),
avec TLS émis par la CA interne (annotation
`cert-manager.io/cluster-issuer: internal-ca`) — patron :
[`platform/dagster/gateway.yaml`](../platform/dagster/gateway.yaml). Le hostname
`*.cluster.lan` est un **placeholder** ; l'admin réseau pose le vrai.

## Observabilité — sans rien câbler

Le socle fournit les opérateurs ; vous les consommez en émettant des objets :

- **Métriques** : exposez un `ServiceMonitor`/`PodMonitor` → Prometheus scrape
  automatiquement.
- **Logs** : écrivez sur stdout/stderr → [Promtail](glossaire.md#promtail) les
  collecte (DaemonSet) et les pousse vers Loki, sans action de votre part.

## Déployer — la boucle GitOps

Vous ne déployez **pas** vos workflows avec `kubectl`, mais par
[la boucle GitOps](composants.md#la-boucle-gitops-de-bout-en-bout) (build → push
registry → commit manifeste dans la forge → webhook → réconciliation Argo CD).
La mise en pratique pas à pas sur un banc — cloner la forge, pousser, observer
la réconciliation — est décrite dans le tutoriel
[Monter le banc local](banc-local.md#pousser-sur-gitea).

## Pour aller plus loin

- Référence des endpoints (table consolidée) :
  [guide du développeur data](guide-dev-data.md).
- Présentation des briques : [composants](composants.md).
- Mettre la plateforme en place :
  [`bootstrap/dataops.yaml`](../bootstrap/dataops.yaml)
  ([ADR 0033](decisions/0033-orchestration-ansible-platform-dataops.md)).
