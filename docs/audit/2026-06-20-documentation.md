# 2026-06-20 — Audit « documentation du dépôt » (194 fichiers Markdown)

| Champ        | Contenu                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Date**     | 2026-06-20                                                                                                                                                                                                                                                                                                                                                                                 |
| **Type**     | revue exhaustive de la documentation (194 `.md`) sur 14 dimensions (qualité interne · attrayant · explorable · défendable), conduite en éventail multi-agents (16 lots par-fichier + 6 passes transverses + revue Diátaxis + comparatif atlas→cluster), preuves = fichier:ligne **vérifiées adversarialement** contre le code.                                                             |
| **Fonde**    | _réflexion_ — les corrections triviales et majeures sûres sont appliquées dans la PR qui porte ce passage ; les manques restants alimentent une issue parapluie « doc-rot & explorabilité ». Aucune décision nouvelle (les statuts d'ADR promus l'ont été sur code livré vérifié).                                                                                                         |
| **Prolonge** | la doctrine documentaire ([ADR 0059](../decisions/0059-diataxis-typologie-documentation.md) Diátaxis, [ADR 0029](../decisions/0029-markdown-atteignable-doc.md) atteignabilité, [ADR 0060](../decisions/0060-audit-conventions-gouvernance.md) gouvernance chiffrée) ; complète l'[audit notations-cyber](2026-06-16-audit-notations-cyber.md).                                            |
| **Verdict**  | Documentation **forte et défendable** : traçabilité ADR systématique (88 ADR tous liés), honnêteté des preuves exemplaire (ADR 0052), 0 lien mort / 0 orphelin (ADR 0029). **Dette principale = doc-rot** (banc Vagrant supprimé encore cité, compteurs figés périmés, ADR `Proposed` livrés) — **corrigée dans cette passe**. Diátaxis réellement appliqué, maillon faible = le tutoriel. |

## Synthèse par famille de dimensions

### Qualité interne (exactitude, complétude, cohérence doctrinale)

Socle technique très fiable (versions de la matrice ADR 0006 sans écart,
comportements `cni.sh`/`run-phases.sh`/rôles fidèles). Les écarts d'exactitude
se concentraient sur le **doc-rot** : (1) le banc Vagrant `bench/multi-node/`
supprimé mais encore référencé ; (2) des **compteurs figés à la main** périmés
(README STATS « 62 ADR » vs 88 réels, SAFEGUARDS, sidebar) ; (3) des
affirmations fausses sur le code vivant (image MLflow décrite « officielle »
alors que maison, « trois » bases PostgreSQL vs quatre, palier 2 monitoring «
différé » vs livré). Cohérence doctrinale ADR 0023 globalement tenue, quelques
fuites de marques d'instance à généraliser.

### Attrayant (première impression, pédagogie néophyte)

Excellent : QUOI net en 5 s, table « Par où commencer » orientée intention,
accueil néophyte rare pour de l'infra (encarts 🔰, glossaire ordonné par ordre
de rencontre). Réserve : le manifeste « néophyte » ouvre sur ~150 lignes de
revue académique avant « Objectif » — un TL;DR lèverait le palier (→ issue).

### Explorable (navigabilité, lien doc↔code)

Solide et **prouvé mécaniquement** (`check_md_orphans.py` : 0 orphelin, ~55
liens de nav résolus). Backlinks code→doc systématiques. Trois faiblesses de
parcours (« brancher mon app » absent du README, 3 CLI d'entrée non
hiérarchisées, index `platform/README.md` partiel) → issue.

### Défendable (honnêteté des preuves, traçabilité, reproductibilité)

La dimension la plus forte : traçabilité ADR exemplaire (index 88/88
synchronisé), honnêteté des preuves structurelle (RESULTS.md, badges ADR 0080).
Deux dettes traitées : ADR récents `Proposed` alors que le code est livré
(**promus**), écart doc↔code sur la branch protection (**documenté**, jobs
`python`/`gitleaks` non requis signalés dans SAFEGUARDS).

## Revue Diátaxis (ADR 0059)

Diátaxis est **réellement appliqué, pas seulement revendiqué** — rare. Pilier =
**explanation** (88 ADR Nygard purs, manifeste). How-to et reference forts
(glossaire, `contract/`, RUNBOOK). **Maillon faible = le tutoriel pur** (travers
attendu en IaC) : `demarrage.md` était étiqueté « tutoriel » alors que c'est une
page d'**orientation** (ses étapes n'exécutent rien), et le vrai tutoriel
learn-by-doing (`banc-local.md`) n'était pas reconnu comme tel.

