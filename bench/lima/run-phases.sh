#!/usr/bin/env bash
#
# Harnais node-side du banc léger Lima — sur des VMs Lima (vrai noyau, SSH natif) au
# lieu de VirtualBox. Stockage MODULAIRE : local-path (rapide) par défaut, Ceph optionnel.
#
# ⚠️ L'ORCHESTRATION (séquence des couches, gates de santé, fraîcheur, HA) vit désormais
# dans le MOTEUR PYTHON `nestor` (scripts/topology.py + nestor/path.py, ADR 0063/0097) :
# c'est l'entrée NORMALE (`nestor up/next/remove`). Ce script ne porte plus les chemins
# nommés agrégés (socle/atlas/storage-real/…) — le moteur les a remplacés. Il ne reste que
# les BRIQUES IRRÉDUCTIBLES que le moteur APPELLE (provisioning VM/CNI/inventaire/faits,
# ADR 0049/0056), les PHASES UNITAIRES qu'il consomme via l'arm `layers <seq>` (filet bash
# `--engine=bash`), et le rollback par phase. Chaque phase a un GATE et est idempotente.
#
# À lancer depuis le POSTE DE CONTRÔLE (Mac), pas dans une VM.
#
# Usage (briques irréductibles + phases unitaires ; l'entrée normale est `nestor`) :
#   ── Briques node-side APPELÉES par le moteur Python (ADR 0049/0056) ──
#   bench/lima/run-phases.sh up             # VMs + (si WITH_CEPH=1) disques bruts + gate vd* (#235)
#   bench/lima/run-phases.sh inventory <control_csv> [workers_csv] # (ré)écrit l'inventaire (write_inventory byte-stable)
#   bench/lima/run-phases.sh facts          # contrat machine : imprime CP_IP/L2_IFACE (+ VIP si HA)
#   bench/lima/run-phases.sh ha-cni <iface> # pose Cilium (L4 NodePort) + fetch kubeconfig banc
#   bench/lima/run-phases.sh kubeconfig     # (ré)exporte le kubeconfig banc
#   bench/lima/run-phases.sh access [...]   # accès dev (URLs NodePort + secrets + .env atlas, ADR 0048)
#   bench/lima/run-phases.sh down [vm…]     # détruit les VMs + disques nommés
#   ── Phases unitaires (jouées par l'arm `layers <seq>` que `nestor up --engine=bash` pousse) ──
#   bench/lima/run-phases.sh bootstrap      # bootstrap Ansible + Cilium + gate nœuds Ready
#   bench/lima/run-phases.sh storage-simple # local-path-provisioner (rapide) + gate PVC Bound
#   bench/lima/run-phases.sh metrics-server # Metrics API (kubectl top) + gate APIService Available (#252)
#   bench/lima/run-phases.sh ceph           # Rook-Ceph (metadataDevice=vde) + gate HEALTH_OK
#   bench/lima/run-phases.sh sc             # StorageClasses Ceph + gate PVC Bound
#   bench/lima/run-phases.sh datalake       # CephObjectStore RGW (cible S3 Barman) + gate Ready
#   bench/lima/run-phases.sh smoke-s3       # smoke S3 PUT/GET/DELETE sur le RGW Ceph (scénario 06)
#   bench/lima/run-phases.sh hardening      # durcissement hôte (secure.yml, tags audit,detection — #240)
#   bench/lima/run-phases.sh dataops        # chaîne DataOps via Ansible (dataops.yaml) + lineage (#173/#148)
#   bench/lima/run-phases.sh gitops         # socle GitOps : Gitea + Argo CD via Ansible (gitops.yaml) + gate Ready (#230)
#   bench/lima/run-phases.sh gitops-seed    # init dépôt Gitea : org/repo + workflow jouet + webhook + Application atlas (#231)
#   bench/lima/run-phases.sh monitoring     # observabilité (Prometheus + Grafana + Loki), profil auto-détecté
#   bench/lima/run-phases.sh mlflow         # serveur MLflow (suivi de modèles, backend CNPG + artefacts S3)
#   bench/lima/run-phases.sh portal         # portail d'accès aux UI (NodePort L4, lecture seule)
#   bench/lima/run-phases.sh layers <p1,p2,…> # séquence ORDONNÉE par le moteur Python (ADR 0069) : socle + queue applicative
#   BANC_JETABLE=1 bench/lima/run-phases.sh rollback <phase>  # défait UNE phase (ns+CRD+node-side) pour la re-tester (ADR 0054) — DESTRUCTIF
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
# shellcheck source=bench/lima/lib.sh
. "${HERE}/lib.sh"
# shellcheck source=bench/lima/metrology.sh
. "${HERE}/metrology.sh"
# Lib PARTAGÉE du HEALTHCHECK cluster — MÊME source que bootstrap/state.sh. Les
# classify_* y sont PURES ; le banc collecte via "${KUBECTL[@]}" (kubectl
# --kubeconfig explicite, cible toujours sûre → pas de garde-fou de cible ici,
# ADR 0053) puis classe. Testée par bench/unit/health-classify.bats.
# shellcheck source=bootstrap/lib/health-classify.sh
. "${REPO}/bootstrap/lib/health-classify.sh"
# Primitives + fonctions pures du ROLLBACK PAR PHASE (ADR 0054, #274).
# shellcheck source=bench/lima/rollback-lib.sh
. "${HERE}/rollback-lib.sh"

