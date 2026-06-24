#!/usr/bin/env bash
#
# Seed App-of-Apps EN PROD (ADR 0094) — pose le flux déclaratif citation.
#
# ════════════════════════════════════════════════════════════════════════════
#   ⚠  SCRIPT DANGEREUX — MUTE LA PROD (Gitea + Argo CD de dirqual).        ⚠
# ════════════════════════════════════════════════════════════════════════════
#
# RÔLE (ADR 0094 §2, README platform/argocd/app-of-apps/) : généralise en PROD
# le pattern de DONNÉES post-bootstrap de bench/lima/gitea-init.sh. Pose le flux
# App-of-Apps pour la code-location atlas `citation`, reproductiblement (ADR 0046
# — on code le chemin, on ne fait pas de geste manuel laissé en l'état) :
#
#   1. crée le repo Gitea `cluster/apps` (org cluster, repo apps) — l'état
#      déclaratif des Application installées (possédé par cluster) ;
#   2. pousse la déclaration d'Application `citation` (depuis le patron versionné
#      platform/argocd/app-of-apps/apps/citation.example.yaml) sous
#      apps/citation.yaml dans `cluster/apps`, en INJECTANT le repoURL atlas réel
#      + targetRevision (= SHA `revision` du manifeste de déclaration montant) ;
#   3. pousse le CODE citation atlas dans Gitea (repo atlas/atlas) à la révision
#      figée — l'Application fille pointe path=…/deploy/overlays/prod ;
#   4. crée/applique l'AppProject `cluster-apps` (privilège isolé : fabrique des
#      Application dans argocd, jamais du métier) — repoURL injecté ;
#   5. applique l'Application RACINE `cluster-apps` (surveille `cluster/apps`) —
#      repoURL Gitea `cluster/apps` injecté.
#
# CHOIX TECHNIQUES (documentés ici, pas dans un TODO — décisions structurantes) :
#
#   • EMPLACEMENT — bootstrap/ (PAS bench/lima/). bench/lima/ est le HARNAIS DE
#     BANC (Lima/arm64, jetable). Ici c'est de la PROD (dirqual). bootstrap/
#     porte déjà les scripts/playbooks prod (first-access.sh, cni.sh, state.sh,
#     gitops.yaml). C'est une étape de DONNÉES post-bootstrap (comme gitea-init.sh
#     l'est pour le banc), mais ciblant la prod → sa place est ici.
#
#   • ARBRE atlas : push GIT, PAS Contents API. Pour un fichier isolé
#     (apps/citation.yaml) la Contents API (create-or-update idempotent) est
#     idéale et reprise telle quelle. Pour le SOUS-ARBRE atlas (~68 fichiers sous
#     dataops/citation-dagster/, + le reste du dépôt), fichier-par-fichier serait
#     fragile (N appels, gestion des SHA, pas d'atomicité). On PRÉFÈRE un
#     `git push` depuis un CLONE temporaire du dépôt atlas figé à la révision.
#
#   • TOUT l'arbre atlas vs juste le sous-arbre. On pousse l'ARBRE COMPLET du
#     dépôt atlas à la révision (simple + robuste). Découper le sous-arbre
#     (git subtree / filter-repo) serait complexe et fragile pour zéro bénéfice :
#     l'Application fille ne LIT que path=dataops/citation-dagster/deploy/overlays
#     /prod de toute façon. CONTRAINTE respectée : l'arborescence
#     dataops/citation-dagster/deploy/… est préservée telle quelle (overlays/prod
#     référence ../../base — base + overlays/prod sont autonomes, vérifié, mais
#     l'ARBRE doit rester intact). On pousse la révision sur la branche `main` de
#     Gitea atlas/atlas (la branche que l'Application réconcilie via
#     targetRevision ; ici on ÉPINGLE le SHA dans targetRevision, donc le code
#     poussé DOIT contenir ce SHA — un push de la révision exacte le garantit).
#
#   • CREDENTIALS Gitea : lus/générés du Secret K8s `gitea-admin` (ns gitea),
#     EXACTEMENT comme gitea-init.sh (jamais en clair, jamais versionnés — valeur
#     de déploiement vivant dans le cluster, ADR 0023). Le `git push` HTTP utilise
#     ces creds via un remote `http://<user>:<pass>@127.0.0.1:<port>/…` injecté à
#     la volée (askpass), JAMAIS écrit sur disque ni loggé.
#
#   • PIÈGE DNS (crucial en prod dirqual) : les appels API Gitea tapent
#     localhost:3000 DANS le pod gitea (kubectl exec) — JAMAIS le FQDN
#     *.svc.cluster.local depuis l'hôte (un search domain externe + ndots:5 fait
#     timeouter le FQDN côté glibc/curl ; drift constaté dirqual). Idem le `git
#     push` : il passe par un `kubectl port-forward` vers svc/gitea-http (tunnel
#     k8s, pas de DNS cluster côté hôte), pas par le FQDN.
#
#   • repoURL injecté NON versionné (ADR 0023) : les patrons *.example.yaml ne
#     portent QUE des URLs d'exemple. Les URLs réelles (repo atlas Gitea, repo
#     cluster/apps Gitea) sont des VALEURS DE DÉPLOIEMENT injectées ici, jamais
#     gravées. Forme intra-cluster (gitea-http.gitea.svc.cluster.local) pour les
#     repoURL des Application (lus par argocd-repo-server, qui résout le DNS
#     cluster — lui, contrairement à l'hôte, est DANS le cluster).
#
# Orchestration de CLIs/API → bash (ADR 0017). Valeurs génériques surchargeables
# par env (ADR 0023). Idempotent (re-exécutable). set -euo pipefail, shellcheck.
#
# Usage :
#   bootstrap/seed-app-of-apps.sh            # plan + confirmation, puis exécute
#   bootstrap/seed-app-of-apps.sh --yes      # sans confirmation (CI / non-interactif)
#   bootstrap/seed-app-of-apps.sh --dry-run  # affiche le plan, NE MUTE RIEN
#
set -euo pipefail

