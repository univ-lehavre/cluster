# Plan — Refonte nestor : graphe Python figé + moteur de chemin (zéro bash d'orchestration)

## État

> **État : Actif** (2026-06-25) · **Fonde :**
> [ADR 0096](../decisions/0096-graphe-topologie-python-verifie-ansible.md)
> (Accepted) +
> [ADR 0097](../decisions/0097-moteur-chemin-python-bash-artefacts.md)
> (Accepted). · **Preuve :**
> [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md).
>
> ADR fondateurs `Accepted` (2026-06-25) ⇒ **implémentation des lots autorisée**
> ([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) §6).
> L'**étape 1** (factorisation pure, fix de bug sans ADR : elle ne décide rien
> de structurant, elle corrige une classe de bug existante) est le premier pas ;
> les lots 2-9 suivent, chacun prouvé au banc puis en prod.

Met en œuvre la refonte de `nestor` décidée par
[ADR 0096](../decisions/0096-graphe-topologie-python-verifie-ansible.md) (graphe
de topologie **Python figé**, vérifié contre Ansible par un check qui notifie)
et [ADR 0097](../decisions/0097-moteur-chemin-python-bash-artefacts.md)
(**moteur de chemin** Python ; bash réduit aux artefacts node-side ; paramétrage
100 % YAML ; deux topologies pilotées par le même moteur). Ce plan **livre
l'étape 1 maintenant** (fix de fidélité `preview`/`next`/`up`, sans ADR) puis
**cadre les lots cible** (2-9), gelés jusqu'à l'acceptation des deux ADR.

## ADR fondateurs

- [0096](../decisions/0096-graphe-topologie-python-verifie-ansible.md) — **le
  premier pilier** : le graphe (`nestor/graph.py`) est la **source unique** de
  l'ordre inter-composant, du périmètre de rollback (4 dimensions) et du signal
  ; `scripts/check_topology.py` **notifie** la divergence graphe ↔ Ansible.
  Implémente en Python
  [0066](../decisions/0066-rollback-atomique-graphe-composants.md) /
  [0069](../decisions/0069-topology-layers-dag-grain-phase.md) /
  [0083](../decisions/0083-layers-source-unique-de-l-ordre.md).
- [0097](../decisions/0097-moteur-chemin-python-bash-artefacts.md) — **le second
  pilier** : `nestor/path.py` absorbe l'orchestration de `run-phases.sh` ; un
  seul sens d'appel Python → bash ; `cni.sh`/`cleanup.sh` restent des artefacts
  node-side ; paramétrage YAML ; les **deux** topologies. Supersede
  partiellement [0049](../decisions/0049-doctrine-choix-outil-par-action.md),
  clôt l'inversion de [0063](../decisions/0063-ansible-runner-boucle-p5.md).
- [0017](../decisions/0017-langage-des-scripts.md) — bash orchestre vs Python
  testé : la frontière évolue, le bash d'orchestration part en **pytest**.
- [0034](../decisions/0034-validation-e2e-from-scratch.md) /
  [0052](../decisions/0052-reproductibilite-des-resultats.md) — preuve banc
  _from-scratch_ AVANT prod ; idempotence rejeu `changed=0`.
- [0046](../decisions/0046-corriger-le-code-pas-l-etat.md) — corriger le
  **code**, pas l'**état** : chaque correctif repart dans le code versionné,
  re-prouvé par un run.
- [0053](../decisions/0053-isolation-multi-cible-banc-prod.md) /
  [0090](../decisions/0090-nestor-pilote-la-prod.md) — gardes d'isolation
  banc/prod traversées **à chaque phase** (invariant de boucle) ; `nestor`
  pilote la prod.
- [0056](../decisions/0056-modele-declaratif-topologies.md) — modèle déclaratif
  : une topologie = **un YAML auto-suffisant** (fonde le paramétrage 100 % YAML
  du lot 8) ; ce plan prolonge
  [`plan-modele-declaratif.md`](plan-modele-declaratif.md) (palier **P9**).
