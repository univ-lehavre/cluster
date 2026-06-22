#!/usr/bin/env bash
#
# Init du dépôt Gitea POST-BOOTSTRAP (#231, ADR 0044/0045) — étape de DONNÉES,
# pas d'infra (Gitea lui-même est posé par bootstrap/gitops.yaml). Idempotent.
#
# Fait, dans l'ordre :
#   1. crée un admin Gitea (CLI `gitea admin user create` dans le pod) ;
#   2. obtient un token API ;
#   3. crée l'organisation + le dépôt des workflows atlas ;
#   4. pousse le workflow jouet (atlas-workflow-sample/) dans ce dépôt ;
#   5. pose le secret partagé `webhook.gitea.secret` dans argocd-secret ;
#   6. enregistre le webhook Gitea → argocd-server/api/webhook.
#
# Orchestration de CLIs/API → bash (ADR 0017). Toutes les valeurs sont des
# EXEMPLES GÉNÉRIQUES (ADR 0023) ; un déploiement réel surcharge via l'env.
# La logique de DÉCISION (classer un statut) vit dans gitops-assert.sh (testée
# en bats) — ici, uniquement de l'orchestration.
#
# Sourcé par run-phases.sh (phase gitops-seed) ; KUBECTL hérité de l'appelant.
set -euo pipefail

