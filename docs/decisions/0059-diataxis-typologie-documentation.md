# 0059 — Diátaxis : typologie des quatre modes de documentation + câblage inline

## Contexte

La documentation du dépôt a atteint une **taille critique** : plus de 50 ADR,
une douzaine de vues d'architecture, des audits, des RUNBOOK colocalisés au
code, un glossaire, des pages développeur. Elle est de très bonne qualité
**technique**, mais l'audit documentation
([04-documentation.md](../audit/2026-05-29/04-documentation.md)) a noté la
**pédagogie néophyte 2/5** : le jargon est employé avant d'être défini, et il
manquait un **récit d'entrée** qui raconte le projet de bout en bout. L'**action
n° 1** de cet audit était précise : « créer un glossaire et **lier chaque
premier usage d'un terme vers son ancre** ». Le [glossaire](../glossaire.md)
existe désormais, mais le **câblage** des termes au fil de la prose reste
partiel.

L'[ADR 0029](0029-markdown-atteignable-doc.md) garantit qu'une page est
**atteignable** (chaîne de navigation, contrôle par
[`scripts/check_md_orphans.py`](../../scripts/check_md_orphans.py)) — mais elle
ne dit rien de sa **fonction**. Une page peut être atteignable et pourtant
mélanger explication, tutoriel et référence, ce qui désoriente le néophyte que
ce dépôt vise explicitement. **Atteignabilité ≠ typologie.**

Sans cadre, les pages **dérivent** : un récit recopie les définitions du
glossaire, un RUNBOOK se met à expliquer le _pourquoi_ qui relève d'un ADR, une
page d'accueil tente d'être à la fois tutoriel et référence. Le coût est double
: la **redite** (plusieurs sources de vérité à maintenir en parallèle, qui
divergent) et la **perte du lecteur** (il ne sait plus où chercher quoi).
[Diátaxis](https://diataxis.fr/) est le cadre établi qui nomme ce problème et le
résout en distinguant quatre besoins de lecture.

## Décision

**On adopte Diátaxis comme typologie des pages de documentation.** Chaque page
sert **un** des quatre besoins de lecture, et le lien entre pages se fait par
**câblage Markdown inline** dirigé par l'intention, jamais par recopie ni par
navigation systématique.

### 1. Les quatre modes et leur incarnation dans le dépôt

| Mode Diátaxis | Besoin du lecteur           | Page(s) du dépôt                                                            |
| ------------- | --------------------------- | --------------------------------------------------------------------------- |
| Tutorial      | apprendre en faisant        | [demarrage.md](../demarrage.md) (parcours 1→5)                              |
| How-to        | accomplir une tâche précise | RUNBOOK (`bootstrap/`, `storage/ceph/`), guides opératoires                 |
| Reference     | vérifier un terme, un fait  | [glossaire.md](../glossaire.md), [`contract/`](../../contract/)             |
| Explanation   | comprendre le pourquoi      | [manifeste.md](../manifeste.md), [composants.md](../composants.md), les ADR |

### 2. Une page = un mode dominant

On ne mélange pas tutoriel et référence dans la même page : on **câble** vers la
page de l'autre mode. Le **mode est une propriété de la page** (il guide
l'auteur) ; il n'est **pas affiché** au lecteur sous forme de badge — aucune
étiquette « explication / procédure » en tête de fichier.

### 3. Le manifeste est l'explanation-chapeau

[`manifeste.md`](../manifeste.md) raconte la trajectoire d'ingénierie (contexte
→ données → méthode → voyage → résultats) et **câble** vers les autres modes ;
il ne **recopie** ni le glossaire (reference) ni les RUNBOOK (how-to). C'est le
seul nœud qui rayonne largement — son rôle d'explication d'ensemble le justifie.

### 4. Câblage par lien Markdown standard

Le premier usage d'un terme technique **par section** est **un lien Markdown
ordinaire** vers sa cible (glossaire / ADR / composants / RUNBOOK) :
`[mot-clé](cible)`. **Markdown pur** (pas de composant Vue, pas de HTML, pas de
symbole décoratif), pour rendre identiquement sur GitHub et sur le site
VitePress. Ce câblage **achève l'action n° 1** de l'audit 04.

### 5. Liens dirigés par l'intention, jamais par complétude

