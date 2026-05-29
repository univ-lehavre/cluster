# 0001 — Réplication ×3 pour les workloads bloc (vs EC)

## Contexte

Le cluster Ceph propose deux modes de redondance pour le stockage bloc (RBD) :

- **Réplication ×3** : chaque objet est copié sur 3 OSDs (3 hôtes distincts
  grâce à `failureDomain: host`). Coût stockage = ×3.
- **Erasure coding (EC)** `k=2, m=1` : chaque objet est découpé en 2 chunks
  données + 1 chunk parité, répartis sur 3 hôtes. Coût stockage = ×1,5.

Sur **4 hôtes**, EC 2+1 a un **piège `min_size`** : par défaut,
`min_size = k + 1 = 3`. La perte d'**un seul hôte** fait passer le pool sous
`min_size` et **bloque toutes les I/O** jusqu'au remplacement — pas de perte de
données, mais interruption applicative.

Les workloads applicatifs (registry, MySQL, RStudio, dashboard) ont besoin de
tolérance de panne **sans interruption** lors de la maintenance d'un nœud
(drain + reboot).

## Décision

Tous les workloads **bloc** utilisent `rook-ceph-block-replicated` (réplication
×3), qui est la **StorageClass par défaut** du cluster (annotation
`storageclass.kubernetes.io/is-default-class: "true"`).

Les pools EC restent disponibles pour des données tolérantes (datalake,
archives) via les classes `rook-ceph-block-ec-delete` et
`rook-ceph-block-ec-retain` — mais leurs pools de **métadonnées** sont durcis en
`replicated size: 3 + requireSafeReplicaSize: true` (Ceph déconseille
`size: 2`).

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- Tolère la perte d'**un hôte** sans interruption I/O (`min_size = 2` par défaut
  sur un pool répliqué ×3).
- Maintenance d'un nœud (drain + reboot) sans dégradation pour les applications.

**Coûts assumés.**

- **Coût stockage doublé** vs EC : 88 TiB utiles ×3 au lieu de 176 TiB ×1,5 sur
  264 TiB brut. Acceptable pour les workloads applicatifs (volumes modestes : 1
  Ti registry, 20 Gi MySQL/WP, 1 Ti RStudio).
- L'EC reste utile pour le **datalake** où le coût stockage prime sur la
  disponibilité (ré-ingestible).
