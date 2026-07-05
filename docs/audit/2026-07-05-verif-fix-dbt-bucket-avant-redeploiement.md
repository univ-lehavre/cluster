# Passage d'audit — vérification adversariale du fix dbt (bucket) avant redéploiement prod

> **Type** : passage d'audit ciblé (ADR 0058) — angle « le fix `build_dbt_vars`
> est-il correct, suffisant côté code atlas, et sans régression, avant de le
> committer + redéployer sur prod ? », pas la grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : suite du passage
> [aval citation](2026-07-05-aval-citation-bugs-config-prod.md), qui désignait
> `build_dbt_vars` (racines S3 non dérivées de `BUCKET_NAME`) comme le blocage
> unique de la chaîne aval. Le fix est écrit ; avant de le pousser en prod, on
> le passe au crible — application concrète de la « gate de config » recommandée
> par le passage doctrine
> [le banc Lima vaut-il le coup ?](2026-07-05-banc-lima-vaut-il-le-coup.md).
>
> **Méthode** : éventail multi-agents (3 skeptics adversariaux, chacun mandaté
> pour **réfuter** le fix sous une lentille) + critique de complétude + synthèse
> go/no-go. Vérification ligne par ligne sur le code atlas (aucune invention).

## Verdict — **GO**

Le fix `build_dbt_vars` (branche `fix/citation-dbt-bucket-roots`, atlas) est
**correct, suffisant côté CODE ATLAS, et bench-neutre**. **Aucun finding
bloquant.** Les 3 skeptics ont tous conclu `refuted=false, severity=none`. Tous
les gaps E2E restants sont des **gestes déployeur/cluster** ou des **conditions
de preuve non-code** : ils n'empêchent pas le commit/PR/redéploiement, mais
doivent être validés avant de déclarer l'E2E vert.

## Ce qui est prouvé correct (3 lentilles adversariales)

### 1. runtime-env-present — pas de crash au démarrage/lint, pas de 404 silencieux

- `build_dbt_vars` n'est appelé **que** dans le corps de l'asset `@dbt_assets`
  (`dbt.py:125`, `# pragma: no cover`), **jamais à l'import** → importer
  `definitions` (démarrage gRPC, lint, collecte pytest) ne déclenche pas
  `ceph_target_from_env()` → la code-location reste chargeable.
- Le `dbt parse` du build image (et le parse paresseux `ensure_manifest`)
  n'appelle **pas** `build_dbt_vars` : il shelle le CLI dbt avec des creds S3
  factices (`_DUMMY_PARSE_ENV`, sans `BUCKET_NAME`) → le fix ne casse pas le
  parse hermétique.
- Dans le pod de run de `transform_job`, `BUCKET_HOST/PORT/NAME` + `AWS_*` sont
  injectés via `_s3_env_from()` (`definitions.py:94-107`), branché par l'overlay
  prod `patch-s3-envfrom.yaml:34-37` (`CITATION_S3_SECRET` +
  `CITATION_S3_CONFIGMAP=citation-datalake`) → `ceph_target_from_env()` ne lève
  pas. Le seul job sélectionnant les assets dbt est `transform_job` (qui porte
  cet `env_from`) ; `ingestion_job` ne sélectionne que `raw_snapshot` ; les
  sensors avalent `ceph_target_from_env` en `try/except → SkipReason`. **Aucun
  chemin ne matérialise l'asset dbt sans `BUCKET_NAME`.** Un overlay mal câblé
  lèverait un `MissingEnvError` clair plutôt qu'un 404 silencieux — **net
  progrès**.

### 2. dbt-vars-coverage — couverture S3 complète

- Les 3 racines injectées (`raw_root`/`curated_root`/`marts_root`) sont les
  **seules** vars de chemin S3 du projet dbt (grep exhaustif models+macros).
  Aucun `s3://` codé en dur dans un modèle. Les 12 modèles externes passent tous
  par `curated_location()`/`marts_location()`.
- Les marts « servis » (researchers, researchers_fts, author_profiles, collab)
  résolvent via `marts_root` ; `index_load`/`quality` les relisent au même
  préfixe dérivé de `BUCKET_NAME`.
- Les assets Python aval (`researcher_embeddings`, `uplift`, `index_load`,
  `drift`, `drift_uplift`, `manifest`, `quality`) dérivaient **déjà** le bucket
  de `ceph_target_from_env()`/`duckdb_s3_config_from_env()` (== `BUCKET_NAME`),
  jamais `s3://citation` en dur. Leurs sous-dossiers (`curated/…`, `marts/…`)
  coïncident avec `<root>/<model>` des macros → **adressage S3 cohérent
  bout-en-bout** dans un `transform_job` mono-run (même `context.run_id` → même
  préfixe `dt=…/run=…`).

### 3. bench-parity-and-tests — zéro régression banc, tests solides

- Banc (`BUCKET_NAME=citation`, `overlays/bench/s3-access.yaml:21`) → les 3
  racines dérivées **égalent** les défauts pré-fix (`dbt_project.yml:31/33`,
  macros) → **aucune régression banc**.
