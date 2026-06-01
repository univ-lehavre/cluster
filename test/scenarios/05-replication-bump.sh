#!/usr/bin/env bash
#
# Scénario 05 — Augmenter la réplication d'un pool : passer un
# CephBlockPool de `size: 3` à `size: N`. Vérifier que Ceph commence à
# répliquer (HEALTH_WARN attendu), puis converge vers HEALTH_OK.
#
# Contrainte : N ≤ nombre d'hôtes (failureDomain: host). Sur banc 3 VMs,
# bump max à 3 ; sur prod 4 nœuds, bump max à 4.
#
# Variables :
#   POOL_NAME     — nom du CephBlockPool (défaut: rook-ceph-block-replicated-pool)
#   NEW_SIZE      — taille cible (défaut: 4)
#   REVERT=1      — restore size original à la fin
set -euo pipefail

POOL_NAME=${POOL_NAME:-rook-ceph-block-replicated-pool}
NEW_SIZE=${NEW_SIZE:-4}
REVERT=${REVERT:-1}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
ceph() { kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph "$@"; }

log "Compter les hôtes (failureDomain: host)"
nb_hosts=$(kubectl get nodes --no-headers | wc -l | tr -d ' ')
log "Cluster : $nb_hosts hôtes"
if [ "$NEW_SIZE" -gt "$nb_hosts" ]; then
    log "✗ NEW_SIZE=$NEW_SIZE > $nb_hosts hôtes — bump impossible (failureDomain: host)"
    log "  Conseil : ajouter des hôtes ou réduire NEW_SIZE"
    exit 1
fi

log "Pool $POOL_NAME — taille actuelle :"
old_size=$(kubectl -n rook-ceph get cephblockpool "$POOL_NAME" -o jsonpath='{.spec.replicated.size}')
log "size = $old_size, cible = $NEW_SIZE"

if [ "$old_size" = "$NEW_SIZE" ]; then
    log "✓ Déjà à la bonne taille — rien à faire"
    exit 0
fi

log "Patch CephBlockPool → size: $NEW_SIZE"
kubectl -n rook-ceph patch cephblockpool "$POOL_NAME" --type=merge \
    -p "{\"spec\":{\"replicated\":{\"size\":$NEW_SIZE}}}"

log "Attendre Ceph à le prendre en compte (1 min)"
sleep 60
ceph status | head -10

log "Attendre HEALTH_OK (10 min max — temps de réplication)"
healthy=0
for _ in $(seq 1 60); do
    # Parsing JSON robuste (cf. audit P9 #14) plutôt que `ceph health | awk`.
    h=$(ceph health -f json 2>/dev/null | jq -r '.status' 2>/dev/null)
    if [ "$h" = "HEALTH_OK" ]; then
        log "✓ HEALTH_OK après bump"
        healthy=1
        break
    fi
    sleep 10
done
if [ "$healthy" -ne 1 ]; then
    log "✗ ÉCHEC : Ceph n'a pas convergé vers HEALTH_OK après 10 min (réplication bloquée ?)"
    ceph status | head -10
    exit 1
fi

ceph status | head -10
ceph osd pool get "$(kubectl -n rook-ceph get cephblockpool "$POOL_NAME" -o jsonpath='{.spec.parameters.poolName}' || echo "$POOL_NAME")" size 2>/dev/null || true

if [ "$REVERT" = "1" ]; then
    log "REVERT=1 → restore size $old_size"
    kubectl -n rook-ceph patch cephblockpool "$POOL_NAME" --type=merge \
        -p "{\"spec\":{\"replicated\":{\"size\":$old_size}}}"
fi
