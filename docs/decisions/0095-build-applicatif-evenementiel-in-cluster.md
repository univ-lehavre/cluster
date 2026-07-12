# 0095 — Build applicatif événementiel in-cluster : fabrique d'images et déploiement GitOps zéro-touch

## Statut

Accepted (2026-06-25 ; proposé le 2026-06-24).

> **Amendé par [ADR 0111](0111-atlas-instancie-application-argocd.md)
> (2026-07-12) sur le canal de déploiement.** Cet ADR décrit le write-back du
> digest dans un repo Gitea `cluster/apps` (App-of-Apps **côté cluster**) et
> l'instanciation de l'`Application` par le seed cluster. 0111 déplace cette
> responsabilité vers atlas : l'`Application` (et l'injection
> `repoURL`/`targetRevision`) est portée par atlas, pas par `cluster/apps`. Le
> §1.b (build événementiel) était déjà abrogé par
> [0105](0105-retrait-build-evenementiel-node-side-terminal.md) ; le build de
> code lui-même est sorti du cluster
> ([0110](0110-preimage-de-build-et-build-in-pod.md)).

**Partiellement superseded par
[0105](0105-retrait-build-evenementiel-node-side-terminal.md) (2026-07-08)** :
le §1.b (build ÉVÉNEMENTIEL in-cluster) est ABROGÉ — instable en prod
(amplification webhook ×45, 52 % d'échec). Le §1.a (build Ansible node-side)
devient le mécanisme TERMINAL. Les §2 (digest figé), §3 (miroir) et §4 restent
valides.

Précise et complète les ADR [0022](0022-argocd-gitops-applicatif.md) (Argo CD
déploie l'applicatif), [0033](0033-orchestration-ansible-platform-dataops.md)
(Ansible converge l'infra, build d'images **node-side** via nerdctl/buildkit),
[0044](0044-topologie-deploiement-banc-atlas.md) (flux GitOps Gitea → Argo CD)
et [0094](0094-frontiere-deploiement-applicatif.md) (frontière de déploiement
cluster ↔ atlas, App-of-Apps `cluster/apps`). Il **SUPERSEDE partiellement
[ADR 0033](0033-orchestration-ansible-platform-dataops.md) sur la frontière du
build applicatif** : à terme, la fabrique d'image **applicative** (code métier
atlas) passe d'un build Ansible `run_once` node-side à un build **événementiel
in-cluster**. Le supersede est **partiel et argumenté** (cf. §Décision) : il ne
concerne **que** le build des images **applicatives** ; le build/retag des
images **de plateforme** reste node-side via Ansible (0033 inchangé sur ce
point), et l'**outil** demeure containerd-natif (nerdctl/buildkit, **pas
Kaniko**). Toutes les valeurs ci-dessous sont des exemples génériques
([ADR 0023](0023-plateforme-exemple-generique.md)) : `cluster/apps`,
`cluster/cluster`, `atlas/atlas`, `citation`, `pgvector-pg-auth`, `registry:80`,
`<app>`, `node1`…`node4`.

## Contexte

