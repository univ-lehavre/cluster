#!/usr/bin/env bash
#
# Scénario 34 — BUILD → DIGEST → GITOPS : le PREMIER PAS de l'ADR 0095 (§1.a) tient-il
# de bout en bout ? Un build d'image rendu GitOps-compatible déploie-t-il PAR DIGEST ?
#
# ADR 0095 §1.a tranche : on garde le build node-side (nerdctl/buildkit, ADR 0033) mais
# on le rend GitOps-compatible — après build+push, on LIT le digest réel de l'image et on
# l'ÉCRIT dans le repo Gitea `cluster/apps`, pour qu'Argo CD déploie par `@sha256:<digest>`
# (référence IMMUABLE, ADR 0095 §2) et JAMAIS par un tag mutable. Le plan associé
# (docs/plans/plan-build-evenementiel-gitops.md, étape 4) demande cette preuve e2e au banc
# Lima mono-nœud local-path (ADR 0085) AVANT tout geste prod. Ce scénario la fournit :
#
#   1. PRÉREQUIS : Gitea + Argo CD + registry interne + Dagster (workspace) présents
#      (sinon SKIP neutre — sauf STRICT_DIGEST=1, qui FAIL, calque STRICT_CACHE du 33).
#   2. BUILD + DIGEST : une image JOUET contrôlée par cluster est buildée node-side
#      (nerdctl/buildkit via `limactl shell`) et poussée dans `registry:80`. On LIT son
#      digest (`nerdctl image inspect … RepoDigests`). Gate : `sha256:<64 hex>` non vide.
#   3. WRITE-BACK : la déclaration d'Application est écrite dans Gitea `cluster/apps` via
#      la Contents API (patron `push_gitea_file`, create-or-update idempotent). Gate : le
#      manifeste poussé référence `registry:80/<app>@sha256:…`, PAS un tag mutable.
#   4. DÉPLOIEMENT PAR DIGEST : Argo CD réconcilie (la racine app-of-apps voit le fichier
#      → crée l'Application fille → elle se synchronise) ; l'Application devient
#      Synced/Healthy ; le pod déployé tire l'image PAR DIGEST. Gate : pod Running ET
#      `.spec.containers[].image` se termine par `@sha256:<digest>`.
#   5. (manuel) un run applicatif observable — hors périmètre ici (cf. scénario 29) ; on
#      prouve la CHAÎNE de fabrique→déploiement-par-digest, pas l'exécution métier.
#
# ── IMAGE DE TEST : jouet contrôlée par cluster (PAS citation) ────────────────
# On build une image JOUET minimale (busybox + un sleep) que CLUSTER maîtrise de bout en
# bout : Dockerfile généré ici, repo `cluster/apps` écrit ici, Application autonome. Cela
# isole la preuve de la CHAÎNE (build→digest→write-back→Argo CD→pod-par-digest) sans
# dépendre du dépôt atlas ni de l'overlay citation. La TENSION citation est volontairement
# DÉTECTÉE et SKIPPÉE (MODE=citation, voir plus bas) : le seed exige le placeholder
# __CITATION_IMAGE__ dans l'overlay atlas (frontière ADR 0094 — cluster ne réécrit pas la
# structure interne d'atlas) ; tant qu'atlas n'a pas factorisé ce placeholder, prouver
# citation reviendrait à deviner cette structure. La preuve de chaîne, elle, ne l'exige pas.
#
# ── GARDE BANC ABSOLUE ───────────────────────────────────────────────────────
# Ce scénario MUTE Gitea + Argo CD (push + Application). Il ne doit JAMAIS toucher la prod.
# On EXIGE que le cluster du contexte kube courant soit le banc (EXPECTED_CLUSTER, défaut
# `cluster-banc` — le nom posé par fetch_kubeconfig_node, bench/lima/lib.sh). Si le cluster
# est `cluster-prod` (ou tout autre), `die` immédiat (symétrique inverse de la garde
# assert_prod_target du seed). run-phases.sh fournit ${WORKDIR}/kubeconfig (cluster
# `cluster-banc`) : lancer avec `KUBECONFIG=bench/lima/.work/kubeconfig`.
#
# ── CONTRAINTES ──────────────────────────────────────────────────────────────
# DNS : les appels API Gitea tapent localhost:3000 DANS le pod gitea (kubectl exec),
# JAMAIS le FQDN *.svc.cluster.local (search domain externe + ndots:5 → timeout glibc/curl,
# drift connu). Le pull kubelet de `registry:80/...@sha256:…` passe par le containerd des
# nœuds (certs.d HTTP + /etc/hosts → ClusterIP du Service registry), donc résolvable.
# Le digest est lu node-side via `limactl shell <CP> sudo nerdctl …` (le banc est mono-nœud
# local-path, ADR 0085 — le CP est aussi le builder ; pas de Ceph).
# Nettoyage : trap qui supprime l'Application, le fichier Gitea de test et l'image jouet
# (best-effort) — ne pas polluer le banc. KEEP=1 inspecte sans nettoyer.
#
# Pré-requis : banc atlas monté (`run-phases.sh atlas`) + socle GitOps + Dagster +
# la racine app-of-apps (Application `cluster-apps`) posée par le seed (ou ce scénario
# applique l'Application fille directement si la racine est absente — voir étape 4).
#
# Variables :
#   STRICT_DIGEST=1   échoue (au lieu de skip) si un prérequis manque (CI banc)
#   MODE              jouet (défaut) | citation — `citation` détecte/skip la tension overlay
#   KUBECONFIG        kubeconfig du BANC (run-phases : bench/lima/.work/kubeconfig)
#   EXPECTED_CLUSTER  (défaut cluster-banc) — cluster attendu du contexte courant (garde)
#   GITEA_NS / ARGOCD_NS                       (défauts gitea / argocd)
#   GITEA_ORG_APPS / GITEA_REPO_APPS           (défauts cluster / apps) — repo déclaratif
#   GITEA_ADMIN_USER                           (défaut atlas-admin) — admin Gitea du banc
#   REGISTRY                                   (défaut registry:80) — registry interne
#   LIMA_CP                                    (défaut cp1) — instance Lima builder/CP
#   ATLAS_REPO_DIR                             (défaut ../atlas) — pour MODE=citation
set -euo pipefail

