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

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — pas de cleanup"; return; }
    log "Cleanup…"
    kubectl delete ns "$NS" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

# Exécute une commande réseau DANS le pod-sonde, avec un timeout côté shell
# distant. Retourne le code de sortie de la commande distante.
in_pod() { kubectl -n "$NS" exec "$POD" -- sh -c "$1"; }

# Teste l'egress TCP 443 vers un hôte externe stable. `wget --timeout` borne
# l'attente : sans policy → connecte ; sous default-deny → timeout (non-zéro).
probe_https() { in_pod "wget -q -T 5 -O /dev/null https://1.1.1.1/ 2>/dev/null"; }
# Teste la résolution DNS d'un service cluster (CoreDNS).
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

log "[1/3] AVANT policy — egress HTTPS doit RÉUSSIR"
if probe_https; then
    log "✓ egress sortant OK sans policy (état additif attendu : tout permis)"
else
    log "✗ egress KO alors qu'aucune policy n'est posée — souci réseau/DNS du banc ?"
    log "  (le banc doit avoir le DNS NAT + connectivité ; cf. RESULTS.md drift 0d)"
    exit 1
fi

log "[2/3] Appliquer default-deny-all (ingress+egress) — egress doit être COUPÉ"
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
    if ! probe_https; then deny_ok=1; break; fi
    sleep 1
done
if [ "$deny_ok" = "1" ]; then
    log "✓ egress coupé sous default-deny — Cilium applique bien la policy"
else
    log "✗ egress TOUJOURS ouvert après default-deny — Cilium n'applique pas la NetworkPolicy !"
    exit 1
fi

log "[3/3] Ajouter allow-dns — DNS doit REMARCHER, egress non-DNS rester coupé"
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

# Le allow-dns ne doit PAS rouvrir l'egress HTTPS (preuve qu'il est ciblé).
if probe_https; then
    log "✗ egress HTTPS rouvert par allow-dns — la policy fuit au-delà du DNS"
    exit 1
fi
log "✓ egress non-DNS reste coupé — l'allow est chirurgical"
log "✓ Cilium applique correctement default-deny + allow ciblé."
exit 0
