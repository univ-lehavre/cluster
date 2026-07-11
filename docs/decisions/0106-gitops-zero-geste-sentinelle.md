# 0106 — GitOps zéro-geste : la Sentinelle (détection API + build node-side inchangé)

## Statut

Superseded by 0110 (2026-07-11). Proposé le 2026-07-10.

> ⚠️ **Superseded PARTIEL par
> [ADR 0110](0110-preimage-de-build-et-build-in-pod.md).** La pré-image (0110)
> supprime l'egress du build de code → ce build passe **in-pod** (buildkit
> rootless), ce qui rend **caduque l'exécution node-side** décrite ici (§1, le
> _timer systemd_ posé par `platform-build-images`). **Ce qui SURVIT de cet
> ADR** : la **Sentinelle** (détection d'écart de révision, CronJob API-only —
> §1 détection), désormais branchée sur un _Job de build in-pod_ au lieu du
> timer ; la doctrine **anti-amplification / coalescing** (§2-§3), reprise sous
> une forme adaptée au Job ; l'**acheminement `main → Gitea`** (§6), orthogonal
> et entièrement conservé ; la **frontière** nestor/atlas/auto (§5). Lire ce qui
> suit comme le témoin de l'état au 2026-07-10.

Complète et **réévalue partiellement**
[ADR 0105](0105-retrait-build-evenementiel-node-side-terminal.md) : on
**conserve** le build node-side terminal (0105 §1) et on **retire**
définitivement la chaîne événementielle Argo Events (0105 §2), mais on
**conteste le corollaire implicite** « donc le déclenchement doit rester un
geste humain ». S'appuie sur le
[reconciler workspace (ADR 0103)](0103-workspace-dagster-multi-code-location-reconciler.md)
comme moule, et sur l'immuabilité par digest
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)/[0046](0046-corriger-le-code-pas-l-etat.md)/[0052](0052-reproductibilite-des-resultats.md)).

## Contexte

### Le symptôme : la prod décroche

Une question opérationnelle simple — « comment mettre à jour la prod ? » — a
révélé que la code-location `citation` déployée pointait un SHA vieux de **~2
semaines et 394 commits** de retard sur `main` (au 2026-07-10). Toute la refonte
du mart Parquet, la cascade de correctifs OOM prod et des changements de
sémantique étaient mergés mais **jamais déployés**. Ce n'est pas un oubli isolé
: c'est le **résultat structurel** du modèle actuel, où déployer exige une
**séquence manuelle multi-étapes** (bumper le `revision` du manifeste, lancer le
build node-side, capturer le digest, seed) que rien ne déclenche au merge — et
que, de fait, personne ne déroule.

### Ce que l'ADR 0105 a réellement tranché — et ce qu'il n'a pas tranché

L'ADR 0105 a retiré la chaîne événementielle §1.b d'ADR 0095 (Argo Events + Argo
Workflows/BuildKit + NATS + webhook Gitea #2). **Ce retrait est fondé** : la
chaîne souffrait d'une **amplification massive** (un Sensor sans clé de
déduplication — `dataKey: body.commits.0.modified.0`, `generateName:` par event
— instanciait un Workflow **par event** ; un force-push d'arbre complet générait
des dizaines d'events → des dizaines de builds concurrents identiques), et
faisait tourner **deux chaînes en parallèle** (node-side + eventful) produisant
des digests concurrents.

**Mais deux nuances, vérifiées, importent pour la présente décision :**

1. **Le grief « ~52 % d'échec » n'a aucune source primaire** dans le dépôt (ni
   dump `kubectl`, ni entrée du registre de drifts porte ces comptes). La cause
   dominante des échecs était l'**amplification** (builds concurrents se
   marchant dessus) et des **bugs de configuration corrigés par ailleurs**
   (Gitea sous-dimensionné → drift L94 ; `nodeSelector` cassé →
   `0/4 nodes match`). Autrement dit : ces échecs mesuraient une
   **implémentation naïve**, pas l'infaisabilité d'un déclenchement automatique.

