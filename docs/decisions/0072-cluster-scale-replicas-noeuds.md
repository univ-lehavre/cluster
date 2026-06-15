# 0072 — `cluster scale` : ajuster les replicas au nombre de nœuds

## Statut

Proposed (2026-06-15)

## Contexte

Le dépôt monte des topologies de 1 à N nœuds (ADR 0023/0056). Les workloads
applicatifs sont versionnés avec un **nombre de replicas figé** dans le
manifeste — tous à `replicas: 1` aujourd'hui : `gitea`
(`platform/gitea/deployment.yaml:7`), `registry`
(`platform/container-registry/deployment.yaml:7`), `rstudio`
(`apps/rstudio/deployment.yaml:7`), `mailpit`
(`platform/mailpit/mailpit.yaml:23`). Ce `1` convient au banc mono-nœud et à
`socle.example`, mais **gâche un cluster multi-workers** : sur 4 nœuds Ready, un
Deployment à 1 replica n'utilise qu'un nœud et ne survit pas à sa perte.

Le besoin : **adapter le nombre de replicas applicatifs au nombre de workers
Ready**. C'est une capacité **dynamique** — elle dépend de l'état RÉEL du
cluster à un instant t (combien de nœuds répondent `Ready`), pas d'une intention
écrite dans `topology.yaml`.

Or l'outil a une frontière nette
([ADR 0056](0056-modele-declaratif-topologies.md) §2/§7) : il **génère** des
artefacts et **constate** un état, il ne **converge** jamais ; Ansible reste le
seul moteur idempotent. Le réel est **lu, jamais stocké**. La lecture du réel
existe déjà et est éprouvée : `_ready_nodes()` (`scripts/topology.py:448-476`)
renvoie les nœuds `Ready` via `kubectl get nodes`, avec repli sur le kubeconfig
du banc et double timeout (`--request-timeout` + `timeout=`) ; `cmd_preview`
l'affiche déjà dans sa section RÉEL (`scripts/topology.py:893,899`).

Deux modélisations s'affrontent.

1. **Le scaling comme COUCHE** du DAG déclaratif
   ([ADR 0069](0069-topology-layers-dag-grain-phase.md)). Une couche est un
   ENSEMBLE ordonné par le graphe de dépendances atomique (`rollback-lib.sh`,
   ADR 0066), montée une fois, idempotente, **dérivée du déclaré**
   (`declared_layers`, `cluster_topology/model.py:91-100`). Le nombre de
   replicas « bon » dépend du nombre de **workers Ready au runtime** — une
   donnée du RÉEL, pas du DAG. Mettre `scale` dans le DAG, ce serait y injecter
   une valeur qui change entre deux `kubectl get nodes` : mauvais fit (un DAG
   ordonne des briques déclarées, il ne lit pas le cluster).

2. **Le scaling comme COMMANDE** `cluster scale`, façade fine au-dessus de
   `_ready_nodes()`, qui DÉRIVE une cible de replicas du réel et l'applique.
   Plus naturel : c'est une opération de **runtime** (« ajuste-toi à ce qui
   tourne »), pas une **brique de montage** (« installe monitoring »). Calque
   `pulumi`/`k8s` familier : un verbe runtime distinct du cycle déclaratif.

Distinction structurante : **replicas ≠ `resources`**. Le bloc `resources` de la
topologie (`model.py:51,140` ; `topologies/ha-3cp.example.yaml:64-66` :
`cpus: 2`, `memory: 6GiB`) dimensionne les **VM Lima** (terrain local), pas les
replicas applicatifs. `scale` ne touche pas `resources` : il ajuste un compte de
pods, pas la taille des machines.

## Décision

**Le scaling est une COMMANDE `cluster scale`, PAS une couche du DAG.** Un verbe
de **runtime** (lit le réel, ajuste un compte), distinct du cycle déclaratif
`up`/`next`/`destroy` (monte des briques déclarées).

### 1. Pourquoi une commande, pas une couche

- Une couche est **déclarative et statique** : ordonnée par le DAG (ADR 0069),
  dérivée de `declared_layers` (`model.py:91-100`), montée à `up`. Le bon nombre
  de replicas dépend des **workers Ready au runtime** (`_ready_nodes()`,
  `topology.py:448`) — il change sans que `topology.yaml` change. Une valeur
  runtime n'a pas sa place dans un graphe de briques déclarées.
