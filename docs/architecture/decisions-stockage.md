# Décisions — Stockage (Ceph, réplication, sauvegarde)

Cette page est une **vue thématique** au-dessus des ADR (Architecture Decision
Records) immuables et datés du dépôt : elle ne les remplace pas, elle les
**agrège et raconte** pour donner une carte de lecture du domaine stockage. Les
ADR restent la **source de vérité** (chacun horodaté ; cette page renvoie vers
eux par lien). Si un point semble en tension entre les deux, c'est l'ADR daté
qui fait foi.

## Le socle : Rook-Ceph plutôt que Longhorn

Le cluster est **hyperconvergé** (calcul + stockage sur les 4 mêmes nœuds) et
sert de **datalake de l'organisation** : environ **264 TiB brut**, avec un
besoin de stockage **bloc** (PVC RBD) **et objet** (S3 pour les datasets), sur
HDD avec `block.db` NVMe.

C'est sur ce terrain que se joue le choix du socle. L'alternative naturelle dans
l'écosystème Kubernetes est **Longhorn** (bloc distribué, plus léger), mais
[ADR 0018](../decisions/0018-rook-ceph-vs-longhorn.md) retient **Rook-Ceph** :

- **Bloc + objet + fichier dans une seule plateforme.** Le datalake a besoin de
  **S3** (RGW) pour les datasets, de **bloc** (RBD) pour les workloads, et
  potentiellement de **CephFS** (RWX). Longhorn ne fait que du bloc — il
  faudrait une seconde solution pour l'objet ; Ceph unifie les trois.
- **Échelle et topologie disque.** Ceph gère nativement des dizaines d'OSDs HDD
  par nœud avec `block.db` sur NVMe et l'erasure coding pour le datalake.
- **`failureDomain: host` + réplicat ×3** collent au modèle 4 nœuds.

Le coût assumé est réel : **complexité opérationnelle** nettement supérieure à
Longhorn (mon/mgr/osd/rgw, pools, CRUSH, rééquilibrage) et **empreinte
ressources** plus élevée — jugée acceptable sur des nœuds à 251 GiB de RAM.
L'ADR note qu'il faudrait **revoir ce choix** si le besoin objet (S3)
disparaissait, ou si l'échelle se réduisait drastiquement.

## Trois profils de stockage : local-path, Longhorn, Ceph

Le choix d'[ADR 0018](../decisions/0018-rook-ceph-vs-longhorn.md) vaut **pour le
datalake** ; il ne dit pas que Ceph est le seul stockage du catalogue. En
pratique, le dépôt — fidèle à sa nature de **catalogue de topologies**
([ADR 0023](../decisions/0023-plateforme-exemple-generique.md)) — **propose
trois profils** de stockage persistant, dont **un seul est activé** par
déploiement. [ADR 0064](../decisions/0064-longhorn-option-stockage-catalogue.md)
acte **Longhorn** comme troisième profil, comblant le trou entre le local-path
(zéro résilience) et Ceph (résilient mais lourd).

| Profil       | Brique                 | Nœuds | Résilience bloc | Objet S3                        | Complexité | Créneau                                      |
| ------------ | ---------------------- | ----- | --------------- | ------------------------------- | ---------- | -------------------------------------------- |
| `local-path` | local-path-provisioner | 1+    | **aucune**      | non                             | minimale   | jetable, mono-nœud, dev, bancs légers        |
| `longhorn`   | Longhorn               | 2-3+  | ×2/×3 répliqué  | **non** (2ᵉ solution si besoin) | légère     | bloc répliqué multi-nœuds, **sans datalake** |
| `ceph`       | Rook-Ceph              | 4+    | ×3 / EC 2+1     | **oui** (RGW intégré)           | élevée     | prod datalake, bloc + objet + fichier unifié |

**local-path** — un Deployment + une StorageClass (`WaitForFirstConsumer`,
`Delete`). Complexité quasi nulle, empreinte minime (c'est ce qui rend le profil
`light` tenable : 8 GiB RAM / 20 GiB disque par VM contre 12/40 en Ceph). En
contrepartie : **aucune résilience** — le PV est épinglé à un nœud, dont la
perte emporte les données ; pas d'objet ni de RWX ; pas de snapshots CSI. Pour
tout ce qui est éphémère ou ré-montable ; jamais pour de la donnée à conserver.

