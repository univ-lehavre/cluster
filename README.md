# Cluster

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/univ-lehavre/cluster/badge)](https://scorecard.dev/viewer/?uri=github.com/univ-lehavre/cluster)

> Un cluster Kubernetes de recherche hyperconvergé — installation, stockage
> distribué, chaîne DataOps et services transverses, racontés de bout en bout.

<!-- Badges — doctrine ADR 0080 (docs/decisions/0080-notations-et-badges-readme.md) :
n'afficher QUE ce qui mesure un état VRAI (dynamique câblé, ou statique factuel
stable) ; GROUPER par thématique pour rendre visibles les familles revendiquées.
Un référentiel noté non encore câblé reste au plan de remédiation du passage
d'audit, PAS affiché à vide. Un référentiel écarté (DORA, ISO) ou auto-déclaratif
non vérifié (Best Practices, retiré le 2026-06-19 — cf. ADR 0080 §Mise à jour)
n'a pas de badge — c'est un choix tracé. Le badge le plus structurant (OpenSSF
Scorecard, recalculé en continu) est mis en avant SOUS LE TITRE ; les autres
sont regroupés par famille, chacune présentée dans la section « Conformité &
badges » plus bas. -->

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
| **tester avant la prod**                | [`bench/`](bench/) — banc Lima ; `just bench all`                                            |
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
| [`bench/`](bench/)               | Banc Lima + scénarios reproductibles                                 |
| [`docs/`](docs/)                 | Glossaire, démarrage, ADR, audit (site VitePress)                    |

## Qualité — garde-fous en place

À chaque étape, des contrôles automatiques empêchent qu'une régression atteigne
la prod :

- **Avant le commit** : hooks Lefthook (prettier, yamllint, shellcheck) + sujet
  de commit Conventional Commits + interdiction d'email dans le message.
- **Avant le push** : tout le dépôt revalidé (`kubeconform`, `ansible-lint`,
  `shellcheck` complet, prettier complet) + interdiction de push direct sur
  `main`.
- **En CI GitHub Actions** : 13 checks requis avant merge (formats, lint,
  `kubeconform`, `ansible-lint`, `trivy`, `jscpd` ≤ 5 % duplication, build
  VitePress, `lychee`…).
- **Sur les serveurs** : [`bootstrap/state.sh`](bootstrap/state.sh) (7 couches
  de drift detection) +
  [`bootstrap/security/report.sh`](bootstrap/security/report.sh) (visibilité
  hardening) + audit-log par nœud + sauvegarde etcd + rollback scripté.
- **Avant la prod** : banc d'essai Lima ([`bench/lima/`](bench/lima/)) qui
  exerce Phase 1-5 + DataOps sur 3 VMs Debian 13 avec disques Ceph.

Inventaire complet et détaillé : [SAFEGUARDS.md](SAFEGUARDS.md). Comment
contribuer / outillage local : [CONTRIBUTING.md](CONTRIBUTING.md).

## Le dépôt en chiffres

La gouvernance est **mesurée**, pas seulement déclarée. Chaque décision est
tracée (ADR), chaque écart de run est indexé (drift), chaque convention est
auto-vérifiée
([ADR 0060](docs/decisions/0060-audit-conventions-gouvernance.md)), et la
duplication shell est tenue à **0 %** (seuil `jscpd` ≤ 5 %). La vitrine
consolidée, pour juger en 5 min : [docs/preuves.md](docs/preuves.md).

<!-- STATS:DEBUT — bloc régénéré par `pnpm check:gouvernance --stats` (ADR 0060) -->

- **88 ADR** (80 Accepted, 6 Proposed, 2 Superseded)
- **8 plans** vivants (4 Achevé, 3 Actif, 1 Brouillon)
- **57 drifts** indexés (3 caduc, 51 corrige, 1 en-cours, 2 ouvert)
- **31 scénarios** E2E reproductibles

<!-- STATS:FIN -->

> Régénérer ce bloc : `pnpm check:gouvernance --stats`. Le respect des
> conventions est vérifié chaque semaine (workflow `conventions-freshness`, non
> bloquant).

## Conformité & badges

Les badges sous le titre ne sont pas décoratifs : chacun reflète un état **vrai
et vérifiable** (recalculé en continu, ou fait stable), groupé par famille pour
dire **quelles cultures** le dépôt revendique
([ADR 0080](docs/decisions/0080-notations-et-badges-readme.md)). Le plus
structurant —
[OpenSSF Scorecard](https://scorecard.dev/viewer/?uri=github.com/univ-lehavre/cluster),
santé supply-chain notée /10 — est mis en avant seul, en tête.

### Identité & licence

Le projet est **citable et ouvert** : un DOI Zenodo fige et référence chaque
version pour la citation académique, et le code est sous licence **MIT**
(réutilisation libre, `LICENSE` + `NOTICE`).

[![DOI](https://zenodo.org/badge/1243564575.svg)](https://doi.org/10.5281/zenodo.20287209)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/univ-lehavre/cluster/blob/main/LICENSE)

### Conventions & versionnement

L'historique est **lisible et outillé**, pas seulement par discipline. Chaque
message de commit suit **Conventional Commits** (validé par commitlint sur toute
la plage d'une PR), les versions suivent **SemVer** (bump dérivé des commits par
release-please), et le **CHANGELOG** est tenu au format _Keep a Changelog_,
généré automatiquement à chaque release.

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://www.conventionalcommits.org)
[![SemVer](https://img.shields.io/badge/SemVer-2.0.0-blue.svg)](https://semver.org)
[![Keep a Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-orange.svg)](https://github.com/univ-lehavre/cluster/blob/main/CHANGELOG.md)

### Qualité & CI

Aucune régression n'atteint `main` sans passer les contrôles : chaque PR doit
satisfaire **13 checks requis** (formats, lint, `kubeconform`, `ansible-lint`,
`trivy`, `jscpd`, build de la doc, tests…) avant merge. Le badge reflète l'état
réel du workflow `ci.yml` sur `main`. Détail des garde-fous : section
[« Qualité — garde-fous en place »](#qualité--garde-fous-en-place) ci-dessus et
[SAFEGUARDS.md](SAFEGUARDS.md).

[![CI](https://github.com/univ-lehavre/cluster/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/univ-lehavre/cluster/actions/workflows/ci.yml)

## Trademarks

Tous les noms de produits et marques mentionnés dans ce dépôt sont la propriété
de leurs détenteurs respectifs.
