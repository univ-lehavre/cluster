# 0016 — Observabilité (metrics-server maintenant, Prometheus plus tard)

## Contexte

L'audit ([08-operabilite](../audit/08-operabilite.md)) classe « aucune
observabilité runtime » en constat **majeur** : pas de metrics-server (donc
`kubectl top` et HPA inopérants), pas de Prometheus/Grafana/alerting, et
`monitoring.enabled: false` côté Ceph. La détection de panne reposait
entièrement sur l'exécution **manuelle** de
[`state.sh`](../../bootstrap/state.sh) par l'unique admin. Aucun ADR ne couvrait
l'observabilité → item ouvert.

L'audit recommande : « a minima metrics-server ; idéalement
kube-prometheus-stack

- `monitoring.enabled: true` ».

## Décision

**Approche par paliers.** On pose le socle autonome maintenant, on diffère le
stack lourd.

### Palier 1 — metrics-server (fait)

[`platform/metrics-server/`](../../platform/metrics-server/) : déploie
metrics-server v0.8.0. Autonome (pas de Prometheus requis), faible empreinte
(`requests` 100m/200Mi). Rend opérants `kubectl top` et les HPA.

### Palier 2 — Prometheus + monitoring Ceph (différé)

`monitoring.enabled: true` dans
[`cluster.yaml`](../../storage/ceph/cluster.yaml) **reste à `false`** tant que
le palier 2 n'est pas fait. Raison technique : le commentaire du CR Rook le dit
— `monitoring.enabled: true` « requires Prometheus to be pre-installed » ;
l'activer ferait créer par l'operator des `PrometheusRule`/`ServiceMonitor` dont
les **CRDs seraient absents** → erreurs. L'activer à vide serait pire que de ne
rien faire.

> Note : l'**exporter Ceph** est déjà actif (`metricsDisabled: false`) — les
> métriques Ceph sont _exposées_, il manque seulement le _collecteur_
> (Prometheus) et les _règles d'alerte_.

À faire au palier 2 (un seul lot cohérent) :

- déployer **kube-prometheus-stack** (Prometheus + Grafana + AlertManager, ou
  équivalent léger), avec les CRDs `monitoring.coreos.com` ;
- passer `monitoring.enabled: true` côté Ceph → alertes OSD down, near-full,
  perte de quorum mon ;
- router AlertManager vers le mail d'exploitation (réutiliser la couche
  `alert`/postfix) ou un webhook.

### Filet actuel (entre les deux paliers)

La surveillance reste **active mais manuelle/ponctuelle** : `state.sh` (drift
par couche, dont santé SMART du NVMe via smartd — audit #19), `report.sh`
(durcissement), et les alertes mail de `smartd`. Pas d'alerting K8s/Ceph temps
réel tant que le palier 2 n'est pas livré.

## Statut

Accepted (2026-06-01).

## Conséquences

**Bénéfices.**

- `kubectl top` / HPA opérationnels tout de suite, empreinte minimale.
- Le constat « majeur » de l'audit est partiellement levé et le reste est
  **tracé** (plus un trou silencieux).

**Coûts assumés.**

- **Pas d'alerting runtime K8s/Ceph** jusqu'au palier 2 : une OSD down ou un
  near-full ne génère pas d'alerte automatique — détection via `state.sh`
  manuel. Risque accepté temporairement (cluster mono-admin, réseau privé).
- `--kubelet-insecure-tls` sur metrics-server (certs kubelet auto-signés
  kubeadm) — compromis classique, acceptable sur réseau privé
  ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)).

## À revoir

- **Déclencheur du palier 2** : dès qu'un incident Ceph passe inaperçu, ou avant
  toute ouverture du cluster au-delà du mono-admin.
- Évaluer une alternative légère à kube-prometheus-stack (VictoriaMetrics,
  Grafana Alloy) vu l'empreinte sur un cluster hyperconvergé.
