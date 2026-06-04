#!/usr/bin/env bash
#
# Scénario 20 — CHAOS : kill aléatoire de pods → Kubernetes les recrée.
#
# Sécurité ACTIVE (ADR 0025), volet CHAOS ENGINEERING. On tue ALÉATOIREMENT des
# pods et on vérifie que le plan de contrôle les RECRÉE (ReplicaSet/STS), que
# tous reviennent Ready, et que la santé Ceph est préservée. Généralise la
# logique du scénario 02 (delete pod → recréation) au kill répété et aléatoire.
#
# Par défaut, AUTONOME : crée un Deployment témoin (3 répliques) et tue ses pods
# au hasard — aucune dépendance à une charge applicative. Si TARGET_NS est fourni
# (ex. rook-ceph), tue plutôt des pods de ce namespace (chaos « réel »).
#
# Chaos DESTRUCTIF (state cluster) → run-all.sh attend HEALTH_OK ensuite.
#
# GARDE-FOU (ADR 0025) : banc jetable uniquement ; et SAFE=1 (défaut) EXCLUT le
# control plane / apiserver / etcd du tirage (sinon perte de l'API).
#
# Pré-requis : cluster K8s joignable (kubectl). Ceph optionnel (observé si là).
# Variables :
#   NAMESPACE  (défaut test-chaos-kill — Deployment témoin)
#   TARGET_NS  (optionnel) tue des pods d'un namespace existant à la place
#   ROUNDS     nombre de tours de kill (défaut 3)
#   KILL_N     pods tués par tour (défaut 1)
#   SAFE=1     (défaut) exclut control-plane/apiserver/etcd du tirage
#   BANC=1     force l'exécution hors plage de banc
#   KEEP=1     ne pas supprimer le namespace témoin en sortie
set -euo pipefail

NS=${NAMESPACE:-test-chaos-kill}
TARGET_NS=${TARGET_NS:-}
ROUNDS=${ROUNDS:-3}
KILL_N=${KILL_N:-1}
SAFE=${SAFE:-1}
BANC=${BANC:-0}
KEEP=${KEEP:-0}
SC_KEY="test.cluster.dev/scenario"
SC_VAL="20-chaos-kill-pods"

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
ceph() { kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph "$@" 2>/dev/null; }
ceph_status() {
    if command -v jq >/dev/null 2>&1; then ceph health -f json 2>/dev/null | jq -r '.status'
    else ceph health 2>/dev/null | head -1; fi
}

# ── Garde « banc jetable uniquement » (ADR 0025) ── cf. scénario 17.
assert_banc() {
    [ "$BANC" = "1" ] && { log "BANC=1 — cible déclarée jetable (garde levée)"; return; }
    local ips ip
    ips=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null) || {
        log "✗ kubectl get nodes a échoué — cluster joignable ?"; exit 2; }
    for ip in $ips; do
        case "$ip" in
            192.168.* | 10.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[0-1].*) ;;
            *) log "✗ REFUS : nœud $ip hors plage de banc — CHAOS interdit hors banc"
               log "  jetable (ADR 0025). Relancer avec BANC=1 si banc de test."; exit 2 ;;
        esac
    done
    log "✓ garde banc : tous les nœuds en IP privée de banc ($ips)"
}

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ -n "$TARGET_NS" ] && return # on ne nettoie pas un namespace existant
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

assert_banc

if [ -n "$TARGET_NS" ]; then
    WORK_NS="$TARGET_NS"
    log "Mode chaos réel : kill de pods aléatoires dans le namespace « $WORK_NS »"
    kubectl get ns "$WORK_NS" >/dev/null 2>&1 || { log "✗ namespace $WORK_NS introuvable"; exit 2; }
