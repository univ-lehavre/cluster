# Architecture — exposition réseau (de l'IP au service web)

Cette page raconte, **de bout en bout**, comment une application déployée sur le
cluster devient joignable depuis le réseau local — et **ce qui a été validé sur
le banc**. Elle relie quatre décisions :
[ADR 0019](../decisions/0019-durcissement-reseau-cilium.md) (durcissement
Cilium), [ADR 0020](../decisions/0020-exposition-reseau-tout-cilium.md)
(exposition tout-Cilium),
[ADR 0021](../decisions/0021-cert-manager-ca-interne.md) (TLS de bordure),
[ADR 0022](../decisions/0022-argocd-gitops-applicatif.md) (GitOps / Argo CD) et
[ADR 0071](../decisions/0071-exposition-gateway-hostnetwork.md) (Gateway en
hostNetwork). Les termes en gras sont définis dans le
[glossaire](../glossaire.md#exposition-réseau-comment-on-atteint-un-service-depuis-lextérieur-du-cluster).

> **Périmètre.** Le cluster de production **n'est pas exposé à Internet**
> (réseau privé `10.0.0.0/22`). « Bordure » = entrée du **réseau local**, pas du
> Web.

## Le choix structurant : tout-Cilium

Le plan d'origine prévoyait deux briques externes (MetalLB pour l'IP,
ingress-nginx pour le routage web). On les a **remplacées par Cilium**, déjà
présent comme CNI : moins de composants à exploiter, un seul plan de données
eBPF. C'est une déviation assumée, tracée en
[ADR 0020](../decisions/0020-exposition-reseau-tout-cilium.md).

## Le chemin par défaut : Gateway en hostNetwork (ADR 0071)

Depuis l'[ADR 0071](../decisions/0071-exposition-gateway-hostnetwork.md), le
chemin **par défaut** expose le Gateway en **hostNetwork** : l'Envoy bind 80/443
**directement sur l'IP du nœud** (`gatewayAPI.hostNetwork.enabled=true`), sans
IP virtuelle. On supprime alors les couches 1 et 2 ci-dessous (ARP/L2 + LB-IPAM)
— le client joint `https://<host>` qui résout vers l'**IP du nœud**, et la
chaîne démarre directement à la couche 3 (Gateway/Envoy). C'est le mode
`gateway` (unique), valable banc Lima comme VM publique mono-NIC.

> **Piège #42786** : en hostNetwork (Cilium 1.19.x) le `Gateway` reste
> `Programmed: False` alors que le trafic passe. On **gate la readiness sur la
> joignabilité L7 réelle** (`curl --resolve <host>:443:<node_ip>`), jamais sur
> `.status.Programmed` (ADR 0071 §6).

Le chemin LB-IPAM + L2 décrit ci-dessous (IP virtuelle annoncée sur le LAN)
reste une **option de prod** (`CILIUM_LB_IPAM_ENABLED=1`) quand l'admin réseau
fournit une plage dédiée.

## La chaîne, couche par couche (chemin LB-IPAM optionnel)

```text
  Client du LAN
      │  https://argocd.cluster.lan
      ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 1. ARP / annonce L2  → "l'IP 192.168.67.240, c'est ce nœud"  │  Cilium L2     (option prod)
 ├─────────────────────────────────────────────────────────────┤
 │ 2. IP LoadBalancer   → pool LB-IPAM (192.168.67.240-250)     │  Cilium LB-IPAM (option prod)
 ├─────────────────────────────────────────────────────────────┤
 │ 3. Gateway (Envoy)   → termine le TLS (HTTPS)                │  Cilium Gateway API
 │      └─ certificat fourni par cert-manager (CA interne)      │  cert-manager
 ├─────────────────────────────────────────────────────────────┤
 │ 4. HTTPRoute         → aiguille le nom/chemin vers le Service │  Cilium Gateway API
 ├─────────────────────────────────────────────────────────────┤
 │ 5. Service → Pod     → routage eBPF (sans kube-proxy)        │  kubeProxyReplacement
 └─────────────────────────────────────────────────────────────┘
      ▼
   Le pod applicatif (ex. argocd-server)
```

> En mode par défaut (hostNetwork), les couches 1-2 disparaissent : l'Envoy du
> Gateway (couche 3) bind 80/443 sur l'IP du nœud, le client l'atteint
> directement.

1. **Datapath eBPF (`kubeProxyReplacement`).** Cilium remplace kube-proxy : tout
   le routage de Service passe par eBPF dans le noyau. Prérequis de tout le
   reste.
2. **Allocation d'IP (`LB-IPAM`).** Un `CiliumLoadBalancerIPPool` réserve une
   plage d'IP du réseau local ; chaque Service `LoadBalancer` en reçoit une.
3. **Annonce sur le réseau (`L2`).** Une `CiliumL2AnnouncementPolicy` fait qu'un
   nœud répond en **ARP** pour ces IP — elles deviennent joignables sur le LAN.
4. **Bordure web (`Gateway API`).** Un `Gateway` (servi par l'Envoy intégré à
   Cilium) **termine le TLS** ; des `HTTPRoute` aiguillent par nom/chemin.
