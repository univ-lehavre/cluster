# kube-prometheus-stack

Observabilité **palier 2**
([ADR 0016](../../docs/decisions/0016-observabilite.md)) : Prometheus +
Alertmanager + Grafana + kube-state-metrics + node-exporter, et activation du
monitoring Ceph. Complète le palier 1 (metrics-server, autonome).

Géré par **Ansible/kubectl, pas par Argo CD** (anti-bootstrap-circulaire, comme
cilium/cert-manager/argocd —
[ADR 0022](../../docs/decisions/0022-argocd-gitops-applicatif.md)).

## Fichiers

| Fichier                      | Rôle                                                                       |
| ---------------------------- | -------------------------------------------------------------------------- |
| `crds.yaml`                  | CRDs `monitoring.coreos.com` (à appliquer **en premier**, `--server-side`) |
| `kube-prometheus-stack.yaml` | operator + Prometheus + Alertmanager + Grafana + exporters                 |
| `gateway.yaml`               | exposition Grafana (Gateway Cilium + TLS interne)                          |
| `values.bench.yaml`          | values Helm de rendu (régénération reproductible)                          |

## Déploiement — ORDRE IMPÉRATIF

L'ordre n'est **pas** négociable (un `kubectl apply` global échoue) :

```bash
# 1. CRDs monitoring.coreos.com (server-side car volumineuses)
kubectl apply --server-side -f platform/kube-prometheus-stack/crds.yaml

# 2. cert-manager doit être déployé (palier 1.3) — il fournit le cert du webhook
#    operator (admissionWebhooks.certManager.enabled=true). Les CRDs Gateway API
#    doivent aussi préexister (posées par Cilium / cilium-expo).

# 3. Le stack : l'operator attend le Secret du webhook créé par cert-manager,
#    puis les CRs (Prometheus/Alertmanager/PrometheusRule) passent par son webhook.
kubectl apply -f platform/kube-prometheus-stack/kube-prometheus-stack.yaml
kubectl -n monitoring rollout status deploy/kube-prometheus-stack-operator

# 4. Exposition Grafana
kubectl apply -f platform/kube-prometheus-stack/gateway.yaml

# 5. SEULEMENT APRÈS : activer le monitoring Ceph (storage/ceph/cluster.yaml
#    monitoring.enabled=true déjà posé) — Rook crée le ServiceMonitor mgr.
```

> Si l'operator reste en `FailedMount` du Secret
> `kube-prometheus-stack-admission` alors que le Secret existe, supprimer son
> pod pour forcer le remount.

## Adaptations à ce cluster (cf. `values.bench.yaml`)

- **Images épinglées par digest d'index multi-arch**
  ([ADR 0006](../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md))
  — banc arm64.
- **Empreinte bornée** (`requests`/`limits`) — cluster hyperconvergé
  ([ADR 0009](../../docs/decisions/0009-pourquoi-4-noeuds.md)).
- **PVC** sur `rook-ceph-block-replicated` (×3) ; rétention Prometheus 15 j.
- **Webhook operator via cert-manager**
  ([ADR 0021](../../docs/decisions/0021-cert-manager-ca-interne.md)) — pas de
  job certgen.
- **`serviceMonitorSelector` vide** : scrape **tous** les ServiceMonitor, dont
  celui du mgr Ceph.
- **Alertmanager → mail paramétrable** : défaut `mailpit.mail.svc:1025` (puits
  de test, cf. [platform/mailpit/](../mailpit/)) ; en prod, surcharger vers un
  service type Mailgun (config locale non versionnée,
  [ADR 0023](../../docs/decisions/0023-plateforme-exemple-generique.md)).

## Exposition

Seul **Grafana** est exposé via le Gateway (`grafana.cluster.lan`, TLS interne).
Prometheus et Alertmanager restent en `kubectl port-forward` (pas de surface
publique).

## Régénérer le manifeste vendored

```bash
helm template kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 86.1.0 --namespace monitoring --include-crds \
  -f platform/kube-prometheus-stack/values.bench.yaml > /tmp/out.yaml
# puis séparer les CRDs dans crds.yaml et injecter les digests d'index.
```
