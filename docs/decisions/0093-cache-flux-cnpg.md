# 0093 — Cache partagé des flux atlas servi par CloudNativePG (pas de Redis)

## Statut

Accepted (2026-06-23)

Sert le contrat
d'[ADR atlas 0040](https://atlas.example-org/decisions/0040-caches-flux-backing-service-vs-fichier)
(« un cache applicatif est un backing service injecté par variable
d'environnement ») par **réutilisation** du PostgreSQL managé
d'[ADR 0024](0024-postgres-manage-cloudnative-pg.md), conformément au contrat
d'interface [ADR 0043](0043-contrat-interface-cluster-atlas.md). Toutes les
valeurs ci-dessous sont des exemples génériques
([ADR 0023](0023-plateforme-exemple-generique/)) : `cache-test-password`,
`pg-rw.postgres`, identifiant `cache`.

## Contexte

Les flux de la plateforme applicative (`atlas-stats`, `crf-logs`, et le
`RefreshCoordinator` qui en orchestre l'actualisation) ont besoin d'un **cache
partagé** : un payload de flux (TTL 24 h, débit modeste — quelques rafraîchis
par jour) lisible/écrivable par **plusieurs répliques** d'un même service.

L'[ADR atlas 0040](https://atlas.example-org/decisions/0040-caches-flux-backing-service-vs-fichier)
a déjà tranché côté applicatif : « un cache applicatif n'est pas un fichier JSON
local ; c'est un backing service injecté par variable d'environnement, avec un
back-end choisi à l'exécution ». Elle nomme **deux** back-ends prod légitimes
derrière la même interface : « un cache clé-valeur en mémoire distribuée **OU**
la base relationnelle déjà présente comme stockage de l'application ». Et elle
**renvoie le branchement effectif à ce dépôt** : « le branchement d'un backing
service partagé (et son test en conditions réelles) relève du dépôt cluster, pas
de celui-ci ». C'est donc à nous de trancher **lequel** des deux back-ends, et
de fournir l'infra.

**État du contrat aujourd'hui (lu, rien modifié dans atlas — dépôt en dev
actif).** Le cache n'est **pas encore** un point de contact
d'[ADR 0043](0043-contrat-interface-cluster-atlas.md). Surtout, l'interface
applicative attend **un chemin de fichier**, pas une URL :
`ATLAS_STATS_CACHE_PATH` / `CRF_LOGS_CACHE_PATH` sont résolus par
`path.resolve(process.env[...])` et lus/écrits par `readFile`/`writeFile` (atlas
`packages/atlas-stats/src/cache.ts` l. 20-26, 61-66 ;
`packages/crf-logs/src/cache.ts` l. 38-44, 70-75). Le TTL est calculé côté JS
(`Date.now() - cache.savedAt > 24 h`, `cache.ts:8`), **pas porté par un
back-end**. La déduplication des actualisations en vol repose sur une `Promise`
locale **non sérialisable inter-instances** (atlas
`apps/atlas-dashboard/src/lib/refresh-coordinator.ts` l. 60-64) ; le bridage de
cadence (`MIN_REFRESH_INTERVAL_MS`, défaut 60 s) sur une variable de module.
Conclusion : fournir un DSN **ne suffit pas** — il faut un **adaptateur** côté
atlas implémentant `readCache`/`writeCache`/`isCacheStale` + un
`RefreshCoordinator` adossés à ce DSN. **Ce travail est hors périmètre de ce
dépôt** (cf. §Frontière). Ce dépôt fournit l'**infra** ; atlas branche le code.

## Décision

**Le cache partagé des flux atlas est servi par réutilisation du CloudNativePG
existant ([ADR 0024](0024-postgres-manage-cloudnative-pg.md)) — une base logique
`cache` dédiée sur le Cluster `pg` — et non par une nouvelle brique Redis.**

### 1. Postgres plutôt que Redis — sobriété, honnêtement pesée

Redis serait, sémantiquement, le choix le plus **naturel** : c'est un cache
clé-valeur, le TTL natif y est trivial, les structures concurrentes (verrous,
`SETNX`) y sont idiomatiques. On l'écarte malgré cela, et on l'assume :

- **Sobriété — pas de brique inutile à opérer.** Une nouvelle brique se déploie,
  se durcit, se sauvegarde, se supervise, se met à jour, s'épingle par digest,
  s'allowliste en NetworkPolicy. Le coût récurrent d'**exploitation** d'un Redis
  (HA, persistance, RBAC, observabilité) est réel et permanent.
- **CNPG est déjà là.** Le Cluster `pg` HA (3 instances) existe, est sauvegardé
  (Barman), durable, supervisé, et **déjà au contrat**
  ([ADR 0043](0043-contrat-interface-cluster-atlas.md) : « CloudNativePG
  accessible par DSN depuis les namespaces consommateurs »). Ajouter un cache =
  **une base logique de plus** sur un serveur déjà opéré, pas une brique de
  plus.
- **Le besoin est modeste et borné.** Caches de flux : TTL 24 h, payloads JSON
  de taille raisonnable, débit de rafraîchi faible. On n'a besoin ni du débit ni
  de la latence sub-milliseconde de Redis. Une table clé-valeur Postgres tient
  largement cette charge.
- **L'[ADR atlas 0040](https://atlas.example-org/decisions/0040-caches-flux-backing-service-vs-fichier)
  l'autorise explicitement** comme back-end prod (« la base relationnelle déjà
  présente »). Choisir Postgres est strictement conforme, pas un détournement.

