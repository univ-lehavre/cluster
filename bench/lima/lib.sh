#!/usr/bin/env bash
#
# Bibliothèque d'orchestration du banc léger Lima — primitives réutilisables
# (VMs Lima, disques bruts, inventaire Ansible, bootstrap, kubeconfig).
#
# SOURCÉE par bench/lima/run-phases.sh (banc multi-nœuds) ET par les spikes qui
# montent des clusters Lima (bench/spikes/clustermesh-latency/). Une seule source
# pour les idiomes log/ok/die/need/retry et pour la plomberie limactl ↔ Ansible
# (sinon duplication signalée par jscpd).
#
# Idiomes log/ok/die/need/retry repris de bench/multi-node/run-phases.sh pour
# rester cohérent avec le banc Vagrant.
#
# Pourquoi Lima plutôt que kind/Vagrant (ADR 0006) : kind figeait K8s en 1.31
# (incompatible ImageVolume/pgvector) ; Vagrant+VirtualBox est lourd (overlayfs
# imbriqué, ~15 GiB). Une VM Lima est une VRAIE VM Linux (vrai noyau, vrais
# cgroups, SSH natif) sur laquelle tourne le VRAI bootstrap Ansible — même
# chemin que la prod.

# ── Emplacements ─────────────────────────────────────────────────────────────
# REPO = racine du dépôt (bootstrap/ et storage/ y vivent). LIMA_DIR = bench/lima.
LIMA_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "${LIMA_DIR}/../.." && pwd)

# Le banc lance ansible-playbook depuis un CWD ≠ bootstrap/ avec le playbook en
# chemin absolu → Ansible ne trouverait PAS bootstrap/ansible.cfg (cherché dans
# le CWD), donc roles_path / interpreter_python / inject_facts_as_vars seraient
# ignorés (drift L46 : warnings interpréteur + config non appliquée). On force
# donc le chargement de la config du dépôt pour TOUTES les invocations du banc.
export ANSIBLE_CONFIG="${REPO}/bootstrap/ansible.cfg"

