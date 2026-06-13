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

| Passage                                     | Synthèse                               | Déclencheur            |
| ------------------------------------------- | -------------------------------------- | ---------------------- |
| **[2026-05-29](2026-05-29/00-synthese.md)** | premier passage (13 dimensions notées) | audit initial du dépôt |

> ⚠️ Le passage du **2026-05-29** est **antérieur à l'installation de
> production** et à ~45 ADR ultérieurs : ses notes /5 reflètent l'état **à cette
> date**, pas l'état courant. Un futur passage les réactualisera (sur jalon —
> cf. _Cadence_).

## Workflows multi-agents consignés (4ᵉ trace empirique)

Les **[workflows multi-agents consignés](workflows/)** — cartographies en
éventail et revues adversariales qui ont fondé une décision structurante — sont
la **4ᵉ trace empirique** du dépôt
([ADR 0067](../decisions/0067-workflows-consignes-4e-trace-empirique.md)), à
côté des passages d'audit ci-dessus, de `RESULTS.md` et du registre des drifts
(ADR 0058 §6). On y consigne la **synthèse + les findings vérifiés** (pas les
rapports bruts, ADR 0023), datés et non réécrits.

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
