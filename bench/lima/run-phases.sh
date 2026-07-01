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
#   bench/lima/run-phases.sh up             # VMs + disques bruts DÉCLARÉS par nœud + gate (ADR 0102 volet C)
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
# SURCHARGEABLE par NODES_OVERRIDE : c'est ainsi que `topology.py up` PILOTE les nœuds
# depuis la topologie active (inversion de frontière, ADR 0056/0102 — la topologie
# décide PAR NŒUD, le harnais exécute). Le 1er nœud control devient le CP primaire
# (kubeconfig + cni.sh).
#
# FORMAT ENRICHI (ADR 0102 volet C) — nœuds séparés par `;`, chaque entrée =
#   `nom|role|cpus,memory,disk|disque1,disque2,…`  (un disque = `name=size=role`).
# Le 4e champ VIDE = nœud sans disque brut (« mode Ceph » = présence de disques
# déclarés, plus de WITH_CEPH). Ex :
#   node1|control|4,12GiB,40GiB|vdb=10GiB=data,vdd=5GiB=metadata;node2|worker|4,12GiB,40GiB|
#
# DÉFAUT (lancement NU, sans override) : format court `nom:rôle` (ressources par
# défaut ci-dessous, pas de disques). phase_up/phase_down DÉTECTENT le format par la
# présence d'un `|` dans l'entrée — le lancement nu reste possible sans NODES_OVERRIDE.
if [ -n "${NODES_OVERRIDE:-}" ]; then
    IFS=';' read -r -a NODES <<< "${NODES_OVERRIDE}"
else
    NODES=(
        "cp1:control"
        "node1:worker"
        "node2:worker"
    )
fi

# node_name <entry> — nom du nœud, quel que soit le format (riche `nom|…` ou court `nom:rôle`).
node_name() {
    local entry=$1
    case "${entry}" in
        *"|"*) printf '%s' "${entry%%|*}" ;;
        *) printf '%s' "${entry%%:*}" ;;
    esac
}

# node_role <entry> — rôle du nœud (control|worker), quel que soit le format.
node_role() {
    local entry=$1 rest
    case "${entry}" in
        *"|"*) rest="${entry#*|}"; printf '%s' "${rest%%|*}" ;;
        *) printf '%s' "${entry##*:}" ;;
    esac
}

# CP = 1er nœud `control` de NODES (primaire). Dérivé, pas codé en dur (suit l'override).
CP=""
for _entry in "${NODES[@]}"; do
    [ "$(node_role "${_entry}")" = control ] && { CP="$(node_name "${_entry}")"; break; }
done
[ -n "${CP}" ] || CP="$(node_name "${NODES[0]}")" # repli : 1er nœud si aucun rôle control explicite
unset _entry
# Port hôte du forward de l'API du control-plane (127.0.0.1:API_PORT → guest 6443).
API_PORT=6443

# Ressources VM par DÉFAUT (fallback). ADR 0102 volet C : les ressources sont PAR
# NŒUD, portées par NODES_OVERRIDE (3e champ `cpus,memory,disk`). Ces défauts ne
# servent QU'au lancement NU (sans override) ou à un nœud dont le champ ressources
# est vide. Valeurs dérivées de l'expérience banc (ADR 0046 : pas de profil codé) :
#   - CPU 4 : un nœud qui porte la chaîne MLOps complète (Dagster webserver+daemon +
#     monitoring + CNPG + MLflow…) sature 2 vCPU (pods Pending `Insufficient cpu`,
#     vécu au banc mono-nœud). 4 vCPU donne la marge.
#   - RAM 12 GiB : la chaîne MLOps complète sature 8 GiB (dagster-daemon Pending/
#     ProgressDeadlineExceeded, mesuré le 2026-06-23), indépendamment de Ceph vs
#     local-path — c'est la CHARGE applicative qui dimensionne, pas le backend.
#   - DISQUE 40 GiB : 20 GiB sature l'ephemeral-storage du rootfs dès qu'on empile la
#     chaîne applicative → DiskPressure → évictions en cascade (125 pods Evicted en
#     local-path le 2026-06-17, #391). 40 GiB (qcow2 thin : gratuit pour un banc léger).
VM_CPUS=${VM_CPUS:-4}
VM_MEMORY=${VM_MEMORY:-12GiB}
VM_DISK=${VM_DISK:-40GiB}

