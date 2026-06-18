# Matrice du catalogue

Le dépôt est un **catalogue de topologies** (ADR 0023) : plusieurs combinaisons
d'infrastructure coexistent, **une seule est activée** par déploiement. Cette
page recense les **axes** du catalogue, la **couverture des scénarios** (quelle
épreuve porte sur quelles dimensions) et la **couverture build** (quelles
combinaisons ont réellement été montées sur banc).

> Les **décisions** détaillées vivent dans les [ADR](../decisions/) ; les
> **historiques de Runs** dans
> [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md) et
> [`bench/RESULTS.md`](../../bench/RESULTS.md) (honnêteté des Runs, ADR 0023).
> Cette page est une **carte de lecture**, pas une source de vérité : en cas
> d'écart, les RESULTS.md font foi.

## 1. Les quatre axes de construction

Une configuration de banc = un point du produit **matériel × topologie × terrain
× briques**.

> **Pourquoi quatre et non cinq.** Le « provisioning » n'est plus un axe : en
> local il se réduit à **Lima** (Vagrant/VirtualBox dépréciés, kind abandonné,
> k3d jamais retenu — [ADR 0038](../decisions/0038-lima-seul-banc-local.md)). Un
> axe à une seule valeur n'en est pas un. Le provisioner devient un **attribut
> dérivé du terrain** (§1.3), pas une dimension à croiser.
>
> **Codes des axes**
> ([ADR 0039](../decisions/0039-nomenclature-axes-catalogue.md)). Chaque valeur
> d'axe a un code stable, ce qui permet de désigner une combinaison par un tuple
> **`arch/terrain/topologie/profil`** — ex. le banc Ceph =
> `arm64/local/multi-node-3/dataops`. Les codes sont donnés dans chaque
> sous-section ci-dessous.

### 1.1 Matériel

Le matériel n'est pas qu'« arch + type de disque » : plusieurs sous-dimensions
**portent des décisions du dépôt** (et certaines ont déjà cassé un run).

