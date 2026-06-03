# Banc mono-nœud (Phase 1-2)

Canari **mono-nœud** permettant de rejouer les **phases 1-2 du bootstrap**
(préparation OS, runtime containerd, `kubeadm init`, CNI Cilium) sur du **vrai
Debian 13 arm64**, dans une VM jetable, **avant** de toucher les serveurs.

> Pour valider Rook-Ceph (Phase 3+), utiliser le
> [banc multi-nœuds](../multi-node/) avec disques additionnels et NVMe virtuel.

## Réserves connues

- **Architecture arm64** (Apple Silicon) ≠ **x86_64** des serveurs HPE → on
  valide la _logique_ (rôles Ansible, manifestes, câblage), pas les artefacts
  binaires x86_64. Pour une validation x86_64, rejouer le même `Vagrantfile` sur
  un hôte Intel.
- **Mono-nœud** → pas de Ceph (qui exige ≥ 3 hôtes pour le quorum
  `mon`/`failureDomain: host`). Le test multi-nœuds + Ceph est dans
  `test/multi-node/`.
- **Fonctionnel, pas perfs** : petit disque virtuel et VM modeste — on prouve
  que ça déploie, pas qu'on tient les 66 TiB/nœud.

## Pré-requis

| Outil                         | Version testée | Installation (Homebrew)                               |
| ----------------------------- | -------------- | ----------------------------------------------------- |
| VirtualBox                    | 7.2.8          | `brew install --cask virtualbox`                      |
| Vagrant                       | 2.4.9          | `brew install --cask hashicorp/tap/hashicorp-vagrant` |
| Ansible (core)                | 2.20.5         | `brew install ansible`                                |
| shellcheck _(pour les hooks)_ | 0.11           | `brew install shellcheck`                             |

La box `bento/debian-13` arm64 (~600 Mo) est téléchargée par Vagrant au premier
`vagrant up`.

## 1. Démarrer la VM

```bash
cd test/single-node
vagrant up --provider=virtualbox
```

À la fin de `vagrant up` :

- la VM est `running` (SSH NAT, port forward `127.0.0.1:2222 → 22`) ;
- un utilisateur **`debian`** a été créé avec `sudo` sans mot de passe et la
  même clé SSH que `vagrant` (le provisioner inline le fait — voir
  `Vagrantfile`). Les rôles Ansible ciblent cet utilisateur, comme en prod.

Vérification rapide :

```bash
vagrant status
ssh -p 2222 -i ~/.vagrant.d/insecure_private_keys/vagrant.key.ed25519 \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    debian@127.0.0.1 'cat /etc/os-release | head -2'
```

## 2. Générer l'inventaire Ansible du banc

Le port SSH peut varier (Vagrant choisit un autre port si 2222 est pris). Génère
un `inventory.yaml` à la volée :

```bash
port=$(vagrant ssh-config | awk '/Port /{print $2}')
cat > inventory.yaml <<EOF
cloud:
  children:
    control:
    workers:
  vars:
    ansible_user: debian
    ansible_ssh_private_key_file: $HOME/.vagrant.d/insecure_private_keys/vagrant.key.ed25519
    ansible_ssh_common_args: -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null

control:
  hosts:
    cp1:
      ansible_host: 127.0.0.1
      ansible_port: $port

workers:
  hosts: {}
EOF
ansible -i inventory.yaml cloud -m ping   # doit répondre "pong"
```

> Le fichier `inventory.yaml` est gitignoré (chemin de clé spécifique au poste).
> Le régénérer après chaque `vagrant destroy && vagrant up` si le port change.

## 3. Rejouer le bootstrap (phases 1-2)

Les playbooks vivent dans `../../bootstrap/`. On enchaîne dans l'ordre — chacun
est idempotent (un 2ᵉ run doit donner `changed=0`) :

```bash
for p in checks cri kubeadm control-planes initialisation; do
  echo "== $p =="
  ansible-playbook -i "$PWD/inventory.yaml" "../../bootstrap/$p.yaml"
done
```

