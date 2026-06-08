#!/usr/bin/env bats
#
# Tests des fonctions PURES de métrologie du banc Lima (test/lima/metrology.sh) :
# identifiant de run, profil, âge/verdict de fraîcheur (garde-fou ADR 0042),
# parsing Prometheus, rendu du bloc métriques. Aucun cluster ni VM requis — on
# source le fichier (qui ne fait que définir des fonctions) et on vérifie les
# sorties sur des fixtures fixes.

setup() {
    # shellcheck source=../lima/metrology.sh
    source "${BATS_TEST_DIRNAME}/../lima/metrology.sh"
}

# ─── metro_run_id ────────────────────────────────────────────────────────────

@test "metro_run_id : compose date compacte + profil + commit" {
    run metro_run_id "2026-06-08T15:30:00Z" ceph a1b2c3d
    [ "$status" -eq 0 ]
    [ "$output" = "2026-06-08T15-ceph-a1b2c3d" ]
}

@test "metro_run_id : déterministe (même entrée → même id)" {
    a=$(metro_run_id "2026-01-02T03:04:05Z" local-path deadbee)
    b=$(metro_run_id "2026-01-02T03:04:05Z" local-path deadbee)
    [ "$a" = "$b" ]
}

# ─── metro_profil ────────────────────────────────────────────────────────────

@test "metro_profil : 1 → ceph" {
    run metro_profil 1
    [ "$output" = ceph ]
}

@test "metro_profil : 0 → local-path" {
    run metro_profil 0
    [ "$output" = local-path ]
}

@test "metro_profil : vide → local-path (défaut)" {
    run metro_profil ""
    [ "$output" = local-path ]
}

# ─── metro_age_days ──────────────────────────────────────────────────────────

@test "metro_age_days : 7 jours pile" {
    run metro_age_days 0 604800
    [ "$output" = 7 ]
}

@test "metro_age_days : arrondi à l'entier inférieur" {
    run metro_age_days 0 700000   # 8,1 j → 8
    [ "$output" = 8 ]
}

@test "metro_age_days : futur borné à 0 (jamais négatif)" {
    run metro_age_days 1000 0
    [ "$output" = 0 ]
}

# ─── metro_freshness_verdict (cœur du garde-fou ADR 0042) ────────────────────

@test "metro_freshness_verdict : sous le seuil → frais" {
    run metro_freshness_verdict 3 7
    [ "$output" = frais ]
}

@test "metro_freshness_verdict : au seuil pile → frais" {
    run metro_freshness_verdict 7 7
    [ "$output" = frais ]
}

@test "metro_freshness_verdict : au-delà du seuil → perime" {
    run metro_freshness_verdict 8 7
    [ "$output" = perime ]
}

# ─── metro_last_date ─────────────────────────────────────────────────────────

@test "metro_last_date : prend la dernière entrée datée (format réel own-line)" {
    out=$(printf 'runs:\n  - id: a\n    date: 2026-06-01T00:00:00Z\n  - id: b\n    date: 2026-06-08T12:00:00Z\n' | metro_last_date)
    [ "$out" = "2026-06-08T12:00:00Z" ]
}

@test "metro_last_date : aucune date → vide" {
    out=$(printf 'runs:\n' | metro_last_date)
    [ -z "$out" ]
}

# ─── metro_fmt_dur ───────────────────────────────────────────────────────────

@test "metro_fmt_dur : 0 → 0m00s" {
    run metro_fmt_dur 0
    [ "$output" = 0m00s ]
}

@test "metro_fmt_dur : 754 s → 12m34s" {
    run metro_fmt_dur 754
    [ "$output" = 12m34s ]
}

# ─── metro_parse_prom_scalar ─────────────────────────────────────────────────

@test "metro_parse_prom_scalar : extrait la valeur d'un résultat instantané" {
    json='{"status":"success","data":{"resultType":"vector","result":[{"value":[1717000000,"123.45"]}]}}'
    out=$(printf '%s' "$json" | metro_parse_prom_scalar)
    [ "$out" = "123.45" ]
}

@test "metro_parse_prom_scalar : résultat vide → vide" {
    json='{"status":"success","data":{"result":[]}}'
    out=$(printf '%s' "$json" | metro_parse_prom_scalar)
    [ -z "$out" ]
}

# ─── metro_round ─────────────────────────────────────────────────────────────

@test "metro_round : arrondit un flottant" {
    run metro_round 123.7
    [ "$output" = 124 ]
}

@test "metro_round : NaN → ?" {
    run metro_round NaN
    [ "$output" = "?" ]
}

@test "metro_round : vide → ?" {
    run metro_round ""
    [ "$output" = "?" ]
}

# ─── metro_metrics_block ─────────────────────────────────────────────────────

@test "metro_metrics_block : rend les trois agrégats indentés" {
    out=$(metro_metrics_block 100 2048 1500)
    [[ "$out" == *"    metriques:"* ]]
    [[ "$out" == *"      cpu_core_s: 100"* ]]
    [[ "$out" == *"      ram_peak_mib: 2048"* ]]
    [[ "$out" == *"      ram_mean_mib: 1500"* ]]
}

@test "metro_metrics_block : conserve les ? (métrique indisponible)" {
    out=$(metro_metrics_block "?" "?" "?")
    [[ "$out" == *"cpu_core_s: ?"* ]]
}

@test "metro_metrics_block : stdout sans code couleur ANSI (pollue le YAML sinon)" {
    out=$(metro_metrics_block 1 2 3)
    # Aucun octet ESC (0x1b) : le bloc est destiné à un fichier YAML versionné.
    ! printf '%s' "$out" | grep -q "$(printf '\033')"
}

# ─── metro_sample_prometheus : Prometheus absent → stdout VIDE ────────────────
# Régression du bug « lignes ANSI dans runs-history.yaml » : quand Prometheus
# est absent, la fonction doit logger sur stderr et n'émettre RIEN sur stdout
# (sinon le warn polluait le bloc capturé). On stube KUBECTL (svc introuvable)
# et log/warn (pour ne pas dépendre de lib.sh).
@test "metro_sample_prometheus : Prometheus absent → stdout vide (pas de pollution)" {
    KUBECTL=(false)        # toute commande kubectl échoue → svc introuvable
    warn() { printf 'WARN %s\n' "$*" >&2; }
    log() { printf 'LOG %s\n' "$*" >&2; }
    out=$(metro_sample_prometheus 600 2>/dev/null)
    [ -z "$out" ]
}
