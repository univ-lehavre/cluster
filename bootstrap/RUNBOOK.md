# Runbook — Installation de Kubernetes

Procédure complète d'installation d'un cluster Kubernetes à partir de serveurs
Debian Trixie (13), depuis la préparation OS jusqu'à la jonction des workers.

## Préparation des serveurs

### Préparation des disques pour le stockage distribué

Afin de préparer les disques pour le stockage distribué, lancez le script
suivant pour supprimer toutes les traces d’installation précédentes.

```bash
sudo rm -fR /var/lib/rook

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y gdisk parted

wipe_all() {
    device=$1
    echo "Device: ${device}"
    sudo sgdisk --zap-all ${device}
    if [ "${device}" == "/dev/nvme1n1" ]; then
        sudo blkdiscard ${device}
    else
        sudo dd if=/dev/zero of=${device} bs=1M count=100 oflag=direct,dsync
    fi
    sudo partprobe ${device}
}

for device in /dev/sd[a-z]
do
    wipe_all ${device}
done

wipe_all /dev/nvme1n1

sudo reboot
```

Vérifiez le nettoyage

```bash
lsblk
```

Afin d’obtenir

```bash
NAME                    MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda                       8:0    0   5,5T  0 disk
sdb                       8:16   0   5,5T  0 disk
sdc                       8:32   0   5,5T  0 disk
sdd                       8:48   0   5,5T  0 disk
sde                       8:64   0   5,5T  0 disk
sdf                       8:80   0   5,5T  0 disk
sdg                       8:96   0   5,5T  0 disk
sdh                       8:112  0   5,5T  0 disk
sdi                       8:128  0   5,5T  0 disk
sdj                       8:144  0   5,5T  0 disk
sdk                       8:160  0   5,5T  0 disk
sdl                       8:176  0   5,5T  0 disk
nvme0n1                 259:1    0 447,1G  0 disk
├─nvme0n1p1             259:2    0   512M  0 part /boot/efi
├─nvme0n1p2             259:3    0   488M  0 part /boot
└─nvme0n1p3             259:4    0 446,1G  0 part
  ├─control1--vg-root   254:0    0 445,1G  0 lvm  /
nvme1n1                 259:5    0   2,9T  0 disk
```

### Installation du système d’exploitation

Image ISO : **Debian Trixie (13)** **avec firmware non-libre** (DVD officiel ou
netinst « with firmware »). Le firmware non-libre est obligatoire pour activer
les cartes réseau **Broadcom BCM57416** ; il est intégré aux ISO officielles
depuis Debian 12.4.

1. **Téléchargez l’image ISO** de Debian Trixie (13) avec firmware.
2. **Attachez l’image ISO** au serveur (KVM iLO / clé USB).
3. **Démarrez en mode expert** : au menu de boot, choisir **« Advanced options »
   → « Expert install »**. Le mode expert est nécessaire sur ce matériel pour
   pouvoir choisir manuellement l’interface câblée et saisir une IP statique
   (cf. ci-dessous).

#### Procédure réseau en mode expert (IP statique sur Broadcom BCM57416)

Le BIOS énumère 4 ports 10 GbE — seul **`ens10f0np0`** est câblé sur le réseau
cluster `10.0.0.0/22`. Il n’y a **pas de serveur DHCP** sur ce réseau, donc
toute autoconfiguration échoue : il faut configurer l’IP **manuellement**.

1. **Charger les composants d’installation** (étape « Load installer components
   from CD ») : laisser les défauts ; cocher éventuellement `network-console` si
   tu veux poursuivre l’install via SSH.
2. **Détecter le matériel réseau** : si l’installateur signale « **Firmware
   manquant : `bnxt/…`** », répondre **Oui, charger le firmware**. Avec l’ISO «
   with firmware » il est trouvé sur le média lui-même. Le pilote noyau
   **`bnxt_en`** est ensuite chargé automatiquement.
3. **Si rien n’est détecté**, basculer en console (`Alt+F2`) pour diagnostic :

   ```bash
   lspci -nn | grep -i ethernet   # doit lister le BCM57416 (vendor 14e4)
   modprobe bnxt_en               # force le chargement du pilote
   dmesg | tail -30               # cherche les erreurs de firmware
   ```

   Revenir à l’installateur (`Alt+F1`) et relancer « Détecter le matériel réseau
   ».

4. **Choix de l’interface** (l’installateur le demande en mode expert s’il y en
   a plusieurs) → choisir **`ens10f0np0`** (le port câblé ; les 3 autres ports
   n’ont pas de lien).
5. **Configuration automatique du réseau** : le DHCP va échouer (~30 s de
   timeout) — c’est attendu. Annuler dès qu’il propose un menu.
6. Au menu suivant, choisir **« Configurer le réseau manuellement »**, puis
   saisir :
   - Adresse IP : `10.0.0.11` (puis `.12`, `.13`, `.14` pour les workers)
   - Masque : `255.255.252.0` (= `/22`)
   - Passerelle : la passerelle réelle du `/22`
   - DNS : ton résolveur
   - Nom de machine : `cp1`, puis `node1`/`node2`/`node3`
   - Domaine : **vide**