- `scale` n'a **aucune dépendance de DAG** : il ne se monte pas « après
  monitoring » ; il s'**applique quand l'opérateur le demande**, sur des couches
  déjà montées. Lui donner une place dans la séquence `up` serait arbitraire.
- La frontière ADR 0056 §7 (« on ne stocke pas de state, on le lit ») colle au
  modèle commande : `scale` **lit** `_ready_nodes()`, **calcule** une cible,
  **applique** ; il ne persiste rien (pas de champ replicas dans
  `topology.yaml`).

### 2. Ce que la commande ajuste

- **Cible = les Deployments applicatifs `stateless` à replicas pilotables** :
  par défaut `gitea`, `registry`, `mailpit`, `rstudio`. Liste **allowlistée**
  (table dans le paquet, comme `_LAYER_SIGNAL`, `topology.py:488-495`) : on ne
  scale QUE ce qu'on a explicitement déclaré scalable — jamais « tous les
  Deployments du cluster ».
- **Exclus par construction** (cf. §4) : StatefulSets (`loki`, `argocd` —
  `platform/loki/loki.yaml`, `platform/argocd/argocd.yaml`), workloads à HA
  gérée par opérateur (CNPG `instances: 3`,
  `platform/cloudnative-pg/cluster.yaml:26`), singletons (operators,
  provisioners), et tout le **control-plane**.

### 3. Lecture du réel et formule

- **Source du réel** : `_ready_nodes()` (`topology.py:448`) déjà éprouvé. On en
  dérive le nombre de **workers Ready** en croisant avec `worker_nodes`
  (`model.py:65-73`) + `hyperconverged_nodes` (`model.py:76-83`) : un nœud
  control+worker hyperconvergé **schedule** (le détaint, ADR 0007/0055) et
  compte donc comme capacité d'exécution, même s'il n'est pas dans
  `worker_nodes` (qui ne liste que les workers PURS).
- **Formule proposée (à valider)** :
  `replicas = clamp(workers_ready, min=1, max=PLAFOND_PAR_WORKLOAD)`. Variante
  HA : `replicas = min(workers_ready, 3)` (3 = quorum applicatif courant, borné
  par `max-replicas`). Linéaire et lisible ; pas de fonction exotique. La
  formule exacte est un **point à valider** (cf. ci-dessous).
- **Read-only par défaut** : `cluster scale` SANS `--apply` affiche le PLAN
  (workload → replicas actuels → cible dérivée), à la manière du PLAN de
  `cmd_preview` (`topology.py:918-928`) ; `--apply` exécute. Aucune mutation
  silencieuse (même posture que `up`/`destroy` : confirmation/`--yes`,
  `topology.py:944-955`).

### 4. Garde-fous

- **Jamais le control-plane** : la cible exclut tout pod control-plane ; la
  capacité comptée est celle des workers Ready (workers purs + hyperconvergés
  schedulables), pas les CP dédiés.
- **Jamais au-delà de la capacité** : un **plafond par workload** dans
  l'allowlist (`max-replicas`) borne la cible ; `replicas ≤ workers_ready` (pas
  plus de replicas que de nœuds pour exécuter, sinon des pods `Pending`). On NE
  scale PAS vers le bas en dessous de 1 (jamais 0 replica → service coupé).
- **Jamais les workloads stateful / opérés** : StatefulSets et clusters
  d'opérateur (CNPG, Ceph) hors périmètre — leur réplication est portée par
  l'opérateur (`instances: 3`), pas par un `kubectl scale` externe qui se
  battrait avec lui (même piège que apply-vs-patch, MEMORY idempotence).
- **Cohérence avec GitOps** : sur une couche `gitops` où ArgoCD réconcilie les
  manifestes (`platform/argocd/`), un `kubectl scale` direct est **écrasé au
  prochain sync** (git = source de vérité). `scale` AVERTIT si le workload est
  managé par ArgoCD et n'agit pas en aveugle — sinon le scaling est un drift
  éphémère, pas un résultat reproductible (ADR 0052).