[ADR 0094](0094-frontiere-deploiement-applicatif.md) a fermé le trou du
**déploiement** applicatif : une app se déclare en poussant un fichier dans le
repo Gitea `cluster/apps`, qu'une `Application` racine app-of-apps réconcilie.
Reste, **en amont**, la **fabrique d'image** : aujourd'hui l'image d'une app
(exemple générique : `citation`) est construite par le rôle Ansible
[`bootstrap/roles/platform-build-images`](../../bootstrap/roles/platform-build-images/)
(`run_once`, `become: true`, build node-side via nerdctl/buildkit), **déclenché
à la main** par un opérateur. Tant que ce build n'a pas tourné, l'image n'existe
pas dans le registry et le déploiement reste **bloqué**. Subsistent aussi des
**gestes manuels** résiduels : le Secret dérivé `pgvector-pg-auth` (auth
Postgres cross-namespace pour une code-location atlas) a été **créé à la main**
en prod — une entorse à [ADR 0046](0046-corriger-le-code-pas-l-etat.md)
(corriger le code, pas l'état) déjà relevée par l'audit (issue atlas #499,
[ADR 0094](0094-frontiere-deploiement-applicatif.md) §Contexte).

L'objectif est **« zéro geste manuel »** de bout en bout : un `git push` du code
applicatif doit aboutir, sans intervention, à un pod qui tourne avec ce code.

Un **workflow de conception multi-agents** (4 scans du code, 3 options
détaillées, 3 vérifications adversariales, synthèse) a instruit la question. Il
corrige d'abord une **prémisse fausse** qui orientait tout le raisonnement, puis
écarte la voie « naïve » et tranche la frontière.

**Correctif factuel — les ressources ne sont pas le blocage.** Le cadrage
initial supposait « mono-control-plane, ressources comptées ». L'audit prod du
2026-06-24 (`docs/audit/2026-06-24-audit-prod-dirqual.md`) le **réfute** : le
cluster a **4 nœuds** (`node1`…`node4`), **~90 % de RAM libre**, abondance de
stockage ; **seul le control-plane est mono-nœud (SPOF)**. Un build d'image
(base Debian + uv/PyPI + DuckDB + un modèle ONNX de ~22 Mo) tient **trivialement
sur un worker**. La vraie contrainte n'est donc **pas** la capacité : c'est
l'**air-gap au build** (ci-dessous).

**Obstacle dirimant — le build a besoin d'Internet, le déploiement non.** La
vérification adversariale des trois options converge sur un fait **vérifié dans
le code** : le `Dockerfile` de l'image applicative
(`atlas/dataops/citation-dagster/Dockerfile`, exemple générique) **exige
plusieurs accès Internet AU BUILD** :

- `apt-get install …` (miroirs Debian) ;
- `pip install uv` + `uv pip install .` (wheels PyPI : DuckDB, le moteur de
  pipelines, le moteur de transformation) ;
- `duckdb INSTALL httpfs/postgres` (CDN d'extensions DuckDB) ;
- un script de pré-chargement qui **télécharge le modèle ONNX**
  `all-MiniLM-L6-v2` depuis `huggingface.co`.

Le build node-side **actuel fonctionne précisément parce que le nœud builder a
Internet sortant au bootstrap** (`get_url`, `become: true`). Un Pod dans un
namespace `default-deny` ne l'a pas. C'est ce qui **condamne** l'option « Job
Kaniko en hook PreSync » (jugée **irréaliste**) : sa NetworkPolicy n'ouvre que
Gitea, registry et DNS — le build **casse au premier `apt-get`**. L'option
confond « clone du contexte air-gappé » (vrai) et « résolution des dépendances
de build air-gappée » (faux). Kaniko cumule deux autres défauts : il écrit en
**root** dans `/` (tension directe avec la Pod Security baseline/restricted,
[ADR 0014](0014-durcissement-kubeadm-init.md), face à un registry qui tourne
déjà `runAsNonRoot`+`readOnlyRootFilesystem`), et il est en **maintenance
réduite**. Surtout, **Kaniko n'aide en rien sur l'air-gap** — le seul vrai
obstacle. **Kaniko est écarté.**

Les deux autres options (Argo Events+Workflows ; Gitea Actions + Image Updater)
sont jugées **réalistes avec réserves**. Le diagnostic en tire la conclusion qui
structure cet ADR : **séparer la fabrique du déploiement**, **assumer un egress
build ciblé**, et **déployer par digest figé**.

## Décision

### 0. Frontière fabrique vs déploiement — l'air-gap protège le déploiement et le runtime, pas la fabrique

L'air-gap ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)) protège le
**chemin de déploiement** (Argo CD ne réconcilie **jamais** depuis Internet) et
le **runtime** (les pods applicatifs ne sortent **jamais** vers Internet). Il ne
protège **pas** la **fabrique d'image** : un `Dockerfile` qui résout ses
dépendances (apt/PyPI/DuckDB/HuggingFace) **a besoin d'Internet au build**.

On **assume** donc, au build et au build seul, un **egress Internet CIBLÉ** :
liste blanche `443` vers PyPI, HuggingFace, miroirs Debian, CDN d'extensions
DuckDB — **jamais `0.0.0.0/0`**. C'est le **vrai trait de conception**, omis ou
nié par les trois options « naïves ». Le builder est traité comme une **zone de
confiance distincte** : il sort vers Internet (ciblé, tracé) ; tout le reste
(Argo CD, registry, pods applicatifs) **reste air-gappé**. Cette frontière est
le pivot de l'ADR ; les deux horizons ci-dessous en découlent.

### 1. Deux horizons explicites — PREMIER PAS sobre, CIBLE événementielle

L'ADR cadre **deux horizons**, présentés tous deux, pour atteindre « zéro geste
manuel » sans pari risqué initial.

#### 1.a Premier pas (à implémenter d'abord) — build Ansible rendu GitOps-compatible

On **garde** le build Ansible node-side existant
([`platform-build-images`](../../bootstrap/roles/platform-build-images/)) — qui
a Internet au bootstrap, est **idempotent** (`changed=0` prouvé) et déjà éprouvé
— mais on le **rend GitOps-compatible** : après `build`+`push`, le rôle **lit le
digest** de l'image (`nerdctl`/`buildkit manifest inspect`) et l'**écrit dans le
repo Gitea `cluster/apps`** (patron `push_gitea_file` de
[`bench/lima/gitea-init.sh`](https://github.com/univ-lehavre/cluster/blob/b522133b7cea/bench/lima/gitea-init.sh),
create-or-update idempotent). Argo CD déploie alors **par digest figé** (§2).

Résultat : **« zéro geste manuel » côté déploiement atteint immédiatement**,
sans rien de neuf et risqué (ni buildkit-in-pod, ni Argo Events, ni egress build
à durcir dans un Pod). Le build reste **déclenché par un `ansible-playbook`**
(geste opérateur unique, assumé) ; **tout le reste est automatique et codé** :
seed, dérivation `pgvector-pg-auth` (§4), déploiement, réconciliation. **Zéro
dérogation
[ADR 0005](0005-cri-containerd-via-depot-docker.md)/[ADR 0033](0033-orchestration-ansible-platform-dataops.md)
sur l'outil** — c'est le même nerdctl/buildkit node-side, simplement complété
d'un write-back de digest.

#### 1.b Cible (horizon) — build ÉVÉNEMENTIEL in-cluster

À terme, le déclenchement du build devient **événementiel**, sans opérateur. La
chaîne :

```text
[atlas/atlas (Gitea)] ── git push (Dockerfile + code-location) ──┐
                                                                 │ webhook Gitea #2 (build)
                                                                 ▼
                        [Argo Events]  capte le webhook (EventSource + EventBus NATS + Sensor)
                                                                 │  instancie un Workflow paramétré par le SHA
                                                                 ▼
                        [Argo Workflows]  pod builder sur un WORKER (jamais le control-plane)
                          clone Gitea@SHA → build (BuildKit) → push registry:80/<app>:<sha12>
                          lit le DIGEST (manifest inspect) → write-back dans cluster/apps
                                                                 │ webhook Gitea #1 (deploy, DÉJÀ câblé)
                                                                 ▼
                        [Argo CD]  réconcilie cluster/apps → Application fille
                          → kubelet pull registry:80/<app>@sha256:… (digest figé)
                          → pod code-location gRPC démarre, run observable
```

**Technologie choisie pour la cible** :

- **Argo Events** capte le webhook Gitea `push` (EventSource webhook + EventBus
  **NATS** + Sensor filtrant la branche). Deux webhooks Gitea **distincts** :
  `#1` push `cluster/apps` → Argo CD (déjà câblé) ; `#2` push code → Argo Events
  (nouveau).
- **Argo Workflows** orchestre
  `clone@SHA → build → push → lit digest → write-back cluster/apps`.
- **BuildKit** est le **moteur de build** — cohérent avec le nerdctl-full /
  buildkit **déjà utilisé node-side**
  ([ADR 0033](0033-orchestration-ansible-platform-dataops.md)). **Kaniko est
  écarté** (cf. §Contexte) : root-fs en tension avec la Pod Security baseline
  ([ADR 0014](0014-durcissement-kubeadm-init.md)), maintenance réduite, et
  surtout **il n'aide en rien sur l'air-gap**.

**Le builder est un Pod sur un WORKER** — **jamais le control-plane** (SPOF
unique du cluster). L'audit prouve que cela tient trivialement (~90 % RAM
libre). Le builder porte une **NetworkPolicy egress build ciblée** : DNS +
Gitea + `registry:80` + **`443` vers la liste blanche Internet** (PyPI / Debian
/ HuggingFace / CDN DuckDB). Sans cet egress, le build casse au premier
`apt-get`.

**Piège réel à coder — buildkitd-in-pod et le registry HTTP.** Le build
node-side actuel pousse vers `registry:80` en HTTP grâce au `hosts.toml`
containerd **du nœud**. Un `buildkitd` **rootless en Pod n'hérite PAS** de ce
`hosts.toml` : il faut lui fournir un **`buildkitd.toml`** déclarant
`registry:80` en `http = true` / `insecure = true`, sinon le `push` échoue
(handshake TLS sur du HTTP). C'est le vrai point dur de la cible, à coder et
**prouver au banc**.

### 2. Déploiement par DIGEST figé (pas tag mutable)

Le builder **lit le digest réel après push**
(`nerdctl`/`buildkit manifest inspect`) et l'**écrit dans `cluster/apps`**
(patron `push_gitea_file`, create-or-update idempotent). Le manifeste de
déploiement référence `registry:80/<app>@sha256:…` → **immuabilité totale** côté
Argo CD/kubelet, conforme
[ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md) (aucune version
flottante) et [ADR 0052](0052-reproductibilite-des-resultats.md). Le **SHA12
git** reste le **tag lisible** (traçabilité commit → image,
[ADR 0094](0094-frontiere-deploiement-applicatif.md) §3 `revision`) ; le
**digest** est l'**ancre d'immuabilité**.

C'est précisément **la séparation build/déploiement** qui rend cela propre : un
hook PreSync Kaniko ne pourrait pas réécrire le manifeste entre PreSync et Sync
(les deux phases lisent la même révision git figée). En **fabriquant avant de
déclarer**, le builder calcule le digest puis l'écrit dans le repo que
réconcilie Argo CD.

**Écart ADR assumé (mineur, documenté).** Un build **mono-arch** in-cluster
produit un digest de **manifest single-arch**, pas un digest d'**index
multi-arch** — le standard
d'[ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md). C'est
**acceptable** sur la prod, qui est **x86-only** (un seul type de nœud) : le
SHA12 immuable satisfait « aucune version flottante » ; seule la **granularité
d'arch** diffère. À **assumer**, pas un bloqueur. (Les images de **plateforme**,
elles, restent épinglées par digest d'**index** multi-arch via Ansible — 0006
inchangé sur ce périmètre.)

### 3. Tout le code sur Gitea — trois repos, miroir GitHub→Gitea en PULL

Gitea est la **source de vérité prod**
([ADR 0044](0044-topologie-deploiement-banc-atlas.md)). **Trois repos** (noms
génériques [ADR 0023](0023-plateforme-exemple-generique.md), injectés au seed) :

| Repo Gitea        | Contenu                                                                                                           | Source                          | Qui écrit                   |
| ----------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------- | --------------------------- |
| `atlas/atlas`     | Code métier complet (Dockerfiles, code-locations, overlays). **Déjà présent.**                                    | Miroir GitHub (code applicatif) | Miroir (lecture)            |
| `cluster/cluster` | Socle **déclaratif** : `platform/`, `storage/`, `contract/`, `docs/decisions/`. **PAS** `bootstrap/` ni `bench/`. | Miroir GitHub (partiel)         | Miroir (lecture)            |
| `cluster/apps`    | Déclarations d'`Application` Argo CD générées + **digest d'image figé**. < 1 Mo.                                  | Généré (seed + builder)         | seed + builder (write-back) |

`bootstrap/` (Ansible **impératif** one-time) et `bench/` (harnais de **test**)
**ne sont pas réconciliables** par Argo CD : ils restent hors du miroir
déclaratif. `cluster/apps` n'est **pas un miroir** (généré localement).

**Miroir GitHub → Gitea = PULL unidirectionnel.** Les repos miroirs sont créés
en mode « Mirror Repository » : **Gitea tire** depuis GitHub (jamais GitHub ne
pousse), via un **CronJob** `gitea-mirror-sync` (horaire) lançant
`gitea admin repo-mirror-sync` depuis un point ayant un egress GitHub
**temporaire**. **Argo CD ne réconcilie JAMAIS depuis GitHub** — uniquement
depuis Gitea local (air-gap déploiement préservé).

**Pourquoi PULL (Cron) et PAS un webhook entrant GitHub → cluster.** Un webhook
de la CI GitHub vers un endpoint Argo Events serait plus **réactif** (déclencher
le miroir/build dès la CI verte, sans latence horaire), mais il **casse
l'air-gap dans le sens entrant** : il faut exposer un **port entrant** du
cluster à Internet, ce qui crée une **surface d'attaque entrante** et une
**dépendance à GitHub pour déployer** — l'exact inverse de la posture
([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)) où **le cluster TIRE,
Internet ne POUSSE jamais**. On **écarte** donc le webhook entrant : la latence
horaire du Cron est le **prix assumé** de l'air-gap. (Alternative sans port
entrant si la réactivité devient nécessaire : un **runner GitHub self-hosted**
qui POUSSE vers Gitea après CI verte — à instruire séparément, hors périmètre.)

