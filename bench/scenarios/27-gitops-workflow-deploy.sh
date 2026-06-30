#!/usr/bin/env bash
#
# Scénario 27 — INTÉGRATION : un push sur Gitea déploie-t-il la code-location atlas
# par Argo CD ?
#
# Cœur du banc atlas (ADR 0044/0045/0086) : prouve que le contenu poussé dans la forge
# Gitea intra-banc est réconcilié par Argo CD (via webhook) jusqu'au déploiement d'une
# VRAIE code-location Dagster gRPC (Deployment toy-codeloc + Service + patch workspace),
# branchée dans l'orchestrateur. Argo CD déploie la CODE-LOCATION, pas l'infra DataOps
# (montée par Ansible, ADR 0022/0045). Le RUN e2e (launchRun → lineage Marquez) relève
# du scénario 29 ; ici l'intention est « GitOps déploie une code-location fonctionnelle ».
#
# Pré-requis : socle GitOps (Gitea + Argo CD) + infra DataOps + init du dépôt
# (phase `gitops-seed`, portée par nestor/seed.py) — c.-à-d. un banc monté avec la
# chaîne gitops. SKIP NEUTRE (exit 0) si l'un manque, sauf STRICT_GITOPS=1 qui fait
# alors ÉCHOUER (calque STRICT_MON/STRICT_OL).
#
# Variables :
#   STRICT_GITOPS=1   échoue (au lieu de skip) si la chaîne GitOps n'est pas prête
#   GITEA_NS / ARGOCD_NS / GITEA_ORG / GITEA_REPO   (mêmes défauts que le seed gitops)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

STRICT_GITOPS=${STRICT_GITOPS:-0}
GITEA_NS=${GITEA_NS:-gitea}
ARGOCD_NS=${ARGOCD_NS:-argocd}
GITEA_ORG=${GITEA_ORG:-atlas}
GITEA_REPO=${GITEA_REPO:-workflows}
APP=${APP:-atlas-workflows}

# shellcheck source=bench/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Assertions PURES (testées en bats) : classify_argocd_app, classify_webhook_trigger
# (gitops-assert). Le lineage Marquez (parse_ol_job_count) relève désormais du
# scénario 29 (run e2e), plus du 27 (qui prouve le DÉPLOIEMENT de la code-location).
# shellcheck source=bench/lima/gitops-assert.sh
. ../lima/gitops-assert.sh

