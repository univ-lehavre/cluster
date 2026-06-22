# Plan — `nestor` lit l'état réel d'un cluster prod (ADR 0090)

## État

> **État : Brouillon** (2026-06-22) · **Fonde :
> [ADR 0090](../decisions/0090-nestor-pilote-la-prod.md)** (Proposed).
>
> `Proposed` ⇒ **pas d'implémentation** tant que l'ADR n'est pas `Accepted` (ADR
> 0057 §plans). Ce plan cadre le travail ; il ne le lance pas.

## Objectif

Rendre `nestor preview` (et la lecture d'état) **honnête sur un cluster prod** :
quand `target_kind: prod`, l'état réel est lu via `kubectl` (nœuds + couches),
pas via les VMs Lima. Sans abaisser l'isolation banc/prod (ADR 0053/0084) :
**lecture seule**, aucune voie de mutation prod ouverte.

## Périmètre

- **Inclus** : `preview` et les sondes d'état réel en `target_kind: prod` ;
  réutilisation des sondes `discover` (ADR 0074) ; choix du kubeconfig prod sûr.
- **Exclu** (décision ultérieure, hors ADR 0090) : faire **muter** la prod par
  `nestor` (`up`/`next`/`remove`). L'install prod reste **Ansible/RUNBOOK**.

## Le point dur (diagnostic du 2026-06-22)

Trois fonctions de `scripts/topology.py` à conditionner par `target_kind` :

| Fonction            | Comportement actuel (prod)               | Cible (prod)                                     |
| ------------------- | ---------------------------------------- | ------------------------------------------------ |
| `_real_vms`         | `return []` → « VMs à créer : dirqual\*» | section VMs **omise** (machines hors nestor)     |
| `_ready_nodes`      | gaté → vide sans `KUBECONFIG`            | lit `kubectl get nodes` via kubeconfig prod      |
| `_bench_kubeconfig` | `/dev/null` hors banc                    | `kubeconfig:` **déclaré dans la topo** (lecture) |
| couches présentes   | non lues (PLAN = tout à monter)          | déduites du réel K8s (sondes `_discover_*`)      |

## Étapes (chacune prouvable SANS toucher la prod)

### Étape 0 — Convention : un kubeconfig par stack, hors dépôt

Un fichier **`~/.kube/<stack>.config`** par cible (ex.
`~/.kube/dirqual.config`), **hors de l'arbre du dépôt** (credentials réels,
jamais commités). Rapatriement depuis le control plane (manuel/documenté) :
copier `/etc/kubernetes/admin.conf` de `dirqual1` → `~/.kube/dirqual.config`,
vérifier `kubectl --kubeconfig ~/.kube/dirqual.config get nodes`. Documenter
dans le RUNBOOK. _(Aucune modification de fichier versionné : c'est de la config
locale opérateur.)_

### Étape 1 — Champ `kubeconfig:` dans la topologie + résolution sûre

(a) **Schéma** : ajouter un champ optionnel **`kubeconfig: <chemin>`** au modèle
de topologie (`cluster_topology/model.py` + schéma de validation) ; le
`*.example` documente l'usage (`~/.kube/<stack>.config`), le `.yaml` réel
(gitignoré) le renseigne (ADR 0023). (b) **Résolution** : étendre
`_bench_kubeconfig`/`_kubectl_env` — en `target_kind: prod`, priorité
`KUBECONFIG` exporté → `kubeconfig:` de la topo → **échec clair** (jamais
`~/.kube/config`). `/dev/null` anti-mutation conservé pour le banc. **Preuve** :
tests unitaires (parsing du champ + ordre de résolution, stub env), aucun appel
réseau.

### Étape 1bis — Confirmation interactive + rapatriement assisté

(a) **Confirmer la cible** : avant une commande prod, lire l'endpoint API + les
nœuds vus (kubectl, fonction pure stubable) et **demander confirmation** («
stack `<nom>` → `<endpoint>` `<nœuds>` ? [y/N] ») ; négatif ⇒ arrêt. En
`--no-input`/CI : **vérification stricte** endpoint attendu vs résolu (pas de
prompt). (b) **Rapatriement assisté** : si le `kubeconfig:` est
absent/injoignable, proposer la copie
`scp <control>:/etc/kubernetes/admin.conf → ~/.kube/<stack>.config`
(control-plane lu dans `bootstrap/hosts.yaml`) + re-vérif `get nodes`.
**Preuve** : tests unitaires (rendu de la confirmation, parsing endpoint/nœuds,
construction de la commande de rapatriement) — tout stubé, aucun appel réseau ni
mutation cluster.

### Étape 2 — État réel polymorphe selon `target_kind`

`preview` : en `prod`, ne pas appeler `_real_vms` (omettre la section VMs) ;
appeler `_ready_nodes` (kubectl) + les sondes couches. Fonction pure de
composition de l'« état réel » testée avec un kubectl **stubé** (sortie
`get nodes`/`get ns` injectée). **Preuve** : `pnpm test:python`.

### Étape 3 — Couches présentes déduites du réel K8s

Brancher les sondes `discover` (ADR 0074 : namespaces, CRD, SC, ressources) dans
le calcul du PLAN : une couche dont les marqueurs réels existent est
**présente** (pas « à monter »). Mapping couche→marqueur (ex.
`ceph`→`cephcluster`, `dataops`→ns `dagster`/`marquez`, `mlflow`→ns `mlflow`).
**Preuve** : table de mapping testée ; sur la prod réelle (lecture seule,
manuel) `preview` doit refléter l'état déjà constaté (`ceph…mlflow` : seules
dataops+mlflow absentes).

### Étape 4 — Garde-fou anti-mutation (test d'isolation)

Test prouvant qu'une lecture prod (`preview`) **ne peut pas** déclencher une
écriture (pas d'appel `apply`/`launch_phase`/`limactl` en chemin lecture).
Préserve ADR 0053. **Preuve** : test unitaire + revue.

### Étape 5 — Doc

Documenter l'état réel **polymorphe** (`lima` = VMs+nœuds ; `prod` = nœuds K8s)
dans la vue outils + l'aide `preview`. Mettre à jour le RUNBOOK (nestor sait
**lire** la prod ; il ne la **monte** pas — Ansible).

## Vérification (transverse)

- **Sans prod** : `pnpm test:python` (sondes pures + stubs kubectl),
  `pnpm lint`.
- **Banc inchangé** : `nestor preview` sur stack `banc`/`lima` rend le même
  résultat qu'avant (non-régression).
- **Lecture prod réelle (manuel, lecture seule)** : `nestor preview` sur stack
  `dirqual` reflète `kubectl get nodes`/`get ns` — plus de « VMs à créer », PLAN
  = seules les couches réellement absentes.

## Risques & parades

- **Régression d'isolation (ADR 0053)** → périmètre lecture seule strict + test
  anti-mutation (étape 4) ; mutation prod **hors scope**.
- **Confusion état polymorphe** → doc explicite + messages `preview` clairs.
- **Mauvais kubeconfig prod** → cible **nommée et vérifiée**, jamais implicite.