- [0023](../decisions/0023-plateforme-exemple-generique.md) — valeurs génériques
  : `node1`…`node4`, `banc`, `local-path`, `ceph`, `platform-cnpg`,
  `platform-s3-bucket`, `marquez`, `dagster`.

## Contexte — le fil rouge

L'audit des causes racines (« pourquoi revient-on souvent aux mêmes erreurs ? »)
tranche : le **même fait** existe en **trois représentations synchronisées à la
main** par le commit, jamais par le code ni par un test.

1. **Le graphe** est déclaré en bash (`bench/lima/rollback-lib.sh` :
   `component_deps`, `component_namespace`, `component_targeted`,
   `component_crd_groups`, `component_has_nodeside`, `component_alias_weight`,
   `component_profile`).
2. **Sa projection nestor** ne re-déclare pas le graphe : elle le **consulte en
   shellant bash** (`nestor/layers.py:91` `_rb`, `nestor/roundtrip.py`
   `_rollback_lib_call`) — un `subprocess` qui source `rollback-lib.sh` à chaque
   appel.
3. **Le signal de santé** vit dans une **3ᵉ table séparée** (`_LAYER_SIGNAL`,
   `scripts/topology.py:739`), mappant une phase → un seul Deployment
   discriminant.

Les **primitives** sont uniques (`topo_sort`, `component_deps`) — ce ne sont pas
elles le problème. Ce sont leurs **câblages** et leurs **miroirs** qui ne le
sont pas : chaque correctif corrige UN miroir, l'autre reste. D'où les erreurs
récurrentes :

- **« Marquez oublié »** : `dataops` a **deux feuilles** (`dagster` ET
  `marquez`), mais `_LAYER_SIGNAL["dataops"]` ne sonde que
  `dagster-dagster-webserver` (`topology.py:751`) → le verdict « DataOps complet
  » peut **mentir** sur un drift de Marquez (MEMORY.md : « `_LAYER_SIGNAL` ment
  »).
- **`preview` ≠ `next`** : l'assemblage de l'état
  (`done`/`observed`/`a_appliquer`) a divergé parce qu'il est **copié-collé**
  entre `cmd_preview` (`topology.py:2167-2199`) et `cmd_next`
  (`topology.py:2522-2562`) — ce dernier manque même le garde
  `if "up" not in done` que `preview` possède (VRAI bug).

Côté exécution, `run-phases.sh` (**1903 lignes**) garde l'orchestration : il
**décide quoi monter**, **enchaîne les `ansible-playbook`**, **gate** via
`kubectl`, **possède l'état partagé** (`CP`, `API_PORT`, `KUBECONFIG_LOCAL`),
**provisionne** (`phase_up`, `write_inventory`). `nestor` ne fait que
**l'appeler en subprocess**, avec une **circularité résiduelle**
(`bootstrap-seq` :508 et `ha-3cp` :1650 re-rappellent Python, qui re-rappelle
bash `ha-cni`). Double-détention Python/bash de la vérité → divergences
récurrentes qu'aucun correctif local ne tarit.

**La cible** : fusionner ces représentations comme **projections d'une source
unique** (graphe Python figé) et **inverser l'exécution** (un seul sens Python →
bash). Ce plan procède **par lots**, banc d'abord, sans jamais casser le
présent.

## Invariants

1. **Banc d'abord**
   ([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)) : chaque lot
   est prouvé sur le **banc Lima** AVANT toute exécution prod. Le banc actuel
   reste la référence (mono-nœud local-path,
   [ADR 0085](../decisions/0085-preuves-applicatives-local-path.md)).
