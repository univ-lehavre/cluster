#!/usr/bin/env bash
#
# Scénario 29 — INTÉGRATION : une code-location EXTERNE (fournie par un
# consommateur, ex. atlas) branchée sur l'orchestrateur Dagster du socle
# fonctionne-t-elle de bout en bout ? (#264)
#
# Généralise la preuve `dataops_chain_emit_and_verify` (asset jouet codé en dur)
# en harnais PARAMÉTRABLE : le cluster fournit le « comment valider » (déployée ?
# branchée ? un run aboutit ? l'aval reçoit ?), le consommateur fournit le
# « contenu » (image, location, job). Frontière ADR 0022/0045 respectée : le
# cluster ne connaît pas le métier — il lance un job nommé et vérifie l'aval.
#
# Chemin RÉEL : le run est lancé par GraphQL sur le webserver (launchRun), comme
# l'UI / atlas — pas un Job k8s synthétique. Le K8sRunLauncher crée le pod de
# run ; on attend la complétion puis on vérifie le lineage Marquez (et,
# optionnellement, qu'un objet est apparu dans un bucket S3).
#
# Pré-requis : banc atlas monté (dataops + gitops-seed) + une code-location
# externe DÉJÀ déployée (par GitOps, scénario 27) et branchée dans le workspace.
# SKIP NEUTRE (exit 0) si absente — sauf STRICT_CODELOC=1.
#
# Variables (contenu fourni par le consommateur) :
#   CODELOC_NAME=citation       nom de la location dans le workspace Dagster
#   CODELOC_JOB=ingestion_job   job Dagster à lancer
#   CODELOC_REPO=__repository__ nom du repository Dagster (défaut : Definitions)
#   CODELOC_NS=dagster          namespace de l'orchestrateur
#   CODELOC_RUN_CONFIG=''       runConfigData YAML/JSON optionnel (BORNE le run)
#   CODELOC_TIMEOUT=600         attente max de complétion du run (secondes)
#   OL_NAMESPACE=dagster        namespace OpenLineage où chercher le lineage
#   VERIFY_S3_ENDPOINT=''       (option) endpoint S3 à vérifier en aval
#   VERIFY_S3_BUCKET=''         (option) bucket où un objet doit apparaître
#   STRICT_CODELOC=1            échoue (au lieu de skip) si prérequis absents
#
# ⚠️ BORNER le run (jobs métier lourds). Le harnais lance le VRAI job ; un sync
# complet (ex. snapshot OpenAlex = To) ne tient pas dans un test. Passer
# CODELOC_RUN_CONFIG avec la config qui réduit le volume — le SCHÉMA est propre
# au job (le consommateur le fournit). Exemple PROUVÉ pour citation/ingestion_job
# (asset `raw_snapshot`, ~14 s sur le banc, 1 fichier de 915 Ko) :
#   CODELOC_RUN_CONFIG='ops:
#     raw_snapshot:
#       config: { partition: "updated_date=2016-06-24", sample_size: 1, entities: ["works"] }'
# Si le schéma ne correspond pas, launchRun renvoie RunConfigValidationInvalid
# (le harnais le rapporte) — c'est au consommateur d'aligner sur SON job.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

STRICT_CODELOC=${STRICT_CODELOC:-0}
CODELOC_NAME=${CODELOC_NAME:-}
CODELOC_JOB=${CODELOC_JOB:-}
CODELOC_REPO=${CODELOC_REPO:-__repository__}
CODELOC_NS=${CODELOC_NS:-dagster}
CODELOC_RUN_CONFIG=${CODELOC_RUN_CONFIG:-}
CODELOC_TIMEOUT=${CODELOC_TIMEOUT:-600}
OL_NAMESPACE=${OL_NAMESPACE:-dagster}
VERIFY_S3_ENDPOINT=${VERIFY_S3_ENDPOINT:-}
VERIFY_S3_BUCKET=${VERIFY_S3_BUCKET:-}

WEBSERVER_URL="http://dagster-dagster-webserver.${CODELOC_NS}.svc.cluster.local:80/graphql"

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Assertions PURES (testées en bats) : parse_ol_job_count, classify_marquez_ingest.
# shellcheck source=test/lima/dataops-assert.sh
. ../lima/dataops-assert.sh

skip_or_fail() {
    if [ "${STRICT_CODELOC}" = 1 ]; then
        log "✗ STRICT_CODELOC=1 et prérequis manquant : $1"
        exit 1
    fi
    log "skip — $1"
    log "  Fournir CODELOC_NAME + CODELOC_JOB (code-location déployée, cf. scénario 27)."
    exit 0
}

# Requête GraphQL au webserver depuis un pod éphémère (le Service est interne).
# $1 = payload JSON ; stdout = réponse JSON brute.
gql() {
    kubectl -n "${CODELOC_NS}" run "gql-29-$$-${RANDOM}" --rm -i --restart=Never \
        --image=curlimages/curl:8.11.1 --quiet -- \
        curl -sS -X POST "${WEBSERVER_URL}" \
        -H 'Content-Type: application/json' \
        --data "$1" --max-time 60 2>/dev/null
}

# Compteur de jobs Marquez (même probe que le scénario 27/23).
marquez_job_count() {
    local json
    json=$(kubectl -n marquez run "marquez-29-$$" --rm -i --restart=Never \
        --image=busybox:1.36 --quiet -- \
        sh -c "wget -qO- 'http://marquez.marquez.svc.cluster.local:5000/api/v1/namespaces/${OL_NAMESPACE}/jobs' 2>/dev/null" 2>/dev/null)
    parse_ol_job_count "${json}"
}

