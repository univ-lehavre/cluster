# Architecture Decision Records (ADR)

Trace **pourquoi** chaque choix de conception du cluster — pas le _comment_
(couvert par les README/RUNBOOK), mais le contexte, l'alternative écartée et les
conséquences assumées.

> 🗺️ **Lecture par thème.** Cet index est **chronologique** (un ADR = une
> décision datée, immuable). Pour une lecture **par domaine** (stockage, réseau,
> sécurité, plan de contrôle, plateforme/GitOps, conventions), voir les
> [vues d'architecture](../architecture/) qui agrègent et relient les ADR.

Format léger inspiré de Michael Nygard :

- **Contexte** — ce qui a forcé une décision.
- **Décision** — ce qui a été acté.
- **Statut** — Accepted / Superseded by `NNNN` / Deprecated.
- **Conséquences** — gain, prix à payer, garde-fous à connaître.

## Index

| #    | Titre                                                                                                      | Statut   |
| ---- | ---------------------------------------------------------------------------------------------------------- | -------- |
| 0001 | [Réplication ×3 pour les workloads bloc (vs EC)](0001-replication-x3-pour-workloads-bloc.md)               | Accepted |
| 0002 | [Control plane unique avec `--control-plane-endpoint`](0002-control-plane-unique-avec-endpoint.md)         | Accepted |
| 0003 | [Pas de chiffrement Ceph — sécurité du réseau déléguée](0003-pas-de-chiffrement-ceph-tailscale.md)         | Accepted |
| 0004 | [Erasure coding 2+1 réservé au datalake](0004-erasure-coding-2plus1-datalake.md)                           | Accepted |
| 0005 | [CRI = `containerd.io` depuis le dépôt Docker](0005-cri-containerd-via-depot-docker.md)                    | Accepted |
| 0006 | [Matrice de versions et politique de bump](0006-matrice-de-versions-et-politique-de-bump.md)               | Accepted |
| 0007 | [Hyperconvergence : control plane portant OSDs](0007-hyperconvergence-control-plane-osd.md)                | Accepted |
| 0008 | [`metadataDevice` NVMe unique — SPOF par nœud assumé](0008-metadatadevice-nvme-spof-par-noeud.md)          | Accepted |
| 0009 | [Pourquoi 4 nœuds ?](0009-pourquoi-4-noeuds.md)                                                            | Accepted |
| 0010 | [Dashboard Kubernetes en `cluster-admin`](0010-dashboard-cluster-admin.md)                                 | Accepted |
| 0011 | [Registry interne HTTP sans authentification](0011-registry-http-sans-auth.md)                             | Accepted |
| 0012 | [RStudio sans authentification (`DISABLE_AUTH=true`)](0012-rstudio-disable-auth.md)                        | Accepted |
| 0013 | [Sauvegarde des données applicatives (VolumeSnapshots CSI)](0013-sauvegarde-donnees-applicatives.md)       | Accepted |
| 0014 | [Durcissement du plan de contrôle (`kubeadm init` nu)](0014-durcissement-kubeadm-init.md)                  | Accepted |
| 0015 | [Stratégie d'upgrade Kubernetes (in-place vs rebuild)](0015-strategie-upgrade-kubernetes.md)               | Accepted |
| 0016 | [Observabilité (metrics-server maintenant, Prometheus plus tard)](0016-observabilite.md)                   | Accepted |
| 0017 | [Langage des scripts (bash / jq / python3 / bats)](0017-langage-des-scripts.md)                            | Accepted |
| 0018 | [Rook-Ceph plutôt que Longhorn](0018-rook-ceph-vs-longhorn.md)                                             | Accepted |
| 0019 | [Durcissement réseau Cilium (WireGuard + Hubble)](0019-durcissement-reseau-cilium.md)                      | Accepted |
| 0020 | [Exposition réseau tout-Cilium (LB-IPAM + L2 + Gateway API)](0020-exposition-reseau-tout-cilium.md)        | Accepted |
| 0021 | [cert-manager + CA interne (TLS de bordure)](0021-cert-manager-ca-interne.md)                              | Accepted |
| 0022 | [Argo CD (GitOps applicatif)](0022-argocd-gitops-applicatif.md)                                            | Accepted |
| 0023 | [Dépôt multi-topologies (plusieurs infra déclarées, une activée)](0023-plateforme-exemple-generique.md)    | Accepted |
| 0024 | [PostgreSQL managé via CloudNativePG (+ pgvector)](0024-postgres-manage-cloudnative-pg.md)                 | Accepted |
| 0025 | [Sécurité active : chaos + attaques contrôlées (D/A/R)](0025-securite-active-chaos-attaques-controlees.md) | Accepted |
