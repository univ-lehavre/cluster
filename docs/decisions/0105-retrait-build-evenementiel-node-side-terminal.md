# 0105 — Retrait du build événementiel in-cluster : le build node-side devient terminal

## Statut

Accepted (2026-07-08).

**Supersede partiel de
[0095](0095-build-applicatif-evenementiel-in-cluster.md)** : abroge le §1.b
(build **événementiel** in-cluster : webhook Gitea #2 → Argo Events → Argo
Workflows → BuildKit → write-back), et **promeut le §1.a (build Ansible
node-side) comme mécanisme TERMINAL**, plus un « premier pas » transitoire.
**Conserve** les §2 (déploiement par digest figé), §3 (miroir GitHub→Gitea), §4
(dérivations seed). S'appuie sur [0046](0046-corriger-le-code-pas-l-etat.md)
(corriger le code, pas l'état),
[0006](0006-matrice-de-versions-et-politique-de-bump.md) (digest figé),
[0052](0052-reproductibilite-des-resultats.md) (reproductibilité). Sans effet
sur [0103](0103-workspace-dagster-multi-code-location-reconciler.md) (le
reconciler de workspace est un **CronJob k8s natif**, pas un Argo Workflow).

## Contexte

L'[ADR 0095](0095-build-applicatif-evenementiel-in-cluster.md) cadrait **deux
horizons** pour fabriquer l'image applicative atlas : un **premier pas** sobre
(§1.a, build Ansible node-side rendu GitOps-compatible par write-back du digest)
et une **cible événementielle** (§1.b, déclenchement par `git push` via Argo
Events + Argo Workflows). Les DEUX ont fini déployées en prod dirqual, **en
parallèle** — et c'est le désordre.

**Défaut mesuré (2026-07-08, prod).** La chaîne événementielle §1.b est
**instable et redondante** :

- **Amplification.** Le seed (`push_atlas_tree`) pousse l'arbre atlas complet en
  `git push --force main:main` (légitime : il épingle l'arbre au SHA de
  `targetRevision`). Gitea émet alors des **dizaines d'events push** ; le Sensor
  `code-location-build` (lecture `body.commits.0.modified.0`) instancie **un
  Workflow par event** → **~45 builds `image-builder` identiques en parallèle**
  pour un **seul** push (mesuré : 48 livraisons webhook, ~45 builds citation
  même révision, créés en ~9 s).
- **Taux d'échec.** ~**52 %** (612 Failed / 565 Succeeded historiques) — chaque
  re-seed rallume une rafale.
- **Divergence d'images.** Les deux chaînes produisent des **digests
  concurrents** (node-side vs eventful) : constaté un pod gRPC déployé sur une
  image eventful **périmée** (sans les correctifs mergés) pendant que
  `DAGSTER_CURRENT_IMAGE` pointait le digest node-side correct — deux images
  dans le même Deployment.

**Alternative évaluée et rejetée : Argo CD Image Updater** (« le registre
notifie Argo »). Écartée pour des raisons vérifiées dans le dépôt : (a) il ne
**build** pas — `platform-build-images` reste requis pour pousser l'image ; (b)
son write-back **git** committerait dans `atlas/atlas` — que les Applications
lisent mais qui est un **miroir en lecture** (§3) → divergence garantie au
prochain sync ; (c) son mode `argocd` déploie par **tag mutable hors-Git** →
viole [0006](0006-matrice-de-versions-et-politique-de-bump.md)/[0046]/[0052] ;
(d) en air-gap, il **poll `docker.io`** par défaut (surface de risque, zéro
bénéfice). Il n'apporte rien que le §1.a ne fasse déjà mieux (immuabilité native
: le builder lit le digest de **ce qu'il vient de pousser**, pas d'un tag à
suivre).

## Décision