# ── Sortie lisible (mêmes codes que bench/lima/lib.sh, mais script autonome) ──
log() { printf '\n\033[1;36m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }
ok() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die() {
    printf '\033[1;31mÉCHEC: %s\033[0m\n' "$*" >&2
    exit 1
}
need() { command -v "$1" > /dev/null 2>&1 || die "outil requis absent : $1"; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "${HERE}/.." && pwd)

# ── Paramètres (exemples génériques surchargeables, ADR 0023) ────────────────
# KUBECONFIG prod : par défaut ~/.kube/dirqual.config (endpoint dirqual1:6443).
# JAMAIS de fallback ~/.kube/config (qui pourrait pointer ailleurs) — on EXIGE
# que le contexte courant soit bien la prod (garde plus bas).
export KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/dirqual.config}"
# Nom de cluster ATTENDU dans le contexte kube courant (garde anti-mauvaise-cible).
EXPECTED_CLUSTER="${EXPECTED_CLUSTER:-cluster-prod}"

# Gitea (forge prod). org/repo des deux dépôts (apps déclaratif + code atlas).
GITEA_NS="${GITEA_NS:-gitea}"
GITEA_ORG_CLUSTER="${GITEA_ORG_CLUSTER:-cluster}" # org du repo déclaratif
GITEA_REPO_APPS="${GITEA_REPO_APPS:-apps}"        # repo déclaratif (Application)
GITEA_ORG_ATLAS="${GITEA_ORG_ATLAS:-atlas}"       # org du repo de code atlas
GITEA_REPO_ATLAS="${GITEA_REPO_ATLAS:-atlas}"     # repo de code atlas
GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-atlas-admin}"
GITEA_ADMIN_EMAIL="${GITEA_ADMIN_EMAIL:-atlas-admin@example-org.lan}"

ARGOCD_NS="${ARGOCD_NS:-argocd}"

