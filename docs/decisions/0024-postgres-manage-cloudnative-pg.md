# 0024 — PostgreSQL managé via CloudNativePG (+ pgvector)

## Contexte

Le socle DataOps (étape 1.6) a besoin d'un PostgreSQL pour **deux usages** :
l'**event log de Dagster** (orchestrateur, 1.7) et un **index de recherche**
lexical + sémantique via **pgvector** (chargé par le dépôt `atlas`). Plutôt
qu'un Postgres posé à la main (stateful fragile, sauvegardes manuelles, pas de
bascule), on veut un opérateur qui gère le cycle de vie : provisioning,
réplication, bascule, sauvegardes, restauration.

Contraintes du catalogue de topologies : stockage stateful sur RBD réplication
×3 ([ADR 0001](0001-replication-x3-pour-workloads-bloc.md) — pas d'erasure
coding, dont le `min_size` bloque l'I/O à la perte d'un hôte) ; sauvegardes vers
l'objet S3 (RGW Ceph) ; réseau privé sans chiffrement interne supposé
([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)) ; valeurs génériques,
spécificités hors dépôt ([ADR 0023](0023-plateforme-exemple-generique.md)).

## Décision

**CloudNativePG** (operator 1.29.1) comme Postgres managé, dans
[`platform/cloudnative-pg/`](../../platform/cloudnative-pg/), déployé par
`kubectl apply` comme les autres addons.

- **Un Cluster HA, 3 instances** (1 primary + 2 replicas, réplication streaming)
  ; **deux bases logiques** (`dagster`, `pgvector`) — isolation des usages sans
  doubler l'infrastructure stateful.
- **pgvector via Image Volume Extensions** (PostgreSQL 18,
  `spec.postgresql.extensions` montant l'image `pgvector` en volume) — **pas
  d'image Postgres custom à maintenir**. L'extension est déclarée côté
  `Database` (nom SQL **`vector`**) ; l'operator exécute `CREATE EXTENSION`.
  - **Prérequis : feature gate Kubernetes `ImageVolume=true`** (apiserver +
    kubelet). Beta en K8s 1.33+ mais **non activée par défaut** ; le bootstrap
    l'active dans la config kubeadm (rôle `k8s-initialization`), tracé dans
    [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md).
- **Sauvegardes via le plugin Barman Cloud** (v0.12.0) vers l'objet S3 — et
  **non** le `barmanObjectStore` in-tree (déprécié, supprimé en CNPG 1.30). Le
  plugin exige **cert-manager** (TLS plugin↔operator), déjà présent
  ([ADR 0021](0021-cert-manager-ca-interne.md)). WAL archivés en continu +
  sauvegardes de base planifiées (`ScheduledBackup`).
- **Stockage RBD `rook-ceph-block-replicated` (×3)** sur la topologie bare-metal
  ; paramétrable (`local-path` sur le banc léger). Endpoint S3 et credentials
  également **paramétrables** (SeaweedFS sur le banc / RGW Ceph sur la topologie
  cible), via Secret non versionné + patron `secret.example.yaml`.
- Images **épinglées par digest d'index multi-arch**
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).

## Statut

Accepted (2026-06-03). Validé de bout en bout sur le banc léger Lima (K8s v1.34)
: Cluster Healthy, `CREATE EXTENSION vector` + requête kNN, base `dagster`
créée, sauvegarde (base + WAL) écrite dans le bucket S3.

## Conséquences

**Bénéfices.**

- Postgres HA managé (bascule, réplication) au lieu d'un SPOF posé à la main.
- pgvector sans image custom (les extensions suivent leur propre cycle de
  version).
- Sauvegardes/restauration déclaratives vers S3 ; archivage continu (PITR
  possible).
- Deux usages isolés (bases distinctes) sur une seule infrastructure.

**Coûts assumés.**

- **Dépendance à la feature beta `ImageVolume`** : à activer explicitement, et à
  surveiller (passage stable, changement de comportement). Repli documenté :
  image Postgres custom avec pgvector (méthode pré-1.29).
- **Dépendance à cert-manager** pour le plugin Barman (déjà dans le socle).
- Composant stateful supplémentaire (RAM/CPU bornés ; sensible à la
  disponibilité du stockage selon la topologie).

## Alternatives écartées

- **Postgres posé à la main** (StatefulSet + cron de dump) : pas de bascule,
  sauvegardes fragiles, réinvention de ce que l'operator fait.
- **`barmanObjectStore` in-tree** : déprécié, supprimé en CNPG 1.30 → dette
  immédiate.
- **Image Postgres custom avec pgvector** : fonctionne sans feature gate, mais
  impose de construire/maintenir/vendorer une image et fige le couple
  PG↔pgvector. Gardé comme repli.

## À revoir

- Quand `ImageVolume` devient stable (activé par défaut) : retirer le feature
  gate explicite.
- Migrer Promtail→Alloy et brancher les métriques CNPG sur le monitoring
  (ServiceMonitor).
- Restauration testée (PITR) lors de l'industrialisation du banc complet.
