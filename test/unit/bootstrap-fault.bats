#!/usr/bin/env bats
#
# Tests des fonctions pures du harnais d'ARRÊT INJECTÉ du bootstrap (#236,
# ADR 0050). Aucun banc requis : on source la lib et on vérifie les verdicts sur
# des fixtures fixes (même patron que dataops-assert.bats / state-classify.bats).

setup() {
    # shellcheck source=../../test/lima/bootstrap-fault-assert.sh
    source "${BATS_TEST_DIRNAME}/../../test/lima/bootstrap-fault-assert.sh"
}

# ─── parse_kubeadm_reset ───────────────────────────────────────────────────

@test "parse_kubeadm_reset détecte la tâche de compensation init" {
    run parse_kubeadm_reset <<< "TASK [k8s-initialization : Compensate the aborted init (kubeadm reset --force)]"
    [ "$status" -eq 0 ]
    [ "$output" = "yes" ]
}

@test "parse_kubeadm_reset détecte la signature kubeadm reset --force" {
    run parse_kubeadm_reset <<< "changed: [cp1] => kubeadm reset --force"
    [ "$output" = "yes" ]
}

@test "parse_kubeadm_reset détecte la trace [Reset] de kubeadm" {
    run parse_kubeadm_reset <<< "[Reset] Stopping the kubelet"
    [ "$output" = "yes" ]
}

@test "parse_kubeadm_reset : aucune compensation → no" {
    run parse_kubeadm_reset <<< "TASK [k8s-initialization : Initialize the control plane]"
    [ "$output" = "no" ]
}

@test "parse_kubeadm_reset : sortie vide → no" {
    run parse_kubeadm_reset < /dev/null
    [ "$output" = "no" ]
}

# ─── classify_compensation ─────────────────────────────────────────────────

@test "classify_compensation : 1er échoue + reset + 2e réussit → ok" {
    run classify_compensation 1 yes 0
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"ADR 0050"* ]]
}

@test "classify_compensation : 1er réussit (faute non prise) → fail" {
    run classify_compensation 0 no 0
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"RÉUSSI"* ]]
}

@test "classify_compensation : 1er échoue mais SANS reset → fail" {
    run classify_compensation 1 no 0
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"SANS compensation"* ]]
}

@test "classify_compensation : compensé mais re-jeu échoue → fail" {
    run classify_compensation 1 yes 2
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"re-jeu"* ]]
}

@test "classify_compensation : ordre des priorités — 1er=0 prime sur reset/2e" {
    # FIRST_RC=0 doit être attrapé en premier, peu importe le reste.
    run classify_compensation 0 yes 1
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"non prise"* ]]
}

# ─── classify_redeploy_recovery (reprise classe (a), sans compensation) ──────

@test "classify_redeploy_recovery : 1er échoue + 2e réussit + idempotent → ok" {
    run classify_redeploy_recovery 1 0 0
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"classe a"* ]]
}

@test "classify_redeploy_recovery : idempotence non mesurée (changed vide) → ok" {
    run classify_redeploy_recovery 1 0 ""
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"non mesurée"* ]]
}

@test "classify_redeploy_recovery : 1er réussit (faute non prise) → fail" {
    run classify_redeploy_recovery 0 0 0
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"non prise"* ]]
}

@test "classify_redeploy_recovery : re-jeu échoue → fail" {
    run classify_redeploy_recovery 1 2 ""
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"reconverge"* ]]
}

@test "classify_redeploy_recovery : re-jeu vert mais non idempotent → fail" {
    run classify_redeploy_recovery 1 0 3
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"NON idempotent"* ]]
}

@test "classify_redeploy_recovery : ordre — 1er=0 prime" {
    run classify_redeploy_recovery 0 1 5
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"non prise"* ]]
}
