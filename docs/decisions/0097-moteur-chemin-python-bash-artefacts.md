# 0097 — Moteur de chemin Python ; bash réduit aux artefacts node-side

## Statut

Proposed (2026-06-25)

S'appuie sur [0096](0096-graphe-topologie-python-verifie-ansible.md) (graphe de
topologie Python figé) — **prérequis** : le moteur de chemin de cet ADR projette
ce graphe pour dériver la séquence et les périmètres. **SUPERSEDE PARTIELLEMENT
[0049](0049-doctrine-choix-outil-par-action.md)** (doctrine du choix d'outil par
action) : la frontière bash/Python **évolue** — le bash d'**orchestration** part
en Python, ne restent **que** les **artefacts node-side** exécutés sans Python.
**Clôt l'inversion amorcée par [0063](0063-ansible-runner-boucle-p5.md)**
(ansible-runner en Python) en supprimant le dernier maillon bash de la boucle de
montage. Cohérent avec [0053](0053-isolation-multi-cible-banc-prod.md) /
[0090](0090-nestor-pilote-la-prod.md) (gardes d'isolation banc/prod, `nestor`
pilote la prod), [0056](0056-modele-declaratif-topologies.md) (modèle déclaratif
des topologies — le paramétrage YAML de §4 en découle) et
[0017](0017-langage-des-scripts.md) (Python testé). Lié à
[0034](0034-validation-e2e-from-scratch.md) /
[0052](0052-reproductibilite-des-resultats.md) (preuve banc, reproductibilité).
Toutes les valeurs ci-dessous sont des exemples génériques
([ADR 0023](0023-plateforme-exemple-generique.md)) : `node1`…`node4`, `banc`,
`local-path`, `ceph`, `KUBECONFIG`.

## Contexte

Aujourd'hui [`bench/lima/run-phases.sh`](../../bench/lima/run-phases.sh) (**1903
lignes**) est l'**orchestrateur** du banc : il **décide quoi monter**,
**enchaîne les `ansible-playbook`**, **gate la santé** via `kubectl`
(`nodes_ready_all`, `ceph_healthy`…), **dérive** les suffixes cibles
(`+hardening`) du réel et **gère l'historique** (`record_full_run`). `nestor`
([`scripts/topology.py`](../../scripts/topology.py), `cmd_up`/`cmd_next`) ne
fait que **l'APPELER en subprocess** (`subprocess([bash, run-phases.sh, …])`).

La **frontière** Python ↔ bash est donc **floue**, et une **circularité
résiduelle** persiste : `run-phases.sh` **rappelle Python** au cœur du montage
(`:508` `bootstrap-seq` → `topology.py`, `:1650` `ha-3cp` → `topology.py`), qui
re-rappelle bash (`ha-cni`). La chaîne réelle est **Python→bash→Python→bash**
sur quatre niveaux. Au total, **21 fichiers bash, ~7000 lignes**.

Le **fil rouge** de l'audit : **Python et bash détiennent chacun une part de la
vérité** — Python sait dériver la séquence (`expected_phase_sequence`,
[`nestor/plan.py`](../../nestor/plan.py) :206), mais bash garde l'**exécution**
du chemin, la **possession de l'état partagé** (`CP`, `API_PORT`,
`KUBECONFIG_LOCAL`) et le **provisioning** (`phase_up`, `write_inventory`).
Cette double-détention est la cause des divergences récurrentes (verdict
`preview` ≠ `next`, signal de santé qui ment) qu'aucun correctif local ne tarit
durablement.

Cette question a été instruite par un **audit** des causes racines puis par un
**workflow de conception multi-agents** (scans du code, classement des 21
fichiers bash, vérifications adversariales, synthèse) qui a tranché la frontière
et établi le **sort de chacun** des 21 scripts.

## Décision

### 1. Moteur de chemin Python — `nestor/path.py`, un seul sens d'appel

On crée [`nestor/path.py`](../../nestor/path.py) : une **boucle Python** qui
**absorbe l'orchestration** de `run-phases.sh`.

- Elle **boucle** sur `expected_phase_sequence`
  ([`nestor/plan.py`](../../nestor/plan.py) :206, **déjà la fonction unique
  partagée** par `cmd_preview`/`cmd_up`/`cmd_next`).
- Elle appelle, par phase, `runner.launch_phase_idempotent`
  ([`nestor/runner.py`](../../nestor/runner.py) :176, **déjà le portage fidèle**
  de `run_ansible_phase` via ansible-runner,
  [ADR 0063](0063-ansible-runner-boucle-p5.md)).
