#!/usr/bin/env bash
#
# Monte le spike Cluster Mesh sur Lima : deux VMs (site-a, site-b), chacune un
# cluster K8s mono-nœud monté par le VRAI bootstrap Ansible (bootstrap/), avec
# une IDENTITÉ de cluster distincte (cluster.name/id + CIDR pods/services
# disjoints — ADR 0025), puis CA Cilium partagée et Cluster Mesh connecté.
# Idempotent : relançable, recrée seulement ce qui manque.
#
# Usage : ./up.sh
# Prérequis : limactl (Lima ≥ 2.0), ansible-playbook, cilium CLI, kubectl, helm.
#
# Remplace le montage kind d'origine (#128) : kind figeait K8s en 1.31 (ADR 0006)
# et n'était pas le chemin de la prod. Ici, le bootstrap qui tourne sur les VMs
# est EXACTEMENT celui de la prod — le spike valide donc aussi son paramétrage
# multi-cluster. La plomberie Lima ↔ Ansible vient de la lib du banc Lima
# (test/lima/lib.sh, sourcée par lib.sh) : pas de duplication.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/clustermesh-latency/lib.sh
. "${HERE}/lib.sh"

need limactl
need ansible-playbook
need cilium
need kubectl
need helm
require_lima
ensure_helm_repo # config Helm isolée (contourne un repositories.yaml incomplet)

mkdir -p "${WORKDIR}"

# ── Bootstrap d'un site : VM Lima → cluster K8s mono-nœud avec identité ───────
# Réutilise les primitives du banc Lima : rend la config VM (avec portForward API
# dédié), démarre, génère l'inventaire, déroule le bootstrap, pose Cilium avec
# l'identité de cluster (CILIUM_* — ADR 0025), exporte le kubeconfig. Le mesh
# EXIGE par site : cluster.name/id uniques + CIDR pods/services DISJOINTS.
bootstrap_site() {
    local vm=$1 cname=$2 cid=$3 pod_cidr=$4 svc_cidr=$5 api_port=$6 kubeconfig=$7 ctx=$8
    local cfg="${WORKDIR}/${vm}.yaml" inv="${WORKDIR}/inventory-${vm}.yaml"

    # VM mono-nœud (pas de disques Ceph) + forward API dédié (port distinct par
    # site → pas de collision sur 127.0.0.1 entre les 2 clusters).
    lima_render_node "${cfg}" "${SPIKE_CPUS}" "${SPIKE_MEMORY}" "${SPIKE_DISK}" "" "${api_port}"
    lima_start_node "${vm}" "${cfg}"

    local cp_ip
    cp_ip=$(vm_uservv2_ip "${vm}")
    [ -n "${cp_ip}" ] || die "${vm} : pas d'IP user-v2 (réseau 192.168.104.0/24)"
    ok "${vm} : IP user-v2 ${cp_ip}"

    # Inventaire mono-nœud (control = la VM, workers vide).
    write_inventory "${inv}" "${vm}" ""

    if vm_sh "${vm}" sudo test -f /etc/kubernetes/admin.conf 2> /dev/null; then
        ok "${vm} : cluster K8s déjà initialisé — skip bootstrap"
    else
        log "Bootstrap K8s sur ${vm} (cluster.name=${cname}, id=${cid}, pod=${pod_cidr})"
        # control_plane_ip = IP user-v2 ; pod/service subnet DISJOINTS (mesh).
        bootstrap_node_sequence "${inv}" \
            -e "control_plane_ip=${cp_ip}" \
            -e "pod_subnet=${pod_cidr}" \
            -e "service_subnet=${svc_cidr}"
        # Cilium via le VRAI cni.sh avec identité de cluster + podCIDR du site.
        run_cni "${vm}" \
            "CILIUM_CLUSTER_NAME=${cname}" \
            "CILIUM_CLUSTER_ID=${cid}" \
            "CILIUM_POD_CIDR=${pod_cidr}"
    fi

    fetch_kubeconfig_node "${vm}" "${kubeconfig}" "${api_port}" "${ctx}"
}

bootstrap_site "${A_VM}" "${A_NAME}" "${A_ID}" "${A_POD_CIDR}" "${A_SVC_CIDR}" \
    "${A_API_PORT}" "${A_KUBECONFIG}" "${A_CTX}"
bootstrap_site "${B_VM}" "${B_NAME}" "${B_ID}" "${B_POD_CIDR}" "${B_SVC_CIDR}" \
    "${B_API_PORT}" "${B_KUBECONFIG}" "${B_CTX}"

# Un seul KUBECONFIG fusionné pour piloter les deux contextes côté hôte.
export KUBECONFIG="${A_KUBECONFIG}:${B_KUBECONFIG}"

# ── CA Cilium partagée (mTLS inter-cluster) — AVANT le mesh ───────────────────
# site-b a généré SA propre CA à l'install → on la REMPLACE par celle de site-a.
# `replace --force` est le bon verbe (secret non géré déclarativement) et reste
# idempotent. Puis redémarrage des agents pour reprendre la CA commune.
log "Partage de la CA Cilium (site-a → site-b)"
ca_already_shared() {
    [ "$(kubectl --context "${A_CTX}" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.crt}')" \
       = "$(kubectl --context "${B_CTX}" -n kube-system get secret cilium-ca -o jsonpath='{.data.ca\.crt}' 2> /dev/null)" ]
}
if ca_already_shared; then
    ok "CA déjà partagée"
else
    kubectl --context "${A_CTX}" get secret -n kube-system cilium-ca -o yaml \
        | kubectl --context "${B_CTX}" -n kube-system replace --force -f -
    kubectl --context "${B_CTX}" -n kube-system rollout restart ds/cilium deploy/cilium-operator
    kubectl --context "${B_CTX}" -n kube-system rollout status ds/cilium --timeout=180s
    ok "CA partagée"
fi

# ── Activation + connexion du mesh ───────────────────────────────────────────
# Pas de LoadBalancer ici → service-type NodePort pour exposer le
# clustermesh-apiserver. Les deux VMs se joignent sur le réseau user-v2.
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
enable_mesh "${A_CTX}"
enable_mesh "${B_CTX}"

log "Connexion des deux clusters"
cilium clustermesh connect --context "${A_CTX}" --destination-context "${B_CTX}"

log "Attente de la convergence du mesh"
cilium clustermesh status --context "${A_CTX}" --wait
cilium clustermesh status --context "${B_CTX}" --wait
ok "Cluster Mesh établi entre ${A_NAME} et ${B_NAME}"

cat <<EOF

Mesh prêt. KUBECONFIG des deux sites :
  export KUBECONFIG="${A_KUBECONFIG}:${B_KUBECONFIG}"

Étapes suivantes :
  ./probe.sh            # déploie un service global et mesure le RTT inter-cluster
  ./latency.sh 50       # injecte 50 ms de latence entre les sites (dans les VMs)
  ./latency.sh clear    # retire la latence
  ./down.sh             # détruit les deux VMs Lima
EOF
