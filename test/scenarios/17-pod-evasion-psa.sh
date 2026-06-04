#!/usr/bin/env bash
#
# Scénario 17 — ATTAQUE CONTRÔLÉE : évasion conteneur → PodSecurity rejette.
#
# Sécurité ACTIVE (ADR 0025) : on PASSE À L'ACTE en tentant de créer des pods
# d'ÉVASION d'hôte, et on asserte la chaîne Détection → Alerte → Réaction.
# Complémentaire du scénario 10 (privileged/hostNetwork) : on cible ici les
# vecteurs d'évasion NON couverts par le 10 :
#   - hostPath: { path: / }  → lecture/écriture du système de fichiers HÔTE ;
#   - hostPID: true          → vue (et signaux) sur les process de l'hôte ;
#   - hostIPC: true          → accès à l'IPC de l'hôte.
# Chacun est une évasion classique du bac à sable conteneur, et chacun est
# interdit par le profil `baseline` de Pod Security Admission.
#
# Chaîne D/A/R assertée :
#   [R] Réaction (BLOQUANT) : chaque pod d'évasion est REJETÉ à l'admission par
#       PSA ; un pod conforme passe. C'est la défense qui agit.
#   [D] Détection           : le message de rejet PSA prouve que le webhook
#       d'admission a VU et qualifié la tentative ; si l'accès control-plane est
#       fourni (CP_IP/SSH), on confirme la trace dans l'audit-log API.
#   [A] Alerte              : N/A aujourd'hui — l'alerte sur tentative
#       d'admission/runtime relève de Falco/Tetragon, DIFFÉRÉ (ADR 0025 §4).
#
# Pourquoi c'est valable en prod : PSA est un contrôleur d'admission de l'API
# server, identique banc/prod (aucune dépendance CNI/stockage/arch).
#
# GARDE-FOU (ADR 0025) : scénario OFFENSIF → ne tourne que sur un banc jetable.
# La garde refuse de s'exécuter si les nœuds ne sont pas reconnus comme un banc
# (IP privée de banc) sauf BANC=1 explicite.
#
# Pré-requis : cluster K8s joignable (kubectl). Aucun Ceph requis.
# Variables :
#   NAMESPACE (défaut: test-evasion)   KEEP=1 → pas de cleanup
#   BANC=1                             force l'exécution (cible déclarée jetable)
#   CP_IP/CP_PORT/SSH_KEY/USER_REMOTE  (optionnel) → confirme la trace audit-log
set -euo pipefail

NS=${NAMESPACE:-test-evasion}
KEEP=${KEEP:-0}
BANC=${BANC:-0}
SC_KEY="test.cluster.dev/scenario"
SC_VAL="17-pod-evasion-psa"

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

# ── Garde « banc jetable uniquement » (ADR 0025) ──────────────────────────────
# Scénario offensif : on refuse de tourner ailleurs que sur un banc. Heuristique
# non intrusive : si TOUTES les IP de nœuds sont dans une plage privée de banc
# (192.168.x / 10.x), on considère la cible jetable. Sinon, exiger BANC=1.
assert_banc() {
    [ "$BANC" = "1" ] && { log "BANC=1 — cible déclarée jetable (garde levée)"; return; }
    local ips
    ips=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null) || {
        log "✗ kubectl get nodes a échoué — cluster joignable ?"; exit 2; }
    local ip
    for ip in $ips; do
        case "$ip" in
            192.168.* | 10.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[0-1].*) ;;
            *)
                log "✗ REFUS : nœud $ip hors plage de banc — scénario OFFENSIF interdit"
                log "  hors banc jetable (ADR 0025). Relancer avec BANC=1 si la cible"
                log "  est bien un banc de test reconstructible."
                exit 2 ;;
        esac
    done
    log "✓ garde banc : tous les nœuds en IP privée de banc ($ips)"
}

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

assert_banc

log "Namespace $NS avec enforce=baseline (ADR 0014)"
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

