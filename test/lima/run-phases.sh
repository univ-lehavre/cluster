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
#   test/lima/run-phases.sh up             # VMs + (si WITH_CEPH=1) disques bruts + gate vd* (#235)
#   test/lima/run-phases.sh bootstrap      # bootstrap Ansible + Cilium + gate 3 nœuds Ready
#   BANC_JETABLE=1 [FAULT_TARGET=join|init|cri-keyring|cnpg-sc|argocd-netpol|addon] test/lima/run-phases.sh bootstrap-fault # arrêt injecté : preuve de reprise (ADR 0050/0052 §5) — DESTRUCTIF. compensation (join/init) ou reprise classe a (cri-keyring/cnpg-sc/argocd-netpol/addon)
#   test/lima/run-phases.sh storage-simple # local-path-provisioner (rapide) + gate PVC Bound
#   test/lima/run-phases.sh metrics-server # Metrics API (kubectl top) + gate APIService Available (#252)
#   test/lima/run-phases.sh platform-prereqs # CRDs Gateway API + containerd insecure-registry
#   test/lima/run-phases.sh ceph           # Rook-Ceph (metadataDevice=vde) + gate HEALTH_OK
#   test/lima/run-phases.sh sc             # StorageClasses Ceph + gate PVC Bound
#   test/lima/run-phases.sh datalake       # CephObjectStore RGW (cible S3 Barman) + gate Ready
#   test/lima/run-phases.sh smoke-s3       # smoke S3 PUT/GET/DELETE sur le RGW Ceph (scénario 06)
#   test/lima/run-phases.sh wordpress      # montage WordPress : PVC bloc RWO Ceph Bound + Pod Ready
#   test/lima/run-phases.sh hardening      # durcissement hôte (secure.yml, tags audit,detection — #240)
#   test/lima/run-phases.sh dataops        # chaîne DataOps via Ansible (dataops.yaml) + lineage (#173/#148)
#   test/lima/run-phases.sh gitops         # socle GitOps : Gitea + Argo CD via Ansible (gitops.yaml) + gate Ready (#230)
#   test/lima/run-phases.sh gitops-seed    # init dépôt Gitea : org/repo + workflow jouet + webhook + Application atlas (#231)
#   test/lima/run-phases.sh monitoring     # observabilité (Prometheus + Grafana + Loki), profil selon WITH_CEPH
#   ── Chemins d'installation nommés (ADR 0045) ──
#   test/lima/run-phases.sh socle          # up → bootstrap → stockage (smoke rapide)
#   test/lima/run-phases.sh atlas          # socle léger → metrics-server → monitoring → gitops → dataops → gitops-seed (banc atlas, local-path)
#   test/lima/run-phases.sh storage-real   # socle Ceph → datalake → smoke S3 (RGW) + montage WordPress (preuve stockage réel)
#   test/lima/run-phases.sh cluster-dataops # socle Ceph → datalake → monitoring → dataops (chaîne DataOps sur Ceph)
#   test/lima/run-phases.sh atlas-ceph     # banc atlas COMPLET sur Ceph : datalake → monitoring → gitops → dataops → gitops-seed + UI (#232)
#   ── Axe orthogonal durcissement (#240) : combinable avec tout chemin ──
#   WITH_HARDENING=1 test/lima/run-phases.sh atlas  # même chemin + secure.yml (audit,detection) après le socle
#   test/lima/run-phases.sh kubeconfig     # (ré)exporte le kubeconfig banc
#   test/lima/run-phases.sh status         # état du banc : VMs, nœuds, phases, UIs, dernier run (#149)
#   test/lima/run-phases.sh down           # détruit les VMs + disques nommés
#
# Pré-requis poste : limactl (Lima ≥ 2.0), ansible-playbook, kubectl, python3.
#
# Pourquoi Lima (vs kind figé en 1.31 / Vagrant lourd) : ADR 0006.
set -euo pipefail

# Intention de cible (ADR 0053 (c)) : ce script ne pilote QUE le banc Lima. On
# déclare l'intention `lima` pour TOUS les ansible-playbook lancés d'ici → le
# garde-fou du rôle audit-log refuse un inventaire prod passé par erreur.
export EXPECTED_TARGET_KIND=lima

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/lima/lib.sh
. "${HERE}/lib.sh"
# shellcheck source=test/lima/metrology.sh
. "${HERE}/metrology.sh"
# Lib PARTAGÉE du HEALTHCHECK cluster — MÊME source que bootstrap/state.sh. Les
# classify_* y sont PURES ; le banc collecte via "${KUBECTL[@]}" (kubectl
# --kubeconfig explicite, cible toujours sûre → pas de garde-fou de cible ici,
# ADR 0053) puis classe. Testée par test/unit/health-classify.bats.
# shellcheck source=bootstrap/lib/health-classify.sh
. "${REPO}/bootstrap/lib/health-classify.sh"

# ── Table des nœuds (noms génériques — ADR 0023) ─────────────────────────────
# "nom:rôle". Topologie `multi-node-3` : 1 control-plane + 2 workers = quorum mon
# Ceph (3 nœuds) + ×3 réplication. Tous nœuds de stockage (disques bruts attachés
# à chacun). C'est la SEULE topologie du banc local (ADR 0040 : single-node
# abandonné ; ha-3cp/multisite = cibles à outillage dédié, pas via ce harnais).
NODES=(
    "cp1:control"
    "node1:worker"
    "node2:worker"
)
CP=cp1 # nœud control-plane (kubeconfig + cni.sh)
# Port hôte du forward de l'API du control-plane (127.0.0.1:API_PORT → guest 6443).
API_PORT=6443

# Ressources par VM. RAM et DISQUE DÉRIVENT du profil (ADR 0046 : pas de valeur
# de profil codée en dur) :
#   - mode Ceph (WITH_CEPH=1) : 12 GiB RAM — un nœud porte OSD/mon Ceph + k8s +
#     CNPG + Dagster/Marquez + monitoring (chemin atlas-ceph). Pic mesuré ~9 GiB ;
#     Ceph sensible à la pression mémoire (OSD lents → boot/HEALTH qui traînent).
#   - mode léger (local-path) : 8 GiB RAM — suffit (drift L28 : pic de build
#     marquez-web arm64) sans gaspiller (banc atlas léger).
# 3×12 = 36 GiB sur un hôte 48 GiB : marge OK pour macOS. Surchargeable via VM_MEMORY.
#
# DISQUE : 20 GiB suffit en léger, mais le profil Ceph+dataops SATURE l'ephemeral-
# storage à 20 GiB (évictions postgres/rgw/exporter sous le seuil ~2 GiB — drift
# consigné). Ceph+dataops empile OSD + images applicatives + logs sur le rootfs.
# → 40 GiB en mode Ceph (qcow2 thin-provisionné : n'occupe le disque hôte qu'à
# l'usage réel). Surchargeable via VM_DISK.
VM_CPUS=2
VM_MEMORY_DEFAULT=$([ "${WITH_CEPH:-0}" = 1 ] && echo 12GiB || echo 8GiB)
VM_MEMORY=${VM_MEMORY:-${VM_MEMORY_DEFAULT}}
VM_DISK_DEFAULT=$([ "${WITH_CEPH:-0}" = 1 ] && echo 40GiB || echo 20GiB)
VM_DISK=${VM_DISK:-${VM_DISK_DEFAULT}}

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

# ── Métriques de run (matériel + temps par phase) ────────────────────────────
# Consignées dans WORKDIR/metrics.txt à reporter en en-tête du log archivé
# (test/lima/runs/, cf. RESULTS.md). Reproductible — pas de saisie manuelle.
METRICS="${WORKDIR}/metrics.txt"
# Durées par phase au format TSV (nom<TAB>secondes), consommé par metro_record_run
# pour bâtir l'entrée d'historique versionnée (#216). Éphémère (.work/).
PHASE_DURATIONS="${WORKDIR}/phase-durations.tsv"

# Émet l'en-tête matériel UNE fois par fichier de métriques (idempotent).
metrics_header() {
    mkdir -p "${WORKDIR}"
    [ -s "${METRICS}" ] && return 0
    {
        printf '# Run banc Lima — matériel & temps (généré par run-phases.sh)\n'
        printf 'host.model=%s\n' "$(sysctl -n hw.model 2> /dev/null || echo '?')"
        printf 'host.cpu=%s\n' "$(sysctl -n machdep.cpu.brand_string 2> /dev/null || echo '?')"
        printf 'host.cores=%s\n' "$(sysctl -n hw.ncpu 2> /dev/null || echo '?')"
        printf 'host.ram=%s\n' "$(sysctl -n hw.memsize 2> /dev/null | awk '{printf "%.0f GiB", $1/1073741824}')"
        printf 'host.os=macOS %s\n' "$(sw_vers -productVersion 2> /dev/null || echo '?')"
        printf 'host.lima=%s\n' "$(limactl --version 2> /dev/null | awk '{print $3}')"
        printf 'vm.cpus=%s vm.memory=%s\n' "${VM_CPUS}" "${VM_MEMORY}"
        printf '# phase\tdurée\n'
    } > "${METRICS}"
}

# Chronomètre une phase et journalise sa durée. Usage : time_phase <nom> <fn...>
time_phase() {
    local name=$1 start end dur rc
    shift
    metrics_header
    start=$(date +%s)
    "$@"
    rc=$?
    end=$(date +%s)
    dur=$((end - start))
    printf '%s\t%dm%02ds\n' "${name}" "$((dur / 60))" "$((dur % 60))" >> "${METRICS}"
    # Durée brute en secondes pour l'historique versionné (#216).
    printf '%s\t%d\n' "${name}" "${dur}" >> "${PHASE_DURATIONS}"
    log "⏱  phase ${name} : $((dur / 60))m$((dur % 60))s"
    return "${rc}"
}

