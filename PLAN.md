# Plan de correction — Cluster K8s (bootstrap + CNI Cilium + Rook-Ceph)

## Contexte

L'audit du dépôt `cluster` (IaC d'une plateforme expérimentale : 1 control plane
`dirqual1` + 3 workers Debian 12, CNI Cilium 1.16.3, stockage hyperconvergé Rook
1.16.5 / Ceph 19.2.1) a révélé un ensemble d'incohérences allant de bugs Ansible
silencieux à des choix de stockage risqués pour les données réelles.

Fait déclencheur clé confirmé par exploration : **toutes les PVC de production**
(`apps/rstudio`, `platform/container-registry`, `storage/ceph/wordpress`)
pointent explicitement vers `rook-ceph-block-ec`, c.-à-d. le pool erasure-coded
2+1 dont le pool de métadonnées est en `replicated size: 2` (déconseillé par
Ceph) et avec un `min_size` EC qui bloque les I/O dès la perte d'un hôte. Les
charges réelles reposent donc sur la classe de stockage la moins sûre.

### Vérité terrain : audit SSH + inventaire matériel (`audit/2026-05-27-k8s-cilium-rook-ceph.md`, `platform/hardware.md`)

Un second audit, mené avec accès SSH réel, **corrobore** les constats statiques
et ajoute des faits machine : nœuds en **Debian 12 bookworm** (kernel 6.1,
cluster non encore déployé), **swap actif dans le fstab**, modules
`br_netfilter`/`overlay` non chargés. L'inventaire matériel précise le contexte
:

- **4 nœuds rigoureusement identiques** (HPE ProLiant XL420 Gen10+) : `dirqual1`
  = 10.67.2.11 (control plane), `dirqual2-4` = .12-.14 (workers), réseau cluster
  **`10.67.2.0/22`** (port 10 GbE actif).
- Par nœud : **251 GiB RAM**, 40 cœurs / 80 threads. Boot sur **miroir NVMe 447
  GiB** mal réparti (`/home` = 404 G inutilisé, **`/var` = 9 G**, `/` = 23 G).
  Data brute : **12× HDD SAS 5,5 TiB + 1× NVMe `nvme1n1` 2,9 TiB** (block.db),
  non partitionnés.
- Cluster : ~1 TiB RAM, 160 cœurs, **48 OSDs HDD prévus** (12/nœud) + 4 NVMe
  block.db.

L'homogénéité matérielle stricte **valide** l'usage de
`metadataDevice: nvme1n1` + `useAllDevices`. Ces faits durcissent plusieurs
items (CIDR, LVM `/var`, NVMe block.db) intégrés ci-dessous.

### Contrainte majeure : rebuild greenfield sur Debian 13

Les 4 serveurs vont être **réinstallés en Debian 13 (Trixie) avec effacement
total des données**. Le cluster est donc reconstruit à neuf : **aucune migration
de volume à chaud n'est nécessaire** — il suffit de déployer des manifestes
pointant dès le départ vers les bonnes classes. Cela supprime la partie la plus
risquée du plan (sauvegarde/copie/restore + nettoyage des PV `Retain`). Le wipe
disques (`/var/lib/rook` inclus) sur les 4 nœuds devient une étape critique de
pré-requis (sinon les `mon` Ceph refusent de démarrer). Debian 13 (kernel 6.12+)
justifie aussi l'activation des fonctionnalités RBD complètes et du client
CephFS kernel.

### Décisions actées avec l'utilisateur

- **Périmètre** : complet (bugs + durcissement Ceph + durcissement archi hors HA
  control plane).
- **Stockage bloc** : les workloads doivent être sur
  `rook-ceph-block-replicated` (réplicat ×3). Le wipe Debian 13 rend toute
  migration inutile → simple (re)déploiement greenfield sur la bonne classe.
- **Control plane** : 1 seul nœud (SPOF **assumé**), **mais**
  `--control-plane-endpoint` posé dès l'init pour garder la HA future possible
  sans réinstallation ; + sauvegarde etcd et procédure de restauration
  documentées.
- **Chiffrement Ceph** : non activé (accès distant déjà chiffré via Tailscale) —
  décision documentée.
- **Montée de versions** : profiter du rebuild pour aligner sur une matrice à
  jour et cohérente (K8s 1.34 / Cilium 1.19.x / Rook 1.19.x / Ceph Tentacle
  20.2.1 / containerd natif Debian 13) — cf. Workstream E.
- **Test local** : banc de test **VirtualBox 7.2.8 + Vagrant** (VMs Debian 13
  arm64) pour répéter tout le flux de bout en bout, + Molecule/Docker en CI pour
  les rôles — cf. Workstream G & section « Faisabilité ». Réserves assumées :
  arm64 (≠ x86_64 cible), échelle réduite (fonctionnel, pas perf) ; même
  `Vagrantfile` rejouable sur hôte Intel pour le x86_64.
- **Documentation des choix** : créer un espace ADR explicitant chaque décision
  de conception — cf. Workstream F.

### Résultat visé

Un bootstrap Ansible idempotent et fiable sur Debian 13 propre (CRI natif,
partitionnement sain, modules noyau, swap réellement désactivé), un réseau pods
Cilium disjoint du réseau d'infra, des charges de production sur du stockage
répliqué ×3 avec une StorageClass par défaut, une consommation de disques
maîtrisée, et une documentation honnête (plus de checks « Not implemented »
trompeurs ; SPOF, endpoint control-plane, NVMe block.db et sauvegarde etcd
explicités).

---

## Workstream A — Bootstrap Ansible (bugs de correction)

