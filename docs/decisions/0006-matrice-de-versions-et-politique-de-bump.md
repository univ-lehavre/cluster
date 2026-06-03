# 0006 — Matrice de versions et politique de bump

## Contexte

Le cluster est un assemblage de composants liés par des contraintes de
compatibilité croisées : Cilium ↔ K8s, Rook ↔ K8s, Ceph ↔ Rook, containerd ↔
K8s, chart Helm dashboard ↔ K8s. Bump l'un sans vérifier les autres → drift
silencieux jusqu'à un échec de provisionnement.

Ces compatibilités croisées ont été vérifiées en mai 2026 (plafond commun imposé
par Cilium 1.19 et Rook 1.19, tous deux testés jusqu'à K8s 1.34).

## Décision

### Matrice cible (mai 2026)

| Composant       | Version cible              | Fichier piloté                                                                                                     |
| --------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Kubernetes      | **1.34**                   | [`bootstrap/roles/k8s-install`](../../bootstrap/roles/k8s-install/) (clé + dépôt `pkgs.k8s.io/v1.34`)              |
| Cilium          | **1.19.x** (dernier patch) | [`bootstrap/cni.sh`](../../bootstrap/cni.sh) (CLI épinglée)                                                        |
| Rook            | **1.19.x**                 | [`storage/ceph/operator.yaml`](../../storage/ceph/operator.yaml) + `crds.yaml`/`common.yaml`                       |
| Ceph            | **20.2.1 Tentacle**        | [`storage/ceph/cluster.yaml`](../../storage/ceph/cluster.yaml) (image `quay.io/ceph/ceph:v20.2.1`)                 |
| containerd.io   | **2.2.4**                  | dépôt Docker (cf. [ADR 0005](0005-cri-containerd-via-depot-docker.md))                                             |
| Dashboard chart | **7.10.0**                 | [`platform/k8s-dashboard/manage.sh`](../../platform/k8s-dashboard/manage.sh) (`CHART_VERSION`)                     |
| Registry image  | **3.1.1**                  | [`platform/container-registry/deployment.yaml`](../../platform/container-registry/deployment.yaml)                 |
| Gateway API CRD | **1.4.1**                  | [`platform/cilium-expo/README.md`](../../platform/cilium-expo/) (pré-install, cf. ADR 0020)                        |
| cert-manager    | **1.20.2**                 | [`platform/cert-manager/cert-manager.yaml`](../../platform/cert-manager/cert-manager.yaml) (images par digest)     |
| Argo CD         | **3.4.3**                  | [`platform/argocd/argocd.yaml`](../../platform/argocd/argocd.yaml) (+ dex 2.45.0, redis 8.2.3 ; images par digest) |

Plafond commun K8s = **1.34** (limite de Cilium 1.19 et Rook 1.19 testés). Ceph
Squid v19 sort d'EOL en septembre 2026 → Tentacle pour une install neuve.

### Politique de bump

1. **Pas de bump silencieux**. Toute montée de version se fait dans une branche
   dédiée + PR.
2. **Vérifier la compat croisée avant** :
   - Cilium release notes → quel K8s testé ?
   - Rook release notes → quel K8s + quel Ceph supportés ?
   - Ceph release notes → quelle version Rook minimale ?
3. **Pinner partout** : tags d'image avec version explicite (jamais `:latest` ni
   `:N` flottant ; idéalement avec digest pour les composants critiques).
4. **Valider sur le banc multi-nœuds**
   ([`test/multi-node/`](../../test/multi-node/)) avant la prod : déployer la
   nouvelle version, vérifier `state.sh` toutes couches vertes, jouer un cycle
   bootstrap → rollback → re-bootstrap.
5. **Mettre à jour cette ADR** (avec la nouvelle matrice + date).

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- Reproductibilité du provisionnement : la matrice est lisible d'un coup d'œil.
- Pas de surprise d'incompatibilité au déploiement.

**Coûts assumés.**

- **Travail de veille** : il faut vérifier les release notes croisées avant
  chaque bump. Compensation : les bumps sont rares (annuels pour K8s,
  semi-annuels pour Cilium/Rook).
- **Pas d'auto-update** : un nouveau patch (`1.34.9` → `1.34.10`) ne s'applique
  que via re-exécution du rôle après bump explicite.

**Sources à surveiller.**

- [Kubernetes releases](https://kubernetes.io/releases/)
- [Cilium releases](https://github.com/cilium/cilium/releases)
- [Rook releases](https://github.com/rook/rook/releases)
- [Ceph releases](https://docs.ceph.com/en/latest/releases/)
