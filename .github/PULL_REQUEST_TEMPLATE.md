<!--
Merci de votre contribution ! Quelques rappels (ADR 0037 — merge commit) :
- Ce dépôt merge en MERGE COMMIT (pas squash) : CHAQUE commit de la PR arrive
  tel quel sur main et alimente le CHANGELOG. Donc :
  - Chaque commit au format Conventional Commits (feat:, fix:, docs:, ci:,
    chore:…), sujet en minuscule, sans email — la CI valide commitlint sur TOUTE
    la plage de la PR (sinon échec). Soigner/regrouper ses commits avant le merge.
  - 1 PR = 1 type/scope cohérent. Les docs/tests qui servent la feature peuvent
    l'accompagner ; deux features distinctes = deux PR.
- Toute modification d'infra réseau/stockage doit passer par le banc
  (test/lima/) avant la prod — cf. SAFEGUARDS.md.
-->

## Quoi & pourquoi

<!-- Décrire le changement et la motivation. Lier l'item d'audit / l'ADR si pertinent. -->

## Issue liée

<!--
Mettre le lien d'auto-fermeture ICI (description de PR). « Closes #N » ferme
l'issue au merge ET garde le lien PR↔issue durable.
-->

Closes #

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
