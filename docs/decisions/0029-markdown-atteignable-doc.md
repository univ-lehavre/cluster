# 0029 — Toute page Markdown est atteignable depuis la documentation

## Contexte

La documentation est publiée par VitePress (`srcDir=..`) : les README/RUNBOOK
restent colocalisés avec le code et sont **surfacés via le sidebar**
(`docs/.vitepress/config.mjs`). Rien n'empêchait jusqu'ici qu'un nouveau `*.md`
(ADR, vue d'architecture, README de brique, page de plan) soit committé **sans
jamais être relié** : il existe sur GitHub mais reste invisible sur le site
publié — une page orpheline. L'audit documentation
([`docs/audit/04-documentation.md`](../audit/2026-05-29/04-documentation.md))
avait déjà relevé ce risque ; il se matérialise à chaque ajout de page non
câblée.

VitePress vérifie les **liens morts** (`ignoreDeadLinks` ciblé) mais **pas
l'inverse** : il ne signale pas une page qui n'est la cible d'aucun lien. La
règle « tout `*.md` doit être lié à la documentation » n'était donc ni écrite ni
contrôlée.

## Décision

**Tout fichier `*.md` versionné est _atteignable_ depuis la documentation.**

« Atteignable » = l'une des deux conditions :

1. le fichier a une entrée `link:` dans le sidebar/nav VitePress ; **ou**
2. il est la cible (éventuellement transitive) d'un lien Markdown depuis une
   page elle-même atteignable.

Cette définition **n'oblige pas** à inscrire chaque page au sidebar : un ADR
atteint via la table de l'[index ADR](README.md), un README de brique atteint
depuis [`platform/`](../../platform/), une vue depuis
[`docs/architecture/`](../architecture/) sont conformes. On exige une **chaîne
de navigation**, pas une entrée plate par fichier (un sidebar de ~100 entrées
serait illisible et fragile).

**Exclusions** (non rendues par le site, alignées sur `srcExclude` du config) :
`node_modules/`, `.github/`, `**/CHANGELOG.md`, `**/LICENSE.md`,
`docs/.vitepress/`.

**Contrôle** : le script
[`scripts/check_md_orphans.py`](../../scripts/check_md_orphans.py) calcule
l'atteignabilité (BFS depuis les racines sidebar + liens Markdown) et échoue sur
tout orphelin. Python plutôt que bash — parcours de graphe + résolution de liens
relatifs ([ADR 0017](0017-langage-des-scripts.md)) — et sa logique pure est
**testée**
([`tests/test_check_md_orphans.py`](../../tests/test_check_md_orphans.py)). Il
est branché dans `pnpm lint` (`lint:docs-orphans`) et donc en CI.

## Statut

Accepted.

## Conséquences

- **Gain** : plus de page publiée invisible ; la règle est exécutable, pas
  déclarative. Le contrôle est local (`pnpm lint`) et bloquant en CI.
- **Prix à payer** : ajouter un `*.md` impose de le relier (sidebar ou lien
  depuis une page existante) avant de merger — friction volontaire, faible.
- **Garde-fou** : le script lit la définition « atteignable » au sens large ; un
  `*.md` légitimement non publié doit être ajouté aux exclusions du script
  **et** du `srcExclude` VitePress, avec justification — pas contourné en le
  liant artificiellement.
- **Limite** : le BFS résout les liens Markdown relatifs et absolus de site, pas
  les inclusions dynamiques ; une page atteinte uniquement par un mécanisme non
  textuel serait vue comme orpheline (cas non rencontré à ce jour).
