#!/usr/bin/env bash
#
# Orchestrateur du banc léger Lima — équivalent fonctionnel du banc Vagrant
# test/multi-node/, mais sur des VMs Lima (vrai noyau, SSH natif) au lieu de
# VirtualBox. Stockage MODULAIRE : local-path (rapide) par défaut, Ceph optionnel.
#
# Chaque phase a un GATE : le script s'arrête (exit ≠ 0) si le critère de succès
# n'est pas atteint. Toutes les phases sont idempotentes (rejouables).
#
# À lancer depuis le POSTE DE CONTRÔLE (Mac), pas dans une VM.
#
# Usage :
#   test/lima/run-phases.sh up             # crée disques bruts + VMs + gate vd* présents
#   test/lima/run-phases.sh bootstrap      # bootstrap Ansible + Cilium + gate 3 nœuds Ready
#   test/lima/run-phases.sh storage-simple # local-path-provisioner (rapide) + gate PVC Bound
#   test/lima/run-phases.sh platform-prereqs # CRDs Gateway API + containerd insecure-registry
#   test/lima/run-phases.sh dataops-chain  # chaîne DataOps assemblée E2E (monitoring→CNPG→Dagster→Marquez) + lineage (#148)
#   test/lima/run-phases.sh ceph           # Rook-Ceph (metadataDevice=vde) + gate HEALTH_OK
#   test/lima/run-phases.sh sc             # StorageClasses Ceph + gate PVC Bound
#   test/lima/run-phases.sh all            # RAPIDE : up → bootstrap → storage-simple
#   WITH_CEPH=1 test/lima/run-phases.sh all  # COMPLET : ajoute ceph → sc (~15 min)
#   test/lima/run-phases.sh kubeconfig     # (ré)exporte le kubeconfig banc
#   test/lima/run-phases.sh down           # détruit les VMs + disques nommés
#
# Pré-requis poste : limactl (Lima ≥ 2.0), ansible-playbook, kubectl, python3.
#
# Pourquoi Lima (vs kind figé en 1.31 / Vagrant lourd) : ADR 0006.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/lima/lib.sh
. "${HERE}/lib.sh"

# ── Table des nœuds (noms génériques — ADR 0023) ─────────────────────────────
# "nom:rôle". 1 control-plane + 2 workers = quorum mon Ceph (3 nœuds) + ×3
# réplication. Tous nœuds de stockage (disques bruts attachés à chacun).
NODES=(
    "cp1:control"
    "node1:worker"
    "node2:worker"
)
CP=cp1 # nœud control-plane (kubeconfig + cni.sh)
# Port hôte du forward de l'API du control-plane (127.0.0.1:API_PORT → guest 6443).
API_PORT=6443

# Ressources par VM (5 GiB : cf. check k8s-pre-install real.total >= 4096 MB).
VM_CPUS=2
VM_MEMORY=5GiB
VM_DISK=20GiB

# CRDs Gateway API (alignées sur Cilium 1.19.x — ADR 0006 ; cf. platform/cilium-expo).
GWAPI_VERSION=1.4.1

# Disques Ceph par nœud : 3 HDD (data) + 1 block.db. Tailles fonctionnelles
# (pas perf), à l'image du banc Vagrant (3 × 10 GiB + 5 GiB).
HDD_COUNT=3
HDD_SIZE=10GiB
BLOCKDB_SIZE=5GiB

# ── Surcharges banc Ceph (Lima virtio-blk → /dev/vd*) ────────────────────────
# Lima présente ses disques en virtio-blk → /dev/vd* (contrairement au banc
# VirtualBox VirtioSCSI → /dev/sd*). state.sh documente ce chemin de surcharge.
# vda = OS ; vdb/vdc/vdd = HDD data ; vde = block.db ; vdf = cidata Lima
# (iso9660 monté, ignoré). On cible explicitement vd[b-e] (PAS vd[b-z]) pour
# exclure le disque cidata vdf de l'inventaire des disques bruts.
export CEPH_HDD_GLOB='/sys/block/vd[b-d]'
export CEPH_BLOCK_DEVICE=vde
export CEPH_MIN_HDD=3
export DATA_DEVICE_GLOB='/dev/vd[b-d]'
export NVME_BLOCK_DEVICE=/dev/vde

