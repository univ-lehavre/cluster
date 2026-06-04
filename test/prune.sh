#!/usr/bin/env bash
# Détruit proprement les bancs locaux (Vagrant multi-node + single-node, et
# Lima) et libère les disques associés.
#
# Idempotent : rejouer sur un banc déjà clean ne fait rien.
# Refuse de tourner si une VM dirqual* est `running` (--force pour passer
# outre, --help pour cette aide).
#
# Voir test/RESULTS.md drift 0c pour la justification du closemedium.

set -euo pipefail

FORCE=0
for arg in "$@"; do
    case "$arg" in
        -f | --force) FORCE=1 ;;
        -h | --help)
            awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
            exit 0
            ;;
        *)
            printf 'ERROR: option inconnue: %s\n' "$arg" >&2
            exit 2
            ;;
    esac
done

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

cd "$(dirname "$0")" || die "cd vers test/ échoué"
log "Cible : $(pwd)"

# ── Banc Vagrant (multi-node + single-node) — best-effort si VirtualBox absent ─
if command -v vagrant > /dev/null && command -v VBoxManage > /dev/null; then
    # Garde-fou : refuse de détruire des VMs en cours
    running="$(VBoxManage list runningvms | grep -oE '"dirqual[0-9]+"' || true)"
    if [[ -n $running && $FORCE -ne 1 ]]; then
        die "VM(s) en cours : ${running//$'\n'/ }. Arrête-les ou relance avec --force."
    fi

    for bench in multi-node single-node; do
        if [[ -d "${bench}/.vagrant" ]]; then
            log "vagrant destroy -f → ${bench}/"
            (cd "${bench}" && vagrant destroy -f 2>&1 | sed 's/^/    /')
        else
            log "${bench}/ : pas de .vagrant, skip"
        fi
    done

    # Drift 0c : vagrant destroy laisse parfois des disques VBox enregistrés
    # (médiums) en plus des fichiers physiques. closemedium les unregister
    # ET supprime le .vdi s'il existe encore.
    orphans="$(VBoxManage list hdds \
        | awk '/^UUID:/{u=$2} /^Location:.*dirqual/{print u}')"
    if [[ -n $orphans ]]; then
        log "Disques VBox orphelins (drift 0c) :"
        while read -r uuid; do
            [[ -z $uuid ]] && continue
            log "  closemedium ${uuid}"
            VBoxManage closemedium disk "$uuid" --delete 2>&1 | sed 's/^/    /' || true
        done <<< "$orphans"
    fi

    rm -rf .vagrant multi-node/.vagrant single-node/.vagrant
    find . -maxdepth 3 -name '*VBoxHeadless*.log' -delete
    log ".vagrant/ + logs VBoxHeadless supprimés"

    remaining_vms="$(VBoxManage list vms | grep -cE '"dirqual[0-9]+"' || true)"
    remaining_hdds="$(VBoxManage list hdds | grep -cE 'dirqual[0-9]+' || true)"
    log "Reste VBox : ${remaining_vms} VM(s), ${remaining_hdds} disque(s) dirqual"
else
    log "Vagrant/VirtualBox absent — banc Vagrant ignoré."
fi

# ── Banc Lima — best-effort si limactl présent ───────────────────────────────
# Délègue au down du banc (détruit VMs cp1/node1/node2 + disques nommés
# <nœud>-hdd*/-blockdb + .work/). Idempotent : ne fait rien si rien n'existe.
if command -v limactl > /dev/null; then
    if [[ -x lima/run-phases.sh ]]; then
        log "Banc Lima : test/lima/run-phases.sh down"
        ./lima/run-phases.sh down 2>&1 | sed 's/^/    /' || true
    fi
    # Filet de sécurité : disques Lima orphelins du banc (préfixes cp1/node1/node2)
    # qu'un down partiel aurait laissés (VM supprimée mais disque encore listé).
    orphan_disks="$(limactl disk list --json 2> /dev/null \
        | grep -oE '"name":"[^"]+"' | sed -E 's/"name":"([^"]+)"/\1/' \
        | grep -E '^(cp1|node[0-9]+)-(hdd[0-9]+|blockdb)$' || true)"
    if [[ -n $orphan_disks ]]; then
        log "Disques Lima orphelins :"
        while read -r d; do
            [[ -z $d ]] && continue
            log "  disk delete ${d}"
            limactl disk delete --force "$d" 2>&1 | sed 's/^/    /' || true
        done <<< "$orphan_disks"
    fi
else
    log "limactl absent — banc Lima ignoré."
fi

log "Banc propre."
