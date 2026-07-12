# 0056 — Modèle déclaratif unifié des topologies (un fichier décrit, Ansible converge)

> ⚠️ **Amendé par
> [ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md)
> (2026-07-11).** Deux points. (1) Le champ **`target_kind`** (prod/lima) cité
> ici comme garde-fou d'intention a été **supprimé** : l'isolation passe à
> l'**identité** (`stack_id`) et la classe **`terrain`**. Le banc et la prod ne
> se distinguent plus « au `target_kind` près » mais par leur identité. (2) La
> frontière **décrire / converger** posée en §5/§7 est enfin **matérialisée dans
> la CLI** : le verbe `up` (qui provisionnait _et_ installait) est scindé en
> **`provision`** (crée le substrat) et **`install`** (converge, idempotent) —
> l'invariant « installer ne re-provisionne jamais » devient explicite. Le corps
> de cet ADR reste valide ; seuls ces deux points sont mis à jour par 0108.

## Contexte

[ADR 0023](0023-plateforme-exemple-generique.md) acte la **vision** d'un
catalogue de topologies « modèle Pulumi/Terraform : plusieurs infra déclarées,
une seule activée » — mais en empruntant le **modèle d'usage**, pas la mécanique
d'état réconcilié ; la « restructuration par profils de topologie » y est
explicitement **reportée à un chantier séparé**. Ce chantier n'a jamais été fait
: aujourd'hui une topologie est **impérative et éparpillée**.

Concrètement, une topologie complète est déterminée par **~25 variables
réparties sur 6 lieux non synchronisés** :

1. **`NODES` (bash, `bench/lima/run-phases.sh`)** — nœuds/rôles du banc, **codés
   en dur**, non paramétrables ; seule encode-machine de « combien de nœuds,
   quels rôles ».
2. **Inventaire Ansible** (`bootstrap/hosts.yaml` réel / `.example` / `.work/`
   généré) — **re-déclare** les mêmes nœuds/rôles + `target_kind`,
   `ansible_user`, `control_plane_ip`…
3. **`defaults/main.yaml` des rôles `platform-*`** — valeurs **prod
   implicites**.
4. **Drapeaux `WITH_CEPH` / `WITH_HARDENING`** (env) — profils binaires qui
   **dérivent** un faisceau de `-e`.
5. **`-e` en ligne** (banc) — surcharges effectives, **aucun group_vars de banc
   versionné**.
6. **Prose ADR + `docs/architecture/matrice-catalogue.md`** — le tuple
   `arch/terrain/topologie/profil`
   ([ADR 0039](0039-nomenclature-axes-catalogue.md)) et les statuts, **en
   tableaux non exécutables**.

**Frein.** Pas de source unique de vérité : répondre « qu'est-ce que
`multi-node-3` Ceph durci ? » exige de lire bash + inventaire + 6 `defaults` +
le `case` de dispatch + 3 ADR. La **double déclaration** nœuds/rôles (`NODES` ↔
inventaire) risque l'incohérence silencieuse — masquée au banc (régénéré depuis
`NODES`), **sans équivalent en prod** (inventaire édité à la main). Changer le
nombre/rôle de nœuds = **éditer du bash**. `multi-node-4` et `ha-3cp` n'ont
**aucun encodage** : ce sont des cibles « à outillage dédié » jamais outillées.

**Déclencheurs récents** (run de production `cluster-prod`, 4 nœuds) :

- L'**exposition réseau dépend de l'admin réseau** : la plage LB-IPAM
  (`10.0.0.0/22`) est un « TODO admin réseau »
  ([ADR 0020](0020-exposition-reseau-tout-cilium.md)) ; on ne la connaît pas
  d'avance. Il faut un **repli sans plage d'IP** (NodePort sur un nœud),
  aujourd'hui écarté par 0020.
- Le **banc ne reproduit PAS l'exposition prod** (juste un `portForward` de
  l'API) → ce qu'on prouve au banc n'est pas ce qui tourne en prod (tension
  [ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md)).
- Des dimensions **manquent** au modèle (VIP HA `control_plane_vip` pour
  `ha-3cp`, ADR 0047/0055 ; mode d'exposition).

## Décision

**Une topologie se décrit dans UN fichier déclaratif unique (`topology.yaml`),
source de vérité versionnée. Un générateur SANS ÉTAT en dérive les entrées que
les outils consomment déjà (inventaire Ansible, group_vars de profil, et —
terrain local — la table de nœuds + profils Lima). Ansible reste le moteur de
convergence impératif/idempotent. On n'introduit AUCUN moteur à état (Pulumi,
Terraform) PAR-DESSUS la couche k8s/plateforme** — non par dogme, mais parce
qu'**il y a déjà deux moteurs à état qui possèdent ces ressources** (voir §7).
L'exclusion ne vaut **que** pour cette couche : OpenTofu reste légitime pour le
provisioning IaaS (VM cloud), où l'outil possède réellement les ressources via
une API ([ADR 0032](0032-opentofu-provisioning-cloud.md)).