**CI de VALIDATION sur GitHub, CI de BUILD + CD in-cluster — trois rôles
distincts.** On sépare nettement **trois** étapes sur **deux** infrastructures :

- **CI-validation = GitHub** (inchangé) : les GitHub Actions du dépôt source
  (lint, test, markdownlint, trivy, kubeconform) **restent sur GitHub** — c'est
  là que le code est **validé** ; seul le code validé est mirroré.
- **CI-build = Argo Workflows in-cluster** (cible, §1.b) : Gitea/cluster
  **construit** l'image.
- **CD = Argo CD** (inchangé, [ADR 0022](0022-argocd-gitops-applicatif.md)) :
  cluster **déploie** par digest figé.

**Gitea de prod ne fait QUE le GitOps** : miroir du code + déploiement (Argo
CD) + build d'image (Argo Workflows). **Pas de Gitea Actions** — éviter de
mirrorer dans un cluster air-gappé les actions `github.com` qu'un workflow Gitea
importerait, et ne pas ajouter la surface d'exécution de code d'un runner
(l'audit relève déjà un RBAC/NetworkPolicy lâches à ne pas aggraver). Mnémonique
: **GitHub VALIDE, Gitea/cluster CONSTRUIT + DÉPLOIE.**

### 4. Fin des gestes manuels — `pgvector-pg-auth` dérivé, seed généralisé

Le Secret `pgvector-pg-auth` (créé à la main, entorse
[ADR 0046](0046-corriger-le-code-pas-l-etat.md)) devient une **étape de seed
CODÉE** : il est **dérivé** du secret `pg-role-pgvector` produit par
CloudNativePG (username/password), exactement comme `dagster-pg-auth` /
`marquez-pg-auth` le sont déjà (cf. la dérivation dans `bench/lima/access.sh`).
La dérivation est idempotente (rejeu `changed=0`).

Le seed (`bootstrap/seed-app-of-apps.sh`, **déjà écrit**) est **généralisé**
pour : (a) dériver `pgvector-pg-auth`, (b) écrire le **digest** (pas le tag
mutable) dans `cluster/apps`, (c) à la cible, poser le **2e webhook** Gitea →
Argo Events. Idempotent et rejouable
([ADR 0034](0034-validation-e2e-from-scratch.md)).

## Conséquences

**Zéro geste manuel.** Côté **déploiement**, atteint **dès le premier pas**
(§1.a) : un `ansible-playbook` build+push+write-back, puis tout est automatique.
À la **cible** (§1.b), le déclenchement du build devient lui aussi automatique
(un `git push` suffit) — bout-en-bout sans opérateur. La dernière entorse
(`pgvector-pg-auth` à la main) **disparaît** (§4).

**Image reproductible-traçable par digest.** Le SHA12 git trace commit → image ;
le digest `sha256:…` ancre l'immuabilité côté Argo CD/kubelet
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)/[ADR 0052](0052-reproductibilite-des-resultats.md)).

