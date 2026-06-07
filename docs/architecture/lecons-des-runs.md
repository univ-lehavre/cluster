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

| Campagne                       | Banc           | Matériel            | Drifts  | Temps total |
| ------------------------------ | -------------- | ------------------- | ------- | ----------- |
| Bootstrap K8s (#127)           | Lima / Vagrant | arm64               | L1–L11  | —           |
| Chaîne DataOps shell (#148)    | Lima (rapide)  | arm64               | L12–L20 | —           |
| Portage DataOps Ansible (#173) | Lima (Ceph)    | M3 Max 16c / 48 GiB | L21–L33 | ~30 min     |

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

## Ce que ça démontre

1. **Le lint ne valide pas** — il filtre le trivial. Les 13 drifts de #173
   passaient tous les linters au vert
   ([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)).
2. **La répétition est le processus, pas un échec.** Chaque run rapproche d'un
   invariant durable ; le compteur de drifts qui se tarit run après run **est**
   la courbe de fiabilisation.
3. **La connaissance capitalise.** Les drifts d'hier (L1–L20) ont servi de
   spécification au portage Ansible (#173). Ceux d'aujourd'hui (L21–L33)
   serviront aux prochains terrains (cloud, x86, HA).
