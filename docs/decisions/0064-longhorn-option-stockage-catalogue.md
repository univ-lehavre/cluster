# 0064 — Longhorn comme option de stockage du catalogue (3ᵉ profil bloc répliqué)

## Contexte

Le dépôt est un **catalogue de topologies**
([ADR 0023](0023-plateforme-exemple-generique.md)) : plusieurs infrastructures
déclarées, une activée par déploiement. Côté stockage persistant, il n'expose
aujourd'hui que **deux profils** :

| Profil       | Brique                         | Résilience                      | Formes                 | Usage actuel              |
| ------------ | ------------------------------ | ------------------------------- | ---------------------- | ------------------------- |
| `local-path` | rancher local-path-provisioner | **aucune** (PV épinglé au nœud) | bloc RWO               | bancs légers, jetable     |
| `ceph`       | Rook-Ceph                      | ×3 / EC 2+1                     | bloc + objet + fichier | prod datalake, banc lourd |

Il y a donc un **trou au milieu du catalogue** : entre le local-path (zéro
résilience, mono-nœud) et Ceph (résilient mais complexité opérationnelle élevée,
plancher de 4 nœuds — [ADR 0009](0009-pourquoi-4-noeuds.md)), **aucune option
n'offre du bloc répliqué multi-nœuds simple**. Une topologie multi-nœuds qui
veut survivre à la perte d'un nœud **sans** payer le coût d'exploitation de Ceph
(mon/mgr/osd/rgw, pools, CRUSH, rééquilibrage) n'a pas de réponse.

[ADR 0018](0018-rook-ceph-vs-longhorn.md) a tranché **Rook-Ceph plutôt que
Longhorn** — mais pour un cas d'usage précis : le **datalake universitaire** (≈
264 TiB brut, besoin **objet S3** ET bloc, gros volumes HDD avec block.db NVMe).
Sa conclusion (« Ceph unifie bloc + objet + fichier ; Longhorn ne fait que du
bloc ») est **vraie pour cette topologie-là**. Elle ne dit rien des topologies
du catalogue qui **n'ont pas** de besoin objet, ou dont l'échelle ne justifie
pas Ceph. 0018 le reconnaît d'ailleurs en clôture (« À revoir si… le besoin
objet disparaît / l'échelle se réduit »).

La question posée ici n'est donc pas « Ceph **ou** Longhorn ? » (0018 a répondu
pour le datalake), mais « le catalogue doit-il **proposer** Longhorn comme
option de stockage, au même titre qu'il propose local-path et Ceph ? ».

## Décision

**Longhorn devient un troisième profil de stockage du catalogue**, à côté de
`local-path` et `ceph` — bloc distribué répliqué, **sans besoin de Ceph**. Il ne
remplace ni n'invalide [ADR 0018](0018-rook-ceph-vs-longhorn.md) : il **comble
le trou** entre les deux profils existants.

| Profil       | Brique                 | Nœuds | Résilience bloc | Objet S3                        | Complexité | Créneau                                      |
| ------------ | ---------------------- | ----- | --------------- | ------------------------------- | ---------- | -------------------------------------------- |
| `local-path` | local-path-provisioner | 1+    | **aucune**      | non                             | minimale   | jetable, mono-nœud, dev                      |
| `longhorn`   | Longhorn               | 2-3+  | ×2/×3 répliqué  | **non** (2ᵉ solution si besoin) | légère     | **bloc répliqué multi-nœuds, sans datalake** |
| `ceph`       | Rook-Ceph              | 4+    | ×3 / EC 2+1     | **oui** (RGW intégré)           | élevée     | prod datalake, bloc + objet + fichier unifié |

1. **Longhorn = bloc répliqué simple.** Réplication synchrone ×2/×3 pilotée par
   un operator, plus simple à opérer que Ceph (pas de pools/CRUSH/rééquilibrage
   manuel), plus résilient que local-path (survit à la perte d'un nœud). C'est
   le **profil intermédiaire** qui manquait.

2. **Longhorn ne fait pas d'objet — et c'est assumé.** Là où 0018 a écarté
   Longhorn parce que le **datalake** exige du S3, ce profil vise précisément
   les topologies **sans datalake**. Si une topologie sous Longhorn a malgré
   tout besoin d'un S3 intra-cluster (Loki, backups CNPG — cf.
   [ADR 0036](0036-backing-s3-unique-rgw.md)), elle l'obtient par une **2ᵉ
   solution objet légère** (SeaweedFS/MinIO), exactement comme le banc léger
   `local-path` le fait déjà avec SeaweedFS. Le couple **Longhorn (bloc) +
   SeaweedFS/MinIO (objet)** est une alternative explicite au **Ceph unifié**,
   au prix de deux briques au lieu d'une.

3. **Ceph reste le socle du datalake.** Pour la topologie de production
   hyperconvergée (gros volumes, bloc + objet + fichier en une plateforme), le
   choix de [ADR 0018](0018-rook-ceph-vs-longhorn.md) tient **intégralement** :
   Longhorn n'y est pas un candidat (échelle disque, objet intégré, EC). Ce
   présent ADR **n'autorise pas** à remplacer Ceph par Longhorn sur le datalake.