**Air-gap déploiement préservé, egress build assumé et tracé.** Argo CD et les
pods applicatifs ne sortent **jamais** vers Internet
([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md) intact). Seul le
**builder** sort, vers une **liste blanche `443` ciblée** (jamais `0.0.0.0/0`),
sous NetworkPolicy dédiée et tracée.

**Frontière du build déplacée — supersede partiel de
[ADR 0033](0033-orchestration-ansible-platform-dataops.md).** Le build des
images **applicatives** passe d'Ansible-INFRA (`run_once`, node-side) à
l'**événementiel in-cluster** (à la cible). Le supersede est **partiel** : il ne
touche **que** le build applicatif ; le build/retag des images **de plateforme**
reste node-side via Ansible, et l'**outil** demeure containerd-natif
(nerdctl/buildkit, **pas Kaniko**). Ce déplacement de frontière **justifie**
l'instruction par ADR (CLAUDE.md : décision structurante).

**Coût assumé.**

- **Surface d'opérateurs (cible)** : Argo Events + Argo Workflows + **NATS** =
  **3 bundles** à vendorer, exclure de prettier/yamllint/jscpd, allowlister le
  RBAC inhérent dans `.trivyignore.yaml`, et **épingler par digest d'index
  multi-arch** ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).
  Bump récurrent — **dette réelle** pour un mono-mainteneur.
