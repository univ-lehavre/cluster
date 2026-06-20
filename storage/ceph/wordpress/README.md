# WordPress (exemple)

Exemple d'usage du stockage bloc Ceph : un MySQL et un WordPress montés sur des
volumes `rook-ceph-block-replicated` (réplication ×3,
[ADR 0001](../../../docs/decisions/0001-replication-x3-pour-workloads-bloc.md)).
Sert à valider que le provisionnement de volumes persistants fonctionne.

## Prérequis

Le mot de passe de la base n'est pas versionné. Créer le secret partagé par les
deux déploiements avant d'appliquer les manifests :

```bash
kubectl create secret generic wordpress-secret \
  --from-literal=password='<mot-de-passe>'
```

## Installation

```bash
kubectl apply -f mysql.yaml
kubectl apply -f wordpress.yaml
```

## Désinstallation

```bash
kubectl delete -f wordpress.yaml -f mysql.yaml
kubectl delete secret wordpress-secret
```