2. L'ADR 0105 concède lui-même (dans sa clôture) qu'un futur déclenchement
   automatique « devra repartir d'un design qui **déduplique** (un build par
   _(code-location, révision)_, pas par event) ». **La porte est donc
   explicitement laissée ouverte** à une automatisation correctement
   dédupliquée. Le présent ADR la franchit.

Le corollaire « le build redevient un geste opérateur unique assumé » a été
**affirmé**, pas outillé : ce geste reste une séquence à deux sources de vérité
(le `revision` du manifeste atlas **et** la topo cluster) plus un digest à
recopier. Les 394 commits prouvent qu'un geste manuel, même « unique », ne tient
pas dans la durée.

### Principe directeur retenu (frontière de responsabilité)

> **`nestor` provisionne l'infrastructure et les logiciels de base. `atlas`
> fournit le code applicatif. Tout le reste — build de l'image, capture du
> digest, mise à jour du dépôt de déploiement, synchronisation — relève de
> l'automatisation.**

Ce principe tranche le désordre actuel où `nestor` **déborde** de son rôle (il
_build_ l'image applicative et _seed_ le déploiement — du « reste » qui n'est
pas du socle).

## Décision

> **On introduit la « Sentinelle » : une détection d'écart de révision _dans le
> cluster_ (CronJob API-only, moule reconciler ADR 0103) qui pose un SIGNAL, et
> une exécution du build _sur le nœud_ (timer systemd, moule etcd-backup) qui
> rejoue le build node-side PROUVÉ, byte-pour-byte. Argo CD (auto-sync déjà en
> service) déploie. Un merge sur `main` devient un déploiement, sans geste après
> le merge, sans ressusciter Argo Events.**

### 1. Séparation détection / exécution (le cœur)

Le point dur est que le build node-side a besoin du **containerd + buildkit du
nœud** en root (vérifié : `nerdctl build` délègue à `buildkitd`, service systemd
du nœud ; `registry:80` n'est joignable que via le `/etc/hosts` +
`certs.d/hosts.toml` + `use_local_image_pull` **du nœud**). Un pod ne peut pas
reproduire cet environnement sans devenir un risque d'évasion. On sépare donc
les deux gestes :

- **Détection (API-only, sobre).** Un **CronJob `code-location-sentinel`** (ns
  `dagster`, SA + Role _namespaced_ minimal), calqué sur le reconciler workspace
  (ADR 0103). Il découvre les code-locations **par label** (zéro énumération
  centrale), compare le SHA amont (Gitea) au digest déployé, et **sur écart pose
  un SIGNAL** (annotation / ConfigMap `<cl>-build-signal`). **Il ne build pas,
  ne SSH pas, n'a aucun pouvoir sur le nœud** — il ne peut que poser un drapeau.

- **Exécution (node-side, inchangée).** Un **timer systemd** posé par
  `platform-build-images` (moule éprouvé `etcd-backup`, qui pose déjà un
  `.timer`/ `.service` root touchant le runtime containerd). Il lit le signal
  et, **si et seulement si** le SHA a changé depuis le dernier build stampé
  localement (`/var/lib/...`), rejoue le rôle `platform-build-images`
  **exactement** comme `nestor ansible code-location-build.yaml` le ferait —
  `nerdctl`→containerd local, buildkitd systemd, résolution registry node-side,
  egress build du nœud : **zéro ligne du moteur touchée**.

### 2. Anti-amplification (la condition posée par 0105)

Trois verrous, tous **par `(code-location, révision)`, jamais par event** :

- **Pas d'events du tout** : la Sentinelle est **périodique** (CronJob), pas un
  Sensor. Un push n'instancie rien ; la cardinalité suit les _ticks_, et un tick
  sans écart est un **no-op** (`changed=0`, comme le reconciler qui ne redémarre
  pas un workspace inchangé).
- **Dédup par état** : build seulement si `SHA_amont ≠ SHA_déployé`.
- **Stamp node-side** : le timer mémorise le dernier SHA construit ; un signal
  déjà traité ne rebuild pas. C'est très exactement le « un build par
  (code-location, révision) » qu'ADR 0105 exige pour rouvrir un déclenchement
  auto.

### 3. Concurrence : coalescing sur le dernier commit (pas de perte, pas de doublon)

