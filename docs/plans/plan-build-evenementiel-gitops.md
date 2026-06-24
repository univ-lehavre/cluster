# Plan — Build applicatif événementiel in-cluster & déploiement GitOps zéro-touch

## État

> **État : Actif** (2026-06-25) · **Fonde :**
> [ADR 0095](../decisions/0095-build-applicatif-evenementiel-in-cluster.md)
> (Accepted) +
> [ADR 0094](../decisions/0094-frontiere-deploiement-applicatif.md). · **Issues
> :** atlas #499/#501 (déblocage citation). · **Preuve :** bench/lima + scénario
> 34 à écrire.
>
> ADR `Accepted` ⇒ implémentation mergeable
> ([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) §6).
> Ce plan **livre le premier pas** (§1.a de l'ADR, étapes 1-4) ; la **cible
> événementielle** (§1.b, étapes 5-8) est **cadrée mais différée** à des
> itérations ultérieures.

Met en œuvre
[ADR 0095](../decisions/0095-build-applicatif-evenementiel-in-cluster.md) :
rendre la fabrique d'image **applicative** (code-location atlas `citation`,
exemple générique) compatible GitOps **par digest figé**, et **clore les gestes
manuels** résiduels — débloquant le déploiement de `citation` en prod après
preuve banc. La cible (build **événementiel** in-cluster Argo Events / Argo
Workflows / NATS) est tranchée par l'ADR et **différée** : ce plan en pose le
cadre sans l'implémenter.

## ADR fondateurs

- [0095](../decisions/0095-build-applicatif-evenementiel-in-cluster.md) — **le
  cœur** : sépare fabrique vs déploiement ; air-gap protège déploiement+runtime,
  **pas** la fabrique (egress build ciblé assumé) ; déploiement par **digest
  figé** ; deux horizons (premier pas sobre, cible événementielle) ; supersede
  **partiel**
  d'[ADR 0033](../decisions/0033-orchestration-ansible-platform-dataops.md) sur
  la frontière du build applicatif (outil nerdctl/buildkit **conservé**).
- [0094](../decisions/0094-frontiere-deploiement-applicatif.md) — frontière de
  déploiement cluster ↔ atlas, App-of-Apps `cluster/apps`, signal canonique
  `revision` ; pose le **déploiement** que ce plan vient **alimenter** par
  digest.
- [0033](../decisions/0033-orchestration-ansible-platform-dataops.md) — build
  d'images **node-side** (nerdctl/buildkit, `run_once`) ; **réutilisé** au
  premier pas, simplement complété d'un write-back de digest.