- Elle **gate** la santé via `_wait_layer_healthy`
  ([`scripts/topology.py`](../../scripts/topology.py) :823, dernier-maillon).
- Elle **traverse les gardes d'isolation** `_assert_bench_target` /
  `_assert_inventory_safe` **AVANT CHAQUE phase**.

**La garde d'isolation est un INVARIANT DE BOUCLE, pas un appel unique.**
Aujourd'hui `cmd_up` délègue tout le chemin en **un** subprocess bash et la
garde tourne **une seule fois** avant. Le moteur Python bouclant **par phase**
doit la ré-affirmer **à chaque** itération (et gérer l'échappatoire `KUBECONFIG`
exporté, « intention explicite assumée », `topology.py` :1469) — **sinon un
montage banc avec `KUBECONFIG` prod taperait la prod** (faille
[ADR 0053](0053-isolation-multi-cible-banc-prod.md), réserve §5).

**Un SEUL sens d'appel : Python → bash, JAMAIS l'inverse.** `cmd_up`/`cmd_next`
**n'appellent plus** `subprocess([bash, run-phases.sh])`. La **circularité**
(`bootstrap-seq` :508, `ha-3cp` :1650, qui re-rappellent bash `ha-cni`) **est
supprimée**. Critère mesurable :
`grep -rn 'uv run python\|topology.py' bench/lima/` rend **0** (aujourd'hui :
508 et 1650).

### 2. Frontière — le sort de chacun des 21 scripts bash

L'audit pose explicitement « **Quid des scripts bash ?** ». Réponse : trois
sorts, **table exhaustive** (depuis le classement des 21 fichiers).

#### 2.a GARDÉS EN BASH — artefacts irréductibles, exécutés _sans Python_

