# La chaîne DataOps de bout en bout — accès & vérifications

Vue **transverse** du socle DataOps assemblé : pour chaque brique (infra et
logiciel), son rôle, **comment y accéder** (URL navigateur via le Gateway, ou
commande console) et **les actions vérifiables** (ce qu'on consulte/clique dans
l'UI, ce qu'on lance en CLI) pour prouver qu'elle est vivante et correctement
câblée.

Ce document est la **carte d'accès** unifiée ; le détail de déploiement de
chaque brique vit dans son `README` (lié dans le tableau). La validation
assemblée est portée par le harnais
[`dataops-chain`](../../bench/lima/run-phases.sh) (#148).

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

- **Automatisé** : `bench/lima/run-phases.sh dataops-chain` déploie la chaîne,
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

## Voir aussi

- [Validation sur banc](validation-banc.md) — méthodologie des runs.
- [`platform/marquez/`](../../platform/marquez/) ·
  [`platform/dagster/`](../../platform/dagster/) ·
  [`platform/cloudnative-pg/`](../../platform/cloudnative-pg/) — déploiement par
  brique.
