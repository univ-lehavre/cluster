#!/usr/bin/env bash
#
# Scénario 36 — INTÉGRATION : la LIVRAISON RÉELLE d'atlas (push main → usine → branche deploy).
#
# Le 35 prouve l'USINE sur un jouet (Dockerfile + workflow poussés par l'épreuve) ; le 36
# pousse le VRAI dépôt atlas (son `main` revu) sur la forge de l'instance et vérifie la
# sortie doctrinale de la chaîne de livraison (ADR 0113, atlas 0104) : le workflow
# `.gitea/workflows/livraison.yaml` — versionné DANS atlas — builde chaque code-location
# in-pod (cible `code` FROM sa pré-image, zéro egress, ADR 0110/0112), pousse
# `<cl>-dagster:<sha12>` au registre interne, puis MATÉRIALISE la branche `deploy`
# (projection `main ⊕ digests`, placeholders substitués, `.deploy/digests.env`).
#
# L'épreuve prouve AU PASSAGE le dernier prérequis d'usine du plan atlas (lot 2) : le
# DROIT DE PUSH du token Actions sur `deploy` — si la branche apparaît, c'est que le job
# a pu la pousser.
#
# PÉRIMÈTRE : la livraison SEULE (push → CI → deploy matérialisée). La réconciliation
# Argo CD des overlays prod (OBC/RGW) attend un terrain Ceph — hors épreuve (verrou de
# stockage documenté au plan atlas) ; le déploiement Argo CD reste prouvé par le 35.
#
# Pré-requis (sinon SKIP neutre, ou échec si STRICT_LIVRAISON=1) :
#   - socle CI/CD Ready : gitea + registry + buildkitd + gitea-runner (topo cicd) ;
#   - un checkout atlas (ATLAS_DIR) portant la chaîne (workflow + regenerate-deploy.sh) ;
#   - les PRÉ-IMAGES des code-locations au registre (flux poste, ADR 0110 :
#     `deploy/build-deps-base.sh` — l'épreuve LISTE celles qui manquent).
#
# Variables :
#   STRICT_LIVRAISON=1   échoue (au lieu de skip) si un prérequis manque
#   ATLAS_DIR            checkout atlas (défaut : dépôt frère `../atlas` du clone cluster)
#   WAIT_CI_S            budget d'attente du run (défaut 1200 s — 4 builds in-pod)
#   LOCAL_PORT           port local du port-forward gitea (défaut 3936)
#   GITEA_NS / REGISTRY_NS / BUILDKIT_NS / RUNNER_NS / GITEA_ADMIN / REPO
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

STRICT_LIVRAISON=${STRICT_LIVRAISON:-0}
GITEA_NS=${GITEA_NS:-gitea}
REGISTRY_NS=${REGISTRY_NS:-registry}
BUILDKIT_NS=${BUILDKIT_NS:-buildkit}
RUNNER_NS=${RUNNER_NS:-gitea-runner}
GITEA_ADMIN=${GITEA_ADMIN:-atlas-admin}
REPO=${REPO:-atlas}
ATLAS_DIR=${ATLAS_DIR:-$(cd ../../.. 2>/dev/null && pwd)/atlas}
WAIT_CI_S=${WAIT_CI_S:-1200}
LOCAL_PORT=${LOCAL_PORT:-3936}
REGISTRY_FQDN=registry.registry.svc.cluster.local:80

# shellcheck source=bench/scenarios/lib.sh
. ./lib.sh

skip_or_fail() {
    if [ "${STRICT_LIVRAISON}" = 1 ]; then
        log "✗ STRICT_LIVRAISON=1 et chaîne non prête : $1"
        exit 1
    fi
    log "skip — $1"
    log "  Socle : nestor install (topo cicd) ; pré-images : flux poste ADR 0110."
    exit 0
}

# Nettoyage : port-forward + miroir temporaire (posés plus bas).
pf_pid=""
MIRROR=""
cleanup() {
    [ -n "${pf_pid}" ] && kill "${pf_pid}" 2>/dev/null || true
    [ -n "${MIRROR}" ] && rm -rf "${MIRROR}" 2>/dev/null || true
}
trap cleanup EXIT

