#!/usr/bin/env bash
#
# Fonctions PURES d'assertion pour le harnais dataops-chain (#148 / bats).
#
# Comme bootstrap/lib/state-classify.sh : ces fonctions ne font NI kubectl, NI
# réseau. Elles prennent en entrée des valeurs déjà collectées et renvoient un
# verdict `STATUS|message` sur stdout (STATUS ∈ {ok, fail, skip}). But : rendre la
# logique de décision du harnais testable sans cluster (test/unit/dataops-assert.bats).
#
# Convention : une ligne "STATUS|message". L'appelant découpe sur le premier '|'.
# Aucune fonction n'appelle `exit` ni n'écrit ailleurs que sur stdout.

# classify_cnpg_health PHASE
#   Mappe la phase d'un Cluster CNPG (champ .status.phase) vers un verdict.
#   - "Cluster in healthy state"  → ok
#   - vide / "?"                  → skip (cluster absent / pas encore de statut)
#   - autre                       → fail (en cours de bascule, dégradé…)
classify_cnpg_health() {
    local phase=${1:-}
    case "$phase" in
        "Cluster in healthy state")
            printf 'ok|CNPG : cluster pg sain (%s)\n' "$phase"
            ;;
        "" | "?")
            printf 'skip|CNPG : cluster pg absent ou sans statut\n'
            ;;
        *)
            printf 'fail|CNPG : cluster pg non sain (phase=%s)\n' "$phase"
            ;;
    esac
}

# classify_dagster_run STATUS
#   Verdict sur l'issue d'un run Dagster (statut DagsterRunStatus).
#   - SUCCESS            → ok
#   - FAILURE / CANCELED → fail
#   - vide / autre       → skip (run introuvable / encore en cours)
classify_dagster_run() {
    local status=${1:-}
    case "$status" in
        SUCCESS)
            printf 'ok|Dagster : run e2e SUCCESS\n'
            ;;
        FAILURE | CANCELED)
            printf 'fail|Dagster : run e2e %s\n' "$status"
            ;;
        *)
            printf 'skip|Dagster : run e2e sans issue (status=%s)\n' "${status:-vide}"
            ;;
    esac
}

# classify_marquez_ingest BEFORE AFTER
#   Verdict sur l'ingestion d'un événement OpenLineage : compare le nombre de jobs
#   Marquez avant/après le run émetteur.
#   - BEFORE ou AFTER illisible (vide/"?")   → skip
#   - AFTER > BEFORE                         → ok (au moins un job ingéré)
#   - AFTER <= BEFORE                        → fail (rien ingéré)
classify_marquez_ingest() {
    local before=${1:-} after=${2:-}
    case "$before$after" in
        *'?'* | '')
            printf 'skip|Marquez : compteur de jobs illisible (API joignable ?)\n'
            return
            ;;
    esac
    if ! printf '%s' "$before" | grep -qE '^[0-9]+$' || ! printf '%s' "$after" | grep -qE '^[0-9]+$'; then
        printf 'skip|Marquez : compteur de jobs non numérique (before=%s after=%s)\n' "$before" "$after"
        return
    fi
    if [ "$after" -gt "$before" ]; then
        printf 'ok|Marquez : lineage ingéré (%s → %s jobs)\n' "$before" "$after"
    else
        printf 'fail|Marquez : aucun job ingéré (%s → %s)\n' "$before" "$after"
    fi
}

# parse_ol_job_count JSON
#   Extrait le nombre de jobs d'une réponse Marquez GET /api/v1/namespaces/<ns>/jobs
#   (objet {"jobs":[...], "totalCount":N}). Pur (python3). Renvoie un entier sur
#   stdout, ou "?" si le JSON est vide/illisible/sans champ exploitable.
parse_ol_job_count() {
    local json=${1:-}
    [ -n "$json" ] || { printf '?\n'; return; }
    printf '%s' "$json" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print("?"); sys.exit(0)
if isinstance(d, dict):
    if isinstance(d.get("totalCount"), int):
        print(d["totalCount"]); sys.exit(0)
    if isinstance(d.get("jobs"), list):
        print(len(d["jobs"])); sys.exit(0)
print("?")
' 2>/dev/null || printf '?\n'
}