4. **Un profil = une StorageClass par défaut, une à la fois.** Comme pour
   local-path et Ceph, activer le profil `longhorn` pose **exactement une**
   StorageClass par défaut (`longhorn`), en s'effaçant des autres (même
   discipline « une seule SC default » que la bascule local-path ↔ Ceph
   existante).

5. **Tension avec 0018 — assumée et bornée.** Ouvrir Longhorn « généralisé » (y
   compris quand il y a un besoin objet, via une 2ᵉ solution) **rouvre**
   frontalement le débat de fond de 0018 : faut-il un stockage **unifié** (Ceph)
   ou **composé** (Longhorn + objet à côté) ? Le catalogue tranche : **les
   deux**, selon la topologie. 0018 garde la main sur le **datalake** ; 0064
   ouvre la composition pour les topologies qui préfèrent la simplicité du bloc
   répliqué et n'ont pas l'échelle du datalake. Le garde-fou : **aucune
   topologie réelle de production datalake** ne bascule sous Longhorn sans un
   ADR successeur qui reviendrait explicitement sur 0018.

## Statut

Proposed (2026-06-13).

**Complète** [ADR 0018](0018-rook-ceph-vs-longhorn.md) **sans l'invalider** :
0018 reste `Accepted` et fait toujours foi pour le **socle datalake** (Ceph).
0064 ajoute Longhorn comme **option du catalogue** pour les topologies
bloc-seul, exploitant le créneau que 0018 laisse ouvert dans son « À revoir si
». Met en œuvre la doctrine [ADR 0023](0023-plateforme-exemple-generique.md)
(catalogue multi-topologies : plusieurs profils déclarés, un activé).

**Conforme à la gouvernance**
[ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) §6 : tant que cet
ADR est `Proposed`, **aucun code** (manifeste vendored, rôle Ansible) n'est
produit ; le plan de mise en œuvre
([`plan-stockage-longhorn.md`](../plans/plan-stockage-longhorn.md)) reste en
`Brouillon`. Le passage à `Accepted` est le signal qui autorise
l'implémentation.

## Conséquences

**Bénéfices.**

- Le catalogue couvre enfin **les trois régimes** : jetable (`local-path`), bloc
  répliqué simple (`longhorn`), unifié haute capacité (`ceph`). Une topologie
  multi-nœuds sans datalake a une réponse résiliente **sans** la complexité
  Ceph.
- Cohérent avec [ADR 0023](0023-plateforme-exemple-generique.md) : un catalogue
  **propose** des briques alternatives ; Longhorn en devient une, documentée et
  activable, pas seulement « l'alternative écartée » de 0018.

**Coûts assumés.**

- **Une brique de plus à maintenir** (manifeste vendored épinglé par digest
  multi-arch — [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md) —,
  rôle Ansible, place dans les chemins d'installation et le healthcheck). Le
  catalogue grandit.
- **Stockage composé** sous Longhorn : si une topologie a besoin d'objet, elle
  porte **deux** briques (Longhorn + SeaweedFS/MinIO) là où Ceph en porterait
  une. Le bilan simplicité/unification se réévalue par topologie.
- **Preuve de banc à produire**
  ([ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md))
  : un profil de stockage n'a de valeur que **prouvé par un run** (réplication
  réelle, survie à la perte d'un nœud). Tant que ce run n'existe pas, Longhorn
  reste une option **déclarée mais non prouvée**.

## À revoir si

- **Longhorn n'apporte pas de gain net** face à Ceph une fois la 2ᵉ brique objet
  comptée (si toutes les topologies finissent par vouloir de l'objet, l'unifié
  Ceph redevient préférable et ce profil perd son créneau).
- **Une topologie de production datalake** veut basculer sous Longhorn : cela
  reviendrait sur le fond de [ADR 0018](0018-rook-ceph-vs-longhorn.md) et exige
  un **ADR successeur dédié** (0064 ne le permet pas).

## Alternatives écartées

- **Ne rien faire (garder Longhorn comme simple « alternative écartée » de
  0018).** Statu quo : le catalogue reste avec un trou (rien entre local-path et
  Ceph). Une topologie multi-nœuds sans datalake n'a aucune option résiliente
  simple — contraire à l'esprit « catalogue de profils »
  d'[ADR 0023](0023-plateforme-exemple-generique.md).
- **Réécrire / superseder 0018.** Lourd et trompeur : 0018 reste **vrai** pour
  le datalake (Ceph y demeure le bon choix). Le superseder suggérerait qu'on
  abandonne Ceph, ce qui n'est pas le cas. Un ADR qui **complète** dit mieux la
  réalité : deux décisions coexistent, chacune sur son périmètre.
- **Longhorn cantonné au bloc-seul strict (interdit dès qu'il y a un besoin
  objet).** Plus prudent, mais ampute le profil de tout un pan d'usage : une
  topologie peut vouloir Longhorn pour sa simplicité **et** un petit S3 à côté
  (SeaweedFS), comme le banc léger le fait déjà. On préfère le profil
  **généralisé** (composition assumée), en gardant le datalake comme la seule
  frontière intouchable de 0018.
