#!/usr/bin/env bats
#
# Tests des fonctions pures d'assertion du harnais dataops-chain (#148).
# Aucun cluster requis : on source la lib et on vérifie les verdicts sur des
# fixtures fixes (même patron que state-classify.bats).

setup() {
    # shellcheck source=../../test/lima/dataops-assert.sh
    source "${BATS_TEST_DIRNAME}/../../test/lima/dataops-assert.sh"
}

# ─── classify_cnpg_health ──────────────────────────────────────────────────

@test "classify_cnpg_health sain → ok" {
    run classify_cnpg_health "Cluster in healthy state"
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "classify_cnpg_health vide → skip" {
    run classify_cnpg_health ""
    [[ "$output" == skip\|* ]]
}

@test "classify_cnpg_health phase inconnue → fail" {
    run classify_cnpg_health "Setting up primary"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"Setting up primary"* ]]
}

# ─── classify_dagster_run ──────────────────────────────────────────────────

@test "classify_dagster_run SUCCESS → ok" {
    run classify_dagster_run SUCCESS
    [[ "$output" == ok\|* ]]
}

@test "classify_dagster_run FAILURE → fail" {
    run classify_dagster_run FAILURE
    [[ "$output" == fail\|* ]]
}

@test "classify_dagster_run vide → skip" {
    run classify_dagster_run ""
    [[ "$output" == skip\|* ]]
}

# ─── classify_marquez_ingest ───────────────────────────────────────────────

@test "classify_marquez_ingest before<after → ok" {
    run classify_marquez_ingest 0 1
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"0 → 1"* ]]
}

@test "classify_marquez_ingest égal → fail" {
    run classify_marquez_ingest 2 2
    [[ "$output" == fail\|* ]]
}

@test "classify_marquez_ingest compteur illisible → skip" {
    run classify_marquez_ingest "?" 1
    [[ "$output" == skip\|* ]]
}

@test "classify_marquez_ingest non numérique → skip" {
    run classify_marquez_ingest abc 1
    [[ "$output" == skip\|* ]]
}

# ─── parse_ol_job_count ────────────────────────────────────────────────────

@test "parse_ol_job_count totalCount nominal" {
    run parse_ol_job_count '{"jobs":[],"totalCount":3}'
    [ "$output" = "3" ]
}

@test "parse_ol_job_count via longueur de jobs" {
    run parse_ol_job_count '{"jobs":[{"name":"a"},{"name":"b"}]}'
    [ "$output" = "2" ]
}

@test "parse_ol_job_count json vide → ?" {
    run parse_ol_job_count ""
    [ "$output" = "?" ]
}

@test "parse_ol_job_count json illisible → ?" {
    run parse_ol_job_count 'pas du json'
    [ "$output" = "?" ]
}

@test "parse_ol_job_count champ absent → ?" {
    run parse_ol_job_count '{"namespaces":[]}'
    [ "$output" = "?" ]
}
