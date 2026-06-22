# Audit du dépôt `cluster` — grille & passages

> **Doctrine** :
> [ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md). L'audit se
> sépare en une **GRILLE permanente** (ce document : dimensions, critères,
> méthode — qui ne périme pas) et des **PASSAGES datés** (l'application de la
> grille à une date, avec les notes /5 — comme `RESULTS.md`). Un passage
> **renvoie aux ADR** pour les _pourquoi_ (il ne les paraphrase pas) et ses
> **manques deviennent des issues**.

## Passages (datés, append-only)

Chaque passage applique la grille ci-dessous à une date. On garde l'historique
(on voit l'évolution des notes) ; un nouveau passage **n'écrase pas** les
précédents.

| Passage                                                                                                    | Synthèse                                                                                                                                                      | Déclencheur                                 |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **[2026-05-29](2026-05-29/00-synthese.md)**                                                                | premier passage (13 dimensions notées)                                                                                                                        | audit initial du dépôt                      |
| **[2026-06-13 — périmètres atomiques](2026-06-13-verification-graphe-atomique.md)**                        | cartographie multi-agents (5 agents) : 23 composants + 30 arêtes                                                                                              | avant l'encodage du graphe (ADR 0066)       |
| **[2026-06-13 — arêtes de stockage](2026-06-13-verification-aretes-stockage.md)**                          | éventail (16 lecteurs + synthèse adversariale) : 5 arêtes bloc                                                                                                | avant `roundtrip.py` (Lot 1)                |
| **[2026-06-15 — outils CNCF / Kyverno](2026-06-15-audit-cncf-kyverno.md)**                                 | éventail + revue adversariale (60 agents) : Kyverno CLI en tête                                                                                               | réflexion d'adoption (ADR 0075)             |
| **[2026-06-16 — notations de cybersécurité](2026-06-16-audit-notations-cyber.md)**                         | Scorecard / CIS / NIST-ANSSI : 3 référentiels applicables                                                                                                     | issue #354 (manques actionnables)           |
| **[2026-06-16 — notations & normes externes (hors cyber)](2026-06-16-audit-notations-normes-externes.md)** | FAIR / OpenSSF-Badge / DORA / OpenGitOps / SemVer-Changelog-CommitsConv / Diátaxis / WCAG / REUSE / ISO : alignement de fait, 4 référentiels notés non câblés | note sœur de la cyber (mêmes manques)       |
| **[2026-06-19 — évaluation Kubescape (NSA)](2026-06-19-kubescape-nsa.md)**                                 | scan réel + évaluation multi-angle adversariale : NE PAS câbler (redondant Trivy/Kyverno) ; vraie dette = resource limits                                     | réflexion d'adoption (Scorecard-like infra) |
| **[2026-06-20 — documentation (194 .md)](2026-06-20-documentation.md)**                                    | audit doc 14 dimensions (éventail multi-agents) + Diátaxis + comparatif atlas : doc forte ; doc-rot corrigé ; gate `--stats-check` livrée                     | revue exhaustive de la documentation        |
| **[2026-06-22 — Best Practices Badge (answer-sheet)](2026-06-22-best-practices-badge-answer-sheet.md)**    | feuille de réponses « passing » prête à coller dans best.openssf.org : ~50 Met, ~12 N/A, 0 Unmet (badge validé, projet 13301)                                 | soumission du badge OpenSSF                 |
| **[2026-06-22 — faisabilité silver & gold](2026-06-22-best-practices-silver-gold-faisabilite.md)**         | gold hors d'atteinte (mono-mainteneur : 5 MUST « 2 personnes »/coverage) ; silver atteignable mais déclaratif → **on reste à passing** (ADR 0061/0080)        | suite du badge passing obtenu               |

> ⚠️ Le passage du **2026-05-29** est **antérieur à l'installation de
> production** et à ~45 ADR ultérieurs : ses notes /5 reflètent l'état **à cette
> date**, pas l'état courant. Un futur passage les réactualisera (sur jalon —
> cf. _Cadence_).

## Une seule famille de passages — la méthode est une propriété

Un passage peut appliquer la **grille /5** complète (comme le 2026-05-29) ou
**cibler** un angle (un référentiel externe, une famille d'outils) ; il peut
être conduit à la main ou **issu d'un workflow multi-agents** (cartographie en
éventail, revue adversariale). **Ces variantes ne sont pas des familles
distinctes** : être issu d'un workflow est une **propriété de méthode** (champ
_Type_ / _Éventail_ de l'en-tête), pas un type d'artefact à part
([ADR 0078](../decisions/0078-passages-audit-famille-unique.md), qui supersède
l'ADR 0067). Tous vivent côte à côte ici, datés et non réécrits ; tous
**renvoient aux ADR** pour les _pourquoi_ et leurs **manques deviennent des
issues**.

## La grille (permanente)

Les **dimensions auditées**. Chaque passage les note /5 ; la grille n'en dit que
le _quoi_ et le _comment_, jamais le _où on en est_.

| #   | Dimension                              | Ce qu'on mesure                                                   |
| --- | -------------------------------------- | ----------------------------------------------------------------- |
| 1   | Bonnes pratiques IaC & structure       | organisation des dossiers, conventions, hygiène, idempotence      |
| 2   | Tests multi-niveaux & banc             | banc d'essai, scénarios, couverture, gates, preuves consignées    |
| 3   | Lint, format & chaîne qualité          | linters, parité CI ↔ hooks, scanners de posture                   |
| 4   | Documentation (néophyte, code, site)   | pédagogie/glossaire, doc dans le code/ADR, site VitePress         |
| 5   | Reproductibilité & pinning             | pinning des versions, déterminisme, supply chain                  |
| 6   | Sécurité                               | durcissement OS/réseau, plan de contrôle, secrets, hypothèses     |
| 7   | Gouvernance & licence                  | licence, gouvernance OSS, citation, versionnement                 |
| 8   | Opérabilité, observabilité, résilience | observabilité, sauvegarde/DR, HA, upgrades, capacité, RGPD        |
| 9   | Langage des scripts                    | adéquation outil↔action, testabilité (bats/pytest)                |
| 10  | Dispersion CLI vs point d'entrée       | scripts dispersés, orchestrateur, parcours d'entrée               |
| 11  | Logiciels open source                  | pertinence des composants, gestion du risque (CVE, bump, digests) |

## Méthode (permanente)

Un passage applique cette méthode :

1. **Exécution réelle de la chaîne qualité** : prettier, yamllint, shellcheck,
   ansible-lint (profil `production`), kubeconform, jscpd, gitleaks — les
   résultats factuels (et non « faut-il linter ») fondent les notes.
2. **Lecture en profondeur** du code et de la documentation.
3. **Vérification adversariale** de chaque constat majeur : un second relecteur
   tente de **réfuter** le constat avant qu'il ne soit retenu ; les gravités
   sont celles **après** réfutation.
4. **Renvoi aux ADR** : un constat qui touche un choix tracé **cite l'ADR**
   correspondant (le _pourquoi_ a un propriétaire unique, l'ADR), il ne le
   ré-explique pas.
5. **Manques → issues** : chaque constat actionnable devient (ou référence) une
   **issue** ; le passage les liste et les lie.

## Cadence

Un passage se déclenche sur **événement** (jalon majeur : installation prod,
refonte) ou **échéance**, pas en continu (re-noter coûte un passage complet). À
l'image de la fraîcheur des preuves de banc
([ADR 0042](../decisions/0042-fraicheur-preuves-banc.md)), un garde-fou pourra
signaler un passage trop ancien (hors scope de l'ADR 0058).
