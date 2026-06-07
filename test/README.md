# Bancs de test locaux

Bancs à choisir selon la phase à valider. Deux **hyperviseurs** : Vagrant +
VirtualBox (`single-node/`, `multi-node/`) et **Lima** (`lima/`, remplaçant
léger de Vagrant — vraie VM, SSH natif, sans VirtualBox).

**Nommage** : chaque banc valide une **topologie** au nom technique stable,
indépendant de l'outil
([ADR 0030](../docs/decisions/0030-nomenclature-bancs-topologies.md)). Une même
topologie peut tourner sur deux outils — `multi-node-3` existe en Vagrant **et**
en Lima (deux lignes, même nom). Les dossiers `test/*/` ne sont pas renommés :
le nom est une étiquette logique.

| Nom technique    | Dossier                                                      | Outil   | Topologie               | Disques Ceph     | Phases couvertes                    | Démarrage |
| ---------------- | ------------------------------------------------------------ | ------- | ----------------------- | ---------------- | ----------------------------------- | --------- |
| `single-node`    | [`single-node/`](single-node/)                               | Vagrant | 1 VM                    | aucun            | 1 (OS/runtime), 2 (init + Cilium)   | ~5 min    |
| `multi-node-3`   | [`multi-node/`](multi-node/)                                 | Vagrant | 3 VMs + privnet         | 3 HDD + NVMe     | 1, 2 (avec join), 3 (Ceph), 4, 5    | ~15 min   |
| `multi-node-3`   | [`lima/`](lima/)                                             | Lima    | 3 VMs + user-v2         | 3 HDD + block.db | 1, 2 (avec join), 3 (Ceph), 4       | ~15 min   |
| `mesh-2clusters` | [`spikes/clustermesh-latency/`](spikes/clustermesh-latency/) | Lima    | 2 clusters + `tc netem` | n/a              | spike Cilium Cluster Mesh (jetable) | variable  |

> Topologies **cibles** nommées mais pas encore montées sur banc : `ha-3cp` (3
> control planes HA), `multisite` (plusieurs sites, 1 cluster autonome par
> site). Cf.
> [ADR 0030](../docs/decisions/0030-nomenclature-bancs-topologies.md).

## Quand utiliser lequel ?

- **`single-node/`** : itération rapide sur les rôles Ansible (`checks`, `cri`,
  `kubeadm`, `initialisation`), validation d'un changement de version
  (containerd, kubeadm, Cilium). Pas de Ceph, pas de join.
- **`multi-node/`** : validation de bout en bout avant le déploiement serveurs —
  exerce `join-workers`, les pré-requis disques pour Ceph, le quorum mon (3
  nœuds), la mise en place des StorageClasses et des workloads applicatifs.
- **`lima/`** : équivalent multi-VM **sans VirtualBox** (vraie VM Lima, SSH
  natif, disques bruts virtio). Couvre jusqu'aux StorageClasses (Ceph inclus) ;
  les workloads applicatifs et l'etcd-backup restent sur `multi-node/`. Plus
  léger à installer (`brew install lima`), résiste mieux à la veille de l'hôte.

Une fois validé sur `single-node/`, repasser **systématiquement** sur
`multi-node/` (ou `lima/`) avant de toucher la prod — c'est le seul endroit où
l'on exerce le multi-VM et les disques Ceph.

## Réserves transversales (tous les bancs)

- **Architecture arm64** (Apple Silicon) ≠ **x86_64** des serveurs lames : on
  valide la _logique_ (rôles, manifestes, ordres, comportements), pas les
  artefacts binaires x86_64. Pour la fidélité x86_64, rejouer le même
  `Vagrantfile` sur un hôte Intel.
- **Fonctionnel, pas perfs** : VMs modestes, disques virtuels petits.
- **Box pré-construite** : `bento/debian-13` — l'installation Debian elle-même
  (mode expert, partitionnement LVM, firmware bnxt, IP statique) n'est **pas**
  rejouée. Cette étape se valide à la main lors du rebuild serveurs (cf.
  [`bootstrap/RUNBOOK.md`](../bootstrap/RUNBOOK.md)).
- **Restore d'un nœud (halt → `vagrant up`) non fidèle** : le retour d'une VM
  exerce des artefacts banc (route ClusterIP perdue au reboot, clock skew,
  `vboxsf`) **absents de la prod**. La _perte_ de nœud reste un test de
  résilience valable ; le _restore_, non — ne pas chercher à le « réparer » sur
  le banc. Détail : [`scenarios/README.md`](scenarios/README.md) (03/04) et
  [`RESULTS.md`](RESULTS.md).

## Pré-requis communs

| Outil      | Version  | Installation                                          | Bancs                         |
| ---------- | -------- | ----------------------------------------------------- | ----------------------------- |
| Ansible    | ≥ 2.20.5 | `brew install ansible`                                | tous                          |
| VirtualBox | ≥ 7.2.8  | `brew install --cask virtualbox`                      | `single-node/`, `multi-node/` |
| Vagrant    | ≥ 2.4.9  | `brew install --cask hashicorp/tap/hashicorp-vagrant` | `single-node/`, `multi-node/` |
| Lima       | ≥ 2.0    | `brew install lima`                                   | `lima/`                       |

Voir le README spécifique de chaque banc pour les détails (réseau host-only VBox
à autoriser pour `multi-node/`, réseau `user-v2` pour `lima/`, etc.).

## Nettoyage

Pour basculer entre bancs, libérer du disque, ou repartir d'un état frais :

```bash
./test/prune.sh           # détruit les VMs Vagrant dirqual* (+ disques VBox,
                          # drift #0c) ET les VMs/disques du banc Lima
./test/prune.sh --help    # options et garde-fous
```

Le script refuse de tourner si une VM `dirqual*` est en cours (`--force` pour
passer outre). Pour ne nettoyer que le banc Lima :
`test/lima/run-phases.sh down`.
