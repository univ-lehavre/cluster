# 0080 — Notations externes & badges README : doctrine d'affichage

## Statut

Accepted (2026-06-16). Application directe du **biais adoptif borné**
([ADR 0061](0061-posture-adoption-bonnes-pratiques.md)) et de l'**honnêteté des
preuves** ([ADR 0052](0052-reproductibilite-des-resultats.md)) au cas
particulier des **badges de README**. Fondé par les deux passages d'audit du
2026-06-16 ([notations cyber](../audit/2026-06-16-audit-notations-cyber.md),
[notations & normes externes](../audit/2026-06-16-audit-notations-normes-externes.md)),
dont il exécute le **plan de remédiation** « rangée de badges ».

## Contexte

Les deux passages d'audit du 2026-06-16 ont confronté le dépôt à des
**référentiels externes notés ou normalisés** (OpenSSF Scorecard & Best
Practices Badge, CIS, FAIR, SemVer, Keep a Changelog, Conventional Commits,
OpenGitOps, WCAG, REUSE…). Verdict commun : le dépôt est **déjà fortement aligné
mais rarement nommé**. La finalité concrète retenue est une **rangée de badges**
au README, qui ne comptait qu'**un seul badge** (DOI Zenodo).

Mais un badge n'est pas neutre. Deux travers guettent, symétriques à ceux que
borne l'[ADR 0061](0061-posture-adoption-bonnes-pratiques.md) :

- **Le badge décoratif** — afficher « OpenSSF passing » alors que rien n'est
  câblé, « build passing » sans CI, un score figé recopié à la main. C'est le «
  badge pour le badge » : il **ment sur l'état**, et contredit frontalement
  l'honnêteté des preuves ([ADR 0052](0052-reproductibilite-des-resultats.md) :
  un résultat n'a de valeur que reproductible et vrai).
- **L'inflation illisible** — empiler vingt badges en vrac jusqu'à ce que la
  rangée ne porte plus aucun signal. Sans ordre, le lecteur ne voit pas
  **quelles familles** le dépôt revendique.

Sans doctrine, chaque ajout de badge rejouerait l'arbitrage « honnête ?
pertinent ? où le mettre ? ». Il faut une règle.

## Décision

**Un badge n'est affiché que s'il reflète un état VRAI et vérifiable, et la
rangée est ORDONNÉE par thématique.** Trois règles.

### 1. Honnêteté — n'afficher que ce qui mesure quelque chose de vrai

Un badge est admissible **si et seulement si** l'une des conditions tient :

- **Dynamique & câblé** : il est servi par un outil réellement branché qui
  recalcule l'état (badge d'état d'un workflow GitHub Actions, badge OpenSSF
  Scorecard alimenté par `scorecard.yml`, badge Best Practices alimenté par le
  projet bestpractices.dev). L'état affiché **est** l'état réel, à tout instant.
- **Statique mais factuel & stable** : il pointe une vérité **non datée et
  invariante** du dépôt (licence MIT ; conformité à une spec de convention —
  SemVer, Keep a Changelog, Conventional Commits — réellement appliquée et
  outillée ; DOI). Un badge statique ne porte **jamais** un score ou un palier
  susceptible de bouger (pas de « coverage 87 % » figé à la main).

**Conséquence opératoire** : un référentiel « noté » dont l'outil n'est pas
encore câblé **n'a pas de badge** — il reste au **plan de remédiation** du
passage d'audit jusqu'à son câblage. On ne pose pas un badge « en attendant ».

### 2. Pertinence — pas de badge pour un référentiel écarté

