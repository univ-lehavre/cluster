# 0040 — Stratégie terrains × topologies : quel terrain monte quelle topologie

## Contexte

Le catalogue a deux axes liés ici : le **terrain** (`local`, `cloud`,
`baremetal` — [ADR 0039](0039-nomenclature-axes-catalogue.md)) et la
**topologie** (`multi-node-3`, `multi-node-4`, `ha-3cp`, `multisite` —
[ADR 0030](0030-nomenclature-bancs-topologies.md)). Tous les croisements ne sont
pas réalisables : un terrain **contraint** les topologies qu'il peut porter, et
les ressources disponibles bornent la complexité atteignable.

Trois faits concrets fixent la stratégie :

1. **Local = Lima sur le poste de dev**
   ([ADR 0038](0038-lima-seul-banc-local.md)) : Lima crée **plusieurs VMs
   distinctes** → il porte `multi-node-3` (3 VMs, Ceph ×3 réel), la topologie de
   **référence**, déjà validée e2e.
2. **Cloud = Oracle Free Tier Ampere (arm64).** Le « Always Free » offre **4
   OCPU Ampere A1 + 24 Go RAM**, _usable as **1 VM or up to 4 VMs**_, plus **1
   Load Balancer**, **200 Go de block storage** (2 volumes) et 20 Go d'object
   storage. L'offre x86 gratuite (AMD E2.1.Micro, 1/8 OCPU / 1 Go) est
   **inutilisable** pour k8s → **pas de x86 sur Oracle**, tout est **arm64**. Le
   pool 4 VMs permet un vrai `multi-node-3` en cloud (pas seulement un nœud
   unique).
3. **Bare-metal = prod réelle x86** : châssis HPE Apollo 2000, 4 lames XL420 → 1
   CP + 3 workers (`multi-node-4`, [ADR 0009](0009-pourquoi-4-noeuds.md)). Seul
   terrain **x86** du catalogue.

> **`single-node` est abandonné.** Un nœud unique impose trop de dégradations
> (Ceph ×1 non résilient, CNPG mono-instance, risque OOM/disque — drifts
> L28/L43) pour rester représentatif. Le cloud Oracle, grâce aux 4 VMs du Free
> Tier, fait `multi-node-3` natif plutôt qu'un single-node. La topologie
> `single-node` est donc retirée du catalogue
> ([ADR 0030](0030-nomenclature-bancs-topologies.md)).

## Décision

**Chaque terrain porte la topologie qui lui correspond ; la complexité des
topologies HA/multisite s'adapte aux ressources locales.**

| Terrain (code) | Topologie      | Provisioner         | Rôle                                                       | État             |
| -------------- | -------------- | ------------------- | ---------------------------------------------------------- | ---------------- |
| `local`        | `multi-node-3` | Lima                | **référence** : multi-nœuds, Ceph ×3 (arm64)               | **buildé**       |
| `local`        | `ha-3cp`       | Lima                | HA control plane (3 CP), complexité adaptée aux ressources | cible            |
| `local`        | `multisite`    | Lima                | fédération Cilium Cluster Mesh, si ressources suffisantes  | cible (étirée)   |
| `cloud`        | `multi-node-3` | OpenTofu (ADR 0032) | cible cloud (arm64) : 3 VMs du pool Ampere                 | cible            |
| `cloud`        | `ha-3cp`       | OpenTofu            | HA via le **Load Balancer** Free Tier (endpoint flottant)  | cible (escalade) |
| `baremetal`    | `multi-node-4` | manuel / PXE        | **prod réelle x86** : 4 nœuds (1 CP + 3 workers, ADR 0009) | cible (prod)     |

Conséquences de cadrage :

1. **`multi-node-3` est la topologie d'itération, en arm64**, sur deux terrains
   : `local` (Lima, référence validée) et `cloud` (Oracle, 3 VMs du pool). On
   **n'imbrique jamais** Lima dans une VM cloud : on découpe le pool Free Tier
   en vraies instances OCI distinctes.
