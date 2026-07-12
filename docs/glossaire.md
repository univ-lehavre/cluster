# Glossaire

Ce dépôt décrit un **cluster Kubernetes hyperconvergé** (calcul + stockage sur
les mêmes machines) pour la recherche. Beaucoup de termes techniques y sont
employés ; cette page les définit en langage simple, dans l'ordre où un néophyte
les rencontre. Les définitions sont volontairement courtes et orientées « à quoi
ça sert ici », pas exhaustives.

> 💡 Si vous débutez, lisez d'abord **Cluster**, **Kubernetes**, **nœud**,
> **control plane / worker**, puis **conteneur**, puis la section Stockage.

## Concepts de base

### Conteneur (container)

Un programme empaqueté avec tout ce dont il a besoin pour tourner (code,
bibliothèques, config), isolé du reste de la machine. Plus léger qu'une machine
virtuelle. Une **image** est le modèle figé ; un **conteneur** est une instance
qui tourne.

### Cluster

Un ensemble de machines (`node1`, `node2`… selon la topologie) qui travaillent
ensemble comme une seule ressource. On y déploie des applications sans se
soucier de _quelle_ machine les exécute — le cluster décide.

### Nœud (node)

Une machine du cluster (un serveur, ou une VM sur le banc). Chaque nœud exécute
des conteneurs et, en topologie hyperconvergée, participe au stockage. Le nombre
de nœuds est un axe du catalogue
([ADR 0023](decisions/0023-plateforme-exemple-generique.md)), pas une valeur
figée.

### Hyperconvergence

Faire tourner sur les **mêmes** machines à la fois le calcul (les applications)
et le stockage (les disques de données), au lieu d'avoir des serveurs séparés
pour chaque rôle. Choix assumé ici — voir
[ADR 0007](decisions/0007-hyperconvergence-control-plane-osd.md).

## Kubernetes et le plan de contrôle

### Kubernetes (K8s)

Le « chef d'orchestre » du cluster : il décide où placer les conteneurs, les
redémarre s'ils tombent, gère le réseau et le stockage. On lui décrit l'état
souhaité (« je veux 3 copies de cette app »), il s'arrange pour l'atteindre.

### Control plane (plan de contrôle)