# Service HTTP interne de Gitea (cf. platform/gitea/service.yaml). Sert au repoURL
# des Application (lu par argocd-repo-server → DNS cluster, résolvable depuis argocd).
GITEA_SVC="${GITEA_SVC:-http://gitea-http.gitea.svc.cluster.local}"
# Endpoint API : l'`api()` tourne via kubectl exec DANS le pod gitea (localhost:3000).
# Évite toute résolution DNS côté hôte (piège FQDN, cf. en-tête).
GITEA_API="${GITEA_API:-http://localhost:3000}"

# Dépôt atlas (code applicatif). EN PAUSE — lecture seule (NE PAS commit/modifier).
# On en fait un CLONE temporaire (scratchpad) figé à la révision, jamais de push
# DEPUIS le checkout de travail (qui pourrait être sale / sur une autre révision).
ATLAS_REPO_DIR="${ATLAS_REPO_DIR:-${REPO}/../atlas}"
# Révision figée du code citation à déployer (SHA `revision` du manifeste de
# déclaration montant atlas, ADR 0094 §3 — signal canonique d'évolution).
CITATION_REVISION="${CITATION_REVISION:-c98feea9}"

# Patrons versionnés *.example (ADR 0023) — source des manifestes rendus.
AOA_DIR="${REPO}/platform/argocd/app-of-apps"
CITATION_EXAMPLE="${AOA_DIR}/apps/citation.example.yaml"
APPPROJECT_EXAMPLE="${AOA_DIR}/appproject-cluster-apps.example.yaml"
ROOT_APP_EXAMPLE="${AOA_DIR}/root-application.example.yaml"

# Drapeaux d'exécution.
ASSUME_YES=0
DRY_RUN=0

# Répertoire temporaire (clone atlas + manifestes rendus). Nettoyé en sortie.
WORKDIR=""
PF_PID=""

# ── Parse des arguments ──────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --yes | -y) ASSUME_YES=1 ;;
        --dry-run | -n) DRY_RUN=1 ;;
        -h | --help)
            sed -n '/^# Usage :/,/^set -euo/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//; /^set -euo/d'
            exit 0
            ;;
        *) die "argument inconnu : $1 (voir --help)" ;;
    esac
    shift
done

# ── Nettoyage (port-forward + temp) à la sortie, quoi qu'il arrive ───────────
cleanup() {
    if [ -n "${PF_PID}" ] && kill -0 "${PF_PID}" 2> /dev/null; then
        kill "${PF_PID}" 2> /dev/null || true
        wait "${PF_PID}" 2> /dev/null || true
    fi
    [ -n "${WORKDIR}" ] && [ -d "${WORKDIR}" ] && rm -rf "${WORKDIR}"
}
trap cleanup EXIT INT TERM

# ── kubectl wrapper (KUBECONFIG déjà exporté) ────────────────────────────────
KUBECTL=(kubectl)

# Le pod gitea (un seul réplica, Recreate).
gitea_pod() {
    "${KUBECTL[@]}" -n "${GITEA_NS}" get pod -l app=gitea \
        -o jsonpath='{.items[0].metadata.name}' 2> /dev/null
}

# Exécute une commande `gitea`/`curl` DANS le pod gitea (réseau intra-cluster).
gitea_cli() {
    local pod
    pod=$(gitea_pod)
    [ -n "${pod}" ] || die "pod gitea introuvable (ns ${GITEA_NS})"
    "${KUBECTL[@]}" -n "${GITEA_NS}" exec "${pod}" -- "$@"
}

# Génère un secret aléatoire (jamais versionné, ADR 0023 — vit dans le cluster).
gen_secret() { head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32; }

