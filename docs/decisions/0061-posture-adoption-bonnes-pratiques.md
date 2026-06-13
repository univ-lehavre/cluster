# 0061 — Posture d'adoption des bonnes pratiques (principe-chapeau)

## Contexte

Ce dépôt adopte des bonnes pratiques **en continu** — discipline ADR, registre
des drifts, gel de versions, factorisation, épinglage par SHA, vérification de
fraîcheur, doctrine documentaire… Chacune a été adoptée parce qu'elle améliorait
le tout. Mais la **posture générale** face à une bonne pratique nouvelle n'est
**nulle part décidée** : adopte-t-on par défaut (biais adoptif), ou résiste-t-on
par défaut (biais conservateur, « ça marche, ne touchons à rien ») ?

Sans posture explicite, deux travers symétriques guettent :

- **Conservatisme par inertie** : refuser une amélioration réelle parce que
  l'adopter demande un effort, ou « parce qu'on a toujours fait comme ça ». Le
  dépôt stagne sous le poids de l'existant.
- **Adoption compulsive** : empiler des pratiques/outils « parce que c'est bien
  » sans mesurer le coût de la diversité, jusqu'à un dépôt incohérent (le
  travers que l'[ADR 0049](0049-doctrine-choix-outil-par-action.md) combat déjà
  pour les _outils_).

Le risque le plus subtil est qu'un principe « adopter ce qui est bien » serve de
**blanc-seing** : « c'est une bonne pratique, donc je l'adopte » — en
**court-circuitant** la délibération ADR (contexte, alternative, conséquences)
qui fait précisément la rigueur du dépôt. Un principe d'adoption mal écrit
**affaiblirait** la gouvernance au lieu de la servir.

## Décision

**Le dépôt a un BIAIS ADOPTIF, borné par trois garde-fous. Par défaut, une bonne
pratique éprouvée est adoptée ; mais l'adoption n'est ni automatique ni
dispensée de traçabilité.**

Une bonne pratique candidate est adoptée **si et seulement si** :

1. **Elle ne contredit aucun ADR `Accepted`.** Le test de non-conflit est
   premier : une pratique qui heurte une décision en vigueur n'est PAS adoptée
   sur ce seul motif — elle exige d'abord de **superseder** l'ADR concerné (par
   un nouvel ADR qui assume le revirement). On n'empile pas une pratique contre
   une décision tenue ; on révise la décision, explicitement, ou on renonce.
2. **Son gain dépasse le coût de la diversité.** Reprise directe du critère
   d'[ADR 0049](0049-doctrine-choix-outil-par-action.md) (cohérence de
   l'existant, maîtrise, toolchain, lint, CI) : une pratique légèrement
   meilleure mais qui fragmente l'ensemble (un 6ᵉ langage, un 2ᵉ formateur, une
   convention parallèle) peut **coûter plus qu'elle ne rapporte**. Le bénéfice
   doit être réel et net, pas théorique.
3. **Si elle est structurante, elle est tracée par un ADR.** Le principe
   **n'autorise pas** à adopter une pratique structurante sans la décider
   ([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)). Le biais
   adoptif **incline la réponse** (« oui, sauf raison de ne pas »), il ne
   **remplace pas** la décision. Une pratique mineure et locale (un idiome, un
   refactor) s'adopte sans cérémonie ; une pratique qui change une norme du
   dépôt passe par un ADR — où ce principe joue comme **défaut argumenté**, pas
   comme dispense.

Mnémonique : **adopter par défaut, mais ne jamais adopter CONTRE une décision ni
SANS la tracer si elle est structurante.**

## Portée — « documentation, code, normes, etc. »

Le principe vaut pour **toutes** les natures de pratique :

- **Code/outillage** : nouvel outil, idiome, motif d'architecture — arbitré
  aussi par [ADR 0049](0049-doctrine-choix-outil-par-action.md) (qui en est le
  cas particulier « outil par action »).