- **Architecture CPU** (codes
  [ADR 0039](../decisions/0039-nomenclature-axes-catalogue.md)) : **`arm64`**
  (tout l'existant) · `x86` (x86_64, cible).
- **CPU (cœurs)** : pèse sur le **build** (`dataops` est dominé par le build
  d'images arm64). Banc actuel = **2 vCPU/nœud**.
- **RAM par nœud** : dimension **éprouvée** — le drift L28 (OOM de `marquez-web`
  à 5 GiB) a imposé **8 GiB/nœud** sur le banc. Cité dans nombre d'ADR.
- **Réseau (NIC / débit)** : 1 GbE · 2.5 GbE · **10 GbE** (cible prod, cf.
  stockage). Ceph y est très sensible (réplication, recovery) ; la **séparation
  réseau public ↔ cluster Ceph** est une sous-dimension à part entière. Sur le
  banc local, c'est le réseau virtuel de l'hyperviseur (non représentatif).
- **Topologie de disques** (type **et** rôle, pas seulement le média) :
  - **HDD** : données d'objets OSD (capacité) ;
  - **NVMe/SSD** : **métadonnées Ceph** de l'OSD (`metadataDevice`) — la couche
    BlueStore rapide : `block.db` RocksDB (index des objets, omaps) **et** WAL.
    Les HDD portent les données, le NVMe porte les métadonnées
    ([ADR 0008](../decisions/0008-metadatadevice-nvme-spof-par-noeud.md) ;
    hyperconvergence
    [ADR 0007](../decisions/0007-hyperconvergence-control-plane-osd.md)). Un
    `metadataDevice` NVMe par nœud = **SPOF par nœud assumé** (sa perte invalide
    tous les OSD du nœud).
  - Banc = 3× HDD data + 1× NVMe métadonnées par nœud (disques bruts `vd[b-e]`).

> **Trous matériels connus** : **x86_64**, médias **NVMe réels** (le banc émule
> des disques), **réseau ≥ 2.5 GbE** et séparation public/cluster Ceph,
> **sécurité firmware** (UEFI/Secure Boot/TPM) — cette dernière non traitée par
> le dépôt à ce jour (à cadrer si le durcissement
> [ADR 0014](../decisions/0014-durcissement-kubeadm-init.md) /
> [ADR 0025](../decisions/0025-securite-active-chaos-attaques-controlees.md)
> descend au niveau matériel).
>
> **x86_64 n'est testé QUE sur bare-metal (prod).** Tous les terrains
> d'itération sont arm64 : le local (Mac, Lima) **et** le cloud (Oracle Ampere —
> le Free Tier x86 est inexploitable). Émuler x86 en local est exclu (QEMU
> ~5–10× plus lent → gates en timeout ; Rosetta = binaires x86 sur **kernel
> arm**, non fidèle). x86 n'est donc validé qu'en
> **`x86/baremetal/multi-node-4`** (cible prod, ADR 0009) — un **angle mort**
> des bancs d'itération, mitigé par un chemin strictement identique arm64/x86
> ([ADR 0040](../decisions/0040-terrains-x-topologies.md)).

### 1.2 Topologie — le _quoi_ : forme du cluster

Deux sous-dimensions **indépendantes** — les confondre masque la combinaison
réellement buildée (multi-nœuds **sans** HA du control plane) :

- **HA du control plane** : **1 CP** (SPOF assumé,
  [ADR 0002](../decisions/0002-control-plane-unique-avec-endpoint.md)) · **≥3
  CP** (quorum etcd, haute disponibilité). C'est la dimension qui dit si le plan
  de contrôle survit à la perte d'un nœud (scénario 04).
- **Répartition des nœuds** : mono-nœud · multi-nœuds · multi-sites.

Topologies nommées
([ADR 0030](../decisions/0030-nomenclature-bancs-topologies.md)) qui croisent
ces deux sous-dimensions :

| Nom            | Control plane  | Nœuds                           | Rôle / terrain ([ADR 0040](../decisions/0040-terrains-x-topologies.md))   | État         |
| -------------- | -------------- | ------------------------------- | ------------------------------------------------------------------------- | ------------ |
| `multi-node-3` | **1 CP**       | 3 nœuds (1 CP + 2 workers)      | **référence** — `local` (Lima) **+** cible `cloud` (Oracle, 3 VMs), arm64 | **buildé**   |
| `multi-node-4` | 1 CP           | 4 nœuds (1 CP + 3 workers)      | **prod** — `baremetal` (x86, ADR 0009) ; banc = modèle réduit             | cible (prod) |
| `ha-3cp`       | **≥3 CP (HA)** | 3 control planes                | cible HA — `local` (VIP) ou `cloud` (Load Balancer) ; complexité adaptée  | cible        |
| `multisite`    | ≥3 CP (HA)     | plusieurs sites, 1 cluster/site | cible **étirée** — si ressources suffisantes                              | cible        |

> **Le banc de référence (`multi-node-3`) est multi-nœuds mais _pas_ HA control
> plane** : un seul CP, SPOF assumé (ADR 0002). La HA réelle (`ha-3cp`) est une
> **cible** : le prérequis manquant est un **endpoint flottant** (VIP en local /
> Load Balancer Free Tier en cloud) devant les 3 CP — d'où le scénario 04 (perte
> du CP) qui éprouvera vraiment la HA une fois `ha-3cp` monté.
>
> **Stratégie terrains × topologies**
> ([ADR 0040](../decisions/0040-terrains-x-topologies.md)) : `multi-node-3` est
> la topologie d'**itération arm64**, sur `local` (Lima, référence) **et**
> `cloud` (Oracle, 3 VMs du pool Free Tier). `ha-3cp`/`multisite` sont des
> cibles à **complexité adaptée aux ressources** (paliers de RAM allouée, ADR
> 0040). Seul `baremetal` porte `multi-node-4` **en x86** (cible **prod**,
> ADR 0009) : **x86 n'est validé qu'en prod** — angle mort des bancs d'itération
> (tous arm64). Le banc `multi-node-3` est le **modèle réduit fidèle** de la
> prod `multi-node-4`. _(`single-node` retiré du catalogue : trop dégradé — ADR
> 0040.)_

### 1.3 Terrain d'exécution — où tourne le cluster

