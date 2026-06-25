# 0096 — Graphe de topologie Python figé, vérifié contre Ansible

## Statut

Accepted (2026-06-25)

Précise et étend les ADR [0066](0066-rollback-atomique-graphe-composants.md)
(rollback atomique : le graphe de composants devient **du Python figé**, plus du
bash), [0069](0069-topology-layers-dag-grain-phase.md) (layers : DAG au grain
phase) et [0083](0083-layers-source-unique-de-l-ordre.md) (layers, source unique
de l'ordre : le **module Python EST désormais cette source**, plus le subprocess
bash). Il ne les **supersede pas** frontalement : il les **implémente en
Python**, en gardant intacte la sémantique du graphe atomique. Lié à
[0017](0017-langage-des-scripts.md) (Python testé : pytest garde-fou),
[0023](0023-plateforme-exemple-generique.md) (valeurs génériques) et
[0043](0043-contrat-interface-cluster-atlas.md) (modèle du check-qui-notifie
`check_contract.py`). Toutes les valeurs ci-dessous sont des exemples génériques
([ADR 0023](0023-plateforme-exemple-generique.md)) : `platform-cnpg`,
`platform-marquez`, `platform-s3-bucket`, `dataops`, `marquez`, `dagster`,
`s3-backing-{loki,cnpg,mlflow}`.

## Contexte

Le graphe de dépendances des phases/composants est aujourd'hui déclaré **à la
main en bash** : un gros `case` dans
[`bench/lima/rollback-lib.sh`](../../bench/lima/rollback-lib.sh)
(`component_deps`, ~l. 378-425) porte les arêtes, et les tables sœurs
(`component_namespace`, `component_targeted`, `component_crd_groups`,
`component_has_nodeside`, `component_alias_weight`, `component_profile`) portent
le périmètre de rollback. `nestor` ne re-déclare pas ce graphe : il le
**consulte en SHELLANT bash** — `nestor/layers.py` (`phase_deps` :217,
`resolve_layers` :148) passe par le pont `_rb` (:91, un `subprocess` qui source
`rollback-lib.sh` à chaque appel), et `nestor/roundtrip.py` fait de même via
`_rollback_lib_call` (:71). Enfin, la **santé** des couches est portée par une
**3e table séparée** : `_LAYER_SIGNAL` dans
[`scripts/topology.py`](../../scripts/topology.py) (:739), qui mappe une phase →
un seul Deployment discriminant.

**Trois représentations du même fait, synchronisées à la main** : le graphe
(bash), sa projection nestor (consultée par subprocess) et le signal de santé.
Cette synchronisation par discipline humaine — par le commit, pas par le code ni
par un test — produit des erreurs récurrentes :

- **Le « Marquez oublié »** : `platform-marquez` déploie bien Marquez (gate
  `readyReplicas==1` au montage), mais la phase `dataops` a **deux feuilles**
  (`dagster` ET `marquez`) et `_LAYER_SIGNAL["dataops"]` ne sonde que
  `dagster-dagster-webserver`. Le verdict « DataOps complet » peut donc être
  **mensonger** sur un drift post-montage de Marquez.
- **`preview` affiche `mlflow` à-jour alors qu'il est absent** : l'assemblage de
  l'état (`done`/`observed`) a divergé entre commandes parce que les
  **câblages** du graphe, eux, ne sont pas uniques.

Le **fil rouge** de l'audit le formule précisément : ce n'est **pas** « pas de
source unique » au sens naïf — les **primitives** SONT uniques (`diff_phases`,
`topo_sort`, `component_deps`). C'est que **leurs CÂBLAGES et leurs MIROIRS ne
le sont pas** : il existe partout deux (ou trois) représentations du même fait,
et la cohérence des miroirs n'est garantie que par discipline humaine + tests
d'échantillon. D'où la récurrence : chaque correctif corrige UN câblage/miroir,
l'autre reste.

Cette question a été instruite par un **audit** des causes racines (pourquoi «
on revient souvent aux mêmes erreurs ») puis par un **workflow de conception
multi-agents** (scans du code, options détaillées, vérifications adversariales,
synthèse) qui a écarté l'approche « Ansible = source » et tranché la frontière.

## Décision

### 0. Approche RETENUE : le graphe Python est la source, le check vérifie Ansible

Deux approches sont possibles pour rendre le graphe et Ansible cohérents.

**Approche A (retenue)** : le graphe Python figé est la **source unique** ;
Ansible est **vérifié contre lui** par un check qui **notifie** la divergence.

**Approche B (ÉCARTÉE)** : « déduire le graphe d'Ansible par introspection »
(Ansible = source). Écartée parce que **le code montre que les dépendances
Ansible sont INCOMPLÈTES pour ça** :

- **mapping rôle↔composant non 1:1** (`platform-cnpg` porte 4 composants,
  `platform-s3-bucket` en porte 3) : un rôle ne désigne pas un composant ;