# Chemin ABSOLU du dossier du scénario (résout quel que soit le cwd de lancement —
# un `cd` + dirname relatif doublait le préfixe et ne trouvait pas lib.sh, cf. 33).
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# shellcheck source=bench/scenarios/lib.sh
. "${HERE}/lib.sh"

STRICT_DIGEST=${STRICT_DIGEST:-0}
MODE=${MODE:-jouet}
EXPECTED_CLUSTER=${EXPECTED_CLUSTER:-cluster-banc}
GITEA_NS=${GITEA_NS:-gitea}
ARGOCD_NS=${ARGOCD_NS:-argocd}
GITEA_ORG_APPS=${GITEA_ORG_APPS:-cluster}
GITEA_REPO_APPS=${GITEA_REPO_APPS:-apps}
GITEA_ADMIN_USER=${GITEA_ADMIN_USER:-atlas-admin}
REGISTRY=${REGISTRY:-registry:80}
LIMA_CP=${LIMA_CP:-cp1}
ATLAS_REPO_DIR=${ATLAS_REPO_DIR:-${HERE}/../../../atlas}

# Image jouet contrôlée par cluster (nom générique, ADR 0023). Tag MUTABLE `:test` :
# c'est volontaire — on prouve justement qu'on déploie par DIGEST, pas par ce tag.
TOY_APP=${TOY_APP:-toy-digest-probe}
TOY_TAG=${TOY_TAG:-test}
TOY_NS=${TOY_NS:-default}
# Suffixe unique par run (fichier Gitea + Application + Deployment de test isolés).
RUN_ID="sc34-${RANDOM}${RANDOM}"
# Nom de l'Application fille de test (déployée via cluster/apps, réconciliée par la racine).
TEST_APP="${RUN_ID}"

skip_or_fail() {
    if [ "${STRICT_DIGEST}" = 1 ]; then
        log "✗ STRICT_DIGEST=1 et prérequis manquant : $1"
        exit 1
    fi
    log "skip — $1"
    log "  Monter d'abord : run-phases.sh atlas puis le seed app-of-apps (ADR 0094/0095)."
    exit 0
}