| #      | Fichier                                                                                     | Correction                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------ | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A1     | `bootstrap/roles/k8s-pre-install/tasks/main.yaml` (L106-119) + `handlers/main.yaml`         | **Swap cassé** : la tâche `debug` n'est jamais « changed » donc le handler ne part jamais, et la condition `when: stdout == ""` est inversée. Remplacer par une tâche `command: swapoff -a` conditionnée à `output_swapon.stdout != ""` avec `changed_when`, et désactiver le swap dans `/etc/fstab` (déplacer la logique du handler vers une tâche déterministe).                                                                                                                                                                                                                                                                                                 |
| A2     | `bootstrap/roles/k8s-install/tasks/main.yaml` (avant L15)                                   | **Répertoire keyrings absent** : ajouter `ansible.builtin.file: path=/etc/apt/keyrings state=directory mode=0755` avant le `gpg -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg` (échoue sinon sur Debian 13 minimal). Ne concerne plus que le dépôt Kubernetes (le dépôt Docker est supprimé, cf. A10).                                                                                                                                                                                                                                                                                                                                                           |
| A3     | `bootstrap/roles/k8s-initialization/tasks/main.yaml` (L13-18)                               | **`${HOME}` non interprété** par le module `file` → remplacer `path: ${HOME}/.kube` par `path: /home/debian/.kube`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| A4     | `bootstrap/roles/k8s-join-cluster/tasks/main.yaml` (L8, L13)                                | **Hostname codé en dur** `dirqual1` → `groups['control'][0]`. Augmenter `wait_for timeout: 1` → `30`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| A5     | `bootstrap/roles/k8s-pre-install/tasks/main.yaml` (L4-9)                                    | **Cible Debian 13 (Trixie)** : remplacer le pin `== '12.11'` par `ansible_distribution == 'Debian' and ansible_distribution_major_version == '13'` (et non un simple assouplissement).                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| A10    | `bootstrap/roles/k8s-CRI-install/tasks/main.yaml` (L36-52)                                  | **CRI = containerd natif Debian 13** (décision actée) : supprimer les tâches dépôt Docker + keyring Docker (`docker.asc`, `apt_repository` Docker), et installer le paquet **`containerd`** de Debian. Conserver ensuite `containerd config default` → `/etc/containerd/config.toml` + `SystemdCgroup = true` + restart. Une dépendance externe en moins, pas de keyring Docker.                                                                                                                                                                                                                                                                                   |
| A6     | `bootstrap/roles/k8s-CRI-install/tasks/main.yaml` (L6-24)                                   | **Prérequis noyau manquants** : charger `overlay` + `br_netfilter` via `/etc/modules-load.d/k8s.conf` + `community.general.modprobe`, et ajouter `net.bridge.bridge-nf-call-iptables=1` / `-ip6tables=1` au sysctl k8s.conf (en plus de `ip_forward`). Corriger la comparaison `when: output_ipv4_forward == "..."` (compare un objet registre, jamais vrai) → `output_ipv4_forward.stdout`.                                                                                                                                                                                                                                                                       |
| A7     | `bootstrap/roles/k8s-install/tasks/main.yaml` (L35-36) + `k8s-control-plane-nodes` (L11-12) | **Idempotence `apt-mark hold`** : remplacer le `command` par `ansible.builtin.dpkg_selections: name=... selection=hold` (idempotent).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| A8     | `bootstrap/roles/k8s-initialization/tasks/main.yaml` (L7)                                   | **Secrets dans `cluster-setup.log`** (token + hash CA) : restreindre les droits du fichier (`mode: 0600`, `owner: debian`) ou rediriger vers un fichier temporaire purgé.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| A11    | `bootstrap/roles/k8s-initialization/tasks/main.yaml` (L7-10)                                | **Idempotence `kubeadm init` cassée** : `creates: cluster-setup.log` empêche tout rejeu après un échec partiel (le log existe déjà). Conditionner plutôt sur l'état réel (`creates: /etc/kubernetes/admin.conf`) ou un `kubeadm reset` préalable en cas d'échec.                                                                                                                                                                                                                                                                                                                                                                                                   |
| A12 🟠 | `bootstrap/roles/k8s-initialization/tasks/main.yaml` (L7) + nouveau rôle/tâche `/etc/hosts` | **`--control-plane-endpoint` dès l'init** (décision actée) : init avec un nom d'endpoint stable (ex. `cluster-api`) au lieu d'un `kubeadm init` nu. Reste 1 seul control-plane (SPOF assumé) mais autorise l'ajout futur de control-planes sans réinstaller. Mettre l'endpoint dans les SANs (fichier de config kubeadm `ClusterConfiguration.controlPlaneEndpoint`), le résoudre via une entrée `/etc/hosts` (ou DNS) → IP de `dirqual1` **propagée sur les 4 nœuds** par Ansible, et ajouter `--upload-certs` pour faciliter un futur join control-plane. Vérifier la cohérence avec le kubeconfig (A3) et le join-command (les workers héritent de l'endpoint). |
| A9     | `bootstrap/roles/k8s-pre-install/tasks/main.yaml` (L25-104)                                 | **Vérifications factices** : les tâches `fail: msg=Not implemented` + `ignore_errors` donnent une fausse confiance. Soit implémenter le minimum utile (ports control-plane via `wait_for`, connectivité via `ansible.builtin.wait_for`/ping inter-nœuds), soit les **supprimer** et documenter qu'elles sont manuelles. Décision par défaut : supprimer les stubs et garder uniquement les checks réels (distro, RAM/CPU, hostnames/UUID uniques, swap).                                                                                                                                                                                                           |

---

