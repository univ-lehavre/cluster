# bootstrap

Playbooks Ansible et scripts d'installation initiale de Kubernetes sur un parc
de serveurs Debian.

## Contenu

| Fichier                                              | Rôle                                                                                |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------- |
| [`hosts.example.yaml`](hosts.example.yaml)           | Modèle d'inventaire générique (le `hosts.yaml` réel n'est pas versionné — ADR 0023) |
| [`checks.yaml`](checks.yaml)                         | Vérifications préalables                                                            |
| [`cri.yaml`](cri.yaml)                               | Installation de la runtime conteneur                                                |
| [`kubeadm.yaml`](kubeadm.yaml)                       | Installation des paquets kubeadm/kubelet/kubectl                                    |
| [`control-planes.yaml`](control-planes.yaml)         | Configuration des nœuds control plane                                               |
| [`initialisation.yaml`](initialisation.yaml)         | Initialisation du cluster avec `kubeadm init`                                       |
| [`cni.sh`](cni.sh)                                   | Installation du CNI Cilium (à lancer sur le control plane)                          |
| [`join-workers.yaml`](join-workers.yaml)             | Ajout des nœuds workers                                                             |
| [`os-upgrade.yaml`](os-upgrade.yaml)                 | Mise à jour OS de l'ensemble du parc                                                |
| [`k8s-upgrade.yaml`](k8s-upgrade.yaml)               | Upgrade Kubernetes in-place, séquencé (ADR 0015)                                    |
| [`etcd-backup.yaml`](etcd-backup.yaml)               | Sauvegarde etcd horaire (timer systemd) — control plane                             |
| [`etcd-fetch.yaml`](etcd-fetch.yaml)                 | Copie hors-nœud du dernier snapshot etcd (audit P1 #3)                              |
| [`audit-log-baseline.yaml`](audit-log-baseline.yaml) | Initialise le journal d'audit-log sur des nœuds existants                           |
| [`rollback.yaml`](rollback.yaml)                     | Rollback du bootstrap K8s (DESTRUCTIF — `-e confirm=yes`)                           |
| [`gitops.yaml`](gitops.yaml)                         | Socle GitOps : Gitea (forge intra-banc) + Argo CD (moteur) — ADR 0022/0044          |
| [`roles/`](roles/)                                   | Rôles Ansible utilisés par les playbooks                                            |

## Procédure complète

Voir [`RUNBOOK.md`](RUNBOOK.md).
