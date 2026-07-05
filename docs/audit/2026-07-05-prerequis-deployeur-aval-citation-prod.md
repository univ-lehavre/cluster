# Passage d'audit — prérequis déployeur de l'aval citation (prod dirqual, lecture seule)

> **Type** : passage d'audit ciblé (ADR 0058) — angle « les prérequis
> déployeur/cluster de la chaîne aval citation sont-ils en place sur prod, AVANT
> le redéploiement du fix dbt ? », pas la grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : le passage
> [vérif du fix dbt](2026-07-05-verif-fix-dbt-bucket-avant-redeploiement.md) a
> conclu **GO** côté code, avec 8 gaps E2E qui sont des **gestes
> déployeur/cluster** (hors code atlas). Avant de redéployer + prouver, on
> vérifie qu'aucun de ces prérequis ne manque — pour ne pas découvrir un trou au
> moment du run.
>
> **Méthode** : sondes **lecture seule** (`kubectl get`/`describe`, `psql`
> SELECT-only) sur prod dirqual. Contexte vérifié
> `kubernetes-admin@cluster-prod`, nœuds `dirqual1..4`, avant chaque commande
> (garde d'isolation ADR 0053). **Aucune mutation** (ni pod probe, ni `apply`,
> ni migration) — conforme ADR 0046 (diagnostic uniquement).

## Verdict — **tous les prérequis sont en place** ✅

Les 8 gestes déployeur identifiés par la vérif du fix sont **déjà satisfaits sur
prod**. Aucun blocage déployeur avant le redéploiement du fix (atlas #541, en
automerge). Reste, côté code : merge #541 → redéploiement → preuve.

## Détail des sondes (lecture seule)

| #   | Prérequis                                   | État | Preuve                                                                                                                                                                                                                                                                               |
| --- | ------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Secret `pgvector-pg-auth` (ns dagster)      | ✅   | présent, clés `username`/`password` ; source `pg-role-pgvector` (ns postgres) présente aussi.                                                                                                                                                                                        |
| 2   | Schéma `researchers` + extension `vector`   | ✅   | db `pgvector` : extension `vector` installée ; table `public.researchers` présente ; **`embedding vector(384)`** (dim alignée `EMBEDDING_DIM=384`), colonnes `researcher_id text / embedding vector / fts tsvector / dt text / run text` ; 0 ligne (attendu, transform jamais joué). |
| 3   | DNS court `pg-rw.postgres:5432` + egress    | ✅   | svc `pg-rw` (ClusterIP, 5432) présent ; NP `allow-postgres-egress` : TCP 5432 → ns `postgres`. CNPG `pg` healthy 3/3.                                                                                                                                                                |
| 4   | Overlay S3 (`CITATION_S3_SECRET/CONFIGMAP`) | ✅   | image citation déployée + code-location `citation` chargée ; déjà prouvé de fait par l'ingestion (run pods écrivent sous le vrai bucket OBC).                                                                                                                                        |
| 5   | Armement du `transform_job`                 | ✅   | sensor **`transform_on_watermark_advance` = RUNNING** (déclenche le transform quand le watermark avance) ; `ingest_snapshot` RUNNING ; `retrain_on_drift` RUNNING ; `transform_daily` STOPPED (le sensor est le déclencheur voulu).                                                  |
| 6   | Egress MLflow + Marquez                     | ✅   | NP `allow-mlflow-egress` (TCP 5000 → ns mlflow) + `allow-marquez-egress` (TCP 5000 → ns marquez) ; pods `mlflow` 1/1, `marquez` + `marquez-web` 1/1 Running.                                                                                                                         |
| 7   | 2 runs pour un vrai drift Evidently         | ⏳   | condition de PREUVE (pas d'infra) : au 1er run, baseline N-1 absente → `passed=True` sans calcul. À enchaîner (2 runs même `dt=0000-00`).                                                                                                                                            |
| 8   | Volume de données pour un uplift prédictif  | ⏳   | condition de PREUVE : si trop peu de paires (`curated_pair_uplift_labels`), `uplift_model` sert en repli `descriptive` (run vert, pas un modèle entraîné). À qualifier lors du run.                                                                                                  |

Note sur les NetworkPolicies : les `podSelector` des règles d'egress sont
**vides (`{}`)** → elles s'appliquent à **tous** les pods de `dagster`, y
compris les pods de run transitoires `dagster-run-*` (label
`app.kubernetes.io/component=run_worker`). `default-deny-all` +
`allow-dns-egress` présents → le socle réseau du run pod est complet.
L'ingestion (`ingestion_job`) a déjà tourné à travers ces mêmes règles
(S3/DNS/apiserver), ce qui prouve le chemin ; le transform ajoute postgres +
mlflow/marquez, tous trois explicitement autorisés.

## État de déploiement (référence)

- Image citation déployée : `registry:80/citation-dagster@sha256:25994d83…`
  (**pré-fix** — le redéploiement produira une nouvelle image portant le fix
  `build_dbt_vars`).
- Argo `citation-dagster` : `Synced` / `Healthy`, `targetRevision=091a2460…`.

## Manques → suite

- Merge **atlas #541** (automerge) → **redéployer** (`nestor next` : build →
  digest → `dirqual.yaml` → seed).
- Enchaîner la preuve transform E2E : déclencher l'ingestion (ou attendre le
  watermark) → le sensor cascade sur `transform_job` → dbt → marts → embeddings
  → uplift → Evidently/MLflow → index_load pgvector. Puis **2ᵉ run** pour un
  vrai drift, et qualifier le mode uplift (predictive vs descriptive) selon le
  volume.
