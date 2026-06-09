# Gitea — forge git intra-banc (air-gapped)

Forge git légère **hébergée dans le cluster**, source des manifestes GitOps
qu'Argo CD réconcilie sur le **banc atlas**
([ADR 0044](../../docs/decisions/0044-topologie-deploiement-banc-atlas.md)).

## Pourquoi une forge interne

Le cluster cible est **isolé, sans Internet**
([ADR 0003](../../docs/decisions/0003-pas-de-chiffrement-ceph-tailscale.md)) —
les images sont déjà mirrorées dans le registry interne pour cette raison
([ADR 0022](../../docs/decisions/0022-argocd-gitops-applicatif.md)). Argo CD ne
peut donc pas tirer ses manifestes d'un GitHub public : il les pull depuis
**Gitea, intra-cluster**. Le banc prouve ainsi le flux GitOps tel qu'il tournera
en prod, sans dépendre d'un egress externe.

## Frontière infra / applicatif (ADR 0022)

Gitea est de l'**infra** : il doit converger **avant** qu'Argo CD réconcilie
(sinon bootstrap circulaire). Il est donc posé par **Ansible**
([`bootstrap/roles/platform-gitea/`](../../bootstrap/roles/platform-gitea/)),
pas par une `Application` Argo CD.

L'**initialisation du dépôt** (créer l'organisation + le dépôt, seed/push du
contenu atlas, enregistrer le webhook Gitea → Argo CD) est une étape de
**données**, **post-bootstrap**, portée par le harnais de banc
([`test/lima/`](../../test/lima/)) — hors de cette brique.

## Manifestes

| Fichier                                                        | Rôle                                                            |
| -------------------------------------------------------------- | --------------------------------------------------------------- |
| [`namespace.yaml`](namespace.yaml)                             | Namespace `gitea` (Pod Security `baseline`).                    |
| [`persistent-volume-claim.yaml`](persistent-volume-claim.yaml) | PVC données (dépôts + SQLite). storageClass templé par le rôle. |
| [`deployment.yaml`](deployment.yaml)                           | Pod Gitea **rootless** (uid 1000), durci, image par digest.     |
| [`service.yaml`](service.yaml)                                 | Service ClusterIP `gitea-http` :80 → 3000.                      |

NetworkPolicies sous default-deny :
[`platform/network-policies/gitea/`](../network-policies/gitea/) (default-deny +
DNS + ingress `:3000` + egress webhook → `argocd-server`, **pas d'Internet**).

## Choix d'implémentation

- **Image `-rootless`** (vs l'image s6 par défaut) : tourne en uid 1000,
  entrypoint `dumb-init`, montages explicites `/var/lib/gitea` + `/etc/gitea` →
  `readOnlyRootFilesystem: true` tenable. Image épinglée par **digest d'index
  multi-arch** (amd64 + arm64 ; le banc est arm64) —
  [ADR 0006](../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md).
- **SQLite** (pas CloudNativePG) : aucune dépendance externe → vrai air-gapped,
  et Gitea (infra) ne dépend pas d'une brique applicative.
- **Inscription fermée**, install verrouillée, webhooks restreints au seul hôte
  Argo CD interne (cohérent air-gapped). Valeurs d'exemple génériques
  ([ADR 0023](../../docs/decisions/0023-plateforme-exemple-generique.md)) ;
  surcharge réelle en config locale non versionnée.
