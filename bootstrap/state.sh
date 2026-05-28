#!/usr/bin/env bash
#
# État du cluster — passe en revue chaque couche du déploiement face à l'état
# attendu et propose la prochaine étape (ou lève un drift).
#
# Usage :
#   bootstrap/state.sh                              # tous les hôtes par défaut
#   bootstrap/state.sh dirqual1 dirqual2            # subset
#   SSH_OPTS='-p 2222 -i ~/key' bootstrap/state.sh 127.0.0.1   # banc/dev
#
# Variables d'env :
#   USER_REMOTE      utilisateur SSH                (défaut: debian)
#   SSH_OPTS         options ssh additionnelles     (défaut: vide)
#   NO_COLOR=1       désactive les couleurs ANSI
#
# Codes de sortie :
#   0 — tout est conforme
#   1 — drift détecté (au moins un check ✗) ; voir « Prochaine étape »
#   2 — aucun hôte joignable (exécuter first-access.sh d'abord)

set -euo pipefail

USER_REMOTE=${USER_REMOTE:-debian}
read -ra SSH_OPTS_ARR <<<"${SSH_OPTS:-}"

hosts=("$@")
if [ ${#hosts[@]} -eq 0 ]; then
    hosts=(dirqual1 dirqual2 dirqual3 dirqual4)
fi

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[34m'
    C=$'\033[36m'; D=$'\033[2m';  N=$'\033[0m'
else
    G=''; R=''; Y=''; B=''; C=''; D=''; N=''
fi

declare -i ok_n=0 fail_n=0 skip_n=0 reachable_n=0
next_step=""

ssh_q() {
    # ssh_q HOST CMD — best effort, stderr muet, retourne stdout.
    ssh "${SSH_OPTS_ARR[@]}" -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" 2>/dev/null
}

ssh_ok() {
    # ssh_ok HOST CMD — exit 0 si la commande distante renvoie 0.
    ssh "${SSH_OPTS_ARR[@]}" -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" >/dev/null 2>&1
}

mark() {
    # mark ok|fail|skip "label" ["remedy"]
    local status=$1 label=$2 remedy=${3:-}
    case "$status" in
        ok)   printf '  %s✓%s %s\n' "$G" "$N" "$label"; ok_n+=1 ;;
        fail) printf '  %s✗%s %s\n' "$R" "$N" "$label"; fail_n+=1
              if [ -n "$remedy" ] && [ -z "$next_step" ]; then
                  next_step="$remedy"
              fi ;;
        skip) printf '  %s⏭ %s%s\n' "$D" "$label" "$N"; skip_n+=1 ;;
    esac
    return 0
}

section() { printf '\n%s── %s ──%s\n' "$B" "$1" "$N"; }

# ─── Joignabilité ──────────────────────────────────────────────────────────
section "Joignabilité SSH"
reachable=()
for h in "${hosts[@]}"; do
    if ssh_ok "$h" true; then
        mark ok "$h joignable (clé SSH OK)"
        reachable+=("$h")
        reachable_n+=1
    else
        mark skip "$h non joignable — install OS + bootstrap/first-access.sh $h"
    fi
done

if [ "$reachable_n" -eq 0 ]; then
    printf '\n%sAucun hôte joignable.%s Étape : installer l'\''OS + déposer la clé.\n' "$R" "$N"
    exit 2
fi