2. **LES DEUX topologies à chaque lot.** Un lot n'est « fait » que s'il marche
   sur **(a)** le banc mono-nœud local-path
   ([`topologies/banc.yaml`](../../topologies/banc.yaml)) **ET (b)** la prod 4
   nœuds Ceph ([`topologies/dirqual.yaml`](../../topologies/dirqual.yaml)) —
   **banc d'abord, prod ensuite**. Le graphe
   [ADR 0096](../decisions/0096-graphe-topologie-python-verifie-ansible.md) est
   **backend-conditionnel** : `local-path` → `storage-simple` ; `ceph` →
   `ceph`/`sc`/`datalake`.
3. **Byte-identité**
   ([ADR 0056](../decisions/0056-modele-declaratif-topologies.md) §3) : un
   portage Python **ne change pas le rendu** (inventaire, ordre de phases,
   périmètre de rollback) — **prouvé par test**, pas postulé. Piège connu : le
   tie-break lexicographique de `topo_sort` (`rollback-lib.sh:537`, clé
   `%s%03d`, comparaison `\<` bash) à reproduire **à l'octet** via
   `rollback.bats` rejoué en pytest.
4. **Coexistence sans régression.** Aucun lot ne casse le précédent ; le bash et
   le Python **coexistent** pendant la transition — on ne **bascule** un câblage
   qu'avec la preuve en main (portage **à côté** d'abord, bascule ensuite).
5. **Corriger le code, pas l'état**
   ([ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md)) : tout passe
   par les modules/chemins nommés ; idempotence prouvée par rejeu `changed=0`
   ([ADR 0052](../decisions/0052-reproductibilite-des-resultats.md)).
6. **Garde d'isolation = invariant de boucle**
   ([ADR 0053](../decisions/0053-isolation-multi-cible-banc-prod.md)) : le
   moteur Python bouclant par phase traverse `_assert_bench_target` /
   `_assert_inventory_safe` **à CHAQUE itération** (+ échappatoire `KUBECONFIG`
   assumée) — sinon un montage banc avec `KUBECONFIG` prod taperait la prod.

## Étapes

> **Honnêteté** : l'étape 1 est **déblocable maintenant** (fix pur, sans ADR).
> Les lots 2-9 sont **gelés** jusqu'à 0096/0097 `Accepted` (invariant
> documentaire,
> [ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) §6).
> Chaque lot cible est re-prouvé par un run banc **puis** prod (invariants 1-2).

### ⭐ Étape 1 — Factoriser le calcul d'état partagé `preview`/`next`/`up` (PREMIER PAS, sans ADR)

La divergence `preview` ≠ `next` vient de **deux blocs copiés-collés** qui
recalculent `done`/`observed`/`a_appliquer` :

- `cmd_preview` (`topology.py:2167-2199`) :
  `done -= {"up","bootstrap"} - observed_socle` ;
  `a_appliquer -= observed_socle` ; soustrait `_observed_layers`.
- `cmd_next` (`topology.py:2522-2562`) : même logique recopiée, recalcul
  **séparé** de `observed_socle`/`observed_layers` — et il **manque** le garde
  `if "up" not in done` que `preview` possède (**VRAI bug**, classe de bug, pas
  instance).

- **Faire** : extraire une **fonction PURE unique**
  `compute_plan_state(topo, seq, target, runs, now, runtime_probe) -> PlanState(done, observed, a_appliquer, freshness)`
  dans [`nestor/plan.py`](../../nestor/plan.py) (à côté de `installable_now` /
  `expected_phase_sequence`), appelée par les **TROIS** commandes
  (`cmd_preview`, `cmd_next`, `cmd_up`). Corrige la **classe** de bug **+** le
  garde manquant. ~30-50 lignes. Application directe de l'enseignement MEMORY.md
  : « `next` et `preview` doivent rendre le même verdict ; soustraire
  `done | observed`, pas l'historique seul ».
- **WIP à reprendre** : un correctif partiel est **stashé sur la branche
  `fix/preview-fidelite-reel`** — il corrige `preview` **et** le signal
  `dataops → marquez`, **mais pas `next`** (les deux blocs sont indépendants).
  L'intégrer ici (la factorisation `next` est le morceau manquant).
