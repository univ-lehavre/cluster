<!--
Merci de votre contribution ! Quelques rappels :
- Titre de PR et commits au format Conventional Commits (feat:, fix:, docs:,
  ci:, chore:…) — sinon commitlint échoue. Sujet en minuscule, sans email.
- Toute modification d'infra réseau/stockage doit passer par le banc
  (test/multi-node/) avant la prod — cf. SAFEGUARDS.md.
-->

## Quoi & pourquoi

<!-- Décrire le changement et la motivation. Lier l'item d'audit / l'ADR si pertinent. -->

## Type de changement

- [ ] `fix` — correction de bug
- [ ] `feat` — nouvelle capacité
- [ ] `docs` — documentation seule
- [ ] `ci` / `chore` — outillage, CI, dépendances
- [ ] Autre :

## Vérifications

- [ ] `pnpm lint` passe en local (prettier, yamllint, shellcheck, jscpd)
- [ ] `pnpm lint:k8s` / `ansible-lint` passent si manifestes/rôles modifiés
- [ ] Décision de conception tracée en ADR si structurante (`docs/decisions/`)
- [ ] Validé sur le banc si changement d'infra (ou raison expliquée)
- [ ] `STATUS.md` mis à jour si un item d'audit avance (avec horodatage)

## Notes pour la revue

<!-- Points d'attention, limites de validation, captures, etc. -->
