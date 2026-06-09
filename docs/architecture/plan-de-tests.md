# Plan de tests — les trois niveaux

Point d'entrée unique décrivant **ce qui est testé, à quel niveau, et où**.
Trois niveaux complémentaires, du plus rapide/isolé au plus complet/réel
([ADR 0017](../decisions/0017-langage-des-scripts.md) pour le langage,
[ADR 0034](../decisions/0034-validation-e2e-from-scratch.md) pour la doctrine «
la preuve est un run e2e from-scratch »).

| Niveau          | Question posée                                               | Où c'est codé                                                         | Exécution                | Cluster requis |
| --------------- | ------------------------------------------------------------ | --------------------------------------------------------------------- | ------------------------ | -------------- |
| **Unitaire**    | « cette fonction de décision classe-t-elle correctement ? »  | [`test/unit/*.bats`](../../test/unit/)                                | `pnpm test:shell` (bats) | non            |
| **Intégration** | « la couche monte-t-elle et passe-t-elle son gate ? »        | gates dans [`test/lima/run-phases.sh`](../../test/lima/run-phases.sh) | `run-phases.sh <phase>`  | oui (banc)     |
| **Scénario**    | « le cluster résiste-t-il / se comporte-t-il comme prévu ? » | [`test/scenarios/NN-*.sh`](../../test/scenarios/)                     | `run-all.sh`             | oui (banc)     |

> **Pourquoi trois niveaux ?** L'unitaire verrouille la **logique** (rapide,
> sans cluster) ; l'intégration prouve qu'une **couche monte** (gate) ; le
> scénario prouve un **comportement** (résilience, sécurité, chaos,
> observabilité). Un changement validé au lint + unitaire **doit** repasser par
> un run e2e from-scratch avant d'être déclaré validé (ADR 0034).

## Niveau 1 — Tests unitaires (assertions pures, bats)

Logique de décision **isolée** des effets de bord (classification, comptage,
parsing), testable **sans cluster**
([ADR 0017](../decisions/0017-langage-des-scripts.md)). shellcheck valide la
syntaxe ; bats valide le **comportement**.

