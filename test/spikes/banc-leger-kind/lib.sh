#!/usr/bin/env bash
#
# Constantes et helpers communs du banc léger (sourcé par up/down/probe).
# Idiomes log/ok/die/need/retry repris de test/multi-node/run-phases.sh.

# shellcheck disable=SC2034 # consommées par les scripts qui sourcent lib.sh
CLUSTER=leger
CTX=kind-leger

log() { printf '\n\033[1;36m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }
ok() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mÉCHEC: %s\033[0m\n' "$*" >&2; exit 1; }
need() { command -v "$1" > /dev/null 2>&1 || die "outil requis absent : $1"; }

retry() {
    local max=$1 itv=$2
    shift 2
    local waited=0
    until "$@"; do
        [ "${waited}" -ge "${max}" ] && return 1
        sleep "${itv}"
        waited=$((waited + itv))
    done
    return 0
}

require_docker() {
    need docker
    docker info > /dev/null 2>&1 || die \
        "démon Docker injoignable — lance Docker Desktop (open -a Docker) puis réessaie."
}

k() { kubectl --context "${CTX}" "$@"; }