- **Event-loss (cible)** : **NATS `replicas:1`** = SPOF transitoire d'un event
  en vol ; or **le build n'a pas de polling natif** (contrairement à Argo CD, ~3
  min côté déploiement). Un push dont l'event est perdu n'est jamais construit
  sans filet → **CronWorkflow de réconciliation** (compare HEAD atlas au tag
  courant). C'est un **filet**, pas l'équivalent du rejeu `changed=0` d'Ansible
  ([ADR 0052](0052-reproductibilite-des-resultats.md)) — honnêteté assumée.
- **buildkitd-in-pod** : `buildkitd.toml` insecure pour `registry:80`,
  NetworkPolicy egress build, rupture de posture (root node-side qui by-passe
  les NetworkPolicies → Pod rootless fencé). À coder et **prouver au banc**.
- **SPOF registry** : `replicas:1` sur PVC RWO, sur le chemin du **build**
  (push) **et** du **déploiement** (pull) ; risque Multi-Attach au reschedule
  sur panne de nœud. SPOF déjà connu
  ([ADR 0011](0011-registry-http-sans-auth.md)), ici **amplifié**.
- **Control-plane SPOF inchangé** : si le control-plane tombe, tout tombe (Argo
  CD, registry). Hors-scope build ; le builder sur worker **n'aggrave pas**.
