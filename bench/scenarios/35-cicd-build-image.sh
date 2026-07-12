#!/usr/bin/env bash
#
# Scénario 35 — INTÉGRATION : un push sur Gitea build-il une image via la CI in-cluster ?
#
# Preuve du socle CI/CD léger (ADR 0112, topo `cicd` = layers [gitops, build]) : on pousse
# un Dockerfile JOUET (FROM image interne, air-gap) + un workflow Gitea Actions dans un repo
# Gitea ; le runner (act_runner, mode host) le prend, soumet à buildkitd in-pod (buildctl),
# et l'image produite est poussée au registre interne. On vérifie qu'elle y apparaît.
#
# C'est la preuve de la topo `cicd` SEULE (pas de dataops, pas de code-location, pas de
# déploiement Argo CD — ça, c'est le scénario 27 sur une topo dataops). Ici : push → image.
#
# Pré-requis : gitea + argocd + registry + buildkit + gitea-runner (montés par `cicd`).
# SKIP NEUTRE (exit 0) si un maillon manque, sauf STRICT_CICD=1 qui fait alors ÉCHOUER.
#
# Variables :
#   STRICT_CICD=1   échoue (au lieu de skip) si la chaîne CI/CD n'est pas prête
#   GITEA_NS / REGISTRY_NS / BUILDKIT_NS / RUNNER_NS   (défauts standard)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