# ════════════════════════════════════════════════════════════════════════════
# GARDE BANC — ne JAMAIS muter une autre cible que le banc attendu (symétrique
# inverse de assert_prod_target du seed : ici on REFUSE la prod).
# ════════════════════════════════════════════════════════════════════════════
ctx=$(kubectl config current-context 2>/dev/null) \
    || die "aucun contexte kube courant (KUBECONFIG=${KUBECONFIG:-<défaut>}) — fournir le kubeconfig du banc"
cluster=$(kubectl config view -o \
    "jsonpath={.contexts[?(@.name=='${ctx}')].context.cluster}" 2>/dev/null)
[ "${cluster}" = "${EXPECTED_CLUSTER}" ] \
    || die "cible kube = cluster '${cluster:-∅}' (contexte '${ctx}'), attendu '${EXPECTED_CLUSTER}'. \
Ce scénario MUTE Gitea/Argo CD : il REFUSE de tourner ailleurs que sur le banc. \
Lancer avec KUBECONFIG=bench/lima/.work/kubeconfig (surcharger EXPECTED_CLUSTER si volontaire)."
log "Garde banc OK — contexte '${ctx}' → cluster '${cluster}' (≠ prod)."

# ── MODE citation : détecter la tension overlay puis SKIP (frontière ADR 0094) ──
# Le seed n'injecte le digest citation QUE via le placeholder __CITATION_IMAGE__ qu'atlas
# expose. Tant qu'atlas ne l'a pas factorisé, cluster ne devine pas la structure interne
# de l'overlay → on SKIP avec un message clair (la preuve de chaîne se fait en MODE jouet).
if [ "${MODE}" = citation ]; then
    overlay="${ATLAS_REPO_DIR}/dataops/citation-dagster/deploy/overlays/prod"
    if [ ! -d "${overlay}" ]; then
        skip_or_fail "overlay citation introuvable (${overlay}) — dépôt atlas absent ? (surcharger ATLAS_REPO_DIR)"
    fi
    if ! grep -rqlF '__CITATION_IMAGE__' "${overlay}" 2>/dev/null; then
        log "skip — atlas doit factoriser __CITATION_IMAGE__ dans l'overlay citation (${overlay})."
        log "  cluster n'injecte le digest QUE via ce point d'injection (frontière ADR 0094) — il ne"
        log "  réécrit pas la structure interne d'atlas. Issue de factorisation (résout aussi le"
        log "  double-couplage images[].newTag + DAGSTER_CURRENT_IMAGE, audit #499). Preuve de chaîne"
        log "  en MODE=jouet (défaut) en attendant. STRICT_DIGEST=1 ne force PAS (tension upstream)."
        exit 0
    fi
    skip_or_fail "MODE=citation au-delà de la détection du placeholder n'est pas implémenté ici (cf. seed-app-of-apps.sh + scénarios 27/29 pour le bout-en-bout citation)"
fi

# ── 1. Pré-requis : la chaîne build→GitOps est-elle montée ? ──────────────────
log "[1/4] prérequis : Gitea + Argo CD + registry + Dagster + builder node-side"
kubectl -n "${GITEA_NS}" get deploy gitea >/dev/null 2>&1 \
    || skip_or_fail "Gitea absent (ns ${GITEA_NS})"
kubectl -n "${ARGOCD_NS}" get deploy argocd-server >/dev/null 2>&1 \
    || skip_or_fail "Argo CD absent (ns ${ARGOCD_NS})"
kubectl -n "${ARGOCD_NS}" get applications.argoproj.io >/dev/null 2>&1 \
    || skip_or_fail "CRD Application Argo CD absente"
kubectl get ns "${REGISTRY%%:*}" >/dev/null 2>&1 \
    || skip_or_fail "namespace registry '${REGISTRY%%:*}' absent (registry interne non monté)"
kubectl get ns dagster >/dev/null 2>&1 \
    || skip_or_fail "namespace dagster absent (workspace Dagster non monté)"
command -v limactl >/dev/null 2>&1 \
    || skip_or_fail "limactl absent (build node-side impossible — banc Lima requis)"
