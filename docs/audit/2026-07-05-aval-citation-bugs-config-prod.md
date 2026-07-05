# Passage d'audit — aval citation : bugs de config prod (vérification adversariale)

> **Type** : passage d'audit ciblé (ADR 0058) — angle « pourquoi la chaîne
> citation cale APRÈS l'ingestion, jusqu'au modèle entraîné + Evidently », pas
> la grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : l'ingestion OpenAlex est prouvée bout-en-bout sur prod
> dirqual (`RUN_SUCCESS`), mais le transform (dbt → embeddings → uplift →
> Evidently) n'a jamais tourné. Question : combien de bugs restent en aval, et
> un seul lot de fix suffit-il ?
>
> **Méthode** : éventail multi-agents (3 cartes de findings) + **vérification
> adversariale** (chaque bug proposé confirmé/réfuté ligne par ligne sur le code
> atlas).
>
> **Contexte banc↔prod** : ce passage est le post-mortem factuel qui fonde le
> passage doctrine
> [le banc Lima vaut-il le coup ?](2026-07-05-banc-lima-vaut-il-le-coup.md).

## Verdict — un seul bug racine de code atlas

Les 3 cartes de findings convergent : **il n'y a qu'UN SEUL bug de code atlas à
corriger en aval. Tout le reste en découle.**

| #     | Bug                                                                                                                                                                                                                         | Fichier                                                      | Fix                                                                                                           |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| **1** | `build_dbt_vars` n'injecte pas `raw_root`/`curated_root`/`marts_root` → dbt retombe sur les littéraux `s3://citation/…` (bucket **banc**), inexistant en prod → RGW 404 sur toute lecture staging + écriture curated/marts. | `dataops/citation-dagster/src/citation_dagster/dbt.py:74-78` | Dériver les trois roots de `BUCKET_NAME` (même source que les assets Python) et les ajouter au dict retourné. |

### Preuve (chaîne complète)

- `dbt.py:74-78` — `build_dbt_vars` retournait UNIQUEMENT `curated_dt`,
  `curated_run`, `opposition_pairs`. **Aucun des trois `*_root`.**
- `dbt.py:120-121` — le run fait `dbt build --vars <json>` avec ce dict amputé ;
  les roots ne sont donc jamais surchargés au run.
- Fallback aux littéraux : `dbt_project.yml:31` `raw_root: "s3://citation/raw"`,
  `:33` `marts_root: "s3://citation/marts"` ; `macros/curated_location.sql:23`
  et `macros/marts_location.sql:20` défaut `"s3://citation/…"`. `curated_root`
  n'est même pas déclaré dans `vars:` (seul le défaut du macro existe).
- Lecture staging : `models/staging/_staging__sources.yml:24,28,32` —
  `read_json_auto('{{ var('raw_root') }}/works/**/*.gz', …)`.
- **Divergence prouvée** : tous les assets Python composent `s3://{bucket}` avec
  `bucket = BUCKET_NAME` (OBC) — `index_load.py`, `uplift.py`,
  `researcher_embeddings.py`, `drift.py`, `manifest.py`, `raw_snapshot.py` ;
  `resources.py:56` `bucket = _require(env, "BUCKET_NAME")` (jamais `citation`
  en dur).
- **Le banc MASQUE le bug** : `deploy/overlays/bench/s3-access.yaml:21` pose
  `BUCKET_NAME: citation` → les littéraux `s3://citation/…` coïncident au banc.
  En prod, `deploy/overlays/prod/patch-s3-envfrom.yaml` branche le ConfigMap OBC
  `citation-datalake` (`BUCKET_NAME=citation-datalake-<hash>`) → les littéraux
  pointent un bucket **inexistant** → RGW `NoSuchBucket` / HTTP 404.
- **Intention de surcharge PROUVÉE par le test** : `test_dbt_models.py:74-81` —
  le harnais injecte explicitement `raw_root`/`curated_root`/`marts_root` =
  `f"s3://{minio.bucket}/…"`. C'est exactement ce que `build_dbt_vars` doit
  faire et ne faisait pas.

**Symptôme prod exact** : le brut est écrit par `raw_snapshot` sous
`BUCKET_NAME/raw/` ; dbt lit `s3://citation/raw/` (vide/`NoSuchBucket`) → échec
au premier `read_json_auto` staging ; toute écriture curated/marts va dans le
bucket fantôme `citation`. Les deux moitiés (dbt vs Python) sont sur deux
buckets différents.

### Fix appliqué (2026-07-05)

```python
# en tête : from citation_dagster.resources import ceph_target_from_env
def build_dbt_vars(run_id: str, curated_dt: str) -> dict[str, str]:
    bucket = ceph_target_from_env().bucket   # == BUCKET_NAME (OBC en prod)
    return {
        "raw_root": f"s3://{bucket}/raw",
        "curated_root": f"s3://{bucket}/curated",
        "marts_root": f"s3://{bucket}/marts",
        "curated_dt": curated_dt,
        "curated_run": run_id,
        "opposition_pairs": os.environ.get("OPPOSITION_PAIRS", "[]"),
    }
```

