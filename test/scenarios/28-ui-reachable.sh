#!/usr/bin/env bash
#
# Scénario 28 — PORTAIL : les UI exposées répondent-elles via le Gateway ? (#232)
#
# Un portail à liens morts est pire qu'aucun portail. Ce scénario découvre les
# HTTPRoute RÉELLEMENT posés (état du cluster, pas le contrat — robuste, sans yq)
# et vérifie que chaque hostname répond À TRAVERS le Gateway Cilium (HTTPRoute +
# TLS bordure cert-manager). C'est le chemin exact qu'un lien du portail emprunte.
#
# Les hostnames `*.cluster.lan` sont des PLACEHOLDERS non résolus en DNS cluster
# (l'admin réseau pose les vrais) : on sonde donc l'IP du Gateway (LB Cilium) via
# `curl --resolve host:443:IP` qui pose à la fois le SNI TLS ET l'en-tête Host
# (le Gateway Envoy choisit le certificat par SNI — sans SNI il RESET). TLS
# auto-signé toléré (CA interne). « Atteignable » = code < 400, ou 401/403
# (protégé mais vivant) — cf. classify_ui_http. Échec = timeout, 404 (route
# morte), 5xx (backend cassé).
#
# INDÉPENDANT du déploiement. SKIP NEUTRE si aucun HTTPRoute — sauf STRICT_UI=1.
#
# Variables : STRICT_UI=1 (échoue si aucune UI), GATEWAY_NS/GATEWAY_NAME (auto-détectés).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

STRICT_UI=${STRICT_UI:-0}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

# shellcheck source=test/lima/ui-assert.sh
. ../lima/ui-assert.sh

# Liste les HTTPRoute (tous namespaces) sous forme "ns/route hostname".
routes=$(kubectl get httproute -A \
    -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{" "}{.spec.hostnames[0]}{"\n"}{end}' 2>/dev/null \
    | awk 'NF==2')

if [ -z "${routes}" ]; then
    if [ "${STRICT_UI}" = 1 ]; then
        log "✗ STRICT_UI=1 et aucun HTTPRoute trouvé — les UI ne sont pas exposées."
        exit 1
    fi
    log "skip — aucun HTTPRoute (UI non exposées ; poser les Gateway après cert-manager)."
    exit 0
fi
log "✓ HTTPRoute découverts :"
printf '%s\n' "${routes}" | sed 's/^/    /'

# IP du Gateway Cilium (LB-IPAM). On prend la 1re IP d'un Service de type
# LoadBalancer dans le namespace d'un Gateway (Cilium crée un Service par Gateway).
gw_ip() {
    local ns=$1
    kubectl -n "${ns}" get svc -o jsonpath='{range .items[?(@.spec.type=="LoadBalancer")]}{.status.loadBalancer.ingress[0].ip}{"\n"}{end}' 2>/dev/null \
        | grep -E '^[0-9]' | head -1
}

fails=0 total=0
while read -r nsroute host; do
    [ -n "${host}" ] || continue
    total=$((total + 1))
    ns=${nsroute%%/*}
    ip=$(gw_ip "${ns}")
    if [ -z "${ip}" ]; then
        log "$(classify_ui_http "${host}" "" | sed 's/^[^|]*|//') (pas d'IP LB dans ${ns})"
        fails=$((fails + 1)); continue
    fi
    # Sonde HTTPS via l'IP du Gateway. INDISPENSABLE : envoyer le SNI TLS =
    # hostname (curl --resolve host:443:IP), pas seulement l'en-tête Host HTTP.
    # Le Gateway Envoy sélectionne le certificat par SNI ; sans SNI, il RESET le
    # handshake (faux négatif). busybox wget ne pose pas le SNI → on utilise curl
    # (--resolve = SNI + Host + cert matching). TLS auto-signé toléré (-k, CA
    # interne). Code HTTP via -w. (Bug historique : wget --header Host = pas de
    # SNI → « Connection reset » alors que curl --resolve donne 200.)
    code=$(kubectl -n "${ns}" run ui-probe-$$-"${RANDOM}" --rm -i --restart=Never \
        --image=alpine/curl --quiet --command -- \
        curl -sk -o /dev/null -w '%{http_code}' --max-time 12 \
        --resolve "${host}:443:${ip}" "https://${host}/" 2>/dev/null \
        | grep -oE '[0-9]+' | head -1)
    verdict=$(classify_ui_http "${host}" "${code}")
    if [ "${verdict%%|*}" = ok ]; then
        log "✓ ${verdict#*|}"
    else
        log "✗ ${verdict#*|}"
        fails=$((fails + 1))
    fi
done <<EOF
${routes}
EOF

echo
if [ "${fails}" -eq 0 ]; then
    log "🎉 ${total} UI atteignable(s) via le Gateway — liens de portail fonctionnels."
else
    log "✗ ${fails}/${total} UI non atteignable(s) — voir ci-dessus."
    exit 1
fi
