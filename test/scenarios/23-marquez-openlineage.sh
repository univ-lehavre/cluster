#!/usr/bin/env bash
#
# Scénario 23 — INTÉGRATION : Dagster émet-il du lineage que Marquez ingère ?
#
# Cœur de l'étape 1.8 (ADR 0028) et de l'épopée #148 (validation E2E de la chaîne
# DataOps assemblée). Vérifie le maillon final : un run Dagster a émis des
# événements OpenLineage que Marquez a INGÉRÉS et expose via son API.
#
# Ce scénario est INDÉPENDANT du déploiement : il assume que la chaîne est déjà
# montée (par `test/lima/run-phases.sh dataops-chain`, qui déploie monitoring →
# CNPG → Dagster → Marquez + un émetteur jetable, lance un run réel et le retire).
# Ici on RE-VÉRIFIE, façon run-all.sh (PASS/FAIL, exit code), que l'ingestion est
# bien visible côté Marquez.
#
# SKIP NEUTRE (exit 0) si Marquez ou Dagster ne sont pas déployés — sauf
# STRICT_OL=1 qui fait alors ÉCHOUER (utile en CI une fois la chaîne posée ;
# calque le STRICT_ALERT du scénario 22, maillon dépendant d'un pré-requis).
#
# Pré-requis : kubectl (Marquez + Dagster déployés via dataops-chain).
# Variables :
#   STRICT_OL=1     échoue (au lieu de skip) si la chaîne n'est pas montée
#   MARQUEZ_SVC     (défaut marquez.marquez.svc.cluster.local) — API HTTP :5000
#   OL_NAMESPACE    (défaut dagster) — namespace OpenLineage interrogé côté Marquez
set -euo pipefail

STRICT_OL=${STRICT_OL:-0}
MARQUEZ_SVC=${MARQUEZ_SVC:-marquez.marquez.svc.cluster.local}
OL_NAMESPACE=${OL_NAMESPACE:-dagster}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

# Lib pure d'assertion (verdicts STATUS|message) — partagée avec dataops-chain.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=test/lima/dataops-assert.sh
. "${HERE}/../lima/dataops-assert.sh"

# ── Pré-requis : la chaîne est-elle montée ? ──
chain_present=1
kubectl -n marquez get deploy/marquez >/dev/null 2>&1 || chain_present=0
kubectl -n dagster get deploy/dagster-daemon >/dev/null 2>&1 || chain_present=0

if [ "$chain_present" != "1" ]; then
    if [ "$STRICT_OL" = "1" ]; then
        log "✗ STRICT_OL=1 et chaîne DataOps non montée (Marquez et/ou Dagster absents)."
        log "  Attendu après 'test/lima/run-phases.sh dataops-chain'."
        exit 1
    fi
    log "skip — chaîne DataOps non montée (Marquez et/ou Dagster absents)."
    log "  Monter la chaîne d'abord : test/lima/run-phases.sh dataops-chain"
    log "  (puis STRICT_OL=1 en CI sur un banc où la chaîne tourne)."
    exit 0
fi
log "✓ Marquez + Dagster déployés — vérification de l'ingestion du lineage"

# ── Interroge l'API Marquez DEPUIS le cluster (Service ClusterIP :5000) ──
# Renvoie le corps JSON de la liste des jobs du namespace OpenLineage.
marquez_jobs_json() {
    kubectl -n marquez run marquez-probe-$$ --rm -i --restart=Never \
        --image=busybox:1.36 --quiet -- \
        sh -c "wget -qO- 'http://${MARQUEZ_SVC}:5000/api/v1/namespaces/${OL_NAMESPACE}/jobs' 2>/dev/null" 2>/dev/null
}

log "[OL] interrogation de Marquez (namespace '${OL_NAMESPACE}')…"
jobs_json=$(marquez_jobs_json || true)
job_count=$(parse_ol_job_count "${jobs_json}")
log "  jobs visibles dans Marquez : ${job_count}"

# Verdict : au moins un job de lineage ingéré (delta depuis 0 = ingestion prouvée).
verdict=$(classify_marquez_ingest 0 "${job_count}")
status=${verdict%%|*}
message=${verdict#*|}

case "$status" in
    ok)
        log "✓ ${message}"
        log "  La chaîne Dagster → OpenLineage → Marquez est COMPLÈTE (lineage ingéré)."
        exit 0
        ;;
    skip)
        if [ "$STRICT_OL" = "1" ]; then
            log "✗ STRICT_OL=1 et ${message}"
            exit 1
        fi
        log "skip — ${message}"
        exit 0
        ;;
    *)
        log "✗ ${message}"
        log "  Marquez est joignable mais aucun job de lineage n'a été ingéré. Vérifier"
        log "  que le sensor OpenLineage du run Dagster a bien POST sur l'API Marquez"
        log "  (OPENLINEAGE_URL=http://${MARQUEZ_SVC}:5000, namespace '${OL_NAMESPACE}')."
        exit 1
        ;;
esac
