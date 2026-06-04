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

| #   | Étape (phase)                     | Résultat                                                         |
| --- | --------------------------------- | ---------------------------------------------------------------- |
| 0   | `up` — 3 VMs Lima + disques bruts | ✅ disques `vdb`-`vde` bruts détectés sur chaque nœud            |
| 1   | `bootstrap` — checks/cri/kubeadm  | ✅ 3 nœuds, containerd + kubeadm/kubelet v1.34.8                 |
| 2   | `bootstrap` — control-planes/init | ✅ après fixes drifts L1/L2/L3 (`kubeadm init` OK)               |
| 3   | `bootstrap` — cni.sh (Cilium)     | ✅ après fix drift L4, Cilium 1.19.4 + WireGuard (3/3 nodes)     |
| 4   | `bootstrap` — join-workers        | ✅ après fix drift L2bis, node1 + node2 joints                   |
| 5   | `bootstrap` — gate 3 nœuds Ready  | ✅ après fix drift L5 (kubeconfig hôte)                          |
| 6a  | `storage-simple` — local-path     | ✅ provisioner Ready, PVC `local-path` → **Bound** (mode rapide) |
| 6b  | `ceph` — operator + cluster       | ✅ images dé-épinglées arm64, operator Ready                     |
| 7   | `ceph` — OSD + HEALTH_OK          | ✅ après fix drift L6 (lvm2), 9 OSD up/in, HEALTH_OK             |
| 8   | `sc` — StorageClasses + PVC test  | ✅ PVC `rook-ceph-block-replicated` → **Bound**                  |
| 9   | `down` — destruction              | ✅ VMs + disques nommés supprimés, rien ne subsiste              |

> **Stockage modulaire** (#151) : `all` par défaut = mode **rapide** (up →
> bootstrap → `storage-simple`/local-path) ; `WITH_CEPH=1 … all` ajoute le
> stockage réel (Ceph). Le banc complet ci-dessus = mode Ceph.

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

## Validation e2e Dagster (#144, 2026-06-04)

Chaîne DataOps **Dagster** validée de bout en bout sur le banc Lima arm64 (mode
rapide local-path), débloquée par le fix des digests multi-arch (#140) :

| Étape                                 | Résultat                                                                 |
| ------------------------------------- | ------------------------------------------------------------------------ |
| cert-manager + CNPG operator          | ✅ après fix drift L8 (CRDs Gateway API)                                 |
| CNPG cluster `pg` + base `dagster`    | ✅ Healthy 3/3 (PG18 + pgvector), base `dagster` créée                   |
| registry interne (image `registry:3`) | ✅ pull arm64 OK (digest d'index, #140) après fix drift L10 (PVC SC)     |
| image Dagster arm64 → `registry:80`   | ✅ buildée + poussée (via nerdctl sur un nœud), `architecture: arm64`    |
| pods Dagster pull `registry:80`       | ✅ après fix drift L9 (containerd insecure) + drift L11 (namespace)      |
| storage Dagster                       | ✅ **22 tables dans Postgres** (base `dagster`), **pas de SQLite**       |
| run e2e via `K8sRunLauncher`          | ✅ **Job K8s `dagster-run-…` Complete**, run `SUCCESS`, 21 événements PG |

Séquence d'événements du run (event log Postgres) :
`PIPELINE_ENQUEUED → PIPELINE_STARTING → STEP_WORKER_STARTED → STEP_START → STEP_SUCCESS → PIPELINE_SUCCESS`.
Exemple jetable retiré ensuite.

| #   | Symptôme                                                             | Cause                                                                                     | Correctif                                                                       |
| --- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| L8  | cert-manager controller CrashLoop : « Gateway API CRDs not present » | `cni.sh` active `gatewayAPI` ; Cilium n'embarque pas les CRDs ; le bootstrap nu non plus  | phase `platform-prereqs` : pose les CRDs Gateway API v1.4.1                     |
| L9  | ImagePullBackOff : « HTTP response to HTTPS client » (`registry:80`) | containerd tente HTTPS sur le registry interne HTTP ; nom `registry` non résolu côté nœud | phase `platform-prereqs` : `/etc/hosts` + `certs.d/registry:80/hosts.toml` HTTP |
| L10 | registry pod Pending : `unbound PersistentVolumeClaim`               | PVC du registry hardcodé `rook-ceph-block-replicated`, absent du banc (local-path)        | override banc : PVC sur `local-path` (à paramétrer comme CNPG `storageClass`)   |
| L11 | `kubectl apply -f dagster.yaml` → ressources dans `default`          | le helm template figé ne porte pas `metadata.namespace`                                   | README : `kubectl apply -n dagster …` (corrigé)                                 |

## Réserves

- **`os-upgrade` non rejoué** (contrairement au banc Vagrant) : image Lima
  fraîche — divergence assumée (cf. [`README.md`](README.md)).
- **arm64** : images Ceph dé-épinglées (digests amd64 → `exec format error`)
  côté banc seulement ; le livrable garde ses digests.
- **StorageClass `default` unique** : le banc pose `is-default-class` sur UNE
  seule SC à la fois (`set_default_sc`) — `local-path` en mode rapide,
  `rook-ceph-block-replicated` en mode Ceph. La bascule local-path → Ceph a été
  validée (le `default` passe proprement de l'un à l'autre). Une SC résiduelle
  d'un autre outil ne fausse donc plus le gate.
- **Gate Ceph sous charge** : sur un hôte chargé (peu de RAM libre), la montée
  HEALTH_OK peut dépasser la fenêtre de 20 min du gate alors que Ceph converge
  ensuite normalement — relancer `ceph` (idempotent) ou libérer de la RAM. Le
  mode rapide (local-path) évite ce coût au quotidien.
