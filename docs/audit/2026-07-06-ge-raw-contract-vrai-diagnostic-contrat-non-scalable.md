# Passage d'audit — `ge_raw_contract` : le VRAI diagnostic (contrat non-scalable), après deux fausses pistes

> **Type** : passage d'audit ciblé, issu de deux **workflows multi-agents** +
> mesures empiriques sur le RGW prod
> ([ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md) /
> [0078](../decisions/0078-passages-audit-famille-unique.md)). Pas la grille /5.
>
> **Date** : 2026-07-05/06 (session de nuit autonome).
>
> **Déclencheur** : `ge_raw_contract` continuait d'échouer « Could not resolve
> hostname » **après** le fix `ndots:1` (atlas#551) — preuve que le diagnostic
> précédent (amplification DNS) était **incomplet**. Ce passage établit la
> **vraie** cause et corrige honnêtement les conclusions du
> [passage ndots](2026-07-05-ge-raw-contract-ndots-fanout-dns.md).
>
> **Honnêteté (ADR 0052)** : ce diagnostic a traversé **deux fausses pistes**
> avant la bonne. Elles sont consignées — la valeur d'un audit est aussi dans
> les impasses documentées.

## Ce qui a été RÉFUTÉ (les deux fausses pistes)

### Fausse piste nº1 — l'amplification DNS (`ndots`)

Le [passage précédent](2026-07-05-ge-raw-contract-ndots-fanout-dns.md) concluait
« amplification `ndots:5` × HEAD-par-fichier → `EAI_AGAIN` ». Le fix `ndots:1`
(atlas#551) a été **déployé et vérifié posé** sur le pod de run… et
`ge_raw_contract` a **quand même échoué**, au même endroit, à la même durée (~73
s, déterministe).

**Réfuté par la mesure** : depuis un pod dagster,
`socket.getaddrinfo(rook-ceph-rgw-datalake.rook-ceph)` → **300/300 OK en 0,7 s**
(séquentiel) et **500/500 OK en 0,7 s** (concurrent). Le DNS **n'est pas** le
goulot. Le fix `ndots:1` était donc **inutile** (pas nuisible — c'est une
optimisation légitime, gardée à ce titre, mais requalifiée : ce n'était pas LA
cause). Même le workflow adversarial du 1er passage s'était trompé (il avait
affirmé « DuckDB = c-ares » ; c'est **glibc `getaddrinfo`**, le même que
rclone).

### Fausse piste nº2 — l'index RGW / la mémoire du pod de test

Mes tests DuckDB sur des **pods de test sous-dimensionnés** (2-3 GiB) les ont
**OOM-killés** — j'ai un moment cru à un problème mémoire structurel. **Réfuté**
: le **pod de run réel n'a AUCUNE limite mémoire** (`resources={}`) et **n'a PAS
OOM** (`lastState` vide) — il a échoué sur le timeout, pas la RAM. L'OOM était
un artefact de **mes** pods de test. Leçon : reproduire un incident dans un
environnement fidèle (ici : sans limite mémoire, comme le pod de run).

## La VRAIE cause — un contrat qualité qui ne passe pas à l'échelle

`check_raw` (quality.py) faisait :

```sql
SELECT id, referenced_works, authorships
FROM read_json_auto('s3://…/raw/works/**/*.gz', union_by_name=true)  -- puis .df()
```

Il **matérialisait en pandas l'INTÉGRALITÉ** du brut. Après l'ingestion complète
(**261k fichiers `.gz`**, chacun ~150-290k works au JSON très imbriqué), c'est
**intraitable** :

- **Volume** : `read_json_auto` **infère et parse le schéma JSON complet** de
  chaque work (`abstract_inverted_index` imbriqué, etc.) — mesuré **10-19 s pour
  UN fichier**. Lire les 261k = des jours.
- **Le run gèle à ~73 s** et **httpfs déguise le timeout HTTP S3 en « Could not
  resolve hostname »** (comportement connu de httpfs — l'erreur DNS était un
  **symptôme trompeur**, à l'origine des deux fausses pistes).

Le contrat a **toujours marché tant que le datalake était échantillonné** (2446
petits fichiers) ; il casse au datalake **complet**. C'est un défaut de
conception : **une porte bloquante ne doit jamais lire l'intégralité d'un lac de
691 GiB.**

## Le fix — échantillonner + colonnes explicites (prouvé sur prod)

atlas#552. Trois leviers, chacun nécessaire :

1. **Échantillon déterministe et réparti** (`_sample_raw_files`) : `glob()`
   **liste** les clés (1 LIST S3, pas 261k GET) puis prend `files[::step]` —
   couvre toutes les partitions `updated_date`, pas les N premières
   lexicographiques. Défaut **N=4** fichiers/entité
   (`CITATION_GE_RAW_SAMPLE_FILES`).
2. **`read_json` avec `columns={}` EXPLICITES** (pas `read_json_auto`) : impose
   le type des 3 colonnes validées → DuckDB **ne parse plus** le JSON imbriqué
   complet → **plus d'OOM**. C'est le levier décisif : sans lui, même 4-8
   fichiers faisaient OOM (le coût est le **parsing**, pas seulement le nombre
   de fichiers).
3. **Réglages HTTP** dans `lakehouse.connect` (keep-alive, timeout 120 s,
   retries) — robustesse, **en complément** du bornage (jamais en substitut : un
   timeout seul masquerait le faux message DNS sans réduire le volume).

**PROUVÉ sur le RGW prod** (N=4) : works **725 676 lignes / 41 s** + authors
**751 782 / 19 s**, **0 id mal formé**, **sans OOM**. ~60 s pour un asset check
bloquant = acceptable.

### Portée — seul `check_raw` était vulnérable

Les six autres `check_*` lisent le Parquet du **`run={run_id}` courant** (borné
par un run), pas l'historique cumulé. La différence de fond : `raw/` est
**append-only cumulatif** ; `curated/`/`marts/` sont **partitionnés par run**,
donc auto-bornés. Aucun autre check à corriger.

## Ce que le contrat perd (honnêteté)

Un échantillon ne voit pas un défaut de forme **localisé** sur un fichier non
lu. Acceptable pour un **contrat structurel** : la forme OpenAlex (colonnes
présentes, `id` préfixé `W`/`A`) est un **invariant homogène** — vrai pour
toutes les lignes ou aucune. L'audit ligne-à-ligne exhaustif vit **en aval**
(tests dbt `not_null`/`unique`/`relationships` sur le staging, suites
`curated`/`marts`). `check_raw` ne doit pas être présenté comme une preuve
d'exhaustivité.

## Consigné comme drifts

- **L74 requalifié** : le correctif réel n'est pas `ndots:1` mais
  l'échantillonnage du contrat.
- **L76** : le contrat GE non-scalable (lit tout le lac).
- **L77** : `read_json_auto` OOM sur le brut OpenAlex (parsing du JSON imbriqué)
  → colonnes explicites.

## Leçon de méthode

Trois pièges enchaînés, tous documentés : (1) un **message d'erreur trompeur**
(httpfs déguise un timeout en erreur DNS) a envoyé deux diagnostics sur le DNS ;
(2) un **workflow adversarial peut se tromper** sur un fait technique (c-ares vs
glibc) — la **mesure** tranche, pas le raisonnement ; (3) **reproduire dans un
environnement fidèle** (pod sans limite mémoire) évite de confondre l'artefact
de test avec le bug. Le fil conducteur : **prouver par la mesure** (ADR 0052), à
chaque étape.