# Consigne le run complet dans l'historique versionné (#216) et, si Prometheus
# est déployé, y joint les métriques de coût échantillonnées (#217). Appelé en
# fin d'un run de chemin réussi. <total_s> = durée cumulée ; <profil> dérivé de WITH_CEPH.
record_full_run() {
    local total=$1 profil block
    profil=$(metro_profil "${WITH_CEPH:-0}")
    # Échantillonnage Prometheus sur la fenêtre du run (best-effort, non bloquant).
    block=$(METRO_METRICS_BLOCK='' metro_sample_prometheus "${total}" || true)
    # TARGET (chemin nommé courant, suffixe +hardening inclus) consigné pour la
    # fraîcheur PAR CHEMIN (ADR 0045 §6 / #244).
    METRO_METRICS_BLOCK="${block}" \
        metro_record_run "${profil}" "multi-node-3" "${total}" "${PHASE_DURATIONS}" "${TARGET:-}"
}

# Joue un playbook Ansible de plateforme (depuis l'hôte, kubeconfig banc) PUIS
# prouve son IDEMPOTENCE en le REJOUANT : un rôle idempotent doit donner
# `changed=0` au 2ᵉ passage (gate d'idempotence — décision « pas de Molecule, on
# prouve par le banc » ; attrape les changed_when:true fautifs, ADR 0051). Le
# verdict passe par la fonction PURE classify_idempotence (testée bats).
# Args : $1 = chemin du playbook (relatif à REPO), puis args -e supplémentaires.
run_ansible_phase() {
    local playbook=$1; shift
    # shellcheck source=test/lima/dataops-assert.sh
    . "${HERE}/dataops-assert.sh"
    # 1er passage : déploie (échec dur si le playbook échoue).
    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/${playbook}" -e dataops_k8s_host=localhost "$@" \
        || die "${playbook} : échec du déploiement"
    # 2e passage : rejeu pour prouver l'idempotence (capture le PLAY RECAP).
    log "  rejeu idempotence — ${playbook}"
    local recap changed verdict
    recap=$(KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/${playbook}" -e dataops_k8s_host=localhost "$@" 2>&1 | tail -20)
    changed=$(printf '%s\n' "${recap}" | parse_ansible_changed)
    verdict=$(classify_idempotence "${changed}")
    case "${verdict%%|*}" in
        ok) ok "${verdict#*|}" ;;
        skip) log "    ${verdict#*|}" ;;
        *) die "${verdict#*|}" ;;
    esac
}

# Noms des disques nommés Lima d'un nœud (data hdd1..N + blockdb).
node_disks() {
    local vm=$1 i
    for i in $(seq 1 "${HDD_COUNT}"); do echo "${vm}-hdd${i}"; done
    echo "${vm}-blockdb"
}

# ── Prédicats pour retry (repris de multi-node) ──────────────────────────────
# Gate générique : tous les nœuds attendus (${#NODES[@]}) sont Ready.
nodes_ready_all() { [ "$("${KUBECTL[@]}" get nodes --no-headers 2> /dev/null | grep -cw Ready)" -eq "${#NODES[@]}" ]; }
# (operator_ready : SUPPRIMÉ — le gate operator Ready est porté dans le rôle
#  platform-ceph-cluster, ADR 0049. Le diagnostic status garde osds_up/toolbox_ceph.)
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
# (set_default_sc : SUPPRIMÉ — le marquage « exactement 1 SC default » est porté
#  dans les rôles Ansible platform-local-path et platform-ceph-storageclasses,
#  ADR 0049. Anti-double-source.)

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
    # Disques bruts = SEULEMENT en mode Ceph (#235) : local-path provisionne sur
    # le filesystem du nœud (disque OS vda), Rook-Ceph est le seul à consommer
    # vdb/vdc/vdd (data) + vde (block.db). En mode léger on ne crée donc que le
    # disque OS — up/down plus rapides, pas de réservation disque inutile.
    local with_ceph="${WITH_CEPH:-0}"
    log "Phase 0 — VMs Lima$([ "${with_ceph}" = 1 ] && echo " + disques bruts (Ceph)" || echo " (local-path : disque OS seul)")"
    mkdir -p "${WORKDIR}"
    local entry vm role
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        role="${entry##*:}"
        local disks=""
        if [ "${with_ceph}" = 1 ]; then
            # Disques bruts (créés AVANT le start ; idempotent).
            local i
            for i in $(seq 1 "${HDD_COUNT}"); do
                lima_disk_create "${vm}-hdd${i}" "${HDD_SIZE}"
            done
            lima_disk_create "${vm}-blockdb" "${BLOCKDB_SIZE}"
            disks="$(node_disks "${vm}")"
        fi
        # Config VM rendue (additionalDisks SI Ceph ; portForward API pour le CP)
        # puis start. disks vide ⇒ lima_render_node n'écrit pas additionalDisks.
        local cfg="${WORKDIR}/${vm}.yaml" api_port=""
        [ "${role}" = control ] && api_port="${API_PORT}"
        lima_render_node "${cfg}" "${VM_CPUS}" "${VM_MEMORY}" "${VM_DISK}" "${disks}" "${api_port}"
        lima_start_node "${vm}" "${cfg}"
    done

    # GATE disques : SEULEMENT en mode Ceph (sans Ceph, aucun disque brut attendu).
    if [ "${with_ceph}" != 1 ]; then
        ok "mode local-path : pas de disque brut attendu (#235)"
        return 0
    fi
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

    # Exposition tout-Cilium (ADR 0020) : DÉRIVER la plage LB-IPAM et l'interface
    # L2 du réseau user-v2 réel du banc (pas de valeur codée en dur — ADR 0023).
    # Plage = .240-.250 du /24 des nœuds (hors DHCP) ; interface = NIC user-v2
    # détecté côté invité (Lima ne garantit pas le nom selon les versions).
    local lb_prefix l2_if
    lb_prefix=${cp_ip%.*}                       # ex. 192.168.104.1 → 192.168.104
    l2_if=$(vm_uservv2_iface "${CP}")
    [ -n "${l2_if}" ] || die "${CP} : interface user-v2 introuvable"
    ok "expo : LB-IPAM ${lb_prefix}.240-.250, L2 sur ${l2_if}"
    # CRDs Gateway API AVANT Cilium (drift L56) : l'operator les vérifie au boot.
    apply_gwapi_crds_in_vm "${CP}" "${GWAPI_VERSION}"
    run_cni "${CP}" \
        "LB_IPAM_RANGE_START=${lb_prefix}.240" \
        "LB_IPAM_RANGE_STOP=${lb_prefix}.250" \
        "L2_INTERFACE=${l2_if}"
    # Contexte nommé `cluster-banc` (ADR 0053 (b)) : tue l'homonymie kubeadm
    # (`kubernetes-admin@kubernetes`) qui ferait s'écraser banc et prod dans une
    # fusion KUBECONFIG=banc:prod. Étiquette générique (ADR 0023), pas une valeur
    # de déploiement. La prod reçoit son `cluster-prod` côté kubeadm (k8s-init).
    fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" cluster-banc

    # GATE : tous les nœuds attendus (${#NODES[@]}) Ready.
    log "Attente des ${#NODES[@]} nœud(s) Ready (max 5 min)"
    retry 300 10 nodes_ready_all \
        || die "moins de ${#NODES[@]} nœud(s) Ready : $("${KUBECTL[@]}" get nodes 2>&1)"
    ok "${#NODES[@]} nœud(s) Ready"
    "${KUBECTL[@]}" get nodes -o wide
}

# ── Phase bootstrap-fault — ARRÊT INJECTÉ : prouve le rescue (ADR 0050/0052 §5) ─
# Exerce le chemin de REPRISE d'un rôle à effet de bord non idempotent (init OU
# join) en INJECTANT une faute, puis vérifie le protocole opposable de la règle 5
# (ADR 0052) : 1er run ÉCHOUE → compensation `kubeadm reset` TRACÉE → re-jeu du
# MÊME chemin RÉUSSIT. Le verdict passe par la fonction PURE classify_compensation
# (testée bats, test/unit/bootstrap-fault.bats) — symétrique de run_ansible_phase.
#
# DESTRUCTIF : la faute injectée casse un nœud SAIN. À ne lancer que sur un banc
# JETABLE (garde BANC_JETABLE=1). Mode déterministe (ADR 0052 §3) : on retire le
# marqueur `creates:` d'une étape DÉJÀ acquise puis on rejoue → le rôle re-tente
# `kubeadm init/join` sur un demi-état réel → le rescue compense.
#
# Cible via FAULT_TARGET :
#   - `join` (1er worker, DÉFAUT) : le rescue `kubeadm reset` ne touche QUE le
#     worker → le control-plane et le cluster SURVIVENT, le kubeconfig banc reste
#     valide. Mode RECOMMANDÉ (preuve fidèle du rescue sans détruire le cluster).
#   - `init` (control-plane) : le rescue `kubeadm reset` DÉTRUIT etcd/le cluster ;
#     le re-jeu reconstruit tout, mais le kubeconfig banc devient invalide et les
#     phases suivantes cassent → réserver à un banc qu'on accepte de perdre.
# Joue un playbook depuis l'hôte (kubeconfig banc), renvoie son rc sur $1 (nameref
# via echo) — wrapper set+e/set -e pour capturer un échec sans planter le harnais.
_fault_play() {
    local pb=$1; shift
    set +e
    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/${pb}.yaml" "$@"
    local rc=$?
    set -e
    return "${rc}"
}

