# 0090 — `nestor` lit l'état RÉEL d'un cluster prod (état = K8s, pas VMs)

## Statut

Proposed (2026-06-22) — mise en œuvre suivie par
[`plan-nestor-pilote-prod.md`](../plans/plan-nestor-pilote-prod.md). Suite
directe de [ADR 0053](0053-isolation-multi-cible-banc-prod.md) (isolation
banc/prod) et [ADR 0084](0084-sondes-de-lecture-gatees-par-target-kind.md)
(sondes gatées par `target_kind`).

## Contexte

`nestor` est l'outil **déclaratif** du dépôt (ADR 0056). Mais en pratique il ne
sait piloter que le **banc Lima** : sur une stack `target_kind: prod`, ses
commandes de lecture **mentent sur l'état réel**.

Constat empirique (2026-06-22, cluster prod `dirqual1-4`, sain depuis 10 jours —
Ceph `HEALTH_OK`, CNPG 3/3, monitoring/gitops/registry en place) :

```text
$ nestor preview            # stack dirqual, target_kind: prod
RÉEL (lu, non stocké) :
  VMs présentes  : —
  VMs à créer    : dirqual1, dirqual2, dirqual3, dirqual4    ← FAUX
  nœuds Ready    : —                                          ← FAUX
PLAN : 10 couche(s) à installer                               ← DANGEREUX
```

Or `kubectl` (contexte prod) montre les 4 nœuds **Ready** et 8 couches déjà
saines. **Si l'on avait suivi ce plan (`nestor up`/`next`), nestor aurait tenté
de réinstaller K8s + Ceph par-dessus une prod saine.** Le piège n'est évité que
parce qu'on a diagnostiqué à la main, en lecture seule.

Trois causes, toutes dans `scripts/topology.py` :

1. **`preview` raisonne en VMs Lima.** `_real_vms(target_kind)` (ADR 0084) fait
   `if target_kind != "lima": return []` → en prod, « 0 VM » → « VMs à créer :
   dirqual1-4 ». L'état réel d'un cluster bare-metal **n'est pas une liste de
   VMs** : les machines existent hors de `nestor` (provisionnées en amont).
2. **L'état réel des nœuds est gaté.** `_ready_nodes(target_kind)` sait lire
   `kubectl get nodes`, mais se neutralise en prod sans `KUBECONFIG` explicite
   (ADR 0084 §repli) → renvoie vide → « nœuds Ready : — ».
3. **Le kubeconfig prod n'est jamais choisi automatiquement.**
   `_bench_kubeconfig()` (ADR 0053) pointe `/dev/null` hors banc — protection
   **correcte contre les mutations**, mais elle prive aussi la **lecture** prod
   d'une cible.

À l'inverse, `nestor discover` (ADR 0074) lit **déjà** le K8s réel par kubectl
(`_discover_node_roles`, `_discover_namespaces`, `_discover_sc_provisioners`,
`_discover_crd_groups`…). La capacité de lecture existe ; elle n'est simplement
**pas branchée dans `preview`/l'état réel** pour `target_kind: prod`.

## Décision

> **Quand `target_kind: prod`, l'« état RÉEL » de `nestor` est celui du cluster
> Kubernetes lu par `kubectl` (nœuds Ready, namespaces, couches via CRD/SC/
> ressources), PAS une liste de VMs Lima.** `preview` (et les commandes de
> lecture) comparent alors le **voulu** au **réel K8s**, et le PLAN ne propose
> que les couches **réellement absentes**.

Principes de mise en œuvre (détaillés dans le plan) :

- **L'état réel est conditionné par `target_kind`.** En `lima`, inchangé (VMs
  `limactl` + nœuds). En `prod`, l'état des machines **n'est pas** du ressort de
  `nestor` (provisionnées en amont, RUNBOOK) : la section « VMs » disparaît au
  profit de « nœuds Ready (kubectl) ». Les couches présentes se déduisent du
  réel K8s (réutiliser les sondes `_discover_*` existantes), pas d'un état
  stocké.