- **l'ORDRE inter-composant n'existe pas dans Ansible** — il n'y a que l'ordre
  des `import_role` dans un playbook, pas le DAG fin du graphe atomique ;
- **le SIGNAL de santé n'est nulle part dans Ansible** — quel maillon atteste
  une phase est une donnée que le rôle ne porte pas.

Nuance importante (et c'est ce que le **check exploite**, pas pour générer mais
pour **vérifier**) : les dépendances **sont partiellement exprimées** dans les
rôles — gates `assert` (« déployer `platform-cnpg` avant `platform-dagster` »
dans un `fail_msg`), lectures cross-rôle (`k8s_info` sur un Secret CNPG). Le
graphe Python en est la **forme complète et figée** ; le check confronte les
deux.

### 1. Graphe Python figé — `nestor/graph.py`

On crée `nestor/graph.py` : un `@dataclass(frozen=True) Component` qui porte
**ce qu'Ansible ne dit pas** — l'**ordre** inter-composant, le **périmètre** de
rollback (4 dimensions) et le **signal** :

```python
@dataclass(frozen=True)
class Component:
    name: str
    deps: tuple[str, ...]            # arêtes directes        (= component_deps)
    role: str | None                 # rôle Ansible (None = socle)
    profile: str = "always"          # always|ceph|leger      (= component_profile)
    weight: int = 9                  # tie-break topo lexico   (= component_alias_weight)
    namespace: str | None = None     # périmètre rollback      (= component_namespace)
    targeted: tuple[str, ...] = ()   # ressources ciblées      (= component_targeted)
    crd_groups: tuple[str, ...] = () # groupes CRD             (= component_crd_groups)
    has_nodeside: bool = False       # wipe disque node-side   (= component_has_nodeside)
```

**Le dataclass DOIT porter les 4 dimensions de périmètre**
(`namespace`/`targeted`/`crd_groups`/`has_nodeside`), pas seulement les arêtes :
`nestor/roundtrip.py` (:115-137) consomme ces 4 dimensions via le pont bash,
donc sans elles le portage **n'est pas byte-identique** et le rollback régresse.

Projections **pures** remplaçant le subprocess bash : `topo_sort()`,
`phase_closure()`, `phase_of_component()`, `phase_deps()`, `PHASE_COMPONENTS`,
et `phase.signal_component` (donnée **humaine** : « est une feuille » ne tranche
pas quand une phase a plusieurs feuilles — `dataops` en a deux).

**Pourquoi Python figé et PAS YAML.** Le graphe est **déjà du Python testé**
(via `rollback-lib.sh` +
[`bench/unit/rollback.bats`](../../bench/unit/rollback.bats)) ; le porter en
dataclass **garde pytest comme garde-fou**
([ADR 0017](0017-langage-des-scripts.md)). Un YAML perdrait cette couverture. La
**byte-identité est à PROUVER** (piège connu : le tie-break lexicographique de
`topo_sort` via la clé `%s%03d`, comparaison `\<` bash — à reproduire à l'octet
via `rollback.bats` rejoué en pytest).

### 2. Check de parité graphe ↔ Ansible qui NOTIFIE — `scripts/check_topology.py`

On crée `scripts/check_topology.py` calqué **ligne à ligne** sur
[`scripts/check_contract.py`](../../scripts/check_contract.py) — le **modèle du
check-qui-notifie** : `Finding(level, message)`, fonctions **pures** testées,
`_report()` qui sort `0/1/2`, branché en CI. Quatre familles de constats
**bloquants** (exit 1) :

1. **Composant → rôle** : tout `Component(role≠None)` a son
   `bootstrap/roles/<role>/` ET est importé par un playbook (ancrage
   anti-faux-vert).
2. **Rôle → composant** — **LE notifieur « Marquez oublié »** : tout
   `platform-X` importé est référencé par **≥1** `Component`, sinon **ERREUR**.
   Allowlist `EXPECTED_NON_GRAPH_ROLES` **justifiée par chemin** (comme
   `.trivyignore.yaml`) pour les rôles socle.
3. **Signal** : `signal_component ∈ PHASE_COMPONENTS[phase]` ET est une
   **feuille** ; sa cible kubectl (`_LAYER_SIGNAL`) est **ancrée** dans les
   manifestes du rôle.
4. **Cohérence interne** : acyclicité, arêtes connues, jetons résolus (= portage
   des invariants de `rollback.bats`).

**Réserves à coder** (sinon le notifieur a des angles morts) :

- **Mapping rôle↔composant NON 1:1** : `platform-cnpg` porte 4 composants,
  `platform-s3-bucket` en porte 3 (`s3-backing-{loki,cnpg,mlflow}`). La famille
  2 doit **tolérer un rôle multi-composant** ET vérifier que **CHAQUE**
  composant du rôle est référencé (sinon un rôle masque l'oubli d'un de ses
  composants).
