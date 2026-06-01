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

Un ensemble de machines (ici 4 serveurs) qui travaillent ensemble comme une
seule ressource. On y déploie des applications sans se soucier de _quelle_
machine les exécute — le cluster décide.

### Nœud (node)

Une machine du cluster (physique ici : un serveur HPE). Chaque nœud exécute des
conteneurs et participe au stockage.

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

### Tailscale

Un VPN « maillé » (basé sur WireGuard) qui crée un réseau privé chiffré entre
machines, où qu'elles soient. Ici, c'est la compensation de sécurité qui permet
d'exposer certains services en HTTP sans authentification (réseau supposé
privé). Voir [ADR 0003](decisions/0003-pas-de-chiffrement-ceph-tailscale.md).

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

Le processus Ceph qui gère **un disque** de données. Un disque = un OSD. Avec 12
disques par serveur × 4 serveurs, le cluster a beaucoup d'OSD. La perte d'un OSD
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

## Opérations & qualité

### Drift (dérive)

Un écart entre ce que la documentation/le code prétend et ce que la réalité
fait. Le banc de test trace ses drifts dans
[`test/RESULTS.md`](../test/RESULTS.md) — par honnêteté et pour ne pas répéter
les mêmes erreurs.

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
