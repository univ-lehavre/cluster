#!/usr/bin/env bash
#
# Scénario 08 — Audit des `requests`/`limits` des composants Rook-Ceph
# côté banc et prod. Imprime un tableau lisible et signale les anomalies
# (demandes > 50 % de la RAM dispo par nœud, ratio limits/requests > 4×).
#
# But : prévenir le drift où des composants Ceph (OSDs surtout) demandent
# plus que ce que le banc peut servir → Pending. Cf. drift #8 dans
# test/RESULTS.md (banc 5 GiB/VM × 12 OSDs : OSDs avec requests=2Gi → 8
# OSDs Pending sur 12).
set -euo pipefail

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

log "Composants rook-ceph et leurs requests/limits"
kubectl -n rook-ceph get pods -o json | \
    jq -r '.items[] | .metadata.name as $n |
        .spec.containers[] |
        select(.resources.requests or .resources.limits) |
        [
            $n,
            .name,
            (.resources.requests.cpu // "-"),
            (.resources.requests.memory // "-"),
            (.resources.limits.cpu // "-"),
            (.resources.limits.memory // "-")
        ] | @tsv' | \
    column -t -s $'\t' -N POD,CONTAINER,REQ_CPU,REQ_MEM,LIM_CPU,LIM_MEM

log "Capacité allouable par nœud"
kubectl get nodes -o json | jq -r '
    .items[] | [
        .metadata.name,
        (.status.allocatable.cpu // "-"),
        (.status.allocatable.memory // "-")
    ] | @tsv' | column -t -s $'\t' -N NODE,CPU,MEM

log "Pods Ceph en Pending (drift de dimensionnement potentiel)"
kubectl -n rook-ceph get pods --field-selector status.phase=Pending -o wide | head -20

log "Conseil : sur banc 5 GiB/VM, baisser osd.requests.memory à 512Mi"
log "         puis re-appliquer le CephCluster pour permettre plus d'OSDs/VM."
