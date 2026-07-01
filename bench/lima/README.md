# Banc Lima (multi-VM + Ceph)

**Seul banc local**
([ADR 0038](/cluster/docs/decisions/0038-lima-seul-banc-local/)) — 3 VMs +
disques bruts + Rook/Ceph, sur des **VMs Lima**.

Pourquoi Lima
([ADR 0006](/cluster/docs/decisions/0006-matrice-de-versions-et-politique-de-bump/))
:

- **kind est abandonné** : son image de nœud figeait Kubernetes en **1.31**
  (incompatible `ImageVolume`/pgvector).
- **Vagrant + VirtualBox sont dépréciés** (ADR 0038, VirtualBox sans support
  arm64 fiable). Lima monte une **vraie VM Linux** (vrai noyau, vrais cgroups,
  swap contrôlable, SSH natif) sur laquelle tourne le **VRAI bootstrap Ansible**
  — même chemin que la prod, sans overlayfs imbriqué (échec du DinD) ni
  VirtualBox.

## Topologie

| Nœud    | Rôle          | Réseau                       | Disques bruts (virtio)           |
| ------- | ------------- | ---------------------------- | -------------------------------- |
| `cp1`   | control-plane | user-v2 (`192.168.104.0/24`) | 3 × 10 GiB (`vdb`-`vdd`) + `vde` |
| `node1` | worker        | user-v2                      | 3 × 10 GiB + `vde` (block.db)    |
| `node2` | worker        | user-v2                      | 3 × 10 GiB + `vde` (block.db)    |

- **Réseau `user-v2`** : connectivité VM↔VM **sans `socket_vmnet` ni `sudo`
  hôte** ; chaque VM est joignable en `lima-<nom>.internal` et porte le trafic
  inter-nœuds (join workers, mon Ceph) ET l'accès API depuis l'hôte. Le
  `control_plane_ip` du bootstrap est posé sur cette IP user-v2 (pas le NAT par
  défaut, non routable entre VMs).
