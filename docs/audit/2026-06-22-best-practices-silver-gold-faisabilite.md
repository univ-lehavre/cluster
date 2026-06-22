# 2026-06-22 — Faisabilité OpenSSF Best Practices : silver & gold

| Champ       | Contenu                                                                                                                                                                                                                      |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**    | 2026-06-22                                                                                                                                                                                                                   |
| **Type**    | passage ciblé — **faisabilité** des paliers supérieurs du badge OpenSSF Best Practices (silver, gold) à partir du **passing** déjà obtenu (projet 13301)                                                                     |
| **Méthode** | critères officiels récupérés en direct (`coreinfrastructure/best-practices-badge`, `docs/other.md`) croisés avec l'état réel du dépôt, vérification adversariale                                                             |
| **Fonde**   | une **décision** (ne pas viser silver/gold à court terme) tracée ici, application datée de [ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md) et [ADR 0080](../decisions/0080-notations-et-badges-readme.md) |
| **Verdict** | **gold structurellement hors d'atteinte** (mono-mainteneur) ; **silver atteignable mais à gain faible/partiellement déclaratif** → **on reste à `passing`**, quick-wins à valeur intrinsèque réalisés au fil de l'eau        |

## Pourquoi ce passage

Après l'obtention du badge **passing** (answer-sheet :
[2026-06-22-best-practices-badge-answer-sheet.md](2026-06-22-best-practices-badge-answer-sheet.md)),
la question se pose : viser **silver** puis **gold** ? Ce passage l'instruit
avant toute action, fidèle au **biais adoptif borné** (ADR 0061 : un palier n'a
de valeur que si son gain dépasse son coût **ici**) et à la **doctrine des
badges** (ADR 0080 : n'afficher/poursuivre que ce qui mesure du vrai).

## Gold — hors d'atteinte (5 MUST irréductibles)

Gold exige, en **MUST** (pas SHOULD), des critères incompatibles avec un projet
d'IaC **mono-mainteneur assumé** ([CODEOWNERS](../../CODEOWNERS),
[SAFEGUARDS.md](../../SAFEGUARDS.md) : 0 review requise, auto-merge
release-please) :

| Critère gold                | Pourquoi bloqué                                                              |
| --------------------------- | ---------------------------------------------------------------------------- |
| `bus_factor` ≥ 2            | bus factor = 1, mono-mainteneur assumé                                       |
| `contributors_unassociated` | un seul contributeur significatif ; exigerait un 2ᵉ dev d'une autre org      |
| `two_person_review` ≥ 50 %  | 0 review requise (exiger une approbation casserait l'auto-merge release)     |
| `test_statement_coverage90` | couverture chiffrée jamais mesurée ; dépôt majoritairement bash/Ansible/YAML |
| `test_branch_coverage80`    | couverture **branch** idem                                                   |

Les trois premiers exigent une **seconde personne** : on ne peut pas les
satisfaire **sans changer la nature du projet**. Gold est donc **exclu**, et
c'est un **choix tracé**, pas un manque — exactement le registre de l'ADR 0061
(ne pas courir après un palier qui ne mesure rien de vrai ici).

## Silver — atteignable, mais gain faible et partiellement déclaratif

Bilan des critères silver : **~26 déjà Met**, **~11 N/A** légitimes (build
natif, crypto maison — le dépôt **consomme** TLS via cert-manager sans
implémenter d'algorithme), **~10 faisables**, **1 seul MUST réellement
coûteux**.

**Le dépôt est déjà très mûr** : commits GPG _verified_, releases **cosign
keyless + provenance SLSA**
([ADR 0088](../decisions/0088-signature-releases-cosign-slsa.md)), **CodeQL** +
**trivy** + **gitleaks**, branch protection stricte (`enforce_admins`, required
signatures), **Renovate** (digests, ADR 0006), 89 ADR. La plupart des MUST
silver sont donc acquis.

**Le seul obstacle MUST sérieux** : `test_statement_coverage80`. L'exemption «
pas d'outil FLOSS » ne joue pas (Python a `coverage.py`). Atteindre 80 % de
couverture _statement_ sur le harnais Python (`nestor`/`scripts`) est un effort
**L** ; mais le critère vise « le logiciel produit », or **l'essentiel du dépôt
(bash, Ansible, manifestes) n'a pas de couverture _statement_ classique**. Le
forcer produirait soit un chiffre partiel **trompeur**, soit un gros effort pour
un **signal faible** — précisément ce que l'ADR 0080 refuse (« pas de coverage
figé »).

**La tension doctrinale est le point décisif.** Plusieurs critères silver se
cochent par **affirmation déclarative** (`governance`, `roles_responsibilities`,
`bus_factor` justifié, `input_validation`, `regression_tests_added50`,
`accessibility`). Or le dépôt n'a réintégré le badge passing **que parce qu'il
est validé par un tiers, chaque réponse adossée à une preuve réelle** (ADR 0080,
mise à jour 2026-06-22). Poursuivre un palier qui se gagne **par déclaration**
serait en tension avec cette honnêteté.

## Décision

> **On reste à `passing`.** Silver n'est pas visé **comme palier** (gain faible,
> partiellement déclaratif, un MUST de couverture peu pertinent sur de l'IaC) ;
> gold est **exclu** (5 MUST exigeant une seconde personne / une couverture
> chiffrée hors de portée). C'est une application directe d'ADR 0061 (biais
> adoptif **borné**) et d'ADR 0080 (n'afficher/poursuivre que ce qui mesure du
> vrai).

**Capitalisation possible — sans viser le badge.** Certains « quick-wins silver
» ont une **valeur intrinsèque** (utiles indépendamment du badge) et pourront
être réalisés au fil de l'eau, **s'ils valent par eux-mêmes**, pas pour
décrocher un palier :

- `GOVERNANCE.md` (modèle de décision mono-mainteneur + reprise par l'org
  `univ-lehavre`) → clarté de gouvernance.
- `docs/roadmap.md` (intentions ≥ 12 mois + non-objectifs, matière déjà dans
  ADR 0023) → lisibilité du cap.
- `docs/architecture/assurance-case.md` (exigences sécurité → frontières de
  confiance → contre-mesures, assemblage de SECURITY.md + SAFEGUARDS.md + ADR
  sécurité) → vraie valeur de sécurité.
- Phrase-politique de test explicite dans `CONTRIBUTING.md`.

**À ne pas faire** : `coverage` chiffré affiché (interdit ADR 0080),
`copyright_per_file`/`license_per_file` (lourd, en tension avec ADR 0023 et les
manifestes vendored), tout critère « 2 personnes » (impossible).

> Pas d'issue d'action ouverte : la **décision** ci-dessus tient lieu de
> conclusion. Si un quick-win à valeur intrinsèque est entrepris, il le sera
> pour sa valeur propre, tracé normalement (plan/PR), pas pour « monter en
> palier ».
