# Plan — Refonte documentaire : hero, manifeste, câblage, Diátaxis

## État

> **État : Achevé** (2026-06-13) · **Fonde :
> [ADR 0059](../decisions/0059-diataxis-typologie-documentation.md)** (Accepted)
> · **Issues : [#276](https://github.com/univ-lehavre/cluster/issues/276)**
> (fermée), #279 (mergée)
>
> **Fonde** :
> [ADR 0059 — Diátaxis](../decisions/0059-diataxis-typologie-documentation.md).
> **Issue** : [#276](https://github.com/univ-lehavre/cluster/issues/276).
> **Date** : 2026-06-11.

## Objectif

Faire du site une **porte d'entrée narrative** sans dégrader la doc experte.
L'[audit documentation](../audit/2026-05-29/04-documentation.md) avait noté la
pédagogie néophyte 2/5 (jargon avant définition, pas de récit d'entrée) ; son
action n° 1 (« glossaire + lier chaque premier usage d'un terme ») est à moitié
faite — le [glossaire](../glossaire.md) existe, le câblage manque. Ce plan le
complète et ajoute le récit manquant.

## Principe directeur

Le récit **orchestre et relie** l'existant ; il ne le recopie pas. Un seul lieu
de _narration_ néophyte ([manifeste.md](../manifeste.md)), pas un seul lieu de
_tout_. La typologie des pages suit
[Diátaxis](../decisions/0059-diataxis-typologie-documentation.md) : tutorial
([demarrage](../demarrage.md)), how-to (RUNBOOK), reference
([glossaire](../glossaire.md)), explanation (manifeste,
[composants](../composants.md), ADR). Les liens entre modes sont **dirigés par
l'intention**, jamais « par complétude ».

## Lots (un commit par lot, chacun laisse `pnpm lint` vert)

1. **ADR 0059** — la décision Diátaxis + ligne d'index `decisions/README.md`.
   _(fait)_
2. **Ce plan** — `docs/plans/2026-06-11-…` + ligne d'index `plans/README.md`.
3. **Manifeste** — `docs/manifeste.md` câblé + entrées nav/sidebar dans
   `docs/.vitepress/config.mjs`. Structure (article scientifique) :
   - **Contexte** — cluster de recherche, 4 nœuds, isolé, hypothèse réseau
     privé.
   - **Objectif** — ce que la plateforme vise à démontrer/fournir.
   - **Revue de la littérature** — l'état de l'art et les briques retenues face
     aux alternatives (s'appuie sur [composants](../composants.md) et les ADR de
     choix, ex. Rook-Ceph vs Longhorn, Cilium, CloudNativePG…).
   - **Données** — datalake, lineage, état du cluster, inventaire matériel.
   - **Méthode** — normes (Nygard, Diátaxis, merge-commit, atteignabilité),
     langages/doctrine outil, open-source (vs payant notoire), compétences RH,
     reproductibilité, garde-fous.
   - **Le voyage parcouru** — ADR · Drifts · Audits · Plans · Issues · preuves
     opérationnelles (sous-sections H3).
   - **Résultats** _(minimal)_ — contrat d'interface, guide dev data, chaîne
     DataOps, CLI `access.sh`. PWA/TUI/Sandbox nommés sans lien mort.
4. **Alignement** — `demarrage.md`, `glossaire.md`, `composants.md` : retrait
   **conservateur** des liens « par complétude » (transitions dirigées
   uniquement), chaque retrait justifié dans le commit, aucune atteignabilité
   cassée.
5. **Hero** — frontmatter `layout: home` en tête de `README.md` (cartes
   `features` vers les thématiques), contenu court conservé dessous. Pas de
   changement de rewrite VitePress → zéro orphelin.

## Convention de câblage

Lien Markdown **standard** : `[mot-clé](cible)` (pas de symbole décoratif).
Markdown pur (portable GitHub + VitePress). Premier usage **par section**
seulement. Cibles : `glossaire.md#slug`, `decisions/NNNN-slug.md`,
`composants.md#slug`, `../bootstrap/RUNBOOK.md`. Vérifier chaque ancre contre le
slug réel du titre cible (sinon `docs:build` casse).

## Contraintes dures (vérifiées)

- `pnpm lint` couvre `format:check` + `lint:docs-orphans`, **pas** `docs:build`
  (job CI séparé) : le récit doit donc exister avant que les liens `.md` vers
  lui passent le build → ordre des lots respecté (manifeste au lot 3).
- `check_md_orphans.py`
  ([ADR 0029](../decisions/0029-markdown-atteignable-doc.md)) : `link: '/'` →
  `README.md`. Garder le hero dans le README préserve la racine du BFS ; chaque
  page nouvelle doit être atteignable.
- Généricité de la prose
  ([ADR 0023](../decisions/0023-plateforme-exemple-generique.md)) : valeurs
  d'exemple, jamais valeurs réelles. Garder les briques nommées.
- Commits ([ADR 0037](../decisions/0037-strategie-merge-commit.md)) : sujet
  minuscule, ≤ 100 col, sans `Co-Authored-By`, hooks jamais bypassés.

## Hors scope (signalé, non traité)

La sidebar ne liste que les ADR 0001-0019 sur 50+ — incohérence d'expérience
(pas un défaut d'atteignabilité : les autres ADR restent atteignables via
l'index `decisions/`). À traiter dans un lot dédié (génération dynamique de la
liste ADR), pas ici.

## Vérification (avant push)

1. `pnpm docs:build` — aucun lien ni ancre mort (contrôle dur des `.md` et
   `#…`).
2. `pnpm lint:docs-orphans` — aucun orphelin.
3. `pnpm format:check` (prettier proseWrap 80) + markdownlint.
4. `pnpm docs:dev` — revue visuelle : hero (cartes), liens de câblage
   cliquables.
5. commitlint vert sur toute la plage.

## Journal d'exécution

- 2026-06-11 — Première rédaction (PR #279), ADR proposé en 0055.
- 2026-06-13 — Rattrapage du contenu de #279 (restée en conflit) : l'ADR
  Diátaxis est **renuméroté 0059** (0055 a été pris entre-temps par
  [ha-3cp](../decisions/0055-ha-3cp-hyperconverge-promotion-in-place.md)).
  Manifeste + hero + câblage nav repris et réconciliés avec `main` (sans
  `STATUS.md` retiré, sans Tailscale abandonné, datasets nommés génériques).

## Suivi (ADR 0057)

État : **Achevé** (cf. en-tête `## État`). Hero, manifeste, ADR Diátaxis (0059)
et alignement `demarrage` livrés via #279.

**Issues rattachées** : #276 (fermée — livrée par #279), #279 (mergée). **Runs
de preuve** : sans objet (refonte documentaire, validée par `docs:build`).
