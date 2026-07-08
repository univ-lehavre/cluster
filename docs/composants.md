# Composants — la pile technologique, brique par brique

Cette page **présente chaque technologie** employée par le cluster : à quoi elle
sert, _pourquoi elle est là_, et ce qu'elle remplace ou évite. C'est le registre
intermédiaire entre trois autres documents :

- le [glossaire](glossaire.md) définit les **termes** (lexique court) ;
- les README sous [`platform/`](../platform/) et
  [`storage/ceph/`](../storage/ceph/) disent **comment installer** chaque brique
  ;
- les [ADR](decisions/) actent **pourquoi** chaque choix, avec l'alternative
  écartée.

Ici, on décrit la **brique elle-même** et son rôle dans l'ensemble. Les briques
sont regroupées par couche, du plus bas (le socle Kubernetes) au plus haut (la
chaîne DataOps et l'observabilité).

> **Valeurs génériques (ADR
> [0023](decisions/0023-plateforme-exemple-generique.md)).** Les noms d'hôtes,
> IP, ports et adresses cités (`10.0.0.0/22`, `http://<IP-nœud>:<nodePort>`…)
> sont des **exemples**. Les briques nommées (Ceph, Cilium, Dagster…) sont en
> revanche les vraies décisions techniques du dépôt — on les garde.

## Socle Kubernetes et exécution des conteneurs

### Kubernetes (kubeadm)

Kubernetes est le chef d'orchestre du cluster : on lui décrit l'état souhaité («
3 copies de cette application, joignable sur ce port »), il s'arrange pour
l'atteindre et corrige les écarts en continu. C'est le **substrat** sur lequel
tout le reste (stockage, réseau, DataOps) se déploie sous forme de ressources
déclaratives.

Le cluster est amorcé avec **kubeadm**, l'outil officiel d'installation
(`kubeadm init` sur le control plane, `kubeadm join` sur les workers). Le choix
de kubeadm — plutôt qu'une distribution clé en main (k3s, RKE…) — donne un
cluster **standard, non opinionné**, dont chaque composant reste explicite et
auditable. La topologie du plan de contrôle est un axe du catalogue : control
plane unique pour la simplicité
([ADR 0002](decisions/0002-control-plane-unique-avec-endpoint.md)), ou control
plane dédié en HA avec VIP kube-vip et etcd 2/3
([ADR 0047](decisions/0047-topologie-ha-3cp-control-plane-dedie.md)).

L'amorçage complet (OS → runtime → Kubernetes → réseau → stockage) est porté par
Ansible et des scripts sous [`bootstrap/`](../bootstrap/), repris pas à pas dans
le [RUNBOOK](../bootstrap/RUNBOOK.md).

### containerd

containerd est le moteur qui exécute réellement les conteneurs sous Kubernetes :
il tire les images et lance/arrête les processus, derrière l'interface standard
**CRI** (Container Runtime Interface). Kubernetes ne parle jamais directement
aux conteneurs, il délègue à containerd via le CRI — ce qui permet d'en changer
sans toucher au reste.

Il est installé depuis le dépôt Docker plutôt que via le paquet de la
distribution, pour disposer d'une version maîtrisée et à jour
([ADR 0005](decisions/0005-cri-containerd-via-depot-docker.md)). C'est aussi lui
qu'on configure pour tirer le **registry interne en HTTP**
(`use_local_image_pull`, `certs.d`) puisque le cluster est isolé d'Internet.

### etcd

etcd est la base de données du plan de contrôle : elle stocke **tout** l'état du
cluster (objets, configuration, secrets). C'est le composant le plus critique du
socle — perdre etcd sans sauvegarde, c'est perdre le cluster. D'où les
**snapshots etcd** réguliers
([`bootstrap/roles/etcd-backup/`](../bootstrap/roles/etcd-backup/)). En
topologie HA, etcd tourne en quorum 2/3 sur les control planes dédiés
([ADR 0047](decisions/0047-topologie-ha-3cp-control-plane-dedie.md)).

## Réseau et exposition

### Cilium (CNI)

Cilium est le plugin **CNI** (Container Network Interface) du cluster : il donne
une adresse réseau à chaque pod, route le trafic entre eux et applique la
sécurité réseau. Il s'appuie sur **eBPF**, une technologie du noyau Linux qui
programme le réseau directement dans le kernel plutôt qu'en empilant des règles
iptables.

Le choix de Cilium est structurant car il **absorbe plusieurs rôles** qui
demanderaient autrement des outils séparés :

- il **remplace kube-proxy** (`kubeProxyReplacement`) en faisant l'aiguillage
  des services en eBPF, plus rapide et sans le composant kube-proxy ;
- il fournit le **durcissement réseau** : chiffrement WireGuard du trafic
  pod-à-pod et observabilité Hubble
  ([ADR 0019](decisions/0019-durcissement-reseau-cilium.md)) ;
- il porte toute la chaîne d'**exposition** (ci-dessous), évitant MetalLB et
  ingress-nginx.

### Exposition tout-Cilium (LB-IPAM + annonce L2 + Gateway API)

Pour qu'un service soit joignable depuis le réseau local (jamais Internet ici),
il faut une IP, que le réseau sache où la trouver, et une porte d'entrée
HTTP/HTTPS. Sur des machines « nues » (bare-metal), aucun cloud ne fournit ces
fonctions — on s'appuie donc entièrement sur Cilium
([ADR 0020](decisions/0020-exposition-reseau-tout-cilium.md)) :

- **LB-IPAM** pioche une IP dans un pool déclaré (`CiliumLoadBalancerIPPool`) et
  l'attribue aux services de type LoadBalancer ;
- l'**annonce L2 / ARP** (`CiliumL2AnnouncementPolicy`) fait qu'un nœud « crie »
  sur le réseau local « cette IP, c'est moi ! » — avec bascule sur un autre nœud
  en cas de panne (failover, pas répartition de charge) ;
- la **Gateway API** (`GatewayClass` `cilium`, implémentée via Envoy) décrit «
  quelle URL va vers quel service » via des objets `Gateway` (la porte : IP +
  port + HTTPS) et `HTTPRoute` (les règles d'aiguillage).

Les CRDs Gateway API ne sont **pas** embarquées par Cilium : elles sont posées
en amont (version épinglée,
[ADR 0006](decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
Toutefois, **les UI ne passent plus par le Gateway L7** : depuis
l'[ADR 0092](decisions/0092-exposition-hostport-l4.md) l'accès aux UI se fait en
**L4** (`NodePort`/`hostPort` sur l'IP du nœud, `http://<IP-nœud>:<port>` — zéro
DNS, zéro LB-IPAM). Le dossier de manifestes `platform/cilium-expo/` et les
`gateway.yaml` de brique ont été **retirés** avec cette bascule ; LB-IPAM et la
Gateway API restent des features Cilium (chemin de prod optionnel).

### cert-manager (CA interne)

cert-manager fabrique et **renouvelle automatiquement** les certificats TLS (le
cadenas HTTPS) internes du cluster. Depuis
l'[ADR 0092](decisions/0092-exposition-hostport-l4.md) les UI sont exposées en
**L4** (HTTP clair sur l'IP du nœud), donc **hors** du chemin cert-manager ;
celui-ci reste le socle de CA interne (webhooks, gateway-shim de prod
optionnel). Comme le cluster n'est pas joignable depuis Internet, on ne peut pas
employer une autorité publique type Let's Encrypt (ACME a besoin d'une
validation externe) : cert-manager monte une **autorité interne** (CA), une
chaîne `selfsigned-bootstrap → root-ca → internal-ca`, qui signe les certificats
du cluster ([ADR 0021](decisions/0021-cert-manager-ca-interne.md)).

L'intégration se fait par **annotation** : on annote un `Gateway`
(`cert-manager.io/cluster-issuer: internal-ca`), et le pont **gateway-shim**
comprend qu'il doit émettre le certificat et remplir le secret — aucun
certificat à gérer à la main. Contrepartie assumée : les navigateurs ne
connaissent pas la CA interne, il faut leur importer son certificat racine une
fois. Manifestes : [`platform/cert-manager/`](../platform/cert-manager/).

### NetworkPolicies (micro-segmentation est-ouest)

Les **NetworkPolicies** posent une barrière réseau _entre_ les pods (trafic
est-ouest). Le principe est un **default-deny par namespace** : un pod ne peut
communiquer qu'avec ce qui est explicitement autorisé (DNS, puis les flux métier
nécessaires). C'est du **defense-in-depth**, pas une correction de faille : si
un pod est compromis, il ne peut pas balayer librement le cluster
([`platform/network-policies/`](../platform/network-policies/)).

## Stockage

### Rook-Ceph

**Ceph** est un système de stockage distribué : il agrège les disques de tous
les nœuds en un grand pool unique, **répliqué** pour résister aux pannes, et
expose les trois formes de stockage dont le cluster a besoin — **bloc** (RBD,
pour les bases et l'état applicatif), **fichier** (CephFS, pour le partagé
multi-pods RWX) et **objet** (S3 via le RGW, pour le datalake).

**Rook** est l'opérateur Kubernetes qui installe et pilote Ceph _dans_ le
cluster : on décrit le stockage voulu via des CRDs (`CephCluster`,
`CephObjectStore`…), Rook le déploie et le maintient. Rook-Ceph a été retenu
plutôt que Longhorn pour couvrir ces trois formes de stockage avec une seule
brique, et pour son adéquation à l'hyperconvergence
([ADR 0018](decisions/0018-rook-ceph-vs-longhorn.md)).

Le dispositif est conçu pour l'**hyperconvergence** (calcul et stockage sur les
mêmes machines,
[ADR 0007](decisions/0007-hyperconvergence-control-plane-osd.md)) et tolère la
perte d'un nœud entier : `failureDomain: host` place chaque copie sur un hôte
distinct. Deux profils de durabilité coexistent — **réplication ×3** par défaut
pour le stateful critique
([ADR 0001](decisions/0001-replication-x3-pour-workloads-bloc.md)), et **erasure
coding 2+1** pour le datalake où le volume prime sur la latence
([ADR 0004](decisions/0004-erasure-coding-2plus1-datalake.md)). Procédures :
[`storage/ceph/`](../storage/ceph/) et son
[RUNBOOK](../storage/ceph/RUNBOOK.md).

### SeaweedFS

SeaweedFS est un **stockage objet S3 léger**, alternative au RGW de Ceph pour
les topologies où l'on ne monte pas tout Ceph (banc léger). Le point clé : il
expose la **même API S3** que la prod, donc les briques qui consomment du S3
(Loki, les sauvegardes CloudNativePG) testent le **vrai chemin de code S3** sans
dépendre de Ceph — l'endpoint et les identifiants sont paramétrables, le
protocole reste identique ([ADR 0036](decisions/0036-backing-s3-unique-rgw.md)).
Manifeste :
[`platform/seaweedfs/seaweedfs.yaml`](../platform/seaweedfs/seaweedfs.yaml).

### local-path

Le provisioner **local-path** fournit du stockage bloc simple, adossé au disque
local du nœud, sans la machinerie distribuée de Ceph. Il sert de StorageClass de
repli pour les topologies ou bancs minimaux où Ceph n'est pas déployé. Manifeste
:
[`storage/local-path/local-path-storage.yaml`](../storage/local-path/local-path-storage.yaml).

## GitOps et forge

### Argo CD (GitOps applicatif)

Le **GitOps** est un principe : git est la source de vérité. On décrit l'état
voulu dans un dépôt git, et un outil le **réconcilie** en continu — il applique
les changements et corrige les écarts. **Argo CD** est cet outil ici
([ADR 0022](decisions/0022-argocd-gitops-applicatif.md)).

Une **frontière nette** sépare ce qu'Argo CD gère de ce qu'il ne gère pas, pour
éviter un bootstrap circulaire : l'**infra** (Cilium, exposition, cert-manager,
registry, Rook, opérateurs, et Argo CD lui-même) est posée par **Ansible** — la
retirer empêcherait Argo CD de démarrer ; l'**applicatif** (vos workflows :
code-locations, assets, jobs, et les instances stateful déclarées en
`Application`) est réconcilié par Argo CD. Vous poussez le _contenu_, le socle
fournit le _contenant vide_. Un **AppProject** sert de garde-fou : il limite ce
qu'une application a le droit de déployer et où. Manifestes :
[`platform/argocd/`](../platform/argocd/).

