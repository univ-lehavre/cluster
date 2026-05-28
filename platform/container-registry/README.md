# Container registry

Déploiement d'un container registry interne au cluster
([distribution v3](https://github.com/distribution/distribution), image
officielle `registry:3.1.1`), avec un volume persistant 1 Ti sur la StorageClass
par défaut (`rook-ceph-block-replicated`, réplicat ×3).

## Décisions assumées

- **HTTP sans TLS et sans authentification** : la sécurité de l'accès est
  déléguée au contrôle d'accès au Service (réseau cluster, port-forward, ou
  tunnel Tailscale si l'operator est déployé). Voir
  [`docs/decisions/0011-registry-http-sans-auth.md`](../../docs/decisions/0011-registry-http-sans-auth.md)
  (cohérent avec
  [`0003-pas-de-chiffrement-ceph-tailscale.md`](../../docs/decisions/0003-pas-de-chiffrement-ceph-tailscale.md)).
- **`replicas: 1` (SPOF applicatif)** : RBD = `ReadWriteOnce`, donc pas de
  scale-out simple ; suffisant pour un usage recherche. HA réelle = passer sur
  CephFS (`ReadWriteMany`).
- **Suppression de blobs activée** (`REGISTRY_STORAGE_DELETE_ENABLED=true`) pour
  permettre la garbage collection mensuelle.

## Pré-requis

- Cluster bootstrap (CNI + Rook-Ceph + StorageClass par défaut) en place.
- **Tailscale operator (optionnel)** : si déployé (cf.
  [`storage/ceph/RUNBOOK.md`](../../storage/ceph/RUNBOOK.md)), les annotations
  `tailscale.com/expose` et `tailscale.com/hostname` du Service exposent le
  registry comme `registry:80` sur le tailnet. **Sans Tailscale**, ces
  annotations sont des no-ops sans erreur ; le registry reste accessible via
  `kubectl port-forward` ou depuis l'intérieur du cluster.

## Installation

```bash
kubectl apply -f namespace.yaml
kubectl apply -f persistent-volume-claim.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f garbage-collect-cronjob.yaml   # suspended par défaut
```

Vérifier que tout est Ready :

```bash
kubectl -n registry get pods,svc,pvc,cronjob
```

## Utilisation

### Depuis un pair Tailscale (si l'operator est déployé)

Le registry est joignable à `registry:80` depuis tout pair Tailscale ayant le
bon tag. Côté daemon Docker (poste de dev) :

```json
{
  "insecure-registries": ["registry:80"]
}
```

```bash
docker pull alpine:3.20
docker tag alpine:3.20 registry:80/alpine:3.20
docker push registry:80/alpine:3.20
docker pull registry:80/alpine:3.20
```

### Sans Tailscale (fallback)

Depuis un poste autorisé à parler à l'API K8s :

```bash
kubectl -n registry port-forward svc/registry 8080:80
# puis sur le poste local :
#   "insecure-registries": ["localhost:8080"]
docker tag alpine:3.20 localhost:8080/alpine:3.20
docker push localhost:8080/alpine:3.20
```

Depuis un nœud du cluster, le registry est directement résolvable comme
`registry.registry.svc.cluster.local:80`.

## Garbage collection

`registry garbage-collect` supprime les blobs orphelins (référencés par aucun
manifest). Sans GC, ces blobs s'accumulent à chaque retag/écrasement.

Le CronJob [`garbage-collect-cronjob.yaml`](garbage-collect-cronjob.yaml) est
livré **suspendu** ; à activer une fois la validation banc faite :

```bash
kubectl -n registry patch cronjob registry-gc \
  --type=merge -p '{"spec":{"suspend":false}}'
```

Schedule par défaut : **17 min après 3 h UTC, 1er du mois**.

> ⚠️ La doc officielle recommande de **stopper le registry** pendant la GC (les
> pushs simultanés peuvent voir leurs blobs supprimés). Procédure manuelle :
>
> ```bash
> kubectl -n registry scale deploy/registry --replicas=0
> kubectl -n registry create job --from=cronjob/registry-gc registry-gc-manual
> kubectl -n registry wait --for=condition=complete job/registry-gc-manual --timeout=10m
> kubectl -n registry scale deploy/registry --replicas=1
> kubectl -n registry delete job registry-gc-manual
> ```
>
> Le CronJob automatique tourne en arrière-plan **sans scale-down** : on accepte
> le risque de race (rare, pertes minimes) pour la simplicité. Pour un usage
> critique, désactiver le CronJob et utiliser la procédure manuelle.

## Désinstallation

```bash
kubectl delete -f garbage-collect-cronjob.yaml
kubectl delete -f service.yaml
kubectl delete -f deployment.yaml
kubectl delete -f persistent-volume-claim.yaml   # ⚠️ supprime les images
kubectl delete -f namespace.yaml
```
