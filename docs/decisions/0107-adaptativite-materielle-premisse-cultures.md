# 0107 — Adaptativité matérielle (prémisse des cultures d'ingénierie)

## Statut

Proposed (2026-07-10). **Principe-chapeau**, au même rang que
[ADR 0052](0052-reproductibilite-des-resultats.md) (reproductibilité) et
[ADR 0062](0062-cultures-ingenierie.md) (cultures d'ingénierie), qu'il **précède
logiquement** : il énonce la prémisse sous laquelle les cultures revendiquées
par 0062 s'exercent. Il ne crée aucune pratique et ne supersede aucun ADR — il
**pose un cadre** que des ADR d'implémentation (à venir) déclineront. Conforme à
la posture anti-sur-revendication
d'[ADR 0061](0061-posture-adoption-bonnes-pratiques.md) : revendiqué **en
construction**, pas « en place ». Conception détaillée :
[audit du 2026-07-10](../audit/2026-07-10-doctrine-adaptativite-materielle.md).

## Contexte

L'[ADR 0062](0062-cultures-ingenierie.md) nomme les cultures d'ingénierie que le
dépôt revendique — GitOps, DataOps, DevSecOps, IaC en place ; Platform
Engineering et MLOps en construction. Mais ces cultures ont, jusqu'ici, été
pensées **pour une seule cible** : la topologie prod massive (4 nœuds
bare-metal, kubeadm, Ceph). Les autres topologies du catalogue
([ADR 0023](0023-plateforme-exemple-generique.md)) sont traitées comme des
**variantes dégradées** de cette cible — un « banc » qui simule la prod, à
fidélité près.

Or le projet vise plusieurs **classes de matériel réellement distinctes**, pas
un gradient de fidélité :

- un **portable** (dev local, Lima) ;
- un **bare-metal à disques lents** (HDD-only) où `etcd` est inutilisable
  (latence `fsync`) et où le stockage massif d'OpenAlex/GDELT est impossible ;
- **quatre bare-metal massifs** (l'actuel dirqual).

Ces classes n'ont pas les mêmes **contraintes physiques** : la distribution k8s
viable, le backend de stockage, le volume de données cachable et les ressources
de calcul en dépendent. Traiter les petites classes comme des « bancs » masque
cette réalité et **fige les décisions à une seule valeur** : `kubeadm` (ADR
0035), `Ceph` (ADR 0018), « tout stocker », le profil compute de dirqual.
Chacune est un choix **correct pour la classe massive**, mais **erroné** pour
une autre.

Le symptôme concret : sur un bare-metal HDD-only, la pile actuelle **ne démarre
même pas** (etcd instable), et le pipeline **sature le disque** (1,27 Tio de
works bruts). Ce n'est pas un défaut d'implémentation — c'est l'absence d'un
**principe** disant que l'infrastructure, les données et le code doivent
**s'adapter au matériel**, et non présumer la classe massive.

## Décision

> **Prémisse d'adaptativité matérielle.** La mise à disposition d'une
> infrastructure DataOps+MLOps s'**adapte à la classe de matériel**. Une seule
> **classe** déclarée fait dériver, de façon cohérente, l'infrastructure (§1),
> le cache des données (§2) et le comportement du code applicatif (§3). Il n'y a
> plus de « prod » ni de « banc » — seulement des **instances** sur des
> **classes**, isolées par leur **identité** (§4). Les cultures revendiquées par
> [ADR 0062](0062-cultures-ingenierie.md) s'exercent **sous** cette prémisse :
> la classe est l'entrée, la culture est la manière.

### 1. L'infrastructure s'adapte (IaC, Platform Engineering)

La classe dérive le triplet **distribution × stockage bloc × stockage objet**.
La distribution n'est plus figée à `kubeadm` : une classe HDD-only impose `k3s`
(datastore `kine`/SQLite, sans `etcd`) ; la classe massive garde `kubeadm`. Le
backend bloc va de `local-path` (portable) à `Longhorn` (HDD) à `Ceph` (massif)
; l'objet, de `SeaweedFS` (léger) à `RGW` Ceph (massif). `nestor` reste
**orchestrateur** ([ADR 0056](0056-modele-declaratif-topologies.md) §7) : il
**délègue** le provisionnement à l'outil-propriétaire (`limactl`, OpenTofu
[ADR 0032](0032-opentofu-provisioning-cloud.md), ou rien pour un bare-metal
existant) et **orchestre** Ansible pour l'installation.

### 2. Le cache des données s'adapte (DataOps)

Le volume caché suit le stockage. Sur la classe massive : tout OpenAlex + tout
GDELT. Sur une classe contrainte : une **fenêtre glissante bornée** — on ne
garde que ce qui est utile (le périmètre filtré, l'agrégat) et on évince le brut
ancien. Concrètement : filtrer OpenAlex à la volée pour ne matérialiser que le
périmètre (pas les 1,27 Tio bruts) ; garder GDELT en **agrégats mensuels
immuables** plutôt que le flux complet. Le résultat courant reste **exact** ; ce
qui se dégrade est la **capacité** (re-filtrer un autre périmètre sans
re-télécharger), pas l'exactitude.

### 3. Le code applicatif s'adapte

Le code (`atlas`) dérive un **profil** de la classe : ressources de calcul
(mémoire, threads, tailles de lot), et **dégradation propre** des composants
optionnels (une instance sans `pgvector`/MLflow produit un résultat correct
quoique réduit, jamais un crash — en généralisant le patron `no-op` déjà en
place). Le code reste **générique**
([ADR 0023](0023-plateforme-exemple-generique.md)) : la classe est un
**paramètre d'instance**, jamais une branche par déployeur. `nestor` transporte
la **classe** (une variable sémantique) ; `atlas` **dérive** le profil (fonction
pure), la classe massive reproduisant les défauts actuels à l'octet — continuité
totale.

### 4. Isolation par identité (remplace prod/bench)

Puisqu'il n'y a plus « la prod » et « le banc » mais des instances sur des
classes, le garde-fou de sécurité change de nature : il ne repose plus sur la
**catégorie** (`target_kind`) mais sur l'**identité d'instance**. On n'agit que
sur l'instance explicitement nommée (le `stack_id` — nom de fichier de
topologie, « identité système, source unique »,
[ADR 0102](0102-catalogue-topologies-v2-topo-source-unique.md)) et son
kubeconfig dédié, jamais sur une cible implicite. Cette garde est **aussi sûre**
que la précédente — dont elle corrige la faille documentée (« un `next dataops`
visant le banc a reconfiguré containerd sur les nœuds prod ») en supprimant
toute cible implicite.

## Conséquences

- **Cap culturel clarifié.** Les cultures
  d'[ADR 0062](0062-cultures-ingenierie.md) se lisent désormais **sous** cette
  prémisse. Platform Engineering en particulier gagne son sens plein : le
  catalogue de topologies n'est pas une collection de variantes, c'est un
  **ensemble de classes matérielles adaptatives**.
- **Décisions dé-figées.** Trois décisions structurantes cessent d'être des
  invariants et deviennent **fonction de la classe** : la distribution
  (`kubeadm`-only, [ADR 0035](0035-strategie-bancs-fidelite-vitesse.md)), le
  backend bloc (Ceph, [ADR 0018](0018-rook-ceph-vs-longhorn.md)), la politique
  de cache. Ces ADR ne sont pas superseded : ils décrivent le **choix de la
  classe massive**, désormais une valeur parmi d'autres.
- **La « fidélité banc↔prod » perd son objet.** Elle motivait `kubeadm`-only ;
  sans prod/bench, chaque classe se valide **chez elle**, sur son propre
  matériel — ce qui est plus honnête (un portable ne « prouve » pas un
  bare-metal massif).
- **Honnêteté sur l'état.** Cette prémisse est **conçue, non implémentée** (hors
  quelques amorces déjà présentes : catalogue 4 axes
  [ADR 0039](0039-nomenclature-axes-catalogue.md), `SeaweedFS`/`local-path` dans
  la matrice, leviers `env` du code, patron `no-op`, `stack_id`). Revendiquée
  **en construction**, elle oriente les prochains ADR sans les figer —
  exactement le registre qu'[ADR 0062](0062-cultures-ingenierie.md) réserve à
  Platform Engineering.
