#!/usr/bin/env bash
#
# Orchestrateur de validation des phases 1-6 sur le banc multi-node Vagrant.
# À lancer depuis le POSTE DE CONTRÔLE (Mac), pas dans une VM.
#
# Chaque phase a un GATE : le script s'arrête (exit ≠ 0) si le critère de
# succès n'est pas atteint, pour ne pas enchaîner sur un état cassé. Toutes
# les phases sont idempotentes (rejouables).
#
# Surcharges BANC déjà câblées (vs prod) :
#   - metadataDevice: sde   (banc VirtioSCSI) au lieu de nvme1n1 (prod)
#   - CEPH_HDD_GLOB=/sys/block/sd[b-z], CEPH_BLOCK_DEVICE=sde (state.sh)
#   - kubeconfig récupéré depuis dirqual1 et réécrit sur l'IP privée du banc
#
# Usage :
#   test/multi-node/run-phases.sh up         # vagrant up + gate VMs/disques
#   test/multi-node/run-phases.sh bootstrap  # phases 1-2 (Ansible + Cilium) + gate nodes Ready
#   test/multi-node/run-phases.sh ceph       # phase 3 (Rook-Ceph) + gate HEALTH_OK
#   test/multi-node/run-phases.sh sc         # phase 4 (StorageClasses) + gate PVC Bound
#   test/multi-node/run-phases.sh workloads  # phase 5 (wordpress + datalake) + gate
#   test/multi-node/run-phases.sh etcd       # phase 6 (etcd-backup) + gate snapshot
#   test/multi-node/run-phases.sh all        # tout, dans l'ordre, en s'arrêtant au 1er gate rouge
#   test/multi-node/run-phases.sh kubeconfig # (ré)export le kubeconfig banc seulement
#
# Pré-requis poste : vagrant, VBoxManage, ansible-playbook, kubectl, ssh.
set -euo pipefail

# ── Constantes banc ───────────────────────────────────────────────────────
HERE=$(cd "$(dirname "$0")" && pwd)         # test/multi-node
REPO=$(cd "${HERE}/../.." && pwd)            # racine du repo
INVENTORY="${HERE}/inventory.yaml"
KUBECONFIG_LOCAL="${HERE}/.vagrant/kubeconfig"   # gitignoré (.vagrant/)
CP_IP=192.168.67.11                          # dirqual1 (control plane), réseau privé
NODES=(192.168.67.11 192.168.67.12 192.168.67.13)
SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
SSH_KEY="${HOME}/.vagrant.d/insecure_private_keys/vagrant.key.ed25519"

# Surcharges banc (devices sd* via VirtioSCSI ; block.db sde au lieu de
# nvme1n1 prod). Le contrôleur de la box bento/debian-13 est de type
# VirtioSCSI : il présente ses disques au noyau comme du SCSI (/dev/sd*),
# PAS comme du virtio-blk (/dev/vd*). L'OS est sur sda, les 4 disques Ceph
# sur sdb-sde — même schéma de nommage que la prod (HDD sd*), seul le
# block.db diffère (sde ici vs nvme1n1 en prod). Cf. RESULTS.md drift 0b.
# state.sh : détection des disques bruts (couche 3b).
export CEPH_HDD_GLOB='/sys/block/sd[b-z]'   # HDD data (jamais sda = OS)
export CEPH_BLOCK_DEVICE=sde                 # block.db (4e disque VirtioSCSI)
export CEPH_MIN_HDD=3
# cleanup.sh (si lancé à la main pour repartir à neuf) : mêmes devices.
# /dev/sd[b-z] exclut sda (OS) ; /dev/sde = block.db.
export DATA_DEVICE_GLOB='/dev/sd[b-z]'
export NVME_BLOCK_DEVICE=/dev/sde

KUBECTL=(kubectl --kubeconfig "${KUBECONFIG_LOCAL}")

