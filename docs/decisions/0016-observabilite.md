# 0016 — Observabilité (metrics-server + kube-prometheus-stack par paliers)

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

### Palier 2 — kube-prometheus-stack + Loki + monitoring Ceph (livré)

Livré :
[`platform/kube-prometheus-stack/`](../../platform/kube-prometheus-stack/)
(Prometheus + Alertmanager + Grafana + kube-state-metrics + node-exporter),
[`platform/loki/`](../../platform/loki/) (logs, Loki SingleBinary + Promtail),
et `monitoring.enabled: true` dans
[`cluster.yaml`](../../storage/ceph/cluster.yaml). Géré par Ansible/kubectl (pas
Argo CD — anti-bootstrap-circulaire,
[ADR 0022](0022-argocd-gitops-applicatif.md)).

**Liaison Ceph ↔ Prometheus.** Les CRDs `monitoring.coreos.com` étant désormais
présentes, Rook crée automatiquement le `ServiceMonitor` du mgr et les
`PrometheusRule` Ceph (OSD down, near-full, perte de quorum mon). Prometheus les
scrape grâce à un `serviceMonitorSelector` **vide** (sélectionne tous les
ServiceMonitor) — sans quoi celui de Ceph serait ignoré. **Ordre impératif** :
déployer kube-prometheus-stack (donc les CRDs) **avant** de passer
`monitoring.enabled: true` (sinon ServiceMonitor/PrometheusRule orphelins —
c'est la raison qui avait motivé le report).

**Destination des alertes.** Alertmanager route vers un **smarthost SMTP
paramétrable** : défaut générique = **Mailpit**
([`platform/mailpit/`](../../platform/mailpit/), puits de test SMTP + UI) ; en
production, surcharge vers un service type **Mailgun** via config locale non
versionnée ([ADR 0023](0023-plateforme-exemple-generique.md)). La couche
`alert`/postfix du durcissement hôte sera branchée sur le **même** smarthost
(destination mail unifiée) dans une étape dédiée.

**Empreinte** maîtrisée : `requests`/`limits` bornés sur tous les composants
(cluster hyperconvergé, [ADR 0009](0009-pourquoi-4-noeuds.md)), images épinglées
par digest d'index multi-arch
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)). Exposition de
Grafana via le Gateway Cilium + TLS interne
([ADR 0020](0020-exposition-reseau-tout-cilium.md)/[0021](0021-cert-manager-ca-interne.md)).

## Statut

Accepted (2026-06-01). **Palier 2 livré le 2026-06-03.**

## Conséquences

**Bénéfices.**

- `kubectl top` / HPA opérationnels tout de suite, empreinte minimale.
- Le constat « majeur » de l'audit est partiellement levé et le reste est
  **tracé** (plus un trou silencieux).

- **Alerting runtime K8s/Ceph actif** (palier 2) : OSD down, near-full, perte de
  quorum mon et anomalies K8s lèvent désormais des alertes automatiques, routées
  vers le mail (Mailpit en test, Mailgun en prod). Plus de dépendance au
  `state.sh` manuel pour la détection.

**Coûts assumés.**

- Empreinte accrue (Prometheus/Alertmanager/Grafana/Loki + exporters) — bornée
  par `requests`/`limits`, mais non négligeable sur un cluster hyperconvergé.
- `--kubelet-insecure-tls` sur metrics-server **et** les ServiceMonitor kubelet
  (certs kubelet auto-signés kubeadm) — compromis classique, acceptable sur
  réseau privé ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)).
- Le chart **Promtail est déprécié** en amont (Grafana pousse Alloy) — dette de
  migration à prévoir.

## À revoir

- **Brancher la couche `alert`/postfix du durcissement hôte** sur le même
  smarthost (Mailpit/Mailgun) que l'alerting K8s — destination mail unifiée
  (étape dédiée).
- **Migrer Promtail → Grafana Alloy** (chart Promtail déprécié).
- Évaluer une alternative légère à kube-prometheus-stack (VictoriaMetrics,
  Grafana Alloy) si l'empreinte devient contraignante.
