# Résultats — banc Lima

> Première exécution : **2026-06-04**, branche
> `feat/127-banc-lima-industrialise`, banc `test/lima/` sur Mac Apple Silicon +
> Lima 2.1.2, Kubernetes v1.34.8.

Honnêteté des Runs (ADR 0023) : ce fichier consigne le déroulé réel et les
_drifts_ (écarts banc, pas bugs du dépôt) rencontrés en montant le banc Lima de
bout en bout. Le banc Vagrant a son propre log :
[`../RESULTS.md`](../RESULTS.md).

## Le chemin — pourquoi ces drifts comptent

Ce fichier n'est pas une liste d'erreurs : c'est la **trace du travail patient**
qui rend le processus digne de confiance. Trois campagnes successives, **aucune
n'a fonctionné e2e du premier coup** :

- **L1–L11** (bootstrap K8s, #127) — porter kubeadm sur de vraies VM Lima.
- **L12–L20** (chaîne DataOps en shell, #148) — assembler CNPG/Dagster/Marquez.
- **L21–L33** (portage Ansible, #173) — refaire la chaîne en rôles idempotents,
  validée e2e le 2026-06-07 (lineage réel ingéré dans Marquez).

À chaque campagne, le même schéma : le code passe **tout le lint au vert**, puis
le **run réel from-scratch** révèle des drifts que seul un vrai cluster expose —
et on les verrouille un par un. C'est exactement pourquoi
[ADR 0034](../../docs/decisions/0034-validation-e2e-from-scratch.md) pose que
**la validation est un run e2e, pas le lint**. La synthèse par catégorie et le
tableau de bord (matériel + temps) :
[leçons des Runs](../../docs/architecture/lecons-des-runs.md).

> La répétition n'est pas un échec — c'est la **courbe de fiabilisation**.
> Chaque drift traversé devient un invariant durable et un savoir réutilisable
> pour les terrains suivants (cloud, x86, HA).

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

## Chaîne DataOps assemblée — phase `dataops-chain` (#148, étape 1.8) — 2026-06-05

> **✅ Validé e2e sur banc Lima arm64 (2026-06-05).** La chaîne
> `monitoring → CNPG → Dagster → Marquez` a été déployée et vérifiée
> **assemblée**, et le **lineage d'un run Dagster RÉEL est ingéré et visible
> dans Marquez** — preuve attendue par l'épopée #148.

Chaîne validée de bout en bout (run réel, mode rapide local-path) :

| Étape                                   | Résultat                                                                                                                                                                          |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| infra (up → bootstrap → storage-simple) | ✅ 3 nœuds Ready (K8s v1.34.8, Cilium 1.19.4 + WireGuard), PVC local-path Bound                                                                                                   |
| registry interne + 4 images arm64       | ✅ buildées (nerdctl+buildkitd) + poussées : `marquez`, `marquez-web`, `dagster-celery-k8s`, `dagster-openlineage-emit`                                                           |
| CNPG cluster `pg`                       | ✅ **Healthy 3/3**, bases `dagster`/`marquez`/`pgvector` créées                                                                                                                   |
| Dagster webserver + daemon              | ✅ Ready, storage CNPG (connexion authentifiée OK)                                                                                                                                |
| Marquez API + web                       | ✅ Ready, **migration Flyway OK** sur la base `marquez`                                                                                                                           |
| **émetteur jetable → lineage**          | ✅ run Dagster `toy_dataset` **RUN_SUCCESS** ; **ingéré dans Marquez** : `GET /api/v1/namespaces/dagster/jobs` → `totalCount: 1`, job `toy_dataset`, `latestRun.state: COMPLETED` |

> **Preuve #148** : `totalCount` passé de **0 → 1** après le run. Le job
> `toy_dataset` (namespace OpenLineage `dagster`) apparaît dans Marquez avec son
> dernier run `COMPLETED`. La chaîne Dagster → sensor OpenLineage → API Marquez
> → ingestion est prouvée assemblée, pas seulement verte-en-CI.

### Drifts rencontrés et correctifs (L12–L19)

Préfixe **L** = banc **L**ima. Plusieurs sont de **vrais bugs du livrable** (pas
des écarts banc) — corrigés dans le dépôt, pas seulement contournés.

| #   | Symptôme                                                               | Cause                                                                                           | Correctif                                                                                      |
| --- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| L12 | `bootstrap` exit 141 (SIGPIPE) — kubeconfig non récupéré               | un `cilium status \| grep` ferme le pipe avant `fetch_kubeconfig`                               | contournement : phase `kubeconfig` (le cluster était sain) ; à durcir dans le bootstrap        |
| L13 | **Pull `registry:80` HTTP échoue** : « HTTP response to HTTPS client » | containerd v2.2 (Debian 13) route le pull via le **transfer service** qui IGNORE certs.d        | `use_local_image_pull = true` dans containerd config (les 3 nœuds) — **fix racine**            |
| L14 | **CNPG bloqué** : « unknown plugin being required »                    | `cluster.yaml` exige le plugin Barman, non installé par `dataops-chain`                         | surcharge banc : retirer le bloc `plugins:` (backups hors périmètre lineage)                   |
| L15 | PVC `pg` Pending : « unbound immediate PersistentVolumeClaims »        | `cluster.yaml` hardcode `storageClass: standard`, absent du banc (local-path)                   | surcharge banc : `standard → local-path` (cf. #158)                                            |
| L16 | **Dagster « too many retries for DB connection »** (BUG LIVRABLE)      | `managed.roles` CNPG SANS `passwordSecret` → rôles créés sans mot de passe (`rolpassword` NULL) | **fix dépôt** : `passwordSecret` par rôle + `role-secrets.example.yaml`                        |
| L17 | Secret dérivé appli ≠ pwd réel du rôle                                 | nécessitait une recopie manuelle                                                                | résolu par L16 : `.example` de rôle et dérivés alignés sur les mêmes valeurs de test           |
| L18 | Build d'images impossible dans les VMs                                 | `git` absent + `buildkitd` (service présent mais `disabled`)                                    | `apt install git` + `systemctl enable --now buildkit` (à intégrer dans la prépa-build)         |
| L19 | **Run émetteur timeout** sur le POST OpenLineage (BUG LIVRABLE)        | aucune NetworkPolicy egress `dagster → marquez:5000` (seul l'ingress côté marquez existait)     | **fix dépôt** : `platform/network-policies/dagster/allow-marquez-egress.yaml`                  |
| L20 | webserver/daemon Dagster CrashLoop : « no [tool.dagster] block » (BUG) | l'orchestrateur vide est lancé sans workspace (`-w`)                                            | **fix dépôt** : ConfigMap `dagster-workspace` (`load_from: []`) monté + `-w` dans dagster.yaml |

### Enseignement (→ refonte Ansible)

Ces drifts en cascade viennent tous de la **couture shell/kubectl** de la couche
plateforme (le bootstrap, lui — en Ansible — n'en a produit qu'un, cosmétique).
Chacun (config containerd, secrets de rôles, attentes Ready, surcharges par
topologie) est nativement géré par Ansible (`kubernetes.core`, `lineinfile`,
gestion de secrets, templating). D'où la décision de **porter la couche
plateforme DataOps en rôles Ansible** (issue dédiée) : transformer ces drifts en
tâches idempotentes plutôt que les redécouvrir à chaque run.

## Chaîne DataOps en rôles Ansible — phase `dataops` (#173) — 2026-06-07

> **✅ Validé e2e sur banc Lima arm64 (2026-06-07), en MODE CEPH.** Le portage
> de la couche plateforme en rôles Ansible (`bootstrap/dataops.yaml`,
> [ADR 0033](../../docs/decisions/0033-orchestration-ansible-platform-dataops.md))
> a été monté de bout en bout **par le playbook** (plus de shell impératif) et
> le **lineage d'un run Dagster réel est ingéré dans Marquez**.
>
> ⚠️ **Honnêteté du Run (ADR 0023).** Le vert initial a été atteint **après 13
> correctifs intermédiaires** (drifts L21–L33) : la chaîne a échoué et été
> relancée de nombreuses fois avant de passer — fidèle au constat que rien ne
> marche e2e du premier coup
> ([ADR 0034](../../docs/decisions/0034-validation-e2e-from-scratch.md)). Un
> **run propre from-scratch d'une traite** (banc détruit puis remonté) a
> **ensuite confirmé** le résultat : `all` + `datalake` + `dataops` sans
> intervention, vert (cf. encadré « Run from-scratch confirmé » plus bas). Le
> dernier drift (L33, gate RGW) n'a d'ailleurs été révélé **que** par ce run
> propre — preuve qu'il fallait le faire.

Log brut **générisé** (preuve, ADR 0023) :
[`runs/2026-06-07-dataops-ansible.log`](runs/2026-06-07-dataops-ansible.log).
Séquence : `WITH_CEPH=1 all → datalake → dataops`.

| Étape                          | Résultat                                                                                           |
| ------------------------------ | -------------------------------------------------------------------------------------------------- |
| up → bootstrap → ceph → sc     | ✅ 3 nœuds Ready (K8s v1.34.8, Cilium 1.19.4), Ceph **HEALTH_OK**, SC Bound                        |
| datalake (RGW)                 | ✅ `CephObjectStore datalake`, `rook-ceph-rgw-datalake-a` 3/3 (cible S3 Barman)                    |
| registry + CRDs Gateway API    | ✅ via `platform-registry` (kubernetes.core), gate Ready ; containerd `use_local_image_pull`       |
| cert-manager                   | ✅ via `platform-cert-manager`, webhook Ready, CA interne posée                                    |
| CNPG cluster `pg` + **Barman** | ✅ **Healthy 3/3** AVEC plugin Barman → backups vers le **RGW Ceph** (OBC `cnpg-backups`)          |
| build images arm64             | ✅ `dagster-celery-k8s`, `marquez`, `marquez-web` buildées+poussées (sources copiées sur nœud)     |
| Dagster webserver + daemon     | ✅ Ready, storage CNPG (Secret dérivé du rôle CNPG)                                                |
| Marquez API + web              | ✅ Ready, migration Flyway OK                                                                      |
| **émetteur → lineage**         | ✅ run `toy_dataset` **COMPLETED** ingéré : `namespaces/dagster/jobs` → job présent, run COMPLETED |

> **Preuve #173/#148 par Ansible** : toute la chaîne est désormais une commande
> reproductible (`run-phases.sh dataops` → `ansible-playbook dataops.yaml`). Le
> lineage est prouvé assemblé, et Barman archive vers le RGW Ceph (vs le banc
> #148 qui retirait le plugin, drift L14 — éliminé à la racine).

### Drifts rencontrés et correctifs (L21–L32)

Drifts du **portage Ansible** + de l'**exécution depuis l'hôte / mode Ceph**.
Tous corrigés dans le dépôt ; aucun n'est un bug de conception — ce sont des
écarts d'environnement que seul un run e2e révèle.

| #   | Symptôme                                                         | Cause                                                                                   | Correctif                                                                    |
| --- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| L21 | `ansible_user_id is undefined` (play cluster)                    | `gather_facts: false` sur le play localhost, requis par `audit-log`                     | retrait de l'audit-log du play cluster (cf. L22)                             |
| L22 | `sudo: a password is required` (audit-log sur localhost)         | `audit-log` écrit un log SYSTÈME (`become`) — n'a pas de sens sur le poste              | audit-log retiré de `dataops.yaml` (reste sur les playbooks de nœuds)        |
| L23 | `SSL: CERTIFICATE_VERIFY_FAILED` (get_url/k8s)                   | le Python d'Ansible (Homebrew) n'utilise pas le CA système                              | `SSL_CERT_FILE` via certifi, résolu en pré-tâche par le bon interpréteur     |
| L24 | volet `node` du rôle registry tourne sur localhost               | `import_role` charge tout le rôle ; le tag ne filtre pas les blocs internes             | rôle scindé `cluster.yaml`/`node.yaml`, importés via `tasks_from`            |
| L25 | Secret dérivé : « namespaces postgres not found »                | secrets posés avant que `cluster.yaml` ne crée le namespace                             | namespace `postgres` créé en premier dans `platform-cnpg`                    |
| L26 | build : `dict has no attribute 'clone_subdir'`                   | ternary Jinja évalue les deux branches (image `local` sans `clone_subdir`)              | `default('')` sur les attributs optionnels                                   |
| L27 | build : `Dockerfile no such file or directory` sur nœud          | banc Lima `mounts: []` → sources du dépôt absentes de la VM                             | copier contextes/Dockerfiles sur le nœud avant build                         |
| L28 | build `marquez-web` **OOM-killed** (rc 137)                      | webpack/npm sature la VM 5 GiB (déjà k8s+Ceph+CNPG)                                     | `VM_MEMORY` 5 → **8 GiB**                                                    |
| L29 | operator CNPG CrashLoop après reboot (RAM)                       | reboot cp1 → Cilium pas reconvergé → ClusterIP plugin injoignable                       | artefact de reboot (cf. réserve « restore non fidèle ») ; restart operator   |
| L30 | pods Dagster `ImagePullBackOff registry:80` (HTTP/HTTPS)         | containerd des workers pas rechargé après pose de la config insecure-reg.               | restart containerd sur les nœuds (handler à fiabiliser)                      |
| L31 | preuve lineage : image émetteur absente du registry              | l'émetteur jetable n'était pas dans `build_images` (hors prod, ADR 0022)                | `build_emitter_image=true` au banc (câblé conditionnellement)                |
| L32 | « aucun job ingéré (1 → 1) » alors que le lineage est là         | le prédicat exigeait un **delta** ; le run est idempotent (namespace gardé)             | `classify_marquez_ingest` teste la **présence** (`after >= 1`) + bats à jour |
| L33 | `RGW datalake pas Ready` alors que les 3 pods sont `2/2 Running` | le gate `datalake` testait `readyReplicas == 1`, or le CephObjectStore a `instances: 3` | gate `>= 1` (au moins une instance up) — révélé par le run **from-scratch**  |

> **Run from-scratch confirmé (2026-06-07).** Après correction de L33, le banc a
> été **détruit puis remonté d'une traite** : `WITH_CEPH=1 all` est passé sans
> intervention (socle + Ceph), et `dataops` a abouti **vert (0 échec)** —
> `dataops` mesuré à **13m37s** (M3 Max, 8 GiB/VM), lineage `0 → 1` ingéré dans
> Marquez. Total banc complet ≈ **30 min**. Métriques émises par `run-phases.sh`
> (cf. [tableau de bord](../../docs/architecture/lecons-des-runs.md)).

### Enseignement

Le portage Ansible **tient sa promesse** : les drifts L12-L20 (couture shell)
ont disparu — la chaîne se monte d'une commande idempotente. Les nouveaux drifts
L21-L32 sont d'une autre nature : **modèle d'exécution** (localhost vs nœud :
L21-L24), **isolation/ressources du banc** (L27-L30) et **harnais de test**
(L31-L32). Aucun n'est un défaut du livrable — ils sont corrigés une fois et
deviennent des invariants du run. Barman archive désormais vers le **RGW Ceph**
(L14 éliminé à la racine), au prix d'un banc en **mode Ceph** (8 GiB/VM).

## Observabilité paramétrable — phase `monitoring` (#158/#186) — 2026-06-07

> **✅ Validé e2e sur banc Lima arm64 (2026-06-07), sur les DEUX profils S3.**
> Portage en rôles Ansible de `kube-prometheus-stack` (Prometheus + Alertmanager
>
> - Grafana), `loki` et `seaweedfs`
>   ([ADR 0036](../../docs/decisions/0036-backing-s3-unique-rgw.md)), avec
>   **storageClass paramétrable** (#158) et **backing S3 par topologie** (#186).
>   Deux runs from-scratch du namespace : profil **léger** (local-path +
>   SeaweedFS) **puis** profil **Ceph** (rook-ceph + RGW via OBC).
>
> ⚠️ **Honnêteté du Run.** 6 correctifs intermédiaires (drifts **L34–L39**),
> **tous de code/universels**. Fait notable validant la stratégie deux-bancs : 2
> drifts (**L38/L39**) **n'apparaissent qu'en RGW** — le profil léger (creds
> admin SeaweedFS) les masquait. C'est la preuve concrète qu'un chemin de code
> partagé doit être validé **sur chaque backing réellement employé** (cf.
> [Leçons des Runs](../../docs/architecture/lecons-des-runs.md), cat. 7).

| Profil         | storageClass PVC             | Backing S3 Loki                         | Verdict                                      | Temps `monitoring` |
| -------------- | ---------------------------- | --------------------------------------- | -------------------------------------------- | ------------------ |
| Léger (rapide) | `local-path`                 | **SeaweedFS** (`s3` ns, buckets nommés) | ✅ Prometheus/AM/Grafana/Loki Ready, S3 réel | **3m05s**          |
| Ceph (fidèle)  | `rook-ceph-block-replicated` | **RGW** via OBC (bucket unique)         | ✅ idem, Loki `started` sur le bucket OBC    | **2m53s**          |

> **Preuve #158** : tous les storageClass codés en dur sont désormais paramétrés
> (registry, CNPG, monitoring, Loki) — PVC Bound en `local-path` **et** en
> `rook-ceph-block-replicated` selon la topologie, sans modifier le code.
> **Preuve #186** : Loki tourne en **profil S3 réel** (jamais `filesystem`) sur
> SeaweedFS **et** sur RGW — même chemin de code, endpoint et bucket résolus par
> variable.

### Drifts rencontrés et correctifs (L34–L39)

| #   | Symptôme                                             | Cause                                                                                           | Correctif                                                                                  | Profil  |
| --- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------- |
| L34 | CRDs monitoring rejetées par le module `k8s`         | enum `- =` non quoté → PyYAML SafeLoader rejette (tag `value`)                                  | appliquer les CRDs via `kubectl apply --server-side` (Go), pas le module                   | les 2   |
| L35 | « no matches for cert-manager.io/v1.Certificate »    | le manifeste monitoring contient des `Certificate`/`Issuer`                                     | `platform-cert-manager` appliqué **avant** monitoring (dans `monitoring.yaml`)             | les 2   |
| L37 | cert-manager **CrashLoop** au démarrage              | tourne avec `--enable-gateway-api` mais les CRDs Gateway API sont absentes                      | le rôle `platform-cert-manager` pose lui-même les CRDs Gateway API (1.4.1)                 | les 2   |
| L36 | `PrometheusRule` rejetés en masse (HTTP 500 webhook) | appliqués avant que l'operator (porteur du webhook) soit Ready                                  | **deux passes** : stack sauf PrometheusRule → attente operator → PrometheusRule            | les 2   |
| L38 | Loki **CrashLoop** `NoSuchBucket` (compactor)        | l'OBC Rook n'expose qu'**un bucket auto-nommé** + creds restreints → buckets nommés impossibles | en RGW : résoudre le bucket OBC, l'employer pour chunks **et** ruler ; init-buckets skippé | **RGW** |
| L39 | init-buckets « prêt » alors que rien n'est créé      | gate faux : `grep make_bucket` matchait aussi `make_bucket **failed**`                          | script réécrit (`set -eu`) : échec franc si le bucket n'est ni créé ni déjà présent        | **RGW** |

### Enseignement

Le paramétrage **tient** : un seul code, deux topologies (#158/#186). La leçon
forte est la **portée des drifts** : L34–L37 cassaient les deux profils (ordre
CRD/webhook/contrôleur — invariants d'admission), mais **L38/L39 ne se révèlent
qu'en RGW**. Le banc léger, avec ses creds admin SeaweedFS, validait une version
**plus permissive** que la prod. D'où la règle inscrite en
[ADR 0036](../../docs/decisions/0036-backing-s3-unique-rgw.md) : un changement
S3 validé en léger **doit** être revalidé en Ceph avant prod.

## Re-validation from-scratch des deux bancs (2026-06-08)

> **But** : confirmer **zéro drift résiduel** après les chantiers #158/#186, par
> deux runs **from-scratch d'une traite** (banc détruit puis remonté), un par
> profil ([ADR 0034](../../docs/decisions/0034-validation-e2e-from-scratch.md)).

Un **drift de plus** est apparu — précisément ce que cherche un from-scratch :

| #   | Symptôme                                         | Cause                                                                                                                                                                                         | Correctif | Portée |
| --- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------ | ------------------------------------- | ---- |
| L40 | `platform-prereqs` meurt (EXIT 1) sur banc léger | `set -e` + `reg_ip=$(kubectl get svc registry …)` : sans le ns `registry` (monitoring seul, pas de dataops), `kubectl` sort en 1 → l'assignation tue le script avant le garde `[ -z reg_ip ]` | `…        |        | true` sur l'assignation (skip propre) | code |

> **L40 n'apparaît que sur le profil léger** (monitoring sans dataops, donc sans
> registry) : les runs précédents montaient toujours le registry via `dataops`,
> qui masquait le bug. Encore un drift qu'**un seul profil révèle** (cf.
> [Leçons des Runs](../../docs/architecture/lecons-des-runs.md), cat. 7).

Verdicts (M3 Max, 8 GiB/VM, `multi-node-3` arm64, local) :

| Profil | Séquence from-scratch                                                  | Verdict                    | Temps notables                                 |
| ------ | ---------------------------------------------------------------------- | -------------------------- | ---------------------------------------------- |
| léger  | `all → platform-prereqs → monitoring`                                  | ✅ **0 drift** (après L40) | up 3m14s · bootstrap 6m40s · monitoring ~3m    |
| Ceph   | `WITH_CEPH=1 all → datalake → platform-prereqs → dataops → monitoring` | ✅ **0 drift**             | ceph 3m09s · dataops 14m33s · monitoring 2m34s |

Les **scénarios d'observabilité 24–26** (Prometheus scrape, alerte `Watchdog`
firing, Loki round-trip LogQL) ont été **écrits puis passés au vert** sur le
banc Ceph (profil RGW) — la stack monitoring passe de _montée_ à _éprouvée_.

## DataOps sans Ceph — backing S3 factorisé (2026-06-08)

> **But** : rendre la chaîne DataOps (CNPG/Barman) **montable sans Ceph**, en la
> découplant du RGW via un rôle S3 factorisé `platform-s3-bucket` (backing `rgw`
> | `seaweedfs`,
> [ADR 0036](../../docs/decisions/0036-backing-s3-unique-rgw.md)). Loki et CNPG
> partagent désormais cette brique (fin de la duplication OBC/creds).

Validé e2e **sur les deux profils** (M3 Max, `multi-node-3` arm64, local) — le
refactor S3 ne casse pas le chemin prod (RGW) **et** débloque le banc léger :

| Profil | Backing S3 (CNPG + Loki)  | Chaîne DataOps                                | Temps notables                                              |
| ------ | ------------------------- | --------------------------------------------- | ----------------------------------------------------------- |
| léger  | **SeaweedFS** (sans Ceph) | ✅ CNPG sain + Dagster + Marquez, lineage 0→1 | bootstrap 6m31s · monitoring 3m05s · dataops **11m01s**     |
| Ceph   | **RGW** (OBC)             | ✅ idem (non-régression rgw), lineage 0→1     | ceph 3m09s · datalake 1m31s · dataops ~14m · monitoring ~3m |

Drifts de cette campagne (détail :
[`registre-drifts.yaml`](../../docs/architecture/registre-drifts.yaml)) :
**L41** (storageClass registry/CNPG non aligné au profil → paramétré),
**L42/L43** (single-node : gate Dagster lent, éviction CNPG disque — _caducs_,
topologie abandonnée ADR 0040), **L44** (dépendance à `WITH_CEPH` en variable
d'env — _ouvert_ : dataops/monitoring devraient détecter le profil).

## Métrologie du banc — run from-scratch (#216/#217/#219, 2026-06-08)

> **✅ Socle validé from-scratch en mode Ceph (2026-06-08), branche
> `feat/banc-metrologie-cache`.** Première preuve consignée **automatiquement**
> dans [`runs-history.yaml`](runs-history.yaml) par `run-phases.sh` (plus de
> saisie manuelle). Log brut :
> [`runs/2026-06-08-banc-metrologie-e2e.log`](runs/2026-06-08-banc-metrologie-e2e.log).

`NO_CACHE=1 WITH_CEPH=1 run-phases.sh all` — up → bootstrap → ceph → sc, monté
de zéro (preuve ADR 0034) :

| Phase     | Durée      | Gate                                          |
| --------- | ---------- | --------------------------------------------- |
| up        | 2m45s      | disques `vd*` présents sur les 3 VMs          |
| bootstrap | 6m39s      | 3 nœuds Ready (Cilium 1.19 + WireGuard)       |
| ceph      | 3m09s      | **9 OSD up, HEALTH_OK**                       |
| sc        | 0m06s      | PVC test Bound (`rook-ceph-block-replicated`) |
| **total** | **12m39s** | entrée `runs-history.yaml` appendée           |

- **#219 cache du socle** prouvé : un second `WITH_CEPH=1 run-phases.sh all`
  (socle inchangé, VMs up) a **sauté up+bootstrap+ceph+sc** et rendu la main en
  **~1 s** (clé `socle:ceph:…` inchangée). `NO_CACHE=1` force le rebuild
  (preuve).
- **#217 métriques** échantillonnées depuis Prometheus (fenêtre 900 s, profil
  Ceph) : **CPU 272 cœur·s, RAM pic 7606 MiB, moy 7489 MiB**.

Drifts de cette campagne :

- **L44 reproduit** (déjà _ouvert_) : la phase `monitoring` lancée **sans
  propager `WITH_CEPH=1`** a choisi le profil léger (SeaweedFS/local-path) sur
  un cluster dont le `default storageClass` est Ceph → PVC `local-path`
  **Pending** (`unbound immediate PersistentVolumeClaims`). Confirme l'utilité
  de l'auto-détection de profil que L44 réclame. Pas un bug du livrable — un
  oubli d'invocation, exactement le piège que L44 documente.
- **L47** (harnais, _corrigé_) : `metro_sample_prometheus` interrogeait
  Prometheus via `kubectl exec` dans son pod **distroless** (ni `wget` ni `sh` —
  même piège que le drift #14 etcd) → métriques toujours `?`. Et ses logs
  partaient sur **stdout**, capturé dans le bloc YAML → **pollution ANSI du
  `runs-history.yaml`**. Correctif : requête via pod **busybox éphémère**
  ciblant le Service `prometheus-operated` ; tous les logs routés sur
  **stderr**. Couvert par deux tests bats anti-régression (stdout sans ANSI,
  Prometheus absent → stdout vide).

## Socle GitOps — Gitea + Argo CD sans Ceph (#230, 2026-06-09)

> **✅ Socle GitOps validé sur banc (2026-06-09), branche
> `feat/230-gitea-banc-atlas`.** Première mise en service d'**Argo CD par le
> banc** (jusqu'ici posé en `kubectl` manuel) + **Gitea** (forge git intra-banc
> air-gapped, ADR 0044). Profil **léger** : `local-path`, **sans Ceph**.

`run-phases.sh gitops` (par-dessus `up → bootstrap → storage-simple`) — déploie
Gitea puis Argo CD via `bootstrap/gitops.yaml` :

| Brique                 | Gate                         | Résultat                        |
| ---------------------- | ---------------------------- | ------------------------------- |
| Gitea (rootless arm64) | `deploy/gitea` Ready         | ✅ 1/1 (image par digest index) |
| Argo CD                | `deploy/argocd-server` Ready | ✅ 7 pods 1/1 (après fix L48)   |

- **Image Gitea rootless arm64** : démarre sans souci (digest d'**index
  multi-arch** ADR 0006 — pas de `exec format error`).

Drifts de cette campagne :

- **L48** (livrable, _corrigé_) : `argocd-server` restait `0/1` — tous les
  composants Argo CD en `CreateContainerConfigError`
  (`secret "argocd-redis" not found`). Cause : l'initContainer `secret-init` de
  `argocd-redis` **crée** ce Secret via l'**API K8s**, mais échouait (exit 20)
  car la NetworkPolicy **préexistante**
  `platform/network-policies/argocd/allow-egress.yaml` autorisait l'egress
  apiserver via `to.ipBlock 0.0.0.0/0`. **Sous Cilium, un `ipBlock` EXCLUT les
  entités réservées** (`host`/`kube-apiserver`) → l'apiserver (ClusterIP
  `10.96.0.1:443` ET endpoint `:6443`) était injoignable. Correctif : egress
  **sans `to:`** (idiome du dépôt, calque `dagster/allow-apiserver-egress`) +
  ports 443 et 6443. Bug **latent** révélé par la 1re mise en service d'Argo CD
  par le banc (avant : `kubectl` manuel sur un datapath différent). Vérifié :
  `10.96.0.1:443` joignable, Secret créé, cascade résolue, tous pods `1/1`.
- **L49** (harnais, _corrigé_) : un `all` relancé sur **socle en cache** (#219)
  consignait dans `runs-history.yaml` une entrée « run complet » avec `total_s`
  tronqué et `phases` partielles (`gitops: 12` seul) — **fausse preuve** pour le
  garde-fou de fraîcheur (ADR 0042). Cause : `record_full_run` appelé
  inconditionnellement, même sur cache hit (up/bootstrap/storage sautés, absents
  de `PHASE_DURATIONS`). Correctif : ne consigner que les runs **from-scratch**
  (flag `socle_built`) ; run sur cache → message, pas d'entrée. Fausse entrée
  retirée.

> **✅ Run from-scratch consigné (2026-06-09, commit `24cb7e5`).**
> `NO_CACHE=1 run-phases.sh all` monté de zéro :
> `up 169s → bootstrap 406s → storage-simple 13s → gitops 75s` (total **663s**,
> profil local-path). Entrée appendée automatiquement dans
> [`runs-history.yaml`](runs-history.yaml) — preuve ADR 0034/0042 (et validation
> du correctif L49 : l'entrée est complète, pas tronquée).

## Chemins d'installation + scénarios atlas (#237, 2026-06-09)

> **✅ Chemin `atlas` validé from-scratch (commit `98e7467`).** ADR 0045
> implémenté : cibles `socle`/`atlas`/`cluster`.
> `NO_CACHE=1 run-phases.sh atlas` de zéro :
> `up 194s → bootstrap 402s → storage-simple 11s → monitoring 188s → gitops 75s → dataops 694s`
> (total **1564s**, local-path, RAM pic 9191 MiB). Première exécution de l'ordre
> **monitoring AVANT dataops** : SeaweedFS posé par monitoring, consommé par
> dataops — ordre validé. Consigné dans
> [`runs-history.yaml`](runs-history.yaml).

**Scénarios pertinents joués sur le banc `atlas` (9/9 PASS)** — preuve de
comportement par-dessus les gates d'intégration (sous-ensemble applicable au
profil local-path, cf.
[plan de tests](../../docs/architecture/plan-de-tests.md)) :

| #   | Scénario                     | Résultat                                            |
| --- | ---------------------------- | --------------------------------------------------- |
| 10  | Pod Security admission       | ✅ pod dangereux rejeté, conforme admis             |
| 11  | NetworkPolicy default-deny   | ✅ egress coupé, allow-dns ciblé rouvre             |
| 12  | securityContext runtime      | ✅ non-root + rootfs RO vérifiés au runtime         |
| 17  | Pod d'évasion → PSA          | ✅ hostPath/hostPID/hostIPC rejetés                 |
| 18  | Exfiltration → NetworkPolicy | ✅ canal coupé, DNS légitime préservé               |
| 23  | Marquez ← OpenLineage        | ✅ lineage d'un run Dagster réel ingéré             |
| 24  | Prometheus scrape + Grafana  | ✅ 22 targets UP, Grafana health ok                 |
| 25  | PrometheusRule → alerte      | ✅ `Watchdog` firing (pipeline d'alerting vivant)   |
| 26  | Loki ← LogQL                 | ✅ round-trip push → LogQL (+ backing S3 SeaweedFS) |

Drift de cette campagne :

- **L50** (harnais, _corrigé_) : `run-all.sh` lancé avec un **KUBECONFIG en
  chemin relatif** faisait échouer/skipper tous les scénarios
  (`localhost:8080 refused`) — le runner fait `cd` dans son dossier, invalidant
  le chemin relatif. Correctif : résoudre `KUBECONFIG` en **absolu avant le
  `cd`**. Validé (ONLY=24 avec KUBECONFIG relatif passe).

## Chaîne GitOps → workflows atlas — scénario 27 prouvé (#231, 2026-06-09)

> **✅ Cœur du banc atlas prouvé sur banc (2026-06-09), branche
> `feat/231-scenario27-gitops-dataops`.** Un **push sur Gitea déclenche, via
> webhook, le déploiement par Argo CD du workflow atlas**, qui lance un run
> Dagster réel dont le **lineage est ingéré par Marquez**. Objectif ADR
> 0044/0045 atteint : atlas lance sa GitOps qui pilote toute la chaîne DataOps.

`run-phases.sh gitops-seed` (init dépôt Gitea + webhook + Application) puis
`STRICT_GITOPS=1 ONLY='27' run-all.sh` — **scénario 27 PASS** :

| Étape (gate)                           | Résultat                                                       |
| -------------------------------------- | -------------------------------------------------------------- |
| Gitea + Argo CD + Application présents | ✅                                                             |
| push commit de déclenchement (Gitea)   | ✅ nouveau commit                                              |
| Argo CD réconcilie via webhook         | ✅ **nouvelle révision** (fc6d860 → 57ff5f4), `Synced/Healthy` |
| run Dagster + lineage Marquez          | ✅ Job `Complete`, lineage ingéré                              |

Drifts de cette campagne (détail : registre-drifts.yaml) — **4 bugs du livrable
révélés par le run réel**, corrigés dans les manifestes versionnés (appliqués
par le rôle Ansible `platform-argocd`, plus de `kubectl patch`) :

- **L51** : `sourceRepos` `/*` → `/**` (le glob Argo ne traverse pas les `/`).
- **L52** : egress interne argocd (controller → repo-server:8081 / redis) — le
  default-deny coupait le trafic intra-Argo.
- **L53** : egress repo-server → Gitea (namespaceSelector) — `ipBlock 0.0.0.0/0`
  exclut les pods cluster sous Cilium (même piège que L48).
- **L54** : workflow jouet sans securityContext durci (Dagster écrit son
  DAGSTER_HOME ; aligné sur l'émetteur de référence ; durcissement = #234).

> **Note** : l'update Contents API de `gitea-init.sh` (PUT avec sha) a été
> soupçonné défaillant en cours de run, mais **vérification faite, il
> fonctionne** (un changement local du workflow produit bien un commit
> `update workflow` dans Gitea, contenu mis à jour). La fausse piste venait d'un
> comptage erroné (`grep readOnlyRootFilesystem` matchait les **commentaires**
> du fichier, pas le YAML effectif) et de l'idempotence (relancer sans
> changement ne crée pas de commit — comportement attendu). Pas de bug d'update.
> Le correctif « push vérifié » (commit de la campagne) échoue désormais
> explicitement si un PUT/POST ne renvoie pas de commit, ce qui aurait rendu un
> vrai défaut visible.
