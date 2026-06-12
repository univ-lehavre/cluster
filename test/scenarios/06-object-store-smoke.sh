#!/usr/bin/env bash
#
# Scénario 06 — Stockage objet (RGW + S3) : déploie le datalake et lance
# le smoke-test S3 existant.
#
# Wrapper qui :
#   1. Applique storage/ceph/storageClass/datalake/{datalake-ec,storage-class}.yaml
#   2. Attend que le RGW soit ready
#   3. Port-forward le service rook-ceph-rgw-datalake
#   4. Lance storage/ceph/storageClass/datalake/smoke-test.sh
#
# Variables : KEEP_DATALAKE=1 → laisser le CephObjectStore en place
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
KEEP_DATALAKE=${KEEP_DATALAKE:-0}

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# shellcheck disable=SC2329 # invoquxc3xa9 via trap EXIT
cleanup() {
    if [ "$KEEP_DATALAKE" = "1" ]; then
        log "KEEP_DATALAKE=1 — datalake conservé"
    else
        log "Cleanup datalake"
        kubectl delete -f "$REPO/storage/ceph/storageClass/datalake/datalake-ec.yaml" --wait=false 2>/dev/null || true
        kubectl delete -f "$REPO/storage/ceph/storageClass/datalake/storage-class.yaml" --wait=false 2>/dev/null || true
    fi
    [ -n "${PF_PID:-}" ] && kill "$PF_PID" 2>/dev/null || true
}
trap cleanup EXIT

log "Apply datalake (CephObjectStore + StorageClass S3)"
kubectl apply -f "$REPO/storage/ceph/storageClass/datalake/datalake-ec.yaml"
kubectl apply -f "$REPO/storage/ceph/storageClass/datalake/storage-class.yaml"

log "Attendre RGW ready (5 min)"
for _ in $(seq 1 30); do
    ready=$(kubectl -n rook-ceph get cephobjectstore datalake -o jsonpath='{.status.phase}' 2>/dev/null)
    if [ "$ready" = "Connected" ] || [ "$ready" = "Ready" ]; then
        log "✓ CephObjectStore datalake $ready"
        break
    fi
    sleep 10
done

log "Port-forward le RGW service"
kubectl -n rook-ceph port-forward svc/rook-ceph-rgw-datalake 8080:80 >/tmp/pf-rgw.log 2>&1 &
PF_PID=$!
sleep 3

log "Lancer le smoke-test S3 existant"
# Capturer explicitement le code de sortie du smoke-test : sans ça, le
# `trap cleanup EXIT` s'exécute après et son dernier `kubectl delete … || true`
# (code 0) ÉCRASE le code de sortie du script — un smoke-test en échec
# ressortait alors en RC=0 (faux positif). On mémorise donc le verdict et on
# `exit` explicitement avec, pour que le trap ne le masque pas.
smoke_rc=0
ENDPOINT=http://localhost:8080 \
    bash "$REPO/storage/ceph/storageClass/datalake/smoke-test.sh" || smoke_rc=$?
if [ "$smoke_rc" -eq 0 ]; then
    log "✓ Smoke-test S3 réussi (PUT/GET/DELETE)."
else
    log "✗ Smoke-test S3 en échec (rc=$smoke_rc) — voir la sortie ci-dessus."
fi
exit "$smoke_rc"