limactl shell "${LIMA_CP}" true >/dev/null 2>&1 \
    || skip_or_fail "instance Lima '${LIMA_CP}' injoignable (surcharger LIMA_CP)"
gitea_pod=$(kubectl -n "${GITEA_NS}" get pod -l app=gitea \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -n "${gitea_pod}" ] || skip_or_fail "pod gitea introuvable (ns ${GITEA_NS})"
log "✓ Gitea (${gitea_pod}) + Argo CD + registry '${REGISTRY}' + dagster + builder '${LIMA_CP}' présents"

# ── Helpers API Gitea (DANS le pod gitea, localhost:3000 — JAMAIS le FQDN). ───
# Token éphémère (admin posé par le seed / gitea-init). --raw : valeur seule.
gitea_token=$(kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- \
    gitea admin user generate-access-token -u "${GITEA_ADMIN_USER}" \
    -t "${RUN_ID}" --scopes all --raw 2>/dev/null | tr -d '[:space:]')
[ -n "${gitea_token}" ] || skip_or_fail "token Gitea non obtenu (admin '${GITEA_ADMIN_USER}' présent ? seed fait ?)"

# api METHOD PATH [BODY] — appel REST Gitea depuis le pod (intra-cluster, localhost).
api() {
    local method=$1 path=$2 body=${3:-}
    if [ -n "${body}" ]; then
        kubectl -n "${GITEA_NS}" exec -i "${gitea_pod}" -- curl -sS \
            -X "${method}" -H "Authorization: token ${gitea_token}" \
            -H "Content-Type: application/json" \
            "http://localhost:3000/api/v1${path}" -d "${body}" 2>/dev/null
    else
        kubectl -n "${GITEA_NS}" exec -i "${gitea_pod}" -- curl -sS \
            -X "${method}" -H "Authorization: token ${gitea_token}" \
            "http://localhost:3000/api/v1${path}" 2>/dev/null
    fi
}

# push_gitea_file REPO_PATH LOCAL_FILE MESSAGE — create-or-update idempotent (patron
# push_gitea_file de gitea-init.sh / push_contents_file du seed). Lit le sha existant
# pour une MAJ ; VÉRIFIE la présence de "commit" (un push raté laisserait l'ancien
# manifeste → Argo CD déploierait un manifeste périmé : drift à NE PAS reproduire).
push_gitea_file() {
    local rpath=$1 lfile=$2 msg=$3 content sha payload resp
    content=$(base64 < "${lfile}" | tr -d '\n')
    sha=$(api GET "/repos/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}/contents/${rpath}" \
        | grep -oE '"sha":"[a-f0-9]+"' | head -1 | cut -d'"' -f4) || true
    if [ -n "${sha}" ]; then
        payload="{\"content\":\"${content}\",\"sha\":\"${sha}\",\"message\":\"${msg}\"}"
        resp=$(api PUT "/repos/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}/contents/${rpath}" "${payload}")
    else
        payload="{\"content\":\"${content}\",\"message\":\"${msg}\"}"
        resp=$(api POST "/repos/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}/contents/${rpath}" "${payload}")
    fi
    printf '%s' "${resp}" | grep -q '"commit"' \
        || die "push Contents API de ${rpath} ÉCHOUÉ — réponse: ${resp}"
}

# delete_gitea_file REPO_PATH — supprime un fichier de test (best-effort, nettoyage).
delete_gitea_file() {
    local rpath=$1 sha
    sha=$(api GET "/repos/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}/contents/${rpath}" \
        | grep -oE '"sha":"[a-f0-9]+"' | head -1 | cut -d'"' -f4) || true
    [ -n "${sha}" ] || return 0
    api DELETE "/repos/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}/contents/${rpath}" \
        "{\"sha\":\"${sha}\",\"message\":\"sc34 cleanup ${rpath}\"}" >/dev/null 2>&1 || true
}

# ── Le repo déclaratif cluster/apps existe-t-il ? (posé par le seed) ──────────
api GET "/repos/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}" | grep -q '"full_name"' \
    || skip_or_fail "repo Gitea ${GITEA_ORG_APPS}/${GITEA_REPO_APPS} absent (seed app-of-apps non joué)"

