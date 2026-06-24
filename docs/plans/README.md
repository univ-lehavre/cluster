# Plans & audits de session

Ce dossier conserve la **trace des feuilles de route d'implémentation** (plans
d'étape du socle) et des **audits de session** (analyses d'impact ponctuelles :
réalignements de branche, décisions de réintégration, dettes constatées).

Il complète les autres traces du dépôt, sans s'y substituer — **un ADR DÉCIDE,
un plan MET EN ŒUVRE, une issue EXÉCUTE, une PR LIVRE**
([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md)) :

| Trace                         | Dossier                      | Rôle                                                                              |
| ----------------------------- | ---------------------------- | --------------------------------------------------------------------------------- |
| **Décisions**                 | `docs/decisions/`            | ADR (Nygard) — **décide** (le _pourquoi_), structurante, **immuable**.            |
| **Audit du dépôt**            | `docs/audit/`                | **Mesure** l'écart à un standard — grille permanente + passages datés (ADR 0058). |
| **Plans & audits de session** | `docs/plans/` _(ce dossier)_ | **Met en œuvre** une décision (plan vivant) ; trace une session (audit daté).     |

## Frontière (ADR 0023) — ce qui vit ICI vs ailleurs

Ce dépôt est un **catalogue de topologies d'infrastructure** générique. Donc :

- ✅ **Plans d'INFRA** (socle cluster : monitoring, base managée,
  orchestrateur…), en **valeurs génériques**, sont versionnés ici.
- ❌ **Plans MÉTIER / applicatifs** (cas d'usage propres à un projet, pipelines
  de données spécifiques, ADR applicatifs) **n'ont pas leur place ici** : ils
  vivent dans le dépôt applicatif (`atlas`). Un plan-maître transverse couvrant
  l'infra ET le métier reste côté applicatif (sa Phase « socle » référence ce
  dépôt).

## Deux natures, deux conventions ([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md))

- **Plan (thématique, VIVANT)** : `plan-<thème>.md` — **pas daté**. Met en œuvre
  une décision tant qu'elle se réalise. **Référence l'ADR qui le fonde** en
  en-tête. Porte deux choses obligatoires :
  - un **en-tête `## État`** (champ de 1er niveau, comme l'ADR a son
    `## Statut`) : **Brouillon / Actif / Achevé / Abandonné**, daté, avec l'ADR
    fondateur et les issues. Un coup d'œil suffit à situer la mise en œuvre ;
  - une section **« Suivi »** : paliers (cases à cocher), **issues rattachées**
    (`#NNN`, créées OU **préexistantes adoptées**), renvoi aux runs de preuve
    ([`RESULTS.md`](../../bench/lima/RESULTS.md)).

  Le plan est le **tableau de bord** de la décision. **Jamais de
  paliers/checklist dans l'ADR** — ils vivent ici (l'ADR est immuable, le
  déroulé évolue). **`Proposed` ⇒ pas d'implémentation** : un plan ne devient
  `Actif` (et son code mergeable) qu'une fois l'ADR fondateur `Accepted`
  ([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) §6).
  Exemple : [`plan-modele-declaratif.md`](plan-modele-declaratif.md).

- **Audit de session (FIGÉ)** : `AAAA-MM-JJ-audit-<sujet>.md` — **daté**. Le
  journal d'un moment (collision de branches, réintégration, dette constatée).
  Reste daté car c'est une **photo assumée**, pas un tableau de bord.

> Le nommage thématique `plan-<thème>.md` s'applique à **tous** les plans
> vivants (les plans historiquement datés ont été renommés le 2026-06-13). Seuls
> les **audits de session** restent datés (`AAAA-MM-JJ-audit-<sujet>.md`).

## Index

| Fichier                                                                                        | Type        | Sujet                                                                                                                               |
| ---------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [plan-modele-declaratif.md](plan-modele-declaratif.md)                                         | Plan vivant | Modèle déclaratif des topologies — paliers P0-P8 + suivi (met en œuvre ADR 0056)                                                    |
| [plan-dagster.md](plan-dagster.md)                                                             | Plan        | Étape 1.7 — orchestrateur Dagster (event log dans CNPG)                                                                             |
| [plan-marquez.md](plan-marquez.md)                                                             | Plan        | Étape 1.8 — Marquez (lineage OpenLineage) + harnais E2E                                                                             |
| [2026-06-04-audit-realignement-main-dagster.md](2026-06-04-audit-realignement-main-dagster.md) | Audit       | Réalignement `feat/dagster` ↔ `main` (renumérotation ADR)                                                                           |
| [plan-rollback-par-phase.md](plan-rollback-par-phase.md)                                       | Plan        | Rollback par phase sur le banc (mise en œuvre ADR 0054)                                                                             |
| [plan-refonte-doc.md](plan-refonte-doc.md)                                                     | Plan        | Refonte documentaire — hero, manifeste, câblage Diátaxis (met en œuvre ADR 0059)                                                    |
| [plan-stockage-longhorn.md](plan-stockage-longhorn.md)                                         | Plan        | Longhorn, 3ᵉ profil de stockage (met en œuvre ADR 0064 — `Brouillon`)                                                               |
| [plan-renommer-test-bench.md](plan-renommer-test-bench.md)                                     | Plan vivant | Renommer `test/` → `bench/` + ré-indexer `bootstrap/` (met en œuvre ADR 0070)                                                       |
| [plan-ha-3cp-control-plane.md](plan-ha-3cp-control-plane.md)                                   | Plan        | HA control-plane 3 nœuds (promotion in-place, kube-vip) — met en œuvre ADR 0055/0047, absorbe #486/#490/#487 (`Brouillon`)          |
| [plan-build-evenementiel-gitops.md](plan-build-evenementiel-gitops.md)                         | Plan        | Build applicatif événementiel in-cluster + déploiement GitOps par digest — met en œuvre ADR 0095 (premier pas) + 0094 (`Brouillon`) |
