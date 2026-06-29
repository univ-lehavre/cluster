# Plan — HA control-plane 3 nœuds (`ha-3cp` hyperconvergé, promotion in-place)

## État

> **État : Abandonné** (2026-06-29) · **Fonde :**
> [ADR 0055](../decisions/0055-ha-3cp-hyperconverge-promotion-in-place.md)
> (Superseded) +
> [ADR 0047](../decisions/0047-topologie-ha-3cp-control-plane-dedie.md)
> (Accepted). · **Issues :**
> [#486](https://github.com/univ-lehavre/cluster/issues/486) (SPOF
> control-plane), [#490](https://github.com/univ-lehavre/cluster/issues/490)
> (scrape CP), [#487](https://github.com/univ-lehavre/cluster/issues/487)
> (CoreDNS), suivi [#491](https://github.com/univ-lehavre/cluster/issues/491). ·
> **Preuve :** `bench/lima/RESULTS.md` (run `ha-3cp` jamais consigné).
>
> **Abandonné (2026-06-29).** La topologie `ha-3cp` n'est plus poursuivie :
> [ADR 0055](../decisions/0055-ha-3cp-hyperconverge-promotion-in-place.md) est
> passé **Superseded** et son outillage est retiré. La preuve exigeait un **banc
> 3-VM** (quorum etcd impair + failover VIP) qui est **abandonné** (poste de dev
> sans les ressources pour 3 VM) ; la HA du control plane ne se prouvant **que**
> sur prod, elle est instruite au **rebuild dirqual ~sept. 2026** (finding
> #486), hors de ce plan. Le geste CNI `ha-cni` (pose Cilium + fetch kubeconfig
> du bootstrap normal, sans rapport avec la HA) **reste** câblé. Le contenu
> ci-dessous est conservé comme trace de l'instruction, non comme feuille de
> route active.
>
> Le passage à `Abandonné` clôt la mise en œuvre incrémentale autorisée par
> [ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md).

Matérialise la mise en haute disponibilité du plan de contrôle de dirqual,
réponse au finding majeur #486 de l'audit prod du 2026-06-24
([docs/audit/2026-06-24-audit-prod-dirqual.md](../audit/2026-06-24-audit-prod-dirqual.md)).
Le chantier **absorbe** aussi #490 (scrape control-plane), #487 (CoreDNS) et
l'extension du backup etcd aux 3 CP.

## 1. Contexte + findings absorbés

L'audit prod (verdict : prod saine, mais 8 risques majeurs) place le
**control-plane mono-nœud comme le SPOF le plus grave**.

- **#486 (audit M4) — SPOF total.** `dirqual1` est le **seul** control-plane ;
  etcd a **1 seul membre**. Perdre/rebooter `dirqual1` perd l'API K8s **et**
  etcd en même temps. Dette structurante, objet central de ce chantier.
- **#490 (audit M8) — scrape control-plane DOWN.** `kube-etcd` /
  `kube-scheduler` / `kube-controller-manager` sont `up=0` (binding métriques
  sur `127.0.0.1`, Prometheus scrape l'IP du nœud) → alertes en faux positif.
  **Absorbé** : la mise en HA exige de toute façon de binder etcd sur `0.0.0.0`
  (le 3ᵉ membre doit être joignable hors-nœud) ; même réglage `kubeadm` + mêmes
  `values` monitoring.
- **#487 (audit M5) — 2 répliques CoreDNS sur `dirqual1`.** Anti-affinité `soft`
  non respectée → DNS interne entièrement sur le SPOF. **Absorbé** : la
  dispersion DNS n'a de sens qu'avec ≥ 2 nœuds sains, même geste « durcir la
  répartition ».
- **Backup etcd étendu.** Le rôle `etcd-backup` cible `hosts: control` ; passer
  de 1 à 3 membres impose d'étendre le snapshot horaire + le fetch hors-nœud aux
  3 CP (ADR 0055 §3 : **HA ≠ backup**, le backup reste le filet pendant la
  promotion).

## 2. ADR fondateurs

| ADR                                                                                                                       | Apport                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [0055](../decisions/0055-ha-3cp-hyperconverge-promotion-in-place.md)                                                      | **Le cœur** : 3 CP hyperconvergés sur 4 nœuds identiques ; promotion **in-place** ; VIP kube-vip ARP **hors pool LB-IPAM** ; etcd stacked quorum 3 ; mon Ceph hors alignement etcd ; banc avant prod ; un CP à la fois. |
| [0047](../decisions/0047-topologie-ha-3cp-control-plane-dedie.md)                                                         | Cadre `ha-3cp`, mécanisme VIP kube-vip pod statique.                                                                                                                                                                    |
| [0002](../decisions/0002-control-plane-unique-avec-endpoint.md)                                                           | `cluster-api:6443` posé dès l'init → la VIP s'y substitue sans réinstaller les workers.                                                                                                                                 |
| [0034](../decisions/0034-validation-e2e-from-scratch.md) / [0052](../decisions/0052-reproductibilite-des-resultats.md)    | Preuve banc _from-scratch_ AVANT prod ; comportement **mesuré**, pas postulé.                                                                                                                                           |
| [0045](../decisions/0045-chemins-installation-banc-couches.md) / [0046](../decisions/0046-corriger-le-code-pas-l-etat.md) | Chemin nommé codé ; corriger le **code**, pas l'**état**.                                                                                                                                                               |
| [0054](../decisions/0054-rollback-par-phase-banc.md)                                                                      | Rollback par phase au banc.                                                                                                                                                                                             |
| [0092](../decisions/0092-exposition-hostport-l4.md)                                                                       | **Fait nouveau** : exposition passée en L4 NodePort/hostPort ⇒ le piège L2 d'ADR 0055 §2 est **caduc** (cf. invariant 1).                                                                                               |
| [0023](../decisions/0023-plateforme-exemple-generique.md)                                                                 | VIP/IP/noms = valeurs **génériques**, surcharges réelles gitignorées.                                                                                                                                                   |

## 3. Invariants

1. **VIP API HORS du pool LB-IPAM Cilium** (ADR 0055 §2). La VIP n'est pas un
   Service k8s. À réserver formellement avec l'admin réseau.
   - **Nuance vérifiée dans le code** : le « piège hyperconvergence §2 » d'ADR
     0055 (lever l'exclusion control-plane du `CiliumL2AnnouncementPolicy`) est
     **caduc** — `bootstrap/cni.sh` est passé en **L4 NodePort pur (ADR 0092)**
     et **supprime** `ciliuml2announcementpolicy default-l2`. Plus de L2
     announcement Cilium à dé-exclure. **À confirmer au banc** : kube-vip ARP
     (VIP API) et le datapath eBPF L4 ne se chevauchent pas. Si l'organisation
     re-bascule un jour sur LB-IPAM/L2, le garde-fou 0055 §2 redevient actif.
2. **Quorum etcd impair = 3 membres** (les 3 CP), jamais 4. Survie à 1 panne ;
   perte de 2 CP = etcd figé (limite assumée).
3. **Découplage etcd / mon Ceph** : perdre 1 nœud ne doit pas amputer en même
   temps 1/3 du quorum etcd ET 1/3 du quorum mon sur le **même** nœud (ADR 0055
   §1 ; voir étape P0).
4. **Banc avant prod** : aucune commande sur dirqual avant un run de preuve 3-VM
   consigné (ADR 0034/0052). Le banc actuel (1 CP) ne reproduit PAS le chemin
   HA.
5. **Corriger le code, pas l'état** (ADR 0046). Tout passe par les rôles/chemins
   nommés ; aucun `kubectl edit` / `kubeadm` manuel hors RUNBOOK.
6. **Un CP à la fois, gate etcd healthy entre chaque** (ADR 0055 §4). La fenêtre
   N=2 est plus fragile que N=1 : la perte d'1 membre y fige le quorum. Le
   backup etcd horaire est le filet.

## 4. État de l'art du code (à RÉUTILISER, ne pas recréer)

| Brique                  | Fichier                                                                  | État                                                                                                           |
| ----------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Rôle kube-vip (ARP)     | `bootstrap/roles/kube-vip/`                                              | ✅ codé, image épinglée par digest, amorçage super-admin→admin paramétré.                                      |
| Rôle promotion CP       | `bootstrap/roles/k8s-join-control-plane/`                                | ✅ codé : upload-certs, `join --control-plane`, marqueur idempotent, **rescue** (reset + retrait membre etcd). |
| Backup etcd             | `bootstrap/roles/etcd-backup/` + `etcd-backup.yaml` / `etcd-fetch.yaml`  | ✅ codé, `hosts: control` (s'étend quand `node1/2` rejoignent `control`). _(template réparé — PR #492)._       |
| kubeadm-config          | `bootstrap/roles/k8s-initialization/templates/kubeadm-config.yaml.j2`    | ✅ certSANs VIP. **+ ce chantier** : `controllerManager`/`scheduler`/`etcd` `bind-address 0.0.0.0` pour #490.  |
| Playbooks montage       | `bootstrap/kube-vip.yaml`, `bootstrap/join-control-plane.yaml`           | ✅ codés (`hosts: control` + audit-log).                                                                       |
| Orchestration HA Python | `scripts/topology.py` (`cmd_ha_3cp`) + `nestor/ha.py`                    | ✅ codé et testé (fonctions pures : `cp_join_order`, `classify_etcd_health`, gates).                           |
| Chemin banc             | `bench/lima/run-phases.sh` (`run_ha_3cp`, arm `ha-3cp`)                  | ✅ codé (`cp1/cp2/cp3`, VIP `.40` hors LB-IPAM).                                                               |
| Scénarios HA            | `bench/scenarios/30-ha-3cp-cp-survival.sh`, `04-*`, `09-etcd-restore.sh` | ✅ codés (30 = survie VIP+etcd à 1 panne ; 09 = restore etcd).                                                 |
| Placement mon Ceph      | `storage/ceph/cluster.yaml`                                              | ⚠️ **aucun `placement.mon` actif** (exemples commentés) → work item ADR 0055 §1 (étape P0).                    |
| Scrape monitoring CP    | `platform/kube-prometheus-stack/values.bench.yaml`                       | ⚠️ **aucun override** `kubeEtcd`/`kubeScheduler`/`kubeControllerManager` → work item #490 (étape B0).          |
| CoreDNS anti-affinité   | _(aucun fichier)_                                                        | ⚠️ **aucun patch CoreDNS** → work item #487 (étape P3).                                                        |

**Cadrage** : chantier à ~70 % outillé. Reste = (a) **3 correctifs de code** non
faits (#490 kubeadm+values, #487 CoreDNS, placement.mon), (b) le **run de preuve
3-VM consigné** (jamais fait), (c) la **promotion prod in-place**.

## 5. Étapes

Deux blocs : **(A) banc 3-VM de preuve** puis **(B) promotion prod in-place**.
Le bloc B ne démarre qu'après preuve A consignée (invariant 4). Noms génériques
au banc (`cp1/cp2/cp3`, VIP `<préfixe>.40`) ; noms prod réels observés
(`dirqual1-4`).

### Bloc A — Banc 3-VM de preuve

#### B0 — Compléter les 3 correctifs de code (pré-requis au run)

- **Faire** : (1) #490/kubeadm — `controllerManager`/`scheduler`/`etcd.local`
  `extraArgs` bind-address `0.0.0.0` dans `kubeadm-config.yaml.j2` _(amorcé sur
  la branche de ce plan)_ ; (2) #490/monitoring — pointer
  `kubeEtcd`/`kubeControllerManager`/`kubeScheduler` sur les IP des 3 CP +
  régénérer `kube-prometheus-stack.yaml` ; (3) noter que `placement.mon` (P0) ne
  concerne que la prod-avec-Ceph (le banc 3-VM est **local-path**, pas de Ceph).
- **Fichiers** : `kubeadm-config.yaml.j2`, `values.bench.yaml` (+ chart
  régénéré).
- **Preuve SANS banc** : `ansible-lint`, rendu Jinja (dry-run), `helm template`
  diff, `pytest nestor/ha.py`.
- **Preuve banc 3-VM** : `/api/v1/targets` → 3 targets CP **up=1** (#490
  disparaît).

#### B1 — Monter le banc 3-VM `ha-3cp` from-scratch

- **Faire** : `bench/lima/run-phases.sh ha-3cp` (chemin nommé codé) : 3 VM
  local-path, kube-vip AVANT `kubeadm init` (VIP = `controlPlaneEndpoint`), CNI
  Cilium L4, puis promotion `cp2` puis `cp3` un à un (gate etcd entre chaque).
- **Preuve banc 3-VM (le run ADR 0034)** : VIP `/healthz` ok ;
  `controlPlaneEndpoint` = VIP (TLS via VIP OK) ; 3 membres etcd healthy (quorum
  3/3) ; 3 CP Ready ; **idempotence** rejeu `changed=0`.

#### B2 — Prouver la survie à la perte d'1 CP (la VALEUR de la HA)

- **Faire** : scénario `30-ha-3cp-cp-survival.sh` : 3/3 → arrêt du CP porteur de
  la VIP → bascule kube-vip + quorum 2/3 + API joignable → restore → 3/3.
- **Preuve banc 3-VM** : scénario 30 vert ; pas de collision ARP VIP↔L4
  (invariant 1) ; scénario 09 (restore etcd) vert ; consigner dans `RESULTS.md`.

#### B3 — Mesurer le coût hyperconvergence

- **Faire** : mesurer le **slow-apply etcd** (réserve ADR 0047/0055 : etcd
  cohabite avec OSD). Au banc local-path **pas d'OSD** → mesure **partielle** ;
  la mesure complète (etcd + OSD) = prod ou banc HA+Ceph ultérieur. **Dette de
  preuve** (§7).
- **Preuve banc 3-VM** : plancher RAM/CP confirmé (cible ~5 GiB/CP), latence au
  repos consignée.

> **Gate A→B** : `RESULTS.md` consigné (B1+B2 verts, changed=0). Sans cela, le
> bloc B est interdit (invariant 4).

### Bloc B — Promotion prod in-place sur dirqual

Cible (ADR 0055 §1) : **3 CP** = `dirqual1` + **2 des workers** ; le 4ᵉ reste
worker pur sans membre etcd.

#### P0 — Choisir les 2 nœuds + figer le placement mon (DÉCISION À POSER)

- **Faire** : observer en prod quels nœuds portent les 3 mon Ceph, puis **forcer
  `placement.mon`** dans `storage/ceph/cluster.yaml` pour découpler etcd/mon
  (invariant 3). Cible ADR 0055 : mon hors `cp1` ; recouvrement etcd∩mon limité
  à 2 nœuds (assumé, mitigé par `size=3 failureDomain=host`).
- **Fichiers** : `storage/ceph/cluster.yaml` (ajouter `placement.mon`, absent).
- **Preuve prod (lecture seule d'abord)** : `kubectl get pods -o wide` mon+nodes
  ; après application, mon respectent l'affinité **sur un Ceph vivant**
  (R-CEPH).

> **NB** : « 3-CP AVANT Ceph » (ADR 0055) est gratuit (CP sur Ceph absent). En
> prod Ceph est **déjà vivant** → cas coûteux (déplacer une mon sur données
> réelles). Argument fort pour la **reco rebuild** (cf. §8).

#### P1 — Réserver la VIP + poser kube-vip sur dirqual1 (encore 1-CP)

- **Faire** : réserver la VIP (hors DHCP, hors LB-IPAM), surcharge gitignorée,
  jouer `bootstrap/kube-vip.yaml` (`hosts: control` = `dirqual1`), repointer
  `cluster-api` → VIP.
- **Preuve prod** : `curl -sk https://<VIP>:6443/healthz` = ok ; workers
  joignent toujours l'API ; **rollback trivial** (retirer le static pod,
  repointer cluster-api).

#### P2 — Promouvoir le 1er worker (etcd 1→2) puis le 2e (2→3)

- **Faire** : ajouter le worker au groupe `control` (`hosts.yaml` gitignoré),
  jouer `bootstrap/join-control-plane.yaml --limit <nœud>` (reset → join, gate
  VIP, rescue armé). **Attendre etcd 2/2 healthy.** Répéter pour le 2e. **Jamais
  en parallèle** (invariant 6).
- **Preuve prod** : après CP n°2 → etcd 2/2 ; après CP n°3 → 3/3 + 3 CP Ready ;
  static pods apiserver/etcd présents sur les 3 nœuds.
- **Filet** : backup etcd horaire actif AVANT P2 ; rescue compense un échec ;
  restore snapshot en dernier recours (scénario 09 prouvé au banc).

#### P3 — Durcir CoreDNS (#487) + étendre backup etcd

- **Faire** : anti-affinité CoreDNS `preferred` → **`required`** (ou
  `topologySpreadConstraint` hard sur `kubernetes.io/hostname`) — possible car ≥
  2 nœuds sains. Confirmer `etcd-backup`/`etcd-fetch` couvrent les 3 CP.
- **Fichiers** : patch CoreDNS (à créer, absent),
  `etcd-backup.yaml`/`etcd-fetch.yaml`.
- **Preuve prod** : 2 répliques CoreDNS sur 2 nœuds distincts ; 3 snapshots etcd
  horaires (1/CP) + fetch OK.

#### P4 — ADR/RUNBOOK/plan + clore findings

- RUNBOOK section HA ; #486 résolu (1 CP → 3 CP) ; #490/#487 clos ; plan → Actif
  puis Achevé ; run prod consigné dans RESULTS/audit.

## 6. kube-vip ARP vs « vrai » LB — load-balancing sur 3 CP & kubeconfig

> Questions posées : « comment load-balancer sur 3 CP ? » + « configurable dans
> kubeconfig ? »

- **Ce n'est PAS du load-balancing réparti.** kube-vip en mode **ARP** porte
  **une VIP unique** qui vit **sur un seul CP à la fois** (élection de leader).
  Toutes les requêtes API vont vers le CP porteur. S'il tombe, kube-vip
  **réélit** un leader et la VIP **bascule** (failover ARP, < 60 s, prouvé par
  le scénario 30). C'est de la **haute disponibilité par bascule**, pas de la
  **répartition de charge** entre les 3 apiservers.
- **Dans le kubeconfig** : un **seul** `server: https://cluster-api:6443` (= la
  VIP). Le client ne connaît qu'une adresse stable ; le failover est transparent
  (la VIP ne change pas, seul le nœud qui la porte change). On ne met **pas** 3
  endpoints — kubeconfig ne sait pas load-balancer plusieurs `server:`.
- **Vraie répartition** : exigerait un **LB L4 externe** (équipement réseau de
  l'organisation) devant les 3 IP:6443 — **hors code**, donc non reproductible
  (ADR 0052) ; repli conditionnel si l'organisation le fournit. La cible par
  défaut reste kube-vip ARP (bare-metal/Lima sans BGP).

## 7. Risques + rollback

| #         | Risque                                                | Étape | Mitigation                                                             | Rollback                                                |
| --------- | ----------------------------------------------------- | ----- | ---------------------------------------------------------------------- | ------------------------------------------------------- |
| R-QUORUM  | Erreur en promotion → perte quorum etcd (fenêtre N=2) | P2    | Un CP à la fois + gate etcd healthy ; backup etcd horaire actif        | Rescue du rôle ; restore snapshot (scénario 09/RUNBOOK) |
| R-CEPH    | `placement.mon` sur Ceph **vivant** → rééquilibrage   | P0    | Hors charge, mon par mon, surveiller `HEALTH_OK`                       | Retirer `placement.mon`, laisser Rook re-scheduler      |
| R-L2      | Collision ARP VIP API ↔ exposition réseau             | P1/B2 | Invariant 1 ; **L2 Cilium déjà supprimé (ADR 0092)** → résiduel faible | Retirer static pod kube-vip, repointer cluster-api      |
| R-VIP-RES | VIP non réservée → conflit DHCP/IP                    | P1    | Réservation formelle admin réseau, hors LB-IPAM                        | Changer la VIP (surcharge), rejouer kube-vip            |
| R-CERTKEY | certificate-key expirée (TTL 2 h) entre 2 promotions  | P2    | Le rôle régénère la clé à chaque jeu                                   | Re-jouer le rôle (idempotent)                           |
| R-STARVE  | etcd affamé par OSD sous charge (hyperconvergence)    | P2/B3 | LV `etcd` dédiée (I/O isolées) ; **mesurer** slow-apply (B3 partiel)   | Re-tainter les CP, ou modèle CP dédiés (ADR 0047)       |
| R-DROP    | Promotion prod sans preuve banc                       | A→B   | Invariant 4 strict : RESULTS.md consigné obligatoire                   | N/A (interdit)                                          |

**Rollback par phase (ADR 0054)** : au banc, le cycle monte→rollback→remonte est
rejouable (banc jetable). En prod, rollback **par étape** (table ci-dessus), pas
destructif global.

## 8. Question ouverte — promouvoir AVANT ou ATTENDRE le rebuild ~sept 2026 ?

**Recommandation : ATTENDRE le rebuild _from-scratch_ en 3-CP d'emblée.**

1. **Ceph vivant rend P0 coûteux.** ADR 0055 dit « 3-CP AVANT Ceph » : gratuit
   sur Ceph absent, **risqué** sur Ceph vivant (déplacer une mon sur données
   réelles, R-CEPH). Le rebuild repart d'un Ceph absent → P0 gratuit.
2. **`kubeadm reset` des workers en prod** (promotion in-place) est plus risqué
   qu'un montage _from-scratch_ où chaque nœud naît CP.
3. **L'audit lui-même** classe #486 en dette structurante à instruire **au
   rebuild ~sept 2026**.

**MAIS** la promotion in-place reste **outillée et prouvable dès maintenant**.
**Repli si le rebuild glisse ou si un incident `dirqual1` survient avant** :
exécuter le bloc B in-place (gain HA immédiat), filet = backup etcd. Dans tous
les cas, le **bloc A (preuve banc) est à faire sans attendre** — il ne dépend
pas de la prod et débloque les deux options.

## Suivi

- [ ] B0 — 3 correctifs de code (#490 kubeadm _(amorcé)_ + values ;
      placement.mon noté ; CoreDNS noté)
- [ ] B1 — banc 3-VM `ha-3cp` from-scratch (VIP, quorum 3/3, idempotence)
- [ ] B2 — scénario 30 (survie 1 CP) + 09 (restore etcd) verts, RESULTS.md
- [ ] B3 — mesure coût hyperconvergence (partielle, dette documentée)
- [ ] P0 — choix des 2 nœuds + `placement.mon` (DÉCISION)
- [ ] P1 — VIP réservée + kube-vip sur dirqual1
- [ ] P2 — promotion 1er puis 2e worker (etcd 1→2→3)
- [ ] P3 — CoreDNS `required` + backup etcd 3 CP
- [ ] P4 — RUNBOOK/ADR/plan + clôture #486/#490/#487
