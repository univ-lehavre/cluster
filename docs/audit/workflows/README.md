# Workflows d'audit consignés — 4ᵉ trace empirique

Trace, **datée et non réécrite**, des **workflows multi-agents** qui ont fondé
une décision structurante : cartographie en éventail (N lecteurs + synthèse) ou
**revue adversariale** (N lentilles, findings vérifiés sceptiquement) avant un
merge. C'est la **4ᵉ trace empirique** du dépôt
([ADR 0067](../../decisions/0067-workflows-consignes-4e-trace-empirique.md)), à
côté des [passages d'audit](../), de
[`RESULTS.md`](../../../test/lima/RESULTS.md) et du
[registre des drifts](../../architecture/registre-drifts.yaml) (ADR 0058 §6).

## Ce qu'on consigne

La **synthèse + les findings vérifiés** — pas les rapports bruts des lecteurs
(chemins absolus, sorties non génériques → ADR 0023). Un fichier Markdown par
workflow, **append-only** (« le raisonnement **au** AAAA-MM-JJ »), qui
**renvoie** à l'ADR/PR qu'il a fondé(e) sans re-justifier la décision.

## Quand consigner

Un workflow qui **fonde une décision structurante** (ADR, palier livré,
changement de modèle) ou dont la **revue adversariale** a un verdict qui mérite
trace (findings réels avant merge). **Pas** les fan-outs opérationnels jetables
(recherche de fichier, sweep sans verdict) — la trace sert la gouvernance, pas
chaque exécution.

Honnêteté ([ADR 0052](../../decisions/0052-reproductibilite-des-resultats.md)) :
on consigne **autant** un workflow qui a rejeté une approche ou trouvé peu de
findings qu'un succès.

## Format d'une entrée

| Champ        | Contenu                                          |
| ------------ | ------------------------------------------------ |
| **Date**     | `AAAA-MM-JJ`                                     |
| **Type**     | cartographie · revue adversariale · autre        |
| **Fonde**    | ADR / plan / PR (lien)                           |
| **Éventail** | nombre de lecteurs / lentilles + nombre d'agents |
| **Verdict**  | findings confirmés / écartés (pour une revue)    |
| **Synthèse** | la conclusion assainie (générique, ADR 0023)     |

## Entrées

- [2026-06-13 — Vérification des périmètres atomiques (graphe ADR 0066)](2026-06-13-verification-graphe-atomique.md)
  — cartographie en éventail (5 agents) qui a vérifié 23 composants + 30+ arêtes
  contre le code avant l'encodage du graphe atomique (Lot 0).
