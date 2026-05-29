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
cluster `10.67.2.0/22`. Il n’y a **pas de serveur DHCP** sur ce réseau, donc
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
   - Adresse IP : `10.67.2.11` (puis `.12`, `.13`, `.14` pour les workers)
   - Masque : `255.255.252.0` (= `/22`)
   - Passerelle : la passerelle réelle du `/22`
   - DNS : ton résolveur
   - Nom de machine : `dirqual1` (puis 2/3/4)
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
donc le disque de boot ainsi (control plane `dirqual1`) :

| Partition / LV | Taille   | Montage         | FS    | Rôle                                                                |
| -------------- | -------- | --------------- | ----- | ------------------------------------------------------------------- |
| ESP            | 512 MiB  | `/boot/efi`     | FAT32 | amorçage EFI                                                        |
| `boot`         | 1 GiB    | `/boot`         | ext4  | noyaux + initramfs (marge Debian 13)                                |
| `lv_root`      | 40 GiB   | `/`             | ext4  | OS, `/usr`, paquets                                                 |
| `lv_etcd`      | 10 GiB   | `/var/lib/etcd` | ext4  | isole etcd (control plane) : I/O dédiées, protégé d’un `/var` plein |
| `lv_var`       | ~360 GiB | `/var`          | ext4  | `containerd`, `kubelet`, `/var/log`, `/var/lib/rook` (mon)          |
| (libre)        | ~30 GiB  | —               | —     | extents LVM libres : snapshots / marge                              |
| swap           | —        | —               | —     | **aucun** (Kubernetes refuse le swap actif)                         |

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
   - créer le groupe de volumes **`dirqual1-vg`** sur ce volume physique ;
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

> **Workers `dirqual2-4`** : layout identique, sauf que `lv_etcd` est inutile
> (pas de control plane) → réaffecter ses 10 Go à `var`, ou conserver la même
> recette pour l’uniformité (la LV reste alors simplement inutilisée).

### Configuration réseau

Chaque nœud reçoit une **IP statique** sur le port 10 GbE actif `ens10f0np0`
(réseau `10.67.2.0/22`). Le plus simple est le défaut Debian (ifupdown), le
fichier `/etc/network/interfaces` (sans extension) :

| Nœud     | IP            |
| -------- | ------------- |
| dirqual1 | 10.67.2.11/22 |
| dirqual2 | 10.67.2.12/22 |
| dirqual3 | 10.67.2.13/22 |
| dirqual4 | 10.67.2.14/22 |

Exemple pour `dirqual1` :

```text
auto ens10f0np0
iface ens10f0np0 inet static
    address 10.67.2.11/22
    gateway 10.67.0.1          # à adapter : passerelle réelle du /22
    dns-nameservers 10.67.0.1  # à adapter : résolveur(s) DNS
```

Appliquer avec `sudo systemctl restart networking` (ou au redémarrage).

Cette configuration peut être saisie directement à l'étape « Configurer le
réseau » de l'installateur en choisissant **Configuration manuelle** ; y
renseigner aussi le **nom de machine** (`dirqual1`…`dirqual4`) et laisser le
**domaine** vide. Vérifier la passerelle et le DNS réels du `/22` (non
documentés dans le dépôt).

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
bash bootstrap/first-access.sh      # cibles par défaut : dirqual1..dirqual4
```

Variantes :

```bash
# Sélectionner les nœuds explicitement
bash bootstrap/first-access.sh dirqual1 dirqual2

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

