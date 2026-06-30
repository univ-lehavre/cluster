#!/usr/bin/env bash
#
# Helpers partagés par les scénarios de banc (#296). Sourcé en tête de chaque
# scénario : `. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"`.
#
# PÉRIMÈTRE VOLONTAIREMENT MINIMAL : seuls les helpers STRICTEMENT identiques
# entre tous les scénarios sont factorisés ici. `cleanup()`, `assert_banc()`,
# `ceph()` etc. DIVERGENT d'un scénario à l'autre (ressources nettoyées propres
# à chacun, gardes spécifiques, redirections différentes) → ils restent définis
# DANS chaque scénario. Factoriser une fonction qui diverge subtilement
# introduirait des régressions silencieuses dans des tests.

# log MESSAGE — horodatage cyan + message (identique aux 29 scénarios).
log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

# read_lines VAR < flux → peuple le tableau nommé VAR (une entrée par ligne).
# Substitut portable de `mapfile`/`readarray`, absents du bash 3.2 de macOS — un
# scénario peut tourner depuis le poste de contrôle (ADR 0100).
read_lines() {
    local __name=$1 __line
    eval "${__name}=()"
    while IFS= read -r __line; do
        eval "${__name}+=(\"\${__line}\")"
    done
}
