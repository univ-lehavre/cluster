# Plan d'implémentation — Rollback par phase sur le banc (ADR 0054)

Met en œuvre [ADR 0054](../decisions/0054-rollback-par-phase-banc.md) : un
rollback **par phase**, symétrique du montage, destructif total, banc jetable.
Ce plan est le **comment** ; la décision (le **pourquoi**) est dans l'ADR.

## Principe d'architecture

Un dispatch `rollback <phase>` dans `test/lima/run-phases.sh`, symétrique du
dispatch de montage. Chaque phase a une **fonction de rollback** qui efface son
périmètre déclaré. Au plus près du style existant (`phase_*`, `vm_sh`, helpers
`KUBECTL`), garde `BANC_JETABLE=1` (comme `phase_bootstrap_fault`).

```bash
# Symétrie :
test/lima/run-phases.sh ceph              # monte
BANC_JETABLE=1 test/lima/run-phases.sh rollback ceph   # défait (destructif)
```

## Primitives partagées (à écrire une fois)

Dans `test/lima/lib.sh` (ou un `rollback-lib.sh` dédié) :

- `k8s_force_delete_ns NS…` — `kubectl delete ns NS --wait=false` puis, si
  bloqué sur finalizers, patch `metadata.finalizers=null` sur le ns ET les
  ressources coincées (OBC, CR Rook/CNPG). Robuste aux deadlocks (RUNBOOK Ceph).
- `k8s_delete_crd GROUP…` — supprime les CRD d'un groupe API (ex.
  `*.ceph.rook.io`), ce qui GC les CR restants. Après les namespaces.
- `k8s_delete_pvc_all` / ciblé par ns — PVC + PV liés (reclaim).
- `rollback_guard` — exige `BANC_JETABLE=1` + cible banc (KUBECONFIG_LOCAL),
  refuse sinon (calqué sur le garde de `phase_bootstrap_fault`).
- Fonctions PURES testables bats si logique non triviale (ex. parser l'ordre des
  phases, classer un état « propre / résidu ») — ADR 0017.

## Table de périmètre par phase (le cœur)

Générique (ADR 0023) ; valeurs d'exemple banc. À garder en phase avec ce que
chaque rôle crée (sinon résidu).

| Phase            | Namespaces                              | CRD (groupes)                                            | PVC                 | Node-side                                    | Dépend de (ordre inverse)     |
| ---------------- | --------------------------------------- | -------------------------------------------------------- | ------------------- | -------------------------------------------- | ----------------------------- |
| `metrics-server` | `kube-system` (deploy ciblé, PAS le ns) | —                                                        | —                   | —                                            | —                             |
| `sc`             | —                                       | StorageClass + CephBlockPool/Filesystem (`ceph.rook.io`) | —                   | —                                            | `ceph`                        |
| `datalake`       | `rook-ceph` (OBC/store)                 | CephObjectStore (`ceph.rook.io`)                         | OBC/buckets         | —                                            | `ceph`                        |
| `ceph`           | `rook-ceph`                             | `*.ceph.rook.io` (crds.yaml)                             | toutes PVC bloc/fs  | disques `vd*` + `/var/lib/rook` (cleanup.sh) | `sc`, `datalake`, `wordpress` |
| `monitoring`     | `monitoring`                            | `monitoring.coreos.com`                                  | PVC Prometheus/Loki | —                                            | —                             |
| `dataops`        | `postgres`, `dagster`, `marquez`        | `postgresql.cnpg.io`                                     | PVC CNPG            | —                                            | —                             |
| `gitops`         | `argocd`, `gitea`                       | `argoproj.io`                                            | PVC gitea           | —                                            | `gitops-seed`                 |
| `gitops-seed`    | (données dans gitea)                    | —                                                        | —                   | —                                            | —                             |

> Les phases avec **node-side** (Ceph) sont les seules à exiger un nettoyage
> hors Kubernetes — le `delete ns` ne touche pas les disques. cleanup.sh (ADR
> 0049 : wipe destructif conscient) s'en charge, par `vm_sh` sur chaque nœud.

## Garde-fou d'ordre (règle 4 ADR 0054)

`rollback ceph` doit refuser (ou avertir+exiger `--force`) si `sc`/`datalake`/
`wordpress` sont encore présents (CRD/CR détectés). Réutiliser les prédicats de
présence du healthcheck (`health-classify.sh` / `phase_status`) pour détecter
les phases aval.

## Preuve (ADR 0034/0052)

Pour chaque phase, un **cycle prouvé sur banc** :
`monte → rollback → état propre vérifié → remonte (changed≥1, ré-installe bien)`.

- « État propre » = un prédicat (réutiliser `state.sh`/healthcheck) qui confirme
  **zéro trace** : ns absent, CRD absents, PVC absentes, disques propres
  (`lsblk` node-side pour Ceph).
- Consigner dans `test/lima/RESULTS.md` (un cycle par phase). La phase Ceph est
  le **pilote** (la plus complexe : CRD + CR + OSD + disques + finalizers) — la
  prouver d'abord, puis décliner aux autres.

## Découpage en lots (issues)

1. **Socle** : primitives partagées (`k8s_force_delete_ns`, `k8s_delete_crd`,
   `rollback_guard`) + dispatch `rollback <phase>` + garde `BANC_JETABLE=1`.
2. **Pilote Ceph** : `rollback ceph` (ns + CRD + finalizers + disques node-side
   via cleanup.sh) + cycle prouvé + RESULTS.
3. **Phases stockage** : `rollback sc`, `rollback datalake` (ordre vs ceph).
4. **Phases plateforme** : `rollback monitoring`, `rollback dataops`,
   `rollback gitops`, `rollback gitops-seed`, `rollback metrics-server`.
5. **Garde-fou d'ordre** + détection des phases aval (réutilise le healthcheck).
6. **Doc** : `docs/outils.md` (catalogue : `rollback <phase>`) + RUNBOOK.

## Validation

`pnpm lint` (shellcheck, ansible-lint si playbooks, bats pour les fonctions
pures), `pnpm docs:build`, markdownlint. Conventional Commits, `BANC_JETABLE`
jamais contourné. Un lot = une PR, re-prouvée par cycle banc avant le suivant.

## Suivi (ADR 0057)

Issue de pilotage : [#274](https://github.com/univ-lehavre/cluster/issues/274).

| Lot                                   | État                                                                                                          |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| 1. Socle (primitives + dispatch)      | ✅ fait — `test/lima/rollback-lib.sh`, dispatch `run-phases.sh`, `test/unit/rollback.bats` (commit `c6d2bd9`) |
| 2. Pilote Ceph                        | ✅ fait — `phase_rollback ceph` + node-side `cleanup.sh` (commit `236815f`)                                   |
| 3. Phases stockage (`sc`, `datalake`) | ✅ fait — couvertes par `rollback-lib.sh`                                                                     |
| 4. Phases plateforme                  | ✅ fait — `monitoring`/`dataops`/`gitops`/`gitops-seed`/`metrics-server`                                      |
| 5. Garde-fou d'ordre aval             | ✅ fait — `classify_downstream_block`                                                                         |
| 6. Doc (`docs/outils.md` + RUNBOOK)   | 🔲 reste — catalogue `rollback <phase>` non encore documenté                                                  |
| Preuve par cycle banc (`RESULTS.md`)  | 🔲 reste — cycle monte→rollback→remonte par phase non consigné (ADR 0034/0052)                                |

**Achèvement** : lots 1-5 livrés sur `main` ; restent le lot 6 (doc) et la
consignation des cycles de preuve. Fermer #274 une fois ces deux derniers faits.