> Si l’écran « manuel » n’apparaît jamais : soit le DHCP a abouti sur un autre
> port (revenir au menu principal et relancer « Configurer le réseau »), soit
> l’interface n’a pas été détectée (cf. firmware, étape 3).

### Partitionnement du disque de démarrage

> Ne concerne **que** le disque de démarrage (miroir NVMe HPE NS204i-p, ~447
> GiB). Les **12 HDD SAS 5,5 TiB et le NVMe `nvme1n1` 2,9 TiB restent bruts, non
> partitionnés** : ils sont consommés directement par Ceph (voir
> [`storage/ceph/cluster.yaml`](../storage/ceph/cluster.yaml)). Ne jamais créer
> de partition dessus.

Le défaut d’usine (`/home` = 404 G, `/var` = 9 G) étouffe `/var`, qui héberge
`containerd`, les logs, `/var/lib/rook` et `/var/lib/etcd`. On repartitionne
donc le disque de boot. **Tous les nœuds reçoivent le MÊME layout** (recette
d’installation unique, moins d’erreurs manuelles ; un nœud peut être promu
control plane sans repartitionner — cf. évolution HA,
[ADR 0002](../docs/decisions/0002-control-plane-unique-avec-endpoint.md)). La
seule LV dont l’usage diffère est `lv_etcd`, détaillée sous le tableau.

| Partition / LV | Taille   | Montage         | FS    | Rôle                                                                  |
| -------------- | -------- | --------------- | ----- | --------------------------------------------------------------------- |
| ESP            | 512 MiB  | `/boot/efi`     | FAT32 | amorçage EFI                                                          |
| `boot`         | 1 GiB    | `/boot`         | ext4  | noyaux + initramfs (marge Debian 13)                                  |
| `lv_root`      | 40 GiB   | `/`             | ext4  | OS, `/usr`, paquets                                                   |
| `lv_etcd`      | 10 GiB   | `/var/lib/etcd` | ext4  | isole etcd : I/O dédiées, protégé d’un `/var` plein — voir ci-dessous |
| `lv_var`       | ~360 GiB | `/var`          | ext4  | `containerd`, `kubelet`, `/var/log`, `/var/lib/rook` (mon)            |
| (libre)        | ~30 GiB  | —               | —     | extents LVM libres : snapshots / marge                                |
| swap           | —        | —               | —     | **aucun** (Kubernetes refuse le swap actif)                           |

> **`lv_etcd` selon le rôle du nœud :**
>
> - **Control plane (`cp1`)** : `lv_etcd` **héberge etcd** (la base d’état du
>   cluster). Indispensable : isole les I/O d’etcd et le protège d’un `/var`
>   saturé par containerd/logs/rook.
> - **Workers (`node1-3`)** : etcd ne tourne **pas** sur les workers →
>   `/var/lib/etcd` y reste **vide**. La LV est donc **inutilisée**, mais on la
>   **crée quand même** (recette identique partout) : promotion HA future sans
>   repartitionnement, et moins d’erreurs à l’install. Les ~9 Go immobilisés
>   sont négligeables face aux 12 × 5,5 To Ceph. Variante acceptable si l’espace
>   est compté : ne pas créer `lv_etcd` sur un worker et réaffecter ses 10 Go à
>   `lv_var` — au prix de l’uniformité.
>
> ⚠️ Sur les nœuds **control plane**, `lv_etcd` est une LV ext4 fraîchement
> formatée : elle contient un répertoire `lost+found` qui fait échouer le
> préflight `kubeadm init` (`[ERROR DirAvailable--var-lib-etcd]: not empty`). Le
> rôle `k8s-initialization` retire ce `lost+found` **avant** l’init (uniquement
> si la LV est vierge — jamais sur un etcd peuplé). Rien à faire à la main.

Procédure dans l’installateur Debian (partitionnement **manuel**) :

1. À l’étape « Partitionner les disques », choisir **Manuel**.
2. Sélectionner le disque de boot (~447 GiB) → créer une **nouvelle table de
   partitions** vide (GPT).
3. Créer la partition **EFI** : 512 Mo, usage **« Partition système EFI »**.
   L'installateur la monte automatiquement sur `/boot/efi` (il ne demande pas de
   point de montage : c'est normal) et pose le bon type GPT. **Aucun drapeau
   d'amorçage à activer** — le « bootable flag » est un concept MBR, inutile en
   UEFI.
4. Créer **`/boot`** : 1 Go, `ext4`, point de montage `/boot`.
5. Créer une partition occupant **tout l’espace restant**, usage « volume
   physique pour LVM ».
6. Entrer dans « Configurer le gestionnaire de volumes logiques (LVM) » :
   - créer le groupe de volumes **`cp1-vg`** sur ce volume physique ;
   - y créer les volumes logiques : **`root` 40 Go**, **`var` 360 Go**, **`etcd`
     10 Go** ; **laisser ~30 Go non alloués** dans le VG.
7. De retour dans le partitionnement, formater et monter chaque LV :
   - `root` → `/` en `ext4` ;
   - `var` → `/var` en `ext4` ;
   - `etcd` → `/var/lib/etcd` en `ext4` (l’installateur ordonne les montages
     imbriqués automatiquement).