- **Cible kubeconfig DÉCLARÉE dans la topologie.** La topologie prod porte un
  champ **`kubeconfig: <chemin>`** (dans le `.yaml` gitignoré qui contient déjà
  les valeurs réelles, ADR 0023). C'est la **source de vérité** de la cible : la
  lecture prod n'est **jamais** laissée au `~/.kube/config`/contexte courant du
  poste (ambigu — c'est précisément ce qui a fait pointer un cluster fantôme
  lors du diagnostic). Résolution, par priorité : (1) `KUBECONFIG` exporté =
  intention explicite de l'opérateur (déjà respectée, ADR 0053) ; (2) sinon le
  **`kubeconfig:` de la topologie** ; (3) sinon, en `prod`, **échec clair** («
  cible kubeconfig non déclarée ») — jamais de repli silencieux. Si le fichier
  porte plusieurs contextes, son **`current-context`** fait foi. Le fallback
  `/dev/null` (anti-mutation) **reste** pour le banc (`target_kind: lima`).
- **Un kubeconfig dédié par stack, HORS du dépôt.** Convention : chaque stack a
  son propre fichier **`~/.kube/<stack>.config`** (ex.
  `~/.kube/dirqual.config`). Hors de l'arbre du dépôt → **aucun risque de
  commit** de credentials réels (les kubeconfig portent des certificats/tokens),
  emplacement standard kubectl, un fichier par cible (fini le `~/.kube/config`
  fourre-tout aux contextes fantômes). Le `kubeconfig:` de la topo pointe ce
  fichier. Le banc Lima garde son propre kubeconfig généré
  (`bench/lima/.work/kubeconfig`) — même esprit (un fichier par cible),
  emplacement distinct car généré par le harnais.
- **Lecture d'abord ; les mutations restent hors périmètre de cet ADR.** Cet ADR
  rend `nestor` **honnête en lecture** sur la prod (`preview`/`discover`/santé).
  Faire **muter** la prod par `nestor` (`up`/`next`/`remove` → délégation aux
  playbooks Ansible du RUNBOOK) est une **décision distincte et ultérieure**,
  avec ses propres garde-fous (confirmation explicite, `target_kind` re-vérifié,
  interdiction absolue de réinstaller un socle existant). Tant qu'elle n'est pas
  prise, **l'installation prod reste pilotée par Ansible** (RUNBOOK).
- **Garde-fou anti-régression d'isolation.** Rien dans cet ADR n'abaisse l'ADR
  0053 : on **élargit la lecture**, on ne **débride pas la mutation**. Un test
  doit prouver que `preview` prod en lecture ne peut pas déclencher d'écriture.

## Conséquences

**Positif :**

- `nestor preview` **dit la vérité** sur un cluster prod existant → plus de « 10
  couches à installer » sur une prod saine. Le PLAN devient fiable.
- Cohérence : l'outil déclaratif du dépôt **couvre enfin la prod** en lecture,
  pas seulement le banc.
- Réutilise l'acquis : les sondes `discover` (ADR 0074) deviennent la source de
  l'état réel prod ; peu de code neuf, surtout du **branchement conditionné**.

**Coût / risques :**

- **Sensible** : on touche au cœur de l'isolation banc/prod (ADR 0053/0084). Le
  risque est qu'une lecture prod ouvre par inadvertance une voie de mutation —
  d'où le périmètre **lecture seule** strict et le test anti-régression.
- L'« état réel » devient **polymorphe** (`lima` = VMs+nœuds ; `prod` = nœuds
  K8s). À documenter clairement pour ne pas re-confondre.
- Preuve : testable **sans toucher la prod** (sondes pures + stubs kubectl) ;
  validation finale sur le banc (target_kind lima inchangé) + une lecture prod
  réelle constatée (`preview` reflète `kubectl get nodes`).

**Neutre :**

- L'installation prod **reste pilotée par Ansible** (RUNBOOK) tant que la
  décision « mutation prod par nestor » n'est pas prise séparément.

## Voir aussi

- [Plan de mise en œuvre](../plans/plan-nestor-pilote-prod.md).
- [ADR 0053](0053-isolation-multi-cible-banc-prod.md) — isolation banc/prod
  (mutations) ; cet ADR en est le pendant **lecture**.
- [ADR 0084](0084-sondes-de-lecture-gatees-par-target-kind.md) — sondes gatées
  par `target_kind` (le mécanisme à étendre).
- [ADR 0074](0074-cluster-discover-reconstruire-topologie.md) — `discover` lit
  déjà le K8s réel (source des sondes réutilisées).
- [ADR 0056](0056-modele-declaratif-topologies.md) — `nestor`, outil déclaratif.
