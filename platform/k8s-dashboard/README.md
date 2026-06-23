# Kubernetes Dashboard

Déploiement du
[dashboard officiel Kubernetes](https://github.com/kubernetes/dashboard) via
Helm, avec un compte de service `admin-user` lié au rôle `cluster-admin`.

> **Décision assumée** : le dashboard utilise le rôle `cluster-admin` (tous
> droits sur tous les namespaces). C'est cohérent avec un cluster mono-admin de
> recherche, **pas** un modèle multi-tenants. Voir
> [docs/decisions/0010-dashboard-cluster-admin.md](/cluster/docs/decisions/0010-dashboard-cluster-admin/).

## Installation

```bash
./manage.sh                                          # helm install --version figée + --wait + Service NodePort (ADR 0092)
kubectl apply -f service-account.yaml                # SA admin-user
kubectl apply -f cluster-role-binding.yaml           # SA → cluster-admin
```

> `manage.sh` applique aussi `nodeport.yaml` : un Service `NodePort` **séparé**
> (n'édite pas le chart Helm vendored, cf. CLAUDE.md) qui expose l'UI en L4 sur
> `http://<IP-nœud>:<nodePort>` (ADR 0092). Le `nodePort` n'est **pas figé** —
> Kubernetes l'attribue ; le lire avec
> `kubectl -n kubernetes-dashboard get svc kubernetes-dashboard-nodeport -o jsonpath='{.spec.ports[0].nodePort}'`.
>
> ⚠️ **`bearer-token.yaml` (Secret `kubernetes.io/service-account-token`) a été
> supprimé** : c'est l'anti-pattern explicite depuis K8s 1.24 (token long-lived
> persistant dans `etcd`, jamais rotaté). Les tokens sont maintenant générés à
> la demande via l'API `TokenRequest` (cf. `credentials.sh`).

## Ouvrir le dashboard

```bash
# 1. Récupérer un token éphémère (8h par défaut) :
./credentials.sh
# (ou ./credentials.sh 30m pour une durée plus courte)

# 2. Lancer le port-forward du service Kong (dashboard récent = architecture
#    multi-container : Kong fait la terminaison TLS + reverse-proxy) :
kubectl -n kubernetes-dashboard port-forward svc/kubernetes-dashboard-kong-proxy 8443:443

# 3. Ouvrir https://localhost:8443 (accepter le certificat auto-signé) et
#    coller le token dans l'écran de login.
```

## Vérification

```bash
kubectl -n kubernetes-dashboard get pods                  # tout Ready
kubectl -n kubernetes-dashboard get sa admin-user         # service account présent
kubectl get clusterrolebinding admin-user                 # binding cluster-admin
kubectl -n kubernetes-dashboard get secret | grep token   # AUCUN secret 'admin-user' attendu
```

L'absence du `Secret admin-user` est la preuve observable que la migration vers
les tokens éphémères est effective.

## Désinstallation

```bash
kubectl delete -f cluster-role-binding.yaml
kubectl delete -f service-account.yaml
helm uninstall kubernetes-dashboard -n kubernetes-dashboard
kubectl delete namespace kubernetes-dashboard
```
