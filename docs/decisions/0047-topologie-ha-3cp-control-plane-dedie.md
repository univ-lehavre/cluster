# 0047 — Topologie `ha-3cp` : control plane dédié, VIP kube-vip, etcd quorum 2/3

## Contexte

[ADR 0002](0002-control-plane-unique-avec-endpoint.md) a assumé un **control
plane unique** (`cp1`) — SPOF API + etcd — pour garder 3 workers complets sur 4
nœuds. La parade au SPOF était la sauvegarde etcd horaire + restore, **pas** la
HA. `--control-plane-endpoint cluster-api:6443` a été posé dès le bootstrap
**précisément** pour pouvoir ajouter des CP plus tard **sans réinstaller** les
workers.

[ADR 0030](0030-nomenclature-bancs-topologies.md) nomme `ha-3cp` (« 3 control
planes, haute disponibilité ») comme **cible non buildée**, et
[ADR 0040](0040-terrains-x-topologies.md) la pose en cible `local`/`cloud` à
**complexité adaptée aux ressources**, avec un verrou explicite : un **endpoint
flottant** (VIP) devant les 3 CP **n'est pas encore outillé** — aujourd'hui
`cluster-api` pointe le seul `cp1` via `/etc/hosts`, ce qui **ne survit pas** à
la perte de `cp1`. Tant que ce verrou n'est pas levé, `ha-3cp` reste théorique.

Cet ADR **lève le cadrage** : il décide _ce que `ha-3cp` signifie concrètement_
— combien de nœuds, qui porte quoi, comment l'API reste joignable quand un CP
tombe — pour sortir de `multi-node-3` (1 CP / SPOF). Il **précise**
[ADR 0030](0030-nomenclature-bancs-topologies.md) et
[ADR 0040](0040-terrains-x-topologies.md) sans les contredire ; l'implémentation
(rôle kube-vip, banc 6 VMs, run de preuve) est tracée en issue de suite.

### Trois questions à trancher

1. **Quoi mettre en HA ?** Le SPOF de `multi-node-3` est le **control plane**
   (API + etcd). C'est lui qu'on rend redondant : 3 CP.
2. **CP dédiés ou hyperconvergés ?** Le dépôt a fait de l'hyperconvergence (CP
   portant OSD + workloads,
   [ADR 0007](0007-hyperconvergence-control-plane-osd.md),
   [ADR 0009](0009-pourquoi-4-noeuds.md)) **sous contrainte de matériel** —
   c'est un compromis de **densité**, pas un signe de robustesse. Pour la HA,
   l'inverse est vrai : faire cohabiter etcd et des OSD Ceph sur le même nœud
   **affaiblit** ce qu'on cherche à protéger (etcd veut des I/O disque à faible
   latence et stables ; un OSD sous charge peut l'**affamer** → instabilité du
   quorum, le cœur de la HA), et **corrèle les pannes** (perdre 1 nœud = perdre
   d'un coup un CP, un mon, des OSD et des workloads). La HA _sérieuse_
   **sépare** le control plane de la charge.
3. **Comment l'API reste-t-elle joignable ?** Une **VIP** (endpoint flottant)
   devant les 3 API servers. Choix du mécanisme : l'exposition du dépôt est
   **tout-Cilium** (LB-IPAM + L2,
   [ADR 0020](0020-exposition-reseau-tout-cilium.md)), mais Cilium ne peut
   **pas** porter la VIP **de l'API** : au `kubeadm init`, l'API attend de
   répondre sur `--control-plane-endpoint` (la VIP) **avant** que le CNI soit
   installé — or les pods Cilium ont besoin de l'API pour démarrer. Dépendance
   circulaire (API → VIP → Cilium → API) : un LB porté par le CNI ne **bootstrap
   pas** le control plane.

## Décision

**`ha-3cp` = control plane HA dédié, à 6 VMs (3 CP dédiés + 3 workers), VIP API
portée par kube-vip en amorçage statique, etcd stacked à quorum 2/3.**

### 1. Topologie : 3 CP **dédiés** + 3 workers (6 VMs)

- **3 control planes dédiés** (`cp1`,`cp2`,`cp3`) : API + etcd + scheduler +
  controller-manager + kube-vip. **Ni OSD Ceph, ni workloads applicatifs.** Le
  control plane est **découplé** de la charge → pannes isolées, etcd non affamé.
- **3 workers** (`node1`,`node2`,`node3`) : portent calcul + workloads atlas (et
  le stockage quand il sera ajouté).
- C'est une **déviation assumée de l'hyperconvergence**
  ([ADR 0007](0007-hyperconvergence-control-plane-osd.md)/[0009](0009-pourquoi-4-noeuds.md))
  : on échange la densité contre la robustesse du control plane, parce que c'est
  le sens même de la HA. L'hyperconvergence reste le bon compromis quand le
  matériel est rare (cible prod `multi-node-4`) ; `ha-3cp` vise l'autre point.

### 2. VIP de l'API : kube-vip en **amorçage statique**, Cilium pour le reste

- **kube-vip en pod statique** (manifeste dans `/etc/kubernetes/manifests/`,
  porté par kubelet — **sans CNI ni API disponibles**) porte la VIP de l'API au
  bootstrap. C'est ce qui **résout l'œuf-poule** : la VIP existe avant Cilium.
- Une fois le cluster up, **Cilium reste le datapath de tout le reste**
  (LB-IPAM + L2 + Gateway API pour les Services/UI applicatifs,
  [ADR 0020](0020-exposition-reseau-tout-cilium.md)) — kube-vip ne porte **que**
  l'endpoint du control plane. Frontière nette : **CP = kube-vip ; applicatif =
  Cilium**.
- `--control-plane-endpoint cluster-api:6443` (déjà posé,
  [ADR 0002](0002-control-plane-unique-avec-endpoint.md)) **pointe désormais la
  VIP** au lieu de l'IP de `cp1`. Les workers joignent l'API via ce nom stable
  (déjà le cas) → leur configuration ne change pas.

### 3. etcd : stacked, quorum 2/3

- etcd **stacked** (colocalisé sur les 3 CP, pas externe) : suffisant pour la
  cible, un cluster externe serait de la complexité prématurée.
- **Quorum 2/3** : le cluster survit à la perte d'**1 CP** (2 membres restants =
  majorité). La perte de 2 CP fige etcd (lecture seule) — limite assumée d'un
  quorum à 3.