### 1. Le fichier `topology.yaml` — source unique

Versionné en `topologies/socle.example.yaml` (générique,
[ADR 0023](0023-plateforme-exemple-generique.md)), réel gitignoré. Il capture
les dimensions aujourd'hui éparpillées, regroupées :

- **`catalog`** : `arch`, `terrain` (local/cloud/baremetal), `topology`
  (multi-node-3/4, ha-3cp…), `profile` (base⊂store⊂obs⊂dataops), `status`
  (buildé/cible/spike) — le tuple
  [ADR 0039](0039-nomenclature-axes-catalogue.md) hissé en données.
  **Description par profil, avec défauts.** On déclare une **intention** de haut
  niveau (`profile: dataops`) et l'outil **déduit** ce qu'elle implique en amont
  : l'inclusion cumulative `base ⊂ store ⊂ obs ⊂ dataops`
  ([ADR 0039](0039-nomenclature-axes-catalogue.md)) fixe les briques requises
  (un `dataops` exige le stockage, l'observabilité, etc.) dans le bon ordre
  (graphe de dépendances, voir §2). Chaque dimension non précisée prend une
  **valeur par défaut** (Ceph répliqué, exposition `lb-ipam`, hardening
  `false`…) ; les **variantes** restantes (backend `ceph` vs `local-path`,
  exposition…) sont à fixer, **une par défaut**. Minimum à écrire :
  `{ profile, terrain }` — tout le reste se dérive (invariant : profil prod →
  entrées byte-identiques à l'actuel, §3).
- **`nodes[]`** : `{name, roles[], ansible_host?, disks?}` — **une seule**
  déclaration nœuds/rôles (résorbe la double déclaration `NODES` ↔ inventaire).
  `roles` est une **liste** : un nœud peut cumuler `control`+`worker`+`storage`
  (hyperconvergence
  [ADR 0007](0007-hyperconvergence-control-plane-osd.md)/[0055](0055-ha-3cp-hyperconverge-promotion-in-place.md)).
- **`network`** : `control_plane_endpoint`, `control_plane_port`,
  `control_plane_ip?`, et **`control_plane_lb?`** = le **point d'entrée unique
  devant les control planes** (dimension aujourd'hui INEXISTANTE, requise dès
  qu'il y a > 1 CP —
  [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md)/[0055](0055-ha-3cp-hyperconverge-promotion-in-place.md)).
  Un cluster HA **exige** un tel LB devant ses 3 API servers ; `topology.yaml`
  en déclare le **mécanisme** :
  - `kube-vip` mode **ARP/failover** (VIP active/passive — défaut retenu,
    suffisant pour un control plane) ;
  - `kube-vip` mode **control-plane LB** (répartition active entre les 3 API) ;
  - `external` (LB L4 du réseau de l'organisation,
    [ADR 0055](0055-ha-3cp-hyperconverge-promotion-in-place.md)). En mono-CP, ce
    champ est **vide** (pas de LB — l'endpoint pointe le seul CP,
    [ADR 0002](0002-control-plane-unique-avec-endpoint.md)).
- **`network` (suite)** : `pod_subnet?`/`service_subnet?`/`cluster{name,id}?`
  (opt-in [ADR 0027](0027-bootstrap-parametre-multi-cluster.md), défauts vides =
  prod).
- **`exposition`** : **`{mode: lb-ipam | nodeport | none, plage?, interface?}`**
  — NOUVELLE dimension (voir §4).
- **`storage`** : `backend` (ceph/local-path), `osd_expected?`,
  `metadata_device?`, disques bruts (banc).
- **`persistence`** : **`{mode: full | bounded | ephemeral}`** — curseur global
  de rétention des données applicatives, frère d'`exposition`/`storage`, dérivé
  sur six briques infra ([ADR 0109](0109-persistance-declarative-topologie.md)).
- **`hardening`** : `{enabled, tags?}` — axe orthogonal
  ([ADR 0045](0045-chemins-installation-banc-couches.md) §3), enfin dans le
  modèle.
- **`resources`** (terrain local) : `cpus`, `memory`, `disk` — remplace les
  `VM_*` dérivés ; `cpus` enfin paramétrable (codé en dur aujourd'hui).
- **`target_kind`** (prod/lima) — garde-fou d'intention
  ([ADR 0053](0053-isolation-multi-cible-banc-prod.md)).

### 2. Un outil unique en **Python**, trois façades, sans état

Le générateur est un **outil Python** (`uv`/`ruff`/`pytest`,
[ADR 0017](0017-langage-des-scripts.md)/[0049](0049-doctrine-choix-outil-par-action.md)
: la logique — parse + validation de schéma + génération + interrogation de
l'état — est **non triviale**, donc Python testé, pas du bash). **Python et non
Go** (le meilleur TUI du marché, bubbletea) :
[ADR 0017](0017-langage-des-scripts.md) proscrit le portage Go opportuniste, Go
serait un **6ᵉ langage** (coût de diversité,
[ADR 0049](0049-doctrine-choix-outil-par-action.md)), et `textual`/`rich`
couvrent amplement le besoin de TUI ; l'écosystème (`uv`, `pyyaml`, lib
`kubernetes`) est **déjà présent**.

**Fortement couplé à Ansible.** Python est l'écosystème **natif** d'Ansible :
l'outil lit/écrit l'inventaire et les group_vars dans les mêmes structures, rend
les mêmes templates Jinja2, et **pilote les playbooks via `ansible-runner`**
(lib Python officielle : exécution programmatique, events et résultats
structurés en JSON — pas de `subprocess` fragile). C'est ce couplage qui rend
l'assistant « que faire ensuite » réellement actionnable (cf. ci-dessous).
**Frontière à tenir** (§5) : l'outil **orchestre** Ansible (lance, lit les
résultats, suggère) ; **Ansible reste le moteur de convergence idempotent** —
l'outil ne ré-implémente jamais la convergence ni un état réconcilié (ce que
[ADR 0023](0023-plateforme-exemple-generique.md) refuse).

**Un cœur, trois façades** sur la même logique :

- **CLI / CI** (`typer`/`click`, non-interactif) : `generate`, `validate`,
  `status`, `diff` — utilisable en pipeline CI (`--no-input`, codes de sortie).
- **TUI / REPL interactif** (`textual`) : **assistant guidé** qui déroule la
  boucle **décrire → diff → converger → vérifier** : (1) lit l'état voulu
  (`topology.yaml`) et l'état réel (lib `kubernetes` + `state.sh`), (2)
  **calcule le diff** (quelles phases manquent), (3) **suggère / lance** le bon
  playbook Ansible via `ansible-runner` (commande `next` / « que faire ensuite »
  — la couche « Prochaine étape » de `state.sh` hissée en interactif), (4)
  re-vérifie ; et **aide à générer la config** (questions → `topology.yaml`).
- **Bibliothèque** : le cœur est importable/testable (pytest) indépendamment des
  façades.

Ce que l'outil **rend** (générateur sans état — il décrit/produit, ne réconcilie
pas) :

