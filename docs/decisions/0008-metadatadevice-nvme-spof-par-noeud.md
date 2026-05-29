# 0008 — `metadataDevice` NVMe unique — SPOF par nœud assumé

## Contexte

Chaque nœud dispose de :

- 12 HDD SAS de 5,5 TiB pour les données (les OSDs Ceph) ;
- 1 NVMe de 2,9 TiB destiné au `block.db` Ceph (métadonnées BlueStore + WAL).

Le `block.db` sur NVMe accélère **drastiquement** les opérations métadonnées
(small writes, lookup d'objet, journal BlueStore) — c'est recommandé pour des
OSDs HDD. La doc Ceph suggère ~4 % de la capacité du disque data en block.db (12
× 5,5 TiB × 4 % ≈ 2,6 TiB par nœud → tient sur les 2,9 TiB du NVMe).

Le défi : **un seul NVMe par nœud**, partagé entre les 12 OSDs.

## Décision

[`storage/ceph/cluster.yaml`](../../storage/ceph/cluster.yaml) configure
`metadataDevice: nvme1n1` sur tous les nœuds — l'opérateur Rook découpe le NVMe
en 12 partitions, une par OSD HDD.

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- Performances métadonnées Ceph multipliées vs all-HDD.
- Pas d'achat de matériel supplémentaire (le NVMe existe déjà).

**Coûts assumés — SPOF par nœud.**

- **Si le NVMe d'un nœud meurt → les 12 OSDs du nœud tombent simultanément.** Du
  point de vue Ceph, c'est équivalent à la perte du nœud entier
  (`failureDomain: host`) → la réplication ×3 absorbe (tolère 1 hôte perdu) et
  l'EC 2+1 absorbe aussi (un hôte = 1 chunk perdu sur 3).
- **Pas de dégradation progressive** : la perte est binaire (12 OSDs d'un coup).

**Pourquoi c'est acceptable.**

- Notre `failureDomain` est déjà `host` — la perte d'un hôte est notre modèle de
  panne nominal. Le NVMe-SPOF ne fait que matérialiser ce scénario via un
  composant différent.
- La probabilité de panne simultanée de 2 NVMe sur 2 nœuds différents reste très
  faible (composants NVMe SLC enterprise, MTBF élevé).

**À surveiller.**

- État SMART des NVMe (`smartctl -A /dev/nvme1n1`).
- Si l'un commence à montrer des erreurs, drainer le nœud, remplacer le NVMe,
  recréer les OSDs (Rook le fait automatiquement à la reconnexion).

**Alternative écartée.**

- Découper le block.db sur plusieurs NVMe → nécessiterait du matériel en plus,
  non justifié pour un cluster de recherche.