# ════════════════════════════════════════════════════════════════════════════
# GARDE — ne JAMAIS muter une autre cible que la prod attendue (ADR 0046 : un
# geste dangereux exige une cible prouvée, pas un défaut implicite).
# ════════════════════════════════════════════════════════════════════════════
assert_prod_target() {
    log "Garde — vérification de la cible kube (prod attendue : ${EXPECTED_CLUSTER})"
    [ -r "${KUBECONFIG}" ] || die "KUBECONFIG illisible : ${KUBECONFIG}"

    local ctx cluster
    ctx=$("${KUBECTL[@]}" config current-context 2> /dev/null) \
        || die "aucun contexte kube courant (KUBECONFIG=${KUBECONFIG})"
    # Le NOM DE CLUSTER du contexte courant (pas le nom de contexte, plus stable).
    cluster=$("${KUBECTL[@]}" config view -o \
        "jsonpath={.contexts[?(@.name=='${ctx}')].context.cluster}" 2> /dev/null)
    [ "${cluster}" = "${EXPECTED_CLUSTER}" ] \
        || die "cible kube = cluster '${cluster}' (contexte '${ctx}'), attendu '${EXPECTED_CLUSTER}'. Refus de muter une mauvaise cible. Surcharger EXPECTED_CLUSTER si volontaire."
    ok "contexte '${ctx}' → cluster '${cluster}'"

    # dirqual répond ? (API joignable — pas juste un kubeconfig figé).
    "${KUBECTL[@]}" version -o json > /dev/null 2>&1 \
        || die "l'API Kubernetes ne répond pas (dirqual injoignable ?)"
    ok "API Kubernetes joignable"

    # Le pod gitea ET le namespace argocd existent (sinon le seed n'a pas de sens).
    [ -n "$(gitea_pod)" ] || die "pod gitea absent (ns ${GITEA_NS}) — Gitea posé ?"
    "${KUBECTL[@]}" get ns "${ARGOCD_NS}" > /dev/null 2>&1 \
        || die "namespace ${ARGOCD_NS} absent — Argo CD posé ?"
    ok "Gitea (pod) et Argo CD (ns ${ARGOCD_NS}) présents"
}