- **`platform-s3-bucket` n'est JAMAIS importé par un PLAYBOOK** : il est tiré
  par `include_role` **RÔLE→RÔLE** imbriqué (dans
  `platform-{loki,cnpg,mlflow}`). Le check **doit scanner les `import_role`
  rôle→rôle aussi**, sinon faux positif « rôle mort ».

### 3. Déclencheur de re-vérification

Le déclencheur de re-vérification est un **hook lefthook** : quand
`bootstrap/roles/` change, le check re-tourne en local — au plus près du geste
qui peut introduire la divergence (un rôle ajouté/retiré sans toucher le
graphe). Le check tourne **aussi** en CI (`pnpm lint:topology`, à côté de
`pnpm lint:contract`).

## Conséquences

**Fin de la synchro humaine des 3 tables.** Le graphe, sa projection nestor et
le signal de santé dérivent d'**une seule source** ; le notifieur **attrape «
Marquez oublié »** au lieu de le laisser passer jusqu'au verdict mensonger.

**Graphe testable sans cluster.** `nestor/graph.py` est du Python pur : pytest
le couvre (ordres, clôtures, périmètres) **sans cluster** — la byte-identité
avec le bash est prouvée par `rollback.bats` rejoué.

**Un check CI de plus + un hook.** `pnpm lint:topology` (à côté de
`pnpm lint:contract`) et un hook lefthook sur `bootstrap/roles/`. Coût
d'entretien modeste, sur le modèle déjà éprouvé de `check_contract.py`.

**Réserve honnête — le check est NÉCESSAIRE mais PAS SUFFISANT seul.** Les
énumérations de phases vivent **à 6 endroits** : `rollback-lib.sh`,
`nestor/layers.py`, `_LAYER_SIGNAL`, `KNOWN_PHASES`, `PHASE_PLAYBOOK`+labels, et
Ansible. Le check ne couvre que rôle↔composant + signal↔rôle : un « Marquez »
retiré d'un **label** ou de `KNOWN_PHASES` passerait sous le radar. **La
robustesse durable exige de FUSIONNER ces tables comme projections du graphe
unique** (objet du plan de migration), **pas seulement d'ajouter le check à
côté**. Le check est le filet immédiat ; la fusion est la cible.

**Angles morts connus** (à documenter, hors périmètre du check initial) :

- **`redcap.yaml`, playbook orphelin** : il importe `platform-registry` /
  `platform-build-images` mais `redcap` n'est ni composant ni phase — un nouveau
  playbook applicatif peut exister **hors graphe** sans déclencher d'erreur.
- **`platform-build-images` multi-import** : **UN** rôle sert **N** builds
  (tags/contextes différents). Les familles 1-2 doivent gérer ce multi-import,
  sinon faux positif/négatif dans le notifieur même censé attraper l'oubli.

**Mise en œuvre incrémentale, prouvée au banc.** Le graphe est d'abord porté **à
côté** du bash (byte-identité prouvée par `rollback.bats`→pytest), puis les deux
ponts subprocess (`layers._rb`, `roundtrip._rollback_lib_call`) basculent sur
`graph.py`, puis `check_topology.py` arrive en CI. Chaque lot est re-prouvé par
un run banc ([ADR 0034](0034-validation-e2e-from-scratch.md) /
[ADR 0052](0052-reproductibilite-des-resultats.md)).

## Voir aussi

- [ADR 0017](0017-langage-des-scripts.md) — Langage des scripts (Python testé :
  porter le graphe en dataclass garde pytest comme garde-fou ; raison du « pas
  de YAML »).
- [ADR 0023](0023-plateforme-exemple-generique.md) — Valeurs génériques (noms de
  rôles/composants/phases sont des exemples).
- [ADR 0043](0043-contrat-interface-cluster-atlas.md) — Contrat d'interface
  (`check_contract.py`, le **modèle du check-qui-notifie** calqué ici).
- [ADR 0066](0066-rollback-atomique-graphe-composants.md) — Rollback atomique :
  graphe de composants unique (**implémenté en Python** par cet ADR, plus en
  bash).
- [ADR 0069](0069-topology-layers-dag-grain-phase.md) — `topology.layers` (DAG
  au grain phase ; projeté par `phase_deps`, désormais pur Python).
- [ADR 0083](0083-layers-source-unique-de-l-ordre.md) — Layers, source unique de
  l'ordre (le **module Python EST cette source** ; plus de subprocess bash).
- [ADR 0034](0034-validation-e2e-from-scratch.md) /
  [ADR 0052](0052-reproductibilite-des-resultats.md) — Validation e2e /
  reproductibilité (byte-identité prouvée, lots re-prouvés au banc).

---