phase_bootstrap_fault() {
    preflight
    [ "${BANC_JETABLE:-0}" = 1 ] || die "phase bootstrap-fault DESTRUCTIVE (casse un nœud sain) — exiger BANC_JETABLE=1 sur un banc jetable"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    # shellcheck source=test/lima/bootstrap-fault-assert.sh
    . "${HERE}/bootstrap-fault-assert.sh"

    # DEUX familles d'arrêt injecté (doctrine ADR 0050) :
    #  - COMPENSATION (init|join) : étape à effet de bord NON idempotent → le 1er
    #    run échoue, le rescue COMPENSE (kubeadm reset), le re-jeu repart propre.
    #    Verdict classify_compensation (exige le reset tracé).
    #  - REPRISE classe (a) (cri-keyring|cnpg-sc|argocd-netpol|addon) : apply
    #    déclaratif / opérateur idempotent → le 1er run échoue, le SIMPLE RE-JEU
    #    reconverge SANS compensation. Verdict classify_redeploy_recovery (n'exige
    #    AUCUN reset — l'exiger serait un faux-échec, malhonnêteté ADR 0052).
    local target="${FAULT_TARGET:-join}"
    case "${target}" in
        init | join) _fault_compensation "${target}" ;;
        cri-keyring | cnpg-sc | argocd-netpol | addon) _fault_redeploy "${target}" ;;
        *) die "FAULT_TARGET inconnu : ${target} (init|join|cri-keyring|cnpg-sc|argocd-netpol|addon)" ;;
    esac
}

# Famille COMPENSATION (init|join) — preuve du rescue compensateur (ADR 0052 §5).
_fault_compensation() {
    local target=$1 pb vm marker home entry
    case "${target}" in
        init)
            pb=initialisation; vm="${CP}"
            marker=/etc/kubernetes/admin.conf ;;
        join)
            pb=join-workers
            for entry in "${NODES[@]}"; do
                [ "${entry##*:}" = control ] || { vm="${entry%%:*}"; break; }
            done
            [ -n "${vm:-}" ] || die "bootstrap-fault join : aucun worker dans NODES"
            # $HOME doit s'expandre DANS la VM (côté invité) → single-quote voulu.
            # shellcheck disable=SC2016
            home=$(vm_sh "${vm}" sh -c 'echo "$HOME"' | tr -d '\r')
            marker="${home}/node-joined.log" ;;
    esac

    log "Phase bootstrap-fault — arrêt injecté COMPENSATION sur '${target}' (${vm}), rescue ADR 0050"
    log "  injection : rm ${marker} sur ${vm} (l'étape ${target} re-tente sur un demi-état)"
    vm_sh "${vm}" sudo rm -f "${marker}" \
        || die "bootstrap-fault : échec de la suppression du marqueur ${marker}"

    log "  1er run ${pb}.yaml — DOIT échouer puis compenser (kubeadm reset)"
    local out1 first_rc reset_seen second_rc verdict
    set +e
    out1=$(KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/${pb}.yaml" 2>&1)
    first_rc=$?
    set -e
    printf '%s\n' "${out1}" | tail -25
    reset_seen=$(printf '%s\n' "${out1}" | parse_kubeadm_reset)
    log "  1er run : rc=${first_rc}, compensation tracée=${reset_seen}"

    log "  re-jeu ${pb}.yaml — DOIT réussir (le chemin repart propre)"
    _fault_play "${pb}"; second_rc=$?

    verdict=$(classify_compensation "${first_rc}" "${reset_seen}" "${second_rc}")
    case "${verdict%%|*}" in
        ok) ok "${verdict#*|}" ;;
        *) die "${verdict#*|}" ;;
    esac
}

# Famille REPRISE classe (a) (cri-keyring|cnpg-sc|argocd-netpol|addon) — preuve
# qu'une étape idempotente (apply/opérateur) reconverge par SIMPLE RE-JEU après
# une faute, SANS compensation (ADR 0050 cas a / 0052 §5). Verdict
# classify_redeploy_recovery (1er échoue → re-jeu vert, n'exige aucun reset).
_fault_redeploy() {
    local target=$1 pb=() inject_desc gate_pred first_rc second_rc verdict
    case "${target}" in
        # CRI keyring : tronque le keyring k8s (marqueur menteur) → re-jeu kubeadm.yaml.
        # AVANT le fix, le re-jeu n'aurait pas réparé ; APRÈS, il re-valide+converge.
        cri-keyring)
            pb=(kubeadm)
            inject_desc="truncate keyring k8s sur ${CP}"
            vm_sh "${CP}" sudo truncate -s0 /etc/apt/keyrings/kubernetes-apt-keyring.gpg \
                || die "bootstrap-fault cri-keyring : échec truncate keyring"
            # le marqueur .valid doit aussi sauter, sinon le re-jeu croit acquis.
            vm_sh "${CP}" sudo rm -f /etc/apt/keyrings/.kubernetes-apt-keyring.valid || true
            gate_pred=cri_keyring_ok ;;
        # CNPG : SC bidon au 1er run → PVC Pending → gate santé expire → échec ;
        # re-jeu avec la vraie SC (dérivée de WITH_CEPH) → Cluster healthy.
        cnpg-sc)
            local good_sc; good_sc=$(ceph_default_sc_or_localpath)
            log "Phase bootstrap-fault — REPRISE cnpg-sc (SC bidon → ${good_sc})"
            log "  1er run dataops.yaml -e cnpg_storage_class=does-not-exist — DOIT échouer"
            _fault_play dataops -e cnpg_storage_class=does-not-exist; first_rc=$?
            log "  1er run : rc=${first_rc}"
            log "  re-jeu dataops.yaml -e cnpg_storage_class=${good_sc} — DOIT converger"
            _fault_play dataops -e "cnpg_storage_class=${good_sc}"; second_rc=$?
            verdict=$(classify_redeploy_recovery "${first_rc}" "${second_rc}" "")
            case "${verdict%%|*}" in ok) ok "${verdict#*|}" ;; *) die "${verdict#*|}" ;; esac
            return 0 ;;
        # argocd : supprime une NetworkPolicy allow pendant la convergence →
        # argocd-server jamais Ready → le rescue DIAGNOSTIQUE existant se déclenche.
        argocd-netpol)
            inject_desc="delete netpol allow-server-ingress (argocd)"
            "${KUBECTL[@]}" -n argocd delete networkpolicy allow-server-ingress --ignore-not-found >/dev/null 2>&1 || true
            pb=(gitops)
            gate_pred=argocd_server_ready ;;
        # addon générique : supprime le Deployment metrics-server pendant le wait.
        addon)
            inject_desc="delete deploy metrics-server"
            "${KUBECTL[@]}" -n kube-system delete deploy metrics-server --ignore-not-found >/dev/null 2>&1 || true
            pb=(metrics-server)
            gate_pred=metrics_server_ready ;;
    esac

    log "Phase bootstrap-fault — arrêt injecté REPRISE sur '${target}' : ${inject_desc}"
    log "  1er run ${pb[0]}.yaml après injection — peut échouer (faute prise)"
    _fault_play "${pb[0]}"; first_rc=$?
    log "  1er run : rc=${first_rc}"
    log "  re-jeu ${pb[0]}.yaml — DOIT reconverger (sans compensation)"
    _fault_play "${pb[0]}"; second_rc=$?

    verdict=$(classify_redeploy_recovery "${first_rc}" "${second_rc}" "")
    case "${verdict%%|*}" in ok) ok "${verdict#*|}" ;; *) die "${verdict#*|}" ;; esac
    # Gate finale d'état (au-delà du rc) : la composante visée est saine.
    if [ -n "${gate_pred:-}" ]; then
        if retry 120 10 "${gate_pred}"; then
            ok "gate de reprise OK (${gate_pred})"
        else
            die "gate de reprise ÉCHOUÉE (${gate_pred}) — reconvergence incomplète"
        fi
    fi
}

