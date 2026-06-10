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
#   Verdict sur l'ingestion d'un événement OpenLineage : examine le nombre de jobs
#   Marquez avant/après le run émetteur.
#   - BEFORE ou AFTER illisible (vide/"?")   → skip
#   - AFTER >= 1                             → ok (au moins un job présent)
#   - AFTER == 0                             → fail (rien ingéré)
#   NB : on teste la PRÉSENCE (after >= 1), pas le delta : le run est idempotent
#   (Marquez ne vide pas le namespace), donc un 2ᵉ passage laisse after == before
#   alors que l'ingestion a bien eu lieu (drift L32). before sert d'info au message.
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
    if [ "$after" -ge 1 ]; then
        printf 'ok|Marquez : lineage présent (%s → %s jobs)\n' "$before" "$after"
    else
        printf 'fail|Marquez : aucun job ingéré (%s → %s)\n' "$before" "$after"
    fi
}

# classify_egress_probe WITH_NP_CODE WITHOUT_NP_CODE
#   Verdict sur la PREUVE de l'egress Internet du ns `dagster` (NP
#   allow-internet-egress, #256). On ne mocke PAS S3 : un mock intra-cluster
#   n'emprunte pas la règle testée (sous Cilium un `ipBlock` exclut les pods du
#   cluster). On probe donc une VRAIE sortie vers une IP publique sur 443, dans
#   les deux états :
#     - WITH_NP_CODE    : code HTTP curl AVEC la NP appliquée (doit ABOUTIR).
#     - WITHOUT_NP_CODE : code curl SANS la NP (default-deny doit MORDRE → "000").
#   Un code curl "000" = pas de réponse (timeout/connexion refusée) ; tout code
#   HTTP (2xx/3xx/4xx — même un 403 de S3) prouve que la connexion sortante a
#   abouti (c'est le FLUX réseau qu'on valide, pas une autorisation applicative).
#   Verdicts :
#     - WITH abouti (≠000) ET WITHOUT bloqué (=000) → ok (la NP, et ELLE SEULE, ouvre le flux)
#     - WITH "000"                                  → fail (la NP n'ouvre pas l'egress)
#     - WITH abouti mais WITHOUT abouti aussi       → fail (ça passe SANS la NP : default-deny ne mord pas)
#     - WITH vide / non collecté                    → skip (probe non exécutée)
classify_egress_probe() {
    local with=${1:-} without=${2:-}
    [ -n "$with" ] || { printf 'skip|Egress : probe non exécutée (code AVEC-NP vide)\n'; return; }
    if [ "$with" = "000" ]; then
        printf 'fail|Egress : la NP n'\''ouvre PAS la sortie Internet (curl=000 avec la policy)\n'
        return
    fi
    # WITH a abouti. Reste à confirmer que c'est bien la NP qui l'autorise.
    case "$without" in
        000)
            printf 'ok|Egress : flux Internet ouvert par la NP (avec=%s, sans=bloqué)\n' "$with"
            ;;
        "")
            # On n'a pas mesuré l'état SANS la NP : on atteste l'allow, sans
            # prouver le deny (moins fort, mais pas un échec).
            printf 'ok|Egress : sortie Internet aboutie (avec=%s ; deny sans-NP non mesuré)\n' "$with"
            ;;
        *)
            printf 'fail|Egress : la sortie aboutit AUSSI sans la NP (avec=%s, sans=%s) — default-deny ne mord pas\n' "$with" "$without"
            ;;
    esac
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