Le « cerveau » de Kubernetes : les composants qui prennent les décisions
(planification, suivi de l'état). Ici, un seul nœud joue ce rôle — un choix de
simplicité assumé, voir
[ADR 0002](decisions/0002-control-plane-unique-avec-endpoint.md).

### Worker (nœud de travail)

Un nœud qui exécute les applications (par opposition au control plane qui
décide). Ici les nœuds sont hyperconvergés : ils sont workers **et** hébergent
le stockage.

### etcd

La base de données du control plane : elle stocke **tout** l'état du cluster
(quelles apps, quelle config, quels secrets). Si etcd est perdu sans sauvegarde,
le cluster est perdu — d'où l'importance des **snapshots etcd** (voir
[`bootstrap/roles/etcd-backup/`](../bootstrap/roles/etcd-backup/)).

### kubeadm

L'outil officiel qui installe et initialise un cluster Kubernetes
(`kubeadm init` sur le control plane, `kubeadm join` sur les workers).

### kubelet

L'agent Kubernetes présent sur chaque nœud : il reçoit les ordres du control
plane et lance/arrête réellement les conteneurs localement.

### CRD (Custom Resource Definition)

Une extension de Kubernetes : un nouveau « type d'objet » que K8s ne connaît pas
de base. Rook et Ceph en ajoutent beaucoup (`CephCluster`, `CephObjectStore`…).

## Exécution des conteneurs

### CRI (Container Runtime Interface)

L'interface standard par laquelle Kubernetes parle au moteur qui exécute
réellement les conteneurs. Permet de changer de moteur sans changer Kubernetes.

### containerd

Le moteur d'exécution de conteneurs utilisé ici (derrière le CRI). C'est lui qui
télécharge les images et lance les conteneurs. Voir
[ADR 0005](decisions/0005-cri-containerd-via-depot-docker.md).

## Réseau

### CNI (Container Network Interface)

L'interface standard qui donne une adresse réseau à chaque conteneur et gère la
communication entre eux. Kubernetes ne fait pas le réseau lui-même : il délègue
à un « plugin CNI ».

### Cilium

Le plugin CNI choisi ici : il fournit le réseau entre pods, la sécurité réseau
et l'observabilité, en s'appuyant sur eBPF (une technologie du noyau Linux).

## Exposition réseau (comment on atteint un service depuis l'extérieur du cluster)

> Ces termes décrivent la chaîne qui rend une application **joignable depuis le
> réseau local** (jamais Internet ici). Vue d'ensemble :
> [architecture/exposition-reseau.md](architecture/exposition-reseau.md).

### kube-proxy / kubeProxyReplacement

Dans un Kubernetes « standard », un composant appelé **kube-proxy** programme
des règles réseau (iptables) pour aiguiller le trafic vers les bons conteneurs.
Cilium sait faire ce travail **lui-même**, en plus rapide (eBPF, directement
dans le noyau) : c'est le **kubeProxyReplacement**. On supprime alors
kube-proxy. Voir [ADR 0020](decisions/0020-exposition-reseau-tout-cilium.md).

### LoadBalancer / LB-IPAM

Un service de type **LoadBalancer** a besoin d'une **adresse IP fixe** par
laquelle on l'atteint. Sur un cloud, le fournisseur la donne ; sur nos machines
« nues » (bare-metal), personne ne la donne. **LB-IPAM** (IP Address Management)
est la fonction de Cilium qui **pioche une IP dans une réserve** (un « pool »
d'adresses) et l'attribue au service. Voir
[ADR 0020](decisions/0020-exposition-reseau-tout-cilium.md).

### Annonce L2 (L2 announcement / ARP)

Une fois l'IP attribuée, encore faut-il que le réseau **sache où la trouver**.
En mode **L2**, un nœud du cluster « crie » sur le réseau local (protocole
**ARP**) « cette IP, c'est moi ! ». Un seul nœud le fait à la fois ; si ce nœud
tombe, un autre prend le relais (bascule, _failover_) — ce n'est **pas** de la
répartition de charge. Voir
[ADR 0020](decisions/0020-exposition-reseau-tout-cilium.md).

### Gateway API / HTTPRoute

La façon moderne, standard, de décrire « quelle URL va vers quel service ». Un
**Gateway** est la porte d'entrée (l'IP + le port + le HTTPS) ; une
**HTTPRoute** est une règle d'aiguillage (« _ce_ nom de domaine, _ce_ chemin →
_ce_ service »). Cilium implémente cette API (via Envoy) — on n'a donc pas
besoin d'un outil séparé comme ingress-nginx. Voir
[ADR 0020](decisions/0020-exposition-reseau-tout-cilium.md).

### cert-manager / ClusterIssuer / CA interne

