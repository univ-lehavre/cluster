# Plan — renommer `test/` → `bench/` (et clarifier `bootstrap/`)

## État

**Actif** (2026-06-15). Fonde :
[ADR 0070](../decisions/0070-renommer-test-en-bench-bootstrap-plat.md). Issues :
_(à créer)_.

Périmètre : renommage du dossier banc `test/` → `bench/` + ré-indexation de
`bootstrap/README.md`. Le dossier `tests/` (pytest) **ne bouge pas**. Les
playbooks `bootstrap/*.yaml` **ne bougent pas**.

## Objectif

Supprimer la collision `test/` (banc Lima E2E) / `tests/` (pytest) en renommant
le banc en `bench/`, mot déjà employé partout dans la prose et l'outillage
(`just bench`, `docs/banc-local.md`, `bench-freshness.yml`). PR **atomique** :
`git mv` + réécriture de toutes les références, en un seul commit logique, pour
qu'aucun état intermédiaire ne casse la CI ni les liens VitePress.

## Surface mesurée (2026-06-15)

| Catégorie                                               | Volume                           |
| ------------------------------------------------------- | -------------------------------- |
| Fichiers **externes** à `test/` à éditer (hors RESULTS) | **152 fichiers**                 |
| Fichiers **internes** à `test/` à réécrire (post mv)    | **57 fichiers**                  |
| Fichiers `RESULTS.md` (banc + lima) — **NON réécrits**  | 2 (contenu historique, ADR 0023) |