# ════════════════════════════════════════════════════════════════════════════
# PLAN — affiche ce qui va être fait + demande confirmation (sauf --yes).
# ════════════════════════════════════════════════════════════════════════════
print_plan() {
    local atlas_repo_url="${GITEA_SVC}/${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}.git"
    local apps_repo_url="${GITEA_SVC}/${GITEA_ORG_CLUSTER}/${GITEA_REPO_APPS}.git"
    cat << PLAN

  ┌──────────────────────────────────────────────────────────────────────────┐
  │  SEED APP-OF-APPS — PLAN (cible : ${EXPECTED_CLUSTER})
  └──────────────────────────────────────────────────────────────────────────┘

  Gestes MUTANTS qui vont s'exécuter sur la PROD :

   1. Gitea — org '${GITEA_ORG_CLUSTER}' + repo '${GITEA_ORG_CLUSTER}/${GITEA_REPO_APPS}'
      (déclaratif), créés si absents (idempotent).
   2. Gitea — org '${GITEA_ORG_ATLAS}' + repo '${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}'
      (code atlas), créés si absents (idempotent).
   3. git push — arbre complet du dépôt atlas figé à ${CITATION_REVISION}
      → ${apps_repo_url%/*/*}/${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}.git (branche main, via port-forward).
   4. Gitea Contents API — pousse apps/citation.yaml dans '${GITEA_ORG_CLUSTER}/${GITEA_REPO_APPS}',
      rendu depuis citation.example.yaml :
        repoURL        → ${atlas_repo_url}
        targetRevision → ${CITATION_REVISION}
   5. kubectl apply — AppProject 'cluster-apps' (sourceRepos injecté).
   6. kubectl apply — Application RACINE 'cluster-apps' :
        repoURL → ${apps_repo_url}

  KUBECONFIG : ${KUBECONFIG}
  Dépôt atlas (lecture seule, cloné en temp) : ${ATLAS_REPO_DIR}

PLAN
    if [ "${DRY_RUN}" = 1 ]; then
        warn "DRY-RUN — aucun geste mutant ne sera exécuté."
        return 0
    fi
    if [ "${ASSUME_YES}" = 1 ]; then
        warn "--yes — confirmation sautée."
        return 0
    fi
    printf '\033[1;33m  Confirmer l%cexecution sur la PROD ? [tapez "oui"] : \033[0m' "'"
    local answer
    read -r answer
    [ "${answer}" = "oui" ] || die "abandon (réponse : '${answer:-<vide>}')"
}

# ── Token API Gitea (admin créé/lu du Secret, comme gitea-init.sh) ───────────
# Pose la fonction globale api() (capturée par les étapes suivantes). Le token
# est local à cette fonction mais api() le ferme par closure bash.
TOKEN=""
ADMIN_PW=""
setup_gitea_admin_and_token() {
    log "Gitea — admin '${GITEA_ADMIN_USER}' + token API (idempotent)"
    # Mot de passe admin : généré et stocké dans un Secret K8s (jamais en clair).
    if ! "${KUBECTL[@]}" -n "${GITEA_NS}" get secret gitea-admin > /dev/null 2>&1; then
        local pw
        pw=$(gen_secret)
        "${KUBECTL[@]}" -n "${GITEA_NS}" create secret generic gitea-admin \
            --from-literal=username="${GITEA_ADMIN_USER}" \
            --from-literal=password="${pw}"
    fi
    ADMIN_PW=$("${KUBECTL[@]}" -n "${GITEA_NS}" get secret gitea-admin \
        -o jsonpath='{.data.password}' | base64 -d)
    # `gitea admin user create` échoue si l'utilisateur existe → idempotent.
    gitea_cli gitea admin user create \
        --username "${GITEA_ADMIN_USER}" --password "${ADMIN_PW}" \
        --email "${GITEA_ADMIN_EMAIL}" --admin --must-change-password=false \
        2>&1 | grep -v "user already exists" || true

    # Token : `--raw` n'affiche QUE la valeur ; nom unique par run (un nom déjà
    # pris ferait échouer la commande) → suffixe aléatoire.
    local token_name="seed-aoa-${RANDOM}"
    TOKEN=$(gitea_cli gitea admin user generate-access-token \
        --username "${GITEA_ADMIN_USER}" --token-name "${token_name}" \
        --scopes all --raw 2> /dev/null | tr -d '[:space:]') || true
    [ -n "${TOKEN}" ] || die "token API Gitea non obtenu"
    ok "admin + token API prêts"
}

# Helper API REST Gitea — appel DANS le pod (localhost:3000, pas de DNS hôte).
api() {
    local method=$1 path=$2 body=${3:-}
    local args=(-sS -X "${method}" -H "Authorization: token ${TOKEN}"
        -H "Content-Type: application/json" "${GITEA_API}/api/v1${path}")
    [ -n "${body}" ] && args+=(-d "${body}")
    gitea_cli curl "${args[@]}"
}

# Crée org + repo (auto_init main) — idempotent (|| true sur 422 déjà existant).
ensure_org_repo() {
    local org=$1 repo=$2
    api POST "/orgs" "{\"username\":\"${org}\"}" > /dev/null 2>&1 || true
    api POST "/orgs/${org}/repos" \
        "{\"name\":\"${repo}\",\"auto_init\":true,\"default_branch\":\"main\"}" \
        > /dev/null 2>&1 || true
}

# push_contents_file <org> <repo> <repo_path> <local_file> <message>
# Pousse UN fichier via la Contents API (create-or-update idempotent). Lit le SHA
# existant pour une MAJ ; VÉRIFIE la réponse (un PUT/POST raté laissait l'ancienne
# version → Argo CD déploierait un manifeste périmé : drift à NE PAS reproduire).
push_contents_file() {
    local org=$1 repo=$2 rpath=$3 lfile=$4 msg=$5
    local content sha payload resp
    content=$(base64 < "${lfile}" | tr -d '\n')
    sha=$(api GET "/repos/${org}/${repo}/contents/${rpath}" 2> /dev/null \
        | grep -oE '"sha":"[a-f0-9]+"' | head -1 | cut -d'"' -f4) || true
    if [ -n "${sha}" ]; then
        payload="{\"content\":\"${content}\",\"sha\":\"${sha}\",\"message\":\"${msg}\"}"
        resp=$(api PUT "/repos/${org}/${repo}/contents/${rpath}" "${payload}")
    else
        payload="{\"content\":\"${content}\",\"message\":\"${msg}\"}"
        resp=$(api POST "/repos/${org}/${repo}/contents/${rpath}" "${payload}")
    fi
    printf '%s' "${resp}" | grep -q '"commit"' \
        || die "push Contents API de ${rpath} ÉCHOUÉ — réponse: ${resp}"
}

# ════════════════════════════════════════════════════════════════════════════
# ÉTAPE 3 — push GIT de l'arbre atlas (révision figée) vers Gitea atlas/atlas.
# ════════════════════════════════════════════════════════════════════════════
push_atlas_tree() {
    log "atlas — push de l'arbre complet à ${CITATION_REVISION} → ${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}"

    [ -d "${ATLAS_REPO_DIR}/.git" ] \
        || die "dépôt atlas introuvable : ${ATLAS_REPO_DIR} (surcharger ATLAS_REPO_DIR)"
    # La révision DOIT exister dans le checkout atlas (sinon rien à pousser).
    git -C "${ATLAS_REPO_DIR}" cat-file -e "${CITATION_REVISION}^{commit}" 2> /dev/null \
        || die "révision ${CITATION_REVISION} absente du dépôt atlas (${ATLAS_REPO_DIR})"

    # CLONE temporaire figé : on NE pousse JAMAIS depuis le checkout de travail
    # atlas (en pause, lecture seule). Clone local (pas de réseau), puis on place
    # une branche `main` sur la révision exacte — c'est CE main que Gitea recevra,
    # et que l'Application réconcilie via targetRevision (qui épingle ce SHA).
    local clone="${WORKDIR}/atlas-clone"
    git clone --quiet --no-local "${ATLAS_REPO_DIR}" "${clone}" \
        || die "clone du dépôt atlas échoué"
    # --no-local force un vrai clone (objets copiés), donc la révision est présente
    # même si elle n'est pas sur une branche du checkout source.
    git -C "${clone}" branch -f main "${CITATION_REVISION}" \
        || die "impossible de placer main sur ${CITATION_REVISION}"
    git -C "${clone}" checkout --quiet main

    # Port-forward vers le Service ClusterIP gitea-http (tunnel k8s, PAS de DNS
    # cluster côté hôte → contourne le piège FQDN). Port local éphémère choisi
    # par kubectl (:3000 côté svc, 0 = port libre côté hôte).
    local pf_out lport
    pf_out=$(mktemp "${WORKDIR}/pf.XXXXXX")
    "${KUBECTL[@]}" -n "${GITEA_NS}" port-forward svc/gitea-http :3000 \
        > "${pf_out}" 2>&1 &
    PF_PID=$!
    # Attendre l'annonce du port local par kubectl (« Forwarding from 127.0.0.1:PORT »).
    local tries=0
    while [ "${tries}" -lt 50 ]; do
        lport=$(grep -oE '127\.0\.0\.1:[0-9]+' "${pf_out}" 2> /dev/null | head -1 | cut -d: -f2)
        [ -n "${lport}" ] && break
        kill -0 "${PF_PID}" 2> /dev/null || die "port-forward gitea-http mort : $(cat "${pf_out}")"
        tries=$((tries + 1))
        sleep 0.2
    done
    [ -n "${lport}" ] || die "port-forward gitea-http : port local non annoncé"
    ok "port-forward 127.0.0.1:${lport} → svc/gitea-http:3000"

    # askpass : fournit user+password au git push HTTP SANS écrire les creds dans
    # l'URL du remote (qui finirait dans .git/config / les logs). git appelle ce
    # helper pour « Username » puis « Password ». ADMIN_PW jamais loggé.
    local askpass="${WORKDIR}/askpass.sh"
    cat > "${askpass}" << 'ASKPASS'
#!/usr/bin/env bash
case "$1" in
    *[Uu]sername*) printf '%s' "${GIT_ASKPASS_USER}" ;;
    *[Pp]assword*) printf '%s' "${GIT_ASKPASS_PASS}" ;;
esac
ASKPASS
    chmod +x "${askpass}"

    local push_url="http://127.0.0.1:${lport}/${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}.git"
    # --force : Gitea a auto_init le repo (un commit README initial). On impose
    # l'arbre atlas figé comme `main` (l'historique d'auto_init n'a aucune valeur ;
    # le SHA épinglé dans targetRevision DOIT être la tête poussée). Idempotent :
    # un rejeu re-pousse le même SHA (no-op « up to date » ou fast-forward).
    GIT_ASKPASS="${askpass}" \
        GIT_ASKPASS_USER="${GITEA_ADMIN_USER}" \
        GIT_ASKPASS_PASS="${ADMIN_PW}" \
        GIT_TERMINAL_PROMPT=0 \
        git -C "${clone}" push --force "${push_url}" "main:main" \
        || die "git push de l'arbre atlas échoué (vers ${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS})"

    # Ferme le port-forward dès que le push est fini (cleanup le refera au pire).
    kill "${PF_PID}" 2> /dev/null || true
    wait "${PF_PID}" 2> /dev/null || true
    PF_PID=""
    ok "arbre atlas poussé (main = ${CITATION_REVISION})"
}

# ════════════════════════════════════════════════════════════════════════════
# ÉTAPE 4 — rendre + pousser apps/citation.yaml dans cluster/apps.
# ════════════════════════════════════════════════════════════════════════════
push_citation_declaration() {
    log "cluster/apps — rendu + push de apps/citation.yaml (repoURL/targetRevision injectés)"
    [ -r "${CITATION_EXAMPLE}" ] || die "patron introuvable : ${CITATION_EXAMPLE}"

    local atlas_repo_url="${GITEA_SVC}/${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}.git"
    local rendered="${WORKDIR}/citation.yaml"

    # Injection (ADR 0023) : on remplace les valeurs d'EXEMPLE du patron par les
    # valeurs de DÉPLOIEMENT. On NE remplace QUE les deux lignes ciblées :
    #   - repoURL: <…>        → repoURL atlas réel
    #   - targetRevision: <…> → SHA figé
    # On ancre sur l'indentation « 4 espaces » de spec.source.* pour ne pas
    # toucher d'autres champs. Le `path:` (overlays/prod) reste tel quel.
    sed -E \
        -e "s#^([[:space:]]{4})repoURL:.*#\\1repoURL: ${atlas_repo_url}#" \
        -e "s#^([[:space:]]{4})targetRevision:.*#\\1targetRevision: ${CITATION_REVISION}#" \
        "${CITATION_EXAMPLE}" > "${rendered}"

    # Garde anti-injection ratée : la sortie DOIT contenir les valeurs réelles.
    grep -q "repoURL: ${atlas_repo_url}" "${rendered}" \
        || die "injection repoURL ratée dans citation.yaml (motif sed non matché)"
    grep -q "targetRevision: ${CITATION_REVISION}" "${rendered}" \
        || die "injection targetRevision ratée dans citation.yaml"

    push_contents_file "${GITEA_ORG_CLUSTER}" "${GITEA_REPO_APPS}" \
        "apps/citation.yaml" "${rendered}" "seed: apps/citation.yaml (ADR 0094)"
    ok "apps/citation.yaml poussé dans ${GITEA_ORG_CLUSTER}/${GITEA_REPO_APPS}"
}

# ════════════════════════════════════════════════════════════════════════════
# ÉTAPE 5/6 — AppProject cluster-apps + Application racine (repoURL injectés).
# ════════════════════════════════════════════════════════════════════════════
apply_appproject_and_root() {
    local apps_repo_url="${GITEA_SVC}/${GITEA_ORG_CLUSTER}/${GITEA_REPO_APPS}.git"

    log "Argo CD — AppProject 'cluster-apps' (sourceRepos injecté)"
    [ -r "${APPPROJECT_EXAMPLE}" ] || die "patron introuvable : ${APPPROJECT_EXAMPLE}"
    # sourceRepos du patron = exemple générique (…/**). On le surcharge par l'URL
    # Gitea réelle de cluster/apps (la racine ne tire QUE ce repo). `/**` couvre
    # org/repo (le glob Argo CD ne traverse pas les `/`).
    local proj_src="${GITEA_SVC}/${GITEA_ORG_CLUSTER}/**"
    sed -E "s#^([[:space:]]+- )http://gitea-http\\.gitea\\.svc\\.cluster\\.local/\\*\\*#\\1${proj_src}#" \
        "${APPPROJECT_EXAMPLE}" > "${WORKDIR}/appproject-cluster-apps.yaml"
    grep -q "${proj_src}" "${WORKDIR}/appproject-cluster-apps.yaml" \
        || die "injection sourceRepos ratée dans l'AppProject"
    "${KUBECTL[@]}" apply -f "${WORKDIR}/appproject-cluster-apps.yaml" > /dev/null
    ok "AppProject cluster-apps appliqué"

    log "Argo CD — Application RACINE 'cluster-apps' (repoURL ${apps_repo_url})"
    [ -r "${ROOT_APP_EXAMPLE}" ] || die "patron introuvable : ${ROOT_APP_EXAMPLE}"
    # repoURL du patron = exemple (…/cluster/apps.git). On l'aligne sur l'instance.
    sed -E "s#^([[:space:]]{4})repoURL:.*#\\1repoURL: ${apps_repo_url}#" \
        "${ROOT_APP_EXAMPLE}" > "${WORKDIR}/root-application.yaml"
    grep -q "repoURL: ${apps_repo_url}" "${WORKDIR}/root-application.yaml" \
        || die "injection repoURL ratée dans l'Application racine"
    "${KUBECTL[@]}" apply -f "${WORKDIR}/root-application.yaml" > /dev/null
    ok "Application racine cluster-apps appliquée"
}

# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
main() {
    need kubectl
    need git
    need base64

    WORKDIR=$(mktemp -d "${TMPDIR:-/tmp}/seed-aoa.XXXXXX")

    assert_prod_target
    print_plan

    if [ "${DRY_RUN}" = 1 ]; then
        log "DRY-RUN terminé — rien n'a été muté."
        return 0
    fi

    setup_gitea_admin_and_token

    log "Gitea — org/repo '${GITEA_ORG_CLUSTER}/${GITEA_REPO_APPS}' (déclaratif, idempotent)"
    ensure_org_repo "${GITEA_ORG_CLUSTER}" "${GITEA_REPO_APPS}"
    ok "org/repo ${GITEA_ORG_CLUSTER}/${GITEA_REPO_APPS} prêt"

    log "Gitea — org/repo '${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}' (code atlas, idempotent)"
    ensure_org_repo "${GITEA_ORG_ATLAS}" "${GITEA_REPO_ATLAS}"
    ok "org/repo ${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS} prêt"

    push_atlas_tree
    push_citation_declaration
    apply_appproject_and_root

    log "OK — flux App-of-Apps posé en prod."
    cat << DONE
  Vérifier la réconciliation :
    KUBECONFIG=${KUBECONFIG} kubectl -n ${ARGOCD_NS} get application cluster-apps citation-dagster
    (attendu : cluster-apps Synced/Healthy → crée citation-dagster, qui réconcilie
     ${GITEA_ORG_ATLAS}/${GITEA_REPO_ATLAS}@${CITATION_REVISION} path=…/deploy/overlays/prod)
DONE
}

# Exécutable seul ou sourçable (tests).
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
