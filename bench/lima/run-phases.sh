#!/usr/bin/env bash
#
# Harnais node-side du banc léger Lima — sur des VMs Lima (vrai noyau, SSH natif) au
# lieu de VirtualBox. Stockage MODULAIRE : local-path (rapide) par défaut, Ceph optionnel.
#
# ⚠️ L'ORCHESTRATION (séquence des couches, gates de santé, fraîcheur, HA) ET LE MONTAGE
# DES COUCHES vivent désormais ENTIÈREMENT dans le MOTEUR PYTHON `nestor` (scripts/topology.py
# + nestor/path.py, ADR 0063/0097) : c'est l'entrée NORMALE (`nestor up/next/remove`) et le
# SEUL moteur. Le filet bash redondant (chemins nommés agrégés, arm `layers <seq>`, phases
# applicatives `phase_*`) a été RETIRÉ — plus de double source de vérité. Ce script ne porte
# plus que les BRIQUES IRRÉDUCTIBLES node-side que le moteur APPELLE (provisioning VM, CNI,
# inventaire, faits, kubeconfig, accès dev, démontage) + le rollback par phase (ADR 0049/0054).
#
# À lancer depuis le POSTE DE CONTRÔLE (Mac), pas dans une VM.
#
# Usage (briques irréductibles node-side ; l'entrée normale est `nestor`) :
#   ── Briques node-side APPELÉES par le moteur Python (ADR 0049/0056) ──
#   bench/lima/run-phases.sh up             # VMs + (si WITH_CEPH=1) disques bruts + gate vd* (#235)
#   bench/lima/run-phases.sh inventory <control_csv> [workers_csv] # (ré)écrit l'inventaire (write_inventory byte-stable)
#   bench/lima/run-phases.sh facts          # contrat machine : imprime CP_IP/L2_IFACE (+ VIP si HA)
#   bench/lima/run-phases.sh cni            # pose Cilium (L4 NodePort) + fetch kubeconfig banc
#   bench/lima/run-phases.sh kubeconfig     # (ré)exporte le kubeconfig banc
#   bench/lima/run-phases.sh down [vm…]     # détruit les VMs + disques nommés
#   (rollback d'UNE phase : porté en Python — `nestor remove <phase>`, ADR 0101)
#
# Pré-requis poste : limactl (Lima ≥ 2.0), ansible-playbook, kubectl, python3.
#
# Pourquoi Lima (vs kind figé en 1.31 / Vagrant lourd) : ADR 0006.
set -euo pipefail

# Intention de cible (ADR 0053 (c)) : ce script ne pilote QUE le banc Lima. On
# déclare l'intention `bench` pour TOUS les ansible-playbook lancés d'ici → le
# garde-fou du rôle audit-log refuse un inventaire prod passé par erreur.
export EXPECTED_TARGET_KIND=bench

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=bench/lima/lib.sh
. "${HERE}/lib.sh"
# Le ROLLBACK est porté en Python (ADR 0101) : la destruction d'une couche passe par
# `nestor remove --discover` (k8s par découverte + node-side Ceph via _node_exec_script) —
# rollback-lib.sh + metrology.sh sont retirés, leur logique pure vit dans nestor/ (graph.py,
# history.py). run-phases.sh ne garde que le MONTAGE des phases (bash node-side légitime).

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

# ── Emplacements (gitignorés : artefacts de run) ─────────────────────────────
# Lima présente ses disques bruts (mode Ceph) en virtio-blk → /dev/vd* : vda = OS ;
# vdb/vdc/vdd = HDD data ; vde = block.db ; vdf = cidata Lima (ignoré). `phase_up`
# gate sur leur présence. (Les surcharges Ceph CEPH_*/DATA_DEVICE_GLOB consommées par
# l'ancienne phase `ceph` ont été retirées avec le filet bash — montage en Python.)
WORKDIR="${HERE}/.work"
INVENTORY="${WORKDIR}/inventory.yaml"
KUBECONFIG_LOCAL="${WORKDIR}/kubeconfig"

# ── Métriques de run (matériel + temps par phase) ────────────────────────────
# Consignées dans WORKDIR/metrics.txt à reporter en en-tête du log archivé
# (bench/lima/runs/, cf. RESULTS.md). Reproductible — pas de saisie manuelle.
METRICS="${WORKDIR}/metrics.txt"
# Durées par phase au format TSV (nom<TAB>secondes), écrit par time_phase. Éphémère
# (.work/) — la consignation dans l'historique versionné (#216) vit côté moteur Python.
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

# Noms des disques nommés Lima d'un nœud (data hdd1..N + blockdb).
node_disks() {
    local vm=$1 i
    for i in $(seq 1 "${HDD_COUNT}"); do echo "${vm}-hdd${i}"; done
    echo "${vm}-blockdb"
}

preflight() {
    require_lima
    need ansible-playbook
    need kubectl
    need python3
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


# phase_cni — pose Cilium (CNI) sur le CP primaire puis fetch le kubeconfig banc.
# Geste 100 % CNI (le vestige HA `ha-cni` a été renommé : aucune VIP/iface ici). Le
# moteur Python le rappelle via l'arm `cni` (la CNI reste du bash, ADR 0049).
phase_cni() {
    # Exposition L4 NodePort (ADR 0092, supersede 0071) : plus de Gateway L7 ni
    # LB-IPAM. cni.sh pose Cilium en L4 pur (NodePort en eBPF par kubeProxyReplacement)
    # et retire tout CR d'exposition résiduel. Aucune variable d'exposition à passer ;
    # les CRD Gateway API ne sont plus pré-installées (plus aucun objet Gateway).
    run_cni "${CP}"
    fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" cluster-banc
}

# NB : l'orchestration HA (bootstrap primaire, gates VIP/etcd, promotion des CP) vit
# désormais ENTIÈREMENT en PYTHON (nestor/path.py via runner.launch_phase, ADR 0063/0097) —
# l'ancien chemin bash `ha-3cp` a été retiré (le moteur Python remplace l'orchestration) ;
# seuls le provisioning VM et la CNI (phase_cni) restent du bash ici (ADR 0049).

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
# SEULES les briques node-side IRRÉDUCTIBLES que le moteur Python APPELLE (ADR
# 0049/0056) + le rollback par phase (ADR 0054). Le montage des couches (séquence,
# gates, idempotence) vit ENTIÈREMENT dans le moteur Python (un seul moteur, le filet
# bash `layers`/phases applicatives a été retiré).
case "${1:-}" in
    up) time_phase up phase_up ;;
    kubeconfig) preflight; fetch_kubeconfig_node "${CP}" "${KUBECONFIG_LOCAL}" "${API_PORT}" cluster-banc ;;
    # cni : rappel interne du moteur Python (la CNI reste bash, ADR 0049). Pose Cilium
    # (L4 NodePort) + fetch le kubeconfig banc. Aucun argument (geste 100 % CNI : le
    # vestige `ha-cni <vip_iface>` a été renommé — plus de VIP/iface au banc).
    cni) phase_cni ;;
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
    # Rollback d'UNE phase : porté en Python (ADR 0101). Utiliser `nestor remove <phase>`
    # (destruction par découverte : k8s + node-side Ceph). L'arm bash `rollback` est retiré.
    *)
        grep -E '^#( |$)' "$0" | sed -E 's/^# ?//' | head -40
        exit 2
        ;;
esac