**cert-manager** est l'outil qui **fabrique et renouvelle automatiquement** les
certificats TLS (le « cadenas » HTTPS). Un **Issuer** (ou **ClusterIssuer**, sa
version valable pour tout le cluster) est l'autorité qui les signe. Comme le
cluster n'est **pas** joignable depuis Internet, on ne peut pas utiliser une
autorité publique (Let's Encrypt) : on crée notre **propre autorité interne**
(_CA interne_, _Certificate Authority_). Inconvénient : les navigateurs ne la
connaissent pas, il faut leur **importer** son certificat racine une fois. Voir
[ADR 0021](decisions/0021-cert-manager-ca-interne.md).

### gateway-shim

Le **pont** entre cert-manager et la Gateway API : on **annote** un Gateway, et
cert-manager comprend tout seul qu'il doit produire le certificat du site et
**remplir** le secret correspondant. Aucun certificat à gérer à la main. Voir
[ADR 0021](decisions/0021-cert-manager-ca-interne.md).

### GitOps / Argo CD / AppProject

Le **GitOps** est un principe : **git est la source de vérité**. On décrit
l'état voulu du cluster dans un dépôt git, et un outil le **réconcilie** en
continu (applique les changements, corrige les écarts). **Argo CD** est cet
outil ici. Un **AppProject** est un garde-fou : il **limite** ce qu'une
application a le droit de déployer et où (quels dépôts, quels espaces de noms).
Voir [ADR 0022](decisions/0022-argocd-gitops-applicatif.md).

### gRPC / gRPC-Web

Un protocole de communication efficace (utilisé par l'outil en ligne de commande
d'Argo CD). Sa variante **gRPC-Web** le fait passer par du HTTP classique, ce
qui lui permet de traverser une passerelle web (Gateway) sans configuration
particulière — d'où l'option `--grpc-web` côté client.

## Stockage (Rook-Ceph)

### Ceph

Un système de stockage distribué : il agrège les disques de plusieurs machines
en un grand pool unique, **répliqué** pour résister aux pannes. Fournit du
stockage bloc, fichier et objet.

### Rook

L'« opérateur » qui installe et pilote Ceph **dans** Kubernetes (via des CRD
comme `CephCluster`). On décrit le stockage voulu, Rook le déploie et le
maintient.

### OSD (Object Storage Daemon)

Le processus Ceph qui gère **un disque** de données. Un disque = un OSD. Plus il
y a de disques par nœud et de nœuds, plus le cluster a d'OSD ; la perte d'un OSD
est rattrapée par la réplication.

### MON (Monitor)

Le processus Ceph qui maintient la « carte » du cluster (qui détient quoi, qui
est vivant). Il en faut un nombre impair pour le **quorum** (voir ci-dessous) —
ici 3.

### Quorum

La majorité nécessaire pour qu'un groupe de décideurs (les MON) prenne une
décision valide. Avec 3 MON, il en faut 2 d'accord : le cluster survit donc à la
perte d'**un** MON. C'est pourquoi on déploie un nombre impair de MON.

### block.db

Une zone de métadonnées rapide d'un OSD, placée sur un disque **NVMe** (rapide)
plutôt que sur le disque de données (HDD, lent). Accélère Ceph. Ici, le NVMe qui
porte les block.db est un point sensible par nœud — voir
[ADR 0008](decisions/0008-metadatadevice-nvme-spof-par-noeud.md).

### Réplication ×3 / réplica

Garder **3 copies** de chaque donnée sur 3 nœuds différents. Si un nœud tombe,
les 2 autres copies suffisent. Voir
[ADR 0001](decisions/0001-replication-x3-pour-workloads-bloc.md).

### min_size

Le nombre minimum de copies qui doivent être disponibles pour que Ceph accepte
encore les **écritures**. Avec réplica ×3 et `min_size 2`, on peut perdre une
copie et continuer à écrire ; en dessous, Ceph bloque les écritures pour
protéger les données.

### failureDomain (domaine de panne)

Le niveau auquel Ceph répartit les copies pour résister aux pannes. Ici
`failureDomain: host` = les 3 copies sont sur 3 **hôtes** différents, donc la
perte d'un serveur entier ne perd jamais plus d'une copie.

### Erasure coding (codage à effacement)

Une alternative à la réplication, plus économe en espace : au lieu de 3 copies
complètes, on découpe la donnée en fragments + fragments de parité (ici « 2+1
»). Utilisé pour le datalake, où le volume prime sur la latence. Voir
[ADR 0004](decisions/0004-erasure-coding-2plus1-datalake.md).

### PG (Placement Group) / peering

Ceph regroupe les données en **PG** pour les gérer par paquets plutôt qu'objet
par objet. Le **peering** est la phase où les OSD d'un PG se synchronisent sur
l'état à jour ; un PG qui reste « peering » trop longtemps signale un blocage.

## Stockage côté Kubernetes

### PVC (PersistentVolumeClaim)

Une **demande** de stockage faite par une application (« j'ai besoin de 10 Gio
persistants »). Kubernetes la satisfait en fournissant un volume. Quand un PVC
est `Bound`, le stockage est attribué et prêt.

### StorageClass

Le « catalogue » de types de stockage disponibles (bloc répliqué, erasure-coded,
fichier…). Un PVC référence une StorageClass pour obtenir le bon type.

### RWX / RWO (ReadWriteMany / ReadWriteOnce)

Modes d'accès d'un volume. **RWO** : montable en écriture par un seul nœud à la
fois (stockage bloc). **RWX** : montable par plusieurs nœuds simultanément
(nécessite un système de fichiers partagé, ici **CephFS**).

### Persistance (`persistence.mode`)

Un **curseur de rétention** des données applicatives, **global à l'instance** et
déclaré une seule fois dans la topologie, à trois crans : `full` (défaut — on
stocke tout, comportement actuel à l'octet, aucune éviction), `bounded` (bornes
finies : fenêtres et quotas resserrés) et `ephemeral` (jetable — rétention
minimale, sauvegardes/snapshots désarmés). Posé **à l'installation** : nestor le
fait dériver sur six briques (StorageClass, CNPG, Loki, Prometheus, datalake,
CronJob de snapshots), qui appliquent chacune leur borne **nativement** — nestor
n'exécute aucune éviction. Ne régit **jamais** le plan de contrôle (etcd). Voir
[ADR 0109](decisions/0109-persistance-declarative-topologie.md).

## Stockage objet (S3)

### RGW (RADOS Gateway)

La passerelle Ceph qui expose le stockage objet via l'API **S3** (la même que le
service Amazon). Les applications y déposent/récupèrent des fichiers (« objets
») dans des **buckets**.

