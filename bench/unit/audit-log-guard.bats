#!/usr/bin/env bats
#
# Garde anti-régression (#359, ADR 0053) : TOUT play `hosts: cloud` de bootstrap/*.yaml
# (qui SSH sur les nœuds) DOIT importer le rôle `audit-log` en pre_tasks — il asserte
# que la topologie ciblée correspond à l'intention (EXPECTED_TARGET_KIND) AVANT toute
# tâche distante. Sans ce garde par-play, un montage banc a déjà SSHé sur la PROD
# (dataops play 2 + rollback.yaml étaient orphelins, faille du 2026-06-16).
#
# On ne PARSE pas le YAML finement (pas de dép. bats supplémentaire) : on compte, par
# fichier, les plays `hosts: cloud` vs les imports `name: audit-log`. Un fichier avec ≥1
# play cloud DOIT avoir ≥1 audit-log. Heuristique volontairement stricte : un play cloud
# sans garde est un faux-négatif qu'on REFUSE (mieux vaut un faux positif corrigé à la main).

_ROOT="${BATS_TEST_DIRNAME}/../.."

@test "tout play 'hosts: cloud' de bootstrap/ importe le rôle audit-log" {
    local manquants=""
    for f in "${_ROOT}"/bootstrap/*.yaml; do
        # nombre de plays ciblant les nœuds (hosts: cloud) dans ce fichier
        local n_cloud n_audit
        n_cloud=$(grep -cE '^\s*hosts:\s*cloud\s*$' "$f" || true)
        [ "${n_cloud:-0}" -eq 0 ] && continue
        # nombre d'imports du rôle audit-log (un par play gardé)
        n_audit=$(grep -cE 'name:\s*audit-log' "$f" || true)
        if [ "${n_audit:-0}" -lt "${n_cloud}" ]; then
            manquants="${manquants} $(basename "$f")(cloud=${n_cloud},audit-log=${n_audit})"
        fi
    done
    [ -z "${manquants}" ] || {
        echo "Plays 'hosts: cloud' SANS garde audit-log (ADR 0053) :${manquants}" >&2
        echo "Ajouter le pre_task audit-log (cf. bootstrap/cri.yaml)." >&2
        false
    }
}
