# Plans & audits de session

Ce dossier conserve la **trace des feuilles de route d'implémentation** (plans
d'étape du socle) et des **audits de session** (analyses d'impact ponctuelles :
réalignements de branche, décisions de réintégration, dettes constatées).

Il complète les deux autres traces du dépôt, sans s'y substituer :

| Trace                         | Dossier                      | Nature                                                                                                         |
| ----------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Décisions**                 | `docs/decisions/`            | ADR (format Nygard) — **décision** structurante, immuable.                                                     |
| **Audit du dépôt**            | `docs/audit/`                | État des lieux qualité daté, vérifié de façon adversariale.                                                    |
| **Plans & audits de session** | `docs/plans/` _(ce dossier)_ | **Comment** on met en œuvre une décision (plan d'étape) et **ce qui s'est passé** en route (audit de session). |

## Frontière (ADR 0023) — ce qui vit ICI vs ailleurs

Ce dépôt est un **catalogue de topologies d'infrastructure** générique. Donc :

- ✅ **Plans d'INFRA** (socle cluster : monitoring, base managée,
  orchestrateur…), en **valeurs génériques**, sont versionnés ici.
- ❌ **Plans MÉTIER / applicatifs** (cas d'usage propres à un projet, pipelines
  de données spécifiques, ADR applicatifs) **n'ont pas leur place ici** : ils
  vivent dans le dépôt applicatif (`atlas`). Un plan-maître transverse couvrant
  l'infra ET le métier reste côté applicatif (sa Phase « socle » référence ce
  dépôt).

## Convention de nommage

- **Plan d'étape** : `AAAA-MM-JJ-<sujet>.md` (date de rédaction du plan).
  Référence en en-tête l'ADR qui le **fonde** (un plan met en œuvre une décision
  ; il ne la remplace pas).
- **Audit de session** : `AAAA-MM-JJ-audit-<sujet>.md`. Consigne une analyse
  d'impact ponctuelle (collision de branches, réintégration, dette).
- Chaque plan d'étape porte une section **« Journal d'exécution »** renvoyant
  aux audits de session liés.

## Index

| Fichier                                                                                        | Type  | Sujet                                                     |
| ---------------------------------------------------------------------------------------------- | ----- | --------------------------------------------------------- |
| [2026-06-04-etape-1.7-dagster.md](2026-06-04-etape-1.7-dagster.md)                             | Plan  | Étape 1.7 — orchestrateur Dagster (event log dans CNPG)   |
| [2026-06-05-etape-1.8-marquez.md](2026-06-05-etape-1.8-marquez.md)                             | Plan  | Étape 1.8 — Marquez (lineage OpenLineage) + harnais E2E   |
| [2026-06-04-audit-realignement-main-dagster.md](2026-06-04-audit-realignement-main-dagster.md) | Audit | Réalignement `feat/dagster` ↔ `main` (renumérotation ADR) |
