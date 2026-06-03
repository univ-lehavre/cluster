# Loki

Agrégation des **logs** ([ADR 0016](../../docs/decisions/0016-observabilite.md)
palier 2). Loki stocke les logs, **Promtail** les collecte sur chaque nœud, et
**Grafana** (cf. [kube-prometheus-stack](../kube-prometheus-stack/)) les explore
via la datasource Loki.

Géré par Ansible/kubectl (pas Argo CD), comme le reste du socle.

## Fichiers

| Fichier                | Rôle                                                        |
| ---------------------- | ----------------------------------------------------------- |
| `loki.yaml`            | Loki 7.0.0 **SingleBinary**, backend S3                     |
| `promtail.yaml`        | DaemonSet Promtail (collecte des logs nœuds/pods → Loki)    |
| `init-buckets.yaml`    | Job créant les buckets S3 de Loki (**à lancer avant** Loki) |
| `values.bench.yaml`    | values Helm de rendu de `loki.yaml`                         |
| `values.promtail.yaml` | values Helm de rendu de `promtail.yaml`                     |

## Déploiement

```bash
# 1. Créer les buckets S3 — Loki en backend S3 ne les auto-crée PAS (NoSuchBucket).
kubectl apply -f platform/loki/init-buckets.yaml
kubectl -n monitoring wait --for=condition=complete job/loki-init-buckets

# 2. Loki + Promtail
kubectl apply -f platform/loki/loki.yaml
kubectl apply -f platform/loki/promtail.yaml
kubectl -n monitoring rollout status statefulset/loki
```

## Adaptations à ce cluster (cf. `values.bench.yaml`)

- **Mode SingleBinary** (monolithique) — adapté à un cluster peu nombreux,
  empreinte maîtrisée (`requests`/`limits` bornés).
- **Backend S3 PARAMÉTRABLE** : défaut **SeaweedFS**
  (`seaweedfs.s3.svc.cluster.local:8333`, banc léger) ; en prod, surcharger vers
  le **RGW Ceph** (objectstore datalake), endpoint + creds dans un Secret non
  versionné
  ([ADR 0023](../../docs/decisions/0023-plateforme-exemple-generique.md)).
- **Rétention 7 jours** (compactor + `retention_period: 168h`).
- **PVC** `standard` (local-path) sur banc léger / `rook-ceph-block-replicated`
  en prod.
- **Images épinglées par digest d'index multi-arch**
  ([ADR 0006](../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md)).

## Dette connue

Le chart `promtail` est **déprécié** en amont (Grafana pousse **Alloy**). Il
fonctionne, mais migrer Promtail → Grafana Alloy est une évolution à prévoir.

## Régénérer les manifestes vendored

```bash
helm template loki grafana/loki --version 7.0.0 --namespace monitoring \
  -f platform/loki/values.bench.yaml > /tmp/loki.yaml        # puis injecter les digests
helm template promtail grafana/promtail --version 6.17.1 --namespace monitoring \
  -f platform/loki/values.promtail.yaml > /tmp/promtail.yaml # puis injecter le digest
```