Le terrain détermine le **provisioner** (attribut, pas axe —
[ADR 0038](../decisions/0038-lima-seul-banc-local.md)) :

| Code        | Terrain                                                                            | Provisioner | État                                                |
| ----------- | ---------------------------------------------------------------------------------- | ----------- | --------------------------------------------------- |
| `local`     | machine de dev — **Lima** (kubeadm 1.34, même chemin que la prod)                  | Lima        | **utilisé**                                         |
| `cloud`     | IaaS — **OpenTofu** ([ADR 0032](../decisions/0032-opentofu-provisioning-cloud.md)) | OpenTofu    | cible (**arm64**, `multi-node-3` ; 3 VMs Free Tier) |
| `baremetal` | serveurs physiques — manuel / PXE                                                  | manuel/PXE  | cible **prod** (x86, `multi-node-4`)                |

> **Provisioning local = Lima uniquement.** Vagrant/VirtualBox **dépréciés**
> (conservés pour l'historique des Runs, plus maintenus), kind **abandonné**
> (figeait k8s en 1.31,
> [ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)),
> k3d jamais retenu — [ADR 0038](../decisions/0038-lima-seul-banc-local.md). Le
> choix d'un banc selon **fidélité vs vitesse** (profils Ceph / local-path) est
> cadré par [ADR 0035](../decisions/0035-strategie-bancs-fidelite-vitesse.md).

### 1.4 Briques déployées — le _comment_ : ce qu'on installe dessus

- Socle : k8s, Cilium
- Stockage : Rook-Ceph / Longhorn / local-path
- Stockage objet S3 : RGW Ceph (prod) / SeaweedFS (banc léger) — ADR 0036
- Observabilité : Prometheus + Alertmanager + Grafana (métriques) · Loki (logs)
- DataOps : CNPG, Dagster, Marquez, MLflow (dont Airflow envisagé)
- GitOps · MLOps · AIOps — MLOps (côté atlas) : drift Evidently des embeddings
  (run N vs N-1, non bloquant) + entraînement continu (CT, schedule
  `transform_daily`), tous deux loggués dans MLflow (maturité MLOps 1→2)
- IaaS : OpenStack
- Interfaces : CLI, API, WebApp

**Profils de briques** (codes
[ADR 0039](../decisions/0039-nomenclature-axes-catalogue.md)) — combinaisons
**cumulatives** (chaque profil inclut les précédents), alignées sur les paliers
du banc :

| Code      | Contenu (cumulatif)                             | Phase `run-phases.sh`                     |
| --------- | ----------------------------------------------- | ----------------------------------------- |
| `base`    | socle : k8s + Cilium (+WireGuard)               | `bootstrap`                               |
| `store`   | + stockage : local-path **ou** Ceph (+SC, +RGW) | `storage-simple` / `ceph`+`sc`+`datalake` |
| `obs`     | + observabilité : Prometheus + Grafana + Loki   | `monitoring`                              |
| `dataops` | + DataOps : CNPG, Dagster, Marquez, MLflow      | `dataops`                                 |

### 1.5 Dimensions fines paramétrables (à briques fixées)

Au-delà des quatre axes, plusieurs **briques sont paramétrables par topologie**
: une même brique tourne avec un réglage différent selon le banc. Ce sont ces
réglages qui démultiplient les combinaisons à valider — et c'est là que vivent
les drifts spécifiques à un profil (cf. [Leçons des Runs](lecons-des-runs.md),
cat. 7).

| Dimension              | Brique(s)                        | Valeurs testées                                                | Pilotage                       | Réf.                                                              |
| ---------------------- | -------------------------------- | -------------------------------------------------------------- | ------------------------------ | ----------------------------------------------------------------- |
| **storageClass PVC**   | registry, CNPG, monitoring, Loki | **local-path** (léger) · **rook-ceph-block-replicated** (Ceph) | variable de rôle / `WITH_CEPH` | #158                                                              |
| **backing S3**         | Loki, CNPG/Barman                | **SeaweedFS** (léger) · **RGW Ceph** via OBC (prod)            | `loki_s3_backing`, `WITH_CEPH` | #186, [ADR 0036](../decisions/0036-backing-s3-unique-rgw.md)      |
| **profil stockage**    | socle                            | **local-path** (rapide) · **Rook-Ceph** (fidèle)               | `WITH_CEPH`                    | [ADR 0035](../decisions/0035-strategie-bancs-fidelite-vitesse.md) |
| **chiffrement réseau** | Cilium                           | **WireGuard actif**                                            | bootstrap                      | [ADR 0019](../decisions/0019-durcissement-reseau-cilium.md)       |

> **Invariant clé** ([ADR 0036](../decisions/0036-backing-s3-unique-rgw.md)) :
> pour une dimension à deux valeurs dont l'une élargit les droits (ex. creds
> admin SeaweedFS vs creds OBC restreints), la valeur permissive **masque** les
> contraintes de l'autre. Un chemin de code partagé doit donc être validé **sur
> chaque valeur réellement employée** — sinon le banc rapide valide une version
> plus laxiste que la prod.

