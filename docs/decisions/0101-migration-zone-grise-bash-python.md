# 0101 — Migration de la zone grise bash → Python (`bench/lima/` confort)

## Statut

Proposed (2026-06-30)

Prolonge [0097](0097-moteur-chemin-python-bash-artefacts.md) (le moteur de
chemin est Python ; le bash restant = artefacts node-side) et applique
[0049](0049-doctrine-choix-outil-par-action.md) /
[0017](0017-langage-des-scripts.md) (bash node-side, Python testé) à la
**dernière poche de bash d'orchestration** : cinq scripts de confort dans
`bench/lima/`. S'inscrit dans la lignée des retraits déjà faits — le `Justfile`
et `env.sh` (redondants avec `nestor`). Cohérent avec
[0034](0034-validation-e2e-from-scratch.md) (preuve banc) et
[0042](0042-fraicheur-preuves-banc.md) (fraîcheur des preuves). Valeurs
d'exemple génériques ([0023](0023-plateforme-exemple-generique.md)).

## Contexte

Après la refonte du moteur (ADR 0097), il subsiste **~1900 lignes de bash de
confort** dans `bench/lima/` — `access.sh` (275), `metrology.sh` (421),
`rollback-lib.sh` (871), `check-freshness.sh` (129), `gitea-init.sh` (207). Un
audit de chacun (rôle réel, irréductibilité node-side, appelants, équivalent
Python, testabilité) établit un **constat central** : **aucun n'est, en
totalité, irréductible node-side**. Ce sont de l'**orchestration `kubectl` +
calcul + parsing + rendu de fichier hôte** — exactement la cible Python de
l'ADR 0097. Et le Python couvre **déjà** l'essentiel (`history.py`,
`metrics.py`, `seed.py`, `graph.py`) ; la « migration » est surtout **brancher
l'appelant et retirer le doublon bash**, pas réécrire.

## Décision

On migre la zone grise vers Python, par étapes prouvables, en gardant
**uniquement** l'irréductible node-side (qui n'est pas dans ces scripts mais
dans les primitives `vm_sh`/`limactl` et `storage/ceph/cleanup.sh`). Verdicts :

| Script (L)                   | Verdict                                   | Pourquoi                                                                                                                                                                                                                 |
| ---------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **gitea-init.sh** (207)      | **SUPPRIMER**                             | Mort : 0 appelant ; le seed est déjà live en Python (`seed.py` + `_seed_do_banc`), prouvé au banc (drift L60). Son en-tête « Sourcé par run-phases.sh » est **mensonger**.                                               |
| **access.sh** (275)          | **MIGRER** (`nestor/access.py`)           | `topology.py:cmd_access` fait déjà `subprocess → run-phases.sh → access.sh` (double shell-out). Toute la plomberie Python existe (`_kubectl`, décodage secret, patron `Popen`+port-forward de `seed.py`). 0 % node-side. |
| **check-freshness.sh** (129) | **MIGRER** (Python)                       | Logique pure **déjà** dans `history.py` (parité testée). Reste ~30 L de glue + recâbler 1 ligne du workflow `bench-freshness.yml`. Un seul appelant (CI cron).                                                           |
| **metrology.sh** (421)       | **MIGRER le pur + SUPPRIMER le mort**     | ~40 % déjà porté (`history.py`/`metrics.py`) ; ~55 % record/sample/cache **orphelin** (run-phases.sh ne le source plus).                                                                                                 |
| **rollback-lib.sh** (871)    | **SUPPRIMER le pur + MIGRER le reliquat** | ~85 % déjà porté **byte-pour-byte dans `nestor/graph.py`** (`topo_sort`, 54 tests). Reste `phase_rollback` (orchestration kubectl) + 1 geste node-side ceph (`vm_sh < cleanup.sh`).                                      |

### Ordre (dégressif en risque)

1. **gitea-init.sh → supprimer** — mort, geste propre évident (catégorie
   Justfile/env.sh). Aucune dépendance.
2. **access.sh → migrer** (`nestor/access.py`) — le candidat le plus naturel :
   remplace le double subprocess de `cmd_access` par du Python natif, banc-only,
   testable par stub. Corrige au passage la dette des flags morts
   (`--print-hosts`/`--no-hosts`).
3. **check-freshness.sh → migrer** — pur consommateur de `history.py`, recâble 1
   ligne de workflow.
4. **metrology.sh → après (3)** — quand le dernier `source` vivant disparaît :
   supprimer le `.sh` + `metrology.bats` + le bloc record/cache mort.
5. **rollback-lib.sh → en dernier, en 2 temps** — (a) migrer `phase_rollback` +
   primitives `kubectl` vers le chemin `remove --discover` Python (le geste
   node-side ceph passe par la couche nodeside) ; (b) **alors seulement**
   supprimer la partie pure (déjà dans `graph.py`) + `rollback.bats`. **Preuve
   banc obligatoire** (k8s sur mono-nœud local-path ; le node-side ceph ne se
   prouve que sur prod, ADR 0085).

## Conséquences

- **Une seule source de vérité** : plus de logique dupliquée bash ↔ Python (la
  fraîcheur, la métrologie, l'ordre de rollback vivent en un seul endroit,
  testé).
- **`bench/lima/` se réduit à l'orchestrateur node-side** (`run-phases.sh` +
  `lib.sh` + `cni.sh`) — l'irréductible ADR 0049, hors de cette migration.
- **Chaque étape est prouvable au banc** ; les étapes 1–4 sont à faible risque
  (mort / CI / banc-only), seule l'étape 5 touche le montage et exige une preuve
  banc complète.
- Migrer `rollback-lib` **résout** l'issue #519 (compat bash 3.2 de `topo_sort`)
  par disparition — la version Python (`graph.py`) n'a pas le problème ; pas
  besoin de patcher le bash si on le supprime.

## Ce qui RESTE en bash légitimement (pas un échec)

L'irréductible node-side est **plus petit que les scripts** et **déjà séparé** :

- **`storage/ceph/cleanup.sh`** : wipe disques + `/var/lib/rook` **dans la VM**.
  `rollback-lib` ne fait que le pousser via `vm_sh` ; le node-side réel y reste.
- L'enveloppe **`vm_sh`/`limactl shell`** (transport d'un script dans la VM) —
  une primitive, pas la logique des 5 scripts.
- **`run-phases.sh`/`lib.sh`** (chemin nommé codé, ADR 0045 ; `limactl`,
  `write_inventory`) — hors périmètre, gardent leur légitimité (ADR 0049).

Mnémonique : reste en bash **ce qui s'exécute dans la VM ou provisionne**.

## Alternatives écartées

- **Tout garder en bash** (statu quo) : maintient une logique dupliquée
  (fraîcheur/métrologie/rollback en double bash ↔ Python), à l'encontre d'ADR
  0097 ; et laisse `gitea-init.sh` mort avec un en-tête mensonger.
- **Tout migrer d'un coup** (big-bang) : `rollback-lib` touche le
  montage/démontage banc — un big-bang sans preuve par étape contredit ADR 0034.
  D'où l'ordre dégressif et la preuve banc en fin (étape 5).
- **Patcher `rollback-lib` pour bash 3.2** (#519) sans migrer : corrige le
  symptôme en gardant le doublon. Migrer le résout par disparition.
