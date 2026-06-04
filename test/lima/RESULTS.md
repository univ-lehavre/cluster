# Résultats — banc Lima

> Première exécution : **2026-06-04**, branche
> `feat/127-banc-lima-industrialise`, banc `test/lima/` sur Mac Apple Silicon +
> Lima 2.1.2, Kubernetes v1.34.8.

Honnêteté des Runs (ADR 0023) : ce fichier consigne le déroulé réel et les
_drifts_ (écarts banc, pas bugs du dépôt) rencontrés en montant le banc Lima de
bout en bout. Le banc Vagrant a son propre log :
[`../RESULTS.md`](../RESULTS.md).

## Topologie testée

| VM    | Réseau user-v2 | Rôle          | Disques (virtio-blk)                            |
| ----- | -------------- | ------------- | ----------------------------------------------- |
| cp1   | 192.168.104.1  | control plane | vda=OS 20G, vdb-vdd=HDD 10G ×3, vde=block.db 5G |
| node1 | 192.168.104.3  | worker        | (idem)                                          |
| node2 | 192.168.104.4  | worker        | (idem)                                          |

- Image : `_images/debian-13` (Lima), kernel `6.12.90+deb13-cloud-arm64`.
- `vdf` (263 MiB, iso9660 `cidata`) = disque cloud-init de Lima, ignoré par
  Ceph.
- API jointe depuis l'hôte via le portForward Lima `127.0.0.1:6443` (l'IP
  user-v2 n'est pas routable depuis macOS) + `tls-server-name: cluster-api`.

## Chemin obligatoire testé

| #   | Étape (phase)                     | Résultat                                                     |
| --- | --------------------------------- | ------------------------------------------------------------ |
| 0   | `up` — 3 VMs Lima + disques bruts | ✅ disques `vdb`-`vde` bruts détectés sur chaque nœud        |
| 1   | `bootstrap` — checks/cri/kubeadm  | ✅ 3 nœuds, containerd + kubeadm/kubelet v1.34.8             |
| 2   | `bootstrap` — control-planes/init | ✅ après fixes drifts L1/L2/L3 (`kubeadm init` OK)           |
| 3   | `bootstrap` — cni.sh (Cilium)     | ✅ après fix drift L4, Cilium 1.19.4 + WireGuard (3/3 nodes) |
| 4   | `bootstrap` — join-workers        | ✅ après fix drift L2bis, node1 + node2 joints               |
| 5   | `bootstrap` — gate 3 nœuds Ready  | ✅ après fix drift L5 (kubeconfig hôte)                      |
| 6   | `ceph` — operator + cluster       | ✅ images dé-épinglées arm64, operator Ready                 |
| 7   | `ceph` — OSD + HEALTH_OK          | ✅ après fix drift L6 (lvm2), 9 OSD up/in, HEALTH_OK         |
| 8   | `sc` — StorageClasses + PVC test  | ✅ PVC `rook-ceph-block-replicated` → **Bound**              |
| 9   | `down` — destruction              | ✅ VMs + disques nommés supprimés, rien ne subsiste          |

## Drifts détectés et correctifs

Préfixe **L** = spécifique au banc **L**ima (vs les drifts numériques du banc
Vagrant). Tous corrigés dans ce chantier ; aucun n'est un bug du dépôt — ce sont
des écarts entre l'environnement Lima et les hypothèses du bootstrap/banc.

| #     | Symptôme                                                     | Cause                                                                                               | Correctif                                                                                     |
| ----- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| L1    | `initialisation` : `ansible_user is undefined`               | inventaire posait l'utilisateur via SSH (ssh.config) mais pas la **variable** `ansible_user`        | inventaire généré : `cloud.vars.ansible_user: lima`                                           |
| L2    | `initialisation` : `Permission denied: /home/lima` (.kube)   | home Lima = `/home/lima.guest` (≠ `/home/lima`) ; rôle construisait le home via `ansible_user`      | rôles `k8s-initialization`/`k8s-rollback` : home résolu via `ansible_env.HOME` (le vrai home) |
| L2bis | `join-workers` : `Unable to change directory` (/home/debian) | `chdir: /home/debian` codé en dur dans `k8s-join-cluster` ; absent sur Lima                         | `chdir` via `ansible_env.HOME`                                                                |
| L3    | `initialisation` : `taint "…control-plane" not found`        | kubeadm v1.34 : le control-plane n'a pas le taint control-plane → `taint …-` échoue                 | tâche tolérante : `failed_when` ignore « not found »                                          |
| L4    | `cni.sh` : `cluster unreachable: localhost:8080`             | `cni.sh` lancé en `sudo` → kubectl/cilium pointent sur le kubeconfig root absent                    | lancer `cni.sh` **en tant qu'utilisateur** (sudo interne où nécessaire seulement)             |
| L5    | gate kubeconfig : API injoignable depuis l'hôte              | IP user-v2 (`192.168.104.x`) non routable depuis macOS                                              | réécrire `server:` sur `127.0.0.1:<portForward>` + `tls-server-name: cluster-api`             |
| L6    | OSD-prepare CrashLoopBackOff : `binary lvm does not exist`   | `metadataDevice` (block.db) → Rook en mode LVM → `ceph-volume` exige `lvm` ; absent de l'image Lima | installer `lvm2` dans le provision de la VM (`profiles/node.yaml.tmpl`)                       |
| L7    | gate Ceph vert à 0 OSD                                       | `ceph health` = HEALTH_OK sur un cluster neuf SANS pool (rien à dégrader)                           | gate renforcé : HEALTH_OK **ET** OSD attendus up (nœuds × disques data)                       |

## Réserves

- **`os-upgrade` non rejoué** (contrairement au banc Vagrant) : image Lima
  fraîche — divergence assumée (cf. [`README.md`](README.md)).
- **arm64** : images Ceph dé-épinglées (digests amd64 → `exec format error`)
  côté banc seulement ; le livrable garde ses digests.
- **Pollution hôte possible** : un `local-path` StorageClass résiduel d'un
  ancien spike peut rester marqué `default` et faire échouer le gate « 1 SC
  default ». Le banc lui-même n'installe pas local-path ; nettoyer avec
  `prune.sh`.