## 2. Couverture des scénarios (épreuves × axes)

Un scénario n'est pas un axe de construction : c'est une **épreuve** passée à un
banc déjà monté. La table ci-dessous dit ce qu'un scénario **requiert** (sa
catégorie, la topologie et les briques nécessaires, le terrain particulier
exigé) — **pas** s'il a tourné. Le statut d'exécution réel (quoi a été passé,
sur quelle combinaison, quand) est dans le **bloc « Scénarios exécutés »** juste
après la table. Source : [`bench/scenarios/`](../../bench/scenarios/).

> **Miroir machine (ADR 0056 P4).** Cette table a un pendant exécutable :
> `nestor/epreuves.py` (constante `EPREUVES`) la reprend champ par champ pour
> **filtrer** les épreuves jouables selon une `topology.yaml`
> (`topology.py epreuves`). Un test de parité (`tests/test_epreuves.py`) casse
> si le code et le glob `bench/scenarios/NN-*.sh` divergent — la table reste la
> source humaine, le code son miroir testé.

La colonne **Type** distingue la **nature** de l'épreuve :

- **`unit`** — vérifie **une propriété isolée** d'une brique (ex. un PVC se
  monte, une NetworkPolicy bloque, un pod non conforme est rejeté).
- **`intég`** — **test d'intégration de chaîne** : un flux **traverse plusieurs
  briques** bout-en-bout, et c'est le bout du flux qu'on observe (ex. lineage
  Dagster→OpenLineage→Marquez ; log poussé→Loki→S3→relu en LogQL ;
  snapshot→restore→le témoin revient).
- **`chaos`** — intégration **sous panne** : on casse (réseau, nœud, ressources)
  et on vérifie que la chaîne **survit et reconverge**
  ([ADR 0025](../decisions/0025-securite-active-chaos-attaques-controlees.md)).

