# 0069 — `topology.layers` : déclaration explicite des couches (DAG, grain phase)

## Statut

Accepted (2026-06-15)

## Contexte

L'[ADR 0039](0039-nomenclature-axes-catalogue.md) modélise le déploiement par un
**profil scalaire** : un point sur une chaîne **totalement ordonnée**
`base ⊂ metrics ⊂ store ⊂ obs ⊂ dataops` (chaque profil inclut tous les
précédents). L'[ADR 0056](0056-modele-declaratif-topologies.md) en fait le
pilote déclaratif : `catalog.profile` → `default_target` → séquence de phases.

Ce modèle a une **limite d'expressivité** révélée à l'usage (et confirmée par
une cartographie multi-agents,
[ADR 0067](0067-workflows-consignes-4e-trace-empirique.md)) : un ordre **total**
impose des dépendances **fausses**. Exemples concrets :

- déclarer `store` **force** `metrics` (tout ce qui précède dans la chaîne),
  alors que le stockage ne dépend PAS de metrics-server ;
- on ne peut PAS exprimer « `gitops` + `metrics` SANS `monitoring` » : la chaîne
  oblige à prendre `obs` (donc monitoring) avant `dataops`/`gitops` ;
- `profile: dataops` (chemin `atlas`) monte gitops **et** dataops d'un bloc —
  pas moyen d'avoir l'un sans l'autre.

Or les dépendances **réelles** entre couches forment un **DAG**, pas une chaîne
: `metrics-server → [bootstrap]` (aucun stockage),
`storage-simple → [bootstrap]` (branche sœur, indépendante de metrics),
`monitoring → [storage]`, `dataops → [storage, monitoring]` (PVC + SeaweedFS),
`gitops-seed → [gitops, dataops]`. La chaîne totale est une **linéarisation
arbitraire** de ce DAG.

Point décisif : **ce DAG existe déjà**.
L'[ADR 0066](0066-rollback-atomique-graphe-composants.md) a institué un **graphe
de dépendances atomique unique** (`component_deps` dans `rollback-lib.sh`) au
grain **composant**, avec un tri topologique stable (`topo_sort`) calibré pour
reproduire l'ordre codé des arms. Réintroduire une **seconde** table de
dépendances phase→phase en Python recréerait exactement le double-graphe que
l'ADR 0066 a supprimé (les deux dériveraient).

## Décision

**Introduire un champ `layers` au top-level de la topologie : un ENSEMBLE de
couches (grain phase) que l'outil ordonne par tri topologique du DAG de
dépendances**, en remplacement progressif du profil scalaire.

1. **Grain = la phase** (les briques montables de `run-phases.sh` :
   `metrics-server`, `storage-simple`, `monitoring`, `gitops`, `dataops`,
   `gitops-seed`, `ceph`, `sc`, `datalake`…) — chacune a déjà un arm bash prouvé
   et idempotent. `layers` REORDONNE des briques existantes, n'en invente
   aucune.

2. **L'ordre est DÉRIVÉ, pas déclaré** : `layers` est un _set_. `resolve_layers`
   calcule la fermeture transitive des prérequis puis un tri topologique stable.
   Déclarer `[dataops]` tire automatiquement `storage` + `monitoring` ; déclarer
   `[metrics-server]` ne tire RIEN d'autre (preuve de la fausse dépendance
   levée).

3. **Une seule source de vérité d'ordre** : le DAG atomique de `rollback-lib.sh`
   (ADR 0066). `resolve_layers` **appelle** `topo_sort`/`phase_closure` du bash
   (via le même pont que `roundtrip.py`), il ne réimplémente PAS un graphe
   Python. Le tri-up est l'inverse cohérent du tri-down (rollback).

4. **`layers` au TOP-LEVEL** (frère de `nodes`/`storage`) : c'est une INTENTION
   de déploiement, pas une métadonnée descriptive — `catalog` redevient purement
   descriptif (`arch`/`terrain`/`topology`/`status`, ADR 0039).

