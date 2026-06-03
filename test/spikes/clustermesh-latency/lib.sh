#!/usr/bin/env bash
#
# Constantes et helpers communs du spike Cluster Mesh (sourcé par up/latency/
# probe/down). Idiomes log/ok/die/need/retry repris de test/multi-node/run-phases.sh
# pour rester cohérent avec le banc existant.

# ── Identité des deux « sites » (clusters kind) ──────────────────────────────
# cluster.id doit être unique (1-255) ; cluster.name unique (≤32 car., alphanum
# minuscule + tirets) — exigences Cilium Cluster Mesh.
# shellcheck disable=SC2034 # consommées par les scripts qui sourcent lib.sh
C1_KIND=c1
C2_KIND=c2
C1_CTX=kind-c1
C2_CTX=kind-c2
C1_NAME=site-a
C2_NAME=site-b
C1_ID=1
C2_ID=2

# Version Cilium alignée sur la prod (bootstrap/cni.sh : CILIUM_VERSION=1.19.4).
CILIUM_VERSION="${CILIUM_VERSION:-1.19.4}"

# ── Config Helm isolée ───────────────────────────────────────────────────────
# cilium-cli embarque la lib Helm, qui charge TOUT le repositories.yaml de
# l'utilisateur et exige l'index de CHAQUE repo. Si un seul index manque (repo
# ajouté mais jamais `helm repo update`), l'install échoue avec
# « no cached repo found ». On isole donc cilium-cli sur une config Helm dédiée
# ne contenant que le repo cilium — la config Helm de l'utilisateur reste intacte.
SPIKE_HELM_DIR="${SPIKE_HELM_DIR:-${TMPDIR:-/tmp}/spike-helm}"
export HELM_REPOSITORY_CONFIG="${SPIKE_HELM_DIR}/repositories.yaml"
export HELM_REPOSITORY_CACHE="${SPIKE_HELM_DIR}/cache"

ensure_helm_repo() {
    mkdir -p "${SPIKE_HELM_DIR}/cache"
    if [ ! -f "${HELM_REPOSITORY_CONFIG}" ]; then
        cat > "${HELM_REPOSITORY_CONFIG}" <<'YAML'
apiVersion: ""
generated: "0001-01-01T00:00:00Z"
repositories:
- name: cilium
  url: https://helm.cilium.io/
  caFile: ""
  certFile: ""
  keyFile: ""
  username: ""
  password: ""
  insecure_skip_tls_verify: false
  pass_credentials_all: false
YAML
    fi
    if [ ! -f "${SPIKE_HELM_DIR}/cache/cilium-index.yaml" ]; then
        helm repo update cilium > /dev/null 2>&1 \
            || die "helm repo update cilium a échoué (réseau ?)"
    fi
}

# ── Helpers d'affichage (repris de run-phases.sh) ────────────────────────────
log() { printf '\n\033[1;36m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }
ok()  { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mÉCHEC: %s\033[0m\n' "$*" >&2; exit 1; }
need() { command -v "$1" > /dev/null 2>&1 || die "outil requis absent : $1"; }

# Boucle d'attente générique : retry <secondes_max> <intervalle> <cmd...>
retry() {
    local max=$1 itv=$2
    shift 2
    local waited=0
    until "$@"; do
        [ "${waited}" -ge "${max}" ] && return 1
        sleep "${itv}"
        waited=$((waited + itv))
    done
    return 0
}

# Garde-fou : Docker doit tourner (kind crée des nœuds-conteneurs).
require_docker() {
    need docker
    docker info > /dev/null 2>&1 || die \
        "démon Docker injoignable — lance Docker Desktop (open -a Docker) puis réessaie."
}

# Nom du conteneur kind du nœud control-plane d'un cluster (kind nomme
# <cluster>-control-plane). C'est là qu'on pose le tc netem.
node_container() { echo "${1}-control-plane"; }
