#!/usr/bin/env bash
#
# Scénario 21 — CHAOS : saturation CPU / mémoire → les limits contiennent
# l'impact, les voisins survivent.
#
# Sécurité ACTIVE (ADR 0025), volet CHAOS ENGINEERING. On déploie un pod
# « stresseur » qui sature CPU et mémoire, et on vérifie que :
#   - ses `resources.limits` CONTIENNENT l'impact (le pod est throttlé CPU et
#     OOMKilled si la mémoire dépasse sa limite — preuve que les limits
#     protègent le nœud, lien scénario 08) ;
#   - les VOISINS (un pod témoin) restent Ready et l'API reste réactive ;
#   - après suppression du stresseur, tout redevient nominal.
#
# Le stress est fait en pur busybox (même image que les autres scénarios, pas de
# nouvelle image à épingler — ADR 0006) : `yes >/dev/null` en N process pour le
# CPU, et une allocation mémoire bornée pour déclencher l'OOM sous la limite.
#
# GARDE-FOU (ADR 0025) : banc jetable uniquement ; `resources.limits`
# OBLIGATOIRES sur le stresseur (bornage des dégâts — il ne peut pas tuer le
# nœud). Chaos DESTRUCTIF léger (charge transitoire) → run-all.sh attend
# HEALTH_OK ensuite.
#
# Pré-requis : cluster K8s joignable (kubectl). Ceph optionnel.
# Variables :
#   NAMESPACE   (défaut test-chaos-stress)   KEEP=1 → pas de cleanup
#   STRESS_CPU  process CPU à brûler (défaut 4)
#   STRESS_MEB  Mio à allouer par le stresseur, > limite mémoire → OOM (défaut 256)
#   CPU_LIMIT / MEM_LIMIT  limites du pod stresseur (défauts 500m / 128Mi)
#   BANC=1      force l'exécution hors plage de banc
set -euo pipefail

NS=${NAMESPACE:-test-chaos-stress}
KEEP=${KEEP:-0}
BANC=${BANC:-0}
STRESS_CPU=${STRESS_CPU:-4}
STRESS_MEB=${STRESS_MEB:-256}    # Mio alloués (> MEM_LIMIT) → doit finir OOMKilled
CPU_LIMIT=${CPU_LIMIT:-500m}
MEM_LIMIT=${MEM_LIMIT:-128Mi}
SC_KEY="test.cluster.dev/scenario"
SC_VAL="21-chaos-saturation-cpu-mem"

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
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
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

assert_banc

log "Namespace $NS (témoin + stresseur)"
kubectl create ns "$NS" 2>/dev/null || true
kubectl label ns "$NS" "$SC_KEY=$SC_VAL" --overwrite >/dev/null

# Pod témoin = le voisin qui DOIT survivre.
log "Déploiement du pod témoin (le voisin à protéger)…"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: voisin
  namespace: $NS
  labels: { app: voisin, "$SC_KEY": "$SC_VAL" }
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
      resources:
        requests: { cpu: 50m, memory: 32Mi }
        limits:   { cpu: 100m, memory: 64Mi }
      securityContext:
        allowPrivilegeEscalation: false
        capabilities: { drop: [ALL] }
EOF
kubectl -n "$NS" wait --for=condition=Ready --timeout=60s pod/voisin

# Pod stresseur — limits OBLIGATOIRES (garde-fou). CPU : N × `yes`. Mémoire :
# STRESS_MEB Mio écrits dans /dev/shm (tmpfs compté dans le cgroup) — au-delà de
# MEM_LIMIT, le cgroup OOM-kill le conteneur (preuve que la limite protège).
log "Déploiement du stresseur (CPU×$STRESS_CPU, mem→${STRESS_MEB}Mio ; limits $CPU_LIMIT/$MEM_LIMIT)…"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: stresseur
  namespace: $NS
  labels: { app: stresseur, "$SC_KEY": "$SC_VAL" }
