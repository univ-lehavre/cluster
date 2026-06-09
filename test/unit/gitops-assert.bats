#!/usr/bin/env bats
#
# Tests des fonctions pures d'assertion du scénario GitOps → workflows atlas
# (#231). Aucun cluster requis : on source la lib et on vérifie les verdicts sur
# des fixtures fixes (même patron que dataops-assert.bats).

setup() {
    # shellcheck source=../../test/lima/gitops-assert.sh
    source "${BATS_TEST_DIRNAME}/../../test/lima/gitops-assert.sh"
}

# ─── classify_argocd_app ───────────────────────────────────────────────────

@test "classify_argocd_app Synced/Healthy → ok" {
    run classify_argocd_app "Synced" "Healthy"
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "classify_argocd_app OutOfSync/Healthy → fail" {
    run classify_argocd_app "OutOfSync" "Healthy"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"OutOfSync"* ]]
}

@test "classify_argocd_app Synced/Degraded → fail" {
    run classify_argocd_app "Synced" "Degraded"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"Degraded"* ]]
}

@test "classify_argocd_app sync vide → fail (Application introuvable)" {
    run classify_argocd_app "" "Healthy"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"introuvable"* ]]
}

@test "classify_argocd_app health vide → fail" {
    run classify_argocd_app "Synced" ""
    [[ "$output" == fail\|* ]]
}

# ─── classify_webhook_trigger ──────────────────────────────────────────────

@test "classify_webhook_trigger révision changée → ok" {
    run classify_webhook_trigger "abc123" "def456"
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"abc123"* ]]
    [[ "$output" == *"def456"* ]]
}

@test "classify_webhook_trigger révision inchangée → fail (pas déclenché)" {
    run classify_webhook_trigger "abc123" "abc123"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"inchangée"* ]]
}

@test "classify_webhook_trigger after vide → fail (webhook non reçu)" {
    run classify_webhook_trigger "abc123" ""
    [[ "$output" == fail\|* ]]
}

@test "classify_webhook_trigger before vide mais after présent → ok (1re sync)" {
    run classify_webhook_trigger "" "def456"
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}
