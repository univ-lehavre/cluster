# Passage d'audit — transform citation PROUVÉ E2E sur prod (1re fois)

> **Type** : passage d'audit ciblé (ADR 0058) — angle « la chaîne aval citation
> tourne-t-elle enfin de bout en bout en prod, et où va la donnée ? », pas la
> grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : après le fix bucket (#541) et le retrait des tests
> `relationships author_id` (#542), rebuild + re-seed prod (digest
> `sha256:64298aab…`, revision atlas `96838ee0`) puis relance de
> `transform_job`.
>
> **Méthode** : sondes **lecture seule** post-run (GraphQL run status, logs du
> run pod, `psql` SELECT sur pgvector, API MLflow). Contexte
> `kubernetes-admin@cluster-prod` vérifié à chaque commande.

## Verdict — **RUN_SUCCESS, chaîne complète prouvée** ✅

Le run `dagster-run-6e9a3c32` a fini **`SUCCESS`** : **20 steps réussis, 0
échec, 30 matérialisations**. **Pour la première fois**, la chaîne applicative
citation tourne de bout en bout en prod. C'est l'aboutissement de la série de
bugs de config prod (#578 seed · #539 chemin OpenAlex · #540 quota OBC · #541
bucket dbt · #542 orphelins author_id) — chacun découvert et corrigé sur un run
prod successif.

## Ce qui a réellement produit de la donnée (preuves)

| Étape                          | Preuve                                                                                                                                                                             |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **dbt** (19 modèles, 64 tests) | `dbt build --vars` sur le **vrai bucket** `s3://citation-datalake-ca8434c3-…/{raw,curated,marts}` ; 0 test en échec (les 6 relationships author_id retirés par #542).              |
| **embeddings**                 | `researcher_vectors_manifest` + `work_vectors_manifest` matérialisés.                                                                                                              |
| **uplift**                     | `pair_uplift_model` matérialisé + **run MLflow** (experiment `citation_uplift_fwci`, exp. 36).                                                                                     |
| **Evidently**                  | `evidently_uplift_drift` : asset check **passed** (baseline N-1 absente au 1er run → normal).                                                                                      |
| **index_load (pgvector)**      | matérialisé ; GE check `ge_index_load` passed. **Table `public.researchers` = 1152 lignes** (était 0), chacune `embedding vector(384)` + `fts tsvector` **peuplés**, `dt=0000-00`. |
| **Great Expectations**         | `ge_author_recommendations`, `ge_pair_uplift_predictions`, `ge_index_load` : tous loggés à MLflow (exp. 34).                                                                       |
| **MLflow**                     | reçoit les runs (exp. 34 + 36) — egress `mlflow.mlflow:5000` opérationnel.                                                                                                         |

**Preuve dure côté index** : `select count(*) from public.researchers` =
**1152** (vec+fts non nuls), sous un seul `dt`/`run`. L'index vectoriel pgvector
est chargé et interrogeable.

## Frontière honnête — le modèle uplift est DESCRIPTIF, pas encore prédictif

MLflow (run uplift, exp. 36) enregistre :

```text
served_mode      = descriptive
predictive       = 0.0
n_pairs_labeled  = 0.0
n_pairs_served   = 0.0
embedding_coverage = 0.0
```

Le modèle a tourné mais **basculé en repli `descriptive`** faute de **paires de
collaboration étiquetées** : `curated_pair_uplift_labels` a produit **0 ligne**
(aucune paire d'auteurs avec ≥2 co-publications EUNICoast + baseline solo
antérieure des deux côtés dans cette tranche de données). C'est **une condition
de données, pas un bug** — le repli est le comportement conçu de `uplift.py`
(`evaluate_grouped` → `descriptive` quand trop peu de groupes), exactement la
condition de preuve #8 anticipée par
[le passage prérequis](2026-07-05-prerequis-deployeur-aval-citation-prod.md).

**Donc** : la **plomberie** est prouvée E2E (ingestion → dbt → marts →
embeddings → index pgvector → Evidently/MLflow/GE). Le **modèle prédictif**
attend un **volume de données suffisant** (des paires collaboratives qualifiées)
— à obtenir en élargissant l'échantillon d'ingestion OpenAlex (`max_partitions`/
`sample_size`) ou en attendant l'accumulation mensuelle.

## Portée doctrine

Les **5 bugs de config prod** (seed, chemin OpenAlex, quota OBC, bucket dbt,
orphelins author_id) vivaient **tous dans l'écart banc/prod** — aucun visible au
banc (fixtures self-consistantes, SeaweedFS, source mockée, seed stubbé). Cette
session est la validation empirique de la thèse du passage
[le banc Lima vaut-il le coup ?](2026-07-05-banc-lima-vaut-il-le-coup.md) : banc
= gate de logique, prod = gate d'intégration externe. Elle motive directement
l'ADR de doctrine à deux étages (à écrire, révise ADR 0034).

## Manques → suite

- **Modèle prédictif** : élargir l'ingestion pour obtenir des paires collab
  qualifiées → uplift `predictive` (suivi, condition de données).
- **2ᵉ run** (même `dt=0000-00`) pour prouver un **vrai** calcul de drift
  Evidently (baseline N-1 présente).
- **ADR 0104** « doctrine de preuve à deux étages » (révise 0034) + test de
  contrat seed git.
- **Consolider `docs/architecture/chaine-dataops.md`** sur la progression réelle
  (maintenant que l'E2E est prouvé) — cf.
  [[doc-progression-reelle-pipeline-citation]].
- **parquet** (réécriture staging DuckDB) ; **mediawatch** (même traitement
  E2E).
