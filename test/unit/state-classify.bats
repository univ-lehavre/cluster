#!/usr/bin/env bats
#
# Tests des fonctions pures de classification de state.sh (audit P9 #12).
# Aucun cluster requis : on source la lib et on vérifie les verdicts sur des
# fixtures fixes.

setup() {
    # shellcheck source=../../bootstrap/lib/state-classify.sh
    source "${BATS_TEST_DIRNAME}/../../bootstrap/lib/state-classify.sh"
}

# ─── classify_passwd ───────────────────────────────────────────────────────

@test "classify_passwd MOD → ok" {
    run classify_passwd MOD 42
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"~42 j"* ]]
}

@test "classify_passwd NEVER → fail" {
    run classify_passwd NEVER 0
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"JAMAIS"* ]]
}

@test "classify_passwd AMBIGUOUS → skip" {
    run classify_passwd AMBIGUOUS 1
    [[ "$output" == skip\|* ]]
    [[ "$output" == *"ambigu"* ]]
}

@test "classify_passwd valeur inconnue → skip" {
    run classify_passwd UNKNOWN 0
    [[ "$output" == skip\|* ]]
}

@test "classify_passwd sans argument → skip (robustesse)" {
    run classify_passwd
    [[ "$output" == skip\|* ]]
}

# ─── classify_hdd ──────────────────────────────────────────────────────────

@test "classify_hdd 12 clean, 0 dirty, min 12 → ok" {
    run classify_hdd 12 12 0 12
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"12/12"* ]]
}

@test "classify_hdd dirty > 0 → fail (signatures résiduelles)" {
    run classify_hdd 12 10 2 12
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"résiduelle"* ]]
}

@test "classify_hdd pas assez de disques → fail" {
    run classify_hdd 8 8 0 12
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"< 12 requis"* ]]
}

@test "classify_hdd total illisible (?) → skip" {
    run classify_hdd '?' 0 0 12
    [[ "$output" == skip\|* ]]
}

@test "classify_hdd total vide → skip" {
    run classify_hdd '' 0 0 12
    [[ "$output" == skip\|* ]]
}

@test "classify_hdd dirty prime sur clean insuffisant" {
    # 1 clean (< min) ET 1 dirty : le dirty doit l'emporter (fail signature)
    run classify_hdd 2 1 1 12
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"résiduelle"* ]]
}

# ─── classify_device_state ─────────────────────────────────────────────────

@test "classify_device_state clean → ok" {
    run classify_device_state clean "/dev/nvme1n1"
    [[ "$output" == ok\|* ]]
}

@test "classify_device_state dirty → fail" {
    run classify_device_state dirty "/dev/nvme1n1"
    [[ "$output" == fail\|* ]]
}

@test "classify_device_state absent → skip" {
    run classify_device_state absent "/dev/nvme1n1"
    [[ "$output" == skip\|* ]]
}

@test "classify_device_state inconnu → skip avec l'état brut" {
    run classify_device_state weird "/var/lib/rook"
    [[ "$output" == skip\|* ]]
    [[ "$output" == *"weird"* ]]
}

# ─── count_field ───────────────────────────────────────────────────────────

@test "count_field extrait le bon champ" {
    run count_field 4 "12 12 0 clean clean"
    [ "$output" = "clean" ]
}

@test "count_field champ 1" {
    run count_field 1 "12 12 0 clean clean"
    [ "$output" = "12" ]
}

@test "count_field hors limite → vide" {
    run count_field 9 "12 12 0 clean clean"
    [ "$output" = "" ]
}
