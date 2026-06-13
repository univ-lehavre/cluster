# 0057 — Gouvernance documentaire : un ADR décide, un plan met en œuvre, une issue exécute

## Contexte

Le dépôt a un appareil de pilotage riche : **56 ADR**, des **plans**
(`docs/plans/`), des **audits** (`docs/audit/`), des **issues** GitHub, des
**PR**. Le cadre est posé ([CONTRIBUTING.md](../../CONTRIBUTING.md) «
Traçabilité », `docs/plans/README.md`) et bon sur le papier — « trois natures
d'écrits, aucun ne remplace l'autre ». Mais à mesure que le volume monte,
**trois frontières dérivent en pratique**, et la plus nette est : **l'ADR «
avale » le plan.**

Constat sur pièce (auto-critique) :

- **[ADR 0056](0056-modele-declaratif-topologies.md)** contient une **§9 «
  Paliers de réalisation » P0-P8** (un tableau d'implémentation ordonnée) et une
  **§8 « Portée visée »** (13 exigences). Or un ADR est **immuable** ; ces
  paliers vont **évoluer** (on en réordonnera, on en cochera). Mettre un plan
  évolutif dans un document immuable est une **contradiction de nature**.
- **[ADR 0055](0055-ha-3cp-hyperconverge-promotion-in-place.md)** embarque de
  même une checklist d'implémentation.

**Cause structurelle** (pas un accident) : quand on raisonne en continu, il est
_commode_ de tout mettre au même endroit — la décision ET son déroulé. La règle
existante (« un plan met en œuvre une décision, la référence en en-tête »)
demande de **scinder** au moment où on en a le moins envie. Sans règle
**immuable** ni **obligation**, la discipline cède sous le flux. Les principes
sont aujourd'hui dispersés (CONTRIBUTING + README), donc **rien d'immuable** ne
cadre la dérive — et un méta-cadre documentaire mérite lui-même un ADR.

Deux faiblesses corollaires du dispositif actuel des plans :

- Le **nommage est chronologique** (`AAAA-MM-JJ-sujet`) → il encourage des plans
  **de session** (photos datées) plutôt que des plans **thématiques qui vivent**
  le temps d'une mise en œuvre.
- Le plan ne **trace pas son avancement** : pas de lien systématique vers les
  **issues créées** ni d'**état d'achèvement** (quels paliers faits). Le «
  Journal d'exécution » renvoie aux audits de session, pas aux issues/paliers.

## Décision

**Quatre artefacts, quatre rôles non chevauchants, et une règle qui interdit la
dérive : un ADR DÉCIDE (immuable), un plan MET EN ŒUVRE (vivant), une issue
EXÉCUTE (fermable), une PR LIVRE (et ferme/coche).**

### 1. Frontière par temporalité (le test de découpe)

Le critère qui range un contenu est sa **temporalité** :

| Va dans…  | si le contenu est…                   | test                                                 |
| --------- | ------------------------------------ | ---------------------------------------------------- |
| **ADR**   | **immuable** (un choix, un pourquoi) | « est-ce encore vrai dans 2 ans, sauf superseded ? » |
| **Plan**  | **un ordre de marche qui évoluera**  | « vais-je réordonner / cocher ça ? »                 |
| **Issue** | **une unité de travail fermable**    | « est-ce que ça se ferme un jour ? »                 |
| **PR**    | **un changement + sa preuve**        | « est-ce que ça merge ? »                            |

Appliqué à [ADR 0056](0056-modele-declaratif-topologies.md) §9 : « vais-je
réordonner P0-P8 ? » → **oui** → c'est un **plan**, pas un ADR.

### 2. Un ADR avec mise en œuvre ⇒ un plan dédié OBLIGATOIRE (relation 1:1)

- Dès qu'un ADR implique un **travail échelonné** (paliers, tâches, checklist),
  il a **UN plan dédié** — séparé, **jamais dans l'ADR**.
- Un ADR **purement conceptuel** (doctrine sans mise en œuvre échelonnée, ex.
  [ADR 0023](0023-plateforme-exemple-generique.md),
  [ADR 0052](0052-reproductibilite-des-resultats.md)) peut n'avoir **aucun**
  plan.
- **Interdit dans un ADR** : tableau de paliers, checklist d'implémentation, «
  TODO », ordre de réalisation. L'ADR porte la **décision** et ses
  **conséquences** (ce qui découle, immuable) ; le **déroulé** (qui évolue) sort
  dans le plan.
- L'ADR peut **nommer** son plan en conséquence (« mise en œuvre : voir le plan
  `<thème>` ») ; le plan **référence l'ADR qui le fonde** en en-tête (règle
  existante conservée).

