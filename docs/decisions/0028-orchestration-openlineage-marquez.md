# 0028 — Store de lineage OpenLineage via Marquez

## Contexte

Dernière brique du socle DataOps. Après l'orchestrateur
([ADR 0026](0026-orchestration-dagster.md), étape 1.7) et le PostgreSQL managé
([ADR 0024](0024-postgres-manage-cloudnative-pg.md), étape 1.6), il manque la
**traçabilité du lineage** : quels jeux de données produisent quels autres, par
quels jobs, avec quel schéma. Le standard ouvert **OpenLineage** décrit ces
événements ; **Marquez** est son store/serveur de référence (collecte,
agrégation, API et visualisation). Le lineage est **émis** par Dagster (sensor
OpenLineage) et, en Phase 2+, par le code `atlas` (dbt, assets) ; Marquez ne
fait qu'**ingérer et visualiser** — il ne pilote rien.

## Décision

**Marquez** (API + UI web) sur Kubernetes (chart `marquezproject/marquez`
0.51.1), dans [`platform/marquez/`](../../platform/marquez/), déployé par
`kubectl apply` comme les autres addons
([ADR 0022](0022-argocd-gitops-applicatif.md) — pas Argo CD pour l'infra).

- **Composants** : API Marquez (collecte/agrégation, port 5000 ; health 5001) et
  **UI web** (visualisation, port 3000). L'UI appelle l'API en intra-cluster.
- **Store dans CloudNativePG, base dédiée `marquez`** : Marquez applique ses
  **migrations Flyway au démarrage** (`MIGRATE_ON_STARTUP=true`) — d'où une
  **base dédiée**, pas un schéma dans une base partagée. Cette base est ajoutée
  au **cluster CNPG HA unique `pg`** (un seul cluster PostgreSQL HA porte toutes
  les bases applicatives — `dagster`, `pgvector`, `marquez` — plutôt qu'un
  cluster par appli). Le subchart `bitnami/postgresql` du chart est
  **désactivé** (`postgresql.enabled: false`) ; host/user/db pointent
  `pg-rw.postgres.svc:5432`. Le mot de passe vient d'un **Secret dérivé**
  `marquez-pg-auth` (clé `marquez-db-password`, pointée par
  `marquez.existingSecretName`), recopié du Secret CNPG `pg-marquez` — config
  locale non versionnée ([ADR 0023](0023-plateforme-exemple-generique.md)).
- **InitContainer wait-for-db** ajouté au rendu (le chart ne le rend que pour le
  subchart postgres) ; image `postgres` épinglée par digest d'index multi-arch
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).
- **Vendoring « helm template figé »** (comme Dagster / Loki) :
  `values.bench.yaml` → `marquez.yaml` rendu et committé. Retouches locales
  documentées en en-tête du rendu (init wait-for-db, port Service web, retrait
  des Pods `helm test`).
- **Exposition de l'UI web seule** via le Gateway Cilium + TLS interne
  ([ADR 0020](0020-exposition-reseau-tout-cilium.md)/[0021](0021-cert-manager-ca-interne.md)),
  **sans auth** : réseau privé de confiance mono-admin
  ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)), comme Dagster et le
  registry. **L'API reste interne** : les émetteurs OpenLineage (sensor Dagster,
  code atlas) la joignent par le Service ClusterIP `marquez.marquez.svc:5000` ;
  pas besoin de la publier en bordure. Une auth en bordure reste une évolution
  ultérieure.
- **Invariant — aucune PII dans le lineage** : les métadonnées tracées sont des
  noms d'assets/colonnes **techniques**, jamais de donnée nominative (ADR 0023).

### Images : amd64-only en amont → build arm64 en interne

Les images officielles `docker.io/marquezproject/marquez` (API) **et**
`marquez-web` (UI) sont publiées en **amd64 uniquement** (vérifié Docker Hub,
0.51.1). Leurs bases sont multi-arch (`eclipse-temurin:17` pour l'API Java,
`node:18-alpine` pour l'UI React) → les images **arm64** se reconstruisent
depuis le source au tag, sans modification des Dockerfiles upstream
([`image/`](../../platform/marquez/image/Dockerfile),
[`image-web/`](../../platform/marquez/image-web/Dockerfile), copies fidèles).
Selon la topologie :

- **bare-metal (x86)** : images **officielles** amd64 (re-taguées) ;
- **banc léger Lima (arm64)** : images **maison** arm64.

Les deux sont poussées dans le **registry interne**
([ADR 0011](0011-registry-http-sans-auth.md)) ; le manifeste référence
`registry:80/marquez:0.51.1` et `registry:80/marquez-web:0.51.1`.

## Statut

Accepted (2026-06-05). **Validation banc en suivi** (#130/#148) : la chaîne
DataOps assemblée (`monitoring → CNPG → Dagster → Marquez`) est validée par le
harnais reproductible `test/lima/run-phases.sh dataops-chain`, qui prouve e2e
l'ingestion d'un événement OpenLineage émis par un **vrai run Dagster** (sensor
`openlineage-dagster`) et visible dans Marquez. Ce harnais **clôt l'épopée de
validation systémique #148** une fois le run consigné dans
[`test/lima/RESULTS.md`](../../test/lima/RESULTS.md).

## Conséquences

**Bénéfices.**

- Traçabilité du lineage (OpenLineage, standard ouvert) avec API + UI.
- Store HA/sauvegardé (base CNPG `marquez`), pas d'infrastructure stateful
  supplémentaire (réutilise le cluster `pg`).
- Socle DataOps complet : orchestration (Dagster) + métadonnées/lineage
  (Marquez).
- Le harnais E2E rend la validation de la chaîne **reproductible** (corrige
  l'anti-pattern « livrer lint-clean, reporter l'E2E » constaté en #148).

**Coûts assumés.**

- **Deux images arm64 à construire/maintenir en interne** (API + web) : à
  reconstruire à chaque bump. Suivi via la matrice ADR 0006.
- **API/UI sans auth** : acceptable sur réseau privé mono-admin ; à durcir si le
  cluster s'ouvre.
- Migrations Flyway au démarrage : une base dédiée par contrainte (acceptée).

## Alternatives écartées

- **Schéma dans une base partagée** (plutôt qu'une base dédiée) : Flyway gère un
  historique de migrations par base ; un schéma partagé imposerait un
  `search_path`/owner fragile et heurterait les migrations. Base dédiée retenue.
- **Un cluster CNPG dédié à Marquez** : doublerait l'infrastructure stateful HA
  pour un store modeste. Un seul cluster `pg` partagé (une base par appli)
  suffit.
- **Subchart bitnami/postgresql du chart Marquez** : créerait un Postgres
  parallèle non HA/non sauvegardé, hors de notre CNPG. Désactivé.
- **Images officielles amd64 seules** : cassent le banc arm64
  (`exec format error`).
- **POST OpenLineage synthétique pour la validation** : prouverait « Marquez
  ingère » mais pas « Dagster émet ». On valide la **vraie chaîne** via un
  émetteur Dagster jetable (sensor réel), plus honnête vis-à-vis de #148.

## À revoir

- Si Marquez publie des images multi-arch officielles : retirer les builds
  maison arm64.
- Brancher un ServiceMonitor Marquez sur le monitoring (métriques d'ingestion).
- Auth en bordure de l'UI (oauth2-proxy) si ouverture du cluster.
- Politique de rétention du lineage (`dbRetention`) à ajuster selon le volume
  réel.
