# Résultats — banc multi-node

> Dernière exécution : **2026-05-28**, branche `chore/cluster-rebuild-debian13`,
> banc `test/multi-node/` sur Mac Apple Silicon (M3 Max, 48 GiB) + VirtualBox
> 7.2.8 + Vagrant 2.4.9.

## Topologie testée

| VM       | IP NAT         | IP privée     | Rôle          | Disques                                     |
| -------- | -------------- | ------------- | ------------- | ------------------------------------------- |
| dirqual1 | 127.0.0.1:2222 | 192.168.67.11 | control plane | sda=OS 64G, sdb-sdd=HDD 10G ×3, sde=NVMe 5G |
| dirqual2 | 127.0.0.1:2200 | 192.168.67.12 | worker        | (idem, ordre différent)                     |
| dirqual3 | 127.0.0.1:2201 | 192.168.67.13 | worker        | (idem, ordre différent)                     |

Box : `bento/debian-13` arm64 v202510.26.0, kernel `6.12.48+deb13-arm64`.

## Chemin obligatoire testé

| #   | Étape                                           | Résultat                                                          | Idempotence (2ᵉ run)     |
| --- | ----------------------------------------------- | ----------------------------------------------------------------- | ------------------------ |
| 0   | `vagrant up` 3 VMs + disques                    | ✅ après 3 fixes Vagrantfile (cf. drifts 0a, 0b, 0c)              | n/a                      |
| 1   | `audit-log-baseline.yaml` (test du rôle)        | ✅ ligne posée sur 3 VMs                                          | ✓ rejouable              |
| 2   | `checks.yaml` (Phase 1.1)                       | ✅ 3 VMs, swap désactivé, warning `/var` < 100 GB (banc)          | ✓ `changed=0`            |
| 3   | `cri.yaml` (Phase 1.2)                          | ✅ containerd.io 2.2.4 + `SystemdCgroup=true`                     | non testé (manque temps) |
| 4   | `kubeadm.yaml` (Phase 1.3)                      | ✅ kubeadm/kubelet 1.34.8 installé, `/etc/hosts cluster-api` posé | non testé                |
| 5   | `control-planes.yaml` (Phase 1.4)               | ✅ kubectl posé sur dirqual1                                      | non testé                |
| 6   | `initialisation.yaml` (Phase 2.1)               | ✅ après fix drift #3, `kubeadm init` réussi avec endpoint        | non testé                |
| 7   | `cni.sh` (Phase 2.2)                            | ✅ Cilium 1.19.4 installé sur dirqual1, pod CIDR `10.244.0.0/16`  | non testé                |
| 8   | `join-workers.yaml` (Phase 2.3)                 | ✅ après fix drift #3bis, dirqual2 + dirqual3 joints              | non testé                |
| 9   | `state.sh` couches 0-3b                         | ✅ détecte audit-log + bootstrap K8s + disques bruts              | n/a                      |
| 10  | `rollback.yaml --limit dirqual3 -e confirm=yes` | ✅ kubeadm + containerd + configs supprimés                       | n/a                      |

## Phases non encore testées (gap connu)

