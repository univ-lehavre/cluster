# 0020 — Exposition réseau tout-Cilium (kube-proxy replacement + LB-IPAM + L2 + Gateway API)

## Contexte

L'exposition réseau du cluster reste à construire (Phase 1 du plan
[`pipeline-collaborations`](../plans/2026-06-02-pipeline-collaborations.md)). Le
cluster est bare-metal, kubeadm, **4 nœuds non-HA** (control-plane unique = SPOF
assumé, cf. [ADR 0002](0002-control-plane-unique-avec-endpoint.md) et
[ADR 0009](0009-pourquoi-4-noeuds.md)). Cilium 1.19.4 est **déjà le CNI**
([`bootstrap/cni.sh`](../../bootstrap/cni.sh)), durci avec chiffrement WireGuard
pod-to-pod + Hubble relay/CLI ([ADR 0019](0019-durcissement-reseau-cilium.md)).
Stockage Rook-Ceph ([ADR 0018](0018-rook-ceph-vs-longhorn.md)). Réseau prod
`10.67.2.0/22` (isolé) ; banc Vagrant `192.168.67.0/24`.

Sur bare-metal, un `Service type=LoadBalancer` n'a pas de provider cloud : il
faut (a) **allouer** des IP virtuelles depuis un pool et (b) **annoncer** ces IP
sur le LAN pour qu'elles soient joignables. Il faut aussi un point d'entrée
HTTP(S) en bordure (routage par host/path, terminaison TLS).

> **« Bordure » = bordure du réseau privé, pas Internet.** Le cluster de
> production **n'est pas accessible depuis l'extérieur** (cohérent ADR 0003 :
> réseau `10.67.2.0/22` isolé). Les IP du pool sont annoncées sur le **LAN
> interne** ; le Gateway est le point d'entrée des **clients internes** (LAN /
> VPN), jamais d'Internet. Conséquence directe pour le TLS de bordure (étape
> cert-manager suivante) : **ACME/Let's Encrypt est exclu** (challenge
> injoignable depuis l'extérieur) → une **CA interne** sera utilisée.