2. **`ha-3cp` et `multisite` : cibles à _complexité adaptée aux ressources_.**
   Le banc HA/multisite monte ce que le poste peut porter, par **paliers de RAM
   allouée au banc** — la **somme `nb_VMs × VM_MEMORY`** qu'on _donne_ aux VMs,
   **pas** la RAM physique (qui inclut macOS + apps + Lima). Mesure déterministe
   : sur le banc de référence, 3 × 8 Go = **24 Go alloués** (sur 48 installés).

   Principe directeur : **dissocier ce qu'on éprouve (la _mécanique_ de la
   topologie : quorum, fédération) de la _charge_ (les briques applicatives)**.
   Un banc HA **minimal** prouve déjà la HA (quorum etcd + VIP + survie à la
   perte d'un CP) **sans** Ceph ni dataops. On n'ajoute le lourd que si la RAM
   suit.

   | RAM allouée au banc  | `ha-3cp`                                           | `multisite`                      |
   | -------------------- | -------------------------------------------------- | -------------------------------- |
   | socle ×3 (mécanique) | 3 CP **légers** (`base`) — quorum + VIP + perte CP | 2 clusters légers — Cluster Mesh |
   | + marge stockage     | 3 CP + workers + Ceph (HA réaliste)                | 2 clusters `multi-node` + Mesh   |
   | + grande marge       | + chaîne `dataops` (charge complète)               | + `dataops` réparti              |

   **Plancher exact = à MESURER au 1er run `ha-3cp`**
   ([ADR 0034](0034-validation-e2e-from-scratch.md) : pas de chiffre inventé).
   Un CP minimal (k8s + etcd + Cilium) coûte ~2–3 Go ; le plancher mécanique est
   donc bien plus bas que le banc Ceph actuel — le run dira combien de RAM/CP
   avant instabilité du quorum etcd ; on inscrira la valeur ici.

   Prérequis technique de `ha-3cp` : un **endpoint flottant** (VIP) devant les 3
   CP — aujourd'hui `control_plane_endpoint` pointe le seul cp1 via
   `/etc/hosts`, ce qui ne survit pas à la perte de cp1. Le **mécanisme est
   désormais tranché** par
   [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md) : **kube-vip en pod
   statique** en local (amorçage avant Cilium → pas d'œuf-poule), **Load
   Balancer** Free Tier en cloud. `ha-3cp` y est aussi **défini** comme 3 CP
   **dédiés** + 3 workers (≠ hyperconvergé), banc en **local-path d'abord** (la
   mécanique HA avant Ceph). Il reste `cible` tant que l'outillage (rôle
   kube-vip, banc 6 VMs) et le run de preuve ne sont pas faits. La sélection
   topologie × palier sera un **outillage dédié** (l'ancien `TOPO`, limité à la
   variation du nombre de nœuds, a été abandonné).

3. **`x86` ne se teste QUE sur bare-metal.** L'unique terrain x86 est
   **`x86/baremetal/multi-node-4`** (cible **prod**, 4 nœuds, ADR 0009). Tous
   les terrains d'**itération** (local Lima, cloud Oracle) sont **arm64** :
   émuler x86 en local est exclu (QEMU trop lent → gates en timeout ; Rosetta =
   binaires x86 sur kernel arm, non fidèle), et le Free Tier x86 est
   inexploitable. x86 est donc un **angle mort des bancs d'itération** : un bug
   spécifique x86 ne se révélerait qu'au déploiement prod — d'où l'impératif
   d'un chemin **strictement identique** arm64/x86 (kubeadm, images multi-arch
   [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)). Le banc local
   `multi-node-3` est le **modèle réduit fidèle** de la prod `multi-node-4`
   (même chemin, un worker de moins).

## Statut

Accepted. (Précise [ADR 0030](0030-nomenclature-bancs-topologies.md) et
[ADR 0038](0038-lima-seul-banc-local.md) en liant terrain et topologie ; cadre
la cible cloud de [ADR 0031](0031-terrain-cloud-arm.md) /
[ADR 0032](0032-opentofu-provisioning-cloud.md). Abandonne `single-node` et le
mécanisme `TOPO`.)

## Conséquences

- **Gain** : la question « quel terrain monte quelle topologie » a une réponse
  nette, avec un rôle par combinaison (référence, cible cloud, HA, prod). La
  complexité HA/multisite est **proportionnée aux ressources**, pas
  tout-ou-rien.
- **Couverture résultante** : `arm64/local/multi-node-3` (référence validée),
  `arm64/cloud/multi-node-3` (fidélité cloud), `x86/baremetal/multi-node-4`
  (prod), et à terme `arm64/{local,cloud}/ha-3cp` (vraie HA CP via VIP/LB).
  **arm64 partout en itération ; x86 seulement en prod bare-metal.**
- **Prix à payer** : pas de témoin `single-node` pour isoler finement un axe —
  on l'assume (single-node était trop dégradé pour être un témoin fiable). x86
  reste non couvert hors prod (angle mort assumé, mitigé par le chemin
  identique).
- **Discipline** : ne pas reproduire artificiellement une topologie sur un
  terrain qui ne s'y prête pas. `ha-3cp` exige d'abord l'endpoint flottant
  (VIP/LB). La validation reste un run **from-scratch** (ADR 0034), quel que
  soit le palier.