### Gitea (forge git intra-cluster)

Gitea est une forge git légère **hébergée dans le cluster**. Elle existe parce
que le cluster cible est isolé, sans Internet : Argo CD ne peut donc pas tirer
ses manifestes d'un GitHub public, il les pull depuis Gitea, en intra-cluster
([ADR 0044](decisions/0044-topologie-deploiement-banc-atlas.md)). Le banc prouve
ainsi le flux GitOps tel qu'il tournera en production (build image → push
registry → commit manifeste → webhook Gitea → réconciliation Argo CD), sans
dépendre d'un egress externe. Comme Argo CD doit pouvoir la joindre dès le
départ, Gitea est de l'**infra** posée par Ansible. Manifestes :
[`platform/gitea/`](../platform/gitea/).

### Registry d'images interne

Le registry interne (distribution v3) stocke les **images applicatives** (par
exemple les code-locations Dagster ou les jobs) en intra-cluster. Comme le
cluster est isolé, on y mirrore aussi les images upstream nécessaires (Argo CD,
cert-manager…) pour éviter `ImagePullBackOff`. Il est servi en **HTTP sans
authentification**, un compromis assumé sur un réseau supposé privé
([ADR 0011](decisions/0011-registry-http-sans-auth.md)) — d'où la configuration
containerd côté nœuds pour le tirer en HTTP. On le référence en
`registry:80/<repo>:<tag>` dans les manifestes. Manifestes :
[`platform/container-registry/`](../platform/container-registry/).