# ── Emplacements (gitignorés : artefacts de run) ─────────────────────────────
# Lima présente ses disques bruts en virtio-blk → /dev/vd* : vda = OS ; les disques
# DÉCLARÉS par le nœud (NODES_OVERRIDE) sont attachés dans l'ordre → vdb, vdc… ; le
# dernier vd* est le cidata Lima (iso9660, ignoré). `phase_up` crée les disques
# déclarés et gate sur leur présence (fin de WITH_CEPH — la topo pilote, ADR 0102).
WORKDIR="${HERE}/.work"
INVENTORY="${WORKDIR}/inventory.yaml"
# Kubeconfig du banc = `.kubeconfigs/<stack>.config` à la RACINE du dépôt (ADR 0102 volet B) :
# un banc EST une stack (nommée par le FICHIER de sa topologie, `stack_id`), son kubeconfig
# vit à l'emplacement UNIQUE nommé par la stack (in-repo, gitignoré fail-safe). C'est PYTHON
# qui décide le chemin (topology.py `_bench_kubeconfig_path(<stack>)` = `.kubeconfigs/<stack>.config`,
# dérivé du nom de fichier de la topo active) et le passe par env `KUBECONFIG_LOCAL` ; bash
# l'UTILISE. Le défaut ci-dessous (`banc.config`) ne sert QUE si le script est lancé nu (hors
# moteur Python) — fallback banc générique. Une seule source de vérité pour le chemin.
# `${REPO}` = racine du dépôt (défini dans lib.sh).
KUBECONFIG_LOCAL="${KUBECONFIG_LOCAL:-${REPO}/.kubeconfigs/banc.config}"

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

# node_disk_specs <entry> — imprime les specs de disque déclarées d'un nœud (format
# riche), une par ligne, au format `name=size=role`. Vide si le nœud n'a pas de 4e
# champ ou est au format court `nom:rôle` (lancement nu → pas de disque).
node_disk_specs() {
    local entry=$1 field
    case "${entry}" in
        *"|"*)
            # 4e champ = tout après le 3e `|`. On enlève les 3 premiers champs.
            field="${entry#*|}"  # role|res|disks
            field="${field#*|}"  # res|disks
            field="${field#*|}"  # disks
            [ -n "${field}" ] || return 0
            local IFS=','
            local spec
            for spec in ${field}; do printf '%s\n' "${spec}"; done
            ;;
        *) : ;; # format court : aucun disque
    esac
}

preflight() {
    require_lima
    need ansible-playbook
    need kubectl
    need python3
}

