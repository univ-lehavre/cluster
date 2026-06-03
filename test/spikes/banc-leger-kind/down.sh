#!/usr/bin/env bash
#
# Détruit le banc léger (cluster kind + tout son contenu). Jetable.
# Usage : ./down.sh

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/banc-leger-kind/lib.sh
. "${HERE}/lib.sh"

need kind
require_docker

if kind get clusters 2> /dev/null | grep -qx "${CLUSTER}"; then
    log "Suppression du cluster kind '${CLUSTER}'"
    kind delete cluster --name "${CLUSTER}"
    ok "'${CLUSTER}' supprimé"
else
    ok "'${CLUSTER}' déjà absent"
fi