- Le smoke hermétique `test_dbt_models.py` construit ses propres `--vars` en
  sous-process (dont les 3 roots) et n'appelle pas `build_dbt_vars` → **pas de
  double-injection**. Le fix aligne juste le chemin `@dbt_assets` de prod sur ce
  que le smoke faisait déjà.
- Tests : avec dbt sur le PATH, `test_dbt.py` = **9 passed** (baseline 8, + le
  test de contrat neuf), `test_resources.py`+`test_collab_manifest.py` = 17
  passed. Suite complète `citation-dagster` = **212 passed, couverture 91,17 %**
  (gate 90 % atteinte), `dbt.py` à **100 %**. Le test de contrat
  `test_build_dbt_vars_derives_s3_roots_from_bucket_name` est genuine (override
  `BUCKET_NAME`, assertions sur les 3 roots), non tautologique.

## Points non bloquants (notés, pas des bugs)

- **`curated_root` absent du bloc `vars:` de `dbt_project.yml`** (contrairement
  à `raw_root`/`marts_root`) ; son seul défaut vit dans
  `macros/curated_location.sql:23`. Cosmétique/pré-existant : le run injecte
  toujours `curated_root`, donc aucun effet runtime prod. Optionnel : l'ajouter
  au bloc `vars:` pour la symétrie.
- **Piège d'invocation locale** (pas un défaut du code) : lancer `pytest` sans
  `.venv/bin` (dbt) sur le PATH fait échouer `test_definitions_module_loads…` et
  `test_dbt_components_nominal…` sur « dbt executable does not exist »
  (construction de `DbtCliResource`), sans rapport avec `build_dbt_vars` ni
  régression. Avec dbt sur le PATH : 9 passed. La CI a dbt dans l'image →
  utiliser `uv run pytest`.
- **`CURATED_DT` figé à `'0000-00'`** (`dbt.py:60`) : paramètre d'instance
  provisoire, pas un bug ; les runs se distinguent par `run=<run_id>`, pas par
  `dt`. Conditionne la lecture des preuves de drift (N vs N-1 sous le même
  `dt=0000-00`).

## Gaps E2E restants — TOUS des gestes déployeur/cluster (aucun code atlas)

À valider **avant de déclarer l'E2E vert**, mais sans impact sur le commit/PR :

1. **Secret dérivé `pgvector-pg-auth`** (clés `username`/`password`, recopie de
   `pg-role-pgvector`) dans le ns `dagster` — sinon `_TRANSFORM_ENV` ne mappe
   pas `POSTGRES_USER/PASSWORD` et `index_load` **lève** via
   `postgres_target_from_env`.
2. **Migration du schéma d'index** appliquée à la db `pgvector` (table
   `researchers(researcher_id, embedding vector, fts tsvector, dt, run)` +
   extension pgvector) **avant** le run : `index_load` fait INSERT/DELETE mais
   ne crée ni schéma ni extension (hors périmètre, `index_load.py:20-22` ;
   `0001_researchers_index.sql`).
3. **DNS/NetworkPolicy pgvector** : db joignable en **nom court**
   `pg-rw.postgres:5432` depuis le ns dagster (piège FQDN prod) + egress
   pod-de-run(dagster) → CNPG(postgres).
4. **Overlay prod S3** : `CITATION_S3_SECRET` +
   `CITATION_S3_CONFIGMAP=citation-datalake` sur le Deployment gRPC (**vérifié
   présent** dans le code, `patch-s3-envfrom.yaml:34-37` ; déjà prouvé en prod
   via l'ingestion #540). Sans lui, `ceph_target_from_env` lève et le fix ne
   peut pas dériver le bucket.
5. **Armement du déclenchement** : `transform_job` doit s'exécuter
   (`transform_daily` + sensor `transform_on_watermark_advance` STOPPED par
   défaut, ADR 0062 ; ou re-trigger manuel ; ou `retrain_on_drift` RUNNING par
   défaut).
6. **Egress MLflow/Marquez** (`mlflow.mlflow:5000`, `marquez.marquez:5000`) :
   sinon `_log_to_mlflow`/`lineage.emit` tombent en **no-op SILENCIEUX** (run
   SUCCESS mais HTML Evidently + lineage non émis).
7. **Preuve d'un vrai drift Evidently** : exige **2 runs** transform au même
   `dt=0000-00` — au 1er run, `passed=True, baseline absente` (aucun N-1). Geste
   opérateur, pas du code.
8. **Volume/qualité des données prod** : pour que `curated_pair_uplift_labels`
   produise assez de paires (≥2 co-pubs avec baseline solo antérieure des deux
   côtés), sinon `uplift_model.evaluate_grouped` bascule en repli
   **`descriptive`** — run VERT mais **pas un modèle entraîné prédictif**.
   Condition de données à qualifier lors de la preuve, pas un bug.

## Manques → suite

- Commit + PR atlas du fix (`fix/citation-dbt-bucket-roots`) — **GO**.
- Redéploiement prod (`nestor next` : build → digest → `dirqual.yaml` → seed).
- Valider les prérequis déployeur 1–4 **avant** le run, puis armer (5) et
  prouver le transform E2E (dbt → marts → embeddings → uplift → Evidently/MLflow
  → index_load pgvector), en tenant compte de 6–8.
