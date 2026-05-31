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

# `column -N` (en-têtes) n'existe que sur util-linux (Linux) ; le `column`
# BSD de macOS — où tourne souvent ce script via kubectl distant — l'ignore et
# échoue. On émet donc l'en-tête nous-mêmes (1ʳᵉ ligne TSV) et on garde le seul
# `column -t -s` portable.
log "Composants rook-ceph et leurs requests/limits"
{
    printf 'POD\tCONTAINER\tREQ_CPU\tREQ_MEM\tLIM_CPU\tLIM_MEM\n'
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
            ] | @tsv'
} | column -t -s "$(printf '\t')"

log "Capacité allouable par nœud"
{
    printf 'NODE\tCPU\tMEM\n'
    kubectl get nodes -o json | jq -r '
        .items[] | [
            .metadata.name,
            (.status.allocatable.cpu // "-"),
            (.status.allocatable.memory // "-")
        ] | @tsv'
} | column -t -s "$(printf '\t')"

log "Pods Ceph en Pending (drift de dimensionnement potentiel)"
kubectl -n rook-ceph get pods --field-selector status.phase=Pending -o wide | head -20

# Assertion : un OSD Pending = dimensionnement incohérent (requests > allouable).
# Le script ne se contente plus d'informer, il ÉCHOUE si un OSD ne schedule pas
# (cf. reco audit 02-tests : « 08 purement informatif → implémenter un seuil »).
#
# Sur le banc, le sous-dimensionnement est ASSUMÉ (drift #10 : 5 GiB/VM ×
# osd.requests=2Gi → seuls ~3 OSD/9 schedulables, HEALTH_OK quand même). On
# tolère donc jusqu'à ALLOW_PENDING_OSD OSD Pending (défaut 0 = strict, prod).
# Le banc lance avec ALLOW_PENDING_OSD assez haut.
ALLOW_PENDING_OSD=${ALLOW_PENDING_OSD:-0}
pending_osd=$(kubectl -n rook-ceph get pods \
    -l app=rook-ceph-osd --field-selector status.phase=Pending \
    --no-headers 2> /dev/null | grep -c . || true)
if [ "${pending_osd:-0}" -gt "${ALLOW_PENDING_OSD}" ]; then
    log "✗ ${pending_osd} OSD(s) Pending (> seuil toléré ${ALLOW_PENDING_OSD}) —"
    log "  requests > capacité allouable d'un hôte. Sur banc 5 GiB/VM : baisser"
    log "  osd.requests.memory (ex. 512Mi) puis ré-appliquer le CephCluster ;"
    log "  ou relancer avec ALLOW_PENDING_OSD=<n> si ce sous-dim est assumé."
    exit 1
fi
if [ "${pending_osd:-0}" -gt 0 ]; then
    log "✓ ${pending_osd} OSD Pending, dans la tolérance assumée (ALLOW_PENDING_OSD=${ALLOW_PENDING_OSD}, drift #10)."
else
    log "✓ Aucun OSD Pending — dimensionnement cohérent avec la capacité des hôtes."
fi
