# 0078 — Passages d'audit : une seule famille, la méthode est une propriété

## Statut

Accepted (2026-06-16). **Supersède
[ADR 0067](0067-workflows-consignes-4e-trace-empirique.md)** (workflows
multi-agents consignés comme 4ᵉ trace empirique distincte). Prolonge
[ADR 0058](0058-doctrine-audit-grille-passages.md) (grille & passages d'audit)
et [ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) (gouvernance
documentaire).

## Contexte

L'[ADR 0058](0058-doctrine-audit-grille-passages.md) a institué la doctrine
**grille permanente + passages datés** de l'audit, dans `docs/audit/`. Un
passage applique la grille /5 à une date, renvoie aux ADR et transforme ses
manques en issues.

L'[ADR 0067](0067-workflows-consignes-4e-trace-empirique.md) a ensuite traité
les **workflows multi-agents consignés** (cartographie en éventail, revue
adversariale qui fonde une décision) comme une **4ᵉ trace empirique distincte**,
matérialisée par un **sous-dossier** `docs/audit/workflows/` avec son propre
README.

À l'usage, cette séparation crée plus de friction qu'elle n'apporte :

- **La frontière est poreuse.** Le sous-dossier `workflows/` a fini par
  accueillir aussi bien de vrais fan-outs multi-agents (vérification du graphe
  atomique, 5–60 agents) que des **passages d'audit ciblés** conduits sans
  éventail (notations de cybersécurité externes). Classer chaque nouvelle entrée
  « workflow ou passage ? » est un arbitrage récurrent sans valeur.
- **Deux README à tenir** (`docs/audit/README.md` et
  `docs/audit/workflows/README.md`) qui répètent la même doctrine (daté,
  append-only, renvoi aux ADR, manques → issues) et **deux index** des mêmes
  passages.
- **La distinction n'est pas de nature.** Qu'un passage soit conduit à la main
  ou par un essaim d'agents indépendants ne change ni ce qu'il **est** (une
  évaluation datée et non réécrite), ni ce qu'il **produit** (des findings
  vérifiés, des manques actionnables). C'est une **propriété de la méthode**,
  déjà capturée par les champs _Type_ et _Éventail_ de l'en-tête d'un passage.

Le registre des drifts (3ᵉ trace, ADR 0058 §6) et `RESULTS.md` restent, eux, des
familles **distinctes** : ils capturent autre chose qu'une évaluation (un écart
de run indexé ; le déroulé réel d'un run de banc). La fusion ne concerne **que**
les passages d'audit entre eux.

## Décision

**Il n'y a qu'une seule famille de passages d'audit.** Tous vivent **à plat**
dans `docs/audit/` ; un passage est conduit à la main **ou** issu d'un workflow
multi-agents — c'est une **propriété de méthode**, pas un type d'artefact à
part.

### Conventions

- **Emplacement** : `docs/audit/AAAA-MM-JJ-slug.md` pour un passage
  mono-fichier, ou `docs/audit/AAAA-MM-JJ/` pour un passage multi-fichiers
  (comme `2026-05-29/`). **Plus de sous-dossier `workflows/`.**
- **Un seul index** : `docs/audit/README.md` (grille + tableau de tous les
  passages). Le README de `workflows/` est supprimé, sa doctrine repliée dans
  l'index unique.
- **La méthode multi-agents est un champ d'en-tête**, pas un dossier : _Type_
  (grille /5 · ciblé · cartographie · revue adversariale) et _Éventail_ (nombre
  de lecteurs/lentilles + agents) disent comment le passage a été produit.
- **Ce qu'on consigne ne change pas** (repris de l'ADR 0067) : la **synthèse +
  les findings vérifiés**, jamais les rapports bruts (chemins absolus, sorties
  non assainies → [ADR 0023](0023-plateforme-exemple-generique.md)) ;
  **append-only / non réécrit** (« le raisonnement **au** AAAA-MM-JJ ») ;
  **renvoi** à l'ADR/plan/PR fondé(e) sans le re-justifier (ADR 0057) ;
  **honnêteté** ([ADR 0052](0052-reproductibilite-des-resultats.md)) — un
  passage qui ne trouve rien est une donnée, pas un trou.

### Conséquences sur les traces empiriques

L'ADR 0058 §6 dénombrait, après 0067, **quatre** traces empiriques. Après le
présent ADR il en reste **trois** : (1) les **passages d'audit** (qui absorbent
les ex-« workflows consignés »), (2) **`RESULTS.md`**, (3) le **registre des
drifts**. La trace « workflow consigné » n'est pas perdue — elle **est** un
passage d'audit dont l'en-tête porte la méthode multi-agents.

## Conséquences

- **Moins de friction** : plus d'arbitrage « workflow ou passage » à chaque
  entrée ; un seul README, un seul index.
- **Migration** : les entrées de `docs/audit/workflows/` remontent à plat dans
  `docs/audit/` (liens internes reprofondis d'un cran) ; les références externes
  (ADR 0058, 0075) pointent vers le nouvel emplacement ; l'ADR 0067 passe
  `Superseded`.
- **Doctrine préservée** : aucune règle de fond de 0058/0067 n'est abandonnée —
  elles sont unifiées. Un futur passage peut toujours **noter** la couverture
  des décisions par des passages issus de workflows.

### Alternatives écartées

- **Garder le sous-dossier `workflows/`** (statu quo 0067) : maintient deux
  README et l'arbitrage de classement, pour une distinction qui n'est pas de
  nature.
- **Amender 0067 sans le superseder** (cesser de matérialiser la 4ᵉ trace par un
  dossier, mais la garder comme famille conceptuelle) : laisse vivre une « 4ᵉ
  trace » que plus rien ne distingue d'un passage — la fiction d'une famille
  sans frontière observable. Superseder est plus honnête.
- **Fusionner aussi le registre des drifts et `RESULTS.md`** dans les passages :
  rejeté — ceux-là capturent une **autre nature** (incident de run indexé ;
  déroulé d'un run), pas une évaluation datée.