- [0046](../decisions/0046-corriger-le-code-pas-l-etat.md) — corriger le
  **code**, pas l'**état** : la dérivation `pgvector-pg-auth` remplace le geste
  manuel (entorse relevée par l'audit, issue atlas #499).
- [0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md) /
  [0052](../decisions/0052-reproductibilite-des-resultats.md) — épinglage par
  digest, reproductibilité (écart single-arch x86 assumé, cf. invariants).
- [0034](../decisions/0034-validation-e2e-from-scratch.md) /
  [0085](../decisions/0085-preuves-applicatives-local-path.md) — preuve banc
  _from-scratch_ AVANT prod ; banc = Lima mono-nœud local-path (plus de banc
  Ceph).
- [0023](../decisions/0023-plateforme-exemple-generique.md) — valeurs génériques
  : `cluster/apps`, `atlas/atlas`, `citation`, `registry:80`,
  `pgvector-pg-auth`, `<app>` ; surcharges réelles injectées au seed, jamais
  versionnées.
- [0086](../decisions/0086-code-location-jouet-du-socle.md) — code-location
  déployée par GitOps (le type d'app fabriqué+déployé par cette chaîne) ; pièges
  workspace reload / conflit Ansible ↔ Argo CD.

## Invariants (repris d'ADR 0095)

1. **Air-gap asymétrique.** Déploiement (Argo CD) et runtime (pods applicatifs)
   restent air-gappés — **jamais** d'egress Internet. Le **BUILD** a un egress
   Internet **ciblé** : au premier pas il l'a **déjà** (build node-side au
   bootstrap, `get_url`/`become: true`) → **aucun changement réseau au premier
   pas**. L'egress build durci dans un Pod (NetworkPolicy liste blanche) est un
   sujet **de la cible** (étape 6).
2. **Déploiement par DIGEST figé** (`registry:80/<app>@sha256:…`), jamais un tag
   mutable. Le SHA12 git reste le tag **lisible** (traçabilité commit → image,
   ADR 0094 §3 `revision`) ; le digest est l'ancre d'immuabilité côté Argo
   CD/kubelet (ADR 0006/0052). Écart **single-arch x86 assumé** : un build
   mono-arch produit un digest de manifest, pas d'index multi-arch ; acceptable
   sur la prod x86-only (ADR 0095 §2).
3. **Corriger le code, pas l'état** (ADR 0046). La dérivation `pgvector-pg-auth`
   (créée à la main en prod, entorse) **repart dans le code**, rejouable
   `changed=0`. Aucun `kubectl create secret` manuel laissé en l'état.
4. **Banc avant prod** (ADR 0034/0052). Le premier pas se prouve **au banc Lima
   mono-nœud local-path** (ADR 0085) AVANT tout geste prod ; tout est
   **idempotent** (rejeu `changed=0`).
5. **Builder hors control-plane.** À la **cible**, le pod builder tourne sur un
   **worker**, jamais le control-plane (SPOF unique). Au premier pas, le build
   reste node-side via Ansible (le nœud builder est désigné par l'inventaire) ;
   l'invariant cadre la cible.
6. **Outil conservé** (ADR 0005/0033) : containerd-natif nerdctl/buildkit, **pas
   Kaniko** (écarté : root-fs en tension avec la Pod Security, maintenance
   réduite, **n'aide en rien sur l'air-gap**).

## Étapes — PREMIER PAS (cœur de ce plan, à implémenter)

> Honnêteté assumée (ADR 0095 §Conséquences) : le premier pas garde le build
> **déclenché par un `ansible-playbook`** (geste opérateur **unique**). « Zéro
> geste manuel » est atteint **côté déploiement** (seed, dérivation, write-back
> et réconciliation tout codés) ; le déclenchement **événementiel** du build est
> la **cible**.

### Étape 1 — Write-back du digest dans le build Ansible

Après `nerdctl push`, lire le **digest réel** de l'image poussée et l'écrire
dans le repo Gitea pour que le déploiement référence
`registry:80/<app>@sha256:…` au lieu d'un tag mutable.

- **ÉDITER**
  [`bootstrap/roles/platform-build-images/tasks/image.yaml`](../../bootstrap/roles/platform-build-images/tasks/image.yaml)
  : après la tâche `Push to the internal registry` (lignes ~66-70), ajouter une
  tâche qui lit le digest via
  `nerdctl manifest inspect {{ build_registry_host }}/{{ img.name }}:{{ img.tag }}`
  (ou `nerdctl image inspect`), extrait le `sha256:…` du **manifest** (pas le
  `Config.Digest` d'image local) et le `register`. **Garde** : le digest DOIT
  matcher `^sha256:[0-9a-f]{64}$` (sinon `fail` explicite — un push raté ne doit
  pas écrire un digest vide, cf. drift « push raté laisse l'ancienne version »).
- **Write-back** : une tâche **tagguée** `write-back-digest` (n'agit que pour
  les images **applicatives**, pas les images de plateforme — porter le
  write-back par un drapeau `img.write_back_digest | default(false)`, à `true`
  seulement sur l'entrée `citation`) écrit ce digest dans Gitea via la
  **Contents API** (create-or-update **idempotent**), en réutilisant le patron
  `push_gitea_file` de
  [`bench/lima/gitea-init.sh`](../../bench/lima/gitea-init.sh) (lit le `sha`
  existant pour une MAJ, **vérifie** la présence de `"commit"` dans la réponse).
  En Ansible, l'équivalent est `kubernetes.core.k8s_exec` du pod gitea + `curl`
  localhost:3000 (piège DNS FQDN : **jamais** le FQDN `*.svc.cluster.local`,
  toujours `localhost` dans le pod — cf. en-tête de `seed-app-of-apps.sh`), OU
  un appel délégué au seed (cf. étape 3). **Recommandé** : factoriser le
  write-back dans une tâche/rôle bash appelé, pour partager **un seul** patron
  Contents API avec le seed.
- **Cible du write-back — à trancher (DÉCISION).** L'ADR 0095 §1.a dit « écrit
  dans `cluster/apps` ». Or la référence d'image **réelle** vit dans l'**overlay
  prod kustomize** du code atlas
  (`dataops/citation-dagster/deploy/overlays/prod/kustomization.yaml`,
  `images[].newTag`) — poussé dans Gitea `atlas/atlas` par le seed. Deux
  options, **prouver au banc** laquelle réconcilie proprement :
  - **(A)** patcher le `images[]` de la kustomization prod **dans
    `atlas/atlas`** (champ `digest:` kustomize →
    `registry:80/citation-dagster@sha256:…`) au SHA poussé. Plus fidèle à
    kustomize, mais écrit dans le repo **miroir** (tension : `atlas/atlas` est
    censé être un miroir lecture — acceptable tant que le seed en est l'unique
    writer, comme aujourd'hui via `git push --force`).
  - **(B)** écrire le digest dans `cluster/apps` (ex. un overlay/patch côté
    déclaration `apps/citation.yaml`, ou un fichier `apps/citation.digest`
    consommé par l'Application). Conforme à la lettre de l'ADR (`cluster/apps`
    seul repo écrit par le builder), mais demande à l'Application de
    **surcharger** l'image (kustomize `images` injecté côté Argo CD `source`, ou
    2ᵉ source).
  - **Reco initiale** : (A) au premier pas (le seed pousse déjà tout l'arbre
    atlas, le patch d'un seul champ est local et idempotent) ; (B) cadré comme
    évolution propre quand `cluster/apps` deviendra l'unique surface de
    déclaration. La décision est **prouvée par le scénario 34**, pas postulée.
- **Preuve SANS banc** : `ansible-lint` + `yamllint` (tâche ajoutée), rendu de
  la tâche (dry-run `--check` : le pré-check `manifest inspect` tourne déjà en
  `check_mode: false`, ADR 0051), `shellcheck` si patron bash factorisé.
- **Preuve banc** : build d'une **image jouet** (ex. l'entrée émetteur
  `dagster-openlineage-emit:dev` déjà prévue, ou une entrée jouet dédiée) →
  digest lu → écrit dans le repo cible → relu et vérifié `== sha256` poussé.

### Étape 2 — Dérivation codée de `pgvector-pg-auth` (fin de l'entorse ADR 0046)

Le Secret `pgvector-pg-auth` (ns `dagster`) doit être **dérivé par le code** du
secret `pg-role-pgvector` (ns `postgres`, `username`/`password` produits par
CloudNativePG), jamais créé à la main (entorse ADR 0046, issue atlas #499).

- **État du code.** Le rôle
  [`platform-dagster`](../../bootstrap/roles/platform-dagster/tasks/main.yaml) a
  **déjà** la dérivation
  (`Derive the pgvector Postgres Secret for atlas code-locations`, lignes
  ~96-108, var `pgvector_pg_auth_secret` = `pgvector-pg-auth`, source
  `pg-role-pgvector`). **MAIS** elle vit dans le même bloc `run_once` que
  `Apply Dagster manifest` et le **workspace** : un rejeu du rôle complet
  **réécrit le workspace dagster** (piège
  [ADR 0086](../decisions/0086-code-location-jouet-du-socle.md), vérifié — un
  dry-run montre `configmap/dagster-workspace configured`). Rejouer
  `platform-dagster` pour (re)poser le secret n'est donc **pas** anodin.
- **Faire — option (a) recommandée.** **Extraire** la dérivation du secret
  (`Read the CNPG pgvector role credentials` + `Assert …` +
  `Derive the pgvector Postgres Secret …`, lignes ~79-108) sous un **tag dédié**
  `pgvector-secret`, rejouable **seul**
  (`ansible-playbook bootstrap/dataops.yaml --tags pgvector-secret`) **sans
  toucher au workspace** ni au reste du rôle. Idempotent `changed=0` (la
  dérivation `k8s` est déclarative — re-pose le même contenu).
- **Alternative — option (b).** Porter la dérivation dans le **seed** (modèle
  `secret_val` de [`bench/lima/access.sh`](../../bench/lima/access.sh) lignes
  ~188-226, qui lit déjà `pg-role-pgvector`) : le seed lit le secret CNPG et
  pose `pgvector-pg-auth` avant de créer l'Application. **Reco : (a)** — garder
  la dérivation dans le rôle qui en est propriétaire, juste rendue **rejouable
  isolément** par un tag.
- **Preuve** : rejeu de la **tâche seule** (`--tags pgvector-secret`) →
  `pgvector-pg-auth` présent dans `dagster`, contenu (`username`/`password`)
  **== source** `pg-role-pgvector`, **workspace dagster INTACT** (aucun
  `configmap/dagster-workspace configured` dans le diff du rejeu) ; second rejeu
  `changed=0`.

### Étape 3 — Généraliser le seed pour le déploiement complet `citation`

Intégrer dans
[`bootstrap/seed-app-of-apps.sh`](../../bootstrap/seed-app-of-apps.sh) la chaîne
complète, avant de créer l'Application, en **gardant** les gardes prod
existantes.

- **Faire** : enrichir le seed pour (a) **déclencher le build** (ou **vérifier**
  l'image présente par digest via `manifest inspect` — au minimum vérifier
  qu'elle existe avant de déclarer, sinon `die` explicite), (b) **write-back du
  digest** dans le repo cible (étape 1 — factoriser le **même** patron Contents
  API `push_contents_file`/`push_gitea_file`), (c) **dériver
  `pgvector-pg-auth`** (étape 2, via `--tags pgvector-secret` délégué OU port du
  `secret_val`), puis injecter le **digest** (pas le tag mutable) dans
  `apps/citation.yaml` / l'overlay prod selon la décision étape 1.
- **Gardes conservées** : `assert_prod_target` (contexte = `cluster-prod`),
  `print_plan` + confirmation `oui`, `--dry-run` / `--yes`, port-forward + piège
  DNS, creds Gitea lus du Secret `gitea-admin` (jamais versionnés).
  **Idempotent** (rejeu re-pousse le même digest, no-op).
- **Preuve** : `--dry-run` du seed (plan affiché, **rien muté**) ; puis
  exécution **banc** (cible banc, pas prod) prouvée par le scénario 34.

### Étape 4 — Scénario banc 34 (preuve e2e du premier pas)

- **CRÉER** `bench/scenarios/34-build-gitops-digest.sh` : prouve sur le banc
  Lima local-path qu'un **build → push → write-back digest → Application
  réconciliée par Argo CD → pod qui tourne**, **par DIGEST**. Calque la
  structure du scénario [27](../../bench/scenarios/27-gitops-workflow-deploy.sh)
  (skip neutre si la chaîne GitOps absente, `STRICT_*=1` pour échouer en CI ;
  assertions pures testables en bats via `gitops-assert.sh` ; idempotent +
  `trap EXIT`).
- **Gate** : (1) le manifeste déployé référence l'image par `@sha256:…` (pas un
  tag) ; (2) l'`Application` (`citation-dagster` ou app jouet) est
  **Synced/Healthy** ; (3) le pod code-location gRPC est **Ready** et tiré par
  digest (`kubectl get pod -o jsonpath …image` contient `@sha256`) ; (4) rejeu
  du seed → `changed`/no-op stable (idempotence).
- **Catalogue** : ajouter la ligne **34** dans la matrice de
  [`bench/scenarios/README.md`](../../bench/scenarios/README.md) (n°, sujet,
  tests, durée, couverture) + l'arbre ASCII.

## Étapes — CIBLE (cadrée, **différée**, NON implémentée dans ce plan)

> Chacune est tranchée par
> [ADR 0095](../decisions/0095-build-applicatif-evenementiel-in-cluster.md)
> §1.b/§3 et **différée à une itération ultérieure**, **prouvée au banc avant
> prod**. Elles ne sont **pas** livrées par ce plan — il en pose le cadre.

### Étape 5 (cible / différé) — Vendorer Argo Events + Argo Workflows + NATS

Trois bundles upstream, **épinglés par digest d'index multi-arch**
([ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md),
vérifier `MediaType: …image.index…`), **exclus** de prettier/yamllint/jscpd
(comme `platform/{cert-manager,argocd}`), RBAC inhérent **allowlisté** dans
`.trivyignore.yaml` avec justification par chemin. **Dette de bump récurrent**
assumée (mono-mainteneur, ADR 0095 §Coût).

### Étape 6 (cible / différé) — Workflow builder BuildKit-in-pod sur worker

Pod `buildkitd` **rootless sur un worker** (jamais le control-plane, invariant
5). Point dur : `buildkitd` en Pod **n'hérite pas** du `hosts.toml` du nœud →
fournir un **`buildkitd.toml`** déclarant `registry:80` en `http = true` /
`insecure = true` (sinon `push` échoue en handshake TLS sur du HTTP).
**NetworkPolicy egress build** = liste blanche `443` (PyPI / HuggingFace /
miroirs Debian / CDN DuckDB) + DNS + Gitea + `registry:80` — **jamais
`0.0.0.0/0`**. **À coder et prouver au banc.**

### Étape 7 (cible / différé) — Argo Events (webhook Gitea #2) + filet event-loss

EventSource webhook Gitea (push code → build) + **EventBus NATS** + Sensor
filtrant la branche, instanciant un Workflow paramétré par le SHA. Deux webhooks
Gitea **distincts** : `#1` push `cluster/apps` → Argo CD (**déjà câblé**) ; `#2`
push code → Argo Events (**nouveau**, posé au seed). **NATS `replicas:1` = SPOF
transitoire** d'un event en vol → **CronWorkflow de réconciliation** (compare
HEAD atlas au tag courant) comme **filet** (pas l'équivalent du rejeu
`changed=0` Ansible — honnêteté assumée, ADR 0095 §Coût).

### Étape 8 (cible / différé) — Miroir GitHub → Gitea en PULL

Repos miroirs `cluster/cluster` (+ `atlas/atlas`) en mode « Mirror Repository »
: **Gitea TIRE** depuis GitHub (jamais GitHub ne pousse), via **CronJob**
`gitea-mirror-sync` (`gitea admin repo-mirror-sync`, egress GitHub
**temporaire**). **Argo CD ne réconcilie JAMAIS depuis GitHub** — air-gap
déploiement préservé (ADR 0095 §3). Webhook entrant GitHub → cluster **écarté**
(casserait l'air-gap entrant). Mnémonique : **GitHub VALIDE, Gitea/cluster
CONSTRUIT + DÉPLOIE.**

## Stratégie de preuve

- **Premier pas (étapes 1-4) prouvable au banc Lima local-path MAINTENANT.**
  Tout le chemin (build jouet → write-back digest → Application Synced/Healthy →
  pod tiré par `@sha256`) tient sur le banc mono-nœud
  ([ADR 0085](../decisions/0085-preuves-applicatives-local-path.md)). Une fois
  le scénario 34 **PASS** + idempotence (`changed=0`) consignés dans
  [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md), le déploiement de
  `citation` est **débloqué en prod** (seed sur cible `cluster-prod`).
- **Cible (étapes 5-8) = itérations suivantes**, **chacune un run banc** avant
  prod (vendoring → buildkit-in-pod → Argo Events → miroir), dans l'ordre de
  l'ADR 0095 §Mise en œuvre incrémentale.
- **Honnêteté.** Le premier pas garde le build déclenché par `ansible-playbook`
  (**geste opérateur unique assumé**) : « zéro geste manuel » est atteint **côté
  déploiement** (seed/dérivation/write-back/réconciliation tout codés), le build
  **événementiel** est la cible. Réserves ADR conservées : build non
  bit-reproductible (apt/base non lockés) ; SPOF registry `replicas:1` amplifié
  ; écart digest single-arch x86.

## Suivi

- [ ] **Étape 1** — write-back digest dans
      `platform-build-images/tasks/image.yaml` (lecture `manifest inspect`,
      garde `sha256`, tâche tagguée `write-back-digest`, patron Contents API
      factorisé) ; **DÉCISION** cible du write-back (A) `atlas/atlas` overlay
      prod vs (B) `cluster/apps` — tranchée par le scénario 34.
      `ansible-lint`/`yamllint` verts.
- [ ] **Étape 2** — dérivation `pgvector-pg-auth` extraite sous tag dédié
      `pgvector-secret` (option a), rejouable seule **sans toucher au
      workspace** ; rejeu `changed=0`, contenu == `pg-role-pgvector`.
- [ ] **Étape 3** — `seed-app-of-apps.sh` généralisé : (a) build/vérif image,
      (b) write-back digest, (c) dérivation `pgvector-pg-auth`, injection
      **digest** (pas tag) ; gardes prod conservées ; `--dry-run` propre.
- [ ] **Étape 4** — scénario `34-build-gitops-digest.sh` créé + matrice
      `bench/scenarios/README.md` (n° 34) ; **joué au banc** (Application
      Synced/Healthy, pod tiré par `@sha256`, idempotence) → `RESULTS.md`.
- [ ] **Déblocage prod** — seed sur `cluster-prod` après preuve banc ; clôture
      atlas #499 (`pgvector-pg-auth` rendu au code) / #501 (citation déployée).
- [ ] **Étape 5 (cible / différé)** — vendoring Argo Events + Argo Workflows +
      NATS (digest index multi-arch, exclusions lint, `.trivyignore`).
- [ ] **Étape 6 (cible / différé)** — Workflow builder BuildKit-in-pod sur
      worker (`buildkitd.toml` insecure `registry:80`, NetworkPolicy egress
      build).
- [ ] **Étape 7 (cible / différé)** — Argo Events (webhook Gitea #2 + EventBus
      NATS + Sensor) + CronWorkflow filet event-loss.
- [ ] **Étape 8 (cible / différé)** — miroir GitHub → Gitea en PULL
      (`cluster/cluster` + CronJob `gitea-mirror-sync`), zéro egress GitHub au
      sync Argo CD.
