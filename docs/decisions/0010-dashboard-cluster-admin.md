# 0010 — Kubernetes Dashboard avec rôle `cluster-admin`

## Contexte

Le [Kubernetes Dashboard](https://github.com/kubernetes/dashboard) est utilisé
comme interface graphique d'inspection et de dépannage du cluster (lecture des
pods, logs, events, déploiements à la volée pour expérimenter). La question est
de savoir **quel niveau de privilège** lui donner.

Le cluster est :

- mono-tenant (laboratoire de recherche universitaire) ;
- mono-administrateur (l'opérateur du cluster) ;
- accédé exclusivement via Tailscale par cet opérateur unique ;
- non multi-tenants (pas de cloisonnement par équipe / projet / labo).

## Décision

Le compte de service `admin-user` du dashboard est lié à `cluster-admin` via un
`ClusterRoleBinding`. Pas de moindre privilège imposé : l'opérateur qui se
connecte au dashboard est aussi celui qui possède `~/.kube/config` avec les
mêmes droits.

**Authentification** : pas de Secret de type
`kubernetes.io/service-account-token` persistant (anti-pattern depuis K8s 1.24 —
token long-lived, jamais rotaté, stocké en clair dans `etcd`). Les tokens sont
générés à la demande via l'API `TokenRequest` :

```bash
kubectl -n kubernetes-dashboard create token admin-user --duration=8h
```

Le script
[`platform/k8s-dashboard/credentials.sh`](../../platform/k8s-dashboard/credentials.sh)
encapsule cet appel.

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- Pas de prise de tête de RBAC fin pour un usage qui n'en a pas besoin
  (mono-admin).
- Aucun secret long-lived sur le cluster — un token fuité expire en ≤ 8 h.
- L'opérateur peut tout faire depuis le dashboard, comme en CLI.

**Coûts assumés.**

- **Compromission du token = compromission complète du cluster** pendant la
  durée de validité (≤ 8 h). Mitigation : tokens courts, accès dashboard
  uniquement via Tailscale, port-forward local (pas d'Ingress public).
- Si le périmètre évolue vers multi-utilisateurs (plusieurs chercheurs,
  équipes), cette ADR devient obsolète : il faudra introduire des rôles scopés
  (un `Role` par namespace par utilisateur) et plusieurs comptes dashboard. À ce
  moment, écrire `0010-bis` qui supersede celle-ci.

**Garde-fous opérationnels.**

- [`bootstrap/state.sh`](../../bootstrap/state.sh) (couche 7 plateforme) vérifie
  que **le `Secret admin-user` n'existe PAS** dans le namespace
  `kubernetes-dashboard` — preuve que la migration vers les tokens éphémères est
  effective.
- Ne pas exposer le dashboard via `Ingress` public : toujours
  `kubectl port-forward` + accès local.