# Helper : tente une création de pod d'ÉVASION et exige un REJET à l'admission.
# `kubectl apply` sort non-zéro si l'API rejette ; on vérifie que le rejet vient
# bien de PodSecurity (et pas d'une autre cause : image, quota…).
expect_rejected() {
    local name=$1 manifest=$2 out rc
    log "  [attaque] pod « $name » (doit être REJETÉ par PSA)…"
    set +e
    out=$(printf '%s' "$manifest" | kubectl apply -f - 2>&1)
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then
        log "✗ [R] « $name » ADMIS — évasion possible, PSA n'enforce pas !"
        kubectl -n "$NS" delete pod "$name" --wait=false 2>/dev/null || true
        return 1
    fi
    if printf '%s' "$out" | grep -qiE 'violat|pod ?security|forbidden|hostPath|hostPID|hostIPC'; then
        log "✓ [R] « $name » rejeté à l'admission : $(printf '%s' "$out" | tail -1)"
        log "✓ [D] détecté+qualifié par le webhook PSA (motif ci-dessus)"
        return 0
    fi
    log "✗ « $name » rejeté mais PAS par PodSecurity (cause inattendue) :"
    printf '%s\n' "$out" >&2
    return 1
}

log "[R/D] Tentatives d'évasion d'hôte (vecteurs non couverts par le 10)"

# 1) hostPath: / → monte le FS racine de l'hôte dans le conteneur (évasion).
expect_rejected "hostpath-root" "$(cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: hostpath-root
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  volumes:
    - name: host-root
      hostPath: { path: / }
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
      volumeMounts:
        - { name: host-root, mountPath: /host }
EOF
)" || exit 1

# 2) hostPID → partage l'espace de PID de l'hôte (vue/signaux sur ses process).
expect_rejected "hostpid" "$(cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: hostpid
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  hostPID: true
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
EOF
)" || exit 1

# 3) hostIPC → partage l'IPC de l'hôte (mémoire partagée, sémaphores).
expect_rejected "hostipc" "$(cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: hostipc
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  hostIPC: true
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
EOF
)" || exit 1

# [A] Alerte : N/A — pas d'alerte sur tentative d'admission aujourd'hui
# (relèverait d'un détecteur runtime Falco/Tetragon, différé — ADR 0025 §4).
log "[A] alerte : N/A — détection runtime différée (ADR 0025 §4)"

# [D] confirmation optionnelle : la tentative figure-t-elle dans l'audit-log API ?
if [ -n "${CP_IP:-}" ]; then
    CP_PORT=${CP_PORT:-22}
    SSH_KEY=${SSH_KEY:-${HOME}/.vagrant.d/insecure_private_keys/vagrant.key.rsa}
    USER_REMOTE=${USER_REMOTE:-debian}
    SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
    log "[D] confirmation audit-log API sur $CP_IP (SSH)…"
    if ssh "${SSH_OPTS[@]}" -p "$CP_PORT" -i "$SSH_KEY" "$USER_REMOTE@$CP_IP" \
        "sudo grep -q '\"namespace\":\"$NS\"' /var/log/kubernetes/audit/audit.log 2>/dev/null"; then
        log "✓ [D] tentatives tracées dans l'audit-log API (namespace $NS)"
    else
        log "! [D] pas de trace audit-log pour $NS — audit API non activé ? (non bloquant)"
    fi
fi

# Pod conforme baseline → doit être ADMIS (la défense ne bloque pas le légitime).
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
if kubectl -n "$NS" wait --for=condition=Ready --timeout=60s pod/conforme; then
    log "✓ Pod conforme admis — PSA bloque l'évasion, pas le légitime."
    log "✓ Chaîne D/R validée : PSA détecte+qualifie ET rejette les évasions."
    exit 0
else
    log "✗ Pod conforme non Ready — PSA trop strict, ou souci de scheduling."
    kubectl -n "$NS" describe pod/conforme | tail -20 >&2
    exit 1
fi