- l'**inventaire Ansible** (`control`/`workers`/`cloud.vars`) ;
- un **group_vars de profil** (consolide les `-e` épars —
  `WITH_CEPH`→storageClass/ backing, `WITH_HARDENING`→hardening,
  `osd_expected`…) ;
- pour le **terrain local** : la table de nœuds (≈ `NODES`) + les **profils
  Lima** (`node.yaml.tmpl` rendu, comme `lima_render_node`/`write_inventory`
  déjà existants).

Il **ne génère pas** les manifestes K8s ni les chemins de couches
([ADR 0045](0045-chemins-installation-banc-couches.md)) — il les **alimente**.
Il **ne converge pas** : Ansible reste le moteur (§5).

### 3. Invariant d'or (hérité [ADR 0027](0027-bootstrap-parametre-multi-cluster.md))

**Un `topology.yaml` au profil prod actuel doit générer l'inventaire /
group_vars / profils byte-identiques à l'existant.** C'est le critère de
**non-régression** : tant qu'il tient, remplacer la source bash codée en dur par
le fichier ne change RIEN au comportement (re-prouvé par un run,
[ADR 0034](0034-validation-e2e-from-scratch.md)).

### 4. Exposition configurable (amende [ADR 0020](0020-exposition-reseau-tout-cilium.md))

L'exposition devient une **dimension de la topologie**, avec trois modes :

- **`lb-ipam`** : Cilium attribue des IP `LoadBalancer` annoncées en L2 (le mode
  tout-Cilium d'[ADR 0020](0020-exposition-reseau-tout-cilium.md)). Exige une
  **plage réservée** (`plage`) + `interface`. C'est le mode cible quand l'admin
  réseau a réservé une plage.
- **`nodeport`** : exposition par **port d'un nœud** (`https://<nœud>:3xxxx`).
  **Réintroduit NodePort** comme mode de repli **assumé**, là où
  [ADR 0020](0020-exposition-reseau-tout-cilium.md) l'avait écarté — justifié :
  la plage prod y est un « TODO admin réseau » non résolu, et un déploiement
  doit pouvoir s'exposer **sans dépendre d'une réservation** ni d'un DNS (les
  nœuds ont des IP statiques connues ; kube-proxy-less Cilium route le NodePort
  depuis n'importe quel nœud). Compromis assumé : ports hauts, pas de
  virtual-hosting L7.
- **`none`** : pas d'exposition (différée — ce qu'on a fait en prod avant la
  réservation de plage).

