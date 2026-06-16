# 0067 — Workflows multi-agents consignés : 4ᵉ trace empirique

## Statut

Superseded (2026-06-16) par [ADR 0078](0078-passages-audit-famille-unique.md).
Accepted le 2026-06-13.

> **Pourquoi superseded.** Cet ADR traitait les workflows multi-agents consignés
> comme une **4ᵉ trace empirique distincte**, matérialisée par un sous-dossier
> `docs/audit/workflows/`. L'ADR 0078 acte qu'un passage d'audit **issu d'un
> workflow** n'est pas une famille à part mais une **propriété de méthode** du
> passage : tous les passages vivent à plat dans `docs/audit/`. La doctrine de
> fond (consigner la synthèse + les findings vérifiés, append-only, renvoi aux
> ADR, honnêteté) **reste valable** — elle est reprise et généralisée par 0078.

## Contexte

Les décisions structurantes du dépôt s'appuient de plus en plus sur des
**workflows multi-agents** : une cartographie en éventail (N lecteurs +
synthèse) qui fonde une ADR, une **revue adversariale** (N lentilles, chaque
finding vérifié sceptiquement) avant de committer un palier. Plusieurs décisions
récentes en sont issues : la conception de l'outil déclaratif (ADR 0056 paliers
P3-P6), l'**[ADR 0066](0066-rollback-atomique-graphe-composants.md)** (rollback
atomique, fondée sur une cartographie des composants), et des **revues
adversariales** qui ont rattrapé de vrais bugs avant merge (mappings de
catalogue erronés, race `Terminating`, périmètre de rollback incomplet…).

Or **ces rapports et synthèses sont éphémères** : ils vivent dans un répertoire
de tâches temporaire, **hors du dépôt**, et disparaissent. On perd alors la
**justification empirique** d'une décision — combien d'indépendants l'ont
vérifiée, quels findings ont été confirmés, ce qui a été écarté. C'est
exactement ce que les autres traces empiriques préservent pour les _runs_ et les
_audits_.

L'[ADR 0058](0058-doctrine-audit-grille-passages.md) a déjà institué **trois
traces empiriques** (datées, mesurées, non réécrites) :

1. les **passages d'audit** datés (`docs/audit/AAAA-MM-JJ/`) ;
2. **`bench/lima/RESULTS.md`** (déroulé réel des runs de banc) ;
3. le **registre des drifts** (`registre-drifts.yaml`, §6) — un écart révélé par
   un run que le lint ne voyait pas.

Un workflow d'audit relève de la **même famille** : un raisonnement assisté,
**vérifié par des agents indépendants**, qui fonde une décision et que le lint
ne produit pas.

## Décision

**Un workflow multi-agents qui fonde une décision structurante est consigné
comme 4ᵉ trace empirique** — au même titre que les passages d'audit,
`RESULTS.md` et le registre des drifts (ADR 0058 §6).

### Quoi consigner (et quoi NON)

- **On consigne la SYNTHÈSE + les findings vérifiés** — la conclusion du
  workflow : la décision fondée, le verdict consolidé, les findings confirmés
  (et combien écartés). **Pas les rapports bruts des lecteurs.**
- **Pourquoi pas les rapports bruts** : ils contiennent des **chemins absolus du
  poste**, des sorties non assainies, des détails propres à une instance — les
  versionner tels quels **violerait
  l'[ADR 0023](0023-plateforme-exemple-generique.md)** (valeurs génériques). La
  synthèse, elle, est rédigée et citable.
- **Honnêteté** ([ADR 0052](0052-reproductibilite-des-resultats.md)) : on
  consigne **autant** un workflow dont la revue a **rejeté** une approche ou
  trouvé peu/pas de findings qu'un succès — un audit qui ne trouve rien est une
  donnée, pas un trou.

### Format & emplacement

- Emplacement : **`docs/audit/workflows/`** (sous la racine d'audit existante,
  ADR 0058) — un fichier Markdown par workflow consigné.
- Chaque entrée porte : **date**, **type** (cartographie | revue adversariale |
  autre), **décision/PR fondée** (lien), **éventail** (nombre de
  lecteurs/lentilles), **verdict** (findings confirmés / écartés), et la
  **synthèse** assainie.
- **Append-only / non réécrite** : comme un passage d'audit ou `RESULTS.md`, une
  entrée consignée n'est pas réactualisée — elle est « le raisonnement **au**
  AAAA-MM-JJ ». Les décisions évoluent dans les ADR ; la trace reste honnête à
  sa date.
- **Renvoi, pas duplication** : l'entrée **cite** l'ADR/le plan/la PR qu'elle a
  fondé(e) ; elle ne re-justifie pas la décision (les _pourquoi_ vivent dans
  l'ADR, [ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)).

### Quand consigner (et quand pas)

- **À consigner** : un workflow qui **fonde une décision structurante** (une
  ADR, un palier livré, un changement de modèle) ou dont la **revue
  adversariale** garde-le mérite (findings réels avant merge).
- **À NE PAS consigner** : les fan-outs **opérationnels** jetables (une
  recherche de fichier, un sweep sans verdict décisionnel). La trace sert la
  **gouvernance**, pas chaque exécution — sinon elle se dilue (même esprit que «
  le registre de drifts ne consigne pas chaque log de run »).

## Conséquences

- Une nouvelle famille d'artefact versionné, **léger** (synthèses, pas de
  dumps), qui matérialise la doctrine « **éprouver, pas affirmer** » : on voit
  qu'une décision a été **vérifiée par des indépendants** avant d'être actée.
- **Étend l'ADR 0058 §6** : la cartographie documentaire compte désormais
  **quatre** traces empiriques. Un futur passage d'audit peut **noter** la
  couverture des décisions par des workflows consignés.
- Charge : un workflow consigné = une synthèse à **assainir** (retirer chemins
  absolus, génériser) avant commit. Acceptable car on ne consigne que les
  workflows **décisionnels**, pas tous.

### Alternatives écartées

- **Consigner les rapports bruts** : trace complète mais lourde et en conflit
  avec l'ADR 0023 (chemins/instances) ; coût d'assainissement à chaque lecteur.
- **Un simple journal append-only** (workflow, date, lien — sans contenu) : trop
  pauvre ; on perd le **verdict** (findings confirmés/écartés) qui fait la
  valeur d'audit.
- **Ne rien consigner** (statu quo) : la justification empirique des décisions
  reste éphémère — exactement le problème que les trois autres traces ont résolu
  pour les runs et les audits.
