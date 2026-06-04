#!/usr/bin/env bash
#
# Détruit le spike : supprime les deux VMs Lima (site-a, site-b) et leurs
# artefacts de run (inventaires, kubeconfigs). Jetable par construction — le
# netem vit dans les VMs, il disparaît avec elles.
#
# Usage : ./down.sh

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/clustermesh-latency/lib.sh
. "${HERE}/lib.sh"

require_lima

for vm in "${A_VM}" "${B_VM}"; do
    lima_delete_node "${vm}"
done
rm -rf "${WORKDIR}"
ok "spike démonté — rien ne subsiste (netem inclus, vivait dans les VMs)"
