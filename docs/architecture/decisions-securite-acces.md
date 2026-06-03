# Décisions — Sécurité & accès

> Cette page est une **vue thématique** : elle agrège et raconte, par sujet, les
> décisions de sécurité prises au fil du temps. Elle ne remplace pas les ADR —
> ceux-ci restent la **source de vérité datée et immuable**. Considérez cette
> page comme une carte de lecture qui pointe vers chaque ADR concerné.

## Le modèle de menace, fil rouge de toutes les décisions

Toutes les décisions de sécurité de ce cluster découlent d'un même modèle de
menace, posé une fois pour toutes dans
[ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md) et rappelé
ensuite à chaque arbitrage :

- cluster **mono-tenant** (laboratoire de recherche) ;
- **mono-administrateur** (un seul opérateur) ;
- **réseau privé isolé** `10.67.2.0/22` (lien 10 GbE inter-nœuds, pas de routage
  Internet), CIDR pods Cilium `10.244.0.0/16` ;
- **pas de données réglementées** : données de recherche (article public,
  observation géoclimatique…), pas de données personnelles, pas de classifié.

Dans ce cadre,
[ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md) pose le
principe directeur : **la sécurité du transport est déléguée au contrôle d'accès
au réseau**. Le rempart, c'est le périmètre du réseau privé ; le reste des
décisions en découle. Tailscale (tunnel chiffré pour l'accès distant) reste
**optionnel** : aucun composant ne s'appuie en dur dessus, c'est un moyen
d'accès possible et non le pivot de la sécurité. Une porte de sortie OSS est
notée ([Headscale](https://github.com/juanfont/headscale)) si la dépendance au
SaaS Tailscale devenait un souci.

Pour tout ce qui touche à l'exposition des services, au TLS et à l'accès
distant, voir la vue dédiée
[Exposition & réseau](../architecture/exposition-reseau.md).

## Pas de chiffrement Ceph : un coût écarté, pas une négligence

Ceph offre deux dimensions de chiffrement, toutes deux **écartées** par
[ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md) :

- **in-transit** (`network.connections.encryption.enabled`, msgr2 secure mode) ;
- **at-rest** (OSDs chiffrés via LUKS bluestore).

Le RGW (datalake S3) est lui aussi exposé en **HTTP port 80**, pas en TLS 443.

La justification est explicite et mesurée : le chiffrement in-transit a un
**coût CPU non négligeable** (chaque réplication, chaque flux OSD↔OSD), et le
at-rest LUKS impose une **gestion de clés** (KMS, Vault) et un overhead
constant. Pour un réseau privé isolé hébergeant des données non réglementées, le
bénéfice ne justifie pas ce coût. Le gain assumé : pas d'overhead CPU
(réplications et lectures rapides), aucune mécanique de clés à inventer,
configuration plus simple à reprendre.

Cette décision est cohérente avec le reste de la pile (registry HTTP, dashboard
en port-forward) : **un seul modèle de sécurité réseau à comprendre**.

## Durcissement réseau Cilium : une défense en profondeur à faible coût

[ADR 0019](../decisions/0019-durcissement-reseau-cilium.md) pose une question
**distincte** de 0003 : non pas « faut-il chiffrer Ceph », mais « peut-on
ajouter une défense en profondeur au niveau du réseau **pods**, à faible coût,
sans réintroduire la complexité que 0003 a refusée ? ». La réponse active deux
fonctions Cilium, appliquées par `cni.sh` à l'install **et** à l'upgrade (donc
convergentes en rejouant le script).

### WireGuard pod-to-pod

`--set encryption.enabled=true --set encryption.type=wireguard` chiffre le
trafic **pod-to-pod inter-nœuds** via une interface `cilium_wg0` par nœud (mesh
WireGuard entre tous les agents). Le point clé : **Cilium gère les clés tout
seul** (génération, rotation, distribution via le control plane K8s). C'était
précisément l'objection de 0003 au LUKS Ceph — pas de KMS ni de Vault à
inventer. WireGuard lève cette objection.

Choix de portée assumés :

- on reste sur le chiffrement **pod-to-pod** et **pas** `nodeEncryption`
  (host-to-host), jugé plus intrusif et susceptible de gêner les health-checks
  pour un gain marginal dans ce modèle ;
- le trafic **Ceph OSD↔OSD** reste non chiffré au niveau msgr2 (choix 0003
  inchangé), mais comme il transite par le réseau pods, il bénéficie
  **indirectement** du tunnel WireGuard inter-nœuds.

WireGuard est donc une **couche additionnelle peu coûteuse** (overhead inférieur
au chiffrement msgr2 Ceph écarté), qui réduit l'impact d'un attaquant passé
**sur** le réseau cluster — le coût assumé n° 1 de 0003 (« sniffer tout le
trafic »). Pré-requis : module kernel `wireguard` (Debian 13, kernel ≥ 5.6).

### Hubble + Relay (observabilité réseau), sans UI

`--set hubble.enabled=true --set hubble.relay.enabled=true` donne
`hubble observe` (flux L3/L4/L7, identités, verdicts policy, drops) en **CLI**,
utile pour diagnostiquer une `NetworkPolicy` ou un flux inattendu. **Pas de
Hubble UI** : un dashboard web ajouterait un Service et une surface à protéger,
sans valeur pour un cluster mono-admin. Hubble reste autonome (pas de Prometheus
requis).

### Validation et garde-fou anti-dérive

Validé sur banc multi-node (3 nœuds, K8s 1.34.8, Cilium 1.19.4, Run #6) :
WireGuard actif `Encryption: Wireguard (3/3 nodes)`, `hubble observe` retourne
les flux réels, Ceph `HEALTH_OK` après reconvergence. Point opérationnel
important : `cilium upgrade` seul met à jour la ConfigMap sans rouler les agents
(le config-drift-checker signalerait `enable-wireguard actual=false`). `cni.sh`
**force donc un `rollout restart`** après upgrade, puis **vérifie**
`cilium encrypt status` et échoue si WireGuard n'est pas réellement actif — un
durcissement silencieusement inactif est pire qu'un échec visible. Détails de
banc dans [Validation sur banc](../architecture/validation-banc.md).

## Durcissement du plan de contrôle

[ADR 0014](../decisions/0014-durcissement-kubeadm-init.md) part d'un constat
d'audit (P6, item #21) : le control plane était initialisé par un `kubeadm init`
**en ligne de commande** (sans `--config`), laissant trois manques au niveau du
plan de contrôle, qu'aucun ADR ne couvrait. L'ADR les traite de façon
**différenciée** selon leur rapport risque/valeur.

- **Pod Security admission — activé.** Le contrôleur intégré (depuis K8s 1.25)
  est activé par **labels de namespace** (pas d'`AdmissionConfiguration`
  globale, pour éviter de toucher l'init). Niveau **`baseline` en `enforce`**
  sur les namespaces maison (`rstudio`, `registry`, `default`) — bloque le plus
  dangereux (privileged, hostPID/IPC, hostNetwork) sans casser les workloads ;
  **`restricted` en `warn`** pour préparer un durcissement ultérieur. **Pas**
  d'enforce sur `rook-ceph`, dont l'operator/CSI a légitimement besoin de
  privilèges élevés.
- **Chiffrement at-rest des Secrets etcd — implémenté.** `kubeadm init --config`
  pose une `EncryptionConfiguration` provider **`secretbox`**
  (XSalsa20-Poly1305, pas de KMS externe, cohérent avec 0003). La clé (32 octets
  aléatoires base64) est générée **sur le nœud au bootstrap**, stockée dans
  `/etc/kubernetes/enc/key1.b64` (0600 root, **hors dépôt, jamais commitée**) et
  une seule fois. Validé sur banc (Run #8, scénario 15) : la valeur brute d'un
  Secret lue via `etcdctl` commence par `k8s:enc:secretbox:v1:key1:`.
- **Audit-policy API server — implémenté.** Politique **`Metadata`-level** par
  défaut (qui/quoi/quand sans le corps des requêtes), avec exclusion du bruit
  (lectures kubelet/scheduler, `/healthz`, events, leases) et rotation
  (`audit-log-max*` : 30 j / 10 backups / 100 Mo). Couvre les appels API directs
  d'un humain (`kubectl`), que l'audit Ansible et `auditd` ne voyaient pas.

Une question voisine est tranchée dans le même ADR : faut-il **chiffrer le
fichier snapshot etcd** au repos ? **Non**, et la dette est close en l'assumant
— voir l'encadré honnêteté.

## Les compromis d'accès assumés (et pourquoi ils tiennent)

Trois services maison roulent sans authentification applicative. Ce ne sont pas
des oublis : chacun est un ADR daté, qui assume le coût et délègue la sécurité
au contrôle d'accès au Service, dans le modèle mono-tenant de 0003.

### Registry interne — HTTP en clair, sans auth

[ADR 0011](../decisions/0011-registry-http-sans-auth.md) : le registry
(distribution v3) expose le port **80 en HTTP clair, sans module
`REGISTRY_AUTH`**. Périmètre : pulls intra-cluster par `kubelet` depuis le
réseau pods `10.244.0.0/16` ; accès distant **optionnel** via Tailscale, sinon
`kubectl port-forward` ou saut SSH. Coûts assumés : tout client autorisé à
atteindre le Service peut **pusher** des images arbitraires (y compris écraser
des tags), et **tout pod du cluster peut tirer** (pas d'`imagePullSecret`).
Acceptable en mono-tenant ; inacceptable dès qu'on introduit du multi-tenancy.

### RStudio — `DISABLE_AUTH=true`

[ADR 0012](../decisions/0012-rstudio-disable-auth.md) conserve
`DISABLE_AUTH=true` (image `rocker/geospatial:4.6.0`), ce qui **désactive
complètement l'écran de login** : quiconque atteint le port 8787 ouvre une
session shell + RStudio en tant qu'utilisateur `rstudio`, avec accès à la PVC
`/home/rstudio/workspace` (RBD réplicat ×3, 1 Ti). Service de type
**`ClusterIP`** (pas de NodePort, pas de LoadBalancer Internet). L'ADR souligne
lui-même des **coûts plus importants que 0010/0011** : shell + filesystem
accessibles (exécution de code R/python avec réseau sortant, lecture/écriture de
la PVC, `system()` shell), et **pas d'audit utilisateur** (`auditd` voit
`uid=1000` mais pas quel humain est derrière). Garde-fous : ne **pas** exposer
via Ingress public ni LoadBalancer ; restreindre `tag:rstudio-user` si Tailscale
est utilisé ; sauvegarder régulièrement la PVC.

### Kubernetes Dashboard — `cluster-admin`

[ADR 0010](../decisions/0010-dashboard-cluster-admin.md) lie le compte de
service `admin-user` à **`cluster-admin`** : pas de moindre privilège imposé,
puisque l'opérateur qui se connecte au dashboard est aussi celui qui détient
`~/.kube/config` avec les mêmes droits. Point de sécurité notable sur
l'authentification : **pas de Secret de token persistant** (anti-pattern depuis
K8s 1.24 — token long-lived jamais rotaté, stocké en clair dans etcd). Les
tokens sont générés à la demande via l'API `TokenRequest`
(`kubectl -n kubernetes-dashboard create token admin-user --duration=8h`), donc
un token fuité **expire en ≤ 8 h**. `bootstrap/state.sh` vérifie d'ailleurs que
le `Secret admin-user` **n'existe pas** — preuve que la migration vers les
tokens éphémères est effective. Garde-fou : toujours `kubectl port-forward` +
accès local, jamais d'Ingress public.

### Le fil commun de ces trois compromis

Tous délèguent la sécurité au **contrôle d'accès au Service** et reposent sur la
même hypothèse : en mono-tenant, les pairs qui peuvent atteindre le Service sont
de confiance. Tous deviennent **caducs si le périmètre s'ouvre** (plusieurs
équipes, utilisateurs externes, accès public) — chaque ADR documente alors sa
sortie : activer l'auth (htpasswd/OIDC pour le registry, `PASSWORD` + comptes
par chercheur pour RStudio, rôles scopés et `0010-bis` pour le dashboard),
imposer le TLS, poser des `NetworkPolicy` strictes.

## Encadré honnêteté — SPOF et risques résiduels assumés

Plusieurs compromis sont **assumés** dans le modèle de menace et le redeviennent
problématiques si ce modèle change :

- **Sniffing du trafic Ceph.** Un attaquant passé sur le réseau cluster
  (`10.67.2.0/22`) peut sniffer le trafic Ceph et les credentials S3 : la
  sécurité périmétrique du réseau privé est le seul rempart
  ([ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md)).
  WireGuard Cilium ([ADR 0019](../decisions/0019-durcissement-reseau-cilium.md))
  atténue ce risque pour le trafic pod-to-pod, mais ne le supprime pas (msgr2
  reste en clair).
- **Disques retirés lisibles en clair** (`ceph bluestore`, pas de LUKS) : en cas
  de rebut, faire un `blkdiscard` ou un wipe physique
  ([ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md)).
- **Clé de chiffrement etcd en clair sur le control plane**
  (`/etc/kubernetes/enc/`, 0600 root) : un accès disque au nœud control plane
  permet de la lire. Le risque visé (vol d'un **snapshot** etcd) est couvert,
  mais pas l'accès disque au nœud lui-même — hors modèle, pas de KMS
  ([ADR 0014](../decisions/0014-durcissement-kubeadm-init.md)).
- **Snapshots etcd non chiffrés au repos — dette close, assumée.** Depuis le
  chiffrement secretbox, les Secrets sont déjà chiffrés _dans_ le snapshot ; ce
  qui reste en clair est l'inventaire d'objets (ConfigMaps, Deployments, RBAC…),
  soit de la **configuration, pas des credentials**. Chiffrer le contenant
  ajouterait une **clé privée hors-nœud = nouveau SPOF de restauration** (la
  perdre = snapshots irrécupérables au pire moment) et une étape de
  déchiffrement d'urgence. Mitigation retenue : permissions strictes
  (`/var/lib/etcd-backups` en `0700`, snapshots `0600` root) et copie hors-nœud
  sur **poste de confiance**. Porte de sortie si le modèle change : chiffrement
  asymétrique `age`
  ([ADR 0014](../decisions/0014-durcissement-kubeadm-init.md)).
- **RStudio = shell sans audit utilisateur**, et **dashboard `cluster-admin`** :
  une compromission de token = compromission complète du cluster pendant ≤ 8 h
  ([ADR 0010](../decisions/0010-dashboard-cluster-admin.md),
  [ADR 0012](../decisions/0012-rstudio-disable-auth.md)).
- **Bascule WireGuard à chaud = `HEALTH_WARN` transitoire** : activer WireGuard
  sur un cluster live roule le DaemonSet `cilium`, Ceph signale brièvement des «
  slow OSD heartbeats » (retour `HEALTH_OK` en ~70 s sur banc). En prod :
  appliquer hors heure de pointe
  ([ADR 0019](../decisions/0019-durcissement-reseau-cilium.md)).

Tous ces ADR convergent sur la même clause de réouverture : **si le cluster
cesse d'être mono-tenant / mono-admin / sur réseau isolé**, ou s'il héberge des
données réglementées, chacun doit être revu (KMS, auth, TLS, `NetworkPolicy`,
chiffrement Ceph msgr2, chiffrement des snapshots).

## Voir aussi

- [Exposition & réseau](../architecture/exposition-reseau.md) — exposition des
  services, TLS, accès distant Tailscale.
- [Validation sur banc](../architecture/validation-banc.md) — scénarios de test
  (WireGuard/Hubble, chiffrement etcd/audit).
