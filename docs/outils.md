# Boîte à outils — quels scripts lancer, et pour quoi

Catalogue des scripts **opérables** du dépôt (hors playbooks Ansible, qui sont
joués par l'orchestrateur de banc ou décrits dans les RUNBOOK). Doctrine du
choix d'outil : [ADR 0049](decisions/0049-doctrine-choix-outil-par-action.md) —
Ansible **converge l'état durable** ; le shell/Python porte l'**orchestration**,
le **diagnostic en lecture seule**, l'**accès**, les **tests** et les actes que
Ansible ne peut pas faire (poule/œuf, sans dépôt, destructif conscient).

> Les chemins sont relatifs à la racine du dépôt. Chaque script documente son
> usage précis dans son en-tête (`head -20 <script>`). Les valeurs montrées ici
> sont génériques ([ADR 0023](decisions/0023-plateforme-exemple-generique.md)) —
> surcharger avec les vraies valeurs de votre déploiement (config locale).

## L'outil `nestor` — installer la commande

`nestor` (l'outil déclaratif : `nestor up`/`preview`/`stack select`…) est une
**fonction shell à sourcer**, pas un exécutable. Pourquoi ? Pour que
`nestor stack select` puisse **poser `KUBECONFIG` dans ton shell** — ce qu'un
programme lancé ne peut pas faire (un enfant ne modifie pas l'environnement de
son parent ; patron `nvm`/`pyenv`/`direnv`). La fonction délègue à
l'implémentation `scripts/nestor-exec` et applique le `export KUBECONFIG=…` que
`stack select` imprime.

> `nestor env` a été **supprimée**
> ([ADR 0097](decisions/0097-moteur-chemin-python-bash-artefacts.md) §3) — elle
> incarnait le paramétrage-par-variable-d'environnement aboli. À la place, deux
> mécanismes :
>
> - **`nestor kubectl <args…>`** — lance `kubectl` sur la cible de la **stack
>   active**, kubeconfig résolu automatiquement (banc Lima ou `kubeconfig:` de
>   la topo prod, jamais `~/.kube/config` par accident). C'est le remplaçant
>   direct : `nestor kubectl get pods -A` au lieu de
>   `eval "$(nestor env)" ; kubectl …`. Si la stack **prod** est active, il vise
>   la prod ; si c'est le banc, il vise le banc — **sans manipuler
>   l'environnement du shell**.
> - `nestor stack select <topo>` **pose aussi un contexte kubectl nommé** dans
>   le kubeconfig de la cible (mécanisme standard `kubectl --context <topo> …`).

**Installation** — sourcer le fichier `nestor.sh` (racine du dépôt) dans ton
profil :

```bash
echo 'source <racine-du-dépôt>/nestor.sh' >> ~/.zshrc   # ou ~/.bashrc
source ~/.zshrc                                          # (ou ouvrir un nouveau shell)
```

Ensuite, depuis n'importe quel dossier :

```bash
nestor up                  # monter le banc
nestor preview             # voir l'état (VOULU/RÉEL/PLAN)
nestor stack select banc   # activer une stack ET pointer KUBECONFIG (banc, ou
                            #   /dev/null si pas de banc — jamais la prod, ADR 0053)
```

> **Sans sourcer** (usage ponctuel, sans la pose auto de `KUBECONFIG`) : appeler
> l'implémentation directement — `scripts/nestor-exec preview`. La garde
> d'isolation ([ADR 0053](decisions/0053-isolation-multi-cible-banc-prod.md))
> protège la prod dans les deux cas.

## Prérequis & contexte — « quels sont MES hôtes ? »

Plusieurs scripts (`bootstrap/state.sh`, `bootstrap/security/report.sh`…)
attendent une **liste d'hôtes** ou un **kubeconfig**. Or, par conception
([ADR 0023](decisions/0023-plateforme-exemple-generique.md)), le dépôt **ne
contient pas** tes vrais hôtes : ils vivent en config locale **gitignorée**.

| Tu cherches…             | Où ça vit                                                                    |
| ------------------------ | ---------------------------------------------------------------------------- |
| Hôtes **prod**           | `bootstrap/hosts.yaml` (gitignoré ; copié de `bootstrap/hosts.example.yaml`) |
| Hôtes **banc Lima**      | les VMs réelles — `limactl list` (noms `cp1`, `node1`…)                      |
| `kubeconfig` du **banc** | `bench/lima/.work/kubeconfig` (généré par `run-phases.sh`)                   |

**Le plus simple — laisse `env.sh` dériver ton contexte et t'imprimer les
commandes exactes à copier** (hôtes courants + invocation `state.sh` par nœud),
sans rien deviner :

```bash
bench/lima/env.sh                    # auto-détecte (banc Lima ou prod)
```

> Pour **brancher `kubectl`**, plus de `eval "$(env.sh export)"` :
> `nestor stack select <topo>` pose un **contexte kubectl nommé**, puis
> `kubectl --context <topo> …` (mécanisme standard k8s, sans variable d'env —
> ADR 0097 §3).

Exemple de ce qu'il imprime sur un banc Lima à 3 nœuds :
l'`USER_REMOTE=lima SSH_OPTS='-F ~/.lima/cp1/ssh.config' bootstrap/state.sh cp1`
prêt à coller, pour chaque nœud. En prod, il lit `bootstrap/hosts.yaml` et te
donne `bootstrap/state.sh <tes-nœuds>`.

## Monter et piloter un banc de test (local)

Le banc Lima est l'environnement de validation e2e
([ADR 0034](decisions/0034-validation-e2e-from-scratch.md)). Tout passe par un
**orchestrateur unique** :

| Pour…                                               | Commande                                                          | Détails                                                                                  |
| --------------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Monter le banc par étapes (gate par phase)          | `bench/lima/run-phases.sh <phase>`                                | [bench/lima/README.md](../bench/lima/README.md)                                          |
| Monter un **chemin nommé** complet                  | `bench/lima/run-phases.sh socle\|atlas\|atlas-ceph\|storage-real` | [ADR 0045](decisions/0045-chemins-installation-banc-couches.md)                          |
| Voir l'état du banc (VMs, nœuds, phases, UIs)       | `bench/lima/run-phases.sh status`                                 | lecture seule                                                                            |
| (Ré)exporter le kubeconfig du banc                  | `bench/lima/run-phases.sh kubeconfig`                             |                                                                                          |
| Détruire le banc (VMs + disques)                    | `bench/lima/run-phases.sh down`                                   | destructif                                                                               |
| Prouver une **reprise après faute** (arrêt injecté) | `BANC_JETABLE=1 bench/lima/run-phases.sh bootstrap-fault`         | [ADR 0050](decisions/0050-modele-reprise-role-ansible.md) — **destructif**, banc jetable |

## Accès développeur

| Pour…                                                                                         | Commande                                                                    | Détails                                               |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------- |
| Rendre le banc consommable depuis l'hôte (URLs `*.cluster.lan` cliquables + secrets + `.env`) | `bench/lima/access.sh`                                                      | [ADR 0048](decisions/0048-acces-local-developpeur.md) |
| Premier accès SSH à des nœuds Debian fraîchement installés (poule/œuf avant Ansible)          | `bootstrap/first-access.sh`                                                 | prérequis d'Ansible                                   |
| Identifiants / gestion du dashboard Kubernetes                                                | `platform/k8s-dashboard/manage.sh`, `platform/k8s-dashboard/credentials.sh` |                                                       |

## Diagnostic & reporting (lecture seule)

Ansible **converge** l'état ; il ne **reporte** pas. Le diagnostic vit donc en
shell ([ADR 0049](decisions/0049-doctrine-choix-outil-par-action.md)).

| Pour…                                                                 | Commande                              | Détails                                                                                                             |
| --------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Dériver ton contexte** (hôtes courants + commandes prêtes à copier) | `bench/lima/env.sh`                   | banc Lima ou prod ; voir « Prérequis & contexte » ci-dessus                                                         |
| État des **nœuds + composantes cluster** (drift + prochaine étape)    | `bootstrap/state.sh <hôte…>`          | SSH + kubectl ; hôtes **requis** (cf. `env.sh`) ; verdicts purs testés (`state-classify.sh` + `health-classify.sh`) |
| Tableau de bord du **durcissement** (preuves observables par hôte)    | `bootstrap/security/report.sh`        | [bootstrap/security/](../bootstrap/security/README.md)                                                              |
| Vérifier l'**épinglage des images** par digest d'index multi-arch     | `scripts/audit-image-digests.sh`      | invariant [ADR 0006](decisions/0006-matrice-de-versions-et-politique-de-bump.md)                                    |
| Vérifier la **fraîcheur des preuves** de banc (par chemin)            | `bench/lima/check-freshness.sh`       | [ADR 0042](decisions/0042-fraicheur-preuves-banc.md)                                                                |
| Détecter les pages Markdown **orphelines**                            | `python3 scripts/check_md_orphans.py` | [ADR 0029](decisions/0029-markdown-atteignable-doc.md)                                                              |

> **Garde-fou de cible (`EXPECT_CLUSTER`)** — les couches **cluster** de
> `state.sh` (Cilium, Rook-Ceph, StorageClasses, plateforme) auditent le
> `KUBECONFIG` ambiant. Pour qu'elles ne vérifient pas le banc en croyant viser
> la prod ([ADR 0053](decisions/0053-isolation-multi-cible-banc-prod.md)), elles
> **refusent** tout verdict (skip « cible non confirmée ») tant que
> `EXPECT_CLUSTER` n'est pas posée — l'empreinte du cluster visé (affichée par
> la 1ʳᵉ couche kubectl) ou une étiquette libre (`prod`/`lima`). Les couches
> **nœuds** (SSH) ne sont pas concernées.

## Tests end-to-end

| Pour…                                                                     | Commande                                              | Détails                                                   |
| ------------------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------- |
| Lancer **tous** les scénarios e2e (PASS/FAIL récapitulé)                  | `bench/scenarios/run-all.sh`                          | [bench/scenarios/README.md](../bench/scenarios/README.md) |
| Lancer **un** scénario (résilience, sécurité active, DataOps, GitOps, UI) | `bench/scenarios/NN-*.sh`                             | scénarios 01→29                                           |
| Smoke S3 réel (PUT/GET/DELETE) sur le RGW Ceph                            | `storage/ceph/storageClass/datalake/smoke-test.sh`    |                                                           |
| Tests des **fonctions pures** (bash)                                      | `pnpm test:shell` (bats)                              | `bench/unit/`                                             |
| Spike de latence Cluster Mesh (jetable)                                   | `bench/spikes/clustermesh-latency/{up,probe,down}.sh` |                                                           |

## Convergence hors Ansible (cas particuliers assumés)

Ces actes ne passent **pas** par Ansible, par nécessité
([ADR 0049](decisions/0049-doctrine-choix-outil-par-action.md)) :

| Pour…                                          | Commande                                      | Pourquoi pas Ansible                                                                          |
| ---------------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Poser Cilium (CNI) dans la VM                  | `bootstrap/cni.sh` (joué par l'orchestrateur) | tourne **dans** la VM, sans le dépôt                                                          |
| Wipe destructif des disques avant rebuild Ceph | `storage/ceph/cleanup.sh`                     | destructif, lancé **consciemment**                                                            |
| Seed du dépôt Gitea (org/repo/workflow)        | `bench/lima/gitea-init.sh`                    | **données**, pas convergence ([ADR 0044](decisions/0044-topologie-deploiement-banc-atlas.md)) |
| Anonymiser un `.env` en `.env-example`         | `python3 bootstrap/security/blur_env.py`      | texte/regex pur → Python                                                                      |

## Validation avant de pousser

| Pour…                                                                               | Commande          |
| ----------------------------------------------------------------------------------- | ----------------- |
| Lint complet (format, yamllint, shellcheck, kubeconform, ansible-lint, jscpd, bats) | `pnpm lint`       |
| Construire la doc (échoue sur lien mort)                                            | `pnpm docs:build` |

> **markdownlint** et **trivy** sont des jobs CI séparés non couverts par
> `pnpm lint` — les reproduire localement avant de pousser
> ([CONTRIBUTING.md](../CONTRIBUTING.md)).
