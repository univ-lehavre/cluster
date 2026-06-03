#!/usr/bin/env bash
#
# Vérifie le banc léger : HA (etcd quorum 3), PVC local-path, endpoint S3 SeaweedFS
# (création d'un bucket + put/get via un pod client aws-cli).
#
# Usage : ./probe.sh

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/banc-leger-kind/lib.sh
. "${HERE}/lib.sh"

need kubectl
require_docker

# ── 1. HA : 3 control-plane ──────────────────────────────────────────────────
log "Contrôle HA (control-plane)"
cp_count=$(k get nodes -l node-role.kubernetes.io/control-plane --no-headers 2> /dev/null | grep -cw Ready)
if [ "${cp_count}" -eq 3 ]; then
    ok "3 control-plane Ready (etcd quorum 3)"
else
    warn "control-plane Ready = ${cp_count} (attendu 3)"
fi

# ── 2. PVC local-path ────────────────────────────────────────────────────────
log "Test d'un PVC local-path"
k apply -f - <<EOF > /dev/null
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: probe-pvc
  namespace: default
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: standard
  resources: { requests: { storage: 64Mi } }
EOF
# local-path est WaitForFirstConsumer → besoin d'un pod consommateur
k apply -f - <<EOF > /dev/null
apiVersion: v1
kind: Pod
metadata:
  name: probe-writer
  namespace: default
spec:
  restartPolicy: Never
  containers:
    - name: w
      image: docker.io/library/busybox:1.38.0@sha256:fd8d9aa63ba2f0982b5304e1ee8d3b90a210bc1ffb5314d980eb6962f1a9715d
      command: ["sh", "-c", "echo banc-leger-ok > /data/probe && sleep 5"]
      volumeMounts: [{ name: d, mountPath: /data }]
  volumes:
    - name: d
      persistentVolumeClaim: { claimName: probe-pvc }
EOF
pvc_bound() { [ "$(k -n default get pvc probe-pvc -o jsonpath='{.status.phase}' 2> /dev/null)" = "Bound" ]; }
if retry 60 3 pvc_bound; then ok "PVC local-path Bound"; else warn "PVC non Bound"; fi

# ── 3. S3 SeaweedFS : bucket + put/get via aws-cli ───────────────────────────
log "Test S3 SeaweedFS (bucket + put/get)"
k -n s3 delete pod s3probe --ignore-not-found > /dev/null 2>&1 || true
k -n s3 run s3probe --restart=Never \
    --image=docker.io/amazon/aws-cli:2.31.21 --command -- sleep 300 > /dev/null
k -n s3 wait --for=condition=Ready pod/s3probe --timeout=120s > /dev/null
s3() {
    k -n s3 exec s3probe -- env \
        AWS_ACCESS_KEY_ID=seaweedadmin AWS_SECRET_ACCESS_KEY=seaweedadmin-secret \
        aws --endpoint-url http://seaweedfs.s3.svc.cluster.local:8333 s3 "$@"
}
if s3 mb s3://probe-bucket > /dev/null 2>&1 \
    && k -n s3 exec s3probe -- sh -c 'echo hello > /tmp/o' \
    && s3 cp /tmp/o s3://probe-bucket/o > /dev/null 2>&1 \
    && s3 ls s3://probe-bucket/ 2> /dev/null | grep -q "o"; then
    ok "S3 SeaweedFS opérationnel (bucket créé, put/get OK)"
else
    warn "S3 SeaweedFS : test put/get KO (voir logs seaweedfs)"
fi

# ── Nettoyage des sondes ─────────────────────────────────────────────────────
k -n default delete pod probe-writer --ignore-not-found > /dev/null 2>&1 || true
k -n default delete pvc probe-pvc --ignore-not-found > /dev/null 2>&1 || true
k -n s3 delete pod s3probe --ignore-not-found > /dev/null 2>&1 || true
ok "sondes nettoyées"