## Workstream B — CNI Cilium

| #     | Fichier                      | Correction                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1    | `bootstrap/cni.sh` (L5, L14) | Monter Cilium `1.16.3` → **`1.19.x`** (dernier patch ; cf. matrice Workstream E). **Figer la version de la CLI** : la L5 tire `stable.txt` (non reproductible) → épingler une version explicite. Garder la vérification checksum (déjà correcte).                                                                                                                                                                                              |
| B2 🔴 | `bootstrap/cni.sh` (L14)     | **Collision CIDR confirmée (bloquant)** : le réseau des nœuds `10.67.2.0/22` est inclus dans le pool IPAM Cilium par défaut `10.0.0.0/8` → routage cassé. Fixer un CIDR pods disjoint à l'install : `cilium install --set ipam.operator.clusterPoolIPv4PodCIDRList=10.244.0.0/16` (disjoint de `10.67.2.0/22` et du service CIDR kubeadm `10.96.0.0/12`). Documenter les 3 plages dans le RUNBOOK. Tailscale `100.64.0.0/10` ne chevauche pas. |
| B3    | `bootstrap/RUNBOOK.md`       | **Recommandation (optionnelle, non bloquante)** : noter la possibilité d'activer `kubeProxyReplacement` (Cilium remplace kube-proxy) pour de meilleures perfs. Laisser en option documentée, pas de changement par défaut.                                                                                                                                                                                                                     |

> Note : la montée de version Kubernetes (1.31 → 1.34) est désormais **dans le
> périmètre** (cf. Workstream E).

---

## Workstream C — Rook-Ceph (stockage)

### C1. StorageClass par défaut + workloads sur réplicat ×3 (greenfield)

Avec le rebuild Debian 13, **pas de migration** : on corrige les manifestes et
on les déploie sur le cluster neuf.

- `storage/ceph/storageClass/block-replicated.yaml` : ajouter l'annotation
  `storageclass.kubernetes.io/is-default-class: "true"`. Activer les
  `imageFeatures` complètes
  (`layering,fast-diff,object-map,deep-flatten,exclusive-lock`) — noyau Debian
  13 (6.12+) compatible.
- Repointer les PVC de `rook-ceph-block-ec` → `rook-ceph-block-replicated`
  (simple édition de manifeste, créées à neuf au déploiement) :
  - `apps/rstudio/persistent-volume-claim.yaml` (L12)
  - `platform/container-registry/persistent-volume-claim.yaml` (L12)
  - `storage/ceph/wordpress/wordpress.yaml` (L24) et `mysql.yaml` (L24)
    (exemples — aligner sur la même classe).
- **Pré-requis rebuild (critique)** : avant `kubectl create -f cluster.yaml`,
  vérifier que `/var/lib/rook` et les disques ont bien été effacés sur **les 4
  nœuds** (assuré par le script de préparation / `cleanup.sh`). Sinon les `mon`
  redémarrent sur un ancien état et échouent. À expliciter dans
  `storage/ceph/RUNBOOK.md` comme étape obligatoire du rebuild.

### C2. Durcissement des pools EC restants

- `storage/ceph/storageClass/block-ec-delete.yaml` (L7-8) et
  `block-ec-retain.yaml` (L7-8) : pool de métadonnées `replicated size: 2` →
  **`size: 3`** + `requireSafeReplicaSize: true`.
