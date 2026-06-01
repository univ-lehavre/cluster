# 0013 — Sauvegarde des données applicatives (VolumeSnapshots CSI)

## Contexte

Seul **etcd** est sauvegardé (rôle
[`etcd-backup`](../../bootstrap/roles/etcd-backup/), restauration prouvée par
[`test/scenarios/09-etcd-restore.sh`](../../test/scenarios/09-etcd-restore.sh)).
Les **données applicatives** — PVC bloc (MySQL/WordPress, registry, RStudio) et
buckets S3 du datalake — ne le sont pas.

La réplication Ceph (`size: 3`, `failureDomain: host`) protège du **crash
matériel** (perte d'un disque, d'un nœud), mais **pas** :

- d'une **suppression accidentelle** (`kubectl delete pvc`,
  `delete CephObjectStore`) ;
- d'une **corruption logique** applicative (une mauvaise migration SQL, un bug
  qui écrase des données) ;
- d'un **ransomware** / chiffrement malveillant des volumes.

Aggravant : la StorageClass bloc par défaut est en `reclaimPolicy: Delete` et le
datalake en `preservePoolsOnDelete: false` — un `delete` de PVC ou de
`CephObjectStore` est aujourd'hui **irréversible** (cf. audit
[08-operabilite](../audit/08-operabilite.md)).

## Décision

**Sauvegarde par VolumeSnapshots CSI natifs (Ceph-CSI), programmés.**

1. **VolumeSnapshotClass** RBD et CephFS (Ceph-CSI), `deletionPolicy: Retain`
   pour que la suppression d'un `VolumeSnapshot` ne détruise pas le snapshot
   Ceph sous-jacent. Voir [`storage/ceph/backup/`](../../storage/ceph/backup/).
2. **Snapshots programmés** via un `CronJob` Kubernetes qui crée des
   `VolumeSnapshot` horodatés des PVC critiques et applique une **rétention**
   (les N derniers, comme etcd). RPO cible : **24 h** (snapshot quotidien) ;
   ajustable par PVC selon la criticité.
3. **`reclaimPolicy: Retain`** sur les StorageClasses précieuses (les volumes
   applicatifs persistants), pour qu'un `delete pvc` libère la réclamation mais
   **conserve** le volume Ceph (récupérable). Les volumes jetables/éphémères
   restent en `Delete`.

### RPO / RTO

- **RPO** (perte de données max) : 24 h en nominal (fréquence du CronJob),
  réductible par PVC.
- **RTO** (temps de restauration) : restauration d'un PVC depuis un
  `VolumeSnapshot` = création d'un nouveau PVC `dataSource` → quelques minutes.
- **etcd** : couvert séparément (horaire, cf. rôle etcd-backup).

## Statut

Accepted (2026-06-01).

## Conséquences

**Bénéfices.**

- Couvre la suppression accidentelle et la corruption logique — les angles morts
  que la réplication ne traite pas.
- Aucune dépendance nouvelle lourde : VolumeSnapshots sont natifs K8s + Ceph-CSI
  (déjà déployé via `ROOK_USE_CSI_OPERATOR: "false"`, cf. ADR/drift #8/#9).
- `reclaimPolicy: Retain` rend les suppressions non destructrices.

**Limites assumées (et pistes).**

- **In-cluster** : les VolumeSnapshots vivent dans le **même cluster Ceph** que
  les données. Ils ne protègent **pas** d'une perte **totale** du cluster
  (incendie, destruction des 4 nœuds). Pour un vrai off-site, une étape
  ultérieure exporterait les snapshots (ou les buckets S3) hors-cluster — non
  couvert ici, tracé comme évolution.
- **Buckets S3 datalake** : les VolumeSnapshots couvrent les PVC bloc/CephFS,
  pas les objets S3 RGW. Le datalake est **ré-ingestible depuis les sources
  upstream** (hypothèse déjà posée pour `preservePoolsOnDelete: false`) ; une
  réplication S3 dédiée reste une évolution possible si le coût de ré-ingestion
  devient prohibitif.
- **Cohérence applicative** : un snapshot de volume est _crash-consistent_, pas
  _application-consistent_ (une base SQL active peut nécessiter un quiesce).
  Pour MySQL, un `mysqldump` logique complémentaire serait plus sûr — noté comme
  amélioration.

**Coûts.**

- Espace : chaque snapshot consomme l'espace des blocs modifiés depuis le
  précédent (copy-on-write Ceph) — la rétention borne la consommation.
- Un CronJob + RBAC à maintenir.

## Validation

VolumeSnapshotClass + création/restauration d'un snapshot à valider sur le banc
multi-node (scénario dédié à ajouter, dans l'esprit du 09 etcd-restore : créer
une donnée → snapshot → corrompre/supprimer → restaurer → vérifier).