# ── Helpers d'affichage (repris de run-phases.sh) ────────────────────────────
log() { printf '\n\033[1;36m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }
ok() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mÉCHEC: %s\033[0m\n' "$*" >&2; exit 1; }
need() { command -v "$1" > /dev/null 2>&1 || die "outil requis absent : $1"; }

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

# Garde-fou : Lima doit être installé (les VMs en dépendent).
require_lima() { need limactl; }

# ── Lima : état / shell / réseau ─────────────────────────────────────────────
# Une VM Lima existe-t-elle (quel que soit son état) ? Capture avant grep
# (SIGPIPE + pipefail — cf. lima_disk_exists).
vm_exists() {
    local out
    out=$(limactl list --format '{{.Name}}' 2> /dev/null)
    printf '%s' "${out}" | grep -qx "$1"
}

# Une VM Lima tourne-t-elle ?
vm_running() {
    [ "$(limactl list --format '{{.Status}}' "$1" 2> /dev/null)" = "Running" ]
}

# Exécute une commande DANS une VM Lima (non interactif).
vm_sh() {
    local vm=$1
    shift
    limactl shell "${vm}" "$@"
}

# IP user-v2 de la VM (192.168.104.0/24) : adresse joignable depuis l'AUTRE VM
# ET depuis l'hôte (le NAT user-mode par défaut n'est PAS routable entre VMs).
# Lue côté invité — l'interface user-v2 est un NIC secondaire.
vm_uservv2_ip() {
    local vm=$1
    vm_sh "${vm}" sh -c \
        "ip -4 -o addr show | awk '/192\.168\.104\./ {print \$4}' | cut -d/ -f1 | head -1"
}

# Interface portant le réseau user-v2 dans la VM (cible de tc netem). Détectée,
# pas codée en dur : Lima ne garantit pas le nom `lima0` selon les versions.
vm_uservv2_iface() {
    local vm=$1
    vm_sh "${vm}" sh -c \
        "ip -4 -o addr show | awk '/192\.168\.104\./ {print \$2}' | head -1"
}

# ── Lima : disques bruts (Ceph) ──────────────────────────────────────────────
# Ceph/Rook exige des disques BRUTS, non partitionnés. Lima ne sait pas créer de
# disque vierge inline : on crée des disques nommés persistants (qcow2) AVANT le
# start, référencés par la VM en `additionalDisks: [{name, format:false}]` pour
# rester bruts. Idempotents : ne recrée/supprime que si nécessaire.
# `limactl disk list` n'a pas de --format go-template (≠ `limactl list`) → on
# parse le JSON (un objet {"name":...} par disque). NB : on capture AVANT de
# grep — un `limactl … | grep -q` ferme le tube au 1er match, `limactl` reçoit
# SIGPIPE et sort ≠0, et `set -o pipefail` ferait échouer la détection à tort.
lima_disk_exists() {
    local out
    out=$(limactl disk list --json 2> /dev/null)
    printf '%s' "${out}" | grep -q "\"name\":\"$1\""
}

lima_disk_create() {
    local name=$1 size=$2
    if lima_disk_exists "${name}"; then
        ok "disque Lima '${name}' déjà présent"
    else
        log "Création du disque Lima brut '${name}' (${size})"
        limactl disk create "${name}" --size "${size}"
    fi
}

lima_disk_delete() {
    local name=$1
    lima_disk_exists "${name}" || return 0
    if limactl disk delete --force "${name}" > /dev/null 2>&1; then
        ok "disque '${name}' supprimé"
    else
        warn "disque '${name}' non supprimé (encore attaché ?)"
    fi
}

# ── Lima : rendu d'une config VM depuis le template + démarrage ──────────────
# Rend profiles/node.yaml.tmpl en injectant cpus/mémoire/disque, et en ajoutant
# en fin de fichier (1) le bloc additionalDisks pour les nœuds de stockage et
# (2) le portForward de l'API pour les control-planes.
#   $disks    = noms de disques nommés séparés par des espaces (vide → pas de bloc)
#   $api_port = port hôte (127.0.0.1) pour l'API du nœud (vide → pas de forward,
#               cas des workers qui ne servent pas l'API)
lima_render_node() {
    local out=$1 cpus=$2 memory=$3 disk=$4 disks=$5 api_port="${6:-}"
    local tmpl="${LIMA_DIR}/profiles/node.yaml.tmpl"
    [ -f "${tmpl}" ] || die "template introuvable : ${tmpl}"

    # En-tête : substitue les ressources dans le template.
    sed -e "s/@@CPUS@@/${cpus}/" \
        -e "s/@@MEMORY@@/${memory}/" \
        -e "s/@@DISK@@/${disk}/" \
        "${tmpl}" > "${out}"

    # Forward de l'API (control-plane uniquement) : guest 6443 → host 127.0.0.1.
    if [ -n "${api_port}" ]; then
        {
            echo ""
            echo "# Forward déterministe de l'API (l'IP user-v2 n'est pas routable depuis l'hôte)."
            echo "portForwards:"
            echo "  - guestPort: 6443"
            echo "    hostIP: 127.0.0.1"
            echo "    hostPort: ${api_port}"
        } >> "${out}"
    fi

    # Bloc additionalDisks (disques bruts pour Ceph) — uniquement si demandé.
    if [ -n "${disks}" ]; then
        {
            echo ""
            echo "# Disques bruts pour Ceph/Rook (format:false → non formatés)."
            echo "additionalDisks:"
            local d
            for d in ${disks}; do
                echo "  - name: ${d}"
                echo "    format: false"
            done
        } >> "${out}"
    fi
}

# Démarre une VM Lima (la crée au premier appel). Idempotent.
# `--yes` (= --tty=false) : harnais automatisé → PAS de prompt « Proceed with the
# current configuration? [y/N] » à la création (Lima le pose dès que stdout est un
# terminal). Sans lui, un `run-phases.sh` lancé à la main bloque sur la question.
lima_start_node() {
    local vm=$1 cfg=$2
    if vm_running "${vm}"; then
        ok "VM Lima '${vm}' déjà démarrée"
    elif vm_exists "${vm}"; then
        log "Démarrage de la VM Lima '${vm}' (déjà créée)"
        limactl start --yes "${vm}"
    else
        log "Création + démarrage de la VM Lima '${vm}'"
        limactl start --yes --name "${vm}" "${cfg}"
    fi
}

# Supprime une VM Lima (idempotent).
lima_delete_node() {
    local vm=$1
    if vm_exists "${vm}"; then
        log "Suppression de la VM Lima '${vm}'"
        limactl delete --force "${vm}"
        ok "'${vm}' supprimée"
    else
        ok "'${vm}' déjà absente"
    fi
}

# ── Ansible : inventaire + bootstrap ─────────────────────────────────────────
# Génère l'inventaire Ansible (gitignoré : artefact de run). Ansible joint chaque
# VM via sa config SSH Lima (alias d'hôte `lima-<vm>`). $control / $workers =
# listes de noms de VM séparés par des espaces ($workers peut être vide).
write_inventory() {
    local inv=$1 control=$2 workers=$3
    {
        echo "# Inventaire généré par le banc Lima — NE PAS versionner (artefact de run)."
        echo "cloud:"
        echo "  children:"
        echo "    control:"
        echo "    workers:"
        echo "  vars:"
        # Lima crée toujours l'utilisateur invité `lima` (quel que soit l'utilisateur
        # hôte). Le bootstrap référence `ansible_user` comme VARIABLE (ex. rôle
        # k8s-initialization : /home/{{ ansible_user }}/.kube) — la connexion SSH
        # seule (via ssh.config) ne la peuple PAS. On la pose donc explicitement,
        # comme l'inventaire Vagrant pose `ansible_user: debian`.
        echo "    ansible_user: lima"
        # Marqueur de CRITICITÉ (ADR 0053 (c) / 0099) : le banc déclare `bench` (parc
        # jetable) ; l'assert du rôle audit-log refuse de tourner si l'intention diffère.
        # NB : `ansible_user: lima` reste l'utilisateur de la VM Lima (l'outil), distinct.
        echo "    target_kind: bench"
        echo "control:"
        echo "  hosts:"
        local vm ssh_cfg
        for vm in ${control}; do
            ssh_cfg="${HOME}/.lima/${vm}/ssh.config"
            [ -f "${ssh_cfg}" ] || die "config SSH Lima introuvable : ${ssh_cfg}"
            echo "    ${vm}:"
            echo "      ansible_host: lima-${vm}"
            echo "      ansible_ssh_common_args: \"-F ${ssh_cfg}\""
        done
        echo "workers:"
        if [ -n "${workers}" ]; then
            echo "  hosts:"
            for vm in ${workers}; do
                ssh_cfg="${HOME}/.lima/${vm}/ssh.config"
                [ -f "${ssh_cfg}" ] || die "config SSH Lima introuvable : ${ssh_cfg}"
                echo "    ${vm}:"
                echo "      ansible_host: lima-${vm}"
                echo "      ansible_ssh_common_args: \"-F ${ssh_cfg}\""
            done
        else
            echo "  hosts: {}"
        fi
        # Poste de contrôle (#277) : les plays plateforme/Ceph pilotent l'API k8s
        # depuis `localhost` (-e dataops_k8s_host=localhost). On le déclare dans le
        # groupe `control_host` pour qu'il hérite de bootstrap/group_vars/
        # control_host.yaml → interpréteur = .venv du dépôt (kubernetes+certifi
        # provisionnés par `uv sync`). connection: local (pas de SSH vers soi-même).
        echo "control_host:"
        echo "  hosts:"
        echo "    localhost:"
        echo "      ansible_connection: local"
    } > "${inv}"
}

# NB : la séquence des 6 playbooks du socle (checks→…→join-workers) est désormais
# orchestrée EN PYTHON (nestor/bootstrap.py, via runner.launch_phase ;
# « Python parle Ansible », ADR 0063), appelée par topology.py bootstrap-seq. La
# fonction bash bootstrap_node_sequence a été retirée (plus aucun appelant).

# Pose Cilium via le VRAI bootstrap/cni.sh, exécuté DANS la VM. Variables d'env
# supplémentaires (ex. CILIUM_CLUSTER_NAME/ID/POD_CIDR pour le mesh) passées en
# tête : `run_cni cp1 CILIUM_POD_CIDR=10.245.0.0/16`.
#
# cni.sh tourne EN TANT QU'UTILISATEUR (pas sudo) : kubectl/cilium utilisent le
# ~/.kube/config de l'utilisateur (posé par le rôle k8s-initialization) ; le
# script n'élève en root (sudo interne) que les commandes qui l'exigent (install
# du CLI, purge iptables). Le wrapper sudo global ferait pointer kubectl sur le
# kubeconfig root absent → « localhost:8080 connection refused ». `env` injecte
# les variables (sudo -E ne propagerait que vers les sous-commandes root).
run_cni() {
    local vm=$1
    shift
    log "  Cilium (cni.sh sur ${vm})"
    vm_sh "${vm}" env "$@" bash -s < "${REPO}/bootstrap/cni.sh"
}

# Exporte le kubeconfig d'un nœud control-plane vers l'hôte. L'API est jointe via
# le portForward Lima (127.0.0.1:<api_port>), l'IP user-v2 n'étant pas routable
# depuis le Mac. Le certificat de l'API porte le SAN `cluster-api` → on pose
# `tls-server-name: cluster-api` pour que la validation TLS passe malgré l'adresse
# 127.0.0.1. Gate `kubectl version`.
#   $api_port = port hôte du forward de l'API (cf. lima_render_node)
#   $ctx (optionnel) = nom de contexte. Si fourni, on renomme AUSSI le cluster et
#     l'utilisateur sur ce nom : sinon deux kubeconfigs de clusters kubeadm
#     distincts partagent les noms par défaut (`kubernetes`/`kubernetes-admin`) et
#     s'ÉCRASENT mutuellement une fois fusionnés (KUBECONFIG=a:b) — fatal pour le
#     pilotage multi-cluster (ex. mesh : `cilium clustermesh connect` voyait deux
#     fois le même cluster).
fetch_kubeconfig_node() {
    local vm=$1 out=$2 api_port=$3 ctx="${4:-}"
    [ -n "${api_port}" ] || die "fetch_kubeconfig_node : api_port manquant"
    mkdir -p "$(dirname "${out}")"
    vm_sh "${vm}" sudo cat /etc/kubernetes/admin.conf > "${out}" \
        || die "kubeconfig introuvable sur ${vm} (bootstrap fait ?)"
    # admin.conf pointe sur cluster-api:6443 (résolu DANS la VM) → réécrit sur le
    # forward hôte.
    sed -i.bak -E "s#server: https://[^[:space:]]+#server: https://127.0.0.1:${api_port}#" "${out}"
    rm -f "${out}.bak"

    if [ -n "${ctx}" ]; then
        # Renomme cluster + user + contexte sur des noms UNIQUES dérivés de $ctx.
        # kubeadm pose toujours les noms par défaut `kubernetes` (cluster),
        # `kubernetes-admin` (user) et `kubernetes-admin@kubernetes` (contexte) :
        # on les remplace par des chaînes exactes (du plus long au plus court pour
        # éviter les remplacements partiels). Édition directe : un seul
        # cluster/user/contexte par kubeconfig de nœud.
        sed -i.bak \
            -e "s#kubernetes-admin@kubernetes#${ctx}#g" \
            -e "s#kubernetes-admin#${ctx}-admin#g" \
            -e "s#name: kubernetes\$#name: ${ctx}#g" \
            -e "s#cluster: kubernetes\$#cluster: ${ctx}#g" \
            "${out}"
        rm -f "${out}.bak"
    fi

    # tls-server-name : la validation TLS se fait contre le SAN cluster-api.
    local cluster
    cluster=$(KUBECONFIG="${out}" kubectl config view -o jsonpath='{.clusters[0].name}')
    KUBECONFIG="${out}" kubectl config set-cluster "${cluster}" \
        --tls-server-name=cluster-api > /dev/null

    chmod 600 "${out}"
    KUBECONFIG="${out}" kubectl version > /dev/null 2>&1 \
        || die "kubectl ne joint pas l'API via ${out} (forward 127.0.0.1:${api_port} actif ?)"
    ok "kubeconfig prêt : ${out} (API via 127.0.0.1:${api_port}, tls-server-name=cluster-api)"
}
