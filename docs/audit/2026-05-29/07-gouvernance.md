# 7 — Gouvernance, licence & conformité projet

**Note : 3 / 5**

Gouvernance de base solide : licence MIT cohérente racine ↔ `package.json`,
`CONTRIBUTING.md` clair, versionnement automatisé via release-please documenté,
`CHANGELOG` tenu, gouvernance des décisions exemplaire (12 ADR indexés), badge
DOI Zenodo, et « branch protection » applicative via le hook pre-push. En
revanche, plusieurs éléments attendus d'un dépôt OSS académique public manquent,
et deux incohérences de conformité existent (licence divergente du subtree,
outillage de versionnement redondant).

## Points forts

- `LICENSE` MIT cohérente avec `package.json` (© Université Le Havre Normandie
  2026).
- `CONTRIBUTING.md` complet (installation, workflow PR, Conventional Commits,
  validation locale, section Tests).
- Versionnement automatique documenté (release-please + `release.yml`).
- 12 ADR au format Nygard indexés.
- `CHANGELOG` conforme Keep a Changelog + SemVer, généré.
- Badge DOI Zenodo (`10.5281/zenodo.20287209`).
- Branch protection applicative (hook `no-direct-push-to-main`) + commitlint CI.
- Mention Trademarks dans le README.

## Constats

### Majeur (→ vérifié mineur) — Licence Unlicense (subtree) vs MIT (racine)

- **Fichier** : `bootstrap/security/LICENSE`
- **Constat** : la racine est MIT, mais le subtree `bootstrap/security/` est en
  Unlicense (domaine public, vestige de `server-security`), sans note
  explicative racine. _Ramené à mineur : Unlicense n'est pas incompatible avec
  MIT (domaine public, maximalement permissif) ; défaut de clarté, pas de
  blocage légal._
- **Recommandation** : re-licencier le subtree en MIT (et supprimer son
  `LICENSE`), **ou** documenter la divergence (NOTICE racine + en-tête SPDX).
  Vérifier la politique de PI de l'Université.

### Majeur (→ vérifié mineur) — Absence de `SECURITY.md`

- **Fichier** : `.github/` (ne contient que `workflows/`)
- **Constat** : aucune politique de divulgation, alors que c'est de l'IaC de
  sécurité avec des compromis assumés. _Ramené à mineur : ne crée aucune faille,
  l'e-mail mainteneur est un canal ad hoc, choix risqués déjà en ADR._
- **Recommandation** : `SECURITY.md` (versions supportées, canal privé / GitHub
  Security Advisories, délai de réponse) ; activer Private Vulnerability
  Reporting.

### Mineur — Outillage de versionnement redondant

- **Fichier** : `package.json:24-25`, `CONTRIBUTING.md:97-99`
- **Constat** : release-please (source de vérité) **et** commit-and-tag-version
  (scripts `release`/`release:dry`) coexistent ; risque de désynchronisation des
  sections de CHANGELOG.
- **Recommandation** : trancher pour release-please seul (retirer
  commit-and-tag-version), ou documenter le fallback manuel comme exception.

### Mineur — En-tête du `CHANGELOG.md` contredit la source de vérité

- **Fichier** : `CHANGELOG.md:7-15`
- **Constat** : l'en-tête référence commit-and-tag-version alors que le corps
  est au format release-please. Doc auto-contradictoire.
- **Recommandation** : réécrire l'en-tête pour pointer release-please.

### Mineur — Absence de `CODE_OF_CONDUCT.md`

- **Recommandation** : Contributor Covenant + point de contact, lié depuis
  `CONTRIBUTING.md`.

### Mineur — Absence de `CITATION.cff` (public = recherche)

- **Fichier** : racine ; cf. `README.md:3`
- **Constat** : badge DOI présent mais pas de `CITATION.cff` → pas de bouton «
  Cite this repository » GitHub. Deux DOI coexistent (cluster + server-security)
  sans indication de celui à citer.
- **Recommandation** : `CITATION.cff` (auteurs + ORCID, titre, DOI cluster,
  version, date) ; préciser le DOI à citer. **Important pour la reproductibilité
  académique.**

### Suggestions

- Pas de templates issue/PR ni de `CODEOWNERS` → ajouter
  `.github/pull_request_template.md` (checklist hooks/ADR/doc), un template
  d'issue, un `CODEOWNERS`.
- Branch protection **uniquement** côté client (hook contournable via
  `--no-verify`) → activer une **branch protection rule GitHub** (PR
  obligatoire, status checks CI requis) ; documenter dans `SAFEGUARDS.md`.
- `bootstrap/security/CHANGELOG.md` au format Changesets = 3ᵉ schéma de
  versionnement vestigial → supprimer ou marquer « gelé/historique ».