# ── Table des nœuds (noms génériques — ADR 0023) ─────────────────────────────
# "nom:rôle". Défaut `multi-node-3` : 1 control-plane + 2 workers (quorum mon Ceph
# + ×3 réplication). SURCHARGEABLE par NODES_OVERRIDE (csv "nom:rôle,…") : c'est
# ainsi que `topology.py up` PILOTE les nœuds depuis la topologie active (inversion
# de frontière, ADR 0056 — la topologie décide, le harnais exécute). Le 1er nœud
# control devient le CP primaire (kubeconfig + cni.sh).
if [ -n "${NODES_OVERRIDE:-}" ]; then
    IFS=',' read -r -a NODES <<< "${NODES_OVERRIDE}"
else
    NODES=(
        "cp1:control"
        "node1:worker"
        "node2:worker"
    )
fi
# CP = 1er nœud `control` de NODES (primaire). Dérivé, pas codé en dur (suit l'override).
CP=""
for _entry in "${NODES[@]}"; do
    [ "${_entry##*:}" = control ] && { CP="${_entry%%:*}"; break; }
done
[ -n "${CP}" ] || CP="${NODES[0]%%:*}" # repli : 1er nœud si aucun rôle control explicite
unset _entry
# Port hôte du forward de l'API du control-plane (127.0.0.1:API_PORT → guest 6443).
API_PORT=6443

# Ressources par VM. RAM et DISQUE DÉRIVENT du profil (ADR 0046 : pas de valeur
# de profil codée en dur) :
#   - mode Ceph (WITH_CEPH=1) : 12 GiB RAM — un nœud porte OSD/mon Ceph + k8s +
#     CNPG + Dagster/Marquez + monitoring (chemin atlas-ceph). Pic mesuré ~9 GiB ;
#     Ceph sensible à la pression mémoire (OSD lents → boot/HEALTH qui traînent).
#   - mode léger (local-path) : 12 GiB RAM. Un banc atlas/banc.yaml MONO-NŒUD porte
#     la chaîne MLOps complète (monitoring Prometheus/Grafana/Loki + Argo CD + Gitea
#     + CNPG + registry + Dagster webserver+daemon + MLflow). 8 GiB ne suffit PAS :
#     dagster-daemon reste Pending/ProgressDeadlineExceeded (limits memory > 88 %,
#     mesuré le 2026-06-23). 12 GiB requis, comme le mode Ceph — c'est la CHARGE
#     applicative qui dimensionne, pas le backend de stockage.
# 12 GiB sur un hôte 48 GiB : marge OK pour macOS. Surchargeable via VM_MEMORY.
#
# DISQUE : 40 GiB par défaut (les DEUX backends). 20 GiB ne tenait que pour un banc
# LÉGER (socle/metrics) ; dès qu'on empile la chaîne applicative — Ceph+dataops, OU
# local-path+atlas (DataOps + MLflow + churn argocd) — l'ephemeral-storage du rootfs
# sature à 20 GiB → DiskPressure → évictions en cascade (postgres/rgw/repo-server/mlflow
# sous le seuil ~2 GiB ; 125 pods Evicted constatés en local-path le 2026-06-17, #391).
# 40 GiB partout (qcow2 thin-provisionné : n'occupe le disque hôte qu'à l'usage réel,
# donc gratuit pour un banc léger). Surchargeable via VM_DISK.
# CPU par VM. Surchargeable via VM_CPUS (comme VM_MEMORY/VM_DISK). Défaut 4 : un nœud
# qui porte la chaîne MLOps complète (Dagster webserver+daemon + monitoring + CNPG +
# MLflow…) sature 2 vCPU — la somme des requests.cpu dépasse l'allouable et le
# scheduler laisse des pods Pending (`Insufficient cpu`, vécu au banc mono-nœud :
# dagster-webserver non plaçable). 4 vCPU donne la marge.
VM_CPUS=${VM_CPUS:-4}
# 12 GiB pour les DEUX backends : la chaîne MLOps complète (dataops/mlflow) sature
# 8 GiB sur un nœud, indépendamment de Ceph vs local-path (mesuré le 2026-06-23).
VM_MEMORY_DEFAULT=12GiB
VM_MEMORY=${VM_MEMORY:-${VM_MEMORY_DEFAULT}}
VM_DISK=${VM_DISK:-40GiB}

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
# (bench/lima/runs/, cf. RESULTS.md). Reproductible — pas de saisie manuelle.
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

# derive_topology_label : étiquette de FORME dérivée de NODES (honnêteté de Run, ADR
# 0052) — REPLI quand le nom de stack n'est pas fourni (invocation bash directe, sans
# l'entrée topology.py). On compte les rôles `control`/`worker` de NODES :
#   1 control seul        → mono-node      ;  ≥2 control → ha-<n>cp
#   1 control + N workers → multi-node-<n> (défaut historique : multi-node-3 = 1+2)
derive_topology_label() {
    local entry role n_control=0 n_worker=0 total=${#NODES[@]}
    for entry in "${NODES[@]}"; do
        role=${entry##*:}
        case "${role}" in
            control) n_control=$((n_control + 1)) ;;
            *) n_worker=$((n_worker + 1)) ;;
        esac
    done
    if [ "${n_control}" -ge 2 ]; then
        printf 'ha-%dcp' "${n_control}"
    elif [ "${n_worker}" -eq 0 ]; then
        printf 'mono-node'
    else
        printf 'multi-node-%d' "${total}"
    fi
}

