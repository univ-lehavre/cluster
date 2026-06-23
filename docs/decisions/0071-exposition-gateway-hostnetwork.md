# 0071 — Exposition `gateway` en hostNetwork (80/443 sur l'IP du nœud)

> **Superseded by [ADR 0092](0092-exposition-hostport-l4.md)** (2026-06-23) pour
> le MÉCANISME d'exposition : les UI passent du Gateway L7 (hostNetwork, SNI,
> TLS de bordure) au L4 `hostPort`/`NodePort` (`http://<IP-nœud>:<port>`, zéro
> DNS). La prémisse réseau privé / mono-NIC d'ADR 0071 reste valable ; c'est le
> choix Gateway-L7 qui est remplacé (cf. ADR 0092 §Contexte).

## Statut

Superseded by [ADR 0092](0092-exposition-hostport-l4.md) (2026-06-23).
Initialement Accepted (2026-06-15).

**Amende l'[ADR 0020](0020-exposition-reseau-tout-cilium.md)** : fait du Gateway
exposé en **hostNetwork** le mode d'exposition **unique** câblé, et rétrograde
LB-IPAM + L2 en chemin de prod _optionnel_. Complète
l'[ADR 0048](0048-acces-local-developpeur.md) (accès hôte) et
l'[ADR 0056](0056-modele-declaratif-topologies.md) §4 (`exposition` comme
dimension déclarative).

> Cet ADR **remplace** une version antérieure (jamais implémentée) qui proposait
> un mode `hostport` distinct (un `hostPort` posé sur chaque workload, sans
> bordure L7). Le besoin est identique — **80/443 sur l'IP d'une VM publique
> mono-NIC, sans plage IP à réserver** — mais le mécanisme retenu est meilleur :
> exposer **le Gateway lui-même** en hostNetwork rend le même service tout en
> **gardant** le routage L7/SNI et la terminaison TLS de bordure. `hostport`
> devient un alias historique de `gateway`.

## Contexte

L'[ADR 0020](0020-exposition-reseau-tout-cilium.md) a retenu une exposition
**tout-Cilium** (LB-IPAM + L2 + Gateway API). Le Gateway y bind 80/443 sur une
**IP LoadBalancer** fournie par un `CiliumLoadBalancerIPPool` et **annoncée en
L2** (ARP). Ce chemin exige :

- une **plage d'IP réservée** négociée avec l'admin réseau (le pool LB-IPAM) ;
- une **interface L2 annonçable** (L2 announcements, beta en 1.19) ;
- du DNS pointant les hostnames vers ces IP.

Sur une **VM publique mono-NIC** (un nœud, une IP publique, pas de LB amont) —
et sur le **banc Lima** (pas de plage L2 annonçable jetable) — ce chemin est
**surdimensionné** : on veut juste que le service réponde sur les ports
standards 80/443 de l'IP du nœud.

**Fait décisif (recherche Cilium 1.19 vérifiée)** : Cilium sait exposer le
Gateway API **directement sur le host network**, par le flag Helm
`gatewayAPI.hostNetwork.enabled=true`. C'est le chemin documenté « quand un
Service LoadBalancer est indisponible ». Conséquences :

- l'Envoy du Gateway bind sur `0.0.0.0`/`::` → **joignable sur l'IP propre du
  nœud** ;
- activer hostNetwork **désactive automatiquement** le mode Service LoadBalancer
  (mutuellement exclusifs en 1.19) → **plus aucune LB-IPAM requise**, aucune IP
  virtuelle à réserver ;
- `kubeProxyReplacement=true` (`bootstrap/cni.sh`) est un **prérequis déjà
  satisfait** et compatible.

On **garde** donc toute la bordure L7 — `HTTPRoute`, multiplexage de plusieurs
services sur 443 par hostname (SNI), terminaison TLS par cert-manager
([ADR 0021](0021-cert-manager-ca-interne.md)) — **sans** le coût d'entrée
LB-IPAM/L2. C'est strictement supérieur à un `hostPort` L4 posé sur chaque
workload (qui perdrait le L7, le SNI et le TLS de bordure).