8. **Ne pas créer de partition d’échange (swap).**
9. « Terminer le partitionnement » et appliquer les changements.

`/tmp` est déjà monté en **tmpfs** par défaut sur Debian 13 (systemd ≥ 256
active `tmp.mount` d’office) — rien à faire en post-installation.

> **Workers `node1-3`** : appliquer **exactement la même recette** (mêmes LV,
> mêmes tailles, VG nommé d’après le nœud — `node1-vg`…). `lv_etcd` y est créée
> mais reste inutilisée (cf. encadré « `lv_etcd` selon le rôle du nœud »
> ci-dessus). Ne pas la supprimer, sauf contrainte d’espace explicite.

### Configuration réseau

Chaque nœud reçoit une **IP statique** sur le port 10 GbE actif `ens10f0np0`
(réseau `10.0.0.0/22`). Le plus simple est le défaut Debian (ifupdown), le
fichier `/etc/network/interfaces` (sans extension) :

| Nœud  | IP           |
| ----- | ------------ |
| cp1   | 10.0.0.11/22 |
| node1 | 10.0.0.12/22 |
| node2 | 10.0.0.13/22 |
| node3 | 10.0.0.14/22 |

Exemple pour `cp1` :

```text
auto ens10f0np0
iface ens10f0np0 inet static
    address 10.0.0.11/22
    gateway 10.0.0.1           # à adapter : passerelle réelle du /22
    dns-nameservers 10.0.0.1   # à adapter : résolveur(s) DNS
```

Appliquer avec `sudo systemctl restart networking` (ou au redémarrage).

Cette configuration peut être saisie directement à l'étape « Configurer le
réseau » de l'installateur en choisissant **Configuration manuelle** ; y
renseigner aussi le **nom de machine** (`cp1`, `node1`, `node2`, `node3`) et
laisser le **domaine** vide. Vérifier la passerelle et le DNS réels du `/22`
(non documentés dans le dépôt).

> Alternatives selon le gestionnaire réseau : `systemd-networkd`
> (`/etc/systemd/network/*.network`) ou NetworkManager
> (`/etc/NetworkManager/system-connections/*.nmconnection`).

## Premier accès SSH

Le script [`first-access.sh`](first-access.sh) automatise le **strict minimum**
nécessaire pour qu'Ansible puisse ensuite piloter les nœuds sans mot de passe,
**et** ferme immédiatement la fenêtre d'authentification par mot de passe :

- dépôt de la clé publique de l'opérateur (`ssh-copy-id`) ;
- règle `sudo NOPASSWD` pour `debian` ;
- **durcissement `sshd`** via drop-in `/etc/ssh/sshd_config.d/00-hardening.conf`
  (`PasswordAuthentication no`, `PermitRootLogin no`, `AllowUsers debian`,
  `MaxAuthTries 3`, `ClientAlive*`).

