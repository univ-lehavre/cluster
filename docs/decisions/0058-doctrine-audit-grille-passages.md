# 0058 — Doctrine de l'audit : une grille permanente, des passages datés

## Contexte

`docs/audit/` contient une **évaluation qualité** du dépôt en 13 documents
(bonnes pratiques, tests, lint, doc, reproductibilité, sécurité, gouvernance,
opérabilité, langage, dispersion CLI, OSS, plan d'action), chaque dimension
**notée /5** et vérifiée de façon adversariale. C'est un travail sérieux et
utile.

Mais sa **forme** pose deux problèmes, devenus visibles à mesure que le dépôt
avance :

1. **Péremption.** L'audit est daté du **2026-05-29**. Depuis : **45 ADR
   ajoutés, ~100 PR mergées, l'installation de production complète**. Les notes
   /5 décrivent un dépôt qui n'existe plus. Or les documents **présentent** ces
   notes comme un état (« Note : 3,2 / 5 ») sans que leur péremption soit
   structurellement marquée — un audit figé qui se lit comme un présent est un
   **faux** avec le temps.
2. **Recoupement partiel avec les ADR.** Quand un audit explique _pourquoi_ un
   choix de moindre sécurité est acceptable (registry HTTP, dashboard
   cluster-admin…), il **paraphrase** un ADR existant
   ([0011](0011-registry-http-sans-auth.md),
   [0010](0010-dashboard-cluster-admin.md)…). Le _pourquoi_ appartient aux ADR
   (immuables) ; l'audit ne devrait que **renvoyer**.

Pourtant l'audit occupe une **case réelle que rien d'autre ne couvre** : il
**mesure l'écart à un standard** et **note** (pédagogie néophyte 2/5, sécurité
3,2/5…). Ni un ADR (le _pourquoi_, immuable), ni un plan (le _comment_ d'une
décision), ni une issue (une _unité de travail_), ni `RESULTS.md` (ce qui a
_tourné_) ne fait cela. La question n'est donc **pas** « l'audit est-il
redondant ? » (il ne l'est pas) mais « **quelle forme** lui donner pour qu'il
cesse de périmer et de paraphraser les ADR ? ».

L'[ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) a posé le **test
de temporalité** (immuable → ADR ; évolutif → plan ; fermable → issue). Appliqué
aux composants de l'audit, il **range** chaque morceau :

| Composant de l'audit                          | Temporalité      | Devrait vivre comme…             |
| --------------------------------------------- | ---------------- | -------------------------------- |
| La **grille** (dimensions, critères, méthode) | stable           | un document permanent            |
| Les **notes /5** (mesure à un instant)        | photo périssable | un **passage daté**              |
| Les **manques constatés** (« il manque X »)   | travail fermable | des **issues**                   |
| Les **pourquoi** des choix                    | immuable         | **déjà dans les ADR** → renvoyer |

## Décision

**L'audit se sépare en une GRILLE permanente (dimensions + critères + méthode,
qui ne périme pas) et des PASSAGES datés (les notes /5 à une date, comme
`RESULTS.md`). Un passage RENVOIE aux ADR pour les _pourquoi_ (il ne les
paraphrase pas) et ses manques deviennent des ISSUES.** Même pattern que les
preuves de banc
([ADR 0042](0042-fraicheur-preuves-banc.md)/[0052](0052-reproductibilite-des-resultats.md))
et que les plans ([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)) :
**ce qui mesure un état est daté, ce qui définit un cadre est permanent.**

### 1. La grille (permanente)

