#!/usr/bin/env bash
#
# Fonctions PURES de classification pour state.sh (audit P9 #12 / bats).
#
# Ces fonctions ne font NI SSH, NI kubectl : elles prennent en entrée des
# valeurs déjà collectées (par le shell distant) et renvoient un verdict
# `STATUS|message` sur stdout, où STATUS ∈ {ok, fail, skip}. Le but est de
# rendre la logique de décision de state.sh testable sans cluster (bats).
#
# Convention de sortie : une ligne "STATUS|message". L'appelant découpe sur le
# premier '|'. Aucune fonction n'écrit ailleurs que sur stdout, ni n'appelle
# `exit` (testabilité).

# classify_passwd STATUS DAYS
#   Mappe l'état brut du check "mot de passe debian modifié" (calculé côté nœud)
#   vers un verdict. STATUS_IN ∈ {MOD, NEVER, AMBIGUOUS, UNKNOWN/autre}.
#   - MOD       → ok   (modifié ~DAYS j après l'install)
#   - NEVER     → fail (jamais modifié depuis l'install)
#   - AMBIGUOUS → skip (install trop récent pour trancher)
#   - autre     → skip (dates illisibles)
classify_passwd() {
    local status_in=${1:-} days=${2:-0}
    case "$status_in" in
        MOD)
            printf 'ok|mot de passe debian modifié (~%s j après install)\n' "$days"
            ;;
        NEVER)
            printf 'fail|mot de passe debian JAMAIS modifié depuis l'\''install\n'
            ;;
        AMBIGUOUS)
            printf 'skip|install récent (%s j) — check passwd ambigu, re-vérifier dans 2 jours\n' "$days"
            ;;
        *)
            printf 'skip|impossible de lire les dates passwd/install (sudo ? chage ? machine-id ?)\n'
            ;;
    esac
}

# classify_hdd TOTAL CLEAN DIRTY MIN
#   Verdict sur les HDD bruts prêts pour Ceph.
#   - total illisible (vide ou "?")     → skip
#   - dirty > 0                          → fail (signatures résiduelles)
#   - clean >= MIN et dirty == 0         → ok
#   - sinon                              → fail (pas assez de disques)
classify_hdd() {
    local total=${1:-?} clean=${2:-0} dirty=${3:-0} min=${4:-1}
    if [ "$total" = "?" ] || [ -z "$total" ]; then
        printf 'skip|impossible d'\''inspecter les disques (sudo ? wipefs ?)\n'
        return
    fi
    if [ "$dirty" -gt 0 ]; then
        printf 'fail|%s HDD avec partition/signature résiduelle\n' "$dirty"
    elif [ "$clean" -ge "$min" ]; then
        printf 'ok|%s/%s HDD bruts (≥ %s requis)\n' "$clean" "$total" "$min"
    else
        printf 'fail|%s/%s HDD bruts (< %s requis)\n' "$clean" "$total" "$min"
    fi
}

# classify_device_state STATE LABEL
#   Verdict générique pour un device (NVMe block.db) ou un chemin (/var/lib/rook)
#   dont l'état brut est clean|dirty|absent.
#   - clean  → ok
#   - dirty  → fail
#   - absent → skip
#   - autre  → skip (indéterminé)
classify_device_state() {
    local state=${1:-} label=${2:-device}
    case "$state" in
        clean)  printf 'ok|%s brut/propre\n' "$label" ;;
        dirty)  printf 'fail|%s a une signature/partition/des résidus\n' "$label" ;;
        absent) printf 'skip|%s absent\n' "$label" ;;
        *)      printf 'skip|%s état indéterminé (%s)\n' "$label" "$state" ;;
    esac
}

# count_field FIELD STRING
#   Renvoie le Nᵉ champ (1-indexé) d'une chaîne séparée par des espaces, ou ""
#   si absent. Utilitaire de parsing du rapport positionnel renvoyé par le shell
#   distant (ex. "12 12 0 clean clean") — testable indépendamment.
count_field() {
    local n=${1:-1}; shift
    local str=${*:-}
    # shellcheck disable=SC2086 # split voulu sur les espaces
    set -- $str
    if [ "$n" -ge 1 ] && [ "$n" -le "$#" ]; then
        eval "printf '%s\\n' \"\${$n}\""
    else
        printf '\n'
    fi
}
