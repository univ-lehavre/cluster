# 0066 — Rollback atomique : composants + graphe de dépendances unique

## Statut

Accepted (2026-06-13)

## Contexte

Le rollback par phase ([ADR 0054](0054-rollback-par-phase-banc.md)) défait une
phase de `run-phases.sh` via une **table de périmètre** (`rollback-lib.sh` :
`rollback_phase_namespaces` / `_targeted_resources` / `_crd_groups` /
`_has_nodeside` / `_downstream`). Cette table est **indexée par phase** — mais
une phase est **composite** : `dataops` monte ~10 composants (registry,
cert-manager, operator CNPG, plugin Barman, instance CNPG, backing S3, Dagster,
Marquez…) vivant dans **5 namespaces** (`postgres`, `cnpg-system`, `dagster`,
`marquez`, + une OBC dans `rook-ceph`). La table doit **ré-énumérer à la main**
l'union de ces composants.

Ce modèle est **fragile par construction**, et un run réel l'a prouvé en cascade
:

- `rollback_phase_namespaces(dataops)` **oubliait `cnpg-system`** (l'operator
  CNPG survivait au rollback et **re-réconciliait** le Cluster pendant la
  destruction — drift bloquant) ;
- l'OBC `cnpg-backups` (dans `rook-ceph`) fut oubliée, puis rajoutée ;
- l'OBC `loki-buckets` de même
  ([#319](https://github.com/univ-lehavre/cluster/issues/319)) ;
- l'`ObjectStore` Barman (`postgres`) coinçait le ns en `Terminating`, rajouté
  après coup aux finalizers forcés.

Le motif n'est pas un bug isolé : **chaque composant d'une phase composite est
une occasion d'oublier une ressource**, découverte rétrospectivement par un run
qui laisse un résidu (coûteux). S'ajoutent deux défauts structurels :

- **deux graphes de dépendances parallèles**, tous deux manuels et au grain
  phase : `rollback_phase_downstream` (rollback-lib) et `_DEPENDENTS`
  (`roundtrip.py`, « validé à la main », explicitement non dérivé du premier) →
  **divergence latente** ;
- le périmètre d'une phase **agrégée** (`atlas-ceph`) n'existe qu'**en
  intension** (« on défait dans l'ordre inverse ») : il est _supposé_ être
  l'union correcte des tables atomiques — l'hypothèse même que les oublis
  ci-dessus invalident.

## Décision

**Déplacer l'unité du périmètre et du graphe de la PHASE (composite) vers le
COMPOSANT ATOMIQUE, et faire du graphe de dépendances atomique la SOURCE
UNIQUE.**

### Composant atomique

La plus petite unité dont le périmètre de rollback est **à la fois trivial** (≤
1 namespace propre + ses CRD propres + ses ressources hors-ns explicitement
attachées) **et complet** (tout ce qu'il pose, rien qu'un autre pose). Règle de
découpe :

- poser X crée un namespace que **personne d'autre** ne possède → X est atomique
  sur ce ns (`cnpg-operator` possède `cnpg-system`, `cnpg-cluster-pg` possède
  `postgres` : **deux composants distincts** — l'oubli de `cnpg-system` devient
  **structurellement impossible**) ;
- poser X dépose une ressource dans le ns d'un **autre** (OBC dans `rook-ceph`,
  plugin dans `cnpg-system`) → cette ressource est un **`targeted` explicite du
  composant qui la crée**, jamais un résidu du composant qui possède le ns.

### Trois invariants (testables sans banc, bats)

1. **Trivialité** : un composant a **au plus un** namespace propre.
2. **Complétude par ownership** : toute ressource hors-ns est attachée
   déclarativement à **son producteur** (OBC `cnpg-backups` → composant
   `s3-backing-cnpg`). Pas de ressource orpheline.
3. **Graphe unique** : un **seul** graphe atomique (composant → dépendances) est
   la source de vérité. Il dérive (a) l'ordre de montage d'un alias (tri
   topologique), (b) l'ordre de rollback (inverse), (c) la clôture descendante
   du `roundtrip` (transitive). `rollback_phase_downstream` **et**
   `roundtrip.py:_DEPENDENTS` sont **remplacés** par des dérivations de ce
   graphe — fin des deux sources.

### Phase = alias

`dataops`/`monitoring`/`gitops`/`atlas-ceph` ne sont plus des entités de premier
ordre côté périmètre : ce sont des **alias** désignant un sous-ensemble du
graphe atomique. Monter un alias = monter ses composants en ordre topologique ;
le défaire = clôture descendante en ordre inverse. **Le périmètre composite
n'est plus en intension : c'est l'union CALCULÉE des périmètres atomiques**
(garantie complète par l'invariant de complétude). Un composant peut être
conditionnel au profil (`seaweedfs` vs `s3-backing-loki`) ; la condition vit
**dans le composant** (`when:`), pas dans l'alias.

### Compatibilité doctrine

- **[ADR 0045](0045-chemins-installation-banc-couches.md)** (chemins nommés
  codés) : les alias **restent** des chemins nommés codés — définis comme
  expansion du graphe au lieu d'une séquence en dur. L'**API CLI de
  `run-phases.sh` ne change pas**
  (`up`/`bootstrap`/`ceph`/`dataops`/`atlas-ceph`… restent les noms publics).
- **[ADR 0054](0054-rollback-par-phase-banc.md)** : généralisé en **rollback par
  composant** (l'alias-rollback dérive la clôture). 0054 reste valable ; cet ADR
  le raffine.
- **[ADR 0023](0023-plateforme-exemple-generique.md)** : valeurs génériques
  inchangées. **« Corriger le code, pas l'état »** : la complétude est
  **prouvée** par un cycle `monte → rollback → état-propre` (zéro résidu) sur
  banc, pas supposée.

## Conséquences

- `rollback-lib.sh` : les fonctions `*_phase_*` deviennent `*_component_*` +
  `component_deps` (graphe) + `component_expand_alias` + `topo_sort` (pur,
  remplace un `_MOUNT_ORDER` en dur). `_STUCK_CR_KINDS` devient une **union
  dérivée** des CRD à finalizer des composants.
- `roundtrip.py` : supprime `_DEPENDENTS` et `_MOUNT_ORDER`, les **dérive** du
  graphe atomique de `rollback-lib.sh`. `closure()` opère sur composants. Fin de
  la seconde source de vérité.
- `run-phases.sh` : dispatch et noms publics **inchangés** ; en interne, un
  alias itère ses composants en ordre topologique.

### Migration incrémentale (le graphe ne casse rien avant d'être prouvé)

Cet ADR fonde un **plan** (`plan-rollback-atomique.md`) :

- **Lot 0-2 (CI seule, zéro banc)** : écrire le graphe atomique + les fonctions
  par composant **à côté** des fonctions par phase (rien retiré) ; tests bats
  des invariants (trivialité, acyclicité, déterminisme, et l'assertion qui
  aurait attrapé l'oubli `cnpg-system`) ; faire `roundtrip.py` **consommer** le
  graphe (fin de la 2ᵉ source). Aucune bascule du rollback réel.
- **Lot 3 (bascule alias par alias, avec banc)** : un alias dérive sa clôture du
  graphe ; commencer par `dataops` (oublis prouvés) ; **prouver par cycle
  monte→rollback→état-propre** (zéro résidu) avant de retirer l'ancien `case`.
- **Lot 4 (montage par graphe)** : l'ordre de montage dérive du tri topologique
  ; pré-condition vérifiée en lot 1 (le topo-sort **reproduit exactement**
  l'ordre codé actuel). Étape la plus risquée → en dernier, après que le
  rollback est atomique et prouvé. Un run `atlas-ceph` from-scratch inchangé
  valide ([ADR 0034](0034-validation-e2e-from-scratch.md)).

### Alternatives écartées

- **Garder le modèle par phase et compléter la table** : c'est ce qu'on faisait
  — chaque oubli rattrapé rétrospectivement par un run. Ne supprime pas la cause
  (granularité fausse).
- **Dériver le périmètre des rôles Ansible automatiquement** (introspection) :
  séduisant mais fragile (un rôle ne déclare pas toujours ses ressources
  hors-ns, ni l'ordre) ; un graphe **explicite** et testé est plus sûr qu'une
  introspection.
- **Tout réécrire d'un coup** : casse les chemins nommés et exige une re-preuve
  massive. La migration incrémentale (graphe en CI d'abord, bascule alias par
  alias avec preuve banc) tient l'invariant byte/état à chaque étape.