`build_dbt_vars` est appelé dans le corps `@dbt_assets` (run pod), où
`BUCKET_HOST/PORT/NAME` sont présents via `_s3_env_from` →
`ceph_target_from_env()` ne lève pas. Les littéraux `s3://citation/…` de
`dbt_project.yml`/macros restent comme défauts **inertes** de `dbt parse`/dev.
Doublé d'un **test de contrat**
(`test_build_dbt_vars_derives_s3_roots_from_bucket_name`) qui franchit l'écart
banc/prod que le smoke hermétique (bucket `citation`) ne voit pas.

## Symptômes (confirmés comme conséquences, PAS des bugs distincts)

- **`drift.py` « baseline absente » pour toujours** — `drift.py` est
  correctement câblé ; il rapporte l'absence de baseline uniquement parce que
  dbt a écrit les vecteurs ailleurs. Aucun fix propre à `drift.py`.
- **`index_load.py` « manifest absent »** — échoue à `_validate_artifact` parce
  que les manifests dbt sont dans le mauvais bucket. Le câblage pgvector est
  correct (nom court `pg-rw.postgres`, secret `pgvector-pg-auth`,
  `_TRANSFORM_ENV` au run pod).
- **`manifest.py` « Aucune part Parquet »** — liste sous `BUCKET_NAME/<subdir>`
  où dbt n'a rien écrit. Le `rcat` (write) est correct.

## Réfutés (NE PAS fixer)

- **« no-op MLflow »** → **RÉFUTÉ.** `MLFLOW_TRACKING_URI` est set en prod
  (`drift.py:100-101`, `tracking.py:107-108/132-133` gardent sur
  `config is None` dérivée de la présence de l'URI). MLflow logge réellement
  (runs uplift + registry embeddings + rapport Evidently HTML).
- **« `DBT_S3_USE_SSL` absent = mauvais »** → **RÉFUTÉ.** `profiles.yml:25`
  défaut `'false'`, correct pour RGW HTTP :80.
- **`region: us-east-1` littéral** → **RÉFUTÉ.** Ignoré en path-style RGW.
- **`BUCKET_PORT` défaut `'8333'` vs `'80'`** → **RÉFUTÉ.** Prod pose
  `BUCKET_PORT=80` via le ConfigMap OBC → le défaut ne s'applique jamais.
  Divergence inerte.
- **`no_check_bucket` / chemin `data/jsonl`** → hors périmètre (déjà corrigés,
  #540/#539).

## Ordre de dépendance (chaîne strictement linéaire, débloquée par le fix racine)

```text
dbt (BUG-1 fix) ─┬─> staging lit BUCKET_NAME/raw          [aujourd'hui 404]
                 └─> écrit curated_* + marts_* sous BUCKET_NAME
                          │
                          ├─> researcher_embeddings → marts/researcher_vectors
                          │        ├─> pair_uplift_model → prédictions/recos
                          │        └─> evidently_embedding_drift → verdict S3 + MLflow
                          │
                          └─> manifests → index_load valide + charge pgvector
```

Aucun de ces étages n'a de bug propre : tous lisent/écrivent déjà `BUCKET_NAME`.
Ils sont juste **affamés** par dbt.

## Ce lot suffit-il jusqu'au modèle entraîné + Evidently ?

**Oui — ce fix unique débloque toute la chaîne applicative atlas jusqu'au modèle
uplift entraîné, aux embeddings, à `index_load` pgvector et à Evidently (drift +
MLflow HTML).** C'est le blocage unique, racine, prouvé.

**Inconnues résiduelles — HORS code atlas, à confirmer côté déployeur/cluster
avant de déclarer E2E vert** (gestes cluster, pas un fix d'image atlas) :

1. Secret `pgvector-pg-auth` (clés `username`/`password`) présent dans le ns
   `dagster` — sinon les run pods de `transform_job` échouent « secret not found
   » et `index_load` ne démarre pas.
2. Migration `deploy/base/migrations/0001_researchers_index.sql` appliquée à la
   db `pgvector` (colonne `vector(384)` alignée sur `EMBEDDING_DIM=384`) — sinon
   `index_load` échoue à l'INSERT.
3. 1ᵉʳ run : `evidently_embedding_drift` rapportera légitimement « baseline
   absente (1er run) » — normal, drift réel seulement à partir du 2ᵉ run.
4. `CURATED_DT` reste figé à `'0000-00'` (`dbt.py:59`) — toute la donnée
   atterrit sous `dt=0000-00`. Correct fonctionnellement (partition unique), à
   noter.

## Manques → suite

- Redéployer l'image atlas (fix `build_dbt_vars`) puis **prouver le transform
  E2E sur prod** (dbt → marts → embeddings → uplift → Evidently/MLflow).
- Vérifier les 2 prérequis déployeur (secret `pgvector-pg-auth` + migration)
  AVANT le run E2E.
- Après preuve : consolider `docs/architecture/chaine-dataops.md` sur la
  progression réelle (audit daté croisant #578/#539/#540 + ce fix).