[ADR 0020](0020-exposition-reseau-tout-cilium.md) n'est pas annulé : le
tout-Cilium reste le mode **préféré**. 0056 ajoute `nodeport` comme repli et
`none` comme report, et fait du **choix une donnée déclarée**, pas un drapeau de
fin d'install.

### 5. Frontière état / installation (décrit vs converge)

Deux faces nettes :

- **Décrire / vérifier / mesurer l'état** : `topology.yaml` (état voulu) + les
  outils qui constatent l'état (`state.sh`, assertions de banc, scénarios,
  spikes).
- **Converger vers l'état** : Ansible (moteur), qui pousse du code transitoire
  sur les nœuds (modules Python éphémères — normal,
  [ADR 0033](0033-orchestration-ansible-platform-dataops.md)).

Conséquence : **tout se pilote depuis le poste d'installation**. Les seuls
artefacts **persistants** sur un nœud doivent être des **services runtime
délibérés** (ex. `etcd-snapshot.sh` + timer systemd, gardé hors-k8s **par
robustesse** : la sauvegarde du control-plane ne doit pas dépendre du composant
qu'elle protège, [ADR 0002](0002-control-plane-unique-avec-endpoint.md)).
**`cni.sh` est l'unique ANOMALIE** : un script d'installation lancé à la main
_sur_ le control-plane (scp + bash) au lieu d'être piloté depuis le poste — **à
résorber** (le faire piloter comme le reste).

### 6. Fidélité banc = prod

Le banc et la prod lisent le **même `topology.yaml`** (au `target_kind` près).
En particulier, le banc doit reproduire les **modes d'exposition** (lb-ipam via
L2 sur le réseau Lima ; nodeport) pour que ce qu'on prouve au banc soit ce qui
tourne en prod
([ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md)).

### 7. Pourquoi pas de moteur à état par-dessus k8s (raison de fond)

L'exclusion d'un moteur à état (Terraform/Pulumi/Crossplane) pour la couche
k8s/plateforme **n'est pas dogmatique** — elle tient à un fait technique :

- **K8s est DÉJÀ un moteur à état réconcilié.** Ses contrôleurs convergent en
  permanence vers les manifestes déclarés. Les **operators** (Rook, CNPG,
  Cilium…) en rajoutent une couche : ils **densifient/mutent** les CR qu'on
  applique. Superposer Terraform/Pulumi crée **deux propriétaires de la même
  réalité** qui se disputent : l'outil à état voit comme « drift » ce que
  l'operator a légitimement densifié, et veut le « corriger ». **On l'a vécu
  littéralement** avec la densification du CephCluster par Rook (generation
  N→N+1 → `changed` perpétuel), parade `hidden_fields` + stabilisation. Un
  moteur à état généraliserait ce conflit à toute la plateforme.