Un référentiel **examiné et écarté** par un passage d'audit (DORA sans prod, ISO
27001/25010 hors périmètre, SRE error-budget non mesurable sur réseau isolé)
**n'obtient pas de badge**, même s'il en existe un upstream. Son absence est un
**choix tracé** (le passage d'audit le dit), pas un oubli. C'est le critère 2 de
l'[ADR 0061](0061-posture-adoption-bonnes-pratiques.md) appliqué à l'affichage :
le badge doit apporter un signal **net**, pas du bruit.

### 3. Lisibilité — la rangée est ordonnée par thématique

Les badges sont **groupés par famille**, dans cet ordre (du plus identitaire au
plus opérationnel), un groupe par ligne logique :

1. **Identité & licence** — DOI, License.
2. **Conventions & versionnement** — Conventional Commits, SemVer, Keep a
   Changelog.
3. **Qualité & CI** — état CI (`ci.yml`).
4. **Sécurité & supply-chain** — OpenSSF Scorecard (`scorecard.yml`) ; Best
   Practices Badge à venir (action hors dépôt sur bestpractices.dev).
5. **Science ouverte & accessibilité** — _réservée_ : un badge a11y est prévu
   mais son câblage a été différé (outil `pa11y-ci` obsolète, gain net
   insuffisant — cf. passage d'audit & issue #368). La famille existe dans
   l'ordre pour quand un outil à jour sera retenu.

L'ordre **est une règle**, pas une esthétique : il rend visible **quelles
cultures** le dépôt revendique ([ADR 0062](0062-cultures-ingenierie.md)), dans
le même esprit que la vue « par culture d'ingénierie » de
[`bonnes-pratiques.md`](../architecture/bonnes-pratiques.md). Un nouveau badge
se range **dans sa famille**, jamais en fin de liste par commodité. Un
commentaire HTML dans le README rappelle la règle au point d'insertion.

## Conséquences

- **Une rangée qui ne ment pas** : tout badge affiché est soit recalculé en
  continu, soit une vérité stable. Le lecteur peut s'y fier — c'est l'honnêteté
  des preuves portée jusqu'à la vitrine.
- **Un plan de remédiation lisible** : les badges « notés » non encore câblés
  ont une place nommée (le passage d'audit) et un critère de clôture (« le badge
  devient honnête quand l'outil tourne »). L'écart entre l'ambition et l'état
  est **visible et borné**, pas masqué.
- **Une rangée qui se lit** : groupée par thématique, elle **dit** les familles
  revendiquées. L'ajout d'un badge est trivial (le ranger dans sa famille) et ne
  rouvre pas l'arbitrage de fond.
- **Pas de blanc-seing** : ce n'est pas « tout référentiel a son badge ». La
  pertinence (règle 2) écarte ce qui ne mesure rien de vrai **ici** — fidèle au
  fait que le dépôt n'est pas un produit en prod permanente
  ([ADR 0023](0023-plateforme-exemple-generique.md)).
- **Prix à payer** : un jugement humain reste requis à chaque badge candidat («
  dynamique ou stable ? quelle famille ? écarté ou en attente ? »). La règle
  cadre, elle n'automatise pas — comme l'ADR 0061 dont elle dérive.

## Alternatives écartées

- **Tout badge sans condition d'honnêteté** (« si un badge existe upstream, on
  l'affiche »). Écarté : ouvre au badge décoratif, qui ment sur l'état et
  contredit [ADR 0052](0052-reproductibilite-des-resultats.md). Le badge le plus
  visible serait le plus faux.
- **Badges figés recopiés à la main** (scores statiques mis à jour
  manuellement). Écarté : un palier recopié périme silencieusement — exactement
  le travers « état complété à la main = preuve invalide »
  ([ADR 0046](0046-corriger-le-code-pas-l-etat.md)). Un badge de score **doit**
  être dynamique ou ne pas exister.
- **Rangée non ordonnée** (ajouter au fil de l'eau). Écarté : perd le signal «
  quelles familles » ; rejoue l'arbitrage de placement à chaque ajout.
- **Ne pas faire d'ADR** (laisser le passage d'audit décider seul). Écarté : la
  posture d'affichage est **structurante et transverse** (elle vaut pour tout
  badge futur, pas seulement ceux de 2026-06-16) — donc tracée par ADR
  ([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)/[0061](0061-posture-adoption-bonnes-pratiques.md)).
  Un passage d'audit **constate et propose** ; il ne **décide** pas une doctrine
  durable.
