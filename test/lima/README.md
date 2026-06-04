# Banc léger Lima (multi-VM + Ceph)

Banc d'essai **équivalent fonctionnel du banc Vagrant
[`multi-node/`](../multi-node/)** — 3 VMs + disques bruts + Rook/Ceph — mais sur
des **VMs Lima** au lieu de VirtualBox.

Pourquoi Lima
([ADR 0006](../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md))
:

- **kind est abandonné** : son image de nœud figeait Kubernetes en **1.31**
  (incompatible `ImageVolume`/pgvector).
- **Vagrant + VirtualBox** reste valable mais lourd. Lima monte une **vraie VM
  Linux** (vrai noyau, vrais cgroups, swap contrôlable, SSH natif) sur laquelle
  tourne le **VRAI bootstrap Ansible** — même chemin que la prod, sans overlayfs
  imbriqué (échec du DinD) ni VirtualBox.

## Topologie

| Nœud    | Rôle          | Réseau                       | Disques bruts (virtio)           |
| ------- | ------------- | ---------------------------- | -------------------------------- |
| `cp1`   | control-plane | user-v2 (`192.168.104.0/24`) | 3 × 10 GiB (`vdb`-`vdd`) + `vde` |
| `node1` | worker        | user-v2                      | 3 × 10 GiB + `vde` (block.db)    |
| `node2` | worker        | user-v2                      | 3 × 10 GiB + `vde` (block.db)    |

- **Réseau `user-v2`** : connectivité VM↔VM **sans `socket_vmnet` ni `sudo`
  hôte** ; chaque VM est joignable en `lima-<nom>.internal` et porte le trafic
  inter-nœuds (join workers, mon Ceph) ET l'accès API depuis l'hôte. Le
  `control_plane_ip` du bootstrap est posé sur cette IP user-v2 (pas le NAT par
  défaut, non routable entre VMs).
- **Disques bruts** : Lima ne crée pas de disque vierge inline → des disques
  nommés persistants (`<nœud>-hdd1..3`, `<nœud>-blockdb`) sont créés **avant**
  le démarrage et attachés en `additionalDisks: {format: false}` pour rester
  bruts (exigence Ceph). Lima les présente en **virtio-blk → `/dev/vd*`** (≠
  banc VirtualBox VirtioSCSI → `/dev/sd*`), d'où les surcharges `CEPH_HDD_GLOB`,
  `CEPH_BLOCK_DEVICE=vde` dans l'orchestrateur.

## Pré-requis poste

| Outil   | Version  | Installation           |
| ------- | -------- | ---------------------- |
| Lima    | ≥ 2.0    | `brew install lima`    |
| Ansible | ≥ 2.20.5 | `brew install ansible` |
| kubectl | —        | `brew install kubectl` |
| python3 | —        | (préinstallé macOS)    |

**RAM consommée** : 3 × 5 GiB ≈ **15 GiB** (5 GiB/VM : le check bootstrap
`k8s-pre-install` exige `real.total ≥ 4096 MB`, qu'une VM 4 GiB ne garantit
pas).

## Orchestrateur

```bash
test/lima/run-phases.sh up         # crée disques bruts + VMs, gate vd* présents
test/lima/run-phases.sh bootstrap  # bootstrap Ansible + Cilium, gate 3 nœuds Ready
test/lima/run-phases.sh ceph       # Rook-Ceph (metadataDevice=vde), gate HEALTH_OK
test/lima/run-phases.sh sc         # StorageClasses, gate PVC test Bound
test/lima/run-phases.sh all        # tout, dans l'ordre, arrêt au 1er gate rouge
test/lima/run-phases.sh kubeconfig # (ré)exporte le kubeconfig banc
test/lima/run-phases.sh down       # détruit VMs + disques nommés
```

Chaque phase est **gated** (s'arrête si le critère n'est pas atteint) et
**idempotente** (rejouable). Le kubeconfig est exporté sous `.work/kubeconfig`
(gitignoré), avec le `server:` réécrit sur l'IP user-v2 du control-plane :

```bash
KUBECONFIG=test/lima/.work/kubeconfig kubectl get nodes -o wide
KUBECONFIG=test/lima/.work/kubeconfig kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status
```

## Réserves transversales

- **Architecture arm64** (Apple Silicon) ≠ **x86_64** des serveurs : on valide
  la _logique_ (rôles, manifestes, ordres), pas les artefacts binaires x86_64.
  Les images Ceph épinglées par digest amd64 sont **dé-épinglées** (retombée sur
  le tag multi-arch) côté banc UNIQUEMENT — le livrable garde ses digests
  intacts.
- **Fonctionnel, pas perfs** : VMs modestes, disques virtuels petits.
- **`os-upgrade` n'est PAS rejoué** (contrairement au banc Vagrant) : l'image
  `_images/debian-13` de Lima est fraîche. C'est une divergence **assumée** — ne
  pas la « corriger ».
- **Couverture** : up → bootstrap → ceph → storageClasses. Les workloads
  applicatifs (WordPress/datalake) et l'etcd-backup restent validés sur le banc
  Vagrant [`multi-node/`](../multi-node/).

## Nettoyage

```bash
test/lima/run-phases.sh down   # détruit ce banc (VMs + disques nommés)
./test/prune.sh                # nettoyage global des bancs (Vagrant + Lima)
```

## Résultats de validation

Déroulé réel du banc (de bout en bout : up → bootstrap → ceph `HEALTH_OK` → sc
PVC Bound) et drifts rencontrés (honnêteté des Runs, ADR 0023) :
[`RESULTS.md`](RESULTS.md).

## Architecture interne

- [`run-phases.sh`](run-phases.sh) : orchestrateur, table de nœuds + phases
  gated.
- [`lib.sh`](lib.sh) : bibliothèque d'orchestration Lima ↔ Ansible
  (`lima_disk_create`, `lima_render_node`, `lima_start_node`, `write_inventory`,
  `bootstrap_node_sequence`, `run_cni`, `fetch_kubeconfig_node`). **Sourcée
  aussi par les spikes** qui montent des clusters Lima (ex.
  [`../spikes/clustermesh-latency/`](../spikes/clustermesh-latency/)) — source
  unique, pas de duplication.
- [`profiles/node.yaml.tmpl`](profiles/node.yaml.tmpl) : template de VM Lima
  (Debian 13, user-v2, provision noyau K8s), rendu par `lima_render_node`.