- **Le state devient un passif** : fichier à stocker / verrouiller /
  **chiffrer** (il contient les secrets) / réconcilier après tout geste manuel.
  Or on fait du `kubectl` de diagnostic (et on a fait du `ceph osd purge`
  manuel, drift #278) — le state divergerait en continu.
- **Le bare-metal n'est pas provisionnable** par un moteur à état (pas d'API
  pour créer un serveur physique — c'est manuel/PXE).

Ansible a justement été retenu parce qu'il est **sans état** : il _applique_
puis _part_, il ne _possède_ pas les ressources — il coexiste donc proprement
avec les moteurs à état de k8s. La règle exacte : **moteur à état là où l'outil
possède réellement les ressources via une API (VM cloud → OpenTofu,
[ADR 0032](0032-opentofu-provisioning-cloud.md)) ; pas là où un autre moteur les
possède déjà (k8s + operators).**

Compromis assumé : on **renonce** au
`plan`/`diff`/`destroy`/graphe-de-dépendances natifs d'un moteur à état. Le
`diff` est partiellement reconstruit côté outil (état voulu `topology.yaml` vs
état réel via `state.sh`/lib `kubernetes`, §2), mais sans la garantie d'un vrai
moteur. Réévaluable si ce manque devenait critique — en privilégiant alors une
option qui vit **dans** k8s (Crossplane) plutôt qu'au-dessus.

### 8. Portée visée de l'outil (vision complète)

`topology.yaml` **décrit** ; l'outil **orchestre, éprouve, mesure, optimise,
consigne**. Vision complète (l'ordre de réalisation est en §9 — tout n'est pas
le socle). Frontière constante : **décrire/vérifier/mesurer** vs **converger**
(Ansible), §5.

**Décrire (le fichier `topology.yaml`)**

- **(1) État voulu** : nœuds, rôles, réseau, stockage, exposition (§1).
- **(2) Ressources** : `resources{cpus, memory, disk}` (terrain local) — `cpus`
  enfin paramétrable.
- **(3) Profil + défauts + variantes** : `profile: dataops` ⇒ briques déduites
  (base⊂store⊂obs⊂dataops), défauts choisis, variantes à fixer dont une par
  défaut (§1, `catalog`).
- **(4) LB devant les CP** : `control_plane_lb` (kube-vip failover / LB /
  externe) — requis dès > 1 CP (§1, `network`).
- **(5) Exposition configurable** : `lb-ipam | nodeport | none` (§4).

**Éprouver (catalogue d'épreuves, orchestré par l'outil — pas dans le fichier)**

- **(6) Épreuves filtrées par la topologie**, jouables **au choix** : tests
  unitaires (bats/pytest), tests d'intégration, et les **29 scénarios par type**
  (résilience 01-09, durcissement/sécurité 10-18, **chaos** 19-21
  [ADR 0025](0025-securite-active-chaos-attaques-controlees.md), observabilité
  22-26, GitOps/UI 27-29). On choisit **si** on les joue et **quels types**. Un
  scénario incompatible (ex. Ceph sur un cluster `local-path`) n'est pas
  proposé.
- **(7) Smoke-test de réversibilité** (nouveau) : créer un objet (ns/PVC) →
  vérifier `Bound`/présent → détruire → vérifier détruit. Éprouve l'apply **ET**
  le rollback (rejoint le rollback-par-phase,
  [ADR 0054](0054-rollback-par-phase-banc.md) / #274).

**Mesurer & optimiser**

- **(8) Métriques** exportées (existent déjà — `bench/lima/metrology.sh`) :
  durée, `cpu_core_s` (CPU×temps), `ram_peak_mib` (pic), `ram_mean_mib`. L'outil
  les LIT et les EXPOSE, ne les réinvente pas.
- **(9) Optimiseur** (palier lointain) : à partir des métriques consignées,
  **propose** d'ajuster à la hausse ou à la baisse des caractéristiques (RAM/CPU
  d'un nœud, `osd_memory_request`, nombre de replicas…). Il **propose**,
  l'opérateur décide — pas d'auto-tuning silencieux.

**Consigner (historique des runs — `bench/lima/runs-history.yaml`, existe)**

- **(10) Lit l'historique** (fraîcheur via `check-freshness.sh`, déjà câblé) →
  nourrit le « que faire ensuite » (« ce chemin n'a pas de run frais »).
- **(11) Un run emporte l'objectif d'infra visé** : le `topology.yaml` (ou son
  empreinte) est **attaché au run** — on sait **sur quoi** le résultat a été
  obtenu (quelle topologie, quel profil, quelles ressources).
- **(12) Un run `fail` est consigné** au même titre qu'un succès (honnêteté des
  Runs,
  [ADR 0023](0023-plateforme-exemple-generique.md)/[0052](0052-reproductibilite-des-resultats.md))
  — un échec est une donnée, pas un trou dans l'historique.

**Connaître les dépendances**

- **(13) Graphe de dépendances formalisé** : l'ordre inter-rôles/briques
  (aujourd'hui en **prose** dans les playbooks — ex. « cert-manager AVANT cnpg
  », aucun `meta/main.yml`) devient une **déclaration explicite** que l'outil
  lit pour ordonner et suggérer la prochaine action.

### 9. Mise en œuvre (déléguée à un plan dédié)

La vision (§8) **n'est pas le socle** : elle se réalise de façon
**incrémentale**, chaque palier prouvé par un run
([ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md)).
Le **déroulé évolutif** (paliers P0-P8, ordre, état d'avancement, issues créées)
vit dans un **plan dédié**, pas dans cet ADR immuable
([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md)) :
**[`docs/plans/plan-modele-declaratif.md`](../plans/plan-modele-declaratif.md)**.
Repère : P0-P3 = socle (générateur), P4-P6 = plateforme d'épreuve/mesure, P7 =
HA (#250), P8 = optimiseur — détail et suivi dans le plan.

### 10. Doctrine de la convergence différée (les 3 états d'une gate k8s)

**Principe — un état k8s est toujours différé.** On ne l'obtient jamais à
l'instant de l'`apply` : k8s et ses operators sont **level-triggered,
reconcile-forever** (§7) — ils convergent en arrière-plan, **retentent
éternellement**, et n'émettent presque jamais « ceci ne convergera jamais ».
Toute lecture d'état est l'**instantané d'une trajectoire**, pas un verdict ;
**la terminaison de l'attente est une politique de l'appelant**, pas une lecture
de l'état. Racine du piège vécu (osd-43, disque mort) : la gate Ceph
([`platform-ceph-cluster`](../../bootstrap/roles/platform-ceph-cluster/tasks/main.yaml),
`ceph_health_retries: 80` × 15 s ≈ **20 min**) _attend_ un succès qui ne viendra
jamais, épuise son budget, puis échoue par timeout — sans diagnostic, sans
abandonner tôt (et ce rôle n'a même pas de `rescue`).

**Les trois états — et la fiabilité (inégale) de leur signal.**

- **(1) En cours** (`ContainerCreating`, `phase: Progressing`,
  `observedGeneration < generation`, `HEALTH_WARN` de rebalance) → cas par
  défaut : ni succès ni terminal franc ⇒ on reboucle.
- **(2) Erreur récupérable** (`CrashLoopBackOff`, `ImagePullBackOff` registry
  lent, `FailedMount` CSI) → le retry **est** la réparation ; attendre est
  correct.
- **(3) Erreur terminale** (disque mort, image inexistante, placement
  insatisfiable, clé de Secret absente) → ne converge pas sans intervention.

**Vérité à assumer : distinguer (2) de (3) n'a PAS de signal générique fiable.**
`phase: Failed` n'existe que pour `restartPolicy != Always` (absent des
workloads gérés) ; `restartCount` est monotone, sans seuil natif ; un Event
`Warning` a un TTL (son absence ne prouve rien) et `Warning ≠ terminal`. Les
**seuls** verdicts terminaux fiables sont (a) une petite **allowlist de reasons
durs** (`ErrImageNeverPull`, `InvalidImageName`,
`PodScheduled=False/Unschedulable` stable), (b) ce qu'un **operator EXPOSE**
(`HEALTH_ERR`, `status.phase`) — non standardisé, et qui **peut ne pas
remonter** (le `Medium Error` d'osd-43 vit dans les logs de la job
`rook-ceph-osd-prepare`, pas dans `CephCluster.status`). Pour le reste, «
récupérable vs terminal » est **log-dépendant, voire indécidable en ligne** —
toute prétention à « tout détecter » serait fausse.

**Répartition (qui _possède_ quoi, §7) :**

| Acteur           | Possède                | Rôle face aux 3 états                                                                                                                                                                                                      |
| ---------------- | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| k8s + operators  | l'état (propriétaire)  | **calculent** les 3 états et les **exposent** (`.status.phase`, `.conditions`, Events)                                                                                                                                     |
| **Ansible**      | rien (applique, part)  | **applique + sonde** : `until` = succès ; `failed_when` sur un signal terminal **exposé** = fail-fast ; sinon reboucle (= en-cours). **Ne dérive aucun état.**                                                             |
| **Outil Python** | rien (décrit/constate) | **diff + classe + suggère** (après le `fail`) : lit conditions/events (lib `kubernetes`) + résultats (`ansible-runner`), **propose** « attends » vs « interviens sur `/dev/sdX` ». L'opérateur décide. Consigne le `fail`. |

**La ligne anti-réimplémentation (§7), en règle opérationnelle :**

> **Consommer** un verdict que l'operator **expose** (`status.phase`, condition
> nommée, Event `reason` durci) est **permis** ; **dériver** un verdict qu'il
> n'expose pas (heuristique de temps, seuil sur `restartCount`, agrégation de
> symptômes) est **interdit** — ce serait le 3ᵉ moteur à état écarté en §7.

Ansible lit `phase == 'Ready'` (il _consomme_ le verdict de Rook) ; il ne
construit jamais « si tel Event depuis tel délai alors c'est mort ». Il reste
**binaire enrichi d'une seule branche** (succès / terminal-franc / reboucle),
pas un classifieur.

**Fail-fast — porté par Ansible, au prix de la spécificité.** On garde le
`until` (succès) et on ajoute un **`failed_when` sur une condition terminale
exposée et non ambiguë** : les 3 états sont **encodés sans être « compris »**.
C'est **par-ressource** (chaque operator a son vocabulaire), pas générique ; et
**là où l'operator n'expose rien de franc, on assume le timeout** — on ne
fabrique pas un faux terminal. Le raisonnement explicatif (pourquoi, quoi faire
du disque) reste à l'outil Python (palier P5), qui **suggère, ne décide pas**
(pattern de l'optimiseur, §8 (9)).

**Existe déjà / à ajouter.** La taxonomie **`ok` / `fail` / `skip`** de
[`health-classify.sh`](../../bootstrap/lib/health-classify.sh) /
[`state-classify.sh`](../../bootstrap/lib/state-classify.sh) (où `skip` =
pas-encore/indéterminé, `fail` = présent-mais-cassé — ex. `classify_ceph_health`
: `HEALTH_ERR→fail`, `''→skip`) **est déjà la bonne distinction**, mais
aujourd'hui en **audit hors-bande** (`state.sh`), jamais dans une boucle
d'attente. À ajouter : (i) un **`failed_when` terminal** dans les gates — à
commencer par `platform-ceph-cluster` (le timeout le plus aveugle, sans rescue),
en **réutilisant `classify_ceph_health`** plutôt qu'en ré-écrivant un verdict ;
(ii) un **rescue diagnostique** sur cette gate, aligné sur le patron des cinq
autres rôles (ADR 0050 cas (a)) ; (iii) côté outil Python, le **classifieur
best-effort** qui range conditions/events et suggère l'action. Limite assumée :
(i) **écourte** le timeout quand un signal franc existe ; pour tout le reste, le
timeout **reste la garantie de terminaison**.

**Invariant de preuve** ([ADR 0050](0050-modele-reprise-role-ansible.md) inv. 3
;
[ADR 0034](0034-validation-e2e-from-scratch.md)/[0046](0046-corriger-le-code-pas-l-etat.md)/[0052](0052-reproductibilite-des-resultats.md))
: une branche `failed_when` modifie le **chemin d'erreur** → elle se prouve par
**arrêt injecté côté harnais** (disque retiré/marqué mort), consigné dans
`bench/RESULTS.md`, **jamais** par une variable `inject_fault` dans le rôle
prod.

## Statut

Accepted (2026-06-12 ; promu de Proposed le 2026-06-13). **Réalise** la
restructuration par profils de topologie que
[ADR 0023](0023-plateforme-exemple-generique.md) avait actée en vision et
reportée. **Amende** [ADR 0020](0020-exposition-reseau-tout-cilium.md)
(réintroduit NodePort comme repli + exposition = dimension déclarée). **Étend**
le tuple [ADR 0039](0039-nomenclature-axes-catalogue.md) (intègre durcissement +
exposition, résout l'asymétrie avec
[ADR 0045](0045-chemins-installation-banc-couches.md)). **Bâtit sur**
l'invariant byte-identique
d'[ADR 0027](0027-bootstrap-parametre-multi-cluster.md), le template+générateur
Lima existant, et la doctrine d'outil
[ADR 0017](0017-langage-des-scripts.md)/[0049](0049-doctrine-choix-outil-par-action.md).
**Orthogonal** à [ADR 0032](0032-opentofu-provisioning-cloud.md) (OpenTofu reste
cantonné au provisioning IaaS cloud ; le générateur de topologie se branche en
amont du même `write_inventory → bootstrap`, pour les trois terrains).

**Premier cas d'application : issue #250** (banc Lima HA `ha-3cp`) — l'ADR 0056
en est le **prérequis** : la topologie `ha-3cp` (CP dédiés ou hyperconvergés,
VIP, exposition) sera **déclarée** dans `topology.yaml`, ce qui révèle et
structure le delta à coder (VIP, rôle kube-vip, groupe `control` multi-CP).

## Conséquences

> **Amendé par [ADR 0069](0069-topology-layers-dag-grain-phase.md)** : la
> déclaration des couches passe du profil scalaire (chaîne totale) à
> `topology.layers` (ensemble ordonné par le DAG de dépendances réelles) —
> `layers` est la forme explicite du graphe de dépendances que ce modèle décrit.

- **Source unique de vérité** : une topologie se lit/écrit en un endroit ; fin
  de la double déclaration `NODES` ↔ inventaire et des `-e` épars.
- **Topologies cibles enfin encodables** : `multi-node-4`, `ha-3cp` deviennent
  des `topology.yaml`, pas du bash à éditer. Le fichier **expose le delta**
  d'une cible non buildée (ex. `ha-3cp` révèle la VIP manquante) avant tout
  engagement de code.
- **Exposition robuste** : un déploiement s'expose sans dépendre d'une plage
  d'IP (mode `nodeport`) ou la diffère (`none`) — leçon directe du run prod.
- **Implémentation INCRÉMENTALE** (paliers indépendants, chacun prouvé par run,
  [ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md))
  :
  1. **Modéliser sans générer** : écrire `topologies/socle.example.yaml` pour
     les topologies déjà décrites (multi-node-3 léger/Ceph, ha-3cp) — schéma de
     données pur, révèle les deltas.
  2. **Générateur read-only Lima** : `topology.yaml` → inventaire + NODES +
     profils, critère **byte-identique** à l'actuel pour `multi-node-3`.
  3. **Brancher le profil** : faire dériver storage/hardening/exposition en un
     group_vars de profil généré.
  4. **Étendre** : prod `multi-node-4`, puis `ha-3cp` (qui exige d'abord la
     VIP + kube-vip — travail réel, #250).
- **Prix à payer** : écrire/maintenir le générateur + son schéma ; migrer
  `NODES`/inventaire/`-e` sans régression (mitigé par l'invariant §3) ;
  documenter. Risque de sur-modélisation à brider
  ([ADR 0039](0039-nomenclature-axes-catalogue.md) : pas de nomenclature
  spéculative — n'encoder que les dimensions réellement utilisées).
- **`cni.sh` à résorber** (pilotage depuis le poste) — tracé comme conséquence,
  pas bloquant pour les premiers paliers.

> **Addendum 2026-06-14 — emplacement du catalogue.** Le catalogue vit dans
> `topologies/` : les modèles génériques y sont versionnés en `*.example.yaml`
> (`socle.example.yaml`, `ha-3cp.example.yaml`), les topologies réelles
> `topologies/*.yaml` sont gitignorées. À la racine, `topology.yaml` est un
> **symlink d'activation** (gitignoré) pointant la topologie en vigueur
> (`ln -sf topologies/<x>.example.yaml topology.yaml`) ; en son absence l'outil
> retombe sur `topologies/socle.example.yaml`. La décision (un fichier décrit,
> Ansible converge) est inchangée — seul l'emplacement physique est précisé.

## Alternatives écartées

- **Moteur à état (Pulumi / Terraform / Crossplane) par-dessus k8s.** Écarté
  pour la raison technique développée en §7 (conflit de propriété : k8s +
  operators sont déjà des moteurs à état réconcilié), pas par dogme. Apporterait
  pourtant de vrais bénéfices qu'on n'a pas (`plan`/`diff` avant action,
  `destroy` ordonné, graphe de dépendances) — c'est le compromis assumé.
  Réévaluable si ces bénéfices devenaient critiques ET qu'on trouvait comment
  éviter le conflit de propriété (ex. Crossplane _dans_ k8s plutôt
  qu'au-dessus). OpenTofu pour le IaaS cloud
  ([ADR 0032](0032-opentofu-provisioning-cloud.md)) **n'est pas** concerné : là,
  l'outil possède réellement les ressources.
- **Étendre OpenTofu à la description de topologie.**
  [ADR 0032](0032-opentofu-provisioning-cloud.md) **borne** OpenTofu au IaaS
  cloud ; l'étendre au local/baremetal exigerait des providers inexistants
  (Lima/baremetal) et un `tfstate` « sans objet en local ». Détourné,
  incohérent. OpenTofu reste à sa niche (provisionner les VM cloud).
- **Outil en Go (binaire + bubbletea + client-go).** Techniquement le plus
  séduisant pour un TUI riche autonome et un client K8s natif. Écarté pour trois
  raisons cumulées : (1) [ADR 0017](0017-langage-des-scripts.md) **proscrit le
  portage Go opportuniste** ; (2) ce serait un **6ᵉ langage** (toolchain, lint,
  CI), à rebours du critère « cohérence de l'existant »
  d'[ADR 0049](0049-doctrine-choix-outil-par-action.md) ; (3) l'outil est
  **fortement couplé à Ansible** (Python) — `ansible-runner`, inventaire,
  Jinja2, lib `kubernetes` sont nativement Python ; en Go il faudrait shell-out
  vers `ansible-playbook` (le `subprocess` fragile qu'on veut éviter).
  `textual`/`rich` couvrent le besoin de TUI. Choisir Go imposerait d'**amender
  la doctrine de langage** pour un seul outil interne — disproportionné. (Rust,
  Node/TS : écartés a fortiori — aucun précédent, encore plus loin de la
  doctrine.)
- **Tout en bash (+ fzf pour l'interactif).** Conforme à « bash orchestre »,
  mais la logique (parse/validation de schéma YAML, diff état voulu/réel,
  assistant guidé) est **non triviale** → relève de Python par
  [ADR 0017](0017-langage-des-scripts.md)/[0049](0049-doctrine-choix-outil-par-action.md)
  ; et `fzf` ne fait pas un assistant « que faire ensuite » (menu ≠ REPL
  d'état). Bash reste pertinent pour les **wrappers** d'entrée fins, pas pour le
  cœur.
- **Statu quo (bash + inventaire + `-e`).** Le frein documenté ci-dessus :
  éparpillement, double déclaration, topologies cibles non encodables,
  exposition fragile. C'est l'état qu'on quitte.
- **Garder NodePort écarté ([ADR 0020](0020-exposition-reseau-tout-cilium.md)
  seul).** Laisse un déploiement sans plage d'IP réservée **sans solution
  d'exposition** — exactement le blocage du run prod. Écarté au profit du repli
  `nodeport` assumé.
