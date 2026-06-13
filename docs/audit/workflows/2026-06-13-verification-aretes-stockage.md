# 2026-06-13 — Vérification des arêtes de stockage du graphe atomique

| Champ        | Contenu                                                                                                                              |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Date**     | 2026-06-13                                                                                                                           |
| **Type**     | cartographie en éventail + revue adversariale                                                                                        |
| **Fonde**    | [ADR 0066](../../decisions/0066-rollback-atomique-graphe-composants.md) Lot 1 — `roundtrip.py` consomme le graphe                    |
| **Éventail** | 17 agents (16 lecteurs, 1 composant chacun + synthèse adversariale)                                                                  |
| **Verdict**  | **5 arêtes de stockage BLOC manquantes confirmées** (`→ sc`) ; 11 fausses alertes réfutées ; clôture dérivée == ancien `_DEPENDENTS` |

## Pourquoi ce workflow

Le Lot 1 doit faire dériver la clôture de `roundtrip.py` du graphe atomique
(`phase_closure`) au lieu de son `_DEPENDENTS` codé à la main. En préparant la
dérivation, un écart est apparu : la clôture dérivée de `ceph`/`sc` **perdait
`gitops`/`gitops-seed`** que l'ancien `_DEPENDENTS` (validé à la main) incluait.
Le graphe atomique (Lot 0) avait capté les arêtes **S3/datalake** (via
`s3-backing-*`) mais **omis les arêtes de stockage BLOC** : un composant qui
monte un PVC sur la StorageClass `rook-ceph-block-replicated` (produite par
`sc`) dépend de `sc` — détruire `sc` orphelinerait ce PVC.

Avant de corriger le graphe, il fallait **vérifier exhaustivement** quelles
arêtes manquaient, contre le code, sans deviner.

## Synthèse (assainie — valeurs génériques, ADR 0023)

**5 arêtes `→ sc` confirmées**, chacune par un PVC réel sur
`rook-ceph-block-replicated` (fichier:ligne à l'appui) :

| Composant          | Preuve PVC bloc                              | Effet sur la clôture       |
| ------------------ | -------------------------------------------- | -------------------------- |
| `prometheus-stack` | PVC Grafana / Alertmanager / Prometheus      | exhaustivité (déjà via S3) |
| `registry`         | `registry-pvc.yaml.j2`                       | exhaustivité (déjà via S3) |
| `loki`             | `loki_storage_class` (en plus de son OBC S3) | exhaustivité (déjà via S3) |
| `cnpg-cluster-pg`  | `cluster.yaml` `storageClass`                | exhaustivité (déjà via S3) |
| **`gitea`**        | `gitea-pvc.yaml.j2`                          | **load-bearing**           |

L'arête **`gitea → sc` est load-bearing** : c'est la **seule** qui fait entrer
`gitops` (gitea) **et** `gitops-seed` (`gitops-seed → gitea → sc`) dans la
clôture de `sc`/`ceph`. Les quatre autres corrigent l'**exhaustivité** du graphe
(PVC bloc réels que le Lot 0 n'avait pas captés en intension) ; au niveau
projeté sur les phases elles sont redondantes (monitoring/dataops dépendaient
déjà de `sc` transitivement par le chemin S3).

**Closure dérivée == ancien `_DEPENDENTS`**, vérifié après ajout :

- `closure(sc)` → `{datalake, monitoring, gitops, dataops, gitops-seed}` ✅
- `closure(ceph)` → tout ✅

### Fausses alertes réfutées (11)

`ceph` (CephCluster, ne monte aucun PVC bloc — racine), `datalake`
(CephObjectStore RGW, pas de PVC bloc), `dagster`/`marquez` (consommateurs purs
de la base CNPG, pas de PVC propre), `argocd` (volumes
`emptyDir`/`configMap`/`secret` seulement), `cnpg-operator`/`barman-plugin`
(operator/plugin sans stockage), `s3-backing-*` (créent une OBC, pas un PVC
bloc), `seaweedfs` (PVC sur `local-path`, profil léger), `gitops-seed` (aucun
PVC ni OBC ; devient dépendant de `sc` **transitivement** via `gitea`, pas par
une arête directe).

## Ce qui en est sorti

- `component_deps` (`test/lima/rollback-lib.sh`) : **5 arêtes `→ sc`** ajoutées.
- `phase_closure` / `phase_involves_storage` / `phase_of_component` ajoutés à la
  lib (projection du graphe atomique sur les phases) — **source unique**.
- `roundtrip.py` : `_DEPENDENTS`, `_MOUNT_ORDER`, `_STORAGE_LAYERS`
  **supprimés** ; `closure()` / `involves_storage()` **dérivent** désormais de
  la lib (fin de la 2ᵉ source de vérité, ADR 0066 §invariant 3).
- **10 invariants bats** verrouillent la clôture dérivée contre l'ancien
  `_DEPENDENTS` (régression impossible).

> 2ᵉ entrée de la 4ᵉ trace empirique
> ([ADR 0067](../../decisions/0067-workflows-consignes-4e-trace-empirique.md)),
> après
> [la vérification du graphe atomique](2026-06-13-verification-graphe-atomique.md).