> Le compte se vérifie par le `grep` de non-régression de l'étape 4. Recompter
> avant de commencer (l'arbre bouge) :
> `grep -rln -E '(^|[^a-zA-Z_/.])test/' . --include='*.md' --include='*.sh' --include='*.py' --include='*.yaml' --include='*.yml' --include='*.json' --include='*.toml' --include='Justfile' --exclude-dir={node_modules,.venv,.git,__pycache__,dist,cache,artifacts,.work} | grep -vE '/tests?/'`

## Étapes

### 1. `git mv` du dossier

```sh
git mv test bench
```

L'historique de chaque fichier suit le renommage. Les sous-dossiers
(`bench/lima/`, `bench/scenarios/`, `bench/spikes/`, `bench/unit/`) sont
préservés tels quels.

### 2. Réécrire les références — par zone

Réécriture mécanique `test/` → `bench/` (frontière de mot : ne PAS toucher
`tests/`, ni `.pytest_cache`, ni les `*.bench.yaml` de `platform/` qui sont des
**fichiers** sans rapport avec le dossier). Procéder zone par zone et relire les
diffs « gros consommateurs » à la main.

**2.1 — Config racine & outillage (pièges, à éditer à la main) :**

- [ ] `.gitignore` — lignes **55-58, 62-63, 66** : `test/**/.vagrant/`,
      `test/**/inventory.yaml`, `test/**/*.vdi`, `test/*.log`,
      `!test/lima/runs/`, `!test/lima/runs/*.log`, `test/**/.work/` → préfixe
      `bench/`.
- [ ] `.prettierignore` — ligne **36** `test/lima/runs-history.yaml` (+
      commentaire l.35).
- [ ] `.trivyignore.yaml` — 2 refs.
- [ ] `.yamllint.yaml` — 1 ref.
- [ ] `lefthook.yml` — 2 refs.
- [ ] `lychee.toml` — 1 ref.
- [ ] `package.json` — `test:shell` (`bats test/unit/` → `bats bench/unit/`)
      **et** dans `lint:k8s` les exclusions `:!:test/*/inventory.yaml` et
      `:!:test/lima/runs-history.yaml`. ⚠️ Ne PAS toucher les exclusions
      `*.bench.yaml` (fichiers de valeurs Helm, sans rapport). Les clés npm
      `test:shell`/`test:python` **gardent leur nom** (convention npm) ; seuls
      leurs chemins internes changent.
- [ ] `Justfile` — 3 refs (cible `bench` → `bench/lima/run-phases.sh`,
      `bench-destroy`, commentaire l.102).

**2.2 — CI :**

- [ ] `.github/workflows/bench-freshness.yml` — 3 refs
      (`bench/lima/check-freshness.sh`, `bench/lima/runs-history.yaml`,
      `bench/lima/run-phases.sh`).
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` — 1 ref.

**2.3 — Outil topologie (Python) — chemins par défaut & docstrings :**

- [ ] `scripts/topology.py` (4), `cluster_topology/history.py` (3),
      `cluster_topology/epreuves.py` (2), `cluster_topology/metrics.py` (1),
      `cluster_topology/plan.py` (1), `cluster_topology/__init__.py` (1). ⚠️
      Vérifier les **valeurs par défaut** de chemins (`test/lima/…`) — un défaut
      oublié fausse silencieusement le runner.

**2.4 — Tests unitaires pytest (chemins en dur dans les assertions) :**

- [ ] `tests/test_epreuves.py` (3), `tests/test_cluster_topology.py` (2),
      `tests/test_check_md_orphans.py` (2), `tests/test_parity.py` (1),
      `tests/test_history.py` (1). Ces fichiers **restent dans `tests/`** ;
      seules leurs chaînes `"test/…"` deviennent `"bench/…"`.

**2.5 — Docs (gros volume) :** `docs/outils.md` (17), `docs/dev-atlas.md` (10),
`docs/audit/2026-05-29/02-tests.md` (10), `docs/banc-local.md` (8),
`docs/architecture/plan-de-tests.md` (8),
`docs/architecture/matrice-catalogue.md` (8),
`docs/architecture/registre-drifts.yaml` (6), plans, et ~40 ADR (1-7 refs
chacun). README.md (3), CONTRIBUTING.md (6), SAFEGUARDS.md (5), CLAUDE.md (2),
CHANGELOG.md (2). Le tableau « Structure » du README et le tableau « Par où
commencer » mentionnent `test/` → `bench/`.

**2.6 — Manifestes / rôles / divers :** `bootstrap/state.sh` (2),
`bootstrap/lib/health-classify.sh` (2), `bootstrap/RUNBOOK.md` (2),
`bootstrap/cni.sh`, `bootstrap/gitops.yaml`, 5
`bootstrap/roles/*/tasks/main.yaml`, `bootstrap/hosts.example.yaml`,
`bootstrap/group_vars/dataops.example.yaml`, `storage/**`, `platform/**`
README + `platform/argocd/_test/…`, `contract/storage-classes.example.yaml`.

**2.7 — Fichiers DANS `bench/` (post-mv, 57 fichiers) :** chemins en dur
auto-référents dans `bench/lima/run-phases.sh` (42 !), `bench/lima/README.md`
(28), `bench/scenarios/README.md` (16), `bench/lima/access.sh`, `metrology.sh`,
`env.sh`, `lib.sh`, `rollback-lib.sh`, les 30 scénarios `bench/scenarios/*.sh`,
`bench/spikes/clustermesh-latency/*`, etc. → `test/` interne devient `bench/`.

### 3. Exceptions — à NE PAS réécrire

- [ ] **`bench/RESULTS.md`** et **`bench/lima/RESULTS.md`** : contenu
      **historique** (runs datés, `test/multi-node/` Vagrant déprécié inclus) —
      honnêteté des Runs,
      [ADR 0023](../decisions/0023-plateforme-exemple-generique.md). Le fichier
      suit le `git mv` ; son **contenu reste tel quel**. Seules les **futures**
      entrées emploieront `bench/`.
- [ ] **`docs/decisions/0070-…md`** : les `test/` y décrivent l'**état avant**
      le renommage — les laisser.
- [ ] Les `*.bench.yaml` de `platform/` (valeurs Helm) et `.pytest_cache` : sans
      rapport, ne pas toucher.

### 4. Validation (avant push)

- [ ] **Non-régression** — zéro `test/` résiduel hors exceptions :

  ```sh
  grep -rn -E '(^|[^a-zA-Z_/.])test/' . \
    --include='*.md' --include='*.sh' --include='*.py' --include='*.yaml' \
    --include='*.yml' --include='*.json' --include='*.toml' --include='Justfile' \
    --exclude-dir={node_modules,.venv,.git,__pycache__,dist,cache,artifacts,.work} \
    | grep -vE '/tests/|RESULTS\.md|0070-renommer'
  ```

  Doit être **vide**.

- [ ] `pnpm lint` (format, yamllint, shellcheck, kubeconform, ansible-lint,
      jscpd, bats).
- [ ] `pnpm docs:build` (VitePress échoue sur lien mort — détecte un
      `[..](test/…)` oublié).
- [ ] **markdownlint** + **trivy** (jobs CI séparés — reproduire localement, cf.
      CLAUDE.md).
- [ ] `uv run python -m unittest discover -s tests` (les assertions de chemins).
- [ ] `just --list` puis `just bench --help` (ou un dry-run) — la cible pointe
      bien `bench/lima/`.
- [ ] `check:gouvernance` / `check_md_orphans` si présent (orphelins de doc).

### 5. Commit & PR

- Un commit `refactor(bench): renommer test/ en bench/ (ADR 0070)` — la
  stratégie **merge-commit** (ADR 0037) préserve l'historique fin ; commit
  propre et atomique.
- Sujet **en minuscules** (commitlint `subject-case`), sans email /
  `Co-Authored-By`.
- Ajouter la ligne **0070** à `docs/decisions/README.md` (index ADR).
- Ajouter ce plan à `docs/plans/README.md` (index des plans).

## Volet `bootstrap/` — ré-indexer, ne PAS déplacer

Conformément à
[ADR 0070](../decisions/0070-renommer-test-en-bench-bootstrap-plat.md) («
corriger le code, pas l'état »), les playbooks restent à plat. Une seule action
de lisibilité :

- [ ] **Réordonner le tableau de `bootstrap/README.md` par phase**, avec
      sous-titres : **Installation** (`checks` → `cri` → `kubeadm` →
      `control-planes` → `initialisation` → `cni.sh`) · **Extension HA / join**
      (`kube-vip`, `join-control-plane`, `join-workers`) · **Storage &
      platform** (`local-path`, `ceph-*`, `metrics-server`, `monitoring`,
      `gitops`, `dataops`, `cnpg-secrets`) · **Ops & maintenance**
      (`os-upgrade`, `k8s-upgrade`, `etcd-backup`, `etcd-fetch`,
      `audit-log-baseline`, `rollback`, `state.sh`). L'ordre canonique
      d'exécution reste le RUNBOOK.
- [ ] Une ligne dans `topologies/README.md` (ou `docs/`) clarifiant les **quatre
      « topology »** : `cluster_topology/` (paquet, logique pure),
      `scripts/topology.py` (façade CLI), `topologies/` (catalogue de données),
      `topology.yaml` (symlink d'activation). Friction relevée à l'audit, hors
      périmètre du renommage mais bon compagnon de PR.

> **Pas** de préfixe numérique sur les playbooks, **pas** de déplacement en
> sous-dossiers : ~60 références littérales (`plan.py`, banc, Justfile, tests,
> ADR) en dépendent et l'ordre vit déjà dans le DAG des couches
> ([ADR 0069](../decisions/0069-topology-layers-dag-grain-phase.md)).
