# Les preuves de qualité, en un coup d'œil

Cette page est une **vitrine** : elle rassemble, pour un lecteur pressé
(évaluateur, décideur, développeur qui découvre), les **preuves vérifiables**
que ce dépôt n'affirme pas sa qualité — il la **trace**. Chaque ligne renvoie à
la **source brute** (registre, journal de run, script, manifeste) ; cette page
ne recopie rien, elle **oriente**.

> **Pourquoi une page séparée ?** Le détail vit déjà partout (ADR, registre de
> drifts, journaux de banc, garde-fous). Mais ces preuves sont **dispersées** :
> un décideur n'a pas le temps de fouiller. Cette page les **consolide** et
> pointe vers la trace de chacune. Pour le récit complet du projet, lire le
> [manifeste](manifeste.md) ; pour la liste des garde-fous, voir
> [SAFEGUARDS.md](../SAFEGUARDS.md).

## Le dépôt en chiffres

Les chiffres agrégés sont **calculés**, pas saisis à la main : le script
[`check_gouvernance.py`](../scripts/check_gouvernance.py)
([ADR 0060](decisions/0060-audit-conventions-gouvernance.md)) les régénère, et
le [README](../README.md#le-dépôt-en-chiffres) en publie le bloc à jour
(`pnpm check:gouvernance --stats`). À la dernière régénération :

- des dizaines d'**ADR** (décisions de conception, datées et immuables),
- des **plans** vivants (la mise en œuvre des décisions, avec leur état),
- des dizaines de **drifts** indexés (chaque écart révélé par un run, avec cause
  et correctif),
- des dizaines de **scénarios E2E** reproductibles,
- **0 %** de duplication shell (seuil `jscpd` ≤ 5 %).

Le bloc chiffré faisant foi (avec la ventilation par statut) est dans le
[README](../README.md#le-dépôt-en-chiffres) — il est **régénéré par script**,
jamais édité à la main.

## Cinq preuves, et où les vérifier

| Preuve                         | Ce qu'elle démontre                                                                                  | Trace brute (à vérifier soi-même)                                                                                                                    |
| ------------------------------ | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Gouvernance tracée**         | Chaque choix est daté, immuable, et relié à sa mise en œuvre (ADR → plan → issue → PR).              | [index des ADR](decisions/) · [plans](plans/) · [grille & passages d'audit](audit/)                                                                  |
| **Reproductibilité prouvée**   | Le cluster se monte **de zéro**, sans intervention manuelle, en un temps mesuré et consigné.         | [journal des runs Lima](../test/lima/RESULTS.md) · [ce que le banc prouve](architecture/validation-banc.md)                                          |
| **Honnêteté empirique**        | Chaque écart de run est indexé (symptôme, cause, correctif, statut) — pas caché, capitalisé.         | [registre des drifts](architecture/registre-drifts.yaml) · [leçons des runs](architecture/lecons-des-runs.md)                                        |
| **Couverture E2E**             | Des épreuves réelles (unitaires, intégration de chaîne, chaos) exercent chaque chaîne fonctionnelle. | [scénarios reproductibles](../test/scenarios/) · [matrice du catalogue](architecture/matrice-catalogue.md)                                           |
| **Chaîne qualité automatisée** | Aucune régression n'atteint la prod sans franchir hooks, CI, et banc — un contrat d'interface en CI. | [garde-fous (4 niveaux)](../SAFEGUARDS.md) · [contrat machine-lisible](../contract/) ([ADR 0043](decisions/0043-contrat-interface-cluster-atlas.md)) |

## Ce qui distingue ce dépôt

**On ne déclare « validé » qu'après un run de bout en bout, depuis le code
seul.** Le [lint ne valide pas](architecture/lecons-des-runs.md) — il filtre le
trivial. Les drifts les plus instructifs (une
[NetworkPolicy](glossaire.md#cni-container-network-interface) manquante, un
build qui sature la mémoire, une
[CRD](glossaire.md#crd-custom-resource-definition) qu'un parseur rejette)
passaient **tous** les linters au vert ; seul le run from-scratch les a exposés
([ADR 0034](decisions/0034-validation-e2e-from-scratch.md),
[ADR 0052](decisions/0052-reproductibilite-des-resultats.md)).

**La répétition est le processus, pas un échec.** Aucune brique n'a jamais
fonctionné e2e du premier coup ; le compteur de drifts qui se tarit run après
run **est** la courbe de fiabilisation. Le détail est public, daté, citable.

**Les trous sont assumés, pas masqués.** La
[matrice du catalogue](architecture/matrice-catalogue.md) nomme explicitement ce
qui n'a **pas** encore été monté (x86, haute disponibilité du plan de contrôle,
multi-sites) — l'honnêteté sur la couverture est elle-même une preuve de
sérieux.

## Pour aller plus loin

- **Comprendre le pourquoi** : le [manifeste](manifeste.md) raconte le projet de
  bout en bout (méthode, voyage d'ingénierie, résultats).
- **Juger les décisions** : l'[index des ADR](decisions/) (lecture
  chronologique) ou les [vues d'architecture par domaine](architecture/)
  (lecture par thème).
- **Reproduire soi-même** : monter le [banc local](banc-local.md) et rejouer la
  chaîne.
