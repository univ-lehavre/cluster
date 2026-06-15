# 0068 — Profil `metrics` : palier fin entre `base` et `store`

## Statut

Accepted (2026-06-15)

## Contexte

L'[ADR 0039](0039-nomenclature-axes-catalogue.md) définit les profils comme une
chaîne **cumulative** `base ⊂ store ⊂ obs ⊂ dataops` (chaque profil inclut les
précédents). L'[ADR 0056](0056-modele-declaratif-topologies.md) en fait le
pilote déclaratif : la topologie déclare `catalog.profile`, et `topology.py` en
**dérive** le chemin nommé (`default_target`) puis la séquence de phases.

Or ce mapping profil → chemin est aujourd'hui **binaire** : `dataops` dérive
`atlas` (qui monte d'un bloc `storage-simple` → `metrics-server` → `monitoring`
→ `gitops` → `dataops`), **tout autre profil** dérive `socle` (= `up` →
`bootstrap`, rien de plus). Conséquence constatée au banc : déclarer
`profile: store` ou `profile: obs` est un **no-op** (le chemin reste `socle`,
sans stockage ni observabilité) ; on ne peut monter une couche intermédiaire «
peu à peu » qu'en passant directement à `dataops`, qui monte **tout** d'un coup.

`metrics-server` (l'API `kubectl top`) est la **plus petite brique
d'observabilité** : elle **ne dépend de rien** (ni stockage — aucun PVC —, ni
monitoring), et elle est un **pré-requis** logique de l'observabilité (dans le
chemin `atlas`, `metrics-server` est posé **avant** `monitoring`). En vouloir
JUSTE `metrics-server` sur un cluster — sans embarquer Prometheus/Grafana/Loki
(`obs`, lourd en RAM) — est un besoin légitime et fréquent (mesurer la
consommation avant de décider d'aller plus loin).

La chaîne actuelle n'offre aucun palier pour ça : le saut `base → obs` impose
tout le monitoring ; il n'existe pas de cran « observabilité minimale ».

## Décision

**Insérer un profil `metrics` dans la chaîne cumulative, entre `base` et
`store`** :

```text
base ⊂ metrics ⊂ store ⊂ obs ⊂ dataops
```

- `metrics` = `base` + la brique `metrics-server` (phase banc `metrics-server`).
- **Position avant `store`** : `metrics-server` n'a **aucune** dépendance
  stockage (no-op PVC) — le contraindre après `store` serait une fausse
  dépendance. Il vient juste après le socle.
- **`obs` et au-delà héritent de `metrics`** (cumulatif) : `obs` = `metrics` +
  `monitoring`. `metrics-server` n'est donc plus une brique propre du tail des
  chemins observabilité — il est **fourni par le palier amont** et ne se déclare
  qu'**une fois**, dans `metrics`.

Côté outillage, cela se traduit par :

- `PROFILE_CHAIN` (profile.py) gagne `"metrics"` après `"base"` ;
  `PROFILE_BRICKS["metrics"] = ["metrics-server"]`.
- `default_target` (plan.py) dérive un chemin nommé `metrics` pour
  `profile: metrics` ; `KNOWN_TARGETS` l'inclut ; son tail =
  `["metrics-server"]`.
- `run-phases.sh` gagne un **arm `metrics)`** enchaînant `run_socle` puis la
  phase unitaire `metrics-server` **déjà prouvée** (`phase_metrics_server`,
  `run-phases.sh:730`) — aucune nouvelle logique de montage, transcription d'un
  enchaînement existant (ADR 0063 G3).

La cohérence avec `atlas` est préservée : `atlas` continue de poser
`metrics-server` dans sa séquence (il n'hérite pas du _target_ `metrics`, c'est
un chemin nommé distinct), mais la **table des profils** (ADR 0039) place
désormais `metrics-server` au palier `metrics`, dont `obs`/`dataops` héritent.

## Conséquences

- La stack 1cp peut monter `metrics-server` **seul**, en place, via le modèle
  déclaratif : `catalog.profile: metrics` → `up` le dérive, `preview` le liste,
  le run est consigné comme palier (honnêteté ADR 0052). Plus de no-op
  silencieux ni de recours à un arm bash hors modèle (ADR 0046).
- La chaîne cumulative gagne un cran fin : on peut désormais incrémenter
  `base → metrics → store → obs → dataops` palier par palier (ce que l'ADR 0039
  visait sans l'outiller jusqu'au bout).
- L'[ADR 0039](0039-nomenclature-axes-catalogue.md) est **mise à jour** (table
  des profils : ligne `metrics` insérée). Cet ADR en est la déclinaison fine.
- Le mapping binaire `default_target` (limite identifiée par cartographie
  multi-agents, cf. [ADR 0067](0067-workflows-consignes-4e-trace-empirique.md))
  est corrigé pour `metrics` ; les paliers `store`/`obs` restent à outiller de
  même (travail suivant, hors périmètre de cet ADR).
- Preuve : un run `up` sur `profile: metrics` (banc 1cp) + rejeu `changed=0`
  (idempotence du déploiement metrics-server) + `kubectl top nodes` opérant.

## À revoir si

- Un futur besoin impose `metrics-server` **après** `store` (ex. un
  metrics-server à stockage persistant) — la position amont serait alors à
  reconsidérer.
- L'ajout des paliers `store`/`obs` comme targets dérivés révèle une meilleure
  factorisation commune (un mécanisme générique « profil → tail cumulatif »
  plutôt que des targets nommés un à un).

> **Amendé par [ADR 0069](0069-topology-layers-dag-grain-phase.md)** : le
> mécanisme générique anticipé ci-dessus EST `topology.layers` (DAG, grain
> phase). `metrics` y devient une couche du DAG (`metrics-server → [bootstrap]`,
> sans dépendance stockage) plutôt qu'un palier de la chaîne scalaire.

## Alternatives écartées

- **`metrics-server` en add-on orthogonal** (hors chaîne, ex.
  `catalog.addons: [metrics]`) : introduit un concept nouveau (add-ons) dans le
  modèle de profils cumulatifs — plus gros changement, écarté au profit de
  l'insertion dans la chaîne existante (cohérence ADR 0039).
- **Target `metrics` via `--target` seulement** (sans dérivation depuis le
  profil) : ne respecte pas ADR 0056 (la topologie déclare, l'outil dérive) — un
  chemin que seul un flag impératif atteint n'est pas piloté par la topo.
- **Palier `obs` complet** (metrics-server + monitoring) au lieu de `metrics`
  seul : embarque Prometheus/Grafana/Loki (RAM lourde sur le banc) alors que le
  besoin est la seule API `kubectl top` — grain trop gros.
