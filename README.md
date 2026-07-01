# Cluster

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/univ-lehavre/cluster/badge)](https://scorecard.dev/viewer/?uri=github.com/univ-lehavre/cluster)

> Un cluster Kubernetes de recherche hyperconvergé — installation, stockage
> distribué, chaîne DataOps et services transverses, racontés de bout en bout.
>
> 🇬🇧 **English summary.** A self-hosted, hyperconverged research Kubernetes
> cluster: provisioning, distributed storage (Rook-Ceph), a DataOps chain and
> shared services, documented end to end. The documentation is written in French
> (the maintaining team's language), but **issues, pull requests and security
> reports written in English are welcome** — see
> [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

<!-- Badges — doctrine ADR 0080 (docs/decisions/0080-notations-et-badges-readme.md) :
n'afficher QUE ce qui mesure un état VRAI (dynamique câblé, ou statique factuel
stable) ; GROUPER par thématique pour rendre visibles les familles revendiquées.
Un référentiel noté non encore câblé reste au plan de remédiation du passage
d'audit, PAS affiché à vide. Un référentiel écarté (DORA, ISO) n'a pas de badge —
c'est un choix tracé. Le Best Practices Badge, retiré le 2026-06-19 tant qu'il
était à vide, est réintégré le 2026-06-22 une fois le questionnaire VALIDÉ par
l'OpenSSF (état vérifié — cf. ADR 0080 §Mises à jour). Le badge le plus
structurant (OpenSSF Scorecard, recalculé en continu) est mis en avant SOUS LE
TITRE ; les autres sont regroupés par famille dans la section « Conformité » plus
bas. -->

Ce dépôt est de l'**Infrastructure-as-Code** : une infrastructure entièrement
décrite par du code versionné. Son cœur est une **déclaration unique** — un
`topology.yaml` qui décrit nœuds, réseau, stockage et briques data — dont tout
le reste se dérive
([ADR 0056](docs/decisions/0056-modele-declaratif-topologies.md)). Il en sort
**deux produits** :

- **`nestor`** — l'outil déclaratif qui lit la topologie et **dérive puis
  converge** le cluster (`nestor up`, `preview`, `stack select`…) ;
- **un cluster Kubernetes data fonctionnel** — multi-nœuds, hyperconvergé, dont
  les **17 briques** ([`platform/`](platform/)) s'activent par **profil
  cumulatif à 4 niveaux** (`base ⊂ store ⊂ obs ⊂ dataops`) : stockage distribué
  Rook-Ceph, orchestration Dagster, lineage Marquez, base managée
  CloudNative-PG, observabilité Prometheus/Loki, GitOps Argo CD…

Le dépôt n'est pas l'infrastructure d'un déploiement particulier mais un
**catalogue de topologies** réutilisables : plusieurs déclarées, une seule
activée par déploiement
([ADR 0023](docs/decisions/0023-plateforme-exemple-generique.md)).

`cluster` est le **socle** ; l'**applicatif vit dans le dépôt jumeau
[`atlas`](https://github.com/univ-lehavre/atlas)**. Les deux sont reliés par un
**contrat d'interface explicite**
([ADR 0043](docs/decisions/0043-contrat-interface-cluster-atlas.md)) — `atlas`
publie des images immuables, `cluster` les réconcilie et lui fournit ses briques
(stockage, base managée, orchestration, MLflow). Pour le **récit complet**
(néophyte, de bout en bout), lire le [**manifeste**](docs/manifeste.md).

📖 **Documentation en ligne** :
[univ-lehavre.github.io/cluster](https://univ-lehavre.github.io/cluster/) —
publiée automatiquement depuis `main` par
[.github/workflows/docs.yml](.github/workflows/docs.yml).

> 🔰 **Nouveau sur le sujet ?** Les termes techniques (Kubernetes, etcd, OSD,
> PVC, erasure coding, quorum…) sont définis en langage simple dans le
> [**glossaire**](docs/glossaire.md) — à garder ouvert à côté en lisant les
> runbooks.

## Démarrage rapide

Prérequis : [Node.js](https://nodejs.org) et [pnpm](https://pnpm.io) (outillage
qualité du dépôt), [uv](https://docs.astral.sh/uv/) (scripts de gouvernance et
lint Python), et [Lima](https://lima-vm.io/) pour le banc d'essai. Pour
**déployer ou opérer** un cluster, suivre le
[`bootstrap/RUNBOOK.md`](bootstrap/RUNBOOK.md) ; ce dépôt ne « se lance » pas
comme une application — il décrit une infrastructure.

Pour travailler **sur le dépôt** (contribuer, valider en local à l'identique de
la CI) :

```bash
pnpm install   # outillage Node + installe les hooks Lefthook
pnpm lint      # tous les contrôles qualité (format, yaml, shell, k8s, ansible, python…)
pnpm format    # applique le formatage (prettier + ruff format)
pnpm docs:build  # construit le site Astro (échoue sur lien mort)
```

Pour **piloter une topologie** ou **valider de bout en bout**, deux points
d'entrée nommés (détaillés sous le tableau « Par où commencer ») :

```bash
nestor up                          # déploie la topologie sélectionnée (façade déclarative)
bench/lima/run-phases.sh <chemin>  # monte le banc Lima par un chemin codé (gate E2E)
```

Pour contribuer (branche, commits, revue, merge), le point d'entrée canonique
est [CONTRIBUTING.md](CONTRIBUTING.md) ; l'ordre d'installation **canonique** du
cluster reste décrit dans le [`bootstrap/RUNBOOK.md`](bootstrap/RUNBOOK.md).

## Par où commencer

| Je veux…                                | Aller voir                                                                                                                       |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **installer le cluster** (pas à pas)    | [`bootstrap/RUNBOOK.md`](bootstrap/RUNBOOK.md) — la séquence de référence                                                        |
| **brancher mon code / mon app**         | [`docs/se-brancher.md`](docs/se-brancher.md) — endpoints des briques · [`docs/dev-atlas.md`](docs/dev-atlas.md) (dev applicatif) |
| **opérer Ceph** (storage)               | [`storage/ceph/RUNBOOK.md`](storage/ceph/RUNBOOK.md)                                                                             |
| **vérifier l'état du cluster**          | [`bootstrap/state.sh`](bootstrap/state.sh)                                                                                       |
| **tester avant la prod**                | [`bench/`](bench/) — banc Lima ; `bench/lima/run-phases.sh`                                                                      |
| **comprendre les choix d'architecture** | [`docs/decisions/`](docs/decisions/) (ADR)                                                                                       |
| **suivre l'avancement**                 | [`docs/plans/`](docs/plans/) (mise en œuvre) · [`docs/audit/`](docs/audit/) (passages datés)                                     |

Deux points d'entrée, deux rôles complémentaires (pas concurrents). **`nestor`**
est l'outil déclaratif recommandé pour piloter une topologie
(`nestor up`/`preview`/`stack select`, et `nestor ansible <playbook>` pour un
geste de bootstrap prod) ; c'est une fonction shell à sourcer décrite dans
[`docs/outils.md`](docs/outils.md)
([ADR 0056](docs/decisions/0056-modele-declaratif-topologies.md)).
**`bench/lima/run-phases.sh`** est le harnais de banc par chemin nommé codé — la
_gate_ de validation E2E
([ADR 0045](docs/decisions/0045-chemins-installation-banc-couches.md)), jamais
enchaîné à la main. L'ordre d'installation **canonique** du cluster reste décrit
dans le [`bootstrap/RUNBOOK.md`](bootstrap/RUNBOOK.md).

## Structure

**Une responsabilité par dossier**, du provisioning de la machine jusqu'à la
gouvernance — c'est ce qui rend le dépôt lisible pour un nouveau contributeur.

| Dossier                          | Rôle                                                                 | Brique / règle                                           |
| -------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------- |
| [`bootstrap/`](bootstrap/)       | Installation initiale de Kubernetes (Ansible)                        | kubeadm durci ; idempotence prouvée (`changed=0`)        |
| [`storage/ceph/`](storage/ceph/) | Stockage distribué (Rook-Ceph)                                       | Bundles vendored épinglés par digest d'index multi-arch  |
| [`platform/`](platform/)         | Services transverses (dashboard, registry, metrics, NetworkPolicies) | Manifestes validés `kubeconform` + `trivy` (IaC)         |
| [`apps/`](apps/)                 | Charges applicatives (RStudio)                                       | Charge consommatrice ; ne porte aucun service transverse |
| [`bench/`](bench/)               | Banc Lima + scénarios reproductibles                                 | Monté par chemin nommé codé, jamais à la main (ADR 0045) |
| [`docs/`](docs/)                 | Glossaire, démarrage, ADR, audit (site Astro Starlight)              | Lien mort = build rouge ; conventions auto-vérifiées     |

Ces conventions sont vérifiées en CI : `pnpm check:gouvernance`
(ADR↔plans↔drifts), `pnpm lint:contract` (contrat d'interface `cluster`↔`atlas`)
et `pnpm lint:topology` (cohérence des topologies déclarées). Détail des choix
d'architecture : [`docs/decisions/`](docs/decisions/) (ADR).

## Qualité — garde-fous en place

Le dépôt est outillé pour que chaque modification passe un ensemble cohérent de
garde-fous, à la fois sur la machine du contributeur (via les _hooks Git_, des
scripts déclenchés automatiquement par Git) et sur les serveurs d'intégration
continue (via GitHub Actions), jusqu'au cluster en production. **12
vérifications sont requises** avant qu'une PR ne puisse fusionner.

### Cohérence du code

- **Prettier** (formateur automatique) sur YAML, Markdown et JSON, vérifié à
  chaque commit et en CI.
- **yamllint** (analyseur YAML) et **ShellCheck** (analyseur de scripts shell) —
  zéro avertissement toléré ; la couverture shell s'étend au-delà des `*.sh` (le
  wrapper `nestor.sh`, les templates `.sh.j2`, les scripts Perl par `perl -c`).
- **ansible-lint** sur les **34 rôles** Ansible de [`bootstrap/`](bootstrap/),
  **ruff** (analyseur + formateur) sur le périmètre Python.
- **Conventional Commits** appliqué par **commitlint** sur **toute la plage**
  d'une PR (pas seulement le titre, vu la stratégie merge-commit,
  [ADR 0037](docs/decisions/0037-strategie-merge-commit.md)) ; sujet en
  minuscules, **adresse e-mail interdite** dans le message.

### Validation des manifestes

- **kubeconform** (validateur de schémas Kubernetes) en mode `-strict`, contre
  les schémas officiels **+ le catalogue de CRDs** (Rook-Ceph, cert-manager,
  CloudNative-PG…) — un manifeste invalide ne franchit pas le push.
- **Trivy** (scanner de vulnérabilités IaC) — **bloquant sur HIGH/CRITICAL** ;
  le RBAC inhérent aux bundles upstream est allowlisté par chemin dans
  [`.trivyignore.yaml`](.trivyignore.yaml), avec justification.
- **Images épinglées par digest d'index multi-arch** (ADR 0006) : aucune image
  par tag mouvant, le banc étant arm64.

### Tests

- **`nestor` (le moteur déclaratif)** — **981 tests** Python (`unittest`, 39
  fichiers sous [`tests/`](tests/)) couvrant **95 % des 2 287 lignes** des 32
  modules de [`nestor/`](nestor/) ; la moitié des modules sont à **100 %**. La
  couverture est **mesurée en CI** avec un plancher bloquant
  (`coverage --fail-under=90`), recalculé à chaque PR — jamais un chiffre figé.
  Les fonctions pures sont en plus exercées par **property-based testing**
  (Hypothesis,
  [ADR 0087](docs/decisions/0087-property-based-testing-nestor.md)).
- **Scripts bash** — **248 cas de tests `bats`** répartis en **10 suites**
  ([`bench/unit/`](bench/unit/)), exécutés à chaque `pre-push` et en CI ; tout
  script shell passe par ailleurs ShellCheck, **zéro avertissement**.
- **End-to-end** — **34 scénarios E2E reproductibles** au banc Lima : Phases 1 à
  5 + DataOps sur 3 VMs Debian 13 avec disques Ceph, **_from scratch_** (depuis
  le code seul, [ADR 0034](docs/decisions/0034-validation-e2e-from-scratch.md)).
- **Idempotence prouvée** : un rôle n'est validé que si son rejeu donne
  `changed=0`
  ([ADR 0052](docs/decisions/0052-reproductibilite-des-resultats.md)).

### Audits structurels

- **jscpd** (détecteur de duplication) — seuil ≤ 5 %, **duplication shell tenue
  à 0 %**.
- **check_md_orphans** — aucune page de documentation orpheline (toute page est
  atteignable, [ADR 0029](docs/decisions/0029-markdown-atteignable-doc.md)).
- La cohérence **structurelle** du dépôt (ADR ↔ plans ↔ drifts, contrat
  d'interface, déclaratif byte-à-byte) fait l'objet d'une discipline propre,
  détaillée dans la section [**Gouvernance**](#gouvernance) ci-dessous.

### Hooks Git locaux

[Lefthook](https://github.com/evilmartians/lefthook) (orchestrateur de hooks
Git) bloque en local ce qui échouerait de toute façon en CI — **jamais
contournable** (`--no-verify`, `LEFTHOOK=0` interdits) :

- **pre-commit** : Prettier, yamllint, ShellCheck sur les fichiers indexés.
- **commit-msg** : commitlint + rejet des e-mails.
- **pre-push** : **interdiction de push direct sur `main`**, puis suite complète
  (kubeconform, ansible-lint, `bats`, jscpd, ShellCheck/Prettier sur les
  fichiers du push).

### Drift detection & opérabilité

- [`bootstrap/state.sh`](bootstrap/state.sh) compare l'état réel à l'état
  déclaré sur **7 couches** (_drift detection_) ;
  [`bootstrap/security/report.sh`](bootstrap/security/report.sh) donne la
  visibilité sur le durcissement (_hardening_).
- Complétés par un **audit-log par nœud**, une **sauvegarde etcd** (RPO borné)
  et un **rollback scripté**.

Inventaire complet et détaillé : [SAFEGUARDS.md](SAFEGUARDS.md). Comment
contribuer (branche, commits, revue, merge) et outiller sa machine :
[CONTRIBUTING.md](CONTRIBUTING.md).

## Culture d'ingénierie

Au-delà des garde-fous transverses, le dépôt **nomme** les cultures d'ingénierie
qu'il incarne — chacune ancrée dans des décisions d'architecture (_ADR_,
_Architecture Decision Record_, dans [`docs/decisions/`](docs/decisions/)), pas
seulement déclarée, et **honnête sur les manques** : ce qui est en place, ce qui
est en construction, ce qui est sciemment écarté
([ADR 0062](docs/decisions/0062-cultures-ingenierie.md)) : **4 cultures en
place**, 2 en construction, le reste sciemment écarté. L'**IaC est le cœur** —
les trois autres cultures en place (GitOps, DataOps, DevSecOps) en sont les
facettes, pas des piliers parallèles. Chaque affirmation ci-dessous **pointe
vers sa preuve** (la décision, le manifeste, le test) sans la recopier. Le récit
complet, néophyte et de bout en bout, vit dans le
[**manifeste**](docs/manifeste.md).

### IaC — le cœur : une déclaration unique, deux produits

_IaC_ (_Infrastructure-as-Code_) : toute l'infrastructure est décrite par du
code versionné, rejouable et prouvé reproductible. Une **source de vérité
unique** — le `topology.yaml` — décrit nœuds, réseau, stockage et briques data ;
tout le reste (inventaire Ansible, variables de profil, table de nœuds Lima) en
est **dérivé** par un générateur **sans état**, et Ansible reste le moteur de
**convergence**
([ADR 0056](docs/decisions/0056-modele-declaratif-topologies.md)).

- **Catalogue de topologies** : plusieurs infra déclarées, une seule activée par
  déploiement, sur valeurs d'exemple génériques — le dépôt n'est pas
  l'infrastructure d'un déploiement particulier
  ([ADR 0023](docs/decisions/0023-plateforme-exemple-generique.md)).
- **Deux produits dérivés de la déclaration** : **`nestor`**, l'outil qui lit la
  topologie et converge le cluster (`nestor up`/`preview`/`stack select`,
  [`docs/outils.md`](docs/outils.md)), et **un cluster Kubernetes data
  fonctionnel**, hyperconvergé, dont les briques s'activent par profil cumulatif
  (`base ⊂ store ⊂ obs ⊂ dataops`).
- **Idempotence prouvée** : un rôle Ansible n'est correct que si son rejeu donne
  `changed=0` — un résultat n'a de valeur que **reproductible depuis le code
  seul** ([ADR 0052](docs/decisions/0052-reproductibilite-des-resultats.md)).
- **Provisioning de la couche machine** déclaré avec **OpenTofu** pour le
  terrain cloud (décidé ; bancs locaux Lima/Vagrant inchangés)
  ([ADR 0032](docs/decisions/0032-opentofu-provisioning-cloud.md)).

### GitOps — le dépôt Git est la source de vérité

_GitOps_ : tout passe par Git et une _pull request_ (PR, proposition de
modification revue avant fusion), rien à la main sur les serveurs. Aucune
modification n'atteint `main` autrement que par une PR revue et verte en CI, et
le déploiement lui-même se pilote par ce qui est écrit dans Git.

- **Tout par PR, jamais en direct.** Commits et push directs sur `main` sont
  mécaniquement refusés (hooks Lefthook, _jamais_ contournables) ; `main`
  n'accepte que des **merge commits** — l'historique fin de chaque PR est
  préservé ([ADR 0037](docs/decisions/0037-strategie-merge-commit.md)).
- **Réconciliation déclarative** par **Argo CD** + **Gitea** air-gapped : l'état
  cible est dans Git, l'opérateur converge le cluster vers cet état
  ([ADR 0022](docs/decisions/0022-argocd-gitops-applicatif.md)).
- **Le déploiement suit Git, pas l'inverse.** `cluster` et l'applicatif
  [`atlas`](https://github.com/univ-lehavre/atlas) sont deux dépôts au **contrat
  d'interface explicite** : `atlas` publie des images immuables identifiées par
  empreinte (_digest_), `cluster` les réconcilie — jamais de tag `latest`
  ([ADR 0043](docs/decisions/0043-contrat-interface-cluster-atlas.md),
  [ADR 0044](docs/decisions/0044-topologie-deploiement-banc-atlas.md)).

### DataOps — les données comme du code, contrôlées par contrat

_DataOps_ : appliquer au traitement de données la même discipline qu'au code —
orchestration déclarative, transformations versionnées, qualité vérifiée à
chaque étape, résultats reproductibles. La plateforme de données est fournie par
le socle et consommée par l'applicatif au travers d'un contrat d'interface
explicite.

- **Orchestration déclarative** avec [Dagster](https://dagster.io/), déployée
  par Ansible sur la plateforme
  ([ADR 0026](docs/decisions/0026-orchestration-dagster.md),
  [ADR 0033](docs/decisions/0033-orchestration-ansible-platform-dataops.md)).
- **Traçabilité de bout en bout** : lineage
  [OpenLineage](https://openlineage.io/) →
  [Marquez](https://marquezproject.ai/), **sans donnée personnelle** (noms
  techniques uniquement)
  ([ADR 0028](docs/decisions/0028-orchestration-openlineage-marquez.md)).
- **Complétude gouvernée** : la chaîne DataOps est tenue complète par un audit
  de gouvernance dédié, et son interface avec l'applicatif est contractuelle
  ([ADR 0041](docs/decisions/0041-gouvernance-completude-dataops.md),
  [ADR 0043](docs/decisions/0043-contrat-interface-cluster-atlas.md)).

### DevSecOps — la sécurité câblée dans la chaîne

_DevSecOps_ : intégrer la sécurité dans la chaîne plutôt qu'en étape finale —
chaîne d'approvisionnement vérifiée, durcissement par défaut, analyse continue.
Chaque maillon, de l'image épinglée au cluster en marche, porte sa garantie.

- **Chaîne d'approvisionnement épinglée** : images par **digest d'index
  multi-arch**, actions GitHub par **SHA**, secrets jamais versionnés
  ([ADR 0006](docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
- **Durcissement par défaut** : `kubeadm` durci, PSA + audit-policy, **etcd
  chiffré**, réseau Cilium verrouillé
  ([ADR 0014](docs/decisions/0014-durcissement-kubeadm-init.md),
  [ADR 0019](docs/decisions/0019-durcissement-reseau-cilium.md)).
- **Analyse continue** : `trivy` (IaC, bloquant HIGH/CRITICAL), `gitleaks`
  (secrets), `CodeQL` (SAST), score **OpenSSF Scorecard** recalculé en continu.

### Platform Engineering — _en construction_

_Platform Engineering_ : offrir aux équipes des **paved roads** (chemins
balisés) self-service plutôt que de la configuration sur mesure. Les fondations
sont posées, le cœur self-service est partiel.

- **Acquis** : le **catalogue de topologies** réutilisables
  ([ADR 0023](docs/decisions/0023-plateforme-exemple-generique.md)), le
  **contrat plateforme↔consommateur** machine-lisible (3 artefacts sous
  [`contract/`](contract/),
  [ADR 0043](docs/decisions/0043-contrat-interface-cluster-atlas.md)), et un
  amorçage self-service : `nestor stack new` (assistant qui écrit un
  `topology.yaml` minimal valide) et `nestor next` (le « que faire ensuite » qui
  monte la couche suivante d'après le graphe de dépendances réel).
- **Manque** : le portail in-cluster ([`platform/portal/`](platform/portal/),
  [ADR 0091](docs/decisions/0091-portail-acces-ui.md)) — sa logique de
  rapprochement contrat↔état existe en code, son service n'est pas encore
  déployé. D'où **en construction**, pas acquis.

### MLOps — _socle posé, usages à venir_

_MLOps_ : exploiter des modèles avec la rigueur du logiciel — expériences
tracées, modèles versionnés, artefacts persistés. Le **socle est en place** ;
les cas d'usage relèvent de l'applicatif.

- **Serveur MLflow déployé** (tracking + registry + artefact store) par le rôle
  Ansible `platform-mlflow`, **livré vide** — exactement comme Dagster et
  Marquez ([ADR 0082](docs/decisions/0082-suivi-modeles-mlflow.md)). Backend sur
  la base managée CloudNative-PG dédiée, artefacts sur S3 (Ceph/SeaweedFS),
  câblé dans le graphe `nestor` et dans la layer `atlas`
  ([ADR 0083](docs/decisions/0083-layers-source-unique-de-l-ordre.md)).
- **À venir** : le **code ML qui logge ses runs vit côté
  [`atlas`](https://github.com/univ-lehavre/atlas)** (l'applicatif), pas dans le
  socle ; côté `cluster`, restent la validation au banc et l'observation des
  métriques MLflow. Le socle fournit la capacité ; l'usage est l'affaire du
  consommateur.

### FinOps — _efficience amorcée, coût € écarté_

_FinOps_ : piloter la consommation des ressources. Seule sa **moitié
efficience** s'applique ici ; le volet **coût €** est sciemment hors périmètre.

- **Amorcé (efficience / capacité)** : observabilité **kube-prometheus-stack**
  (Prometheus/Grafana/Alertmanager) + **metrics-server**
  ([ADR 0016](docs/decisions/0016-observabilite.md)) ; **métrologie de banc**
  ([`nestor/metrics.py`](nestor/metrics.py)) qui mesure `cpu_core_s`,
  `ram_peak_mib`, `ram_mean_mib` par run et les indexe ; gestion de **capacité
  Ceph** (seuils nearfull/full).
- **Écarté (coût €)** : pas de dimension monétaire — l'infra est **bare-metal
  non facturée à l'usage** et **mono-tenant** : chargeback et refacturation
  n'ont pas de sens tant que ce contexte ne change pas (la topologie cloud ARM,
  si elle est buildée, rouvrira la question)
  ([ADR 0062](docs/decisions/0062-cultures-ingenierie.md)).

> **SRE** est par ailleurs **partiel** (drift detection, fraîcheur des preuves,
> sauvegarde etcd et rollback existent ; manquent SLO/SLI et error budgets
> formels). Le _pourquoi_ de chaque frontière — en place / en construction /
> partiel / écarté — est tracé dans
> l'[ADR 0062](docs/decisions/0062-cultures-ingenierie.md).

## Sécurité

La sécurité n'est pas un chapitre à part : elle est **câblée dans la chaîne**
(_DevSecOps_, cf. ci-dessus) et **assumée honnêtement**. Cette section
consolide, en un seul endroit, **ce qui protège** (contrôles actifs) et **ce qui
est délibérément relâché** (compromis tracés) — car sur ce dépôt les deux se
lisent ensemble.

### Modèle de menace (à lire d'abord)

Le cluster est **mono-tenant**, **mono-admin**, sur **réseau privé isolé**
(`10.0.0.0/22`), sans données réglementées. Ce périmètre est le socle de
plusieurs choix : certains contrôles « attendus » sont **volontairement
allégés** parce que l'**isolation réseau** en tient lieu, et ces relâchements
sont **tracés en ADR**, pas subis. Un signalement utile est donc plutôt « telle
hypothèse d'isolation est fausse dans tel cas » que « tel service n'a pas d'auth
» — le détail est dans [SECURITY.md](SECURITY.md). **Porte de sortie unique** :
le jour où le cluster s'ouvre (multi-tenant, accès externe, données
réglementées), chaque compromis ci-dessous est repris par un nouvel ADR
([ADR 0003](docs/decisions/0003-pas-de-chiffrement-ceph-tailscale.md)).

### Contrôles actifs

Chaque ligne pointe vers sa preuve (ADR, manifeste, workflow) ; l'inventaire
opérationnel complet est dans [SAFEGUARDS.md](SAFEGUARDS.md).

#### Chaîne d'approvisionnement & CI (_shift-left_)

- **Analyse IaC bloquante** : `trivy` scanne les manifestes en `HIGH,CRITICAL`
  avec `exit-code 1` (**bloque le merge**) ; le RBAC inhérent aux bundles
  upstream est allowlisté **par chemin et avec justification** dans
  [`.trivyignore.yaml`](.trivyignore.yaml).
- **SAST** : **CodeQL** (requêtes `security-and-quality`) sur le périmètre
  Python du harnais (`nestor/`, `scripts/`) —
  [.github/workflows/codeql.yml](.github/workflows/codeql.yml).
- **Secret scanning** : `gitleaks` balaie **tout l'historique git** (mode
  `git`), binaire **épinglé par version + SHA-256**, allowlist limitée aux
  valeurs d'exemple dans [`.gitleaks.toml`](.gitleaks.toml) ; en complément,
  secrets jamais versionnés (`.env`, `secrets/`, snapshots etcd sous
  `.gitignore`).
- **Supply-chain épinglée** : **toutes** les actions GitHub sont épinglées par
  **SHA de commit** (une seule exception documentée — le générateur SLSA exige
  un tag), et les images conteneurs par **digest d'index multi-arch**, jamais
  par tag mouvant
  ([ADR 0006](docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
- **Releases signées** : chaque release publie une archive source **signée
  cosign _keyless_** (OIDC, aucune clé à gérer) + une **provenance SLSA**
  (`.intoto.jsonl`) liant l'artefact au commit/workflow
  ([ADR 0088](docs/decisions/0088-signature-releases-cosign-slsa.md),
  [.github/workflows/release.yml](.github/workflows/release.yml)).
- **Least privilege CI** : `permissions:` restreintes au strict nécessaire (top
  level en lecture, élargi par job), `persist-credentials: false`, et **PAT
  fine-grained** dédiés (scope = ce repo) pour les rares gestes en écriture
  (release-please, Scorecard branch-protection).
- **Posture supply-chain notée** : **OpenSSF Scorecard** recalculé en continu +
  **OpenSSF Best Practices Badge** validé par questionnaire — voir
  [Conformité](#conformité). _Non bloquants (modèle « alerte », pas « gate »)
  aujourd'hui : CodeQL, gitleaks et Scorecard remontent dans l'onglet Security ;
  seul `trivy` gate le merge — cf._ [SAFEGUARDS.md](SAFEGUARDS.md).

#### Plan de contrôle Kubernetes ([ADR 0014](docs/decisions/0014-durcissement-kubeadm-init.md))

- **Secrets etcd chiffrés at-rest** via `EncryptionConfiguration` (provider
  `secretbox`) — donc chiffrés aussi dans les snapshots ; clé générée sur le
  nœud, **jamais versionnée**.
- **Audit-policy API** de niveau `Metadata` : les appels API directs (qui/quoi/
  quand) sont journalisés, avec exclusion du bruit.
- **Pod Security Admission** `baseline` en `enforce` (et `restricted` en `warn`)
  sur les namespaces applicatifs — bloque `privileged`, `hostPID/IPC`,
  `hostNetwork`.

#### Réseau

- **Micro-segmentation** : **56 NetworkPolicies** sous
  [`platform/network-policies/`](platform/network-policies/) — patron
  `default-deny` (ingress + egress) puis autorisations strictement nécessaires
  par namespace, validées au banc (le trafic non listé est refusé).
- **Chiffrement pod-to-pod** inter-nœuds par **WireGuard** (Cilium), clés gérées
  par Cilium — défense en profondeur qui atténue le principal coût de
  l'[ADR 0003](docs/decisions/0003-pas-de-chiffrement-ceph-tailscale.md)
  ([ADR 0019](docs/decisions/0019-durcissement-reseau-cilium.md)).
- **Observabilité réseau** : **Hubble** (flux L3/L4/L7, verdicts de policy,
  drops) en CLI par défaut, UI opt-in
  ([ADR 0073](docs/decisions/0073-hubble-ui-observabilite-reseau.md)).
- **Bordure unique** : services applicatifs en `ClusterIP`, exposition par
  **Gateway API** (pas de `NodePort`/`LoadBalancer` bruts sur l'applicatif), TLS
  terminé par **cert-manager + CA interne** (chaîne self-signed → CA, feuilles
  renouvelées automatiquement ; pas d'ACME, cluster non joignable d'Internet)
  ([ADR 0021](docs/decisions/0021-cert-manager-ca-interne.md)).

#### Durcissement OS & accès nœuds

- **SSH durci par défaut** dès le premier accès
  ([`bootstrap/first-access.sh`](bootstrap/first-access.sh)) :
  `PasswordAuthentication no`, clés uniquement, `PermitRootLogin no`,
  `AllowUsers debian`, `MaxAuthTries 3`, timeout d'inactivité — idempotent.
- **Durcissement OS opt-in par tags** (`bootstrap/security/`) : mises à jour
  automatiques + expiration mot de passe, `auditd` (règles syscall), `fail2ban`
  (anti-brute-force SSH), redirection du mail root, **UFW** (après K8s/Cilium/
  Ceph). Chaque couche s'active explicitement
  ([`bootstrap/security/IMPLICATIONS.md`](bootstrap/security/IMPLICATIONS.md)) ;
  visibilité par [`bootstrap/security/report.sh`](bootstrap/security/report.sh).
- **Audit-log par nœud** : chaque playbook appose qui/quoi/quand dans
  `/var/log/cluster-bootstrap.log`, corrélé par
  [`bootstrap/state.sh`](bootstrap/state.sh).

#### Opérabilité & résilience

- **Détection de drift** sur **7 couches** (état réel vs déclaré,
  [`bootstrap/state.sh`](bootstrap/state.sh)), **sauvegarde etcd** horaire
  (timer systemd, restauration prouvée réversible au banc) et **rollback
  scripté** du bootstrap (`-e confirm=yes`).
- **Sécurité active** : des scénarios d'**attaques contrôlées** (brute-force SSH
  → ban `fail2ban`, pod privilégié → rejet PSA, exfil → coupe NetworkPolicy) et
  de chaos valident la défense **par l'acte**, au banc jetable uniquement
  ([ADR 0025](docs/decisions/0025-securite-active-chaos-attaques-controlees.md)).

### Compromis délibérés (le réseau isolé fait rempart)

Ces relâchements sont des **choix tracés**, pas des failles — chacun assume son
coût et sa porte de sortie :

| Choix                                                              | ADR                                                              |
| ------------------------------------------------------------------ | ---------------------------------------------------------------- |
| Pas de chiffrement Ceph (in-transit / at-rest), RGW HTTP           | [0003](docs/decisions/0003-pas-de-chiffrement-ceph-tailscale.md) |
| Registry interne en HTTP sans authentification                     | [0011](docs/decisions/0011-registry-http-sans-auth.md)           |
| RStudio sans login (`DISABLE_AUTH=true`)                           | [0012](docs/decisions/0012-rstudio-disable-auth.md)              |
| Dashboard Kubernetes lié à `cluster-admin` (tokens ≤ 8 h)          | [0010](docs/decisions/0010-dashboard-cluster-admin.md)           |
| Clé de chiffrement etcd en clair sur le control plane (pas de KMS) | [0014](docs/decisions/0014-durcissement-kubeadm-init.md)         |

Tous reposent sur l'accès **exclusivement local** (`kubectl port-forward`, saut
SSH) et l'isolation réseau ; aucun n'est exposé publiquement.

### Signaler une vulnérabilité

**Ne pas** ouvrir d'issue publique. Utiliser le **Private Vulnerability
Reporting** de GitHub
(<https://github.com/univ-lehavre/cluster/security/advisories/new>) ou écrire au
mainteneur — procédure, périmètre et modèle de menace détaillés dans
[SECURITY.md](SECURITY.md). Les rapports en anglais sont bienvenus.

## Gouvernance

La gouvernance n'est pas qu'une discipline d'auteur : elle est **mesurée,
outillée et auto-vérifiée**, comme le code. Chaque décision est tracée (ADR),
chaque écart de run est indexé (drift), chaque convention est auto-vérifiée
([ADR 0060](docs/decisions/0060-audit-conventions-gouvernance.md)). Les chiffres
ci-dessous ne sont **pas saisis à la main** mais **recalculés par un script** et
comparés en CI ; tout écart fait rougir le build. La vitrine consolidée, pour
juger en 5 min : [docs/preuves.md](docs/preuves.md).

<!-- STATS:DEBUT — bloc régénéré par `pnpm check:gouvernance --stats` (ADR 0060) -->

- **101 ADR** (88 Accepted, 9 Proposed, 4 Superseded)
- **16 plans** vivants (1 Abandonné, 6 Achevé, 8 Actif, 1 Brouillon)
- **73 drifts** indexés (3 caduc, 67 corrige, 1 en-cours, 2 ouvert)
- **34 scénarios** E2E reproductibles

<!-- STATS:FIN -->

_Bloc régénéré par `pnpm check:gouvernance --stats`. L'avancement détaillé est
suivi par [**milestones**](https://github.com/univ-lehavre/cluster/milestones)
et dans [`docs/plans/`](docs/plans/) ; contribuer :
[CONTRIBUTING.md](CONTRIBUTING.md) ; signaler une vulnérabilité :
[SECURITY.md](SECURITY.md)._

### Décisions tracées (ADR)

Toute décision structurante passe par un **ADR** (_Architecture Decision
Record_, format Nygard léger), jamais par une note dans un TODO. Le corpus
**chiffré ci-dessus** est indexé chronologiquement dans
[`docs/decisions/README.md`](docs/decisions/), et chaque affirmation de ce
README **pointe vers l'ADR qui la fonde**.

### Écarts de run indexés (drifts)

Un _drift_ est un **écart révélé par un run de bout en bout** que le lint ne
voyait pas : il est consigné, daté et corrigé dans le code (jamais à la main sur
l'état, [ADR 0046](docs/decisions/0046-corriger-le-code-pas-l-etat.md)). Le
registre
[`docs/architecture/registre-drifts.yaml`](docs/architecture/registre-drifts.yaml)
compte **73 entrées** (symptôme, cause, correctif, statut, issue) ; sa page
publiée est **régénérée et comparée en CI** (`render_drifts --check`).

### Contrat d'interface `cluster` ↔ `atlas`

La frontière avec l'applicatif [`atlas`](https://github.com/univ-lehavre/atlas)
est un **contrat machine-lisible** : **3 artefacts** sous
[`contract/`](contract/) (endpoints des services, storage-classes par profil,
namespaces & conventions de secrets). `pnpm lint:contract` vérifie en CI que ce
contrat reste **aligné sur ce que `platform/` expose réellement**
([ADR 0043](docs/decisions/0043-contrat-interface-cluster-atlas.md)).

### Auto-vérification continue

- **`check_gouvernance`**
  ([ADR 0060](docs/decisions/0060-audit-conventions-gouvernance.md)) vérifie la
  cohérence **ADR ↔ plans ↔ drifts ↔ issues**, la complétude des index, la
  **fraîcheur des traces** (dernier passage d'audit < 180 j) et régénère le bloc
  de stats.
- **`check_topology`** valide le modèle déclaratif et prouve que les artefacts
  dérivés d'un `topology.yaml` sont **byte-identiques** à l'attendu.
- **`check_md_orphans`** garantit qu'aucune page de doc n'est orpheline.
- Deux **workflows de fraîcheur** non bloquants ouvrent une issue dédiée en cas
  de dérive : `conventions-freshness` (hebdomadaire) et `bench-freshness`
  (quotidien, preuves de banc).

### Passages d'audit datés

La gouvernance se relit elle-même : **12 passages d'audit** datés sous
[`docs/audit/`](docs/audit/) (convention `AAAA-MM-JJ-thème.md`), figés — un
constat passé n'est pas réécrit (honnêteté des traces). La vitrine consolidée,
pour juger en 5 min : [docs/preuves.md](docs/preuves.md).

## Documentation

[![Documentation](https://img.shields.io/badge/docs-univ--lehavre.github.io%2Fcluster-blue.svg)](https://univ-lehavre.github.io/cluster/)

La documentation est publiée sur
**[univ-lehavre.github.io/cluster](https://univ-lehavre.github.io/cluster/)**
(sources dans [`docs/`](docs/), construites avec Astro Starlight) :

- [Manifeste](docs/manifeste.md) — le récit complet, de bout en bout, pour un
  public néophyte
- [Glossaire](docs/glossaire.md) — définitions des termes techniques (etcd, OSD,
  PVC, erasure coding, quorum…) en langage simple
- [Démarrage & outils](docs/demarrage.md) — installer le cluster, piloter une
  topologie avec `nestor`
- [Se brancher](docs/se-brancher.md) — endpoints des briques, brancher son code
  et ses applications
- [Décisions d'architecture](docs/decisions/) — pourquoi chaque choix (ADR)
- [Vitrine des preuves](docs/preuves.md) — juger la gouvernance du dépôt en 5
  min

## Conformité

Les badges ne sont pas décoratifs : chacun reflète un état **vrai et
vérifiable** (recalculé en continu, ou fait stable). Le plus structurant —
[OpenSSF Scorecard](https://scorecard.dev/viewer/?uri=github.com/univ-lehavre/cluster),
santé supply-chain notée /10 — est mis en avant **sous le titre**, seul.
Regroupés ci-dessous par famille, les autres disent **quelles familles de
qualité le dépôt revendique** — un badge n'est posé que s'il est honnête
([ADR 0080](docs/decisions/0080-notations-et-badges-readme.md)).

### Identité & licence

Le projet est **citable et ouvert** : un DOI Zenodo fige et référence chaque
version pour la citation académique, et le code est sous licence **MIT**
(réutilisation libre, `LICENSE` + `NOTICE`).

[![DOI](https://zenodo.org/badge/1243564575.svg)](https://doi.org/10.5281/zenodo.20287209)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/univ-lehavre/cluster/blob/main/LICENSE)

### Conventions & versionnement

L'historique est **lisible et outillé**, pas seulement par discipline. Chaque
message de commit suit **Conventional Commits** (validé par commitlint sur toute
la plage d'une PR), les versions suivent **SemVer** (bump dérivé des commits par
release-please), et le **CHANGELOG** est tenu au format _Keep a Changelog_,
généré automatiquement à chaque release.

[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://www.conventionalcommits.org)
[![SemVer](https://img.shields.io/badge/SemVer-2.0.0-blue.svg)](https://semver.org)
[![Keep a Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-orange.svg)](https://github.com/univ-lehavre/cluster/blob/main/CHANGELOG.md)

### Qualité & CI

Aucune régression n'atteint `main` sans passer les contrôles : chaque PR doit
satisfaire **12 checks requis** (formats, lint, `kubeconform`, `ansible-lint`,
`trivy`, `jscpd`, tests…) avant merge. Le badge **CI** reflète l'état réel du
workflow `ci.yml` sur `main` ; l'analyse de sécurité **CodeQL** (SAST) s'exécute
sur le périmètre Python du dépôt. Détail des garde-fous : section
[« Qualité — garde-fous en place »](#qualité--garde-fous-en-place) ci-dessus et
[SAFEGUARDS.md](SAFEGUARDS.md).

[![CI](https://github.com/univ-lehavre/cluster/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/univ-lehavre/cluster/actions/workflows/ci.yml)
[![CodeQL](https://github.com/univ-lehavre/cluster/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/univ-lehavre/cluster/actions/workflows/codeql.yml)

### Sécurité & supply-chain

Au-delà du score Scorecard (en tête), le dépôt vise les **bonnes pratiques OSS**
de l'OpenSSF : le **Best Practices Badge** atteste, après questionnaire **validé
par l'OpenSSF** (et non auto-déclaré à vide), la couverture des critères de
santé projet — change control, tests, rapport de vulnérabilités, analyse
statique ([ADR 0080](docs/decisions/0080-notations-et-badges-readme.md)). Détail
des réponses :
[answer-sheet](docs/audit/2026-06-22-best-practices-badge-answer-sheet.md).

[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13301/badge)](https://www.bestpractices.dev/projects/13301)

### Marques

Tous les noms de produits et marques mentionnés dans ce dépôt sont la propriété
de leurs détenteurs respectifs.
