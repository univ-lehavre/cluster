#!/usr/bin/env bash
#
# Fonctions PURES d'assertion pour l'atteignabilité des UI via le Gateway (#232,
# scénario 28). Aucun kubectl, aucun réseau : prennent un code HTTP déjà collecté
# et renvoient un verdict `STATUS|message` sur stdout (STATUS ∈ {ok, fail}).
# Testées sans cluster (test/unit/ui-assert.bats).
#
# Convention : une ligne "STATUS|message". L'appelant découpe sur le premier '|'.

# classify_ui_http HOST CODE
# Classe la réponse HTTP d'une UI atteinte via le Gateway. Un lien de portail est
# « vivant » si le Gateway route et que le backend répond — donc tout code < 400
# est un SUCCÈS, y compris :
#   - 200 (UI ouverte qui sert directement),
#   - 301/302 (redirection : install WordPress, login Grafana/Argo…),
#   - 401/403 (protégé : le backend répond, l'auth est juste exigée).
# Échec = pas de réponse (timeout → code vide) ou 5xx (backend cassé) ou 404
# (HTTPRoute mal monté). 404 est traité comme échec : le lien serait mort.
classify_ui_http() {
    local host=$1 code=$2
    if [ -z "${code}" ]; then
        printf 'fail|%s : aucune réponse (timeout) — Gateway/HTTPRoute/backend injoignable\n' "${host}"
        return 0
    fi
    case "${code}" in
        2[0-9][0-9] | 30[0-9] | 401 | 403)
            printf 'ok|%s : HTTP %s — UI atteignable via le Gateway\n' "${host}" "${code}" ;;
        *)
            printf 'fail|%s : HTTP %s (attendu <400 ou 401/403) — lien de portail non fonctionnel\n' "${host}" "${code}" ;;
    esac
}
