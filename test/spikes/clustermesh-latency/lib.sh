#!/usr/bin/env bash
#
# Constantes et helpers PROPRES au spike Cluster Mesh (sourcé par up/latency/
# probe/down). La plomberie Lima ↔ Ansible (VMs, disques, inventaire, bootstrap,
# kubeconfig, log/ok/die/retry) vient de la bibliothèque du banc Lima
# test/lima/lib.sh — source unique, pas de duplication (jscpd).
#
# MIGRATION kind → Lima (#128, ADR 0006 : kind abandonné). Les deux « sites » ne
# sont plus des clusters kind (conteneurs Docker) mais de VRAIES VMs Lima sur
# lesquelles le bootstrap Ansible monte K8s — même chemin que le banc et que la
# prod. `tc netem` se pose sur l'interface user-v2 de la VM (vraie pile réseau),
# pas via `docker exec`.

# Les constantes A_*/B_*/SPIKE_* ci-dessous sont consommées par les scripts qui
# SOURCENT ce fichier (up/probe/down/latency) → shellcheck ne voit pas leur usage.
# shellcheck disable=SC2034

# ── Banc Lima : plomberie partagée ───────────────────────────────────────────
SPIKE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=test/lima/lib.sh
. "${SPIKE_DIR}/../../lima/lib.sh"

# ── Identité des deux « sites » (VMs Lima + clusters K8s) ────────────────────
# cluster.id unique (1-255) ; cluster.name unique (≤32 car., alphanum minuscule
# + tirets) ; CIDR pods/services DISJOINTS — exigences Cilium Cluster Mesh,
# posées via le bootstrap paramétré (ADR 0025).
A_VM=site-a
B_VM=site-b
A_NAME=site-a
B_NAME=site-b
A_ID=1
B_ID=2
# CIDR disjoints (site A garde les défauts prod ; site B décalé d'un /16).
A_POD_CIDR=10.244.0.0/16
B_POD_CIDR=10.245.0.0/16
A_SVC_CIDR=10.96.0.0/12
B_SVC_CIDR=10.97.0.0/16
# Contextes kubectl (un kubeconfig par site, généré par up.sh — gitignorés).
A_CTX=spike-site-a
B_CTX=spike-site-b
# Ports hôte du forward de l'API de chaque site (127.0.0.1 ; distincts pour ne
# pas entrer en collision — 2 clusters mono-nœud tournent en parallèle).
A_API_PORT=6443
B_API_PORT=6444
# Ressources des VMs du spike (mono-nœud, pas de Ceph → moins que le banc).
SPIKE_CPUS=2
SPIKE_MEMORY=5GiB
SPIKE_DISK=20GiB

# Emplacements (gitignorés : artefacts de run, jamais versionnés).
WORKDIR="${SPIKE_DIR}/.work"
A_KUBECONFIG="${WORKDIR}/kubeconfig-site-a"
B_KUBECONFIG="${WORKDIR}/kubeconfig-site-b"

# ── Config Helm isolée (contourne un repositories.yaml incomplet côté hôte) ───
# cilium-cli embarque la lib Helm, qui charge TOUT le repositories.yaml de
# l'utilisateur et exige l'index de CHAQUE repo. Si un seul index manque,
# l'install échoue (« no cached repo found »). On isole donc cilium-cli sur une
# config Helm dédiée ne contenant que le repo cilium. (Le bootstrap pose Cilium
# DANS la VM ; côté hôte on n'utilise cilium-cli que pour le clustermesh.)
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
