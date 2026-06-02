# Plateforme

Services transverses du cluster (au-delà du bootstrap K8s et du stockage Ceph).

| Composant                                    | Rôle                                                           |
| -------------------------------------------- | -------------------------------------------------------------- |
| [`cilium-expo/`](cilium-expo/)               | Exposition tout-Cilium : LB-IPAM + L2 + Gateway API (ADR 0020) |
| [`container-registry/`](container-registry/) | Registry d'images interne (distribution v3, RBD ×3)            |
| [`k8s-dashboard/`](k8s-dashboard/)           | Kubernetes Dashboard (Helm, tokens éphémères — cf. ADR 0010)   |
| [`metrics-server/`](metrics-server/)         | Métriques CPU/mémoire (`kubectl top`, HPA — cf. ADR 0016)      |
| [`network-policies/`](network-policies/)     | NetworkPolicies default-deny par namespace (audit P6 #22)      |
| [`hardware.md`](hardware.md)                 | Inventaire matériel des 4 nœuds HPE                            |

Chaque composant a son propre README avec installation et décisions assumées.
Vue d'ensemble du dépôt : [README racine](../README.md) ·
[Par où commencer](../docs/demarrage.md).
