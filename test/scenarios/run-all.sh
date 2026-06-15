#!/usr/bin/env bash
#
# Runner agrégé des scénarios de test (audit P2 #15 / 02-tests).
#
# Exécute les scénarios `NN-*.sh` dans l'ordre, capture le code de sortie de
# chacun, et affiche un tableau récapitulatif PASS/FAIL à la fin. Entre deux
# scénarios DESTRUCTIFS (qui touchent à l'état du cluster), attend le retour à
# `HEALTH_OK` côté Ceph pour ne pas enchaîner sur un cluster encore dégradé.
#
# Usage :
#   test/scenarios/run-all.sh                  # tous les scénarios (kubectl)
#   SKIP='03 04' test/scenarios/run-all.sh     # exclure des scénarios (par n°)
#   ONLY='01 02 07' test/scenarios/run-all.sh  # n'exécuter que ceux-là
#   HOSTS='cp1 node1' test/scenarios/run-all.sh  # inclut le 13 (host)
#   TARGET_IP=192.168.67.11 ONLY='16' …        # joue un scénario SSH ciblé
#
# ⚠️ Sur le banc Vagrant, la phase « restore » des scénarios 03/04 ne se valide
# pas (artefacts arm64 sans valeur prod — cf. test/scenarios/README.md). Les
# exclure avec SKIP='03 04' sur le banc.
#
# ℹ️ Scénarios SSH (interrogent/attaquent les nœuds, pas kubectl) : sautés par
# défaut, joués si l'accès est fourni (HOSTS pour 13 ; TARGET_IP/NODE_IP pour
# 16/19/22) ou via ONLY :
#   - 13      durcissement hôte (lecture seule via state.sh) ;
#   - 16/19/22 sécurité ACTIVE offensive/chaos (ADR 0025).
#
# 🚨 SÉCURITÉ ACTIVE (16-22, ADR 0025) : scénarios OFFENSIFS (brute-force,
# évasion, exfiltration) et CHAOS (perte réseau, kill, saturation). À LANCER
# UNIQUEMENT SUR UN BANC JETABLE — jamais une topologie réelle/prod ni une cible
# tierce. Chaque scénario porte une garde « banc-only » (refus hors plage de
# banc, sauf BANC=1). 19/20/21 sont destructifs → attente HEALTH_OK après.
# 16/22 dépendent de #131 pour le maillon Alerte (best-effort/skip sinon).
#
# Sortie : 0 si tous les scénarios joués passent, 1 sinon.
set -uo pipefail

# KUBECONFIG en chemin ABSOLU avant le `cd` (drift L50) : ce runner se déplace
# dans son propre dossier, donc un KUBECONFIG relatif (ex.
# `test/lima/.work/kubeconfig`) deviendrait invalide → kubectl retomberait sur
# localhost:8080 et TOUS les scénarios échoueraient/skipperaient à tort. On le
# résout depuis le CWD courant pendant qu'il est encore correct.
if [ -n "${KUBECONFIG:-}" ] && [ "${KUBECONFIG#/}" = "${KUBECONFIG}" ]; then
    KUBECONFIG="$(cd "$(dirname "${KUBECONFIG}")" && pwd)/$(basename "${KUBECONFIG}")"
    export KUBECONFIG
fi

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 2

SKIP=${SKIP:-}
ONLY=${ONLY:-}

# Wrapper ceph (toolbox) — identique aux scénarios.
ceph() { kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph "$@"; }

wait_health_ok() {
    # Best-effort : si la toolbox n'est pas là (pas de Ceph), on n'attend pas.
    kubectl -n rook-ceph get deploy/rook-ceph-tools >/dev/null 2>&1 || return 0
    echo "  … attente HEALTH_OK (5 min max) avant le scénario suivant"
    for _ in $(seq 1 30); do
        [ "$(ceph health -f json 2>/dev/null | jq -r '.status' 2>/dev/null)" = "HEALTH_OK" ] && return 0
        sleep 10
    done
    echo "  ⚠️ HEALTH_OK non atteint — on continue quand même (à investiguer)"
    return 0
}

# Scénarios destructifs (changent l'état du cluster) → attente HEALTH_OK après.
# 03/04/05 = résilience ; 19/20/21 = chaos (ADR 0025) ; 30 = panne CP HA (ha-3cp,
# local-path → wait_health_ok no-op sans Ceph ; le scénario se restaure lui-même).
is_destructive() { case "$1" in 03|04|05|19|20|21|30) return 0 ;; *) return 1 ;; esac; }

# Scénarios qui interrogent/attaquent les nœuds par SSH (pas kubectl) et n'ont
# pas leur place dans un run kubectl-only :
#   13 = durcissement hôte (via state.sh) ;
#   16/19/22 = sécurité ACTIVE offensive/chaos côté HÔTE (ADR 0025) — DANGEREUX
#   hors banc. On les saute par défaut, sauf si l'opérateur a fourni un accès SSH
#   (HOSTS pour le 13 ; TARGET_IP/NODE_IP pour 16/19/22) OU les force via ONLY.
# Ce skip par défaut évite de déclencher un brute-force/une partition par
# inadvertance dans un run agrégé.
needs_ssh() { case "$1" in 13|16|19|22) return 0 ;; *) return 1 ;; esac; }

results=()
rc_global=0

for script in [0-9][0-9]-*.sh; do
    num=${script%%-*}
    if [ -n "$ONLY" ] && ! grep -qw "$num" <<<"$ONLY"; then continue; fi
    if [ -n "$SKIP" ] && grep -qw "$num" <<<"$SKIP"; then
        results+=("SKIP  $script")
        continue
    fi
    # Skip auto des scénarios SSH si aucun accès fourni et pas demandé via ONLY.
    # Signal d'accès : HOSTS (13) ou TARGET_IP/NODE_IP (16/19/22, sécurité active).
    if needs_ssh "$num" \
        && [ -z "${HOSTS:-}" ] && [ -z "${TARGET_IP:-}" ] && [ -z "${NODE_IP:-}" ] \
        && ! grep -qw "$num" <<<"$ONLY"; then
        results+=("SKIP  $script (SSH — fournir HOSTS/TARGET_IP/NODE_IP, ou ONLY='$num')")
        continue
    fi

    echo "═══ $script ═══"
    if bash "$script"; then
        results+=("PASS  $script")
    else
        rc=$?
        results+=("FAIL($rc) $script")
        rc_global=1
    fi

    is_destructive "$num" && wait_health_ok
done

echo
echo "═══ Récapitulatif ═══"
for r in "${results[@]}"; do
    case "$r" in
        PASS*) printf '  ✓ %s\n' "$r" ;;
        SKIP*) printf '  ⏭ %s\n' "$r" ;;
        *)     printf '  ✗ %s\n' "$r" ;;
    esac
done

[ "$rc_global" -eq 0 ] && echo "Tous les scénarios joués ont réussi." \
    || echo "Au moins un scénario a échoué (voir ✗ ci-dessus)."
exit "$rc_global"
