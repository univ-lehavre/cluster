#!/usr/bin/env bash
#
# Scénario 30 — Survie du control-plane HA (ha-3cp, ADR 0047/0055, #250).
#
# Prouve la VALEUR de la topologie ha-3cp : la VIP kube-vip + le quorum etcd
# SURVIVENT à la perte d'1 control-plane. Distinct du scénario 04 (perte du CP
# UNIQUE → API HS, SPOF assumé) : ici l'API DOIT rester joignable.
#
# Mécanique éprouvée, en trois temps — la VIP est testée À CHAQUE phase, car
# c'est l'invariant qui doit survivre :
#   1. RÉFÉRENCE : 3 CP Ready, quorum etcd 3/3, la VIP répond.
#   2. PANNE     : on arrête le CP qui PORTE la VIP (le leader) → kube-vip doit
#      réélire un leader sur un autre CP, la VIP BASCULE et répond TOUJOURS ;
#      quorum etcd 2/3 (majorité conservée), l'API reste joignable via la VIP.
#   3. RESTORE   : on redémarre le CP → retour à 3 Ready, quorum 3/3.
#
# Banc Lima (limactl). Cible : ha-3cp monté (test/lima/run-phases.sh ha-3cp).
# Variables : HA_VIP (auto-dérivée si absente), DOWNTIME_S, ETCD_NS.
set -euo pipefail

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DOWNTIME_S=${DOWNTIME_S:-45}

# ── Helpers locaux (la VIP et etcd divergent des autres scénarios → ici) ─────

# vip_responds VIP — 0 si la VIP de l'API répond à /healthz (depuis l'hôte via le
# port-forward du kubeconfig n'est PAS la VIP ; on teste DEPUIS un CP encore vivant).
vip_responds() {
    local vip=$1 from=$2
    limactl shell "${from}" sh -c \
        "curl -sk --max-time 5 https://${vip}:6443/healthz 2>/dev/null | grep -q '^ok$'"
}

# etcd_healthy_count CP — nombre d'endpoints etcd « healthy » vus depuis CP.
# etcdctl n'est PAS sur l'hôte : on l'exécute DANS le conteneur etcd via crictl
# exec (même approche que le RUNBOOK/etcd-snapshot), DIRECTEMENT (l'image etcd n'a
# ni `env` ni `sh`). Renvoie 0 si le conteneur etcd est absent (CP arrêté).
etcd_healthy_count() {
    local cp=$1 cid
    cid=$(limactl shell "${cp}" sudo crictl ps --state Running --name '^etcd$' -q 2>/dev/null | head -1)
    [ -n "${cid}" ] || { echo 0; return 0; }
    limactl shell "${cp}" sudo crictl exec "${cid}" etcdctl \
        --endpoints=https://127.0.0.1:2379 \
        --cacert=/etc/kubernetes/pki/etcd/ca.crt \
        --cert=/etc/kubernetes/pki/etcd/server.crt \
        --key=/etc/kubernetes/pki/etcd/server.key \
        endpoint health --cluster 2>&1 \
        | grep -c 'is healthy' || true
}

# vip_leader VIP — le CP qui PORTE actuellement la VIP (celui dont une interface a
# l'adresse VIP/32). Vide si aucun (transitoire). Sert à cibler la panne du leader.
vip_leader() {
    local vip=$1 cp
    for cp in cp1 cp2 cp3; do
        if limactl shell "${cp}" ip -o addr show 2>/dev/null | grep -q " ${vip}/"; then
            printf '%s\n' "${cp}"
            return 0
        fi
    done
    printf '\n'
}

fail() {
    log "✗ ÉCHEC : $*"
    exit 1
}

# skip MESSAGE — sortie NEUTRE (rc 0) : ce scénario n'a de sens que sur la
# topologie ha-3cp ; sur un banc normal (1 CP) il se saute sans faire échouer
# run-all.sh (comme un scénario hors-périmètre).
skip() {
    log "⏭  SKIP : $*"
    exit 0
}

# ── Pré-requis : ha-3cp monté (3 CP) ─────────────────────────────────────────
log "Vérifier que le banc est en topologie ha-3cp (3 control-planes)"
cp_count=$(kubectl get nodes -l node-role.kubernetes.io/control-plane --no-headers 2>/dev/null | grep -c Ready || true)
[ "${cp_count}" -eq 3 ] || skip "topologie ha-3cp requise (3 CP Ready), trouvé ${cp_count} — scénario hors périmètre sur ce banc"