> **On RETIRE la chaîne de build événementiel in-cluster (§1.b d'ADR 0095) et on
> fait du build Ansible node-side (§1.a) le mécanisme TERMINAL de fabrique
> d'image. Le déclencheur du déploiement reste le SEED (write-back du digest
> figé dans l'overlay Gitea), qu'Argo CD réconcilie — inchangé.**

### 1. Le chemin conservé — node-side → seed → Argo CD (PROUVÉ)

Inchangé et déjà en service : `nestor ansible code-location-build.yaml`
(`platform-build-images`) **build + push** `registry:80/<cl>-dagster`, **lit le
digest réel** (`nerdctl image inspect … RepoDigests`), le seed l'**injecte**
dans `kustomization.yaml` (`images: digest:`) de l'overlay prod poussé dans
Gitea `atlas/atlas`, et **Argo CD déploie** par digest figé (§2 conservé).
**Prouvé le 2026-07-08** : Sensor eventful suspendu (replicas 0), re-seed →
**SEED_EXIT=0, 0 build déclenché, Argo réconcilie le digest seedé, 3
Applications Synced/Healthy**. Le §1.b n'était donc que du **bruit redondant**
par-dessus un chemin déjà complet.

### 2. Ce qui est RETIRÉ

Le rôle `platform-eventful` et les manifestes qu'il applique — **la chaîne §1.b
uniquement** :

- **Argo Events** (`platform/argo-events/`) : EventSource `gitea-push`, Sensor
  `code-location-build`, EventBus **NATS**, RBAC de soumission.
- **Argo Workflows — VOLET BUILD** (`platform/argo-workflows/`) :
  WorkflowTemplate `image-builder`, `builder-rbac`, ConfigMap `buildkitd`,
  CronWorkflow `builder-reconcile` (filet event-loss du build), NetworkPolicies
  du build.
- Le **webhook Gitea #2** (build) et le Secret HMAC associé, le miroir de build
  (`bootstrap/eventful-mirror.yaml`), le playbook `bootstrap/eventful.yaml`.
- La couche `eventful` de la topologie et ses références dans le moteur de
  chemin.

**Bilan-dette : −3 opérateurs (Argo Events + Argo Workflows + NATS), +0** —
aucun remplaçant à construire, le §1.a est déjà le terminal en service.

### 3. Ce qui est CONSERVÉ (ne pas confondre)

- **§2 (digest figé)**, **§3 (miroir GitHub→Gitea)**, **§4 (dérivations seed)**
  d'ADR 0095 : inchangés.
- Le **reconciler de workspace Dagster**
  ([ADR 0103](0103-workspace-dagster-multi-code-location-reconciler.md)) est un
  **CronJob k8s natif** (`platform/dagster/reconciler.yaml`) — **AUCUN** lien
  avec Argo Workflows/Events : il survit intégralement.
- Le webhook Gitea **#1 (deploy)** vers Argo CD et le reste du seed : inchangés.

## Conséquences

**Positif.** Une seule chaîne de build (plus de digests concurrents ni de
divergence d'images) ; plus de tempête de webhooks (le déclencheur webhook #2
disparaît) ; −3 opérateurs à opérer/patcher/sécuriser ; surface d'attaque et
charge réduites. Le build redevient un **geste opérateur unique assumé**
(`nestor ansible`), fiable et idempotent, cohérent avec le §1.a d'origine.

**Négatif / assumé.** On abandonne le « zéro geste » du déclenchement par push
pour la **fabrique** (le déploiement, lui, reste zéro-geste : seed → Argo).
C'est un recul délibéré vers la sobriété : la cible événementielle d'ADR 0095
était un **pari** dont le coût réel (instabilité, amplification, 52 % d'échec)
dépassait le bénéfice. Si un jour un déclenchement automatique de build
redevient souhaitable, il devra repartir d'un design qui **déduplique** (un
build par (code-location, révision), pas par event) — ce que l'ancien Sensor ne
faisait pas.

**Preuve (ADR 0052/0034).** From-scratch au banc par chemin nommé codé : monter
une code-location par `platform-build-images` + seed **sans**
`platform-eventful`, prouver le déploiement du digest par Argo, idempotence
`changed=0` au rejeu, et **absence de tempête** (0 Workflow `image-builder` créé
après un push). Sur prod dirqual : suspension du Sensor déjà prouvée concluante
(cf. §1).