# ── Emplacements (gitignorés : artefacts de run) ─────────────────────────────
WORKDIR="${HERE}/.work"
INVENTORY="${WORKDIR}/inventory.yaml"
KUBECONFIG_LOCAL="${WORKDIR}/kubeconfig"
KUBECTL=(kubectl --kubeconfig "${KUBECONFIG_LOCAL}")

# Noms des disques nommés Lima d'un nœud (data hdd1..N + blockdb).
node_disks() {
    local vm=$1 i
    for i in $(seq 1 "${HDD_COUNT}"); do echo "${vm}-hdd${i}"; done
    echo "${vm}-blockdb"
}

# ── Prédicats pour retry (repris de multi-node) ──────────────────────────────
nodes_ready_3() { [ "$("${KUBECTL[@]}" get nodes --no-headers 2> /dev/null | grep -cw Ready)" -eq 3 ]; }
operator_ready() { [ "$("${KUBECTL[@]}" -n rook-ceph get deploy rook-ceph-operator -o jsonpath='{.status.readyReplicas}' 2> /dev/null)" = "1" ]; }
# Nombre d'OSD attendus = nœuds × disques data (3 × 3 = 9).
OSD_EXPECTED=$(( ${#NODES[@]} * HDD_COUNT ))
# HEALTH_OK SEUL est un faux-vert au démarrage : un cluster neuf SANS OSD ni pool
# rapporte HEALTH_OK (rien à dégrader). On exige donc AUSSI les OSD attendus up+in
# — c'est l'état réellement utilisable (les OSD montent sur les disques bruts vd*).
osds_up() { [ "$(toolbox_ceph osd stat 2> /dev/null | grep -oE '[0-9]+ up' | grep -oE '^[0-9]+')" = "${OSD_EXPECTED}" ]; }
# Cluster sain = OSD attendus up ET (HEALTH_OK OU un HEALTH_WARN dont le SEUL motif
# est le crash récent et bénin d'un module mgr — race de démarrage du module
# prometheus observée sur banc, qui se rétablit seule). On ignore donc
# RECENT_MGR_MODULE_CRASH mais aucune autre alerte.
ceph_health_ok_or_benign() {
    local codes
    codes=$(toolbox_ceph health detail --format json 2> /dev/null \
        | python3 -c "import sys,json;d=json.load(sys.stdin);print(' '.join(d.get('checks',{}).keys()))" 2> /dev/null) || return 1
    # Vide = HEALTH_OK ; sinon le seul code toléré est RECENT_MGR_MODULE_CRASH.
    [ -z "${codes}" ] || [ "${codes}" = "RECENT_MGR_MODULE_CRASH" ]
}
ceph_healthy() { osds_up && ceph_health_ok_or_benign; }
pvc_bound() { [ "$("${KUBECTL[@]}" -n default get pvc run-phases-test-pvc -o jsonpath='{.status.phase}' 2> /dev/null)" = "Bound" ]; }
toolbox_ceph() { "${KUBECTL[@]}" -n rook-ceph exec deploy/rook-ceph-tools -- ceph "$@"; }

preflight() {
    require_lima
    need ansible-playbook
    need kubectl
    need python3
}

# ── Stockage : helpers partagés (storage-simple ET ceph) ─────────────────────
# Marque UNE seule StorageClass `default` : pose l'annotation sur $1 et la retire
# de toutes les autres. Évite le gate « exactement 1 SC default » rouge quand
# plusieurs provisionneurs coexistent (ex. local-path + Ceph, ou un local-path
# résiduel — cf. drift #128).
set_default_sc() {
    local want=$1 sc
    for sc in $("${KUBECTL[@]}" get sc -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'); do
        if [ "${sc}" = "${want}" ]; then
            "${KUBECTL[@]}" patch sc "${sc}" -p \
                '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}' > /dev/null
        else
            "${KUBECTL[@]}" patch sc "${sc}" -p \
                '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"false"}}}' > /dev/null
        fi
    done
    local ndefault
    ndefault=$("${KUBECTL[@]}" get sc -o json \
        | python3 -c "import sys,json;print(sum(1 for i in json.load(sys.stdin)['items'] if i['metadata'].get('annotations',{}).get('storageclass.kubernetes.io/is-default-class')=='true'))")
    [ "${ndefault}" = "1" ] || die "il faut exactement 1 SC default, trouvé : ${ndefault}"
    ok "StorageClass default = ${want} (1 seule)"
}

# Gate commun : crée un PVC test sur la SC $1 (défaut si vide) et vérifie Bound.
gate_test_pvc() {
    local sc="${1:-}"
    log "  PVC test (Bound ?)"
    "${KUBECTL[@]}" apply -f - <<PVC
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: run-phases-test-pvc
  namespace: default
spec:
  accessModes: [ReadWriteOnce]
$([ -n "${sc}" ] && printf '  storageClassName: %s\n' "${sc}")
  resources:
    requests:
      storage: 1Gi
PVC
    # local-path est WaitForFirstConsumer → le PVC reste Pending sans consommateur.
    # On crée un pod éphémère qui le monte pour forcer le binding, puis on nettoie.
    "${KUBECTL[@]}" apply -f - <<'POD'
apiVersion: v1
kind: Pod
metadata:
  name: run-phases-test-pod
  namespace: default
spec:
  restartPolicy: Never
  containers:
    - name: pause
      image: registry.k8s.io/pause:3.10
      volumeMounts:
        - name: vol
          mountPath: /data
  volumes:
    - name: vol
      persistentVolumeClaim:
        claimName: run-phases-test-pvc
POD
    retry 120 5 pvc_bound \
        || die "PVC test pas Bound : $("${KUBECTL[@]}" -n default describe pvc run-phases-test-pvc | tail -10)"
    ok "PVC test Bound"
    "${KUBECTL[@]}" -n default delete pod run-phases-test-pod --wait=false > /dev/null 2>&1 || true
    "${KUBECTL[@]}" -n default delete pvc run-phases-test-pvc --wait=false > /dev/null 2>&1 || true
}

# ── Phase 0 — VMs Lima + disques bruts ───────────────────────────────────────
phase_up() {
    preflight
    log "Phase 0 — VMs Lima + disques bruts"
    mkdir -p "${WORKDIR}"
    local entry vm role
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        role="${entry##*:}"
        # Disques bruts (créés AVANT le start ; idempotent).
        local i
        for i in $(seq 1 "${HDD_COUNT}"); do
            lima_disk_create "${vm}-hdd${i}" "${HDD_SIZE}"
        done
        lima_disk_create "${vm}-blockdb" "${BLOCKDB_SIZE}"
        # Config VM rendue (additionalDisks ; portForward API pour le CP) puis start.
        local cfg="${WORKDIR}/${vm}.yaml" api_port=""
        [ "${role}" = control ] && api_port="${API_PORT}"
        lima_render_node "${cfg}" "${VM_CPUS}" "${VM_MEMORY}" "${VM_DISK}" "$(node_disks "${vm}")" "${api_port}"
        lima_start_node "${vm}" "${cfg}"
    done

    # GATE : disques data bruts présents (vdb) + block.db (vde) sur chaque nœud.
    # NB : `limactl shell <vm> '<cmd avec |>'` ne passe PAS par un shell → on
    # enveloppe dans `sh -c`. Lima attache aussi un disque cidata (vdf, iso9660,
    # monté) ignoré par Ceph (useAllDevices ne prend que les disques bruts) ; nos
    # surcharges ciblent vd[b-e] uniquement.
    log "Vérification des disques bruts (vdb..vde) sur chaque nœud"
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        vm_sh "${vm}" sh -c 'lsblk -dno NAME | grep -qx vdb' \
            || die "${vm} : disque data vdb absent (additionalDisks non attachés ?)"
        vm_sh "${vm}" sh -c 'lsblk -dno NAME | grep -qx vde' \
            || die "${vm} : disque block.db vde absent"
        ok "${vm} : disques bruts présents ($(vm_sh "${vm}" sh -c 'lsblk -dno NAME,SIZE | grep -E "^vd[b-e]" | tr "\n" " "'))"
    done
}

# ── Phases 1-2 — bootstrap K8s + Cilium ──────────────────────────────────────
phase_bootstrap() {
    preflight
    log "Phases 1-2 — bootstrap K8s + CNI"
    mkdir -p "${WORKDIR}"

    # Inventaire : control = CP, workers = le reste.
    local entry vm control="" workers=""
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        if [ "${entry##*:}" = control ]; then control="${control} ${vm}"; else workers="${workers} ${vm}"; fi
    done
    write_inventory "${INVENTORY}" "${control# }" "${workers# }"

    # control_plane_ip = IP user-v2 du CP (joignable depuis les workers ET l'hôte ;
    # pose /etc/hosts cluster-api + advertiseAddress kubeadm). Cluster UNIQUE →
    # PAS de pod_subnet/service_subnet (défauts prod conservés).
    local cp_ip
    cp_ip=$(vm_uservv2_ip "${CP}")
    [ -n "${cp_ip}" ] || die "${CP} : pas d'IP user-v2"
    ok "${CP} : IP user-v2 ${cp_ip}"

    bootstrap_node_sequence "${INVENTORY}" -e "control_plane_ip=${cp_ip}"
    run_cni "${CP}"
    fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}"

    # GATE : 3 nœuds Ready.
    log "Attente des 3 nœuds Ready (max 5 min)"
    retry 300 10 nodes_ready_3 \
        || die "moins de 3 nœuds Ready : $("${KUBECTL[@]}" get nodes 2>&1)"
    ok "3 nœuds Ready"
    "${KUBECTL[@]}" get nodes -o wide
}

# ── Phase storage-simple — local-path-provisioner (mode rapide, sans Ceph) ───
# Provisionneur de stockage simple (PVC sur disque local du nœud) pour itérer
# vite sur la couche applicative/plateforme sans payer les ~15 min de Ceph.
phase_storage_simple() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    log "Phase storage-simple — local-path-provisioner"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/local-path/local-path-storage.yaml"
    "${KUBECTL[@]}" -n local-path-storage rollout status deploy/local-path-provisioner --timeout=120s
    set_default_sc local-path
    gate_test_pvc local-path
}

# ── Phase platform-prereqs — pré-requis transverses de la couche plateforme ──
# Pose ce dont les addons plateforme ont besoin et que le bootstrap nu n'installe
# pas : (1) les CRDs Gateway API (cert-manager les exige car cni.sh active
# gatewayAPI ; Cilium ne les embarque pas — ADR 0006/0020) ; (2) la config
# containerd « insecure registry » sur chaque nœud pour le registry interne HTTP
# (registry:80, ADR 0011) — sinon ImagePullBackOff « HTTP response to HTTPS
# client » au pull des images applicatives.
phase_platform_prereqs() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"

    log "Phase platform-prereqs — CRDs Gateway API (v${GWAPI_VERSION})"
    local base="https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v${GWAPI_VERSION}/config/crd/standard"
    local crd
    for crd in gatewayclasses gateways httproutes referencegrants grpcroutes; do
        "${KUBECTL[@]}" apply -f "${base}/gateway.networking.k8s.io_${crd}.yaml" > /dev/null \
            || die "échec apply CRD Gateway API ${crd} (réseau ?)"
    done
    ok "CRDs Gateway API posées"

    log "Configuration containerd insecure-registry (registry:80 HTTP) sur chaque nœud"
    configure_insecure_registry
}

# Configure containerd pour tirer le registry interne HTTP (registry:80) : nom
# 'registry' résolu vers la ClusterIP (servie par Cilium eBPF) + hosts.toml HTTP.
# Idempotent. Restart containerd pour que le CRI relise certs.d.
configure_insecure_registry() {
    local reg_ip vm
    reg_ip=$("${KUBECTL[@]}" -n registry get svc registry -o jsonpath='{.spec.clusterIP}' 2> /dev/null)
    if [ -z "${reg_ip}" ]; then
        warn "Service registry/registry absent — déployer le registry interne d'abord (skip insecure-registry)"
        return 0
    fi
    local entry
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        # shellcheck disable=SC2016 # ${REG_IP} s'expanse DANS la VM (posé par `env`), pas localement
        vm_sh "${vm}" sudo env REG_IP="${reg_ip}" sh -c '
            grep -q " registry$" /etc/hosts || echo "${REG_IP} registry" >> /etc/hosts
            mkdir -p "/etc/containerd/certs.d/registry:80"
            cat > "/etc/containerd/certs.d/registry:80/hosts.toml" <<EOF
server = "http://registry:80"
[host."http://registry:80"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF
            systemctl restart containerd
        ' || die "${vm} : configuration insecure-registry échouée"
        ok "${vm} : registry:80 HTTP insecure configuré"
    done
}

# ── Phase 3 — Rook-Ceph ──────────────────────────────────────────────────────
phase_ceph() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    log "Phase 3 — Rook-Ceph (banc Lima : metadataDevice=vde)"

    # /var/lib/rook sur chaque nœud.
    local entry vm
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        vm_sh "${vm}" sh -c 'sudo mkdir -p /var/lib/rook && sudo chmod 755 /var/lib/rook'
    done

    # Manifeste cluster surchargé pour le banc (non committé). Deux surcharges :
    #  1. metadataDevice vde (block.db virtio-blk Lima, vs nvme1n1 en prod).
    #  2. osd.requests.memory 2Gi → 512Mi : sur banc 5 GiB/VM, 2Gi ne laisse
    #     scheduler qu'1 OSD/hôte → les autres restent Pending. 512Mi laisse
    #     monter les ~3 OSD/hôte. La valeur prod (2Gi) reste correcte — surcharge
    #     banc. L'awk ne touche QUE le bloc osd: (memory: '2Gi' apparaît aussi
    #     sous mon:).
    local cluster_bench="${WORKDIR}/cluster-bench.yaml"
    sed "s/metadataDevice: 'nvme1n1'/metadataDevice: 'vde'/" \
        "${REPO}/storage/ceph/cluster.yaml" \
        | awk '
            /^[[:space:]]*osd:[[:space:]]*$/ { in_osd = 1 }
            in_osd && /memory: .2Gi./ { sub(/2Gi/, "512Mi"); in_osd = 0 }
            { print }
          ' > "${cluster_bench}"
    grep -q "metadataDevice: 'vde'" "${cluster_bench}" || die "surcharge metadataDevice=vde non appliquée"
    grep -q "memory: '512Mi'" "${cluster_bench}" || die "surcharge osd.requests.memory=512Mi non appliquée"

    # SURCHARGE BANC : dé-épingler les images @sha256 (arm64). Les images Ceph
    # sont épinglées par DIGEST amd64 (corrects en prod x86_64). Sur ce banc
    # ARM64, l'image amd64 donne `exec format error`. On retombe sur le TAG
    # (multi-arch) côté banc UNIQUEMENT — le livrable garde son digest intact.
    undigest() { sed -E 's/(image:[[:space:]]*[^@[:space:]]+)@sha256:[0-9a-f]+/\1/'; }

    log "  apply crds → common → operator (images dé-épinglées pour arm64)"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/crds.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/common.yaml"
    undigest < "${REPO}/storage/ceph/operator.yaml" | "${KUBECTL[@]}" apply -f -
    retry 180 5 operator_ready || die "rook-ceph-operator pas Ready"
    ok "operator Ready"

    log "  apply cluster-bench.yaml + toolbox (images dé-épinglées pour arm64)"
    undigest < "${cluster_bench}" | "${KUBECTL[@]}" apply -f -
    undigest < "${REPO}/storage/ceph/toolbox.yaml" | "${KUBECTL[@]}" apply -f -

    # GATE : HEALTH_OK (peut prendre 5-15 min).
    log "Attente HEALTH_OK (max 20 min)"
    retry 1200 15 ceph_healthy \
        || die "Ceph pas HEALTH_OK : $(toolbox_ceph status 2>&1 | head -20)"
    ok "Ceph HEALTH_OK"
    toolbox_ceph status
    if "${KUBECTL[@]}" -n rook-ceph describe cephcluster 2> /dev/null | grep -qi 'no matches for kind'; then
        die "erreur CSI 'no matches for kind' — ROOK_USE_CSI_OPERATOR ?"
    fi
    ok "pas d'erreur CSI"
}

# ── Phase 4 — StorageClasses ─────────────────────────────────────────────────
phase_sc() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    log "Phase 4 — StorageClasses"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/block-replicated.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/block-ec-retain.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/block-ec-delete.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/filesystem/fs.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/filesystem/storageclass.yaml"

    # GATE 1 : Ceph block-replicated devient la SC default (1 seule).
    set_default_sc rook-ceph-block-replicated

    # PRÉ-CONDITION : la config CSI doit lister les monitors avant le PVC test
    # (sinon « empty monitor list » au premier run from-scratch).
    log "  Attente de la config CSI (monitors peuplés)"
    csi_monitors_ready() {
        "${KUBECTL[@]}" -n rook-ceph get cm rook-ceph-csi-config \
            -o jsonpath='{.data.csi-cluster-config-json}' 2> /dev/null \
            | grep -q '"monitors":\["'
    }
    retry 180 5 csi_monitors_ready \
        || die "config CSI sans monitors après 3 min (mons en quorum ?)"

    # GATE 2 : PVC test (Bound) sur la SC Ceph par défaut.
    gate_test_pvc rook-ceph-block-replicated
}