On ne met **pas** de bandeau « voir aussi : les trois autres modes » en pied de
page — ce réflexe re-fusionne ce que Diátaxis sépare, alourdit, et ne sert
personne. On lie vers le mode où le lecteur voudra aller **ensuite**, compte
tenu de ce qu'il fait. Les transitions naturelles sont **asymétriques** :

| Depuis (mode)                | Lie vers…                                          | Pas vers (en bloc) |
| ---------------------------- | -------------------------------------------------- | ------------------ |
| Explanation (manifeste, ADR) | reference (glossaire), explanation (autre ADR)     | tutorial / how-to  |
| Tutorial (demarrage)         | how-to (RUNBOOK), pour l'étape suivante            | explanation        |
| How-to (RUNBOOK)             | reference (glossaire), explanation si choix subtil | tutorial           |
| Reference (glossaire)        | explanation (l'ADR du choix)                       | tutorial / how-to  |

Le dépôt suit déjà cet instinct (le glossaire renvoie aux ADR ; le démarrage
enchaîne vers les RUNBOOK) ; cet ADR le **formalise**.

### 6. Articulation avec l'ADR 0029

[L'ADR 0029](0029-markdown-atteignable-doc.md) régit l'**atteignabilité** (toute
page est reliée au graphe de navigation ; contrôle automatique bloquant). Le
présent ADR régit la **typologie** (quel mode, et le câblage dirigé qui relie
les modes). Les deux sont **complémentaires et non redondants** : 0029 dit «
aucune page orpheline », 0059 dit « chaque page a une fonction claire et renvoie
aux autres modes par lien dirigé plutôt que par copie ». Cet ADR **n'ajoute
pas** de nouveau garde-fou exécutable : le câblage reste vérifié indirectement
par le build VitePress (liens et ancres morts) et par `check_md_orphans.py`
(atteignabilité).

## Statut

Accepted (2026-06-11).

## Conséquences

- **Gain** : le néophyte sait où chercher (un mode = un besoin) ; **une seule
  source de vérité par fait** (la redite disparaît) ; le récit d'entrée comble
  le trou pédagogique relevé par l'audit 04.
- **Prix à payer** : une **discipline de rédaction** (ne pas recopier, câbler) ;
  le choix du terme à lier reste un acte humain, **non automatisable à 100 %**.
- **Garde-fous existants suffisants** : le build VitePress casse sur lien ou
  ancre mort ; `check_md_orphans.py` casse sur orphelin
  ([ADR 0029](0029-markdown-atteignable-doc.md)). Pas de nouveau contrôle à
  écrire.
- **Achève l'action n° 1** de
  l'[audit documentation](../audit/2026-05-29/04-documentation.md) (glossaire +
  câblage des premiers usages).

## Alternatives écartées

**Inliner le glossaire dans le récit.** Écarté : redite et double maintenance ;
casse la fonction _reference_ autonome (on ne grep pas un terme dans un récit
linéaire). Un lien vers le glossaire rend l'inlining inutile.

**Tout mettre dans un README long.** Écarté : mélange les quatre modes dans une
seule page ; le README doit rester **court** (porte d'entrée GitHub), le récit
vit dans `manifeste.md`.

**Navigation inter-modes systématique / badge de mode par page.** Écarté :
cargo-cult de Diátaxis — re-fusionne ce que le cadre sépare, alourdit chaque
page, et n'aide pas le lecteur. Le mode guide l'auteur, pas le lecteur.

**Composant Vue pour les liens (tooltip au survol) ou glyphe décoratif accolé au
lien.** Écarté : ne rend pas sur GitHub (HTML brut visible / glyphe parasite) ;
viole la portabilité Markdown pur exigée. Un lien Markdown standard suffit.

## Amendement 2026-06-20 — préciser le mode « Tutorial »

La table §1 listait `demarrage.md` comme **le** tutoriel (« parcours 1→5 »).
Précision après revue Diátaxis : `demarrage.md` est en réalité une **page
d'orientation/aiguillage** (ses 5 étapes n'exécutent aucune commande, ce sont
des renvois), tandis que le **vrai tutoriel learn-by-doing est
[`banc-local.md`](../banc-local.md)** (monter le banc Lima de zéro, commandes +
résultats vérifiables, environnement jetable). La décision (typologie Diátaxis,
un mode par page, câblage dirigé) est **inchangée** ; seule la classification de
ces deux pages est corrigée — `demarrage.md` reste l'index d'entrée qui
**câble** vers le tutoriel `banc-local.md`. `docs/README.md` (colonne « Mode »)
est aligné en conséquence.
