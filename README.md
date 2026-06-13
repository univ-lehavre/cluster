---
layout: home
hero:
  name: Cluster
  tagline: >-
    Un cluster Kubernetes de recherche hyperconvergé — installation, stockage
    distribué, chaîne DataOps et services transverses, racontés de bout en bout.
  actions:
    - theme: brand
      text: Lire le manifeste
      link: /docs/manifeste
    - theme: alt
      text: Le guide
      link: /docs/demarrage
features:
  - icon: 📖
    title: Le manifeste
    details: >-
      Le récit du projet pour néophyte — contexte, objectif, méthode, voyage,
      résultats. Les mots-clés renvoient au glossaire et aux décisions.
    link: /docs/manifeste
  - icon: 🚀
    title: Démarrer
    details: Public visé, prérequis, parcours d'installation pas à pas.
    link: /docs/demarrage
  - icon: 🧱
    title: Les composants
    details: La pile technologique brique par brique — rôle et raison d'être.
    link: /docs/composants
  - icon: 🧭
    title: Décisions (ADR)
    details:
      Pourquoi chaque choix de conception, au format Nygard, daté et immuable.
    link: /docs/decisions/
  - icon: 🔬
    title: Audit & qualité
    details: État des lieux vérifié, plan d'action, garde-fous en place.
    link: /docs/audit/
  - icon: 🧪
    title: Banc de test
    details: Topologies reproductibles sur Lima, preuves opérationnelles.
    link: /test/
---

[![DOI](https://zenodo.org/badge/1243564575.svg)](https://doi.org/10.5281/zenodo.20287209)

Manifests, playbooks et runbooks pour déployer et opérer un cluster Kubernetes
de recherche : installation, stockage distribué, applications de calcul et
services transverses. Pour le **récit complet** (néophyte, de bout en bout),
lire le [**manifeste**](docs/manifeste.md).

📖 **Documentation en ligne** :
[univ-lehavre.github.io/cluster](https://univ-lehavre.github.io/cluster/) —
publiée automatiquement depuis `main` par
[.github/workflows/docs.yml](.github/workflows/docs.yml).

> 🔰 **Nouveau sur le sujet ?** Les termes techniques (Kubernetes, etcd, OSD,
> PVC, erasure coding, quorum…) sont définis en langage simple dans le
> [**glossaire**](docs/glossaire.md) — à garder ouvert à côté en lisant les
> runbooks.

## Par où commencer

| Je veux…                                | Aller voir                                                                                   |
| --------------------------------------- | -------------------------------------------------------------------------------------------- |
| **installer le cluster** (pas à pas)    | [`bootstrap/RUNBOOK.md`](bootstrap/RUNBOOK.md) — la séquence de référence                    |
| **opérer Ceph** (storage)               | [`storage/ceph/RUNBOOK.md`](storage/ceph/RUNBOOK.md)                                         |
| **voir les raccourcis de commandes**    | [`Justfile`](Justfile) — `just` pour la liste (nomme l'existant)                             |
| **vérifier l'état du cluster**          | `just state` (ou [`bootstrap/state.sh`](bootstrap/state.sh))                                 |
| **tester avant la prod**                | [`test/`](test/) — banc Lima ; `just bench all`                                              |
| **comprendre les choix d'architecture** | [`docs/decisions/`](docs/decisions/) (ADR)                                                   |
| **suivre l'avancement**                 | [`docs/plans/`](docs/plans/) (mise en œuvre) · [`docs/audit/`](docs/audit/) (passages datés) |

> Le [`Justfile`](Justfile) n'est **pas** un orchestrateur : il donne des
> raccourcis découvrables (`just lint`, `just state`, `just bench ceph`).
> L'ordre d'installation canonique reste décrit dans le RUNBOOK.

## Structure

| Dossier                          | Rôle                                                                 |
| -------------------------------- | -------------------------------------------------------------------- |
| [`bootstrap/`](bootstrap/)       | Installation initiale de Kubernetes (Ansible)                        |
| [`storage/ceph/`](storage/ceph/) | Stockage distribué (Rook-Ceph)                                       |
| [`platform/`](platform/)         | Services transverses (dashboard, registry, metrics, NetworkPolicies) |
| [`apps/`](apps/)                 | Charges applicatives (RStudio)                                       |
| [`test/`](test/)                 | Banc Lima + scénarios reproductibles                                 |
| [`docs/`](docs/)                 | Glossaire, démarrage, ADR, audit (site VitePress)                    |

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
- **Avant la prod** : banc d'essai Lima ([`test/lima/`](test/lima/)) qui exerce
  Phase 1-5 + DataOps sur 3 VMs Debian 13 avec disques Ceph.

Inventaire complet et détaillé : [SAFEGUARDS.md](SAFEGUARDS.md). Comment
contribuer / outillage local : [CONTRIBUTING.md](CONTRIBUTING.md).

## Le dépôt en chiffres

La gouvernance est **mesurée**, pas seulement déclarée. Chaque décision est
tracée (ADR), chaque écart de run est indexé (drift), chaque convention est
auto-vérifiée ([ADR 0060](docs/decisions/0060-audit-conventions-gouvernance.md))
:

<!-- STATS:DEBUT — bloc régénéré par `pnpm check:gouvernance --stats` (ADR 0060) -->

- **60 ADR** (56 Accepted, 4 Proposed) — chaque choix de conception, daté et
  immuable
- **6 plans** vivants — la mise en œuvre des décisions, avec leur état
  d'avancement
- **57 drifts** indexés — chaque écart révélé par un run e2e, avec cause et
  correctif
- **29 scénarios** E2E reproductibles — les preuves opérationnelles sur banc
  Lima
- **0 % de duplication** shell (seuil `jscpd` ≤ 5 %) — primitives factorisées en
  libs

<!-- STATS:FIN -->

> Régénérer ce bloc : `pnpm check:gouvernance --stats`. Le respect des
> conventions est vérifié chaque semaine (workflow `conventions-freshness`, non
> bloquant).

## Trademarks

Tous les noms de produits et marques mentionnés dans ce dépôt sont la propriété
de leurs détenteurs respectifs.