### 3. Plans THÉMATIQUES et VIVANTS, avec un état et une section « Suivi »

- **Nommage thématique**, lié à la décision, pas daté : `plan-<thème>.md` (ex.
  `plan-modele-declaratif.md`, `plan-ha-3cp.md`). Le plan **vit** tant que la
  décision se met en œuvre ; il n'est pas une photo de session.
- **En-tête `## État` OBLIGATOIRE** — un champ de **premier niveau**, comme
  l'ADR a son `## Statut`. Un coup d'œil suffit à savoir où en est la mise en
  œuvre, sans lire tout le Suivi. Valeurs normées **datées** :

  | État          | Sens                                                                                                                   |
  | ------------- | ---------------------------------------------------------------------------------------------------------------------- |
  | **Brouillon** | rédigé mais non engagé ; typiquement l'ADR fondateur est encore `Proposed` (cf. §6) → **pas d'implémentation** active. |
  | **Actif**     | mise en œuvre en cours ; l'ADR fondateur est `Accepted` ; des issues/PR avancent les paliers.                          |
  | **Achevé**    | tous les paliers faits et prouvés ; reste versionné comme trace.                                                       |
  | **Abandonné** | mise en œuvre arrêtée (décision révisée / superseded) ; conservé pour l'historique.                                    |

  Forme en en-tête :
  `> **État : Actif** (depuis AAAA-MM-JJ) · **Fonde : ADR NNNN** · **Issues : #N…**`.