**Longhorn** — bloc distribué répliqué synchrone (×2/×3) piloté par un operator.
Plus simple à opérer que Ceph (pas de pools/CRUSH/rééquilibrage manuel), plus
résilient que local-path (survit à la perte d'un nœud). Son angle mort est
l'objet : **il ne fait que du bloc**. C'est précisément ce qui l'a écarté du
datalake ([ADR 0018](../decisions/0018-rook-ceph-vs-longhorn.md)), où le S3 est
requis ; mais c'est sans objet pour les topologies **sans datalake**. Si l'une
d'elles a malgré tout besoin d'un petit S3 (Loki, backups CNPG), elle l'obtient
par une **2ᵉ brique légère** — SeaweedFS/MinIO — exactement comme le profil
`local-path` le fait déjà
([ADR 0036](../decisions/0036-backing-s3-unique-rgw.md)). Le couple **Longhorn
(bloc) + SeaweedFS (objet)** est l'alternative **composée** au **Ceph unifié** :
deux briques simples contre une brique riche.

**Ceph** — bloc + objet + fichier dans une seule plateforme, résilience graduée
par criticité (×3 sans coupure pour le bloc critique, EC 2+1 économique pour le
datalake ré-ingestible), échelle disque native (dizaines d'OSDs/nœud, block.db
NVMe). En contrepartie : complexité opérationnelle élevée, empreinte ressources,
plancher de 4 nœuds. Reste le **socle obligatoire du datalake** — Longhorn n'y
est pas un candidat (échelle, objet intégré, EC), et 0064 **n'autorise pas** à
l'y remplacer.

> **La ligne de partage du catalogue.** local-path pour ce qui est **jetable** ;
> Longhorn dès qu'il faut du **bloc qui survit à un nœud sans la lourdeur de
> Ceph** ; Ceph dès qu'il faut **du durable haute capacité ou du S3 intégré**
> (le datalake). Le choix se fait **par topologie** —
> [ADR 0064](../decisions/0064-longhorn-option-stockage-catalogue.md) rouvre,
> pour les topologies bloc-seul, le débat « unifié vs composé » que
> [ADR 0018](../decisions/0018-rook-ceph-vs-longhorn.md) avait tranché pour le
> seul datalake. Longhorn est aujourd'hui une option **actée mais non encore
> implémentée** : ADR `Proposed`, mise en œuvre suivie par
> [`plan-stockage-longhorn.md`](../plans/plan-stockage-longhorn.md) (état
> `Brouillon` tant que l'ADR n'est pas `Accepted` —
> [ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) §6).

## Deux régimes de redondance : ×3 pour le bloc, EC 2+1 pour le datalake

Ceph propose deux modes de redondance, et le dépôt les répartit volontairement
selon la criticité de la donnée. Le point dur commun est la **topologie à 4
hôtes** avec `failureDomain: host`.

### Réplication ×3 pour les workloads bloc

[ADR 0001](../decisions/0001-replication-x3-pour-workloads-bloc.md) fixe la
règle : tous les workloads **bloc** utilisent `rook-ceph-block-replicated`
(réplication ×3), qui est la **StorageClass par défaut** du cluster (annotation
`storageclass.kubernetes.io/is-default-class: "true"`).

La raison est la **tolérance de panne sans interruption** lors de la maintenance
d'un nœud (drain + reboot). Un pool répliqué ×3 a `min_size = 2` par défaut : il
tolère la perte d'**un hôte** sans bloquer les I/O. À l'inverse, l'erasure
coding 2+1 sur 4 hôtes porte un **piège `min_size`** : par défaut
`min_size = k + 1 = 3`, donc la perte d'**un seul hôte** fait passer le pool
sous `min_size` et **bloque toutes les I/O** jusqu'au remplacement (pas de perte
de données, mais interruption applicative). Inacceptable pour le registry,
MySQL, RStudio ou le dashboard.

Le coût assumé est le **doublement du stockage** par rapport à l'EC : ~88 TiB
utiles (×3) contre ~176 TiB (×1,5) sur les 264 TiB brut — acceptable car les
volumes applicatifs sont modestes (1 Ti registry, 20 Gi MySQL/WP, 1 Ti RStudio).

### Erasure coding 2+1 réservé au datalake