# ── Helpers ─────────────────────────────────────────────────────────────────
log()  { printf '\n\033[1;36m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }
ok()   { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mGATE ÉCHOUÉ: %s\033[0m\n' "$*" >&2; exit 1; }
need() { command -v "$1" > /dev/null 2>&1 || die "outil requis absent : $1"; }

dssh() { ssh "${SSH_OPTS[@]}" -i "${SSH_KEY}" "debian@$1" "${@:2}"; }

# Prédicats pour retry (évitent les bash -c à quoting fragile)
nodes_ready_3()  { [ "$("${KUBECTL[@]}" get nodes --no-headers 2> /dev/null | grep -cw Ready)" -eq 3 ]; }
operator_ready() { [ "$("${KUBECTL[@]}" -n rook-ceph get deploy rook-ceph-operator -o jsonpath='{.status.readyReplicas}' 2> /dev/null)" = "1" ]; }
ceph_healthy()   { "${KUBECTL[@]}" -n rook-ceph exec deploy/rook-ceph-tools -- ceph health 2> /dev/null | grep -q HEALTH_OK; }
pvc_bound()      { [ "$("${KUBECTL[@]}" -n default get pvc run-phases-test-pvc -o jsonpath='{.status.phase}' 2> /dev/null)" = "Bound" ]; }
wp_running()     { "${KUBECTL[@]}" get pods -l app=wordpress --no-headers 2> /dev/null | grep -q Running; }

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

preflight() {
    need vagrant
    need VBoxManage
    need ansible-playbook
    need kubectl
    need ssh
    [ -f "${INVENTORY}" ] || die "inventaire absent : ${INVENTORY}"
}

# ── kubeconfig : récupère depuis dirqual1, réécrit sur l'IP privée ──────────
fetch_kubeconfig() {
    log "Récupération du kubeconfig depuis dirqual1 (${CP_IP})"
    mkdir -p "$(dirname "${KUBECONFIG_LOCAL}")"
    dssh "${CP_IP}" 'sudo cat /etc/kubernetes/admin.conf' > "${KUBECONFIG_LOCAL}" \
        || die "kubeconfig introuvable sur dirqual1 (bootstrap fait ?)"
    # Le admin.conf pointe sur l'endpoint cluster-api ; on force l'IP privée
    # joignable depuis le poste.
    sed -i.bak -E "s#server: https://[^:]+:6443#server: https://${CP_IP}:6443#" "${KUBECONFIG_LOCAL}"
    rm -f "${KUBECONFIG_LOCAL}.bak"
    chmod 600 "${KUBECONFIG_LOCAL}"
    "${KUBECTL[@]}" version -o yaml > /dev/null 2>&1 || die "kubectl ne joint pas l'API via ${KUBECONFIG_LOCAL}"
    ok "kubeconfig prêt : ${KUBECONFIG_LOCAL}"
}

toolbox_ceph() { "${KUBECTL[@]}" -n rook-ceph exec deploy/rook-ceph-tools -- ceph "$@"; }

# ── Phase 0 — vagrant up ────────────────────────────────────────────────────
phase_up() {
    preflight
    log "Phase 0 — vagrant up (3 VMs + disques)"
    if VBoxManage list hostonlyifs | grep -qE 'IPAddress:\s+10\.67\.'; then
        die "interface VBox host-only sur 10.67.x détectée — collision prod possible (cf. drift #6)"
    fi
    (cd "${HERE}" && vagrant up --provider=virtualbox)
    # GATE : 3 VMs running + disques bruts sd[bcd]+sde sans partition
    # (VirtioSCSI → /dev/sd* ; sda = OS, sdb-sde = disques Ceph attachés)
    for ip in "${NODES[@]}"; do
        dssh "${ip}" 'lsblk -dno NAME,TYPE | grep -q "^sdb"' || die "${ip} : disques data absents"
    done
    ok "3 VMs up, disques data présents"
    log "⏱️  Pense à : (cd ${HERE} && vagrant snapshot save 01-fresh-vms)"
}

# ── Phases 1-2 — bootstrap K8s + Cilium ─────────────────────────────────────
phase_bootstrap() {
    preflight
    log "Phases 1-2 — bootstrap K8s + CNI"
    for pb in upgrade checks cri kubeadm control-planes initialisation join-workers; do
        log "  ansible-playbook ${pb}.yaml"
        ansible-playbook -i "${INVENTORY}" "${REPO}/bootstrap/${pb}.yaml"
    done
    log "  Cilium (cni.sh sur dirqual1)"
    dssh "${CP_IP}" 'bash -s' < "${REPO}/bootstrap/cni.sh"
    fetch_kubeconfig
    # GATE : 3 nœuds Ready
    log "Attente des 3 nœuds Ready (max 5 min)"
    retry 300 10 nodes_ready_3 \
        || die "moins de 3 nœuds Ready : $("${KUBECTL[@]}" get nodes 2>&1)"
    ok "3 nœuds Ready"
    "${KUBECTL[@]}" get nodes -o wide
    log "⏱️  Snapshot conseillé : (cd ${HERE} && vagrant snapshot save 02-k8s-cni-ready)"
}

# ── Phase 3 — Rook-Ceph ─────────────────────────────────────────────────────
phase_ceph() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || fetch_kubeconfig
    log "Phase 3 — Rook-Ceph (banc : metadataDevice=sde)"

    # Pré-gate : disques bruts (state.sh couche 3b, surcharges banc exportées)
    log "  Vérif disques bruts (state.sh)"
    bash "${REPO}/bootstrap/state.sh" "${NODES[@]}" || true   # informatif, ne bloque pas seul

    # /var/lib/rook sur chaque nœud
    for ip in "${NODES[@]}"; do
        dssh "${ip}" 'sudo mkdir -p /var/lib/rook && sudo chmod 755 /var/lib/rook'
    done

    # Manifeste cluster surchargé pour le banc — non committé. Deux surcharges :
    #  1. metadataDevice sde (block.db VirtioSCSI, cf. #11)
    #  2. osd.requests.memory 2Gi → 512Mi : sur banc 5 GiB/VM, 2Gi ne laisse
    #     scheduler qu'1 OSD/hôte → les autres restent Pending (drift #10) et,
    #     avec tous les pools (block ×3 + EC + cephfs + RGW), le cluster sature
    #     en PGs et le peering se fige. 512Mi laisse monter les ~3 OSD/hôte. La
    #     valeur prod (2Gi, cluster.yaml) reste correcte — c'est une surcharge
    #     banc, comme le conseille le scénario 08. L'awk ne touche QUE le bloc
    #     osd: (memory: '2Gi' apparaît aussi sous mon:).
    local cluster_bench="${HERE}/.vagrant/cluster-bench.yaml"
    sed "s/metadataDevice: 'nvme1n1'/metadataDevice: 'sde'/" \
        "${REPO}/storage/ceph/cluster.yaml" \
        | awk '
            /^[[:space:]]*osd:[[:space:]]*$/ { in_osd = 1 }
            in_osd && /memory: .2Gi./ { sub(/2Gi/, "512Mi"); in_osd = 0 }
            { print }
          ' > "${cluster_bench}"
    grep -q "metadataDevice: 'sde'" "${cluster_bench}" || die "surcharge metadataDevice=sde non appliquée"
    grep -q "memory: '512Mi'" "${cluster_bench}" || die "surcharge osd.requests.memory=512Mi non appliquée"

    log "  apply crds → common → operator"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/crds.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/common.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/operator.yaml"
    retry 180 5 operator_ready \
        || die "rook-ceph-operator pas Ready"
    ok "operator Ready"

    log "  apply cluster-bench.yaml + toolbox"
    "${KUBECTL[@]}" apply -f "${cluster_bench}"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/toolbox.yaml"

    # GATE : HEALTH_OK (peut prendre 5-15 min)
    log "Attente HEALTH_OK (max 20 min)"
    retry 1200 15 ceph_healthy \
        || die "Ceph pas HEALTH_OK : $(toolbox_ceph status 2>&1 | head -20)"
    ok "Ceph HEALTH_OK"
    toolbox_ceph status
    # Garde-fou CSI : pas de 'no matches for kind'
    if "${KUBECTL[@]}" -n rook-ceph describe cephcluster 2> /dev/null | grep -qi 'no matches for kind'; then
        die "erreur CSI 'no matches for kind' — ROOK_USE_CSI_OPERATOR ?"
    fi
    ok "pas d'erreur CSI"
    log "⏱️  Snapshot conseillé : (cd ${HERE} && vagrant snapshot save 03-ceph-healthy)"
}

# ── Phase 4 — StorageClasses ────────────────────────────────────────────────
phase_sc() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || fetch_kubeconfig
    log "Phase 4 — StorageClasses"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/block-replicated.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/block-ec-retain.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/block-ec-delete.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/filesystem/fs.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/filesystem/storageclass.yaml"

    # GATE 1 : exactement une SC default
    local ndefault
    ndefault=$("${KUBECTL[@]}" get sc -o json \
        | python3 -c "import sys,json;print(sum(1 for i in json.load(sys.stdin)['items'] if i['metadata'].get('annotations',{}).get('storageclass.kubernetes.io/is-default-class')=='true'))")
    [ "${ndefault}" = "1" ] || die "il faut exactement 1 SC default, trouvé : ${ndefault}"
    ok "1 seule StorageClass default"

    # GATE 2 : PVC test → Bound
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
    log "⏱️  Snapshot conseillé : (cd ${HERE} && vagrant snapshot save 04-storageclasses)"
}

# ── Phase 5 — Workloads + datalake ──────────────────────────────────────────
phase_workloads() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || fetch_kubeconfig
    log "Phase 5 — Workloads (wordpress) + datalake"
    "${KUBECTL[@]}" create secret generic wordpress-secret \
        --from-literal=password='changeme' --dry-run=client -o yaml | "${KUBECTL[@]}" apply -f -
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/wordpress/mysql.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/wordpress/wordpress.yaml"

    # GATE : pods wordpress Running + PVC Bound
    log "Attente MySQL + WordPress Running (max 5 min)"
    retry 300 10 wp_running \
        || die "pods wordpress pas Running : $("${KUBECTL[@]}" get pods -l app=wordpress 2>&1)"
    ok "MySQL + WordPress Running (LoadBalancer restera Pending sur banc — attendu)"

    # Datalake : object store + users + OBCs
    log "  datalake : object store + users + OBC"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/datalake/datalake-ec.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/datalake/storage-class.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/datalake/user-datalake.yaml"
    for b in gdelt twitter reddit openalex stormglass; do
        "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/storageClass/datalake/object-bucket-claim-${b}.yaml"
    done
    log "  Smoke-test datalake S3 (via port-forward, peut prendre 1-2 min)"
    KUBECONFIG="${KUBECONFIG_LOCAL}" bash "${REPO}/storage/ceph/storageClass/datalake/smoke-test.sh" \
        || die "smoke-test datalake échoué"
    ok "Smoke-test datalake OK"
    log "Note : registry / rstudio / dashboard = accès port-forward seulement (pas de Tailscale sur banc)"
}

