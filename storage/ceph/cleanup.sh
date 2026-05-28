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
#                      surcharger en /dev/nvme0n1 sur le banc Vagrant).
#   SKIP_REBOOT        si non vide, ne reboote pas (utile en CI / dry-run).
set -euo pipefail

NVME_BLOCK_DEVICE=${NVME_BLOCK_DEVICE:-/dev/nvme1n1}

sudo rm -fR /var/lib/rook

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y gdisk parted

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

# `shopt -s nullglob` : sur un nœud sans /dev/sd* (NVMe-only ou banc
# Vagrant avec uniquement vd*), le glob renvoie une liste vide au lieu
# de la chaîne littérale `/dev/sd[a-z]` qui ferait planter wipe_all.
shopt -s nullglob
for device in /dev/sd[a-z]; do
    wipe_all "${device}"
done
shopt -u nullglob

wipe_all "${NVME_BLOCK_DEVICE}"

if [ -z "${SKIP_REBOOT:-}" ]; then
    sudo reboot
else
    echo "SKIP_REBOOT défini — pas de redémarrage."
fi