- Documenter dans le RUNBOOK le piège `min_size` de l'EC 2+1 sur 4 hôtes
  (blocage I/O à la perte d'un hôte) ; ces classes restent réservées aux usages
  tolérants (datalake/archives), pas aux workloads critiques (désormais sur
  réplicat ×3).
- `storage/ceph/storageClass/datalake/datalake-ec.yaml` : métadonnées déjà en
  `size: 3` (OK) ; ajouter une note sur le `min_size` du data pool EC.

### C3. Maîtrise de la consommation de disques

- `storage/ceph/operator.yaml` : `ROOK_ENABLE_DISCOVERY_DAEMON: 'true'` →
  **`'false'`** (L501) et `ROOK_DISABLE_DEVICE_HOTPLUG: 'false'` → **`'true'`**
  (L551). Empêche qu'un nouveau disque brut soit automatiquement transformé en
  OSD.
- `storage/ceph/cluster.yaml` : `metadataDevice: 'nvme1n1'` (L288) +
  `useAllNodes/useAllDevices: true` est **validé par l'homogénéité matérielle
  confirmée** (`platform/hardware.md`). Documenter dans le RUNBOOK que le NVMe
  unique portant le block.db des 12 OSDs HDD du nœud est un **SPOF par nœud**
  (sa perte = perte simultanée des 12 OSDs ; tolérable car
  `failureDomain: host`). Garder `useAllDevices`, figé par la désactivation
  discovery/hotplug ci-dessus.

### C6. Observabilité et comportements destructifs (documentation / option)

- `storage/ceph/cluster.yaml` (L84) : `monitoring.enabled: false` → lacune
  d'observabilité pour un cluster de stockage. **Option recommandée** : déployer
  le Prometheus operator puis passer à `true` (hors périmètre si pas de stack
  monitoring ; à acter dans le RUNBOOK).
- `storage/ceph/storageClass/datalake/datalake-ec.yaml` (L21) :
  `preservePoolsOnDelete: false` → supprimer le `CephObjectStore` **détruit les
  pools et les données**. Documenter ce comportement comme assumé dans le
  RUNBOOK.

### C4. Ressources et propreté

- `storage/ceph/cluster.yaml` (L233-256) : ajouter des `requests` mémoire
  (mon/mgr/osd) et des bornes CPU (au moins `requests`) sur les OSD ;
  aujourd'hui seules des `limits` mémoire existent, aucun CPU.
- `storage/ceph/operator.yaml` (L672-678) : décommenter/définir `resources`
  (requests/limits) pour l'opérateur (actuellement non borné).
- `storage/ceph/storageClass/datalake/storage-class.yaml` (L5) : retirer
  `namespace: rook-ceph` (sans effet sur un objet cluster-scoped).

### C5. Chiffrement (décision documentée, sans changement technique)

- `storage/ceph/RUNBOOK.md` : noter explicitement le choix « accès via
  Tailscale, chiffrement Ceph in-transit/at-rest et TLS RGW non activés » comme
  décision assumée, avec le pré-requis que tout accès externe passe par le VPN.

---

## Workstream D — Opérations & documentation

| #     | Fichier                                                    | Correction                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ----- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1    | `storage/ceph/cleanup.sh` (L22)                            | **Robustesse glob** : `for device in /dev/sd[a-z]` avorte sous `set -e` sur un nœud NVMe-only (glob non expansée). Ajouter `shopt -s nullglob` ou un garde d'existence. Mutualiser la logique dupliquée avec le bloc équivalent du `bootstrap/RUNBOOK.md` (extraire un script unique référencé par les deux).                                                                                                                                                                                                                                   |
| D2    | `bootstrap/roles/k8s-pre-install/tasks/main.yaml` (L13-17) | **Assertion RAM cosmétique** : le plancher `>= 2048` Mo est très en-dessous du réel (251 GiB/nœud, RAM abondante pour 48 OSDs). Non bloquant — relever le seuil pour la cohérence et documenter le dimensionnement (~4-5 Go/OSD) dans le RUNBOOK.                                                                                                                                                                                                                                                                                               |
| D5 🟠 | `bootstrap/RUNBOOK.md` (préparation OS)                    | **Repartitionnement du miroir boot NVMe 447 GiB** (vérité terrain : `/var` = 9 G, `/home` = 404 G inutilisé, `/` = 23 G). `/var` héberge `containerd` (images), logs et `/var/lib/etcd` → `DiskPressure` quasi certain. Profiter de la réinstallation Debian 13 pour **redistribuer l'espace** (réduire drastiquement `/home`, allouer l'essentiel à `/var` ou `/`). À documenter comme étape obligatoire de préparation, idéalement préseedée à l'installation. Ajouter un check `assert` sur la taille minimale de `/var` dans `checks.yaml`. |
| D3    | `bootstrap/RUNBOOK.md` (nouvelle section)                  | **SPOF assumé** : documenter explicitement que `dirqual1` est un point de défaillance unique (API/etcd), la procédure de restauration, et **ajouter une sauvegarde etcd régulière** (`etcdctl snapshot save` via cron/systemd timer, ou tâche Ansible dédiée) + procédure de restore.                                                                                                                                                                                                                                                           |
| D4    | `README.md` racine / RUNBOOKs                              | **Politique de versions** : centraliser/documenter la matrice cible (cf. Workstream E : K8s 1.34, Cilium 1.19.x, Rook 1.19.x, Ceph Tentacle 20.2.1) et la procédure de bump (vérifier les compatibilités croisées avant toute montée).                                                                                                                                                                                                                                                                                                          |

---

## Workstream E — Montée de versions (matrice mi-2026)

Matrice cible cohérente et vérifiée (mai 2026), contrainte par les
compatibilités croisées : Cilium 1.19.x est testé jusqu'à K8s **1.34**, Rook
1.19.x supporte K8s **1.30–1.35** → plafond commun **K8s 1.34**.

| Composant  | Actuel       | Cible                                | Fichier(s)                                                            | Note                                                                                                                                                                                                                                    |
| ---------- | ------------ | ------------------------------------ | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Kubernetes | 1.31         | **1.34**                             | `bootstrap/roles/k8s-install/tasks/main.yaml` (L17, L24)              | Remplacer `v1.31` → `v1.34` dans l'URL du dépôt `pkgs.k8s.io` (clé + repo).                                                                                                                                                             |
| Cilium     | 1.16.3       | **1.19.x** (dernier patch)           | `bootstrap/cni.sh` (L14)                                              | 1.20 en pré-release → écarté. CLI figée (L5).                                                                                                                                                                                           |
| Rook       | 1.16.5       | **1.19.x**                           | `storage/ceph/operator.yaml` (L611) **+ `crds.yaml` + `common.yaml`** | ⚠️ Ne pas changer que l'image : **re-télécharger `crds.yaml`, `common.yaml`, `operator.yaml` depuis la release Rook v1.19.x** (les CRDs/RBAC doivent matcher l'opérateur).                                                              |
| Ceph       | 19.2.1       | **20.2.1 Tentacle** (décision actée) | `storage/ceph/cluster.yaml` (L24)                                     | Squid v19.2 **EOL 09/2026** → Tentacle pour une install neuve. Éviter v20.2.0 (corruption read-affinity). Utiliser un tag build complet (ex. `v20.2.1-AAAAMMJJ`). `allowUnsupported: false` reste OK (Tentacle supporté par Rook 1.19). |
| containerd | dépôt Docker | **natif Debian 13**                  | `bootstrap/roles/k8s-CRI-install`                                     | cf. A10. Version figée par la distro.                                                                                                                                                                                                   |
| Cilium CLI | `stable.txt` | version figée                        | `bootstrap/cni.sh` (L5)                                               | cf. B1.                                                                                                                                                                                                                                 |

