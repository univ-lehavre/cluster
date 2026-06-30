#!/usr/bin/env bats
#
# Garde anti-régression (#359, ADR 0053) : TOUT play qui SSH sur un parc DISTANT
# (`hosts: cloud`, `all` ou `control`) DOIT importer le rôle `audit-log` en pre_tasks —
# il asserte que la topologie ciblée correspond à l'intention (EXPECTED_TARGET_KIND)
# AVANT toute tâche distante. Sans ce garde par-play, un montage banc a déjà SSHé sur
# la PROD (dataops play 2 + rollback.yaml orphelins, faille du 2026-06-16) ; les
# playbooks `hosts: all/control` (secure/upgrade/etcd-fetch) étaient un angle mort
# élargi le 2026-06-30.
#
# On ne PARSE pas le YAML finement (pas de dép. bats) : on compte, par fichier, les
# plays ciblant un parc distant (cloud|all|control) vs les imports `name: audit-log`.
# Couvre bootstrap/*.yaml ET bootstrap/security/*.yml. Un fichier avec ≥1 play distant
# DOIT avoir ≥1 audit-log. Heuristique stricte : un play distant sans garde est un
# faux-négatif REFUSÉ (mieux vaut un faux positif corrigé à la main).
#
# NB `localhost` n'est PAS gardé (pas de SSH distant ; ex. cnpg-secrets cible localhost
# par défaut — il importe quand même audit-log par cohérence, mais ce n'est pas exigé).

_ROOT="${BATS_TEST_DIRNAME}/../.."

@test "tout play ciblant un parc distant (cloud/all/control) importe le rôle audit-log" {
    local manquants=""
    for f in "${_ROOT}"/bootstrap/*.yaml "${_ROOT}"/bootstrap/security/*.yml; do
        [ -f "$f" ] || continue
        # nombre de plays ciblant un parc DISTANT (cloud|all|control) dans ce fichier
        local n_remote n_audit
        n_remote=$(grep -cE '^\s*hosts:\s*(cloud|all|control)\s*$' "$f" || true)
        [ "${n_remote:-0}" -eq 0 ] && continue
        # nombre d'imports du rôle audit-log (un par play gardé)
        n_audit=$(grep -cE 'name:\s*audit-log' "$f" || true)
        if [ "${n_audit:-0}" -lt "${n_remote}" ]; then
            manquants="${manquants} $(basename "$f")(distant=${n_remote},audit-log=${n_audit})"
        fi
    done
    [ -z "${manquants}" ] || {
        echo "Plays distants (cloud/all/control) SANS garde audit-log (ADR 0053) :${manquants}" >&2
        echo "Ajouter le pre_task audit-log (cf. bootstrap/cri.yaml)." >&2
        false
    }
}
