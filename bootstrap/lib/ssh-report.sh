#!/usr/bin/env bash
#
# Primitives SSH partagées par state.sh et security/report.sh (#296) — extraites
# pour lever la duplication (ssh_q / ssh_ok / ssh_script étaient copiées à
# l'identique). Sourcée, pas exécutée : `. "$(dirname …)/lib/ssh-report.sh"`
# (même patron que lib/{state,health}-classify.sh).
#
# Contrat (variables d'environnement lues, défauts posés ici si absentes) :
#   USER_REMOTE   utilisateur SSH                       (défaut: debian)
#   SSH_OPTS      options ssh additionnelles (banc/dev) (défaut: vide)
#                 ex. SSH_OPTS='-p 2222 -i ~/key' pour un banc local
#
# Toutes les fonctions sont best-effort (timeout court, BatchMode → pas de prompt
# interactif) : un hôte injoignable renvoie un échec silencieux, jamais un blocage.

USER_REMOTE=${USER_REMOTE:-debian}
SSH_OPTS=${SSH_OPTS:-}

ssh_q() {
    # ssh_q HOST CMD — best effort, stderr muet, retourne stdout.
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" 2> /dev/null
}

ssh_ok() {
    # ssh_ok HOST CMD — exit 0 si la commande distante renvoie 0.
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" > /dev/null 2>&1
}

ssh_script() {
    # ssh_script HOST — lit un script bash depuis stdin et l'exécute via
    # `sudo bash -s` sur HOST. Utile pour les vérifications multi-lignes qui
    # touchent à /etc/shadow ou autres fichiers privilégiés.
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" 'sudo bash -s' 2> /dev/null
}