# ─── Couche 1 — Premier accès / sshd hardening ─────────────────────────────
section "Premier accès SSH (bootstrap/first-access.sh)"
for h in "${reachable[@]}"; do
    # shellcheck disable=SC2016 # $VERSION_ID expanded on the remote shell
    if [ "$(ssh_q "$h" '. /etc/os-release; echo "$VERSION_ID"')" = "13" ]; then
        mark ok "$h : Debian 13"
    else
        mark fail "$h : pas en Debian 13" "réinstaller en Debian 13 (cf. RUNBOOK)"
    fi

    if ssh_ok "$h" 'sudo -n true'; then
        mark ok "$h : sudo NOPASSWD"
    else
        mark fail "$h : sudo demande encore un mot de passe" \
                  "bash bootstrap/first-access.sh $h"
    fi

    if ssh_ok "$h" 'sudo test -f /etc/ssh/sshd_config.d/00-hardening.conf'; then
        mark ok "$h : sshd drop-in présent"
    else
        mark fail "$h : sshd drop-in absent" "bash bootstrap/first-access.sh $h"
    fi

    if [ "$(ssh_q "$h" "sudo sshd -T 2>/dev/null | awk '/^passwordauthentication/{print \$2}'")" = "no" ]; then
        mark ok "$h : PasswordAuthentication=no"
    else
        mark fail "$h : PasswordAuthentication toujours autorisé" \
                  "bash bootstrap/first-access.sh $h"
    fi
done

# ─── Couche 2 — Hardening OS (server-security, progressif) ─────────────────
section "Hardening OS (bootstrap/security/secure.yml)"
for h in "${reachable[@]}"; do
    for svc in unattended-upgrades postfix auditd fail2ban; do
        if ssh_ok "$h" "systemctl is-active --quiet $svc"; then
            mark ok "$h : $svc actif"
        else
            local_tag="os"
            case "$svc" in
                postfix) local_tag=alert ;;
                auditd)  local_tag=audit ;;
                fail2ban) local_tag=detection ;;
            esac
            mark fail "$h : $svc non actif" \
                      "(cd bootstrap/security && ansible-playbook -i ../hosts.yaml secure.yml --tags $local_tag --limit $h)"
        fi
    done
done

# ─── Couche 3 — Bootstrap Kubernetes (CRI + paquets + endpoint) ────────────
section "Bootstrap Kubernetes (cri / kubeadm / endpoint)"
for h in "${reachable[@]}"; do
    if ssh_ok "$h" 'systemctl is-active --quiet containerd'; then
        if [ "$(ssh_q "$h" 'sudo grep -c "SystemdCgroup = true" /etc/containerd/config.toml')" = "1" ]; then
            mark ok "$h : containerd + SystemdCgroup=true"
        else
            mark fail "$h : containerd actif mais SystemdCgroup pas forcé" \
                      "ansible-playbook -i bootstrap/hosts.yaml bootstrap/cri.yaml --limit $h"
        fi
    else
        mark skip "$h : containerd non installé (cri.yaml à jouer)"
    fi

    if ssh_ok "$h" 'command -v kubeadm'; then
        kver=$(ssh_q "$h" 'kubeadm version -o short')
        mark ok "$h : kubeadm $kver"
    else
        mark skip "$h : kubeadm non installé (kubeadm.yaml à jouer)"
    fi

    if ssh_ok "$h" 'grep -q cluster-api /etc/hosts'; then
        mark ok "$h : entrée /etc/hosts pour cluster-api"
    else
        mark skip "$h : pas d'entrée cluster-api (kubeadm.yaml à jouer)"
    fi

    if ssh_ok "$h" 'sudo test -f /etc/kubernetes/admin.conf'; then
        mark ok "$h : kubeadm init réalisé (admin.conf)"
    else
        mark skip "$h : kubeadm init pas encore joué"
    fi
done

# ─── Résumé ────────────────────────────────────────────────────────────────
section "Résumé"
printf "  ${G}%d ok${N}   ${R}%d drift${N}   ${D}%d non applicable${N}\n" \
    "$ok_n" "$fail_n" "$skip_n"

if [ "$fail_n" -gt 0 ]; then
    printf '\n%sProchaine étape (1er drift)%s :\n' "$Y" "$N"
    printf '  %s%s%s\n' "$C" "$next_step" "$N"
    exit 1
fi

printf '\n%sÉtat conforme%s sur la couche couverte par ce script.\n' "$G" "$N"
printf 'Couches futures à intégrer ici au fil des phases : '
printf 'Cilium, Rook-Ceph, StorageClasses, workloads.\n'
printf 'Consulter %sbootstrap/RUNBOOK.md%s pour la prochaine grande étape.\n' "$C" "$N"