Vérifier après bump : `kubeconform` re-passe (CRDs Rook 1.19),
`cilium connectivity test`, `ceph versions` homogène.

## Workstream F — Espace documentaire des choix de conception (ADR)

Créer un répertoire **`docs/decisions/`** (ADR — Architecture Decision Records)
au format léger _Context / Decision / Status / Consequences_, plus un index
`docs/decisions/README.md`. But : tracer **pourquoi** chaque choix, pas
seulement le _comment_ (déjà couvert par les README/RUNBOOK).

ADR à rédiger (issus des décisions de ce plan) :

- `0001-replication-x3-pour-workloads-bloc.md` — réplicat ×3 vs EC pour les
  charges bloc.
- `0002-control-plane-unique-avec-endpoint.md` — SPOF assumé +
  `--control-plane-endpoint` pour HA future.
- `0003-pas-de-chiffrement-ceph-tailscale.md` — chiffrement délégué au VPN.
- `0004-erasure-coding-2plus1-datalake.md` — EC réservé au datalake, compromis
  capacité/durabilité.
- `0005-cri-containerd-natif-debian.md` — containerd distro vs dépôt Docker.
- `0006-matrice-de-versions-et-politique-de-bump.md` — K8s 1.34 / Cilium 1.19 /
  Rook 1.19 / Ceph Tentacle.
- `0007-hyperconvergence-control-plane-osd.md` — control-plane détainté portant
  OSDs + charges.
- `0008-metadatadevice-nvme-spof-par-noeud.md` — NVMe unique block.db assumé.
- **`0009-pourquoi-4-noeuds.md`** — discussion de dimensionnement (ci-dessous).

### Discussion fondatrice : pourquoi 4 nœuds ?

À développer dans l'ADR 0009, points clés à argumenter :

- **Contrainte matérielle** : un châssis HPE Apollo 2000 Gen10+ héberge **4
  lames XL420** → 4 nœuds = une unité d'achat/rack naturelle.
- **Quorum des mon** : Ceph/etcd exigent un nombre **impair** de mon (3) ; avec
  4 nœuds on déploie **3 mon** (1 nœud sans mon) et on tolère la perte d'1 mon.
  5 nœuds permettraient 5 mon mais coût supérieur.
- **Tolérance de panne + maintenance** : 4 nœuds permettent de **drainer 1 nœud
  (maintenance) tout en tolérant 1 panne** sur les 3 restants en réplicat ×3 —
  marge qu'un cluster à 3 n'offre pas (3 = minimum strict, zéro marge pendant
  maintenance).
- **Limite de l'erasure coding** : `failureDomain: host` impose hôtes ≥ k+m. À 4
  nœuds, EC 2+1 (k+m=3) est le **maximum pragmatique** (laisse 1 hôte de marge)
  ; EC 2+2 (=4) ne tolérerait aucune maintenance. → justifie réplicat ×3 pour le
  critique.
- **Capacité** : 4 × (12×5,5 TiB) ≈ **264 TiB brut**, soit ~88 TiB utiles en
  réplicat ×3 — dimensionné pour le datalake universitaire.
- **À expliciter** : ce que 4 nœuds **ne** donne **pas** (HA control-plane
  réelle, tolérance 2 pannes simultanées sur le critique).

## Faisabilité — banc de test Docker du bootstrap

**Question** : peut-on tester le bootstrap Ansible localement sous Docker ?

**Évaluation** : Docker convient pour des **tests unitaires de rôles**, pas pour
une répétition de bout en bout.

| Aspect                                         | Faisable sous Docker ? | Détail                                                                                                                                                                                |
| ---------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Syntaxe / lint / idempotence des rôles         | ✅ Oui                 | Via **Molecule + driver Docker** sur image Debian 13 systemd-enabled. Couvre install paquets (containerd, kubeadm/kubelet/kubectl), keyrings, config sysctl/containerd, version pins. |
| `swapoff` / fstab (A1)                         | ⚠️ Partiel             | Pas de swap dans un conteneur → logique testable mais non représentative.                                                                                                             |
| Modules noyau `br_netfilter`/`overlay` (A6)    | ❌ Non                 | Modules partagés avec l'hôte, non chargeables depuis le conteneur.                                                                                                                    |
| Tâches `reboot` (swap, upgrade-os)             | ❌ Non                 | Incompatibles conteneur → à mocker/skipper en test.                                                                                                                                   |
| `kubeadm init`/`join` réel (etcd, réseau, CNI) | ❌ Fragile             | kubeadm-in-Docker exige privilégié + cgroups + /sys ; non fiable et non représentatif.                                                                                                |
| Ceph / OSD sur disques bruts                   | ❌ Non                 | Nécessite des block devices réels ; Docker n'en fournit pas.                                                                                                                          |

**Recommandation** :

1. **Docker/Molecule en CI** pour valider rôles + idempotence (rapide, gratuit)
   — ajout possible au workflow `.github/workflows/ci.yml` à côté
   d'`ansible-lint`. Faisable, périmètre limité (≈ install/config, pas le
   cluster).
2. **Répétition de bout en bout sur VMs** (Vagrant + libvirt/QEMU, ou multipass)
   avec disques virtuels attachés → seule façon fidèle de tester `kubeadm` +
   Cilium + Ceph mono-nœud avant le rebuild Debian 13.

Conclusion : **Docker = oui pour les tests de rôles, non pour l'intégration
cluster** ; prévoir des VMs pour la validation finale.

### Sur macOS Apple Silicon (M3 Max arm64, 48 Go RAM — poste détecté)

**Peut-on tester l'ensemble de l'installation sur ce Mac ?** Oui pour un
**smoke-test fonctionnel complet**, avec deux réserves majeures.