# Prédicats de gate de reprise (lecture seule).
cri_keyring_ok() { vm_sh "${CP}" sh -c 'sudo gpg --show-keys /etc/apt/keyrings/kubernetes-apt-keyring.gpg >/dev/null 2>&1 && sudo apt-cache policy kubeadm 2>/dev/null | grep -q pkgs.k8s.io'; }
argocd_server_ready() { [ "$("${KUBECTL[@]}" -n argocd get deploy argocd-server -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = 1 ]; }
metrics_server_ready() { [ "$("${KUBECTL[@]}" -n kube-system get deploy metrics-server -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = 1 ]; }
# SC par défaut selon le profil (Ceph → block-replicated ; léger → local-path).
ceph_default_sc_or_localpath() { [ "${WITH_CEPH:-0}" = 1 ] && echo rook-ceph-block-replicated || echo local-path; }

# ── Phase storage-simple — local-path-provisioner (mode rapide, sans Ceph) ───
# Provisionneur de stockage simple (PVC sur disque local du nœud) pour itérer
# vite sur la couche applicative/plateforme sans payer les ~15 min de Ceph.
phase_storage_simple() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase storage-simple — local-path-provisioner via Ansible"
    # PORTÉ EN RÔLE ANSIBLE (platform-local-path) : apply du manifeste figé +
    # StorageClass default (exactement 1) dans le rôle ; anti-double-source (plus
    # de kubectl apply / set_default_sc shell ici). gate_test_pvc reste un TEST.
    run_ansible_phase bootstrap/local-path.yaml
    gate_test_pvc local-path
}

# ── Phase metrics-server — Metrics API (kubectl top) ─────────────────────────
# Palier 1 AUTONOME (ADR 0016, #252) : pas de dépendance Prometheus. Sans cette
# brique, `kubectl top nodes/pods` renvoie « Metrics API not available » — un
# développeur atlas qui consomme le banc n'a aucune visibilité usage CPU/RAM.
# PORTÉ EN RÔLE ANSIBLE (platform-metrics-server, ADR 0033/0049) : le manifeste
# figé n'est plus appliqué en kubectl shell ici mais par le playbook, qui gate
# sur l'APIService agrégée Available:True (kubectl top opérant) — et le rejeu
# prouve l'idempotence. Anti-double-source : aucun kubectl d'apply dans la phase.
phase_metrics_server() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase metrics-server — Metrics API (kubectl top) via Ansible"
    run_ansible_phase bootstrap/metrics-server.yaml
    ok "Metrics API disponible — kubectl top nodes/pods opérant"
}

# ── Phase platform-prereqs — pré-requis transverses de la couche plateforme ──
# Pose ce dont les addons plateforme ont besoin et que le bootstrap nu n'installe
# pas : (1) les CRDs Gateway API — RÉAPPLIQUÉES ici par IDEMPOTENCE (la pose
# PRIMAIRE est désormais au bootstrap, AVANT cni.sh : l'operator Cilium les exige
# à son démarrage pour armer le contrôleur Gateway — drift L56, ADR 0006/0020) ;
# (2) la config containerd « insecure registry » sur chaque nœud pour le registry
# interne HTTP (registry:80, ADR 0011) — sinon ImagePullBackOff « HTTP response
# to HTTPS client » au pull des images applicatives.
phase_platform_prereqs() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"

    # Réapplication idempotente (posées au bootstrap avant Cilium — drift L56).
    log "Phase platform-prereqs — CRDs Gateway API (v${GWAPI_VERSION}, idempotent)"
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
    # `|| true` : sous `set -e`, l'assignation `x=$(cmd-qui-échoue)` tue le script.
    # Or sur le banc LÉGER (monitoring seul, sans dataops) le ns registry n'existe
    # pas → `kubectl get` sort en 1 (drift L40). On tolère l'échec et on skippe
    # proprement via le garde ci-dessous (le registry n'est requis que par dataops).
    reg_ip=$("${KUBECTL[@]}" -n registry get svc registry -o jsonpath='{.spec.clusterIP}' 2> /dev/null || true)
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
# Prépare un dossier de manifestes Ceph DÉ-ÉPINGLÉS pour le banc arm64 : les
# images Ceph sont épinglées par DIGEST amd64 (corrects en prod x86_64, ADR 0006)
# → `exec format error` sur ce banc ARM64. On retombe sur le TAG multi-arch côté
# banc UNIQUEMENT (le livrable garde ses digests intacts — surcharge HARNAIS, pas
# le rôle). Renvoie le chemin du dossier dé-épinglé. Idempotent (refait à chaque
# run, peu coûteux). Drift Ceph arm64 du banc.
ceph_undigest_manifests() {
    local out="${WORKDIR}/ceph-undigest"
    mkdir -p "${out}/storageClass/datalake" "${out}/storageClass/filesystem"
    local f
    for f in crds common operator cluster toolbox; do
        sed -E 's/(image:[[:space:]]*[^@[:space:]]+)@sha256:[0-9a-f]+/\1/' \
            "${REPO}/storage/ceph/${f}.yaml" > "${out}/${f}.yaml"
    done
    printf '%s' "${out}"
}

phase_ceph() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase 3 — Rook-Ceph via Ansible (banc Lima : metadataDevice=vde, OSD 512Mi)"

    # /var/lib/rook sur chaque nœud (node-side, reste au harnais).
    local entry vm
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        vm_sh "${vm}" sh -c 'sudo mkdir -p /var/lib/rook && sudo chmod 755 /var/lib/rook'
    done

    # PORTÉ EN RÔLE ANSIBLE (platform-ceph-cluster). Le rôle applique les
    # manifestes figés (SSA + force_conflicts sur les CR mutés par Rook), patche
    # les surcharges de topologie, et gate sur HEALTH_OK + OSD up. Anti-double-
    # source : plus de kubectl apply / retry shell ici. Surcharges banc passées
    # en -e (defaults du rôle = valeurs PROD) : dossier dé-épinglé arm64,
    # metadataDevice vde, OSD 512Mi, 9 OSD attendus (3 nœuds × 3 HDD).
    local undig; undig=$(ceph_undigest_manifests)
    run_ansible_phase bootstrap/ceph-cluster.yaml \
        -e "ceph_manifests_dir=${undig}" \
        -e "ceph_cluster_src=${undig}/cluster.yaml" \
        -e ceph_metadata_device=vde \
        -e ceph_osd_memory_request=512Mi \
        -e "ceph_osd_expected=$(( ${#NODES[@]} * HDD_COUNT ))"
    ok "Ceph HEALTH_OK (operator + cluster + toolbox, OSD up)"
}

# ── Phase 4 — StorageClasses ─────────────────────────────────────────────────
phase_sc() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase 4 — StorageClasses Ceph via Ansible"
    # PORTÉ EN RÔLE ANSIBLE (platform-ceph-storageclasses) : apply des SC bloc/fs,
    # SC default (1 seule), pré-condition CSI monitors. Anti-double-source. Pas de
    # surcharge banc (SC sans image ni device). gate_test_pvc reste un TEST.
    run_ansible_phase bootstrap/ceph-storageclasses.yaml
    gate_test_pvc rook-ceph-block-replicated
}

# ── Phase datalake — CephObjectStore RGW (cible S3 des backups Barman) ────────
# Monte le store objet S3 du datalake (RGW Ceph) : prérequis du plugin Barman de
# CloudNativePG (l'OBC `cnpg-backups` du rôle platform-cnpg s'y branche). Mode
# Ceph uniquement. À lancer après `sc`, avant `dataops`.
phase_datalake() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase datalake — CephObjectStore RGW via Ansible"
    # PORTÉ EN RÔLE ANSIBLE (platform-ceph-datalake) : CephObjectStore (SSA +
    # force_conflicts, CR muté par Rook) + SC bucket, gate RGW Ready. Anti-double-
    # source. La phase_smoke_s3 qui suit reste un TEST (PUT/GET/DELETE réel).
    run_ansible_phase bootstrap/ceph-datalake.yaml
    ok "RGW datalake Ready (cible S3 des backups Barman)"
}

# ── Phase smoke-s3 — preuve objet : PUT/GET/DELETE réel sur le RGW Ceph ───────
# Réutilise le scénario 06 (wrapper port-forward + smoke-test.sh datalake), seul
# garant que l'objet S3 fonctionne *vraiment* (pas seulement le Deployment Ready).
# KEEP_DATALAKE=1 : le datalake est posé par la phase `datalake`, on ne le détruit
# pas en sortie. Mode Ceph uniquement, à lancer après `datalake`.
phase_smoke_s3() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    log "Phase smoke-s3 — PUT/GET/DELETE sur le RGW Ceph (scénario 06)"
    # KUBECONFIG exporté EN ABSOLU pour le scénario externe : il fait du kubectl
    # qui lit l'env (pas le tableau KUBECTL du harnais) ; sans ça il tombe sur
    # localhost:8080 (même piège que L50). Le scénario fait `cd` → chemin absolu.
    KUBECONFIG="${KUBECONFIG_LOCAL}" KEEP_DATALAKE=1 \
        bash "${REPO}/test/scenarios/06-object-store-smoke.sh" \
        || die "smoke-test S3 (RGW) en échec — voir la sortie ci-dessus"
    ok "smoke-test S3 réussi (PUT/GET/DELETE sur le RGW Ceph)"
}

