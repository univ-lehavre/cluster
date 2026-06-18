# Guide du développeur data — la référence d'interface

Cette page est la **référence** des points d'accès de la plateforme pour le
développeur data : la liste des services à joindre, leurs ports, et les
conventions de secrets et de stockage. C'est un aide-mémoire à consulter, pas un
parcours à suivre.

> **Pour _faire_, pas seulement vérifier :** le mode d'emploi de chaque
> branchement (connexion PostgreSQL, émission de lineage, code-location Dagster,
> stockage…) est dans [Se brancher sur la plateforme](se-brancher.md) ; le
> parcours pas à pas en local est le tutoriel
> [Monter le banc local](banc-local.md). Pour _ce que fait_ et _pourquoi_ chaque
> brique, [composants](composants.md).
>
> **Frontière (ADR [0022](decisions/0022-argocd-gitops-applicatif.md) /
> [0023](decisions/0023-plateforme-exemple-generique.md)).** Ce dépôt décrit
> l'**infrastructure** (générique). Le **code métier** vit dans le dépôt
> applicatif, pas ici. Les valeurs réelles (mots de passe, hostnames) viennent
> d'une config locale non versionnée.
>
> **Version machine-lisible — la source de vérité.** Cette table (et les
> StorageClasses, namespaces, conventions de secrets) est aussi publiée comme
> **contrat versionné** sous [`contract/`](../contract/) — diff-able et
> consommable par un script
> ([ADR 0043](decisions/0043-contrat-interface-cluster-atlas.md)). En cas
> d'écart, **le contrat fait foi** ; cette page en est la version lisible.

## Points d'accès (services intra-cluster)

Toutes les adresses sont des **services Kubernetes intra-cluster** (DNS
`*.svc.cluster.local`) : votre code tourne **dans un pod du cluster**, dans un
namespace autorisé par les NetworkPolicies.

| Brique               | Service (intra-cluster)                      | Port | Auth (Secret)                        |
| -------------------- | -------------------------------------------- | ---- | ------------------------------------ |
| PostgreSQL (CNPG)    | `pg-rw.postgres.svc.cluster.local` (primary) | 5432 | Secret du rôle (`pg-role-<rôle>`)    |
| PostgreSQL (replica) | `pg-ro.postgres.svc.cluster.local` (lecture) | 5432 | idem                                 |
| Marquez (lineage)    | `marquez.marquez.svc.cluster.local`          | 5000 | aucune (intra-cluster)               |
| MLflow (modèles)     | `mlflow.mlflow.svc.cluster.local`            | 5000 | aucune (intra-cluster)               |
| Registry d'images    | `registry:80` (sur les nœuds)                | 80   | aucune (HTTP interne, ADR 0011)      |
| S3 datalake (RGW)    | `rook-ceph-rgw-datalake.rook-ceph`           | 80   | creds d'un `ObjectBucketClaim`       |
| Gitea (forge GitOps) | `gitea-http.gitea.svc.cluster.local`         | 80   | Secret `gitea-admin` (mot de passe)  |
| Argo CD (GitOps)     | `argocd-server.argocd.svc.cluster.local`     | 80   | Secret `argocd-initial-admin-secret` |