- La **sauvegarde etcd horaire + restore**
  ([ADR 0002](0002-control-plane-unique-avec-endpoint.md)) est **conservée** :
  la HA protège de la **panne** d'un nœud, **pas** de la corruption logique ni
  de la perte simultanée du quorum. HA ≠ backup.

### 4. Stockage du banc : local-path d'abord (HA ⊥ stockage)

- Le **premier** banc `ha-3cp` prouve la **mécanique HA** (quorum etcd, VIP,
  failover à la perte d'un CP) en **local-path** — **pas** de disques Ceph
  bruts. Conforme au principe « dissocier la mécanique de la charge »
  ([ADR 0040](0040-terrains-x-topologies.md)) et à la décomposition en couches
  ([ADR 0045](0045-chemins-installation-banc-couches.md) : stockage est un axe
  indépendant).
- Raison **mesurée** (pas inventée,
  [ADR 0034](0034-validation-e2e-from-scratch.md)) : 6 VMs tiennent en RAM
  (3×4 + 3×8 = **36 GiB / 48**) et CPU (12 vCPU / 16), mais **pas** en disque
  hôte libre avec des disques Ceph bruts par nœud. **HA+Ceph en CP dédiés** est
  une variante ultérieure, quand le disque hôte le permet.

### 5. Dimensionnement des VMs (banc local Lima, profil léger)

Calculé **au plus juste** par rôle (à confirmer au 1er run — plancher exact
mesuré, [ADR 0034](0034-validation-e2e-from-scratch.md)) :

| Rôle             | Compte | RAM/VM | vCPU/VM | Porte                                           |
| ---------------- | ------ | ------ | ------- | ----------------------------------------------- |
| CP **dédié**     | 3      | 4 GiB  | 2       | API + etcd + scheduler + cm + kube-vip + Cilium |
| Worker           | 3      | 8 GiB  | 2       | workloads atlas + Cilium (stockage local-path)  |
| **Total alloué** | **6**  |        |         | **36 GiB / 48 ; 12 vCPU / 16** — marge macOS OK |

- **Pas de VM LB** : la VIP est portée par kube-vip **sur les CP eux-mêmes**,
  pas par une instance dédiée.
- **4 GiB/CP est le défaut sûr, pas le plancher.** Un CP dédié au repos coûte
  ~2,5 GiB (apiserver + etcd + scheduler/cm + kube-vip + kubelet/Cilium/OS) :
  **3 GiB tient au repos** mais avec une marge serrée. Le risque n'est pas
  l'API, c'est **etcd** — sous charge atlas (beaucoup d'objets/watchers API), un
  CP étranglé ferait **swapper etcd** et déstabiliserait le quorum, c.-à-d.
  fausserait la mesure même de la HA. On retient donc **4 GiB par défaut** et on
  **mesure au 1er run si 3 GiB tient sous charge** ; si oui, on descend le
  défaut et on inscrit le plancher ici et dans
  [ADR 0040](0040-terrains-x-topologies.md)
  ([ADR 0034](0034-validation-e2e-from-scratch.md) : plancher mesuré, pas
  estimé).

## Statut

Accepted (2026-06-09). Précise [ADR 0030](0030-nomenclature-bancs-topologies.md)
(définit `ha-3cp`) et [ADR 0040](0040-terrains-x-topologies.md) (lève le verrou
« endpoint flottant » côté `local`). Dévie de l'hyperconvergence
([ADR 0007](0007-hyperconvergence-control-plane-osd.md)) pour le control plane,
de façon assumée. Bâtit sur
[ADR 0002](0002-control-plane-unique-avec-endpoint.md)
(`--control-plane-endpoint` déjà posé) et
[ADR 0020](0020-exposition-reseau-tout-cilium.md) (Cilium pour l'applicatif,
kube-vip pour le CP).

## Conséquences

- **Gain** : sortie du SPOF `multi-node-3`. Le control plane survit à la perte
  d'1 CP (quorum 2/3) ; l'API reste joignable (VIP). CP **dédiés** → etcd
  découplé de la charge, pannes isolées : la HA _robuste_, pas la densité.
- **Bootstrap sain** : kube-vip pod statique brise l'œuf-poule (VIP avant CNI) ;
  Cilium garde l'applicatif → un seul datapath eBPF côté charge, deux mécanismes
  seulement là où c'est nécessaire (CP).
- **Prix à payer** :
  - **6 VMs au lieu de 3** : plus de RAM/CPU alloués, marges hôte plus serrées.
    36/48 tient, mais on ne monte **pas** Ceph en parallèle sur 48 GiB.
  - **Deux mécanismes de VIP** (kube-vip pour le CP, Cilium pour l'applicatif) :
    frontière à tenir, kube-vip à épingler/maintenir (matrice
    [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).
  - **Déviation de l'hyperconvergence** : on ne maximise plus la densité sur
    `ha-3cp` ; assumé, c'est le sens de la HA.
  - **Quorum 3 = survie à 1 CP perdu**, pas 2. Backup etcd toujours requis.
- **Implémentation = issue de suite** (cet ADR cadre, n'outille pas) :
  1. rôle/manifeste **kube-vip** épinglé par digest d'index multi-arch
     ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)), valeurs
     génériques ([ADR 0023](0023-plateforme-exemple-generique.md)) ;
  2. banc Lima **6 VMs** (3 CP dédiés + 3 workers) dans `test/lima/` via un
     **chemin nommé codé**
     ([ADR 0045](0045-chemins-installation-banc-couches.md)/[0046](0046-corriger-le-code-pas-l-etat.md))
     ;
  3. **run de preuve from-scratch**
     ([ADR 0034](0034-validation-e2e-from-scratch.md)) : quorum etcd, VIP
     joignable, **survie à l'arrêt d'1 CP** (l'API répond toujours via la VIP) ;
     plancher RAM/CP mesuré et inscrit dans
     [ADR 0040](0040-terrains-x-topologies.md).
- **Cloud (escalade)** : en cloud Oracle, la VIP peut être le **Load Balancer
  Free Tier** au lieu de kube-vip ([ADR 0040](0040-terrains-x-topologies.md)) —
  même décision (endpoint flottant), mécanisme adapté au terrain.

## Alternatives écartées

- **Rester hyperconvergé en HA (3 nœuds CP+Ceph, 3 VMs).** Tient sur 48 GiB
  **avec** Ceph, plus dense. Écarté pour la cible HA : fait cohabiter etcd et
  OSD (risque d'affamer etcd) et **corrèle les pannes** — l'inverse de ce que la
  HA cherche. L'hyperconvergence reste pertinente hors HA (prod `multi-node-4`).
- **Cilium LB-IPAM + L2 pour la VIP de l'API** (réutiliser l'existant).
  Séduisant (un seul mécanisme), mais **dépendance circulaire au bootstrap** :
  l'API attend la VIP, la VIP attend Cilium, Cilium attend l'API. Non
  bootstrap-able pour le control plane. Cilium garde donc l'**applicatif**
  uniquement.
- **HAProxy/keepalived sur une VM LB dédiée.** LB externe classique. Écarté :
  ajoute une 7e VM (RAM/CPU) et un composant à opérer, là où kube-vip en pod
  statique porte la VIP **sur les CP** sans nœud supplémentaire ni œuf-poule.
- **etcd externe (cluster etcd séparé).** Découplerait encore plus etcd de
  l'API. Écarté pour la cible : complexité de bootstrap et d'opération
  prématurée ; stacked + CP dédiés suffit déjà à découpler etcd de la **charge**
  (le risque principal). Réévaluable si le quorum se révèle instable.
- **6 VMs avec Ceph d'emblée.** La preuve HA+Ceph complète en CP dédiés. Écarté
  pour le **premier** banc : ne rentre pas dans le disque hôte libre. Variante
  ultérieure (HA ⊥ stockage), pas un renoncement.
