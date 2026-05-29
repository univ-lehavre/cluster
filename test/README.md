# Bancs de test locaux (VirtualBox)

Deux bancs Vagrant à choisir selon la phase à valider :

| Banc                           | Topologie       | Disques Ceph | Phases couvertes                  | Démarrage |
| ------------------------------ | --------------- | ------------ | --------------------------------- | --------- |
| [`single-node/`](single-node/) | 1 VM            | aucun        | 1 (OS/runtime), 2 (init + Cilium) | ~5 min    |
| [`multi-node/`](multi-node/)   | 3 VMs + privnet | 3 HDD + NVMe | 1, 2 (avec join), 3 (Ceph), 4, 5  | ~15 min   |

## Quand utiliser lequel ?

- **`single-node/`** : itération rapide sur les rôles Ansible (`checks`, `cri`,
  `kubeadm`, `initialisation`), validation d'un changement de version
  (containerd, kubeadm, Cilium). Pas de Ceph, pas de join.
- **`multi-node/`** : validation de bout en bout avant le déploiement serveurs —
  exerce `join-workers`, les pré-requis disques pour Ceph, le quorum mon (3
  nœuds), la mise en place des StorageClasses et des workloads applicatifs.

Une fois validé sur `single-node/`, repasser **systématiquement** sur
`multi-node/` avant de toucher la prod — c'est le seul endroit où l'on exerce le
multi-VM et les disques Ceph.

## Réserves transversales (les deux bancs)

- **Architecture arm64** (Apple Silicon) ≠ **x86_64** des serveurs HPE : on
  valide la _logique_ (rôles, manifestes, ordres, comportements), pas les
  artefacts binaires x86_64. Pour la fidélité x86_64, rejouer le même
  `Vagrantfile` sur un hôte Intel.
- **Fonctionnel, pas perfs** : VMs modestes, disques virtuels petits.
- **Box pré-construite** : `bento/debian-13` — l'installation Debian elle-même
  (mode expert, partitionnement LVM, firmware bnxt, IP statique) n'est **pas**
  rejouée. Cette étape se valide à la main lors du rebuild serveurs (cf.
  [`bootstrap/RUNBOOK.md`](../bootstrap/RUNBOOK.md)).

## Pré-requis communs

| Outil      | Version  | Installation                                          |
| ---------- | -------- | ----------------------------------------------------- |
| VirtualBox | ≥ 7.2.8  | `brew install --cask virtualbox`                      |
| Vagrant    | ≥ 2.4.9  | `brew install --cask hashicorp/tap/hashicorp-vagrant` |
| Ansible    | ≥ 2.20.5 | `brew install ansible`                                |

Voir le README spécifique de chaque banc pour les détails (réseau host-only VBox
à autoriser pour `multi-node/`, etc.).