## Décision

**Un seul mode d'exposition câblé, `gateway`, exposé via
`gatewayAPI.hostNetwork.enabled=true` sur les ports 80/443 de l'IP du nœud, sans
LB-IPAM. Valable partout (VM publique mono-NIC comme banc Lima). `none` reste
possible (ClusterIP seuls).** Six points.

### 1. Mode unique `gateway`, en hostNetwork, partout

`exposition.mode` ne câble plus qu'un mécanisme : la bordure L7 Cilium exposée
en hostNetwork. Le banc Lima **comme** une VM publique l'emploient — le
hostNetwork ne réclamant ni plage IP ni interface L2, c'est le plus
**reproductible** (preuve from-scratch sans prérequis réseau,
[ADR 0034](0034-validation-e2e-from-scratch.md)).

### 2. `hostport` et `lb-ipam` deviennent des alias de `gateway`

`VALID_EXPOSITION_MODES = {"gateway", "none"}` (`nestor/model.py`). Les anciens
noms sont des **alias déprécié-doux** résolus à la lecture
(`_EXPOSITION_ALIASES = {"lb-ipam": "gateway", "hostport": "gateway"}`), pour ne
casser aucun `topology.yaml` existant :

- `lb-ipam` était l'_implémentation_ historique du Gateway → `gateway` ;
- `hostport` (« 80/443 sur l'IP de l'hôte ») est exactement ce que fait
  désormais gateway-hostNetwork → `gateway`.

Même patron « alias déprécié-doux » que `catalog.profile` → `layers`
([ADR 0069](0069-topology-layers-dag-grain-phase.md) §7).

### 3. Défaut global `gateway` (renversement du défaut banc)

`_EXPOSITION_DEFAULT = "gateway"` — plus de défaut par terrain. Le banc Lima n'a
plus de défaut `hostport` propre : gateway-hostNetwork est aussi simple à monter
sur le banc que sur une VM publique.

### 4. LB-IPAM + L2 : chemin de prod OPTIONNEL

Le chemin IP-virtuelle-annoncée-sur-LAN (LB-IPAM + L2) **reste disponible** pour
la prod quand l'admin réseau fournit une plage dédiée et qu'on veut une IP
stable annoncée sur le LAN. Il n'est plus **armé par défaut** :
`CILIUM_LB_IPAM_ENABLED=0` (`bootstrap/cni.sh`) — `=1` ré-arme
`l2announcements` + pose le `CiliumLoadBalancerIPPool`. Le `GatewayClass` est,
lui, **toujours** posé (le contrôleur Gateway en a besoin dans les deux
chemins).

### 5. Ports privilégiés 80/443 : deux réglages Helm

L'Envoy de Cilium n'a aucune capacité réseau par défaut → il ne peut pas binder
un port ≤ 1023. Pour 80/443, **deux** réglages (l'un ne suffit pas sans l'autre)
:

- `envoy.securityContext.capabilities.keepCapNetBindService=true` ;
- ajout de `NET_BIND_SERVICE` à la liste des capabilities de l'Envoy.

> **À confirmer au banc** : selon que l'Envoy tourne en DaemonSet **standalone**
> (`cilium-envoy`) ou **embedded** dans l'agent, le chemin Helm diffère
> (`envoy.securityContext.capabilities.*` vs
> `securityContext.capabilities.ciliumAgent`). On pose le chemin `envoy.*`
> (probable en 1.19.4) et on **sonde** au banc le bind 80/443 ; on bascule si
> besoin. Ne pas présumer.

### 6. Readiness gatée sur la joignabilité L7, jamais sur `Programmed`

