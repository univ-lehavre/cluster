# Leçons des Runs — ce que la validation e2e a appris

Cette page agrège, **par catégorie**, les _drifts_ rencontrés en validant le
catalogue sur banc — run après run, depuis le bootstrap jusqu'à la chaîne
DataOps. Elle transforme une suite d'incidents en **savoir réutilisable** : les
patterns récurrents et les invariants qu'ils imposent.

> **Pourquoi cette page existe.** Aucune brique d'infra du dépôt n'a jamais
> fonctionné e2e du premier coup : chaque chantier a traversé plusieurs runs
> avec correctifs
> ([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)). Ce n'est pas
> un aveu de faiblesse — c'est la **preuve que le processus est sérieux** : on
> ne déclare « validé » qu'après un run from-scratch réel, et chaque piège
> traversé est verrouillé pour de bon. Le détail daté vit dans les
> [`RESULTS.md`](../../test/lima/RESULTS.md) ; ici, la vue d'ensemble.

## Tableau de bord — runs e2e consignés

Matériel + temps + drifts par campagne de validation (mesurés ; cf.
`RESULTS.md`).

**Portée d'un drift** (colonne ci-dessous) : un drift est **code** s'il révèle
un défaut du livrable (manque un prérequis, mauvais ordre, parser inadapté) — il
vaut alors pour **tous les bancs ET la prod**, et se corrige à la racine. Il est
**env** s'il n'existe que pour la topologie de banc en cours (ressources,
mounts, artefact Vagrant) — il ne « bouleverse » pas les autres bancs. Cette
distinction décide _où_ corriger : code → le rôle/manifeste ; env → la config du
banc.

