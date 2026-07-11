# 0109 — Persistance déclarative de l'instance (curseur de rétention des données)

## Statut

Proposed (2026-07-11). **ADR d'implémentation** du volet §2 de
[ADR 0107](0107-adaptativite-materielle-premisse-cultures.md) (adaptativité
matérielle — « Le cache des données s'adapte »), au même titre
qu'[ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md)
(isolation par identité) l'est du volet §4. Là où 0107 §2 énonce la doctrine («
sur la classe massive, tout ; sur une classe contrainte, une fenêtre glissante
bornée »), le présent ADR la rend **déclarative** : un curseur explicite dans la
topologie ([ADR 0056](0056-modele-declaratif-topologies.md) §5,
décrire/converger) porté par un nouvel axe du modèle
([ADR 0099](0099-axes-du-modele-topologie.md)), frère de l'axe `terrain`. Il ne
supersede aucun ADR ; il **nomme et généralise** des bornes de rétention déjà
présentes en pièces détachées (cache-flux CNPG
[ADR 0093](0093-cache-flux-cnpg.md), rétention Loki, `retentionPolicy` des
backups CNPG). Conception détaillée du volet données :
[audit du 2026-07-10](../audit/2026-07-10-doctrine-adaptativite-materielle.md)
§3 (volet B). Sous-tâche de l'épique d'implémentation de l'adaptativité
(cluster#627, volet B). **Conçu, non câblé** : cet ADR pose le contrat
déclaratif et nomme où chaque mode mordra ; le câblage par composant est
explicitement différé en issues (§Conséquences).

> **Dépendance.** L'axe `terrain` et la propriété `Topology.terrain` sur
> lesquels cet ADR calque `persistence` sont introduits par
> [ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md)
> (isolation par identité). L'implémentation de `persistence` (propriété
> `Topology.persistence`, `VALID_PERSISTENCE`) suppose ce socle.

## Contexte

Une instance conserve aujourd'hui **tout** par défaut, sans le déclarer nulle
part : les volumes (PVC) vivent, les buckets objet (RGW / SeaweedFS) sont
conservés, les historiques Postgres (CNPG) sont gardés. Les seules bornes de
rétention existantes sont **câblées localement, brique par brique** : Loki
(`retention_period` 168 h), backups CNPG (`retentionPolicy` 30 j), cache-flux
CNPG (TTL 24 h, [ADR 0093](0093-cache-flux-cnpg.md)). Il n'existe **aucun
endroit où l'exploitant déclare l'intention de rétention de son instance** —
c'est une propriété émergente de réglages épars, pas une décision lisible.

Or [ADR 0107](0107-adaptativite-materielle-premisse-cultures.md) §2 pose que le
volume caché **suit le matériel** : la classe massive stocke tout ; une classe
contrainte (bare-metal HDD-only, portable) garde une **fenêtre glissante
bornée** et évince le brut ancien. Cette doctrine est écrite mais **non
exprimable** : rien dans la topologie ne dit « cette instance stocke tout /
borne / ne conserve rien ». Le déployeur ne peut que régler les 12+ leviers à la
main, ce que 0107 identifie précisément comme l'anti-pattern à supprimer.

Le besoin est un **curseur d'intention, global à l'instance**, homogène aux
autres axes de la topologie (`terrain`, `exposition`, `storage.backend`), qui
déclare la politique de rétention **une fois** et fait dériver le reste — sur le
patron de l'axe `terrain` introduit par
[ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md).

## Décision

> **Persistance déclarée.** La topologie déclare la politique de rétention des
> **données applicatives** de l'instance via un axe unique `persistence.mode`, à
> trois crans — `full`, `bounded`, `ephemeral`. Ce curseur est **global à
> l'instance** (tout le stack en hérite) et **explicite** : il ne dérive pas
> silencieusement du terrain. Son défaut, quand la topologie est muette, est
> `full` — le comportement actuel, prudent : **on ne perd jamais de données par
> surprise**. Le curseur régit les **données applicatives**, **jamais** le plan
> de contrôle (etcd, quorum), régi séparément
> ([ADR 0013](0013-sauvegarde-donnees-applicatives.md)).

### 1. Le champ et ses trois crans

Un bloc racine dans la topologie, frère d'`exposition:` et de `storage:`,
valeurs en anglais court comme tout axe technique du modèle
([ADR 0039](0039-nomenclature-axes-catalogue.md)) :

```yaml
persistence:
  mode: full # full | bounded | ephemeral
```

