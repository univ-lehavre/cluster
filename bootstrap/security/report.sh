#!/usr/bin/env bash
#
# Tableau de bord du durcissement — agrège, par hôte, les **preuves
# observables** des protections activées. Le but : que l'utilisateur voie
# ce qui est en place sans avoir à lancer chaque commande à la main.
#
# Usage :
#   bootstrap/security/report.sh                    # tous les hôtes
#   bootstrap/security/report.sh cp1 node1          # subset
#   SSH_OPTS='-p 2222 -i ~/key' report.sh 127.0.0.1 # banc/dev
#
# Variables d'env :
#   USER_REMOTE      utilisateur SSH                (défaut: debian)
#   SSH_OPTS         options ssh additionnelles     (défaut: vide)
#   NO_COLOR=1       désactive les couleurs ANSI
#
# Le script lit seulement — il ne modifie rien à distance.

set -euo pipefail

USER_REMOTE=${USER_REMOTE:-debian}
SSH_OPTS=${SSH_OPTS:-}

hosts=("$@")
if [ ${#hosts[@]} -eq 0 ]; then
    # Défaut d'EXEMPLE (ADR 0023) ; surcharger via les arguments (vrais hôtes).
    hosts=(cp1 node1 node2 node3)
fi

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[34m'
    C=$'\033[36m'; D=$'\033[2m';  N=$'\033[0m'
else
    G=''; R=''; Y=''; B=''; C=''; D=''; N=''
fi

ssh_q() {
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" 2>/dev/null
}

ssh_ok() {
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" >/dev/null 2>&1
}

active() {
    # active HOST SVC — renvoie "active" / "inactive" / "absent"
    if ssh_ok "$1" "command -v systemctl"; then
        if ssh_ok "$1" "systemctl is-active --quiet $2"; then
            echo active
        elif ssh_ok "$1" "systemctl list-unit-files --no-legend $2.service | grep -q $2"; then
            echo inactive
        else
            echo absent
        fi
    else
        echo absent
    fi
}

decorate() {
    case "$1" in
        active)   printf '%s● actif%s' "$G" "$N" ;;
        inactive) printf '%s○ inactif%s' "$Y" "$N" ;;
        absent)   printf '%s× absent (non activé)%s' "$D" "$N" ;;
    esac
}

