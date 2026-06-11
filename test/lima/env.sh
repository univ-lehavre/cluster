#!/usr/bin/env bash
#
# Imprime le CONTEXTE d'exécution courant (hosts + kubeconfig) et les commandes
# prêtes à copier pour lancer les scripts de diagnostic (bootstrap/state.sh,
# bootstrap/security/report.sh…) SANS deviner les hôtes.
#
# Motivation : les vrais hôtes vivent en config locale GITIGNORÉE (ADR 0023) —
#   - banc Lima : VMs détectées par `limactl list` (noms cp1/node1/…),
#   - prod      : bootstrap/hosts.yaml (copié de hosts.example.yaml).
# Depuis le dépôt seul on ne PEUT donc pas connaître les hôtes ; ce helper les
# dérive du contexte réel et te donne l'invocation exacte. LECTURE SEULE (il
# n'exécute aucun des scripts, il les affiche).
#
# Usage :
#   test/lima/env.sh            # auto-détecte (banc Lima si des VMs existent, sinon prod)
#   test/lima/env.sh lima       # force le contexte banc Lima
#   test/lima/env.sh prod       # force le contexte prod (bootstrap/hosts.yaml)
#   eval "$(test/lima/env.sh export)"   # exporte KUBECONFIG du banc dans ton shell

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "${HERE}/../.." && pwd)
KUBECONFIG_LOCAL="${HERE}/.work/kubeconfig"

if [ -t 1 ]; then B=$'\033[1m'; C=$'\033[36m'; D=$'\033[2m'; N=$'\033[0m'
else B=''; C=''; D=''; N=''; fi

# Noms des VMs Lima du banc (celles qui existent réellement).
lima_hosts() { limactl list --format '{{.Name}}' 2>/dev/null | grep -E '^(cp|node)[0-9]+$' || true; }

# Mode `export` : imprime la ligne d'export KUBECONFIG du BANC (pour `eval`).
# Vecteur d'armement de la cible ambiante (ADR 0053 (d)) : il ANNONCE sur stderr
# ce qu'il charge, et AVERTIT si un inventaire prod coexiste (le shell pointera
# alors le banc — danger pour un kubectl/state.sh visant la prod).
if [ "${1:-}" = export ]; then
    printf 'export KUBECONFIG=%q\n' "${KUBECONFIG_LOCAL}"
    printf '# env.sh : KUBECONFIG → banc Lima (%s)\n' "${KUBECONFIG_LOCAL}" >&2
    if [ -f "${REPO}/bootstrap/hosts.yaml" ]; then
        printf '# ⚠ inventaire prod présent : ce shell pointe désormais le BANC, pas la prod (ADR 0053).\n' >&2
    fi
    exit 0
fi

# Détection du contexte. CESSE DE DEVINER quand les deux cibles coexistent
# (ADR 0053 (d)) : auto-détecter UNIQUEMENT si une seule est plausible ; si un
# banc Lima est up ET un inventaire prod existe, l'intention n'est pas déductible
# de l'état du shell → on REFUSE et on exige lima|prod explicite. La friction est
# ciblée sur le seul cas dangereux ; le poste mono-cible reste ergonomique.
mode="${1:-auto}"
has_lima=""; [ -n "$(lima_hosts)" ] && has_lima=1
has_prod=""; [ -f "${REPO}/bootstrap/hosts.yaml" ] && has_prod=1
if [ "${mode}" = auto ]; then
    if [ -n "${has_lima}" ] && [ -n "${has_prod}" ]; then
        printf '\n%sBanc Lima ET inventaire prod coexistent — cible AMBIGUË (ADR 0053).%s\n' "${B}" "${N}" >&2
        printf '  Préciser la cible : %stest/lima/env.sh lima%s  ou  %stest/lima/env.sh prod%s\n' \
            "${C}" "${N}" "${C}" "${N}" >&2
        exit 2
    elif [ -n "${has_lima}" ]; then mode=lima
    else mode=prod
    fi
fi

printf '\n%sContexte : %s%s%s\n' "${B}" "${C}" "${mode}" "${N}"

if [ "${mode}" = lima ]; then
    hosts=$(lima_hosts | tr '\n' ' ')
    if [ -z "${hosts# }" ]; then
        printf '  %sAucune VM Lima en cours. Monter le banc : %stest/lima/run-phases.sh up%s\n' "${D}" "${N}${C}" "${N}"
        exit 0
    fi
    printf '  hôtes du banc Lima : %s%s%s\n' "${C}" "${hosts}" "${N}"
    printf '\n%sDiagnostic des nœuds (bootstrap/state.sh — un nœud à la fois, SSH Lima)%s\n' "${B}" "${N}"
    # Chaque VM Lima a SA propre config SSH (~/.lima/<vm>/ssh.config) et
    # l'utilisateur `lima` (≠ debian prod). state.sh prend les hôtes en args.
    for vm in $(lima_hosts); do
        printf '  %sUSER_REMOTE=lima SSH_OPTS=%q bootstrap/state.sh %s%s\n' \
            "${C}" "-F ${HOME}/.lima/${vm}/ssh.config" "${vm}" "${N}"
    done
    printf '\n%sÉtat global du banc (sans SSH, via kubeconfig)%s\n' "${B}" "${N}"
    printf '  %stest/lima/run-phases.sh status%s   %s← vue d'\''ensemble VMs+nœuds+phases+UIs%s\n' "${C}" "${N}" "${D}" "${N}"
    printf '\n%sPiloter le cluster (kubectl)%s\n' "${B}" "${N}"
    if [ -f "${KUBECONFIG_LOCAL}" ]; then
        # Exemple littéral à copier (le `$(...)` ne doit PAS s'expandre ici).
        # shellcheck disable=SC2016
        printf '  %seval "$(test/lima/env.sh export)"%s   %s← exporte KUBECONFIG=%s%s\n' \
            "${C}" "${N}" "${D}" "${KUBECONFIG_LOCAL}" "${N}"
    else
        printf '  %skubeconfig absent — %stest/lima/run-phases.sh kubeconfig%s\n' "${D}" "${C}" "${N}"
    fi
else
    printf '  hôtes prod : lus dans %sbootstrap/hosts.yaml%s (gitignoré)\n' "${C}" "${N}"
    if [ -f "${REPO}/bootstrap/hosts.yaml" ]; then
        names=$(grep -E '^\s{4}[a-z0-9-]+:' "${REPO}/bootstrap/hosts.yaml" 2>/dev/null | tr -d ' :' | tr '\n' ' ' || true)
        printf '  hôtes déclarés : %s%s%s\n' "${C}" "${names:-?}" "${N}"
        printf '\n%sDiagnostic des nœuds%s\n' "${B}" "${N}"
        printf '  %sbootstrap/state.sh %s%s   %s(USER_REMOTE/SSH_OPTS si besoin)%s\n' "${C}" "${names}" "${N}" "${D}" "${N}"
    else
        printf '  %sbootstrap/hosts.yaml absent. Le créer : %scp bootstrap/hosts.example.yaml bootstrap/hosts.yaml%s\n' \
            "${D}" "${C}" "${N}"
        printf '  puis y mettre tes nœuds, et lancer : %sbootstrap/state.sh <hôte…>%s\n' "${C}" "${N}"
    fi
fi
printf '\n'
