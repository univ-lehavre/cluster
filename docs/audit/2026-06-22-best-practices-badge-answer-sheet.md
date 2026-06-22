# 2026-06-22 — OpenSSF Best Practices Badge : answer-sheet « passing »

| Champ       | Contenu                                                                                                                                                                    |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**    | 2026-06-22                                                                                                                                                                 |
| **Type**    | feuille de réponses opérationnelle — pour remplir le questionnaire **passing** du badge sur [best.openssf.org](https://www.bestpractices.dev/) (BadgeApp)                  |
| **Fonde**   | les quick-wins maturité de juin 2026 (Scorecard 4.9 → 6.4) + la migration doc Astro Starlight ([ADR 0089](../decisions/0089-migration-doc-vitepress-astro-starlight.md))   |
| **Verdict** | **passing atteignable** : ~50 Met, ~12 N/A légitimes, **0 Unmet**. `discussion` Met (Discussions activées) ; `english` Met (encarts anglais README/CONTRIBUTING/SECURITY). |

## Comment s'en servir

1. Créer le projet sur <https://www.bestpractices.dev/> (connexion GitHub, dépôt
   `univ-lehavre/cluster`). Le BadgeApp **auto-remplit** beaucoup de critères
   via l'API GitHub.
2. Pour chaque critère ci-dessous : recopier la réponse (Met / N/A) et coller la
   justification + l'URL de preuve. **Plusieurs critères exigent une URL**
   (champ obligatoire dans le BadgeApp) : toute mention `fichier.md` ci-dessous
   se traduit en URL par la base
   `https://github.com/univ-lehavre/cluster/blob/main/` + le chemin.
3. Les critères marqués **N/A** sont légitimement non applicables (dépôt d'IaC,
   pas de cryptographie maison) — le badge les compte comme satisfaits dès lors
   que la justification est fournie.

### URL prêtes pour les critères qui en exigent une

| Critère                        | URL à coller (préfixe `https://github.com/univ-lehavre/cluster/`) |
| ------------------------------ | ----------------------------------------------------------------- |
| `contribution`                 | `blob/main/CONTRIBUTING.md`                                       |
| `contribution_requirements`    | `blob/main/CONTRIBUTING.md#workflow-de-pr`                        |
| `documentation_basics`         | `blob/main/bootstrap/RUNBOOK.md`                                  |
| `documentation_interface`      | `blob/main/contract/README.md`                                    |
| `vulnerability_report_process` | `blob/main/SECURITY.md`                                           |
| `report_process`               | `blob/main/.github/ISSUE_TEMPLATE/bug_report.md`                  |
| `static_analysis`              | `blob/main/.github/workflows/codeql.yml`                          |
| `test_policy`                  | `blob/main/docs/architecture/plan-de-tests.md`                    |
| `sites_https`                  | `https://univ-lehavre.github.io/cluster/`                         |
| `discussion`                   | `https://github.com/univ-lehavre/cluster/discussions`             |

> **Discipline d'honnêteté (ADR 0061/0080).** Aucun critère n'est coché « pour
> le badge » : chaque ligne cite une preuve réelle. Les N/A crypto reflètent que
> le dépôt **consomme** du TLS standard (cert-manager) sans implémenter
> d'algorithme.

## Basics