| Fichier                                                    | Lignes | Pourquoi irréductible                                                                                                                                                                                                         |
| ---------------------------------------------------------- | -----: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`bootstrap/cni.sh`](../../bootstrap/cni.sh)               |    234 | **Œuf-poule CNI** : Cilium s'installe **dans la VM** entre `kubeadm init` et nœuds-Ready — **fenêtre où aucun kubeconfig hôte n'est joignable** ; purge iptables node-side root. **NE PAS scinder** (doit tourner d'un bloc). |
| [`storage/ceph/cleanup.sh`](../../storage/ceph/cleanup.sh) |     64 | **Wipe disque node-side** : `sgdisk`/`blkdiscard`/`dd`/`partprobe` + `rm /var/lib/rook` + reboot. **Root, contexte VM pré-k8s** : le porter = installer python3 sur chaque VM (absurde).                                      |

Ces deux artefacts sont invoqués via
`subprocess(limactl shell … bash -s < cni.sh)` **comme on applique un
manifeste** : Python **pousse l'artefact**, **consomme un `rc`**, **ne lit
jamais sa logique**.

#### 2.b GARDÉ PAR OPPORTUNITÉ — transport pur (non prioritaire)

Les parties **transport** de [`bench/lima/lib.sh`](../../bench/lima/lib.sh)
(`vm_sh`, `lima_start_node`, `lima_disk_*`, `lima_render_node`, `run_cni`,
`fetch_kubeconfig_node`) sont **extraites** dans `bench/lima/vm.sh` (~250 l.).
Honnêteté : **pas strictement irréductible** (`limactl` a `--json`), mais
**transport pur déjà testé** → portage **gratuit, non prioritaire**
([ADR 0049](0049-doctrine-choix-outil-par-action.md) critère 3 : on ne réécrit
pas le bash qui marche). **RÉSERVE** : `phase_ha_cni` fait **DEUX gestes**
(`run_cni` **PUIS** `fetch_kubeconfig_node`, sed-rewrite de `admin.conf`) — la
façade Python doit **couvrir les deux**, sinon la sous-commande-pont `ha-cni`
reste appelée pour le kubeconfig et la circularité résiduelle subsiste.

#### 2.c PORTÉS EN PYTHON — avec effort, depuis le classement

| Fichier (bash)                                                               | Lignes | Cible Python                                                                    | Effort       |
| ---------------------------------------------------------------------------- | -----: | ------------------------------------------------------------------------------- | ------------ |
| [`bench/lima/run-phases.sh`](../../bench/lima/run-phases.sh)                 |   1903 | `nestor/path.py` (cœur du chantier)                                             | **élevé**    |
| [`bench/lima/rollback-lib.sh`](../../bench/lima/rollback-lib.sh) (pur)       |   ~600 | `nestor/graph.py` ([ADR 0096](0096-graphe-topologie-python-verifie-ansible.md)) | moyen        |
| `rollback-lib.sh` (orch. kubectl/ssh)                                        |   ~150 | subprocess kubectl                                                              | moyen        |
| [`bootstrap/state.sh`](../../bootstrap/state.sh)                             |    868 | orchestration audit (kubectl/ssh)                                               | moyen        |
| [`bootstrap/seed-app-of-apps.sh`](../../bootstrap/seed-app-of-apps.sh)       |    595 | `nestor/seed.py` (garde **prod** `assert_prod_target`)                          | faible→moyen |
| [`bench/lima/gitea-init.sh`](../../bench/lima/gitea-init.sh)                 |    207 | `nestor/seed.py` (garde **banc** `_assert_bench_target`)                        | moyen        |
| [`bench/lima/metrology.sh`](../../bench/lima/metrology.sh) (pur)             |   ~150 | pytest (verdict/parsing)                                                        | faible       |
| `lib.sh` (orch. `lima_*`, `write_inventory`)                                 |   ~230 | provisioning Python                                                             | moyen        |
| [`bootstrap/first-access.sh`](../../bootstrap/first-access.sh)               |    130 | paramiko                                                                        | faible       |
| [`bench/lima/check-freshness.sh`](../../bench/lima/check-freshness.sh)       |    129 | garde-fou Python                                                                | faible       |
| [`bench/lima/access.sh`](../../bench/lima/access.sh)                         |    275 | mixte (port-forward reste subprocess)                                           | faible       |
| [`bench/lima/env.sh`](../../bench/lima/env.sh)                               |    104 | présentation contexte                                                           | faible       |
| [`bootstrap/security/report.sh`](../../bootstrap/security/report.sh)         |    190 | paramiko (lecture seule)                                                        | faible       |
| [`bootstrap/lib/health-classify.sh`](../../bootstrap/lib/health-classify.sh) |    282 | `HealthClassifier` (pytest 1:1)                                                 | faible       |
| [`bootstrap/lib/state-classify.sh`](../../bootstrap/lib/state-classify.sh)   |     91 | pytest 1:1                                                                      | faible       |
| `*-assert.sh` (gitops / dataops / ui / bootstrap-fault)                      |   ~340 | `HealthClassifier` (pytest)                                                     | faible       |
| [`scripts/audit-image-digests.sh`](../../scripts/audit-image-digests.sh)     |     86 | SDK registre Python                                                             | faible       |
| [`bootstrap/lib/ssh-report.sh`](../../bootstrap/lib/ssh-report.sh)           |     40 | paramiko (transport SSH)                                                        | faible       |

**RÉSERVE — des phases « triviales » qui ne le sont PAS.** `phase_dataops`
(`run-phases.sh` :1002) n'est **pas** un simple `run_ansible_phase <playbook>` :
il appelle `dataops_chain_emit_and_verify` (~62 l. : Job émetteur
**OpenLineage**, poll, puis delta **Marquez**) et
`dataops_egress_internet_check` (preuve **NetworkPolicy** egress 443). Ces
harnais de **preuve e2e** ne sont **pas** couverts par `_wait_layer_healthy`
(qui ne teste que le dernier-maillon Ready) : **à porter explicitement**, pas à
supposer trivial.

### 3. Paramétrage 100 % YAML — fin des variables d'environnement éparses

Aujourd'hui **~40 variables d'environnement** paramètrent le montage : côté bash
`CEPH_BLOCK_DEVICE`, `CEPH_HDD_GLOB`, `HA_VIP`, `HA_VIP_IFACE`,
`CILIUM_CLUSTER_*`, `GITEA_ORG_*`, `GITEA_NS`, `EXPECTED_CLUSTER`,
`BANC_JETABLE`, `HARDENING_TAGS`, `ATLAS_REPO_DIR`, `CITATION_*`… ; côté Python
`KUBECONFIG`, `PORTAL_*`, `SEUIL_JOURS`. Un montage dépend donc d'un **env shell
non versionné**.

**Décision** : ces paramètres **remontent dans le YAML de topologie**
(`topologies/*.yaml`, qui porte **déjà** `catalog`/`nodes`/`storage`/`layers`/
`target_kind`/`kubeconfig`). `nestor` **lit la config depuis le YAML**, plus
depuis l'env. **Exception** : le strict nécessaire à la sémantique du shell —
typiquement `KUBECONFIG`, dont la **sémantique d'override** (« intention
explicite assumée », garde §1) **reste assumée et documentée**.

