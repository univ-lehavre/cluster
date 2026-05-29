#!/usr/bin/env bash
#
# Smoke-test end-to-end du datalake S3 (Ceph RGW).
#
# Démarche :
#   1. Crée un utilisateur S3 (CephObjectStoreUser `smoke`) + un bucket
#      via ObjectBucketClaim (`user-smoke.yaml`).
#   2. Récupère les credentials depuis les Secrets posés par Rook.
#   3. Écrit un fichier dans le bucket, le relit, vérifie qu'il est
#      identique, puis le supprime.
#   4. Nettoie : supprime le contenu du bucket, puis l'OBC + le user.
#
# Prérequis :
#   - kubectl pointe sur le cluster, namespace rook-ceph accessible
#   - python3 (déjà sur le poste de contrôle) — pour les calculs base64
#   - mc (mclient MinIO) OU aws (CLI v2) — l'un des deux
#
# Usage :
#   bash storage/ceph/storageClass/datalake/smoke-test.sh                # run + cleanup
#   KEEP=1 bash storage/ceph/storageClass/datalake/smoke-test.sh         # ne nettoie pas
#   ENDPOINT=http://10.67.2.11:30080 bash ...smoke-test.sh               # override endpoint
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
NS=rook-ceph
OBC=smoke
BUCKET=smoke
KEEP=${KEEP:-0}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { printf '\033[31m[%s] FAIL: %s\033[0m\n' "$(date +%H:%M:%S)" "$*" >&2; exit 1; }

cleanup() {
    if [ "$KEEP" = "1" ]; then
        log "KEEP=1 — pas de cleanup. À supprimer manuellement :"
        log "  kubectl delete -f ${HERE}/user-smoke.yaml"
        return 0
    fi
    log "Cleanup : vide le bucket et supprime OBC + user…"
    if command -v mc >/dev/null 2>&1 && mc alias list smoke >/dev/null 2>&1; then
        mc rb --force "smoke/${BUCKET}" 2>/dev/null || true
        mc alias remove smoke 2>/dev/null || true
    fi
    kubectl -n "$NS" delete -f "${HERE}/user-smoke.yaml" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

# ─── 1. Création du user + bucket ─────────────────────────────────────
log "Apply ${HERE}/user-smoke.yaml (CephObjectStoreUser + ObjectBucketClaim)…"
kubectl apply -f "${HERE}/user-smoke.yaml"

log "Attendre que le Secret de l'OBC soit créé (timeout 60s)…"
for _ in $(seq 1 30); do
    if kubectl -n "$NS" get secret "$OBC" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
kubectl -n "$NS" get secret "$OBC" >/dev/null 2>&1 \
    || fail "Secret ${OBC} pas créé — l'OBC n'a probablement pas convergé. Vérifier : kubectl -n ${NS} describe obc ${OBC}"

# ─── 2. Récupérer les credentials ─────────────────────────────────────
AWS_ACCESS_KEY_ID=$(kubectl -n "$NS" get secret "$OBC" -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 --decode)
AWS_SECRET_ACCESS_KEY=$(kubectl -n "$NS" get secret "$OBC" -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 --decode)
BUCKET_HOST=$(kubectl -n "$NS" get configmap "$OBC" -o jsonpath='{.data.BUCKET_HOST}' || true)
BUCKET_PORT=$(kubectl -n "$NS" get configmap "$OBC" -o jsonpath='{.data.BUCKET_PORT}' || true)

# Endpoint S3 : utiliser ENDPOINT en priorité, sinon BUCKET_HOST:BUCKET_PORT
# du ConfigMap (résolvable depuis l'intérieur du cluster), sinon
# port-forward sur le service rook-ceph-rgw-datalake.
if [ -n "${ENDPOINT:-}" ]; then
    S3_ENDPOINT="$ENDPOINT"
elif [ -n "$BUCKET_HOST" ] && [ -n "$BUCKET_PORT" ]; then
    # Probable que ça ne marche que dans un pod du cluster, sinon fallback
    S3_ENDPOINT="http://${BUCKET_HOST}:${BUCKET_PORT}"
else
    fail "Pas d'ENDPOINT : passer ENDPOINT=http://… ou lancer dans un pod du cluster"
fi

log "Endpoint : $S3_ENDPOINT  | Bucket : $BUCKET  | KeyID : ${AWS_ACCESS_KEY_ID:0:8}…"

# ─── 3. PUT / GET / LIST / DELETE ─────────────────────────────────────
TMPDIR=$(mktemp -d)
echo "hello cluster datalake — $(date -u +%FT%TZ)" > "$TMPDIR/upload.txt"

if command -v mc >/dev/null 2>&1; then
    log "Outil : mc (MinIO client)"
    mc alias set smoke "$S3_ENDPOINT" "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" --api S3v4 >/dev/null
    log "PUT  → smoke/${BUCKET}/upload.txt"
    mc cp "$TMPDIR/upload.txt" "smoke/${BUCKET}/upload.txt" >/dev/null
    log "LIST → smoke/${BUCKET}"
    mc ls "smoke/${BUCKET}/" | head
    log "GET  ← smoke/${BUCKET}/upload.txt"
    mc cp "smoke/${BUCKET}/upload.txt" "$TMPDIR/download.txt" >/dev/null
elif command -v aws >/dev/null 2>&1; then
    log "Outil : aws-cli"
    export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
    log "PUT  → s3://${BUCKET}/upload.txt"
    aws --endpoint-url "$S3_ENDPOINT" s3 cp "$TMPDIR/upload.txt" "s3://${BUCKET}/upload.txt" >/dev/null
    log "LIST → s3://${BUCKET}"
    aws --endpoint-url "$S3_ENDPOINT" s3 ls "s3://${BUCKET}/"
    log "GET  ← s3://${BUCKET}/upload.txt"
    aws --endpoint-url "$S3_ENDPOINT" s3 cp "s3://${BUCKET}/upload.txt" "$TMPDIR/download.txt" >/dev/null
else
    fail "Ni 'mc' ni 'aws' trouvés sur le PATH. Installer l'un des deux."
fi

if diff -q "$TMPDIR/upload.txt" "$TMPDIR/download.txt" >/dev/null; then
    log "✓ Contenu lu identique au contenu écrit."
else
    fail "Contenu lu DIFFÉRENT du contenu écrit — datalake corrompu ou auth en lecture cassée."
fi

# ─── 4. Vérification du quota / size ──────────────────────────────────
if command -v mc >/dev/null 2>&1; then
    log "Stat du bucket :"
    mc stat "smoke/${BUCKET}/upload.txt" || true
fi

log "✓ Smoke-test datalake : OK"
rm -rf "$TMPDIR"