| #   | Scénario                             | Type      | Catégorie     | Topologie req. | Briques testées                             | Terrain particulier    |
| --- | ------------------------------------ | --------- | ------------- | -------------- | ------------------------------------------- | ---------------------- |
| 01  | RBD block write-read                 | unit      | stockage      | agnostique     | Rook-Ceph, k8s                              | —                      |
| 02  | Pod rescheduling (persistance)       | **intég** | stockage      | agnostique     | Rook-Ceph, k8s                              | —                      |
| 03  | Perte worker + Ceph HEALTH           | chaos     | résilience    | multi-nœuds    | Rook-Ceph, k8s                              | SSH hôte + halt/up     |
| 04  | Perte control plane + snapshot       | chaos     | résilience    | mono-nœud      | etcd, k8s                                   | SSH hôte + halt/up     |
| 05  | Bump réplication pool                | **intég** | stockage      | multi-nœuds    | Rook-Ceph                                   | —                      |
| 06  | Object store (RGW) smoke             | **intég** | stockage      | agnostique     | Rook-Ceph, k8s                              | —                      |
| 07  | Connectivité Cilium                  | unit      | réseau        | agnostique     | Cilium, k8s                                 | —                      |
| 08  | Audit requests/limits                | unit      | observabilité | agnostique     | Rook-Ceph, k8s                              | —                      |
| 09  | Restore snapshot etcd                | **intég** | résilience    | mono-nœud      | etcd                                        | SSH hôte + etcdctl     |
| 10  | Pod Security Admission               | unit      | sécurité      | agnostique     | PSA, k8s                                    | —                      |
| 11  | NetworkPolicy default-deny           | unit      | sécurité      | agnostique     | Cilium, NetworkPolicy                       | —                      |
| 12  | securityContext runtime              | unit      | sécurité      | agnostique     | k8s, securityContext                        | —                      |
| 13  | Durcissement host/node               | unit      | sécurité      | agnostique     | host-hardening                              | SSH hôte + state.sh    |
| 14  | Chiffrement Cilium + Hubble          | unit      | sécurité      | multi-nœuds    | Cilium, WireGuard                           | —                      |
| 15  | Chiffrement at-rest etcd + audit     | **intég** | sécurité      | mono-nœud      | etcd, PSA                                   | SSH hôte + etcdctl     |
| 16  | Brute-force SSH → fail2ban           | **intég** | sécurité      | agnostique     | host-hardening, fail2ban                    | SSH hôte               |
| 17  | Évasion pod → PSA rejette            | unit      | sécurité      | agnostique     | PSA, k8s                                    | offensif (BANC=1)      |
| 18  | Exfiltration → NetworkPolicy         | **intég** | sécurité      | agnostique     | Cilium, NetworkPolicy                       | offensif (BANC=1)      |
| 19  | Chaos perte paquets/partition        | chaos     | chaos         | multi-nœuds    | Cilium, Rook-Ceph, k8s                      | tc netem (VM réelle)   |
| 20  | Chaos kill pods                      | chaos     | chaos         | agnostique     | k8s, Rook-Ceph                              | offensif (BANC=1)      |
| 21  | Chaos saturation CPU/mém             | chaos     | chaos         | agnostique     | k8s, resource limits                        | offensif (BANC=1)      |
| 22  | Alerte détecteurs → Mailpit          | **intég** | observabilité | agnostique     | host-hardening, Mailpit                     | SSH hôte               |
| 23  | Marquez OpenLineage                  | **intég** | dataops       | agnostique     | DataOps, CNPG, Dagster                      | API Marquez            |
| 24  | Prometheus scrape + Grafana up       | **intég** | observabilité | agnostique     | kube-prometheus-stack                       | API Prometheus/Grafana |
| 25  | PrometheusRule → alerte tirée        | **intég** | observabilité | agnostique     | Prometheus, Alertmanager                    | API Prometheus         |
| 26  | Loki : ingest logs + requête LogQL   | **intég** | observabilité | agnostique     | Loki, S3 (SeaweedFS/RGW)                    | API Loki               |
| 27  | GitOps → code-location (déploiement) | **intég** | gitops        | agnostique     | Gitea, Argo CD, Dagster                     | webhook + GraphQL      |
| 28  | UI joignables via le Gateway         | **intég** | gitops        | agnostique     | Gateway Cilium, cert-manager                | SNI/TLS de bordure     |
| 29  | Code-location externe (run e2e)      | **intég** | dataops       | agnostique     | Dagster, code-location gRPC, K8sRunLauncher | GraphQL launchRun      |
| 30  | ha-3cp : survie à 1 panne CP         | chaos     | résilience    | multi-nœuds    | etcd, kube-vip, k8s API                     | SSH + halt CP (VIP)    |
| 31  | Contrat cluster→atlas (endpoints)    | **intég** | gitops        | agnostique     | tous les Services du contrat                | API (TCP/HTTP)         |

