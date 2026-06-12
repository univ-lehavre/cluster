#!/usr/bin/env bash
#
# Scénario 14 — Durcissement réseau Cilium (ADR 0019) : vérifier que le
# chiffrement WireGuard est RÉELLEMENT actif dans le datapath et que Hubble
# est opérationnel.
#
# Vérifie :
#   1. `cilium encrypt status` rapporte WireGuard actif sur TOUS les nœuds ;
#   2. l'interface `cilium_wg0` existe avec ≥ 1 peer (mesh inter-nœuds) ;
#   3. `hubble observe` retourne des flux (observabilité réseau opérationnelle).
#
# Pourquoi c'est valable en prod : ce sont des propriétés du datapath Cilium
# (interface WireGuard, peers, flux Hubble), identiques banc/prod. Le scénario
# n'exige PAS de dégrader le cluster.
#
# Pré-requis : Cilium installé avec encryption WireGuard + Hubble (cf.
# bootstrap/cni.sh / ADR 0019). kubectl configuré.
# Variables : EXPECTED_NODES (défaut: auto = nb de nœuds Ready)
set -euo pipefail

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Un pod cilium-agent quelconque sert de point d'exécution pour cilium-dbg /
# hubble (présents dans l'image de l'agent).
agent_pod() {
    kubectl -n kube-system get pod -l k8s-app=cilium \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

POD=$(agent_pod)
[ -n "$POD" ] || { log "✗ Aucun pod cilium-agent trouvé — Cilium est-il installé ?"; exit 1; }
in_agent() { kubectl -n kube-system exec "$POD" -c cilium-agent -- "$@"; }

# Nombre de nœuds attendus chiffrés = nœuds Ready (sauf override).
if [ -n "${EXPECTED_NODES:-}" ]; then
    expected=$EXPECTED_NODES
else
    expected=$(kubectl get nodes --no-headers 2>/dev/null | grep -cw Ready || echo 0)
fi
[ "${expected:-0}" -ge 1 ] || { log "✗ Impossible de compter les nœuds Ready"; exit 1; }
log "Nœuds attendus dans le mesh chiffré : $expected"

log "[1/3] cilium encrypt status — WireGuard doit être actif"
enc=$(in_agent cilium-dbg encrypt status 2>/dev/null || true)
printf '%s\n' "$enc" | sed 's/^/    /'
if ! printf '%s' "$enc" | grep -qi 'wireguard'; then
    log "✗ Chiffrement non-WireGuard ou désactivé — ADR 0019 non appliqué"
    log "  Appliquer : bootstrap/cni.sh (encryption.enabled + rollout agents)"
    exit 1
fi
log "✓ Chiffrement WireGuard rapporté actif"

log "[2/3] Interface cilium_wg0 + peers (mesh inter-nœuds)"
# Le nombre de peers attendu = (nœuds - 1) du point de vue d'un nœud.
peers=$(printf '%s' "$enc" | awk -F: '/[Nn]umber of peers/ {gsub(/ /,"",$2); print $2}')
if [ -z "$peers" ]; then
    # Repli : lire via wg directement.
    peers=$(in_agent wg show cilium_wg0 peers 2>/dev/null | grep -c . || echo 0)
fi
log "  peers vus depuis $POD : ${peers:-0} (attendu ≥ $((expected - 1)))"
if [ "${peers:-0}" -lt "$((expected - 1))" ]; then
    log "✗ Trop peu de peers WireGuard — le mesh chiffré est incomplet"
    exit 1
fi
log "✓ Mesh WireGuard complet ($peers peer(s))"

log "[3/3] Hubble observe — l'observabilité réseau doit retourner des flux"
# `hubble observe` peut : (a) échouer/timeout si le relay est KO, (b) réussir
# mais ne rien retourner si le cluster est au repos. On DISTINGUE les deux : on
# capture la sortie ET le code retour SÉPARÉMENT (sans masquer le rc par
# `|| echo 0`), pour ne pas attribuer un timeout à un « 0 flux ». `|| true`
# protège la capture sous `set -e` ; le vrai verdict est dans `hubble_rc`.
hubble_out=$(in_agent timeout 15 hubble observe --last 20 2>/dev/null) && hubble_rc=0 || hubble_rc=$?
if [ "${hubble_rc:-0}" -ne 0 ]; then
    log "  hubble observe a échoué (rc=$hubble_rc) — relay pas prêt ? nouvel essai"
    sleep 5
    hubble_out=$(in_agent timeout 15 hubble observe --last 20 2>/dev/null) && hubble_rc=0 || hubble_rc=$?
fi
if [ "${hubble_rc:-0}" -ne 0 ]; then
    log "✗ hubble observe échoue (rc=$hubble_rc) — Hubble Relay/agent non opérationnel"
    log "  Vérifier : cilium status (Hubble Relay) ; bootstrap/cni.sh (hubble.enabled)"
    exit 1
fi
flows=$(printf '%s' "$hubble_out" | grep -c . || true)
if [ "${flows:-0}" -lt 1 ]; then
    # commande OK mais aucun flux : générer un peu de trafic puis réessayer.
    log "  Hubble répond mais 0 flux (cluster au repos) — génération de trafic"
    kubectl -n kube-system get svc kube-dns >/dev/null 2>&1 || true
    sleep 5
    hubble_out=$(in_agent timeout 15 hubble observe --last 20 2>/dev/null || true)
    flows=$(printf '%s' "$hubble_out" | grep -c . || true)
fi
if [ "${flows:-0}" -lt 1 ]; then
    log "✗ Hubble opérationnel mais aucun flux observé même après trafic — à investiguer"
    exit 1
fi
log "✓ Hubble opérationnel ($flows flux observés)"

log "✓ Durcissement réseau Cilium vérifié : WireGuard actif + Hubble opérationnel (ADR 0019)."
exit 0
