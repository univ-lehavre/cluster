# Plan — Modèle déclaratif unifié des topologies

## État

> **État : Actif** (depuis 2026-06-12) · **Fonde :
> [ADR 0056](../decisions/0056-modele-declaratif-topologies.md)** (Accepted —
> modèle déclaratif unifié, un fichier `topology.yaml` décrit, Ansible converge)
> · **Issues : [#250](https://github.com/univ-lehavre/cluster/issues/250)**
> (palier P7, ha-3cp).
>
> **Cadre**
> ([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md)) :
> ce plan met en œuvre une décision, il ne la remplace pas. Les _pourquoi_
> vivent dans l'ADR 0056 ; ce plan porte le **déroulé évolutif** et son
> **suivi**.

## Paliers de réalisation (P0 → P8)

La vision de l'[ADR 0056](../decisions/0056-modele-declaratif-topologies.md) §8
(13 exigences : décrire / éprouver / mesurer / optimiser / consigner) **n'est
pas le socle**. Réalisation incrémentale, chaque palier prouvé par un run
([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)/[0052](../decisions/0052-reproductibilite-des-resultats.md)).

| Palier | Contenu                                                                                                                                                  | Exigences 0056 §8 |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| **P0** | Modéliser sans générer : `topologies/socle.example.yaml` des topologies décrites — révèle les deltas (VIP/LB manquant…)                                  | 1-5 (schéma)      |
| **P1** | Générateur read-only Lima → inventaire + NODES + profils, **byte-identique** (ADR 0056 §3)                                                               | 1-3               |
| **P2** | Profil + défauts/variantes + graphe de dépendances                                                                                                       | 3, 13             |
| **P3** | Façade CLI/CI (`generate`/`validate`/`status`/`diff`)                                                                                                    | —                 |
| **P4** | Épreuves filtrées + historique lu + consignation (objectif + fail)                                                                                       | 6, 10-12          |
| **P5** | Boucle « que faire ensuite » CLI (diff → suggère → lance via `ansible-runner`) ; TUI différé ([ADR 0063](../decisions/0063-ansible-runner-boucle-p5.md)) | (boucle)          |
| **P6** | Métriques exposées + smoke-test réversibilité                                                                                                            | 7-8               |
| **P7** | Étendre aux topologies cibles (`multi-node-4`, `ha-3cp` + VIP/LB + kube-vip — #250)                                                                      | 4                 |
| **P8** | Optimiseur (propose des ajustements depuis les métriques)                                                                                                | 9                 |

P0-P3 = **socle** (générateur de config) ; P4-P6 = **plateforme
d'épreuve/mesure** ; P7 débloque la HA (#250) ; P8 (optimiseur) est le plus
lointain. Aucun palier ne casse le précédent (invariant byte-identique, ADR 0056
§3).

## Suivi

État global : voir l'en-tête [`## État`](#état) (Actif). Démarré le 2026-06-13 :
**P0 à P6 faits** — générateur byte-identique des deux inventaires (P1) +
dérivation de profil pure et à parité avec le bash (P2) + façade CLI/CI
`scripts/topology.py` (`generate`/`validate`/`status`/`diff`, P3) + filtrage des
épreuves par la topologie et lecture de l'historique/fraîcheur
(`epreuves`/`runs`, P4) + boucle `next` « que faire ensuite » qui suggère la
prochaine phase et la lance via `ansible-runner` sur `--apply`
([ADR 0063](../decisions/0063-ansible-runner-boucle-p5.md), P5) + exposition des
métriques consignées (`metrics`) et smoke-test de réversibilité (`smoke`, P6),
prouvés par test. La commande `diff` est câblée en CI
(`pnpm lint:topology-drift`) : la moindre dérive de l'inventaire prod régénéré
casse le lint.

| Palier | État       | Issue(s)                         | Run de preuve                                                                                                                                                                                                                            |
| ------ | ---------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0     | ✅ fait    | —                                | `topologies/socle.example.yaml` + paquet `cluster_topology/`                                                                                                                                                                             |
| P1     | ✅ fait    | —                                | **inventaires prod + banc byte-identiques** (12 tests, vs `hosts.example.yaml` et `write_inventory`)                                                                                                                                     |
| P2     | ✅ fait    | —                                | **dérivation de profil** (inclusion cumulative ADR 0039 + faisceau `-e` à parité bash, `cluster_topology/profile.py`, 12 tests)                                                                                                          |
| P3     | ✅ fait    | —                                | **façade CLI/CI** `scripts/topology.py` (`generate`/`validate`/`status`/`diff`, argparse stdlib) ; `diff` câblé en CI (`lint:topology-drift`), 16 tests                                                                                  |
| P4     | ✅ fait    | —                                | **épreuves filtrées + historique lu** (`cluster_topology/epreuves.py` miroir de la matrice + `history.py` à parité fraîcheur bash ; commandes `epreuves`/`runs` ; 40 tests)                                                              |
| P5     | ✅ fait    | —                                | **boucle `next`** (suggère la prochaine phase ; `--apply` lance via `ansible-runner`, [ADR 0063](../decisions/0063-ansible-runner-boucle-p5.md)) : `plan.py` (séquence fidèle à run-phases.sh) + `runner.py` isolé ; 34 tests            |
| P6     | ✅ fait    | —                                | **métriques + smoke réversibilité** : `metrics.py` (expose durées/cpu/ram consignés, ne mesure rien de neuf) + `smoke.py` (créer→vérifier→détruire→vérifier, couche kubernetes isolée/stubable) ; commandes `metrics`/`smoke` ; 27 tests |
| P7     | ⬜ à faire | **#250** (banc Lima HA `ha-3cp`) | —                                                                                                                                                                                                                                        |
| P8     | ⬜ à faire | —                                | —                                                                                                                                                                                                                                        |

**Issues créées depuis ce plan** : _(aucune encore — à lier au fil de
l'implémentation)_.

**Runs de preuve** : à consigner dans
[`test/lima/RESULTS.md`](../../test/lima/RESULTS.md) ; un run `fail` est
consigné au même titre qu'un succès
([ADR 0056](../decisions/0056-modele-declaratif-topologies.md) §8,
[ADR 0052](../decisions/0052-reproductibilite-des-resultats.md)).
