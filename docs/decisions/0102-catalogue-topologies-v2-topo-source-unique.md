# 0102 — Catalogue de topologies v2 : la topologie, source unique (nommage, kubeconfig, provisioning)

## Statut

Proposed (2026-07-01)

Amende [0023](0023-plateforme-exemple-generique.md) (patron `*.example` /
exception `banc.yaml`), [0090](0090-nestor-pilote-la-prod.md) (emplacement du
kubeconfig prod) et prolonge [0056](0056-modele-declaratif-topologie.md) (la
topo est la source de vérité) /
[0097](0097-moteur-chemin-python-bash-artefacts.md) (Python décide, bash rend) /
[0053](0053-isolation-multi-cible-banc-prod.md) (garde d'isolation banc/prod).
Valeurs génériques ([0023](0023-plateforme-exemple-generique.md)).

## Contexte

Trois frictions, toutes des **entorses au même principe** — « la topologie est
la source de vérité unique » — se sont accumulées et sont apparues ensemble en
montant un banc Ceph (2026-07-01) :

1. **Nommage du catalogue incohérent** : les modèles sont versionnés en
   `*.example.yaml` (patron ADR 0023), SAUF `banc.yaml` — une **exception**
   versionnée sans suffixe. Deux patrons pour la même chose (un modèle générique
   public).

2. **kubeconfig dédoublé banc/prod** : la décision « quel fichier kubeconfig
   pour cette stack ? » est éclatée sur **~9 sites** (3 réimplémentations de la
   priorité, 4 branchements `if target_kind == "bench"`, 2 fetchers parallèles
   bash+Python). Le banc vit dans `bench/lima/.work/kubeconfig` (codé en dur),
   la prod dans `~/.kube/<stack>.config` (champ `kubeconfig:` de la topo).
   Contre-intuitif : un même outil gère le kubeconfig de deux façons selon la
   cible.

3. **Provisioning piloté par l'ENV, pas par la topo** : la création des disques
   Ceph est gatée par `WITH_CEPH=1` (variable bash), jamais posée par nestor →
   une topo `backend: ceph` avec `nodes[].disks` monte des VM **sans disques**
   (constaté au banc). Et les ressources VM sont appliquées **globalement**
   (celles du control-plane pour toutes les VM), alors que `nodes[].resources`
   existe dans le modèle.

Ces trois points ont la même racine : **des mécanismes parallèles (suffixe
spécial, chemin par terrain, variable d'env) doublent ou contredisent ce que la
topologie déclare déjà.**

## Décision

**La topologie est la source de vérité unique — pour le nommage, le kubeconfig
ET le provisioning. On supprime les mécanismes parallèles.** Trois volets.

### Volet A — Nommage uniforme du catalogue

Tout modèle générique versionné porte le suffixe **`.example.yaml`**. Fin de
l'exception `banc.yaml` : il devient `banc.example.yaml` (versionné) ; le
`banc.yaml` local (surcharge de l'opérateur) redevient gitignoré comme toute
topo réelle. Un seul patron :

- `topologies/*.example.yaml` → **versionné** (modèle générique, ADR 0023).
- `topologies/*.yaml` (sans `.example`) → **gitignoré** (topo réelle/locale).

`ceph.example.yaml` (banc Ceph 3-VM générique) est ajouté — le catalogue gagne
un exemple par cas d'usage (mono-nœud local-path, Ceph 3-VM, prod, HA…). Un
`topology.yaml` racine (symlink d'activation) reste non versionné.

### Volet B — kubeconfig unifié, nommé par la stack, emplacement unique

Un kubeconfig **par stack**, **nommé `<stack>.config`**, dans un répertoire
racine unique gitignoré `.kubeconfigs/` — **identique pour banc et prod**. Le
banc et la prod cessent d'être deux catégories de chemin ; ce sont deux façons
de **remplir** le même emplacement.

- **Résolution UNIQUE** : une seule fonction
  `kubeconfig_path(stack, *, env_kubeconfig, declared)` → (1) `KUBECONFIG`
  exporté [ADR 0065] ; (2) `declared` = override rare (chemin custom) ; (3)
  `<racine>/.kubeconfigs/<stack>.config`. Les 3 réimplémentations
  (`_bench_kubeconfig`, `resolve_kubeconfig`,
  `_resolve_prod_kubeconfig_into_env`) fusionnent. Les 4 branchements
  `if target_kind == "bench"` s'évaporent (les deux terrains appellent la même
  fonction).
- **Écriture UNIQUE** : banc (généré par le provisioning) et prod (rapatrié)
  écrivent au **même chemin nommé pareil**. Le seul delta banc/prod restant est
  le **contenu** du `server:` (127.0.0.1 port-forward vs IP du control-plane) —
  une différence de **données**, pas de **chemin de code**. L'identité prouvée
  par `server:` disjoint (ADR 0053) est préservée.
- **Garde d'isolation RENFORCÉE (ADR 0053)** : le cran par défaut est calculé
  DANS le dépôt à partir du nom de stack — il ne peut **plus jamais** retomber
  sur `~/.kube/config`. C'est structurellement plus fort que le `/dev/null`
  actuel (qui était une branche explicite) : si `.kubeconfigs/<stack>.config`
  n'existe pas, le fichier est absent, kubectl échoue proprement (lectures vides
  honnêtes).

Le champ `kubeconfig:` de la topo (ADR 0090) **change de rôle** : de « chemin
prod obligatoire » à **override optionnel rare** (chemin hors convention). Par
défaut None → la convention `.kubeconfigs/<stack>.config` s'applique pour banc
ET prod.

### Volet C — Provisioning piloté par la topo, par nœud

Le provisioning DÉRIVE tout de la topologie, **par nœud**. Fin de `WITH_CEPH`
(double la déclaration) et fin des ressources globales.

- **Disques** : `nodes[].disks` de la topo pilote la création. Un nœud qui
  déclare des disques → le provisioning les crée ; le « mode Ceph » n'est plus
  une variable d'env mais la **présence de disques déclarés**. Le schéma
  `disks:` s'enrichit en objets `{name, size, role}` (role `data`|`metadata`,
  tailles déclarées) pour être pleinement expressif (fin des tailles codées
  `HDD_SIZE`/`BLOCKDB_SIZE`).
- **Ressources par nœud** : le provisioning lit `node_resources(n)` pour CHAQUE
  nœud (plus le control-plane appliqué à tous). Un `nodes[].resources` a enfin
  un effet réel.
- **Canal unique** : `NODES_OVERRIDE` (nestor → run-phases.sh) est enrichi pour
  porter, par nœud, rôle + ressources + disques. Python décide les valeurs (de
  la topo), bash garde le RENDU (`lima_render_node`) — continuité ADR 0097.

## Conséquences

- **Une seule source de vérité, partout** : le nommage, le kubeconfig et le
  provisioning dérivent de la topologie ; plus de suffixe spécial, plus de
  chemin par terrain, plus de variable d'env parallèle.
- **~9 sites de duplication kubeconfig → 1 fonction** ; suppression de
  `_BENCH_KUBECONFIG`, fusion des résolveurs, un seul fetcher (le portage Python
  continue ADR 0101).
- **`nestor provision <topo ceph>` monte réellement un banc Ceph** (disques
  créés) — ce qui n'était pas le cas (bug constaté).
- **Sécurité (volet B, choix in-repo)** : les kubeconfig — dont la PROD — vivent
  dans l'arbre `.kubeconfigs/` gitignoré. Le `.gitignore` DOIT être
  **fail-safe** (`/.kubeconfigs/*` ignore tout, jamais de ré-inclusion
  `!*.config`) ; un garde-fou `git check-ignore` avant tout rapatriement prod.
  C'est le contre-argument assumé (cf. Alternatives).
- **Prouvable au banc** : le volet C touche le montage → **preuve banc
  obligatoire** (ADR 0034) : `nestor provision ceph.example.yaml` crée les
  disques (`limactl disk list`, `lsblk` vdb/vdc/vdd), ressources par nœud
  respectées, rejeu `changed=0`.

## Mise en œuvre incrémentale (chaque lot prouvable)

Amendement d'abord (cet ADR), puis par lots, chacun re-prouvé (ADR 0034/0097) :

1. **Volet A** (nommage) : `git mv banc.yaml banc.example.yaml`, retirer
   l'exception `.gitignore`, recâbler les références (docs/plans, ADR 0097,
   README portal), ajouter `ceph.example.yaml`. Pur, sans banc.