# VIP : fournie, ou dérivée de l'IP user-v2 d'un CP (même /24, .40 — cf. run_ha_3cp).
VIP=${HA_VIP:-}
if [ -z "${VIP}" ]; then
    cp_ip=$(limactl shell cp1 sh -c \
        "ip -4 -o addr show | awk '/192\.168\.104\./ {print \$4}' | cut -d/ -f1 | head -1" 2>/dev/null)
    [ -n "${cp_ip}" ] || fail "VIP indéterminable (passer HA_VIP=...)"
    VIP="${cp_ip%.*}.40"
fi
log "VIP de l'API : ${VIP}"

# ── 1. RÉFÉRENCE ─────────────────────────────────────────────────────────────
log "── Phase 1 : RÉFÉRENCE (3 CP, quorum 3/3, VIP répond) ──"

leader=$(vip_leader "${VIP}")
[ -n "${leader}" ] || fail "aucun CP ne porte la VIP ${VIP} (kube-vip down ?)"
log "VIP portée par : ${leader}"

# La VIP répond depuis un autre CP (preuve qu'elle est annoncée en L2, pas juste locale).
witness=cp1; [ "${leader}" = cp1 ] && witness=cp2
vip_responds "${VIP}" "${witness}" || fail "la VIP ne répond pas depuis ${witness} (réf.)"
log "✓ VIP répond depuis ${witness}"

healthy=$(etcd_healthy_count "${leader}")
[ "${healthy}" -eq 3 ] || fail "quorum etcd attendu 3/3, vu ${healthy}/3"
log "✓ quorum etcd 3/3"

# ── 2. PANNE du leader VIP ───────────────────────────────────────────────────
log "── Phase 2 : PANNE — arrêt de ${leader} (porteur de la VIP) ──"
limactl stop -f "${leader}" 2>&1 | tail -1 || true

# Un CP encore vivant pour observer (≠ leader arrêté).
alive=cp1; [ "${leader}" = cp1 ] && alive=cp2; [ "${leader}" = "${alive}" ] && alive=cp3

log "Attendre la BASCULE de la VIP (kube-vip réélit un leader, max 60 s)"
switched=0
for _ in $(seq 1 15); do
    if vip_responds "${VIP}" "${alive}"; then
        switched=1
        break
    fi
    sleep 4
done
[ "${switched}" -eq 1 ] || fail "la VIP n'a PAS basculé : injoignable depuis ${alive} après l'arrêt de ${leader}"
new_leader=$(vip_leader "${VIP}")
log "✓ VIP a basculé — répond depuis ${alive} (nouveau porteur : ${new_leader:-?})"
[ "${new_leader}" != "${leader}" ] || fail "la VIP est restée sur le CP arrêté (${leader}) — bascule KO"

log "Quorum etcd : majorité conservée (2/3 attendu, le 3ᵉ down) ?"
healthy=$(etcd_healthy_count "${alive}")
[ "${healthy}" -ge 2 ] || fail "quorum etcd PERDU (${healthy}/3 healthy) — l'API devrait être HS"
log "✓ quorum etcd ${healthy}/3 — majorité conservée"

log "L'API K8s reste-t-elle joignable via la VIP ? (depuis ${alive})"
limactl shell "${alive}" sh -c \
    "sudo KUBECONFIG=/etc/kubernetes/admin.conf kubectl get nodes >/dev/null 2>&1" \
    || fail "API K8s injoignable pendant la panne — la HA ne tient pas"
log "✓ API K8s répond pendant la panne d'1 CP"

log "Laisser tourner ${DOWNTIME_S}s sous panne"
sleep "${DOWNTIME_S}"

# ── 3. RESTORE ───────────────────────────────────────────────────────────────
log "── Phase 3 : RESTORE — redémarrage de ${leader} ──"
limactl start "${leader}" 2>&1 | tail -1 || true

log "Attendre le retour à 3/3 (quorum etcd, max 5 min)"
restored=0
for _ in $(seq 1 30); do
    if [ "$(etcd_healthy_count "${alive}")" -eq 3 ]; then
        restored=1
        break
    fi
    sleep 10
done
[ "${restored}" -eq 1 ] || fail "quorum etcd non revenu à 3/3 après restore de ${leader}"
log "✓ quorum etcd revenu à 3/3"

log "3 CP de nouveau Ready ?"
ready=$(kubectl get nodes -l node-role.kubernetes.io/control-plane --no-headers 2>/dev/null | grep -c Ready || true)
[ "${ready}" -eq 3 ] || fail "seulement ${ready}/3 CP Ready après restore"
log "✓ 3 CP Ready"

log "✓ Scénario 30 ha-3cp terminé : la VIP et le quorum etcd survivent à la perte d'1 CP."
