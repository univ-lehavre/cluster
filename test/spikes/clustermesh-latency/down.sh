#!/usr/bin/env bash
#
# Détruit le spike : supprime les deux clusters kind (et donc leurs conteneurs,
# réseaux, et toute règle netem qui vivait dedans). Jetable par construction.
#
# Usage : ./down.sh

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/clustermesh-latency/lib.sh
. "${HERE}/lib.sh"

need kind
require_docker

for kname in "${C1_KIND}" "${C2_KIND}"; do
    if kind get clusters 2> /dev/null | grep -qx "${kname}"; then
        log "Suppression du cluster kind '${kname}'"
        kind delete cluster --name "${kname}"
        ok "'${kname}' supprimé"
    else
        ok "'${kname}' déjà absent"
    fi
done
ok "spike démonté — rien ne subsiste (netem inclus, vivait dans les conteneurs)"