- **Section « Suivi » obligatoire** — le plan est le **tableau de bord** de la
  décision, ce que ni l'ADR (immuable) ni l'issue (atomique) ne peuvent être :
  - les **paliers** (cases à cocher, l'ordre de marche évolutif) ;
  - les **issues rattachées** (liens `#NNN`) et leur état — qu'elles soient
    **créées depuis le plan** OU **préexistantes adoptées** : un plan formalisé
    après coup (extraction de paliers d'un ADR, cadrage tardif) **embarque les
    issues en cours** qui le réalisent déjà (ex. #250 pour `ha-3cp`, #274 pour
    le rollback) au lieu d'en ouvrir de nouvelles. Le plan **agrège**, il ne
    duplique pas ;
  - un renvoi aux **runs de preuve** (`RESULTS.md`) qui valident un palier
    ([ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md)).
- L'**état d'achèvement global** vit dans l'en-tête `## État` (ci-dessus), pas
  enfoui dans le Suivi. Quand tous les paliers sont faits et prouvés, l'en-tête
  passe **Achevé** (le plan reste versionné comme trace, comme un ADR superseded
  reste lisible).

### 4. Distinguer plan vivant et audit de session

`docs/plans/` mélange aujourd'hui deux natures ; on les distingue explicitement
:

- **Plan** (thématique, vivant, 1 par ADR-mise-en-œuvre, section « Suivi ») —
  `plan-<thème>.md`.
- **Audit de session** (daté, **figé** : le journal d'un moment — réalignement
  de branche, dette constatée) — `AAAA-MM-JJ-audit-<sujet>.md`. Reste daté car
  c'est une **photo assumée**, pas un tableau de bord.

### 5. Le chaînage ADR ↔ plan ↔ issue ↔ PR

- **ADR** → référence son **plan** (si mise en œuvre) ; **plan** → référence
  l'**ADR** fondateur + les **issues** créées ; **issue** → référence l'ADR/plan
  qui la motive ; **PR** → référence l'**issue** qu'elle ferme / le palier
  qu'elle coche.
- Le **plan est le pivot** du suivi : c'est lui qui agrège « où en est la mise
  en œuvre de cette décision », plutôt qu'un chaînage à reconstituer à la main.

### 6. Cycle de vie de l'ADR — `Proposed` n'autorise pas l'implémentation

Le statut de l'ADR **gouverne** ce que le plan a le droit de faire. La règle :
**on n'implémente (plan `Actif` + PR de code) qu'à partir d'un ADR `Accepted`.**

| Statut ADR     | Plan autorisé                            | Code (PR) autorisé           |
| -------------- | ---------------------------------------- | ---------------------------- |
| **Proposed**   | `Brouillon` (cadrage, paliers esquissés) | **Non** — décision pas figée |
| **Accepted**   | `Actif` (paliers déroulés, issues, PR)   | **Oui**                      |
| **Superseded** | plan basculé `Abandonné` ou réécrit      | (selon l'ADR successeur)     |
| **Deprecated** | plan `Abandonné`                         | non                          |

Raison : un ADR `Proposed` peut encore être **réécrit ou rejeté** ; investir du
code dessus, c'est risquer de jeter le travail (ou pire, figer dans le code une
décision que l'ADR n'a pas actée). Acter d'abord (`Accepted`), implémenter
ensuite. Le **passage `Accepted`** est précisément le signal qui fait passer le
plan de `Brouillon` à `Actif`.

**Exception bornée** : un **prototype jetable** (spike, `test/spikes/`) peut
précéder l'acceptation pour _éclairer_ la décision — mais il ne s'agit pas d'une
mise en œuvre du plan (pas de PR sur le chemin de production, pas de palier
coché). Le spike informe l'ADR ; il ne l'implémente pas.

## Statut

Accepted (2026-06-12 ; amendé 2026-06-13 : ajout du cycle de vie de l'ADR §6 et
de l'en-tête `## État` du plan §3). **Précise et durcit**
[CONTRIBUTING.md](../../CONTRIBUTING.md) (section « Traçabilité ») et
`docs/plans/README.md` (qui suggéraient la relation ADR↔plan sans l'imposer ni
tracer l'avancement). N'invalide aucun ADR ; impose en revanche d'**extraire**
les paliers/checklists des ADR [0056](0056-modele-declaratif-topologies.md) et
[0055](0055-ha-3cp-hyperconverge-promotion-in-place.md) vers leurs plans dédiés
(cf. Conséquences). Le sort de [`docs/audit/`](../audit/) (péremption,
recoupement avec les ADR) est un **chantier distinct**, non tranché ici.

## Conséquences

- **Rôles non chevauchants** : l'ADR cesse de grossir (il décide), le plan porte
  le vivant (paliers + suivi), l'issue exécute, la PR livre. La dérive « l'ADR
  avale le plan » est **interdite par construction** (pas de checklist dans un
  ADR).
- **Le plan devient le tableau de bord** d'une décision : une seule page répond
  « où en est la mise en œuvre de l'ADR X » (paliers, issues, achèvement) — ce
  qu'aucun artefact ne faisait.
- **Travail d'application immédiat** (tracé par un plan, justement) :
  - extraire [ADR 0056](0056-modele-declaratif-topologies.md) §9 (et alléger §8)
    vers `docs/plans/plan-modele-declaratif.md` ;
  - extraire la checklist de
    [ADR 0055](0055-ha-3cp-hyperconverge-promotion-in-place.md) vers le plan
    `ha-3cp` (ou l'issue #250 qui en tient déjà lieu) ;
  - amender [CONTRIBUTING.md](../../CONTRIBUTING.md) et `docs/plans/README.md`
    (nommage thématique, section « Suivi » obligatoire, relation 1:1) ;
  - poser l'en-tête **`## État`** (§3) sur les plans existants ;
  - **promouvoir les ADR `Proposed` qui ont déjà un plan/du code en `Accepted`**
    (§6) : un ADR `Proposed` ne peut pas avoir un plan `Actif` — la décision
    doit être actée pour que sa mise en œuvre soit légitime.
- **Prix à payer** : un peu plus de cérémonie (créer un plan séparé dès qu'un
  ADR a une mise en œuvre, poser l'état, acter l'ADR avant de coder) ; la
  tentation de tout mettre dans l'ADR — ou de coder sur une décision pas figée —
  demande une discipline que la règle rend non négociable.
- **Migration faite** : le nommage thématique `plan-<thème>.md` s'applique à
  **tous** les plans vivants — les plans historiquement datés ont été renommés
  (2026-06-13). Seuls les **audits de session** (§4) restent datés
  (`AAAA-MM-JJ-audit-<sujet>.md`), car un audit EST une photo d'un moment.

## Alternatives écartées

- **Ne rien formaliser (laisser dans CONTRIBUTING/README).** Le statu quo : les
  principes existent mais, **non immuables et non obligatoires**, ils dérivent
  (0055, 0056 le prouvent). Un méta-cadre documentaire qui se veut stable doit
  être un ADR.
- **Tout ADR structurant a un plan jumeau (systématique).** Plus uniforme, mais
  crée des **plans vides** pour les ADR purement conceptuels (0023, 0052…). On
  préfère le 1:1 **conditionné à l'existence d'une mise en œuvre échelonnée**.
- **Garder les paliers DANS l'ADR mais le marquer « évolutif ».** Casse
  l'immuabilité de l'ADR (un ADR ne se réécrit pas, il est superseded) — un
  contenu qui évolue n'a pas sa place dans un artefact immuable, quelle que soit
  l'étiquette.
- **Fusionner plan et issues (tout en GitHub).** Les issues sont atomiques et
  fermables ; aucune ne porte la **vue d'ensemble** d'une décision (paliers +
  ordre + achèvement). Le plan versionné garde cette vue, et survit à la
  fermeture des issues.