2. **Volet B** (kubeconfig) : fonction unique + `.kubeconfigs/` + `.gitignore`
   fail-safe + fusion des résolveurs/fetchers + tests anti-régression
   garde 0053. Le test « jamais `~/.kube/config` » est conservé et étendu.
3. **Volet C** (provisioning) : `DiskSpec` model + `NODES_OVERRIDE` enrichi +
   `phase_up` par nœud + suppression `WITH_CEPH`/`HDD_*`. **Preuve banc**
   (disques créés).

## Alternatives écartées

- **Statu quo (3 mécanismes parallèles)** : maintient la duplication kubeconfig
  (~9 sites), l'exception de nommage, et le provisioning piloté par l'ENV qui
  contredit la topo (bug disques). Contre le principe « topo = source unique ».
- **kubeconfig : nommage unifié mais prod hors arbre (`~/.kube/`)** : élimine
  TOUTE la duplication de code (une fonction) SANS mettre les credentials prod
  dans l'arbre (esprit ADR 0090 préservé). Écarté au profit de l'emplacement
  VRAIMENT unique in-repo, choisi explicitement — la duplication étant dans le
  code, pas dans l'emplacement, cette option était plus sûre mais moins
  intuitive ; le choix in-repo est assumé avec un `.gitignore` fail-safe comme
  garde-fou.
- **Garder l'exception `banc.yaml`** (ADR 0023 intact) : deux patrons de nommage
  coexistent, contre l'uniformité visée. Écarté — un seul patron `.example`.
- **Provisioning : dériver `WITH_CEPH` du backend sans lire `nodes[].disks`** :
  corrige le symptôme (le backend déclenche les disques) mais garde les
  tailles/nombre codés et ne respecte pas « la topo déclare les disques ».
  Écarté au profit du pilotage par nœud.