> **Tests d'intégration de chaîne (`intég`)** — ce sont eux qui valident que
> **toute une chaîne fonctionne bout-en-bout**, pas seulement qu'elle est montée
> (§3). Les principaux : **23** (chaîne DataOps complète : un run Dagster réel →
> OpenLineage → ingéré dans Marquez, #173/#148) ; **26** (chaîne logs : push →
> Loki → backing S3 → relu en LogQL) ; **09** (sauvegarde etcd réellement
> _restaurable_, pas juste produite). La séquence `run-phases.sh dataops`
> elle-même **est** le test d'intégration de montage de la chaîne DataOps
> (registry → CNPG+Barman → Dagster → Marquez) ; le scénario 23 en revérifie le
> maillon final a posteriori.
>
> **Scénarios 24–26 (observabilité) : écrits et éprouvés (2026-06-08).** La
> stack monitoring/Loki (#158/#186) est désormais **sollicitée par des
> épreuves** réelles, scriptées dans
> [`bench/scenarios/`](../../bench/scenarios/) : Prometheus scrape ses targets
> (22 UP), l'alerte témoin `Watchdog` est bien _firing_, et un log poussé est
> relu en LogQL (round-trip via le backing S3). Passés au vert sur le banc Ceph
> (profil RGW) — _monté **et** éprouvé_.

### Synthèse — unitaire vs intégration, par chaîne fonctionnelle

Lecture transversale : pour chaque **chaîne**, ce qui est couvert en
**unitaire** (propriétés isolées) et en **intégration** (le flux complet
bout-en-bout).

| Chaîne fonctionnelle    | Tests **unitaires**        | Test **d'intégration** (flux e2e)                                 | Couvert ?   |
| ----------------------- | -------------------------- | ----------------------------------------------------------------- | ----------- |
| Stockage bloc (Ceph)    | 01 (PVC RBD)               | 02 (pod→PVC persiste), 05 (rebalance ×3→×5)                       | ✅          |
| Stockage objet (S3/RGW) | —                          | 06 (bucket PUT/GET/DELETE)                                        | ✅          |
| Réseau (Cilium)         | 07 (connectivité), 14 (WG) | 11/18 (NetworkPolicy coupe un flux réel)                          | ✅          |
| Sauvegarde plan ctrl    | —                          | 09 (snapshot etcd → **restore** → témoin revient)                 | ✅          |
| Sécurité admission      | 10, 12, 17 (pods rejetés)  | 16 (brute-force→fail2ban), 22 (détecteur→alerte→Mailpit)          | ✅          |
| **DataOps**             | —                          | **23** (run Dagster → OpenLineage → Marquez) + séquence `dataops` | ✅          |
| **Observabilité métr.** | —                          | **24** (scrape→targets+Grafana), **25** (rule→alerte firing)      | ✅          |
| **Observabilité logs**  | —                          | **26** (push→Loki→S3→LogQL)                                       | ✅          |
| Résilience / chaos      | —                          | 03, 04, 19, 20, 21 (panne → reconvergence)                        | ✅          |
| Sauvegarde **données**  | —                          | _PVC → backup Barman → **restore**_                               | ❌ à écrire |

> **À retenir** : la plupart des chaînes ont leur test d'intégration (`intég`).
> Le **trou** notable est la **restauration des données applicatives** :
> CNPG/Barman sauvegarde bien vers le RGW (monté, #173), mais aucun scénario ne
> prouve encore un cycle **PVC → backup → restore → données retrouvées**
> (l'équivalent du 09 pour les données, pas l'etcd). À écrire — c'est le pendant
> données du « backup restaurable »
> ([ADR 0013](../decisions/0013-sauvegarde-donnees-applicatives.md)).

### Scénarios exécutés (statut réel)

Quels scénarios ont **effectivement tourné**, sur quelle **combinaison**
([tuple ADR 0039](../decisions/0039-nomenclature-axes-catalogue.md)) et avec
quel verdict. Une épreuve **agnostique** vaut pour toute combinaison qui
satisfait ses prérequis ; on consigne ici la combinaison **réellement** utilisée
au dernier passage. `?` = jamais consigné explicitement (script présent, dernier
run non tracé — honnêteté des Runs).

| Scénarios                  | Combinaison (tuple)                                        | Date       | Verdict                                                         |
| -------------------------- | ---------------------------------------------------------- | ---------- | --------------------------------------------------------------- |
| 24, 25, 26 (observabilité) | `arm64/local/multi-node-3/dataops` (banc Ceph, profil RGW) | 2026-06-08 | ✅ vert (22 targets UP ; `Watchdog` firing ; round-trip LogQL)  |
| 23 (lineage Marquez)       | `arm64/local/multi-node-3/dataops`                         | 2026-06-07 | ✅ vert (lineage ingéré, #173)                                  |
| 01–22                      | `?`                                                        | `?`        | scripts présents ; dernier passage non consigné par combinaison |

> **À retenir** : seuls **23–26** ont un statut d'exécution **tracé à une
> combinaison**. Les scénarios 01–22 existent et ont tourné par le passé (cf.
> [`RESULTS.md`](../../bench/lima/RESULTS.md)), mais leur dernier passage n'est
> pas consigné par tuple — les y rattacher est un chantier de traçabilité à
> part. Ne pas lire l'absence de tuple comme « échoué » : c'est « non tracé ici
> ».

## 3. Couverture build (combinaisons réellement montées sur banc)

Quelles combinaisons d'axes ont effectivement tourné. Topologies nommées selon
l'[ADR 0030](../decisions/0030-nomenclature-bancs-topologies.md). Source de
vérité : [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md) et
[`bench/RESULTS.md`](../../bench/RESULTS.md).

Toutes les lignes : topologie `multi-node-3` (1 CP + 2 workers), arch `arm64`,
terrain `local`, provisioner **Lima** (seul banc local,
[ADR 0038](../decisions/0038-lima-seul-banc-local.md)). La vraie variable est le
**profil de briques** et ses dimensions fines. Colonne **Tuple** = notation
[ADR 0039](../decisions/0039-nomenclature-axes-catalogue.md)
(`arch/terrain/topologie/profil`) :

| Tuple                              | storageClass | backing S3 | Briques validées                                                        | Run      |
| ---------------------------------- | ------------ | ---------- | ----------------------------------------------------------------------- | -------- |
| `arm64/local/multi-node-3/base`    | local-path   | —          | k8s 1.34, Cilium+WireGuard, local-path                                  | 04/06    |
| `arm64/local/multi-node-3/obs`     | local-path   | SeaweedFS  | + Prometheus/Grafana/**Loki S3 réel** (#158/#186)                       | 07/06    |
| `arm64/local/multi-node-3/store`   | rook-ceph    | RGW (OBC)  | + Rook-Ceph (HEALTH_OK), SC, RGW datalake                               | 04→07/06 |
| `arm64/local/multi-node-3/dataops` | rook-ceph    | RGW (OBC)  | + **DataOps** : CNPG/PG18 + Barman→RGW, Dagster, Marquez lineage (#173) | 07/06    |
| `arm64/local/multi-node-3/obs`     | rook-ceph    | RGW (OBC)  | + Prometheus/Grafana/**Loki S3 RGW** (#158/#186)                        | 07/06    |

> Toutes les lignes sont sur **Lima** (le banc Vagrant historique 28→31/05 n'est
> plus listé — déprécié, ADR 0038 ; sa trace reste dans
> [`bench/RESULTS.md`](../../bench/RESULTS.md)). Les dimensions fines
> **storageClass** et **backing S3** sont validées sur **leurs deux valeurs**
> (léger local-path/SeaweedFS **et** Ceph rook-ceph/RGW) — c'est l'apport de
> #158/#186.

### Trous de la matrice (jamais buildés)

- **Matériel** : x86_64 (tout l'existant est arm64).
- **Topologie** : HA réelle (multi-CP, `ha-3cp`), multi-sites (`multisite`).
- **Terrain** : bare-metal (serveurs lames), cloud — terrain **cloud ARM** cadré
  pour combler `ha-3cp`/`multisite`
  ([ADR 0031](../decisions/0031-terrain-cloud-arm.md)).

> Tout build à ce jour = **arm64 / local / mono-CP-3-nœuds**. C'est le seul coin
> de la matrice couvert.

## Suite

- **Combler les trous d'axes** : matériel `x86_64`, topologie HA réelle
  (`ha-3cp`) et multi-sites (`multisite`), terrain cloud — cadrés par
  [ADR 0031](../decisions/0031-terrain-cloud-arm.md) /
  [ADR 0032](../decisions/0032-opentofu-provisioning-cloud.md).
- **Tenir cette page à jour** à chaque nouveau coin de matrice monté (réflexe de
  fin de run, au même titre que `RESULTS.md`).
