# 0002 — Control plane unique avec `--control-plane-endpoint`

## Contexte

Kubernetes en haute disponibilité (HA) exige **3 control planes** pour le quorum
etcd. Le cluster compte 4 nœuds identiques ; passer 3 d'entre eux en control
planes laisserait **1 seul worker** pour les charges applicatives → topologie
peu intéressante pour un cluster de recherche mono-admin où l'on veut maximiser
les ressources de calcul.

Par ailleurs, `kubeadm init` sans `--control-plane-endpoint` pose dans les
manifestes statiques l'**IP** du nœud control plane. Ajouter un 2e ou 3e control
plane plus tard implique alors de **réinstaller tous les workers** (re-join
contre un endpoint partagé).

## Décision

- **1 seul control plane** (`cp1`) — **SPOF assumé**.
- `kubeadm init --control-plane-endpoint cluster-api:6443 --upload-certs` posé
  dès le bootstrap initial (rôle
  [`k8s-initialization`](../../bootstrap/roles/k8s-initialization/) + variables
  [`group_vars/all.yaml`](../../bootstrap/group_vars/all.yaml)).
- L'entrée `cluster-api → 10.0.0.11` est propagée dans `/etc/hosts` sur les 4
  nœuds (rôle `k8s-install`).
- **Sauvegarde etcd horaire**
  ([rôle `etcd-backup`](../../bootstrap/roles/etcd-backup/))
  - procédure de restauration documentée dans
    [`bootstrap/RUNBOOK.md`](../../bootstrap/RUNBOOK.md).

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- 3 workers complets pour les charges (vs 1 si on avait 3 control planes).
- Si la HA devient nécessaire un jour : passer à 3 control planes **sans
  réinstaller** les workers (ils joignent déjà via le nom DNS stable
  `cluster-api`).

**Coûts assumés.**

- **SPOF API + etcd** : la perte de `cp1` rend le cluster inutilisable jusqu'à
  restauration. Mitigation : sauvegarde etcd horaire + procédure de restore
  testée sur le banc multi-nœuds.
- **Pas de HA workloads pendant la maintenance de cp1** : si on reboot cp1,
  l'API est inaccessible quelques minutes. Workloads applicatifs continuent
  (kubelet local) mais aucun nouvel ordonnancement.

**Garde-fous opérationnels.**

- `etcdctl snapshot save` toutes les heures dans `/var/lib/etcd-backups/`
  (rétention 24h).
- [`bootstrap/state.sh`](../../bootstrap/state.sh) couche 3 vérifie
  `kubeadm init` effectif (présence de `/etc/kubernetes/admin.conf`).
- Ne **pas** repointer `cluster-api` ailleurs sans avoir d'abord réinstallé tous
  les workers (sinon ils perdent l'API).
