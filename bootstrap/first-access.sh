#!/usr/bin/env bash
#
# Premier accès SSH à des serveurs Debian fraîchement installés.
#
# Strict minimum pour qu'Ansible puisse ensuite piloter les nœuds sans mot de
# passe, *et* pour fermer immédiatement la fenêtre d'authentification par mot
# de passe avant de quitter la machine. Le reste du hardening
# (unattended-upgrades, UFW, fail2ban, auditd, postfix, …) est délégué au
# dépôt `server-security`, à lancer juste après.
#
# Sur chaque hôte fourni :
#   1. dépose la clé publique de l'opérateur (`ssh-copy-id`) ;
#   2. installe la règle `sudo NOPASSWD` pour l'utilisateur `debian` ;
#   3. durcit `sshd` via un drop-in (clés uniquement, root off, AllowUsers debian,
#      MaxAuthTries 3, ClientAlive*) ;
#   4. (optionnel, $NEW_DEBIAN_PASSWORD) change le mot de passe `debian`.
#
# Usage :
#   bootstrap/first-access.sh                  # cible dirqual1..dirqual4
#   bootstrap/first-access.sh dirqual1 dirqual2
#
# Variables d'environnement :
#   SSH_PUBKEY            clé publique à déposer (défaut: ~/.ssh/id_ed25519.pub)
#   USER_REMOTE           utilisateur distant    (défaut: debian)
#   NEW_DEBIAN_PASSWORD   nouveau mot de passe `debian` (sinon laissé tel quel)
#
# La 1re passe demande le mot de passe SSH deux fois par hôte (`ssh-copy-id`
# puis `sudo`). Les runs suivants sont silencieux et idempotents.

set -euo pipefail

USER_REMOTE=${USER_REMOTE:-debian}
SSH_PUBKEY=${SSH_PUBKEY:-$HOME/.ssh/id_ed25519.pub}

hosts=("$@")
if [ ${#hosts[@]} -eq 0 ]; then
    hosts=(dirqual1 dirqual2 dirqual3 dirqual4)
fi

if [ ! -f "$SSH_PUBKEY" ]; then
    echo "ERREUR : clé publique introuvable : $SSH_PUBKEY" >&2
    echo "        Générer avec : ssh-keygen -t ed25519" >&2
    exit 1
fi

for h in "${hosts[@]}"; do
    echo
    echo "== $h =="

    # (1) Dépose la clé publique. Demande le mot de passe debian la 1re fois.
    ssh-copy-id -i "$SSH_PUBKEY" "$USER_REMOTE@$h"

    # (2) sudo NOPASSWD + durcissement sshd via drop-ins.
    #
    # On dépose d'abord le script sur le nœud via un ssh sans TTY (le heredoc
    # part dans `cat > /tmp/…`), puis on l'exécute en root via un ssh -t qui
    # n'a PAS de stdin piped — sudo peut ainsi prompter proprement, une seule
    # fois. (Le piège : `ssh -tt … <<heredoc` envoie le heredoc dans le TTY
    # distant et il est consommé par le prompt sudo, qui essaie chaque ligne
    # du script comme mot de passe.)
    ssh "$USER_REMOTE@$h" 'cat > /tmp/cluster-first-access.sh' <<'REMOTE'
#!/bin/bash
# Idempotent : on n'écrit chaque drop-in qu'en cas de différence de contenu
# ou de mode, et on ne reload sshd que si son drop-in a changé.
set -euo pipefail

write_if_changed() {
    # write_if_changed MODE DEST CONTENT
    # Retourne 0 si le fichier a été (ré)écrit, 1 s'il était déjà conforme.
    local mode=$1 dest=$2 content=$3
    local want_mode=${mode#0}
    if [ -f "$dest" ]; then
        local cur cur_mode
        cur=$(cat "$dest")
        cur_mode=$(stat -c '%a' "$dest")
        if [ "$cur" = "$content" ] && [ "$cur_mode" = "$want_mode" ]; then
            return 1
        fi
    fi
    install -m "$mode" -D /dev/stdin "$dest" <<<"$content"
    return 0
}

sudoers_content='debian ALL=(ALL) NOPASSWD: ALL'

sshd_content='# Géré par cluster/bootstrap/first-access.sh — ne pas éditer à la main.
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
AllowUsers debian
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 3'

changed=0
if write_if_changed 0440 /etc/sudoers.d/90-debian-nopasswd "$sudoers_content"; then
    echo "  → sudo NOPASSWD posé"
    changed=1
fi

if write_if_changed 0644 /etc/ssh/sshd_config.d/00-hardening.conf "$sshd_content"; then
    echo "  → sshd drop-in posé"
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
    changed=1
fi

if [ "$changed" -eq 0 ]; then
    echo "  → déjà conforme, rien à faire"
else
    echo "  → hardening appliqué"
fi
REMOTE

    ssh -t "$USER_REMOTE@$h" \
        'sudo bash /tmp/cluster-first-access.sh && rm -f /tmp/cluster-first-access.sh'

    # (3) Optionnel : changement du mot de passe debian (passwordless via sudo).
    if [ -n "${NEW_DEBIAN_PASSWORD:-}" ]; then
        printf 'debian:%s\n' "$NEW_DEBIAN_PASSWORD" |
            ssh "$USER_REMOTE@$h" "sudo chpasswd"
        echo "  → mot de passe debian mis à jour"
    fi
done

echo
echo "Premier accès terminé sur : ${hosts[*]}"
echo "Étape suivante : cloner et lancer le dépôt server-security pour"
echo "le reste du hardening (unattended-upgrades, UFW, fail2ban, auditd, …)."
