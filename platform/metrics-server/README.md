# metrics-server

Observabilité « a minima » (audit P5 #17 /
[ADR 0016](../../docs/decisions/0016-observabilite.md)).

[metrics-server](https://github.com/kubernetes-sigs/metrics-server) collecte
l'usage CPU/mémoire des nœuds et des pods via les kubelets et l'expose dans
l'API `metrics.k8s.io`. Il rend opérants :

- `kubectl top nodes` / `kubectl top pods`,
- les **HorizontalPodAutoscaler** (HPA).

Il est **autonome** (pas de Prometheus requis) — c'est le socle minimal
recommandé par l'audit. Le stack complet (Prometheus/Grafana/AlertManager) et
l'activation du monitoring Ceph (`monitoring.enabled`) restent à brancher
ultérieurement (cf. ADR 0016).

## Déploiement

```bash
kubectl apply -f platform/metrics-server/metrics-server.yaml
# Vérifier (après ~30 s) :
kubectl -n kube-system get deploy metrics-server
kubectl top nodes
```

## Adaptations à ce cluster

Le manifeste est le `components.yaml` officiel de **v0.8.0**, avec :

1. **`--kubelet-insecure-tls`** : les kubelets kubeadm ont des certificats
   auto-signés (pas de `serverTLSBootstrap`) → metrics-server ne peut pas les
   vérifier. Compromis classique kubeadm, acceptable sur réseau privé
   ([ADR 0003](../../docs/decisions/0003-pas-de-chiffrement-ceph-tailscale.md)).
   À lever si un jour les kubelets obtiennent des certs signés par la CA du
   cluster.
2. **Image épinglée par digest** (audit P11 #11).

> **Pas de `limits` (seulement `requests`)** : conforme au manifeste upstream —
> un composant `system-cluster-critical` ne doit pas être throttlé/OOM-killé par
> une limite. Le `request` (100m / 200Mi) suffit au scheduler.