# Consigne le run complet dans l'historique versionné (#216) et, si Prometheus
# est déployé, y joint les métriques de coût échantillonnées (#217). Appelé en
# fin d'un run de chemin réussi. <total_s> = durée cumulée ; <profil> dérivé de WITH_CEPH.
record_full_run() {
    local total=$1 profil block topo
    profil=$(metro_profil "${WITH_CEPH:-0}")
    # `topologie:` = NOM de la stack (STACK_NAME, posé par `topology.py up`) — la CLÉ
    # que `last_run_for_topology` matche pour le verdict de fraîcheur PAR STACK. À
    # défaut (run bash direct), repli sur l'étiquette de FORME dérivée de NODES.
    topo="${STACK_NAME:-$(derive_topology_label)}"
    # Échantillonnage Prometheus sur la fenêtre du run (best-effort, non bloquant).
    block=$(METRO_METRICS_BLOCK='' metro_sample_prometheus "${total}" || true)
    # TARGET (chemin nommé courant, suffixe +hardening inclus) consigné pour la
    # fraîcheur PAR CHEMIN (ADR 0045 §6 / #244).
    METRO_METRICS_BLOCK="${block}" \
        metro_record_run "${profil}" "${topo}" "${total}" "${PHASE_DURATIONS}" "${TARGET:-}"
}

