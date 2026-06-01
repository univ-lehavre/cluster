# Cluster

[![DOI](https://zenodo.org/badge/1243564575.svg)](https://doi.org/10.5281/zenodo.20287209)

Manifests, playbooks et runbooks pour déployer et opérer un cluster Kubernetes
de recherche : installation, stockage distribué, applications de calcul et
services transverses.

📖 **Documentation en ligne** :
[univ-lehavre.github.io/cluster](https://univ-lehavre.github.io/cluster/) —
publiée automatiquement depuis `main` par
[.github/workflows/docs.yml](.github/workflows/docs.yml).

> 🔰 **Nouveau sur le sujet ?** Les termes techniques (Kubernetes, etcd, OSD,
> PVC, erasure coding, quorum…) sont définis en langage simple dans le
> [**glossaire**](docs/glossaire.md) — à garder ouvert à côté en lisant les
> runbooks.

## Par où commencer

| Je veux…                                | Aller voir                                                                |
| --------------------------------------- | ------------------------------------------------------------------------- |
| **installer le cluster** (pas à pas)    | [`bootstrap/RUNBOOK.md`](bootstrap/RUNBOOK.md) — la séquence de référence |
| **opérer Ceph** (storage)               | [`storage/ceph/RUNBOOK.md`](storage/ceph/RUNBOOK.md)                      |
| **voir les raccourcis de commandes**    | [`Justfile`](Justfile) — `just` pour la liste (nomme l'existant)          |
| **vérifier l'état du cluster**          | `just state` (ou [`bootstrap/state.sh`](bootstrap/state.sh))              |
| **tester avant la prod**                | [`test/`](test/) — banc Vagrant ; `just bench all`                        |
| **comprendre les choix d'architecture** | [`docs/decisions/`](docs/decisions/) (ADR)                                |
| **suivre l'avancement du durcissement** | [`STATUS.md`](STATUS.md) · audit complet : [`docs/audit/`](docs/audit/)   |

> Le [`Justfile`](Justfile) n'est **pas** un orchestrateur : il donne des
> raccourcis découvrables (`just lint`, `just state`, `just bench ceph`).
> L'ordre d'installation canonique reste décrit dans le RUNBOOK.

## Structure

| Dossier                          | Rôle                                          |
| -------------------------------- | --------------------------------------------- |
| [`bootstrap/`](bootstrap/)       | Installation initiale de Kubernetes (Ansible) |
| [`storage/ceph/`](storage/ceph/) | Stockage distribué (Rook-Ceph)                |
| [`platform/`](platform/)         | Services transverses (dashboard, registry)    |
| [`apps/`](apps/)                 | Charges applicatives (RStudio)                |

## Qualité — garde-fous en place

À chaque étape, des contrôles automatiques empêchent qu'une régression atteigne
la prod :

- **Avant le commit** : hooks Lefthook (prettier, yamllint, shellcheck) + sujet
  de commit Conventional Commits + interdiction d'email dans le message.
- **Avant le push** : tout le dépôt revalidé (`kubeconform`, `ansible-lint`,
  `shellcheck` complet, prettier complet) + interdiction de push direct sur
  `main`.
- **En CI GitHub Actions** : 8 jobs en parallèle (formats, lint, `jscpd` ≤ 5 %
  duplication, build VitePress).
- **Sur les serveurs** : [`bootstrap/state.sh`](bootstrap/state.sh) (7 couches
  de drift detection) +
  [`bootstrap/security/report.sh`](bootstrap/security/report.sh) (visibilité
  hardening) + audit-log par nœud + sauvegarde etcd + rollback scripté.
- **Avant la prod** : banc d'essai Vagrant
  ([`test/multi-node/`](test/multi-node/)) qui exerce Phase 1-5 sur 3 VMs Debian
  13 avec disques Ceph.

Inventaire complet et détaillé : [SAFEGUARDS.md](SAFEGUARDS.md). Comment
contribuer / outillage local : [CONTRIBUTING.md](CONTRIBUTING.md).

## Trademarks

Tous les noms de produits et marques mentionnés dans ce dépôt sont la propriété
de leurs détenteurs respectifs.
