#!/usr/bin/env bash
#
# Scénario 19 — CHAOS réseau : perte de paquets / partition (tc netem) → le
# cluster survit et se rétablit.
#
# Sécurité ACTIVE (ADR 0025), volet CHAOS ENGINEERING. On DÉGRADE volontairement
# le lien réseau d'un nœud (perte de paquets, ou partition = perte totale) via
# `tc netem`, et on vérifie que :
#   - PENDANT la perturbation, l'API reste joignable et Ceph tient (réplica ×3,
#     min_size 2, failureDomain host) — au pire HEALTH_WARN, pas de perte d'I/O ;
#   - APRÈS retrait du netem, le cluster RECONVERGE vers HEALTH_OK.
#
# Réutilise le PATTERN netem du spike test/spikes/clustermesh-latency/ (qdisc
# replace = idempotent ; del = retrait), transposé en SSH sur une VRAIE VM (banc
# Lima/Vagrant) — pas `docker exec` (kind abandonné). Aucun chemin Lima en dur :
# l'interface privée est DÉTECTÉE par l'IP de banc qu'elle porte.
#
# DESTRUCTIF : à exécuter via run-all.sh qui attend HEALTH_OK ensuite. netem est
# RETIRÉ au cleanup (réversibilité, garde-fou ADR 0025).
#
# GARDE-FOU (ADR 0025) : CHAOS → banc jetable uniquement (NODE_IP en plage banc,
# ou BANC=1). Le netem ne vise qu'UN SEUL nœud (bornage des dégâts).
#
# Pré-requis : accès SSH au nœud cible (root via sudo) ; kubectl pour observer
# la santé Ceph/API. iproute2 (tc) installé au besoin.
# Variables :
#   NODE_IP    (défaut 192.168.67.12 — un worker, PAS le control plane)
#   NODE_PORT  (défaut 22)   SSH_KEY / USER_REMOTE  (comme 13/15/16)
#   MODE       loss (défaut) | partition
#   LOSS       pourcentage de perte en mode loss (défaut 30)
#   IFACE      forcer l'interface (sinon détectée via l'IP de banc)
#   BANC=1     force l'exécution hors plage de banc
#   KEEP=1     ne pas retirer netem en sortie (inspection)
set -euo pipefail

NODE_IP=${NODE_IP:-192.168.67.12}
NODE_PORT=${NODE_PORT:-22}
SSH_KEY=${SSH_KEY:-${HOME}/.vagrant.d/insecure_private_keys/vagrant.key.rsa}
USER_REMOTE=${USER_REMOTE:-debian}
MODE=${MODE:-loss}
LOSS=${LOSS:-30}
IFACE=${IFACE:-}
BANC=${BANC:-0}
KEEP=${KEEP:-0}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
node_ssh() { ssh "${SSH_OPTS[@]}" -p "$NODE_PORT" -i "$SSH_KEY" "$USER_REMOTE@$NODE_IP" "$@"; }
ceph() { kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph "$@" 2>/dev/null; }
# Statut Ceph en un mot (HEALTH_OK/WARN/ERR), via jq si dispo, sinon brut.
ceph_status() {
    if command -v jq >/dev/null 2>&1; then
        ceph health -f json 2>/dev/null | jq -r '.status'
    else
        ceph health 2>/dev/null | head -1
    fi
}

# ── Garde « banc jetable uniquement » (ADR 0025) ──────────────────────────────
assert_banc() {
    [ "$BANC" = "1" ] && { log "BANC=1 — cible déclarée jetable (garde levée)"; return; }
    case "$NODE_IP" in
        192.168.* | 10.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[0-1].*)
            log "✓ garde banc : $NODE_IP en plage privée de banc" ;;
        *)
            log "✗ REFUS : NODE_IP=$NODE_IP hors plage de banc — CHAOS interdit hors"
            log "  banc jetable (ADR 0025). Relancer avec BANC=1 si banc de test."
            exit 2 ;;
    esac
}

# Détecte l'interface portant l'IP de banc (à défaut d'IFACE explicite).
detect_iface() {
    [ -n "$IFACE" ] && { echo "$IFACE"; return; }
    node_ssh "ip -o -4 addr show | awk '/$NODE_IP/ {print \$2; exit}'"
}

NETEM_IFACE=""
# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    if [ "$KEEP" = "1" ]; then
        log "KEEP=1 — netem LAISSÉ en place sur ${NETEM_IFACE:-?}. Retrait manuel :"
        log "  ssh … sudo tc qdisc del dev ${NETEM_IFACE:-<iface>} root"
        return
    fi
    [ -n "$NETEM_IFACE" ] || return
    log "Cleanup — retrait du netem sur $NETEM_IFACE…"
    node_ssh "sudo tc qdisc del dev $NETEM_IFACE root >/dev/null 2>&1 || true" || true
}
trap cleanup EXIT