- **Anti-blocage** : réutiliser le double timeout de `_ready_nodes()`
  (`topology.py:461,466`) — un cluster injoignable rend le PLAN vide, jamais un
  gel.

### 5. Place dans la CLI

`scale` est un **verbe top-level** du cycle de vie (à côté de
`preview`/`up`/`next`/`destroy`, `_DISPATCH` `topology.py:1392-1407`), routé par
une `cmd_scale` façade fine. La logique pure (dérivation cible = f(workers
Ready, allowlist), clamp, exclusions) vit dans le paquet `cluster_topology/`
(ADR 0017/0056 §2 : la logique testable hors I/O), testée sans cluster ; la
seule I/O réelle est `_ready_nodes()` + `kubectl scale`.

## Conséquences

- Le réel pilote le runtime sans polluer le déclaratif : `topology.yaml` ne
  gagne PAS de champ `replicas` (resterait faux dès qu'un nœud tombe). Le DAG
  ADR 0069 reste un graphe de briques déclarées, inchangé.
- `scale` réutilise `_ready_nodes()` (`topology.py:448`) et les dérivations de
  nœuds (`model.py:60-83`) — zéro nouvelle lecture du réel, zéro nouveau graphe.
- Manifestes inchangés (`replicas: 1` reste le défaut versionné, sûr pour le
  banc mono-nœud) ; `scale --apply` est l'override **runtime** explicite, jamais
  le défaut.
- Frontière ADR 0056 §7 respectée : lit/calcule/applique via `kubectl`, ne
  stocke pas de state. La mutation `kubectl scale` est une convergence
  **ponctuelle demandée**, distincte de la convergence idempotente d'Ansible
  (qui, elle, reste le moteur des couches).
- Preuve (ADR 0034/0052) : sur un banc multi-workers, `scale --apply` porte un
  workload à N replicas répartis ; un rejeu `scale` (cluster inchangé) ne change
  rien (idempotence runtime : cible == état → no-op).

## À revoir si

- Le besoin devient **continu** (réagir à un nœud qui tombe sans intervention) :
  alors ce n'est plus une commande ponctuelle mais un **contrôleur** (HPA piloté
  sur métriques, ou un opérateur maison) — sortir du modèle façade read-only.
- Les workloads passent **sous GitOps strict** (tout manifeste réconcilié par
  ArgoCD) : `scale` devrait alors écrire le replicas **dans git** (PR/commit) et
  laisser ArgoCD converger, plutôt que `kubectl scale` direct — bascule de
  l'impératif vers le déclaratif versionné.
- Un besoin de **scaling par couche** émerge (replicas dérivés par workload
  selon la couche) : la formule deviendrait une table dans l'allowlist plutôt
  qu'une fonction unique.

## Alternatives écartées

- **`scale` comme couche du DAG (ADR 0069)** : injecte une valeur runtime
  (workers Ready) dans un graphe de briques déclarées ; n'a aucune dépendance de
  DAG ; change entre deux lectures du cluster. Mauvais fit — rejeté au profit du
  verbe runtime.
- **Champ `replicas` déclaré dans `topology.yaml`** : fige une valeur qui
  devient fausse dès qu'un nœud tombe ; duplique l'information « combien de
  workers » déjà portée par `nodes`/`_ready_nodes()` ; contredit « le réel est
  lu, pas stocké » (ADR 0056 §7). Rejeté.
- **Scaler TOUS les Deployments du cluster** : touche operators, singletons,
  workloads stateful par accident. Rejeté au profit d'une **allowlist**
  explicite (parité avec `_LAYER_SIGNAL`).
- **`kubectl scale` direct sur les StatefulSets/CNPG** : se bat avec l'opérateur
  qui possède le compte (`instances: 3`) — même classe de bug que
  apply-vs-patch. Rejeté : la réplication des stateful reste à l'opérateur.
- **HPA (autoscaler) d'emblée** : réagit à des métriques de charge, pas au
  nombre de nœuds ; exige metrics-server + une politique de charge ;
  sur-dimensionné pour « adapter au nombre de workers ». Reporté (cf. « À revoir
  si »).
