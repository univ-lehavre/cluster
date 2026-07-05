# Passage d'audit — 1er run transform E2E prod : orphelins author_id (dbt relationships)

> **Type** : passage d'audit ciblé (ADR 0058) — angle « le 1er run du transform
> citation en prod (après le fix dbt bucket) : où va la donnée, et pourquoi
> échoue-t-il ? », pas la grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : redéploiement prod du fix `build_dbt_vars`
> ([vérif](2026-07-05-verif-fix-dbt-bucket-avant-redeploiement.md) →
> [prérequis](2026-07-05-prerequis-deployeur-aval-citation-prod.md) tous verts),
> puis 1er `transform_job` lancé sur dirqual pour prouver l'aval E2E.
>
> **Méthode** : lecture des logs du run pod `dagster-run-8fc924d4` + diagnostic
> adversarial (3 lecteurs parallèles ingestion/staging · modèles+tests dbt ·
> précédent `curated_edges` → décision de fix, effort high). Cité ligne par
> ligne sur le code atlas.

## Ce qui est PROUVÉ (le fix bucket fonctionne)

Le run a matérialisé **tous** les modèles dbt sur le **vrai bucket OBC** — le
1er run affiche :

```text
dbt build --vars {"raw_root": "s3://citation-datalake-ca8434c3-…/raw",
                  "curated_root": ".../curated", "marts_root": ".../marts", …}
```

Les 3 racines sont dérivées de `BUCKET_NAME` (le fix #541). Plus aucun 404 :
staging (10 modèles) → curated (8 external) → marts (4 external) **tous créés**,
7 views, 1 seed. Le redéploiement est confirmé de bout en bout : image
`sha256:948080a4…` déployée, `DAGSTER_CURRENT_IMAGE` = ce digest, code-locations
`citation` + `mediawatch` LOADED, Argo `Synced/Healthy`.

## Ce qui a ÉCHOUÉ (un 2ᵉ bug, une couche plus profonde)

Le run a fini **`RUN_FAILURE`** sur **6 tests dbt `relationships` d'intégrité
référentielle `author_id`** — un test qui échoue rend `dbt build` rc≠0 → step
`citation_dbt_models` FAILED → l'aval (embeddings/uplift/Evidently/index_load)
n'a **jamais** tourné.

| Test (échelle réelle)                                                     | Orphelins |
| ------------------------------------------------------------------------- | --------- |
| `relationships_stg_citation_authorships_author_id → stg_citation_authors` | 1133      |
| `relationships_curated_authorships_author_id → curated_authors`           | 1133      |
| `relationships_marts_researchers_author_id → curated_authors`             | 10335     |
| `relationships_marts_researchers_fts_author_id → curated_authors`         | 1121      |
| `relationships_marts_collab_pairs_author_a / author_b → curated_authors`  | 4 / 4     |

**Tous les tests `work_id` passent** — seul `author_id` a des orphelins.

## Cause — réalité de la donnée OpenAlex, pas un bug de modèle

Les `author_id` référencés dérivent de l'entité **`works`**
(`stg_citation_authorships.sql` : `unnest(authorships).author.id`), tandis que
le côté `to:` des tests dérive de l'entité **`authors`**, un snapshot
**indépendant** (`stg_citation_authors.sql` ← `source('citation_raw','authors')`
; `curated_authors.sql` = pur dédup, zéro jointure). Rien ne garantit
`authors ⊇ authors-cités-par-works` :

1. **échantillonnage borné disjoint** des deux entités (chacune son watermark,
   `raw_snapshot.py`) ;
2. **fusions/redirections OpenAlex jamais réconciliées** — `merged_ids` déclaré
   mais jamais `ref()`é, pas de `merged_ids_authors` (ADR 0059). Un `author_id`
   fusionné reste inline dans `works.authorships` mais disparaît de l'entité
   `authors`.

Contrairement à `cited_work_id` (hors échantillon **temporel**), ceci **persiste
même à snapshot complet** → l'hypothèse « prod complète ⇒ author_id cohérents »
(ADR 0063) est **falsifiée** par le run. `work_id` passe car `works` est
l'entité racine, self-contained.

## Fix (atlas PR #542) — même doctrine que le précédent `curated_edges`

Le dépôt a **déjà** tranché ce type de cas : `curated_edges.cited_work_id` n'a
que `not_null` (relationships retiré) car « referenced_works pointe au-delà du
périmètre ingéré → faux échecs à l'échelle réelle » (`_curated__models.yml`).

Ce fix **retire les 6 blocs `relationships author_id`** (garde `not_null`
partout, garde `unique` sur `marts_researchers_fts`), documente le raisonnement
dans les 3 en-têtes de schéma. `curated_authors.author_id` garde `not_null`+
`unique` (clé de sa propre entité). Correctif de **code** (contrat de test),
re-prouvé par un run (ADR 0046/0052).

### Écarté

- **INNER JOIN filtrant les orphelins** : jetterait 10335 auteurs **réels**
  porteurs de labels/vecteurs légitimes → appauvrit l'index pgvector pour une FK
  cosmétique.
- **`severity: warn`** : débloque mais diverge du précédent (`curated_edges` a
  _retiré_, pas relâché) → incohérence de doctrine.
- **réconciliation `merged_ids_authors`** / **`coherent_sample` en prod** : hors
  périmètre / falsifierait la donnée réelle.

## Impact aval — bénin

Aucun consommateur ne joint `curated_authors` : `index_load`
(`index_load.py:139-141`) et `researcher_embeddings`
(`researcher_embeddings.py:205`) dérivent `author_id` des **works**, jamais de
l'entité authors. Un orphelin s'indexe normalement en pgvector ; le seul «
manque » = ses métadonnées `display_name`/`orcid`, que l'index ne charge pas.
Retirer le test **débloque l'aval E2E sans masquer de vrai problème**.

## Portée doctrine — pile ce que l'audit banc/prod prédisait

Ce bug est le **2ᵉ** trouvé au 1er run E2E prod, après le bucket (#541). Les
deux vivent **exactement dans l'écart banc/prod** : le banc (fixtures
self-consistantes, SeaweedFS, bucket `citation`) ne peut **structurellement
pas** voir un orphelin d'entité OpenAlex réelle. Confirme la thèse du passage
[le banc Lima vaut-il le coup ?](2026-07-05-banc-lima-vaut-il-le-coup.md) : le
banc est une gate de logique, la prod est la gate d'intégration externe.

## Manques → suite

- Merge **atlas #542** → **rebuild + re-seed** (nouveau digest) → **relancer
  `transform_job`** → prouver l'aval jusqu'à uplift entraîné + Evidently +
  index_load pgvector.
- Puis **2ᵉ run** (même `dt=0000-00`) pour un vrai drift Evidently.
- Corriger le présupposé d'**ADR 0063** (« prod complète ⇒ author_id cohérents
  ») — noté dans le commentaire de schéma ; à acter si un ADR est révisé.