Un document stable décrit **les dimensions auditées** (les 12 axes actuels),
**les critères** de chaque dimension, et **la méthode** (chaîne qualité
exécutée + relecture adversariale). La grille **ne porte aucune note** — elle
dit _quoi_ mesurer et _comment_, pas _où on en est_. Elle évolue rarement (ajout
d'une dimension), comme un ADR évolue (superseded), pas comme une photo.

### 2. Les passages (datés, append-only)

Un **passage d'audit** est l'application de la grille à une date : `AAAA-MM-JJ`,
les notes /5 par dimension, les constats. **Daté dans son titre / en-tête** (pas
seulement une mention enfouie), il ne prétend jamais être « l'état courant » :
il est « l'état **au** 2026-05-29 ». Les passages s'**empilent** (on garde
l'historique, comme `RESULTS.md` ou un ADR superseded reste lisible) — on voit
ainsi l'évolution des notes dans le temps, ce qu'un document écrasé perdrait.

### 3. Renvoyer aux ADR, ne pas les paraphraser

Un passage qui touche un choix tracé **cite l'ADR** (« registry HTTP : choix
assumé, cf. [ADR 0011](0011-registry-http-sans-auth.md) ») au lieu de ré-exposer
le raisonnement. Le _pourquoi_ a **un** propriétaire (l'ADR, immuable) ; l'audit
**mesure**, il ne **décide** ni ne **justifie**.

### 4. Les manques deviennent des issues

Un constat d'audit actionnable (« il manque un `SECURITY.md` », « la pédagogie
néophyte est faible ») est une **unité de travail fermable** → une **issue**
([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)). Le passage
**liste et lie** ces issues ; il ne les remplace pas. Un audit qui n'est qu'un
constat sans issue est un constat qui meurt avec son document.

### 5. Le passage actuel (2026-05-29) est historisé

Les 13 documents existants sont le **premier passage**, daté — honnête à cette
date, **non réactualisé**. On ne les réécrit pas (honnêteté de l'historique,
comme on ne réécrit pas `RESULTS.md`) : on les **marque** comme passage du
2026-05-29 et on les range sous la nouvelle structure. Un futur passage produira
de nouvelles notes, sans écraser celui-ci.

## Statut

Accepted (2026-06-12 ; promu de Proposed le 2026-06-13). Sœur de
[ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) (gouvernance
documentaire) ; applique aux audits le pattern grille/passage daté déjà acté
pour les preuves de banc ([ADR 0042](0042-fraicheur-preuves-banc.md)) et la
reproductibilité ([ADR 0052](0052-reproductibilite-des-resultats.md)).
N'invalide pas l'audit existant ; impose de le **restructurer** (grille
extraite, passage daté, manques → issues) — cf. Conséquences.

## Conséquences

- **L'audit cesse de périmer en se présentant comme un présent** : un passage
  est daté par construction, un futur passage ne l'écrase pas. On gagne
  l'**historique des notes** (tendance qualité dans le temps).
- **Fin de la paraphrase des ADR** : l'audit renvoie, les _pourquoi_ restent aux
  ADR.
- **Les manques sont exécutables** : ils deviennent des issues liées, pas des
  constats orphelins.
- **Travail d'application** (tracé par une issue,
  [ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)) :
  - extraire une **grille** permanente (dimensions + critères + méthode) du
    README et des 12 docs ;
  - **dater** le passage existant (`docs/audit/2026-05-29/` ou en-tête de
    passage) ;
  - convertir les constats actionnables du `12-plan-action` en **issues** liées
    ;
  - remplacer les paraphrases de _pourquoi_ par des **renvois ADR**.
- **Prix à payer** : une restructuration (les 13 docs sont denses) ; un futur
  audit demande de **re-jouer** la grille (coût d'un passage) — mais c'est le
  prix de la vérité, et c'est ce que le dépôt assume déjà pour les bancs
  ([ADR 0034](0034-validation-e2e-from-scratch.md)).
- **Cadence des passages** : un passage se déclenche sur **événement** (jalon
  majeur : install prod, refonte) ou **échéance** ; pas de re-notation continue.
  À l'image de la fraîcheur des preuves de banc
  ([ADR 0042](0042-fraicheur-preuves-banc.md)), un garde-fou pourra signaler un
  passage trop ancien — hors scope de cet ADR.

## Alternatives écartées

- **Supprimer `docs/audit/`** (les ADR suffisent). Faux : aucun ADR ne **note**
  ni ne **mesure l'écart à un standard** (pédagogie, couverture, manques OSS).
  On perdrait la seule vue « où en est la qualité ». La case existe.
- **Laisser tel quel.** Le statu quo : un audit figé du 29 mai qui se lit comme
  un présent → faux, et qui paraphrase des ADR → redondant. C'est précisément ce
  qu'on corrige.
- **Re-jouer l'audit maintenant** (réactualiser les 13 docs). Utile (un passage
  frais), mais **orthogonal** à la doctrine : sans la séparation grille/passage,
  le nouvel audit re-périmera de la même façon. On pose d'abord la forme (cet
  ADR) ; re-jouer est ensuite **un passage**, quand un jalon le justifie.
- **Fusionner l'audit dans les ADR** (un « ADR qualité »). Casse l'immuabilité :
  une note /5 évolue, un ADR non. C'est exactement la dérive « l'ADR avale le
  mesuré », symétrique de celle qu'a corrigée
  [ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md).