# ── Pré-requis : contenu fourni + orchestrateur + location branchée ──────────
[ -n "${CODELOC_NAME}" ] || skip_or_fail "CODELOC_NAME non fourni (aucune code-location externe à valider)"
[ -n "${CODELOC_JOB}" ] || skip_or_fail "CODELOC_JOB non fourni"
kubectl -n "${CODELOC_NS}" get deploy dagster-dagster-webserver >/dev/null 2>&1 \
    || skip_or_fail "webserver Dagster absent (phase dataops non montée)"

log "[1/5] la location « ${CODELOC_NAME} » est-elle branchée et saine ?"
locations=$(gql '{"query":"{ workspaceOrError { ... on Workspace { locationEntries { name locationOrLoadError { __typename } } } } }"}')
printf '%s' "${locations}" | grep -q "\"name\":\"${CODELOC_NAME}\"" \
    || skip_or_fail "location « ${CODELOC_NAME} » absente du workspace (gRPC déployé ? workspace patché ?)"
printf '%s' "${locations}" | grep -q "RepositoryLocation" \
    || skip_or_fail "location « ${CODELOC_NAME} » en erreur de chargement (gRPC injoignable ?)"
log "  ✓ location chargée"

log "[2/5] le job « ${CODELOC_JOB} » est-il exposé ?"
jobs=$(gql '{"query":"{ repositoriesOrError { ... on RepositoryConnection { nodes { location { name } jobs { name } } } } }"}')
printf '%s' "${jobs}" | grep -q "\"name\":\"${CODELOC_JOB}\"" \
    || skip_or_fail "job « ${CODELOC_JOB} » introuvable dans la location"
log "  ✓ job présent"

# Compteur lineage AVANT (preuve d'ingestion par delta/présence, idempotent L32).
job_before=$(marquez_job_count)

log "[3/5] lancement du run (GraphQL launchRun — le chemin réel de l'UI/atlas)"
# runConfigData optionnel (borne le run : sous-échantillon, dry-run métier…).
run_config_json='"{}"'
[ -n "${CODELOC_RUN_CONFIG}" ] && run_config_json=$(printf '%s' "${CODELOC_RUN_CONFIG}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
launch_payload=$(python3 - "$CODELOC_NAME" "$CODELOC_JOB" "$run_config_json" "$CODELOC_REPO" <<'PY'
import json, sys
loc, job, run_config, repo = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), sys.argv[4]
query = """mutation($p: ExecutionParams!) { launchRun(executionParams: $p) {
  __typename
  ... on LaunchRunSuccess { run { runId } }
  ... on PythonError { message }
  ... on RunConfigValidationInvalid { errors { message } }
} }"""
params = {"selector": {"repositoryLocationName": loc,
                       "repositoryName": repo,
                       "jobName": job},
          "runConfigData": run_config}
print(json.dumps({"query": query, "variables": {"p": params}}))
PY
)
launch_resp=$(gql "${launch_payload}")
run_id=$(printf '%s' "${launch_resp}" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)["data"]["launchRun"]
    print(d.get("run", {}).get("runId", "")) if d.get("__typename") == "LaunchRunSuccess" else print("")
except Exception:
    print("")')
[ -n "${run_id}" ] || { log "✗ launchRun a échoué : $(printf '%s' "${launch_resp}" | head -c 400)"; exit 1; }
log "  ✓ run lancé : ${run_id}"

log "[4/5] attente de la complétion du run (max ${CODELOC_TIMEOUT}s)"
deadline=$(( $(date +%s) + CODELOC_TIMEOUT ))
status=""
while [ "$(date +%s)" -lt "${deadline}" ]; do
    status_resp=$(gql "{\"query\":\"{ runOrError(runId: \\\"${run_id}\\\") { ... on Run { status } } }\"}")
    status=$(printf '%s' "${status_resp}" | grep -oE '"status":"[A-Z]+"' | cut -d'"' -f4 || true)
    case "${status}" in
        SUCCESS) break ;;
        FAILURE | CANCELED) log "✗ run ${run_id} terminé en ${status}"; exit 1 ;;
        *) sleep 10 ;;
    esac
done
[ "${status}" = SUCCESS ] || { log "✗ run ${run_id} pas SUCCESS après ${CODELOC_TIMEOUT}s (status=${status:-inconnu})"; exit 1; }
log "  ✓ run SUCCESS"

log "[5/5] vérification de l'aval"
# 5a. Lineage Marquez (présence, fonction pure — même critère que le scénario 27).
sleep 5
job_after=$(marquez_job_count)
verdict=$(classify_marquez_ingest "${job_before}" "${job_after}")
case "${verdict%%|*}" in
    ok) log "  ✓ ${verdict#*|}" ;;
    *) log "✗ ${verdict#*|}" ; exit 1 ;;
esac
# 5b. (Option) un objet est apparu dans le bucket S3 aval.
if [ -n "${VERIFY_S3_ENDPOINT}" ] && [ -n "${VERIFY_S3_BUCKET}" ]; then
    n_obj=$(kubectl -n "${CODELOC_NS}" run "s3check-29-$$" --rm -i --restart=Never \
        --image=curlimages/curl:8.11.1 --quiet -- \
        sh -c "curl -sS '${VERIFY_S3_ENDPOINT}/${VERIFY_S3_BUCKET}?list-type=2&max-keys=1' --max-time 30 | grep -c '<Key>'" 2>/dev/null || echo 0)
    [ "${n_obj:-0}" -ge 1 ] \
        || { log "✗ aucun objet dans ${VERIFY_S3_BUCKET} (${VERIFY_S3_ENDPOINT})"; exit 1; }
    log "  ✓ objet présent dans le bucket aval ${VERIFY_S3_BUCKET}"
fi

log "🎉 code-location externe « ${CODELOC_NAME} » validée e2e : branchée → run ${CODELOC_JOB} SUCCESS → lineage ingéré."