### Bucket

Un « conteneur » de stockage objet S3 — l'équivalent d'un dossier de haut niveau
où l'on range des fichiers. Ici, un bucket par source de données du datalake.

### OBC (ObjectBucketClaim)

L'équivalent d'un PVC mais pour le stockage objet : une **demande** de bucket
S3. Quand l'OBC converge, Rook crée le bucket et un `Secret` avec les
identifiants d'accès.

## Chaîne DataOps

### PostgreSQL / CloudNativePG (CNPG)

**PostgreSQL** est la base de données relationnelle du socle. Elle n'est pas
posée à la main mais gérée par **CloudNativePG** (« CNPG »), un _opérateur_
Kubernetes qui prend en charge tout son cycle de vie : haute disponibilité,
bascule, et sauvegardes vers S3. On écrit sur le service `pg-rw` (primary), on
lit sur `pg-ro` (replica). Voir
[ADR 0024](decisions/0024-postgres-manage-cloudnative-pg.md).

### pgvector

Une **extension** de PostgreSQL pour la **recherche sémantique** : elle ajoute
un type de colonne `vector(n)` et les opérateurs pour comparer des vecteurs
(trouver les plus « proches »). Utile pour ranger des _embeddings_
(représentations numériques de textes/images) et retrouver les plus similaires.
L'extension SQL s'installe par `CREATE EXTENSION vector` (déjà fait par
l'opérateur) ; « pgvector » est le nom du projet.

### Flyway

Un outil de **migration de base de données** : il applique, dans l'ordre et une
seule fois, une suite de scripts SQL versionnés pour amener le schéma à l'état
voulu. Ici, c'est lui qui crée les tables du store de lineage (Marquez) au
démarrage.

### Code-location

Dans Dagster, une **code-location** est le paquet de code métier (assets, jobs)
qu'on **branche** sur l'orchestrateur. Le socle est livré **sans** code-location
(orchestrateur vide) ; votre code s'y branche depuis le dépôt applicatif, servi
par un serveur gRPC déclaré dans le _workspace_. Voir
[ADR 0026](decisions/0026-orchestration-dagster.md).

### K8sRunLauncher

Le mode d'exécution de Dagster choisi ici : **chaque run devient un Job
Kubernetes** isolé (au lieu de tourner dans le processus de l'orchestrateur).
L'isolation et l'élasticité sont ainsi déléguées au cluster.

### MLflow

Le serveur de **suivi de modèles** du socle : il enregistre les _runs_
d'entraînement (paramètres, métriques, artefacts) et porte un **model registry**
(versions de modèles, promotions). Ses métadonnées vivent dans une base CNPG
dédiée (`mlflow`) ; ses artefacts (modèles, fichiers) dans du **S3**. Livré
**vide**, il est peuplé par le code applicatif via `MLFLOW_TRACKING_URI`. Voir
[composants](composants.md#mlflow-suivi-de-modèles) et
[ADR 0082](decisions/0082-suivi-modeles-mlflow.md).

### Promtail

L'agent qui **collecte les logs** sur chaque nœud (un DaemonSet) et les pousse
vers **Loki** (l'agrégateur de logs). Côté application, il n'y a rien à faire :
écrire sur la sortie standard suffit, Promtail s'occupe du reste.

## CI/CD in-cluster

La chaîne de build/déploiement qui tourne **dans** le cluster isolé, sans egress
(ADR 0112). Un `git push` déclenche le build de l'image de code puis son
déploiement, sans réintroduire l'événementiel (ADR 0105) ni relâcher la
sécurité.

### Gitea

Une **forge git légère** hébergée dans le cluster. Argo CD y **pull** les
manifestes (le cluster est isolé, pas d'egress vers une forge externe). Voir
[composants](composants.md#gitea-forge-git-intra-cluster).

### Gitea Actions / act_runner

Le **moteur de CI** de Gitea : un runner (`act_runner`) enregistré par
**token**, en **mode host durci** (zéro Docker-in-Docker, zéro privilège),
déclenché sur `git push`. C'est le **déclencheur** retenu par l'ADR 0112 (à la
place de la Sentinelle initialement planifiée). Exploitation :
[`platform/gitea-runner/RUNBOOK.md`](../platform/gitea-runner/RUNBOOK.md).

### buildkit / buildkitd

Le **moteur de build d'images** d'OCI, ici en **rootless in-pod** (un daemon
`buildkitd` dans le cluster, piloté par le client `buildctl`). Construit l'image
de code sans Docker ni privilège élevé. Voir
[composants](composants.md#buildkit-build-de-limage-de-code-in-pod) et
[`platform/buildkit/RUNBOOK.md`](../platform/buildkit/RUNBOOK.md).

### Registre d'images interne

Le **registre d'images** hébergé dans le cluster : buildkit y pousse l'image de
code construite, et les pods l'y tirent (via le DNS cluster, en HTTP), faute
d'egress vers un registre externe. Voir
[composants](composants.md#registry-dimages-interne).

## Opérations & qualité

### ConfigMap

Un objet Kubernetes qui stocke de la **configuration** (paires clé/valeur ou
petits fichiers) séparément du code, pour l'injecter dans des pods sans
reconstruire l'image. Le pendant pour les données sensibles est le **Secret**
(chiffré au repos, manipulé à part).

### Drift (dérive)

Un écart entre ce que la documentation/le code prétend et ce que la réalité fait
— typiquement révélé par un run de bout en bout, pas par le lint. Chaque drift
est indexé (symptôme, cause, correctif, statut) dans le **registre**
[`registre-drifts.yaml`](architecture/registre-drifts.yaml), et distillé en
invariants dans les [leçons des runs](architecture/lecons-des-runs.md) — par
honnêteté et pour ne pas répéter les mêmes erreurs.

### ADR (Architecture Decision Record)

Une fiche courte qui acte **une** décision d'architecture : le contexte, le
choix, les conséquences. Permet de comprendre _pourquoi_ une chose est ainsi,
des mois plus tard. Voir l'[index des décisions](decisions/).

### Idempotent

Se dit d'une opération qu'on peut rejouer sans dommage : la lancer 2 fois donne
le même résultat que 2 fois… ou qu'une seule. Les playbooks et scripts du dépôt
visent l'idempotence (on peut les relancer sans casser l'existant).

### Bootstrap

L'amorçage initial : la séquence qui part de serveurs nus et construit le
cluster fonctionnel (OS → runtime → Kubernetes → réseau → stockage). Voir
[`bootstrap/`](../bootstrap/).
