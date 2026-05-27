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

Pour installer le système d’exploitation, utilisez l’image Debian Trixie (13) et
suivez les instructions suivantes :

1. **Téléchargez l’image ISO** de Debian Trixie (13) depuis le site officiel.
2. **Attachez l’image ISO** à la machine virtuelle ou au serveur physique.
3. **Démarrez l’installation** en sélectionnant l’image ISO comme périphérique
   de démarrage.

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
3. Créer la partition **EFI** : 512 Mo, usage « Partition système EFI », point
   de montage `/boot/efi`.
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

### Accès SSH par clef asymétrique

Une fois le système d’exploitation installé, il est recommandé de configurer
l’accès SSH par clef asymétrique pour une sécurité renforcée. Voici les étapes à
suivre :

Tout d’abord, connectez-vous au serveur via SSH en utilisant le mot de passe
initial.

```bash
ssh debian@control1
```

Une fois que la machine est enregistrée dans votre fichier `~/.ssh/known_hosts`,
vous pouvez configurer l’accès SSH par clef asymétrique. Déconnectez-vous.

Si vous n’avez pas de clef, générez-la et transférez-la :

```bash
ssh-keygen -t ed25519 -C "votre_email@example.com"
ssh-copy-id -i ~/.ssh/id_ed25519 control1
```

## Préparation du système d’exploitation des serveurs

Les opérations suivantes sont à réaliser sur tous les nœuds du cluster.

### Changer le mot de passe de l’utilisateur `debian`

```bash
passwd
```

### Autoriser l’utilisateur en sudo sans mot de passe

```bash
sudo visudo
```

Il est nécessaire d’ajouter la ligne : `debian ALL=(ALL) NOPASSWD: ALL`

### Sécurisation du protocole SSH

Modifier le fichier `/etc/ssh/sshd_config` :

```bash
PasswordAuthentication no
AllowUsers debian
PermitRootLogin no
PubkeyAuthentication yes
MaxAuthTries 3
Protocol 2
ClientAliveInterval 300
ClientAliveCountMax 3
```

Et relancer le service :

```bash
sudo systemctl restart sshd
```

### Désactiver le swap

Kubernetes refuse de s'installer si le swap est actif.

```bash
sudo lvdisplay
sudo umount /dev/control1-vg/swap_1
sudo lvremove /dev/control1-vg/swap_1
sudo lvdisplay
```

### Pare-feu

```bash
# Paramétrer le firewall
# Attention : ce paramétrage bloque l’accès au cluster IP
sudo apt-get update
sudo apt-get install ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
sudo ufw status verbose
```

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
curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
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