# ── Phase wordpress — preuve bloc : PVC RWO Ceph Bound + Pod Ready ────────────
# Monte l'exemple WordPress (storage/ceph/wordpress/) : MySQL + WordPress, chacun
# un PVC `ReadWriteOnce` sur la StorageClass bloc Ceph `rook-ceph-block-replicated`.
# GATE : les deux Deployments rollout et les PVC sont Bound. Mode Ceph uniquement.
phase_wordpress() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    log "Phase wordpress — montage PVC bloc RWO sur la SC Ceph (storage/ceph/wordpress/)"
    # Secret `wordpress-secret` (mot de passe MySQL) : NON versionné (ADR 0023) ;
    # mysql.yaml/wordpress.yaml le référencent en secretKeyRef. Le banc le crée
    # avec une valeur GÉNÉRIQUE de test (idempotent) — sans lui, les pods restent
    # en CreateContainerConfigError (« secret wordpress-secret not found »).
    "${KUBECTL[@]}" -n default create secret generic wordpress-secret \
        --from-literal=password='banc-wordpress-example' \
        --dry-run=client -o yaml | "${KUBECTL[@]}" apply -f - >/dev/null
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/wordpress/mysql.yaml"
    "${KUBECTL[@]}" apply -f "${REPO}/storage/ceph/wordpress/wordpress.yaml"

    # GATE : les Deployments deviennent disponibles (PVC RWO Bound + Pod Ready).
    log "  Attente du rollout MySQL + WordPress (max 5 min)"
    "${KUBECTL[@]}" -n default rollout status deploy/wordpress-mysql --timeout=300s \
        || die "wordpress-mysql pas Ready : $("${KUBECTL[@]}" -n default describe pvc mysql-pv-claim | tail -10)"
    "${KUBECTL[@]}" -n default rollout status deploy/wordpress --timeout=300s \
        || die "wordpress pas Ready : $("${KUBECTL[@]}" -n default describe pvc wp-pv-claim | tail -10)"
    ok "WordPress monté — PVC bloc RWO Bound + Pods Ready (preuve stockage bloc Ceph)"

    # SMOKE HTTP : Pod Ready ≠ application qui sert. On vérifie que WordPress
    # RÉPOND via son Service (pod busybox éphémère → GET http://wordpress/). Une
    # install neuve redirige (301/302) vers /wp-admin/install.php : c'est la PREUVE
    # qu'il sert (PHP + lecture/écriture sur le PVC bloc Ceph). On accepte tout
    # code < 400 (200/301/302) ; un timeout/5xx = échec.
    log "  Smoke HTTP WordPress (GET http://wordpress/ via le Service)"
    local wp_code
    wp_code=$("${KUBECTL[@]}" -n default run wp-smoke-$$ --rm -i --restart=Never \
        --image=busybox:1.36 --quiet --command -- \
        wget -S -T 10 -qO /dev/null 'http://wordpress.default.svc.cluster.local/' 2>&1 \
        | grep -oE 'HTTP/[0-9.]+ [0-9]+' | grep -oE '[0-9]+$' | head -1)
    if [ -n "${wp_code}" ] && [ "${wp_code}" -lt 400 ]; then
        ok "🎉 WordPress répond (HTTP ${wp_code}) — application servie sur stockage bloc Ceph"
    else
        die "smoke WordPress : pas de réponse HTTP < 400 (obtenu '${wp_code:-aucune}')"
    fi

    # Cleanup COMPLET : l'exemple n'a pas vocation à rester (le chemin prouve le
    # montage, pas un service durable). On supprime les workloads + Service ET les
    # PVC bloc Ceph (sinon volumes RBD orphelins) + le Secret. KEEP_WORDPRESS=1
    # conserve tout pour inspection.
    if [ "${KEEP_WORDPRESS:-0}" = 1 ]; then
        log "ℹ️  KEEP_WORDPRESS=1 — WordPress conservé (pods + PVC + secret)."
    else
        log "  Cleanup WordPress (workloads + PVC bloc Ceph + secret)"
        "${KUBECTL[@]}" delete -f "${REPO}/storage/ceph/wordpress/wordpress.yaml" --wait=false 2> /dev/null || true
        "${KUBECTL[@]}" delete -f "${REPO}/storage/ceph/wordpress/mysql.yaml" --wait=false 2> /dev/null || true
        # PVC + Secret ne sont pas dans les manifestes delete -f ci-dessus (le PVC
        # y est mais on force, et le Secret est créé par la phase, pas versionné).
        "${KUBECTL[@]}" -n default delete pvc mysql-pv-claim wp-pv-claim --wait=false 2> /dev/null || true
        "${KUBECTL[@]}" -n default delete secret wordpress-secret 2> /dev/null || true
        ok "WordPress nettoyé — aucun volume RBD ni secret résiduel"
    fi
}

# ── Phase hardening — axe ORTHOGONAL de durcissement hôte (ADR 0045 §3, #240) ─
# Le durcissement est un second axe, indépendant du stockage : activable sur
# N'IMPORTE QUEL chemin via WITH_HARDENING=1 (modèle WITH_CEPH). Applique
# bootstrap/security/secure.yml (durcissement opt-in par tags) sur l'inventaire
# du banc. Tags banc par défaut : `audit,detection` (auditd + fail2ban — ce qui
# rend jouable le scénario 16 au lieu de skip) ; surchargeable par HARDENING_TAGS.
# On EXCLUT volontairement `os` (full-upgrade + reboot) et `network` (UFW, coupe
# le réseau K8s) — destructifs pour un banc éphémère.
# Invoquée après bootstrap (l'hôte est joignable), avant/après les briques k8s.
phase_hardening() {
    preflight
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    local tags="${HARDENING_TAGS:-audit,detection}"
    log "Phase hardening — durcissement hôte via secure.yml (tags: ${tags})"

    # Le rôle `settings` (tag always) ASSERT que 5 variables d'env sont définies
    # et non vides (MAIL_ROOT_REDIRECT, HOST_USER, PASSWORD_EXPIRATION,
    # PUBLIC_SSH_KEY, MAIL_SMARTHOST). On source d'abord un éventuel `.env`
    # gitignoré (surcharge locale, pattern ADR 0023), puis on fournit des
    # DÉFAUTS d'exemple génériques pour le banc — `audit,detection` ne les
    # consomme pas (pas de mail/compte/ssh touchés), mais l'assert les exige.
    local env_file="${REPO}/bootstrap/security/.env"
    if [ -f "${env_file}" ]; then
        log "  source ${env_file} (surcharge locale)"
        set -a
        # shellcheck disable=SC1090
        . "${env_file}"
        set +a
    fi
    export MAIL_ROOT_REDIRECT="${MAIL_ROOT_REDIRECT:-root@example.org}"
    export HOST_USER="${HOST_USER:-bob}"
    export PASSWORD_EXPIRATION="${PASSWORD_EXPIRATION:-42}"
    export PUBLIC_SSH_KEY="${PUBLIC_SSH_KEY:-~/.ssh/exemple.pub}"
    export MAIL_SMARTHOST="${MAIL_SMARTHOST:-[mailpit.example.org]:1025}"

    ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/security/secure.yml" \
        --tags "${tags}" \
        || die "secure.yml : échec du durcissement (tags=${tags})"
    ok "durcissement appliqué (tags ${tags}) — scénarios 10–16 jouables"
}

# ── Phase dataops — chaîne DataOps assemblée via Ansible (#173) ───────────────
# Déploie la chaîne (registry → cert-manager → CNPG+Barman → build → Dagster →
# Marquez) avec le playbook Ansible idempotent bootstrap/dataops.yaml (ADR 0033),
# puis PROUVE le maillon final : un vrai run Dagster émet du lineage OpenLineage
# que Marquez ingère (cœur #148, étape conservée du harnais jetable).
#
# Pré-requis : bootstrap + ceph + sc + datalake (RGW). Le playbook pilote l'API
# depuis l'hôte (dataops_k8s_host=localhost) via le kubeconfig banc.
phase_dataops() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    # shellcheck source=test/lima/dataops-assert.sh
    . "${HERE}/dataops-assert.sh"
    log "Phase dataops — chaîne DataOps via Ansible (registry → CNPG → Dagster → Marquez)"

    # Le playbook tourne depuis l'hôte : kubernetes.core lit ce KUBECONFIG ;
    # storageClass banc = rook-ceph-block-replicated (défaut prod, mode Ceph).
    # Le CA TLS (SSL_CERT_FILE, drift L23) est résolu et posé PAR le playbook
    # lui-même (pré-tâche certifi) — avec le bon interpréteur Python.
    # build_emitter_image=true : le banc build aussi l'émetteur OpenLineage jetable
    # (harnais e2e, ADR 0022) requis par la preuve lineage ci-dessous — JAMAIS en
    # prod (défaut false). Drift L31.
    # Profil de stockage/backing par topologie (ADR 0035/0036), comme monitoring :
    #   - mode Ceph (WITH_CEPH=1) : storageClass rook-ceph ; backups CNPG → RGW.
    #   - mode léger (défaut)      : storageClass local-path ; backups CNPG →
    #     SeaweedFS (déployé par la phase monitoring). Permet la chaîne DataOps
    #     SANS Ceph (banc léger, ADR 0036).
    # DÉPENDANCE (ADR 0045) : en mode léger, `dataops` ne déploie PAS SeaweedFS —
    # il en CONSOMME l'endpoint. Le backing doit donc être posé AVANT (par
    # `monitoring`). Les chemins `atlas`/`cluster` garantissent cet ordre ;
    # lancer `dataops` seul en léger sans `monitoring` préalable échouerait.
    local sc backing endpoint
    if [ "${WITH_CEPH:-0}" = 1 ]; then
        sc=rook-ceph-block-replicated
        backing=rgw
        endpoint=http://rook-ceph-rgw-datalake.rook-ceph:80
    else
        sc=local-path
        backing=seaweedfs
        endpoint=http://seaweedfs.s3.svc.cluster.local:8333
    fi
    log "  storageClass=${sc}, backing S3 CNPG=${backing} (${endpoint})"

    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/dataops.yaml" \
        -e dataops_k8s_host=localhost \
        -e build_emitter_image=true \
        -e "registry_storage_class=${sc}" \
        -e "cnpg_storage_class=${sc}" \
        -e "cnpg_s3_backing=${backing}" \
        -e "cnpg_s3_endpoint=${endpoint}" \
        || die "dataops.yaml : échec du déploiement de la chaîne"
    ok "chaîne DataOps déployée (Ansible) — CNPG sain, Dagster + Marquez Ready"

    # Preuve finale : run Dagster réel → lineage OpenLineage → ingestion Marquez.
    # L'émetteur jetable reste un harnais de test (PAS porté en rôle, ADR 0022).
    log "  Émetteur jetable — run Dagster + sensor OpenLineage → ingestion Marquez"
    dataops_chain_emit_and_verify
    ok "🎉 chaîne DataOps validée — lineage d'un run Dagster réel visible dans Marquez"

    # Preuve de l'egress Internet du ns dagster (NP allow-internet-egress, #256) :
    # un run peut sortir sur 443 AVEC la policy, bloqué SANS. Indispensable au sync
    # du snapshot OpenAlex (aws s3 sync --no-sign-request) sous default-deny.
    log "  Preuve egress Internet — sortie 443 du ns dagster (avec/sans la NP)"
    dataops_egress_internet_check

    log "Consigner ce run dans test/lima/RESULTS.md (honnêteté des Runs, ADR 0023)."
}

