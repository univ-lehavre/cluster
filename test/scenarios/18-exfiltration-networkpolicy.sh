#!/usr/bin/env bash
#
# Scénario 18 — ATTAQUE CONTRÔLÉE : exfiltration réseau → NetworkPolicy coupe.
#
# Sécurité ACTIVE (ADR 0025) : un pod « compromis » TENTE D'EXFILTRER des
# données vers une destination hors de son périmètre ; on asserte la chaîne
# Détection → Alerte → Réaction. Prolonge le scénario 11 (qui prouve que Cilium
# APPLIQUE default-deny) en le formulant comme une intention adverse explicite.
#
# La cible d'exfiltration est INTERNE et DÉTERMINISTE (l'API ClusterIP:443),
# JAMAIS l'Internet (garde-fou ADR 0025 : pas de cible tierce ; et l'egress
# Internet est de toute façon peu fiable sur un banc NAT — cf. note du 11).
# Elle représente le « canal d'exfiltration » que la NetworkPolicy doit couper.
#
# Chaîne D/A/R assertée :
#   [1] baseline            : sans policy, le canal d'exfiltration est OUVERT.
#   [R] Réaction (BLOQUANT) : après default-deny-all (+ allow-dns chirurgical),
#       l'exfiltration est COUPÉE, alors que le DNS LÉGITIME remarche. C'est la
#       défense qui agit, sans casser le trafic autorisé.
#   [D] Détection           : si Hubble est présent (ADR 0019), `hubble observe
#       --verdict DROPPED` montre le drop du flux adverse. Best-effort (WARN).
#   [A] Alerte              : N/A — l'alerte réseau temps réel relève d'un futur
#       axe (métriques Hubble / runtime), DIFFÉRÉ (ADR 0025 §4).
#
# Pourquoi c'est valable en prod : l'application des NetworkPolicy par le CNI est
# identique banc/prod (eBPF Cilium). Aucune dépendance arch/stockage.
#
# GARDE-FOU (ADR 0025) : scénario OFFENSIF → banc jetable uniquement.
#
# Pré-requis : cluster K8s + Cilium opérationnels (kubectl). Pas de Ceph.
# Variables :
#   NAMESPACE (défaut: test-exfil)   KEEP=1 → pas de cleanup
#   BANC=1                           force l'exécution (cible déclarée jetable)
set -euo pipefail

NS=${NAMESPACE:-test-exfil}
POD=exfil-probe
KEEP=${KEEP:-0}
BANC=${BANC:-0}
SC_KEY="test.cluster.dev/scenario"
SC_VAL="18-exfiltration-networkpolicy"

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# ── Garde « banc jetable uniquement » (ADR 0025) ── cf. scénario 17.
assert_banc() {
    [ "$BANC" = "1" ] && { log "BANC=1 — cible déclarée jetable (garde levée)"; return; }
    local ips ip
    ips=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null) || {
        log "✗ kubectl get nodes a échoué — cluster joignable ?"; exit 2; }
    for ip in $ips; do
        case "$ip" in
            192.168.* | 10.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[0-1].*) ;;
            *) log "✗ REFUS : nœud $ip hors plage de banc — offensif interdit hors"
               log "  banc jetable (ADR 0025). Relancer avec BANC=1 si banc de test."; exit 2 ;;
        esac
    done
    log "✓ garde banc : tous les nœuds en IP privée de banc ($ips)"
}

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

assert_banc

# Exécute une commande réseau DANS le pod-sonde.
in_pod() { kubectl -n "$NS" exec "$POD" -- sh -c "$1"; }

# Canal d'exfiltration simulé = connexion TCP vers l'API ClusterIP:443 (interne,
# déterministe, sans Internet). `nc -w` borne l'attente. Le DNS reste le témoin
# du trafic LÉGITIME à préserver.
exfil_channel() { in_pod "nc -z -w 3 kubernetes.default.svc.cluster.local 443 >/dev/null 2>&1"; }
probe_dns()     { in_pod "nslookup kubernetes.default.svc.cluster.local >/dev/null 2>&1"; }

log "Namespace $NS"
kubectl create ns "$NS" 2>/dev/null || true
kubectl label ns "$NS" "$SC_KEY=$SC_VAL" --overwrite >/dev/null

log "Déployer le pod « compromis » ($POD)"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  containers:
    - name: probe
      image: busybox:1.36
      command: ["sleep", "3600"]
EOF
kubectl -n "$NS" wait --for=condition=Ready --timeout=60s "pod/$POD"

log "[1/3] baseline — sans policy, le canal d'exfiltration doit être OUVERT"
exfil_ok=0
for _ in $(seq 1 10); do
    if exfil_channel; then exfil_ok=1; break; fi
    sleep 1
done
if [ "$exfil_ok" = "1" ]; then
    log "✓ canal d'exfiltration ouvert sans policy (état additif attendu)"
else
    log "✗ canal fermé alors qu'aucune policy n'est posée — une policy résiduelle ?"
    exit 1
fi

log "[2/3][R] Appliquer default-deny-all — l'exfiltration doit être COUPÉE"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
EOF
# allow-dns chirurgical : on rouvre UNIQUEMENT le DNS légitime, pour prouver que
# la coupure de l'exfiltration est ciblée (le trafic autorisé n'est pas cassé).
kubectl -n "$NS" apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: $NS
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - { protocol: UDP, port: 53 }
        - { protocol: TCP, port: 53 }
EOF

log "  … attente application par Cilium (datapath eBPF, 15s max)"
cut_ok=0
for _ in $(seq 1 15); do
    if ! exfil_channel; then cut_ok=1; break; fi
    sleep 1
done
if [ "$cut_ok" = "1" ]; then
    log "✓ [R] exfiltration COUPÉE par la NetworkPolicy — la défense agit"
else
    log "✗ [R] exfiltration TOUJOURS possible après default-deny — Cilium n'applique pas !"
    exit 1
fi

log "[3/3] le DNS LÉGITIME doit remarcher (coupure chirurgicale, pas globale)"
dns_ok=0
for _ in $(seq 1 15); do
    if probe_dns; then dns_ok=1; break; fi
    sleep 1
done
if [ "$dns_ok" != "1" ]; then
    log "✗ DNS légitime cassé — la policy est trop large (faux positif réseau)"
    exit 1
fi
log "✓ DNS légitime préservé — la coupure cible bien le canal adverse."

# [D] Détection : Hubble a-t-il observé le DROP du flux d'exfiltration ?
if command -v hubble >/dev/null 2>&1; then
    log "[D] vérifier le drop côté Hubble (observabilité réseau, ADR 0019)…"
    if hubble observe --namespace "$NS" --verdict DROPPED --last 50 2>/dev/null | grep -q .; then
        log "✓ [D] Hubble a observé des flux DROPPED dans $NS — détection réseau OK"
    else
        log "! [D] aucun DROP Hubble capté (relay joignable ? fenêtre courte) — non bloquant"
    fi
else
    log "! [D] hubble CLI absent — détection réseau non vérifiée (non bloquant)"
fi
log "[A] alerte : N/A — alerte réseau temps réel différée (ADR 0025 §4)"

log "✓ Chaîne D/R validée : Cilium coupe l'exfiltration, préserve le légitime."
exit 0
