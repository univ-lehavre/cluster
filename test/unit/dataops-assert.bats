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

@test "classify_marquez_ingest égal mais présent → ok (idempotence, L32)" {
    run classify_marquez_ingest 2 2
    [[ "$output" == ok\|* ]]
}

@test "classify_marquez_ingest after=0 → fail (rien ingéré)" {
    run classify_marquez_ingest 0 0
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

# ─── classify_egress_probe ─────────────────────────────────────────────────

@test "classify_egress_probe avec abouti + sans bloqué → ok (la NP ouvre le flux)" {
    run classify_egress_probe 403 000
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"sans=bloqué"* ]]
}

@test "classify_egress_probe 200 avec / 000 sans → ok" {
    run classify_egress_probe 200 000
    [[ "$output" == ok\|* ]]
}

@test "classify_egress_probe avec=000 → fail (la NP n'ouvre pas)" {
    run classify_egress_probe 000 000
    [[ "$output" == fail\|* ]]
}

@test "classify_egress_probe abouti des DEUX côtés → fail (default-deny ne mord pas)" {
    run classify_egress_probe 403 403
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"sans la NP"* ]]
}

@test "classify_egress_probe avec abouti / sans non mesuré → ok (allow atteste, deny non prouvé)" {
    run classify_egress_probe 200 ""
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"non mesuré"* ]]
}

@test "classify_egress_probe avec vide → skip (probe non exécutée)" {
    run classify_egress_probe "" ""
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
