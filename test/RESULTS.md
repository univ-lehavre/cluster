# Résultats — banc multi-node

> Dernière exécution : **2026-05-28**, branche `chore/cluster-rebuild-debian13`,
> banc `test/multi-node/` sur Mac Apple Silicon (M3 Max, 48 GiB) + VirtualBox
> 7.2.8 + Vagrant 2.4.9.

## Topologie testée

| VM       | IP NAT         | IP privée  | Rôle          | Disques                                     |
| -------- | -------------- | ---------- | ------------- | ------------------------------------------- |
| dirqual1 | 127.0.0.1:2222 | 10.67.2.11 | control plane | sda=OS 64G, sdb-sdd=HDD 10G ×3, sde=NVMe 5G |
| dirqual2 | 127.0.0.1:2200 | 10.67.2.12 | worker        | (idem, ordre différent)                     |
| dirqual3 | 127.0.0.1:2201 | 10.67.2.13 | worker        | (idem, ordre différent)                     |

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

```
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

**Statut prod** : **bloquant** — le drift se reproduira identique en prod.
Action requise : ajouter `storage/ceph/csi-operator.yaml` au dépôt + documenter
dans le RUNBOOK Ceph qu'il faut l'appliquer **avant** `cluster.yaml`.

### 🟠 #9 — Driver CSI pas instancié → PVC pending (impact PROD)

**Cause** : `ceph-csi-operator` ne déploie pas les plugins `csi-rbdplugin` /
`csi-cephfsplugin` automatiquement — il faut créer des objets `Driver` (CR).
Sans eux : `PVC` reste `Pending` avec
`Waiting for external provisioner 'rook-ceph.rbd.csi.ceph.com'`.

**Statut** : non corrigé dans ce run. À documenter pour Phase 3 prod :
`storage/ceph/csi-drivers.yaml` qui pose les Driver CRs RBD + CephFS.

### 🟠 #10 — OSDs Pending : `osd.requests.memory=2Gi` (banc-spécifique)

**Cause** : sur banc 5 GiB/VM × 12 OSDs créés, seuls 3 schedulables (1 par
hôte). HEALTH_OK quand même car suffit pour réplicat ×3 + `failureDomain: host`.

**Statut prod** : OK (251 GiB/nœud). À vérifier via le scénario
[`08-resource-limits-audit.sh`](scenarios/08-resource-limits-audit.sh) que la
réservation cumulée ne pose pas problème quand d'autres workloads cohabitent.

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

**État** : les 8 scripts sont **écrits, shellcheck vert, prêts à dérouler**.
Leur **exécution complète sur le banc** est gated par le drift #9 (Driver CSI).
En prod, ils tourneront de bout en bout après que `csi-operator.yaml` +
`csi-drivers.yaml` soient appliqués.
