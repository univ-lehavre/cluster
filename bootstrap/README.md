# bootstrap

Playbooks Ansible et scripts d'installation initiale de Kubernetes sur un parc
de serveurs Debian.

## Prérequis du poste de contrôle

Les playbooks **plateforme/Ceph** (`dataops`, `ceph-*`, `monitoring`,
`metrics-server`, `local-path`, `cnpg-secrets`, `gitops`) pilotent l'API
Kubernetes via la collection `kubernetes.core` **depuis le poste de contrôle**
(`localhost`), pas depuis un nœud. Cette collection exige le client Python
`kubernetes` (+ `certifi`). Ces libs sont **versionnées** (`pyproject.toml`,
`uv.lock`) et provisionnées dans le `.venv` du dépôt — y compris sur un
contrôleur macOS « externally-managed » où le `pip` système échoue (ADR
0006/0023, [#277]). Avant de jouer ces playbooks :

```sh
uv sync   # à la racine du dépôt — crée/maj .venv avec kubernetes + certifi
```

L'interpréteur Python de `localhost` est dirigé vers ce `.venv` par le groupe
`control_host`
([`group_vars/control_host.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/group_vars/control_host.yaml)).
L'inventaire d'exemple
([`hosts.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/hosts.example.yaml))
montre la déclaration de ce groupe ; un `.venv` placé ailleurs se surcharge par
hôte. Si les libs manquent, ces playbooks **échouent tôt** avec un rappel
`uv sync` (garde en `pre_tasks`).

[#277]: https://github.com/univ-lehavre/cluster/issues/277

## Contenu

Index **par phase** (lisibilité — ADR 0070). L'ordre canonique d'exécution vit
dans le [`RUNBOOK.md`](/cluster/bootstrap/RUNBOOK/) et le DAG des couches
([ADR 0069](/cluster/docs/decisions/0069-topology-layers-dag-grain-phase/)) ; ce
tableau regroupe les playbooks par rôle, il ne prescrit pas la séquence.

### Installation (socle k8s)

| Fichier                                                                                                  | Rôle                                                                                                                                                 |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`hosts.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/hosts.example.yaml)   | Modèle d'inventaire générique (l'inventaire réel est dérivé de la topologie active par `nestor ansible`, plus de `hosts.yaml` persistant — ADR 0098) |
| [`checks.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/checks.yaml)                 | Vérifications préalables                                                                                                                             |
| [`cri.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/cri.yaml)                       | Installation de la runtime conteneur                                                                                                                 |
| [`kubeadm.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/kubeadm.yaml)               | Installation des paquets kubeadm/kubelet/kubectl                                                                                                     |
| [`control-planes.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/control-planes.yaml) | Configuration des nœuds control plane                                                                                                                |
| [`initialisation.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/initialisation.yaml) | Initialisation du cluster avec `kubeadm init`                                                                                                        |
| [`cni.sh`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/cni.sh)                           | Installation du CNI Cilium (à lancer sur le control plane)                                                                                           |

### Extension HA / join

| Fichier                                                                                                          | Rôle                                                            |
| ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| [`kube-vip.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/kube-vip.yaml)                     | VIP de l'API control plane (kube-vip) — topologie HA (ADR 0047) |
| [`join-control-plane.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/join-control-plane.yaml) | Promotion d'un nœud en control plane supplémentaire (etcd 2/3)  |
| [`join-workers.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/join-workers.yaml)             | Ajout des nœuds workers                                         |

### Storage & platform

| Fichier                                                                                                            | Rôle                                                              |
| ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| [`local-path.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/local-path.yaml)                   | StorageClass local-path (profil léger sans Ceph)                  |
| [`ceph-checks.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/ceph-checks.yaml)                 | Vérifications préalables Rook-Ceph (devices, prérequis)           |
| [`ceph-cluster.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/ceph-cluster.yaml)               | Déploiement du cluster Rook-Ceph                                  |
| [`ceph-storageclasses.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/ceph-storageclasses.yaml) | StorageClasses bloc/CephFS (ADR 0001)                             |
| [`ceph-datalake.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/ceph-datalake.yaml)             | Datalake S3 (RGW, erasure coding 2+1 — ADR 0004)                  |
| [`metrics-server.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/metrics-server.yaml)           | metrics-server (`kubectl top`, HPA — ADR 0016/0068)               |
| [`monitoring.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/monitoring.yaml)                   | Pile d'observabilité (Prometheus/Grafana/Loki)                    |
| [`gitops.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/gitops.yaml)                           | Socle GitOps : Gitea (forge intra-banc) + Argo CD — ADR 0022/0044 |
| [`dataops.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/dataops.yaml)                         | Chaîne DataOps (Dagster, Marquez — ADR 0026/0028)                 |
| [`cnpg-secrets.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/cnpg-secrets.yaml)               | Secrets CloudNativePG (PostgreSQL managé — ADR 0024)              |

### Ops & maintenance

| Fichier                                                                                                          | Rôle                                                      |
| ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| [`os-upgrade.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/os-upgrade.yaml)                 | Mise à jour OS de l'ensemble du parc                      |
| [`k8s-upgrade.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/k8s-upgrade.yaml)               | Upgrade Kubernetes in-place, séquencé (ADR 0015)          |
| [`etcd-backup.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/etcd-backup.yaml)               | Sauvegarde etcd horaire (timer systemd) — control plane   |
| [`etcd-fetch.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/etcd-fetch.yaml)                 | Copie hors-nœud du dernier snapshot etcd (audit P1 #3)    |
| [`audit-log-baseline.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/audit-log-baseline.yaml) | Initialise le journal d'audit-log sur des nœuds existants |
| [`rollback.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/rollback.yaml)                     | Rollback du bootstrap K8s (DESTRUCTIF — `-e confirm=yes`) |
| [`state.sh`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/state.sh)                               | Classification d'état d'un nœud/hôte (couche bootstrap)   |
| [`roles/`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/roles)                                    | Rôles Ansible utilisés par les playbooks                  |

## Les quatre « topology » du dépôt

Quatre objets portent le mot _topology_, à ne pas confondre :

- **`nestor/`** — le paquet Python (logique pure : chargement, dérivation, rendu
  d'une topologie).
- **`scripts/topology.py`** — la façade CLI (l'outil `cluster`).
- **`topologies/`** — le catalogue de données (les `*.example.yaml`).
- **`topology.yaml`** — le symlink d'activation (gitignoré) qui désigne la
  topologie active du déploiement courant.

## Procédure complète

Voir [`RUNBOOK.md`](/cluster/bootstrap/RUNBOOK/).
