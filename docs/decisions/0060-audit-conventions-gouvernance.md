# 0060 — Audit régulier du respect des conventions de gouvernance

## Contexte

Le dépôt a une gouvernance documentaire **dense et formalisée** :
[ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) (un ADR décide, un
plan met en œuvre, une issue exécute, une PR livre — avec en-tête `## État` du
plan et cycle de vie `Proposed`→`Accepted`),
[ADR 0058](0058-doctrine-audit-grille-passages.md) (audit = grille + passages
datés ; registre des drifts, `ouvert` ⇒ issue liée),
[ADR 0029](0029-markdown-atteignable-doc.md) (Markdown atteignable),
[ADR 0023](0023-plateforme-exemple-generique.md) (valeurs génériques).

Ces règles sont **vérifiées à la main** aujourd'hui — et c'est leur faiblesse.
Une revue manuelle (celle qui a produit cet ADR) a révélé des dérives réelles :
un plan sans section « Suivi », un plan qui ne pointait pas son issue, des ADR
`Proposed` portant déjà du code mergé, des plans au nommage daté obsolète, un
drift `ouvert` sans issue. **Aucun garde-fou exécutable ne mesure le respect des
conventions** : une dérive ne se voit qu'à la prochaine revue humaine, qui est
épisodique. Une gouvernance qui ne s'auto-vérifie pas **périme en silence**,
exactement le travers que l'ADR 0058 reproche à un audit figé.

Symétriquement, cette gouvernance est **invisible** : 59 ADR, 57 drifts indexés,
29 scénarios E2E, 0 % de duplication shell — des chiffres qui prouvent la
rigueur mais que **rien n'affiche**. La preuve existe sans être montrée.

## Décision

**Un audit AUTOMATIQUE et RÉGULIER vérifie le respect des conventions de
gouvernance et la fraîcheur des traces, via un script versionné lancé par un
cron NON BLOQUANT qui consigne les manquements dans une issue dédiée.** Le même
script produit les **statistiques de gouvernance** affichées dans la doc.

### 1. Ce que l'audit vérifie

Quatre familles de contrôles, sur le code seul (pas d'état distant) :

1. **Conformité ADR ↔ plan ↔ issue ↔ drift** (ADR 0057/0058) :
   - tout **plan** vivant (`plan-*.md`) porte un en-tête `## État` (valeur
     normée) ET une section « Suivi » ET référence son ADR fondateur ;
   - aucun **ADR** ne contient de checklist/paliers d'implémentation (interdit
     §2 ADR 0057 — heuristique : tableau de paliers `P0`/lot dans un ADR) ;
   - tout **drift** `ouvert`/`en-cours` porte un champ `issue:` non vide et ≠
     `TODO` (ADR 0058 §6) ;
   - aucun **ADR `Proposed`** n'a un plan `Actif` ni de code le réalisant (cycle
     de vie ADR 0057 §6) — signalé, pas bloquant.
2. **Cohérence des index** :
   - `decisions/README.md` liste **tous** les fichiers ADR, sans trou ni doublon
     de numéro, et les statuts de l'index **concordent** avec les fichiers ;
   - `plans/README.md` liste tous les `plan-*.md`.
3. **Fraîcheur des traces** (ADR 0058) :
   - le **passage d'audit** le plus récent (`docs/audit/AAAA-MM-JJ/`) n'a pas
     dépassé un seuil (défaut **180 j**) — au-delà, un passage est dû ;
   - (la fraîcheur des **preuves de banc** reste couverte par
     `bench-freshness.yml`, [ADR 0042](0042-fraicheur-preuves-banc.md) — non
     redupliquée ici).
4. **Statistiques de gouvernance** : compter ADR (par statut), plans (par état),
   drifts (par statut), scénarios E2E, libs factorisées — pour les **afficher**
   (voir §3).

### 2. Comment il s'exécute — cron non bloquant

- **Script versionné** Python (`scripts/check_gouvernance.py`,
  [ADR 0017](0017-langage-des-scripts.md)/[0049](0049-doctrine-choix-outil-par-action.md)
  : parsing YAML/Markdown + logique de cohérence = non trivial → Python testé,
  pas bash). Logique pure testée par `tests/test_check_gouvernance.py`.
