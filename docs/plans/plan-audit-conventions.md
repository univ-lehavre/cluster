# Plan — Audit régulier du respect des conventions de gouvernance

## État

> **État : Actif** (depuis 2026-06-13) · **Fonde :
> [ADR 0060](../decisions/0060-audit-conventions-gouvernance.md)** (Accepted) ·
> **Issues : _(aucune — implémenté directement en une PR ; à lier si des lots
> restent ouverts)_**.
>
> **Cadre**
> ([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md)) :
> ce plan met en œuvre
> l'[ADR 0060](../decisions/0060-audit-conventions-gouvernance.md) ; les
> _pourquoi_ vivent dans l'ADR, ce plan porte le déroulé.

## Objectif

Outiller la vérification automatique du respect des conventions de gouvernance
(ADR 0057/0058/0029/0023) et la fraîcheur des traces, via un script versionné +
un cron non bloquant + un bloc de statistiques affiché.

## Lots

1. **Script `scripts/check_gouvernance.py`** — logique pure testée
   (`tests/test_check_gouvernance.py`), façade CLI : `--report` (humain),
   `--stats` (bloc chiffres), code de sortie 0/1. Câblé
   `pnpm check:gouvernance`.
2. **Workflow cron** `.github/workflows/conventions-freshness.yml` —
   hebdomadaire, non bloquant, ouvre/met à jour une issue dédoublonnée par label
   `audit-conventions` (motif `bench-freshness.yml`).
3. **Bloc « le dépôt en chiffres »** — stats injectées dans la doc
   (README/manifeste), régénérables par `--stats`.

## Vérification

`pnpm lint` (ruff + tests pytest), `pnpm docs:build`, markdownlint. Le script
tourné sur le dépôt lui-même doit passer (le dépôt respecte ses propres
conventions, ou les manquements détectés sont réels et tracés).

## Suivi

| Lot                              | État                   |
| -------------------------------- | ---------------------- |
| 1. Script + tests                | 🔲 en cours (cette PR) |
| 2. Workflow cron non bloquant    | 🔲 en cours (cette PR) |
| 3. Bloc statistiques dans la doc | 🔲 en cours (cette PR) |

**Issues rattachées** : aucune préexistante — l'implémentation tient en une PR.
Si le premier run du script révèle des manquements de gouvernance réels, ils
deviennent des issues liées ici (ADR 0058 §4 : un constat actionnable = une
issue).