| Mode            | Intention                    | Sémantique opposable                                                                                                                                                                                                                                                                |
| --------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`full`**      | « on stocke tout »           | Persistance complète : PVC durables, buckets conservés, historiques et backups gardés selon leur politique native. C'est le comportement **actuel**. Le curseur n'évince rien.                                                                                                      |
| **`bounded`**   | « un cache adapté »          | Rétention **bornée** : fenêtre glissante temporelle (`floor = watermark − TTL`, 0107 §2), pas un LRU générique ; les dérivés (agrégats, marques d'avancement, manifests) sont épinglés hors quota ; le brut lourd est le seul candidat à l'éviction, du plus ancien au plus récent. |
| **`ephemeral`** | « on stream sans conserver » | Jetable / pass-through : pas de volume durable (`emptyDir`), pas de bucket de rétention, flux non matérialisé, snapshots désarmés. L'état applicatif est reconstructible par re-provisionnement ; il meurt au recyclage du pod.                                                     |

`persistence` (le nom du parapluie) plutôt que `retention` (qui n'évoque que le
cran médian) : `full` = persistance totale, `ephemeral` = persistance nulle,
`bounded` = persistance bornée — les trois sont des **degrés de persistance**.

### 2. Où chaque mode mord (contrat opposable)

Un champ déclaratif sans effet est une **étiquette morte**, proscrite
([ADR 0056](0056-modele-declaratif-topologies.md) : décrire engage à converger).
Le contrat de cet axe est donc de **nommer, composant par composant, le point de
morsure** de chaque mode dans le graphe
([ADR 0096](0096-graphe-topologie-python-verifie-ansible.md)). Le câblage est
différé (§Conséquences) mais la cible est fixée ici :

| Composant du graphe                                                                                                             | `full`                  | `bounded`                                             | `ephemeral`                                                |
| ------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ----------------------------------------------------- | ---------------------------------------------------------- |
| **StorageClass / PVC bloc** ([ADR 0018](0018-rook-ceph-vs-longhorn.md), [ADR 0064](0064-longhorn-option-stockage-catalogue.md)) | `reclaimPolicy: Retain` | `Retain` + quota taille                               | `Delete` ou `emptyDir`                                     |
| **CNPG / Postgres** ([ADR 0024](0024-postgres-manage-cloudnative-pg.md))                                                        | PVC + Barman            | PVC + rétention WAL bornée                            | `emptyDir` — perte au recyclage (voulu sur classe jetable) |
| **Cache-flux CNPG** ([ADR 0093](0093-cache-flux-cnpg.md))                                                                       | conservé                | **déjà `bounded` natif (TTL 24 h)**                   | table volatile                                             |
| **Datalake / RGW / S3** ([ADR 0036](0036-backing-s3-unique-rgw.md))                                                             | buckets conservés       | lifecycle S3 (`Expiration`) + quota                   | pass-through, `preservePoolsOnDelete: false`               |
| **Loki (logs)** ([ADR 0016](0016-observabilite.md))                                                                             | rétention longue        | **`retention_period` borné + compactor (déjà 168 h)** | rétention minimale                                         |
| **Prometheus (métriques)** ([ADR 0016](0016-observabilite.md))                                                                  | `retention.time` long   | `retention.time` + `retention.size` bornés            | rétention courte                                           |
| **Snapshots / backups** ([ADR 0013](0013-sauvegarde-donnees-applicatives.md))                                                   | CronJob armé + `Retain` | armé, rétention courte                                | **désarmé**                                                |
| **Pipeline applicatif `atlas`** (Dagster — §3)                                                                                  | tout matérialisé        | fenêtre glissante par partition (env par classe)      | filtré à la volée, rien gardé                              |
| **etcd / plan de contrôle**                                                                                                     | —                       | —                                                     | **jamais touché** (garde-fou)                              |

Le mode `bounded` **existe déjà partiellement** (cache-flux CNPG, rétention
Loki, `retentionPolicy` CNPG) : cet ADR le **généralise en politique nommée** au
lieu de réglages dispersés — précisément l'objection « 12+ leviers à la main »
d'0107.

Les huit premières lignes du tableau mordent **côté `cluster`** (stockage,
observabilité, backups). La neuvième mord **côté `atlas`** (le code applicatif),
et engage l'**autre dépôt** — d'où une section dédiée.

### 3. Le versant `atlas` : le code applicatif réagit au mode

La persistance n'est pas qu'une affaire de stockage `cluster` : c'est aussi, et
surtout, le volet §3
d'[ADR 0107](0107-adaptativite-materielle-premisse-cultures.md) (« le code
applicatif s'adapte »). Un mode `bounded` ne se réalise pas seulement en
resserrant une StorageClass — il exige que le **pipeline `atlas`** (jobs
Dagster) _sache_ qu'il opère en fenêtre glissante : ne matérialiser que le
périmètre filtré, épingler les dérivés hors quota, armer l'évinceur du brut
ancien. Un mode `ephemeral` exige que le code accepte de **ne rien conserver**
(filtrer à la volée, ne pas écrire de table de rétention). Sans réaction
applicative, le curseur `cluster` borne le disque pendant que le code continue
de tout produire — incohérence.

**Le point de passage existe déjà.** `nestor` transporte l'intention de haut
niveau vers `atlas` par le faisceau de paramètres de run dérivé de la topologie
(`profile.derive_run_params`, attaché aux phases via les `-e` Ansible,
[`nestor/plan.py`]). C'est le **même canal** que celui par lequel le `profile`
compute atteint déjà le code applicatif. `persistence.mode` doit y **circuler
comme une variable sémantique de plus** (à côté du profil), `atlas` en
**dérivant** son comportement par une fonction pure — exactement le patron «
`nestor` transporte la classe, `atlas` dérive le profil » posé par 0107 §3, la
classe massive (`full`) reproduisant le comportement actuel à l'octet.

**Ce contrat traverse la frontière des dépôts** (`cluster` déclare et transporte
; `atlas` reçoit et réagit) : il excède le périmètre d'un ADR `cluster` et de sa
PR. Le présent ADR **fixe le point de passage** (`persistence.mode` circule par
`derive_run_params`) et **s'arrête à la frontière** ; la décision de la réaction
applicative — quels assets Dagster, quel nom d'env, comment `full` reste neutre
à l'octet — appartient à `atlas` et fera l'objet d'un **ADR `atlas` dédié**,
lui-même précédé d'un **plan demandé en issue** (§Conséquences), rattaché au
volet B de l'épique adaptativité. Si le canal `derive_run_params` gagne un
champ, le
[contrat d'interface `cluster`↔`atlas`](0043-contrat-interface-cluster-atlas.md)
et le manifeste de déclaration montant
([ADR 0094](0094-frontiere-deploiement-applicatif.md)) sont mis à jour dans la
PR `atlas` correspondante, pas ici.

### 4. Curseur explicite, pas dérivé — et responsabilité du déployeur

0107 §2 fait _dériver_ la rétention de la classe matérielle. Ici, la persistance
est **déclarée librement**, pas dérivée : un banc peut vouloir être persistant,
un parc cloud peut vouloir être jetable ; ce sont deux axes distincts. Le lien
au terrain est **pédagogique, pas normatif** :

| terrain \ mode                 |           `full`           |         `bounded`         |                    `ephemeral`                     |
| ------------------------------ | :------------------------: | :-----------------------: | :------------------------------------------------: |
| **`local`** (portable jetable) | possible (banc persistant) |           usuel           |                     démo pure                      |
| **`cloud`** (VM publique)      |           usuel            |           usuel           |                edge/démo sans état                 |
| **`baremetal`** (parc réel)    |         **usuel**          | classe HDD-only (0107 §2) | perte au recyclage — **au déployeur de l'assumer** |

Cette matrice **n'est pas une règle de validation**. Conformément à la posture
du dépôt (« le code **permet**, il ne décide pas à la place du déployeur » —
neutralité et RGPD, [ADR 0023](0023-plateforme-exemple-generique.md)), aucun
couple terrain × persistance n'est interdit. Déclarer `ephemeral` sur un
`baremetal` est **cohérent physiquement discutable** (perte d'état au recyclage
d'un parc qu'on ne re-provisionne pas) mais relève de la **responsabilité de
l'exploitant**, pas d'un refus du modèle. La validation vérifie **uniquement**
l'appartenance à l'énuméré (`full` / `bounded` / `ephemeral`) ; le reste est un
choix éclairé, documenté par cette matrice.

### 5. Défaut fail-safe et lecture tolérante

Le défaut, topologie muette, est **`full`** — le plancher de sûreté. Aujourd'hui
il n'existe aucun champ de persistance et le comportement implicite est « stocke
tout » ; une topologie historique sans bloc `persistence:` ne doit donc **pas**
devenir bornée ou jetable par surprise (perte silencieuse). Même logique que le
défaut `baremetal` de l'axe `terrain`
([ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md)) : le
défaut sûr est le comportement **prudent**, jamais le jetable. La lecture est
**tolérante** (valeur absente ou hors-énuméré → `full`, sans exception au
parsing qui ignore déjà les clés inconnues) ; la validation stricte (qui lève
sur un mode inconnu) vit au point d'entrée `init`.

## Conséquences

- **Un axe de plus, homogène.** `persistence.mode` rejoint `terrain`,
  `exposition.mode`, `storage.backend` comme axe déclaratif de l'instance
  ([ADR 0099](0099-axes-du-modele-topologie.md)) ; il se lit par une propriété
  dérivée `Topology.persistence`, calquée sur `Topology.terrain`.
  L'implémentation v1 se limite à **parser / valider / exposer** ce champ +
  poser un exemple commenté dans le catalogue générique.
- **Contrat déclaratif, câblage différé (issues).** Cet ADR ne recâble **aucun**
  composant. Chaque cellule non triviale du tableau §2 devient une **issue**
  rattachée au volet B (cluster#627) : StorageClass `reclaimPolicy`/quota par
  mode ; `retention_period` Loki + compactor piloté par le mode ;
  `retentionPolicy` et WAL CNPG ; lifecycle et quotas des buckets RGW/S3 ;
  désarmement des VolumeSnapshots
  ([ADR 0013](0013-sauvegarde-donnees-applicatives.md)) en `ephemeral` ; fenêtre
  glissante du pipeline (env par classe, overlay Kustomize — audit §3 B.1) ;
  sous-paramètres de `bounded` (`ttl`, `max_size`) dans le bloc `persistence:`.
  La frontière est explicite, façon [ADR 0093](0093-cache-flux-cnpg.md) (poser
  d'abord, câbler ensuite).
- **Le versant `atlas` : un plan, puis un ADR `atlas` (issue #627).** La
  réaction du code applicatif au mode (§3) traverse la frontière des dépôts et
  excède cet ADR `cluster`. Elle appelle sa **propre décision côté `atlas`** —
  un ADR `atlas` dédié (quels assets Dagster réagissent à `bounded`/`ephemeral`,
  quel nom d'env transporté par `derive_run_params`, comment `full` reste neutre
  à l'octet, et l'éventuelle évolution du contrat d'interface
  [ADR 0043](0043-contrat-interface-cluster-atlas.md) / du manifeste
  [ADR 0094](0094-frontiere-deploiement-applicatif.md)). Cet ADR `atlas` sera
  **précédé d'un plan**, demandé par une **issue rattachée à l'épique
  d'adaptativité (cluster#627, volet B)** — préalable à tout câblage `atlas`,
  pour ne pas figer un contrat d'interface au jugé.
- **Zéro régression sur la classe massive.** Le défaut `full` reproduit le
  comportement actuel à l'octet ; l'évinceur ne s'arme jamais en `full`
  (garde-fou « massif = illimité » de l'audit §3.1). Une instance existante non
  modifiée se comporte à l'identique.
- **Le déployeur décide, le code permet.** Aucune combinaison n'est refusée au
  nom d'une cohérence présumée ; la matrice terrain × persistance est
  documentaire. Cela préserve la neutralité
  ([ADR 0023](0023-plateforme-exemple-generique.md)) et évite une sur-conception
  de garde (un seul contrôle : l'appartenance à l'énuméré).
- **`bounded` et reproductibilité.** Le mode borné est défini comme **fenêtre
  glissante temporelle** (déterministe à horloge fixée), non comme LRU vif ; les
  preuves e2e du banc éprouvent la fenêtre, pas un cache vivant — condition de
  reproductibilité ([ADR 0052](0052-reproductibilite-des-resultats.md)).

## Alternatives écartées

- **Dériver la persistance du terrain** (zéro champ, la rétention sort de la
  classe). Écarté : retire à l'exploitant le curseur explicite demandé et couple
  deux axes indépendants (un banc peut être persistant, un cloud jetable). Le
  défaut fail-safe suffit à garder la prudence sans figer la dérivation.
- **Un booléen `persistent: true|false`.** Écarté : il écrase le cran central
  `bounded`, qui est pourtant le cœur d'0107 §2 (l'adaptativité _est_ la fenêtre
  bornée) et existe déjà (CNPG 24 h, Loki 168 h). Le « tout ou rien » interdit
  d'exprimer « je garde l'utile » sur une classe contrainte.
- **Un réglage de rétention par composant** (`loki.retention`,
  `cnpg.retention`…) dès la v1. Écarté : c'est l'anti-pattern « 12+ leviers à la
  main » qu'0107 proscrit ; multiplie la surface de validation et casse le
  principe « une intention déclarée fait dériver le reste ». Le grain fin reste
  possible **plus tard** comme raffinement (overrides sous le même bloc
  `persistence:`), sous le plancher global.
- **Interdire `(baremetal, ephemeral)` à la validation.** Écarté sur décision :
  la cohérence physique du couple relève de la responsabilité du déployeur, pas
  d'un refus du modèle (le code permet). L'ADR documente le risque (perte au
  recyclage) sans le bloquer.
- **Nommer `ephemeral` `stream` ou `flux`.** Écarté : cela nomme le _mécanisme_
  (le flux) et non la _politique_ (l'absence de rétention) — la même erreur que
  l'ancien `target_kind: lima` qui nommait l'outil, retirée par
  [ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md).
  `ephemeral` est le terme canonique K8s (`emptyDir`, ephemeral storage).
