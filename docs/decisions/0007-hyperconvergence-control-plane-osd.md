# 0007 — Hyperconvergence : control plane portant OSDs + charges

## Contexte

Avec 4 nœuds identiques (HPE XL420 Gen10+, 251 GiB RAM, 40 cœurs, 12 HDD 5,5
TiB + NVMe), deux topologies sont possibles :

1. **Dédiée** : N nœuds control plane + (4-N) workers. Ceph OSDs uniquement sur
   les workers. Les control planes ne portent ni OSDs ni charges applicatives.
2. **Hyperconvergée** : tous les nœuds portent tout — control plane, etcd, OSDs
   Ceph, charges applicatives. La séparation est logique (taints/tolerations)
   plutôt que physique.

ADR 0002 a déjà acté un **seul control plane**. Reste à savoir si ce control
plane héberge aussi des OSDs et des pods utilisateurs.

## Décision

**Hyperconvergence assumée** : `cp1` porte le control plane, 12 OSDs, et est
**détainté** pour accepter les pods (rôle
[`k8s-initialization`](../../bootstrap/roles/k8s-initialization/) :
`kubectl taint nodes --all node-role.kubernetes.io/control-plane-`).

Tous les nœuds (`cp1`/`node1-3`) font tourner :

- `kubelet` + `containerd` ;
- les OSDs Ceph (12 HDD par nœud + block.db sur NVMe) ;
- les pods Cilium ;
- les charges applicatives (registry, RStudio, datalake gateways…).

Seul `cp1` ajoute en plus : `kube-apiserver`, `kube-scheduler`,
`kube-controller-manager`, `etcd`.

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- **Aucun nœud "gâché"** : un cluster de 4 nœuds, c'est déjà petit ; en retirer
  un de la pool de calcul pour le dédier au control plane réduit la capacité
  utilisable de 25 %.
- **Cluster Ceph plein 4 nœuds** : 48 OSDs au lieu de 36 → plus de capacité
  brute, meilleure distribution de la charge I/O.
- Toutes les machines sont rigoureusement identiques côté inventaire.

**Coûts assumés.**

- **Contention CPU/RAM** sur `cp1` : le control plane (etcd surtout, sensible
  aux latences disque) cohabite avec 12 OSDs et des pods applicatifs. Mitigation
  : `/var/lib/etcd` sur LV dédié (10 GiB, isole les I/O), 251 GiB RAM laisse de
  la marge.
- **Maintenance de `cp1` plus délicate** : le drain le retire de la pool de
  calcul (OK) mais aussi de l'API (impact API jusqu'au reboot). Voir
  [ADR 0002](0002-control-plane-unique-avec-endpoint.md).
- **etcd I/O sensible** au comportement des autres charges : si une app sature
  `/var`, etcd peut se mettre en `slow-apply`. Compensation : LV `/var/lib/etcd`
  séparé.

**Garde-fous.**

- Partitionnement LVM dédié pour `/var/lib/etcd` (10 GiB, ext4).
- `requests/limits` sur les OSDs (`storage/ceph/cluster.yaml` :
  `osd: {requests: 200m/2Gi, limits: 2/4Gi}`).
- Sauvegarde etcd horaire (cf. ADR 0002).
