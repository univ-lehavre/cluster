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
    #     Dernier passage où sudo demande un mot de passe.
    ssh -t "$USER_REMOTE@$h" "sudo bash -s" <<'REMOTE'
set -euo pipefail

install -m 0440 /dev/stdin /etc/sudoers.d/90-debian-nopasswd <<'SUDOERS'
debian ALL=(ALL) NOPASSWD: ALL
SUDOERS

install -m 0644 -D /dev/stdin /etc/ssh/sshd_config.d/00-hardening.conf <<'SSHD'
# Géré par cluster/bootstrap/first-access.sh — ne pas éditer à la main.
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
AllowUsers debian
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 3
SSHD
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true

echo "  → sudo NOPASSWD + sshd durci"
REMOTE

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
