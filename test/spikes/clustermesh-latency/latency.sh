#!/usr/bin/env bash
#
# Injecte (ou retire) de la latence réseau entre les deux « sites » du mesh.
# Les sites sont VIRTUELS : la « distance » inter-site est simulée par tc netem
# posé dans les conteneurs de nœuds kind, sur l'interface eth0 (le réseau Docker
# que les deux clusters partagent et qui porte le trafic clustermesh).
#
# Usage :
#   ./latency.sh 50      # 50 ms de délai sur le lien inter-site (symétrique)
#   ./latency.sh 100 10  # 100 ms ± 10 ms de jitter
#   ./latency.sh clear   # retire toute règle netem
#   ./latency.sh status  # affiche les qdisc en place
#
# Premier (et seul) usage de tc/netem du dépôt — délibérément confiné au spike.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/clustermesh-latency/lib.sh
. "${HERE}/lib.sh"

require_docker
IFACE="${NETEM_IFACE:-eth0}" # interface du conteneur kind portant le réseau Docker

# tc/netem ne sont pas garantis dans l'image kind ; on installe iproute2 au besoin
# (une fois, idempotent). Le conteneur kind est Debian-like (apt).
ensure_tc() {
    local cname=$1
    if docker exec "${cname}" sh -c 'command -v tc' > /dev/null 2>&1; then
        return 0
    fi
    warn "tc absent dans ${cname} — installation de iproute2"
    docker exec "${cname}" sh -c 'apt-get update -qq && apt-get install -y -qq iproute2' \
        > /dev/null 2>&1 || die "impossible d'installer iproute2 dans ${cname}"
}

apply_delay() {
    local cname=$1 delay=$2 jitter=$3
    ensure_tc "${cname}"
    # replace = idempotent (add si absent, sinon remplace).
    if [ -n "${jitter}" ]; then
        docker exec "${cname}" tc qdisc replace dev "${IFACE}" root netem delay "${delay}ms" "${jitter}ms"
    else
        docker exec "${cname}" tc qdisc replace dev "${IFACE}" root netem delay "${delay}ms"
    fi
}

clear_delay() {
    local cname=$1
    docker exec "${cname}" tc qdisc del dev "${IFACE}" root > /dev/null 2>&1 || true
}

show_status() {
    local cname=$1
    printf '  %s : ' "${cname}"
    docker exec "${cname}" tc qdisc show dev "${IFACE}" 2> /dev/null | head -1 || echo "(injoignable)"
}

C1_NODE=$(node_container "${C1_KIND}")
C2_NODE=$(node_container "${C2_KIND}")

case "${1:-}" in
    clear)
        log "Retrait de la latence inter-site"
        clear_delay "${C1_NODE}"
        clear_delay "${C2_NODE}"
        ok "netem retiré (RTT nominal restauré)"
        ;;
    status)
        log "Règles netem en place"
        show_status "${C1_NODE}"
        show_status "${C2_NODE}"
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
        apply_delay "${C1_NODE}" "${delay}" "${jitter}"
        apply_delay "${C2_NODE}" "${delay}" "${jitter}"
        ok "latence injectée — vérifie avec ./latency.sh status puis ./probe.sh"
        ;;
esac
