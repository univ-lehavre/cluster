# Plan — Cache partagé des flux atlas via CloudNativePG

## État

> **État : Actif** (2026-06-23) · **Fonde :**
> [ADR 0093](../decisions/0093-cache-flux-cnpg.md) (Accepted). Plan validé ;
> implémentation à dérouler (étapes 1-4, banc d'abord).

Matérialise la brique cluster du cache partagé atlas (#150, épopée DataOps #223)
: une base logique `cache` sur le CNPG existant + le contrat/DSN. L'adaptateur
code derrière l'interface `readCache`/`writeCache` reste **côté atlas**
(frontière, §5 ADR).

## ADR fondateurs

- [0093](../decisions/0093-cache-flux-cnpg.md) — la décision (Postgres, pas
  Redis ; advisory lock + UPSERT + table horodatée).
- [0024](../decisions/0024-postgres-manage-cloudnative-pg.md) (CNPG, une base
  par usage) ; [0043](../decisions/0043-contrat-interface-cluster-atlas.md)
  (contrat) ; [0023](../decisions/0023-plateforme-exemple-generique/) (valeurs
  génériques).
- Externe : ADR atlas 0040 (caches = backing service injectable).

## Invariants

- **Réutiliser CNPG** : aucune nouvelle brique stateful. Base logique `cache` de
  plus sur le Cluster `pg` (comme dagster/pgvector/marquez/mlflow).
- **Frontière** : le cluster fournit base + rôle + DSN. L'adaptateur Postgres
  derrière l'interface atlas (`ATLAS_STATS_CACHE_PATH`/`CRF_LOGS_CACHE_PATH` —
  aujourd'hui un PATH fichier) est **atlas** (issue atlas dédiée). Le cluster ne
  code pas le SQL.
- **Nomenclature** : identifiant `cache`, jamais une marque (ADR 0043).
- **Banc local-path** : preuve e2e sur le banc mono-nœud (plus de banc Ceph).

## Étapes

### 1. Base/rôle `cache` sur le Cluster CNPG

- **ÉDITER** `platform/cloudnative-pg/cluster.yaml` : rôle managé `cache` dans
  `spec.managed.roles` **avec** `passwordSecret: { name: pg-role-cache }`
  (obligatoire — sans lui, `rolpassword` NULL, connexion impossible).
- **ÉDITER** `platform/cloudnative-pg/database.yaml` : `kind: Database`
  `name/owner: cache`, `cluster: pg`.
- **ÉDITER** `platform/cloudnative-pg/role-secrets.example.yaml` : Secret
  `pg-role-cache` (`basic-auth`, valeur de test au banc ; prod via config locale
  non versionnée).
- **Preuve** : rejeu idempotent du rôle `platform-cnpg` (`changed=0`) ; base
  `cache` créée, connexion `psql` avec le rôle `cache` OK.

### 2. Contrat — endpoint cache + DSN

- **ÉDITER** `contract/endpoints.example.yaml` : point de contact
  `postgres-cache` (`service: pg-rw`, `namespace: postgres`, `port: 5432`,
  `auth: secret-role`, base `cache`).
- **ÉDITER** `contract/namespaces-secrets.example.yaml` : entrée `pg-role-cache`
  sous `secrets.postgres_roles.items`.
- **ÉDITER** `contract/atlas.env.cluster.example` : bloc `POSTGRES_CACHE_*`
  dédié (ne PAS écraser les `POSTGRES_*` pgvector).
- **ÉDITER** `scripts/check_contract.py` si l'ancrage du nouveau point de
  contact l'exige.
- **Preuve SANS cluster** : `check_contract` + tests.

### 3. Preuve e2e au banc (local-path, mono-nœud)

- **Scénario bench** : 2 répliques d'un consommateur jouet partagent la base
  `cache` → vérifier (a) dédup (une seule ligne après actualisations
  concourantes), (b) bridage global (`MIN_REFRESH_INTERVAL_MS` respecté via la
  colonne horodatage + advisory lock), (c) pas de corruption sous écritures
  concurrentes (UPSERT atomique).
- **Preuve** : le scénario PASS sur le banc `banc.yaml` (CNPG du banc).

### 4. Frontière atlas (hors cluster — à tracer)

- **Issue atlas** : l'adaptateur Postgres derrière `readCache`/`writeCache` (la
  variable `*_CACHE_PATH` doit accepter un DSN postgres, pas qu'un chemin
  fichier). Hors ce dépôt.

## Suivi

- [x] Étape 1 — base/rôle `cache` (CNPG) : rôle managé + `Database cache` +
      Secret `pg-role-cache` (cluster.yaml / database.yaml /
      role-secrets.example.yaml)
- [x] Étape 2 — contrat : endpoint `postgres-cache` + secret `pg-role-cache` +
      bloc `POSTGRES_CACHE_*` (atlas.env) ; `check_contract` vert
- [x] Étape 3 — scénario banc `33-cache-cnpg.sh` (connexion rôle `cache` +
      UPSERT atomique + `pg_advisory_lock`) + catalogue épreuves ; reste à
      **jouer au banc**
- [x] Étape 4 — issue atlas (adaptateur Postgres derrière
      `readCache`/`writeCache`) :
      [atlas#443](https://github.com/univ-lehavre/atlas/issues/443)
