# 0026 — Orchestration des pipelines via Dagster

## Contexte

Le socle DataOps a besoin d'un orchestrateur pour les pipelines batch
(ingestion, transformations dbt, lineage). Le profil DataOps remplace les
CronJobs K8s bruts par un orchestrateur déclaratif avec historique des runs,
schedules, sensors et observabilité. L'étape 1.6
([ADR 0024](0024-postgres-manage-cloudnative-pg.md)) a posé un PostgreSQL managé
(CloudNativePG) avec une base `dagster` prête pour l'event log. Le **code
métier** (assets, IO managers DuckDB↔S3) vit dans le dépôt `atlas` (Phase 2+) ;
ici on déploie l'**orchestrateur seul**.

## Décision

**Dagster** sur Kubernetes (chart `dagster/dagster` 1.13.7), dans
[`platform/dagster/`](../../platform/dagster/), déployé par `kubectl apply`
comme les autres addons ([ADR 0022](0022-argocd-gitops-applicatif.md) — pas Argo
CD pour l'infra ; le namespace `dagster` reste destinataire Argo CD pour le
**code** d'atlas).

- **Composants** : webserver (UI), daemon (schedules/sensors/run queue),
  **`K8sRunLauncher`** — chaque run devient un **Job Kubernetes** dans le
  namespace `dagster`.
- **Storage dans CloudNativePG** : event log, run storage et schedule storage
  pointent la base `dagster` (Services `pg-rw.postgres.svc:5432`), **jamais
  SQLite éphémère**. Le chart est configuré avec `postgresql.enabled: false` +
  host/user/db externes. Le mot de passe vient d'un **Secret dérivé**
  `dagster-pg-auth` (clé `postgresql-password`), recopié du Secret CNPG
  `pg-dagster` — config locale non versionnée
  ([ADR 0023](0023-plateforme-exemple-generique.md)).
- **Orchestrateur « vide »** : `dagster-user-deployments` désactivé, aucune
  code-location. Le code (assets) est packagé côté `atlas`.
- **Vendoring « helm template figé »** (comme Loki / kube-prometheus-stack) :
  `values.bench.yaml` → `dagster.yaml` rendu et committé, déployé par `kubectl`.
- **Exposition** du webserver via le Gateway Cilium + TLS interne
  ([ADR 0020](0020-exposition-reseau-tout-cilium.md)/[0021](0021-cert-manager-ca-interne.md)),
  **sans auth** : réseau privé de confiance mono-admin
  ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)), comme le registry et
  le dashboard. Une auth en bordure (oauth2-proxy) reste une évolution
  ultérieure.

### Image : amd64-only en amont → build arm64 en interne

Les images Dagster officielles (`docker.io/dagster/dagster-celery-k8s`) sont
publiées en **amd64 uniquement** (dagster-io/dagster#11841, #17167 — infra de
build multi-arch jamais mise en place). Dagster étant du **pur Python** («
cross-compiles to ARM, no C changes »), on **construit une image arm64 en
interne**
([`platform/dagster/image/Dockerfile`](../../platform/dagster/image/Dockerfile),
fidèle à l'officiel : `python:3.10-slim` + mêmes packages). C'est le **premier
build d'image maison du dépôt** (jusqu'ici 100 % vendored upstream). Selon la
topologie :

- **bare-metal (x86)** : image **officielle** amd64 ;
- **banc léger Lima (arm64)** : image **maison** arm64.

Les deux sont poussées dans le **registry interne**
([ADR 0011](0011-registry-http-sans-auth.md)) sous le même repo/tag ; le
manifeste référence `registry:80/dagster-celery-k8s:1.13.7`. L'image `postgres`
(init wait-for-db) reste épinglée par digest d'index multi-arch
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).

## Statut

Accepted (2026-06-04). **Validation banc en suivi** (#144) : recréer le banc
Lima (K8s v1.34, image arm64 maison) et prouver e2e webserver + daemon Ready,
storage dans la base CNPG `dagster` (pas de SQLite), run via `K8sRunLauncher`.
Un blocage `ImagePullBackOff` du registry interne reste à lever (cause racine
candidate : digest mono-arch du registry, #140).

## Conséquences

**Bénéfices.**

- Orchestration déclarative (runs, schedules, sensors, UI) remplaçant les
  CronJobs.
- Historique/observabilité des runs persistés dans Postgres (HA, sauvegardé).
- Séparation nette infra (ici) / métier (atlas).

**Coûts assumés.**

- **Image arm64 à construire/maintenir en interne** (premier build maison) : à
  reconstruire à chaque bump de version Dagster. Suivi via la matrice ADR 0006.
- **Webserver sans auth** : acceptable sur réseau privé mono-admin ; à durcir si
  le cluster s'ouvre.
- Composant supplémentaire (webserver + daemon + Jobs de run) —
  `requests`/`limits` bornés.

## Alternatives écartées

- **CronJobs K8s bruts** : pas d'historique, pas de dépendances entre tâches,
  pas d'UI — ce que Dagster apporte.
- **Image officielle amd64 seule** : casse le banc arm64 (`exec format error`).
- **Image communautaire arm64 tierce** : dépendance non officielle (sécurité /
  maintenance) — on préfère maîtriser le build.
- **Argo CD pour l'orchestrateur** : mêlerait infra et GitOps applicatif,
  contraire au patron des addons (ADR 0022).

## À revoir

- Si Dagster publie des images multi-arch officielles : retirer le build maison
  arm64.
- Brancher un ServiceMonitor Dagster sur le monitoring (métriques de runs).
- Auth en bordure du webserver (oauth2-proxy) si ouverture du cluster.
