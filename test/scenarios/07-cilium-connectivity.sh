#!/usr/bin/env bash
#
# Scénario 07 — Test connectivité Cilium : lance la suite officielle
# `cilium connectivity test` (200+ checks Pod-to-Pod, Pod-to-Service,
# E/W, NetworkPolicy, etc.). Filtre les tests non pertinents sur banc.
#
# Variables :
#   FAST=1     — uniquement les tests rapides (pas de scaling, pas de all-flows)
#   TESTS=…    — selection explicite (man cilium connectivity test)
set -euo pipefail

FAST=${FAST:-1}
TESTS=${TESTS:-}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

if ! command -v cilium >/dev/null 2>&1; then
    log "✗ CLI 'cilium' absente — installer cilium-cli (cf. bootstrap/cni.sh)"
    exit 1
fi

log "État Cilium"
cilium status --wait --wait-duration 1m

log "Suite connectivité"
args=()
if [ "$FAST" = "1" ]; then
    args+=( --include-conn-disrupt-test=false )
fi
if [ -n "$TESTS" ]; then
    args+=( --test "$TESTS" )
fi

cilium connectivity test "${args[@]}"
