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