| Campagne                       | Banc                    | Matériel            | Drifts  | Portée                | Temps total     |
| ------------------------------ | ----------------------- | ------------------- | ------- | --------------------- | --------------- |
| Bootstrap K8s (#127)           | Lima / Vagrant          | arm64               | L1–L11  | mixte (code + env)    | —               |
| Chaîne DataOps shell (#148)    | Lima (rapide)           | arm64               | L12–L20 | surtout code          | —               |
| Portage DataOps Ansible (#173) | Lima (Ceph)             | M3 Max 16c / 48 GiB | L21–L33 | mixte (code + env)    | ~30 min         |
| storageClass + S3 (#158/#186)  | Lima (léger, puis Ceph) | M3 Max 16c / 48 GiB | L34–L40 | **code (universels)** | ~11 min (léger) |

Détail des temps par phase du run #173 (M3 Max, mode Ceph, 8 GiB/VM) :

| Phase       | Durée         | Ce qu'elle monte                                                            |
| ----------- | ------------- | --------------------------------------------------------------------------- |
| `up`        | ~3m40s        | 3 VMs Lima + disques bruts                                                  |
| `bootstrap` | ~7m10s        | kubeadm 1.34 + Cilium (3 nœuds Ready)                                       |
| `ceph`      | ~3m45s        | Rook-Ceph, 9 OSD, HEALTH_OK                                                 |
| `sc`        | ~10s          | StorageClasses                                                              |
| `datalake`  | ~4m (à froid) | CephObjectStore RGW (cible S3 Barman)                                       |
| `dataops`   | **13m37s**    | registry → cert-manager → CNPG+Barman → build → Dagster → Marquez + lineage |

> Le `dataops` (≈14 min) est dominé par le **build d'images arm64** (gradle Java
> Marquez + npm React). C'est l'argument premier pour des **bancs plus rapides
> et ciblés** quand on n'itère que sur une brique — d'où la stratégie
> fidélité/vitesse de
> [ADR 0035](../decisions/0035-strategie-bancs-fidelite-vitesse.md) (profil
> `local-path` ~11 min vs Ceph ~30 min).

## Les drifts par catégorie

### 1. Modèle d'exécution (où tourne le code vs où il agit)

Le banc pilote l'API **depuis l'hôte** (port-forward), alors que le bootstrap
historique tourne **sur les nœuds**. Tout ce qui supposait « exécution sur le
nœud » a cassé en localhost.

- **L21** `gather_facts` manquant · **L22** audit-log = `sudo` sans objet sur le
  poste · **L23** CA Python absent (SSL) · **L24** un rôle multi-cible chargé en
  bloc tourne sur le mauvais hôte.
- **Invariant** : un rôle qui agit via l'API k8s doit être **indépendant de
  l'hôte d'exécution** (variable `dataops_k8s_host`, `tasks_from` pour séparer
  les volets nœud/cluster, libs Python posées sur l'exécuteur réel).

### 2. Ordre et dépendances inter-briques

- **L25** Secret posé avant que son namespace n'existe · **L14** plugin requis
  avant d'être installé · **L31** image référencée avant d'être construite.
- **Invariant** : créer **explicitement** le prérequis (namespace, plugin,
  image) avant l'objet qui en dépend — ne jamais supposer un ordre implicite.

### 3. Isolation et ressources du banc

Le banc est volontairement **isolé** (`mounts: []`) et **modeste**.

- **L27** sources du dépôt absentes de la VM → copier sur le nœud · **L28**
  build web **OOM** à 5 GiB → 8 GiB · **L29** reboot → Cilium pas reconvergé ·
  **L30** containerd pas rechargé après pose de config.
- **Invariant** : ne rien supposer du host dans la VM ; dimensionner pour le
  **pic** (build), pas le repos ; après tout reboot, attendre la reconvergence
  réseau (artefact « restore non fidèle », connu).

### 4. Gates — la mesure elle-même peut être fausse

Un gate trop strict transforme un succès en échec.

- **L7** HEALTH*OK trompeur (cluster vide) → exiger aussi les OSD · **L32**
  ingestion testée par \_delta* alors que le run est idempotent → tester la
  **présence** · **L33** gate RGW `== 1` alors que `instances: 3` → `>= 1`.
- **Invariant** : un gate teste la **propriété voulue** (présence, santé
  réelle), pas un proxy fragile. Un gate est du code — il a ses bugs, il se
  teste (bats).

### 5. Bugs réels du livrable (corrigés à la racine)

Tous les drifts ne sont pas des artefacts banc — certains sont de **vrais bugs**
que seul le run a exposés, corrigés dans le dépôt (pas contournés).

- **L16/L17** rôles CNPG sans `passwordSecret` (connexion impossible) · **L19**
  NetworkPolicy egress `dagster→marquez` manquante · **L20** orchestrateur sans
  workspace (CrashLoop) · **L13** `use_local_image_pull` (fix racine du pull
  HTTP).

### 6. Webhooks d'admission et CRDs — l'ordre est implicite mais réel

Le portage monitoring/Loki (#158/#186) a buté sur des dépendances **invisibles
dans les manifestes** mais imposées par l'API server. Tous **code/universels** :
ils cassent partout, banc léger comme prod.

- **L34** CRDs `kube-prometheus-stack` avec enum `- =` non quoté → le parser
  PyYAML du module `k8s` rejette (tag `yaml.org,2002:value`) ; `kubectl` (Go)
  les charge → appliquer ces CRDs via `kubectl apply --server-side`, pas le
  module.
- **L35** le manifeste monitoring contient des `Certificate`/`Issuer` →
  **cert-manager doit exister avant** (sinon « no matches for
  cert-manager.io/v1.Certificate »).
- **L37** (cause racine de L36) cert-manager du dépôt tourne avec
  `--enable-gateway-api` → **CrashLoop** si les CRDs Gateway API sont absentes →
  le rôle `platform-cert-manager` les pose lui-même.
- **L36** les `PrometheusRule` passent par le **webhook d'admission de
  l'operator** → appliqués avant qu'il soit Ready, ils échouent en masse (HTTP
  500 `prometheusrulemutate`) → **deux passes** : tout sauf les
  `PrometheusRule`, attendre l'operator Ready, puis les `PrometheusRule`.
- **Invariant** : une CRD, un webhook, un contrôleur sont des **prérequis
  d'ordre** au même titre qu'un namespace (cat. 2) — les garantir **Established
  / Ready** avant d'appliquer ce qui en dépend. Ces drifts sont **de code** :
  ils valent pour toute topologie (cf. colonne _Portée_).

### 7. Drifts qu'un seul profil masque — pourquoi valider les deux backings

Le profil S3 de Loki est le **même code** partout, mais le **backing diffère**
(SeaweedFS léger ↔ RGW Ceph,
[ADR 0036](../decisions/0036-backing-s3-unique-rgw.md)). Deux drifts **de code**
n'apparaissent **qu'en RGW** — le banc léger les masquait (ses creds admin
SeaweedFS créent n'importe quel bucket) :

- **L38** l'**OBC Rook n'expose qu'UN bucket auto-nommé** + des creds restreints
  à ce bucket → impossible de créer les buckets nommés
  `loki-chunks`/`loki-ruler` attendus (`NoSuchBucket` au démarrage du compactor)
  → en RGW, résoudre le bucket de l'OBC et l'employer pour chunks **et** ruler ;
  init-buckets skippé.
- **L39** le Job init-buckets avait un **gate faux** : son `grep make_bucket`
  matchait aussi `make_bucket failed` → toujours vert, même quand rien n'était
  créé → réécrit pour **échouer franchement** si le bucket n'est ni créé ni déjà
  présent.
- **L40** (symétrique, côté **léger**) `platform-prereqs` mourait sur le banc
  léger : `set -e` + `reg_ip=$(kubectl get svc registry …)` sans le namespace
  `registry` (présent uniquement avec `dataops`) → l'assignation échoue et tue
  le script avant son garde → `… || true`. Masqué jusque-là car les runs
  montaient toujours le registry via `dataops` ; seul un run **monitoring-seul**
  l'expose.
- **Invariant** : un profil de banc qui **élargit les droits** (creds admin) ou
  masque les contraintes du profil réel (creds restreints OBC). Un chemin de
  code partagé doit être **validé sur chaque backing réellement employé** —
  sinon le banc rapide valide une version plus permissive que la prod. C'est
  l'argument concret de la double validation léger **puis** Ceph (cf. colonne
  _Portée_).

## Ce que ça démontre

1. **Le lint ne valide pas** — il filtre le trivial. Les 13 drifts de #173
   passaient tous les linters au vert
   ([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)).
2. **La répétition est le processus, pas un échec.** Chaque run rapproche d'un
   invariant durable ; le compteur de drifts qui se tarit run après run **est**
   la courbe de fiabilisation.
3. **La connaissance capitalise.** Les drifts d'hier (L1–L20) ont servi de
   spécification au portage Ansible (#173). Ceux d'hier (L21–L33) et
   d'aujourd'hui (L34–L40, tous **code**) serviront aux prochains terrains
   (cloud, x86, HA).
4. **Tester le banc léger n'est pas tricher.** Le profil S3 (Loki, CNPG) est le
   **même code** partout — seul le backing change (SeaweedFS léger ↔ RGW Ceph,
   [ADR 0036](../decisions/0036-backing-s3-unique-rgw.md)). Le banc léger valide
   donc le **vrai chemin S3** sans monter Ceph ; le banc Ceph ne revalide que ce
   qui diffère réellement (l'implémentation RGW).
