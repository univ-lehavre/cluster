#!/usr/bin/env bash
#
# Injecte (ou retire) de la latence réseau entre les deux « sites » du mesh.
# Les sites sont VIRTUELS : la « distance » inter-site est simulée par tc netem
# posé DANS chaque VM Lima, sur l'interface user-v2 (le réseau 192.168.104.0/24
# que les deux clusters partagent et qui porte le trafic clustermesh).
#
# Usage :
#   ./latency.sh 50      # 50 ms de délai sur le lien inter-site (symétrique)
#   ./latency.sh 100 10  # 100 ms ± 10 ms de jitter
#   ./latency.sh clear   # retire toute règle netem
#   ./latency.sh status  # affiche les qdisc en place
#
# Premier (et seul) usage de tc/netem du dépôt — délibérément confiné au spike.
# Sur Lima (vraie VM), tc s'applique à une vraie interface : plus réaliste que le
# `docker exec` des conteneurs kind d'origine.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/clustermesh-latency/lib.sh
. "${HERE}/lib.sh"

require_lima

# tc/netem (iproute2) est présent sur l'image Debian 13 de Lima ; on l'installe
# au besoin (idempotent).
ensure_tc() {
    local vm=$1
    if vm_sh "${vm}" sh -c 'command -v tc' > /dev/null 2>&1; then
        return 0
    fi
    warn "tc absent dans ${vm} — installation de iproute2"
    vm_sh "${vm}" sudo sh -c 'apt-get update -qq && apt-get install -y -qq iproute2' \
        > /dev/null 2>&1 || die "impossible d'installer iproute2 dans ${vm}"
}

apply_delay() {
    local vm=$1 delay=$2 jitter=$3 iface
    ensure_tc "${vm}"
    iface=$(vm_uservv2_iface "${vm}")
    [ -n "${iface}" ] || die "${vm} : interface user-v2 introuvable"
    # replace = idempotent (add si absent, sinon remplace).
    if [ -n "${jitter}" ]; then
        vm_sh "${vm}" sudo tc qdisc replace dev "${iface}" root netem delay "${delay}ms" "${jitter}ms"
    else
        vm_sh "${vm}" sudo tc qdisc replace dev "${iface}" root netem delay "${delay}ms"
    fi
}

clear_delay() {
    local vm=$1 iface
    iface=$(vm_uservv2_iface "${vm}") || return 0
    [ -n "${iface}" ] || return 0
    vm_sh "${vm}" sudo tc qdisc del dev "${iface}" root > /dev/null 2>&1 || true
}

show_status() {
    local vm=$1 iface
    iface=$(vm_uservv2_iface "${vm}")
    printf '  %s (%s) : ' "${vm}" "${iface}"
    vm_sh "${vm}" sudo tc qdisc show dev "${iface}" 2> /dev/null | head -1 || echo "(injoignable)"
}

case "${1:-}" in
    clear)
        log "Retrait de la latence inter-site"
        clear_delay "${A_VM}"
        clear_delay "${B_VM}"
        ok "netem retiré (RTT nominal restauré)"
        ;;
    status)
        log "Règles netem en place"
        show_status "${A_VM}"
        show_status "${B_VM}"
        ;;
    "")
        die "usage : ./latency.sh <ms> [jitter_ms] | clear | status"
        ;;
    *)
        delay=$1
        jitter="${2:-}"
        case "${delay}" in
            '' | *[!0-9]*) die "délai invalide : '${delay}' (entier en ms attendu)" ;;
        esac
        # Délai posé des DEUX côtés → latence aller-retour ≈ 2 × delay (réaliste :
        # chaque sens du lien WAN a sa propre latence).
        log "Injection de ${delay} ms${jitter:+ ± ${jitter} ms} de chaque côté (RTT ≈ $((delay * 2)) ms)"
        apply_delay "${A_VM}" "${delay}" "${jitter}"
        apply_delay "${B_VM}" "${delay}" "${jitter}"
        ok "latence injectée — vérifie avec ./latency.sh status puis ./probe.sh"
        ;;
esac