# ── Phase 6 — etcd-backup ───────────────────────────────────────────────────
phase_etcd() {
    preflight
    log "Phase 6 — etcd-backup (timer + snapshot)"
    ansible-playbook -i "${INVENTORY}" "${REPO}/bootstrap/etcd-backup.yaml"
    # GATE : run manuel du script → un .db produit
    dssh "${CP_IP}" 'sudo /usr/local/sbin/etcd-snapshot.sh'
    # /var/lib/etcd-backups est root:root 0700 : le `$(ls …)` doit AUSSI tourner
    # sous root, pas seulement le `test`. On enveloppe tout le pipeline dans
    # `sudo sh -c` (sinon le ls s'exécute en `debian` → Permission denied → la
    # substitution renvoie vide → faux négatif alors que le snapshot existe).
    # shellcheck disable=SC2016 # le $(...) doit s'évaluer côté distant sous root, pas localement
    dssh "${CP_IP}" 'sudo sh -c "test -s \"\$(ls -1t /var/lib/etcd-backups/etcd-*.db | head -1)\""' \
        || die "aucun snapshot etcd produit sur dirqual1"
    ok "Snapshot etcd produit"
    dssh "${CP_IP}" 'systemctl is-enabled etcd-snapshot.timer' \
        || die "timer etcd-snapshot non activé"
    ok "Timer etcd-snapshot activé"
    log "Restauration etcd : procédure manuelle — cf. bootstrap/RUNBOOK.md (faire sur snapshot Vagrant dédié)"
}

# ── Dispatch ────────────────────────────────────────────────────────────────
case "${1:-}" in
    up)         phase_up ;;
    bootstrap)  phase_bootstrap ;;
    ceph)       phase_ceph ;;
    sc)         phase_sc ;;
    workloads)  phase_workloads ;;
    etcd)       phase_etcd ;;
    kubeconfig) preflight; fetch_kubeconfig ;;
    all)        phase_up; phase_bootstrap; phase_ceph; phase_sc; phase_workloads; phase_etcd
                log "🎉 Phases 1-6 validées sur le banc." ;;
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -40
        exit 2
        ;;
esac