# Joue un playbook Ansible de plateforme (depuis l'hôte, kubeconfig banc) PUIS
# prouve son IDEMPOTENCE en le REJOUANT : un rôle idempotent doit donner
# `changed=0` au 2ᵉ passage (gate d'idempotence — décision « pas de Molecule, on
# prouve par le banc » ; attrape les changed_when:true fautifs, ADR 0051). Le
# verdict passe par la fonction PURE classify_idempotence (testée bats).
# Args : $1 = chemin du playbook (relatif à REPO), puis args -e supplémentaires.
run_ansible_phase() {
    local playbook=$1; shift
    # shellcheck source=bench/lima/dataops-assert.sh
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
# nodes_ready_count N — au MOINS N nœuds Ready. Utile en HA (ha-3cp) où les CP
# rejoignent un à un : le gate de chaque étape attend le compte attendu à ce
# stade (1 après l'init du primaire, 2 après cp2…), pas les ${#NODES[@]} finaux.
nodes_ready_count() { [ "$("${KUBECTL[@]}" get nodes --no-headers 2> /dev/null | grep -cw Ready)" -ge "${1:-1}" ]; }
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

# detect_storage_profile : DÉRIVE le profil de stockage de l'ÉTAT RÉEL du cluster
# (ADR 0065 : un état se détecte, il ne se re-saisit pas — drift L44 / #319). Pose
# STORAGE_SC / STORAGE_BACKING / STORAGE_ENDPOINT selon la StorageClass présente,
# AU LIEU de brancher sur WITH_CEPH dans chaque phase post-bootstrap
# (monitoring/dataops/gitops). Détection FIABLE ou refus franc : pas de profil par
# défaut silencieux (la leçon de L44).
#   - SC `rook-ceph-block-replicated` présente → profil Ceph (RGW) ;
#   - SC `local-path` présente → profil léger (SeaweedFS) ;
#   - aucune des deux → die (socle non monté ? cluster injoignable ?).
# L'exposition des UI est en L4 NodePort (ADR 0092), indépendante du profil de
# stockage — il n'y a plus de drapeau Gateway à dériver ici.
detect_storage_profile() {
    if "${KUBECTL[@]}" get sc rook-ceph-block-replicated -o name > /dev/null 2>&1; then
        STORAGE_SC=rook-ceph-block-replicated
        STORAGE_BACKING=rgw
        STORAGE_ENDPOINT=http://rook-ceph-rgw-datalake.rook-ceph:80
    elif "${KUBECTL[@]}" get sc local-path -o name > /dev/null 2>&1; then
        STORAGE_SC=local-path
        STORAGE_BACKING=seaweedfs
        STORAGE_ENDPOINT=http://seaweedfs.s3.svc.cluster.local:8333
    else
        die "profil de stockage indétectable : ni la SC 'rook-ceph-block-replicated' ni 'local-path' (socle monté ? cluster joignable ?)"
    fi
    log "  profil détecté : storageClass=${STORAGE_SC}, backing S3=${STORAGE_BACKING} (${STORAGE_ENDPOINT})"
}

# detect_hardening_state : DÉRIVE l'état de DURCISSEMENT de l'ÉTAT RÉEL de l'hôte
# (ADR 0065 §2 : le durcissement est un état CONSTATABLE, pas un flag à re-saisir).
# Constate via SSH (comme state.sh) les couches que phase_hardening pose sur le
# banc (tags `audit,detection` → auditd + fail2ban) et pose HARDENING_STATE :
#   - les deux actifs            → HARDENING_STATE=hardened (durci → +hardening) ;
#   - les deux inactifs/absents  → HARDENING_STATE=plain ;
#   - hôte INJOIGNABLE (SSH KO)  → die (« détection fiable ou refus franc », L44) ;
#   - état PARTIEL (un seul actif) → die (durcissement incohérent à corriger).
# WITH_HARDENING=1 reste l'INTENTION d'APPLIQUER sur un build neuf (run_hardening_
# if_requested) ; cette détection sert à dériver le suffixe TARGET de la RÉALITÉ.
detect_hardening_state() {
    local node="${CP}" auditd fail2ban verdict
    # 1. Sonder la JOIGNABILITÉ d'abord, séparément de l'état des unités : seul un
    # hôte injoignable doit `die` (illisible). Un paquet de durcissement ABSENT
    # (auditd/fail2ban non installé) est légitimement « inactif » → plain, pas
    # `unknown` (sinon un hôte plain ferait échouer la détection selon la version
    # de systemd qui rend ''/'unknown' pour une unité inconnue).
    if ! vm_sh "${node}" true > /dev/null 2>&1; then
        auditd=unknown
        fail2ban=unknown
    else
        # SSH OK : `is-active` rend active/inactive/failed/unknown sur stdout. Tout
        # ce qui n'est pas `active` (inactif, échoué, absent) compte comme inactif.
        auditd=$(vm_sh "${node}" systemctl is-active auditd 2> /dev/null || true)
        fail2ban=$(vm_sh "${node}" systemctl is-active fail2ban 2> /dev/null || true)
        [ "${auditd}" = active ] || auditd=inactive
        [ "${fail2ban}" = active ] || fail2ban=inactive
    fi
    verdict=$(classify_hardening_signal "${auditd}" "${fail2ban}")
    case "${verdict%%|*}" in
        ok)
            case "${verdict#*|}" in
                hardened*) HARDENING_STATE=hardened ;;
                *)         HARDENING_STATE=plain ;;
            esac
            log "  durcissement détecté : ${HARDENING_STATE} (auditd=${auditd}, fail2ban=${fail2ban})" ;;
        *) die "détection du durcissement : ${verdict#*|}" ;;
    esac
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

    # Interface L2 du réseau user-v2 (LB-IPAM/CNI), dérivée du banc (ADR 0023).
    local l2_if
    l2_if=$(vm_uservv2_iface "${CP}")
    [ -n "${l2_if}" ] || die "${CP} : interface user-v2 introuvable"

    # ORCHESTRATION des 6 playbooks du socle DÉLÉGUÉE à Python (« Python parle Ansible »,
    # ADR 0063 ; migration de bootstrap_node_sequence). topology.py bootstrap-seq lance
    # checks→…→join-workers via runner.launch_phase, puis rappelle ICI `ha-cni` (CNI +
    # CRDs GW API + kubeconfig) — qui reste du bash (Cilium dans la VM, ADR 0049). Le
    # provisioning VM, l'inventaire (write_inventory) et la dérivation cp_ip/iface
    # restent au bash ; la SÉQUENCE et le fail-fast sont en Python testé (test_bootstrap).
    uv run python "${REPO}/scripts/topology.py" bootstrap-seq \
        --cp-ip "${cp_ip}" --l2-iface "${l2_if}" --inventory "${INVENTORY}" \
        || die "bootstrap : socle k8s (orchestration Python) en échec"

    # GATE : tous les nœuds attendus (${#NODES[@]}) Ready.
    log "Attente des ${#NODES[@]} nœud(s) Ready (max 5 min)"
    retry 300 10 nodes_ready_all \
        || die "moins de ${#NODES[@]} nœud(s) Ready : $("${KUBECTL[@]}" get nodes 2>&1)"
    ok "${#NODES[@]} nœud(s) Ready"
    "${KUBECTL[@]}" get nodes -o wide
}

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
        bash "${REPO}/bench/scenarios/06-object-store-smoke.sh" \
        || die "smoke-test S3 (RGW) en échec — voir la sortie ci-dessus"
    ok "smoke-test S3 réussi (PUT/GET/DELETE sur le RGW Ceph)"
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
    # shellcheck source=bench/lima/dataops-assert.sh
    . "${HERE}/dataops-assert.sh"
    log "Phase dataops — chaîne DataOps via Ansible (registry → CNPG → Dagster → Marquez)"

    # Le playbook tourne depuis l'hôte : kubernetes.core lit ce KUBECONFIG ;
    # storageClass banc = rook-ceph-block-replicated (défaut prod, mode Ceph).
    # Le CA TLS (SSL_CERT_FILE, drift L23) est résolu et posé PAR le playbook
    # lui-même (pré-tâche certifi) — avec le bon interpréteur Python.
    # build_emitter_image=true : le banc build aussi l'émetteur OpenLineage jetable
    # (harnais e2e, ADR 0022) requis par la preuve lineage ci-dessous — JAMAIS en
    # prod (défaut false). Drift L31.
    # Profil de stockage/backing DÉTECTÉ du cluster (ADR 0035/0036/0065), comme
    # monitoring : SC rook-ceph présente → Ceph (backups CNPG → RGW) ; sinon
    # local-path → léger (backups CNPG → SeaweedFS, posé par `monitoring`). Permet
    # la chaîne DataOps SANS Ceph (banc léger, ADR 0036).
    # DÉPENDANCE (ADR 0045) : en mode léger, `dataops` ne déploie PAS SeaweedFS —
    # il en CONSOMME l'endpoint. Le backing doit donc être posé AVANT (par
    # `monitoring`). Les chemins `atlas`/`cluster` garantissent cet ordre ;
    # lancer `dataops` seul en léger sans `monitoring` préalable échouerait.
    # Profil DÉTECTÉ du cluster (ADR 0065 — plus de WITH_CEPH, #319/drift L44).
    detect_storage_profile

    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/dataops.yaml" \
        -e dataops_k8s_host=localhost \
        -e build_emitter_image=true \
        -e "registry_storage_class=${STORAGE_SC}" \
        -e "cnpg_storage_class=${STORAGE_SC}" \
        -e "cnpg_s3_backing=${STORAGE_BACKING}" \
        -e "cnpg_s3_endpoint=${STORAGE_ENDPOINT}" \
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

    log "Consigner ce run dans bench/lima/RESULTS.md (honnêteté des Runs, ADR 0023)."
}

