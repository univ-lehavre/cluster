# 0071 — Exposition `hostport` (80/443 sur l'hôte) via Cilium eBPF

## Statut

Proposed (2026-06-15)

**Amende l'[ADR 0020](0020-exposition-reseau-tout-cilium.md)** : ajoute un
mécanisme d'exposition `hostport` à côté du Gateway, et **bascule le banc Lima
en `hostport` par défaut**. Complète
l'[ADR 0048](0048-acces-local-developpeur.md) (accès hôte) et
l'[ADR 0056](0056-modele-declaratif-topologies.md) §4 (`exposition` comme
dimension déclarative).

## Contexte

L'[ADR 0020](0020-exposition-reseau-tout-cilium.md) a retenu une exposition
**tout-Cilium** (LB-IPAM + L2 + Gateway API) et écarté NodePort. Le champ
`exposition.mode` existe (`cluster_topology/model.py:48`) et annonce déjà des
valeurs (`lb-ipam | nodeport | none`, `topologies/socle.example.yaml:50`),
**mais aucune n'est câblée** : la seule lecture est un affichage
(`scripts/topology.py`).

Le besoin concret qui force cette décision : **exposer un service sur les ports
standards 80/443 d'une VM publique** (point d'entrée web sans port exotique). Or
:

- **NodePort ne peut pas** : la plage est `30000-32767`
  (`--service-node-port-range` par défaut) ; demander 80/443 imposerait
  d'élargir la plage à tous les ports bas (collisions avec les services hôte) —
  déconseillé. NodePort ne répond donc PAS au besoin « 80/443 public » ; il est
  **abandonné** (cf. Alternatives).
- **Le Gateway répond, mais avec des prérequis lourds** : LB-IPAM exige une
  plage d'IP réservée avec l'admin réseau, les annonces L2 (beta en 1.19) une
  interface L2 annonçable, le Gateway des CRDs + un certificat de bordure. Sur
  une VM publique mono-NIC sans LB amont, ce chemin est surdimensionné.

Fait décisif : **Cilium sait router `hostPort` en eBPF**, gratuitement.
`kubeProxyReplacement=true` (`bootstrap/cni.sh:110`) **remplace le plugin CNI
portmap** : un pod déclarant `hostPort: 443` voit le port 443 du **nœud** routé
vers lui par le datapath eBPF — y compris les **ports privilégiés < 1024**, sans
composant ni flag supplémentaire. C'est exactement « 80/443 sur l'IP de la VM »,
sans IP virtuelle à réserver. Tout passe par la **même brique Cilium** déjà
posée — la cohérence « une seule matrice de versions » de l'ADR 0020 (la ligne
Cilium) est préservée.

## Décision

**Ajouter un mode d'exposition `hostport` (80/443 servis sur l'IP de l'hôte par
Cilium eBPF), de premier rang à côté de `gateway`. Le choix se DÉCLARE par
topologie via `exposition.mode`, et l'outil le CÂBLE.** Six points.

### 1. Trois modes officiels, un critère de choix net

`exposition.mode` accepte :

- **`gateway`** (ex-`lb-ipam`, _cf._ point 3) — **bordure L7 complète** : IP
  virtuelle stable annoncée sur le LAN (LB-IPAM + L2), routage host/path
  (`HTTPRoute`), **terminaison TLS** par cert-manager (ADR 0021), Hubble L7.
  L'Envoy du Gateway bind lui-même 80/443 sur l'IP LoadBalancer. **Le mode de
  référence** quand l'admin réseau fournit une plage d'IP + le DNS.
- **`hostport`** — **80/443 directement sur l'IP du/des nœud(s)**, routés en
  eBPF (`kubeProxyReplacement`, déjà actif). Aucune IP virtuelle à réserver,
  aucune annonce L2, aucun CRD Gateway. **Le mode pour une VM publique
  mono-NIC** (le service répond sur `IP_publique:443`). TLS terminé par le pod
  applicatif (ou un reverse-proxy applicatif), pas par une bordure L7 dédiée.