# ── Phase 0 — VMs Lima + disques bruts DÉCLARÉS par nœud ──────────────────────
# ADR 0102 volet C : la TOPOLOGIE pilote, PAR NŒUD, les ressources VM et les disques
# bruts (fin de WITH_CEPH). Le « mode Ceph » = la PRÉSENCE de disques déclarés : un
# nœud sans disque ne provisionne que le disque OS (vda), un nœud de stockage crée SES
# disques nommés Lima (attachés en additionalDisks → vdb, vdc…) et est gaté.
phase_up() {
    preflight
    log "Phase 0 — VMs Lima (ressources + disques bruts pilotés par la topologie, ADR 0102)"
    mkdir -p "${WORKDIR}"
    local entry vm role resources
    for entry in "${NODES[@]}"; do
        vm="$(node_name "${entry}")"
        role="$(node_role "${entry}")"

        # Ressources du NŒUD (3e champ `cpus,memory,disk` du format riche). Fallback
        # sur les défauts globaux (VM_*) si le champ est vide/absent (lancement nu).
        local cpus="${VM_CPUS}" memory="${VM_MEMORY}" disk="${VM_DISK}"
        case "${entry}" in
            *"|"*)
                resources="${entry#*|}"    # role|res|disks
                resources="${resources#*|}" # res|disks
                resources="${resources%%|*}" # res
                if [ -n "${resources}" ]; then
                    IFS=',' read -r cpus memory disk <<< "${resources}"
                    cpus="${cpus:-${VM_CPUS}}"
                    memory="${memory:-${VM_MEMORY}}"
                    disk="${disk:-${VM_DISK}}"
                fi
                ;;
        esac

        # Disques DÉCLARÉS du nœud (4e champ). Pour chaque `name=size=role` : on crée le
        # disque nommé Lima `${vm}-${name}` (créé AVANT le start ; idempotent) et on
        # collecte SON nom pour le bloc additionalDisks. `disks` vide ⇒ lima_render_node
        # n'écrit pas additionalDisks (nœud sans stockage brut : disque OS seul).
        local disks="" spec name size
        while IFS= read -r spec; do
            [ -n "${spec}" ] || continue
            IFS='=' read -r name size _drole <<< "${spec}"
            lima_disk_create "${vm}-${name}" "${size}"
            disks="${disks:+${disks} }${vm}-${name}"
        done < <(node_disk_specs "${entry}")

        # Config VM rendue avec les ressources DU NŒUD (additionalDisks si disques
        # déclarés ; portForward API pour le CP) puis start.
        local cfg="${WORKDIR}/${vm}.yaml" api_port=""
        [ "${role}" = control ] && api_port="${API_PORT}"
        lima_render_node "${cfg}" "${cpus}" "${memory}" "${disk}" "${disks}" "${api_port}"
        lima_start_node "${vm}" "${cfg}"
    done

    # GATE disques : SEULEMENT sur les nœuds qui DÉCLARENT des disques (les autres
    # n'attachent que le disque OS). NB : `limactl shell <vm> '<cmd avec |>'` ne passe
    # PAS par un shell → on enveloppe dans `sh -c`. Lima attache aussi un disque cidata
    # (iso9660, monté) que Rook ignore (useAllDevices ne prend que les disques bruts).
    # On gate sur le NOMBRE de disques bruts présents (≥ nombre déclaré) plutôt que sur
    # des devices codés en dur (vdb/vde) : l'ordre d'attachement dérive de la topo.
    local gated=0
    for entry in "${NODES[@]}"; do
        vm="$(node_name "${entry}")"
        local n_expected=0
        while IFS= read -r spec; do
            [ -n "${spec}" ] && n_expected=$((n_expected + 1))
        done < <(node_disk_specs "${entry}")
        [ "${n_expected}" -gt 0 ] || continue
        gated=1
        log "Vérification des disques bruts sur ${vm} (${n_expected} attendu(s))"
        # Disques bruts = vd* SAUF vda (OS) et le cidata iso9660. On compte les vd[b-z].
        local n_present
        n_present=$(vm_sh "${vm}" sh -c 'lsblk -dno NAME | grep -cE "^vd[b-z]$"' | tr -d '[:space:]')
        [ "${n_present:-0}" -ge "${n_expected}" ] \
            || die "${vm} : ${n_present:-0} disque(s) brut(s) présent(s) < ${n_expected} déclaré(s) (additionalDisks non attachés ?)"
        ok "${vm} : disques bruts présents ($(vm_sh "${vm}" sh -c 'lsblk -dno NAME,SIZE | grep -E "^vd[b-z] " | tr "\n" " "'))"
    done
    [ "${gated}" = 1 ] || ok "aucun disque brut déclaré : pas de gate disque (mode local-path)"
}


# ── Down — détruit VMs + disques nommés ──────────────────────────────────────
# phase_down [vm…] — détruit les VMs nommées (+ leurs disques). Sans argument :
# les NODES du harnais (banc complet). AVEC arguments (noms de VM) : seulement
# celles-ci — c'est ainsi que `topology.py destroy` cible les VMs de la STACK active
# (déléguée ici, limactl reste du bash, ADR 0049). Ne retire le WORKDIR que pour un
# démontage COMPLET (sans liste explicite).
phase_down() {
    require_lima
    local targets=("$@") vm d entry
    # Table nom→entrée (pour retrouver les disques déclarés d'une VM ciblée par nom).
    if [ ${#targets[@]} -eq 0 ]; then
        for entry in "${NODES[@]}"; do targets+=("$(node_name "${entry}")"); done
        log "Destruction du banc Lima (VMs + disques nommés)"
    else
        log "Destruction des VMs : ${targets[*]} (+ disques nommés)"
    fi
    for vm in "${targets[@]}"; do
        lima_delete_node "${vm}"
        # Disques nommés Lima de cette VM = ceux DÉCLARÉS dans NODES pour l'entrée
        # de même nom (`${vm}-${name}` par spec). Si la VM n'est pas dans NODES (cas
        # d'une cible externe), aucun disque nommé attendu → rien à supprimer.
        for entry in "${NODES[@]}"; do
            [ "$(node_name "${entry}")" = "${vm}" ] || continue
            local spec name
            while IFS= read -r spec; do
                [ -n "${spec}" ] || continue
                IFS='=' read -r name _rest <<< "${spec}"
                lima_disk_delete "${vm}-${name}"
            done < <(node_disk_specs "${entry}")
            break
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
        [ "$(node_role "${entry}")" = control ] && n_control=$((n_control + 1))
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
