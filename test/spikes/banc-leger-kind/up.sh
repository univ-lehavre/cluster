#!/usr/bin/env bash
#
# Monte le banc léger : cluster kind HA (3 CP + 1 worker), vérifie le
# local-path-provisioner, déploie SeaweedFS (S3-compatible). Idempotent.
#
# Usage : ./up.sh
# Prérequis : docker (démon lancé), kind, kubectl.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/banc-leger-kind/lib.sh
. "${HERE}/lib.sh"

need kind
need kubectl
require_docker

# ── 1. Cluster kind HA ───────────────────────────────────────────────────────
if kind get clusters 2> /dev/null | grep -qx "${CLUSTER}"; then
    ok "cluster kind '${CLUSTER}' déjà présent"
else
    log "Création du cluster kind HA '${CLUSTER}' (3 control-plane + 1 worker)"
    kind create cluster --name "${CLUSTER}" --config "${HERE}/kind-cluster.yaml"
    ok "cluster '${CLUSTER}' créé"
fi

log "Attente des nœuds Ready"
nodes_ready() { [ "$(k get nodes --no-headers 2> /dev/null | grep -cw Ready)" -ge 4 ]; }
retry 180 5 nodes_ready || die "les 4 nœuds ne sont pas Ready"
ok "$(k get nodes --no-headers | grep -cw Ready) nœuds Ready"

# ── 2. StorageClass local-path (fournie par kind) ────────────────────────────
log "Vérification du provisioner de volumes (local-path, défaut kind)"
if k get storageclass standard > /dev/null 2>&1; then
    ok "StorageClass 'standard' (local-path) présente"
else
    warn "StorageClass 'standard' absente — PVC indisponibles"
fi

# ── 3. SeaweedFS (objectstore S3 léger) ──────────────────────────────────────
log "Déploiement de SeaweedFS (S3 léger)"
k apply -f "${HERE}/manifests/seaweedfs.yaml"
k -n s3 rollout status deploy/seaweedfs --timeout=180s
ok "SeaweedFS prêt (S3 sur seaweedfs.s3.svc.cluster.local:8333)"

cat <<EOF

Banc léger prêt. K8s HA (3 CP + 1 worker), local-path + SeaweedFS S3.
  ./probe.sh            # vérifie K8s HA, PVC local-path, et l'endpoint S3 SeaweedFS
  ./down.sh             # détruit le cluster

Accès S3 (depuis un pod) : endpoint http://seaweedfs.s3.svc.cluster.local:8333
  access key = seaweedadmin / secret key = seaweedadmin-secret
EOF