Le plan, calqué sur le benchmark DataOps, prévoyait deux briques OSS externes :
**étape 1.1 = MetalLB** (`IPAddressPool` + `L2Advertisement`) puis **étape 1.2 =
ingress-nginx** (contrôleur d'ingress exposé via une IP MetalLB). Le plan note
d'ailleurs « Cilium ne fait pas le LB de service externe ici » — hypothèse que
cet ADR remet en cause : Cilium ≥ 1.13/1.14 sait désormais faire LB-IPAM,
annonces L2 et Gateway API **nativement**, et le RUNBOOK décrit déjà
`kubeProxyReplacement` comme option (section « Optionnel —
`kubeProxyReplacement` »).

La question : faut-il ajouter MetalLB + ingress-nginx (deux composants externes,
deux datapaths supplémentaires) alors que le CNI Cilium en place couvre
maintenant ces trois fonctions (allocation d'IP, annonce L2, passerelle L7) au
sein du datapath eBPF déjà déployé ?

## Décision

Adopter une exposition réseau **tout-Cilium**, en remplacement de MetalLB (étape
1.1) **et** d'ingress-nginx (étape 1.2). Quatre fonctions Cilium sont activées,
appliquées par [`bootstrap/cni.sh`](../../bootstrap/cni.sh) (idempotent à
l'install **et** à l'upgrade, comme le durcissement de l'ADR 0019), les CRs
étant versionnés sous [`platform/cilium-expo/`](../../platform/cilium-expo/).

### 1. `kubeProxyReplacement` — remplacement de kube-proxy par eBPF

`--set kubeProxyReplacement=true` (+ `k8sServiceHost=cluster-api`,
`k8sServicePort=6443`, **obligatoires** sans kube-proxy : l'agent ne peut plus
joindre l'API server via la ClusterIP `kubernetes.default`). Le routage des
Services (ClusterIP, NodePort, LoadBalancer) passe d'`iptables` au datapath
**eBPF**. C'est le pré-requis du LB-IPAM, des annonces L2 et du Gateway API.
**Impact transverse assumé** : ce réglage change le datapath de _tout_ le
cluster, pas seulement la bordure ; à valider en priorité sur banc. En 1.19 le
flag est un **booléen** (`true`/`false`) — les anciennes valeurs
`strict`/`partial`/`probe` n'existent plus — et il active automatiquement
NodePort/HostPort/ExternalIPs (les flags `--enable-node-port`, etc. sont retirés
en 1.19 : ne **pas** les positionner).

Retrait de kube-proxy : ordre **obligatoire** — Cilium converge d'abord
(`KubeProxyReplacement: True`), **puis** on retire le DaemonSet/ConfigMap
kube-proxy et on purge ses règles iptables résiduelles par nœud. Durabilité :
`skipPhases: [addon/kube-proxy]` dans l'`InitConfiguration` kubeadm (v1beta4)
évite que `kubeadm init`/`upgrade` ne les recrée.

### 2. LB-IPAM — allocation d'IP LoadBalancer (remplace le pool MetalLB)

`CiliumLoadBalancerIPPool` (`cilium.io/v2`, **promu** en 1.19 — `v2alpha1`
déprécié) versionné sous `platform/cilium-expo/`. LB-IPAM est actif **dès qu'un
pool existe** (pas de flag d'activation). **Banc** : pool `192.168.67.240-250`.
**Prod (`10.67.2.0/22`)** : **TODO documenté**, plage à fixer **avec l'admin
réseau** — aucune IP prod attribuée à l'aveugle (collision sur un /22 partagé
hors de notre maîtrise).

### 3. L2 Announcements — annonce des IP sur le LAN (remplace `L2Advertisement`)

`CiliumL2AnnouncementPolicy` (`cilium.io/v2alpha1` — ce CRD **reste** en alpha
en 1.19, à ne pas confondre avec le pool en `v2`) +
`--set l2announcements.enabled=true`. Un nœud élu (lease) répond aux ARP pour
les IP du pool. Le réglage `k8sClientRateLimit.qps/burst` est **relevé** : L2
crée un Lease par Service LoadBalancer renouvelé en continu, et les défauts
(5–10 QPS) sont vite saturés. **Cadrage non-HA honnête** : L2 fournit du
**failover d'IP** (réélection si le nœud annonceur tombe), **PAS** de la
répartition de charge multi-nœuds — tout le trafic d'une IP transite par un seul
nœud à la fois. Cohérent avec le SPOF déjà assumé (ADR 0002) ; on ne survend pas
une HA inexistante. **Statut amont** : les L2 Announcements sont en **beta** en
1.19.

### 4. Gateway API — bordure L7 (remplace ingress-nginx)

`--set gatewayAPI.enabled=true` (active `enable-envoy-config` ; `l7Proxy=true`
est déjà le défaut), **CRDs Gateway API v1.4.1 pré-installées** (Cilium ne les
embarque pas), `GatewayClass`/`Gateway` (`gateway.networking.k8s.io/v1`)
versionnés. `controllerName` = `io.cilium/gateway-controller`. Le `Gateway` fait
créer **un** `Service type=LoadBalancer` (servi par LB-IPAM + L2 → boucle
tout-Cilium) ; routage host/path via `HTTPRoute` et **terminaison TLS** via un
listener HTTPS (`mode: Terminate` + `certificateRefs` vers un Secret).
`externalTrafficPolicy` reste **`Cluster`** (et non `Local`) : en L2, `Local`
_droppe_ le trafic si le nœud annonceur n'héberge pas d'endpoint local.

**Pourquoi cette déviation.** Le plan et le benchmark DataOps nommaient
MetalLB + ingress-nginx. C'est une **déviation assumée** : maximiser Cilium déjà
en place plutôt que d'empiler deux composants externes. Bénéfices structurants :
**moins de composants à opérer/patcher/superviser** ; **datapath eBPF unifié**
(CNI + service-routing + LB + bordure dans un seul plan de données, au lieu de
Cilium + kube-proxy + MetalLB speaker + nginx) ; **observabilité L7 Hubble**
native sur le trafic de bordure.

## Statut

Accepted (2026-06-02).

## Conséquences

**Bénéfices.**

- Deux composants externes en moins (MetalLB + ingress-nginx) : surface
  d'opération, de mise à jour et de supervision réduite, une seule matrice de
  versions à suivre (la ligne Cilium).
- **Datapath eBPF unifié** : CNI, chiffrement WireGuard (ADR 0019),
  service-routing (kube-proxy supprimé), LB-IPAM, annonce L2 et bordure L7 dans
  un seul plan de données.
- **Observabilité L7 de bordure** : le trafic traversant le Gateway est visible
  via `hubble observe`, dans la continuité de l'ADR 0019.
- Tout est **tracé et convergent** : `--set` et CRs appliqués par `cni.sh` à
  l'install et à l'upgrade ; un cluster reconverge en rejouant le script.

**Prix à payer.**

- **Déviation du plan écrit et du benchmark** : la fiche Phase 1 (étapes
  1.1/1.2) nommait MetalLB + ingress-nginx, deux briques OSS éprouvées. On
  s'écarte d'un chemin balisé pour parier sur la consolidation Cilium ; les
  étapes 1.1/1.2 du plan sont à réécrire en conséquence.
- **`kubeProxyReplacement` impacte tout le cluster** : bascule du
  service-routing de _tous_ les Services, pas un changement de bordure isolé.
  Une régression touche l'ensemble des charges.
- **Maturité amont inégale** : L2 Announcements en **beta** (1.19), Gateway API
  d'implémentation **récente** (bugs connus sur certains setups 1.19).
- **Pas de répartition de charge** : L2 = failover d'IP mono-nœud, conforme au
  non-HA (ADR 0002/0009), à ne pas confondre avec de la HA.

**Garde-fous.**

- **Validation banc multi-node obligatoire avant prod** : un
  `Service type=LoadBalancer` obtient une IP du pool `192.168.67.240-250`,
  joignable en ARP/L2 ; une `HTTPRoute` route vers un pod echo ; le failover
  d'IP fonctionne à l'arrêt du nœud annonceur ; **aucune régression** de
  service-routing après `kubeProxyReplacement` (Ceph `HEALTH_OK`, CoreDNS,
  ClusterIP applicatifs).
- **`k8sServiceHost=cluster-api` à valider** : le nom est résolu via
  `/etc/hosts` du nœud (rôle `k8s-install`) ; les pods `cilium-agent` étant en
  `hostNetwork`, ils utilisent ce resolver — vérifier sur banc avant de retirer
  kube-proxy. Repli sûr documenté : IP du control-plane en dur, ou `auto`.
- **IP prod non attribuée à l'aveugle** : la plage LB-IPAM dans `10.67.2.0/22`
  reste **TODO** explicite jusqu'à arbitrage avec l'admin réseau.
- **Exception drift tracée** : `bootstrap/state.sh` « Couche 7b — Exposition
  réseau » (audit P6 #25) flagge tout `Service type=LoadBalancer` comme DRIFT
  (hors `kubernetes-dashboard`). Le `Service` du Gateway de bordure y est ajouté
  en **exception nommée**. Le principe #25 reste intact : services applicatifs
  en ClusterIP, exposition **uniquement** par la bordure Gateway.
- **`rollout restart` + vérification post-upgrade** : comme pour WireGuard (ADR
  0019), `cilium upgrade` ne suffit pas à armer un réglage ; `cni.sh` force le
  rollout des agents et **échoue visiblement** si le datapath attendu n'est pas
  réellement actif.
- **NetworkPolicies default-deny préservées** (ADR 0019) : ouvrir explicitement
  les flux vers/depuis le Gateway, ne pas relâcher le default-deny.

## Alternatives écartées

**MetalLB + ingress-nginx (le plan d'origine, étapes 1.1/1.2).** Solution OSS
éprouvée, alignée sur le benchmark. La recherche associée avait abouti (MetalLB
**v0.16.1**, mode L2 pur, images épinglées par digest — digests vérifiés
byte-for-byte contre quay.io). Écartée parce qu'elle ajoute **deux composants
externes** (MetalLB speaker/controller + contrôleur nginx) avec leurs datapaths,
cycles de version et surfaces à superviser, alors que Cilium — **déjà CNI et
déjà durci** (ADR 0019) — couvre nativement LB-IPAM, annonce L2 et bordure L7.
La consolidation l'emporte sur la familiarité, au prix d'une déviation assumée.

**Hybride MetalLB (LB-IPAM/L2) + Cilium Gateway API (bordure).** Garderait
MetalLB juste pour l'IP LoadBalancer. Écarté : si l'on bascule de toute façon
sur Gateway API + `kubeProxyReplacement`, LB-IPAM + L2 Cilium viennent « dans la
boîte » — conserver MetalLB en parallèle maintiendrait un composant externe pour
un gain nul, et **deux mécanismes d'annonce L2** sur le même LAN (double ARP →
flap MAC/IP).

**Garder kube-proxy (iptables) + MetalLB.** Éviterait le risque transverse de
`kubeProxyReplacement`. Écarté : LB-IPAM et annonces L2 Cilium **requièrent**
`kubeProxyReplacement` ; le conserver enfermerait dans MetalLB et priverait du
datapath eBPF unifié — l'inverse de l'objectif.

**NodePort / `externalIPs` bruts.** Ports hauts non stables, pas d'IP stable,
pas de routage host/path ni de terminaison TLS en bordure, et **contredit
frontalement le principe #25** (services applicatifs non exposés). Régression.

**Cilium Ingress Controller (API `Ingress` historique) plutôt que Gateway API.**
`ingressController.enabled=true` reste possible mais l'API `Ingress` est figée ;
Gateway API est son successeur (routage et TLS plus expressifs, `HTTPRoute`).
Retenu : Gateway API. **Host firewall Cilium** non activé : éviterait l'advisory
GHSA-5r23-prx4-mqg3 (host-policy mal appliquée avec WireGuard) — on conserve
WireGuard pod-to-pod + NetworkPolicies pod, sans host-policy à risque.