| Approche                                                                                                     | Sur ce Mac                                                                                                                  | Verdict                                                                                                             |
| ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Molecule + Docker/Podman (présents)                                                                          | conteneurs **arm64**                                                                                                        | ✅ tests de rôles uniquement (idem section Docker), pas de cluster réel                                             |
| **VirtualBox 7.2.8 + Vagrant** (présent, à jour) — VMs Debian arm64 + disques + **NVMe virtuel** + snapshots | invité **arm64** mûr en 7.2 ; **invités x86_64 toujours non supportés** sur hôte Apple Silicon (émulation Intel désactivée) | ✅ **backend retenu** (multi-VM/snapshots/NVMe natifs ; même `Vagrantfile` rejouable sur hôte Intel pour le x86_64) |
| **Lima** (`brew install lima`) — VMs Debian 13 **arm64** + disques attachés                                  | 3-4 VMs (2-4 Go RAM ch.), OSDs sur petits disques virtuels                                                                  | ⚠️ repli mac-natif (très stable arm64) ; réseau multi-VM via `socket_vmnet`                                         |
| multipass (présent)                                                                                          | **Ubuntu only**                                                                                                             | ❌ diverge de Debian + containerd natif → non fidèle                                                                |
| QEMU **x86_64** émulé (archi fidèle)                                                                         | TCG, très lent                                                                                                              | ❌ impraticable pour un cluster + Ceph                                                                              |

**Réserves déterminantes** :

1. **Architecture** : cluster cible = **x86_64** (Xeon), Mac = **arm64**. Des
   VMs arm64 valident la **logique** (rôles Ansible, manifestes, câblage,
   liaison des PVC) mais **pas les artefacts x86_64** réels (images conteneurs,
   paquets `containerd`/kubeadm diffèrent par arch). L'émulation x86_64 fidèle
   est trop lente.
2. **Échelle** : 48 Go RAM + petits disques virtuels → on prouve que **ça
   déploie et fonctionne**, pas les 66 To/nœud ni les performances.

**Recommandation macOS** : monter le banc fonctionnel de bout en bout sur le
poste avec **VirtualBox 7.2.8 + Vagrant** (décision actée ; cf. **Workstream
G**), puis **rejouer le même `Vagrantfile` sur un hôte Intel** (ou VMs cloud
x86_64 / pré-prod matériel réel) pour la fidélité x86_64 avant le rebuild
définitif. Ne pas se reposer sur multipass (Ubuntu) ni sur l'émulation x86_64.

## Workstream G — Banc de test local (rehearsal de bout en bout)

Objectif : répéter **tout le flux** (bootstrap Ansible → kubeadm → Cilium →
Rook-Ceph → liaison PVC) sur des VMs locales **avant** le rebuild Debian 13,
comme garde-fou ; + tests de rôles automatisés en CI.

**Backend VM retenu : VirtualBox 7.2.8 + Vagrant** (décision actée ; Lima =
repli) :

- `Vagrantfile` **multi-machine** (1 control + 2-3 workers), provisioner
  **Ansible natif** de Vagrant pour lancer les playbooks.
- Disques additionnels via `VBoxManage` (OSDs) + **contrôleur NVMe virtuel**
  pour émuler `nvme1n1`/block.db.
- Réseau **host-only/internal** simulant `10.67.2.0/22` ; **snapshots** pour
  réinitialiser entre runs.
- Box **Debian 13 arm64** à fournir (importer une box, ou build via
  `packer`/install ISO) — principal effort de mise en place.
- Invités **arm64** (7.2 mûr) ; invités **x86_64 non supportés** sur Apple
  Silicon → le **même `Vagrantfile` resservira sur hôte Intel** pour la fidélité
  x86_64.

**Comparatif des backends** (cas : 3-4 VMs Debian 13 arm64 sur M3 Max 48 Go) :

| Critère                          | Lima                     | VirtualBox 7.2.8 + Vagrant         |
| -------------------------------- | ------------------------ | ---------------------------------- |
| Déjà installé                    | ❌ (`brew install lima`) | ✅ présent/à jour                  |
| Invités Debian arm64             | ✅✅ très mûr            | ✅ mûr (7.2)                       |
| Invités x86_64 sur ce Mac        | ❌ émulé (lent)          | ❌ non supporté                    |
| Réseau multi-VM (10.67.2.0/22)   | ⚠️ `socket_vmnet`        | ✅ host-only/internal natif        |
| Disques OSDs / NVMe virtuel      | ✅ / ⚠️ virtio-blk       | ✅ / ✅ contrôleur NVMe            |
| Snapshots                        | ⚠️ limité                | ✅ mûr                             |
| Orchestration multi-VM           | ⚠️ par VM                | ✅ multi-machine (1 `Vagrantfile`) |
| Réutilisable hôte Intel (x86_64) | ✅ (autre install)       | ✅✅ même `Vagrantfile`            |
| Stabilité Apple Silicon          | ✅✅                     | ✅                                 |
| Friction                         | réseau `socket_vmnet`    | box Debian arm64 à fournir         |

**Recommandation : VirtualBox 7.2.8 + Vagrant** — déjà en place,
multi-VM/snapshots/NVMe natifs, et **même `Vagrantfile` réutilisable sur hôte
Intel** pour l'étape x86_64. (Lima = repli plus stable en arm64 pur.)

**Éléments communs (indépendants du backend)** :

- **3-4 VMs Debian 13** (1 control + 2-3 workers) : 3 suffisent à exercer le
  quorum mon (3), le réplicat ×3 et l'EC 2+1 ; 4 collent à la topologie réelle.
  ~6-8 Go RAM/VM tiennent dans 48 Go.
