#!/usr/bin/env bash
#
# Scénario 02 — Reschedule pod : prouver que la donnée survit à la
# destruction d'un pod. Écrire, supprimer le pod, recréer, relire.
#
# Vérifie :
#   - PVC reste Bound après suppression du pod
#   - Donnée persistante après recréation
#
# Variables : NAMESPACE, KEEP=1
set -euo pipefail

NS=${NAMESPACE:-test-scenarios}
PVC=pvc-02-reschedule
POD=pod-02-reschedule
KEEP=${KEEP:-0}
# En YAML inline, le label s'écrit `clé: "valeur"` (le format `clé=valeur` n'est
# valable que pour `kubectl label` / les sélecteurs `-l`).
SC_KEY="test.cluster.dev/scenario"
SC_VAL="02-pod-rescheduling"

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

# shellcheck disable=SC2329 # invoquxc3xa9 via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl -n "$NS" delete pod "$POD" --wait=false 2>/dev/null || true
    kubectl -n "$NS" delete pvc "$PVC" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

kubectl create ns "$NS" 2>/dev/null || true

log "Créer PVC + pod, écrire un fichier"
expected="data-survives-$(date -u +%s)"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: $PVC, labels: { "$SC_KEY": "$SC_VAL" } }
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 100Mi } }
---
apiVersion: v1
kind: Pod
metadata: { name: $POD, labels: { "$SC_KEY": "$SC_VAL" } }
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: busybox:1.36
      command: ["/bin/sh", "-c", "echo $expected > /data/survives.txt; sleep 3600"]
      volumeMounts: [{ name: data, mountPath: /data }]
  volumes:
    - name: data
      persistentVolumeClaim: { claimName: $PVC }
EOF
kubectl -n "$NS" wait --for=condition=Ready --timeout=60s "pod/$POD"

log "Vérifier écriture initiale"
kubectl -n "$NS" exec "$POD" -- cat /data/survives.txt

log "Supprimer le pod (PVC reste)"
kubectl -n "$NS" delete pod "$POD" --wait=true

log "PVC toujours Bound ?"
kubectl -n "$NS" get pvc "$PVC" -o jsonpath='{.status.phase}'; echo

log "Recréer le pod, monter le même PVC, lire le fichier"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata: { name: $POD, labels: { "$SC_KEY": "$SC_VAL" } }
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: busybox:1.36
      command: ["/bin/sh", "-c", "sleep 3600"]
      volumeMounts: [{ name: data, mountPath: /data }]
  volumes:
    - name: data
      persistentVolumeClaim: { claimName: $PVC }
EOF
kubectl -n "$NS" wait --for=condition=Ready --timeout=60s "pod/$POD"

log "Lire le fichier dans le nouveau pod"
actual=$(kubectl -n "$NS" exec "$POD" -- cat /data/survives.txt)
if [ "$actual" = "$expected" ]; then
    log "✓ Donnée survivante au reschedule : $actual"
    exit 0
else
    log "✗ Donnée perdue ou modifiée : '$actual' vs '$expected'"
    exit 1
fi
