# Matrice du catalogue

Le dépôt est un **catalogue de topologies** (ADR 0023) : plusieurs combinaisons
d'infrastructure coexistent, **une seule est activée** par déploiement. Cette
page recense les **axes** du catalogue, la **couverture des scénarios** (quelle
épreuve porte sur quelles dimensions) et la **couverture build** (quelles
combinaisons ont réellement été montées sur banc).

> Les **décisions** détaillées vivent dans les [ADR](../decisions/) ; les
> **historiques de Runs** dans
> [`test/lima/RESULTS.md`](../../test/lima/RESULTS.md) et
> [`test/RESULTS.md`](../../test/RESULTS.md) (honnêteté des Runs, ADR 0023).
> Cette page est une **carte de lecture**, pas une source de vérité : en cas
> d'écart, les RESULTS.md font foi.

## 1. Les cinq axes de construction

Une configuration de banc = un point du produit **matériel × topologie × terrain
× provisioning × briques**.

### 1.1 Matériel

- Architectures : x86_64, arm64
- Stockage : NVMe, HDD

### 1.2 Topologie — le _quoi_ : forme du cluster

- k8s HA multi-sites
- k8s HA
- k8s mono-nœud

### 1.3 Terrain d'exécution — où tourne le cluster

- Bare-metal : 4 serveurs lames
- Cloud / IaaS : 1 VM cloud
- Local : machine de dev

### 1.4 Provisioning local — outil qui monte le cluster local

- VM : Lima, Vagrant, VirtualBox
- Conteneurs : kind, k3d

> kind/k3d figent la version de Kubernetes hors du chemin `kubeadm` de prod : le
> banc retenu est **Lima** (vrai kubeadm 1.34), cf.
> [ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md). Le
> choix d'un banc selon **fidélité vs vitesse** (profils Ceph / local-path) est
> cadré par [ADR 0035](../decisions/0035-strategie-bancs-fidelite-vitesse.md).

### 1.5 Briques déployées — le _comment_ : ce qu'on installe dessus

- Socle : k8s, Cilium
- Stockage : Rook-Ceph / Longhorn / local-path
- Observabilité : Prometheus
- DataOps (dont Airflow)
- GitOps · MLOps · AIOps
- IaaS : OpenStack
- Interfaces : CLI, API, WebApp

## 2. Couverture des scénarios (épreuves × axes)

Un scénario n'est pas un axe de construction : c'est une **épreuve** passée à un
banc déjà monté. La table dit, pour chacun, la catégorie, la topologie requise,
les briques validées et le terrain particulier exigé. Source :
[`test/scenarios/`](../../test/scenarios/).

| #   | Scénario                         | Catégorie     | Topologie req. | Briques testées          | Terrain particulier  |
| --- | -------------------------------- | ------------- | -------------- | ------------------------ | -------------------- |
| 01  | RBD block write-read             | stockage      | agnostique     | Rook-Ceph, k8s           | —                    |
| 02  | Pod rescheduling (persistance)   | stockage      | agnostique     | Rook-Ceph, k8s           | —                    |
| 03  | Perte worker + Ceph HEALTH       | résilience    | multi-nœuds    | Rook-Ceph, k8s           | SSH hôte + halt/up   |
| 04  | Perte control plane + snapshot   | résilience    | mono-nœud      | etcd, k8s                | SSH hôte + halt/up   |
| 05  | Bump réplication pool            | stockage      | multi-nœuds    | Rook-Ceph                | —                    |
| 06  | Object store (RGW) smoke         | stockage      | agnostique     | Rook-Ceph, k8s           | —                    |
| 07  | Connectivité Cilium              | réseau        | agnostique     | Cilium, k8s              | —                    |
| 08  | Audit requests/limits            | observabilité | agnostique     | Rook-Ceph, k8s           | —                    |
| 09  | Restore snapshot etcd            | résilience    | mono-nœud      | etcd                     | SSH hôte + etcdctl   |
| 10  | Pod Security Admission           | sécurité      | agnostique     | PSA, k8s                 | —                    |
| 11  | NetworkPolicy default-deny       | sécurité      | agnostique     | Cilium, NetworkPolicy    | —                    |
| 12  | securityContext runtime          | sécurité      | agnostique     | k8s, securityContext     | —                    |
| 13  | Durcissement host/node           | sécurité      | agnostique     | host-hardening           | SSH hôte + state.sh  |
| 14  | Chiffrement Cilium + Hubble      | sécurité      | multi-nœuds    | Cilium, WireGuard        | —                    |
| 15  | Chiffrement at-rest etcd + audit | sécurité      | mono-nœud      | etcd, PSA                | SSH hôte + etcdctl   |
| 16  | Brute-force SSH → fail2ban       | sécurité      | agnostique     | host-hardening, fail2ban | SSH hôte             |
| 17  | Évasion pod → PSA rejette        | sécurité      | agnostique     | PSA, k8s                 | offensif (BANC=1)    |
| 18  | Exfiltration → NetworkPolicy     | sécurité      | agnostique     | Cilium, NetworkPolicy    | offensif (BANC=1)    |
| 19  | Chaos perte paquets/partition    | chaos         | multi-nœuds    | Cilium, Rook-Ceph, k8s   | tc netem (VM réelle) |
| 20  | Chaos kill pods                  | chaos         | agnostique     | k8s, Rook-Ceph           | offensif (BANC=1)    |
| 21  | Chaos saturation CPU/mém         | chaos         | agnostique     | k8s, resource limits     | offensif (BANC=1)    |
| 22  | Alerte détecteurs → Mailpit      | observabilité | agnostique     | host-hardening, Mailpit  | SSH hôte             |
| 23  | Marquez OpenLineage              | dataops       | agnostique     | DataOps, CNPG, Dagster   | API Marquez          |

## 3. Couverture build (combinaisons réellement montées sur banc)

Quelles combinaisons d'axes ont effectivement tourné. Topologies nommées selon
l'[ADR 0030](../decisions/0030-nomenclature-bancs-topologies.md). Source de
vérité : [`test/lima/RESULTS.md`](../../test/lima/RESULTS.md) et
[`test/RESULTS.md`](../../test/RESULTS.md).

| Topologie      | Mat.  | Terrain | Provisioning | Briques validées                                                  | Run      |
| -------------- | ----- | ------- | ------------ | ----------------------------------------------------------------- | -------- |
| `multi-node-3` | arm64 | local   | Lima         | k8s 1.34, Cilium+WireGuard, local-path, Rook-Ceph (HEALTH_OK), SC | 04/06    |
| `multi-node-3` | arm64 | local   | Lima         | + DataOps : CNPG/PG18, Dagster (SUCCESS), Marquez (mode rapide)   | 04→07/06 |
| `multi-node-3` | arm64 | local   | Vagrant      | k8s 1.34, Cilium ; Rook-Ceph + SC + datalake                      | 28→31/05 |

### Trous de la matrice (jamais buildés)

- **Matériel** : x86_64 (tout l'existant est arm64).
- **Topologie** : HA réelle (multi-CP, `ha-3cp`), multi-sites (`multisite`).
- **Terrain** : bare-metal (serveurs lames), cloud — terrain **cloud ARM** cadré
  pour combler `ha-3cp`/`multisite`
  ([ADR 0031](../decisions/0031-terrain-cloud-arm.md)).

> Tout build à ce jour = **arm64 / local / mono-CP-3-nœuds**. C'est le seul coin
> de la matrice couvert.

## Suite

- Croiser ces axes en une table normalisée (matrice catalogue) et nommer
  bancs/topologies.
- Cadrer le terrain cloud.
