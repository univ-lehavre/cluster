# Configuration matérielle — plateforme `dirqual`

> Relevé effectué le 2026-05-27 par connexion SSH sur les 4 nœuds. Les nœuds
> sont **rigoureusement identiques** (modèle, BIOS, CPU, RAM, stockage, réseau).

## Vue d'ensemble

| Nœud       | IP         | Rôle Kubernetes             |
| ---------- | ---------- | --------------------------- |
| `dirqual1` | 10.67.2.11 | control plane (+ Tailscale) |
| `dirqual2` | 10.67.2.12 | worker                      |
| `dirqual3` | 10.67.2.13 | worker                      |
| `dirqual4` | 10.67.2.14 | worker                      |

Rôles définis dans l'inventaire Ansible (modèle :
[`bootstrap/hosts.example.yaml`](../bootstrap/hosts.example.yaml) ; le
`hosts.yaml` réel n'est pas versionné — ADR 0023).

## Spécifications par nœud

| Composant          | Détail                                                              |
| ------------------ | ------------------------------------------------------------------- |
| **Châssis**        | HPE ProLiant **XL420 Gen10 Plus** (lame Apollo) — fabricant HPE     |
| **BIOS**           | HPE U50, 22/02/2024                                                 |
| **OS**             | Debian GNU/Linux 12 (bookworm)                                      |
| **Noyau**          | `6.1.0-48-amd64` (x86_64)                                           |
| **CPU**            | 2× **Intel Xeon Silver 4316** @ 2,30 GHz (turbo 3,40 GHz)           |
| **Cœurs**          | 20 cœurs/socket × 2 sockets = **40 cœurs / 80 threads** (HT activé) |
| **NUMA**           | 2 nœuds NUMA                                                        |
| **Virtualisation** | VT-x                                                                |
| **RAM**            | **251 GiB** (~256 Go)                                               |
| **GPU**            | Matrox G200eH3 — vidéo iLO/BMC uniquement (pas de calcul)           |

## Réseau (par nœud)

- 2× contrôleurs **Broadcom BCM57416 NetXtreme-E Dual-Media 10G RDMA**, soit **4
  ports 10 GbE** au total.
- Interfaces : `ens10f0np0`, `ens10f1np1`, `ens2f0np0`, `ens2f1np1`.
- Port actif : **`ens10f0np0` @ 10 Gb/s** (réseau cluster 10.67.2.0/22).

## Stockage (par nœud)

### Disque de démarrage

- Contrôleur **HPE NS204i-p Gen10+ Boot Controller** (NVMe miroir matériel),
  capacité utile **447 GiB**.
- Partitionnement LVM (`dirqual<n>-vg`) :

  | Volume                  | Taille | Point de montage |
  | ----------------------- | ------ | ---------------- |
  | `root`                  | 23 G   | `/`              |
  | `home`                  | 404 G  | `/home`          |
  | `var`                   | 9 G    | `/var`           |
  | `tmp`                   | 1,8 G  | `/tmp`           |
  | (partition `nvme0n1p2`) | 456 M  | `/boot`          |
  | (partition `nvme0n1p1`) | 511 M  | `/boot/efi`      |

### Stockage de données (réserve brute, non monté)

- 1× NVMe SSD **MO003200KXPTT** — **2,9 TiB** (~3,2 To).
- 12× HDD SAS **MB006000JWZVQ** — **5,5 TiB** chacun (rotatifs), soit **~66 TiB
  brut/nœud**.

> ⚠️ Ces 13 disques de données ne sont **ni partitionnés ni montés** : ils
> constituent la réserve brute consommée par **Rook/Ceph** (voir
> [`storage/ceph/cluster.yaml`](../storage/ceph/cluster.yaml)).

## Totaux cluster (4 nœuds)

| Ressource       | Total                  |
| --------------- | ---------------------- |
| Cœurs physiques | 160 (320 threads)      |
| RAM             | ~1 TiB (4× 251 GiB)    |
| NVMe data       | ~11,6 TiB (4× 2,9 TiB) |
| HDD SAS brut    | ~264 TiB (48× 5,5 TiB) |
| Réseau          | 16× ports 10 GbE       |

## À compléter

Le détail des barrettes mémoire (rang, vitesse, slots peuplés, fabricant,
référence) reste à relever. La limitation `sudo` qui empêchait initialement la
collecte n'existe plus depuis que `bootstrap/first-access.sh` pose
`sudo NOPASSWD` sur le compte `debian`. À actualiser en lançant :

```bash
for h in dirqual1 dirqual2 dirqual3 dirqual4; do
    echo "=== $h ==="
    ssh debian@$h 'sudo dmidecode -t memory' | grep -E 'Locator|Size|Speed|Manufacturer|Part Number' | head -40
done
```

Les totaux RAM proviennent actuellement de `free`.
