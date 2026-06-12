#!/usr/bin/env bash
#
# Scénario 10 — Pod Security Admission : vérifier que le contrôleur
# d'admission PodSecurity (intégré depuis K8s 1.25, ADR 0014) bloque bien
# les pods dangereux dans un namespace `enforce=baseline`, et laisse passer
# un pod conforme.
#
# Vérifie :
#   - un pod `privileged: true` est REJETÉ à l'admission (baseline) ;
#   - un pod `hostNetwork: true` est REJETÉ à l'admission (baseline) ;
#   - un pod conforme (non privilégié) est ADMIS et démarre.
#
# Pourquoi c'est valable en prod : PSA est un contrôleur d'admission de
# l'API server — son comportement est IDENTIQUE sur le banc et en prod
# (aucune dépendance au CNI, au stockage ni à l'arch). C'est donc une vraie
# validation, pas un artefact de banc. Les namespaces applicatifs maison
# (`registry`, `rstudio`) portent déjà `enforce=baseline` ; ce scénario
# crée son PROPRE namespace labellisé pour rester autonome et idempotent.
#
# Pré-requis : cluster K8s joignable (kubectl). Aucun Ceph requis.
# Variables : NAMESPACE (défaut: test-podsecurity), KEEP=1 → pas de cleanup
set -euo pipefail

NS=${NAMESPACE:-test-podsecurity}
KEEP=${KEEP:-0}
# Clé/valeur du label de scénario. En YAML inline, on l'écrit `clé: "valeur"`
# (le format `clé=valeur` n'est valable que pour `kubectl label`).
SC_KEY="test.cluster.dev/scenario"
SC_VAL="10-pod-security-admission"

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

log "Namespace $NS avec enforce=baseline + warn/audit=restricted (ADR 0014)"
kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: $NS
  labels:
    $SC_KEY: "$SC_VAL"
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
EOF

# Helper : tente de créer un pod et ATTEND un rejet à l'admission.
# `kubectl apply` sort non-zéro si l'API rejette ; on capture aussi le
# message pour vérifier qu'il s'agit bien du contrôleur PodSecurity (et pas
# d'une autre erreur, ex. image/quota).
expect_rejected() {
    local name=$1 manifest=$2 out rc
    log "Tentative pod « $name » (doit être REJETÉ par PodSecurity)…"
    set +e
    out=$(printf '%s' "$manifest" | kubectl apply -f - 2>&1)
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then
        log "✗ « $name » a été ADMIS alors qu'il aurait dû être bloqué — PSA inactif ?"
        kubectl -n "$NS" delete pod "$name" --wait=false 2>/dev/null || true
        return 1
    fi
    if printf '%s' "$out" | grep -qiE 'violat|pod ?security|forbidden|privileged|hostNetwork'; then
        log "✓ « $name » rejeté à l'admission : $(printf '%s' "$out" | tail -1)"
        return 0
    fi
    log "✗ « $name » rejeté mais PAS par PodSecurity (cause inattendue) :"
    printf '%s\n' "$out" >&2
    return 1
}

# 1) Pod privileged — interdit par baseline.
expect_rejected "privileged" "$(cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: privileged
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
      securityContext:
        privileged: true
EOF
)"

# 2) Pod hostNetwork — interdit par baseline.
expect_rejected "hostnet" "$(cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: hostnet
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  hostNetwork: true
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
EOF
)"

# 3) Pod conforme baseline — doit être ADMIS et démarrer.
log "Pod conforme (doit être ADMIS et démarrer)…"
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: conforme
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities: { drop: [ALL] }
EOF

log "Attendre que le pod conforme soit Ready (60s)"
if kubectl -n "$NS" wait --for=condition=Ready --timeout=60s pod/conforme; then
    log "✓ Pod conforme admis et Running — PodSecurity bloque le dangereux, pas le légitime."
    exit 0
else
    log "✗ Pod conforme non Ready — PodSecurity trop strict, ou souci de scheduling."
    kubectl -n "$NS" describe pod/conforme | tail -20 >&2
    exit 1
fi