C'est l'application directe du **modèle déclaratif**
([ADR 0056](0056-modele-declaratif-topologies.md)) : **une topologie = UN
fichier YAML auto-suffisant**. Bénéfice double : **reproductibilité**
([ADR 0052](0052-reproductibilite-des-resultats.md) — plus de montage dépendant
d'un env shell non versionné) et **source de paramétrage unique**.

**Conséquence sur les commandes annexes — `nestor env` est SUPPRIMÉE.** Sa seule
fonction était d'imprimer `export KUBECONFIG=<banc>` à `eval` dans le shell :
elle **incarne** le paramétrage-par-variable-d'environnement que cette décision
abolit. À la place, **`nestor` maintient des contextes nommés dans
`~/.kube/config`** (un par topologie : `banc`, `dirqual`…), dérivés du champ
`kubeconfig` du YAML. L'opérateur branche son `kubectl` par le **mécanisme
standard k8s** — `kubectl --context banc …` ou `kubectl config use-context banc`
— **sans aucune variable d'environnement**. C'est cohérent avec
[ADR 0090](0090-nestor-lecture-prod.md) (`nestor` lit le bon cluster depuis la
topologie) et avec le champ `kubeconfig:` déjà présent dans
`topologies/dirqual.yaml`.

Les **autres commandes annexes restent** (leur _implémentation_ peut changer,
pas leur raison d'être) : `access` (URLs/identifiants dev — `access.sh` porté en
Python, §2), `scale` ([ADR 0072](0072-scale-replicas-noeuds.md)), `discover`
([ADR 0074](0074-discover-topology-depuis-cluster.md) — _renforcée_ : « le réel
prime »), `refresh` ([ADR 0076](0076-refresh-topology-voulu.md)), `artifact`,
`test`. Seule `env` disparaît, comme dette directe du zéro-variable-d'env.

### 4. Les DEUX topologies, pilotées par le même moteur depuis leur YAML

Le moteur `path.py` doit gérer **nativement et sans régression** les **deux**
topologies déclarées, en **dérivant la séquence et les gates de CES
déclarations** (le graphe
[ADR 0096](0096-graphe-topologie-python-verifie-ansible.md) est
**backend-conditionnel**) :

- **(a) BANC Lima mono-nœud + local-storage**
  ([`topologies/banc.yaml`](../../topologies/banc.yaml)) : **1 nœud**
  `control`+`worker`, `storage.backend: local-path`, `target_kind: lima`,
  `layers` **sans Ceph** → le graphe dérive `storage-simple`.
- **(b) PRODUCTION 4 nœuds + Ceph**
  ([`topologies/dirqual.yaml`](../../topologies/dirqual.yaml)) : `node1`
  `control`+`worker` + `node2`/`node3`/`node4` `worker`,
  `storage.backend: ceph`, `target_kind: prod`,
  `kubeconfig: ~/.kube/<topologie>.config`, `layers` `ceph`/`sc`/`datalake` **en
  tête** → le graphe dérive le socle Ceph.

Le **même moteur** lit ces deux YAML et en projette la séquence : `local-path` →
`storage-simple` ; `ceph` → `ceph`/`sc`/`datalake`. Chaque lot de migration est
**prouvé sur LES DEUX** : **banc d'abord**
([ADR 0034](0034-validation-e2e-from-scratch.md)), **puis prod**.

## Conséquences

**Un seul sens Python → bash — fin de la circularité.** Le va-et-vient
`Python→bash→Python→bash` (`bootstrap-seq` :508, `ha-3cp` :1650) **disparaît** :
`cmd_up`/`cmd_next` n'appellent plus `run-phases.sh`, et le grep de sens-unique
rend 0. C'est l'aboutissement de l'inversion amorcée par
[ADR 0063](0063-ansible-runner-boucle-p5.md).

**Bash réduit à ~2-3 artefacts node-side + transport.** Restent `cni.sh` et
`cleanup.sh` (irréductibles, §2.a) et le transport `vm.sh` (par opportunité,
§2.b) ; tout le reste est porté en Python testé
([ADR 0017](0017-langage-des-scripts.md)). La doctrine
[ADR 0049](0049-doctrine-choix-outil-par-action.md) est **partiellement
supersédée** : le bash d'orchestration part, ne reste que l'artefact exécuté
sans Python.

**Paramétrage 100 % YAML.** Fin des ~40 variables d'env éparses ; une topologie
est un **fichier YAML auto-suffisant**
([ADR 0056](0056-modele-declaratif-topologies.md)), gain de **reproductibilité**
([ADR 0052](0052-reproductibilite-des-resultats.md)). `KUBECONFIG` reste la
seule exception, sémantique d'override assumée.

**Les deux topologies pilotées par le même moteur.** Banc local-path et prod
Ceph dérivent leur séquence/gates **du même `path.py`**, depuis leur seul YAML —
preuve sur les deux, banc d'abord
([ADR 0034](0034-validation-e2e-from-scratch.md)).

**Risques honnêtes.**

- **Œuf-poule CNI — la circularité EXISTE aujourd'hui.** L'affirmation «
  `cni.sh` reste bash sans circularité » décrit une **CIBLE**, pas le présent :
  le chemin est **circulaire aujourd'hui**
  (`run-phases.sh:508 → bootstrap-seq → run_cni → ha-cni bash`). Elle ne **tient
  qu'APRÈS** le moteur. La façade Python doit couvrir `run_cni` **ET**
  `fetch_kubeconfig_node` (2ᵉ geste de `phase_ha_cni`), sinon `ha-cni` reste
  appelé pour le kubeconfig.
- **État partagé shell → Python sous-estimé.** `path.py` doit **POSSÉDER** `CP`,
  `API_PORT` (=6443), `KUBECONFIG_LOCAL` **et absorber** `phase_up`
  (provisioning VM) + `write_inventory` — chantier **bien plus large** que «
  porter `cni.sh` ». Sinon Python re-rappelle bash pour ces faits et la
  circularité persiste.
- **Ampleur `run-phases.sh` 1903 l. — limite basse optimiste.** `path.py`
  (~400-600 l. **neuf**) + `seed.py` (~800 l.) + démêlage
  `bootstrap-seq`/`ha-cni` ne sont **pas triviaux** ; l'estimation « risque
  faible » vaut pour les ~12 phases plateforme, pas pour les harnais e2e (§2.c).
- **Mono-mainteneur — cadence lente.** Chaque PR exige un **run banc
  from-scratch consigné** ([ADR 0034](0034-validation-e2e-from-scratch.md) /
  [ADR 0052](0052-reproductibilite-des-resultats.md)) + rejeu `changed=0`. Le
  pattern est éprouvé 2× (`bootstrap.py`, `ha.py`) et chaque phase se prouve
  isolément — risque faible, **coût-temps réel non-LOC**.
- **Garde d'isolation = invariant de boucle + échappatoire.**
  `_assert_bench_target`
  - `_assert_inventory_safe` doivent être traversées **à CHAQUE phase**, avec
    gestion de l'échappatoire `KUBECONFIG` — **sinon un montage banc avec
    `KUBECONFIG` prod taperait la prod**
    ([ADR 0053](0053-isolation-multi-cible-banc-prod.md)).

**Mise en œuvre incrémentale, prouvée au banc.** Le moteur est construit **par
lots** : portage à côté du bash, bascule des ponts, puis suppression du
subprocess `run-phases.sh`. Chaque lot est **re-prouvé par un run banc puis
prod** ([ADR 0034](0034-validation-e2e-from-scratch.md) /
[ADR 0052](0052-reproductibilite-des-resultats.md)) — HA traité en **exception
nommée** jusqu'à sa PR dédiée (le grep sens-unique allowliste `ha-cni`
jusque-là).

