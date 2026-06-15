# 0074 — `cluster discover` : reconstruire un `topology.yaml` depuis un cluster réel

## Statut

Proposed (2026-06-15)

Inverse de `generate` ([ADR 0056](0056-modele-declaratif-topologies.md)) ;
réutilise les sondes de `preview`, le DAG des couches
([ADR 0069](0069-topology-layers-dag-grain-phase.md)) et la classification de
santé existante (`bootstrap/lib/health-classify.sh`, `bootstrap/state.sh`) ;
frontière bash/Python de l'[ADR 0049](0049-doctrine-choix-outil-par-action.md).

## Contexte

L'outil est aujourd'hui **uni-directionnel** : on _déclare_ un `topology.yaml`,
et `generate`/`up` en _dérivent_ l'infra. L'inverse n'existe pas : à partir d'un
cluster **déjà en place** (dont on a un accès SSH / kubeconfig), il n'y a aucun
moyen de **reconstruire la déclaration** — ses nœuds et rôles, ses couches
montées, son backend de stockage, son mode d'exposition.

Or trois besoins le réclament :

1. **Adopter un cluster non déclaré** : reprendre un cluster monté à la main (ou
   par une version antérieure de l'outil) sans le détruire — produire son
   `topology.yaml` pour le piloter ensuite par `up`/`preview`/`scale`.
2. **Auditer la dérive** : comparer ce qui TOURNE à ce qui est DÉCLARÉ — un
   composant présent mais hors topologie est un drift à expliquer.
3. **Détecter l'inconnu** : un namespace / Deployment / StorageClass que le
   catalogue ne connaît PAS doit être **signalé**, pas perdu — sinon la
   topologie reconstruite ment par omission (honnêteté,
   [ADR 0052](0052-reproductibilite-des-resultats.md)).

**Constat fondateur : la moitié de la découverte EXISTE DÉJÀ.**
`cluster preview` détecte et réconcilie une partie du réel, couche par couche :

| Sonde existante                        | Détecte                       | Utilisée par              |
| -------------------------------------- | ----------------------------- | ------------------------- |
| `_real_vms()` (limactl)                | VMs réelles                   | preview RÉEL, destroy     |
| `_ready_nodes()` (kubectl get nodes)   | nœuds Ready                   | preview, scale, scenarios |
| `_observed_layers()` + `_LAYER_SIGNAL` | couches applicatives montées  | preview PLAN, scenarios   |
| `classify_refresh()`                   | réconciliation réel ↔ déclaré | preview                   |

`discover` n'est donc **pas une feature from-scratch** : c'est l'**agrégation de
ces sondes** + quelques sondes manquantes, **émise en `topology.yaml`** au lieu
d'être affichée.

## Décision

**Ajouter une commande `cluster discover` qui sonde un cluster réel (via le
kubeconfig / un accès SSH au nœud) et émet un `topology.yaml` reconstruit.**
C'est l'INVERSE de `generate` (generate : déclaration → infra ; discover : infra
→ déclaration). Six points.

### 1. Reconstruction COMPLÈTE (nœuds/rôles + layers + backend + exposition)

`discover` détecte les quatre dimensions de la topologie (ADR 0056/0069) :

- **nœuds & rôles** : `kubectl get nodes` + labels
  (`node-role.kubernetes.io/control-plane`, taints) → `nodes[].roles` (control /
  worker / hyperconvergé). Étend `_ready_nodes()` (qui ne lit que Ready) par la
  lecture des rôles.
- **layers** : les couches montées via `_observed_layers()` + `_LAYER_SIGNAL`
  (déjà codé pour `preview`/`scenarios`), reprojetées en `layers: [...]` (le set
  d'entrée du DAG, ADR 0069) — pas la clôture, mais les couches **réellement
  présentes**.
- **backend de stockage** : présence d'une StorageClass `rook-ceph-*` → `ceph` ;
  `local-path` → `local-path` (sonde `kubectl get storageclass`).
- **exposition** : présence de CRs `Gateway`/`CiliumLoadBalancerIPPool` →
  `gateway` ; `hostPort` sur les workloads → `hostport` ; sinon `none` (ADR
  0071). Inverse de la dérivation `exposition_mode`.

#### Taxonomie des ressources sondées (par famille)

Un cluster Kubernetes gère bien plus que `nodes`/`pods` ; `discover` parcourt
les **familles de `kind` suivantes**, chacune mappée à une dimension de la
topologie ou — à défaut — énumérée comme inconnue (§2) :

| Famille          | `kind` sondés                                                           | Sert à                                                 |
| ---------------- | ----------------------------------------------------------------------- | ------------------------------------------------------ |
| **Cluster**      | `Node`                                                                  | nœuds & rôles (labels/taints control-plane)            |
| **Workloads**    | `Deployment`, `StatefulSet`, `DaemonSet`, `Job`, `CronJob`              | couches montées (mappées `_LAYER_SIGNAL`) ou inconnues |
| **Organisation** | `Namespace`                                                             | regroupement ; un ns hors catalogue → `unknown`        |
| **Réseau**       | `Service`, `Ingress`, `Gateway`/`HTTPRoute`, `Cilium*` (LBPool/L2/CNP)  | mode d'exposition + policies réseau                    |
| **Stockage**     | `StorageClass`, `PersistentVolumeClaim`, CRs `Ceph*`/CNPG `Cluster`     | backend (ceph vs local-path) + volumes                 |
| **Config**       | `ConfigMap`, `Secret`                                                   | (non reconstruit : signalé en présence/compte seul)    |
| **RBAC / sécu**  | `ServiceAccount`, `Role`/`ClusterRole`(+Bindings), labels PSA           | durcissement constaté (informatif)                     |
| **Extension**    | **`CustomResourceDefinition`** (le PIVOT), `HPA`, `PodDisruptionBudget` | identifie les **opérateurs/plateformes** installés     |

Le **pivot, ce sont les CRDs** : la présence d'une CRD
`cilium.io`/`ceph.rook.io`/
`postgresql.cnpg.io`/`argoproj.io`/`gateway.networking.k8s.io` est le signal le
plus fiable de « telle plateforme tourne » — plus robuste qu'un nom de
Deployment (qui peut varier). `discover` croise donc CRDs **et** workloads pour
mapper une couche ; ce qui ne matche aucun catalogue tombe en `unknown` (§2).

### 2. L'INCONNU est détecté et signalé, jamais ignoré

Principe non négociable : ce que le **catalogue ne connaît pas** (un namespace,
un Deployment, une StorageClass, une CRD hors `_LAYER_SIGNAL` / hors briques
connues) est **listé explicitement** dans la sortie — sous un bloc `unknown:`
(commenté dans le YAML émis) ou un rapport séparé. Raisons :

- **fidélité** : une topologie reconstruite qui tait un composant existant est
  fausse par omission (ADR 0052 : honnêteté du réel constaté) ;
- **drift / squatteur** : un composant non géré par le modèle est précisément ce
  qu'un audit doit faire remonter (besoin 2) ;
- **évolution du catalogue** : l'inconnu d'aujourd'hui est la brique à ajouter
  demain — le signaler alimente `_LAYER_SIGNAL`.

La distinction est binaire et tracée : **connu → mappé** (nœud/layer/backend/
exposition) ; **inconnu → énuméré** (ns/kind/nom + version si lisible).

### 3. Bilan de SANTÉ du cluster (pas seulement sa déclaration)

Pendant qu'il sonde tout le réel, `discover` constate aussi l'**ÉTAT** et émet
un **bilan de santé** — la déclaration reconstruite (§1) dit _ce qui est là_, le
bilan dit _si ça va_. Il agrège, sans rien réinventer, les primitives de santé
existantes (`bootstrap/lib/health-classify.sh`, `cluster_topology/gates.py`) :

- **nœuds** : Ready / NotReady (classification `health-classify.sh`,
  `classify_nodes_ready`) ;
- **workloads** : pods Running vs CrashLoopBackOff / Pending / ImagePullBackOff
  (par couche mappée — un layer « présent » mais en CrashLoop est signalé
  DÉGRADÉ, pas sain) ;
- **stockage** : PVC `Bound` vs `Pending` (`gate_pvc_bound`, `gates.py`) ; OSD
  up en backend ceph (`gate_osds_up`) ;
- **CR d'opérateur** : `.status` des CRs gérés (CephCluster HEALTH_OK, CNPG
  Cluster ready) — la santé se lit sur le `.status` du CR, pas par un exec
  (mémoire `[[k8s-exec-vs-k8s-info-gate]]`).

Sortie : un verdict par dimension (`sain` / `dégradé` / `absent`) + le détail
des anomalies. Read-only (aucune mutation), code 0 informatif. Cohérent avec
`bootstrap/state.sh` (couche santé existante) : `discover` en est la **vue
agrégée et portable**, pas un second outil de diagnostic.

### 4. Accès : kubeconfig d'abord, SSH pour ce que l'API ne dit pas

La plupart des sondes passent par le **kubeconfig** (`kubectl get` — déjà le
canal de `preview`). L'**accès SSH** (au sens ADR 0048 / `access.sh`) sert ce
que l'API Kubernetes n'expose pas : versions de paquets nœud (containerd,
kubelet), état du durcissement hôte, disques bruts (backend Ceph). SSH est
**optionnel** : sans lui, `discover` reconstruit ce que l'API permet et **marque
le reste `inconnu/non-sondé`** (pas d'invention). C'est un outil DÉFENSIF sur
SON cluster (accès légitime), pas un scanner hostile — distinct de l'offensif
(ADR 0025).

### 5. Sortie : un `topology.yaml` repris par le reste de l'outil

`discover` émet un `topology.yaml` **valide** (qui passe `stack validate`,
ADR 0056) sur stdout ou `-o <fichier>`. Boucle vertueuse : `discover` →
`validate` → `preview` (compare au réel) → `up` (réconcilie). La sortie porte
les valeurs **génériques** quand c'est une dimension d'instance (IP/plages →
`.example`-style, ADR 0023) — on ne fige pas une IP réelle dans un fichier
potentiellement versionné.

### 6. Façade fine, sondes réutilisées (ADR 0049/0017)

`cmd_discover` est une **façade** : elle ORCHESTRE les sondes (kubectl/SSH =
bash irréductible, ADR 0049) et assemble un dict de topologie via la **logique
pure** existante (model/layers). Aucune sonde nouvelle réinventée là où
`preview` en a déjà une : `_real_vms`/`_ready_nodes`/`_observed_layers` sont
**partagées**, pas dupliquées (mêmes fonctions). Seules s'ajoutent : lecture des
**rôles**, du **backend**, de l'**exposition réelle**, et l'**énumération de
l'inconnu**.

## Conséquences

- Un cluster non déclaré devient **pilotable** : `discover -o topology.yaml`
  puis `stack select` → tout l'outil (preview/up/scale) s'applique.
- L'**audit de dérive** devient trivial : `discover` vs `topology.yaml` déclaré.
- L'inconnu ne se perd jamais → la reconstruction est **honnête** et alimente
  l'évolution du catalogue (`_LAYER_SIGNAL`).
- ~70 % du code existe déjà (sondes de `preview`) → périmètre neuf borné : 3
  sondes (rôles/backend/exposition) + l'énumération de l'inconnu + l'émission
  YAML.
- Réutilise le DAG (ADR 0069) et le modèle (ADR 0056) sans nouveau graphe.
- Preuve (ADR 0034/0052) : `discover` sur le banc → un `topology.yaml` qui,
  repassé par `up`, reproduit le même cluster (`changed=0`) ; un composant hors
  catalogue posé à la main apparaît bien dans `unknown:`.

## À revoir si

- Le besoin glisse vers la **reconnaissance sans accès** (scan réseau d'un
  cluster tiers, fingerprint de versions à distance) : ce serait de l'offensif
  (ADR 0025, banc jetable + autorisation), une autre décision — `discover` reste
  **défensif, sur SON cluster, avec accès légitime**.
- L'inconnu détecté devient récurrent (même brique re-signalée) → l'ajouter au
  catalogue (`_LAYER_SIGNAL` / briques connues) plutôt que de le laisser en
  `unknown`.

## Alternatives écartées

- **Pas de discover (statu quo)** : un cluster non déclaré reste impilotable ;
  rejeté — le besoin d'adoption/audit est réel.
- **Reconstruire SANS signaler l'inconnu** : topologie fausse par omission,
  audit aveugle ; rejeté (cf. point 2, ADR 0052).
- **Un scanner réseau (sans accès)** : franchit la frontière défensif → offensif
  (ADR 0025) sans le besoin réel (on a l'accès SSH/kubeconfig) ; hors périmètre.
- **Dupliquer les sondes de `preview`** : deux chemins de détection qui
  dériveraient (même piège que le double-graphe d'ADR 0066/0069) ; rejeté — les
  sondes sont PARTAGÉES.