- Par VM : **2-3 disques data virtuels** (~10 Go) + 1 « NVMe » virtuel optionnel
  pour exercer `metadataDevice`/block.db.
- Provisioning minimal : utilisateur `debian` + `sudo` NOPASSWD + clé SSH
  (pré-requis des rôles), pour **réutiliser les playbooks tels quels**.
- **Inventaire Ansible dédié** (`bootstrap/inventories/local.yaml`) pointant les
  VMs ; ne pas toucher `hosts.yaml` (prod).
- Adaptations : mock/skip Tailscale ; tâches `reboot` OK en VM ; CIDR Cilium
  disjoint déjà géré (B2).
- **Molecule + Docker/Podman en CI** (`.github/workflows/ci.yml`, à côté
  d'`ansible-lint`) pour l'idempotence des rôles — arm64 en local, **x86_64 sur
  les runners GitHub** (bonus : couvre l'arch cible côté rôles).
- Script/`Makefile` `up` / `provision` / `destroy` (+ snapshots VBox) pour
  itérer.

**Réserves** (cf. Faisabilité) : arm64 ≠ x86_64 cible, **fonctionnel pas à
l'échelle** → compléter par une répétition x86_64 (VBox+Vagrant sur hôte Intel,
ou VMs cloud x86_64) avant le rebuild définitif.

## Phasage pas à pas (banc VBox → serveurs)

Principe : **chaque phase est d'abord validée sur le banc VirtualBox/Vagrant**
(avec snapshot de retour arrière), **puis appliquée aux serveurs**. On ne passe
à la phase n+1 que si les critères de succès de la phase n sont verts sur le
banc _et_ sur les serveurs. Les correctifs dépôt de chaque phase sont committés
sur une branche avant validation.

> Note rebuild : les phases 1-2 côté serveurs s'exécutent dans la **fenêtre de
> réinstallation** (séquentielles) ; les phases 3-7 s'appliquent au cluster
> fraîchement reconstruit. Le banc, lui, rejoue chaque phase en amont.

### Stratégie de déploiement serveurs : canari `dirqual1` puis les 3 workers

Le déploiement sur le matériel suit un **rollout par nœud en canari**, faisable
sous deux conditions :

1. **Le canari est le control plane `dirqual1`** (ordre imposé : `kubeadm init`
   s'y fait ; un worker ne peut être complet qu'après avoir rejoint un control
   plane existant).
2. **« Complet » s'entend au niveau nœud, pas au niveau stockage** : Ceph
   (`mon.count: 3`, réplicat ×3, EC 2+1, `failureDomain: host`) exige **≥ 3
   hôtes** → il ne devient `HEALTH_OK` qu'une fois les 3 workers joints.

Séquence concrète :

1. **Canari `dirqual1`** : Phases 1-2 de bout en bout (réinstall Debian 13 +
   partitionnement + wipe → bootstrap bas niveau → `kubeadm init` + endpoint →
   Cilium). **Gate** : 1-node cluster Ready, `cilium connectivity test` vert.
   C'est le point où l'on débusque les soucis OS/matériel **avant** de toucher
   les 3 autres.
2. **`dirqual2-4`** : Phase 1 (réinstall + bootstrap) puis join. **Gate** : 4
   nœuds Ready.
3. **Cluster-wide une fois les 4 nœuds Ready** : Phases 3-7 (Rook-Ceph,
   StorageClasses, workloads, exploitation). Ne **pas** déployer le
   `CephCluster` avant d'avoir les 3+ hôtes, sinon mons/OSDs/pools restent
   dégradés.

Greenfield (données effacées) → aucun risque de données pendant la montée
incrémentale. Le banc VBox doit avoir validé ce même enchaînement au préalable.

### Phase 0 — Banc de test (pré-requis)

- **Dépôt** : Workstream G (`Vagrantfile` multi-VM, inventaire
  `bootstrap/inventories/local.yaml`, box Debian 13 arm64, disques + NVMe
  virtuels). Optionnel : Molecule en CI.
- **✅ Banc** : `vagrant up` → 3-4 VMs Debian 13 bootent ; Ansible atteint les
  VMs ; `vagrant snapshot save clean` ; `vagrant destroy && up` reproductible.
- **🖥️ Serveurs** : n/a (outillage).

### Phase 1 — Préparation OS & runtime (bootstrap bas niveau)

- **Dépôt** : A5 (Debian 13), A2 (keyrings), A10 (containerd natif), A6 (modules
  noyau), A1 (swap), A7 (holds idempotents), A9 (checks réels), D2 (RAM), D5
  (partitionnement), E (containerd/K8s repo 1.34).
- **✅ Banc** : `upgrade→checks→cri→kubeadm` ; **idempotence** (2e run = 0
  changed) ; `containerd` actif + `SystemdCgroup=true` ; swap off ;
  `br_netfilter`/`overlay` chargés ; snapshot.
- **🖥️ Serveurs** : réinstallation Debian 13 + partitionnement sain (`/var`) +
  wipe disques (`/var/lib/rook`) ; playbooks bas niveau. **Critère** : nœuds
  prêts, `kubeadm`/`kubelet` installés, containerd up.

### Phase 2 — Init cluster + endpoint + CNI

- **Dépôt** : A12 (`--control-plane-endpoint`), A11 (idempotence init), A3
  (.kube), A8 (secrets log), A4 (join dynamique), B1 (Cilium 1.19.x), B2 (CIDR
  disjoint), E (K8s 1.34).
- **✅ Banc** : `kubeadm init` avec endpoint OK ; workers joints ; Cilium
  installé (CIDR `10.244.0.0/16` disjoint) ; `kubectl get nodes` tous Ready ;
  `cilium connectivity test` vert ; snapshot.
- **🖥️ Serveurs** : init `dirqual1` (endpoint) → `cni.sh` → join workers.
  **Critère** : 4 nœuds Ready, connectivité vert.

### Phase 3 — Rook-Ceph (opérateur + cluster)

- **Dépôt** : E (Rook 1.19.x `crds/common/operator` re-téléchargés, Ceph
  **Tentacle 20.2.1**), C3 (discovery/hotplug off), C4 (ressources mon/mgr/osd +
  opérateur).
- **✅ Banc** : `crds→common→operator→cluster` sur disques + NVMe virtuels ;
  OSDs `Running` ; `ceph status` **HEALTH_OK** ; un disque ajouté à chaud
  **non** auto-consommé ; snapshot.
- **🖥️ Serveurs** : idem. **Critère** : 48 OSDs Up, HEALTH_OK, block.db sur
  `nvme1n1`.

### Phase 4 — StorageClasses (défaut + EC durci)

- **Dépôt** : C1 (classe par défaut + `imageFeatures` complètes), C2 (metadata
  EC `size: 3`), filesystem + datalake SC, C5 (doc chiffrement).
- **✅ Banc** : `kubectl get sc` → **1 seule `(default)`** =
  `rook-ceph-block-replicated` ; PVC test → **Bound** ;
  `ceph osd pool ls detail` → metadata EC `size 3` ; snapshot.
- **🖥️ Serveurs** : appliquer les SC (**défaut d'abord**). **Critère** : PVC
  test Bound, pools conformes.

### Phase 5 — Workloads + object store

- **Dépôt** : PVC apps repointées → `rook-ceph-block-replicated` (rstudio,
  container-registry, wordpress) ; datalake (object store, OBCs, users) ; C6
  (`preservePoolsOnDelete` doc).
- **✅ Banc** : déployer un workload bloc (wordpress) → PVC Bound + pod Running
  ; object store → bucket créé + credentials extractibles ; snapshot.
- **🖥️ Serveurs** : déployer apps/platform + datalake. **Critère** : PVC Bound
  sur réplicat ×3, S3 accessible (via Tailscale).

### Phase 6 — Exploitation (sauvegarde etcd, durcissement)

- **Dépôt** : D3 (sauvegarde etcd + doc SPOF), D1 (`cleanup.sh` robuste), C6
  (monitoring option), B3 (kubeProxyReplacement option).
- **✅ Banc** : `etcdctl snapshot save` OK **et restauration testée** ;
  `cleanup.sh` ne casse pas sur VM sans `sd*` ; snapshot.
- **🖥️ Serveurs** : installer le timer de sauvegarde etcd. **Critère** :
  snapshot etcd produit + restaurable.

### Phase 7 — Documentation

- **Dépôt** : Workstream F (`docs/decisions/*`, dont
  **`0009-pourquoi-4-noeuds`**), D4 (politique de versions).
- **✅ Tests** : CI verte
  (prettier/yamllint/kubeconform/ansible-lint/shellcheck) ; liens ADR valides.
- **🖥️ Serveurs** : n/a (documentation).

---

## Vérification

Sans cluster live accessible depuis ce dépôt, la validation s'appuie sur la CI
existante (`.github/workflows/ci.yml`) reproduite localement :

```bash
pnpm install --frozen-lockfile
pnpm format:check                       # prettier
yamllint -c .yamllint.yaml .            # lint YAML
# kubeconform sur les manifestes (hors bootstrap/)
find . -name '*.yaml' -not -path './bootstrap/*' -not -path './node_modules/*' \
  | xargs kubeconform -strict -ignore-missing-schemas \
      -schema-location default \
      -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
ansible-lint                            # depuis bootstrap/
shellcheck bootstrap/cni.sh storage/ceph/cleanup.sh
```

Validations supplémentaires recommandées :

- **Bootstrap** : `ansible-playbook --syntax-check` sur chaque playbook. Sur le
  parc Debian 13 réinstallé, vérifier l'idempotence (2e run = 0 changed) sur
  `checks.yaml`, `cri.yaml`, `kubeadm.yaml`, et confirmer que `containerd`
  (paquet natif Debian 13, cf. A10) démarre.
- **Cluster reconstruit** : `kubectl get nodes` (4 Ready),
  `cilium connectivity test` OK.
- **Ceph (cluster neuf)** : `kubectl get sc` → une seule classe `(default)` =
  `rook-ceph-block-replicated` ; `ceph osd pool ls detail` → pools de
  métadonnées EC en `size 3` ; un disque ajouté à chaud n'est **pas**
  auto-consommé (discovery/hotplug off) ; les PVC `rstudio`/`container-registry`
  se lient bien sur la classe répliquée.

---

## Points hors périmètre (notés, non traités ici)

- Ajout effectif de control-planes (HA 3 nœuds) — SPOF assumé pour l'instant ;
  l'endpoint posé à l'init (A12) rend l'ajout futur possible sans
  réinstallation.
- Chiffrement Ceph in-transit/at-rest et TLS RGW — couvert par Tailscale.
- Passage à une déclaration explicite `nodes:`/`devices:` dans `cluster.yaml`
  (nécessite un inventaire matériel par hôte — désormais disponible dans
  `platform/hardware.md`, donc faisable ultérieurement).
- Banc de test VM de bout en bout (Vagrant/libvirt) — recommandé mais distinct
  du dépôt actuel.