- **Prix à payer.** Supporter plusieurs distributions (`kubeadm` + `k3s`) et
  plusieurs backends a un coût de maintenance réel ; il ne se paie qu'au fil des
  besoins matériels réels (on n'implémente `k3s`/OVH que le jour où la machine
  existe). Le refactor « classe massive = comportement actuel à l'octet »
  garantit **zéro régression** sur dirqual pendant la transition.

## Alternatives écartées

- **Laisser l'adaptativité implicite** (chaque déployeur bricole ses `env`).
  Écarté : c'est l'état actuel — 12+ leviers réglés à la main sans cohérence, et
  aucune classe HDD ne démarre. Sans prémisse nommée, rien ne garantit qu'un
  nouveau composant sera pensé adaptatif.
- **En faire une culture d'ingénierie de plus dans
  [ADR 0062](0062-cultures-ingenierie.md).** Écarté : l'adaptativité n'est pas
  une culture au même titre que GitOps ou DataOps — elle les **conditionne
  toutes**. Sa place est **au-dessus**, en prémisse, pas dans la liste.
- **Un gradient de fidélité** (les petites classes = bancs simulant la prod).
  Écarté : c'est le cadre actuel, précisément celui qui fige les décisions à la
  classe massive. Une classe HDD n'est pas une « prod dégradée » — c'est une
  cible légitime avec ses propres contraintes physiques.