5. **TLS de bordure (`cert-manager`).** Le certificat du `Gateway` est produit
   et renouvelé automatiquement par cert-manager via une **CA interne** (pas de
   Let's Encrypt : cluster non joignable depuis Internet). Mécanisme :
   **gateway-shim** (une annotation sur le Gateway suffit).

Au-dessus de cette chaîne, **Argo CD** (GitOps) déploie les applications depuis
git ; son interface est elle-même exposée par cette chaîne (Gateway + cert).

## Ce qui a été validé sur le banc

> ⏱️ **Photo historique (banc Vagrant, mai 2026).** Le tableau ci-dessous date
> du banc Vagrant (`192.168.67.0/24`), aujourd'hui **déprécié au profit du banc
> Lima** ([ADR 0038](../decisions/0038-lima-seul-banc-local.md)). L'état de
> validation **courant** (dont cert-manager/Gateway+TLS, scénario 28) vit dans
> le journal Lima vivant —
> [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md) et
> [lecons-des-runs.md](lecons-des-runs.md). On ne réécrit pas ce constat daté
> (honnêteté des Runs,
> [ADR 0052](../decisions/0052-reproductibilite-des-resultats.md)).

Banc Vagrant (3 VM Debian arm64, K8s 1.34.8, Cilium 1.19.4). Détail
chronologique et findings : [validation-banc.md](validation-banc.md) et le
journal brut [`bench/RESULTS.md`](../../bench/RESULTS.md).

| Couche                                         | Validé banc  | Preuve observée                                                                                                                            |
| ---------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 1. `kubeProxyReplacement` + retrait kube-proxy | ✅           | `KubeProxyReplacement: True` (3 nœuds) ; kube-proxy supprimé ; **DNS + ClusterIP OK sans kube-proxy** (`kubernetes.default` → `10.96.0.1`) |
| 2. LB-IPAM (pool d'IP)                         | ✅           | `CiliumLoadBalancerIPPool` : 11 IP disponibles, 0 conflit                                                                                  |
| 3. Annonce L2                                  | ✅           | depuis l'hôte, **ARP résout `192.168.67.240`** → MAC d'un nœud                                                                             |
| 4. Gateway API + HTTPRoute                     | ✅ (partiel) | Gateway de test → IP `192.168.67.240`, `PROGRAMMED True` ; `curl` → **HTTP 404** (Envoy répond)                                            |
| 5. cert-manager (TLS de bordure)               | ⏳ à valider | non déployé sur le banc à ce jour                                                                                                          |
| Argo CD (GitOps)                               | ✅ (cœur)    | déployé, `server.insecure` effectif, **Application de test → `Synced/Healthy`**                                                            |
| Argo CD via Gateway + cert + gRPC              | ⏳ à valider | dépend de cert-manager sur banc                                                                                                            |

> **Honnêteté.** Le ✅ « partiel » du Gateway = l'IP est attribuée et joignable,
> mais le routage applicatif complet (avec un vrai `HTTPRoute` + backend) et la
> terminaison TLS (qui dépend de cert-manager) **restent à valider sur banc**.
> Aucun de ces composants n'est encore déployé en **production**.

## Deux pièges réels rencontrés sur le banc (et corrigés)

- **Détection de bascule trop hâtive** (`cni.sh`) : la vérification que Cilium
  avait pris le relais de kube-proxy concluait « pas prêt » à tort (les agents
  redémarraient encore) → kube-proxy n'était jamais retiré. Corrigé par une
  attente de convergence ([finding #23](validation-banc.md)).
- **Image épinglée sur la mauvaise architecture** : l'image `redis` d'Argo CD
  était épinglée sur un digest **amd64** au lieu de l'index multi-arch →
  `exec format error` sur le banc **arm64**. Corrigé en pinant le digest d'index
  ([finding #25](validation-banc.md)).

Ces deux pièges illustrent pourquoi la **validation sur banc est obligatoire** :
ni l'un ni l'autre n'était détectable par l'analyse statique (lint).

## À retenir (limites assumées)

- **L2 = bascule, pas répartition de charge** : une IP est portée par un seul
  nœud à la fois (cohérent avec le cluster non-HA, ADR 0002/0009).
- **CA interne — avertissement TLS attendu** : le certificat du Gateway est
  signé par une **CA interne** (réseau privé, pas d'autorité publique — ADR
  0003/0021), **sur le banc comme en prod**. Le navigateur affiche donc «
  connexion non sécurisée » à `https://*.cluster.lan` : c'est **normal et sans
  danger** ici (réseau privé, TLS bien présent, juste une racine non publique).
  On **accepte le certificat une fois** ; les sondes (`access.sh`, scénario 28)
  utilisent `curl -k`. Pour supprimer l'avertissement : importer le root
  (`root-ca-secret`) dans le trust store du poste — non fait par défaut (poste
  dev jetable).
- **Plages prod en TODO** : pool LB-IPAM et hostname `.lan` sont des
  **placeholders** à fixer avec l'admin réseau avant la prod.