- **`none`** — aucune exposition câblée (ClusterIP seuls ; accès par
  port-forward / `access.sh`, ADR 0048).

**Critère de choix (les trois légitimes) :**

| Besoin                                                                          | Mode           |
| ------------------------------------------------------------------------------- | -------------- |
| Routage host/path L7, terminaison TLS de bordure, IP virtuelle annoncée sur LAN | **`gateway`**  |
| Plage LB-IPAM négociée **et** interface L2 annonçable                           | **`gateway`**  |
| 80/443 sur l'IP d'une VM publique, sans LB ni plage IP à réserver               | **`hostport`** |
| Point d'entrée web simple (un nœud, une IP, ports standards)                    | **`hostport`** |
| Pas d'exposition hors cluster                                                   | **`none`**     |

### 2. Le choix se déclare via `topology.yaml` → `exposition.mode`

Intention de déploiement, dans la source de vérité unique (ADR 0056). Cet ADR :

- **valide l'enum à la construction** (comme `VALID_LB_MODES`,
  `model.py:153-159`) :
  `VALID_EXPOSITION_MODES = {"gateway", "hostport", "none"}` levant
  `TopologyError` sur valeur inconnue (l'alias `lb-ipam` → `gateway`, point 3) ;
- **rend le mode CONSÉQUENT** : `exposition.mode` pilote ce que `run-phases.sh`
  pose, au lieu d'une simple étiquette. `hostport` → les workloads exposés
  portent un `hostPort` ; `gateway` → `Gateway`+`HTTPRoute`.

`exposition` reste **orthogonal** à `layers` (ADR 0069) et au `backend` (ADR
0036). Un `.example` pédagogique (`topologies/hostport.example.yaml`) illustre
le mode ; aucun `.example` existant n'est réécrit (ADR 0052).

### 3. Renommage doux `lb-ipam` → `gateway`, rétrocompatible

`lb-ipam` (l'implémentation) devient **`gateway`** (le mécanisme) comme nom
canonique ; `lb-ipam` reste **alias accepté** (mappé sur `gateway` à la lecture)
pour ne pas casser les `.example`/`topology.yaml` existants. Même patron « alias
déprécié-doux » que `catalog.profile` → `layers` (ADR 0069 §7).

### 4. Les ports : 80/443 par défaut, surchargeables

- **`hostport`** expose **80 et 443** (ports web standards) sur l'IP de l'hôte.
  Surchargeables par service si nécessaire (`exposition.hostport.ports`), mais
  80/443 est le défaut utile — c'est tout l'intérêt vs NodePort.
- **Ports privilégiés < 1024** : servis par le datapath eBPF de l'agent Cilium
  (hostNetwork, capacités réseau) — pas de souci de bind utilisateur.
- **Pas de valeur d'instance figée versionnée** (ADR 0023) : 80/443 sont des
  ports conventionnels (pas une IP/plage d'instance) ; une surcharge vit en
  config locale / `.example`.

### 5. Cohérence Cilium : rien à armer, hostPort déjà en eBPF

`kubeProxyReplacement=true` (`bootstrap/cni.sh:110`) remplace **déjà** le plugin
portmap et sert hostPort/NodePort en eBPF. Donc :

- **mode `hostport`** : **zéro** flag/CRD/composant en plus ; `run-phases.sh`
  pose des `hostPort` sur les workloads exposés. Le phase `platform-prereqs`
  (CRDs Gateway API) n'est PAS requis.
- **mode `gateway`** : chemin ADR 0020 inchangé.
- Tout reste sur la **ligne de version Cilium unique** (cohérence ADR
  0019/0020).

### 6. Défaut du banc Lima : `hostport` (renversement assumé d'ADR 0020)

**Décision tranchée : le banc Lima passe en `exposition.mode: hostport` par
DÉFAUT.** Renversement du défaut Gateway d'ADR 0020, assumé :

- **Pourquoi** : `hostport` marche sans plage IP réservée ni interface L2
  annonçable — le plus reproductible sur un banc jetable (moins de prérequis
  externes = preuve plus robuste, ADR 0034).
- **Ce que ça déplace** : la chaîne de preuve du mode `gateway` (LB-IPAM + L2 +
  Gateway API) ne passe plus par le défaut du banc ; elle reste prouvée par une
  topologie **`gateway.example.yaml`** dédiée.
- **Risque banc Lima local** : 80/443 de la VM Lima peuvent entrer en conflit
  avec des ports de l'hôte macOS si un forward hôte→VM les mappe. Garde-fou :
  sur le banc local, l'accès dev passe par `access.sh` (forwards SSH, ADR 0048)
  ; `hostport` cible surtout le terrain **VM publique** (le cas qui le motive).
  Le conflit éventuel est documenté, pas silencieux.

> **Conséquence forte** : l'ADR 0020 est amendé au-delà du drift `state.sh` —
> son invariant « validation Gateway sur banc par défaut » est levé. Voir
> ci-dessous.

### Amendement à l'ADR 0020 (drift `state.sh`)

Le contrôle drift `bootstrap/state.sh` traite tout
`hostPort`/`Service type=NodePort` hors bordure comme un **DRIFT** (principe «
services applicatifs non exposés »). Cet ADR l'amende : quand
`exposition.mode == hostport`, les `hostPort` **posés par le chemin codé**
deviennent une **exception tracée** (au même titre que les Service de bordure
Gateway), pas une régression.

## Conséquences

- Un service répond sur **`IP_VM:443`** sans LB ni plage IP — le besoin VM
  publique est couvert par la **même brique Cilium** (eBPF), zéro composant en
  plus.
- `exposition.mode` devient **conséquent** (plus une étiquette morte) :
  `gateway` / `hostport` / `none` pilotent réellement ce qui est posé.
- Banc Lima en `hostport` par défaut → preuve from-scratch sans prérequis réseau
  ; le mode `gateway` reste prouvé par `gateway.example.yaml`.
- ADR 0020 amendé (hostport officiel + défaut banc). Renommage doux
  `lb-ipam → gateway` rétrocompatible.
- Preuve (ADR 0034/0052) : un run `exposition.mode: hostport` → service
  joignable sur `NodeIP:443` ; rejeu `changed=0`.

## À revoir si

- Un besoin de routage **host/path L7** ou de **terminaison TLS de bordure**
  émerge sur le terrain hostport → repasser ce service en `gateway` (les deux
  coexistent).
- Plusieurs services veulent **chacun** 80/443 sur le même nœud : conflit de
  port hôte → il faut un L7 router (Gateway) qui multiplexe par hostname.
  `hostport` vise **un** point d'entrée par nœud.

## Alternatives écartées

- **NodePort** (la proposition initiale) : la plage `30000-32767` ne donne pas
  80/443 ; l'élargir ouvre tous les ports bas (collisions). **Abandonné** au
  profit de `hostport`, qui sert directement les ports standards en eBPF.
- **Élargir `--service-node-port-range` à `80-32767`** : transforme tout port
  bas en NodePort potentiel (collision avec services hôte) — déconseillé par
  Kubernetes ; rejeté.
- **Tout-Gateway (ADR 0020 inchangé)** : le Gateway bind 80/443 mais exige
  LB-IPAM + L2 + CRDs + cert de bordure — surdimensionné pour une VM publique
  mono-NIC. Le Gateway reste le mode `gateway` ; `hostport` est l'option légère.
- **`exposition` sous `catalog`** : `catalog` est descriptif (ADR 0039) ; une
  intention de déploiement vit au top-level / dans son bloc `exposition`.