[ADR 0004](../decisions/0004-erasure-coding-2plus1-datalake.md) prend la
décision symétrique pour le datalake, qui stocke des sources **ré-ingestibles**
(p. ex. corpus ouverts, API publiques) sur Ceph RGW. Ses caractéristiques métier
justifient un autre arbitrage :

- **Données ré-ingestibles** depuis les sources upstream (la perte coûte un
  temps de ré-ingestion, pas une information unique).
- **Disponibilité non-critique** : un blocage I/O temporaire pendant la
  maintenance d'un nœud est acceptable.
- **Coût stockage important** au regard de la valeur de chaque octet.

Le data pool du `CephObjectStore datalake` est donc en **EC 2+1**
(`dataChunks: 2, codingChunks: 1`). Sur 4 hôtes, c'est le maximum atteignable :
`k + m = 3` laisse 1 hôte de marge pour `failureDomain: host` ; EC 2+2 (= 4)
saturerait la topologie et ne tolérerait plus aucune maintenance. Le bénéfice
est un **coût stockage divisé par 2** (×1,5 vs ×3).

Deux décisions de durcissement encadrent ce choix, cohérentes entre les deux ADR
: le **pool de métadonnées** du CephObjectStore (et ceux des classes bloc EC)
est en réplication `size: 3 + requireSafeReplicaSize: true`, car Ceph
déconseille fortement `size: 2` pour des métadonnées. Et les classes bloc EC
`rook-ceph-block-ec-delete` / `rook-ceph-block-ec-retain` restent disponibles
pour des usages tolérants (archives), mais **aucun workload critique** ne s'y
rattache.

## Le SPOF assumé : un `metadataDevice` NVMe unique par nœud

Le découpage data/métadonnées de Ceph repose, ici, sur le matériel. Chaque nœud
dispose de **12 HDD SAS de 5,5 TiB** (les OSDs) et d'**1 NVMe de 2,9 TiB**
destiné au `block.db` (métadonnées BlueStore + WAL). Le `block.db` sur NVMe
accélère drastiquement les opérations métadonnées (small writes, lookup d'objet,
journal BlueStore) ; la doc Ceph suggère ~4 % de la capacité data en block.db,
soit 12 × 5,5 TiB × 4 % ≈ **2,6 TiB par nœud** — qui tiennent sur les 2,9 TiB du
NVMe.

[ADR 0008](../decisions/0008-metadatadevice-nvme-spof-par-noeud.md) configure
donc `metadataDevice: nvme1n1` sur tous les nœuds : l'opérateur Rook découpe le
NVMe en **12 partitions, une par OSD HDD**. C'est efficace, mais cela crée un
**SPOF par nœud** revendiqué comme tel.

> **Encadré honnêteté — SPOF NVMe et angles morts assumés**
>
> - **Un seul NVMe par nœud, partagé par les 12 OSDs** : si ce NVMe meurt, les
>   **12 OSDs du nœud tombent simultanément**. La perte est **binaire**, sans
>   dégradation progressive.
> - C'est, du point de vue Ceph, **équivalent à la perte du nœud entier**. Or
>   `failureDomain: host` est déjà notre modèle de panne nominal : la
>   réplication ×3 l'absorbe (tolère 1 hôte perdu) et l'EC 2+1 aussi (un hôte =
>   1 chunk perdu sur 3). Le NVMe-SPOF ne fait que **matérialiser** ce scénario
>   via un composant différent.
> - La probabilité d'une panne simultanée de 2 NVMe sur 2 nœuds distincts reste
>   très faible (NVMe SLC enterprise, MTBF élevé). À surveiller via l'état SMART
>   (`smartctl -A /dev/nvme1n1`) ; en cas d'erreurs, drainer le nœud, remplacer
>   le NVMe, recréer les OSDs (Rook le fait à la reconnexion).
> - L'alternative — répartir le block.db sur plusieurs NVMe — est écartée car
>   elle exigerait du matériel supplémentaire, non justifié pour un cluster de
>   recherche.

Ce SPOF est donc le miroir matériel du choix de redondance : c'est précisément
parce que la perte d'un hôte est déjà le scénario de panne couvert (×3 et EC
2+1) que le NVMe unique reste acceptable.

## Ce que la réplication ne protège pas : la sauvegarde applicative