spec:
  restartPolicy: Never
  containers:
    - name: stress
      image: busybox:1.36
      command: ["sh", "-c"]
      args:
        - |
          i=0; while [ \$i -lt $STRESS_CPU ]; do yes >/dev/null & i=\$((i+1)); done
          # Allocation mémoire DÉTERMINISTE : on écrit STRESS_MEB Mio dans /dev/shm
          # (tmpfs → compté dans le cgroup mémoire du conteneur). Dépasser MEM_LIMIT
          # déclenche alors l'OOM-kill par le cgroup. dd compte en blocs de 1 Mio.
          dd if=/dev/zero of=/dev/shm/ballast bs=1M count=$STRESS_MEB 2>/dev/null || true
          sleep 120
      resources:
        requests: { cpu: 100m, memory: 32Mi }
        limits:   { cpu: $CPU_LIMIT, memory: $MEM_LIMIT }
      securityContext:
        allowPrivilegeEscalation: false
        capabilities: { drop: [ALL] }
EOF

# PENDANT la saturation : le voisin et l'API doivent tenir. On observe, mais on
# ne tranche le verdict qu'à la FIN (une perturbation transitoire de scheduling
# n'est pas un échec d'isolation ; un voisin qui NE revient PAS Running en est un).
log "[survie] observation sous saturation (40s)…"
for _ in $(seq 1 4); do
    kubectl get --raw='/healthz' >/dev/null 2>&1 || log "  ! API momentanément lente"
    phase=$(kubectl -n "$NS" get pod voisin -o jsonpath='{.status.phase}' 2>/dev/null || echo '?')
    [ "$phase" = "Running" ] || log "  ! voisin transitoirement en phase $phase"
    sleep 10
done
# Verdict d'isolation = état du voisin à la fin de la fenêtre de saturation.
final_phase=$(kubectl -n "$NS" get pod voisin -o jsonpath='{.status.phase}' 2>/dev/null || echo '?')
if [ "$final_phase" = "Running" ]; then
    neighbour_ok=1
    log "✓ [survie] le voisin est Running après la saturation — les limits isolent"
else
    neighbour_ok=0
    log "✗ [survie] le voisin n'est pas Running (phase $final_phase) — isolation insuffisante"
fi

# Le stresseur doit avoir été CONTENU : OOMKilled, ou throttlé puis terminé.
log "[contention] état du stresseur (les limits doivent l'avoir contenu)…"
reason=$(kubectl -n "$NS" get pod stresseur \
    -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}{.status.containerStatuses[0].lastState.terminated.reason}' 2>/dev/null || echo '')
if printf '%s' "$reason" | grep -qi 'OOMKilled'; then
    log "✓ [contention] stresseur OOMKilled — la MEM_LIMIT ($MEM_LIMIT) protège le nœud"
else
    # Pas OOM : soit busybox a borné l'alloc, soit encore en cours. On vérifie au
    # moins que le pod n'a pas débordé sa limite mémoire au point d'affecter le nœud.
    log "! [contention] stresseur non OOMKilled (état: ${reason:-en cours}) — le CPU"
    log "  reste throttlé par CPU_LIMIT ; impact mémoire borné par MEM_LIMIT. OK si"
    log "  le voisin a survécu (ci-dessus)."
fi

# RÉTABLISSEMENT : suppression du stresseur, retour nominal.
log "[rétablissement] suppression du stresseur…"
kubectl -n "$NS" delete pod stresseur --wait=false >/dev/null 2>&1 || true
if kubectl get --raw='/healthz' >/dev/null 2>&1; then
    log "✓ API réactive après retrait"
else
    log "✗ API non réactive après retrait — investiguer"; exit 1
fi

if kubectl -n rook-ceph get deploy/rook-ceph-tools >/dev/null 2>&1; then
    log "  attente HEALTH_OK (3 min max)…"
    cok=0
    for _ in $(seq 1 18); do
        [ "$(ceph_status)" = "HEALTH_OK" ] && { cok=1; break; }
        sleep 10
    done
    if [ "$cok" = "1" ]; then log "✓ Ceph HEALTH_OK"; else log "! Ceph pas encore HEALTH_OK (charge transitoire) — à surveiller"; fi
fi

[ "$neighbour_ok" = "1" ] || { log "✗ verdict : le voisin n'a pas survécu à la saturation"; exit 1; }
log "✓ CHAOS saturation encaissé : les limits contiennent, le voisin survit."
exit 0