**Coût assumé** : on renonce à la sémantique cache native (TTL serveur, verrous
idiomatiques). On le compense par des mécanismes Postgres standards (§2), au
prix d'un peu plus de SQL dans l'adaptateur atlas. Le compromis penche pour la
sobriété : **une brique de moins à opérer** vaut un adaptateur un peu plus
verbeux. Si un jour un usage exige un vrai cache mémoire (débit, latence), un
ADR contraire réintroduira Redis — la décision est révisable, pas dogmatique.

### 2. Concurrence en Postgres — répondre aux garanties exigées par l'ADR atlas 0040

L'[ADR atlas 0040](https://atlas.example-org/decisions/0040-caches-flux-backing-service-vs-fichier)
exige du back-end : **accès atomiques** (garantis par le back-end, pas par le
code), **TTL porté par le back-end quand il le permet**, **aucune hypothèse
mono-instance** (« un cache qui ne tolère pas deux écrivains simultanés n'est
pas prod-ready »), et pour le multi-instance un **verrou distribué + une clé
d'horodatage partagée**. Postgres sert l'intégralité de ce contrat :

- **Table clé-valeur.** Une table
  `cache(key TEXT PRIMARY KEY, value JSONB, saved_at TIMESTAMPTZ)` porte à la
  fois le payload du flux **et** la clé d'horodatage `lastRefreshAt` du bridage.
  La colonne `saved_at` permet de **porter le TTL côté back-end** (souhait
  d'[ADR atlas 0040](https://atlas.example-org/decisions/0040-caches-flux-backing-service-vs-fichier))
  plutôt que de le recalculer en JS — voir le risque « double-vérité du TTL » au
  §Conséquences.
- **Écritures concurrentes sûres (atomicité)** →
  `INSERT ... ON CONFLICT (key) DO UPDATE SET value = ..., saved_at = ...`
  (UPSERT atomique). Sémantique « dernier écrivain gagne, sans état
  intermédiaire visible » — exactement ce que l'écriture `tmp`+`rename`
  d'atlas-stats émule au niveau FS, mais **garanti inter-instances** par le
  moteur transactionnel.
- **Déduplication des actualisations en vol** (dédup multi-réplique) →
  `pg_try_advisory_lock(<clé dérivée du nom de cache>)`. Une seule réplique
  tient le verrou et fait le fetch ; les autres voient le verrou pris et
  attendent / réutilisent le résultat. C'est le **verrou distribué** que la
  `Promise` locale ne peut pas offrir entre répliques.
- **Bridage de cadence global** (`MIN_REFRESH_INTERVAL_MS`) → lecture/écriture
  de `lastRefreshAt` sous le **même** advisory lock (check-and-set sérialisé) :
  le bridage devient **global à toutes les répliques**, plus une variable par
  process.

Ces trois mécanismes (advisory lock, UPSERT, table clé-valeur horodatée) sont du
Postgres standard, sans extension. **Le cluster fournit la base, le rôle et le
DSN ; le SQL ci-dessus est écrit dans l'adaptateur atlas** (§Frontière).

### 3. Base/schéma `cache` + rôle dédié — pattern du dépôt

Une **base logique dédiée** `cache` sur le Cluster `pg`, pas un schéma partagé,
suivant la convention « une base par usage »
d'[ADR 0024](0024-postgres-manage-cloudnative-pg.md) (isolation des sauvegardes,
rétentions, contention — comme dagster, pgvector, marquez, mlflow). Quatre
points, tous **génériques** au rôle Ansible `platform-cnpg` (rien à coder dans
`tasks/main.yaml`, qui applique déjà ces manifestes) :

