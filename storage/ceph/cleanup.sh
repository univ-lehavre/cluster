#!/usr/bin/env bash
#
# Nettoyage complet d'un nœud avant un rebuild Ceph :
# - supprime l'état Rook local (`/var/lib/rook`)
# - efface table de partitions + signatures de FS sur tous les disques data
# - reboot pour redonner la main sur des disques propres
#
# À lancer **sur chaque nœud** quand on veut repartir à neuf, hors fenêtre
# de production (ce script reboote).
#
# Variables d'env :
#   NVME_BLOCK_DEVICE  device NVMe block.db (défaut: /dev/nvme1n1 prod, à
#                      surcharger en /dev/vde sur le banc Vagrant).
#   DATA_DEVICE_GLOB   glob des disques data HDD (défaut: /dev/sd[a-z] prod).
#                      Sur le banc Vagrant (contrôleur VirtIO, aucun /dev/sd*),
#                      surcharger en '/dev/vd[b-z]' — JAMAIS /dev/vd[a-z] qui
#                      inclurait /dev/vda, le disque système.
#   SKIP_REBOOT        si non vide, ne reboote pas (utile en CI / dry-run).
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

wipe_all() {
    local device=$1
    if [ ! -b "${device}" ]; then
        echo "Skip ${device} (absent)"
        return 0
    fi
    echo "Device: ${device}"
    sudo sgdisk --zap-all "${device}"
    if [ "${device}" = "${NVME_BLOCK_DEVICE}" ]; then
        sudo blkdiscard "${device}"
    else
        sudo dd if=/dev/zero of="${device}" bs=1M count=100 oflag=direct,dsync
    fi
    sudo partprobe "${device}"
}

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