# ── Phase dataops-chain — chaîne DataOps assemblée E2E (#148) ─────────────────
# Déploie et VÉRIFIE la chaîne complète monitoring → CNPG → Dagster → Marquez, et
# prouve le maillon final : un VRAI run Dagster émet du lineage OpenLineage que
# Marquez ingère. Clôt l'épopée #148 (dette de validation systémique) : la chaîne
# n'était jamais testée ASSEMBLÉE. Chaque maillon a son gate `retry … || die`.
#
# Pré-requis : bootstrap fait, platform-prereqs posé (CRDs Gateway API +
# insecure-registry), registry interne déployé avec les images maison arm64
# (dagster, marquez, marquez-web, + image user-code de l'émetteur jetable).
#
# Surcharge arm64 : `undigest` retombe sur les tags multi-arch (cf. phase_ceph).
phase_dataops_chain() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    # shellcheck source=test/lima/dataops-assert.sh
    . "${HERE}/dataops-assert.sh"
    log "Phase dataops-chain — chaîne DataOps assemblée (monitoring → CNPG → Dagster → Marquez)"

    undigest() { sed -E 's/(image:[[:space:]]*[^@[:space:]]+)@sha256:[0-9a-f]+/\1/'; }

    # ── 1. Monitoring (kube-prometheus-stack + Loki + Mailpit) ───────────────
    log "  [1/5] Monitoring (kube-prometheus-stack + Loki + Mailpit)"
    undigest < "${REPO}/platform/kube-prometheus-stack/kube-prometheus-stack.yaml" 2>/dev/null \
        | "${KUBECTL[@]}" apply --server-side -f - >/dev/null 2>&1 || warn "monitoring : apply partiel (à compléter selon l'addon)"
    "${KUBECTL[@]}" apply -f "${REPO}/platform/mailpit/" >/dev/null 2>&1 || true
    monitoring_ready() { [ "$("${KUBECTL[@]}" -n mail get deploy mailpit -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]; }
    retry 300 10 monitoring_ready || warn "Mailpit non Ready (monitoring best-effort) — la chaîne DataOps continue"
    ok "monitoring posé (Mailpit gate best-effort)"

    # ── 2. CloudNativePG (operator + cluster pg + bases dagster/marquez) ─────
    log "  [2/5] CloudNativePG (cluster pg + bases dagster, marquez)"
    "${KUBECTL[@]}" apply --server-side -f "${REPO}/platform/cloudnative-pg/operator.yaml" >/dev/null
    retry 180 5 cnpg_operator_ready || die "CNPG operator pas Ready"
    "${KUBECTL[@]}" apply -f "${REPO}/platform/cloudnative-pg/cluster.yaml" >/dev/null
    "${KUBECTL[@]}" apply -f "${REPO}/platform/cloudnative-pg/database.yaml" >/dev/null
    retry 600 10 cnpg_cluster_healthy \
        || die "CNPG cluster pg pas sain : $("${KUBECTL[@]}" -n postgres get cluster pg -o jsonpath='{.status.phase}' 2>&1)"
    ok "CNPG : cluster pg sain, bases dagster+marquez créées"

    # ── 3. Dagster (orchestrateur, storage CNPG) ─────────────────────────────
    log "  [3/5] Dagster (webserver + daemon, storage CNPG)"
    "${KUBECTL[@]}" apply -f "${REPO}/platform/dagster/namespace.yaml" >/dev/null
    "${KUBECTL[@]}" apply -n dagster -f "${REPO}/platform/network-policies/dagster/" >/dev/null
    "${KUBECTL[@]}" apply -n dagster -f "${REPO}/platform/dagster/pg-secret.example.yaml" >/dev/null
    "${KUBECTL[@]}" apply -n dagster -f "${REPO}/platform/dagster/dagster.yaml" >/dev/null
    dagster_ready() {
        [ "$("${KUBECTL[@]}" -n dagster get deploy dagster-dagster-webserver -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ] \
            && [ "$("${KUBECTL[@]}" -n dagster get deploy dagster-daemon -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]
    }
    retry 300 10 dagster_ready || die "Dagster webserver/daemon pas Ready"
    ok "Dagster : webserver + daemon Ready"

    # ── 4. Marquez (API + web, store CNPG, Flyway) ───────────────────────────
    log "  [4/5] Marquez (API + web, store CNPG base marquez)"
    "${KUBECTL[@]}" apply -f "${REPO}/platform/marquez/namespace.yaml" >/dev/null
    "${KUBECTL[@]}" apply -n marquez -f "${REPO}/platform/network-policies/marquez/" >/dev/null
    "${KUBECTL[@]}" apply -n marquez -f "${REPO}/platform/marquez/pg-secret.example.yaml" >/dev/null
    "${KUBECTL[@]}" apply -n marquez -f "${REPO}/platform/marquez/marquez.yaml" >/dev/null
    marquez_ready() {
        [ "$("${KUBECTL[@]}" -n marquez get deploy marquez -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ] \
            && [ "$("${KUBECTL[@]}" -n marquez get deploy marquez-web -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]
    }
    retry 300 10 marquez_ready \
        || die "Marquez API/web pas Ready (Flyway ?) : $("${KUBECTL[@]}" -n marquez get pods 2>&1 | tail -5)"
    ok "Marquez : API + web Ready (migration Flyway OK)"

    # ── 5. Émetteur jetable : run Dagster réel → lineage OpenLineage → Marquez ─
    log "  [5/5] Émetteur jetable — run Dagster + sensor OpenLineage → ingestion Marquez"
    dataops_chain_emit_and_verify
    ok "🎉 chaîne DataOps assemblée validée — lineage d'un run Dagster réel visible dans Marquez"

    log "Consigner ce run dans test/lima/RESULTS.md (honnêteté des Runs, ADR 0023)."
}

# Prédicats CNPG réutilisés par la phase (purs côté décision via dataops-assert.sh).
cnpg_operator_ready() { [ "$("${KUBECTL[@]}" -n cnpg-system get deploy cnpg-controller-manager -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]; }
cnpg_cluster_healthy() {
    local phase verdict
    phase=$("${KUBECTL[@]}" -n postgres get cluster pg -o jsonpath='{.status.phase}' 2>/dev/null)
    verdict=$(classify_cnpg_health "${phase}")
    [ "${verdict%%|*}" = ok ]
}

# Déploie un émetteur OpenLineage jetable (asset jouet Dagster + sensor), lance un
# run réel, vérifie l'ingestion côté Marquez, puis retire l'émetteur. C'est la
# PREUVE de la vraie chaîne Dagster → OpenLineage → Marquez (cœur #148, pas un POST
# synthétique). L'image user-code (registry:80/dagster-openlineage-emit:dev) embarque
# dagster + openlineage-dagster + un asset trivial ; build/push documenté dans
# test/lima/RESULTS.md. Tant que l'image n'est pas poussée, ce maillon échoue
# explicitement (le harnais ne « verdit » pas à tort).
dataops_chain_emit_and_verify() {
    local ns=dagster ol_ns=dagster job_before job_after verdict
    # Compteur de jobs Marquez AVANT (delta = preuve d'ingestion).
    job_before=$(marquez_job_count "${ol_ns}")

    # L'émetteur jetable est un Job K8s qui matérialise un asset Dagster en process
    # local (sans passer par le webserver), sensor OpenLineage configuré par env :
    # OPENLINEAGE_URL pointe l'API Marquez interne. Image user-code maison.
    "${KUBECTL[@]}" -n "${ns}" apply -f - <<EMIT >/dev/null || die "émetteur jetable : apply échoué"
apiVersion: batch/v1
kind: Job
metadata:
  name: ol-emit-toy
  namespace: ${ns}
spec:
  backoffLimit: 1
  ttlSecondsAfterFinished: 600
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: emit
          image: registry:80/dagster-openlineage-emit:dev
          imagePullPolicy: IfNotPresent
          env:
            - name: OPENLINEAGE_URL
              value: "http://marquez.marquez.svc.cluster.local:5000"
            - name: OPENLINEAGE_ENDPOINT
              value: "api/v1/lineage"
            - name: OPENLINEAGE_NAMESPACE
              value: "${ol_ns}"
          # L'image embarque un asset trivial + le sensor openlineage-dagster ;
          # la commande matérialise l'asset, ce qui émet START/COMPLETE OpenLineage.
          command: ["dagster", "asset", "materialize", "--select", "*", "-m", "toy_assets"]
EMIT

    log "    attente de la complétion du run émetteur (max 5 min)…"
    emit_done() { [ "$("${KUBECTL[@]}" -n "${ns}" get job ol-emit-toy -o jsonpath='{.status.succeeded}' 2>/dev/null)" = "1" ]; }
    if ! retry 300 10 emit_done; then
        "${KUBECTL[@]}" -n "${ns}" logs job/ol-emit-toy 2>/dev/null | tail -20 || true
        die "émetteur jetable : le run Dagster n'a pas réussi (image registry:80/dagster-openlineage-emit:dev poussée ?)"
    fi

    # Vérifie l'ingestion côté Marquez (delta du compteur de jobs).
    log "    vérification de l'ingestion côté Marquez…"
    sleep 5 # laisse Marquez traiter l'événement COMPLETE
    job_after=$(marquez_job_count "${ol_ns}")
    verdict=$(classify_marquez_ingest "${job_before}" "${job_after}")
    case "${verdict%%|*}" in
        ok) ok "${verdict#*|}" ;;
        *) die "${verdict#*|} — sensor OpenLineage → API Marquez à vérifier" ;;
    esac

    # Teardown de l'émetteur jetable (l'orchestrateur livré reste VIDE).
    "${KUBECTL[@]}" -n "${ns}" delete job ol-emit-toy --wait=false >/dev/null 2>&1 || true
}

# Nombre de jobs visibles dans Marquez pour un namespace OpenLineage (via l'API,
# depuis un pod busybox éphémère). Renvoie un entier ou "?" (illisible).
marquez_job_count() {
    local ol_ns=$1 json
    json=$("${KUBECTL[@]}" -n marquez run marquez-count-$$ --rm -i --restart=Never \
        --image=busybox:1.36 --quiet -- \
        sh -c "wget -qO- 'http://marquez.marquez.svc.cluster.local:5000/api/v1/namespaces/${ol_ns}/jobs' 2>/dev/null" 2>/dev/null)
    parse_ol_job_count "${json}"
}

# ── Down — détruit VMs + disques nommés ──────────────────────────────────────
phase_down() {
    require_lima
    log "Destruction du banc Lima (VMs + disques nommés)"
    local entry vm d
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        lima_delete_node "${vm}"
        for d in $(node_disks "${vm}"); do
            lima_disk_delete "${d}"
        done
    done
    rm -rf "${WORKDIR}"
    ok "banc démonté — rien ne subsiste"
}

# ── Dispatch ─────────────────────────────────────────────────────────────────
case "${1:-}" in
    up) phase_up ;;
    bootstrap) phase_bootstrap ;;
    storage-simple) phase_storage_simple ;;
    platform-prereqs) phase_platform_prereqs ;;
    dataops-chain) phase_dataops_chain ;;
    ceph) phase_ceph ;;
    sc) phase_sc ;;
    kubeconfig) preflight; fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" ;;
    all)
        # Mode RAPIDE par défaut : stockage simple (local-path), sans Ceph.
        # WITH_CEPH=1 ajoute le stockage réel (Rook/Ceph + StorageClasses, ~15 min).
        phase_up
        phase_bootstrap
        if [ "${WITH_CEPH:-0}" = 1 ]; then
            phase_ceph
            phase_sc
            log "🎉 Banc Lima validé (mode Ceph) : up → bootstrap → ceph → storageClasses."
        else
            phase_storage_simple
            log "🎉 Banc Lima validé (mode rapide) : up → bootstrap → storage-simple."
            log "ℹ️  Pour le stockage réel : WITH_CEPH=1 $0 all  (ou : $0 ceph && $0 sc)"
        fi
        ;;
    down) phase_down ;;
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -40
        exit 2
        ;;
esac