| Critère                     | Réponse | Justification / preuve                                                                                                                                                                                                             |
| --------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `description_good`          | Met     | README (`# Cluster`) + description repo « Installateur et réconciliateur sur kubernetes » + site doc.                                                                                                                              |
| `interact`                  | Met     | README « Par où commencer », `CONTRIBUTING.md`, issue templates, **GitHub Discussions activées**.                                                                                                                                  |
| `contribution`              | Met     | `CONTRIBUTING.md` : process (branches, Conventional Commits, hooks, merge commit ADR 0037).                                                                                                                                        |
| `contribution_requirements` | Met     | Exigences d'acceptation dans `CONTRIBUTING.md` § « Workflow de PR » (sujet minuscule, ≤100 col, hooks pre-push, merge commit). **URL** : `CONTRIBUTING.md#workflow-de-pr`                                                          |
| `floss_license`             | Met     | `LICENSE` = MIT (FLOSS).                                                                                                                                                                                                           |
| `floss_license_osi`         | Met     | MIT = OSI-approved.                                                                                                                                                                                                                |
| `license_location`          | Met     | `LICENSE` + `NOTICE` à la racine.                                                                                                                                                                                                  |
| `documentation_basics`      | Met     | Install (`bootstrap/RUNBOOK.md`), usage (`docs/se-brancher.md`), sécurité (`SECURITY.md`, `SAFEGUARDS.md`).                                                                                                                        |
| `documentation_interface`   | Met     | Contrat versionné `contract/` (endpoints, StorageClasses) + `docs/guide-dev-data.md`.                                                                                                                                              |
| `sites_https`               | Met     | Site doc HTTPS (GitHub Pages, **Astro Starlight** depuis ADR 0089) ; repo GitHub HTTPS.                                                                                                                                            |
| `discussion`                | **Met** | **GitHub Discussions activées** (`hasDiscussionsEnabled: true`) + issue tracker public searchable.                                                                                                                                 |
| `english`                   | Met     | Encart anglais (« English summary ») dans `README.md` + notes anglaises dans `CONTRIBUTING.md` et `SECURITY.md` : issues, PR et rapports de sécurité **en anglais acceptés**. La doc de fond reste française (langue de l'équipe). |
| `maintained`                | Met     | Activité quotidienne (releases régulières, issues traitées sous quelques jours).                                                                                                                                                   |

## Change Control

| Critère               | Réponse | Justification / preuve                                                                    |
| --------------------- | ------- | ----------------------------------------------------------------------------------------- |
| `repo_public`         | Met     | Dépôt public versionné git.                                                               |
| `repo_track`          | Met     | Git suit changements, auteurs, horodatages.                                               |
| `repo_interim`        | Met     | Branches PR + **merge commit** (ADR 0037) préservent les versions intermédiaires.         |
| `repo_distributed`    | Met     | Git (distribué).                                                                          |
| `version_unique`      | Met     | Tags SemVer uniques (`vX.Y.Z`).                                                           |
| `version_semver`      | Met     | SemVer via release-please.                                                                |
| `version_tags`        | Met     | Releases identifiées par tags.                                                            |
| `release_notes`       | Met     | `CHANGELOG.md` (Keep a Changelog) + GitHub Releases, générés par release-please.          |
| `release_notes_vulns` | Met     | Pas de CVE publique corrigée à ce jour ; les `fix:` (sécurité incluse) sont au changelog. |

## Reporting

| Critère                         | Réponse | Justification / preuve                                                          |
| ------------------------------- | ------- | ------------------------------------------------------------------------------- |
| `report_process`                | Met     | `.github/ISSUE_TEMPLATE/` (bug, feature, config).                               |
| `report_tracker`                | Met     | GitHub Issues utilisé activement.                                               |
| `report_responses`              | Met     | Mainteneur réactif (issues ouvertes/fermées sous quelques jours).               |
| `enhancement_responses`         | Met     | `feature_request.md` + issues d'amélioration traitées.                          |
| `report_archive`                | Met     | Issues GitHub publiques et searchable.                                          |
| `vulnerability_report_process`  | Met     | `SECURITY.md` publié, lié au repo.                                              |
| `vulnerability_report_private`  | Met     | GitHub **Private Vulnerability Reporting** + e-mail mainteneur (`SECURITY.md`). |
| `vulnerability_report_response` | Met     | Délai de réponse visé documenté (`SECURITY.md`).                                |

## Quality

| Critère                       | Réponse | Justification / preuve                                                                                           |
| ----------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------- |
| `build`                       | N/A     | IaC : pas de compilation. « Build » = build doc Astro (`docs.yml`) + validation manifestes (kubeconform).        |
| `build_common_tools`          | Met     | pnpm, uv, ansible, kubeconform, Astro (outils standards).                                                        |
| `build_floss_tools`           | Met     | Toute la chaîne est FLOSS.                                                                                       |
| `test`                        | Met     | Suite FLOSS : **bats** (`bench/unit/`, 10 fichiers), **pytest/unittest** (`tests/`, 31 fichiers), scénarios e2e. |
| `test_invocation`             | Met     | `pnpm test:shell`, `pnpm test:python` (unittest discover).                                                       |
| `test_most`                   | Met     | Large couverture : ~31 fichiers pytest + 10 suites bats + 31 scénarios e2e.                                      |
| `test_continuous_integration` | Met     | CI GitHub Actions sur chaque push/PR (`ci.yml`).                                                                 |
| `test_policy`                 | Met     | Politique documentée (`docs/architecture/plan-de-tests.md`, ADR 0045).                                           |
| `tests_are_added`             | Met     | Tests ajoutés avec les features (ex. property-based ADR 0087, `gitops-assert.bats`).                             |
| `tests_documented_added`      | Met     | `plan-de-tests.md` + section Tests de `CONTRIBUTING.md`.                                                         |
| `warnings`                    | Met     | Linters stricts en CI : ruff, shellcheck, yamllint, ansible-lint, markdownlint, kubeconform `-strict`.           |
| `warnings_fixed`              | Met     | **12 checks bloquants** requis sur `main` (`strict`, `enforce_admins`).                                          |
| `warnings_strict`             | Met     | `kubeconform -strict`, `jscpd ≤5%`, `ruff format --check` global, CodeQL `security-and-quality`.                 |

## Security

| Critère                          | Réponse | Justification / preuve                                                                                                     |
| -------------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `know_secure_design`             | Met     | Modèle de menace explicite + compromis tracés en ADR (`SECURITY.md`, `SAFEGUARDS.md`).                                     |
| `know_common_errors`             | Met     | gitleaks (secrets), CodeQL (SAST), trivy (IaC), Scorecard.                                                                 |
| `crypto_published`               | N/A     | Pas de crypto maison ; TLS standard via cert-manager.                                                                      |
| `crypto_call`                    | N/A     | Aucun appel crypto direct dans le code (IaC).                                                                              |
| `crypto_floss`                   | N/A     | Pas de fonctionnalité crypto propre ; briques FLOSS (cert-manager, etcd).                                                  |
| `crypto_keylength`               | N/A     | Pas de génération de clés par le projet ; cert-manager gère.                                                               |
| `crypto_working`                 | N/A     | Aucun algorithme crypto implémenté.                                                                                        |
| `crypto_weaknesses`              | N/A     | Idem.                                                                                                                      |
| `crypto_pfs`                     | N/A     | Pas de négociation de clé maison ; TLS délégué.                                                                            |
| `crypto_password_storage`        | N/A     | Pas de stockage de mot de passe applicatif (RStudio sans auth ADR 0012, registry HTTP ADR 0011, mono-tenant isolé).        |
| `crypto_random`                  | N/A     | Pas de génération de clés/nonces par le projet.                                                                            |
| `delivery_mitm`                  | Met     | Git/HTTPS + **images épinglées par digest** (ADR 0006) + checksums vérifiés (gitleaks).                                    |
| `delivery_unsigned`              | Met     | Téléchargements via HTTPS + vérif checksum.                                                                                |
| `vulnerabilities_fixed_60_days`  | Met     | Renovate (`pinDigests`) + Scorecard ; les vulns transitives VitePress sont **éteintes** par la migration Astro (ADR 0089). |
| `vulnerabilities_critical_fixed` | Met     | Renovate + Scorecard + délai `SECURITY.md`.                                                                                |
| `no_leaked_credentials`          | Met     | Valeurs d'exemple génériques (ADR 0023) ; gitleaks scanne l'historique ; vraies valeurs en config locale gitignorée.       |

## Analysis

| Critère                                  | Réponse | Justification / preuve                                                                            |
| ---------------------------------------- | ------- | ------------------------------------------------------------------------------------------------- |
| `static_analysis`                        | Met     | **CodeQL** (Python, `codeql.yml`) + trivy (IaC) + ruff + shellcheck + ansible-lint + kubeconform. |
| `static_analysis_common_vulnerabilities` | Met     | CodeQL `security-and-quality` + trivy HIGH/CRITICAL + gitleaks.                                   |
| `static_analysis_fixed`                  | Met     | trivy bloque HIGH/CRITICAL (compromis ciblés justifiés dans `.trivyignore.yaml`).                 |
| `static_analysis_often`                  | Met     | À chaque push/PR + cron hebdo (CodeQL, Scorecard).                                                |
| `dynamic_analysis`                       | Met     | Banc e2e Lima : 31 scénarios (résilience, sécu active, chaos) ; property-based (ADR 0087).        |
| `dynamic_analysis_unsafe`                | N/A     | Pas de langage memory-unsafe (Python/bash/YAML).                                                  |
| `dynamic_analysis_enable_assertions`     | Met     | Gates bloquants à chaque phase du banc (`bench/lima/run-phases.sh`).                              |
| `dynamic_analysis_fixed`                 | Met     | Écarts e2e indexés (registre des drifts) puis corrigés dans le code (ADR 0046/0052).              |

## Synthèse & action restante

- **Met : ~49 · N/A : ~12 · Unmet : 1.** Le badge **passing** ignore les N/A
  justifiés → il ne reste qu'**un** critère à traiter.
- **`english` (SHOULD)** — le seul manque. Deux voies :
  1. cocher **Met** en justifiant (« projet académique francophone ; issues et
     rapports de sécurité en anglais acceptés ») — suffisant pour un SHOULD ;
  2. (mieux) ajouter un **encart anglais** dans `README.md` + une mention dans
     `CONTRIBUTING.md`/`SECURITY.md`. Effort ~30 min.

> **Au-delà de passing** (utile pour silver/gold) : signatures GPG vérifiées,
> branch protection stricte (`enforce_admins`), CodeQL + Scorecard + trivy +
> gitleaks, `CITATION.cff` + DOI, `CODEOWNERS`, permissions GITHUB_TOKEN au
> moindre privilège, images épinglées par digest, releases signées (cosign +
> SLSA, [ADR 0088](../decisions/0088-signature-releases-cosign-slsa.md)).