La dédup ci-dessus couvre « deux détections du **même** SHA ». Elle ne couvre
pas le cas concurrent réel : **`main` avance _pendant_ un build en cours** (un
push B arrive alors que le build de A tourne, ~5 min). Deux écueils opposés
doivent être évités : relancer un build de B en parallèle de A **réintroduirait
l'amplification** qu'ADR 0105 reprochait ; skipper B parce qu'« un build est en
cours » **perdrait le dernier commit** (B ne serait jamais déployé). On veut un
**coalescing** : un seul build à la fois par code-location, puis un **unique**
rebuild sur la **tête** si elle a bougé — jamais sur les commits intermédiaires.

**Machine à états, sur un ConfigMap d'état _par code-location_**
(`<cl>-build-state`), trois champs : `built_sha` (dernier construit et déployé),
`building_sha` (build en cours, vide sinon), `pending_sha` (tête en attente
derrière le build courant).

À chaque tick, la Sentinelle lit `SHA_amont` (tête de `main` sur Gitea) et
applique :

1. **Un build tourne** (`building_sha` non vide) :
   - `SHA_amont ≠ building_sha` → `pending_sha := SHA_amont` (on **mémorise la
     tête**, on **n'interrompt pas** et on **ne lance pas** de second build) ;
   - sinon → rien (le build courant couvre déjà la tête).
2. **Aucun build** (`building_sha` vide) :
   - `SHA_amont ≠ built_sha` → `building_sha := SHA_amont`, **signal → build** ;
   - sinon → **no-op** (à jour).

**À la fin d'un build**, le timer node-side stampe `built_sha := building_sha`
puis vide `building_sha`. Au tick suivant, si `pending_sha` diffère de
`built_sha`, il est traité comme le nouvel écart → **un seul build de
rattrapage, sur la tête**.

Propriétés garanties :

- **Jamais deux builds concurrents** d'une même code-location : `building_sha`
  est le verrou logique, `concurrencyPolicy: Forbid` (côté CronJob) et la
  sérialisation systemd (`Type=oneshot`, côté timer) sont les filets.
  L'amplification d'ADR 0105 reste structurellement impossible.
- **Aucun commit perdu** : la tête est toujours retenue dans `pending_sha`.
- **Coalescing réel** : 5 pushes pendant un build long → **1** build de
  rattrapage sur la tête, pas 5 (les intermédiaires sont sautés, pas buildés).
- **Convergence** : dès que `main` se stabilise, `SHA_amont == built_sha` →
  no-op ; le système s'arrête de lui-même (pas de boucle).
- **Verrou _par_ code-location, pas global** : `citation`, `mediawatch`,
  `pageviews` ont chacune leur `<cl>-build-state` et peuvent builder en
  parallèle sur des nœuds/ verrous distincts. Un push citation ne bloque pas un
  build mediawatch.

**Échec de build (cas sœur, sinon `building_sha` resterait bloqué à vie).** Le
timer node-side traite le build en `Type=oneshot` : si le rôle
`platform-build-images` échoue (exit ≠ 0), il **ne stampe pas** `built_sha` et
**libère** `building_sha` (le `.service` en échec ne fige pas l'état). Au tick
suivant, `SHA_amont` (ou `pending_sha`) diffère toujours de `built_sha` →
**retry naturel** du même SHA, borné par un compteur `build_attempts` sur le
ConfigMap : au-delà de N échecs pour un même SHA, la Sentinelle **cesse de
relancer** (elle ne martèle pas un build cassé) et le signale (état `failed`,
visible pour l'opérateur / une alerte) — le prochain **nouveau** commit réarme
le cycle. Un build cassé bloque donc le déploiement de _cette_ code-location
(sécurité : on ne déploie pas une image qui n'existe pas), sans boucler ni
bloquer les autres.

### 4. Une seule chaîne, immuabilité préservée

Il n'y a **qu'une** chaîne de fabrique (le node-side prouvé) — la divergence de
digests d'ADR 0105 (deux chaînes concurrentes) ne peut pas réapparaître. Le
write-back injecte **les deux** références couplées (`__CITATION_IMAGE_DIGEST__`
→ `images[].digest` **et** `__CITATION_IMAGE__` → `DAGSTER_CURRENT_IMAGE`) —
omettre la seconde ressusciterait la divergence. Le déploiement reste **par
`@sha256`**, jamais par tag mutable (ADR 0006).

### 5. Frontière nestor / atlas / auto

| Camp                          | Contenu                                                                                                                                                                                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`nestor` = socle**          | Pose (génériques, vides, une fois) : le CronJob Sentinelle (comme le reconciler ADR 0103) et le timer systemd node-side (comme etcd-backup). Réemploie `platform-build-images` intact. **Ne build rien, ne connaît aucun digest, ne touche aucun repo applicatif.** |
| **`atlas` = code**            | Dockerfile, code-location, overlays kustomize avec **placeholders** (`__…_IMAGE(_DIGEST)?__`), `code-location.manifest.yaml` (`revision` = signal canonique). N'expose que les trous.                                                                               |
| **automatisation = le reste** | Détection d'écart, build, capture du digest, write-back du digest, sync Argo CD.                                                                                                                                                                                    |

Le seul déplacement vs aujourd'hui : le write-back du digest passe du **seed
lancé par un humain** à un **composant du socle** (la Sentinelle). Le seed
`seed-app-of-apps.sh` reste pour le **bootstrap** (première pose de
l'App-of-Apps) ; la Sentinelle prend le **régime permanent**.

### 6. Acheminement `main` GitHub → Gitea dirqual : transport git SSH

La Sentinelle détecte un écart entre `main` **sur le Gitea du cluster** et le
digest déployé. Encore faut-il que `main` GitHub **atteigne** ce Gitea. C'est
une **contrainte du design** (pas un simple « point à prouver ») : sans
acheminement, la Sentinelle n'a rien à détecter.

**Contraintes vérifiées (2026-07-10) qui ferment les voies naïves :**

- **Tailscale est exclu du chemin de déploiement** (décision d'instance) — donc
  pas de runner/relais qui pousse via le Tailnet.
- **Gitea est air-gappé** (`network-policies/gitea/allow-gitea.yaml` : « Egress
  air-gapped ADR 0044, PAS d'Internet ») → Gitea **ne peut pas** mirror-pull
  depuis `github.com`.
- **Pas d'ingress public** : Gitea n'expose que HTTP (ClusterIP `gitea-http:80`,
  NodePort `gitea-http-nodeport:3000→30336`). Aucun endpoint git-SSH
  aujourd'hui.
- **Un runner GitHub _cloud_** ne joint ni le LAN dirqual ni le cluster.

**Décision — exposer le serveur SSH intégré de Gitea et pousser en git natif.**
On **active le serveur SSH intégré de Gitea** (image `gitea/*-rootless`,
configurée par env `GITEA__server__START_SSH_SERVER=true` /
`GITEA__server__SSH_PORT` / `SSH_LISTEN_PORT` — le rootless écoute `2222`), on
l'expose par un **NodePort L4** (`gitea-ssh-nodeport`, plage 30000-32767 non
figée, patron `nodeport.yaml` / [ADR 0092](0092-exposition-hostport-l4.md)), et
le pousseur fait un
**`git push ssh://git@<hôte-nœud>:<nodePort>/atlas/atlas.git`** avec une **clé
de déploiement** (deploy key Gitea, write, propre au repo). Git natif, transport
SSH — **sans `kubectl`, sans port-forward, sans Tailscale, sans egress
cluster**.

**Qui pousse.** Un **runner GitHub self-hosted sur le LAN dirqual**
(`10.67.2.0/22`, joignable en L4 vers le NodePort SSH d'un nœud), déclenché
`on: push: [main]` — donc **après** les 16 checks du ruleset, sur du `main` déjà
validé. Il ne détient qu'une **clé SSH de déploiement Gitea** (rien d'autre :
aucun kubeconfig, aucun token d'API k8s). Le pouvoir du credential est ainsi
**cantonné à `git push` sur ce seul repo** — bien plus étroit qu'un kubeconfig
(port-forward) ou qu'un token admin Gitea.

> Pourquoi le transport SSH plutôt que le port-forward HTTP existant (le seed
> pousse déjà via `kubectl port-forward`) : le port-forward exige un
> **kubeconfig** au pousseur (pouvoir k8s large, à cantonner par RBAC — plus
> délicat). La deploy key SSH est un secret **à portée unique** (un repo, un
> droit `push`), le moindre pouvoir. Le seed garde le port-forward pour le
> **bootstrap** (il a déjà le kubeconfig) ; le **régime permanent** passe par
> SSH, credential minimal.

**Sûreté.** Seul `main` — code ayant passé les 16 checks requis — est propagé ;
Gitea ne reçoit jamais de branche non validée. L'immuabilité est préservée en
aval (le build+digest épingle, pas ce push de code). La frontière tient : le
runner est de **l'automatisation** (pas `nestor`, pas un geste humain) ;
`nestor` **provisionne le socle** — l'activation SSH de Gitea et le
`gitea-ssh-nodeport` sont des manifestes d'infrastructure (rôle Gitea), généri­
ques et vides de tout contenu applicatif.

**À provisionner (hors dépôt versionné, valeurs d'instance — ADR 0023/0033) :**
(i) une machine du **LAN dirqual** enregistrée comme runner self-hosted GitHub
du dépôt `atlas` ; (ii) une **deploy key** Gitea (write) sur `atlas/atlas`, clé
privée en Secret du runner ; (iii) le `nodePort` SSH effectif (attribué par
k8s). Le host-key Gitea doit être épinglé côté runner (`known_hosts`) pour
éviter le TOFU.

## Conséquences

**Positif.**

- **Le merge redevient le seul geste.** La prod cesse de décrocher (plus de
  394-commits-de-retard structurels).
- **+0 opérateur** : aucun Argo Events / Workflows / NATS. Deux capacités
  node/CronJob minces, sur des moules déjà en prod (reconciler, etcd-backup). La
  sobriété d'ADR 0105 est **conservée**, pas sacrifiée.
- **Sécurité** : aucun pod ne détient de pouvoir sur le nœud (ni socket
  containerd monté, ni clé SSH root) — contrairement aux alternatives «
  socket-in-pod » et « CronJob-SSH », toutes deux écartées comme évasions node.
  Le CronJob ne peut que poser un drapeau.
- **Immuabilité et build inchangés** : le moteur prouvé n'est pas touché ; seul
  le déclencheur change.

**Négatif / coût.**

- **Latence = période du cron** (comme le reconciler et le filet builder) : ce
  n'est pas du temps réel. Acceptable (le déploiement suit de quelques minutes
  le merge).
- Un timer systemd node-side est un composant **node-level** de plus à opérer
  (mais du même genre qu'etcd-backup, déjà assumé).

**Points à prouver (avant d'acter Accepted).**

1. **Acheminement `main` GitHub → Gitea dirqual** (voie **tranchée** en §6 :
   push-based via runner self-hosted sur le **LAN dirqual** — décidé). Reste à
   **réaliser** au PoC : enregistrer le runner sur le LAN dirqual, poser la
   deploy key Gitea, prouver qu'un `push: main` propage `main` validé vers
   `atlas/atlas` en quelques secondes. Le mécanisme est décidé ; c'est sa **mise
   en service** qui reste à faire (rien de tel n'existe aujourd'hui — le Gitea
   `main` est figé au 2026-07-08).
2. **Digest multi-arch.** Le build capture
   `nerdctl image inspect --format '{{index .RepoDigests 0}}'` — un digest
   **par-arch**, pas un digest d'**index** (manifest list). `citation` est
   `build_all_arch: true`. Latent aujourd'hui (prod x86-only), mais toute
   automatisation propagerait fidèlement ce digest mono-arch. À corriger si le
   parc devient multi-arch (builder un index + capturer le digest de l'index).
   Dette **documentée, non bloquante**.
3. **PoC du timer + signal** : prouver au banc que le timer node-side lit le
   signal, rejoue le build idempotent (`changed=0` au second tick), et que la
   Sentinelle ne déclenche qu'un build par (code-location, révision).

**Réserve d'honnêteté.** Cet ADR conçoit ; il ne prouve pas encore la chaîne de
bout en bout. Les trois points ci-dessus sont les conditions de passage en
`Accepted`.