Le `sshd` est déjà durci par `first-access.sh` (drop-in) avant ce passage ; si
le rôle `network/sshd` retouche `sshd`, ses changements doivent rester
**cohérents** avec le drop-in (ordre alphanumérique des `*.conf` ; ce dernier
gagne en cas de conflit de directive).

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
ansible-playbook -i ../hosts.yaml secure.yml --tags sshd        # re-applique drop-in sshd (déjà fait par first-access.sh)
ansible-playbook -i ../hosts.yaml secure.yml --tags ssh-keys    # re-dépose les clés
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
bash bootstrap/security/report.sh dirqual1           # un hôte
```

Le rapport affiche les preuves observables : services actifs/inactifs/absents,
sortie de `sshd -T`, dernier `unattended-upgrades.log`, alias root, IPs bannies
par fail2ban, règles auditd chargées, état UFW, expiration mot de passe. Lecture
seule, ne modifie rien.

> ⚠️ **UFW × Kubernetes** : le rôle `network/ufw.yml` durcit le pare-feu. Pour
> que les workers puissent joindre le control plane et que Cilium fonctionne, il
> faut autoriser les ports K8s/Cilium (`6443/tcp`, `10250/tcp`, `2379-2380/tcp`,
> `30000-32767/tcp`, VXLAN `8472/udp`, Cilium health `4240/tcp`) — soit en
> étendant `roles/network/files/ufw.yml`, soit en reportant l'activation d'UFW à
> après le bootstrap du cluster.

La désactivation du swap n'apparaît plus ici : elle est gérée automatiquement
par le rôle Ansible `k8s-pre-install` du présent dépôt (`checks.yaml`).

## Installation de k8s

### CNI

Modifiez le fichier `hosts.yaml` pour y indiquer les adresses IP des machines du
cluster. Par exemple :

```yaml
cloud:
  children:
    control:
    workers:

control:
  hosts:
    control1:

workers:
  hosts:
    worker1:
    worker2:
```

Ensuite, exécutez les playbooks Ansible pour installer Kubernetes.

```bash
ansible-playbook -i ./hosts.yaml ./upgrade.yaml
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

#### Optionnel — `kubeProxyReplacement` (Workstream B3)

Cilium peut remplacer `kube-proxy` (mode IPVS+eBPF), avec de meilleures perfs
réseau et moins de composants à maintenir. **Non activé par défaut** dans
[`cni.sh`](cni.sh) — décision conservatrice (l'install nominale est plus simple
à dépanner).

Pour l'activer plus tard sur un cluster déjà bootstrapé, repasser
`cilium install` avec
`--set kubeProxyReplacement=true --set k8sServiceHost=cluster-api --set k8sServicePort=6443`,
puis retirer `kube-proxy`
(`kubectl -n kube-system delete daemonset kube-proxy + iptables-save | grep KUBE | iptables-restore -n`).
Tester sur le banc multi-nœuds avant.

### Join workers to cluster

```bash
ansible-playbook -i ./hosts.yaml ./join-workers.yaml
```

### Installation de la connexion en local

Récupérer le kubeconfig depuis le control plane :

```bash
mkdir -p ~/.kube
scp control1:/home/debian/.kube/config ~/.kube/config
```

Modifiez le fichier `~/.kube/config` pour y indiquer l’adresse IP du control
plane (control1). Ensuite, vous pouvez vérifier que tout fonctionne correctement
en exécutant les commandes suivantes :

```bash
k get nodes
k get pods --all-namespaces
```

### Virtual private network

Installer tailscale sur tous les nœuds.

```bash
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
sudo apt-get update
sudo apt-get install tailscale
sudo tailscale up --ssh
```

### Installation de Ceph

Voir [`storage/ceph/RUNBOOK.md`](../storage/ceph/RUNBOOK.md).

## Audit-log et rollback (Workstream I)

### Audit-log : qui a fait quoi quand sur chaque nœud

Chaque playbook bootstrap invoque en `pre_tasks` le rôle
[`audit-log`](roles/audit-log/), qui pose une ligne dans
`/var/log/cluster-bootstrap.log` du nœud cible :

```text
2026-05-28T14:32:01Z playbook=cri.yaml from=pierre@laptop ssh-as=debian
```

Format : timestamp UTC ISO-8601, nom du playbook, identité de l'opérateur sur le
poste de contrôle (`$USER@hostname`), nom du compte SSH côté serveur (`debian`).

Lecture :

```bash
ssh debian@dirqual1 'sudo tail -n 20 /var/log/cluster-bootstrap.log'
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
# Sur le banc (exige confirmation explicite)
ansible-playbook -i ../test/multi-node/inventory.yaml rollback.yaml \
  -e confirm=yes --limit dirqual1
```

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
ansible-playbook -i ./hosts.yaml ./upgrade.yaml
```

### Sauvegarde etcd (SPOF assumé)

Le cluster fonctionne avec **1 seul control plane** (`dirqual1`) — décision
assumée (cf. PLAN « Workstream A12 / décision actée »). C'est un **SPOF** : la
perte du nœud control plane → cluster inutilisable jusqu'à restauration.
Mitigations :

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

> Tester cette procédure **sur le banc multi-nœuds** avant d'en avoir besoin en
> prod (cf. `test/multi-node/`).
