# 0004 — Erasure coding 2+1 réservé au datalake

## Contexte

Le datalake stocke des sources de données **ré-ingestibles** (p. ex. corpus
ouverts, API publiques, exports périodiques) sur Ceph RGW. Volumes attendus :
plusieurs dizaines de TiB cumulés à terme. Les caractéristiques métier :

- **Données ré-ingestibles** depuis les sources upstream (en cas de perte, on
  re-télécharge ; coût = temps de ré-ingestion, pas perte d'information unique).
- **Disponibilité non-critique** : un blocage I/O temporaire pendant la
  maintenance d'un nœud est acceptable.
- **Coût stockage important** vs valeur de chaque octet.

Sur 4 hôtes, l'erasure coding atteint au maximum **EC 2+1** (k+m = 3, laissant 1
hôte de marge pour `failureDomain: host`). EC 2+2 (=4) saturait la topologie et
ne tolérait plus aucune maintenance.

## Décision

Le data pool du `CephObjectStore datalake` est en **EC 2+1**
(`dataChunks: 2, codingChunks: 1`) — cf.
[`storage/ceph/storageClass/datalake/datalake-ec.yaml`](../../storage/ceph/storageClass/datalake/datalake-ec.yaml).

Le **pool de métadonnées** du même CephObjectStore est en réplication
`size: 3 + requireSafeReplicaSize: true` (Ceph déconseille fortement `size: 2`
pour les métadonnées d'un object store).

Les classes bloc `rook-ceph-block-ec-delete` et `rook-ceph-block-ec-retain`
restent disponibles pour des usages tolérants (archives), mais aucun workload
critique ne s'y rattache (cf.
[ADR 0001](0001-replication-x3-pour-workloads-bloc.md)).

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- **Coût stockage divisé par 2** vs réplication ×3 (×1,5 vs ×3) → ~176 TiB
  utiles vs ~88 TiB pour la même empreinte brute.

**Coûts assumés.**

- **`min_size = 3` par défaut sur EC 2+1** : la perte d'un hôte bloque les I/O
  jusqu'au remplacement. Acceptable pour le datalake (lecture intermittente, pas
  critique).
- **Pas de bascule warm** : récupération impose la reconstruction du chunk de
  parité (CPU + I/O sur les nœuds restants).

**Garde-fous.**

- `preservePoolsOnDelete: false` (cf.
  [ADR 0004 bis dans le RUNBOOK Ceph](../../storage/ceph/RUNBOOK.md)) :
  supprimer le `CephObjectStore` détruit les pools et toutes les données —
  assumé pour un datalake ré-ingestible, à signaler pour ne pas le faire par
  mégarde.
- Sauvegarde upstream des sources d'ingestion : si une source disparaît
  (rate-limit, dépreciation API), on perd la capacité de reconstruire.
- `rook-ceph-block-replicated` reste la SC par défaut pour les workloads
  critiques (cf. ADR 0001).
