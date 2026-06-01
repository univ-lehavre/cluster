# Sauvegarde des données applicatives

Stratégie de sauvegarde des **données applicatives** (PVC bloc/CephFS) par
**VolumeSnapshots CSI** Ceph, en complément de la sauvegarde **etcd** (rôle
[`etcd-backup`](../../../bootstrap/roles/etcd-backup/)). Décision et limites :
[ADR 0013](../../../docs/decisions/0013-sauvegarde-donnees-applicatives.md).

> ⚠️ **Couverture.** Les VolumeSnapshots protègent de la **suppression
> accidentelle** et de la **corruption logique** — pas d'une **perte totale du
> cluster** (ils vivent dans le même Ceph). Voir l'ADR pour les évolutions
> off-site.

## Contenu

| Fichier                                                        | Rôle                                                                       |
| -------------------------------------------------------------- | -------------------------------------------------------------------------- |
| [`volume-snapshot-class.yaml`](volume-snapshot-class.yaml)     | `VolumeSnapshotClass` RBD + CephFS (`deletionPolicy: Retain`)              |
| [`snapshot-cronjob.yaml`](snapshot-cronjob.yaml)               | `CronJob` quotidien + RBAC : snapshote les PVC `backup=daily`, rétention 7 |
| [`block-replicated-retain.yaml`](block-replicated-retain.yaml) | StorageClass bloc ×3 en `reclaimPolicy: Retain` (volumes précieux)         |

## Installation

```bash
kubectl apply -f storage/ceph/backup/volume-snapshot-class.yaml
kubectl apply -f storage/ceph/backup/block-replicated-retain.yaml
kubectl apply -f storage/ceph/backup/snapshot-cronjob.yaml
```

## Protéger un volume

1. **Le rendre récupérable** : créer le PVC avec
   `storageClassName: rook-ceph-block-replicated-retain` (un `delete pvc` ne
   détruira plus le volume).
2. **L'inclure dans les snapshots quotidiens** : labelliser le PVC.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mydata
  labels:
    backup: daily # ← pris en charge par le CronJob
spec:
  storageClassName: rook-ceph-block-replicated-retain
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
```

Pour un PVC **CephFS** (RWX), surcharger la classe de snapshot du CronJob
(`SNAPCLASS=csi-cephfsplugin-snapclass`) ou créer un CronJob dédié.

## Restaurer un volume depuis un snapshot

```bash
# Lister les snapshots d'un PVC
kubectl get volumesnapshot -n <ns> -l backup-of=<pvc>

# Créer un nouveau PVC à partir d'un snapshot
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: <pvc>-restored
  namespace: <ns>
spec:
  storageClassName: rook-ceph-block-replicated-retain
  dataSource:
    name: <nom-du-volumesnapshot>
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi # ≥ taille du snapshot
EOF
```

Puis re-pointer l'application sur `<pvc>-restored` (ou copier les données).

## RPO / RTO

- **RPO** ≈ 24 h (schedule du CronJob `30 2 * * *`), réductible par PVC.
- **RTO** : quelques minutes (création d'un PVC `dataSource`).
- **Rétention** : 7 snapshots par PVC (`KEEP` dans le CronJob).

## À valider sur le banc

Scénario dédié à ajouter (esprit du
[`09-etcd-restore.sh`](../../../test/scenarios/09-etcd-restore.sh)) : écrire une
donnée → snapshot → supprimer/corrompre → restaurer via `dataSource` → vérifier
le retour de la donnée.
