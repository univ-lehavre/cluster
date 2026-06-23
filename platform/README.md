# Plateforme

Services transverses du cluster (au-delà du bootstrap K8s et du stockage Ceph).

| Composant                                                            | Rôle                                                            |
| -------------------------------------------------------------------- | --------------------------------------------------------------- |
| [`argocd/`](/cluster/platform/argocd/)                               | GitOps applicatif (Argo CD v3.4.3, cf. ADR 0022)                |
| [`cert-manager/`](/cluster/platform/cert-manager/)                   | TLS de bordure via CA interne (cf. ADR 0021)                    |
| [`cloudnative-pg/`](/cluster/platform/cloudnative-pg/)               | PostgreSQL managé (socle DataOps — cf. ADR 0024)                |
| [`container-registry/`](/cluster/platform/container-registry/)       | Registry d'images interne (distribution v3, RBD ×3)             |
| [`dagster/`](/cluster/platform/dagster/)                             | Orchestrateur DataOps (cf. ADR 0026)                            |
| [`gitea/`](/cluster/platform/gitea/)                                 | Forge git intra-banc (air-gapped, source GitOps — cf. ADR 0044) |
| [`k8s-dashboard/`](/cluster/platform/k8s-dashboard/)                 | Kubernetes Dashboard (Helm, tokens éphémères — cf. ADR 0010)    |
| [`kube-prometheus-stack/`](/cluster/platform/kube-prometheus-stack/) | Observabilité palier 2 : Prometheus + Grafana (cf. ADR 0016)    |
| [`loki/`](/cluster/platform/loki/)                                   | Agrégation des logs (cf. ADR 0016)                              |
| [`mailpit/`](/cluster/platform/mailpit/)                             | Puits SMTP + UI de test (destination mail de la plateforme)     |
| [`marquez/`](/cluster/platform/marquez/)                             | Store de lineage OpenLineage (cf. ADR 0028)                     |
| [`metrics-server/`](/cluster/platform/metrics-server/)               | Métriques CPU/mémoire (`kubectl top`, HPA — cf. ADR 0016)       |
| [`network-policies/`](/cluster/platform/network-policies/)           | NetworkPolicies default-deny par namespace (audit P6 #22)       |
| [`hardware.md`](/cluster/platform/hardware/)                         | Inventaire matériel des nœuds (serveurs lames)                  |

**Exposition des UI** : depuis
l'[ADR 0092](/cluster/docs/decisions/0092-exposition-hostport-l4/), les UI sont
servies en **L4** (`NodePort`/`hostPort` sur l'IP du nœud,
`http://<IP-nœud>:<port>`) — plus de Gateway L7 ni de dossier
`platform/cilium-expo/` (retiré). Les features Cilium LB-IPAM/Gateway restent
armées par `bootstrap/cni.sh` (chemin de prod optionnel).

Chaque composant a son propre README avec installation et décisions assumées
(`mlflow/`, `redcap/`, `seaweedfs/` inclus — cf. la pile complète dans
[`docs/composants.md`](/cluster/docs/composants/), source canonique). Vue
d'ensemble du dépôt :
[README racine](https://github.com/univ-lehavre/cluster/blob/main/README.md) ·
[Par où commencer](/cluster/docs/demarrage/).