- **Documentation** : convention de rédaction, structure
  ([Diátaxis, ADR 0059](0059-diataxis-typologie-documentation.md)), gouvernance
  ([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)).
- **Normes/process** : standards externes (FAIR, reproductibilité,
  supply-chain), conventions de commit, garde-fous CI.

Dans tous les cas, les trois conditions ci-dessus s'appliquent
**identiquement**.

## Statut

Accepted (2026-06-13). **Principe-chapeau** : il ne remplace ni n'invalide aucun
ADR ; il **nomme la posture** que le dépôt suivait déjà de fait, et la **borne**
pour qu'elle ne dégénère pas en blanc-seing. Cas particuliers déjà décidés :
[ADR 0049](0049-doctrine-choix-outil-par-action.md) (outils),
[ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) (gouvernance
documentaire), [ADR 0052](0052-reproductibilite-des-resultats.md)
(reproductibilité). Sœur de ces principes-chapeaux.

## Conséquences

- **Une posture nommée** : face à une bonne pratique nouvelle, la réponse par
  défaut est « oui » — ce qui débloque l'amélioration continue (le dépôt ne
  stagne pas par inertie). Mais ce « oui » est **conditionné**, donc défendable.
- **Le conflit prime sur l'engouement** : on n'adopte jamais une pratique
  **contre** un ADR `Accepted` ; on supersede d'abord, explicitement. La
  cohérence des décisions est préservée.
- **Pas de blanc-seing** : le principe **incline** sans **dispenser**. Une
  pratique structurante garde son ADR ; ce principe y figure comme **argument
  par défaut**, pas comme raccourci pour éviter de décider. La rigueur
  case-par-case (contexte/alternative/conséquences) est intacte.
- **Auto-application** : ce principe est lui-même une bonne pratique adoptée
  selon ses propres règles (ne contredit aucun ADR ; gain = lever l'ambiguïté de
  posture ; structurant donc tracé par CET ADR).
- **Inventaire visible** : le corpus des pratiques adoptées est recensé dans une
  page de référence —
  [`bonnes-pratiques.md`](../architecture/bonnes-pratiques.md) — qui renvoie à
  l'ADR fondant chaque pratique. La **conformité** à ces pratiques est vérifiée
  par `pnpm check:gouvernance`
  ([ADR 0060](0060-audit-conventions-gouvernance.md)).
- **Prix à payer** : un jugement humain reste requis (« cette pratique est-elle
  _éprouvée_ ? son gain est-il _net_ ? est-elle _structurante_ ? »). Le principe
  cadre la décision, il ne l'automatise pas — et c'est voulu (cf. le risque de
  blanc-seing).

## Alternatives écartées

- **Biais conservateur par défaut** (« ne rien adopter sans nécessité forte »).
  Écarté : le dépôt s'améliore précisément parce qu'il adopte (toute cette
  gouvernance est le fruit d'adoptions successives). Un défaut conservateur
  freinerait l'amélioration continue qui est sa force.
- **Adoption inconditionnelle** (« toute bonne pratique sans conflit est adoptée
  », sans les garde-fous). Écarté : c'est le blanc-seing — il court-circuiterait
  la délibération ADR et ouvrirait à l'empilement incohérent (cf. Contexte). Le
  principe doit **borner**, pas seulement autoriser.
- **Ne rien formaliser** (laisser la posture implicite). Écarté : l'implicite
  laisse les deux travers (inertie / compulsion) s'exprimer au gré des humeurs ;
  une posture nommée et bornée tranche une fois pour toutes — c'est exactement
  la raison d'être d'un principe-chapeau
  ([ADR 0052](0052-reproductibilite-des-resultats.md)).
- **Le fondre dans l'ADR 0049.** Écarté : 0049 traite le **choix d'outil par
  action** (un cas particulier) ; la posture d'adoption couvre **toute**
  pratique (doc, normes, process). 0061 est le chapeau, 0049 une de ses
  applications.
