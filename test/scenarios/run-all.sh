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
#   test/scenarios/run-all.sh                  # tous les scénarios
#   SKIP='03 04' test/scenarios/run-all.sh     # exclure des scénarios (par n°)
#   ONLY='01 02 07' test/scenarios/run-all.sh  # n'exécuter que ceux-là
#
# ⚠️ Sur le banc Vagrant, la phase « restore » des scénarios 03/04 ne se valide
# pas (artefacts arm64 sans valeur prod — cf. test/scenarios/README.md). Les
# exclure avec SKIP='03 04' sur le banc.
#
# Sortie : 0 si tous les scénarios joués passent, 1 sinon.
set -uo pipefail

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
is_destructive() { case "$1" in 03|04|05) return 0 ;; *) return 1 ;; esac; }

results=()
rc_global=0

for script in [0-9][0-9]-*.sh; do
    num=${script%%-*}
    if [ -n "$ONLY" ] && ! grep -qw "$num" <<<"$ONLY"; then continue; fi
    if [ -n "$SKIP" ] && grep -qw "$num" <<<"$SKIP"; then
        results+=("SKIP  $script")
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
