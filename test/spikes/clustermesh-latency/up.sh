#!/usr/bin/env bash
#
# Monte le spike Cluster Mesh : deux clusters kind légers (site-a, site-b)
# avec Cilium (KPR), CA partagée, puis mesh activé + connecté. Idempotent :
# relançable, recrée seulement ce qui manque.
#
# Usage : ./up.sh
# Prérequis : docker (démon lancé), kind, cilium CLI, kubectl.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/clustermesh-latency/lib.sh
. "${HERE}/lib.sh"

need kind
need cilium
need kubectl
need helm
require_docker
ensure_helm_repo # config Helm isolée (contourne un repositories.yaml incomplet)

# ── 1. Clusters kind (CIDR disjoints, CNI/kube-proxy off) ────────────────────
create_cluster() {
    local kname=$1 cfg=$2
    if kind get clusters 2> /dev/null | grep -qx "${kname}"; then
        ok "cluster kind '${kname}' déjà présent"
    else
        log "Création du cluster kind '${kname}'"
        kind create cluster --name "${kname}" --config "${HERE}/${cfg}"
        ok "cluster '${kname}' créé"
    fi
}
create_cluster "${C1_KIND}" kind-c1.yaml
create_cluster "${C2_KIND}" kind-c2.yaml

# ── 2. Cilium avec identité de cluster unique ────────────────────────────────
# cluster.name / cluster.id distincts (exigence mesh). KPR + tunnel VXLAN (même
# datapath mode des deux côtés). On NE réplique PAS toute la conf prod (WireGuard,
# Hubble, Gateway API) : spike minimal centré sur le mesh.
install_cilium() {
    local ctx=$1 name=$2 id=$3
    if cilium status --context "${ctx}" > /dev/null 2>&1; then
        ok "Cilium déjà installé sur ${ctx}"
    else
        log "Installation de Cilium sur ${ctx} (cluster.name=${name}, cluster.id=${id})"
        cilium install --context "${ctx}" --version "${CILIUM_VERSION}" \
            --set cluster.name="${name}" \
            --set cluster.id="${id}" \
            --set kubeProxyReplacement=true \
            --set ipam.mode=kubernetes
    fi
    log "Attente Cilium prêt sur ${ctx} (téléchargement d'images : patience)"
    cilium status --context "${ctx}" --wait --wait-duration 5m
    ok "Cilium opérationnel sur ${ctx}"
}
install_cilium "${C1_CTX}" "${C1_NAME}" "${C1_ID}"
install_cilium "${C2_CTX}" "${C2_NAME}" "${C2_ID}"

# ── 3. CA Cilium partagée (mTLS inter-cluster) — AVANT le mesh ───────────────
# Le secret cilium-ca de site-a est répliqué sur site-b ; Cilium y redémarre les
# agents pour reprendre la CA commune.
log "Partage de la CA Cilium (site-a → site-b)"
# c2 a généré SA propre CA à l'install → on la REMPLACE (replace --force) par
# celle de c1. `apply` échoue ici (secret non géré déclarativement + conflit de
# version) ; `replace --force` est le bon verbe et reste idempotent.
ca_already_shared() {
    [ "$(kubectl --context "${C1_CTX}" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.crt}')" \
       = "$(kubectl --context "${C2_CTX}" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.crt}' 2> /dev/null)" ]
}
if ca_already_shared; then
    ok "CA déjà partagée"
else
    kubectl --context "${C1_CTX}" get secret -n kube-system cilium-ca -o yaml \
        | kubectl --context "${C2_CTX}" -n kube-system replace --force -f -
    # Redémarrage pour reprendre la CA commune (identités mTLS).
    kubectl --context "${C2_CTX}" -n kube-system rollout restart ds/cilium deploy/cilium-operator
    kubectl --context "${C2_CTX}" -n kube-system rollout status ds/cilium --timeout=120s
    ok "CA partagée"
fi

# ── 4. Activation + connexion du mesh ────────────────────────────────────────
# kind n'a pas de LoadBalancer par défaut → service-type NodePort pour exposer
# le clustermesh-apiserver entre les deux conteneurs kind (même réseau Docker).
enable_mesh() {
    local ctx=$1
    if cilium clustermesh status --context "${ctx}" > /dev/null 2>&1; then
        ok "clustermesh déjà activé sur ${ctx}"
    else
        log "Activation du clustermesh sur ${ctx}"
        cilium clustermesh enable --context "${ctx}" --service-type NodePort
    fi
    cilium clustermesh status --context "${ctx}" --wait
}
enable_mesh "${C1_CTX}"
enable_mesh "${C2_CTX}"

log "Connexion des deux clusters"
cilium clustermesh connect --context "${C1_CTX}" --destination-context "${C2_CTX}"

log "Attente de la convergence du mesh"
cilium clustermesh status --context "${C1_CTX}" --wait
cilium clustermesh status --context "${C2_CTX}" --wait
ok "Cluster Mesh établi entre ${C1_NAME} et ${C2_NAME}"

cat <<EOF

Mesh prêt. Étapes suivantes :
  ./probe.sh            # déploie un service global et mesure le RTT inter-cluster
  ./latency.sh 50       # injecte 50 ms de latence entre les sites
  ./latency.sh clear    # retire la latence
  ./down.sh             # détruit les deux clusters
EOF