Le reste du hardening (mises à jour automatiques, UFW, fail2ban, auditd,
postfix, expiration de mot de passe) est délégué à
[`server-security`](https://github.com/univ-lehavre/server-security) — cf.
section suivante.

Pré-requis : disposer d'une clé SSH locale.

```bash
ssh-keygen -t ed25519               # si absent
bash bootstrap/first-access.sh      # cibles par défaut : cp1 node1 node2 node3
```

Variantes :

```bash
# Sélectionner les nœuds explicitement
bash bootstrap/first-access.sh cp1 node1

# Changer le mot de passe debian dans la foulée
NEW_DEBIAN_PASSWORD='choisir-un-mot-de-passe-robuste' \
  bash bootstrap/first-access.sh
```

La 1re passe demande **deux fois** le mot de passe par hôte (`ssh-copy-id` puis
`sudo`). Les runs suivants sont silencieux et idempotents.

### Vérification : le mot de passe `debian` a-t-il été modifié depuis l'install ?

`bootstrap/state.sh` couche 1 compare la date du dernier `passwd`
(`chage -l debian`) à la date de création de `/etc/machine-id` (= premier boot
post-install). Si l'écart est ≤ 1 jour, l'utilisateur n'a **jamais** changé le
mot de passe d'installation → drift `fail` avec remédiation suggérée
(`NEW_DEBIAN_PASSWORD=… bash bootstrap/first-access.sh <hôte>`). Sinon, `ok`
avec le nombre de jours écoulés.

## Durcissement de l'OS (`bootstrap/security/`)

Les rôles Ansible de durcissement complet sont fusionnés dans ce dépôt via
`git subtree` sous [`bootstrap/security/`](security/) : `unattended-upgrades`,
**UFW**, `fail2ban`, `auditd`, `postfix` (redirection des mails système),
gestion du compte admin (expiration mot de passe). Origine :
`univ-lehavre/server-security` (DOI
[`10.5281/zenodo.16983614`](https://doi.org/10.5281/zenodo.16983614)).

Le `sshd` est durci **uniquement** par `first-access.sh` (drop-in
`/etc/ssh/sshd_config.d/00-hardening.conf`), de même que le dépôt de la clé
publique (`ssh-copy-id`). `secure.yml` ne re-touche plus le `sshd` ni les clés :
les anciens tags `sshd`/`ssh-keys` (doublon Ansible, avec un `AllowUsers`
variable risqué) ont été retirés. `first-access.sh` est la **source unique**.

Le playbook `secure.yml` est **entièrement opt-in** : sans `--tags`, il ne
touche à rien (il charge juste les variables). Voir
[`bootstrap/security/IMPLICATIONS.md`](security/IMPLICATIONS.md) pour, couche
par couche, ce qui change, ce qui est protégé, le compromis assumé, et la
commande pour s'en convaincre soi-même.

```bash
cd bootstrap/security
cp .env-example .env && $EDITOR .env       # MAIL_ROOT_REDIRECT, HOST_USER, …
set -a; source .env; set +a
```

**Menu** — chaque commande active une seule couche (et seulement celle-là) :

```bash
ansible-playbook -i ../hosts.yaml secure.yml --tags os          # mises à jour auto + expiration mot de passe
ansible-playbook -i ../hosts.yaml secure.yml --tags alert       # postfix + redirection mail root
ansible-playbook -i ../hosts.yaml secure.yml --tags audit       # auditd + règles
ansible-playbook -i ../hosts.yaml secure.yml --tags detection   # fail2ban (anti-brute-force SSH)
ansible-playbook -i ../hosts.yaml secure.yml --tags upgrade     # apt full-upgrade + reboot (serial:1) — opérationnel
ansible-playbook -i ../hosts.yaml secure.yml --tags ufw         # APRÈS bootstrap K8s — cf. ports
```

Tout faire d'un coup (sauf upgrade et ufw) :

```bash
ansible-playbook -i ../hosts.yaml secure.yml --tags os,alert,audit,detection
```

**Voir ce qui est en place** — tableau de bord agrégé par hôte :

```bash
bash bootstrap/security/report.sh                    # tous les hôtes
bash bootstrap/security/report.sh cp1           # un hôte
```

Le rapport affiche les preuves observables : services actifs/inactifs/absents,
sortie de `sshd -T`, dernier `unattended-upgrades.log`, alias root, IPs bannies
par fail2ban, règles auditd chargées, état UFW, expiration mot de passe. Lecture
seule, ne modifie rien.

> ⚠️ **UFW × Kubernetes** : le rôle `network/ufw.yml` durcit le pare-feu avec un
> jeu de règles complet K8s/Cilium/Ceph (audit P6 #24). Plutôt qu'énumérer les
> ~30 ports inter-nœuds, il **autorise tout le trafic entre nœuds du cluster**
> (plage `CLUSTER_CIDR`, défaut `10.0.0.0/22`) — ce qui couvre API server, etcd,
> kubelet, VXLAN Cilium et mon/osd Ceph sans risque d'oubli — puis restreint les
> accès externes : **SSH limité** à `SSH_ADMIN_CIDR` (défaut = réseau cluster)
> et plage **NodePort** `30000-32767/tcp` ouverte pour les services exposés.
>
> **À n'activer qu'APRÈS le bootstrap K8s** (`secure.yml --tags ufw`) : activer
> UFW avant que le cluster existe couperait l'init. L'état d'UFW est surveillé
> par [`state.sh`](state.sh) (couche 2) — un UFW actif sans la règle
> inter-nœuds, ou installé mais inactif, est signalé comme **drift**.

La désactivation du swap n'apparaît plus ici : elle est gérée automatiquement
par le rôle Ansible `k8s-pre-install` du présent dépôt (`checks.yaml`).

## Installation de k8s

### CNI

L'inventaire réel (`bootstrap/hosts.yaml`) n'est **pas versionné** : c'est une
spécificité de déploiement
([ADR 0023](../docs/decisions/0023-plateforme-exemple-generique.md)). Copiez le
modèle générique versionné puis renseignez vos nœuds :

```bash
cp bootstrap/hosts.example.yaml bootstrap/hosts.yaml
# puis éditer bootstrap/hosts.yaml avec les noms/IP réels
```

Le modèle ([`hosts.example.yaml`](hosts.example.yaml)) a la forme :

```yaml
cloud:
  children:
    control:
    workers:

control:
  hosts:
    cp1:

workers:
  hosts:
    node1:
    node2:
```

Ensuite, exécutez les playbooks Ansible pour installer Kubernetes.

```bash
ansible-playbook -i ./hosts.yaml ./os-upgrade.yaml
ansible-playbook -i ./hosts.yaml ./checks.yaml
ansible-playbook -i ./hosts.yaml ./cri.yaml
ansible-playbook -i ./hosts.yaml ./kubeadm.yaml
ansible-playbook -i ./hosts.yaml ./control-planes.yaml
ansible-playbook -i ./hosts.yaml ./initialisation.yaml
```

Déplacez le fichier `cni.sh` sur le control plane (control1).

```bash
scp ./cni.sh control1:/home/debian
```

Exécutez le script sur le control node. Puis, une fois que les pods sont
disponibles, lancez la série de tests.

```bash
bash ./cni.sh
cilium connectivity test
```

#### Exposition réseau tout-Cilium (`kubeProxyReplacement` + LB-IPAM + L2 + Gateway API)

Cilium assure l'**exposition réseau** du cluster, en remplacement de MetalLB et
d'ingress-nginx
([ADR 0020](../docs/decisions/0020-exposition-reseau-tout-cilium.md)).
[`cni.sh`](cni.sh) arme désormais, à l'install **et** à l'upgrade :

- **`kubeProxyReplacement=true`** (datapath eBPF) + `k8sServiceHost=cluster-api`
  - `k8sServicePort=6443` (obligatoires sans kube-proxy : l'agent ne joint plus
    l'API via la ClusterIP `kubernetes.default`). En 1.19 le flag est un booléen
    et active déjà NodePort/HostPort/ExternalIPs.
- **LB-IPAM + `l2announcements.enabled=true`** (+ `k8sClientRateLimit` relevé) :
  IP LoadBalancer + annonce ARP, remplacent MetalLB.
- **`gatewayAPI.enabled=true`** : bordure L7 (Envoy intégré), remplace
  ingress-nginx.

Les pools/policies/GatewayClass sont des CRs versionnés sous
[`platform/cilium-expo/`](../platform/cilium-expo/) ; les **CRDs Gateway API
v1.4.1 doivent être pré-installées** (voir le README de cet addon).

Retrait de `kube-proxy` : sur un cluster **neuf**, `kubeadm init` ne le déploie
plus (`skipPhases: [addon/kube-proxy]` dans la config kubeadm). Sur un cluster
**existant**, `cni.sh` le retire **après** avoir vérifié
`KubeProxyReplacement: True`, puis purge les règles iptables `KUBE-*` (à répéter
sur chaque nœud : `iptables-save | grep -v KUBE | iptables-restore`, en root).

**Valider sur le banc multi-nœuds avant la prod** : pas de régression de
service-routing après la bascule eBPF (Ceph `HEALTH_OK`, CoreDNS, ClusterIP
applicatifs), attribution d'IP du pool, annonce ARP, failover L2. La plage prod
du pool LB-IPAM reste **TODO** (arbitrage admin réseau, ADR 0020).

### Join workers to cluster

```bash
ansible-playbook -i ./hosts.yaml ./join-workers.yaml
```

### Installation de la connexion en local

Récupérer le kubeconfig depuis le control plane. Le cluster est nommé
`cluster-prod` (champ `clusterName`, ADR 0053) → son contexte est
`kubernetes-admin@cluster-prod`, **distinct** de l'homonyme kubeadm par défaut.
**Ne pas écraser** `~/.kube/config` : le **fusionner** pour cohabiter avec
d'autres clusters (un banc Lima `cluster-banc`, par ex.) sans collision.

```bash
mkdir -p ~/.kube
scp control1:/home/debian/.kube/config /tmp/cluster-prod.config
# Fusion (--flatten) — jamais d'écrasement (cohabite avec d'autres clusters).
KUBECONFIG=~/.kube/config:/tmp/cluster-prod.config \
  kubectl config view --flatten > ~/.kube/config.merged && mv ~/.kube/config.merged ~/.kube/config
rm -f /tmp/cluster-prod.config
```

> ⚠️ **NE PAS laisser la prod en contexte par défaut** (`current-context`) de
> `~/.kube/config` — c'est un pistolet chargé (ADR 0053). Dans un terminal frais
> SANS `KUBECONFIG` exporté, un `kubectl` nu vise le contexte courant : si c'est
> `cluster-prod`, tu MUTES la prod par accident (vécu : `kubectl get pods -A`
> après un terminal neuf tombait sur la prod). L'outil `nestor` ne pose
> `KUBECONFIG` que pour SES commandes (`env`/`stack select`) ; il ne touche
> jamais `~/.kube/config` (ta config perso). Donc **la cible de `kubectl` nu est
> TON affaire** :
>
> - poser un contexte INOFFENSIF par défaut (banc, ou un contexte vide) :
>   `kubectl config use-context cluster-banc` (ou `default`) ;
> - viser la prod TOUJOURS **explicitement** :
>   `kubectl --context kubernetes-admin@cluster-prod get …` ;
> - ou, pour une session prod assumée, `eval "$(bench/lima/env.sh export)"` côté
>   banc et un `export KUBECONFIG=…` côté prod — jamais le contexte par défaut.

<!-- séparateur : deux blockquotes distincts (MD028) -->

> Cluster prod **déjà installé** sans `clusterName` (contexte homonyme
> `kubernetes-admin@kubernetes`) ? Rejouer `bootstrap/initialisation.yaml` n'est
> pas nécessaire : renommer le contexte en place
> (`kubectl config rename-context kubernetes-admin@kubernetes kubernetes-admin@cluster-prod`)
> avant la fusion.

Indiquez dans le contexte l’adresse IP du control plane (control1). Ensuite,
vous pouvez vérifier que tout fonctionne correctement en exécutant les commandes
suivantes :

```bash
k get nodes
k get pods --all-namespaces
```

### Accès distant aux services du cluster

L'accès distant aux services internes (dashboards, consoles, API d'opérateurs)
passe par `kubectl port-forward` depuis un poste autorisé à joindre l'API
Kubernetes — il n'y a **pas** de réseau d'overlay ni de VPN dédié
([ADR 0003](../docs/decisions/0003-pas-de-chiffrement-ceph-tailscale.md)). Le
poste de contrôle dispose déjà du kubeconfig fusionné (section précédente) ; le
tunnel est local au poste et ne traverse que l'API server.

```bash
# Exposer localement un service ClusterIP (ex. un dashboard) :
kubectl -n <namespace> port-forward svc/<service> <port-local>:<port-service>
# puis ouvrir http://localhost:<port-local>
```

Le tunnel reste actif tant que la commande tourne ; le couper (`Ctrl+C`) ferme
l'accès. Aucun port supplémentaire n'est ouvert sur les nœuds.

### Installation de Ceph

Voir [`storage/ceph/RUNBOOK.md`](../storage/ceph/RUNBOOK.md).

## Audit-log et rollback

### Audit-log : qui a fait quoi quand sur chaque nœud

Chaque playbook bootstrap invoque en `pre_tasks` le rôle
[`audit-log`](roles/audit-log/), qui pose une ligne dans
`/var/log/cluster-bootstrap.log` du nœud cible :

```text
2026-05-28T14:32:01Z playbook=cri.yaml from=pierre@laptop ssh-as=debian
```

Format : timestamp UTC ISO-8601, nom du playbook, identité de l'opérateur sur le
poste de contrôle (`$USER@hostname`), nom du compte SSH côté serveur (`debian`).

> ⚠️ **Ce n'est pas une preuve de non-répudiation** (audit P6). L'identité
> opérateur (`$USER@hostname`) provient de variables d'environnement **côté
> contrôle** — falsifiables par celui qui lance le playbook. Ce journal est un
> outil d'**exploitation** (« quel playbook a tourné quand »), pas une preuve
> opposable. Pour la traçabilité forte, s'appuyer sur ce qui est journalisé
> **côté serveur** et non falsifiable par l'opérateur : `sshd` en
> **`LogLevel VERBOSE`** (déjà posé par le rôle sshd — empreinte de clé publique
> à chaque connexion) et **`auditd`** (couche `--tags audit` — syscalls
> privilégiés). Corréler les deux donne « quelle clé, quand, quels actes ».

Lecture :

```bash
ssh debian@cp1 'sudo tail -n 20 /var/log/cluster-bootstrap.log'
```

[`bootstrap/state.sh`](state.sh) **couche 0** lit ce journal et affiche par nœud
:

- le dernier playbook joué + son âge → suivi rapide.
- l'absence totale de trace → drift potentiel : OS installé mais aucun bootstrap
  appliqué, ou rotation/effacement du log.

#### Initialiser le journal sur des nœuds existants (baseline)

Si les nœuds ont été installés/durcis manuellement **avant** l'introduction du
rôle `audit-log`, le fichier `/var/log/cluster-bootstrap.log` n'existe pas →
state.sh signale un drift sur la couche 0. Pour matérialiser « état initial
reconnu après le fait » sans rejouer tout le bootstrap :

```bash
cd bootstrap
ansible-playbook -i hosts.yaml audit-log-baseline.yaml
```

[`audit-log-baseline.yaml`](audit-log-baseline.yaml) appose une ligne « baseline
» et débloque la couche 0. Les playbooks suivants ajouteront des lignes normales
par-dessus.

### Rollback du bootstrap K8s

[`rollback.yaml`](rollback.yaml) ramène un nœud à un état "Debian 13 +
utilisateur debian + first-access" — comme si aucun playbook K8s n'avait été
joué :

```bash
# Sur le banc Lima, l'inventaire est généré par run-phases.sh dans son WORKDIR
# (bench/lima/.work/inventory.yaml). On rejoue le rollback contre cet inventaire :
ansible-playbook -i ../bench/lima/.work/inventory.yaml rollback.yaml \
  -e confirm=yes --limit cp1
```

> Au banc, préférer le **chemin nommé codé** plutôt qu'un enchaînement manuel
> (ADR 0045) : `BANC_JETABLE=1 bench/lima/run-phases.sh rollback <phase>` défait
> une phase pour la re-tester (ADR 0054). La commande ci-dessus reste utile pour
> un rollback **complet** du bootstrap (hors phases plateforme).

Ce que le rollback fait :

- `kubeadm reset --force`
- stoppe + désactive `kubelet` et `containerd`
- `apt purge` des paquets K8s et `containerd.io`, autoremove
- supprime `/etc/kubernetes`, `/etc/cni`, `/etc/containerd`,
  `/var/lib/{kubelet,etcd,cni}`, `/opt/cni`, les drop-ins `modules-load.d` et
  `sysctl.d` posés par le bootstrap, et les dépôts APT correspondants
- décharge les modules `overlay` et `br_netfilter`

Ce que le rollback **ne** touche **pas** :

- [`first-access.sh`](first-access.sh) (drop-in sshd + sudoers + clé SSH) ;
- [`security/secure.yml`](security/) (hardening opt-in : auditd, fail2ban, mises
  à jour automatiques) ;
- [le partitionnement et l'installation OS](#partitionnement-du-disque-de-démarrage)
  ;
- les **disques Ceph** + `/var/lib/rook` → utiliser
  [`storage/ceph/cleanup.sh`](../storage/ceph/cleanup.sh).

Cas d'usage typique sur le banc :

```bash
# 1. Bootstrap complet
for p in checks cri kubeadm control-planes initialisation; do
  ansible-playbook -i inventory.yaml ../../bootstrap/$p.yaml
done

# 2. Rollback
ansible-playbook -i inventory.yaml ../../bootstrap/rollback.yaml -e confirm=yes

# 3. Re-bootstrap (test d'idempotence à blanc)
for p in checks cri kubeadm control-planes initialisation; do
  ansible-playbook -i inventory.yaml ../../bootstrap/$p.yaml
done
```

## Maintenance

### Mise à jour des systèmes d’exploitation

```bash
ansible-playbook -i ./hosts.yaml ./os-upgrade.yaml
```

### Mise à jour de Kubernetes (upgrade in-place — ADR 0015)

Montée de version K8s **in-place**, séquencée (control plane d'abord, puis
workers un par un). **Une mineure à la fois** ; vérifier la compat croisée
Cilium/Rook/Ceph
([ADR 0006](../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md))
**avant**, et **valider sur le banc multi-node** d'abord.

```bash
# Patch (1.34.x → 1.34.y) :
ansible-playbook -i ./hosts.yaml ./k8s-upgrade.yaml \
  -e k8s_upgrade_version=1.34.9

# Mineure (1.34 → 1.35) : bascule aussi le dépôt apt vers la mineure cible.
ansible-playbook -i ./hosts.yaml ./k8s-upgrade.yaml \
  -e k8s_upgrade_version=1.35.0 -e k8s_upgrade_repo_minor=v1.35
```

Le playbook draine chaque nœud avant son upgrade et le `uncordon` ensuite ; un
seul nœud est indisponible à la fois. L'API est brièvement coupée pendant
l'`apply` sur le control plane (SPOF assumé,
[ADR 0002](../docs/decisions/0002-control-plane-unique-avec-endpoint.md)).
Détails et compromis :
[ADR 0015](../docs/decisions/0015-strategie-upgrade-kubernetes.md).

### Sauvegarde etcd (SPOF assumé)

Le cluster fonctionne avec **1 seul control plane** (`cp1`) — décision assumée
(cf. [ADR 0002](../docs/decisions/0002-control-plane-unique-avec-endpoint.md)).
C'est un **SPOF** : la perte du nœud control plane → cluster inutilisable
jusqu'à restauration. Mitigations :

1. **`--control-plane-endpoint cluster-api:6443` posé dès `kubeadm init`** (rôle
   `k8s-initialization`) : l'API est référencée par un nom DNS stable, donc un
   futur ajout de control planes n'imposera pas de réinstaller les workers.
2. **Sauvegarde etcd horaire** via le rôle [`etcd-backup`](roles/etcd-backup/) :

   ```bash
   ansible-playbook -i ./hosts.yaml ./etcd-backup.yaml
   ```

   Pose un script `/usr/local/sbin/etcd-snapshot.sh` + un timer systemd
   `etcd-snapshot.timer` qui exécute `etcdctl snapshot save` chaque heure et
   garde les **24 derniers snapshots** dans `/var/lib/etcd-backups/`. Vérifier :

   ```bash
   systemctl status etcd-snapshot.timer
   systemctl list-timers etcd-snapshot.timer
   ls -la /var/lib/etcd-backups/
   ```

3. **Copie hors-nœud** via [`etcd-fetch.yaml`](etcd-fetch.yaml) (audit P1 #3) :
   les snapshots du point 2 restent **sur le control plane** → perdus si `cp1`
   meurt. Ce playbook rapatrie le snapshot le plus récent vers le **poste de
   contrôle** (dossier `etcd-snapshots/`, gitignoré) :

   ```bash
   ansible-playbook -i ./hosts.yaml ./etcd-fetch.yaml
   ```

   **RPO** = fréquence de ce fetch. Recommandé : le planifier côté admin (cron /
   launchd), p. ex. toutes les 6 h → RPO ≤ 6 h hors-nœud (et ≤ 1 h sur le nœud
   via le timer horaire). ⚠️ Le snapshot contient **tous les Secrets** (etcd non
   chiffré, [ADR 0014](../docs/decisions/0014-durcissement-kubeadm-init.md)) :
   garder `etcd-snapshots/` sur un poste de confiance.

#### Restauration etcd (procédure)

Sur le control plane à restaurer (ou un nouveau nœud qui va prendre sa place),
avec un snapshot copié dans `/tmp/etcd-snapshot.db` :

```bash
# 1. Arrêter le kubelet et tous les conteneurs (sinon etcd ne se laisse
#    pas remplacer "sous lui").
sudo systemctl stop kubelet
sudo crictl ps -q | xargs -r sudo crictl stop
sudo crictl ps -q | xargs -r sudo crictl rm

# 2. Restaurer le snapshot vers un nouveau data-dir.
sudo rm -rf /var/lib/etcd-restore
sudo ETCDCTL_API=3 etcdctl snapshot restore /tmp/etcd-snapshot.db \
  --name "$(hostname)" \
  --initial-cluster "$(hostname)=https://$(hostname -I | awk '{print $1}'):2380" \
  --initial-advertise-peer-urls "https://$(hostname -I | awk '{print $1}'):2380" \
  --data-dir /var/lib/etcd-restore

# 3. Remplacer l'ancien data-dir (sauvegarde de sécurité incluse).
sudo mv /var/lib/etcd /var/lib/etcd.before-restore-$(date +%s)
sudo mv /var/lib/etcd-restore /var/lib/etcd

# 4. Redémarrer kubelet → l'API + etcd remontent sur le snapshot.
sudo systemctl start kubelet
kubectl get nodes      # attendre que les nœuds redeviennent Ready
```

> Tester cette procédure **sur le banc Lima multi-nœuds** avant d'en avoir
> besoin en prod (cf. [`bench/lima/`](../bench/lima/)).

### Rotation de la clé de chiffrement etcd (ADR 0014)

Les Secrets sont chiffrés at-rest dans etcd (provider `secretbox`, clé dans
`/etc/kubernetes/enc/key1.b64`, posée au bootstrap par `k8s-initialization`).
**Faire tourner la clé** sur événement (suspicion de compromission, départ d'un
admin) ou échéance (ex. annuelle). La rotation est **manuelle** (pas de KMS —
choix ADR 0003) ; elle ne perd aucune donnée si l'ordre est respecté.

> ⚠️ Ne **jamais** se contenter de remplacer la clé : tant qu'un Secret reste
> chiffré avec l'ancienne, la retirer le rend illisible. L'étape de réécriture
> (3) est obligatoire.

```bash
ENC=/etc/kubernetes/enc/encryption-config.yaml

# 1. Générer une nouvelle clé et l'ajouter EN TÊTE (key2 chiffre ; key1 reste
#    pour déchiffrer l'existant). Éditer $ENC :
#       providers:
#         - secretbox:
#             keys:
#               - name: key2
#                 secret: <openssl rand -base64 32>
#               - name: key1
#                 secret: <ancienne valeur>
#         - identity: {}

# 2. Redémarrer l'API server (static pod) → il connaît key2 + key1.
sudo touch /etc/kubernetes/manifests/kube-apiserver.yaml
# attendre que `kubectl version` réponde de nouveau

# 3. Réécrire TOUS les Secrets → ils basculent sur key2 (la 1ʳᵉ clé).
kubectl get secrets -A -o json | kubectl replace -f -

# 4. Retirer key1 de $ENC (ne garder que key2), re-déclencher le redémarrage,
#    et remplacer key1.b64 par la nouvelle clé pour les prochains bootstraps.
sudo touch /etc/kubernetes/manifests/kube-apiserver.yaml
```

Vérifier qu'un Secret est bien chiffré après chaque étape (`k8s:enc:secretbox:`)
via `etcdctl` — c'est ce que fait le scénario
[`bench/scenarios/15-etcd-encryption-audit.sh`](../bench/scenarios/15-etcd-encryption-audit.sh)
(`ROTATE=1` déroule et vérifie toute la rotation, témoin inclus). **Tester sur
le banc avant la prod.**

### Vérifier une release signée (cosign / SLSA — ADR 0088)

Si vous installez à partir d'une **version figée** (et non du HEAD), chaque
release publie une archive source signée — vérifiez son **intégrité** et sa
**provenance** avant usage. Les assets de la release (onglet _Releases_) :
`cluster-<TAG>.tar.gz`, sa signature `.sig` + son certificat `.pem` (cosign), et
l'attestation de provenance `*.intoto.jsonl` (SLSA). Signature **keyless** :
aucune clé publique à récupérer, l'identité est le workflow GitHub lui-même.

```bash
TAG=v2.38.0   # la version visée
gh release download "$TAG" --repo univ-lehavre/cluster   # archive + .sig + .pem + provenance

# 1. Intégrité + identité du signataire (cosign keyless) :
cosign verify-blob \
  --certificate "cluster-${TAG}.pem" \
  --signature   "cluster-${TAG}.tar.gz.sig" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/univ-lehavre/cluster/\.github/workflows/release\.yml@.*' \
  "cluster-${TAG}.tar.gz"

# 2. Provenance SLSA (l'archive vient bien de CE dépôt, à CE commit) :
slsa-verifier verify-artifact "cluster-${TAG}.tar.gz" \
  --provenance-path *.intoto.jsonl \
  --source-uri github.com/univ-lehavre/cluster
```

Une vérification qui échoue (signature invalide, identité inattendue, source
divergente) = **archive non fiable** : ne pas l'utiliser. La signature ne vit
**que** dans le code versionné
([`.github/workflows/release.yml`](../.github/workflows/release.yml)),
re-prouvée à chaque release — pas d'étape manuelle (ADR 0088).