# ── Paramètres (exemples génériques surchargeables, ADR 0023) ────────────────
GITEA_NS=${GITEA_NS:-gitea}
GITEA_ADMIN_USER=${GITEA_ADMIN_USER:-atlas-admin}
GITEA_ADMIN_EMAIL=${GITEA_ADMIN_EMAIL:-atlas-admin@example-org.lan}
GITEA_ORG=${GITEA_ORG:-atlas}
GITEA_REPO=${GITEA_REPO:-workflows}
ARGOCD_NS=${ARGOCD_NS:-argocd}
# Service HTTP interne de Gitea (cf. platform/gitea/service.yaml). Sert au repoURL de
# l'Application Argo CD (lu par le pod argocd-repo-server → nom RÉSOLVABLE depuis argocd).
GITEA_SVC=${GITEA_SVC:-http://gitea-http.gitea.svc.cluster.local}
# Endpoint API : l'`api()` ci-dessous tourne via `kubectl exec` DANS le pod gitea, donc
# on tape Gitea en LOCAL (gitea écoute sur :3000). Évite toute résolution DNS — robuste
# en prod où un search domain externe (resolv.conf, ndots:5) faisait timeouter le FQDN
# `*.svc.cluster.local` côté glibc/curl (« Could not resolve host »), alors que CoreDNS
# répondait (drift constaté sur dirqual, 2026-06-22). Sur le banc comme en prod, le pod
# gitea s'atteint lui-même sur localhost:3000.
GITEA_API=${GITEA_API:-http://localhost:3000}

# KUBECTL : tableau hérité de run-phases.sh ; fallback autonome.
if ! declare -p KUBECTL >/dev/null 2>&1; then
    KUBECTL=(kubectl)
fi

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SAMPLE_DIR="${HERE}/atlas-workflow-sample"

# Le pod gitea (un seul réplica, Recreate).
gitea_pod() {
    "${KUBECTL[@]}" -n "${GITEA_NS}" get pod -l app=gitea \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

# Exécute une commande `gitea` (CLI) dans le pod, en tant qu'utilisateur git.
gitea_cli() {
    local pod
    pod=$(gitea_pod)
    [ -n "${pod}" ] || { echo "gitea-init: pod gitea introuvable" >&2; return 1; }
    "${KUBECTL[@]}" -n "${GITEA_NS}" exec "${pod}" -- "$@"
}

# Génère un secret aléatoire reproductible-par-run (jamais versionné, ADR 0023).
# /dev/urandom : valeur de déploiement, vit uniquement dans le cluster.
gen_secret() { head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32; }

main() {
    echo "[gitea-init] 1/6 — admin Gitea (${GITEA_ADMIN_USER}, idempotent)"
    # Mot de passe admin : généré et stocké dans un Secret K8s (pas en clair ici).
    if ! "${KUBECTL[@]}" -n "${GITEA_NS}" get secret gitea-admin >/dev/null 2>&1; then
        local pw
        pw=$(gen_secret)
        "${KUBECTL[@]}" -n "${GITEA_NS}" create secret generic gitea-admin \
            --from-literal=username="${GITEA_ADMIN_USER}" \
            --from-literal=password="${pw}"
    fi
    local admin_pw
    admin_pw=$("${KUBECTL[@]}" -n "${GITEA_NS}" get secret gitea-admin \
        -o jsonpath='{.data.password}' | base64 -d)
    # `gitea admin user create` échoue si l'utilisateur existe → idempotent via `|| true`
    # mais on log le cas pour ne pas masquer une autre erreur.
    gitea_cli gitea admin user create \
        --username "${GITEA_ADMIN_USER}" --password "${admin_pw}" \
        --email "${GITEA_ADMIN_EMAIL}" --admin --must-change-password=false \
        2>&1 | grep -v "user already exists" || true

    echo "[gitea-init] 2/6 — token API"
    # `--raw` affiche UNIQUEMENT la valeur du token (pas de préfixe à parser) ;
    # `--scopes all` (scope valide de Gitea 1.26). Nom de token unique par run
    # (un nom déjà pris ferait échouer la commande) → suffixe horodaté.
    local token token_name="atlas-init-${RANDOM}"
    token=$(gitea_cli gitea admin user generate-access-token \
        --username "${GITEA_ADMIN_USER}" --token-name "${token_name}" \
        --scopes all --raw 2>/dev/null | tr -d '[:space:]') || true
    [ -n "${token}" ] || { echo "gitea-init: token API non obtenu" >&2; return 1; }

    # Helper API : appel REST depuis le pod (réseau intra-cluster).
    api() {
        local method=$1 path=$2 body=${3:-}
        local args=(-sS -X "${method}" -H "Authorization: token ${token}"
            -H "Content-Type: application/json" "${GITEA_API}/api/v1${path}")
        [ -n "${body}" ] && args+=(-d "${body}")
        gitea_cli curl "${args[@]}"
    }

    # push_gitea_file <nom> — pousse SAMPLE_DIR/<nom> à la racine du dépôt Gitea via
    # la Contents API (create-or-update idempotent). Lit le SHA existant pour une MAJ ;
    # vérifie la réponse (un PUT/POST raté laissait l'ancienne version → Argo CD
    # déployait un manifeste périmé, drift à ne pas reproduire). rc≠0 si pas de commit.
    push_gitea_file() {
        local path=$1 content sha payload resp
        content=$(base64 < "${SAMPLE_DIR}/${path}" | tr -d '\n')
        sha=$(api GET "/repos/${GITEA_ORG}/${GITEA_REPO}/contents/${path}" 2>/dev/null \
            | grep -oE '"sha":"[a-f0-9]+"' | head -1 | cut -d'"' -f4) || true
        if [ -n "${sha}" ]; then
            payload="{\"content\":\"${content}\",\"sha\":\"${sha}\",\"message\":\"update ${path} (atlas-init)\"}"
            resp=$(api PUT "/repos/${GITEA_ORG}/${GITEA_REPO}/contents/${path}" "${payload}")
        else
            payload="{\"content\":\"${content}\",\"message\":\"add ${path} (atlas-init)\"}"
            resp=$(api POST "/repos/${GITEA_ORG}/${GITEA_REPO}/contents/${path}" "${payload}")
        fi
        if ! printf '%s' "${resp}" | grep -q '"commit"'; then
            echo "gitea-init: push de ${path} ÉCHOUÉ — réponse: ${resp}" >&2
            return 1
        fi
    }

    echo "[gitea-init] 3/6 — organisation ${GITEA_ORG} + dépôt ${GITEA_REPO}"
    api POST "/orgs" "{\"username\":\"${GITEA_ORG}\"}" >/dev/null 2>&1 || true
    api POST "/orgs/${GITEA_ORG}/repos" \
        "{\"name\":\"${GITEA_REPO}\",\"auto_init\":true,\"default_branch\":\"main\"}" \
        >/dev/null 2>&1 || true

    echo "[gitea-init] 4/6 — push de la code-location jouet (Contents API, idempotent)"
    # Pousse les manifestes de la code-location jouet (ADR 0086) via l'API Contents
    # (create-or-update). On lit le SHA existant pour une mise à jour idempotente. La
    # réponse est CAPTURÉE et vérifiée (un PUT/POST raté laissait silencieusement
    # l'ANCIENNE version dans Gitea → Argo CD déployait un manifeste périmé : drift à
    # ne pas reproduire). Argo CD réconcilie la VRAIE code-location gRPC (Deployment +
    # Service + patch workspace), pas un Job jetable.
    local f
    for f in code-location.yaml workspace-patch.yaml reload-hook.yaml; do
        push_gitea_file "${f}" || return 1
    done

    echo "[gitea-init] 5/6 — secret partagé webhook.gitea.secret (argocd-secret)"
    local wh_secret
    if "${KUBECTL[@]}" -n "${ARGOCD_NS}" get secret argocd-webhook-shared >/dev/null 2>&1; then
        wh_secret=$("${KUBECTL[@]}" -n "${ARGOCD_NS}" get secret argocd-webhook-shared \
            -o jsonpath='{.data.secret}' | base64 -d)
    else
        wh_secret=$(gen_secret)
        "${KUBECTL[@]}" -n "${ARGOCD_NS}" create secret generic argocd-webhook-shared \
            --from-literal=secret="${wh_secret}"
    fi
    # Patch argocd-secret avec la clé que le serveur Argo CD lit pour valider le
    # webhook Gitea (X-Gitea-Signature).
    "${KUBECTL[@]}" -n "${ARGOCD_NS}" patch secret argocd-secret --type merge \
        -p "{\"stringData\":{\"webhook.gitea.secret\":\"${wh_secret}\"}}"

    echo "[gitea-init] 6/6 — webhook Gitea → argocd-server/api/webhook"
    # Idempotent : on ne crée le webhook que s'il n'existe pas déjà (par URL).
    local hooks_url="http://argocd-server.${ARGOCD_NS}.svc.cluster.local/api/webhook"
    local existing
    existing=$(api GET "/repos/${GITEA_ORG}/${GITEA_REPO}/hooks" 2>/dev/null \
        | grep -c "${hooks_url}") || true
    if [ "${existing:-0}" = 0 ]; then
        api POST "/repos/${GITEA_ORG}/${GITEA_REPO}/hooks" \
            "{\"type\":\"gitea\",\"active\":true,\"events\":[\"push\"],\"config\":{\"url\":\"${hooks_url}\",\"content_type\":\"json\",\"secret\":\"${wh_secret}\"}}" \
            >/dev/null
    fi

    echo "[gitea-init] 7/7 — Application Argo CD atlas-workflows (repoURL Gitea réel)"
    # Pose l'Application qui réconcilie le dépôt Gitea du banc. Le repoURL est la
    # valeur de DÉPLOIEMENT (URL intra-banc) injectée ici, jamais versionnée
    # (ADR 0023) ; le template versionné est application.example.yaml.
    local repo_url="${GITEA_SVC}/${GITEA_ORG}/${GITEA_REPO}.git"
    "${KUBECTL[@]}" apply -f - <<APP >/dev/null
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: atlas-workflows
  namespace: ${ARGOCD_NS}
spec:
  project: atlas
  source:
    repoURL: ${repo_url}
    targetRevision: main
    path: .
  destination:
    server: https://kubernetes.default.svc
    namespace: dagster
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
APP

    echo "[gitea-init] OK — dépôt ${GITEA_ORG}/${GITEA_REPO} prêt, webhook + Application posés."
    echo "  repoURL intra-banc : ${repo_url}"
}

# Exécutable seul ou sourçable (pour les tests).
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