- **Rôle managé** `cache` dans `platform/cloudnative-pg/cluster.yaml`
  (`spec.managed.roles`), **avec `passwordSecret: { name: pg-role-cache }`** —
  un rôle managé **sans** `passwordSecret` est créé avec `rolpassword` NULL,
  connexion impossible (vérifié au banc) ; le `passwordSecret` est
  **obligatoire**.
- **Base logique** `kind: Database` (`name`/`owner: cache`, `cluster: pg`) dans
  `platform/cloudnative-pg/database.yaml` (l'operator exécute `CREATE DATABASE`
  ; pas d'extension).
- **Secret** `pg-role-cache` (`kubernetes.io/basic-auth`, clés
  `username`/`password`) dans
  `platform/cloudnative-pg/role-secrets.example.yaml` — **valeur de test** au
  banc ; en prod le Secret vient de la config locale non versionnée
  (`cnpg_role_secrets_src`, jamais committé —
  [ADR 0023](0023-plateforme-exemple-generique/)).
- **Identifiant `cache`** (jamais une marque) conformément à la nomenclature
  partagée d'[ADR 0043](0043-contrat-interface-cluster-atlas.md).

### 4. Contrat — endpoint cache + DSN, mapping vers les variables atlas

Le Service `pg-rw.postgres` **existe déjà**
([ADR 0043](0043-contrat-interface-cluster-atlas.md), `endpoints` id
`postgres-rw`) : le cache est une **base de plus sur le même Service**, pas un
nouveau Service. On ajoute un point de contact `postgres-cache`
(`service: pg-rw`, `namespace: postgres`, `port: 5432`, `auth: secret-role`,
base logique `cache`) à `contract/endpoints.example.yaml`, l'entrée
correspondante sous `secrets.postgres_roles.items` de
`contract/namespaces-secrets.example.yaml` (`secret: pg-role-cache`,
`role: cache`, `database: cache`), et un bloc de variables **dédié** dans
`contract/atlas.env.cluster.example` (ne **pas** écraser les `POSTGRES_*`
pgvector) :

```sh
# ── Cache partagé des flux (backing service CNPG, base cache) ──
POSTGRES_CACHE_HOST=pg-rw.postgres        # nom COURT (cf. note DNS)
POSTGRES_CACHE_PORT=5432
POSTGRES_CACHE_DB=cache
POSTGRES_CACHE_USER=cache
POSTGRES_CACHE_PASSWORD=cache-test-password   # lu du Secret pg-role-cache
```

Le DSN se compose à la convention du dépôt :
`postgres://${user}:${password}@${host}:${port}/${db}` (mêmes variables que
l'index pgvector côté atlas).

**Point dur du mapping — chemin fichier vs DSN.** Aujourd'hui
`ATLAS_STATS_CACHE_PATH`/`CRF_LOGS_CACHE_PATH` désignent **un chemin de
fichier** (`path.resolve`), **pas** un `postgres://`. Poser les
`POSTGRES_CACHE_*` ne suffit **pas** à brancher le cache : atlas doit d'abord
implémenter un adaptateur Postgres derrière
`readCache`/`writeCache`/`isCacheStale` (et un `RefreshCoordinator` adossé à
l'advisory lock), **sélectionné par variable d'environnement**, qui consomme ce
DSN. **C'est une décision déjà actée côté atlas, pas l'état du code** ; à tracer
en **issue atlas** (hors périmètre). Que l'interface évolue vers un PATH spécial
(`postgres://...` reconnu) ou une variable de sélection de back-end + DSN
distinct relève d'atlas.

**DNS — nom court obligatoire.** Utiliser `pg-rw.postgres`, **jamais** le FQDN
`*.svc.cluster.local` : un search domain externe fait timeouter le FQDN complet
en prod (mémoire « FQDN svc.cluster.local timeout prod » ; `access.sh` émet
encore le FQDN long — incohérence préexistante à ne pas aggraver).

**NetworkPolicy default-deny.** Le namespace consommateur du cache **doit** être
sur l'allowlist `platform/network-policies/postgres/allow-postgres-ingress.yaml`
(aujourd'hui dagster/marquez/mlflow/citation-serving) — sinon **DROP
silencieux** (timeout, pas erreur claire). Si le rôle `cache` doit être lu
depuis un pod **hors namespace `postgres`**, prévoir un **Secret dérivé**
(patron `pgvector-pg-auth`), le Secret `pg-role-cache` n'étant pas atteignable
cross-namespace.

### 5. Frontière des dépôts

- **Cluster (ce dépôt)** : la brique CNPG, la base `cache`, le rôle/Secret
  `pg-role-cache`, le DSN au contrat
  ([ADR 0043](0043-contrat-interface-cluster-atlas.md)), la NetworkPolicy, la
  preuve e2e au banc.
- **Atlas (hors périmètre — dépôt en dev actif, rien modifié ici)** :
  l'**adaptateur** `readCache`/`writeCache`/`isCacheStale` + le
  `RefreshCoordinator` Postgres derrière l'interface, sélectionnés par variable
  d'environnement, et l'ajout du point de contact `cache` au contrat côté atlas
  ([ADR atlas 0033](https://atlas.example-org/decisions/0033-contrat-interface-cluster)).
  Tracé en **issue atlas #150** (hors périmètre cluster). Le cluster **ne ferme
  pas** le contrat à lui seul.

### 6. Preuve e2e au banc — local-path, mono-nœud

La preuve se fait sur `bench/lima/run-phases.sh atlas` (socle léger
**local-path** incluant CNPG — plus de banc Ceph,
[ADR 0085](0085-preuves-applicatives-local-path.md)) : le Cluster `pg` + base
`cache`

- Secret `pg-role-cache` y sont sans Ceph. Scénario à ajouter
  (`33-postgres-cache-shared.sh`, sur le gabarit du scénario
  marquez/openlineage), avec une fonction pure `classify_cache_dedup` dans
  `bench/lima/dataops-assert.sh` (testable bats), prouvant les **trois
  invariants**
  d'[ADR atlas 0040](https://atlas.example-org/decisions/0040-caches-flux-backing-service-vs-fichier)
  avec **deux répliques** d'un consommateur jetable partageant
  `POSTGRES_CACHE_*` :

- **dédup** : une seule ligne de cache après actualisations concourantes
  (`SELECT count(*)` = 1 sur la clé) ;
- **bridage** : `MIN_REFRESH_INTERVAL_MS` respecté en partagé (pas N refreshes
  simultanés) ;
- **pas de corruption** : lecture toujours d'un row JSON valide sous écritures
  concourantes (atomicité **garantie par Postgres**, pas par le code).

Re-prouver par rejeu (`changed=0`) que l'ajout rôle/base est idempotent — un
rôle managé densifie le CR via l'operator, le rejeu immédiat peut afficher
`changed` (mémoire « idempotence CR densifié »). **Corriger le CODE, pas
l'état** ([ADR 0046](0046-corriger-le-code-pas-l-etat/) /
[ADR 0052](0052-reproductibilite-des-resultats.md)).

## Conséquences

**Positives**

- **Une brique de moins à opérer** : pas de Redis à déployer/durcir/sauvegarder/
  superviser. Le cache hérite de l'HA, des backups et de la durabilité du
  Cluster `pg` déjà en place.
- **Conforme au contrat existant** : réutilise le Service/DSN
  d'[ADR 0043](0043-contrat-interface-cluster-atlas.md) ; pas de nouveau
  Service, pas de nouveau chemin réseau.
- **Garanties de concurrence servies** : atomicité (UPSERT), verrou distribué
  (advisory lock), bridage global (clé d'horodatage) — l'intégralité du contrat
  d'[ADR atlas 0040](https://atlas.example-org/decisions/0040-caches-flux-backing-service-vs-fichier).

**Négatives / coûts assumés**

- **Sémantique cache non native** : pas de TTL serveur ni de verrous
  idiomatiques « gratuits » comme avec Redis ; on les recompose en SQL dans
  l'adaptateur atlas. Compromis explicitement pesé en faveur de la sobriété
  (§1).
- **Adaptateur atlas obligatoire** : un DSN ne suffit pas tant que
  `readCache`/`writeCache` parlent au système de fichiers. **Bloquant côté
  atlas** (issue #150 / adaptateur), hors périmètre de ce dépôt.
- **Contrat à compléter des deux côtés** : ce dépôt ajoute `postgres-cache` à
  son contrat ; atlas doit ajouter le point de contact `cache` au sien — à
  coordonner.

**Risques à PROUVER au banc (jamais présumer —
[ADR 0046](0046-corriger-le-code-pas-l-etat/) /
[ADR 0052](0052-reproductibilite-des-resultats.md))**

- **Double-vérité du TTL** : si `saved_at` porte le TTL côté back-end **et** que
  l'app le recalcule (`Date.now() - savedAt`), décider qui fait foi — sinon deux
  vérités divergentes. À trancher avec l'adaptateur atlas.
- **Verrou distribué effectif** : sans `pg_advisory_lock` réellement câblé, N
  répliques = jusqu'à N fetchs (la `Promise` locale ne dédup pas
  inter-instances). Le verrou est **obligatoire**, pas optionnel.
- **NetworkPolicy** : un consommateur hors {dagster,marquez,mlflow,
  citation-serving} = DROP silencieux ; vérifier l'allowlist **avant** de
  conclure.
- **Secret cross-namespace** : `pg-role-cache` (ns `postgres`) inatteignable
  ailleurs ; prévoir un Secret dérivé (patron `pgvector-pg-auth`) si besoin.
- **Idempotence** : rôle managé densifié par l'operator → prouver `changed=0` au
  rejeu, ne pas patcher l'état.
- **DNS** : nom court `pg-rw.postgres`, jamais le FQDN (timeout prod).
- **RAM banc** : dataops+mlflow sature déjà ~12 GiB en local-path mono-nœud ;
  dimensionner les 2 répliques + probes psql.
- **Cibler explicitement le banc** : sans kubeconfig banc, les commandes
  retombent sur la PROD (mémoire « isolation banc/prod kubeconfig fallback »).

## Voir aussi

- [Plan de mise en œuvre](../plans/plan-cache-flux-cnpg.md) — base/rôle `cache`,
  contrat + DSN, preuve e2e banc, frontière atlas (4 étapes).
- [ADR 0024](0024-postgres-manage-cloudnative-pg.md) — PostgreSQL managé via
  CloudNativePG (la brique **réutilisée** ; base `cache` ajoutée comme usage).
- [ADR 0043](0043-contrat-interface-cluster-atlas.md) — Contrat d'interface
  cluster → atlas (point de contact `postgres-cache` ajouté).
- [ADR 0085](0085-preuves-applicatives-local-path.md) — Preuves applicatives sur
  local-path (profil de la preuve e2e du cache).
- [ADR 0046](0046-corriger-le-code-pas-l-etat/) /
  [ADR 0052](0052-reproductibilite-des-resultats.md) — Corriger le code, pas
  l'état / reproductibilité (idempotence prouvée par rejeu).
- [ADR 0019](0019-durcissement-reseau-cilium.md) — Durcissement réseau /
  default-deny (allowlist du consommateur du cache).
- [ADR 0023](0023-plateforme-exemple-generique/) — Valeurs génériques
  (`cache-test-password`, identifiant `cache`).
- ADR atlas 0040 — Caches de flux : backing service vs fichier (le contrat
  applicatif **servi** par cet ADR ; le branchement effectif relève de ce
  dépôt).
- ADR atlas 0033 — Contrat d'interface côté atlas (point de contact `cache` à y
  ajouter, hors périmètre).

---