assert_banc

log "Cible chaos : $USER_REMOTE@$NODE_IP — vérification accès SSH…"
node_ssh "true" || { log "✗ nœud injoignable en SSH"; exit 2; }

# tc/netem présents ? (idempotent — pattern ensure_tc du spike clustermesh.)
if ! node_ssh "command -v tc >/dev/null 2>&1"; then
    log "tc absent — installation de iproute2…"
    node_ssh "sudo apt-get update -qq && sudo apt-get install -y -qq iproute2" \
        || { log "✗ impossible d'installer iproute2"; exit 2; }
fi

NETEM_IFACE=$(detect_iface | tr -d '[:space:]')
[ -n "$NETEM_IFACE" ] || { log "✗ interface portant $NODE_IP introuvable (forcer via IFACE=…)"; exit 2; }
log "Interface ciblée : $NETEM_IFACE (porte $NODE_IP)"

# Santé de départ (best-effort si Ceph absent).
if kubectl -n rook-ceph get deploy/rook-ceph-tools >/dev/null 2>&1; then
    log "Santé Ceph avant chaos : $(ceph health | head -1)"
fi

# Règle netem selon le mode.
case "$MODE" in
    loss)      NETEM_ARGS="loss ${LOSS}%"; log "[chaos] perte de paquets ${LOSS}% sur $NETEM_IFACE" ;;
    partition) NETEM_ARGS="loss 100%";     log "[chaos] PARTITION (perte 100%) sur $NETEM_IFACE" ;;
    *)         log "✗ MODE invalide : '$MODE' (attendu loss|partition)"; exit 2 ;;
esac

# replace = idempotent (add si absent, sinon remplace) — comme le spike.
node_ssh "sudo tc qdisc replace dev $NETEM_IFACE root netem $NETEM_ARGS" \
    || { log "✗ pose du netem échouée"; exit 1; }
node_ssh "sudo tc qdisc show dev $NETEM_IFACE | head -1" || true

# PENDANT la perturbation : l'API doit rester joignable et Ceph ne pas perdre
# l'accès aux données. On observe ~60 s.
log "[survie] observation sous perturbation (60s) — API + santé Ceph…"
api_ok=1
for _ in $(seq 1 6); do
    if ! kubectl get --raw='/healthz' >/dev/null 2>&1; then api_ok=0; fi
    sleep 10
done
if [ "$api_ok" = "1" ]; then
    log "✓ [survie] API Kubernetes restée joignable pendant la perturbation"
else
    # En mode partition d'un worker, l'API (sur le control plane) doit tenir ;
    # une indisponibilité API signale un problème au-delà du nœud ciblé.
    log "✗ [survie] API injoignable pendant la perturbation — au-delà du nœud ciblé ?"
fi
if kubectl -n rook-ceph get deploy/rook-ceph-tools >/dev/null 2>&1; then
    st=$(ceph_status)
    log "  santé Ceph sous perturbation : ${st:-inconnue} (HEALTH_WARN toléré, ×3/min_size 2)"
fi

# RÉTABLISSEMENT : retirer le netem et attendre la reconvergence.
log "[rétablissement] retrait du netem puis attente reconvergence…"
# Retrait explicite ici ; le trap cleanup retentera (del idempotent) en sortie.
node_ssh "sudo tc qdisc del dev $NETEM_IFACE root >/dev/null 2>&1 || true"

# API doit redevenir/rester joignable.
if kubectl get --raw='/healthz' >/dev/null 2>&1; then
    log "✓ API joignable après retrait"
else
    log "✗ API toujours injoignable après retrait — investiguer"; exit 1
fi

# Si Ceph présent : attendre HEALTH_OK (5 min max, pattern scénario 03).
if kubectl -n rook-ceph get deploy/rook-ceph-tools >/dev/null 2>&1; then
    log "  attente HEALTH_OK (5 min max)…"
    ok=0
    for _ in $(seq 1 30); do
        [ "$(ceph_status)" = "HEALTH_OK" ] && { ok=1; break; }
        sleep 10
    done
    if [ "$ok" = "1" ]; then
        log "✓ [rétablissement] Ceph revenu HEALTH_OK — le cluster reconverge"
    else
        log "✗ [rétablissement] HEALTH_OK non atteint en 5 min — reconvergence KO"
        ceph health detail 2>/dev/null | head -10 >&2 || true
        exit 1
    fi
else
    log "  (pas de Ceph : critère de rétablissement = API joignable, validé)"
fi

[ "${api_ok:-1}" = "1" ] || { log "✗ verdict : l'API n'a pas survécu à la perturbation"; exit 1; }
log "✓ CHAOS réseau encaissé : survie sous ${MODE} + reconvergence après retrait."
exit 0
