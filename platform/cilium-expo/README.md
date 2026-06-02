# cilium-expo — exposition réseau tout-Cilium

Exposition réseau du cluster **sans MetalLB ni ingress-nginx** : Cilium fournit
l'allocation d'IP LoadBalancer (LB-IPAM), l'annonce L2 (ARP) et la bordure L7
(Gateway API). Décision et justifications :
[ADR 0020](../../docs/decisions/0020-exposition-reseau-tout-cilium.md).

Les **features côté agent** (kube-proxy replacement, `l2announcements.enabled`,
`gatewayAPI.enabled`, `k8sClientRateLimit`) sont armées par
[`bootstrap/cni.sh`](../../bootstrap/cni.sh) — pas ici. Ce dossier ne contient
que les **CRs déclaratifs** (pool, policy L2, GatewayClass) et un Gateway de
test.

| Fichier                                                      | Rôle                                                     |
| ------------------------------------------------------------ | -------------------------------------------------------- |
| [`lb-ipam-pool.yaml`](lb-ipam-pool.yaml)                     | `CiliumLoadBalancerIPPool` (pool d'IP LoadBalancer)      |
| [`l2-announcement-policy.yaml`](l2-announcement-policy.yaml) | `CiliumL2AnnouncementPolicy` (annonce ARP sur eth1)      |
| [`gateway-class.yaml`](gateway-class.yaml)                   | `GatewayClass` `cilium` (`io.cilium/gateway-controller`) |
| [`gateway-test.yaml`](gateway-test.yaml)                     | `Gateway` HTTP de **test** (validation banc — pas prod)  |

## Pré-requis : CRDs Gateway API (v1.4.1)

Cilium **n'embarque pas** les CRDs Gateway API : il faut les poser **avant**
d'activer `gatewayAPI.enabled` (sinon la `GatewayClass`/`Gateway` est rejetée).
Version épinglée à celle ciblée par Cilium 1.19.x : **v1.4.1** (ADR 0006).

```bash
GWAPI=v1.4.1
BASE=https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/${GWAPI}/config/crd/standard
for crd in gatewayclasses gateways httproutes referencegrants grpcroutes; do
  kubectl apply -f "${BASE}/gateway.networking.k8s.io_${crd}.yaml"
done
# (Optionnel — TLSRoute / passthrough TLS, canal experimental :)
# kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/${GWAPI}/config/crd/experimental/gateway.networking.k8s.io_tlsroutes.yaml
```

## Déploiement

```bash
# 1) cni.sh a armé les features (kubeProxyReplacement + l2announcements +
#    gatewayAPI) et retiré kube-proxy — vérifier :
kubectl -n kube-system exec ds/cilium -- cilium-dbg status --verbose | grep -i KubeProxyReplacement

# 2) CRDs Gateway API (ci-dessus), puis les CRs de ce dossier :
kubectl apply -f platform/cilium-expo/lb-ipam-pool.yaml
kubectl apply -f platform/cilium-expo/l2-announcement-policy.yaml
kubectl apply -f platform/cilium-expo/gateway-class.yaml
```

## Validation (banc multi-node)

```bash
kubectl apply -f platform/cilium-expo/gateway-test.yaml
# Le Gateway doit obtenir une ADDRESS dans 192.168.67.240-250 :
kubectl get gateway test-http -o wide
# Le Service LoadBalancer dérivé doit porter la même EXTERNAL-IP :
kubectl get svc -l gateway.networking.k8s.io/gateway-name=test-http
# Depuis l'hôte Vagrant, l'IP répond en ARP (arp -an) ; brancher un HTTPRoute
# vers un pod echo pour un curl complet. Couper le nœud annonceur → l'IP est
# ré-annoncée par un autre nœud (failover L2).
kubectl delete -f platform/cilium-expo/gateway-test.yaml   # nettoyage
```

## Décisions assumées

- **Pool prod en TODO** : seul le banc (`192.168.67.240-250`) est défini. La
  plage prod (`10.67.2.0/22`) sera ajoutée **après arbitrage admin réseau** —
  aucune IP prod réservée à l'aveugle (ADR 0020).
- **`externalTrafficPolicy: Cluster`** (jamais `Local`) : en L2, `Local` droppe
  le trafic si le nœud annonceur n'a pas d'endpoint local.
- **L2 = failover, pas load-balancing** : un seul nœud annonce une IP donnée
  (cohérent avec le SPOF non-HA, ADR 0002/0009).
- **L2 Announcements = beta** en Cilium 1.19 ; Gateway API d'implémentation
  récente — d'où la validation banc obligatoire avant prod.
- **Service LoadBalancer du Gateway = exception tracée** de la « Couche 7b » de
  [`state.sh`](../../bootstrap/state.sh) (le principe « services applicatifs en
  ClusterIP » reste, exposition uniquement par la bordure).