### La boucle GitOps de bout en bout

Les briques ci-dessus (Argo CD, Gitea, registry) s'articulent en une **boucle**
unique, qui est la façon canonique de déployer un workflow — on ne fait
**jamais** de `kubectl apply` de l'applicatif (frontière
[ADR 0022](decisions/0022-argocd-gitops-applicatif.md)/[0045](decisions/0045-chemins-installation-banc-couches.md))
:

1. **Build + push** de votre image (code-location/job) dans le **registry
   interne** (`registry:80/...`).
2. **Commit + push** du manifeste qui la référence (`Application` Argo CD, ou
   patch de workspace) dans le **dépôt Gitea intra-cluster** — pas un GitHub
   externe : le cluster est isolé.
3. Un **webhook** Gitea → Argo CD déclenche la **réconciliation** : Argo CD
   applique votre manifeste (`Synced/Healthy`).
4. Le run s'exécute (`K8sRunLauncher`) et **émet du lineage** ingéré par
   Marquez.

Argo CD déploie **vos workflows**, **jamais l'infra** : le socle (CNPG, Dagster,
Marquez, Argo CD lui-même) est monté par Ansible. Vous poussez le _contenu_, le
socle fournit le _contenant vide_. C'est cette boucle qu'un développeur rejoue
en local (tutoriel [Monter le banc local](banc-local.md#3-pousser-sur-gitea)) et
qu'invoque le
[mode d'emploi de branchement](se-brancher.md#déployer--la-boucle-gitops).

### Build applicatif : node-side, puis seed → Argo CD

Le _build + push_ de l'image applicative reste un **geste opérateur unique
assumé** : `nestor ansible code-location-build.yaml`
([`platform-build-images`](/cluster/bootstrap/roles/platform-build-images/))
build + push `registry:80/<cl>-dagster`, **lit le digest réel**
(`nerdctl image inspect`), puis le **seed l'injecte** dans l'overlay Kustomize
(`images: digest:`) poussé dans le dépôt de code que réconcilie **Argo CD** —
déploiement **par digest figé** (immuabilité totale, ADR 0006).

> **La chaîne de build ÉVÉNEMENTIEL in-cluster (Argo Events + Argo Workflows +
> NATS, ancienne cible d'ADR 0095 §1.b) a été RETIRÉE**
> ([ADR 0105](decisions/0105-retrait-build-evenementiel-node-side-terminal.md))
> : instable en prod (un `git push` full-tree amplifiait le webhook en dizaines
> de builds redondants, ~52 % d'échec) et **redondante** avec le chemin
> node-side ci-dessus (prouvé suffisant seul). Le build node-side devient le
> mécanisme **terminal** ; −3 opérateurs.

## Chaîne DataOps

### PostgreSQL via CloudNativePG

PostgreSQL est la base relationnelle du socle DataOps. Elle n'est pas déployée à
la main mais via **CloudNativePG (CNPG)**, un opérateur Kubernetes qui gère le
cycle de vie complet d'un cluster PostgreSQL HA : réplication, bascule, et
sauvegardes vers S3 via le **plugin Barman Cloud**
([ADR 0024](decisions/0024-postgres-manage-cloudnative-pg.md)).

Un unique cluster HA porte **plusieurs bases logiques**, chacune avec son rôle
propriétaire et son secret : l'**event log de Dagster**, le store de lineage de
**Marquez** (base dédiée, migrations Flyway), et un index **pgvector** pour la
recherche sémantique. **pgvector** est une extension SQL
(`CREATE EXTENSION vector`, type `vector(n)`) activée par l'opérateur via les
Image Volume Extensions, sans image PostgreSQL custom. On écrit sur le service
primary (`pg-rw`), on lit sur le replica (`pg-ro`). Manifestes :
[`platform/cloudnative-pg/`](../platform/cloudnative-pg/).

### Dagster (orchestration)

Dagster est l'**orchestrateur** de pipelines de données : il déclenche, planifie
et suit l'exécution des jobs
([ADR 0026](decisions/0026-orchestration-dagster.md)). Il est livré **vide** :
c'est le socle (webserver, daemon, run launcher), sans aucun code métier. Le
code (assets, jobs) s'y branche depuis le dépôt applicatif via une
_code-location_, conformément à la frontière infra/applicatif (ADR 0022).

Deux choix de fonctionnement le caractérisent : son état (event/run/schedule
storage) est **persisté dans PostgreSQL** (base CNPG `dagster`), pas dans un
volume local ; et chaque run est exécuté via le **`K8sRunLauncher`**,
c'est-à-dire qu'un run = un Job Kubernetes, ce qui place l'isolation et
l'élasticité au niveau du cluster. Manifestes :
[`platform/dagster/`](../platform/dagster/).

### Marquez et OpenLineage (lineage)

Le **lineage** trace d'où vient une donnée et ce qu'elle a traversé (quels jobs,
quelles entrées/sorties). **OpenLineage** est le standard ouvert qui décrit ces
événements ; **Marquez** est le store qui les **ingère, agrège et visualise**
(API de collecte + UI web)
([ADR 0028](decisions/0028-orchestration-openlineage-marquez.md)).

La séparation des rôles est nette : les événements sont **émis** par les
producteurs (Dagster via un sensor OpenLineage, puis le code applicatif),
Marquez ne fait qu'**ingérer et visualiser** — il ne produit jamais de lineage
lui-même. Son store persiste dans une base PostgreSQL dédiée (`marquez`),
peuplée par des migrations Flyway au démarrage. Manifestes :
[`platform/marquez/`](../platform/marquez/).

### MLflow (suivi de modèles)

**MLflow** est le serveur de **suivi de modèles** du socle DataOps (le frère de
Dagster et Marquez dans la chaîne) : il enregistre les _runs_ d'entraînement —
paramètres, métriques, artefacts — et porte un **model registry** (versions de
modèles, étapes de promotion)
([ADR 0082](decisions/0082-suivi-modeles-mlflow.md)). Comme Dagster, il est
livré **vide** : c'est le socle de traçabilité des modèles, sans aucun run
métier ; c'est le dépôt applicatif `atlas` qui le peuple, en pointant la
variable `MLFLOW_TRACKING_URI` vers le serveur.

Deux stockages le caractérisent, alignés sur le reste du socle : son **backend
store** (métadonnées des runs : paramètres, métriques, tags) est une base
PostgreSQL dédiée `mlflow` du cluster CNPG ; son **artefact store** (les
fichiers volumineux : modèles sérialisés, graphiques) est du **S3** — RGW Ceph
en prod, SeaweedFS sur le banc léger
([ADR 0036](decisions/0036-backing-s3-unique-rgw.md)). L'API et l'UI partagent
le port `5000` (`mlflow.mlflow.svc.cluster.local:5000`) ; l'UI est exposée hors
cluster en **L4** sur un port du nœud (`http://<IP-nœud>:<nodePort>`, le portail
observe le port réel ; [ADR 0092](decisions/0092-exposition-hostport-l4.md)),
**sans authentification** — compromis assumé sur un réseau privé de confiance
mono-admin ([ADR 0003](decisions/0003-pas-de-chiffrement-ceph-tailscale.md)).
L'image est **maison** : la base officielle `ghcr.io/mlflow/mlflow:v3.4.0`
(épinglée par digest) **+ `psycopg2-binary`** (driver PostgreSQL absent de
l'upstream, requis par le backend store CNPG), buildée pour les 2 arches et
tirée du registry interne
([`platform/mlflow/image/Dockerfile`](../platform/mlflow/image/Dockerfile),
[ADR 0082](decisions/0082-suivi-modeles-mlflow.md)). Manifestes :
[`platform/mlflow/mlflow.yaml`](../platform/mlflow/mlflow.yaml).

## Observabilité

L'observabilité est montée par **paliers**
([ADR 0016](decisions/0016-observabilite.md)) : un socle minimal autonome
(metrics-server), puis le stack complet métriques + logs.

### metrics-server

metrics-server est le **palier 1**, autonome et léger : il collecte l'usage
CPU/mémoire des nœuds et des pods via les kubelets et l'expose dans l'API
`metrics.k8s.io`. Il rend opérants `kubectl top nodes` / `kubectl top pods` et
les **HorizontalPodAutoscaler** (HPA), sans nécessiter Prometheus. C'est le
minimum vital recommandé par l'audit. Manifestes :
[`platform/metrics-server/`](../platform/metrics-server/).

### kube-prometheus-stack (métriques)

Le **palier 2** des métriques : Prometheus (collecte et stockage des séries
temporelles) + Alertmanager (routage des alertes) + Grafana (tableaux de bord) +
kube-state-metrics et node-exporter (exporteurs), plus l'activation du
monitoring Ceph. Côté consommateur, on n'a rien à câbler : exposer un
`ServiceMonitor`/`PodMonitor` suffit à ce que Prometheus scrape automatiquement
le workload. Manifestes :
[`platform/kube-prometheus-stack/`](../platform/kube-prometheus-stack/).

### Loki (logs)

Loki agrège les **logs** (palier 2, volet journaux). **Promtail** les collecte
sur chaque nœud (DaemonSet) et les pousse vers Loki, qui les stocke en backend
S3 ; on les explore ensuite dans **Grafana** via la datasource Loki. Côté
application, il n'y a rien à faire : écrire sur stdout/stderr suffit, Promtail
collecte. Manifestes : [`platform/loki/`](../platform/loki/).

### Mailpit

Mailpit est un **puits SMTP de test** doté d'une UI web : il capture les mails
d'alerte (Alertmanager, et à terme la couche de durcissement hôte) pour
**valider la chaîne d'alerting de bout en bout** sur le banc, sans relais mail
externe. C'est un addon de test transverse, pas un composant de production.
Manifestes : [`platform/mailpit/`](../platform/mailpit/).

### Kubernetes Dashboard

Le Dashboard Kubernetes officiel offre une UI de consultation et
d'administration du cluster. Il est déployé avec un compte de service en
`cluster-admin` et des **tokens éphémères** générés à la demande (API
`TokenRequest`), jamais de token long-lived persistant. Le choix du
`cluster-admin` est cohérent avec un cluster **mono-admin de recherche** et
assumé comme tel ([ADR 0010](decisions/0010-dashboard-cluster-admin.md)).
Manifestes : [`platform/k8s-dashboard/`](../platform/k8s-dashboard/).

### Portail d'accès aux UI

Le **portail** est une vue unifiée des UI/endpoints de la plateforme pour
l'opérateur : qu'est-ce qui est exposé, sur quelle adresse
(`http://<IP-nœud>:<nodePort>`, le portail **observe le port réel** ;
[ADR 0092](decisions/0092-exposition-hostport-l4.md)), avec quelle
authentification, et **comment récupérer le credential** (la commande `kubectl`,
jamais la valeur). Serveur **dynamique** in-cluster qui lit l'API k8s en lecture
seule et la croise avec le [contrat](../contract/) ; sidebar par couche, liens
en nouvel onglet (pas d'iframe). RBAC **sans droit sur les Secrets**, pod durci
([ADR 0091](decisions/0091-portail-acces-ui.md)). Manifestes :
[`platform/portal/`](../platform/portal/).

## Applications

Charges applicatives déployées **sur** la plateforme (pas des briques d'infra) —
chacune autonome, hors graphe `nestor` ([`apps/`](../apps/)) :

### RStudio

RStudio Server (image `rocker`) sur PVC RBD, pour le calcul statistique
interactif. Mono-utilisateur, **sans authentification** (réseau isolé, accès par
`kubectl port-forward`) — choix assumé pour un cluster de recherche
([ADR 0012](decisions/0012-rstudio-disable-auth.md)). Manifestes :
[`apps/rstudio/`](../apps/rstudio/).

### REDCap

[REDCap](https://projectredcap.org) (saisie de données de recherche, PHP/Apache)
adossé à un **MariaDB autonome** (REDCap ne supporte pas PostgreSQL/CNPG).
Logiciel **tiers sous licence** : image **maison** (`php:apache` + extensions +
le code source, gitignoré et jamais commité, ADR 0023) ; déployée par un
**playbook dédié** [`bootstrap/redcap.yaml`](../bootstrap/redcap.yaml)
(installation et désinstallation, `redcap_state=present|absent`). Manifestes et
procédure : [`apps/redcap/`](../apps/redcap/).

## Pour aller plus loin

- Consommer ces briques depuis son code :
  [guide du développeur data](guide-dev-data.md).
- Définitions courtes des termes : [glossaire](glossaire.md).
- Pourquoi chaque choix : [index des ADR](decisions/) et les
  [vues d'architecture](architecture/).
- Contrat d'interface machine-lisible : [`contract/`](../contract/).
