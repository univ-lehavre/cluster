#!/usr/bin/env bash
#
# Fonctions PURES d'assertion pour l'atteignabilité des UI en L4 (NodePort/hostPort
# sur l'IP du nœud, http://<IP-nœud>:<port> — ADR 0092 ; #232, scénario 28). Aucun
# kubectl, aucun réseau : prennent un code HTTP déjà collecté et renvoient un
# verdict `STATUS|message` sur stdout (STATUS ∈ {ok, fail}). Testées sans cluster
# (bench/unit/ui-assert.bats). Le verdict ne dépend que du code HTTP : la bascule
# du Gateway L7 vers le L4 (ADR 0092) ne change que la cible de la sonde
# (http://<IP>:<port> au lieu de https://<host>), pas la classification.
#
# Convention : une ligne "STATUS|message". L'appelant découpe sur le premier '|'.

# classify_ui_http TARGET CODE
# Classe la réponse HTTP d'une UI atteinte en L4 (TARGET = <IP-nœud>:<port> ou un
# libellé d'UI). Un lien de portail est « vivant » si le NodePort/hostPort route
# et que le backend répond — donc tout code < 400 est un SUCCÈS, y compris :
#   - 200 (UI ouverte qui sert directement),
#   - 301/302 (redirection : login Grafana/Argo…),
#   - 401/403 (protégé : le backend répond, l'auth est juste exigée).
# Échec = pas de réponse (timeout → code vide) ou 5xx (backend cassé) ou 404
# (NodePort sur le mauvais Service / backend absent). 404 = lien mort → échec.
classify_ui_http() {
    local host=$1 code=$2
    if [ -z "${code}" ]; then
        printf 'fail|%s : aucune réponse (timeout) — NodePort/hostPort/backend injoignable\n' "${host}"
        return 0
    fi
    case "${code}" in
        2[0-9][0-9] | 30[0-9] | 401 | 403)
            printf 'ok|%s : HTTP %s — UI atteignable en L4 (NodePort/hostPort)\n' "${host}" "${code}" ;;
        *)
            printf 'fail|%s : HTTP %s (attendu <400 ou 401/403) — lien de portail non fonctionnel\n' "${host}" "${code}" ;;
    esac
}