else
    WORK_NS="$NS"
    log "Mode autonome : Deployment témoin (3 répliques) dans « $WORK_NS »"
    kubectl create ns "$WORK_NS" 2>/dev/null || true
    kubectl label ns "$WORK_NS" "$SC_KEY=$SC_VAL" --overwrite >/dev/null
    kubectl -n "$WORK_NS" apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chaos-witness
  namespace: $WORK_NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  replicas: 3
  selector: { matchLabels: { app: chaos-witness } }
  template:
    metadata:
      labels: { app: chaos-witness, "$SC_KEY": "$SC_VAL" }
    spec:
      containers:
        - name: app
          image: busybox:1.36
          command: ["sleep", "3600"]
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: { drop: [ALL] }
EOF
    kubectl -n "$WORK_NS" rollout status deploy/chaos-witness --timeout=90s
fi

# Sélection des pods tuables : exclut le control plane si SAFE=1.
list_targets() {
    kubectl -n "$WORK_NS" get pods --field-selector=status.phase=Running \
        -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null \
    | if [ "$SAFE" = "1" ]; then grep -ivE 'apiserver|etcd|controller-manager|scheduler|kube-proxy' || true; else cat; fi
}

# Tirage pseudo-aléatoire SANS Math.random (interdit) : on s'appuie sur `shuf`,
# disponible sur les nœuds Debian. À défaut, on prend les premiers (déterministe).
pick() {
    if command -v shuf >/dev/null 2>&1; then shuf | head -n "$1"; else head -n "$1"; fi
}

total_killed=0
for r in $(seq 1 "$ROUNDS"); do
    mapfile -t victims < <(list_targets | pick "$KILL_N")
    [ "${#victims[@]}" -gt 0 ] || { log "  tour $r : aucun pod tuable (SAFE exclut tout ?)"; continue; }
    log "[chaos] tour $r/$ROUNDS — kill : ${victims[*]}"
    for v in "${victims[@]}"; do
        kubectl -n "$WORK_NS" delete pod "$v" --wait=false >/dev/null 2>&1 || true
        total_killed=$((total_killed + 1))
    done
    sleep 5
done
log "[chaos] $total_killed pod(s) tué(s) au total"

# RÉTABLISSEMENT : tout doit revenir Ready.
log "[rétablissement] attente que les pods soient recréés et Ready (3 min max)…"
if [ -z "$TARGET_NS" ]; then
    if kubectl -n "$WORK_NS" rollout status deploy/chaos-witness --timeout=180s; then
        log "✓ [rétablissement] Deployment témoin de nouveau complet — K8s recrée bien"
    else
        log "✗ [rétablissement] le Deployment témoin n'a pas reconvergé"
        kubectl -n "$WORK_NS" get pods >&2 || true
        exit 1
    fi
else
    ok=0
    for _ in $(seq 1 18); do
        # Distinguer « API inaccessible » (env, exit 2) de « pods non-Ready » (FAIL).
        if ! kubectl get --raw='/healthz' >/dev/null 2>&1; then
            log "✗ API devenue injoignable pendant le rétablissement — environnement"
            log "  inaccessible (au-delà du chaos ciblé)."
            exit 2
        fi
        not_ready=$(kubectl -n "$WORK_NS" get pods --no-headers 2>/dev/null \
            | grep -cvE 'Running|Completed' || true)
        [ "${not_ready:-1}" -eq 0 ] && { ok=1; break; }
        sleep 10
    done
    if [ "$ok" = "1" ]; then
        log "✓ [rétablissement] pods de $WORK_NS de nouveau Running"
    else
        log "✗ [rétablissement] des pods de $WORK_NS restent non-Running"
        kubectl -n "$WORK_NS" get pods >&2; exit 1
    fi
fi

# Santé Ceph (si présent) — le kill ne doit pas l'avoir cassée durablement.
if kubectl -n rook-ceph get deploy/rook-ceph-tools >/dev/null 2>&1; then
    log "  attente HEALTH_OK (5 min max)…"
    cok=0
    for _ in $(seq 1 30); do
        [ "$(ceph_status)" = "HEALTH_OK" ] && { cok=1; break; }
        sleep 10
    done
    if [ "$cok" = "1" ]; then log "✓ Ceph HEALTH_OK"; else log "✗ Ceph pas revenu HEALTH_OK"; exit 1; fi
fi

log "✓ CHAOS kill encaissé : Kubernetes recrée les pods, le cluster reste sain."
exit 0
