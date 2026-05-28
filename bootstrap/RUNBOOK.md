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

Post-installation, monter `/tmp` en **tmpfs** (RAM) plutôt qu’en LV :

```bash
sudo systemctl enable --now tmp.mount
```

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

```bash
cd bootstrap/security
cp .env-example .env && $EDITOR .env       # MAIL_ROOT_REDIRECT, HOST_USER, …
set -a; source .env; set +a
ansible-playbook -i ../hosts.yaml secure.yml
```

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

## Maintenance

### Mise à jour des systèmes d’exploitation

```bash
ansible-playbook -i ./hosts.yaml ./upgrade.yaml
```
