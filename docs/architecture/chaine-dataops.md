# La chaîne DataOps de bout en bout — accès & vérifications

Vue **transverse** du socle DataOps assemblé : pour chaque brique (infra et
logiciel), son rôle, **comment y accéder** (URL navigateur via le Gateway, ou
commande console) et **les actions vérifiables** (ce qu'on consulte/clique dans
l'UI, ce qu'on lance en CLI) pour prouver qu'elle est vivante et correctement
câblée.

Ce document est la **carte d'accès** unifiée ; le détail de déploiement de
chaque brique vit dans son `README` (lié dans le tableau). La validation
assemblée est portée par le harnais
[`cluster-dataops`](../../bench/lima/run-phases.sh) (#148).

> **Valeurs génériques (ADR 0023).** Les URLs `https://<svc>.cluster.lan` sont
> des **placeholders** : sur une topologie réelle, l'administrateur réseau
> substitue le hostname. Les commandes console supposent un `kubectl` pointant
> le cluster (sur le banc Lima : `KUBECONFIG=bench/lima/.work/kubeconfig`).

## Flux d'ensemble

```text
                    ┌──────────────────────────────────────────────┐
                    │              Observabilité (transverse)       │
                    │  Prometheus ─ Grafana ─ Loki ─ Mailpit         │
                    └──────────────────────────────────────────────┘
   source de              ┌─────────┐      ┌─────────┐     ┌──────────┐
   données    ──────────▶ │ Dagster │ ───▶ │  CNPG   │ ◀── │ Marquez  │
   (atlas, Phase 2+)      │ (orch.) │      │ (store) │     │(lineage) │
                          └────┬────┘      └─────────┘     └────▲─────┘
                               │  sensor OpenLineage             │
                               └─────────────────────────────────┘
                                 (événements de lineage POST API)

   ── Couche infra ─────────────────────────────────────────────────
   Kubernetes (kubeadm) · Cilium + Gateway API · cert-manager (CA interne)
   · registry interne (HTTP) · stockage (local-path | Rook-Ceph)
```

Dagster orchestre les runs ; leur état/event log est persisté dans **CNPG**
(base `dagster`). Chaque run émet, via le **sensor OpenLineage**, des événements
que **Marquez** ingère (store dans la base `marquez` du même CNPG) et expose
dans son UI. L'observabilité (Prometheus/Loki/Mailpit) est transverse.

Ce document décrit **deux niveaux** : le **socle** DataOps (infra + briques
plateforme, ci-dessous — la carte d'accès) et la **chaîne applicative réelle**
qui tourne dessus (section
[« Chaîne applicative (citation) »](#chaine-applicative-citation-progression-reelle)).
La « source de données » abstraite du schéma est, en pratique, le snapshot
public **OpenAlex** ingéré par la code-location `citation`.

## Briques d'infrastructure

| Brique                                 | Rôle (ADR)                                                                                                                                         | Accès — navigateur / console                                                        | Actions vérifiables                                                                                           |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Kubernetes** (kubeadm)               | Plan de contrôle + nœuds ([0002](../decisions/0002-control-plane-unique-avec-endpoint.md), [0014](../decisions/0014-durcissement-kubeadm-init.md)) | console : `kubectl …` ; UI : [Dashboard](../../platform/k8s-dashboard/) via Gateway | `kubectl get nodes` → 3× `Ready` ; `kubectl get pods -A` ; Dashboard : workloads par namespace                |
| **Cilium + Gateway API**               | CNI + exposition tout-Cilium ([0019](../decisions/0019-durcissement-reseau-cilium.md), [0020](../decisions/0020-exposition-reseau-tout-cilium.md)) | console : `cilium status`, `hubble observe`                                         | `cilium status` → OK ; WireGuard actif (`cilium_wg0`) ; `kubectl get gateway,httproute -A`                    |
| **cert-manager** (CA interne)          | TLS de bordure des Gateways ([0021](../decisions/0021-cert-manager-ca-interne.md))                                                                 | console : `kubectl -n cert-manager …`                                               | `kubectl get certificate -A` → `Ready=True` ; Secrets `*-server-tls` émis                                     |
| **Registry interne**                   | Images maison HTTP ([0011](../decisions/0011-registry-http-sans-auth.md))                                                                          | console : `registry:80` (ClusterIP)                                                 | `curl -s http://registry:80/v2/_catalog` → liste les images (`marquez`, `marquez-web`, `dagster-celery-k8s`…) |
| **Stockage** (local-path \| Rook-Ceph) | PVC pour les workloads stateful ([0001](../decisions/0001-replication-x3-pour-workloads-bloc.md))                                                  | console : `kubectl get sc,pvc -A` ; toolbox Ceph                                    | PVC `Bound` ; (Ceph) `ceph health` → `HEALTH_OK`, `ceph osd stat`                                             |

## Briques logicielles (socle DataOps)

| Brique                    | Rôle (ADR)                                                                                                                                                                | Accès — navigateur / console                                                           | Actions vérifiables                                                                                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CloudNativePG** (`pg`)  | PostgreSQL HA managé, store de toutes les bases ([0024](../decisions/0024-postgres-manage-cloudnative-pg.md))                                                             | console : `kubectl -n postgres get cluster pg` ; `psql` via `kubectl -n postgres exec` | cluster `Healthy` 3/3 ; bases `dagster`, `marquez`, `pgvector` présentes (`\l`) ; tables Flyway dans `marquez`                                                                     |
| **kube-prometheus-stack** | Métriques + dashboards                                                                                                                                                    | UI : Grafana / Prometheus via Gateway ; console : `kubectl -n monitoring …`            | Prometheus : targets `up` ; Grafana : dashboards cluster ; règles d'alerte chargées                                                                                                |
| **Loki**                  | Agrégation de logs                                                                                                                                                        | UI : Grafana (datasource Loki)                                                         | requête `{namespace="marquez"}` → logs du pod API                                                                                                                                  |
| **Mailpit**               | Puits mail de test (alertes)                                                                                                                                              | UI : Mailpit via Gateway ; API `mailpit.mail.svc:80`                                   | UI : réception d'un mail d'alerte de test (cf. scénario 22)                                                                                                                        |
| **Dagster**               | Orchestrateur, event log dans CNPG ([0026](../decisions/0026-orchestration-dagster.md))                                                                                   | UI : `https://dagster.cluster.lan` (Gateway) ; console : `kubectl -n dagster …`        | UI : code-location chargée, **lancer un run** (Launchpad), suivre l'event log ; `kubectl -n dagster get deploy` → webserver + daemon Ready                                         |
| **Marquez**               | Store de lineage OpenLineage ([0028](../decisions/0028-orchestration-openlineage-marquez.md))                                                                             | UI : `https://marquez.cluster.lan` (Gateway) ; API interne `marquez.marquez.svc:5000`  | UI : explorer **namespaces / jobs / datasets**, voir le **graphe de lineage** d'un run ; API : `GET /api/v1/namespaces/dagster/jobs` → jobs ingérés                                |
| **MLflow**                | Suivi de modèles + registre ([0082](../decisions/0082-suivi-modeles-mlflow.md)) ; store CNPG `mlflow` + artefacts S3 ([0036](../decisions/0036-backing-s3-unique-rgw.md)) | UI : `https://mlflow.cluster.lan` (Gateway) ; API interne `mlflow.mlflow.svc:5000`     | UI : explorer **experiments / runs / modèles** ; API : `GET /api/2.0/mlflow/experiments/search` → experiments (serveur livré **vide**, peuplé par atlas via `MLFLOW_TRACKING_URI`) |

## Vérifier la chaîne complète (le maillon d'intégration)

Le maillon qui prouve que tout est câblé est **Dagster → Marquez** : un run réel
émet du lineage que Marquez ingère.

- **Automatisé** : `bench/lima/run-phases.sh cluster-dataops` déploie la chaîne,
  lance un run émetteur réel et vérifie l'ingestion ; puis
  `bench/scenarios/run-all.sh ONLY='23'` re-vérifie l'assertion isolément.
- **À la main, dans le navigateur** :
  1. ouvrir l'UI Dagster (`dagster.cluster.lan`), lancer un run d'un asset ;
  2. ouvrir l'UI Marquez (`marquez.cluster.lan`), namespace `dagster` → le
     **job** correspondant apparaît avec son **graphe de lineage**
     (entrées/sorties) ;
  3. en console :
     `kubectl -n postgres exec -it pg-1 -- psql -d marquez -c '\dt'` montre les
     tables Flyway peuplées.
- **État de validation** : [résultats du banc Lima](../../bench/lima/RESULTS.md)
  (section « Chaîne DataOps assemblée »).

> **Code-location jouet du socle
> ([ADR 0086](../decisions/0086-code-location-jouet-du-socle.md)).**
> L'orchestrateur Dagster est livré **vide** (`load_from: []`). Pour exercer la
> chaîne réelle (webserver → gRPC → `K8sRunLauncher` → run → lineage → drift
> MLflow) **sans dépendre du dépôt applicatif**, le socle déploie **par GitOps**
> une code-location jouet `toy-codeloc` (serveur gRPC chargeant `toy_assets` :
> `toy_dataset` émet du lineage, `toy_drift` calcule un drift Evidently et le
> logge dans MLflow). C'est ce que le **scénario 27** prouve (déploiement +
> branchement) et le **29** exécute (run e2e → lineage + MLflow). ⚠️ Les env
> (`MLFLOW_TRACKING_URI`, `OPENLINEAGE_*`) doivent être injectées dans les
> **pods de run** via un tag `dagster-k8s/config` — voir la note du contrat.

## Chaîne applicative (citation) — progression réelle {#chaine-applicative-citation-progression-reelle}

Le socle ci-dessus est la **plomberie** ; la première chaîne _applicative_ qui
la traverse réellement est **citation** (code-location atlas déployée par
App-of-Apps, [ADR 0094/0095](../decisions/)). Cette section décrit la
**progression réelle des données** — telle que **prouvée** sur prod dirqual le
**2026-07-05**
([passage d'audit](../audit/2026-07-05-transform-e2e-prouve-prod.md)) — et non
un flux idéalisé. Elle distingue explicitement ce qui est **prouvé** de ce qui
reste une **frontière** (doctrine à deux étages,
[ADR 0104](../decisions/0104-doctrine-preuve-deux-etages-banc-logique-prod-integration.md)).

### Le flux, étage par étage

```text
OpenAlex S3 (snapshot public, 482 partitions updated_date)
   │  ingestion_job  ──  raw_snapshot (rclone, borné au banc / COMPLET en prod)
   ▼
raw/{works,authors,merged_ids}/           (Ceph RGW, bucket OBC citation-datalake-…)
   │  transform_job (dbt-duckdb)
   ▼
staging (views) → curated_* (parquet external)   ← « mart 1 : tout OpenAlex »
   │                    └─ curated_eunicoast_works ← « mart 2 : ≥1 auteur EUNICoast ∩ <N ans »
   ▼                                    └─ curated_pair_uplift_labels (paires ≥2 co-pubs + baseline solo)
marts_* (researchers, researchers_fts, author_profiles, collab_pairs)
   │
   ├─▶ researcher_embeddings  → marts/researcher_vectors (ONNX all-MiniLM-L6-v2, 384d)
   ├─▶ pair_uplift_model      → prédictions/recos     ─┐  runs MLflow (experiments)
   ├─▶ evidently_*_drift      → verdict S3 + MLflow    ─┤  + rapports Evidently
   ├─▶ great_expectations     → checks + MLflow        ─┘
   └─▶ index_load             → Postgres pgvector (table researchers : embedding+fts)
```

### Ce qui est PROUVÉ (run 6e9a3c32, `RUN_SUCCESS`, 2026-07-05)

- **Ingestion** OpenAlex → `raw/` (Ceph RGW), watermark avancé,
  `ge_raw_contract` PASS.
- **dbt** (staging → curated → marts) sur le **vrai bucket OBC**
  (`s3://citation-datalake-…/{raw,curated,marts}`), 0 test en échec.
- **Embeddings** (`researcher_vectors_manifest`, `work_vectors_manifest`),
  **uplift** (`pair_uplift_model` + run MLflow), **Evidently** drift (check
  passé), **Great Expectations** (3 checks loggés MLflow).
- **`index_load` → pgvector** : table `public.researchers` peuplée (**1152
  lignes**, `embedding vector(384)` + `fts tsvector`), `ge_index_load` PASS.
- **Lineage** Marquez + **runs MLflow** (egress `marquez.marquez:5000` /
  `mlflow.mlflow:5000` opérationnels).

### Frontières (à prouver / conditionnées aux données)

- **Modèle uplift prédictif** : au 1er run, `served_mode=descriptive`
  (`n_pairs_labeled=0`) — pas assez de **paires de collaboration** (≥2 co-pubs
  EUNICoast + baseline solo antérieure des deux côtés) dans une tranche ingérée
  petite. C'est une **condition de données**, pas un bug : le modèle bascule en
  prédictif dès que le volume le permet (bootstrap OpenAlex complet en prod, la
  polarité d'échantillonnage étant désormais **prod-complète par défaut**, le
  banc bornant — cf. la révision d'ingestion et
  [ADR 0104 §5](../decisions/0104-doctrine-preuve-deux-etages-banc-logique-prod-integration.md)).
- **Drift Evidently réel** : exige **2 runs** au même `dt` (le 1er n'a pas de
  baseline N-1). `passed=True, baseline absente` au 1er run est normal.

### Le fil rouge — 5 bugs de config prod, tous dans l'écart banc/prod

Cette chaîne **n'avait jamais tourné E2E** avant le 2026-07-05. Elle a été
débloquée couche par couche par une série de bugs qui **passaient tous le lint
ET le run banc au vert** mais ne se révélaient que sur prod (seed prod I/O ·
chemin OpenAlex `data/jsonl` · quota OBC Ceph · bucket dbt non dérivé de
`BUCKET_NAME` · orphelins `author_id` d'entité OpenAlex). C'est l'illustration
fondatrice de la **doctrine à deux étages** : le banc prouve la **logique**, la
prod prouve l'**intégration externe**
([ADR 0104](../decisions/0104-doctrine-preuve-deux-etages-banc-logique-prod-integration.md),
[passage doctrine](../audit/2026-07-05-banc-lima-vaut-il-le-coup.md)).

## Voir aussi

- [Validation sur banc](validation-banc.md) — méthodologie des runs.
- [`platform/marquez/`](../../platform/marquez/) ·
  [`platform/dagster/`](../../platform/dagster/) ·
  [`platform/cloudnative-pg/`](../../platform/cloudnative-pg/) — déploiement par
  brique.