# ── Phase gitops — socle GitOps : Gitea (forge) + Argo CD (moteur) ───────────
# Déploie le socle GitOps via bootstrap/gitops.yaml (ADR 0022/0044) : Gitea
# (forge git intra-banc air-gapped) puis Argo CD (moteur). INFRA, posée par
# Ansible (anti-bootstrap-circulaire). Profil banc atlas = local-path (ADR 0044,
# pas de Ceph). L'UI Argo CD via Gateway exige cert-manager + CRDs Gateway API ;
# sur le banc léger sans cert-manager, on n'applique PAS le Gateway
# (argocd_apply_gateway=false) — la réconciliation GitOps reste prouvable sans UI.
#
# L'INIT du dépôt Gitea (org + repo + seed atlas + webhook) est l'étape suivante
# (test e2e, #231) — hors de cette phase qui ne fait que poser le socle.
phase_gitops() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase gitops — socle GitOps via Ansible (Gitea → Argo CD)"

    # storageClass du PVC Gitea + exposition UI : SUIVENT le profil du banc
    # (comme dataops/monitoring) — WITH_CEPH=1 ⇒ stockage Ceph (sinon le PVC
    # demande local-path, absent en mode Ceph → Gitea Pending). En mode Ceph,
    # cert-manager est présent (posé par dataops, prérequis Barman) → on peut
    # exposer l'UI Argo CD via Gateway ; en léger, non (pas de cert-manager garanti).
    local sc apply_gw
    if [ "${WITH_CEPH:-0}" = 1 ]; then
        sc=rook-ceph-block-replicated
        apply_gw=true
    else
        sc=local-path
        apply_gw=false
    fi
    log "  gitea_storage_class=${sc}, argocd_apply_gateway=${apply_gw}"
    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/gitops.yaml" \
        -e dataops_k8s_host=localhost \
        -e "gitea_storage_class=${sc}" \
        -e "argocd_apply_gateway=${apply_gw}" \
        || die "gitops.yaml : échec du déploiement du socle GitOps"
    ok "socle GitOps déployé (Ansible) — Gitea + Argo CD Ready"

    # GATE : les deux Deployments répondent Ready (le playbook a déjà ses propres
    # waits ; on re-vérifie ici côté harnais, comme les autres phases). KUBECTL
    # embarque déjà --kubeconfig (cf. en-tête du script).
    "${KUBECTL[@]}" -n gitea rollout status deploy/gitea --timeout=120s \
        || die "gitea : Deployment non Ready"
    "${KUBECTL[@]}" -n argocd rollout status deploy/argocd-server --timeout=180s \
        || die "argocd-server : Deployment non Ready"
    ok "🎉 socle GitOps prêt — Gitea (forge) et Argo CD (moteur) Ready"

    log "Suite : phase 'gitops-seed' (init dépôt Gitea + webhook + Application atlas)."
}

# ── Phase gitops-seed — init du dépôt Gitea (DONNÉES, post-bootstrap) ─────────
# Crée l'admin/org/repo Gitea, pousse le workflow atlas jouet, pose le webhook
# Gitea → Argo CD + le secret partagé, et l'Application atlas-workflows (#231,
# ADR 0044/0045). Étape de DONNÉES (pas d'infra : Gitea est déjà posé par gitops).
# Pré-requis : phase `gitops` (Gitea + Argo CD) + `dataops` (image émetteur).
phase_gitops_seed() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    "${KUBECTL[@]}" -n gitea get deploy gitea >/dev/null 2>&1 \
        || die "Gitea absent — lancer la phase 'gitops' d'abord"
    log "Phase gitops-seed — init du dépôt Gitea + webhook + Application atlas"
    # Sourcé (pas exécuté) pour hériter du TABLEAU KUBECTL ; le garde
    # BASH_SOURCE != $0 dans gitea-init.sh empêche son auto-exécution, on appelle
    # `main` explicitement.
    # shellcheck source=test/lima/gitea-init.sh
    . "${HERE}/gitea-init.sh"
    main || die "gitea-init : init du dépôt Gitea échouée"
    ok "🎉 dépôt Gitea initialisé — Application atlas-workflows posée (réconciliation Argo CD)"
    log "Preuve e2e : test/scenarios/27-gitops-workflow-deploy.sh"
}

# ── Phase access — accès développeur (URLs cliquables + secrets + .env atlas) ──
# Délègue à access.sh (#232, ADR 0048) : pose les Gateways des UI, ouvre un
# forward SSH par Gateway, /etc/hosts *.cluster.lan, regroupe les secrets et
# génère ../atlas/.env.cluster.local. C'est l'étape qui rend le banc consommable
# depuis l'hôte (« git push et ça marche »). Args transmis (--no-hosts, --stop…).
phase_access() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'run-phases.sh atlas' d'abord"
    "${HERE}/access.sh" "$@"
}

# ── Phase monitoring — observabilité (Prometheus + Grafana + Loki) ───────────
# Déploie kube-prometheus-stack + Loki via bootstrap/monitoring.yaml (ADR
# 0016/0036). Profil de stockage choisi selon le mode du banc :
#   - mode Ceph (WITH_CEPH=1) : storageClass rook-ceph, Loki en profil s3 → RGW.
#   - mode léger (défaut)      : storageClass local-path, Loki en s3 → SeaweedFS.
# Le profil léger NE requiert PAS Ceph (testable en banc rapide, ADR 0035/0036).
phase_monitoring() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase monitoring — Prometheus + Grafana + Loki (via Ansible)"

    # Profil par topologie (ADR 0035/0036) : Loki est TOUJOURS en S3 (même code
    # que prod) ; seul le backing change — SeaweedFS en banc léger (S3 sans Ceph),
    # RGW Ceph en mode Ceph.
    local sc backing endpoint
    if [ "${WITH_CEPH:-0}" = 1 ]; then
        sc=rook-ceph-block-replicated
        backing=rgw
        endpoint=http://rook-ceph-rgw-datalake.rook-ceph:80
    else
        sc=local-path
        backing=seaweedfs
        endpoint=http://seaweedfs.s3.svc.cluster.local:8333
    fi
    log "  storageClass=${sc}, backing S3 Loki=${backing} (${endpoint})"

    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/monitoring.yaml" \
        -e dataops_k8s_host=localhost \
        -e "monitoring_storage_class=${sc}" \
        -e "loki_storage_class=${sc}" \
        -e "loki_s3_backing=${backing}" \
        -e "loki_s3_endpoint=${endpoint}" \
        || die "monitoring.yaml : échec du déploiement de l'observabilité"
    ok "🎉 observabilité déployée — Prometheus + Grafana + Loki (S3/${backing}) Ready"
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
    # shellcheck disable=SC2329  # invoquée indirectement par `retry`
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

# Code HTTP curl d'une sortie HTTPS vers une IP publique depuis un pod éphémère du
# ns `dagster` (preuve du FLUX egress Internet, pas d'un service S3 précis). On
# vise une IP littérale stable (Cloudflare 1.1.1.1) pour ne PAS dépendre du DNS ni
# d'un endpoint AWS mouvant : ce qu'on prouve, c'est qu'un paquet sortant sur 443
# atteint le « world ». curl imprime LUI-MÊME "000" via `-w '%{http_code}'` quand
# la connexion n'aboutit pas (timeout/refus) — PAS de fallback `|| printf 000`
# (curl sort alors en erreur ET a déjà imprimé 000 → la valeur doublerait en
# "000000", faux verdict). On normalise : toute sortie non « 3 chiffres » (pod qui
# ne démarre pas, etc.) est ramenée à "000".
egress_probe_code() {
    local code
    code=$("${KUBECTL[@]}" -n dagster run egress-probe-$$ --rm -i --restart=Never \
        --image=curlimages/curl:8.11.1 --quiet -- \
        curl -sS -o /dev/null --max-time 8 -w '%{http_code}' https://1.1.1.1/ \
        2>/dev/null)
    case "$code" in
        [0-9][0-9][0-9]) printf '%s' "$code" ;;
        *) printf '000' ;;
    esac
}

# PREUVE de la NP allow-internet-egress (#256) : un run du ns `dagster` peut sortir
# sur Internet (443) AVEC la policy, et est bloqué SANS (default-deny mord). On ne
# mocke PAS S3 — un mock intra-cluster n'emprunte pas la règle `ipBlock 0.0.0.0/0`
# (sous Cilium les pods du cluster sont exclus du CIDR « world »). Méthode :
#   1. probe AVEC la NP (déjà déployée par la phase dataops) → doit aboutir ;
#   2. retire la NP, re-probe → doit timeouter (000) ;
#   3. RÉAPPLIQUE la NP depuis le manifeste versionné (corriger le code/l'état du
#      banc, pas l'inventer — ADR 0046 : le retrait est interne au test et se
#      RECONVERGE ; un trap garantit la réapplication même si la probe échoue).
# Le verdict est rendu par la fonction PURE classify_egress_probe (testée bats).
dataops_egress_internet_check() {
    local np=platform/network-policies/dagster/allow-internet-egress.yaml
    local with_np without_np verdict
    # 1. État nominal (NP présente, posée par le playbook dataops).
    with_np=$(egress_probe_code)

    # 2/3. Bascule SANS la NP, puis garantit la réapplication quoi qu'il arrive.
    # shellcheck disable=SC2329  # invoquée par le trap RETURN
    _restore_egress_np() { "${KUBECTL[@]}" apply -f "${REPO}/${np}" >/dev/null 2>&1 || true; }
    trap _restore_egress_np RETURN
    "${KUBECTL[@]}" delete -f "${REPO}/${np}" --ignore-not-found >/dev/null 2>&1 || true
    without_np=$(egress_probe_code)
    _restore_egress_np
    trap - RETURN

    verdict=$(classify_egress_probe "${with_np}" "${without_np}")
    case "${verdict%%|*}" in
        ok) ok "${verdict#*|}" ;;
        skip) log "    ${verdict#*|}" ;;
        *) die "${verdict#*|} — NP allow-internet-egress à vérifier" ;;
    esac
}

