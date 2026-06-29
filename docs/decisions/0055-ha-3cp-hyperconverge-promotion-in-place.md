# 0055 — `ha-3cp` hyperconvergé : 3 control planes sur 4 nœuds identiques, promotion in-place

## Contexte

[ADR 0002](0002-control-plane-unique-avec-endpoint.md) a assumé un **control
plane unique** (SPOF API + etcd) sur le parc de 4 nœuds identiques, pour garder
**3 workers complets**. Sa parade au SPOF était la sauvegarde etcd horaire, pas
la HA — mais `--control-plane-endpoint cluster-api:6443` a été posé **dès
l'init** précisément pour permettre d'ajouter des control planes **sans
réinstaller** les workers.

[ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md) a cadré la cible
`ha-3cp` comme **3 control planes _dédiés_ + 3 workers (6 VMs)**, VIP portée par
**kube-vip** en pod statique, etcd stacked quorum 2/3 — et a **explicitement
écarté** la variante hyperconvergée (« Rester hyperconvergé en HA […] fait
cohabiter etcd et OSD (risque d'affamer etcd) et corrèle les pannes »).

Cet ADR statue sur un cas que ni 0002 ni 0047 ne couvrent : **rendre le control
plane HA sur le parc prod RÉEL — 4 nœuds physiques identiques déjà déployés en 1
CP** — sans 6e/7e machine et sans réinstallation. Le parc compte 4 nœuds
(`cp1`…`node3`), 251 GiB RAM / 80 vCPU chacun, partitionnés à **l'identique avec
une LV `etcd` dédiée montée sur les 4** (choix d'uniformité,
[RUNBOOK](../../bootstrap/RUNBOOK.md)) — donc promouvoir un nœud en control
plane ne demande **aucun repartitionnement**.

### La question à trancher

L'ADR 0047 conclut que la HA _robuste_ exige des CP **dédiés** (découpler etcd
de la charge). Mais ce modèle suppose 6 machines. **Sur 4 nœuds**, dédier 3 CP
laisserait **1 seul nœud** de calcul/stockage : on perdrait 3/4 du parc OSD (36
disques sur 48) et l'essentiel du calcul — exactement le compromis que
[ADR 0009](0009-pourquoi-4-noeuds.md) refuse à 4 nœuds, et que
[ADR 0007](0007-hyperconvergence-control-plane-osd.md) tranche par
l'hyperconvergence. **Faut-il renoncer à la HA du control plane sur 4 nœuds, ou
l'assumer en hyperconvergé malgré la réserve de 0047 ?**

L'argument central de 0002 (« garder 3 workers ») est par ailleurs devenu
**caduc** : le taint `node-role.kubernetes.io/control-plane` est **retiré** sur
le parc (les CP schedulent déjà des charges). Promouvoir 2 nœuds en CP ne coûte
donc **aucun** nœud de calcul — on garde 4 nœuds schedulables.

## Décision

**Sur le parc prod 4 nœuds identiques, `ha-3cp` se décline en _hyperconvergé,
promotion in-place_ : 3 nœuds cumulent control plane + worker + OSD, le 4ᵉ reste
worker + OSD. Déviation assumée de la réserve « CP dédiés » de
[ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md), justifiée par les
contraintes matérielles du parc.**

### 1. Topologie cible — 4 nœuds de calcul, dont 3 control planes

| Nœud    | Control plane (API + etcd) | Worker (pods) | Ceph OSD | mon Ceph |
| ------- | -------------------------- | ------------- | -------- | -------- |
| `cp1`   | ✅                         | ✅            | ✅       | ❌       |
| `node1` | ✅                         | ✅            | ✅       | ✅       |
| `node2` | ✅                         | ✅            | ✅       | ✅       |
| `node3` | ❌ (worker pur)            | ✅            | ✅       | ✅       |

- **etcd : 3 membres** (sur les 3 CP), pas 4 — quorum **impair**, survie à la
  perte d'**1** nœud. `node3` reste worker pur, sans membre etcd.
- **Les 4 nœuds restent schedulables** (taint CP retiré, uniforme) : on ne perd
  aucun nœud de calcul — le contre-argument de
  [ADR 0002](0002-control-plane-unique-avec-endpoint.md) ne tient plus.
- **mon Ceph dispersés HORS de l'alignement etcd** (`node1/2/3`, pas `cp1`) : on
  **découple les deux quorums** — perdre 1 nœud ne doit pas amputer
  simultanément 1/3 du quorum etcd ET 1/3 du quorum mon sur le **même** nœud. À
  forcer via `placement.mon` dans
  [`storage/ceph/cluster.yaml`](../../storage/ceph/cluster.yaml) (sinon Rook
  peut coller une mon sur `cp1`).

### 2. VIP de l'API — kube-vip ARP, hors pool LB-IPAM Cilium

Le mécanisme d'endpoint flottant est celui déjà décidé par
[ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md) : **kube-vip en pod
statique, mode ARP** (porté par kubelet, sans CNI ni API → brise l'œuf-poule).
`cluster-api:6443` ([ADR 0002](0002-control-plane-unique-avec-endpoint.md))
**pointe la VIP** au lieu de l'IP de `cp1`.

**Frontière nette VIP/Cilium (le point sensible de l'hyperconvergence)** :
kube-vip (ARP) et le L2 announcement de Cilium
([ADR 0020](0020-exposition-reseau-tout-cilium.md)) sont le même protocole. Ils
ne collisionnent **que** s'ils revendiquent la même IP. Deux garde-fous :

1. **La VIP API est HORS du pool LB-IPAM Cilium** (`LB_IPAM_RANGE_*`,
   [`cni.sh`](../../bootstrap/cni.sh)), à réserver formellement avec l'admin
   réseau — au même titre que la plage LB-IPAM. La VIP n'est **pas** un Service
   k8s : Cilium ne l'allouera jamais.
2. **Piège SPÉCIFIQUE à l'hyperconvergence** : aujourd'hui le
   `CiliumL2AnnouncementPolicy` exclut les nœuds control-plane des annonceurs
   L2. Quand `node1/2` deviennent CP **tout en restant workers**, Cilium
   cesserait d'y annoncer les Services applicatifs → il ne resterait que `node3`
   comme annonceur ⇒ **SPOF d'exposition applicative**. Décision : **lever
   l'exclusion control-plane** du `nodeSelector` L2 (les 4 nœuds annoncent les
   Services applicatifs) — sûr précisément parce que la VIP API est hors pool
   (garde-fou 1). En CP _dédiés_ (0047) ce piège n'existe pas ; il est propre à
   l'hyperconvergence.

### 3. etcd stacked, quorum 3, backup conservé

- etcd **stacked** (colocalisé sur les 3 CP). Quorum **3** → survie à 1 CP
  perdu. La perte de 2 CP fige etcd (limite assumée).
- La **sauvegarde etcd horaire + fetch hors-nœud**
  ([ADR 0002](0002-control-plane-unique-avec-endpoint.md)) est **conservée et
  étendue aux 3 CP** : la HA protège de la panne d'un nœud, pas de la corruption
  logique. **HA ≠ backup.**

### 4. Promotion in-place, prouvée au banc d'abord

- La promotion se fait **in-place** : `node1/2` sont déjà workers →
  `kubeadm reset` (worker → propre) puis `kubeadm join --control-plane`. Un
  worker ne se « promeut » pas sans reset (contrainte kubeadm). Séquence **un CP
  à la fois**, membre etcd `healthy` avant le suivant (la fenêtre etcd N=2 est
  plus fragile que N=1 : la perte d'1 membre y fige le quorum).
- **Aucune commande en prod avant un run de preuve au banc**
  ([ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md))
  : le banc actuel (Lima 1 CP + 2 workers) ne reproduit **pas** ce chemin. La
  **mécanique HA se prouve à 3 VM** (3 CP hyperconvergés en local-path — le
  minimum pour un quorum etcd impair de 3 et un failover de VIP) via un **chemin
  nommé codé**
  ([ADR 0045](0045-chemins-installation-banc-couches.md)/[0046](0046-corriger-le-code-pas-l-etat.md)).
  Le 4ᵉ nœud de la prod (`node3`, worker pur sans membre etcd) n'ajoute aucune
  mécanique HA à prouver : 3 VM suffisent au banc, 4 nœuds en prod. Le run
  prouve : kube-vip up → VIP répond → repointage `cluster-api → VIP` → 3ᵉ membre
  etcd → **survie à l'arrêt d'1 CP** → **absence de collision ARP** VIP/Services
  LB → **exposition survit à la perte d'1 nœud** → idempotence `changed=0`.

## Statut

Superseded by [ADR 0097](0097-moteur-chemin-python-bash-artefacts.md)
(2026-06-29). Initialement Accepted (2026-06-11 ; promu de Proposed le
2026-06-13).

> **Topologie `ha-3cp` abandonnée (2026-06-29).** La cible HA hyperconvergée
> décrite ici n'est plus poursuivie : sa preuve exigeait un **banc 3-VM**
> (quorum etcd impair + failover de VIP), or ce banc est **abandonné** (poste de
> dev sans les ressources pour 3 VM — cf. le passage au banc mono-nœud
> local-path comme référence). La HA du control plane ne se prouvant **que** sur
> prod (rebuild dirqual ~sept. 2026), l'outillage `ha-3cp` (orchestration,
> sondes etcd/VIP, chemin banc, exemple de topologie) est **retiré** par
> [ADR 0097](0097-moteur-chemin-python-bash-artefacts.md) ; le geste CNI
> `ha-cni` (pose Cilium + fetch kubeconfig du bootstrap **normal**, sans rapport
> avec la HA malgré son nom) est **conservé**. Le plan
> [plan-ha-3cp-control-plane](../plans/plan-ha-3cp-control-plane.md) passe
> **Abandonné**. Cet ADR reste **immuable sur le fond**
> ([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) : un ADR décide,
> immuable) : seul son statut acte que la décision n'est plus active.

**Précise** [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md) (variante
hyperconvergée 4 nœuds, là où 0047 décrit le modèle CP dédiés 6 VMs) et
**amende** [ADR 0002](0002-control-plane-unique-avec-endpoint.md) (argument « 3
workers » caduc, taint CP retiré). Bâtit sur
[ADR 0007](0007-hyperconvergence-control-plane-osd.md) (hyperconvergence),
[ADR 0020](0020-exposition-reseau-tout-cilium.md) (Cilium pour l'applicatif,
kube-vip pour le CP) et
[ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md) (image kube-vip
épinglée). Implémentation tracée par l'issue **#250** (à amender pour la
variante hyperconvergée).

## Conséquences

- **Gain** : sortie du SPOF control plane sur le parc 4 nœuds **réel**, sans
  matériel supplémentaire ni réinstallation des workers. API joignable via la
  VIP quand un CP tombe ; etcd survit à 1 panne. **4 nœuds de calcul/stockage
  conservés** (≠ modèle CP dédiés qui n'en laisserait qu'1).
- **Déviation assumée de
  [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md)** : etcd cohabite
  avec des OSD. Le risque « etcd affamé » est **mitigé** par la LV `etcd` dédiée
  (I/O isolées du `/var` partagé par containerd/rook), **mais doit être MESURÉ
  sous charge** (slow-apply etcd), pas postulé
  ([ADR 0034](0034-validation-e2e-from-scratch.md)). Si la mesure montre une
  instabilité du quorum sous charge, re-tainter les CP (sacrifier du calcul) ou
  revenir au modèle dédié 0047 reste l'échappatoire.
- **Pannes partiellement corrélées** : perdre 1 nœud parmi `node1/2` ôte d'un
  coup 1 CP, 1 mon et 12 OSD. Mitigation : mon dispersés hors `cp1`, réplication
  Ceph `size=3 failureDomain=host` (tolère 1 nœud), etcd quorum 3 (tolère 1
  nœud) — les domaines tiennent à **1 panne simultanée**.
- **Deux mécanismes de VIP** (kube-vip pour le CP, Cilium pour l'applicatif) :
  frontière à tenir, VIP API hors pool LB-IPAM **impérativement**, exclusion L2
  control-plane à lever.
- **Backup etcd étendu aux 3 CP** : le rôle
  [`etcd-backup`](../../bootstrap/roles/etcd-backup/) cible `hosts: control` →
  ajouter `node1/2` au groupe `control` suffit.
- **Implémentation = issue de suite (#250, amendée)** — cet ADR cadre, n'outille
  pas :
  1. rôle **kube-vip** (pod statique, image épinglée par digest d'index
     multi-arch [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md),
     valeurs génériques [ADR 0023](0023-plateforme-exemple-generique.md)) ;
  2. rôle **promotion control-plane** (génération `certificate-key` + join
     command sur le 1ᵉʳ CP ; `kubeadm join --control-plane` idempotent avec
     marqueur écrit après succès et rescue
     [ADR 0050](0050-modele-reprise-role-ansible.md), sur le patron de
     [`k8s-join-cluster`](../../bootstrap/roles/k8s-join-cluster/)) ;
  3. `certSANs` (VIP) dans
     [`kubeadm-config.yaml.j2`](../../bootstrap/roles/k8s-initialization/templates/kubeadm-config.yaml.j2)
     - repoint `cluster-api → VIP` dans
       [`k8s-install`](../../bootstrap/roles/k8s-install/) ;
  4. lever l'exclusion control-plane du `nodeSelector` L2 dans
     [`cni.sh`](../../bootstrap/cni.sh) ;
  5. **banc Lima 3 VM hyperconvergées** (3 CP, local-path — minimum pour prouver
     quorum 3 + VIP + survie à 1 panne) + **run de preuve from-scratch**
     ([ADR 0034](0034-validation-e2e-from-scratch.md)) ;
  6. `placement.mon` dans
     [`storage/ceph/cluster.yaml`](../../storage/ceph/cluster.yaml) +
     anti-affinité CoreDNS.
- **Ordre recommandé : 3-CP AVANT Ceph.** Promouvoir des CP sur un Ceph
  **absent** est gratuit ; déployer Ceph en 1-CP puis promouvoir obligerait à
  déplacer une mon sur un cluster Ceph **vivant** (rééquilibrage à risque sur
  données réelles). Tant que l'outillage et le run de preuve ne sont pas faits,
  le parc reste en **1 CP** (état
  [ADR 0002](0002-control-plane-unique-avec-endpoint.md)).

## Alternatives écartées

- **Rester en 1 CP** ([ADR 0002](0002-control-plane-unique-avec-endpoint.md)).
  Le plus simple, SPOF assumé + backup. Écarté **comme cible** dès lors que la
  HA est jugée nécessaire ET que son coût est devenu nul en calcul (taint
  retiré). Reste l'**état courant** tant que l'outillage HA n'est pas prouvé.
- **CP dédiés sur 4 nœuds** (modèle
  [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md) appliqué tel quel).
  Plus robuste (etcd découplé), mais laisserait **1 seul nœud** de
  calcul/stockage sur 4 → perte de 36 OSD et du calcul, inacceptable à cette
  densité ([ADR 0009](0009-pourquoi-4-noeuds.md)). Le modèle dédié vise un parc
  ≥ 6 machines, pas 4.
- **HAProxy + keepalived** pour la VIP. Écarté par
  [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md) (composant en plus,
  même contrainte ARP que kube-vip via le VRRP, sans le bénéfice du pod statique
  idempotent).
- **Cilium LB-IPAM pour la VIP de l'API.** Dépendance circulaire au bootstrap
  (API → VIP → Cilium → API), non bootstrap-able pour le control plane — déjà
  écarté par [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md). Cilium
  reste sur l'applicatif.
- **Promouvoir les 4 nœuds en CP** (etcd quorum 4). Quorum **pair** : ne tolère
  toujours qu'1 panne (besoin de 3 sur 4) tout en payant un 4ᵉ membre etcd.
  Aucun gain de tolérance, surcoût etcd. Écarté : 3 CP est l'optimum.
- **LB L4 externe** (équipement réseau de l'organisation). Techniquement
  supérieur (zéro composant cluster, zéro ARP concurrent) mais **hors code**,
  donc non reproductible depuis le code seul
  ([ADR 0052](0052-reproductibilite-des-resultats.md)). Repli conditionnel si
  l'organisation le fournit ; le banc reste sur kube-vip.