skip_or_fail() {
    if [ "${STRICT_GITOPS}" = 1 ]; then
        log "✗ STRICT_GITOPS=1 et chaîne GitOps non prête : $1"
        exit 1
    fi
    log "skip — $1"
    log "  Monter d'abord le banc avec la chaîne gitops (nestor up — la phase gitops-seed"
    log "  initialise Gitea, portée par nestor/seed.py)."
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

# ── 2. Push un changement dans Gitea (nouveau fichier → nouveau commit) ──────
# On CRÉE un fichier de déclenchement unique (POST Contents = toujours un commit
# neuf, donc une nouvelle révision) — plus fiable qu'un update du workflow (qui
# exige le sha courant) et suffisant pour prouver que le PUSH déclenche le
# webhook. Le contenu déployé (le workflow) est posé par l'init en amont.
log "[2/4] push d'un commit de déclenchement sur ${GITEA_ORG}/${GITEA_REPO}"
gitea_pod=$(kubectl -n "${GITEA_NS}" get pod -l app=gitea -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -n "${gitea_pod}" ] || skip_or_fail "pod gitea introuvable"
# Token API éphémère (admin créé par l'init). --raw : valeur seule.
gitea_token=$(kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- \
    gitea admin user generate-access-token -u atlas-admin -t "sc27-${RANDOM}" --scopes all --raw 2>/dev/null | tr -d '[:space:]')
[ -n "${gitea_token}" ] || skip_or_fail "token Gitea non obtenu (init faite ?)"
# Fichier unique → create garanti (pas de sha à fournir) → commit + webhook.
trigger_path="triggers/sc27-${RANDOM}${RANDOM}.txt"
trigger_b64=$(printf 'scenario 27 trigger\n' | base64 | tr -d '\n')
push_resp=$(kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- curl -sS \
    -X POST -H "Authorization: token ${gitea_token}" -H "Content-Type: application/json" \
    "http://localhost:3000/api/v1/repos/${GITEA_ORG}/${GITEA_REPO}/contents/${trigger_path}" \
    -d "{\"content\":\"${trigger_b64}\",\"message\":\"scenario 27 trigger\"}" 2>/dev/null)
printf '%s' "${push_resp}" | grep -q '"commit"' \
    || { log "✗ push du commit de déclenchement échoué — réponse: ${push_resp}"; exit 1; }

# ── 3. Argo CD réconcilie via webhook → NOUVELLE révision + Synced/Healthy ───
# Condition de sortie = la révision a CHANGÉ (rev_after != rev_before) ET
# Synced/Healthy. Attendre seulement Synced/Healthy sortirait à la 1ʳᵉ
# itération (l'app était déjà Synced sur l'ancienne révision) sans prouver que
# le push a déclenché quoi que ce soit.
log "[3/4] attente réconciliation Argo CD (nouvelle révision via webhook, max 3 min)"
sync='' health='' rev_after="${rev_before}"
for _ in $(seq 1 36); do
    sync=$(kubectl -n "${ARGOCD_NS}" get application "${APP}" -o jsonpath='{.status.sync.status}' 2>/dev/null || true)
    health=$(kubectl -n "${ARGOCD_NS}" get application "${APP}" -o jsonpath='{.status.health.status}' 2>/dev/null || true)
    rev_after=$(kubectl -n "${ARGOCD_NS}" get application "${APP}" -o jsonpath='{.status.sync.revision}' 2>/dev/null || true)
    [ "${rev_after}" != "${rev_before}" ] && [ "${sync}" = "Synced" ] && [ "${health}" = "Healthy" ] && break
    sleep 5
done
verdict=$(classify_argocd_app "${sync}" "${health}")
[ "${verdict%%|*}" = ok ] || { log "✗ ${verdict#*|}"; exit 1; }
log "✓ ${verdict#*|}"
verdict=$(classify_webhook_trigger "${rev_before}" "${rev_after}")
[ "${verdict%%|*}" = ok ] || { log "✗ ${verdict#*|}"; exit 1; }
log "✓ ${verdict#*|}"

# ── 4. La code-location jouet déployée par GitOps est branchée (ADR 0086) ────
# Argo CD a réconcilié la VRAIE code-location gRPC (Deployment toy-codeloc + Service
# + patch workspace), pas un Job jetable. On prouve que le déploiement GitOps aboutit :
# le serveur gRPC est Ready et le workspace Dagster le charge (location « toy »).
# Le LANCEMENT d'un run + le lineage Marquez relèvent du scénario 29 (run e2e via
# launchRun) — ici, l'intention est « GitOps déploie une code-location fonctionnelle ».
log "[4/4] la code-location jouet (toy-codeloc) est déployée + branchée par GitOps"
codeloc_ready() {
    [ "$(kubectl -n dagster get deploy toy-codeloc -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]
}
for _ in $(seq 1 30); do codeloc_ready && break; sleep 10; done
codeloc_ready || {
    log "✗ le Deployment toy-codeloc (code-location gRPC) n'est pas Ready"
    kubectl -n dagster get deploy toy-codeloc -o wide 2>/dev/null || true
    kubectl -n dagster logs deploy/toy-codeloc --tail=15 2>/dev/null || true
    exit 1
}
log "✓ toy-codeloc Ready — code-location gRPC servie"

# Le workspace Dagster charge-t-il bien la location « toy » ? (patch ConfigMap réconcilié)
if kubectl -n dagster get configmap dagster-workspace -o jsonpath='{.data.workspace\.yaml}' 2>/dev/null \
    | grep -q 'location_name: toy'; then
    log "✓ workspace Dagster branché sur la code-location « toy »"
else
    log "✗ le workspace Dagster ne charge pas la location « toy » (patch non réconcilié ?)"
    exit 1
fi

log "🎉 GitOps → code-location prouvé : push Gitea → webhook → Argo CD Synced → code-location gRPC déployée + branchée."
log "ℹ️  Run e2e (launchRun → lineage Marquez) : scénario 29 (CODELOC_NAME=toy CODELOC_JOB=toy_job)."