**Corrigé dans cette passe** : `demarrage.md` reclassé _orientation_,
`banc-local.md` reconnu _tutoriel_, `composants.md` aligné _explanation_ (ADR
0059 amendé daté + colonne « Mode » de `docs/README.md`). **Reste (→ issue)** :
combler le trou pédagogique « premier cluster » (câbler `banc-local §1` depuis
`demarrage`), purifier `banc-local.md` (sortir la section dépannage), extraire
les faits de capacité de `storage/ceph/RUNBOOK.md`.

## Apprentissages d'atlas (→ cluster)

Le comparatif est honnête : beaucoup de **parité** (READMEs lus en place,
link-check, glossaire cross-linké, CHANGELOG auto) et plusieurs pratiques
d'atlas **non pertinentes pour de l'IaC** (référence API TypeDoc — qu'atlas a
d'ailleurs introduite **puis retirée**, signal ADR 0061 ; OpenAPI ;
dictionnaires de données ; WCAG). Les gains nets transposables, par effort
croissant :

| Pratique atlas                        | Verdict              | Suite                                                  |
| ------------------------------------- | -------------------- | ------------------------------------------------------ |
| **Diff-check du bloc STATS**          | **gain net #1**      | **FAIT** : `--stats-check` (cf. ci-dessous)            |
| Registre de drifts navigable          | gain net réel        | → issue (générer `.md` depuis `registre-drifts.yaml`)  |
| Encart « par où commencer » ADR       | gain léger           | → issue                                                |
| Charte doc opposable (1 page)         | gain pédagogie       | → issue (seulement si remplace de la dispersion)       |
| Table d'index ADR générée + `--check` | gain borné           | → issue                                                |
| Sidebar autogénérée (Starlight)       | **conflit ADR 0029** | écarté pour les ADR (noierait le menu sous 88 entrées) |

**Gain net #1 livré** : la gate `--stats-check`
([`scripts/check_gouvernance.py`](../../scripts/check_gouvernance.py)) régénère
le bloc « le dépôt en chiffres » en mémoire, le compare au README entre les
marqueurs `STATS:DEBUT`/`STATS:FIN`, et **échoue si écart** — câblée dans
`pnpm lint` (`lint:stats`) et le job CI `python`. C'est précisément la gate qui
aurait empêché le « 62 ADR » périmé. Logique pure extraite et testée (ADR 0017).

## Corrigé dans cette passe

- **Doc-rot Vagrant** : RUNBOOK, `bench/scenarios/README.md`,
  `docs/architecture/*` réécrits vers le banc Lima ; addenda datés sur les ADR
  0015/0022 ; bandeaux « photo historique » sur `exposition-reseau.md` et
  `validation-banc.md` (sans réécrire les résultats datés, ADR 0052).
- **Compteurs figés** : bloc STATS du README régénéré (88 ADR), sidebar « Index
  des ADR » (sans chiffre), SAFEGUARDS dégelé.
- **Affirmations fausses** : image MLflow maison, **quatre** bases PostgreSQL
  (mlflow ajouté), palier 2 monitoring livré.
- **6 ADR promus** `Proposed → Accepted` (code livré vérifié) : 0072, 0081,
  0083, 0086, 0087, 0088 ; index synchronisé ; format `Superseded by 0078`
  corrigé (0067) ; plan `renommer-test-bench` passé `Achevé` + section Suivi
  (`check_gouvernance` repassé vert).
- **Diátaxis** reclassé (cf. ci-dessus) ; **gate `--stats-check`** câblée.
- **Triviaux** : `dataops-chain → cluster-dataops`,
  `topology.py epreuves → test scenarios`, disque banc 40 GiB,
  `rook-ceph-block-replicated` (WordPress).

## Reste → issue parapluie « doc-rot & explorabilité »

Manifeste TL;DR · parcours « brancher mon app » + hiérarchie des 3 CLI · index
`platform/README.md` complet · trou pédagogique « premier cluster » ·
purification Diátaxis (banc-local, storage RUNBOOK, contract) · registre de
drifts navigable · généralisation des dernières marques d'instance (ADR 0040,
datalake) · RAM banc Lima à réactualiser.

## Note de méthode et limites

Passage **figé** (ADR 0058) : l'état décrit périmera. Les findings d'exactitude
ont été **vérifiés adversarialement** contre le code (faux-positifs retirés).
Les écarts « à re-prouver » (branch protection, validation banc Lima) sont
tracés et se clôturent par vérification GitHub / run from-scratch. Audit conduit
en éventail multi-agents — propriété de méthode, pas une famille de passage à
part ([ADR 0078](../decisions/0078-passages-audit-famille-unique.md)).
