#!/usr/bin/env bash
#
# Scénario 12 — securityContext au runtime : vérifier qu'un pod durci comme
# les workloads maison (registry/wordpress/rstudio — runAsNonRoot,
# readOnlyRootFilesystem, capabilities drop ALL, seccomp RuntimeDefault)
# DÉMARRE et que ses contraintes sont RÉELLEMENT appliquées par le runtime.
#
# Vérifie :
#   - le conteneur tourne en non-root (UID ≠ 0) ;
#   - l'écriture sur le système de fichiers racine est REFUSÉE
#     (readOnlyRootFilesystem) ;
#   - l'écriture sur un volume writable monté (emptyDir) est AUTORISÉE.
#
# Complément du contrôle statique : trivy vérifie déjà ces champs dans les
# manifests en CI, mais NE prouve pas qu'un conteneur ainsi configuré
# démarre et se comporte comme prévu. Ici on l'exécute vraiment. Comportement
# identique en prod (contrainte runtime du conteneur, indépendante du CNI/Ceph).
#
# Pré-requis : cluster K8s joignable (kubectl). Aucun Ceph requis.
# Variables : NAMESPACE (défaut: test-secctx), KEEP=1 → pas de cleanup
set -euo pipefail

NS=${NAMESPACE:-test-secctx}
POD=secctx-probe
KEEP=${KEEP:-0}
# `LABEL` (clé=valeur) pour `kubectl label` ; en YAML inline on écrit
# séparément `clé: "valeur"` (le `=` y est invalide).
SC_KEY="test.cluster.dev/scenario"
SC_VAL="12-securitycontext-runtime"
LABEL="$SC_KEY=$SC_VAL"

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

log "Namespace $NS"
kubectl create ns "$NS" 2>/dev/null || true
kubectl label ns "$NS" "$LABEL" --overwrite >/dev/null

log "Déployer un pod durci (runAsNonRoot + readOnlyRootFilesystem + drop ALL)"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: { drop: [ALL] }
      volumeMounts:
        - { name: scratch, mountPath: /scratch }
  volumes:
    - name: scratch
      emptyDir: {}
EOF

log "Attendre le pod Ready (60s) — prouve qu'un pod ainsi durci DÉMARRE"
if ! kubectl -n "$NS" wait --for=condition=Ready --timeout=60s "pod/$POD"; then
    log "✗ Le pod durci ne démarre pas :"
    kubectl -n "$NS" describe "pod/$POD" | tail -25 >&2
    exit 1
fi
log "✓ Pod durci Running"

log "[1/3] Vérifier l'exécution en non-root (UID ≠ 0)"
uid=$(kubectl -n "$NS" exec "$POD" -- id -u)
if [ "$uid" = "0" ]; then
    log "✗ Le conteneur tourne en root (UID 0) malgré runAsNonRoot — non appliqué"
    exit 1
fi
log "✓ Conteneur en non-root (UID $uid)"

log "[2/3] L'écriture sur le rootfs doit être REFUSÉE (readOnlyRootFilesystem)"
if kubectl -n "$NS" exec "$POD" -- sh -c 'echo x > /oops 2>/dev/null'; then
    log "✗ Écriture sur / réussie — readOnlyRootFilesystem NON appliqué"
    exit 1
fi
log "✓ Écriture sur / refusée — rootfs en lecture seule"

log "[3/3] L'écriture sur le volume monté (/scratch) doit RÉUSSIR"
if kubectl -n "$NS" exec "$POD" -- sh -c 'echo ok > /scratch/probe && cat /scratch/probe' | grep -qx ok; then
    log "✓ Écriture sur le volume writable OK — durcissement n'empêche pas le travail légitime"
else
    log "✗ Écriture sur /scratch impossible — volume writable non monté correctement"
    exit 1
fi

log "✓ securityContext réellement appliqué au runtime (non-root + rootfs RO + volume RW)."
exit 0