# ── Pré-requis 1 : les maillons du socle exercés par la livraison ───────────
kubectl -n "${GITEA_NS}" get deploy gitea >/dev/null 2>&1 || skip_or_fail "Gitea absent"
kubectl -n "${REGISTRY_NS}" get deploy registry >/dev/null 2>&1 || skip_or_fail "registry absent"
kubectl -n "${BUILDKIT_NS}" get deploy buildkitd >/dev/null 2>&1 || skip_or_fail "buildkitd absent"
kubectl -n "${RUNNER_NS}" get deploy gitea-runner >/dev/null 2>&1 || skip_or_fail "gitea-runner absent"
runner_ready=$(kubectl -n "${RUNNER_NS}" get deploy gitea-runner -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
[ "${runner_ready}" = "1" ] || skip_or_fail "gitea-runner pas Ready"
log "✓ gitea + registry + buildkitd + gitea-runner présents et Ready"

# ── Pré-requis 2 : le checkout atlas porte la chaîne ────────────────────────
git -C "${ATLAS_DIR}" rev-parse --git-dir >/dev/null 2>&1 \
    || skip_or_fail "checkout atlas introuvable (ATLAS_DIR=${ATLAS_DIR})"
# Le sha LIVRÉ : `origin/main` (le geste deploy.sh pousse ce ref, jamais HEAD — ADR 0104) ;
# replis pour un banc hors-ligne : main local, puis HEAD.
SHA=$(git -C "${ATLAS_DIR}" rev-parse --verify -q refs/remotes/origin/main \
    || git -C "${ATLAS_DIR}" rev-parse --verify -q refs/heads/main \
    || git -C "${ATLAS_DIR}" rev-parse HEAD)
short_sha=$(printf '%s' "${SHA}" | cut -c1-12)
for f in .gitea/workflows/livraison.yaml scripts/regenerate-deploy.sh; do
    git -C "${ATLAS_DIR}" cat-file -e "${SHA}:${f}" 2>/dev/null \
        || skip_or_fail "atlas@${short_sha} ne porte pas ${f} (main trop ancien ?)"
done
# Les code-locations livrables À CE SHA (répertoires dataops/*-dagster avec Dockerfile).
CLS=$(git -C "${ATLAS_DIR}" ls-tree --name-only "${SHA}" dataops/ 2>/dev/null \
    | sed -n 's|^dataops/\(.*-dagster\)$|\1|p' \
    | while read -r d; do
        if git -C "${ATLAS_DIR}" cat-file -e "${SHA}:dataops/${d}/Dockerfile" 2>/dev/null; then echo "${d}"; fi
    done)
[ -n "${CLS}" ] || skip_or_fail "aucune code-location buildable à atlas@${short_sha}"
nb_cls=$(printf '%s\n' "${CLS}" | wc -l | tr -d ' ')
log "✓ atlas@${short_sha} : chaîne présente, ${nb_cls} code-location(s) ($(printf '%s' "${CLS}" | tr '\n' ' '))"

# ── Pré-requis 3 : les pré-images au registre (flux poste, ADR 0110) ────────
# Le build in-pod part de `FROM deps-base@<tag>` : sans la pré-image, le workflow échoue
# BRUYAMMENT — on le dit AVANT, avec la liste et le geste de remédiation.
missing=""
for d in ${CLS}; do
    logical=$(git -C "${ATLAS_DIR}" show "${SHA}:dataops/${d}/deploy/deps-base.ref" 2>/dev/null | tr -d '[:space:]')
    [ -n "${logical}" ] || { missing="${missing} ${d}(deps-base.ref absent)"; continue; }
    name_tag="${logical#registry:80/}"
    name="${name_tag%%:*}"; tag="${name_tag##*:}"
    tags=$(kubectl -n "${BUILDKIT_NS}" exec deploy/buildkitd -- \
        wget -T8 -qO- "http://${REGISTRY_FQDN}/v2/${name}/tags/list" 2>/dev/null || true)
    printf '%s' "${tags}" | grep -q "\"${tag}\"" || missing="${missing} ${d}(${name}:${tag})"
done
[ -z "${missing}" ] || skip_or_fail "pré-image(s) absente(s) du registre :${missing}
  → sur le poste (egress + port-forward registre) : dataops/<cl>-dagster/deploy/build-deps-base.sh"
log "✓ pré-images présentes au registre pour les ${nb_cls} code-location(s)"

# ── 1. Admin + token + API Gitea (curl DANS le pod, pas de port-forward API) ─
gitea_pod=$(kubectl -n "${GITEA_NS}" get pod -l app=gitea -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -n "${gitea_pod}" ] || skip_or_fail "pod gitea introuvable"
if ! kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- gitea admin user list 2>/dev/null \
    | awk '{print $2}' | grep -qx "${GITEA_ADMIN}"; then
    kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- gitea admin user create \
        --username "${GITEA_ADMIN}" --password "sc36-${RANDOM}${RANDOM}" \
        --email "${GITEA_ADMIN}@example.lan" --admin --must-change-password=false >/dev/null 2>&1 \
        || skip_or_fail "création de l'admin ${GITEA_ADMIN} échouée"
    log "✓ admin Gitea ${GITEA_ADMIN} créé"
fi
gitea_token=$(kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- \
    gitea admin user generate-access-token -u "${GITEA_ADMIN}" -t "sc36-${RANDOM}" --scopes all --raw 2>/dev/null | tr -d '[:space:]')
[ -n "${gitea_token}" ] || skip_or_fail "token Gitea non obtenu (admin ${GITEA_ADMIN} présent ?)"
gapi() { # gapi <METHOD> <path> [data]
    kubectl -n "${GITEA_NS}" exec "${gitea_pod}" -- curl -sS \
        -X "$1" -H "Authorization: token ${gitea_token}" -H "Content-Type: application/json" \
        "http://localhost:3000/api/v1/$2" ${3:+-d "$3"} 2>/dev/null
}

# ── 2. Le dépôt atlas sur la forge (idempotent, SANS auto-init : vraie histoire) ─
log "[1/4] dépôt ${GITEA_ADMIN}/${REPO} sur la forge"
if ! gapi GET "repos/${GITEA_ADMIN}/${REPO}" | grep -q '"full_name"'; then
    gapi POST "user/repos" "{\"name\":\"${REPO}\",\"auto_init\":false,\"default_branch\":\"main\"}" \
        | grep -q '"full_name"' || { log "✗ création du dépôt échouée"; exit 1; }
fi

# ── 3. LE geste : push du main revu vers la forge ───────────────────────────
# Un vrai `git push` du dépôt complet exige un endpoint git côté poste : port-forward
# scopé (l'API seule passe par le pod, mais pas un pack de ~10⁴ objets). On pousse
# depuis un MIROIR bare temporaire : aucun hook du poste, aucune mutation du checkout.
# `--force` : la forge est un MIROIR du main revu — l'épreuve converge même si elle
# porte un état d'essai antérieur (le geste réel, deploy.sh, reste fast-forward).
log "[2/4] push atlas@${short_sha} → forge (port-forward :${LOCAL_PORT})"
kubectl -n "${GITEA_NS}" port-forward "svc/gitea-http" "${LOCAL_PORT}:80" >/dev/null 2>&1 &
pf_pid=$!
PUSH_URL="http://${GITEA_ADMIN}:${gitea_token}@127.0.0.1:${LOCAL_PORT}/${GITEA_ADMIN}/${REPO}.git"
for _ in $(seq 1 20); do
    git ls-remote "${PUSH_URL}" >/dev/null 2>&1 && break
    sleep 1
done
git ls-remote "${PUSH_URL}" >/dev/null 2>&1 || { log "✗ forge injoignable via le port-forward"; exit 1; }
remote_main=$(git ls-remote "${PUSH_URL}" refs/heads/main 2>/dev/null | cut -f1)
if [ "${remote_main}" = "${SHA}" ]; then
    log "  forge déjà à ${short_sha} (pas d'événement push) — on valide l'état livré"
else
    MIRROR=$(mktemp -d "${TMPDIR:-/tmp}/sc36-atlas-XXXXXX")
    git clone --quiet --mirror "${ATLAS_DIR}" "${MIRROR}/atlas.git"
    git -C "${MIRROR}/atlas.git" push --quiet --force "${PUSH_URL}" "${SHA}:refs/heads/main" \
        || { log "✗ push vers la forge échoué"; exit 1; }
    log "✓ main poussé (le workflow livraison prend la main)"
fi

# ── 4. L'usine livre : attendre `deploy` = main ⊕ digests ───────────────────
# Signal de COMPLÉTION : le write-back est la DERNIÈRE étape du workflow et signe son
# commit `deploy: main <sha12> ⊕ …` — on attend CE message. Échec rapide : la tâche
# Actions de NOTRE sha passe `failure`.
log "[3/4] l'usine builde ${nb_cls} code-location(s) puis matérialise deploy (max ${WAIT_CI_S}s)"
deploy_ok=''
elapsed=0
while [ "${elapsed}" -lt "${WAIT_CI_S}" ]; do
    deploy_msg=$(gapi GET "repos/${GITEA_ADMIN}/${REPO}/branches/deploy" 2>/dev/null \
        | grep -o '"message":"[^"]*"' | head -1 || true)
    case "${deploy_msg}" in *"main ${short_sha}"*) deploy_ok=1; break ;; esac
    task_status=$(gapi GET "repos/${GITEA_ADMIN}/${REPO}/actions/tasks" | tr '{' '\n' \
        | grep -m1 "\"head_sha\":\"${SHA}\"" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p' || true)
    if [ "${task_status}" = "failure" ]; then
        log "✗ run livraison en ÉCHEC pour ${short_sha} (voir Actions sur la forge)"
        exit 1
    fi
    sleep 10; elapsed=$((elapsed + 10))
done
[ -n "${deploy_ok}" ] || { log "✗ deploy non matérialisée pour ${short_sha} après ${WAIT_CI_S}s"; exit 1; }
log "✓ branche deploy au sommet « main ${short_sha} » — poussée PAR LE JOB :"
log "  DROIT DE PUSH DU TOKEN ACTIONS PROUVÉ (dernier prérequis d'usine du lot 2)"

# ── 5. La sortie doctrinale : digests + images + placeholders substitués ────
log "[4/4] vérification de la projection deploy (digests.env, registre, substitutions)"
digests=$(gapi GET "repos/${GITEA_ADMIN}/${REPO}/raw/.deploy/digests.env?ref=deploy")
nb_digests=$(printf '%s\n' "${digests}" | grep -c '=sha256:' || true)
[ "${nb_digests}" = "${nb_cls}" ] || {
    log "✗ .deploy/digests.env : ${nb_digests} digest(s) pour ${nb_cls} code-location(s)"
    exit 1
}
for d in ${CLS}; do
    cl="${d%-dagster}"
    digest=$(printf '%s\n' "${digests}" | sed -n "s/^${cl}=//p")
    [ -n "${digest}" ] || { log "✗ pas de digest pour ${cl} dans digests.env"; exit 1; }
    # L'image du sha livré est au registre interne (poussée par buildctl in-pod).
    tags=$(kubectl -n "${BUILDKIT_NS}" exec deploy/buildkitd -- \
        wget -T8 -qO- "http://${REGISTRY_FQDN}/v2/${d}/tags/list" 2>/dev/null || true)
    printf '%s' "${tags}" | grep -q "\"${short_sha}\"" \
        || { log "✗ image ${d}:${short_sha} absente du registre"; exit 1; }
    # Les placeholders de l'overlay prod sont substitués SUR deploy (et sur elle seule).
    kust=$(gapi GET "repos/${GITEA_ADMIN}/${REPO}/raw/dataops/${d}/deploy/overlays/prod/kustomization.yaml?ref=deploy")
    printf '%s' "${kust}" | grep -q "_IMAGE_DIGEST__" \
        && { log "✗ ${cl} : placeholder encore présent sur deploy"; exit 1; }
    printf '%s' "${kust}" | grep -q "${digest}" \
        || { log "✗ ${cl} : le digest de digests.env n'est pas dans l'overlay"; exit 1; }
    log "  ✓ ${cl} : image :${short_sha} au registre, overlay @${digest%%:*}:$(printf '%s' "${digest#sha256:}" | cut -c1-12)…"
done

log "🎉 LIVRAISON RÉELLE prouvée (ADR 0113/0104) : push atlas main → usine (runner →"
log "   buildctl → buildkitd in-pod, zéro egress) → ${nb_cls} image(s) @sha → deploy ="
log "   main ⊕ digests, placeholders substitués. Hors épreuve : la réconciliation Argo CD"
log "   des overlays prod (OBC/RGW) — terrain Ceph requis (verrou documenté au plan atlas)."
