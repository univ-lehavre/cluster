#!/usr/bin/env bash
#
# Orchestrateur du banc léger Lima — équivalent fonctionnel du banc Vagrant
# test/multi-node/, mais sur des VMs Lima (vrai noyau, SSH natif) au lieu de
# VirtualBox. Couvre les phases up → bootstrap → ceph → storageClasses.
#
# Chaque phase a un GATE : le script s'arrête (exit ≠ 0) si le critère de succès
# n'est pas atteint. Toutes les phases sont idempotentes (rejouables).
#
# À lancer depuis le POSTE DE CONTRÔLE (Mac), pas dans une VM.
#
# Usage :
#   test/lima/run-phases.sh up         # crée disques bruts + VMs + gate vd* présents
#   test/lima/run-phases.sh bootstrap  # bootstrap Ansible + Cilium + gate 3 nœuds Ready
#   test/lima/run-phases.sh ceph       # Rook-Ceph (metadataDevice=vde) + gate HEALTH_OK
#   test/lima/run-phases.sh sc         # StorageClasses + gate PVC Bound
#   test/lima/run-phases.sh all        # up → bootstrap → ceph → sc, arrêt au 1er gate rouge
#   test/lima/run-phases.sh kubeconfig # (ré)exporte le kubeconfig banc
#   test/lima/run-phases.sh down       # détruit les VMs + disques nommés
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

    # GATE 1 : exactement une SC default.
    local ndefault
    ndefault=$("${KUBECTL[@]}" get sc -o json \
        | python3 -c "import sys,json;print(sum(1 for i in json.load(sys.stdin)['items'] if i['metadata'].get('annotations',{}).get('storageclass.kubernetes.io/is-default-class')=='true'))")
    [ "${ndefault}" = "1" ] || die "il faut exactement 1 SC default, trouvé : ${ndefault}"
    ok "1 seule StorageClass default"

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

    # GATE 2 : PVC test → Bound.
    log "  PVC test (Bound ?)"
    "${KUBECTL[@]}" apply -f - <<'PVC'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: run-phases-test-pvc
  namespace: default
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 1Gi
PVC
    retry 120 5 pvc_bound \
        || die "PVC test pas Bound : $("${KUBECTL[@]}" -n default describe pvc run-phases-test-pvc | tail -10)"
    ok "PVC test Bound"
    "${KUBECTL[@]}" -n default delete pvc run-phases-test-pvc --wait=false
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
    ceph) phase_ceph ;;
    sc) phase_sc ;;
    kubeconfig) preflight; fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" ;;
    all)
        phase_up
        phase_bootstrap
        phase_ceph
        phase_sc
        log "🎉 Banc Lima validé : up → bootstrap → ceph → storageClasses."
        ;;
    down) phase_down ;;
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -40
        exit 2
        ;;
esac