- **NON bloquant en CI** : on ne **bloque pas** une PR sur une convention de
  gouvernance (une dérive documentaire ne casse pas le produit, et bloquer
  frictionne au mauvais moment). Le script tourne en **cron hebdomadaire**
  (`.github/workflows/conventions-freshness.yml`) ; s'il trouve des manquements,
  il **ouvre/met à jour UNE issue récapitulative** dédoublonnée par **label**
  (`audit-conventions`), exactement comme `bench-freshness.yml` (l'unicité par
  label, pas par titre — leçon des doublons #273/#288).
- **Lançable à la main** : `pnpm check:gouvernance` (rapport local) et
  `workflow_dispatch`. Le rapport est **lisible** (liste les manquements par
  famille) — pas un simple code de sortie.

### 3. Les statistiques deviennent visibles

Le script émet un bloc « le dépôt en chiffres » (ADR par statut, plans, drifts,
scénarios, duplication). Ce bloc est **affiché dans la doc** (README /
manifeste) comme **preuve** de la rigueur de gouvernance — régénérable, donc
jamais périmé à la main. La mise en valeur n'est pas cosmétique : elle rend la
gouvernance **lisible** pour un néophyte
([ADR 0059](0059-diataxis-typologie-documentation.md) : le manifeste explique ;
ces chiffres l'étayent).

## Statut

Accepted (2026-06-13).

## Conséquences

- **La gouvernance s'auto-vérifie** : une dérive (plan sans `## État`, drift
  ouvert sans issue, index incohérent, passage d'audit périmé) est **détectée
  automatiquement**, plus seulement à la revue humaine épisodique. Le travers «
  périmer en silence » que l'ADR 0058 combat pour l'audit est neutralisé pour
  les conventions elles-mêmes.
- **Non bloquant = pas de friction** : une PR n'est jamais bloquée sur une règle
  documentaire ; le cron signale, l'humain corrige. Cohérent avec ADR 0042 §1 («
  signaler, ne pas bloquer ») pour les traces empiriques.
- **La preuve devient visible** : les chiffres de gouvernance, jusqu'ici tus,
  sont affichés et régénérés — mise en valeur factuelle, pas déclarative.
- **Prix à payer** : un script à maintenir quand les conventions évoluent (ses
  heuristiques — « qu'est-ce qu'une checklist dans un ADR » — sont
  approximatives par nature ; il signale, il ne juge pas à la place de
  l'humain). Les faux-positifs sont tolérés (non bloquant) et affinés dans le
  temps.
- **Plan de mise en œuvre** : ce travail (script + tests + workflow + bloc
  stats) est déroulé par
  [`plan-audit-conventions.md`](../plans/plan-audit-conventions.md) (ADR 0057 :
  un ADR avec mise en œuvre échelonnée a un plan dédié).

## Alternatives écartées

- **Check bloquant en CI.** Écarté : bloquer une PR sur une convention de
  gouvernance frictionne (un contributeur corrige un bug et se voit refuser pour
  un plan sans `## État` sans rapport). Les conventions documentaires se
  rattrapent à froid ; le produit, lui, a des checks bloquants (lint, banc).
- **Revue humaine seule (statu quo).** Écarté : épisodique, donc les dérives
  s'accumulent entre deux revues (prouvé par cette revue-ci). Un garde-fou
  exécutable régulier est ce qui manque.
- **Tout en bash.** Écarté : parser le front-matter/statut des 59 ADR, croiser
  index ↔ fichiers, valider le YAML des drifts = logique de cohérence non
  triviale → Python testé
  ([ADR 0017](0017-langage-des-scripts.md)/[0049](0049-doctrine-choix-outil-par-action.md)).
- **Un dashboard externe (CI badge, service tiers).** Écarté : dépendance
  externe pour une donnée que le dépôt produit lui-même ; le bloc stats
  versionné suffit et reste sous contrôle (ADR 0023, souveraineté de
  l'outillage).
