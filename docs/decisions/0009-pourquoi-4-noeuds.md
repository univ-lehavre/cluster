# 0009 — Pourquoi 4 nœuds ?

## Contexte

Le dimensionnement d'un cluster Ceph + K8s est rarement neutre : il résulte d'un
compromis entre contraintes matérielles, modèle de panne acceptable, et capacité
visée. Pour ce cluster de recherche, le parc disponible est un châssis HPE
Apollo 2000 Gen10+ pouvant héberger 4 lames XL420.

## Décision

**4 nœuds rigoureusement identiques** : `dirqual1-4` (10.67.2.11-14).

Topologie associée :

- 1 control plane + 3 workers (cf.
  [ADR 0002](0002-control-plane-unique-avec-endpoint.md))
- 48 OSDs Ceph (12/nœud × 4) + 4 NVMe block.db
- 3 mon Ceph + 1 mon en réserve

## Statut

Accepted (2026-05-28).

## Conséquences

### Pourquoi 4 et pas autre chose ?

**Pourquoi pas 3 ?**

- 3 nœuds = minimum strict pour Ceph (quorum mon + `failureDomain: host` sur ×3)
  → **zéro marge** pour la maintenance.
- Si on drain 1 nœud pour reboot, le cluster est à 2 nœuds → la perte d'un nœud
  en plus ne tient pas le ×3 → I/O bloquées.
- Toute opération de maintenance devient risquée.

**Pourquoi pas 5 ?**

- Permettrait 5 mon (plus de tolérance Byzantine, mais c'est inutile à notre
  échelle).
- Coût matériel supérieur sans bénéfice opérationnel net.
- Sortirait du format châssis Apollo 2000 (4 lames).

**Pourquoi 4 ?**

- **Châssis unitaire** : 4 lames XL420 = 1 Apollo 2000 = une unité d'achat
  naturelle, racable d'un bloc.
- **Maintenance + tolérance simultanées** : drainer 1 nœud laisse 3 nœuds
  opérationnels → on garde le quorum mon (3 mon) + ×3 sur 3 hôtes restants.
  C'est la **première topologie qui autorise la maintenance** sans dégrader la
  tolérance de panne.
- **EC 2+1 max possible** (`failureDomain: host` → hôtes ≥ k+m = 3 ; 4 hôtes
  laisse 1 hôte de marge). EC 2+2 (=4) saturerait. → justifie réplicat ×3 pour
  le critique + EC 2+1 pour le datalake (cf.
  [ADR 0001](0001-replication-x3-pour-workloads-bloc.md),
  [ADR 0004](0004-erasure-coding-2plus1-datalake.md)).

### Bilan de capacité

| Ressource     | Par nœud        | Cluster total       |
| ------------- | --------------- | ------------------- |
| RAM           | 251 GiB         | ~1 TiB              |
| CPU           | 40 c / 80 t     | 160 c / 320 t       |
| HDD brut      | 12 × 5,5 TiB    | 264 TiB             |
| HDD ×3        | —               | **~88 TiB utiles**  |
| HDD EC 2+1    | —               | **~176 TiB utiles** |
| NVMe data     | 2,9 TiB         | 11,6 TiB            |
| NVMe block.db | 2,9 TiB (utile) | 11,6 TiB            |

### Ce que 4 nœuds **ne** donne **pas**

- **Pas de HA control-plane** : 1 control plane unique (cf. ADR 0002). Une HA 3
  nœuds laisserait 1 worker, ce qui n'est pas viable.
- **Pas de tolérance double-panne simultanée** sur les workloads critiques :
  `min_size = 2` sur ×3 ; 2 hôtes perdus → I/O bloquées.
- **Pas de N+2 sur la maintenance** : drainer 2 nœuds en même temps laisse 2
  nœuds → on perd quorum mon dès qu'un 3e nœud bouge.

### Quand revisiter ?

- Si on passe à 8 nœuds (2 châssis) :
  - HA control-plane 3 nœuds réelle devient viable.
  - EC 4+2 envisageable (k+m = 6 ≤ 8).
  - Tolérance double-panne possible.
- Si une charge dépasse les 88 TiB utiles (ou 176 TiB en EC).
- Si on passe en multi-tenants → besoin de marge CPU/RAM accrue.
