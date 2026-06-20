# 0083 — `layers` source unique de l'ordre : presets en alias, plus de chemins nommés par défaut

## Statut

Accepted (2026-06-19) — livraison INCRÉMENTALE. Le code est livré
(`nestor/layers.py`, source unique de l'ordre) ; promu depuis
`Proposed (2026-06-17)`.

## Contexte

L'[ADR 0069](0069-topology-layers-dag-grain-phase.md) a introduit `layers` : un
ensemble de couches dont l'**ordre est DÉRIVÉ** du graphe atomique unique
([ADR 0066](0066-rollback-atomique-graphe-composants.md), `resolve_layers` →
`topo_sort`). Mais il a **conservé les presets de chemin** comme étape
transitoire (son point 8) :
`socle`/`atlas`/`storage-real`/`cluster-dataops`/`atlas-ceph`/`ha-3cp` gardent
une **séquence figée** (`_PATH_TAIL` dans `nestor/plan.py`), et `default_target`
re-mappe l'ensemble de couches déclaré vers un nom de preset.

Cela laisse **deux sources de vérité de l'ORDRE** des couches en parallèle :

1. `_PATH_TAIL` — tables ordonnées par preset, transcription manuelle des arms
   de `bench/lima/run-phases.sh` ;
2. le graphe atomique (`resolve_layers`) — la source que l'ADR 0069 voulait
   unique.

`test_parity` ne fait que **constater** leur égalité ; il ne supprime pas le
doublon. Le « À revoir si » de l'ADR 0069 anticipait précisément ce dénouement :
« le mapping `layers → preset` devient un frein → rendre les presets de simples
raccourcis ».

**Le doublon a produit un bug vécu.** `default_target` mappe approximativement
(`dataops ∈ layers → atlas`) : pour une topo `layers: [dataops, mlflow]`, il
rend `atlas`, dont la séquence figée n'inclut PAS `mlflow`. Résultat : `next` et
`preview` **divergent** — `preview` (qui dérive la vraie séquence via
`resolve_layers`, branche de rustine) voit « MLflow à installer », tandis que
`next` (sur le preset `atlas`) propose « rejouer up » sur un banc déjà monté.
Les branches `layers_seq` de `cmd_up` et `cmd_preview` sont des rustines de ce
même décalage.

## Décision

**`layers` (graphe atomique) devient la SEULE source de l'ordre. Les presets de
chemin ne sont plus dérivés par défaut.**

1. **`default_target(topo)` rend TOUJOURS `layers`** (suppression du mapping
   vers `atlas`/`socle`/`metrics`/`atlas-ceph`). La séquence vient exclusivement
   de `resolve_layers(topo.declared_layers, backend)` + le socle dérivé. Plus de
   « second routeur » qui peut diverger du montage réel.

2. **`ha-3cp` cesse d'être un chemin nommé : c'est une propriété de la
   TOPOLOGIE.** La HA se déduit de `topo.is_ha_control_plane` (≥2
   control-planes,
   [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md)/[0055](0055-ha-3cp-hyperconverge-promotion-in-place.md)).
   Son amorçage (`bootstrap-ha`, `join-cp` : kube-vip + join etcd) n'est PAS
   réductible à des layers (aucun nœud dans le graphe atomique, aucun arm
   unitaire) : il devient un **socle dérivé** — `expected_phase_sequence`
   produit, pour une topo HA,
   `[up, bootstrap-ha, join-cp] + queue resolve_layers`. À l'exécution, `cmd_up`
   délègue le socle HA à l'arm `run-phases.sh ha-3cp` **inchangé**
   (l'orchestration VIP/etcd reste portée par `nestor/ha.py`), puis enchaîne la
   queue. `ha-3cp` disparaît comme **target saisi par l'utilisateur** ; il
   survit comme détail d'implémentation du moteur bash, dérivé de la topologie.

3. **`atlas` devient un alias de LAYERS** (`LAYER_PHASES`, `nestor/layers.py`),
   valant la chaîne MLOps complète
   `[metrics, obs, gitops, dataops, gitops-seed, mlflow]` (`obs` = monitoring,
   `metrics` = metrics-server ; `gitops-seed` listé explicitement car phase de
   **queue** non tirée par la clôture de `[gitops]`). Une topo déclare
   `layers: [atlas]` pour toute la chaîne. `resolve_layers` l'ordonne via le
   graphe :
   - local-path :
     `storage-simple, metrics-server, monitoring, gitops, dataops, gitops-seed, mlflow`
     ;
   - ceph :
     `ceph, sc, datalake, metrics-server, monitoring, gitops, dataops, gitops-seed, mlflow`.

   C'est l'ancien `atlas`/`atlas-ceph` **plus `mlflow`** (ADR 0082, brique
   livrée) ; l'atlas-ceph gagne aussi `metrics-server` (inoffensif, déjà présent
   en local-path) — sur-ensemble cohérent assumé, pas une régression de couche.

4. **`profile: atlas` n'existe PAS** : `profile` reste le préfixe **cumulatif**
   `base ⊂ metrics ⊂ store ⊂ obs ⊂ dataops`
   ([ADR 0039](0039-nomenclature-axes-catalogue.md)) ; `atlas` n'est pas un
   préfixe (il ajoute gitops/seed/mlflow hors chaîne). On l'expose donc
   **uniquement** via `layers: [atlas]`, sans casser l'invariant du profil
   scalaire.

5. **`run-phases.sh` reste inchangé** (moteur bash,
   [ADR 0049](0049-doctrine-choix-outil-par-action.md)/[0063](0063-ansible-runner-boucle-p5.md)).
   Hors HA, `cmd_up` passe par l'arm générique `layers <séquence>` (Python
   décide l'ordre, bash exécute). Les arms nommés (`atlas`, `atlas-ceph`,
   `storage-real`, `cluster-dataops`, `metrics`, `socle`) survivent pour
   `--target <nom>` explicite et la rétrocompat des scénarios/bench, mais ne
   sont plus la cible par défaut.

