# bootstrap

Playbooks Ansible et scripts d'installation initiale de Kubernetes sur un parc
de serveurs Debian.

## Contenu

| Fichier                                      | Rôle                                                       |
| -------------------------------------------- | ---------------------------------------------------------- |
| [`hosts.yaml`](hosts.yaml)                   | Inventaire Ansible (groupes `control`, `workers`, `vm`)    |
| [`checks.yaml`](checks.yaml)                 | Vérifications préalables                                   |
| [`cri.yaml`](cri.yaml)                       | Installation de la runtime conteneur                       |
| [`kubeadm.yaml`](kubeadm.yaml)               | Installation des paquets kubeadm/kubelet/kubectl           |
| [`control-planes.yaml`](control-planes.yaml) | Configuration des nœuds control plane                      |
| [`initialisation.yaml`](initialisation.yaml) | Initialisation du cluster avec `kubeadm init`              |
| [`cni.sh`](cni.sh)                           | Installation du CNI Cilium (à lancer sur le control plane) |
| [`join-workers.yaml`](join-workers.yaml)     | Ajout des nœuds workers                                    |
| [`os-upgrade.yaml`](os-upgrade.yaml)         | Mise à jour OS de l'ensemble du parc                       |
| [`k8s-upgrade.yaml`](k8s-upgrade.yaml)       | Upgrade Kubernetes in-place, séquencé (ADR 0015)           |
| [`roles/`](roles/)                           | Rôles Ansible utilisés par les playbooks                   |

## Procédure complète

Voir [`RUNBOOK.md`](RUNBOOK.md).
