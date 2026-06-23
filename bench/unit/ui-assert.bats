#!/usr/bin/env bats
#
# Tests de la fonction pure classify_ui_http (atteignabilité UI en L4 NodePort/
# hostPort, ADR 0092 ; #232 scénario 28). Aucun cluster requis : on source la lib
# et on vérifie les verdicts. Le 1ᵉʳ argument est un libellé d'UI opaque (le
# verdict ne dépend que du code HTTP), conservé tel quel pour stabilité des tests.

setup() {
    # shellcheck source=../../bench/lima/ui-assert.sh
    source "${BATS_TEST_DIRNAME}/../../bench/lima/ui-assert.sh"
}

@test "classify_ui_http : 200 → ok" {
    run classify_ui_http grafana.cluster.lan 200
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "classify_ui_http : 302 (redirection login/install) → ok" {
    run classify_ui_http wordpress.cluster.lan 302
    [[ "$output" == ok\|* ]]
}

@test "classify_ui_http : 401 (protégé mais vivant) → ok" {
    run classify_ui_http argocd.cluster.lan 401
    [[ "$output" == ok\|* ]]
}

@test "classify_ui_http : 403 (protégé) → ok" {
    run classify_ui_http dashboard.cluster.lan 403
    [[ "$output" == ok\|* ]]
}

@test "classify_ui_http : code vide (timeout) → fail" {
    run classify_ui_http gitea.cluster.lan ""
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"timeout"* ]]
}

@test "classify_ui_http : 404 (route morte) → fail" {
    run classify_ui_http x.cluster.lan 404
    [[ "$output" == fail\|* ]]
}

@test "classify_ui_http : 500 (backend cassé) → fail" {
    run classify_ui_http x.cluster.lan 500
    [[ "$output" == fail\|* ]]
}

@test "classify_ui_http : 503 → fail" {
    run classify_ui_http x.cluster.lan 503
    [[ "$output" == fail\|* ]]
}
