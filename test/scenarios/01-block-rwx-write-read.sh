#!/usr/bin/env bash
#
# Scénario 01 — Stockage bloc RBD : créer un PVC, monter dans un pod,
# écrire et relire un fichier, vérifier l'identité du contenu.
#
# Vérifie :
#   - StorageClass par défaut = rook-ceph-block-replicated
#   - PVC Bound en < 60s
#   - Pod Running monte le RBD sans erreur
#   - Écriture + lecture sur le volume = contenu identique
#
# Pré-requis : CephCluster HEALTH_OK + StorageClass `rook-ceph-block-replicated`
# Variables : NAMESPACE (défaut: test-scenarios), KEEP=1 → pas de cleanup
set -euo pipefail

NS=${NAMESPACE:-test-scenarios}
PVC=pvc-01-block
POD=pod-01-block
KEEP=${KEEP:-0}
# En YAML inline, le label s'écrit `clé: "valeur"` (le format `clé=valeur` n'est
# valable que pour `kubectl label` / les sélecteurs `-l`).
SC_KEY="test.cluster.dev/scenario"
SC_VAL="01-block-rwx-write-read"

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# shellcheck disable=SC2329 # invoquxc3xa9 via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl -n "$NS" delete pod "$POD" --wait=false 2>/dev/null || true
    kubectl -n "$NS" delete pvc "$PVC" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

log "Namespace $NS"
kubectl create ns "$NS" 2>/dev/null || true

log "Vérifier StorageClass par défaut"
default_sc=$(kubectl get sc -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}')
[ "$default_sc" = "rook-ceph-block-replicated" ] \
    || { log "FAIL : default SC = '$default_sc' (attendu rook-ceph-block-replicated)"; exit 1; }

log "Créer PVC $PVC"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $PVC
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 100Mi } }
EOF

log "Attendre PVC Bound (60s)"
kubectl -n "$NS" wait --for=jsonpath='{.status.phase}'=Bound \
    --timeout=60s "pvc/$PVC"

log "Créer pod $POD qui écrit dans /data"
expected="hello-ceph-$(date -u +%s)"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: busybox:1.36
      command: ["/bin/sh", "-c", "echo $expected > /data/hello.txt; sleep 3600"]
      volumeMounts: [{ name: data, mountPath: /data }]
  volumes:
    - name: data
      persistentVolumeClaim: { claimName: $PVC }
EOF

log "Attendre pod Ready (60s)"
kubectl -n "$NS" wait --for=condition=Ready --timeout=60s "pod/$POD"

log "Lire le contenu du fichier"
actual=$(kubectl -n "$NS" exec "$POD" -- cat /data/hello.txt)
if [ "$actual" = "$expected" ]; then
    log "✓ Contenu lu identique au contenu écrit : $actual"
    exit 0
else
    log "✗ Contenu lu différent : '$actual' (attendu '$expected')"
    exit 1
fi
