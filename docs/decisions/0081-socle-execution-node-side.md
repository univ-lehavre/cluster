# 0081 — Socle d'exécution node-side : une brique `node_exec`, deux usages (`discover`, `remove`)

## Statut

Accepted (2026-06-19) — livraison INCRÉMENTALE. Le code est livré
(`nestor/nodeside.py`, usages `discover`/`remove`) ; promu depuis
`Proposed (2026-06-16)`.

Prolonge [ADR 0079](0079-rollback-par-decouverte-appartenance.md) (rollback par
découverte) et [ADR 0074](0074-cluster-discover-reconstruire-topologie.md)
(`discover` : lire le réel). Le rollback par découverte couvre tout le k8s
**namespacé** ; il restait l'**irréductible node-side** (disques, CRI, CNI,
kubeconfig) que l'API Kubernetes ne porte pas. Borné par
[ADR 0049](0049-doctrine-choix-outil-par-action.md) (SSH/exécution de CLI = bash
irréductible) et [ADR 0053](0053-isolation-multi-cible-banc-prod.md) (cible
banc/prod).

## Contexte

Deux features distinctes ont besoin du **même geste** — exécuter une commande
**sur un nœud** (pas via l'API k8s) — et ce geste existe DÉJÀ, dispersé :

- **`discover`** ([ADR 0074](0074-cluster-discover-reconstruire-topologie.md))
  reconstruit `topology.yaml` depuis l'API k8s. Mais (1) il EXIGE un kubeconfig
  déjà sous la main — or la première fois, il faut aller le CHERCHER sur le
  control-plane ; (2) il ne voit PAS le node-side (containerd, Cilium posé par
  `cni.sh`, disques/montages, durcissement hôte) car ces états ne sont pas des
  objets Kubernetes.
- **`remove`** ([ADR 0079](0079-rollback-par-decouverte-appartenance.md), étape
  A) défait tout le k8s namespacé par découverte. Mais le **wipe node-side
  Ceph** (effacer `/var/lib/rook` + signatures FS des disques data) reste au
  chemin TABLE — c'est la SEULE raison pour laquelle la table `rollback-lib.sh`
  survit.

Les primitives node-side existent, en bash, déjà éprouvées :

- `vm_sh vm cmd…` (`bench/lima/lib.sh:70`) — exécute sur une VM via
  `limactl shell` (le banc Lima **n'utilise pas SSH brut**) ;
- `fetch_kubeconfig_node vm out api_port ctx` (`lib.sh:310`) —
  `sudo cat /etc/kubernetes/admin.conf` + réécriture de l'endpoint ;
- `storage/ceph/cleanup.sh` (paramétré par
  `NVME_BLOCK_DEVICE`/`DATA_DEVICE_GLOB`) — invoqué par `rollback-lib.sh:800`
  via `vm_sh … bash -s < cleanup.sh`.

Côté prod, le transport est différent : **SSH direct** via l'inventaire Ansible
(`bootstrap/hosts.yaml`, `ansible_user: debian`, `ansible_host: <ip>`), pas
`limactl`. Aujourd'hui ce node-side prod passe par des playbooks Ansible, pas
par une brique unifiée.

**Le problème** : trois besoins (rapatrier le kubeconfig, lire le node-side pour
`discover`, wiper le node-side pour `remove`) reposent sur le même geste — «
exec sur un nœud » — mais il n'y a pas de **brique unique** ; le transport
(limactl vs SSH) est mêlé à chaque appelant, et Python ne sait pas l'invoquer
(seul `nestor/ha.py` appelle `limactl shell`, en dur, Lima-only).

## Décision (proposée)

Extraire une **brique d'exécution node-side unique**, `node_exec`, qui abstrait
le **transport** (limactl pour `target_kind: lima`, SSH direct pour `prod`)
derrière une signature stable, et la faire consommer par les DEUX features. Cinq
points.

### 1. `node_exec(node, argv, *, target_kind)` — transport abstrait, bash

Une fonction bash unique (dans `bench/lima/lib.sh` ou un `node-exec.sh` dédié)
prend un **nœud** (nom logique de l'inventaire), un **argv**, et le
`target_kind` ; elle route :

- `lima` → `limactl shell <node-vm> -- <argv>` (l'existant `vm_sh`, généralisé)
  ;
- `prod` → `ssh <ansible_user>@<ansible_host> -- <argv>`, hôte/clé résolus de
  l'inventaire (`bootstrap/hosts.yaml`, mêmes champs qu'Ansible).

Le transport est l'unique différence ; tout le reste (sudo, env, stdin d'un
script via `bash -s`) est identique. C'est l'irréductible bash de l'ADR 0049 —
on NE le porte PAS en Python ; on l'EXPOSE proprement pour que Python l'appelle
(un sous-processus, comme `runner.launch_phase` appelle ansible-runner).

### 2. La liste de nœuds vient de l'inventaire — source unique, jamais codée

`node_exec` résout `<node> → (transport, hôte, user, clé/ssh.config)` depuis la
**même source que tout le reste** : l'inventaire de la topologie active
(`bench/lima/.work/inventory.yaml` pour Lima, `bootstrap/hosts.yaml` pour la
prod, ADR 0053). Pas de seconde liste de nœuds. Le `.example` versionné
(`hosts.example.yaml`) emploie des valeurs génériques `cp1`/`node1`…`node4`
(ADR 0023) ; les vrais noms/IP vivent dans l'inventaire gitignoré.

### 3. Usage A — `discover` rapatrie le kubeconfig (résout le chicken-and-egg)

`nestor discover --cp <node>` (ou dérivé de l'inventaire) appelle `node_exec`
pour exécuter `fetch_kubeconfig_node` : rapatrie `/etc/kubernetes/admin.conf`,
réécrit l'endpoint, dépose le kubeconfig en local. `discover` n'EXIGE plus un
kubeconfig préalable — il sait aller le chercher. Esprit ADR 0074 poussé au bout
: **ne rien présumer, pas même la clé d'accès**.

### 4. Usage B — `discover` lit le node-side ; `remove` le wipe

Le MÊME `node_exec` sert les deux verbes (miroir « health/remove » de
l'ADR 0079) :

| Geste              | Via `node_exec`, sur chaque nœud                                 |
| ------------------ | ---------------------------------------------------------------- |
| `discover` (lire)  | version containerd, CNI installé, disques/montages, durcissement |
| `remove` (défaire) | `cleanup.sh` (wipe `/var/lib/rook` + signatures FS disques data) |

La logique reste PURE et testable (ADR 0049/0074 §6) : `node_exec` rend des
octets bruts (stdout du nœud) ; le mapping (« cette sortie `lsblk` → tels
disques », « cette version → tel CRI ») est du Python pur, stubable sans nœud.
Côté `remove`, le wipe quitte la table `rollback-lib.sh` → la dernière raison de
survie de la table disparaît une fois ce point livré (objectif **zéro table**,
ADR 0079).

### 5. Garde-fous PRÉSERVÉS — cible banc, jamais la prod par accident

`node_exec` hérite des gardes existants : la cible (banc vs prod) est dérivée du
`target_kind` de l'inventaire ACTIF, validée par `_assert_bench_target` /
`_assert_inventory_safe` (ADR 0053) AVANT tout exec mutant ; un wipe node-side
exige `BANC_JETABLE=1` (ADR 0054). On ne wipe JAMAIS un disque de prod par un
chemin de banc — l'inventaire disjoint reste le filet.

## Conséquences

- Une seule brique node-side : la dispersion (`vm_sh`, `_vm_exec` Lima-only,
  `fetch_kubeconfig_node`, l'invocation cleanup.sh) converge ; le transport
  limactl/SSH n'est résolu qu'à UN endroit.
- `discover` devient autonome (rapatrie sa propre clé) et complet (node-side,
  pas que l'API) — il reconstruit vraiment « tout le réel ».
- `remove` retire le node-side de la table → la table peut DISPARAÎTRE (zéro
  table) une fois le node-side découvert/wipé par cette brique.
- Coût : exposer un transport SSH/limactl à Python (sous-processus borné), et
  paramétrer les devices par profil (Lima `vd*` vs prod `sd*/nvme*`) —
  paramètres DÉRIVÉS du profil, jamais codés (ADR 0023/0065).
- Risque : un `node_exec` mal ciblé toucherait un nœud de prod. Mitigation : la
  cible vient de l'inventaire actif + gardes ADR 0053, et le wipe exige
  `BANC_JETABLE=1` ; la preuve node-side Ceph reste DIFFÉRÉE à un banc Ceph (ADR
  0034 : pas de preuve fabriquée sur local-path).

## Stratégie de livraison (incrémentale, prouvable, comme l'ADR 0079)

1. **`node_exec` + résolution inventaire** — la brique seule, prouvée sur le
   banc Lima (un `node_exec node1 -- hostname` rend le bon hôte). Pur : la
   résolution `<node> → cible` est testable sans nœud (stub inventaire).
2. **`discover` rapatrie le kubeconfig** — usage A, prouvé au banc : sans
   kubeconfig préalable, `discover` le récupère et lit l'API.
3. **`discover` node-side** — usage B lecture : CRI/CNI/disques/durcissement
   ajoutés au `topology.yaml` reconstruit (les sondes manquantes de l'ADR 0074).
4. **`remove` node-side** — usage B mutation : le wipe Ceph passe par
   `node_exec` ; `closure_has_nodeside` cesse de router vers la table. **Preuve
   DIFFÉRÉE** (banc Ceph requis, ADR 0034). À ce stade la table
   `rollback-lib.sh` peut être retirée.

Les étapes 1–2 sont prouvables sur le banc local-path actuel ; 3 partiellement ;
4 attend un banc Ceph. La table survit jusqu'à 4 — assumé, pas un renoncement.

## Alternatives écartées

- **Garder le node-side dans Ansible (playbooks) pour la prod, limactl pour le
  banc** : deux chemins parallèles qui divergent — c'est la dispersion actuelle.
  Une brique unique à transport abstrait évite la 2ᵉ source.
- **Tout porter en Python (paramiko/SSH natif)** : non — SSH/exec de CLI est
  l'irréductible bash de l'ADR 0049 ; Python l'APPELLE, ne le réimplémente pas.
- **Découvrir le node-side via un DaemonSet k8s (pas de SSH)** : possible pour
  la lecture (un pod privilégié lit `/host`), mais (1) ça n'aide pas à rapatrier
  le kubeconfig AVANT d'avoir un cluster, (2) le wipe de disques d'un nœud qu'on
  démonte ne peut pas dépendre d'un pod qui tourne dessus. SSH/limactl reste
  requis.

## À revoir si

- Le transport prod n'est pas que SSH (un fournisseur impose un agent/bastion) →
  `node_exec` gagne un 3ᵉ mode, la signature ne change pas.
- La preuve node-side Ceph reste inaccessible longtemps (pas de banc Ceph) →
  l'étape 4 reste différée ; les étapes 1–3 (discover) ont leur valeur propre et
  ne sont pas bloquées par 4.