5. **Conditionnel backend** (seul) : la couche `storage` se résout en
   `storage-simple` (local-path) **ou** `ceph`+`sc` (ceph) ;
   `datalake`/`smoke-s3`/ `wordpress` sont interdits hors backend ceph
   (PlanError).

6. **HA reste structurelle** : dérivée des nœuds (`>1 control` → `ha-3cp`, ADR
   0047/0055), hors `layers`. `layers` ne pilote que la queue applicative.

7. **Rétrocompatibilité** : `catalog.profile` reste un **alias déprécié-doux**.
   `layers` absent → dérivé du profil (`layers_from_profile`, projection du
   préfixe cumulatif). `layers` présent → il prime. **Aucun `.example` versionné
   n'est réécrit** (honnêteté ADR 0052) ; un nouvel `.example` pédagogique
   illustre un `layers` non-préfixe (ex. `[gitops, metrics]`).

8. **Les chemins nommés survivent comme PRESETS** :
   `socle`/`atlas`/`storage-real`/ `cluster-dataops`/`atlas-ceph`/`ha-3cp`
   restent les cibles que `up` passe à `run-phases.sh <nom>` (parité bash figée
   par `test_parity`). `default_target` mappe `layers` → un preset quand il en
   existe un ; sinon `up` cible un nouvel arm générique `layers <séquence>`
   (l'ordre est fourni par Python, le bash exécute — ADR 0063 : bash exécute,
   Python décide).

## Conséquences

- Expressivité fine : `layers: [metrics-server]` (zéro stockage),
  `[gitops, metrics-server]` (sans monitoring), `[dataops]` (avec ses seuls
  vrais prérequis) — des paliers que le profil scalaire ne pouvait pas exprimer.
- Zéro duplication de graphe : `resolve_layers` réutilise le DAG ADR 0066. Le
  drift « deux graphes parallèles » est structurellement évité (RISQUE principal
  borné).
- `resolve_layers` **ferme** les dépendances manquantes (déclarer `[obs]` sans
  store en local-path ajoute `storage` + un message) : pas de couche orpheline.
- Migration **incrémentale, sans big-bang** (Lots A/B/C calqués sur ADR 0066),
  `profile` actif tout du long.
- ADR amendés : [0039](0039-nomenclature-axes-catalogue.md) (le profil devient
  un préfixe particulier de `layers`),
  [0056](0056-modele-declaratif-topologies.md) (`layers` = forme explicite du
  graphe de dépendances), [0068](0068-profil-metrics-palier-fin.md) (son « À
  revoir si » anticipait ce mécanisme générique — `layers` l'est).
  [0066](0066-rollback-atomique-graphe-composants.md) reste le socle technique
  réutilisé, inchangé.
- Preuve (ADR 0034/0052) : un run from-scratch d'un `layers` **non-préfixe**
  (ex. `[gitops, metrics]`, impossible via `profile`) + rejeu `changed=0` — la
  justification empirique de la feature.

## À revoir si

- Un besoin réel de grain **composant** émerge (ex. Grafana sans Loki) :
  `layers` descendrait au grain composant (le DAG ADR 0066 le porte déjà), au
  prix d'une décomposition des playbooks composites.
- Le mapping `layers → preset` (court terme) devient un frein : on passerait à
  un `PHASES_OVERRIDE` bash généralisé (tout `layers` non-preset via l'arm
  générique), rendant les presets de simples raccourcis.

## Alternatives écartées

- **Coder une table `PHASE_DEPS` en Python** : recrée le double-graphe qu'ADR
  0066 a supprimé ; rejeté au profit de la projection du graphe atomique unique.
- **Grain composant d'emblée** : ~40+ composants, exige de décomposer chaque
  playbook ; sur-dimensionné pour le besoin (« couches fines »), reporté.
- **Supprimer `profile` immédiatement** : casse les `.example`, les presets et
  la parité bash d'un coup ; rejeté au profit de l'alias déprécié-doux.
- **`layers` sous `catalog`** : `catalog` est descriptif (ADR 0039) ; une
  intention de déploiement vit au top-level, comme `nodes`/`storage`.