- **Disques bruts** : Lima ne crée pas de disque vierge inline → des disques
  nommés persistants (`<nœud>-hdd1..3`, `<nœud>-blockdb`) sont créés **avant**
  le démarrage et attachés en `additionalDisks: {format: false}` pour rester
  bruts (exigence Ceph). Lima les présente en **virtio-blk → `/dev/vd*`** (≠
  l'ex-banc VirtualBox VirtioSCSI → `/dev/sd*`), d'où les surcharges
  `CEPH_HDD_GLOB`, `CEPH_BLOCK_DEVICE=vde` dans l'orchestrateur.

## Pré-requis poste

Poste de contrôle = **macOS** (Apple Silicon) **ou Linux** ; Windows → **WSL2**
([ADR 0100](/cluster/docs/decisions/0100-perimetre-os-poste-et-noeuds/)). Les
commandes ci-dessous sont en `brew` (macOS) ; sur Linux, équivalents `apt` /
binaires.

| Outil   | Version  | Installation                              |
| ------- | -------- | ----------------------------------------- |
| Lima    | ≥ 2.0    | `brew install lima`                       |
| Ansible | ≥ 2.20.5 | `brew install ansible`                    |
| kubectl | —        | `brew install kubectl`                    |
| python3 | —        | (préinstallé macOS ; `python3` sur Linux) |

**RAM consommée** : 3 × 12 GiB ≈ **36 GiB** par défaut (`VM_MEMORY` 12 GiB/VM,
marge OK sur un hôte 48 GiB pour macOS). Surchargeable via `VM_MEMORY` ; le
check bootstrap `k8s-pre-install` exige `real.total ≥ 4096 MB` (une VM 4 GiB ne
le garantit pas).

## Modes de stockage

Le stockage est **modulaire** — Ceph (~15 min) n'est monté que si on en a besoin
:

| Mode             | StorageClass par défaut      | Pour quoi                                            | Coût       |
| ---------------- | ---------------------------- | ---------------------------------------------------- | ---------- |
| **simple** (déf) | `local-path`                 | itérer vite sur la couche applicative/plateforme     | ~30 s      |
| **Ceph**         | `rook-ceph-block-replicated` | valider le stockage bloc/objet réel (RBD/CephFS/RGW) | ~10-15 min |

Beaucoup de briques (Argo CD, monitoring, Dagster, Mailpit…) n'ont besoin que
d'un `StorageClass` fournissant des PVC : le mode simple (`local-path`) suffit.

## Orchestrateur

```bash
bench/lima/run-phases.sh up             # crée disques bruts + VMs, gate vd* présents
bench/lima/run-phases.sh bootstrap      # bootstrap Ansible + Cilium, gate 3 nœuds Ready
bench/lima/run-phases.sh storage-simple # local-path-provisioner (rapide), gate PVC Bound
bench/lima/run-phases.sh ceph           # Rook-Ceph (metadataDevice=vde), gate HEALTH_OK
bench/lima/run-phases.sh sc             # StorageClasses Ceph, gate PVC Bound
bench/lima/run-phases.sh datalake       # CephObjectStore RGW (cible S3 Barman), gate Ready
bench/lima/run-phases.sh smoke-s3       # smoke S3 PUT/GET/DELETE sur le RGW Ceph (scénario 06)
bench/lima/run-phases.sh wordpress      # montage WordPress : PVC bloc RWO Ceph Bound + Pod Ready
bench/lima/run-phases.sh hardening      # durcissement hôte (secure.yml, tags audit,detection — #240)
bench/lima/run-phases.sh dataops        # chaîne DataOps via Ansible (dataops.yaml) + lineage
bench/lima/run-phases.sh monitoring     # observabilité (Prometheus + Grafana + Loki)
bench/lima/run-phases.sh kubeconfig     # (ré)exporte le kubeconfig banc
bench/lima/run-phases.sh status         # état du banc : VMs, nœuds, phases, UIs, dernier run
bench/lima/run-phases.sh down           # détruit VMs + disques nommés
```

### Chemins d'installation nommés (ADR 0045)

Quatre chemins, chacun avec une **intention de preuve distincte** (l'agrégat
`all` est supprimé) :

```bash
bench/lima/run-phases.sh socle           # up → bootstrap → stockage (smoke rapide)
bench/lima/run-phases.sh atlas           # léger : socle → monitoring → gitops → dataops (banc atlas)
bench/lima/run-phases.sh storage-real    # Ceph : socle → datalake → smoke S3 + WordPress (stockage réel)
bench/lima/run-phases.sh cluster-dataops # Ceph : socle → datalake → monitoring → dataops (DataOps sur Ceph)
```

**Axe orthogonal durcissement (`WITH_HARDENING=1`, #240).** Combinable avec
n'importe quel chemin : insère la phase `hardening` après le socle (applique
`bootstrap/security/secure.yml`, tags `audit,detection` par défaut —
surchargeables par `HARDENING_TAGS`). Débloque les scénarios 10–16
(durcissement, fail2ban) qui _skippent_ sinon. Le run consigné porte alors le
suffixe `+hardening`. Surcharge locale possible via `bootstrap/security/.env`.

```bash
WITH_HARDENING=1 bench/lima/run-phases.sh storage-real   # banc Ceph durci (audit + fail2ban)
HARDENING_TAGS=audit,detection,smart WITH_HARDENING=1 bench/lima/run-phases.sh atlas
```

## Métrologie, cache & fraîcheur des runs

- **Historique des runs** (`runs-history.yaml`, versionné) : un run de chemin
  complété y **append** une entrée datée (id, date ISO UTC, branche, commit,
  profil, topologie, arch, hôte, durées par phase). C'est la **preuve datée**
  qu'exploite le garde-fou de fraîcheur
  ([ADR 0042](/cluster/docs/decisions/0042-fraicheur-preuves-banc/)) — la date
  vit dans le **contenu** (le checkout CI ne préserve pas le mtime).
  L'auto-consignation bash (`metrology.sh`) a été **retirée** (ADR 0101) ;
  l'append Python reste à câbler (STUB `record`), donc aujourd'hui l'entrée est
  ajoutée par un commit `chore(bench)`. La **lecture** des runs (fraîcheur,
  métriques) vit en Python (`nestor/history.py`, `nestor/metrics.py`).
- **Métriques de coût** (si `monitoring` déployé) : l'entrée peut porter un bloc
  `metriques` échantillonné depuis **Prometheus** sur la fenêtre du run —
  `cpu_core_s` (cumul CPU×temps), `ram_peak_mib`, `ram_mean_mib`. Best-effort :
  `?` si Prometheus est absent (banc rapide).
- **Cache du socle** (`#219`) : un run de chemin **saute**
  `up`+`bootstrap`(+`ceph`+`sc`) si le socle en cache est encore valable — VMs
  up, cluster Ready, **et contenu inchangé** (clé `socle:<profil>:<hash>` sur
  les rôles/manifestes/versions). Tout changement du socle invalide le cache.
  **`NO_CACHE=1` force le rebuild from-scratch** — c'est lui qui produit la
  **preuve**
  ([ADR 0034](/cluster/docs/decisions/0034-validation-e2e-from-scratch/)), le
  cache n'étant qu'un accélérateur d'itération.
- **Fraîcheur** : `nestor artifact check-freshness` (porté en Python, ADR 0101 —
  ex `check-freshness.sh` ; seuil `--seuil-jours`, défaut 7) lit la date du
  dernier run par chemin et sort en échec si un chemin obligatoire est périmé.
  Le workflow cron `.github/workflows/bench-freshness.yml` l'exécute 1×/jour et
  ouvre une issue de rappel — **non bloquant** pour les PR (ADR 0042).

```bash
NO_CACHE=1 bench/lima/run-phases.sh storage-real      # run-preuve from-scratch (ADR 0034)
bench/lima/run-phases.sh status                       # dont le dernier run consigné
nestor artifact check-freshness                       # garde-fou fraîcheur (local)
```

## Run DataOps complet (validation #173)

Valide la chaîne DataOps **portée en Ansible** (`bootstrap/dataops.yaml`,
ADR 0033) de bout en bout, sur le banc en **mode Ceph** (le RGW est la cible S3
des backups Barman) — c'est le chemin nommé `cluster-dataops` (ADR 0045) :

```bash
bench/lima/run-phases.sh cluster-dataops   # socle Ceph → datalake → monitoring →
                                          # dataops (CNPG → Dagster → Marquez + lineage)
```

Le playbook pilote l'API **depuis l'hôte** (`dataops_k8s_host=localhost`, via le
kubeconfig banc) et installe la lib Python `kubernetes` en pré-tâche.

**Critères de succès** (chaque phase est gated — `die` sinon) :

| Étape        | Gate                                                            |
| ------------ | --------------------------------------------------------------- |
| `datalake`   | Deployment `rook-ceph-rgw-datalake-a` Ready                     |
| registry     | Deployment `registry` Ready ; containerd `use_local_image_pull` |
| cert-manager | Deployment `cert-manager-webhook` Ready                         |
| CNPG         | Cluster `pg` phase « Cluster in healthy state » (≤ 600 s)       |
| build images | 3 images poussées sur `registry:80` (skip si déjà présentes)    |
| Dagster      | `dagster-dagster-webserver` ET `dagster-daemon` Ready           |
| Marquez      | `marquez` ET `marquez-web` Ready (migration Flyway)             |
| **lineage**  | un run Dagster réel → événement OpenLineage ingéré par Marquez  |

> Consigner le run dans [`RESULTS.md`](/cluster/bench/lima/RESULTS/) (honnêteté
> des Runs, ADR 0023) — succès **et** drifts éventuels.

Chaque phase est **gated** (s'arrête si le critère n'est pas atteint) et
**idempotente** (rejouable). Le kubeconfig est exporté sous
`.kubeconfigs/banc.config` (le banc EST la stack `banc`, ADR 0102 volet B ;
in-repo gitignoré), avec le `server:` réécrit sur le forward `127.0.0.1:6443` du
control-plane :

```bash
KUBECONFIG=.kubeconfigs/banc.config kubectl get nodes -o wide
KUBECONFIG=.kubeconfigs/banc.config kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status
```

## Réserves transversales

- **Architecture arm64** (Apple Silicon) ≠ **x86_64** des serveurs : on valide
  la _logique_ (rôles, manifestes, ordres), pas les artefacts binaires x86_64.
  Les images Ceph épinglées par digest amd64 sont **dé-épinglées** (retombée sur
  le tag multi-arch) côté banc UNIQUEMENT — le livrable garde ses digests
  intacts.
- **Fonctionnel, pas perfs** : VMs modestes, disques virtuels petits.
- **`os-upgrade` n'est PAS rejoué** : l'image `_images/debian-13` de Lima est
  fraîche. C'est une divergence **assumée** — ne pas la « corriger ».
- **Couverture** : up → bootstrap → stockage (simple par défaut, Ceph en
  option). Les workloads applicatifs (WordPress/datalake) et l'etcd-backup ne
  sont pas encore portés sur ce banc (cf.
  [matrice du catalogue](/cluster/docs/architecture/matrice-catalogue/)).
- **`local-path`** : stockage `WaitForFirstConsumer` sur disque local du nœud
  (pas de réplication, pas de bascule) — suffisant pour des PVC simples, mais le
  stockage **résilient** (réplication ×3, RWX, objet S3) se valide en mode Ceph.

## Nettoyage

```bash
bench/lima/run-phases.sh down   # détruit ce banc (VMs + disques nommés)
```

## Résultats de validation

Déroulé réel du banc (de bout en bout : up → bootstrap → ceph `HEALTH_OK` → sc
PVC Bound) et drifts rencontrés (honnêteté des Runs, ADR 0023) :
[`RESULTS.md`](/cluster/bench/lima/RESULTS/).

## Architecture interne

- [`run-phases.sh`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/run-phases.sh)
  : orchestrateur, table de nœuds + phases gated.
- [`lib.sh`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/lib.sh)
  : bibliothèque d'orchestration Lima ↔ Ansible (`lima_disk_create`,
  `lima_render_node`, `lima_start_node`, `write_inventory`,
  `bootstrap_node_sequence`, `run_cni`, `fetch_kubeconfig_node`). **Sourcée
  aussi par les spikes** qui montent des clusters Lima (ex.
  [`../spikes/clustermesh-latency/`](/cluster/bench/spikes/clustermesh-latency/))
  — source unique, pas de duplication.
- [`profiles/node.yaml.tmpl`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/profiles/node.yaml.tmpl)
  : template de VM Lima (Debian 13, user-v2, provision noyau K8s), rendu par
  `lima_render_node`.