- **Preuve (SANS cluster)** : `tests/test_plan.py` (pytest pur) prouve
  `preview == next == up` (même verdict), mono-couche par mono-couche.
  `ruff check .` + `ruff format --check .` (CI globale, MEMORY.md). Risque
  faible, isolé.

### Lot 2 — Graphe figé à côté du bash _(gelé jusqu'à 0096 Accepted)_

- **Faire** : porter `rollback-lib.sh` (partie pure ~600 l., l. 20-665 : graphe
  **+ les 4 dimensions de périmètre** namespace/targeted/crd/nodeside) en
  [`nestor/graph.py`](../../nestor/graph.py) —
  `@dataclass(frozen=True) Component` (cf.
  [ADR 0096](../decisions/0096-graphe-topologie-python-verifie-ansible.md) §1) +
  projections pures (`topo_sort`, `phase_closure`, `phase_of_component`,
  `phase_deps`, `PHASE_COMPONENTS`). Le bash **reste**, on ne bascule **rien**.
- **Preuve** : pytest rejouant
  [`bench/unit/rollback.bats`](../../bench/unit/rollback.bats) → **byte-identité
  prouvée** (invariant 3 : tie-break `%s%03d`, comparaison `\<` reproduite à
  l'octet). Pur, sans cluster.

### Lot 3 — Éliminer les 2 ponts subprocess bash _(gelé)_

- **Faire** : basculer `nestor/layers.py:91` `_rb` (et
  `:144/:172/:178/:211/:238`) ainsi que `nestor/roundtrip.py`
  `_rollback_lib_call` sur `graph.py`. `rollback-lib.sh` ne garde plus que
  l'orchestration kubectl/ssh (l. 718+).
- **Preuve (test sens-unique)** : plus **aucun**
  `subprocess(bash … rollback-lib.sh)` dans `nestor/`. Run banc
  (séquence/rollback inchangés) **puis** prod.

### Lot 4 — Intégrer le signal + aligner `dataops → marquez` _(gelé)_

- **Faire** : `_LAYER_SIGNAL` devient `phase.signal_component` (donnée
  **humaine** portée par le graphe — « est une feuille » ne tranche pas quand
  `dataops` a deux feuilles) ; **corriger** `topology.py:751`
  `dagster-dagster-webserver` → cible **marquez** (**même lot**, sinon le signal
  continue de mentir).
- **Preuve** : le verdict `dataops` reflète Marquez ; run banc **puis** prod.

### Lot 5 — `check_topology.py` + `lint:topology` en CI + hook lefthook _(gelé)_

- **Faire** : créer `scripts/check_topology.py` calqué **ligne à ligne** sur
  [`scripts/check_contract.py`](../../scripts/check_contract.py)
  (`Finding(level, message)`, fonctions pures testées, `_report()` exit 0/1/2).
  **Quatre familles** bloquantes (composant→rôle, rôle→composant « notifieur
  Marquez oublié », signal, cohérence interne). Brancher `pnpm lint:topology` en
  CI (à côté de `pnpm lint:contract`) **et** un **hook lefthook** régénérant /
  vérifiant quand `bootstrap/roles/` change (décision utilisateur).
- **Réserves à coder** (sinon angles morts) : mapping rôle↔composant **non 1:1**
  (`platform-cnpg` porte 4 composants, `platform-s3-bucket` en porte 3) →
  tolérer un rôle multi-composant ET vérifier que **chaque** composant est
  référencé ; scanner les `import_role` **RÔLE→RÔLE** (cas `platform-s3-bucket`,
  jamais importé par un playbook) ; gérer le **multi-import**
  `platform-build-images`.
- **Preuve** : pytest des fonctions pures (`Finding`) ; le check **attrape** un
  rôle ajouté sans composant. CI verte.

### Lot 6 — Moteur de chemin `nestor/path.py` _(gelé — cœur du chantier)_

- **Faire** : créer [`nestor/path.py`](../../nestor/path.py) — une **boucle
  Python** sur `expected_phase_sequence` (`nestor/plan.py:206`) →
  `runner.launch_phase_idempotent` (`nestor/runner.py:176`) +
  `_wait_layer_healthy` (`topology.py:823`), traversant `_assert_bench_target` /
  `_assert_inventory_safe` **à CHAQUE phase** (invariant 6). Généralise le
  patron **éprouvé 2×** (`bootstrap.py:102` + `ha.py`). `cmd_up`/`cmd_next`
  **n'appellent plus** `subprocess([bash, run-phases.sh])`
  (`topology.py:2349, 2406`).
- **Réserve (état partagé)** : `path.py` doit **POSSÉDER** `CP` (=`:83`),
  `API_PORT` (=6443, `:90`), `KUBECONFIG_LOCAL` (`:146`), `REPO`, et
  **absorber** `phase_up` (provisioning VM) + `write_inventory` — chantier plus
  large que « porter `cni.sh` ».
- **Preuve** : run banc from-scratch **puis** prod, idempotence `changed=0` ;
  grep sens-unique `grep -rn 'uv run python\|topology.py' bench/lima/` rend
  **0** (sauf `ha-cni`, allowlisté jusqu'au lot 9).

### Lot 7 — Porter les phases _(gelé)_

- **Faire** : porter d'abord les **~12 phases plateforme triviales**
  (`run_ansible_phase <playbook>`) ; **PUIS, explicitement**, les **harnais
  e2e** que `_wait_layer_healthy` ne couvre **pas** :
  `dataops_chain_emit_and_verify` (~62 l. : Job émetteur **OpenLineage** +
  poll + delta **Marquez**) et `dataops_egress_internet_check` (preuve
  **NetworkPolicy** egress 443).
- **Preuve** : chaque phase prouvée isolément (`nestor next <phase>`) au banc
  **puis** prod ; les harnais e2e re-prouvés (pas supposés triviaux).

### Lot 8 — Paramétrage 100 % YAML + `nestor/seed.py` _(gelé — EXIGENCE UTILISATEUR)_

- **Faire (env → YAML)** : supprimer les **~40 variables d'environnement**
  (`CEPH_BLOCK_DEVICE`, `CEPH_HDD_GLOB`, `HA_VIP`, `HA_VIP_IFACE`,
  `CILIUM_CLUSTER_*`, `GITEA_ORG_*`, `GITEA_NS`, `EXPECTED_CLUSTER`,
  `BANC_JETABLE`, `HARDENING_TAGS`, `ATLAS_REPO_DIR`, `CITATION_*`, `PORTAL_*`,
  `SEUIL_JOURS`…) au profit du **YAML de topologie**
  ([`topologies/*.yaml`](../../topologies/) porte déjà
  `catalog`/`nodes`/`storage`/`layers`/`target_kind`/`kubeconfig`). `nestor` lit
  la config du **YAML**, plus de l'env. **Exception** : `KUBECONFIG` (sémantique
  d'override « intention explicite assumée », documentée).
- **Faire (commande `env`)** : **SUPPRIMER `nestor env`** (elle imprimait
  `export KUBECONFIG=<banc>` à `eval` — l'incarnation du paramétrage-par-env). À
  la place, `nestor` **maintient des contextes nommés dans `~/.kube/config`**
  (`banc`, `dirqual`…) dérivés du champ `kubeconfig` du YAML ; l'opérateur fait
  `kubectl --context <topo>` (mécanisme standard k8s, zéro env). Les **autres
  annexes restent** (`access`/`scale`/`discover`/`refresh`/`artifact`/`test`).
  Mettre à jour le menu d'aide + retirer
  [`bench/lima/env.sh`](../../bench/lima/env.sh).
- **Faire (seed)** : porter `nestor/seed.py` —
  [`gitea-init.sh`](../../bench/lima/gitea-init.sh) (207 l.) +
  [`seed-app-of-apps.sh`](../../bootstrap/seed-app-of-apps.sh) (595 l.).
  **Garder les DEUX gardes opposés** : `_assert_bench_target` (banc) **vs**
  `assert_prod_target` (prod, défaut `~/.kube/<topologie>.config`). Un module
  mal gardé taperait dirqual.
- **Preuve** : montage piloté **uniquement** par le YAML (aucune var d'env hors
  `KUBECONFIG`) ; seed `--dry-run` propre ; run banc **puis** prod.

### Lot 9 — HA en dernier (exception nommée) _(gelé)_

- **Faire** : `run_ha_3cp` (`run-phases.sh:1607`) + le rappel
  `topology.py ha-3cp` (`:1650`) restent une **exception** jusqu'à leur PR
  dédiée. La façade Python doit couvrir `run_cni` **ET** `fetch_kubeconfig_node`
  (2ᵉ geste de `phase_ha_cni`) — sinon `ha-cni` reste appelé pour le kubeconfig
  (circularité résiduelle).
- **Allowlist** : le test grep sens-unique **allowliste `ha-cni`** jusqu'à cette
  PR (aujourd'hui le grep rend 508 ET 1650 ; le lot 6 retire 508, le lot 9
  retire 1650).
- **Preuve** : la circularité disparaît entièrement après ce lot ; run banc HA
  3-VM (cf. [`plan-ha-3cp-control-plane.md`](plan-ha-3cp-control-plane.md)).

## Stratégie de preuve

- **Étape 1 — prouvable MAINTENANT, sans cluster** : `tests/test_plan.py`
  (pytest pur) prouve `preview == next == up` (même verdict, mono-couche par
  mono-couche) + garde manquant restauré. `ruff check`/`ruff format --check`
  globaux verts.
- **Lots cible (2-9) — banc d'abord, prod ensuite** : chacun prouvé **d'abord au
  banc** (run from-scratch consigné dans
  [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md), idempotence
  `changed=0`) **PUIS** sur dirqual (prod) — un lot n'est « fait » que sur **les
  deux** (invariants 1-2). La **byte-identité** des portages est prouvée par
  test (invariant 3 : `rollback.bats` → pytest).
- **Honnêteté** : le check de parité (lot 5) est **NÉCESSAIRE mais PAS SUFFISANT
  seul** — les énumérations de phases vivent à **6 endroits**
  (`rollback-lib.sh`, `nestor/layers.py`, `_LAYER_SIGNAL`, `KNOWN_PHASES`,
  `PHASE_PLAYBOOK`+labels, Ansible). Un « Marquez » retiré d'un **label** ou de
  `KNOWN_PHASES` passerait sous le radar. La robustesse durable exige de
  **FUSIONNER** ces tables comme projections du graphe unique (cible des lots
  2-6), **pas seulement** d'ajouter le check à côté.
- **Estimation : 8-12 PR**, chacune re-prouvée par un run banc from-scratch
  (puis prod) consigné
  ([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md) /
  [ADR 0052](../decisions/0052-reproductibilite-des-resultats.md)) + rejeu
  `changed=0`.

## Risques

| #         | Risque                                                         | Lot   | Mitigation / réserve                                                                                                                                                             |
| --------- | -------------------------------------------------------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R-CNI     | **Œuf-poule CNI** — la circularité **EXISTE aujourd'hui**      | 6 / 9 | « `cni.sh` reste bash sans circularité » est une **CIBLE** ; le chemin actuel est circulaire (`:508 → bootstrap-seq → run_cni → ha-cni`). Ne tient qu'**après** le lot 6.        |
| R-ÉTAT    | État shell → Python **sous-estimé**                            | 6     | `path.py` doit **posséder** `CP`/`API_PORT`/`KUBECONFIG_LOCAL` **et absorber** `phase_up` (provisioning) + `write_inventory` — sinon Python re-rappelle bash, circularité.       |
| R-AMPLEUR | Ampleur `run-phases.sh` **1903 l.** — limite basse optimiste   | 6-8   | `path.py` (~400-600 l. neuf) + `seed.py` (~800 l.) + démêlage `bootstrap-seq`/`ha-cni` non triviaux. « Risque faible » vaut pour les ~12 phases plateforme, pas les harnais e2e. |
| R-CADENCE | **Mono-mainteneur** — coût-temps réel non-LOC                  | tous  | Chaque PR exige un run banc from-scratch consigné. Pattern éprouvé 2×, chaque phase se prouve isolément (`nestor next <phase>`) → risque faible, **cadence lente**.              |
| R-GARDE   | Garde d'isolation tournée **une seule fois** (faille ADR 0053) | 6     | Invariant de boucle (invariant 6) : `_assert_bench_target` traversée à **chaque** phase + échappatoire `KUBECONFIG` — sinon montage banc avec `KUBECONFIG` prod tape la prod.    |
| R-CHECK   | Check **NÉCESSAIRE pas SUFFISANT** (6 énumérations)            | 5     | **Fusionner** les 6 tables comme projections du graphe (lots 2-6), pas juste un check à côté. Angles morts : `redcap.yaml` orphelin, multi-import `platform-build-images`.       |

## Suivi

> **Avancement (2026-06-25)** : Étape 1 + lots 2-5 **mergés** (PR #508, #509).
> Le graphe figé Python vérifié contre Ansible — le cœur de la refonte — est en
> place et `check_topology` garde la cohérence en CI. **Restent les lots 6-9**
> (moteur `path.py`, portage, env→YAML, HA), qui touchent le **montage réel** et
> exigent donc un **run banc**
> ([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)) — une PR par
> lot, en session banc dédiée.

- [x] **Étape 1** — `compute_plan_state` extraite dans `nestor/plan.py`, appelée
      par `cmd_preview`/`cmd_next`/`cmd_up` + garde `if "up" not in done`
      restauré dans `next` ; `tests/test_plan.py` prouve `preview == next == up`
      ; WIP `fix/preview-fidelite-reel` intégré (incluant `dataops → marquez`).
      `ruff` verts. **(déblocable sans ADR)**
- [x] **Lot 2** — `nestor/graph.py` à côté du bash ; byte-identité prouvée
      (`rollback.bats` → pytest). _(gelé jusqu'à 0096 Accepted)_
- [x] **Lot 3** — ponts `layers._rb` + `roundtrip._rollback_lib_call` basculés
      sur `graph.py` ; plus aucun `subprocess(rollback-lib.sh)` dans `nestor/` ;
      banc + prod. _(gelé)_
- [x] **Lot 4** — `phase.signal_component` + `dataops → marquez` corrigé
      (`topology.py:751`) ; banc + prod. _(gelé)_
- [x] **Lot 5** — `check_topology.py` (4 familles, scan `import_role`
      rôle→rôle) + `pnpm lint:topology` CI + hook lefthook `bootstrap/roles/`.
      _(gelé)_
- [ ] **Lot 6** — moteur `nestor/path.py` ; `cmd_up`/`cmd_next` n'appellent plus
      `run-phases.sh` ; grep sens-unique = 0 (sauf `ha-cni`) ; banc
      from-scratch + prod, `changed=0`. _(gelé)_
- [ ] **Lot 7** — ~12 phases plateforme triviales **puis** harnais e2e
      (`dataops_chain_emit_and_verify`, `egress_check`) ; banc + prod. _(gelé)_
- [ ] **Lot 8** — env → YAML (~40 variables supprimées, exception
      `KUBECONFIG`) + `nestor/seed.py` (gardes opposés banc/prod) ; banc + prod.
      _(gelé)_
- [ ] **Lot 9** — HA exception nommée levée (`run_ha_3cp` + `ha-cni` portés) ;
      allowlist grep retirée ; circularité éteinte ; banc HA + prod. _(gelé)_
