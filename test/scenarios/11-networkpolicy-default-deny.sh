#!/usr/bin/env bash
#
# Scénario 11 — NetworkPolicy default-deny appliquée par Cilium : vérifier
# que le socle `default-deny-all` (cf. platform/network-policies/) coupe
# bien tout l'egress, et qu'un `allow-dns` ciblé rouvre exactement le DNS.
#
# Vérifie, dans un namespace dédié :
#   1. AVANT policy : un pod joint l'extérieur (egress TCP 443) → réussit ;
#   2. APRÈS default-deny-all : le même egress est COUPÉ → échoue (timeout) ;
#   3. APRÈS ajout d'allow-dns : la résolution DNS REMARCHE, mais l'egress
#      non-DNS (TCP 443) reste coupé (le allow est chirurgical).
#
# Ce que ça prouve : Cilium (le CNI) APPLIQUE réellement les NetworkPolicy
# Kubernetes — pas seulement leur présence déclarative. Le comportement
# (deny additif, allow ciblé) est identique en prod. C'est le test le plus
# utile côté Cilium tant que les CiliumNetworkPolicy L7 / l'encryption ne
# sont pas déployées.
#
# Pré-requis : cluster K8s + Cilium opérationnels (kubectl). Pas de Ceph.
# Variables : NAMESPACE (défaut: test-netpol), KEEP=1 → pas de cleanup
set -euo pipefail

NS=${NAMESPACE:-test-netpol}
POD=netpol-probe
KEEP=${KEEP:-0}
# `LABEL` (clé=valeur) pour `kubectl label` ; en YAML inline on écrit
# séparément `clé: "valeur"` (le `=` y est invalide).
SC_KEY="test.cluster.dev/scenario"
SC_VAL="11-networkpolicy-default-deny"
LABEL="$SC_KEY=$SC_VAL"

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

# Exécute une commande réseau DANS le pod-sonde. Retourne le code de sortie de
# la commande distante.
in_pod() { kubectl -n "$NS" exec "$POD" -- sh -c "$1"; }

# Sonde DISCRIMINANTE = résolution DNS d'un service cluster (egress vers
# kube-system:53). On l'utilise comme signal unique du test, parce qu'elle est
# INTERNE et DÉTERMINISTE : pas de dépendance à un egress Internet (peu fiable
# sur un banc NAT — un `wget https://1.1.1.1` y échoue par intermittence, sans
# rapport avec la NetworkPolicy testée). `nslookup` borne lui-même son attente.
probe_dns() { in_pod "nslookup kubernetes.default.svc.cluster.local >/dev/null 2>&1"; }

log "Namespace $NS"
kubectl create ns "$NS" 2>/dev/null || true
kubectl label ns "$NS" "$LABEL" --overwrite >/dev/null

log "Déployer le pod-sonde ($POD)"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  labels: { "$SC_KEY": "$SC_VAL" }
spec:
  containers:
    - name: probe
      image: busybox:1.36
      command: ["sleep", "3600"]
EOF
kubectl -n "$NS" wait --for=condition=Ready --timeout=60s "pod/$POD"

log "[1/3] AVANT policy — la résolution DNS doit RÉUSSIR"
if probe_dns; then
    log "✓ DNS résout sans policy (état additif attendu : tout permis)"
else
    log "✗ DNS KO alors qu'aucune policy n'est posée — CoreDNS/kube-dns en panne ?"
    log "  (vérifier kube-system : kubectl -n kube-system get pods -l k8s-app=kube-dns)"
    exit 1
fi

log "[2/3] Appliquer default-deny-all (ingress+egress) — le DNS doit être COUPÉ"
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

# Laisser à Cilium le temps de programmer la policy (datapath eBPF).
log "  … attente application par Cilium (15s max)"
deny_ok=0
for _ in $(seq 1 15); do
    if ! probe_dns; then deny_ok=1; break; fi
    sleep 1
done
if [ "$deny_ok" = "1" ]; then
    log "✓ DNS coupé sous default-deny — Cilium applique bien la policy"
else
    log "✗ DNS TOUJOURS résolu après default-deny — Cilium n'applique pas la NetworkPolicy !"
    exit 1
fi

log "[3/3] Ajouter allow-dns — la résolution DNS doit REMARCHER"
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

log "  … attente application allow-dns (15s max)"
dns_ok=0
for _ in $(seq 1 15); do
    if probe_dns; then dns_ok=1; break; fi
    sleep 1
done
if [ "$dns_ok" != "1" ]; then
    log "✗ DNS ne remarche pas après allow-dns — policy allow non appliquée par Cilium"
    exit 1
fi
log "✓ DNS rétabli par allow-dns"

# Preuve que l'allow est CHIRURGICAL : il n'ouvre que le DNS (port 53). Un
# egress NON-DNS vers un service interne (l'API ClusterIP sur 443, déterministe
# et sans Internet) doit rester COUPÉ. On tente une connexion TCP brève ;
# `nc -w` borne l'attente. Sous allow-dns seul, elle doit échouer.
api_host=kubernetes.default.svc.cluster.local
log "  vérifier que l'egress non-DNS (API:443) reste coupé"
nondns_blocked=0
for _ in $(seq 1 10); do
    if ! in_pod "nc -z -w 3 $api_host 443 >/dev/null 2>&1"; then nondns_blocked=1; break; fi
    sleep 1
done
if [ "$nondns_blocked" != "1" ]; then
    log "✗ egress non-DNS (API:443) ouvert sous allow-dns — la policy fuit au-delà du DNS"
    exit 1
fi
log "✓ egress non-DNS reste coupé — l'allow est chirurgical"
log "✓ Cilium applique correctement default-deny + allow ciblé."
exit 0