# ── Nettoyage (trap) : Application + Deployment + fichiers Gitea + image jouet. ─
# Best-effort, à la sortie quoi qu'il arrive (sauf KEEP=1). Ne pas polluer le banc.
toy_manifest_path="manifests/${RUN_ID}/deployment.yaml"
toy_app_path="apps/${RUN_ID}.yaml"
# shellcheck disable=SC2329  # invoquée via trap EXIT
cleanup() {
    [ "${KEEP:-0}" = 1 ] && { log "KEEP=1 — pas de nettoyage (ressources de test conservées)."; return 0; }
    kubectl -n "${ARGOCD_NS}" delete application "${TEST_APP}" --wait=false >/dev/null 2>&1 || true
    kubectl -n "${TOY_NS}" delete deployment "${TEST_APP}" --wait=false >/dev/null 2>&1 || true
    delete_gitea_file "${toy_app_path}"
    delete_gitea_file "${toy_manifest_path}"
    # Image jouet node-side (best-effort — le registry garde le blob, on retire le tag local).
    limactl shell "${LIMA_CP}" sudo nerdctl rmi "${REGISTRY}/${TOY_APP}:${TOY_TAG}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# ── 2. BUILD + DIGEST : build node-side de l'image jouet → lire le digest ─────
log "[2/4] build node-side de l'image jouet ${REGISTRY}/${TOY_APP}:${TOY_TAG} (nerdctl/buildkit)"
# Dockerfile jouet minimal (busybox + un sleep) : pas de réseau au build (busybox est dans
# le registry/cache du nœud ; le banc est mono-nœud local-path). On l'écrit DANS la VM et
# on build/push avec nerdctl (containerd du nœud → registry:80 en HTTP via certs.d).
build_out=$(limactl shell "${LIMA_CP}" sudo sh -c "
    set -e
    d=\$(mktemp -d)
    cat > \"\$d/Dockerfile\" <<'DOCKERFILE'
FROM busybox
LABEL test.cluster.dev/scenario=34-build-gitops-digest
ENTRYPOINT [\"sh\", \"-c\", \"echo sc34 alive; sleep 3600\"]
DOCKERFILE
    nerdctl build -t '${REGISTRY}/${TOY_APP}:${TOY_TAG}' \"\$d\" >/dev/null 2>&1
    nerdctl push '${REGISTRY}/${TOY_APP}:${TOY_TAG}' >/dev/null 2>&1
    rm -rf \"\$d\"
    echo built
" 2>&1) || true
[ "${build_out}" = built ] || {
    log "✗ build/push node-side de l'image jouet échoué — sortie: ${build_out}"
    skip_or_fail "build node-side impossible (busybox indisponible hors-ligne ? buildkit down ?)"
}
log "✓ image jouet buildée + poussée dans ${REGISTRY}"

# Lire le DIGEST réel de l'image poussée (RepoDigests[0] = registry:80/<app>@sha256:…),
# comme le rôle platform-build-images (build_image_digests, ADR 0095 §1.a/§2). On en
# extrait la chaîne `sha256:<hex>` SEULE.
repodigest=$(limactl shell "${LIMA_CP}" sudo nerdctl image inspect \
    --format '{{ index .RepoDigests 0 }}' \
    "${REGISTRY}/${TOY_APP}:${TOY_TAG}" 2>/dev/null | tr -d '[:space:]')
digest="${repodigest##*@}"  # garde sha256:<hex>
# Gate 2 : le digest est un sha256 valide (un push raté ne doit pas écrire un digest vide).
if printf '%s' "${digest}" | grep -qE '^sha256:[0-9a-f]{64}$'; then
    log "✓ digest lu : ${digest} (référence immuable, ADR 0095 §2)"
else
    log "✗ digest invalide ou vide : « ${digest:-∅} » (RepoDigests=« ${repodigest:-∅} »)"
    exit 1
fi

# Référence de déploiement par DIGEST (immuable) — l'ANCRE de la preuve.
image_ref="${REGISTRY}/${TOY_APP}@${digest}"

# ── 3. WRITE-BACK : écrire la déclaration dans Gitea cluster/apps PAR DIGEST ──
log "[3/4] write-back dans ${GITEA_ORG_APPS}/${GITEA_REPO_APPS} : manifeste + Application (par @sha256)"
work=$(mktemp -d "${TMPDIR:-/tmp}/sc34.XXXXXX")
# shellcheck disable=SC2329  # invoquée via trap EXIT (chaînée avec cleanup)
rm_work() { rm -rf "${work}"; }
trap 'cleanup; rm_work' EXIT INT TERM

# (a) le Deployment jouet — référence l'image PAR DIGEST (jamais le tag mutable).
cat > "${work}/deployment.yaml" <<DEPLOY
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${TEST_APP}
  namespace: ${TOY_NS}
  labels:
    test.cluster.dev/scenario: 34-build-gitops-digest
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${TEST_APP}
  template:
    metadata:
      labels:
        app: ${TEST_APP}
        test.cluster.dev/scenario: 34-build-gitops-digest
    spec:
      containers:
        - name: probe
          image: ${image_ref}
          imagePullPolicy: IfNotPresent
DEPLOY

# (b) l'Application fille — source = ce MÊME repo cluster/apps, path = le dossier du
# manifeste. La racine app-of-apps (Application cluster-apps, path apps/) la VOIT et la
# crée → elle réconcilie le Deployment. C'est la chaîne réelle « pousser un fichier dans
# cluster/apps = déployer », exercée par digest (le Deployment référence @sha256).
apps_repo_url="http://gitea-http.gitea.svc.cluster.local/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}.git"
cat > "${work}/application.yaml" <<APP
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${TEST_APP}
  namespace: ${ARGOCD_NS}
  labels:
    test.cluster.dev/scenario: 34-build-gitops-digest
spec:
  project: cluster-apps
  source:
    repoURL: ${apps_repo_url}
    targetRevision: main
    path: manifests/${RUN_ID}
  destination:
    server: https://kubernetes.default.svc
    namespace: ${TOY_NS}
  syncPolicy:
    automated:
      selfHeal: true
      prune: true
    syncOptions:
      - CreateNamespace=false
APP

# Pousser d'abord le manifeste (la SOURCE que l'Application lira), puis l'Application.
push_gitea_file "${toy_manifest_path}" "${work}/deployment.yaml" "sc34: manifeste jouet par digest"
push_gitea_file "${toy_app_path}" "${work}/application.yaml" "sc34: Application jouet (ADR 0095)"

# Gate 3 : RELIRE le fichier poussé dans Gitea et vérifier qu'il référence bien @sha256
# (PAS un tag mutable). On lit le contenu via la Contents API (base64) et on le décode.
pushed=$(api GET "/repos/${GITEA_ORG_APPS}/${GITEA_REPO_APPS}/contents/${toy_manifest_path}" \
    | grep -oE '"content":"[^"]*"' | head -1 | cut -d'"' -f4 | base64 -d 2>/dev/null)
if printf '%s' "${pushed}" | grep -qF "image: ${REGISTRY}/${TOY_APP}@${digest}"; then
    log "✓ Gitea contient bien la référence par DIGEST (registry/${TOY_APP}@${digest})"
else
    log "✗ le manifeste poussé NE référence PAS l'image par @sha256 (tag mutable ?)"
    printf '%s\n' "${pushed}" | grep -i 'image:' || true
    exit 1
fi
# Garde explicite : aucune référence par TAG mutable ne doit subsister dans le manifeste.
if printf '%s' "${pushed}" | grep -qE "image: ${REGISTRY}/${TOY_APP}:[^@[:space:]]+$"; then
    log "✗ une référence par TAG mutable subsiste dans le manifeste (NON conforme ADR 0095 §2)"
    exit 1
fi

# ── 4. DÉPLOIEMENT PAR DIGEST : Argo CD réconcilie → pod Running par @sha256 ──
log "[4/4] Argo CD réconcilie ${TEST_APP} → Synced/Healthy + pod tiré PAR DIGEST"
# Laisser la racine app-of-apps créer l'Application fille (path apps/). Si elle n'apparaît
# pas (racine absente / polling lent), on l'applique directement (le fichier Gitea reste
# la source de vérité ; ceci ne fait qu'accélérer la création de l'objet Application).
root_present=$(kubectl -n "${ARGOCD_NS}" get application cluster-apps \
    -o jsonpath='{.metadata.name}' 2>/dev/null || true)
if [ -n "${root_present}" ]; then
    log "  racine app-of-apps présente — on attend qu'elle crée l'Application fille ${TEST_APP}"
    for _ in $(seq 1 24); do
        kubectl -n "${ARGOCD_NS}" get application "${TEST_APP}" >/dev/null 2>&1 && break
        # Forcer un refresh de la racine accélère la détection du nouveau fichier.
        kubectl -n "${ARGOCD_NS}" annotate application cluster-apps \
            argocd.argoproj.io/refresh=normal --overwrite >/dev/null 2>&1 || true
        sleep 5
    done
fi
if ! kubectl -n "${ARGOCD_NS}" get application "${TEST_APP}" >/dev/null 2>&1; then
    log "  Application fille pas encore créée par la racine — application directe (source = Gitea)"
    kubectl apply -f "${work}/application.yaml" >/dev/null \
        || die "apply direct de l'Application ${TEST_APP} échoué"
fi

# Attendre Synced/Healthy (réconciliation du Deployment depuis Gitea).
sync='' health=''
for _ in $(seq 1 36); do
    sync=$(kubectl -n "${ARGOCD_NS}" get application "${TEST_APP}" -o jsonpath='{.status.sync.status}' 2>/dev/null || true)
    health=$(kubectl -n "${ARGOCD_NS}" get application "${TEST_APP}" -o jsonpath='{.status.health.status}' 2>/dev/null || true)
    [ "${sync}" = "Synced" ] && [ "${health}" = "Healthy" ] && break
    kubectl -n "${ARGOCD_NS}" annotate application "${TEST_APP}" \
        argocd.argoproj.io/refresh=normal --overwrite >/dev/null 2>&1 || true
    sleep 5
done
if [ "${sync}" = "Synced" ] && [ "${health}" = "Healthy" ]; then
    log "✓ Application ${TEST_APP} Synced/Healthy — Argo CD a déployé le manifeste par digest"
else
    log "✗ Application ${TEST_APP} ${sync:-∅}/${health:-∅} (attendu Synced/Healthy)"
    kubectl -n "${ARGOCD_NS}" get application "${TEST_APP}" -o wide 2>/dev/null || true
    exit 1
fi

# Gate 4a : le pod déployé est Running (la code/l'image jouet tourne).
pod_ready() {
    [ "$(kubectl -n "${TOY_NS}" get deploy "${TEST_APP}" \
        -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]
}
for _ in $(seq 1 30); do pod_ready && break; sleep 5; done
if pod_ready; then
    log "✓ Deployment ${TEST_APP} Ready (pod Running)"
else
    log "✗ le pod de ${TEST_APP} n'est pas Running"
    kubectl -n "${TOY_NS}" get pods -l "app=${TEST_APP}" -o wide 2>/dev/null || true
    kubectl -n "${TOY_NS}" describe deploy "${TEST_APP}" 2>/dev/null | tail -20 || true
    exit 1
fi

# Gate 4b : le pod tire l'image PAR DIGEST (la VRAIE preuve d'immuabilité côté runtime).
# On lit l'image effective du conteneur du pod : elle DOIT contenir @sha256:<digest>.
pod_image=$(kubectl -n "${TOY_NS}" get pods -l "app=${TEST_APP}" \
    -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null)
if printf '%s' "${pod_image}" | grep -qF "@${digest}"; then
    log "✓ pod tiré PAR DIGEST : ${pod_image} (immuable, pas un tag mutable)"
else
    log "✗ le pod ne référence PAS l'image par @sha256 : « ${pod_image:-∅} » (attendu …@${digest})"
    exit 1
fi

echo
log "🎉 PREMIER PAS ADR 0095 prouvé : build → digest (${digest}) → write-back cluster/apps →"
log "   Argo CD Synced/Healthy → pod Running tiré PAR DIGEST. Déploiement immuable (ADR 0095 §2)."
log "ℹ️  Run applicatif observable : hors périmètre (cf. scénario 29) ; ici on prouve la CHAÎNE."