# ── Status — visualisation de l'état du banc (#149) ──────────────────────────
# Lecture seule : VMs Lima (état), nœuds K8s, phases franchies (déduites de
# l'état réel du cluster, pas d'un fichier d'étape), liens vers les UIs, et le
# dernier run consigné. Ne monte rien, ne casse rien — utile pour « où en est le
# banc ? » sans relire les logs.
phase_status() {
    require_lima
    log "État du banc Lima"

    # 1. VMs Lima + disques.
    printf '\n  \033[1mVMs Lima\033[0m\n'
    local entry vm st
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        if vm_exists "${vm}"; then
            st=$(limactl list "${vm}" --format '{{.Status}}' 2>/dev/null || echo '?')
            printf '    %-7s %s\n' "${vm}" "${st}"
        else
            printf '    %-7s \033[2mabsente\033[0m\n' "${vm}"
        fi
    done

    # Sans kubeconfig, le cluster n'est pas joignable : on s'arrête là.
    if [ ! -f "${KUBECONFIG_LOCAL}" ]; then
        printf '\n  \033[2mPas de kubeconfig (%s) — cluster non démarré ?\033[0m\n' "${KUBECONFIG_LOCAL}"
        status_last_run
        return 0
    fi

    # 2. Nœuds K8s + phases franchies (déduites des objets réellement présents).
    printf '\n  \033[1mNœuds Kubernetes\033[0m\n'
    "${KUBECTL[@]}" get nodes --no-headers 2>/dev/null \
        | awk '{printf "    %-7s %s\n", $1, $2}' || printf '    \033[2minjoignable\033[0m\n'

    printf '\n  \033[1mPhases franchies\033[0m (déduites de l'\''état du cluster)\n'
    status_probe "nœuds Ready" nodes_ready_all
    status_probe "Ceph (OSD up)" "ceph_present"
    status_probe "StorageClass default" "sc_default_present"
    status_probe "DataOps (Dagster+Marquez)" "dataops_present"
    status_probe "monitoring (Prometheus)" "prometheus_present"

    # Santé par composante (verdicts de la lib pure health-classify.sh, partagée
    # avec bootstrap/state.sh). Le banc collecte via "${KUBECTL[@]}" (cible sûre)
    # puis classe. Best-effort : une brique absente → skip (·), pas une erreur.
    printf '\n  \033[1mSanté des composantes\033[0m\n'
    # Collectes best-effort : `|| true` IMPÉRATIF sous set -e — un `kubectl get`
    # sur une ressource/ns absent sort rc≠0 et tuerait l'affectation. La brique
    # absente vaut alors vide → classify_* rend skip (·), pas une erreur.
    local nr rn osd_up sc d_web m_api
    nr=$("${KUBECTL[@]}" get nodes --no-headers 2>/dev/null | awk '$2 != "Ready" {print $1}' | tr '\n' ' ' || true)
    rn=$("${KUBECTL[@]}" get nodes --no-headers 2>/dev/null | grep -cw Ready || true)
    status_health "nœuds" "$(classify_nodes_ready "${nr}" "${rn}")"
    osd_up=$(toolbox_ceph osd stat 2>/dev/null | grep -oE '[0-9]+ up' | grep -oE '^[0-9]+' || true)
    status_health "Ceph OSD" "$(classify_ceph_osd "${osd_up:-}" "${OSD_EXPECTED}")"
    sc=$("${KUBECTL[@]}" get sc -o jsonpath='{range .items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")]}{.metadata.name}{end}' 2>/dev/null || true)
    status_health "StorageClass défaut" "$(classify_sc_default "${sc}")"
    d_web=$("${KUBECTL[@]}" -n dagster get deploy dagster-dagster-webserver -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)
    status_health "Dagster webserver" "$(classify_deploy_ready "Dagster webserver" "${d_web:-}" "$([ -n "${d_web}" ] && echo 1 || echo '')")"
    m_api=$("${KUBECTL[@]}" -n marquez get deploy marquez -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)
    status_health "Marquez API" "$(classify_deploy_ready "Marquez API" "${m_api:-}" "$([ -n "${m_api}" ] && echo 1 || echo '')")"

    # 3. Liens vers les UIs exposées (port-forward suggéré, pas lancé).
    printf '\n  \033[1mAccès UIs\033[0m (port-forward à lancer si besoin)\n'
    status_ui "API K8s" "https://127.0.0.1:${API_PORT}" ""
    # Grafana : le Service du chart s'appelle `kube-prometheus-stack-grafana`
    # (pas `grafana`) — drift L57. Port-forward de secours ; l'accès recommandé
    # passe par `access.sh` (Gateway + /etc/hosts, ADR 0048).
    status_ui_pf "Grafana" monitoring svc/kube-prometheus-stack-grafana 3000 80
    status_ui_pf "Prometheus" monitoring svc/prometheus-operated 9090 9090
    status_ui_pf "Marquez (web)" marquez svc/marquez-web 3000 3000
    status_ui_pf "Dagster" dagster svc/dagster-dagster-webserver 3001 80
    printf '    %-16s \033[2mtest/lima/access.sh\033[0m → URLs *.cluster.lan cliquables + secrets + .env atlas\n' "Tout (dev)"

    status_last_run
}

# Affiche une ligne « phase franchie » : ✓/✗ selon un prédicat (lecture seule).
status_probe() {
    local label=$1 pred=$2
    if "${pred}" 2>/dev/null; then
        printf '    \033[32m✓\033[0m %s\n' "${label}"
    else
        printf '    \033[2m·\033[0m %s\n' "${label}"
    fi
}

# Affiche le verdict "STATUS|message" d'un classify_* (lib health-classify) :
# ✓ ok / ✗ fail / · skip. L'appelant collecte (kubectl) puis classe.
status_health() {
    local label=$1 verdict=$2 status=${2%%|*} msg=${2#*|}
    case "${status}" in
        ok)   printf '    \033[32m✓\033[0m %s — %s\n' "${label}" "${msg}" ;;
        fail) printf '    \033[31m✗\033[0m %s — %s\n' "${label}" "${msg}" ;;
        *)    printf '    \033[2m·\033[0m %s — %s\n' "${label}" "${msg}" ;;
    esac
}

# Prédicats de présence (best-effort, lecture seule) pour le status.
ceph_present() { [ -n "$("${KUBECTL[@]}" -n rook-ceph get deploy rook-ceph-operator -o name 2>/dev/null)" ] && osds_up; }
sc_default_present() { "${KUBECTL[@]}" get sc -o jsonpath='{range .items[*]}{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}{"\n"}{end}' 2>/dev/null | grep -q true; }
dataops_present() { [ -n "$("${KUBECTL[@]}" -n dagster get deploy -o name 2>/dev/null)" ] && [ -n "$("${KUBECTL[@]}" -n marquez get deploy -o name 2>/dev/null)" ]; }
prometheus_present() { [ -n "$("${KUBECTL[@]}" -n monitoring get pods -l app.kubernetes.io/name=prometheus -o name 2>/dev/null)" ]; }

# Affiche un lien UI direct (déjà joignable, ex. API forwardée).
status_ui() {
    local label=$1 url=$2
    printf '    %-16s %s\n' "${label}" "${url}"
}

# Affiche la commande port-forward d'une UI SI le Service existe.
# Args : label ns ressource port_local port_distant
status_ui_pf() {
    local label=$1 ns=$2 res=$3 lport=$4 rport=$5
    if "${KUBECTL[@]}" -n "${ns}" get "${res}" -o name >/dev/null 2>&1; then
        printf '    %-16s \033[2mkubectl -n %s port-forward %s %s:%s\033[0m → http://127.0.0.1:%s\n' \
            "${label}" "${ns}" "${res}" "${lport}" "${rport}" "${lport}"
    fi
}