Exposition **hors cluster** (UI) via le Gateway Cilium + TLS interne
([ADR 0020](decisions/0020-exposition-reseau-tout-cilium.md)/[0021](decisions/0021-cert-manager-ca-interne.md))
: p. ex. `https://dagster.cluster.lan`, `https://marquez.cluster.lan` (hostnames
`*.cluster.lan` = **placeholders génériques** ; l'admin réseau pose les vrais).

## Bases logiques PostgreSQL

Un cluster HA unique `pg` (namespace `postgres`) porte **trois bases logiques**,
chacune avec son rôle propriétaire
([ADR 0024](decisions/0024-postgres-manage-cloudnative-pg.md)) :

| Base       | Rôle (login) | Usage                                                                  |
| ---------- | ------------ | ---------------------------------------------------------------------- |
| `dagster`  | `dagster`    | event log de l'orchestrateur                                           |
| `pgvector` | `pgvector`   | recherche sémantique (extension SQL [`vector`](glossaire.md#pgvector)) |
| `marquez`  | `marquez`    | store de lineage (migrations [Flyway](glossaire.md#flyway))            |

Le mot de passe d'un rôle est dans le Secret `pg-role-<rôle>` (clé `password`,
namespace `postgres`). Connexion : écrire (`pg-rw`) ou lire (`pg-ro`). La
**procédure** (lire le Secret, exemple psycopg) est dans
[Se brancher → PostgreSQL](se-brancher.md#base-de-données-postgresql-cloudnativepg).

## StorageClasses disponibles

Le « catalogue » de types de stockage
([StorageClass](glossaire.md#storageclass)) — défaut =
`rook-ceph-block-replicated` (RBD ×3,
[ADR 0001](decisions/0001-replication-x3-pour-workloads-bloc.md)) :

| StorageClass                 | Profil                                 |
| ---------------------------- | -------------------------------------- |
| `rook-ceph-block-replicated` | RBD ×3 — **défaut**, stateful critique |
| `rook-ceph-block-ec`         | erasure coded — gros volumes tolérants |
| `rook-cephfs`                | RWX (partagé multi-pods)               |
| `rook-ceph-datalake`         | objet S3 (via `ObjectBucketClaim`)     |

La **procédure** (PVC type, ObjectBucketClaim) est dans
[Se brancher → Stockage](se-brancher.md#stockage-réclamer-du-bloc-ou-de-lobjet).

## Variables OpenLineage

Le client OpenLineage standard lit ces variables pour émettre vers
[Marquez](composants.md#marquez-et-openlineage-lineage) :

| Variable                | Valeur (intra-cluster)                           |
| ----------------------- | ------------------------------------------------ |
| `OPENLINEAGE_URL`       | `http://marquez.marquez.svc.cluster.local:5000`  |
| `OPENLINEAGE_ENDPOINT`  | `api/v1/lineage`                                 |
| `OPENLINEAGE_NAMESPACE` | le namespace logique de vos jobs (ex. `dagster`) |

## Variable MLflow

Pendant de `OPENLINEAGE_URL` pour le **suivi de modèles** : le client MLflow lit
cette variable pour logger ses runs vers
[MLflow](composants.md#mlflow-suivi-de-modèles) (serveur livré vide, peuplé par
atlas) :

| Variable              | Valeur (intra-cluster)                        |
| --------------------- | --------------------------------------------- |
| `MLFLOW_TRACKING_URI` | `http://mlflow.mlflow.svc.cluster.local:5000` |

> ⚠️ **Pour que vos RUNS Dagster voient cette variable** (pas seulement la
> code-location) : déclarez-la via un tag `dagster-k8s/config`
> (`container_config.env`) sur vos jobs — les env du pod de la code-location
> gRPC **ne se propagent pas** aux pods de run du K8sRunLauncher. Sinon le
> logging MLflow est un no-op silencieux (run SUCCESS mais rien de loggé).
> Détail : note `dagster-webserver` du
> [contrat](../contract/endpoints.example.yaml).

La **procédure** (logger un run, exemple Python) est dans
[Se brancher → Suivi de modèles](se-brancher.md#suivi-de-modèles-logger-avec-mlflow).

## Pour aller plus loin

- Mode d'emploi de chaque branchement :
  [Se brancher sur la plateforme](se-brancher.md).
- Parcours en local, de zéro : [Monter le banc local](banc-local.md).
- Présentation des briques : [composants](composants.md). Décisions :
  [index ADR](decisions/). Chaque brique a son README dans `platform/<brique>/`
  et `storage/ceph/`.
- Mettre la plateforme en place :
  [`bootstrap/dataops.yaml`](../bootstrap/dataops.yaml)
  ([ADR 0033](decisions/0033-orchestration-ansible-platform-dataops.md)).