| Fichier                                                      | Couvre                                                       | `@test` |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ------- |
| [`state-classify.bats`](../../test/unit/state-classify.bats) | classification d'état de `state.sh` (couche bootstrap/hôte)  | 18      |
| [`dataops-assert.bats`](../../test/unit/dataops-assert.bats) | run Dagster + ingest Marquez (couche dataops)                | 16      |
| [`metrology.bats`](../../test/unit/metrology.bats)           | métrologie/historique du banc (harnais)                      | 24      |
| [`gitops-assert.bats`](../../test/unit/gitops-assert.bats)   | statut Argo CD + déclenchement webhook (couche gitops, #231) | 9       |

### Densification visée (couches sans assertion pure)

Plusieurs couches n'ont **que** des gates impératifs, sans fonction de décision
pure extraite ni bats. À densifier (logique testable hors cluster) :

| Couche / domaine   | Logique extractible candidate                                     | Statut                        |
| ------------------ | ----------------------------------------------------------------- | ----------------------------- |
| `gitops` (Argo CD) | classer un statut Argo (`Synced/Healthy` vs dégradé) en ok/ko     | ✅ `classify_argocd_app`      |
| `gitops` (webhook) | détecter qu'un push a déclenché une nouvelle réconciliation       | ✅ `classify_webhook_trigger` |
| stockage (PVC)     | classer une phase de PVC (`Bound`/`Pending`) — aujourd'hui inline | **à créer**                   |
| monitoring         | au-delà de la métrologie : classer un statut de target Prometheus | **à créer**                   |

> Règle (ADR 0045) : **toute nouvelle couche ajoute son gate, et une assertion
> pure si la décision est non triviale.** La densification ci-dessus rattrape la
> dette des couches antérieures à cette règle.

## Niveau 2 — Tests d'intégration (gates de phase)

Chaque phase du harnais [`run-phases.sh`](../../test/lima/run-phases.sh) se
termine par un **gate** bloquant (exit ≠ 0 sinon) sur le cluster réel. Le détail
gate/assertion par couche, et leur regroupement en **chemins d'installation**
(`socle` / `atlas` / `storage-real` / `cluster-dataops`), est décidé par
[ADR 0045](../decisions/0045-chemins-installation-banc-couches.md). Synthèse :

| Couche / phase   | Gate (preuve sur banc)                                                 |
| ---------------- | ---------------------------------------------------------------------- |
| `bootstrap`      | N nœuds **Ready** (Cilium up)                                          |
| `storage-simple` | provisioner Ready + PVC `local-path` **Bound**                         |
| `ceph` / `sc`    | operator Ready + **HEALTH_OK** ; PVC SC Ceph **Bound**                 |
| `datalake`       | **RGW Ready** + **smoke S3 PUT/GET/DELETE** (sc. 06)                   |
| WordPress (Ceph) | PVC bloc **RWO Bound** sur la SC Ceph + **Pod Ready**                  |
| backing S3 léger | SeaweedFS Ready (rôle conditionnel `when` Ceph absent — pas une phase) |
| `monitoring`     | Prometheus + Grafana + Loki **Ready**                                  |
| `gitops`         | `deploy/gitea` + `deploy/argocd-server` **Ready**                      |
| `dataops`        | CNPG sain, Dagster/Marquez Ready, **lineage d'un run réel ingéré**     |

## Niveau 3 — Scénarios (comportement)

26 scénarios numérotés ([`test/scenarios/`](../../test/scenarios/), runner
`run-all.sh`), couvrant résilience, sécurité active, chaos et observabilité. La
**matrice détaillée** (ce que teste chacun + couverture) vit dans
[`test/scenarios/README.md`](../../test/scenarios/README.md). Chaque famille est
**scellée par un chemin d'installation** (ADR 0045 §4/§6) — le chemin qui monte
le banc requis et que le garde-fou de fraîcheur surveille à sa cadence
([ADR 0025](../decisions/0025-securite-active-chaos-attaques-controlees.md),
[ADR 0042](../decisions/0042-fraicheur-preuves-banc.md)) :

| Plage        | Famille                                                                                                                                            | Chemin scellant (§6)             |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| 06           | Smoke S3 (RGW) + montage WordPress (PVC bloc Ceph)                                                                                                 | `storage-real` (30 j)            |
| 01–05, 07–22 | Stockage, résilience, etcd, durcissement, sécu active, chaos                                                                                       | `storage-real` (banc Ceph monté) |
| 23–26        | Intégration DataOps + observabilité                                                                                                                | `cluster-dataops` (90 j)         |
| **27**       | **e2e GitOps → workflows atlas** (push Gitea → Argo CD déploie les workflows → run Dagster + lineage) — implémenté (#231), preuve banc à consigner | `atlas` (7 j)                    |

**Axe durcissement (`WITH_HARDENING=1`, ADR 0045 §3 / #240).** Les scénarios qui
exigent un hôte durci ne passent que si le chemin a été monté avec
`WITH_HARDENING=1` (phase `hardening`, tags `audit,detection`) : **10–15**
(durcissement) et surtout **16** (fail2ban), qui _skippe_ sur un banc non durci.
Sans le flag, ces scénarios restent en skip assumé — la variante durcie est une
preuve distincte (run consigné avec suffixe `+hardening`).

### Scénario 27 — workflows atlas déployés par GitOps

Le scénario qui prouve le **cœur du banc atlas** (ADR
[0044](../decisions/0044-topologie-deploiement-banc-atlas.md)/[0045](../decisions/0045-chemins-installation-banc-couches.md))
: qu'un **push sur Gitea déclenche le déploiement par Argo CD des workflows
`atlas`** sur l'infra DataOps déjà montée (CNPG/Dagster/Marquez par Ansible —
Argo CD **ne déploie pas l'infra**, seulement les workflows). Pré-requis : la
phase `dataops` a posé l'infra (orchestrateurs vides). Étapes (chacune un gate)
:

1. **push** les **workflows atlas** (code-locations / assets Dagster) dans le
   dépôt Gitea ;
2. le **webhook** Gitea → Argo CD déclenche la réconciliation (pas le polling) ;
3. l'`Application` (workflows) atteint **`Synced/Healthy`** ;
4. un **run Dagster réel** s'exécute et **émet du lineage ingéré par Marquez**
   (réutilise la logique de `dataops-assert.bats`).

Le contenu poussé (workflow jouet d'exemple générique) vit dans
[`test/lima/atlas-workflow-sample/`](../../test/lima/atlas-workflow-sample/) ;
l'init du dépôt Gitea est faite par la phase `gitops-seed`
([`test/lima/gitea-init.sh`](../../test/lima/gitea-init.sh)). Implémentation :
[issue #231](https://github.com/univ-lehavre/cluster/issues/231).

## Voir aussi

- [Chemins d'installation (ADR 0045)](../decisions/0045-chemins-installation-banc-couches.md)
  — quelle couche, quel ordre, quels gates par chemin.
- [Matrice des scénarios](../../test/scenarios/README.md) — détail des 26 (+1).
- [Leçons des Runs](lecons-des-runs.md) — synthèse des drifts par campagne.
