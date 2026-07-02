#!/usr/bin/env bash
#
# Scénario 28 — PORTAIL : les UI exposées répondent-elles via le NodePort L4 ? (#232, ADR 0092)
#
# Un portail à liens morts est pire qu'aucun portail. Depuis l'ADR 0092 l'exposition
# n'est plus L7 (Gateway/HTTPRoute/SNI, TLS de bordure) mais L4 : chaque UI exposée
# est servie par un Service `type: NodePort` sur `http://<IP-nœud>:<nodePort>` (zéro
# DNS, zéro LB-IPAM, zéro Gateway dans le chemin). Ce scénario suit EXACTEMENT le
# data path d'un lien du portail :
#
#   1. itère sur les endpoints `exposed: true` du CONTRAT (source de vérité unique,
#      contract/endpoints.example.yaml — lu via yq) ;
#   2. pour chacun, trouve le Service NodePort (`<service>-nodeport`, ou `portal`
#      lui-même qui EST un NodePort) et lit son `nodePort` RÉEL (spec.ports[].nodePort,
#      attribué par k8s dans 30000-32767 — jamais figé, ADR 0092) ;
#   3. sonde `http://<IP-interne-nœud>:<nodePort>/` depuis un pod ÉPHÉMÈRE DANS le
#      cluster (les nodePort répondent aussi NodeIP-interne→endpoints en eBPF Cilium,
#      kubeProxyReplacement) — pas de dépendance au réseau du poste de contrôle.
#
# « Atteignable » = curl rend un code HTTP != 000 : le data path L4 répond (le backend
# a parlé HTTP). On ne juge PAS le code applicatif (200/302/401/403…) : en L4 il n'y a
# plus de Gateway à blâmer, seul le chemin TCP→HTTP compte. 000 = pas de réponse
# (timeout/RST) = NodePort mort.
#
# CAS HTTPS : kubernetes-dashboard sert l'UI derrière Kong qui TERMINE le TLS
# (8443) ; son NodePort expose donc du HTTPS. On le sonde en `https://` + `-k`
# (cert auto-signé). Les autres UI sont en HTTP clair (ADR 0092 §2 : perte assumée
# du TLS de bordure).
#
# INDÉPENDANT du déploiement. SKIP NEUTRE si aucun endpoint `exposed: true` n'a son
# Service NodePort posé — sauf STRICT_UI=1.
#
# Variables : STRICT_UI=1 (échoue si aucune UI atteignable), CONTRACT (chemin du contrat).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

STRICT_UI=${STRICT_UI:-0}
CONTRACT=${CONTRACT:-../../contract/endpoints.example.yaml}

# shellcheck source=bench/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ ! -f "${CONTRACT}" ]; then
    log "✗ contrat introuvable : ${CONTRACT}"
    exit 1
fi

# IP INTERNE d'un nœud Ready : cible des NodePort, identique pour toutes les UI
# (un NodePort répond sur n'importe quel nœud). Sondée depuis un pod, donc l'IP
# interne du cluster suffit (pas besoin de l'IP routable du poste de contrôle).
node_ip=$(kubectl get nodes \
    -o 'jsonpath={.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)
if [ -z "${node_ip}" ]; then
    # `|| true` ci-dessus : sous `set -e`, un cluster injoignable ferait avorter la
    # substitution AVANT ce garde — on veut le message explicite + exit 1 propre.
    log "✗ aucune InternalIP de nœud — cluster injoignable ?"
    exit 1
fi

# Endpoints exposés du contrat : "service<TAB>namespace<TAB>id".
exposed=$(yq -r \
    '.endpoints[] | select(.exposed == true) | [.service, .namespace, .id] | @tsv' \
    "${CONTRACT}" 2>/dev/null)

if [ -z "${exposed}" ]; then
    if [ "${STRICT_UI}" = 1 ]; then
        log "✗ STRICT_UI=1 et aucun endpoint exposed:true au contrat."
        exit 1
    fi
    log "skip — aucun endpoint exposed:true au contrat (UI non exposées en L4)."
    exit 0
fi

# nodeport_svc SERVICE — nom du Service NodePort pour un service du contrat.
# Convention ADR 0092 : un Service séparé `<service>-nodeport` (ne touche pas le
# bundle vendored). EXCEPTION portal : son propre Service `portal` EST déjà un
# NodePort (brique maison) — pas de suffixe.
nodeport_svc() {
    case "$1" in
        portal) printf 'portal\n' ;;
        *) printf '%s-nodeport\n' "$1" ;;
    esac
}