## Voir aussi

- [ADR 0017](0017-langage-des-scripts.md) — Langage des scripts (bash orchestre
  vs Python testé : la frontière évolue, le bash d'orchestration part en
  pytest).
- [ADR 0023](0023-plateforme-exemple-generique.md) — Valeurs génériques (noms de
  nœuds/topologies/kubeconfig sont des exemples).
- [ADR 0034](0034-validation-e2e-from-scratch.md) /
  [ADR 0052](0052-reproductibilite-des-resultats.md) — Validation e2e /
  reproductibilité (preuve banc puis prod ; paramétrage YAML = fin de l'env non
  versionné).
- [ADR 0049](0049-doctrine-choix-outil-par-action.md) — Doctrine du choix
  d'outil par action (**partiellement supersédée** : frontière bash/Python
  redéfinie).
- [ADR 0053](0053-isolation-multi-cible-banc-prod.md) — Isolation banc/prod
  (gardes traversées à chaque phase, invariant de boucle).
- [ADR 0056](0056-modele-declaratif-topologies.md) — Modèle déclaratif des
  topologies (une topologie = un YAML auto-suffisant ; paramétrage 100 % YAML).
- [ADR 0063](0063-ansible-runner-boucle-p5.md) — ansible-runner en Python
  (inversion **close** : plus de bash dans la boucle de montage).
- [ADR 0090](0090-nestor-pilote-la-prod.md) — `nestor` pilote la prod (le moteur
  Python pilote les deux topologies depuis leur YAML).
- [ADR 0096](0096-graphe-topologie-python-verifie-ansible.md) — Graphe Python
  figé (**prérequis** : projeté par le moteur pour dériver séquence et gates,
  backend-conditionnel banc/prod).

---