> ℹ️ **Mis à jour par le Run #3 (2026-05-31)** : les Phases 3 (Rook-Ceph), 4
> (StorageClasses) et 5 (workloads + datalake) **ont depuis été validées** de
> bout en bout (cf. [Run #3](#run-3-2026-05-31--relance-banc-intégral)). Le
> tableau ci-dessous reflète l'état aux Runs #1/#2 et est conservé pour
> l'historique.

| Phase                                                 | Pourquoi pas testé                                                                                                                                                             |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Phase 3 — Rook-Ceph                                   | Bloqué par drift #4 — workers `NotReady` à cause de l'INTERNAL-IP NAT (Cilium agent ne peut pas joindre l'API). Pas un bug du dépôt — limitation propre au banc Vagrant arm64. |
| Phase 4 — StorageClasses                              | Dépend Phase 3                                                                                                                                                                 |
| Phase 5 — workloads + datalake smoke-test             | Dépend Phase 3                                                                                                                                                                 |
| Phase 6 — etcd-backup timer                           | Pas joué (le control plane fonctionne mais on n'a pas pris le temps)                                                                                                           |
| Cycle bootstrap → rollback → re-bootstrap idempotence | Rollback OK ; le re-bootstrap est trivial (rejouer les mêmes playbooks)                                                                                                        |
| state.sh couches 4-7 (kubectl)                        | Nécessite `KUBECONFIG` local pointant sur le banc — pas relié pour ce test                                                                                                     |

## Drifts détectés et correctifs

### 🔴 0a — Contrôleur SATA inexistant sur arm64

**Symptôme** :

```text
A customization command failed:
["storageattach", :id, "--storagectl", "SATA Controller", "--port", "1", …]
Stderr: Could not find a controller named 'SATA Controller'
```

**Cause** : la box `bento/debian-13` arm64 utilise un contrôleur **VirtIO**
(VirtioSCSI), pas SATA. Mon Vagrantfile attachait les HDD additionnels à
`"SATA Controller"`.

**Correctif appliqué**
([commit b3a742a](https://github.com/univ-lehavre/cluster/commit/b3a742a)) :
[test/multi-node/Vagrantfile](multi-node/Vagrantfile) remplace
`"SATA Controller"` par `"VirtIO Controller"`.

### 🟠 0b — Création contrôleur NVMe séparé fragile sur arm64

**Symptôme** : après le fix 0a, `storageattach … --storagectl NVMe` échoue avec
`Could not find a controller named 'NVMe'`. Le bloc Ruby qui crée le contrôleur
via un flag fichier laissait un état désynchronisé après un `vagrant destroy`
partiel.

**Correctif appliqué** : le « NVMe block.db » est attaché au **même contrôleur
VirtIO** sur un port libre supplémentaire (port = HDD_COUNT+1). Perte de
fidélité prod assumée — on teste la topologie Ceph (12 OSDs + block.db
distinct), pas le matériel exact NVMe. Sur le banc le device apparaît comme
`/dev/sde` au lieu de `/dev/nvme1n1` ; on surcharge `CEPH_BLOCK_DEVICE=sde`
quand on lance state.sh.

### 🟠 0c — Disques VBox registered même après `vagrant destroy`

**Symptôme** : après un échec partiel + cleanup `.vagrant/`, `vagrant up` échoue
avec `VERR_ALREADY_EXISTS` sur `createhd`.

**Cause** : VBox garde les médiums registered dans sa base interne tant qu'on ne
les a pas explicitement `closemedium --delete`. `vagrant destroy` sur une VM
partielle ne nettoie pas tout.

**Correctif suggéré** (procédure manuelle, documentée dans
[test/multi-node/README.md](multi-node/README.md)) :

```bash
for uuid in $(VBoxManage list hdds | awk '/^UUID/ {print $2}'); do
    VBoxManage closemedium disk "$uuid" --delete
done
```

### 🟢 0d — DNS NAT injoignable + `jq` absent (câblés dans le Vagrantfile)

**Symptôme** : `apt-get`/`git` échouent dans les VMs (« pas de réseau ») alors
que la connectivité IP marche (`ping 1.1.1.1` OK) ; et les scénarios de banc
appellent `jq`, absent de la box.

**Cause** : le DHCP du LAN injecte dans la VM des résolveurs (box/université)
**injoignables depuis le NAT VirtualBox**. La résolution DNS échoue donc, ce qui
ressemble à une coupure réseau totale.

**Correctif appliqué** (provisioning persistant, survit à `vagrant destroy`) —
dans le bloc `config.vm.provision "shell"` de
[`test/multi-node/Vagrantfile`](multi-node/Vagrantfile) :

- `supersede domain-name-servers 10.0.2.3, 1.1.1.1;` ajouté à
  `/etc/dhcp/dhclient.conf` → le DHCP ne réécrase plus le DNS (persiste au
  reboot/renew) ;
- `/etc/resolv.conf` écrit immédiatement sur le DNS proxy NAT VBox (`10.0.2.3`)
  - public (`1.1.1.1`) pour le boot courant ;
- `jq` installé via `apt-get` une fois le DNS réparé.

Le bloc est idempotent (`grep -q` avant ajout, `command -v jq` avant install) :
rejeu de `vagrant provision` sans effet de bord. **Sans objet en prod** : les
serveurs HPE ont un DNS interne joignable et `jq` provisionné par les rôles.

### 🔴 3 — `kubeadm init` annonce IP NAT (10.0.2.15) au lieu du réseau privé

**Symptôme** : `join-workers.yaml` échoue avec
`Timeout when waiting for 10.0.2.15:6443`. L'IP NAT n'est pas routable inter-VM.

**Cause** : sur un banc Vagrant multi-VM, chaque VM a 2 interfaces : eth0 (NAT
10.0.2.15) et eth1 (réseau privé 10.67.2.x). Ansible
`ansible_default_ipv4.address` retourne le NAT. Le rôle utilisait cette IP pour
`/etc/hosts cluster-api` et pour `kubeadm init`.

**Correctifs appliqués** :

- Nouvelle variable `control_plane_ip` (optionnelle, défaut = IP par défaut)
  utilisée par les 3 rôles :
  - [`k8s-install`](../bootstrap/roles/k8s-install/tasks/main.yaml) :
    `/etc/hosts cluster-api → <control_plane_ip>` ;
  - [`k8s-initialization`](../bootstrap/roles/k8s-initialization/tasks/main.yaml)
    : `kubeadm init --apiserver-advertise-address=<control_plane_ip>` si la
    variable est posée ;
  - [`k8s-join-cluster`](../bootstrap/roles/k8s-join-cluster/tasks/main.yaml) :
    `wait_for host=<control_plane_ip>`.
- [`test/multi-node/inventory.yaml`](multi-node/inventory.yaml) (gitignoré) pose
  `control_plane_ip: 10.67.2.11` au niveau du groupe.
- **En prod** : la variable reste vide → `ansible_default_ipv4.address` retourne
  `10.67.2.X` directement (les nœuds n'ont qu'une interface cluster, pas de NAT
  séparé).

### 🔴 4 — INTERNAL-IP du kubelet = NAT (corrigé)

**Symptôme** : `kubectl get nodes -o wide` montrait `INTERNAL-IP=10.0.2.15`
(NAT) sur les 3 VMs. Cilium agent sur les workers restait en `Init:0/6` car il
ne pouvait pas joindre l'API service via NAT.

**Cause** : kubelet annonce par défaut son `default_ipv4`, qui est le NAT sur le
banc multi-VM.

**Correctifs appliqués** :

- Nouvelle variable `kubelet_node_ip` (optionnelle) ajoutée au rôle
  [`k8s-install`](../bootstrap/roles/k8s-install/tasks/main.yaml). Pose
  `/etc/default/kubelet KUBELET_EXTRA_ARGS=--node-ip=<ip>` + handler
  `Restart kubelet`.
- [`test/multi-node/inventory.yaml`](multi-node/inventory.yaml) pose la variable
  par host (192.168.67.X).
- Sans la variable (prod) → kubelet détecte l'IP de l'interface cluster unique.

### 🔴 #6 — Collision réseau prod ↔ banc (critique, fixé)

**Symptôme** : pendant le test, l'utilisateur n'arrivait plus à se connecter au
serveur prod `dirqual1` (10.67.2.11). `ssh-keyscan` montrait une clé hôte
ED25519 différente de celle stockée dans `~/.ssh/known_hosts`.

**Cause** : le banc multi-node avait été configuré sur **la même plage IP que la
prod** (`10.67.2.0/24`). VirtualBox crée une interface host-only sur cette plage
→ toutes les routes locales `10.67.2.X` partent vers les VMs du banc, capturant
tout SSH vers les vrais serveurs.

```text
# bridge100 (interface host-only VBox sur la plage prod) :
bridge100: inet 10.67.2.1 netmask 0xffffff00
# Route locale :
10.67.2.11    8.0.27.3c.ba.c7    UHLWIi  bridge100    # = VM banc, pas prod
```

**Impact opérationnel** : tant que le banc tournait, l'utilisateur perdait
l'accès SSH aux 4 serveurs prod. À la limite du sabotage involontaire.

**Correctifs appliqués** :

1. **Plage banc déplacée** sur `192.168.67.0/24` — disjointe de toute prod
   possible. Plage `192.168.0.0/16` autorisée par défaut par VBox → plus de
   `networks.conf` nécessaire.
2. **Pre-flight dans le Vagrantfile** : refuse le `vagrant up` si une interface
   VBox host-only existe encore sur la plage prod (10.67.2.x), signe d'un ancien
   banc non nettoyé.
3. Documentation dans `SAFEGUARDS.md` (règle d'isolation banc/prod) et
   `test/multi-node/README.md`.

**Règle d'or pour éviter à l'avenir** :

> La plage IP du banc DOIT être disjointe de toute plage de production
> accessible depuis le poste de contrôle. Si le poste route vers la prod via
> VPN, switch, Wi-Fi université, etc., toute IP banc qui overlap capture les
> routes locales.

Vérifier avant un `up` :

```bash
netstat -rn | grep <plage-prod>                              # routes locales
VBoxManage list hostonlyifs | grep -E 'Name|IPAddress'       # interfaces VBox
```

### 🟢 5 — `vagrant ssh` se connecte comme `vagrant` (kubeconfig manquant)

**Symptôme** : `vagrant ssh dirqual1 -c 'kubectl get nodes'` retourne
`connection refused localhost:8080` — kubectl en tant que `vagrant` ne trouve
pas `/home/vagrant/.kube/config`.

**Cause** : le kubeconfig est posé dans `/home/debian/.kube/config` par le rôle
`k8s-initialization` (et c'est correct — les rôles ciblent l'utilisateur
`debian`).

**Contournement** : utiliser `ssh -p <port> debian@127.0.0.1` avec la clé
Vagrant directement. Documenté dans
[test/multi-node/README.md](multi-node/README.md).

## Verdict

✅ **Phase 1-2 validées de bout en bout sur 3 VMs** avec 4 drifts détectés et 3
corrigés (drift #4 reste un gap banc-arm64-only, sans impact prod).

✅ **Tous les artefacts neufs testés** : `audit-log-baseline.yaml`, rôle
`audit-log`, `rollback.yaml` (avec confirm=yes), `state.sh` couches 0-3b,
variable `control_plane_ip` partagée par 3 rôles.

⚠️ **Phase 3-5 non testées sur le banc** : bloquées initialement par le drift #4
(INTERNAL-IP NAT), corrigé via la variable `kubelet_node_ip` ; à refaire après
le redéploiement banc sur la plage `192.168.67.0/24`.

✅ **Aucun bug bloquant côté prod** — les 6 drifts détectés sont soit
(0a/0b/0c/5) propres au banc Vagrant arm64, soit (#3/#4) des fixes généralisés
qui rendent les rôles compatibles avec un réseau multi-IP sans surcharger la
prod (variables optionnelles), soit (#6) une erreur de conception du banc qui a
corrigée la plage IP.

---

## Run #2 (2026-05-28 après-midi) — banc sur 192.168.67.0/24

Relance du banc après les correctifs précédents. **3 nouveaux drifts détectés**,
dont **deux qui impactent la prod** (architecture Rook 1.19+).

### ✅ Validé sur ce run

- 3 VMs Debian 13 arm64 sur `192.168.67.0/24` (drift #6 résolu).
- Phase 1 idempotente (`changed=0` au 2ᵉ run).
- Phase 2 : `kubeadm init` avec `control_plane_ip=192.168.67.11`, workers
  joints, `kubelet_node_ip` opérationnel.
- Cilium 1.19.4 + 3 agents Running après ajout de la route
  `10.96.0.0/12 dev eth1` (drift #7).
- Rook v1.19.6 + **CephCluster HEALTH_OK** après ajout du `ceph-csi-operator`
  (drift #8). 3 mons quorum + 2 mgr + 3 OSDs up.
- Image `quay.io/ceph/ceph:v20.2.1` disponible en **arm64** ✓.

### 🔴 #7 — Workers ne peuvent pas joindre ClusterIP API (corrigé, banc-only)

**Cause** : route par défaut workers via NAT eth0 → `curl 10.96.0.1` part avec
source IP NAT `10.0.2.15`, l'API à `192.168.67.11` ne peut pas y répondre.
Conntrack montre `UNREPLIED`.

**Correctif** : route `10.96.0.0/12 dev eth1` posée par le provisioner
[Vagrantfile](multi-node/Vagrantfile) via systemd-networkd drop-in.

**Statut prod** : non-applicable — eth0 prod = interface cluster unique.

### 🔴 #8 — Rook 1.19+ : CRDs `csi.ceph.io` manquants (impact PROD)

**Cause** : à partir de Rook 1.19, le provisioning CSI est délégué à un
opérateur séparé
[`ceph-csi-operator`](https://github.com/ceph/ceph-csi-operator). Les CRDs
`cephconnections.csi.ceph.io`, `clientprofiles.csi.ceph.io`,
`drivers.csi.ceph.io`, etc. **ne sont plus dans le `crds.yaml` de Rook**.

**Symptôme** : `CephCluster Progressing` →
`no matches for kind "CephConnection" in version "csi.ceph.io/v1"`.

**Correctif appliqué (banc)** :

```bash
kubectl apply --server-side -f \
    https://raw.githubusercontent.com/ceph/ceph-csi-operator/v0.3.0/deploy/all-in-one/install.yaml
```

**Statut prod** : ~~bloquant~~ → **RÉSOLU** (cf. note ci-dessous), pas via le
`ceph-csi-operator` mais en **désactivant** la délégation à cet opérateur.

> ✅ **Résolu (commit `1bc5a17`, 2026-05-29 ; confirmé au Run #3)** : plutôt que
> d'ajouter `csi-operator.yaml`/`csi-drivers.yaml`, `operator.yaml` pose
> **`ROOK_USE_CSI_OPERATOR: "false"`** → Rook utilise son **CSI intégré
> classique** (les plugins `csi-rbdplugin`/`csi-cephfsplugin` sont déployés par
> l'operator lui-même), sans le `ceph-csi-operator` séparé, donc **sans** les
> CRDs `csi.ceph.io` ni d'objets `Driver` à créer. Au Run #3, Phase 3
> (HEALTH_OK) et Phase 4 (PVC Bound) passent **sans rien appliquer à la main**.
> Ne PAS versionner `csi-operator.yaml`/`csi-drivers.yaml` : ce serait
> réintroduire la complexité que le flag évite (#8 et #9 tombent tous deux avec
> ce flag).

### 🟠 #9 — Driver CSI pas instancié → PVC pending (impact PROD)

**Cause** : `ceph-csi-operator` ne déploie pas les plugins `csi-rbdplugin` /
`csi-cephfsplugin` automatiquement — il faut créer des objets `Driver` (CR).
Sans eux : `PVC` reste `Pending` avec
`Waiting for external provisioner 'rook-ceph.rbd.csi.ceph.com'`.

**Statut** : **RÉSOLU avec #8** — `ROOK_USE_CSI_OPERATOR: "false"` supprime la
notion même d'objet `Driver` (CSI intégré). Plus de `csi-drivers.yaml` à poser.
Confirmé au Run #3 : PVC test **Bound**, plugins CSI Running.

### 🟠 #10 — OSDs Pending : `osd.requests.memory=2Gi` (banc-spécifique)

**Cause** : sur banc 5 GiB/VM × 12 OSDs créés, seuls 3 schedulables (1 par
hôte). HEALTH_OK quand même car suffit pour réplicat ×3 + `failureDomain: host`.

**Statut prod** : OK (251 GiB/nœud). À vérifier via le scénario
[`08-resource-limits-audit.sh`](scenarios/08-resource-limits-audit.sh) que la
réservation cumulée ne pose pas problème quand d'autres workloads cohabitent.

---

## Run #3 (2026-05-31) — relance banc intégral

Relance de `run-phases.sh all` sur 3 VMs fraîches. **5 drifts détectés
(#11-#15)** ; **#13 et #14 impactent la prod** (backup etcd). Après correctifs,
**Phases 0 à 6 franchies de bout en bout** — première fois qu'un `all` complet
passe.

- ✅ **Phase 0** : gate disques `^sdb` OK après #11.
- ✅ **Phase 1-2** : bootstrap + Cilium, 3 nœuds Ready (drifts #4/#7 ne se
  reproduisent plus — `kubelet_node_ip` + route ClusterIP en place).
- ✅ **Phase 3** : Rook-Ceph **HEALTH_OK**, `metadataDevice: sde`, pas d'erreur
  CSI — drifts #8/#9 résolus via `ROOK_USE_CSI_OPERATOR: "false"` (CSI intégré,
  pas le `ceph-csi-operator` séparé), aucun manifeste CSI à appliquer.
- ✅ **Phase 4** : 1 seule SC default, PVC test Bound.
- ✅ **Phase 5** : WordPress + MySQL Running ; **smoke-test datalake S3 vert**
  (PUT/LIST/GET/DIFF) après #12. 5 OBC applicatifs créés.
- ✅ **Phase 6** : snapshot etcd **19 MB, intégrité etcdutl vérifiée**, timer
  activé — après #13, #14 et #15. C'est la première validation réelle du backup
  etcd (l'audit notait justement « restauration etcd jamais testée »).

### 🔴 #11 — `run-phases.sh` câblé sur `/dev/vd*` alors que VirtioSCSI expose `/dev/sd*`

- **Fichiers** : [`run-phases.sh`](multi-node/run-phases.sh) (gate Phase 0,
  `CEPH_HDD_GLOB`, `CEPH_BLOCK_DEVICE`, surcharge `metadataDevice`,
  `DATA_DEVICE_GLOB`, `NVME_BLOCK_DEVICE`),
  [`Vagrantfile`](multi-node/Vagrantfile) (commentaires),
  [README multi-node](multi-node/README.md).
- **Symptôme** : le gate `lsblk … | grep "^vdb"` ne matche jamais ; les 3 VMs
  bootent pourtant avec leurs disques. `lsblk` sur dirqual1 montre `sda` (OS) +
  `sdb/sdc/sdd` (HDD) + `sde` (block.db) — **aucun `vd*`**.
- **Cause** : le contrôleur de la box `bento/debian-13` est de type
  **`VirtioSCSI`** (vérifié : `VBoxManage showvminfo dirqual1` →
  `storagecontrollertype0="VirtioSCSI"`). VirtioSCSI présente ses disques au
  noyau comme du **SCSI** → `/dev/sd*`. Seul `virtio-blk` produirait `/dev/vd*`.
  L'hypothèse « VirtioSCSI ⇒ `vd*` » des drifts 0a/0b et de `run-phases.sh`
  était fausse. Le Run #2 avait d'ailleurs déjà observé `sd*` (cf. table
  topologie).
- **À noter** : l'audit du 2026-05-29 ([02-tests.md](../docs/audit/02-tests.md))
  avait le diagnostic **à l'envers** — il qualifiait les commentaires `sd*` de
  vestige obsolète « contredit par le code VirtIO `vd*` ». C'est l'inverse : le
  code `vd*` était la régression, les commentaires `sd*` (et le drift 0b ligne
  76, « `/dev/sde` ») avaient raison.
- **Correctif appliqué** : `run-phases.sh` repasse sur `sd*` partout (gate
  `^sdb`, `CEPH_HDD_GLOB=/sys/block/sd[b-z]`, `CEPH_BLOCK_DEVICE=sde`,
  `metadataDevice: 'sde'`, `DATA_DEVICE_GLOB=/dev/sd[b-z]`,
  `NVME_BLOCK_DEVICE=/dev/sde`). `/sys/block/sd[b-z]` exclut naturellement `sda`
  (OS) — même schéma de nommage HDD que la prod ; seul le block.db diffère
  (`sde` banc vs `nvme1n1` prod). Commentaires Vagrantfile + README alignés.
- **Statut prod** : non-applicable (régression purement banc). En prod les
  défauts `/sys/block/sd*` + `nvme1n1` restent corrects.

### 🟠 #12 — Smoke-test datalake : course RGW + endpoint non résolvable depuis le poste

- **Fichiers** :
  [`storage/ceph/storageClass/datalake/smoke-test.sh`](../storage/ceph/storageClass/datalake/smoke-test.sh),
  [README datalake](../storage/ceph/storageClass/datalake/README.md).
- **Symptôme** : gate Phase 5 `smoke-test datalake échoué`. En le déroulant à la
  main, deux échecs successifs et distincts :
  1. `Secret smoke pas créé` — l'OBC ne convergeait pas dans les 60 s.
  2. une fois l'attente corrigée :
     `mc: dial tcp: lookup rook-ceph-rgw-datalake.rook-ceph.svc: no such host`.
- **Causes** :
  1. **Course au démarrage** : le script attendait le Secret de l'OBC, mais
     l'OBC ne peut converger qu'une fois le **RGW joignable**. Sur banc arm64 le
     RGW met **80-120 s** à démarrer après le `CephObjectStore` ; pendant ce
     temps le provisioner OBC boucle sur `connection refused`. Le timeout de 60
     s expirait avant.
  2. **Endpoint interne** : le script promettait (en commentaire) un fallback
     port-forward mais ne l'implémentait pas — il retombait sur `BUCKET_HOST`
     (DNS interne `*.svc`), non résolvable depuis le poste de contrôle.
- **Correctif appliqué** :
  1. Attendre `CephObjectStore` Ready **puis** un pod RGW Ready (`kubectl wait`)
     **avant** le Secret ; timeouts réglables (`RGW_TIMEOUT=240`,
     `SECRET_TIMEOUT=120`).
  2. Vrai fallback **port-forward** automatique sur le service RGW (port local
     `38080`, réglable) quand l'hôte n'est pas résolvable et qu'aucun `ENDPOINT`
     n'est fourni ; fermé via `trap EXIT`.
  3. **Pré-requis poste** : un client S3 (`mc` via `brew install minio-mc`, ou
     `aws`). Documenté dans le README datalake.
- **Statut prod** : non-applicable. En prod le RGW est exposé via Tailscale
  (`ENDPOINT=` explicite) et le démarrage x86_64 est plus rapide — mais
  l'attente RGW-Ready ajoutée est un durcissement utile partout.

### 🔴 #13 — `crictl` jamais installé → backup etcd fantôme (impact PROD)

- **Fichier** : [`k8s-install`](../bootstrap/roles/k8s-install/tasks/main.yaml).
- **Symptôme** : gate Phase 6
  `etcd-snapshot: crictl introuvable (containerd requis)`. Le timer
  `etcd-snapshot.timer` est pourtant posé et activé.
- **Cause** : le bootstrap installe `containerd.io` + `kubelet`/`kubeadm` mais
  **jamais `cri-tools`** — donc pas de `crictl`. Or `etcd-snapshot.sh` repose
  sur `crictl exec` dans le static pod etcd, et le RUNBOOK utilise `crictl` pour
  la récupération. **Le timer tourne mais chaque snapshot échoue** : un backup
  qui ne se produit jamais.
- **Correctif** : ajouter `cri-tools` à l'install + au `hold` du rôle
  `k8s-install` (même dépôt `pkgs.k8s.io/v1.34`, version `1.34.0-1.1` alignée).
- **Statut prod** : **bloquant, se reproduit identique en prod** (mêmes rôles).

### 🔴 #14 — `etcd-snapshot.sh` : `env`/`sh` absents de l'image etcd distroless (impact PROD)

- **Fichier** :
  [`etcd-snapshot.sh.j2`](../bootstrap/roles/etcd-backup/templates/etcd-snapshot.sh.j2).
- **Symptôme** (révélé une fois #13 corrigé) :
  `OCI runtime exec failed: exec: "env": executable file not found in $PATH`,
  puis `etcdctl snapshot save a échoué`.
- **Cause** : le script faisait `crictl exec … env ETCDCTL_API=3 etcdctl …`.
  L'image etcd de kubeadm (`registry.k8s.io/etcd`) est **distroless** : ni `env`
  ni `sh` (vérifié sur le nœud). Le bloc de vérif d'intégrité avait le même
  défaut via `sh -c` (masqué car best-effort).
- **Correctif** : invoquer `etcdctl`/`etcdutl` **directement** (etcdctl 3.6 →
  API v3 par défaut, `ETCDCTL_API=3` inutile). Vérif d'intégrité réécrite en
  appels directs (`etcdutl` puis repli `etcdctl`).
- **Validation** : snapshot **19 MB**,
  `intégrité du snapshot vérifiée (etcdutl)`.
- **Statut prod** : **bloquant, se reproduit identique en prod.**

### 🟢 #15 — Gate Phase 6 : `$(ls …)` hors du `sudo` → faux négatif (banc-only)

- **Fichier** : [`run-phases.sh`](multi-node/run-phases.sh).
- **Symptôme** :
  `ls: cannot access '/var/lib/etcd-backups/etcd-*.db': Permission denied` →
  `GATE ÉCHOUÉ: aucun snapshot etcd produit` alors que le snapshot venait d'être
  écrit.
- **Cause** : `sudo test -s "$(ls -1t /var/lib/etcd-backups/…)"` — le `sudo` ne
  couvre que `test` ; la substitution `$(ls …)` tourne en `debian` sur un
  dossier `root:root 0700` → vide → `test -s ""` échoue.
- **Correctif** : envelopper tout le pipeline dans `sudo sh -c "…"`.
- **Statut prod** : non-applicable (gate de test uniquement).

---

## Suite de scénarios reproductibles

Suivant les questions opérationnelles posées, une
[suite de 8 scénarios](scenarios/README.md) a été écrite — chacun
auto-documenté, idempotent, avec cleanup automatique :

| #   | Scénario                        | Question opérationnelle adressée                   |
| --- | ------------------------------- | -------------------------------------------------- |
| 01  | Stockage bloc PVC write/read    | Le stockage bloc fonctionne-t-il ?                 |
| 02  | Reschedule pod                  | Que se passe-t-il si on détruit un replica (pod) ? |
| 03  | Perte d'un worker               | Rook-Ceph résiste-t-il à la perte d'un worker ?    |
| 04  | Perte du control plane          | Que se passe-t-il si le control plane plante ?     |
| 05  | Bump réplication ×3 → ×N        | Que se passe-t-il si on augmente la réplication ?  |
| 06  | Datalake smoke-test S3          | Le stockage objet fonctionne-t-il ?                |
| 07  | Cilium connectivity test        | Tests Cilium                                       |
| 08  | Audit requests/limits Rook-Ceph | Dimensionnement vs scheduling                      |

### Déroulé réel des scénarios (2026-06-01, banc sain : 9 OSD, HEALTH_OK)

Une fois le blocage CSI levé (`ROOK_USE_CSI_OPERATOR: "false"`, #8/#9) et le
banc correctement dimensionné (#10 → `osd.requests=512Mi`), les scénarios ont
été déroulés sur le poste de contrôle :

| #   | Exit | Verdict                                                                    |
| --- | ---- | -------------------------------------------------------------------------- |
| 01  | 0    | ✅ PVC RBD Bound + write/read identique                                    |
| 02  | 0    | ✅ donnée survit au reschedule de pod                                      |
| 06  | 0    | ✅ object store S3 PUT/GET/DIFF                                            |
| 07  | 0    | ✅ connectivité Cilium (après fix faux-positif log-scan, cf. ci-dessous)   |
| 08  | 0/1  | ✅ portable + assertion OSD Pending (strict=prod / `ALLOW_PENDING_OSD`)    |
| 03  | 1\*  | ⚠️ **résilience Ceph OK** ; échec sur **artefact banc** (cf. encadré)      |
| 04  | —    | non déroulé (même classe d'artefacts banc que 03 au restore)               |
| 05  | —    | skip attendu (< 5 hôtes)                                                   |
| 09  | 0    | ✅ **restauration etcd PROUVÉE** (témoin supprimé → revient après restore) |

### 09 — restauration etcd validée (2026-06-01, banc single-node)

Le test que l'audit pointait comme « le plus critique manquant » (un backup non
restauré n'est pas un backup) est désormais **vert**. Déroulé : ConfigMap témoin
→ `etcd-snapshot.sh` → suppression du témoin → procédure RUNBOOK
(`etcdctl snapshot restore` + remplacement data-dir + restart kubelet) → **le
témoin réapparaît à l'identique**. Logs clés :

```text
✓ snapshot : /var/lib/etcd-backups/etcd-…​.db
✓ témoin supprimé
✓ restauration appliquée
✓ témoin restauré à l'identique : restored-…​
✓ Snapshot etcd RESTAURABLE — backup prouvé.
```

- **Pas de reboot de VM** → aucun artefact banc (contrairement à 03/04). La
  procédure tourne _sur_ le control plane via SSH.
- A fonctionné **node `NotReady`** (Cilium en `ImagePullBackOff` faute d'accès
  quay.io depuis la VM ce jour-là) : le restore etcd ne dépend ni du CNI ni d'un
  node Ready — seulement de l'API server + etcd.
- **Gap prod détecté → RÉSOLU** : `etcdctl` (paquet `etcd-client`) n'était
  **pas** installé par le bootstrap (seul `crictl` l'est, via `cri-tools`/#13),
  alors que la restauration en a besoin sur l'hôte (etcd arrêté → pas de
  `crictl exec`). En urgence, devoir `apt install etcd-client` était un risque.
  **Corrigé** : le rôle [`etcd-backup`](../bootstrap/roles/etcd-backup/)
  installe désormais `etcd-client` (control-plane-only, même esprit que
  crictl/#13). Le scénario 09 vérifie sa présence et n'installe plus qu'en
  secours, avec un WARN si le rôle n'a pas tourné.

**Trois bugs de scénarios corrigés en chemin** (commits `test/`) :

- **07** : `check-log-errors` échouait sur des `warn` Ceph antérieurs et bénins
  (`CEP was deleted externally`, pods canary mon) →
  `--log-check-only-test-time`. La connectivité réelle était 100 % verte (79/80,
  le 1 échec = ce log-scan).
- **08** : `column -N` (util-linux) cassait sur le `column` BSD de macOS →
  en-tête émis manuellement ; + assertion OSD Pending que l'audit réclamait.
- **banc** : `osd.requests=512Mi` (sinon 1 OSD/hôte → peering figé, cf. #10).

> ⚠️ **Périmètre 03/04 — résilience prouvée, restore = artefact banc (PAS
> prod).** Le scénario 03 (perte de `dirqual3`) valide la **vraie** question :
> Ceph passe proprement en `HEALTH_WARN` (`1 host down`, `3 osds down`, 33 %
> degraded), les **6 OSD survivants restent up et les I/O continuent** (réplica
> ×3, `failureDomain: host`, `min_size 2`). **Cette résilience est valable en
> prod.** L'`exit 1` provient de la phase **restore** du banc, sur des artefacts
> **propres au multi-VM Vagrant arm64, inexistants sur les 4 serveurs HPE** :
>
> - **route ClusterIP `10.96/12 dev eth1` perdue au reboot** (drift #7) → agent
>   Cilium pas Ready → taint `node.cilium.io/agent-not-ready` → OSD `Pending` ;
> - **clock skew** sur le mon de la VM rallumée (pas de RTC fiable) ;
> - **`vboxsf`** (montage `/vagrant`) qui fait échouer le `vagrant up`.
>
> Aucun de ces trois n'existe en prod (interface cluster unique, NTP/chrony, pas
> de VirtualBox). **Réparer ces artefacts dans les scénarios serait de la
> sur-adaptation au banc** : on ne le fait pas. La leçon : sur le banc, le cycle
> halt/up d'un nœud exige de reposer la route + resync NTP **hors scénario** ;
> la prod n'en a pas besoin. À terme, scinder 03 en « perte » (assertion prod)
> et « restore » (best-effort banc).

## Run #5 (2026-06-01) — scénarios de durcissement (pod + hôte)

Ajout et validation des **scénarios 10-13** (sécurité, pas résilience). Banc
multi-node `192.168.67.0/24`, 3 VMs Debian 13 arm64, cluster K8s 1.34.8 + Cilium
1.19.4 (3 nœuds `Ready`). Scénarios exécutés sur `dirqual1` (`kubectl` via
`admin.conf`) ; le 13 lancé depuis le poste de contrôle (SSH).

| #   | Scénario                | Résultat banc | Assertion clé                                                      |
| --- | ----------------------- | ------------- | ------------------------------------------------------------------ |
| 10  | Pod Security admission  | ✅ PASS       | pod `privileged` **et** `hostNetwork` rejetés ; pod conforme admis |
| 11  | NetworkPolicy deny      | ✅ PASS       | egress coupé sous default-deny ; `allow-dns` rouvre le seul DNS    |
| 12  | securityContext runtime | ✅ PASS       | pod durci Running ; UID 65532 ; écriture `/` refusée, volume OK    |
| 13  | Host/node hardening     | ✅ mécanique  | parse `state.sh`, isole le bloc hôte, PASS/FAIL correct            |

**Détail 10** — l'API rejette à l'admission :
`violates PodSecurity "baseline:latest": privileged (…)` et
`host namespaces (hostNetwork=true)`. Le pod conforme démarre (avec le warning
`restricted` attendu, non bloquant car `warn`, pas `enforce`). Comportement
**identique en prod** (contrôleur d'admission API, ADR 0014).

**Détail 11** — preuve que **Cilium applique** les NetworkPolicy : `wget https`
réussit sans policy, échoue (timeout) sous `default-deny-all`, et reste coupé
après `allow-dns` alors que `nslookup` remarche. L'`allow` est chirurgical.

**Détail 12** — le `securityContext` est **réellement** appliqué au runtime (pas
seulement déclaré) : `echo > /oops` → `Read-only file system`, `id -u` ≠ 0,
écriture sur l'`emptyDir` monté OK. Complète le contrôle statique trivy.

**Détail 13** — réutilise [`bootstrap/state.sh`](../bootstrap/state.sh) plutôt
que de redupliquer les checks. Sur ce banc il sort **FAIL attendu** : 2 drifts
hôte (`sshd drop-in absent`, `PasswordAuthentication` encore autorisé) car
`first-access.sh` n'est jamais joué sur le banc (compte Vagrant + clé). Les
couches `secure.yml` jouées au Run #4 (postfix/auditd/fail2ban) ressortent bien
`✓ (couche …)`. La branche succès du parsing (bloc hôte sans `✗`, en excluant
les `✗` des sections K8s) est vérifiée séparément → sortie 0. **En prod**, sshd
durci + couches actives → PASS. Le 13 a besoin de `SSH_OPTS`/`HOSTS` (pas
`kubectl`) et est **sauté par défaut** dans `run-all.sh` sans `HOSTS`.

> 🐛 **Bug latent corrigé en passant.** Le pattern `labels: { $LABEL }` (où
> `LABEL="clé=valeur"`) produit du YAML invalide (`=` interdit dans un mapping)
> — révélé en jouant le 10. Tous les scénarios écrivent désormais le label en
> YAML correct (`clé: "valeur"`) et ne gardent `LABEL` (`clé=valeur`) que pour
> `kubectl label` / les sélecteurs `-l`. Les **scénarios 01 et 02** portaient le
> même bug (jamais exécutés sur le banc, gatés par les drifts CSI au Run #2) :
> **corrigés ici** par cohérence.

## Run #6 (2026-06-02) — durcissement réseau Cilium (WireGuard + Hubble)

Activation du chiffrement transparent **WireGuard** (pod-to-pod) et de
**Hubble** (relay + CLI, sans UI) dans [`bootstrap/cni.sh`](../bootstrap/cni.sh)
— [ADR 0019](../docs/decisions/0019-durcissement-reseau-cilium.md). Banc
multi-node (3 nœuds, K8s 1.34.8, Cilium 1.19.4), kernel 6.12 (module `wireguard`
présent).

| Vérification                          | Résultat banc                                           |
| ------------------------------------- | ------------------------------------------------------- |
| `cilium status` après upgrade+rollout | ✅ Cilium/Operator/Envoy OK, **Hubble Relay OK** (1/1)  |
| `cilium encrypt status`               | ✅ `Encryption: Wireguard (3/3 nodes)`                  |
| Interface `cilium_wg0` + peers        | ✅ présente, **2 peers** par nœud (mesh complet)        |
| `hubble observe`                      | ✅ flux réels pod-to-pod (trafic OSD Ceph) visibles     |
| Ceph après bascule                    | ✅ `HEALTH_OK` (warn transitoire ~70 s, cf. ci-dessous) |
| Scénario 14 (reproductible)           | ✅ PASS (3/3 assertions)                                |

### 🟠 #16 — `cilium upgrade` ne roule pas les agents → WireGuard inactif

**Symptôme** : après `cilium upgrade` avec `encryption.enabled=true`, la
ConfigMap porte `enable-wireguard=true` mais `cilium encrypt status` rapporte
`Disabled` et aucune interface `cilium_wg0` n'est créée.

**Cause** : `cilium upgrade` met à jour la ConfigMap **sans rouler le
DaemonSet** quand seules des valeurs changent. Les agents (âge 12 h, 0 restart)
gardent l'ancienne config ; le `config-drift-checker` le dit explicitement dans
les logs agent :
`Mismatch found key=enable-wireguard actual=false expectedValue=true`.

**Correctif appliqué** (dans `cni.sh`) : après l'upgrade, **forcer**
`kubectl rollout restart daemonset/cilium deployment/cilium-operator` +
`rollout status`, puis **vérifier** `cilium encrypt status` et **échouer le
script** si WireGuard n'est pas réellement actif. Après rollout : WireGuard
actif sur 3/3 nœuds (confirmé). Idempotent (un restart sans changement de config
recrée les pods à l'identique). Sans objet à l'install initiale (les agents
démarrent directement avec la bonne config).

> ⚠️ **Bascule WireGuard à chaud = `HEALTH_WARN` transitoire.** Le rollout des
> agents reconstruit le datapath → Ceph signale brièvement des « slow OSD
> heartbeats » (`longest 2089 ms` → décroît → `HEALTH_OK` en ~70 s sur le banc).
> Pas de perte de données, pas d'OSD down. **En prod : appliquer hors heure de
> pointe.** Le scénario 14 ne dégrade rien (lecture seule du datapath).

## Run #7 (2026-06-02) — nettoyage du banc + rejeu intégral des scénarios

Banc nettoyé puis **tous les scénarios rejoués** (sauf 03/04, dont la phase
restore ne se valide pas sur ce banc — cf. avertissement plus haut). Au
préalable : durcissement `sshd` posé sur les 3 VMs via `first-access.sh`
(drop-in `00-hardening.conf`) pour que le scénario 13 puisse passer.

| #   | Scénario                 | Résultat | Lecture                                                                        |
| --- | ------------------------ | -------- | ------------------------------------------------------------------------------ |
| 01  | PVC RBD write/read       | ✅ PASS  | PVC Bound, écriture/lecture identiques                                         |
| 02  | Reschedule pod           | ✅ PASS  | donnée persistante au reschedule, PVC reste Bound                              |
| 05  | Replication bump         | ⏭️ SKIP  | `NEW_SIZE=4 > 3 hôtes` : impossible (`failureDomain: host`)                    |
| 06  | Object store smoke       | ⚙️ fix   | smoke-test échoue (race credentials S3) **et le scénario sort RC=1** (cf. #17) |
| 07  | Cilium connectivity      | ⚠️ banc  | pod-to-pod/service OK ; seuls les tests egress `1.1.1.1` échouent (cf. #18)    |
| 08  | Resource limits audit    | ✅ PASS  | 9 OSD, **0 Pending**, dimensionnement cohérent                                 |
| 09  | Restauration etcd        | ⏭️ n/a   | nécessite single-node ou kubeconfig local relié (transport banc)               |
| 10  | Pod Security admission   | ✅ PASS  | privileged/hostNetwork rejetés, conforme admis                                 |
| 11  | NetworkPolicy deny       | ✅ PASS  | sonde DNS interne (cf. #18) : deny coupe, allow-dns rouvre ciblé               |
| 12  | securityContext runtime  | ✅ PASS  | non-root, rootfs RO, volume RW                                                 |
| 13  | Host/node hardening      | ✅ PASS  | 3 nœuds : sshd durci + couches OS, **aucun drift** (après first-access)        |
| 14  | Cilium encryption+Hubble | ✅ PASS  | WireGuard 3/3, `cilium_wg0` 2 peers, Hubble 20 flux                            |

> ✅ **13 passe vraiment maintenant.** Au Run #5 il sortait FAIL (sshd non durci
> sur le banc). Après pose du drop-in `first-access.sh` sur les 3 VMs, les 3
> nœuds ressortent sans drift host. Note : `AllowUsers debian` bloque le compte
> `vagrant` → `vagrant ssh` ne fonctionne plus, on opère le banc en SSH direct
> `debian@127.0.0.1:<port>` (plus fidèle à la prod, qui n'a pas de compte
> vagrant).

### 🟢 #17 — Scénario 06 : code de sortie du smoke-test masqué par le trap (corrigé)

**Symptôme** : le smoke-test S3 échoue (`mc: access key ID … does not exist` /
`Ni mc ni aws trouvés`) mais le scénario 06 ressortait en **RC=0** — faux
positif.

**Cause** : `bash smoke-test.sh` était la **dernière commande** du script ; le
`trap cleanup EXIT` s'exécute ensuite et son dernier `kubectl delete … || true`
(code 0) **écrase** le code de sortie.

**Correctif appliqué** : capturer le RC du smoke-test (`|| smoke_rc=$?`) et
`exit "$smoke_rc"` explicite. **Vérifié sur banc** : un smoke-test en échec
ressort désormais en **RC=1**. Vaut en prod (un smoke-test S3 raté doit faire
échouer le scénario partout). La race de credentials observée (OBC créé, clé pas
encore propagée par le RGW recréé from scratch) est un timing du banc, sans
objet sur un datalake stable en prod.

### 🟢 #18 — Scénario 11 : sonde réseau dépendant d'Internet (corrigé)

**Symptôme** : l'étape 1 du 11 (`wget https://1.1.1.1`) échouait par
intermittence → faux « souci réseau ». Le `cilium connectivity test` (07) échoue
de même sur ses tests `pod-to-cidr` vers `1.1.1.1`/`1.0.0.1`.

**Cause** : `1.1.1.1` est **réservé côté banc** (DNS proxy NAT VirtualBox +
`nameserver 1.1.1.1` posé dans le resolv.conf, drift 0d) → collision pour le
trafic _data_ vers cette IP. Vérifié : l'egress pod **réel** marche
(`pod → deb.debian.org` OK), le pod-to-pod **inter-nœuds chiffré** (WireGuard),
les gros transferts (MTU) et le pod-to-service ClusterIP **fonctionnent tous**.
**Aucune régression WireGuard/masquerade** — uniquement les IP
`1.0.0.1/1.1.1.1`.

**Correctif appliqué (11 seulement)** : remplacer la sonde egress Internet par
une **sonde DNS interne** (egress vers `kube-system:53`) — déterministe et sans
dépendance Internet. La preuve « allow chirurgical » teste qu'un egress non-DNS
(API ClusterIP:443) reste coupé. **Vérifié PASS** sur banc. Un test de
NetworkPolicy ne doit jamais dépendre d'Internet : ce correctif vaut en prod.
**Le 07** (outil tiers `cilium connectivity test`) est laissé **inchangé** — on
ne le sur-adapte pas au banc ; documenter qu'on l'exécute en prod (egress réel)
ou en excluant `--test '!pod-to-cidr,!pod-to-world'` ponctuellement sur banc.

### 🟠 #19 — Suppression d'un `CephObjectStore` qui contient des buckets (deadlock)

**Symptôme** : le `CephObjectStore datalake` reste bloqué en `Deleting` ; les
logs operator répètent _« will not be deleted until all dependents are removed:
buckets … »_.

**Cause** : Rook **protège les données** — il refuse de supprimer un object
store tant qu'il reste des OBC/buckets. Si on supprime le store **avant** de
vider les buckets, l'OBC ne peut plus se deprovisionner (RGW en cours de
suppression) → deadlock mutuel (finalizers des deux côtés).

**Ce que ça dit pour la PROD** (≠ artefact banc) : **toujours supprimer les OBC
et vider les buckets AVANT de supprimer le `CephObjectStore`**. Déblocage manuel
en dernier recours (données jetables seulement) : retirer les finalizers des
`obc`/`objectbucket`, supprimer les buckets RGW
(`radosgw-admin bucket rm --purge-objects`), puis retirer le finalizer du store.
À tracer au RUNBOOK.

> ℹ️ **Anti-sur-adaptation (consigne).** Le livrable est un bootstrap **prod**.
> Seuls les **vrais bugs valables en prod** ont été corrigés (06 propagation RC,
> 11 sonde réseau interne). Les échecs propres au banc — egress `1.1.1.1` (07),
> transport SSH/kubeconfig (09), `mc/aws` absent — sont **documentés, pas
> contournés dans le code**.

## Run #8 (2026-06-02) — chiffrement at-rest etcd + audit-policy (ADR 0014)

Implémentation du `kubeadm init --config` (au lieu des flags) pour poser, dès
l'init, le **chiffrement des Secrets etcd** (provider `secretbox`) et la
**politique d'audit** de l'API server. Rôle
[`k8s-initialization`](../bootstrap/roles/k8s-initialization/) + ADR 0014
(points 2 et 3 passés de « dette » à « implémenté »).

| Vérification                           | Résultat banc                                                     |
| -------------------------------------- | ----------------------------------------------------------------- |
| `kubeadm init phase … --config`        | ✅ manifeste API server régénéré avec les 3 flags                 |
| Secret témoin lu dans etcd (`etcdctl`) | ✅ `k8s:enc:secretbox:v1:key1:…` (chiffré, pas en clair)          |
| Audit-log API produit                  | ✅ 962 entrées `Metadata`                                         |
| Rotation de clé (`ROTATE=1`)           | ✅ key2 ajoutée → restart → réécriture → témoin survit → rollback |
| Cluster après activation               | ✅ 3 nœuds Ready, API Running, Ceph `HEALTH_OK`, datalake Ready   |
| Scénario 15 (reproductible)            | ✅ PASS (sans et avec rotation)                                   |

**Méthode de validation sur cluster déjà init.** Le banc ayant un cluster
existant, le `kubeadm init --config` complet n'a pas été rejoué (destructif) ; à
la place, `kubeadm init phase control-plane apiserver --config` a **régénéré le
manifeste API server** à partir du `kubeadm-config.yaml` du livrable — ce qui
valide le **vrai chemin de code kubeadm**, pas une approximation. Le chiffrement
réel est ensuite prouvé via `etcdctl`. En prod (bootstrap from scratch), tous
les Secrets naissent chiffrés ; sur un cluster déjà init, les Secrets existants
restent en clair jusqu'à réécriture
(`kubectl get secrets -A -o json | kubectl replace -f -`).

### 🟢 #20 — `kubeadm upgrade` ne fetch pas la version (banc NAT, bénin)

`kubeadm init phase … --config` émet
`could not fetch a Kubernetes version from the internet … falling back to the local client version: v1.34.8`.
Sans conséquence : le fallback sur la version locale est correct, le manifeste
est généré normalement. Artefact du NAT VirtualBox (dl.k8s.io lent/injoignable),
sans objet en prod.

> 🔑 **Rotation testée.** Le scénario 15 (`ROTATE=1`) déroule les 4 étapes de
> rotation et prouve qu'un Secret témoin reste lisible **et** chiffré tout du
> long, puis restaure l'état d'origine. Procédure manuelle documentée au
> [bootstrap/RUNBOOK.md](../bootstrap/RUNBOOK.md) (§ Rotation de la clé de
> chiffrement etcd). Pas de KMS (choix ADR 0003) — rotation sur
> événement/échéance.

## Run #9 (2026-06-02) — rebuild GREENFIELD complet (from scratch)

Premier rebuild **intégral depuis zéro** : `vagrant destroy` des 3 VMs +
`run-phases.sh` (up → bootstrap → ceph → sc → workloads → etcd). But : prouver
que le bootstrap part de rien et arrive à un cluster **complet et durci**, en
intégrant tout le travail récent (chiffrement etcd, audit, WireGuard,
PodSecurity). Les runs précédents repartaient d'un cluster déjà bootstrappé —
celui-ci exerce **réellement** la séquence d'init.

| Phase     | Gate                                                | Résultat                     |
| --------- | --------------------------------------------------- | ---------------------------- |
| up        | 3 VMs + disques sd[b-e]                             | ✅                           |
| bootstrap | 3 nœuds Ready (+ WireGuard 3/3 dès l'init)          | ✅                           |
| ceph      | HEALTH_OK                                           | ✅ (après fix drift 0e)      |
| sc        | PVC Bound                                           | ✅ (après pré-condition CSI) |
| workloads | wordpress + datalake smoke-test S3 (PUT/GET/DELETE) | ✅                           |
| etcd      | snapshot 24 Mo + intégrité + timer                  | ✅                           |

**Durcissements vérifiés _nativement_ sur le cluster from-scratch** (≠ activés à
chaud) : un Secret créé par le bootstrap est `k8s:enc:secretbox:v1:key1:…` dans
etcd (chiffré dès la naissance, sans réécriture) ; audit-log à 7982+ entrées
Metadata ; `enable-wireguard=true`. **Scénarios sécurité rejoués** sur le
cluster neuf : 10 (PodSecurity), 11 (NetworkPolicy/Cilium), 12
(securityContext), 14 (WireGuard+Hubble), 15 (chiffrement etcd + audit) — **tous
PASS**.

> 🎯 **Ce run a une vraie valeur** : il a révélé **trois défauts d'outillage que
> seul un greenfield expose** (les runs incrémentaux les sautaient). Tous
> corrigés dans `test/multi-node/run-phases.sh` :

### 🔴 #21 — `run-phases.sh` appelait `upgrade.yaml` (renommé `os-upgrade.yaml`)

La boucle bootstrap référençait `upgrade.yaml`, renommé `os-upgrade.yaml` à
l'audit P5 #18. Invisible aux runs partant d'un cluster déjà bootstrappé.
**Corrigé** : `os-upgrade` dans la séquence (alignée sur le RUNBOOK).

### 🟠 0e — Images Ceph épinglées par digest **amd64** vs banc **arm64**

Le pinning par digest (audit P11 #11, PR #53) fixe l'image à **une**
architecture — amd64 (correct en prod x86_64). Sur le banc arm64, l'operator
Rook crashe en boucle : `exec /usr/local/bin/rook: exec format error`. **Sans
objet en prod.** **Surcharge banc** (`run-phases.sh`, fonction `undigest`) :
retombe sur le **tag multi-arch** pour operator/cluster/toolbox côté banc
UNIQUEMENT ; le livrable garde son digest amd64 intact (sécurité supply-chain
prod préservée).

### 🟠 #22 — Gate `sc` : PVC test créé avant propagation de la config CSI

Au premier déploiement, le CSI provisioner démarre parfois **avant** que
l'operator ait peuplé `rook-ceph-csi-config` → le PVC échoue
(`empty monitor list`) et reste en backoff, faisant échouer le gate. **Corrigé**
: pré-condition qui attend que la config CSI liste les monitors (mons en quorum)
**avant** de créer le PVC test. Vérifié : un PVC neuf passe `Bound` une fois la
config peuplée.

## Run #10 (2026-06-02) — exposition tout-Cilium (ADR 0020) sur banc

Validation **réelle sur banc multi-node** (dirqual1/2/3, arm64, K8s 1.34.8,
Cilium 1.19.4) du `cni.sh` modifié + des CRs `platform/cilium-expo/`. Banc
préexistant en Cilium baseline (kube-proxy présent) ; snapshots pris avant.

| Étape                                             | Gate                                                                                                                 | Résultat                |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `cni.sh` (kubeProxyReplacement + l2 + gatewayAPI) | ConfigMap + 3 agents `KubeProxyReplacement: True`                                                                    | ✅                      |
| `k8sServiceHost=cluster-api`                      | résolu via `/etc/hosts` du nœud (hostNetwork)                                                                        | ✅                      |
| Retrait kube-proxy                                | DaemonSet + CM supprimés, iptables `KUBE-*` purgées (3 nœuds)                                                        | ✅ (après fix #23)      |
| Non-régression datapath                           | 3 nœuds Ready, CoreDNS Running, DNS+ClusterIP OK **sans kube-proxy** (`kubernetes.default` → `10.96.0.1`)            | ✅                      |
| CRDs Gateway API v1.4.1                           | absents par défaut → installés (canal standard)                                                                      | ✅ (prérequis confirmé) |
| `CiliumLoadBalancerIPPool` banc                   | `IPS AVAILABLE 11`, `CONFLICTING False`                                                                              | ✅                      |
| `GatewayClass cilium`                             | `ACCEPTED True` (`io.cilium/gateway-controller`)                                                                     | ✅                      |
| Gateway de test → IP du pool                      | `ADDRESS 192.168.67.240`, `PROGRAMMED True` ; Service LB dérivé `EXTERNAL-IP 192.168.67.240`                         | ✅                      |
| Joignabilité L2 depuis l'hôte                     | ARP résout `.240` → MAC d'un nœud ; `curl http://192.168.67.240/` → **HTTP 404** (Envoy L7 répond, pas de HTTPRoute) | ✅                      |

### 🔴 #23 — `cni.sh` concluait « KubeProxyReplacement False » à tort → kube-proxy jamais retiré

La vérification post-bascule testait `KubeProxyReplacement: True` **une seule
fois, immédiatement** après le `rollout restart` des agents. Or les pods
`cilium` passent par une phase non-Ready (où `exec` échoue) puis reconvergent en
**1-2 min** ; le test échouait donc systématiquement et kube-proxy n'était
**jamais** retiré (le garde-fou « conserver kube-proxy si non confirmé » jouait
à tort). **Corrigé** : on attend d'abord `rollout status daemonset/cilium`, puis
on **sonde en boucle** (~3 min, sur un pod `status.phase=Running` explicite,
tolérant aux `exec` en échec). Re-joué sur le banc : la 2ᵉ exécution détecte
`True` et retire effectivement kube-proxy, sans régression DNS/ClusterIP. Le
banc arm64 a par ailleurs confirmé que l'épinglage par **digest d'index
multi-arch** (et non amd64) est correct (cf. #0e).

## Run #11 (2026-06-03) — Argo CD GitOps (ADR 0022) sur banc

Validation **réelle** d'Argo CD v3.4.3 sur le banc déjà en tout-Cilium (suite du
Run #10). Images épinglées par digest, `server.insecure` posé.

| Étape                                | Gate                                                       | Résultat                                  |
| ------------------------------------ | ---------------------------------------------------------- | ----------------------------------------- |
| `kubectl apply` du bundle            | CRDs + workloads créés                                     | ✅ (après fix #24 : `--server-side`)      |
| Pull des 3 images (argocd/dex/redis) | pods Running                                               | ✅ (après fix #25 : digest redis = index) |
| `server.insecure`                    | `argocd-server` logue `serving on port 8080 ... tls:false` | ✅                                        |
| Application de test (guestbook)      | passe `Synced/Healthy`, pod `guestbook-ui` Running         | ✅                                        |

### 🔴 #24 — `kubectl apply` client-side échoue sur la CRD `applicationsets`

`The CustomResourceDefinition "applicationsets.argoproj.io" is invalid: metadata.annotations: Too long: may not be more than 262144 bytes`
— la CRD ApplicationSet dépasse la limite de l'annotation
`last-applied-configuration` de l'apply **client-side**. **Corrigé** : déployer
avec `kubectl apply --server-side` (documenté dans le README de l'addon). Validé
: bundle appliqué, 7 workloads créés.

### 🔴 #25 — image `redis` épinglée sur un manifeste **amd64**, pas l'index multi-arch

`exec /usr/local/bin/docker-entrypoint.sh: exec format error` sur le banc
**arm64** → `CrashLoopBackOff` de `argocd-redis`. Cause : le digest résolu pour
`public.ecr.aws/.../redis:8.2.3-alpine` était celui d'un **manifeste de
plateforme unique** (`application/vnd.oci.image.manifest.v1+json`, amd64) et non
celui de l'**index multi-arch** (`...image.index.v1+json`) — un fallback de
résolution (`docker manifest inspect -v` → `Descriptor.digest`) avait renvoyé la
mauvaise valeur. **Corrigé** : ré-épinglé sur le digest d'**index**
(`sha256:08ad0b1d…`). Validé : redis Running sur arm64, app de test
`Synced/Healthy`. Même piège que #0e — toujours vérifier `MediaType: …index…`
avant d'épingler (les digests argocd et dex étaient bien des index).

## Run #12 (2026-06-03) — cert-manager + CA interne (ADR 0021) sur banc

Validation de la chaîne TLS de bordure sur le banc déjà en tout-Cilium (suite
des Runs #10/#11). cert-manager v1.20.2, chaîne CA interne, gateway-shim.
**Campagne propre : aucun finding** (les digests cert-manager étaient bien des
index multi-arch, contrairement à redis #25).

| Étape                              | Gate                                                                                                                                                                        | Résultat |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| Déploiement cert-manager           | 3 pods Running sur **arm64** (controller/webhook/cainjector)                                                                                                                | ✅       |
| Chaîne CA interne (`issuers.yaml`) | `selfsigned-bootstrap` + `internal-ca` `Ready=True` ; `root-ca` émise → `root-ca-secret` (kubernetes.io/tls)                                                                | ✅       |
| gateway-shim (Gateway annoté)      | un Gateway annoté `cert-manager.io/cluster-issuer: internal-ca` fait créer **automatiquement** le `Certificate` + remplir le Secret TLS (aucun Certificate écrit à la main) | ✅       |
| Cert émis : émetteur + SAN         | `issuer=CN=cluster-dataops Internal Root CA` ; `SAN DNS:shimtest.cluster.lan` (hostname du listener propagé)                                                                | ✅       |
| Listener HTTPS du Gateway          | `PROGRAMMED=True`, IP `192.168.67.241` du pool LB-IPAM                                                                                                                      | ✅       |

Conclusion : la chaîne complète de l'ADR 0021 (selfSigned → root CA → issuer CA
→ gateway-shim → cert de bordure) fonctionne de bout en bout. cert-manager est
laissé déployé sur le banc (chaîne CA intacte) pour la suite (exposition Argo CD
via Gateway + cert, gRPC).

## Run #13 (2026-06-03) — exposition Argo CD via Gateway + cert (ADR 0020/0021/0022)

Exposition de l'UI Argo CD via le Gateway Cilium + cert-manager sur le banc
(suite des Runs #10-#12). UI/REST validés ; gRPC-Web du CLI = finding ouvert.

| Étape                                  | Gate                                                                                                                            | Résultat       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| Gateway + HTTPRoute Argo CD            | Gateway `argocd` `PROGRAMMED=True` (IP `192.168.67.241`), HTTPRoute `Accepted=True`                                             | ✅             |
| Cert de bordure (gateway-shim)         | `argocd-server-tls` émis automatiquement par `internal-ca`                                                                      | ✅             |
| **UI Argo CD en HTTPS via le Gateway** | depuis l'hôte : `curl https://argocd.cluster.lan/` → **HTTP 200**, **TLS vérifié contre la CA interne** (`ssl_verify_result=0`) | ✅             |
| API REST via le Gateway                | `GET /api/version` → `{"Version":"v3.4.3"}` (HTTP 200)                                                                          | ✅             |
| CLI `argocd login --grpc-web`          | échoue : 404 sur `/session.SessionService/Create`                                                                               | ❌ finding #26 |

### 🟠 #26 — gRPC-Web du CLI Argo CD ne passe pas le HTTPRoute Cilium (UI/REST OK)

L'UI et l'API REST passent parfaitement par le Gateway (HTTP 200, TLS valide CA
interne). Mais `argocd login --grpc-web` reçoit un **404** sur le path gRPC
(`POST /session.SessionService/Create`) — comportement identique à un path
inexistant, donc Envoy/argocd-server ne route pas le gRPC-Web via le `HTTPRoute`
simple (PathPrefix `/` → argocd-server:80). Diagnostic : un `HTTPRoute` ne
suffit pas pour le gRPC ; la CRD `GRPCRoute` est présente (piste de correctif),
et/ou il faut indiquer au backend de parler HTTP/2 (`appProtocol`). **Conforme à
ce que l'ADR 0022 signalait** (« gRPC via le Gateway à valider »). Correctif en
cours d'instruction ; **repli fiable** documenté :
`kubectl port-forward svc/argocd-server` +
`argocd login localhost --plaintext --grpc-web`.

> **Bilan exposition** : la chaîne d'infrastructure (eBPF → LB-IPAM → L2 →
> Gateway → TLS de bordure) est validée de bout en bout, et l'**UI Argo CD est
> pleinement accessible en HTTPS**. Seul le **CLI gRPC-Web** reste à finaliser.