# Affiche le dernier run consigné dans l'historique (date + tuple).
status_last_run() {
    local f last
    f=$(metro_history_file)
    printf '\n  \033[1mDernier run consigné\033[0m\n'
    if [ ! -f "${f}" ] || ! grep -q '^[[:space:]]*- id:' "${f}" 2>/dev/null; then
        # shellcheck disable=SC2016  # `atlas` est un libellé littéral, pas une expansion
        printf '    \033[2maucun (lancer un chemin, p.ex. `atlas`, pour en consigner un)\033[0m\n'
        return 0
    fi
    last=$(grep -E '^[[:space:]]*- id:' "${f}" | tail -1 | sed -E 's/.*- id:[[:space:]]*//')
    printf '    %s\n' "${last}"
    printf '    \033[2m(détail : %s ; fraîcheur : test/lima/check-freshness.sh)\033[0m\n' "$(basename "${f}")"
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

# ── Chemins d'installation (ADR 0045) ───────────────────────────────────────
# Quatre chemins nommés, du plus court au plus complet. Chacun monte d'abord le
# SOCLE (up → bootstrap → stockage, avec cache #219), puis ses couches
# applicatives. L'observabilité (monitoring) est posée TÔT (avant gitops/dataops)
# pour capter leur démarrage, et fournit le backing S3 SeaweedFS que dataops
# consomme en mode léger. Axe orthogonal : WITH_HARDENING=1 durcit l'hôte sur
# n'importe quel chemin (#240). L'agrégat `all` est supprimé (ADR 0045 §3).
#
# Variable globale `SOCLE_BUILT` (0/1) : posée par run_socle, lue à la fin pour
# ne consigner QUE les runs from-scratch (drift L49).
SOCLE_BUILT=0

# Monte le socle (up → bootstrap → stockage selon profil), avec cache du socle
# (#219). Pose SOCLE_BUILT=1 si le socle a RÉELLEMENT été bâti (pas réutilisé).
run_socle() {
    local profil
    profil=$(metro_profil "${WITH_CEPH:-0}")
    SOCLE_BUILT=0
    if metro_cache_valid "${profil}"; then
        ok "socle réutilisé depuis le cache (clé inchangée) — up/bootstrap sautés (#219)"
        log "ℹ️  Forcer un rebuild from-scratch (preuve ADR 0034) : NO_CACHE=1 $0 ${TARGET:-atlas}"
        return 0
    fi
    time_phase up phase_up
    time_phase bootstrap phase_bootstrap
    if [ "${WITH_CEPH:-0}" = 1 ]; then
        time_phase ceph phase_ceph
        time_phase sc phase_sc
        log "🎉 Socle monté (mode Ceph) : up → bootstrap → ceph → storageClasses."
    else
        time_phase storage-simple phase_storage_simple
        log "🎉 Socle monté (mode rapide) : up → bootstrap → storage-simple."
    fi
    metro_cache_save "${profil}"
    SOCLE_BUILT=1
}

# Consigne le run SI from-scratch (socle réellement bâti). Un run sur cache (#219)
# ne rejoue pas le socle → PHASE_DURATIONS partiel → fausse preuve (drift L49).
record_if_fresh() {
    local started=$1
    if [ "${SOCLE_BUILT}" = 1 ]; then
        record_full_run "$(( $(date +%s) - started ))"
    else
        log "ℹ️  Run sur cache (socle réutilisé) — NON consigné dans runs-history.yaml"
        log "    (seul un run from-scratch est une preuve ADR 0034/0042 ; NO_CACHE=1 pour consigner)"
    fi
}

# Prélude commun aux chemins agrégés : workdir + relevé de durées propre + start.
chemin_prelude() {
    mkdir -p "${WORKDIR}"
    : > "${PHASE_DURATIONS}" # repart d'un relevé propre pour CE run
}

# Axe ORTHOGONAL durcissement (#240, ADR 0045 §3) : applique le hardening hôte si
# WITH_HARDENING=1, sur N'IMPORTE QUEL chemin, juste après le socle (hôte prêt).
# No-op sinon. Le verdict (durci/non) est reflété dans le suffixe de TARGET pour
# que le run consigné distingue les deux variantes (preuve par chemin, ADR 0042).
run_hardening_if_requested() {
    if [ "${WITH_HARDENING:-0}" = 1 ]; then
        time_phase hardening phase_hardening
        TARGET="${TARGET}+hardening"
    fi
}

# ── Dispatch ─────────────────────────────────────────────────────────────────
case "${1:-}" in
    up) time_phase up phase_up ;;
    bootstrap) time_phase bootstrap phase_bootstrap ;;
    bootstrap-fault) time_phase bootstrap-fault phase_bootstrap_fault ;;
    storage-simple) time_phase storage-simple phase_storage_simple ;;
    metrics-server) time_phase metrics-server phase_metrics_server ;;
    platform-prereqs) time_phase platform-prereqs phase_platform_prereqs ;;
    datalake) time_phase datalake phase_datalake ;;
    smoke-s3) time_phase smoke-s3 phase_smoke_s3 ;;
    wordpress) time_phase wordpress phase_wordpress ;;
    hardening) time_phase hardening phase_hardening ;;
    dataops) time_phase dataops phase_dataops ;;
    gitops) time_phase gitops phase_gitops ;;
    gitops-seed) time_phase gitops-seed phase_gitops_seed ;;
    monitoring) time_phase monitoring phase_monitoring ;;
    access) phase_access "${@:2}" ;;
    ceph) time_phase ceph phase_ceph ;;
    sc) time_phase sc phase_sc ;;
    kubeconfig) preflight; fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" cluster-banc ;;
    # ── socle : up → bootstrap → stockage. Smoke-test rapide (ADR 0045). ──────
    socle)
        TARGET=socle
        chemin_prelude
        run_start=$(date +%s)
        run_socle
        run_hardening_if_requested
        log "🎉 Chemin 'socle' : socle monté (profil $(metro_profil "${WITH_CEPH:-0}"))."
        record_if_fresh "${run_start}"
        ;;
    # ── atlas : socle léger → monitoring → gitops → dataops (ADR 0044/0045). ──
    # Observabilité d'abord (capte la suite + pose SeaweedFS) ; puis socle GitOps
    # (Gitea + Argo CD) ; puis l'INFRA DataOps (CNPG/Dagster/Marquez vides — les
    # workflows atlas viendront par Argo CD, scénario 27 / #231). Profil local-path
    # (pas de Ceph sur le banc atlas).
    atlas)
        TARGET=atlas
        if [ "${WITH_CEPH:-0}" = 1 ]; then
            die "chemin 'atlas' = profil local-path (ADR 0044) ; ne pas combiner avec WITH_CEPH=1 (utiliser 'storage-real'/'cluster-dataops')"
        fi
        chemin_prelude
        run_start=$(date +%s)
        run_socle
        run_hardening_if_requested
        # metrics-server AVANT monitoring : palier 1 autonome (#252), rend
        # `kubectl top` opérant dès le socle — un dev atlas voit l'usage CPU/RAM.
        time_phase metrics-server phase_metrics_server
        time_phase monitoring phase_monitoring
        time_phase gitops phase_gitops
        time_phase dataops phase_dataops
        # gitops-seed APRÈS dataops : l'init pousse un workflow qui référence
        # l'image émetteur (buildée par dataops) et cible le ns dagster (monté
        # par dataops). Argo CD réconcilie ensuite le workflow depuis Gitea.
        time_phase gitops-seed phase_gitops_seed
        log "🎉 Chemin 'atlas' : metrics-server → monitoring → gitops → dataops → gitops-seed."
        log "ℹ️  Preuve e2e des workflows atlas par GitOps : scénario 27 (#231)."
        log "👉 Accès dev (URLs *.cluster.lan + secrets + .env atlas) : test/lima/access.sh (ADR 0048)."
        record_if_fresh "${run_start}"
        ;;
    # ── storage-real : socle Ceph → datalake → smoke S3 + WordPress (ADR 0045). ─
    # Preuve du STOCKAGE réel (bloc RWO + objet S3/RGW), PAS la chaîne applicative.
    # Banc Ceph qui porte aussi les scénarios 01–22 (résilience/sécu/chaos).
    storage-real)
        TARGET="storage-real"
        WITH_CEPH=1
        chemin_prelude
        run_start=$(date +%s)
        run_socle
        run_hardening_if_requested
        time_phase datalake phase_datalake
        time_phase smoke-s3 phase_smoke_s3
        time_phase wordpress phase_wordpress
        log "🎉 Chemin 'storage-real' (Ceph) : datalake → smoke S3 (RGW) → montage WordPress."
        log "ℹ️  Scénarios 01–22 jouables sur ce banc monté (ADR 0045 §4)."
        record_if_fresh "${run_start}"
        ;;
    # ── cluster-dataops : socle Ceph → datalake → monitoring → dataops (ADR 0045). ─
    # Chaîne DataOps complète sur stockage réel (confirme atlas en mode Ceph).
    # Pas de GitOps dans ce chemin.
    cluster-dataops)
        TARGET="cluster-dataops"
        WITH_CEPH=1
        chemin_prelude
        run_start=$(date +%s)
        run_socle
        run_hardening_if_requested
        time_phase datalake phase_datalake
        time_phase monitoring phase_monitoring
        time_phase dataops phase_dataops
        log "🎉 Chemin 'cluster-dataops' (Ceph) : datalake → monitoring → dataops."
        record_if_fresh "${run_start}"
        ;;
    # ── atlas-ceph : banc atlas COMPLET sur stockage réel (Ceph) + GitOps + UI. ──
    # L'ordre est CODÉ (ne jamais enchaîner ces phases à la main) : le socle Ceph,
    # puis datalake (RGW — requis par Loki/monitoring en mode Ceph ET par Barman),
    # monitoring (observe la suite), gitops (Gitea+Argo CD, SC Ceph car WITH_CEPH),
    # dataops (CNPG/Dagster/Marquez + build émetteur), enfin gitops-seed (pousse le
    # workflow qui référence l'image émetteur buildée par dataops). C'est le banc
    # sur lequel on vérifie les UI/portail (#232, scénario 28) en mode Ceph.
    atlas-ceph)
        TARGET="atlas-ceph"
        WITH_CEPH=1
        chemin_prelude
        run_start=$(date +%s)
        run_socle
        run_hardening_if_requested
        time_phase datalake phase_datalake
        time_phase monitoring phase_monitoring
        time_phase gitops phase_gitops
        time_phase dataops phase_dataops
        time_phase gitops-seed phase_gitops_seed
        log "🎉 Chemin 'atlas-ceph' : Ceph → datalake → monitoring → gitops → dataops → gitops-seed."
        log "ℹ️  UI exposées : vérifier via le scénario 28 (URLs via Gateway, #232)."
        record_if_fresh "${run_start}"
        ;;
    status) phase_status ;;
    down) phase_down ;;
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -40
        exit 2
        ;;
esac
