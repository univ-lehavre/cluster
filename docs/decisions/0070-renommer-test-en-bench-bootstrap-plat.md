# 0070 — Renommer `test/` en `bench/` ; garder `bootstrap/` à plat

## Statut

Accepted (2026-06-15)

## Contexte

Un audit de lisibilité de l'arborescence (« est-ce lisible pour un nouveau
développeur ? ») a relevé deux frictions de nommage. Cet ADR tranche les deux.

### Friction 1 — collision `test/` vs `tests/`

Le dépôt a **deux dossiers frères** qui ne diffèrent que par un `s` final, pour
deux natures de tests **totalement différentes** :

| Dossier  | Contenu réel                                             | Nature             |
| -------- | -------------------------------------------------------- | ------------------ |
| `test/`  | Banc **Lima** end-to-end (shell, VMs, scénarios, spikes) | E2E / opérationnel |
| `tests/` | 20 fichiers **pytest** du paquet `cluster_topology`      | unitaires Python   |

`tests/` est la **convention Python standard** (découverte par
`unittest discover -s tests`, `package.json`). C'est `test/` qui est mal nommé :
rien dans le nom ne dit « banc Lima ». Pour un nouvel arrivant, « lancer les
tests » est ambigu, l'autocomplétion propose les deux côte à côte, et un `cd` ou
un import partent dans le mauvais dossier. La doc, elle, appelle déjà ce dossier
**« le banc »** partout (`just bench …`, `docs/banc-local.md`,
`bench-freshness.yml`) : le nom du dossier est le seul endroit qui ne suit pas.

### Friction 2 — `bootstrap/` à plat (~26 playbooks à la racine)

`bootstrap/` mélange à sa racine ~26 playbooks `.yaml`, 3 scripts `.sh`, la
config Ansible, l'inventaire, et les sous-dossiers
`roles/ lib/ group_vars/ security/`. Un `ls bootstrap/` est un mur ;
l'arborescence ne dit ni l'ordre ni le regroupement (install / join / platform /
ops).

La tentation est de **déplacer les playbooks en sous-dossiers**
(`playbooks/install/`, `playbooks/ops/`…). Le recensement montre que ce serait
un mauvais marché : les chemins `bootstrap/<playbook>.yaml` sont **codés en dur
comme littéraux** dans des surfaces qui sont précisément les preuves du dépôt :

- `cluster_topology/plan.py` — chaque `PhaseSpec` porte le chemin en littéral
  (`"bootstrap/ceph-cluster.yaml"`…), consommé par le runner P5 (ADR 0063) ;
- le banc E2E — `test/lima/run-phases.sh`, `env.sh`, `metrology.sh` (≈ 22 refs)
  ;
- le `Justfile` (11 refs), `bootstrap/RUNBOOK.md`, `bootstrap/state.sh` ;
- les tests unitaires — `tests/test_runner.py` (10), `test_plan.py`,
  `test_topology_cli.py` ;
- une quinzaine d'ADR et de pages `docs/`.

Déplacer les fichiers obligerait à éditer **toutes** ces références en lockstep
— dont le chemin E2E prouvé (`run-phases.sh`) — ce qui **contredit frontalement
le principe « corriger le code, pas l'état »
([ADR 0046](0046-corriger-le-code-pas-l-etat.md)) et la reproductibilité
([ADR 0052](0052-reproductibilite-des-resultats.md))** : on toucherait le
harnais prouvé pour un gain cosmétique, et il faudrait **re-prouver un run
complet** pour rien. De plus, le « mur » est **déjà documenté** : le tableau de
`bootstrap/README.md` index chaque playbook avec son rôle.

## Décision

### 1. Renommer `test/` → `bench/`

Le banc passe de `test/` à **`bench/`** (sous-dossiers `bench/lima/`,
`bench/scenarios/`, `bench/spikes/`, `bench/unit/` inchangés). Le renommage se
fait par `git mv` (l'historique suit), puis réécriture de **toutes** les
références (externes et internes) en une PR atomique. Le dossier `tests/`
(pytest) **ne bouge pas** — il porte la convention Python.

Exception d'honnêteté des Runs (ADR 0023) : **le contenu historique de
`RESULTS.md`** (banc et `lima/RESULTS.md`) n'est **pas réécrit** — les chemins
`test/…`, `test/multi-node/` (Vagrant déprécié)… y sont des **traces datées**.
Seules les futures entrées emploient `bench/`. Le renommage du **fichier**
(`bench/RESULTS.md`) suit le `git mv`, mais son **contenu** reste tel quel.

### 2. Garder `bootstrap/` à plat — index, pas déplacement

On **ne déplace pas** les playbooks. La lisibilité se gagne par l'**index**, pas
par l'arborescence :

- le tableau de `bootstrap/README.md` est **réordonné par phase** (install →
  join → storage/platform → ops/maintenance), avec un en-tête de section, pour
  que l'ordre canonique se lise sans ouvrir le RUNBOOK ;
- aucun préfixe numérique sur les fichiers (un `01-cri.yaml` figerait l'ordre
  dans le nom alors que le DAG des couches le porte déjà —
  [ADR 0069](0069-topology-layers-dag-grain-phase.md) — et casserait les ~60
  références littérales) ;
- `bootstrap/security/` reste un sous-projet autonome (son README/CHANGELOG),
  inchangé.

Si un jour un déplacement de playbooks devient justifié, il faudra d'abord
**dériver les chemins** d'une source unique (préfixe + nom dans `plan.py`)
plutôt que des littéraux — c'est le préalable, pas ce changement-ci.

## Conséquences

- **Positif** : la collision `test/`/`tests/` disparaît ; le nom du dossier
  rejoint le vocabulaire (« banc ») déjà employé partout. Aucun fichier
  `bootstrap/` déplacé → zéro churn sur le harnais prouvé, pas de run à rejouer.
- **Coût** : une PR de renommage à large surface (≈ 120 fichiers touchés,
  > 330 références externes) — mécanique mais à faire d'un bloc, validée par
  > `pnpm lint` + `pnpm docs:build` (liens morts) + `just bench --help` (ou un
  > dry-run). Détail et checklist :
  > [plan dédié](../plans/plan-renommer-test-bench.md).
- **Risque** : une référence oubliée casse un lien VitePress (détecté par
  `docs:build`) ou une cible Justfile/CI. Mitigé par un `grep` de non-régression
  final `test/` (hors `tests/`, hors `RESULTS.md`) = 0.
- **Neutre** : `bootstrap/` reste dense en surface, assumé — la densité est
  adressée par l'index, conformément à « corriger le code, pas l'état ».

## Liens

- [ADR 0023](0023-plateforme-exemple-generique.md) — honnêteté des Runs
  (`RESULTS.md` non réécrit).
- [ADR 0030](0030-nomenclature-bancs-topologies.md) — nomenclature des bancs par
  topologie (le renommage ne touche que le **dossier conteneur**, pas les noms
  techniques de banc).
- [ADR 0046](0046-corriger-le-code-pas-l-etat.md) /
  [ADR 0052](0052-reproductibilite-des-resultats.md) — fondent le refus de
  déplacer les playbooks `bootstrap/`.
- [ADR 0069](0069-topology-layers-dag-grain-phase.md) — l'ordre des phases vit
  dans le DAG, pas dans des préfixes de noms de fichiers.
- Mise en œuvre :
  [plan-renommer-test-bench](../plans/plan-renommer-test-bench.md).
