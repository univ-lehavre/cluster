# Passage d'audit — révision de l'ingestion citation : échantillonnage banc vs prod complet

> **Type** : passage d'audit ciblé (ADR 0058) — angle « comment réviser
> l'ingestion pour que la prod ne soit pas bridée par les défauts banc, et
> réaliser la demande "mart tout-OpenAlex + mart EUNICoast×période" », pas la
> grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : le transform E2E est prouvé
> ([passage E2E](2026-07-05-transform-e2e-prouve-prod.md)) mais l'uplift reste
> **descriptif** faute de paires de collaboration. L'auteur relève que
> l'échantillonnage, conçu pour ne pas congestionner le **banc**, n'a jamais été
> différencié banc/prod, et demande deux marts (tout OpenAlex + filtré
> période×EUNICoast).
>
> **Méthode** : workflow de conception (judge panel) — 3 lecteurs parallèles
> (ingestion banc/prod · couches dbt · structure source OpenAlex + faisabilité
> filtre) → 3 designs indépendants → jury noté /10, effort high. Grounded
> file:line sur le code atlas ; capacité mesurée en lecture seule sur dirqual.

## Diagnostic racine (confirmé en code, indiscutable)

`RawSnapshotConfig` (`raw_snapshot.py:55`) est un pur `dagster.Config` dont les
défauts sont des **littéraux mini-banc** (`sample_size=4`, `max_partitions=1`).
La `ScheduleDefinition ingest_snapshot` (`definitions.py:298-304`) **n'a pas de
`run_config=`**, et `ingestion_job` (`definitions.py:157-161`) ne pose que des
tags k8s → **aucun canal ne surcharge ces défauts**. La prod hérite donc
**silencieusement du bornage banc** → datalake famélique (1 puis 61 partitions
éparses, works = 4 MiB, watermark bloqué vers 2016-18) → 0 paire collab → uplift
descriptif. **La polarité du défaut est à l'envers** : le défaut devrait être
prod-complet, et c'est le banc qui devrait borner.

## Faits établis (mesurés sur prod dirqual, lecture seule)

- **Capacité Ceph** : 268 TiB total, **256 TiB dispo**, 4,3 % utilisé, 81 TiB
  MAX AVAIL/pool. Stocker tout OpenAlex (~1,6 To works+authors) est **trivial**
  (<2 %). Le stockage n'est **pas** un facteur.
- **Source OpenAlex** : snapshot S3 public partitionné par `updated_date`
  **seul** (482 partitions works, 2016→2026). Une partition récente ≈ 73 GiB /
  160 fichiers ; les anciennes (2016-18) sont minuscules. `updated_date` ≠
  `publication_year`.
- **Ciblage EUNICoast à la source = INFAISABLE** : le snapshot n'est pas
  partitionné par institution, et l'API OpenAlex works est stats-only (group_by,
  plafond 10000). **Seule voie** : ingérer complet + filtrer en dbt aval.
- **Le prédictif EXIGE la complétude** : les baselines solo antérieures des
  co-auteurs doivent être présentes, sinon le modèle est biaisé → un filtrage
  partiel/échantillonné fausserait l'uplift.

## Décision (jury + arbitrage utilisateur)

Les **3 designs convergent** sur le même fix d'ingestion ; ils ne divergent que
sur la couche dbt.

| Design                                                               | Score   | Verdict                                                                                                 |
| -------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------- |
| **MINIMAL** (inverse défaut + run_config sur Schedule, dbt existant) | **8.5** | **Gagnant** : moindre churn, débloque le volume.                                                        |
| CIBLÉ-EUNICOAST (collecte complète du sous-graphe)                   | 7.5     | Meilleure analyse (infaisabilité source, nécessité de complétude) ; 2 corrections dbt justes intégrées. |
| DEUX-MARTS-EXPLICITE (marts servis nommés sous `marts/`)             | 7       | Seul fidèle à la lettre, mais sur-ingénierie sans consommateur du dump complet.                         |

**Plan retenu (hybride)** : MINIMAL pour le volume + les 2 corrections dbt
load-bearing de l'angle #2. **Décisions utilisateur** : (a) **bootstrap complet
unique** (~1,6 To, mono-thread) pour prouver le prédictif maintenant ; (b) **pas
de nouveaux marts servis** — `curated_works` = niveau « tout OpenAlex »,
`curated_eunicoast_works` = mart filtré (structure existante).

## Changements retenus

1. **Inverser la polarité des défauts CODE** (`raw_snapshot.py`) : sentinelle
   `0 = illimité` → défaut **prod-complet** ; `sample_size`, `max_partitions`,
   `max_merged_files` passent à `0` ; les 3 sites de troncature honorent la
   sentinelle. _(Fait 2026-07-05.)_
2. **`run_config=` sur la Schedule** (`definitions.py`) : helper
   `_ingest_run_config()` lisant `CITATION_INGEST_SAMPLE_SIZE` /
   `CITATION_INGEST_MAX_PARTITIONS` / `CITATION_INGEST_COHERENT` (parse
   défensif, patron `_retrain_cooldown_s`) ; absent → défaut complet. **La ligne
   manquante qui causait la famine.**
3. **Overlays** : `bench` pose les bornes (`4/1/coherent=on`) ; **`prod` ne pose
   rien** (défaut complet). Conforme ADR 0023 (aucune valeur prod figée
   versionnée).
4. **2 corrections dbt** : rebrancher `curated_eunicoast_works` sur
   `ref('curated_works')` (mart2 ⊆ mart1, dédup canonique) + **figer la fenêtre
   `eunicoast_min_year` au run** (`--vars`, sinon corpus non déterministe, ADR
   0057 — le var existe déjà avec fallback, seule la fixation manque).
5. **Bootstrap prod** : 1 run `ingestion_job` non borné (482 partitions),
   **mono-thread obligatoire** (`watermark.py` read-modify-write non atomique).
   Puis armer `ingest_snapshot` (STOPPED par défaut) pour l'incrémental mensuel.

## Risques (à surveiller)

- Run bootstrap long (~1,6 To via rclone) — hors schedule, surveillé.
- Inverser le défaut change TOUT run lancé sans `run_config` → documenter la
  sentinelle + tests anti-régression (les tests actuels mockent
  `subprocess.run`).
- Ne pas oublier d'**armer** `ingest_snapshot` après bootstrap (sinon datalake
  vide malgré le fix).
- `coherent_sample` doit rester **OFF en prod** (garde `raw_snapshot.py:432`) —
  posé seulement dans l'overlay banc.
- Rebrancher `curated_eunicoast_works` sur `curated_works` peut changer le
  contenu à l'échelle réelle → re-valider les tests + compteurs de paires.

## Manques → suite

- Terminer l'implémentation (`definitions.py` run_config + overlays + 2 dbt +
  tests) → PR atlas.
- Bootstrap prod complet → relancer transform → prouver **uplift PRÉDICTIF**
  (`served_mode` sort du repli, R²/MAE d'ADR 0067).
- ADR « échantillonnage banc vs prod complet » (inversion de polarité) —
  candidat à fusionner avec l'ADR doctrine 2 étages (révise 0034).