# ── Phase gitops — socle GitOps : Gitea (forge) + Argo CD (moteur) ───────────
# Déploie le socle GitOps via bootstrap/gitops.yaml (ADR 0022/0044) : Gitea
# (forge git intra-banc air-gapped) puis Argo CD (moteur). INFRA, posée par
# Ansible (anti-bootstrap-circulaire). Profil banc atlas = local-path (ADR 0044,
# pas de Ceph). L'UI Argo CD est exposée en L4 NodePort (ADR 0092), sans
# dépendance cert-manager/Gateway — appliquée inconditionnellement.
#
# L'INIT du dépôt Gitea (org + repo + seed atlas + webhook) est l'étape suivante
# (test e2e, #231) — hors de cette phase qui ne fait que poser le socle.
phase_gitops() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase gitops — socle GitOps via Ansible (Gitea → Argo CD)"

    # storageClass du PVC Gitea : SUIT le profil DÉTECTÉ du cluster (comme
    # dataops/monitoring). L'exposition UI est en NodePort (ADR 0092), sans drapeau.
    detect_storage_profile
    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/gitops.yaml" \
        -e dataops_k8s_host=localhost \
        -e "gitea_storage_class=${STORAGE_SC}" \
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
    # shellcheck source=bench/lima/gitea-init.sh
    . "${HERE}/gitea-init.sh"
    main || die "gitea-init : init du dépôt Gitea échouée"
    ok "🎉 dépôt Gitea initialisé — Application atlas-workflows posée (réconciliation Argo CD)"
    log "Preuve e2e : bench/scenarios/27-gitops-workflow-deploy.sh"
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
# 0016/0036). Profil de stockage DÉTECTÉ du cluster (ADR 0065, plus de WITH_CEPH) :
#   - SC rook-ceph présente : storageClass rook-ceph, Loki en profil s3 → RGW ;
#   - sinon SC local-path   : storageClass local-path, Loki en s3 → SeaweedFS.
# Le profil léger NE requiert PAS Ceph (testable en banc rapide, ADR 0035/0036).
phase_monitoring() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase monitoring — Prometheus + Grafana + Loki (via Ansible)"

    # Profil par topologie (ADR 0035/0036) : Loki est TOUJOURS en S3 (même code
    # que prod) ; seul le backing change — SeaweedFS en banc léger (S3 sans Ceph),
    # RGW Ceph en mode Ceph.
    # Profil DÉTECTÉ du cluster (ADR 0065 — plus de WITH_CEPH, #319/drift L44).
    detect_storage_profile

    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/monitoring.yaml" \
        -e dataops_k8s_host=localhost \
        -e "monitoring_storage_class=${STORAGE_SC}" \
        -e "loki_storage_class=${STORAGE_SC}" \
        -e "loki_s3_backing=${STORAGE_BACKING}" \
        -e "loki_s3_endpoint=${STORAGE_ENDPOINT}" \
        || die "monitoring.yaml : échec du déploiement de l'observabilité"
    ok "🎉 observabilité déployée — Prometheus + Grafana + Loki (S3/${STORAGE_BACKING}) Ready"
}

# ── Phase mlflow — suivi de modèles (ADR 0082, layer autonome) ───────────────
# Jumeau de monitoring/dataops : déploie via bootstrap/mlflow.yaml (build image
# maison node-side + serveur MLflow k8s). Backend store = base CNPG `mlflow` (posée
# par dataops, prérequis du graphe) ; artefact store S3 dont le BACKING est DÉTECTÉ
# du cluster (ADR 0036/0065) — SeaweedFS en banc léger, RGW Ceph en mode Ceph,
# parité avec loki_s3_backing. Sans cette fonction, l'arm `layers` appelait
# `phase_mlflow` inexistant → rc=127 (le montage `layers [...,mlflow]` échouait, alors
# que `nestor next` passait car il route mlflow vers son playbook autonome côté Python).
phase_mlflow() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase mlflow — serveur de suivi de modèles (backend CNPG + artefacts S3, via Ansible)"

    # Profil de backing S3 DÉTECTÉ du cluster (ADR 0065), comme monitoring/dataops.
    detect_storage_profile

    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/mlflow.yaml" \
        -e dataops_k8s_host=localhost \
        -e "mlflow_s3_backing=${STORAGE_BACKING}" \
        -e "mlflow_s3_endpoint=${STORAGE_ENDPOINT}" \
        || die "mlflow.yaml : échec du déploiement du suivi de modèles"
    ok "🎉 MLflow déployé — suivi de modèles (S3/${STORAGE_BACKING}) Ready"
}

