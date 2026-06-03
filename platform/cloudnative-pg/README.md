# CloudNativePG

PostgreSQL managé (socle DataOps, étape 1.6,
[ADR 0024](../../docs/decisions/0024-postgres-manage-cloudnative-pg.md)). Un
cluster HA servant **deux usages** via deux bases logiques : l'**event log
Dagster** (1.7) et l'**index pgvector** (recherche sémantique, chargé par
atlas). Sauvegardes vers S3 via le **plugin Barman Cloud**.

Géré par `kubectl apply` (comme les autres addons `platform/`), pas par Argo CD
(anti-bootstrap-circulaire,
[ADR 0022](../../docs/decisions/0022-argocd-gitops-applicatif.md)).

## Fichiers

| Fichier                    | Rôle                                                          | Lint  |
| -------------------------- | ------------------------------------------------------------- | ----- |
| `operator.yaml`            | operator CNPG 1.29.1 **vendored**                             | exclu |
| `plugin-barman-cloud.yaml` | plugin Barman Cloud v0.12.0 **vendored** (sauvegardes S3)     | exclu |
| `cluster.yaml`             | CR `Cluster` (3 instances, PG18, pgvector, rôles, plugin)     | linté |
| `database.yaml`            | CR `Database` ×2 (`dagster`, `pgvector` + extension `vector`) | linté |
| `objectstore.yaml`         | CR `ObjectStore` S3 (endpoint/creds paramétrables)            | linté |
| `init-buckets.yaml`        | Job créant le bucket S3 (à lancer **avant** le Cluster)       | linté |
| `backup.yaml`              | `ScheduledBackup` (plugin)                                    | linté |
| `secret.example.yaml`      | patron creds S3 versionné (`.example`)                        | linté |

## Prérequis impératifs

1. **cert-manager** déployé (le plugin Barman exige du TLS plugin↔operator).
2. **Feature gate Kubernetes `ImageVolume=true`** (apiserver + kubelet) — requis
   par les Image Volume Extensions (la voie pgvector sans image custom). Beta en
   K8s 1.33+ mais **NON activée par défaut**. Le bootstrap l'active (config
   kubeadm, rôle `k8s-initialization` — cf.
   [ADR 0006](../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
   Sans ce flag : `extension "vector" is not available`.
3. Un **provisioner de stockage** (RWO) pour les PVC.

## Déploiement — ordre

```bash
# 1. operator (server-side : CRDs volumineuses) + plugin Barman
kubectl apply --server-side -f platform/cloudnative-pg/operator.yaml
kubectl -n cnpg-system rollout status deploy/cnpg-controller-manager
kubectl apply --server-side -f platform/cloudnative-pg/plugin-barman-cloud.yaml

# 2. credentials S3 + bucket de sauvegarde (avant le Cluster, sinon NoSuchBucket)
kubectl apply -f platform/cloudnative-pg/secret.example.yaml   # renommer/surcharger selon la topologie
kubectl apply -f platform/cloudnative-pg/init-buckets.yaml
kubectl -n postgres wait --for=condition=complete job/cnpg-init-buckets

# 3. ObjectStore (S3) + Cluster (provisionne les 3 instances + pgvector)
kubectl apply -f platform/cloudnative-pg/objectstore.yaml
kubectl apply -f platform/cloudnative-pg/cluster.yaml

# 4. bases logiques (CREATE DATABASE + CREATE EXTENSION vector) + backup planifié
kubectl apply -f platform/cloudnative-pg/database.yaml
kubectl apply -f platform/cloudnative-pg/backup.yaml
```

## Points de surcharge par topologie (jamais de valeur réelle versionnée — ADR 0023)

| Paramètre                             | Banc léger (Lima/kind)            | Topologie bare-metal                            |
| ------------------------------------- | --------------------------------- | ----------------------------------------------- |
| `storage.storageClass` (cluster.yaml) | `standard`/`local-path`           | `rook-ceph-block-replicated` (RBD ×3, ADR 0001) |
| `endpointURL` (objectstore.yaml)      | SeaweedFS `seaweedfs.s3.svc:8333` | RGW Ceph `rook-ceph-rgw-datalake.rook-ceph:80`  |
| Secret `pg-backup-s3`                 | `secret.example.yaml` (test)      | Secret non versionné (config locale)            |

## Adaptations

- **Images épinglées par digest d'index multi-arch**
  ([ADR 0006](../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
- **3 instances HA** (1 primary + 2 replicas, réplication streaming).
- **RBD réplication ×3, jamais EC 2+1** pour ce stateful
  ([ADR 0001](../../docs/decisions/0001-replication-x3-pour-workloads-bloc.md) :
  EC bloque l'I/O à la perte d'un hôte).
- pgvector via **Image Volume Extension** (`cluster.yaml`
  `postgresql.extensions`) ; nom SQL de l'extension = **`vector`** (pas
  `pgvector`).

## Validation

Sur le banc léger : Cluster `Healthy`, `CREATE EXTENSION vector` OK, colonne
`vector(384)` + requête kNN (`<->`), base `dagster` créée, et **sauvegarde
testée** (base + WAL archivés dans le bucket S3). Cf.
[`bootstrap/state.sh`](../../bootstrap/state.sh) (section CloudNativePG).

## Régénérer les manifestes vendored

```bash
curl -sL https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.29/releases/cnpg-1.29.1.yaml -o operator.yaml
curl -sL https://github.com/cloudnative-pg/plugin-barman-cloud/releases/download/v0.12.0/manifest.yaml -o plugin-barman-cloud.yaml
# puis réinjecter les digests d'index multi-arch (cf. ADR 0006).
```
