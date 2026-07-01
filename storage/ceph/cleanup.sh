#!/usr/bin/env bash
#
# Nettoyage complet d'un nœud avant un rebuild Ceph :
# - supprime l'état Rook local (`/var/lib/rook`)
# - LIBÈRE les LV/VG Ceph (device-mapper) qui tiennent les disques
# - efface table de partitions + signatures de FS sur tous les disques data + block.db
# - reboot (optionnel) pour redonner la main sur des disques propres
#
# À lancer **sur chaque nœud** quand on veut repartir à neuf, hors fenêtre
# de production (ce script reboote si SKIP_REBOOT n'est pas défini).
#
# Variables d'env (DÉRIVÉES de la topologie par nestor `ceph_wipe_env`, ADR 0102 volet C —
# les valeurs sont les devices réels DÉCLARÉS, jamais codées ici) :
#   NVME_BLOCK_DEVICE  device block.db (prod: NVMe /dev/nvme1n1 ; banc Lima: /dev/vdd, le
#                      disque `role: metadata` déclaré — JAMAIS /dev/vde, le cidata Lima).
#   DATA_DEVICE_GLOB   glob des disques data (prod: /dev/sd[a-z] ; banc Lima: /dev/vd[bc], les
#                      disques `role: data` déclarés — JAMAIS /dev/vda, le disque système).
#   SKIP_REBOOT        si non vide, ne reboote pas (rollback : on re-monte derrière ; CI/dry-run).
set -euo pipefail

NVME_BLOCK_DEVICE=${NVME_BLOCK_DEVICE:-/dev/nvme1n1}
DATA_DEVICE_GLOB=${DATA_DEVICE_GLOB:-/dev/sd[a-z]}

sudo rm -fR /var/lib/rook

# Outils de wipe : sgdisk (paquet gdisk) + parted. On n'installe QUE s'ils manquent, et
# JAMAIS d'`apt-get upgrade` (mutation lourde/risquée hors périmètre d'un wipe ; sous
# `set -e` un `apt-get update` en échec réseau — banc Lima — faisait avorter tout le
# nettoyage AVANT le wipe, vécu au banc). L'install échoue proprement s'il faut le réseau.
if ! command -v sgdisk > /dev/null || ! command -v parted > /dev/null; then
    sudo apt-get update
    sudo apt-get install -y gdisk parted
fi

# LIBÉRER LES LV/VG Ceph AVANT le wipe (vécu au banc : `blkdiscard /dev/vdd` →
# « Device or resource busy »). Un OSD BlueStore pose des LOGICAL VOLUMES LVM sur ses disques
# (`ceph--<vg>-osd--block--<id>`, `…-osd--db--<id>`) ; tant que ces device-mapper sont ACTIFS,
# le disque sous-jacent est tenu (ouverture exclusive refusée à blkdiscard). On retire donc les
# mappings device-mapper `ceph-*` (dmsetup) puis on efface les métadonnées LVM, comme le fait le
# cleanup de Rook. Best-effort : `|| true` — un mapping déjà parti n'est pas une erreur.
release_ceph_lvm() {
    echo "Libération des LV/VG Ceph (device-mapper) avant wipe…"
    # 1. désactiver les mappings device-mapper `ceph-*` (les LV OSD block/db).
    for dm in $(sudo dmsetup ls 2> /dev/null | awk '/^ceph-/ {print $1}'); do
        sudo dmsetup remove --force "${dm}" 2> /dev/null || true
    done
    # 2. retirer les VG/PV Ceph résiduels (les LV sont partis avec les mappings).
    for vg in $(sudo vgs --noheadings -o vg_name 2> /dev/null | awk '/^ *ceph-/ {print $1}'); do
        sudo vgremove -f "${vg}" 2> /dev/null || true
    done
}

wipe_all() {
    local device=$1
    if [ ! -b "${device}" ]; then
        echo "Skip ${device} (absent)"
        return 0
    fi
    echo "Device: ${device}"
    sudo sgdisk --zap-all "${device}"
    if [ "${device}" = "${NVME_BLOCK_DEVICE}" ]; then
        # blkdiscard exige l'ouverture EXCLUSIVE : si le device reste tenu (LV non libéré),
        # il échoue « busy ». On retombe sur `dd` (non exclusif) — le disque est zappé quoi
        # qu'il arrive (le rebuild Ceph repart d'un disque sans signature).
        sudo blkdiscard "${device}" || sudo dd if=/dev/zero of="${device}" bs=1M count=100 oflag=direct,dsync
    else
        sudo dd if=/dev/zero of="${device}" bs=1M count=100 oflag=direct,dsync
    fi
    sudo partprobe "${device}"
}

release_ceph_lvm

# `shopt -s nullglob` : si le glob ne matche rien (ex. nœud NVMe-only),
# il renvoie une liste vide au lieu de la chaîne littérale qui ferait
# planter wipe_all. Le glob est configurable via DATA_DEVICE_GLOB pour
# couvrir le banc Vagrant (vd*) sans toucher au disque OS.
shopt -s nullglob
# shellcheck disable=SC2206 # glob intentionnel, pas un split de valeur
data_devices=(${DATA_DEVICE_GLOB})
shopt -u nullglob
for device in "${data_devices[@]}"; do
    wipe_all "${device}"
done

wipe_all "${NVME_BLOCK_DEVICE}"

if [ -z "${SKIP_REBOOT:-}" ]; then
    sudo reboot
else
    echo "SKIP_REBOOT défini — pas de redémarrage."
fi