# phase_portal — portail d'accès aux UI (ADR 0091/0092), layer AUTONOME. Build de
# l'image maison (code + contrat embarqués) puis apply k8s (RBAC lecture seule + Deploy
# durci + Service NodePort + NetworkPolicies). Modèle phase_mlflow MAIS plus simple :
# le portail n'a NI stockage NI S3 → PAS de detect_storage_profile. Il observe les
# Services des autres couches à la demande (SKIP neutre si rien d'exposé) → marche dès
# le socle ; placé tard dans les chemins (après les couches qu'il liste).
phase_portal() {
    preflight
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — lancer 'bootstrap' d'abord"
    [ -f "${INVENTORY}" ] || die "inventaire absent — lancer 'bootstrap' d'abord"
    log "Phase portal — portail d'accès aux UI (build image maison + apply k8s, via Ansible)"

    KUBECONFIG="${KUBECONFIG_LOCAL}" ansible-playbook -i "${INVENTORY}" \
        "${REPO}/bootstrap/portal.yaml" \
        -e dataops_k8s_host=localhost \
        || die "portal.yaml : échec du déploiement du portail"
    ok "🎉 Portail déployé — accès aux UI (NodePort) Ready"
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
# bench/lima/RESULTS.md. Tant que l'image n'est pas poussée, ce maillon échoue
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

# ── Down — détruit VMs + disques nommés ──────────────────────────────────────
# phase_down [vm…] — détruit les VMs nommées (+ leurs disques). Sans argument :
# les NODES du harnais (banc complet). AVEC arguments (noms de VM) : seulement
# celles-ci — c'est ainsi que `topology.py destroy` cible les VMs de la STACK active
# (déléguée ici, limactl reste du bash, ADR 0049). Ne retire le WORKDIR que pour un
# démontage COMPLET (sans liste explicite).
phase_down() {
    require_lima
    local targets=("$@") vm d
    if [ ${#targets[@]} -eq 0 ]; then
        local entry
        for entry in "${NODES[@]}"; do targets+=("${entry%%:*}"); done
        log "Destruction du banc Lima (VMs + disques nommés)"
    else
        log "Destruction des VMs : ${targets[*]} (+ disques nommés)"
    fi
    for vm in "${targets[@]}"; do
        lima_delete_node "${vm}"
        for d in $(node_disks "${vm}"); do
            lima_disk_delete "${d}"
        done
    done
    # WORKDIR (inventaire/artefacts du banc) : retiré seulement pour un démontage
    # complet — une destruction ciblée (stack) ne touche pas l'état du harnais.
    [ $# -eq 0 ] && rm -rf "${WORKDIR}"
    ok "VMs démontées — rien ne subsiste"
}

# ── Préfixe SOCLE des chemins (ADR 0045) ────────────────────────────────────
# Les CHEMINS NOMMÉS AGRÉGÉS (socle/atlas/storage-real/cluster-dataops/atlas-ceph/ha-3cp)
# ont été RETIRÉS : le moteur Python `nestor` (ADR 0097) porte désormais l'orchestration
# (séquence + gates + fraîcheur). Ne reste que l'arm GÉNÉRIQUE `layers <seq>` (filet bash
# `--engine=bash`), qui réutilise ce préfixe socle : il monte d'abord le SOCLE (up →
# bootstrap [+ ceph+sc en mode Ceph], avec cache #219) via run_socle pour préserver le
# cache + le verdict SOCLE_BUILT/record_if_fresh, applique le durcissement orthogonal
# (WITH_HARDENING=1, #240) juste après, puis boucle sur la queue applicative ordonnée par
# Python (storage-simple → metrics → monitoring → … chaque phase = un arm unitaire).
#
# Variable globale `SOCLE_BUILT` (0/1) : posée par run_socle, lue à la fin pour
# ne consigner QUE les runs from-scratch (drift L49).
SOCLE_BUILT=0

# Monte le socle, avec cache du socle (#219). Pose SOCLE_BUILT=1 si le socle a
# RÉELLEMENT été bâti (pas réutilisé).
#
# Le socle de BASE = up → bootstrap (k8s + CNI SEULS) : le STOCKAGE n'en fait PAS
# partie (ADR 0039 : `storage` ∈ profil store, pas base ; aligné sur plan.py). En
# mode Ceph le socle pose ceph+sc (indissociable de ce backend). En local-path, la
# couche `storage-simple` est posée SÉPARÉMENT par la queue de `layers` (phase unitaire),
# pas par le socle (profil base).
run_socle() {
    local profil
    profil=$(metro_profil "${WITH_CEPH:-0}")
    SOCLE_BUILT=0
    if metro_cache_valid "${profil}"; then
        ok "socle réutilisé depuis le cache (clé inchangée) — up/bootstrap sautés (#219)"
        log "ℹ️  Forcer un rebuild from-scratch (preuve ADR 0034) : NO_CACHE=1 nestor up (ou $0 layers …)"
        return 0
    fi
    time_phase up phase_up
    time_phase bootstrap phase_bootstrap
    if [ "${WITH_CEPH:-0}" = 1 ]; then
        time_phase ceph phase_ceph
        time_phase sc phase_sc
        log "🎉 Socle monté (mode Ceph) : up → bootstrap → ceph → storageClasses."
    else
        log "🎉 Socle de base monté (k8s + CNI) : up → bootstrap (stockage = couche store+)."
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

# Axe ORTHOGONAL durcissement (#240, ADR 0045 §3) : WITH_HARDENING=1 est l'INTENTION
# d'APPLIQUER le hardening hôte (secure.yml) sur N'IMPORTE QUEL chemin, juste après
# le socle. Le suffixe `+hardening` de TARGET, lui, DÉRIVE de l'ÉTAT RÉEL de l'hôte
# (ADR 0065 §2 : un état se détecte, pas se re-saisit) — pas du flag : ainsi un
# re-jeu/roundtrip contre un hôte DÉJÀ durci retrouve `+hardening` sans repasser le
# flag, et le run consigné distingue les deux variantes par la réalité (ADR 0042).
run_hardening_if_requested() {
    # Intention : appliquer le durcissement sur un build neuf (no-op si déjà fait —
    # phase_hardening est idempotente via Ansible).
    if [ "${WITH_HARDENING:-0}" = 1 ]; then
        time_phase hardening phase_hardening
    fi
    # État : le suffixe reflète ce que l'hôte EST, détecté via SSH (refus franc si
    # injoignable/incohérent). Couvre aussi un hôte durci hors de CE run.
    detect_hardening_state
    # `if` (et non `[ … ] && …`) : sous `set -e`, un `[ … ] && …` FAUX en DERNIÈRE
    # instruction d'une fonction propage son rc=1 → abort du chemin alors que tout a
    # réussi (8e/9e bug du run : socle monté, nœud Ready, puis rc=1 sur l'hôte `plain`).
    if [ "${HARDENING_STATE:-plain}" = hardened ]; then
        TARGET="${TARGET}+hardening"
    fi
}

# ha_cni VIP_IFACE LB_PREFIX — pose Cilium sur le CP primaire (rappelé par la
# sous-commande Python ha-3cp ; la CNI reste du bash, ADR 0049). Dérive la plage
# LB-IPAM du /24 du primaire ; fetch le kubeconfig local après.
phase_ha_cni() {
    local vip_iface=$1
    # Exposition L4 NodePort (ADR 0092, supersede 0071) : plus de Gateway L7 ni
    # LB-IPAM. cni.sh pose Cilium en L4 pur (NodePort en eBPF par kubeProxyReplacement)
    # et retire tout CR d'exposition résiduel. Aucune variable d'exposition à passer ;
    # les CRD Gateway API ne sont plus pré-installées (plus aucun objet Gateway).
    # vip_iface (argument conservé pour la signature ha-cni) n'est plus utilisé ici.
    : "${vip_iface:-}"
    run_cni "${CP}"
    fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" cluster-banc
}

# NB : l'orchestration HA (bootstrap primaire, gates VIP/etcd, promotion des CP) vit
# désormais ENTIÈREMENT en PYTHON (nestor/path.py via runner.launch_phase, ADR 0063/0097) —
# l'ancien chemin bash `ha-3cp` a été retiré (le moteur Python remplace l'orchestration) ;
# seuls le provisioning VM et la CNI (phase_ha_cni) restent du bash ici (ADR 0049).

# emit_facts — CONTRAT MACHINE pour topology.py (inversion de frontière, ADR 0049/0056).
# Imprime sur stdout, en KEY=VALUE byte-stable, les faits du banc que Python consomme :
# l'IP user-v2 du CP primaire (advertiseAddress), son interface L2 (LB-IPAM/CNI), et la
# VIP dérivée si la topo est HA (> 1 nœud control). Réutilise les briques irréductibles
# vm_uservv2_ip/iface (limactl shell). Python DEMANDE ces faits ; le bash ne pilote plus.
emit_facts() {
    require_lima
    local cp_ip l2_if n_control=0 entry
    cp_ip=$(vm_uservv2_ip "${CP}")
    [ -n "${cp_ip}" ] || die "${CP} : pas d'IP user-v2 (banc non provisionné ?)"
    l2_if=$(vm_uservv2_iface "${CP}")
    [ -n "${l2_if}" ] || die "${CP} : interface user-v2 introuvable"
    printf 'CP_IP=%s\n' "${cp_ip}"
    printf 'L2_IFACE=%s\n' "${l2_if}"
    # HA = plus d'un nœud `control` dans NODES → on émet la VIP (le moteur HA Python la consomme).
    for entry in "${NODES[@]}"; do
        [ "${entry##*:}" = control ] && n_control=$((n_control + 1))
    done
    if [ "${n_control}" -gt 1 ]; then
        printf 'VIP=%s\n' "${cp_ip%.*}.40"
        printf 'VIP_IFACE=%s\n' "${l2_if}"
    fi
}

# ── Dispatch ─────────────────────────────────────────────────────────────────
case "${1:-}" in
    up) time_phase up phase_up ;;
    bootstrap) time_phase bootstrap phase_bootstrap ;;
    storage-simple) time_phase storage-simple phase_storage_simple ;;
    metrics-server) time_phase metrics-server phase_metrics_server ;;
    datalake) time_phase datalake phase_datalake ;;
    smoke-s3) time_phase smoke-s3 phase_smoke_s3 ;;
    hardening) time_phase hardening phase_hardening ;;
    dataops) time_phase dataops phase_dataops ;;
    gitops) time_phase gitops phase_gitops ;;
    gitops-seed) time_phase gitops-seed phase_gitops_seed ;;
    monitoring) time_phase monitoring phase_monitoring ;;
    mlflow) time_phase mlflow phase_mlflow ;;
    portal) time_phase portal phase_portal ;;
    access) phase_access "${@:2}" ;;
    ceph) time_phase ceph phase_ceph ;;
    sc) time_phase sc phase_sc ;;
    kubeconfig) preflight; fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" cluster-banc ;;
    # ── layers : séquence ARBITRAIRE de phases, ORDONNÉE par topology.py (ADR 0069). ─
    # L'arm générique des paliers SANS preset dédié (ex. [gitops, metrics]). Python
    # fournit l'ordre (resolve_layers, tri topo du graphe atomique) ; bash EXÉCUTE,
    # ne re-trie PAS (ADR 0063 : bash exécute, Python décide). Le préfixe socle
    # (up,bootstrap[,ceph,sc]) est délégué à run_socle pour préserver le cache #219 +
    # le verdict SOCLE_BUILT/record_if_fresh ; le reste boucle sur les phases unitaires.
    layers)
        [ -n "${2:-}" ] || die "usage : layers <phase1,phase2,…> (séquence ordonnée par topology.py)"
        TARGET=layers
        chemin_prelude
        run_start=$(date +%s)
        IFS=',' read -r -a _seq <<< "$2"
        # Backend dérivé du préfixe : `ceph` dans la séquence ⇒ socle Ceph.
        case ",$2," in *",ceph,"*) WITH_CEPH=1 ;; esac
        run_socle
        run_hardening_if_requested
        # Sauter le préfixe socle déjà monté par run_socle (up/bootstrap[,ceph,sc]) ;
        # boucler sur la queue applicative restante (chaque phase = un arm unitaire).
        for _p in "${_seq[@]}"; do
            case "${_p}" in
                up | bootstrap | ceph | sc) continue ;; # posés par run_socle
                *) time_phase "${_p}" "phase_${_p//-/_}" ;;
            esac
        done
        log "🎉 Chemin 'layers' : socle → ${2//,/ → }."
        record_if_fresh "${run_start}"
        ;;
    # ha-cni : rappel interne de la sous-commande Python ha-3cp (la CNI reste bash,
    # ADR 0049). Args : <vip_iface>. (Le préfixe LB-IPAM n'est plus requis : le
    # Gateway s'expose en hostNetwork, ADR 0071 — plus de pool d'IP au banc.)
    ha-cni) [ -n "${2:-}" ] || die "usage : ha-cni <vip_iface>"; phase_ha_cni "$2" ;;
    # facts — contrat machine : imprime CP_IP/L2_IFACE (+ VIP/VIP_IFACE si HA) que
    # topology.py consomme (inversion de frontière, ADR 0049/0056). Brique LUE par Python.
    facts) emit_facts ;;
    # inventory <control_csv> [workers_csv] — réécrit l'inventaire (control + workers).
    # Brique générique appelée par topology.py (write_inventory reste bash, byte-stable).
    inventory) [ -n "${2:-}" ] || die "usage : inventory <control_csv> [workers_csv]"; mkdir -p "${WORKDIR}"; write_inventory "${INVENTORY}" "$(echo "$2" | tr ',' ' ')" "$(echo "${3:-}" | tr ',' ' ')" ;;
    # ha-inventory <cp1,cp2,…> — ALIAS de compat (= inventory <cp> sans workers, HA
    # hyperconvergé). Conservé le temps de la transition (rappel ha-3cp). Préférer `inventory`.
    ha-inventory) [ -n "${2:-}" ] || die "usage : ha-inventory <cp1,cp2,…>"; mkdir -p "${WORKDIR}"; write_inventory "${INVENTORY}" "$(echo "$2" | tr ',' ' ')" "" ;;
    down) phase_down "${@:2}" ;;
    # Rollback d'UNE phase (ADR 0054, #274) : défait ce que `<phase>` a monté.
    # BANC_JETABLE=1 requis (destructif total). Ex : BANC_JETABLE=1 ... rollback ceph
    rollback) [ -n "${2:-}" ] || die "usage : rollback <phase> (ceph|sc|datalake|metrics-server|monitoring|dataops|gitops|gitops-seed)"; phase_rollback "$2" ;;
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -40
        exit 2
        ;;
esac
