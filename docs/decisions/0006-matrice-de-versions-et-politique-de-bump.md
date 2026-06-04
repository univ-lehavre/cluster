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

### Observabilité & DataOps (ajout juin 2026)

Composants ajoutés avec l'observabilité (ADR 0016 palier 2) et le socle DataOps
(CloudNativePG). Toutes les images sont épinglées par **digest d'index
multi-arch** (politique ci-dessous) ; on note ici le tag de version porteur.

| Composant             | Version cible                                  | Fichier piloté                                                                                                |
| --------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| kube-prometheus-stack | chart **86.1.0** (operator v0.91.0)            | [`platform/kube-prometheus-stack/`](../../platform/kube-prometheus-stack/) (helm template figé)               |
| Loki                  | chart **7.0.0** (app 3.6.7)                    | [`platform/loki/loki.yaml`](../../platform/loki/loki.yaml)                                                    |
| Promtail              | chart **6.17.1** (app 3.5.1, déprécié → Alloy) | [`platform/loki/promtail.yaml`](../../platform/loki/promtail.yaml)                                            |
| Mailpit               | **v1.30.1**                                    | [`platform/mailpit/mailpit.yaml`](../../platform/mailpit/mailpit.yaml)                                        |
| CloudNativePG         | operator **1.29.1**                            | [`platform/cloudnative-pg/operator.yaml`](../../platform/cloudnative-pg/operator.yaml)                        |
| Barman Cloud Plugin   | **v0.12.0**                                    | [`platform/cloudnative-pg/plugin-barman-cloud.yaml`](../../platform/cloudnative-pg/plugin-barman-cloud.yaml)  |
| PostgreSQL (operand)  | **18** (`18-minimal-trixie`)                   | [`platform/cloudnative-pg/cluster.yaml`](../../platform/cloudnative-pg/cluster.yaml)                          |
| pgvector              | **0.8.2** (`0.8.2-18-trixie`)                  | [`platform/cloudnative-pg/cluster.yaml`](../../platform/cloudnative-pg/cluster.yaml) (image volume extension) |
| SeaweedFS             | **4.31**                                       | banc léger uniquement (objectstore S3 de test)                                                                |
| aws-cli               | **2.31.21**                                    | Jobs d'init de buckets S3 (`init-buckets.yaml`)                                                               |
| Dagster               | chart **1.13.7** (app 1.13.7)                  | [`platform/dagster/values.bench.yaml`](../../platform/dagster/values.bench.yaml) (helm template figé)         |

> **Dagster amd64-only.** Les images officielles Dagster sont publiées **amd64
> uniquement** (dagster-io/dagster#11841). Dagster étant du pur Python, on
> **construit l'image arm64 en interne**
> ([`platform/dagster/image/Dockerfile`](../../platform/dagster/image/Dockerfile),
> 1er build maison du dépôt) pour le banc arm64 ; la topologie bare-metal x86
> utilise l'image officielle. À reconstruire à chaque bump (cf. ADR 0026).

<!-- séparateur entre deux encadrés -->

> **CloudNativePG 1.29 + Image Volume Extensions** (la voie pgvector sans image
> custom) reposent sur la feature Kubernetes **`ImageVolume`** : alpha en K8s
> 1.31 (désactivée), beta/activée par défaut **dès 1.33** → fonctionne
> nativement en **1.34**. Cohérence de version impérative : un banc qui dérive
> sous 1.33 ne peut pas valider pgvector.

### Outillage des bancs de test

Les bancs doivent cibler la **même version Kubernetes (1.34)** que le bootstrap
— sinon dérive silencieuse (cf. encadré ImageVolume ci-dessus).

| Banc                        | Installeur K8s                                 | Version  |
| --------------------------- | ---------------------------------------------- | -------- |
| `test/multi-node` (Vagrant) | kubeadm via `bootstrap/` (`pkgs.k8s.io/v1.34`) | **1.34** |
| `test/lima` (Lima)          | kubeadm via `bootstrap/` (VMs Lima)            | **1.34** |

> **kind est abandonné** : son image de node figeait K8s en 1.31 (divergent de
> la matrice), ce qui a bloqué pgvector. Le banc léger est rebâti sur des **VMs
> Lima** (`test/lima/`) exécutant le **vrai bootstrap kubeadm v1.34** — même
> chemin que la prod. (Une voie « conteneurs Docker privilégiés / DinD » a été
> écartée : overlayfs imbriqué non fonctionnel ; la vraie VM Lima le résout.)

### Politique de bump

1. **Pas de bump silencieux**. Toute montée de version se fait dans une branche
   dédiée + PR.
2. **Vérifier la compat croisée avant** :
   - Cilium release notes → quel K8s testé ?
   - Rook release notes → quel K8s + quel Ceph supportés ?
   - Ceph release notes → quelle version Rook minimale ?
3. **Pinner partout** : tags d'image avec version explicite (jamais `:latest` ni
   `:N` flottant ; idéalement avec digest pour les composants critiques). Le
   digest DOIT pointer l'**index multi-arch** (`image.index` / `manifest.list`),
   JAMAIS un manifeste single-arch — sinon `exec format error` sur arm64 (#140).
   Vérification :
   [`scripts/audit-image-digests.sh`](../../scripts/audit-image-digests.sh)
   (audite tous les digests épinglés du dépôt).
4. **Valider sur le banc multi-nœuds**
   ([`test/multi-node/`](../../test/multi-node/)) avant tout déploiement sur une
   topologie cible : déployer la nouvelle version, vérifier `state.sh` toutes
   couches vertes, jouer un cycle bootstrap → rollback → re-bootstrap.
5. **Mettre à jour cette ADR** (avec la nouvelle matrice + date).

## Statut

Accepted (2026-05-28). **Matrice étendue le 2026-06-03** : observabilité,
DataOps et outillage des bancs (abandon de kind).

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