La réplication et l'erasure coding protègent du **crash matériel** (perte d'un
disque, d'un nœud). Elles ne protègent **pas** de la suppression accidentelle,
de la corruption logique applicative ou d'un ransomware.
[ADR 0013](../decisions/0013-sauvegarde-donnees-applicatives.md) part de ce
constat : avant lui, seul **etcd** est sauvegardé ; les **données applicatives**
(PVC bloc MySQL/WordPress, registry, RStudio ; buckets S3 du datalake) ne le
sont pas. Aggravant : la StorageClass bloc par défaut est en
`reclaimPolicy: Delete` et le datalake en `preservePoolsOnDelete: false` — un
`delete` de PVC ou de `CephObjectStore` est aujourd'hui **irréversible**.

La décision : **sauvegarde par VolumeSnapshots CSI natifs** (Ceph-CSI),
programmés.

- **VolumeSnapshotClass** RBD et CephFS en `deletionPolicy: Retain`, pour que la
  suppression d'un `VolumeSnapshot` ne détruise pas le snapshot Ceph
  sous-jacent.
- **Snapshots programmés** par un `CronJob` Kubernetes qui horodate les
  `VolumeSnapshot` des PVC critiques et applique une **rétention** (les N
  derniers, comme etcd). **RPO cible : 24 h** (snapshot quotidien), ajustable
  par PVC.
- **`reclaimPolicy: Retain`** sur les StorageClasses précieuses, pour qu'un
  `delete pvc` libère la réclamation mais **conserve** le volume Ceph
  (récupérable) ; les volumes jetables restent en `Delete`.

Côté **RPO/RTO** : RPO de 24 h en nominal (réductible par PVC) ; RTO de quelques
minutes (restaurer = créer un nouveau PVC `dataSource` depuis un
`VolumeSnapshot`). etcd reste couvert séparément (sauvegarde horaire).

L'honnêteté de l'ADR mérite d'être reportée ici, car ses limites sont assumées :

- **In-cluster** : les VolumeSnapshots vivent dans le **même cluster Ceph** que
  les données ; ils ne protègent **pas** d'une perte totale du cluster
  (incendie, destruction des 4 nœuds). Un vrai off-site est tracé comme
  évolution.
- **Buckets S3 datalake** : non couverts par les VolumeSnapshots (qui visent les
  PVC bloc/CephFS). Le datalake reste **ré-ingestible depuis l'upstream** —
  hypothèse déjà posée pour `preservePoolsOnDelete: false`.
- **Cohérence applicative** : un snapshot de volume est _crash-consistent_, pas
  _application-consistent_ ; pour MySQL, un `mysqldump` logique complémentaire
  serait plus sûr (noté comme amélioration).

## Vue d'ensemble : un fil cohérent

Les décisions forment une chaîne logique. Au niveau du **catalogue**, trois
profils de stockage coexistent — local-path (jetable), Longhorn (bloc répliqué
simple, [0064](../decisions/0064-longhorn-option-stockage-catalogue.md)) et Ceph
(unifié) — un seul activé par topologie. Au niveau du **socle datalake**,
Rook-Ceph est choisi comme socle unifié
([0018](../decisions/0018-rook-ceph-vs-longhorn.md), que 0064 complète sans
l'invalider) ; sa redondance est réglée par criticité — ×3 sans interruption
pour les workloads bloc
([0001](../decisions/0001-replication-x3-pour-workloads-bloc.md)) et EC 2+1
économique pour le datalake ré-ingestible
([0004](../decisions/0004-erasure-coding-2plus1-datalake.md)) ; le `block.db`
NVMe unique par nœud
([0008](../decisions/0008-metadatadevice-nvme-spof-par-noeud.md)) crée un SPOF
que ces redondances absorbent déjà ; et la sauvegarde par VolumeSnapshots
([0013](../decisions/0013-sauvegarde-donnees-applicatives.md)) couvre les angles
morts (suppression, corruption) que la redondance ne traite pas. Le fil rouge du
socle Ceph : `failureDomain: host` et le modèle de panne « perte d'un hôte » sur
4 nœuds.

## Voir aussi

- [Vue — Exposition réseau](../architecture/exposition-reseau.md) (réseau /
  exposition).
- [Vue — Validation sur banc](../architecture/validation-banc.md) (tests de banc
  ; la validation des VolumeSnapshots y est rattachée, dans l'esprit du scénario
  etcd-restore).
