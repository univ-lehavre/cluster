# Banc multi-nœuds (Phase 1-5 + Ceph)

3 VMs Debian 13 arm64 reproduisant la topologie de prod à l'échelle : 1 control
plane (`dirqual1`) + 2 workers (`dirqual2-3`), réseau privé `192.168.67.0/24`,
chaque VM dotée de **3 HDD virtuels + 1 NVMe virtuel** pour exercer Rook-Ceph
(OSDs, block.db, quorum mon). Le contrôleur de la box est **VirtioSCSI**, donc
les disques apparaissent en `/dev/sd*` (sda = OS, sdb-sde = disques Ceph) — même
nommage que la prod, cf. [drift 0b](../RESULTS.md).

> ⚠️ **Plage IP volontairement disjointe de la prod (10.67.2.0/22)** : le banc
> utilise `192.168.67.0/24` pour éviter qu'une interface VBox host-only capture
> les routes locales vers les vrais serveurs (cf.
> [drift #6 dans RESULTS.md](../RESULTS.md)). Un pre-flight dans le Vagrantfile
> refuse le `up` si la collision est détectée.

> Pour un cycle rapide Phase 1-2 uniquement (sans Ceph), préférer le
> [banc mono-nœud](../single-node/) qui démarre en quelques minutes.

## Périmètre validé

| Phase | Quoi                            | Couvert ?                                     |
| ----- | ------------------------------- | --------------------------------------------- |
| 1     | OS/runtime/kubeadm-paquets      | ✅                                            |
| 2     | `kubeadm init` + Cilium         | ✅                                            |
| 2     | `kubeadm join` workers          | ✅ (3 nœuds → quorum mon possible)            |
| 3     | Rook operator + `CephCluster`   | ✅ (OSDs sur HDD virtuels, block.db sur NVMe) |
| 4     | StorageClasses (default + EC)   | ✅                                            |
| 5     | Workloads (Wordpress, RGW, OBC) | ✅                                            |
| 6     | Sauvegarde etcd, cleanup.sh     | ✅ (cleanup exerce les `sd*` virtuels)        |

Réserves :

- Architecture **arm64** ≠ x86_64 de la prod (validation logique pas binaire).
- **Échelle réduite** : 3 HDD/VM × 10 GiB = pas un test de perfs (vs 12 HDD ×
  5,5 TiB en prod). Les pools Ceph se déploient, les replicas marchent, mais la
  bande passante n'est pas représentative.
- 3 VMs, pas 4 (prod) — suffisant pour quorum mon (3) et `failureDomain: host`,
  laisse 0 marge de maintenance. À étendre à 4 si besoin (cf. Vagrantfile).

## Pré-requis hôte

| Outil      | Version  | Installation                                          |
| ---------- | -------- | ----------------------------------------------------- |
| VirtualBox | ≥ 7.2.8  | `brew install --cask virtualbox`                      |
| Vagrant    | ≥ 2.4.9  | `brew install --cask hashicorp/tap/hashicorp-vagrant` |
| Ansible    | ≥ 2.20.5 | `brew install ansible`                                |

**Pas de configuration `/etc/vbox/networks.conf` requise** : la plage
`192.168.67.0/24` est dans `192.168.0.0/16`, autorisée par défaut par VirtualBox
sur macOS. (Ce n'était pas le cas de l'ancienne plage `10.67.2.0/24` — cf. drift
#6.)

## RAM consommée

3 VMs × 5 GiB ≈ **15 GiB**. Sur un Mac 48 GiB, ça tient avec marge. À ajuster
(`vb.memory`) si ton hôte est plus modeste.

## Orchestrateur — `run-phases.sh`

Pour dérouler les phases 1-6 avec les **surcharges banc déjà câblées**
(`metadataDevice: sde`, `CEPH_HDD_GLOB`, kubeconfig réécrit sur l'IP privée) et
un **gate** entre chaque phase :

```bash
test/multi-node/run-phases.sh up         # vagrant up + gate VMs/disques
test/multi-node/run-phases.sh bootstrap  # phases 1-2 + gate 3 nœuds Ready
test/multi-node/run-phases.sh ceph       # phase 3 + gate HEALTH_OK
test/multi-node/run-phases.sh sc         # phase 4 + gate PVC Bound
test/multi-node/run-phases.sh workloads  # phase 5 + gate (wordpress + datalake)
test/multi-node/run-phases.sh etcd       # phase 6 + gate snapshot etcd
test/multi-node/run-phases.sh all        # tout, arrêt au 1er gate rouge
```

Chaque phase est idempotente ; le script s'arrête si un critère de succès n'est
pas atteint. Penser à `vagrant snapshot save <nom>` aux gates (le script
rappelle le nom conseillé). Les sections ci-dessous détaillent chaque étape
manuellement, pour le débogage.

## 1. Démarrer les VMs

```bash
cd test/multi-node
vagrant up --provider=virtualbox
```

Au 1ᵉʳ `up`, Vagrant crée pour chaque VM (contrôleur **VirtioSCSI**, cf. drift
0a/0b dans [RESULTS.md](../RESULTS.md)) :

- 3 HDD virtuels `*-hdd[1-3].vdi` (10 GiB chacun → `/dev/sdb`, `sdc`, `sdd`)
- 1 « NVMe » block.db `*-nvme.vdi` (5 GiB, 4ᵉ disque VirtioSCSI → `/dev/sde`)

Les disques persistent à travers `vagrant halt/up`, mais sont supprimés par
`vagrant destroy`.

> ⚠️ **Différences avec la prod sur ce banc** :
>
> - IPs : `192.168.67.X` (banc) vs `10.67.2.X` (prod) — pour éviter le conflit
>   de routage (drift #6).
> - Disques : HDD `/dev/sd[b-d]` + block.db `/dev/sde` (banc, VirtioSCSI) vs HDD
>   `/dev/sd*` + `/dev/nvme1n1` (prod, NVMe matériel). Seul le block.db diffère
>   ; le nommage HDD `sd*` est identique à la prod.
>
> [`bootstrap/state.sh`](../../bootstrap/state.sh) accepte des variables d'env
> pour s'adapter :
>
> ```bash
> CEPH_HDD_GLOB='/sys/block/sd[b-z]' CEPH_BLOCK_DEVICE=sde CEPH_MIN_HDD=3 \
>   bash bootstrap/state.sh 192.168.67.11 192.168.67.12 192.168.67.13
> ```
>
> En prod, les défauts (`/sys/block/sd*`, `nvme1n1`, 12 HDD) sont les bons.

## 2. Inventaire Ansible

Sur ce banc, les IPs sont fixes (host-only) — pas besoin de regénérer après
chaque `up`. Un inventaire statique suffit :

```yaml
# test/multi-node/inventory.yaml
cloud:
  children: { control, workers }
  vars:
    ansible_user: debian
    ansible_ssh_private_key_file: ~/.vagrant.d/insecure_private_keys/vagrant.key.ed25519
    ansible_ssh_common_args: >-
      -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null

control:
  hosts:
    dirqual1: { ansible_host: 192.168.67.11 }

workers:
  hosts:
    dirqual2: { ansible_host: 192.168.67.12 }
    dirqual3: { ansible_host: 192.168.67.13 }
```

(Gitignoré par sécurité — on peut le générer à la demande.)

## 3. Bootstrap (phases 1-2)

```bash
for p in checks cri kubeadm control-planes initialisation join-workers; do
  echo "== $p =="
  ansible-playbook -i inventory.yaml ../../bootstrap/$p.yaml
done
```

Différences avec le banc mono-nœud :

- `join-workers.yaml` **est** exécuté (et testable).
- `kubeadm init` doit utiliser `--apiserver-advertise-address=192.168.67.11`
  pour que les workers joignent le control plane via le réseau privé (pas le NAT
  Vagrant). À vérifier dans `bootstrap/initialisation.yaml` — au besoin,
  surcharger via une variable d'inventaire.

## 4. Cilium

```bash
ssh debian@192.168.67.11 'bash -s' < ../../bootstrap/cni.sh
```

## 5. Rook-Ceph (Phase 3+)

> Le plus simple est `run-phases.sh ceph`, qui câble tout ce qui suit. La
> procédure manuelle ci-dessous est pour le débogage.

Pré-vérification disques bruts (le pré-requis Phase 3) :

```bash
CEPH_HDD_GLOB='/sys/block/sd[b-z]' CEPH_BLOCK_DEVICE=sde CEPH_MIN_HDD=3 \
  bash ../../bootstrap/state.sh 192.168.67.11 192.168.67.12 192.168.67.13
```

La couche 3b doit afficher :

```text
✓ dirqual1 : 3/3 HDD bruts (≥ 3 requis)
✓ dirqual1 : /dev/sde présent et brut (block.db)
✓ dirqual1 : /var/lib/rook absent ou vide
```

Puis :

```bash
cd ../../storage/ceph
ssh debian@192.168.67.11 'sudo mkdir -p /var/lib/rook'   # créé par Rook, sinon
kubectl apply -f crds.yaml -f common.yaml -f operator.yaml
# attendre l'operator Ready
# surcharger metadataDevice nvme1n1 -> sde AVANT d'appliquer :
sed "s/metadataDevice: 'nvme1n1'/metadataDevice: 'sde'/" cluster.yaml \
  | kubectl apply -f -
```

> ⚠️ Le `metadataDevice: 'nvme1n1'` codé dans `cluster.yaml` est pour la prod.
> Sur ce banc le block.db est `/dev/sde` (4ᵉ disque VirtioSCSI) : surcharger
> comme ci-dessus, ou laisser Rook auto-détecter (`metadataDevice: ""` +
> `useAllDevices: true`). `run-phases.sh ceph` applique la surcharge `sde`.

## 6. Démolir

```bash
./test/prune.sh   # depuis la racine du repo — détruit VMs + disques VBox + .vagrant/
```

Voir [`test/README.md`](../README.md#nettoyage) pour les options (`--force`,
`--help`) et les garde-fous.

## Dépannage

| Symptôme                                     | Cause                                                       | Remède                                                                                                |
| -------------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `Cannot create host-only network 10.67.2.x`  | VBox refuse la plage                                        | Éditer `/etc/vbox/networks.conf` (voir Pré-requis hôte)                                               |
| `Controller already exists: NVMe` au 2ᵉ `up` | Le flag `.flag` a été supprimé sans nettoyer la conf VM     | `vagrant destroy && rm -rf .vagrant/ceph-disks/`                                                      |
| Workers ne joignent pas                      | Endpoint cluster-api non résolvable depuis 192.168.67.12/13 | Ajouter à `/etc/hosts` des workers : `192.168.67.11 cluster-api` (devrait l'être par le rôle kubeadm) |
| OSDs `Pending`                               | Disques pas bruts (déjà utilisés par un cycle précédent)    | Sur chaque worker : `sudo bash storage/ceph/cleanup.sh` puis recréer le `CephCluster`                 |
| Mon non quorum (`HEALTH_WARN`)               | Moins de 3 mon Up                                           | `kubectl -n rook-ceph get pods -l app=rook-ceph-mon` ; chaque worker doit en avoir 1                  |