Un bug Cilium connu
(**[#42786](https://github.com/cilium/cilium/issues/42786)**, reproduit sur
1.19.1) : en hostNetwork, le `Gateway` reste **`Programmed: False`**
(`AddressNotAssigned`, car un ClusterIP est créé au lieu d'une LB → pas
d'adresse dans le `.status`) **alors que le data path fonctionne** (le trafic
atteint les backends). Donc :

- **Ne JAMAIS gater la readiness du Gateway sur `.status.Programmed`** — il
  resterait faux indéfiniment et bloquerait tout gate (Ansible `k8s_info`, bats,
  boucle d'attente). C'est le piège exact de la mémoire « gate sur `.status`,
  pas k8s_exec » poussé d'un cran : ici même `.status` ment.
- **Gater sur la joignabilité L7 réelle** : un
  `curl -k --resolve HOST:443:NODE_IP https://HOST/` qui obtient **n'importe
  quel** code HTTP (même 404/503) prouve qu'Envoy accepte le TLS et route. Un
  échec de **connexion** (rc 7 / code `000`) = pas prêt. C'est aussi la preuve
  from-scratch ([ADR 0034](0034-validation-e2e-from-scratch.md)).

### Amendement à l'ADR 0020 (drift `state.sh`)

Le contrôle drift `bootstrap/state.sh` traite tout `hostPort` hors bordure comme
un DRIFT. Cet amendement le précise : le **SMTP de mailpit** (banc-only, relais
postfix hôte #131) passe d'un `Service type=LoadBalancer` à un
**`hostPort: 1025`** sur le pod (le postfix tourne sur le nœud → joint
`NodeIP:1025` en eBPF, sans LB-IPAM). Ce `hostPort`, **posé par le chemin
codé**, est une **exception tracée** (comme les ports de bordure Gateway), pas
une régression. C'est le seul `hostPort` L4 légitime restant — le L7 passe par
le Gateway.

## Conséquences

- Un service répond sur **`IP_VM:443`** avec **routage L7/SNI + TLS de
  bordure**, sans LB ni plage IP — la même brique Cilium (Gateway API en eBPF),
  zéro composant en plus.
- `exposition.mode` n'a plus que **deux** valeurs canoniques (`gateway` /
  `none`) ; `lb-ipam`/`hostport` sont des alias rétrocompatibles.
- Banc Lima en `gateway`-hostNetwork par défaut → preuve from-scratch sans
  prérequis réseau ; LB-IPAM/L2 restent prouvables par une topologie dédiée
  (`CILIUM_LB_IPAM_ENABLED=1`).
- ADR 0020 amendé (mode unique gateway-hostNetwork ; LB-IPAM/L2 optionnels).
- Preuve
  ([ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md))
  : un run `gateway` → service joignable en L7 (curl) sur `NodeIP:443` ; rejeu
  `changed=0`.

## À revoir si

- Le **multiplexage SNI sur 443 en hostNetwork** s'avère limité (un seul
  listener 443 partagé au lieu d'un Gateway par service) → repenser vers un
  Gateway unique multi-listeners. **Non vérifié end-to-end** par la recherche —
  à prouver au banc.
- Le bug `Programmed: False` (#42786) est corrigé dans un patch 1.19.x → on peut
  re-fiabiliser un gate sur `.status` (mais le gate L7 reste plus robuste).
- Un terrain exige une **IP virtuelle stable annoncée sur le LAN** (multi-nœuds,
  LB amont) → activer le chemin LB-IPAM + L2 (point 4).

## Alternatives écartées

- **`hostPort` sur chaque workload** (la proposition initiale de cet ADR) : sert
  80/443 sur l'IP du nœud mais **perd** le routage L7, le SNI et le TLS de
  bordure ; il faudrait un reverse-proxy applicatif par service. Le
  gateway-hostNetwork rend le même service en gardant le L7 → **retenu** à la
  place.
- **NodePort** : la plage `30000-32767` ne donne pas 80/443 ; l'élargir ouvre
  tous les ports bas (collisions). Déjà écarté par l'ADR 0020.
- **LB-IPAM + L2 partout (ADR 0020 inchangé)** : exige une plage IP négociée +
  une interface L2 annonçable — surdimensionné pour une VM mono-NIC et
  irreproductible sur un banc jetable. Conservé comme **option de prod**, pas
  comme défaut.
- **`exposition` sous `catalog`** : `catalog` est descriptif
  ([ADR 0039](0039-nomenclature-axes-catalogue.md)) ; une intention de
  déploiement vit au top-level / dans son bloc `exposition`.