# ───────────────────────────────────────────────────────────────────────
host_report() {
    local h=$1
    printf '\n%s━━━ %s ━━━%s\n' "$B" "$h" "$N"

    if ! ssh_ok "$h" true; then
        printf '  %s× hôte injoignable%s (clé SSH absente ? OS pas installé ?)\n' "$R" "$N"
        return
    fi

    # ── Identité ──────────────────────────────────────────────────────
    local distro kernel uptime
    # shellcheck disable=SC2016
    distro=$(ssh_q "$h" '. /etc/os-release; printf "%s %s" "$NAME" "$VERSION"')
    kernel=$(ssh_q "$h" 'uname -r')
    uptime=$(ssh_q "$h" 'uptime -p')
    printf '  %sOS%s     : %s — kernel %s\n' "$C" "$N" "$distro" "$kernel"
    printf '  %sUptime%s : %s\n' "$C" "$N" "$uptime"

    # ── Services de durcissement ──────────────────────────────────────
    printf '\n  %sServices de durcissement%s\n' "$C" "$N"
    for svc in unattended-upgrades postfix auditd fail2ban ufw; do
        local st
        st=$(active "$h" "$svc")
        printf '    %-22s %s\n' "$svc" "$(decorate "$st")"
    done

    # ── SSH (sondé via sshd -T) ───────────────────────────────────────
    printf '\n  %sSSH (sondé par sshd -T)%s\n' "$C" "$N"
    if ssh_ok "$h" 'sudo -n true'; then
        local sshd_out
        sshd_out=$(ssh_q "$h" 'sudo sshd -T 2>/dev/null')
        for k in passwordauthentication permitrootlogin pubkeyauthentication \
                 maxauthtries allowusers clientaliveinterval; do
            local v
            v=$(printf '%s\n' "$sshd_out" | awk -v k="$k" '$1==k {$1=""; sub(/^ /,""); print; exit}')
            if [ -z "$v" ]; then v="(non défini)"; fi
            printf '    %-22s %s\n' "$k" "$v"
        done
    else
        printf '    %s(sudo demande un mot de passe — résultat sshd -T indisponible)%s\n' "$D" "$N"
    fi

    # ── Mises à jour ──────────────────────────────────────────────────
    printf '\n  %sMises à jour automatiques%s\n' "$C" "$N"
    if ssh_ok "$h" 'test -f /etc/apt/apt.conf.d/20auto-upgrades'; then
        local reboot_time
        reboot_time=$(ssh_q "$h" 'grep -E "^Unattended-Upgrade::Automatic-Reboot-Time" /etc/apt/apt.conf.d/20auto-upgrades | head -1 | sed -E "s/.*\"([^\"]*)\".*/\1/"')
        printf '    %sconfiguration%s    : %s/etc/apt/apt.conf.d/20auto-upgrades%s\n' "$G" "$N" "$D" "$N"
        printf '    %sheure de reboot%s  : %s\n' "$G" "$N" "${reboot_time:-(non lisible)}"
        local last_run
        last_run=$(ssh_q "$h" 'sudo tail -n 1 /var/log/unattended-upgrades/unattended-upgrades.log 2>/dev/null')
        if [ -n "$last_run" ]; then
            printf '    %sdernière exécution%s : %s%s%s\n' "$G" "$N" "$D" "$last_run" "$N"
        fi
    else
        printf '    %sconfiguration non posée — %sansible-playbook secure.yml --tags os%s\n' "$D" "$Y" "$N"
    fi

    # ── Mail root (alert) ─────────────────────────────────────────────
    printf '\n  %sAlias mail root%s\n' "$C" "$N"
    local alias_line
    alias_line=$(ssh_q "$h" 'grep -E "^root:" /etc/aliases 2>/dev/null')
    if [ -n "$alias_line" ]; then
        printf '    %s%s%s\n' "$G" "$alias_line" "$N"
    else
        printf '    %s(pas d''alias root — %sansible-playbook secure.yml --tags alert%s)%s\n' "$D" "$Y" "$D" "$N"
    fi

    # ── auditd (règles chargées + résumé) ─────────────────────────────
    printf '\n  %sJournal d''audit (auditd)%s\n' "$C" "$N"
    if ssh_ok "$h" 'sudo systemctl is-active --quiet auditd'; then
        local nb_rules
        nb_rules=$(ssh_q "$h" 'sudo auditctl -l 2>/dev/null | grep -cv "^$"')
        printf '    règles chargées    : %s%s%s\n' "$G" "${nb_rules:-0}" "$N"
        printf '    %sderniers événements (5)%s :\n' "$D" "$N"
        ssh_q "$h" 'sudo aureport --summary 2>/dev/null | head -20 | tail -15' | sed "s/^/      /"
    else
        printf '    %s(auditd non actif — %sansible-playbook secure.yml --tags audit%s)%s\n' "$D" "$Y" "$D" "$N"
    fi

    # ── fail2ban (jails + IPs bannies) ────────────────────────────────
    printf '\n  %sDétection (fail2ban)%s\n' "$C" "$N"
    if ssh_ok "$h" 'sudo systemctl is-active --quiet fail2ban'; then
        local jails ipban
        # shellcheck disable=SC2016 # \$2 expands on the remote shell, not locally
        jails=$(ssh_q "$h" 'sudo fail2ban-client status 2>/dev/null | awk -F: "/Jail list/ {print \$2}" | xargs')
        printf '    jails actives      : %s%s%s\n' "$G" "${jails:-(aucune)}" "$N"
        # shellcheck disable=SC2016 # \$2 expands on the remote shell
        ipban=$(ssh_q "$h" 'sudo fail2ban-client status sshd 2>/dev/null | awk -F: "/Currently banned/ {print \$2}" | xargs')
        printf '    IP bannies (sshd)  : %s%s%s\n' "${ipban:+$G}${ipban:-$D}" "${ipban:-(aucune)}" "$N"
    else
        printf '    %s(fail2ban non actif — %sansible-playbook secure.yml --tags detection%s)%s\n' "$D" "$Y" "$D" "$N"
    fi

    # ── UFW ───────────────────────────────────────────────────────────
    printf '\n  %sPare-feu (UFW)%s\n' "$C" "$N"
    if ssh_ok "$h" 'command -v ufw'; then
        local ufw_state
        ufw_state=$(ssh_q "$h" 'sudo ufw status verbose 2>/dev/null | head -5')
        printf '%s\n' "$ufw_state" | sed "s/^/    /"
    else
        printf '    %s(ufw non installé — déconseillé tant que K8s n''est pas opérationnel)%s\n' "$D" "$N"
    fi

    # ── Expiration mot de passe ───────────────────────────────────────
    printf '\n  %sCompte debian%s\n' "$C" "$N"
    if ssh_ok "$h" "sudo chage -l ${USER_REMOTE}"; then
        ssh_q "$h" "sudo chage -l ${USER_REMOTE}" | grep -E 'Password expires|Minimum number|Maximum number' | sed "s/^/    /"
    else
        printf '    %s(chage indisponible sans sudo)%s\n' "$D" "$N"
    fi
}

# ───────────────────────────────────────────────────────────────────────
printf '%sRapport de durcissement — %s%s\n' "$B" "$(date '+%Y-%m-%d %H:%M:%S')" "$N"
printf '%sLecture seule — aucune modification distante.%s\n' "$D" "$N"

for h in "${hosts[@]}"; do
    host_report "$h"
done

printf '\n%s── Légende ──%s\n' "$B" "$N"
printf '  %s● actif%s : service en route\n' "$G" "$N"
printf '  %s○ inactif%s : paquet installé mais service arrêté\n' "$Y" "$N"
printf '  %s× absent%s : couche non activée (voir IMPLICATIONS.md)\n' "$D" "$N"
printf '\nPour activer une couche : %svoir IMPLICATIONS.md → section Menu%s.\n' "$C" "$N"