- **Token Gitea d'écriture `cluster/apps`** (cible) : monté dans le pod builder
  = surface d'élévation (un build compromis peut réécrire les manifestes de
  déploiement). À **cantonner** au scope `cluster/apps`, suivant le patron
  `*.example` versionné + secret généré non versionné
  ([ADR 0023](0023-plateforme-exemple-generique.md), `gen_secret`).

**Réserves honnêtes.**

- **Build non bit-reproductible** : `apt-get` et la base `python:*-slim` ne sont
  **pas lockés** ; un rebuild du même SHA peut produire un digest différent (le
  modèle HuggingFace et les extensions DuckDB sont, eux, figés par révision).
  Traçabilité commit → image **OK** ; bit-reproductibilité **non** — tension
  assumée avec [ADR 0052](0052-reproductibilite-des-resultats.md).
- **Surcharge mono-mainteneur** : 3 opérateurs à maintenir à la cible — d'où le
  **premier pas** sobre comme point de départ non bloquant.
- **buildkit-in-pod moins éprouvé** que le `nerdctl run_once` node-side (qui
  accède directement au containerd du nœud) ; vigilance sur les pièges
  containerd v2 déjà rencontrés au banc.

**Mise en œuvre incrémentale.** Chaque étape est **prouvée au banc** Lima
mono-nœud local-path ([ADR 0085](0085-preuves-applicatives-local-path.md))
**avant** la prod, et **idempotente** (rejeu `changed=0`,
[ADR 0034](0034-validation-e2e-from-scratch.md)) :