## Conséquences

- **Une seule source de vérité de l'ordre** : `_PATH_TAIL`, `_CEPH_PATHS`,
  `_STORAGE_LAYER`, `_LOCAL_PATH_NEEDS_STORAGE` disparaissent de
  `nestor/plan.py`. Le drift potentiel entre presets et graphe est supprimé à la
  racine.
- **`next`/`preview`/`up` convergent par construction** : tous dérivent la
  séquence via `resolve_layers` quand aucun `--target` n'est forcé → le bug
  `next` vs `preview` est dissous (plus deux routeurs).
- **HA = propriété de la topologie** (cohérent avec ADR 0069 point 6 qui la
  disait déjà « structurelle, dérivée des nœuds ») : on ne déclare plus un
  chemin `ha-3cp`, on déclare ≥2 control-planes.
- `test_parity` change de garantie : il prouve désormais que
  `resolve_layers(alias)` reproduit la séquence de référence (le filet
  anti-drift demeure, sur la nouvelle source unique).
- **Aucune destruction de banc** : refactor Python-pur (run-phases.sh intact) ;
  preuve par `pytest`/`bats` sans banc, run from-scratch différé (ADR 0034/0052,
  banc Ceph détruit).
- ADR amendés : [0069](0069-topology-layers-dag-grain-phase.md) (son point 8 «
  presets transitoires » est résorbé ; son « À revoir si » est réalisé),
  [0056](0056-modele-declaratif-topologies.md) (`default_target` ne mappe plus
  vers des presets),
  [0047](0047-topologie-ha-3cp-control-plane-dedie.md)/[0055](0055-ha-3cp-hyperconverge-promotion-in-place.md)
  (HA dérivée de la topologie, plus un chemin nommé).
  [0066](0066-rollback-atomique-graphe-composants.md) reste le socle technique
  réutilisé, inchangé.

## À revoir si

- Un preset nommé redevient nécessaire comme **alias de layers** (pas de chemin)
  : l'ajouter à `LAYER_PHASES` comme `atlas`, jamais à `_PATH_TAIL` (supprimé).
- L'amorçage HA gagne un arm unitaire dans le graphe : le socle HA dérivé
  pourrait alors passer aussi par l'arm `layers`, supprimant le dernier cas
  spécial bash.

## Alternatives écartées

- **Garder les presets comme alias de chemin ordonnés** (conserver `_PATH_TAIL`)
  : laisse les deux sources de vérité, le bug `next`/`preview` peut revenir.
  Rejeté — c'est exactement la dette que cet ADR solde.
- **Supprimer aussi les noms (`atlas`…) entièrement** : chaque topo listerait
  toutes ses phases
  (`layers: [metrics, obs, gitops, dataops, gitops-seed, mlflow]`). Verbeux,
  perd le vocabulaire métier ; rejeté au profit de l'alias `atlas` côté layers.
- **`ha-3cp` reste un chemin nommé à part** : moins risqué (périmètre réduit)
  mais perpétue un « chemin » qui est en réalité une topologie ; rejeté — la HA
  est une propriété du control-plane, pas une cible de montage.
- **Réduire l'amorçage HA à des layers** (`bootstrap-ha`/`join-cp` comme phases
  du graphe) : exigerait des arms unitaires et des nœuds graphe pour le VIP/join
  etcd ; sur-dimensionné, reporté (cf. « À revoir si »).