STRICT_CICD=${STRICT_CICD:-0}
GITEA_NS=${GITEA_NS:-gitea}
REGISTRY_NS=${REGISTRY_NS:-registry}
BUILDKIT_NS=${BUILDKIT_NS:-buildkit}
RUNNER_NS=${RUNNER_NS:-gitea-runner}
ARGOCD_NS=${ARGOCD_NS:-argocd}
DEPLOY_NS=${DEPLOY_NS:-cicd-smoke-app}   # ns cible du déploiement jouet (créé par l'Application)
GITEA_ADMIN=${GITEA_ADMIN:-atlas-admin}
REPO=${REPO:-cicd-smoke}
FROM_IMG=${FROM_IMG:-registry.registry.svc.cluster.local:80/moby/buildkit:v0.19.0-rootless}
BUILDKITD=${BUILDKITD:-tcp://buildkitd.buildkit.svc.cluster.local:1234}
REGISTRY_FQDN=registry.registry.svc.cluster.local:80

# shellcheck source=bench/scenarios/lib.sh
. ./lib.sh

skip_or_fail() {
    if [ "${STRICT_CICD}" = 1 ]; then
        log "✗ STRICT_CICD=1 et chaîne CI/CD non prête : $1"
        exit 1
    fi
    log "skip — $1"
    log "  Monter d'abord le socle CI/CD (nestor install, topo cicd : layers [gitops, build])."
    exit 0
}

# ── Pré-requis : les 5 maillons du socle CI/CD ──────────────────────────────
kubectl -n "${GITEA_NS}" get deploy gitea >/dev/null 2>&1 || skip_or_fail "Gitea absent"
kubectl -n "${ARGOCD_NS}" get deploy argocd-server >/dev/null 2>&1 || skip_or_fail "Argo CD absent"
kubectl -n "${REGISTRY_NS}" get deploy registry >/dev/null 2>&1 || skip_or_fail "registry absent"
kubectl -n "${BUILDKIT_NS}" get deploy buildkitd >/dev/null 2>&1 || skip_or_fail "buildkitd absent"
kubectl -n "${RUNNER_NS}" get deploy gitea-runner >/dev/null 2>&1 || skip_or_fail "gitea-runner absent"
runner_ready=$(kubectl -n "${RUNNER_NS}" get deploy gitea-runner -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
[ "${runner_ready}" = "1" ] || skip_or_fail "gitea-runner pas Ready"
log "✓ gitea + argocd + registry + buildkitd + gitea-runner présents et Ready"

gitea_pod=$(kubectl -n "${GITEA_NS}" get pod -l app=gitea -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -n "${gitea_pod}" ] || skip_or_fail "pod gitea introuvable"

# Admin Gitea (idempotent) : le scénario a besoin d'un compte admin pour créer le repo et
# pousser. On le crée s'il manque (le socle cicd n'a pas de seed qui l'aurait posé).
if ! kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- gitea admin user list 2>/dev/null \
    | awk '{print $2}' | grep -qx "${GITEA_ADMIN}"; then
    kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- gitea admin user create \
        --username "${GITEA_ADMIN}" --password "sc35-${RANDOM}${RANDOM}" \
        --email "${GITEA_ADMIN}@example.lan" --admin --must-change-password=false >/dev/null 2>&1 \
        || skip_or_fail "création de l'admin ${GITEA_ADMIN} échouée"
    log "✓ admin Gitea ${GITEA_ADMIN} créé"
fi

# API Gitea INTERNE : on exécute curl DANS le pod gitea (pas de port-forward hôte).
gitea_token=$(kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- \
    gitea admin user generate-access-token -u "${GITEA_ADMIN}" -t "sc35-${RANDOM}" --scopes all --raw 2>/dev/null | tr -d '[:space:]')
[ -n "${gitea_token}" ] || skip_or_fail "token Gitea non obtenu (admin ${GITEA_ADMIN} présent ?)"
gapi() { # gapi <METHOD> <path> [data]
    kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- curl -sS \
        -X "$1" -H "Authorization: token ${gitea_token}" -H "Content-Type: application/json" \
        "http://localhost:3000/api/v1/$2" ${3:+-d "$3"} 2>/dev/null
}

# ── 1. Repo jouet (idempotent) ──────────────────────────────────────────────
log "[1/4] repo jouet ${GITEA_ADMIN}/${REPO}"
if ! gapi GET "repos/${GITEA_ADMIN}/${REPO}" | grep -q '"full_name"'; then
    gapi POST "user/repos" "{\"name\":\"${REPO}\",\"auto_init\":true,\"default_branch\":\"main\"}" \
        | grep -q '"full_name"' || { log "✗ création repo échouée"; exit 1; }
fi

b64() { printf '%s' "$1" | base64 | tr -d '\n'; }
# put <path> <contenu> <message> : crée OU met à jour un fichier (récupère le sha existant
# pour un PUT si le fichier est déjà là, sinon POST création). Un seul appel, pas de probe vide.
put() {
    local path="$1" content_b64 body method="POST" sha
    content_b64=$(b64 "$2")
    sha=$(gapi GET "repos/${GITEA_ADMIN}/${REPO}/contents/${path}" 2>/dev/null \
        | sed -n 's/.*"sha":"\([^"]*\)".*/\1/p' | head -1)
    body="{\"content\":\"${content_b64}\",\"message\":\"$3\",\"branch\":\"main\""
    if [ -n "${sha}" ]; then body="${body},\"sha\":\"${sha}\""; method="PUT"; fi
    body="${body}}"
    gapi "${method}" "repos/${GITEA_ADMIN}/${REPO}/contents/${path}" "${body}"
}

# ── 2. Push Dockerfile (FROM interne) + workflow → déclenche la CI ──────────
log "[2/4] push Dockerfile (FROM interne, air-gap) + workflow Gitea Actions"
DOCKERFILE="FROM ${FROM_IMG}
RUN echo 'image jouet buildée par la CI in-cluster (nestor, air-gap)' > /tmp/ok.txt
CMD [\"cat\",\"/tmp/ok.txt\"]"
put "Dockerfile" "${DOCKERFILE}" "sc35 Dockerfile jouet" >/dev/null
# Workflow : checkout manuel (git présent dans act_runner) puis buildctl → buildkitd distant.
# Le WORKFLOW MÊLE deux niveaux : les `${{ … }}` de Gitea Actions (LITTÉRAUX → single-quote)
# et mes variables shell BUILDKITD/REGISTRY_FQDN (substituées → motif `'"$VAR"'`, volontaire).
# On tait SC2016 (« expression not expanding ») : la non-expansion des `${{ }}` est VOULUE.
# shellcheck disable=SC2016
WORKFLOW='name: build
on: [push]
jobs:
  build:
    runs-on: host
    steps:
      - name: checkout
        env: { GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
        run: |
          set -eux
          AUTH="$(printf "%s" "${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}.git" | sed -E "s#://#://x:${GITHUB_TOKEN}@#")"
          rm -rf repo && git init -q repo && cd repo && git remote add origin "$AUTH"
          git fetch -q --depth 1 origin "${GITHUB_SHA}" && git checkout -q FETCH_HEAD
      - name: build+push via buildkitd in-pod
        run: |
          set -eux
          cd repo
          IMG="$(printf "%s" "${GITHUB_REPOSITORY}" | tr "[:upper:]" "[:lower:]")"
          buildctl --addr '"${BUILDKITD}"' build \
            --frontend dockerfile.v0 --local context=. --local dockerfile=. \
            --output type=image,name='"${REGISTRY_FQDN}"'/${IMG}:${GITHUB_SHA},registry.insecure=true,push=true'
put ".gitea/workflows/build.yaml" "${WORKFLOW}" "sc35 workflow CI" >/dev/null
log "✓ push effectué (le runner prend le job)"

# ── 3. Attente du run Gitea Actions → success ───────────────────────────────
log "[3/4] attente de la CI (runner → buildctl → buildkitd → push image, max 4 min)"
sleep 8
status=''
for _ in $(seq 1 40); do
    status=$(gapi GET "repos/${GITEA_ADMIN}/${REPO}/actions/tasks" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p' | head -1)
    case "${status}" in
        success) break ;;
        failure) log "✗ run CI en échec"; break ;;
    esac
    sleep 6
done
[ "${status}" = "success" ] || { log "✗ CI non aboutie (status=${status:-∅})"; exit 1; }
log "✓ CI SUCCESS"

# ── 4. L'image jouet est au registre interne ────────────────────────────────
log "[4/6] l'image produite est au registre interne"
head_sha=$(gapi GET "repos/${GITEA_ADMIN}/${REPO}/branches/main" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p' | head -1)
img_path="${GITEA_ADMIN}/${REPO}"
# On interroge le registre DEPUIS un pod (le buildkitd sait le joindre) : /v2/<repo>/tags/list.
tags=$(kubectl -n "${BUILDKIT_NS}" exec deploy/buildkitd -- \
    wget -T8 -qO- "http://${REGISTRY_FQDN}/v2/${img_path}/tags/list" 2>/dev/null || true)
printf '%s' "${tags}" | grep -q "${head_sha}" || {
    log "✗ image ${img_path}:${head_sha} absente du registre (tags: ${tags:-∅})"
    exit 1
}
log "✓ image ${img_path}:${head_sha} présente au registre interne"

# ── 5. CD : push un manifeste de déploiement → Argo CD le réconcilie ────────
# LE DÉCLENCHEUR CD est le PUSH GIT du manifeste (Argo CD suit un dépôt git, PAS le
# registre). On pousse un Deployment jouet (image = celle qu'on vient de builder, nom
# COURT `registry:80` résolu node-side par le kubelet, air-gap) sous `deploy/`, puis on
# crée l'Application Argo CD qui suit ce path. Argo CD (couche gitops) réconcilie → pod.
log "[5/6] push du manifeste de déploiement + Application Argo CD (déclencheur CD = push git)"
DEPLOY_MANIFEST="apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${REPO}
  namespace: ${DEPLOY_NS}
  labels: { app: ${REPO} }
spec:
  replicas: 1
  selector: { matchLabels: { app: ${REPO} } }
  template:
    metadata: { labels: { app: ${REPO} } }
    spec:
      automountServiceAccountToken: false
      securityContext: { runAsNonRoot: true, runAsUser: 1000, seccompProfile: { type: RuntimeDefault } }
      containers:
        - name: app
          image: registry:80/${img_path}:${head_sha}
          imagePullPolicy: IfNotPresent
          command: [\"sh\", \"-c\", \"cat /tmp/ok.txt; echo 'pod déployé par Argo CD depuis l image CI'; sleep 3600\"]
          securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: [ALL] } }"
put "deploy/deployment.yaml" "${DEPLOY_MANIFEST}" "sc35 manifeste de déploiement" >/dev/null

# Application Argo CD : source = le repo Gitea INTERNE (Argo CD clone en cluster), path deploy/.
# syncPolicy.automated : Argo CD réconcilie sans intervention. CreateNamespace : le ns cible.
cat <<YAML | kubectl apply -f - >/dev/null 2>&1 || { log "✗ apply Application échoué"; exit 1; }
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${REPO}
  namespace: ${ARGOCD_NS}
spec:
  project: default
  source:
    repoURL: http://gitea-http.gitea.svc.cluster.local/${GITEA_ADMIN}/${REPO}.git
    targetRevision: main
    path: deploy
  destination:
    server: https://kubernetes.default.svc
    namespace: ${DEPLOY_NS}
  syncPolicy:
    automated: { selfHeal: true, prune: true }
    syncOptions: [CreateNamespace=true]
YAML
log "✓ manifeste poussé + Application '${REPO}' créée"

# ── 6. Argo CD réconcilie → le POD démarre ──────────────────────────────────
log "[6/6] Argo CD réconcilie → le pod démarre (max 3 min)"
pod_ok=''
for _ in $(seq 1 30); do
    sync=$(kubectl -n "${ARGOCD_NS}" get application "${REPO}" -o jsonpath='{.status.sync.status}' 2>/dev/null || true)
    health=$(kubectl -n "${ARGOCD_NS}" get application "${REPO}" -o jsonpath='{.status.health.status}' 2>/dev/null || true)
    phase=$(kubectl -n "${DEPLOY_NS}" get pod -l app="${REPO}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)
    [ "${sync}" = "Synced" ] && [ "${health}" = "Healthy" ] && [ "${phase}" = "Running" ] && { pod_ok=1; break; }
    sleep 6
done
[ -n "${pod_ok}" ] || {
    log "✗ déploiement non abouti (sync=${sync:-∅} health=${health:-∅} pod=${phase:-∅})"
    kubectl -n "${DEPLOY_NS}" get pods -l app="${REPO}" 2>/dev/null || true
    kubectl -n "${ARGOCD_NS}" get application "${REPO}" -o jsonpath='{.status.conditions}' 2>/dev/null | head -c 300 || true
    exit 1
}
log "✓ Application Synced + Healthy, pod Running (déployé par Argo CD depuis l'image CI)"

log "🎉 CHAÎNE CI/CD COMPLÈTE prouvée (topo cicd) : push Gitea → CI (runner → buildctl → buildkitd in-pod → image registre interne) → CD (push manifeste → Argo CD réconcilie → POD déployé) — tout air-gap."