fails=0 total=0 found=0
while IFS=$'\t' read -r service ns id; do
    [ -n "${service}" ] || continue
    total=$((total + 1))
    svc=$(nodeport_svc "${service}")

    # nodePort RÉEL attribué par k8s (jamais figé, ADR 0092). `|| true` : si le Service OU
    # son NAMESPACE est absent (ex. rook-ceph sur un banc local-path), kubectl sort en erreur
    # → sous `set -e` la substitution ferait AVORTER le script (rc=1) AVANT le test « absent »
    # ci-dessous. On neutralise donc le rc : un endpoint non déployé est un skip, pas un échec.
    nodeport=$(kubectl -n "${ns}" get svc "${svc}" \
        -o 'jsonpath={.spec.ports[0].nodePort}' 2>/dev/null || true)
    if [ -z "${nodeport}" ]; then
        # Service NodePort absent (UI non déployée ou pas encore exposée) — pas
        # un échec dur : le contrat couvre tous les profils, ce déploiement peut
        # ne pas porter cette UI.
        log "· ${id} : Service NodePort ${ns}/${svc} absent — ignoré (UI non déployée)."
        continue
    fi
    # PORT côté Service (≠ nodePort) : c'est CE port que `port-forward svc/…` cible (il se
    # branche sur le Service, pas sur le mapping NodePort du nœud). Le `nodePort` reste affiché
    # comme l'accès L4 réel (ADR 0092) que la sonde valide indirectement.
    svc_port=$(kubectl -n "${ns}" get svc "${svc}" \
        -o 'jsonpath={.spec.ports[0].port}' 2>/dev/null || true)
    found=$((found + 1))

    # Schéma : k8s-dashboard est en HTTPS (Kong termine le TLS) → https + -k.
    scheme=http; insecure=
    if [ "${id}" = k8s-dashboard-ui ]; then
        scheme=https; insecure=-k
    fi

    # Sonde via `kubectl port-forward` DEPUIS L'HÔTE (le poste de contrôle), PAS un pod-probe
    # intra-cluster : les ns d'UI appliquent un default-deny qui DROP l'egress d'un pod-sonde
    # (timeout, vécu au banc sur gitea/portal), et l'image curl externe peut manquer au registry
    # air-gap. Le port-forward passe par l'API server (toujours joignable) → robuste, et c'est
    # l'ACCÈS RÉEL d'un opérateur au NodePort L4 (ADR 0092). Pattern éprouvé du scénario 32.
    pf_port=$((18100 + total))
    kubectl -n "${ns}" port-forward "svc/${svc}" "${pf_port}:${svc_port}" \
        >/tmp/ui-pf-$$.log 2>&1 &
    pf_pid=$!
    sleep 3
    # `|| true` : curl sort en erreur (28=timeout, 7=refus) si l'UI ne répond pas → sous
    # `set -e`+`pipefail` la substitution avorterait AVANT le test « 000 » (faux rc global).
    code=$(curl -s ${insecure} -o /dev/null -w '%{http_code}' --max-time 12 \
        "${scheme}://localhost:${pf_port}/" 2>/dev/null | grep -oE '[0-9]+' | head -1 || true)
    kill "${pf_pid}" 2>/dev/null || true
    wait "${pf_pid}" 2>/dev/null || true
    code=${code:-000}

    if [ "${code}" != 000 ]; then
        log "✓ ${id} : HTTP ${code} via ${ns}/${svc} (nodePort ${nodeport}) — UI atteignable."
    else
        log "✗ ${id} : aucune réponse (000) via ${ns}/${svc} (nodePort ${nodeport}) — UI muette."
        fails=$((fails + 1))
    fi
done <<EOF
${exposed}
EOF

echo
if [ "${found}" -eq 0 ]; then
    if [ "${STRICT_UI}" = 1 ]; then
        log "✗ STRICT_UI=1 et aucun Service NodePort d'UI posé — UI non exposées."
        exit 1
    fi
    log "skip — aucun Service NodePort d'UI posé (UI non exposées sur ce déploiement)."
    exit 0
fi
if [ "${fails}" -eq 0 ]; then
    log "🎉 ${found}/${total} UI atteignable(s) en NodePort L4 — liens de portail fonctionnels."
else
    log "✗ ${fails}/${found} UI non atteignable(s) — voir ci-dessus."
    exit 1
fi