| Playbook              | Ce qu'il fait                                                                                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `checks.yaml`         | asserts OS (Debian 13), RAM, CPU, hostname, UUID ; désactive le swap                                                                                         |
| `cri.yaml`            | charge `overlay`/`br_netfilter`, pose les sysctl, ajoute le dépôt **Docker**, installe `containerd.io`, génère `config.toml` avec **`SystemdCgroup = true`** |
| `kubeadm.yaml`        | dépôt `pkgs.k8s.io/v1.34`, installe `kubelet`+`kubeadm`, mappe `cluster-api → IP control plane` dans `/etc/hosts`                                            |
| `control-planes.yaml` | installe `kubectl` (control plane uniquement)                                                                                                                |
| `initialisation.yaml` | `kubeadm init --control-plane-endpoint cluster-api:6443 --upload-certs`, copie le kubeconfig, retire le taint control-plane                                  |

## 4. Installer le CNI (Cilium)

`cni.sh` est un script qui s'exécute sur le control plane (il pose la CLI Cilium
puis lance `cilium install` avec un pod CIDR disjoint du réseau nœuds) :

```bash
port=$(vagrant ssh-config | awk '/Port /{print $2}')
KEY=~/.vagrant.d/insecure_private_keys/vagrant.key.ed25519
SSH_ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

scp -P "$port" -i "$KEY" $SSH_ARGS ../../bootstrap/cni.sh debian@127.0.0.1:cni.sh
ssh -p "$port" -i "$KEY" $SSH_ARGS debian@127.0.0.1 'bash cni.sh'
```

## 5. Vérifier

```bash
ssh -p "$port" -i "$KEY" $SSH_ARGS debian@127.0.0.1 \
    'cilium status --wait --wait-duration 3m; kubectl get nodes'
```

Attendu :

```text
   /¯¯\
/¯¯\__/¯¯\    Cilium:             OK
\__/¯¯\__/    Operator:           OK
/¯¯\__/¯¯\    Envoy DaemonSet:    OK
…
NAME       STATUS   ROLES           AGE   VERSION
cp1   Ready    control-plane   …     v1.34.8
```

Vérifier le pod CIDR (issu de `10.244.0.0/16`, **disjoint** du réseau
`10.0.0.0/22` de la prod) :

```bash
ssh -p "$port" -i "$KEY" $SSH_ARGS debian@127.0.0.1 \
    'kubectl get ciliumnode cp1 -o jsonpath="{.spec.ipam.podCIDRs}"; echo'
# → ["10.244.0.0/24"]
```

## Itérer rapidement avec des snapshots VBox

```bash
vagrant snapshot save default base       # juste après le 1er vagrant up
# … expérimenter, casser, etc.
vagrant snapshot restore default base    # repart de zéro
```

## Démolir

```bash
vagrant destroy -f
rm -f inventory.yaml      # gitignoré, mais on nettoie
```

## Dépannage

| Symptôme                                      | Cause probable                                       | Remède                                                                                              |
| --------------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `vagrant up` se plaint de la version VBox     | Vagrant < 2.4 ; VBox 7.2 non reconnu                 | `brew upgrade --cask hashicorp/tap/hashicorp-vagrant`                                               |
| `Permission denied (publickey)`               | `inventory.yaml` pointe sur un mauvais chemin de clé | Vérifier que `~/.vagrant.d/insecure_private_keys/vagrant.key.ed25519` existe (`vagrant ssh-config`) |
| Asserts checks échouent (`memory_mb < 4096`)  | VBox alloue moins de RAM que demandé                 | Augmenter `vb.memory` dans le `Vagrantfile` (essayer 6144 → Linux voit ~5900)                       |
| `kubeadm init` warns `containerd 1.x deprec.` | Tu es resté sur le containerd 1.6.x natif de Debian  | Vérifier que le dépôt Docker est bien actif (`apt-cache policy containerd.io`)                      |
| Cilium reste en `Pending`                     | Pull image lent (registry `quay.io`)                 | `kubectl describe pod -n kube-system <cilium-pod>` ; relancer `cilium status --wait`                |

## Versions validées

| Composant               | Version                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------ |
| Box                     | `bento/debian-13` v202510.26.0 arm64                                                 |
| Noyau                   | 6.1.0-40-arm64                                                                       |
| containerd              | **containerd.io 2.2.4** (dépôt Docker) — `SystemdCgroup=true`, plugin CRI activé     |
| kubeadm/kubelet/kubectl | **v1.34.8** (`pkgs.k8s.io/v1.34`)                                                    |
| CNI                     | **Cilium 1.19.4**, CLI `v0.19.4`, pod CIDR `10.244.0.0/24` (issu de `10.244.0.0/16`) |
| Endpoint control-plane  | `cluster-api:6443` → `10.0.2.15` (NAT) via `/etc/hosts`                              |
