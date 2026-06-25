# shellcheck shell=bash
#
# `nestor` — fonction shell de l'outil déclaratif (à SOURCER, patron nvm/pyenv).
#
# Pourquoi une fonction et non un exécutable ? Un programme NE PEUT PAS modifier
# l'environnement de son shell parent (invariant Unix) : seule une fonction sourcée
# peut poser `KUBECONFIG` dans TON shell. La fonction délègue à l'implémentation
# `scripts/nestor-exec` (le vrai outil, `uv run … topology.py`) et, pour `stack
# select` (qui désigne une cible), applique le `export KUBECONFIG=…` qu'elle imprime
# — comme `direnv`/`zoxide`/`ssh-agent`.
#
# `nestor env` est SUPPRIMÉE (LOT 8, ADR 0097 §3) : `nestor` maintient désormais des
# CONTEXTES kubectl nommés (`stack select` pose `<topo>` dans le kubeconfig de la
# cible), et l'on branche kubectl par le mécanisme STANDARD k8s — `kubectl --context
# <topo> …` — sans aucune variable d'environnement.
#
# Installation : sourcer ce fichier dans ton profil, puis ouvrir un nouveau shell :
#
#   echo 'source /chemin/vers/nestor/nestor.sh' >> ~/.zshrc   # ou ~/.bashrc
#
# Ensuite : `nestor up`, `nestor preview`, … fonctionnent ; `nestor stack select
# banc` pose en plus KUBECONFIG dans le shell (banc de la stack, ou /dev/null si pas
# de banc — jamais la prod, ADR 0053) ET le contexte kubectl nommé.

# Racine du dépôt, résolue UNE FOIS au source (pas à chaque appel) — évite la syntaxe
# zsh `${(%):-%x}` (non portable bash). bash expose le chemin sourcé dans
# ${BASH_SOURCE} ; zsh dans $0 au moment du source.
if [ -n "${BASH_SOURCE:-}" ]; then
    _NESTOR_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
else
    _NESTOR_ROOT=$(cd "$(dirname "$0")" && pwd)
fi
export _NESTOR_ROOT

nestor() {
    local _bin="${_NESTOR_ROOT}/scripts/nestor-exec"
    # `stack select` IMPRIME un `export KUBECONFIG=…` (stdout) à appliquer au shell.
    # On capture STDOUT (l'export) et on l'eval ; STDERR (messages humains) reste
    # affiché. Le binaire n'imprime l'export que si stdout est capturé (non-TTY) — ici
    # il l'est toujours (substitution de commande). `nestor env` a disparu (ADR 0097
    # §3) : le branchement kubectl passe par le contexte nommé que `stack select` pose
    # dans le kubeconfig (`kubectl --context <topo> …`), plus de variable d'env.
    if [ "$1" = "stack" ] && [ "$2" = "select" ]; then
        local _out
        _out=$("${_bin}" "$@") || return $?
        [ -n "${_out}" ] && eval "${_out}"
        return 0
    fi
    # Toute autre commande (up/next/preview/…) : délégation normale.
    "${_bin}" "$@"
}
