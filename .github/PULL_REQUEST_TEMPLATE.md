<!--
Merci de votre contribution ! Quelques rappels :
- Ce dépôt merge en SQUASH : le TITRE de cette PR devient le commit sur main et
  alimente le CHANGELOG. Donc :
  - Titre au format Conventional Commits (feat:, fix:, docs:, ci:, chore:…),
    sujet en minuscule, sans email — la CI le valide (sinon échec).
  - NE PAS mettre « (#issue) » dans le titre : le squash ajoute déjà « (#PR) ».
  - 1 PR = 1 type/scope cohérent (= 1 ligne de CHANGELOG). Les docs/tests qui
    servent la feature peuvent l'accompagner ; deux features distinctes = deux PR.
- Toute modification d'infra réseau/stockage doit passer par le banc
  (test/multi-node/) avant la prod — cf. SAFEGUARDS.md.
-->

## Quoi & pourquoi

<!-- Décrire le changement et la motivation. Lier l'item d'audit / l'ADR si pertinent. -->

## Issue liée

<!--
Sous squash, c'est ICI (description de PR) que le lien d'auto-fermeture vit —
PAS dans le corps des commits (le squash les enfouit). « Closes #N » ferme
l'issue au merge ET garde le lien commit↔issue durable.
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
