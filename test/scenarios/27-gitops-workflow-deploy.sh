#!/usr/bin/env bash
#
# Scénario 27 — INTÉGRATION : un push sur Gitea déploie-t-il les workflows atlas
# par Argo CD, qui lancent la chaîne DataOps ?
#
# Cœur du banc atlas (ADR 0044/0045) : prouve que le contenu poussé dans la forge
# Gitea intra-banc est réconcilié par Argo CD (via webhook) jusqu'au run Dagster
# réel + lineage Marquez. Argo CD déploie les WORKFLOWS, pas l'infra DataOps
# (montée par Ansible, ADR 0022/0045).
#
# Pré-requis : socle GitOps (Gitea + Argo CD) + infra DataOps + init du dépôt
# (test/lima/gitea-init.sh) — c.-à-d. un banc monté par `run-phases.sh atlas`
# PUIS la phase d'init Gitea. SKIP NEUTRE (exit 0) si l'un manque, sauf
# STRICT_GITOPS=1 qui fait alors ÉCHOUER (calque STRICT_MON/STRICT_OL).
#
# Variables :
#   STRICT_GITOPS=1   échoue (au lieu de skip) si la chaîne GitOps n'est pas prête
#   GITEA_NS / ARGOCD_NS / GITEA_ORG / GITEA_REPO   (mêmes défauts que gitea-init.sh)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

STRICT_GITOPS=${STRICT_GITOPS:-0}
GITEA_NS=${GITEA_NS:-gitea}
ARGOCD_NS=${ARGOCD_NS:-argocd}
GITEA_ORG=${GITEA_ORG:-atlas}
GITEA_REPO=${GITEA_REPO:-workflows}
APP=${APP:-atlas-workflows}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

# Assertions PURES (testées en bats) : classify_argocd_app, classify_webhook_trigger
# (gitops-assert) ; parse_ol_job_count, classify_marquez_ingest (dataops-assert).
# shellcheck source=test/lima/gitops-assert.sh
. ../lima/gitops-assert.sh
# shellcheck source=test/lima/dataops-assert.sh
. ../lima/dataops-assert.sh

# Probe Marquez autonome (calque scénario 23) — compte les jobs d'un namespace
# OpenLineage via un pod busybox jetable. Renvoie un entier sur stdout.
marquez_job_count() {
    local ol_ns=$1 json
    json=$(kubectl -n marquez run marquez-count-$$ --rm -i --restart=Never \
        --image=busybox:1.36 --quiet -- \
        sh -c "wget -qO- 'http://marquez.marquez.svc.cluster.local:5000/api/v1/namespaces/${ol_ns}/jobs' 2>/dev/null" 2>/dev/null)
    parse_ol_job_count "${json}"
}

skip_or_fail() {
    if [ "${STRICT_GITOPS}" = 1 ]; then
        log "✗ STRICT_GITOPS=1 et chaîne GitOps non prête : $1"
        exit 1
    fi
    log "skip — $1"
    log "  Monter d'abord : run-phases.sh atlas puis test/lima/gitea-init.sh"
    exit 0
}

# ── Pré-requis ──────────────────────────────────────────────────────────────
kubectl -n "${GITEA_NS}" get deploy gitea >/dev/null 2>&1 || skip_or_fail "Gitea absent"
kubectl -n "${ARGOCD_NS}" get deploy argocd-server >/dev/null 2>&1 || skip_or_fail "Argo CD absent"
kubectl -n "${ARGOCD_NS}" get application "${APP}" >/dev/null 2>&1 \
    || skip_or_fail "Application ${APP} absente (init du dépôt Gitea non faite)"
log "✓ Gitea + Argo CD + Application ${APP} présents"

# ── 1. Révision synchronisée AVANT (pour prouver le déclenchement par push) ──
rev_before=$(kubectl -n "${ARGOCD_NS}" get application "${APP}" \
    -o jsonpath='{.status.sync.revision}' 2>/dev/null || true)
log "[1/4] révision synchronisée avant push : ${rev_before:-∅}"

# ── 2. Push un changement dans Gitea (touche un fichier → nouveau commit) ────
# Via l'API Contents (update du workflow avec un commit horodaté) — réutilise
# l'admin/token créés par gitea-init.sh (Secret gitea-admin).
log "[2/4] push d'un commit sur ${GITEA_ORG}/${GITEA_REPO} (déclenche le webhook)"
"$(dirname "${BASH_SOURCE[0]}")/../lima/gitea-init.sh" >/dev/null 2>&1 \
    || skip_or_fail "réexécution de l'init (push) a échoué"

# ── 3. Argo CD réconcilie via webhook → Synced/Healthy sur une nouvelle rev ──
log "[3/4] attente réconciliation Argo CD (Synced/Healthy via webhook, max 3 min)"
sync='' health='' rev_after=''
for _ in $(seq 1 36); do
    sync=$(kubectl -n "${ARGOCD_NS}" get application "${APP}" -o jsonpath='{.status.sync.status}' 2>/dev/null || true)
    health=$(kubectl -n "${ARGOCD_NS}" get application "${APP}" -o jsonpath='{.status.health.status}' 2>/dev/null || true)
    rev_after=$(kubectl -n "${ARGOCD_NS}" get application "${APP}" -o jsonpath='{.status.sync.revision}' 2>/dev/null || true)
    [ "${sync}" = "Synced" ] && [ "${health}" = "Healthy" ] && break
    sleep 5
done
verdict=$(classify_argocd_app "${sync}" "${health}")
[ "${verdict%%|*}" = ok ] || { log "✗ ${verdict#*|}"; exit 1; }
log "✓ ${verdict#*|}"
verdict=$(classify_webhook_trigger "${rev_before}" "${rev_after}")
[ "${verdict%%|*}" = ok ] || { log "✗ ${verdict#*|}"; exit 1; }
log "✓ ${verdict#*|}"

# ── 4. Le workflow déployé tourne : run Dagster réussi + lineage Marquez ─────
log "[4/4] le workflow (Job) s'exécute → lineage ingéré par Marquez"
job_before=$(marquez_job_count dagster)
# Argo a déployé le Job atlas-workflow-sample ; on attend sa complétion.
done_ok() { [ "$(kubectl -n dagster get job atlas-workflow-sample -o jsonpath='{.status.succeeded}' 2>/dev/null)" = "1" ]; }
for _ in $(seq 1 30); do done_ok && break; sleep 10; done
done_ok || { log "✗ le Job atlas-workflow-sample n'a pas réussi"; kubectl -n dagster logs job/atlas-workflow-sample 2>/dev/null | tail -15; exit 1; }
sleep 5
job_after=$(marquez_job_count dagster)
verdict=$(classify_marquez_ingest "${job_before}" "${job_after}")
[ "${verdict%%|*}" = ok ] || { log "✗ ${verdict#*|}"; exit 1; }
log "✓ ${verdict#*|}"

log "🎉 GitOps → workflows atlas prouvé : push Gitea → webhook → Argo CD Synced → run Dagster → lineage Marquez."