1. **Premier pas** (§1.a) : build Ansible + write-back digest + dérivation
   `pgvector-pg-auth` ; gate = `Application` Synced/Healthy, run observable.
2. **Miroir** (§3) : `cluster/cluster` + CronJob `gitea-mirror-sync` ; gate =
   réconciliation 100 % depuis Gitea, **zéro egress GitHub** au sync.
3. **Builder in-cluster** (§1.b) : Workflow builder BuildKit sur worker,
   `buildkitd.toml` insecure, NetworkPolicy egress build ; gate = push code →
   image buildée+poussée par digest, sans geste.
4. **Événementiel** (§1.b) : Argo Events/Workflows/NATS + CronWorkflow filet ;
   gate = push code → pod qui tourne, bout-en-bout.
5. **Prod** : rejeu de chaque étape, builder **sur un worker** (jamais le
   control-plane SPOF).

## Voir aussi

- [ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md) — Air-gap réseau
  (protège déploiement + runtime, **pas** la fabrique).
- [ADR 0005](0005-cri-containerd-via-depot-docker.md) /
  [ADR 0033](0033-orchestration-ansible-platform-dataops.md) — containerd natif
  / build node-side nerdctl-buildkit (outil **conservé** ; frontière build
  applicatif **partiellement supersédée**).
- [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md) — Épinglage par
  digest (écart single-arch x86 assumé ; bundles cible épinglés par index).
- [ADR 0011](0011-registry-http-sans-auth.md) — Registry HTTP sans auth (cible
  de push/pull ; SPOF `replicas:1` amplifié).
- [ADR 0014](0014-durcissement-kubeadm-init.md) — Pod Security (raison de
  l'écart à Kaniko : root-fs).
- [ADR 0022](0022-argocd-gitops-applicatif.md) — Argo CD applicatif (déploie le
  digest figé).
- [ADR 0023](0023-plateforme-exemple-generique.md) — Valeurs génériques (repos,
  secrets, webhook injectés au seed).
- [ADR 0034](0034-validation-e2e-from-scratch.md) /
  [ADR 0046](0046-corriger-le-code-pas-l-etat.md) /
  [ADR 0052](0052-reproductibilite-des-resultats.md) — Validation e2e / corriger
  le code / reproductibilité (idempotence ; entorse `pgvector-pg-auth` rendue au
  code).
- [ADR 0044](0044-topologie-deploiement-banc-atlas.md) — Flux GitOps Gitea →
  Argo CD (miroir GitHub → Gitea en PULL ; Gitea source de vérité).
- [ADR 0085](0085-preuves-applicatives-local-path.md) — Preuves au banc
  local-path (gate de chaque étape).
- [ADR 0086](0086-code-location-jouet-du-socle.md) — Code-location déployée par
  GitOps (l'app fabriquée par cette chaîne).
- [ADR 0094](0094-frontiere-deploiement-applicatif.md) — Frontière de
  déploiement cluster ↔ atlas (App-of-Apps `cluster/apps`, signal canonique
  `revision`).

---
