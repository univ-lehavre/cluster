# Plan d'implémentation — Build de code in-pod sur pré-image (ADR 0110)

## État

> **État : Superseded** (2026-07-12) par
> [ADR 0112](../decisions/0112-cicd-in-cluster-gitea-actions-buildkit.md)
> (Accepted). Ce plan fondait
> [ADR 0110](../decisions/0110-preimage-de-build-et-build-in-pod.md) et
> proposait un **déclencheur Sentinelle/Job** (« Pas Gitea Actions »). La
> réalité livrée diverge : l'**ADR 0112 a rétabli le build in-pod** (moteur
> BuildKit rootless prouvé au banc — scénario 35, PR #650) mais **via Gitea
> Actions**, pas la Sentinelle. Le « comment » réel vit désormais dans l'ADR
> 0112 et dans
> [`platform/buildkit/RUNBOOK.md`](../../platform/buildkit/RUNBOOK.md) /
> [`platform/gitea-runner/RUNBOOK.md`](../../platform/gitea-runner/RUNBOOK.md).
> Ce plan est conservé pour trace historique du raisonnement ; ses lots sont
> relus ci-dessous (moteur prouvé, point dur fuse-vs-native tranché).
>
> <!-- historique -->
>
> **État initial (2026-07-11)** · **Fonde :
> [ADR 0110](../decisions/0110-preimage-de-build-et-build-in-pod.md)**
> (Accepted) · **Issue de pilotage :
> [#637](https://github.com/univ-lehavre/cluster/issues/637)** ·
> **Implémentation débloquée** (ADR 0110 acté le 2026-07-11,
> [ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) §6).

Met en œuvre [ADR 0110](../decisions/0110-preimage-de-build-et-build-in-pod.md)
: faire construire l'**image de code** d'une code-location Dagster **dans le
cluster** (in-pod, sans réseau), une fois la **pré-image** de dépendances
disponible au registre. Ce plan est le **comment** (côté `cluster`) ; la
décision (le **pourquoi**) est dans l'ADR. Le volet `atlas` (split du Dockerfile
en deux cibles, garde-fou de fraîcheur, script de build de la pré-image) est
**déjà livré** (atlas#608/#609/#610). Il reste le **moteur de build in-pod** et
son **déclenchement**, tous deux côté `cluster`.

## Principe d'architecture

Décliner les patrons **existants** du dépôt, sans inventer de mécanique nouvelle
:

- **Moteur** : BuildKit (déjà le moteur node-side via `nerdctl-full`), mais
  **rootless in-pod** — un `Deployment buildkitd` dans un namespace `buildkit`,
  calqué sur le durcissement de `platform/container-registry/deployment.yaml`.
- **Déclencheur** : un **Job de build** piloté par la **Sentinelle** (CronJob
  API-only, moule reconciler
  [ADR 0103](../decisions/0103-workspace-dagster-multi-code-location-reconciler.md),
  patron `platform/dagster/reconciler.yaml`). **Pas** Gitea Actions (rejet
  [ADR 0095](../decisions/0095-build-applicatif-evenementiel-in-cluster.md) §3
  non rouvert).
- **Registre** : le pod n'hérite **pas** du `hosts.toml`/`certs.d` du nœud → un
  `buildkitd.toml` **in-pod** déclare `registry:80` en `http`/`insecure`, et la
  résolution passe par le **DNS cluster** (`registry.registry.svc`), pas
  `/etc/hosts`.
- **Réseau** : `default-deny` + trois `allow` chirurgicaux (DNS, registry:80,
  Gitea:3000) — **zéro egress 443** (air-gap
  [ADR 0044](../decisions/0044-topologie-deploiement-banc-atlas.md) ; c'est tout
  l'intérêt de la pré-image : l'image de code ne télécharge rien).
- **Activation** : un `Component` dans `nestor/graph.py`
  (`deps=("registry", "build-images")`), appliqué par un rôle
  `platform-buildkit` — **pas** l'App-of-Apps ArgoCD (l'infra platform est
  Ansible, frontière
  [ADR 0022](../decisions/0022-argocd-gitops-applicatif.md)/[ADR 0033](../decisions/0033-orchestration-ansible-platform-dataops.md)).

### Ce qui NE change PAS (rassurant)

- **Le write-back du digest** : le Job in-pod lit le digest de l'image qu'il
  pousse (comme le fait `nerdctl image inspect RepoDigests` node-side), le
  **seed publie** dans Gitea `cluster/apps`, Argo CD déploie par digest figé
  ([ADR 0105](../decisions/0105-retrait-build-evenementiel-node-side-terminal.md)
  §1.a). Mécanisme inchangé.
- **Le build node-side** (`platform-build-images`) reste, **rétrogradé en
  secours** (build de la pré-image si le poste n'est pas disponible).

## Périmètre — ce que ce plan fait / ne fait pas (ADR 0110)

**Fait** : le moteur `buildkitd` in-pod, sa config registre, ses
NetworkPolicies, le Job de build de l'**image de code** (cible `code`, zéro
egress), le déclenchement par la Sentinelle, l'activation dans le graphe.

**Ne fait pas** (hors périmètre, déjà tranché ailleurs) : le split du Dockerfile
et le garde-fou (livrés côté `atlas`) ; le build de la **pré-image** (geste
poste, `build-deps-base.sh`, atlas#610) ; l'**acheminement `main` GitHub →
Gitea** (reste [ADR 0106](../decisions/0106-gitops-zero-geste-sentinelle.md) §6,
orthogonal — sans lui la Sentinelle n'a rien à détecter, mais c'est un lot
distinct).

## Le point dur (à prouver au banc en priorité)

**BuildKit rootless sous le durcissement du dépôt.** Le style maison est
universellement durci (`runAsNonRoot`, `readOnlyRootFilesystem`,
`capabilities.drop:[ALL]`, `seccompProfile: RuntimeDefault`). Or BuildKit
rootless a besoin de syscalls (`clone`/`unshare`/`mount`) que `RuntimeDefault`
bloque, et d'un snapshotter. Deux voies, **à départager au banc (lot 2)** :

- **`fuse-overlayfs`** : rapide, mais exige `/dev/fuse` +
  `seccompProfile: Unconfined` → **dérogation** au style maison (tolérée par le
  PodSecurity réel `baseline`, interdite par `restricted`). À documenter par un
  commentaire dans le manifeste.
- **snapshotter `native`** : évite `/dev/fuse`, moins de dérogation, mais **plus
  lent** (copie au lieu d'overlay). Acceptable car l'image de **code** est
  petite (le lourd est dans la pré-image).

On conçoit d'abord avec `fuse-overlayfs` (défaut BuildKit) ; le choix final se
tranche à la **preuve du lot 2**. **Aucun** recours à `privileged`/`hostPath`/
`hostNetwork` (aucun précédent dans un ns PodSecurity-labellisé, et `baseline`
les bloque).

> **Tranché (2026-07-12, ADR 0112).** Le point dur est **résolu** : le
> snapshotter `auto` démarre en **overlayfs sans `/dev/fuse`** et le build
> in-pod réussit (aucune dérogation `fuse` finalement nécessaire). Le moteur
> BuildKit rootless est prouvé au banc (scénario 35, PR #650). Détail
> d'exploitation :
> [`platform/buildkit/RUNBOOK.md`](../../platform/buildkit/RUNBOOK.md) §3.

Note de cadrage (corrige l'ADR) : l'ADR 0110 dit « à prouver sous `restricted` »
; l'enforce **réel** du dépôt est `baseline`
([ADR 0014](../decisions/0014-durcissement-kubeadm-init.md), `restricted`
seulement en `warn`) — plus permissif, ce qui **autorise** la dérogation
`fuse`/seccomp sans changer la politique du cluster.

## Découpage en lots (issues)

> ADR 0110 **acté** (`Accepted`, 2026-07-11) → les lots sont **débloqués** (ADR
> 0057 §6). Un lot = une PR, re-prouvée sur banc avant la suivante.

0. **Acter l'ADR** — ✅ fait : ADR 0110 `Proposed → Accepted`, cet en-tête
   `Brouillon → Actif`, issue de pilotage
   [#637](https://github.com/univ-lehavre/cluster/issues/637) ouverte
   (2026-07-11).
1. **Socle `buildkitd`** — `platform/buildkit/` : `namespace.yaml`
   (`enforce: baseline`/`warn: restricted`, idiome gitea/registry),
   `buildkitd-deployment.yaml` (durci comme container-registry, image par
   digest), `buildkitd-config.yaml` (ConfigMap montant le `buildkitd.toml` :
   `registry:80` http/insecure). + `platform/network-policies/buildkit/`
   (`00-default-deny` + `allow-dns` + `allow-registry-egress` port 80). Rôle
   `bootstrap/roles/platform-buildkit` (calqué `platform-dagster` :
   default-deny-first en `loop:`). Composant dans `nestor/graph.py`
   (`deps=("registry","build-images")`, **insérer sans réordonner** — la byte-
   identité du catalogue en dépend). **Pas encore de build.**
2. **Preuve « un pod qui build »** (ADR 0034/0052) — **le lot décisif**. Prouver
   au banc qu'un `buildctl` in-pod build l'image de **code**
   (`FROM deps-base@sha256`, `--network=none`, `UV_OFFLINE=1`) et la pousse au
   registre. Départager **`fuse-overlayfs` vs `native`** ici. Prérequis : une
   pré-image `citation-deps-base:<SHA_DEPS>` présente au registre (build sur le
   poste, atlas#610). Consigner le cycle dans `bench/lima/RESULTS.md`. **Sans ce
   run, le moteur reste déclaré mais non prouvé.**
3. **Job de build** — `platform/buildkit/build-job.yaml` (calqué
   `platform/dagster/reconciler.yaml` : SA+Role+RoleBinding minimaux,
   `concurrencyPolicy: Forbid`, `ttlSecondsAfterFinished`,
   `restartPolicy: OnFailure`, image mirrorée `registry:80/…`). Il : (a) build
   l'image de code à une révision, (b) lit le digest, (c) déclenche le
   write-back (seed). Paramétré par code-location. + `allow-gitea-egress`
   (port 3000) si le Job pousse le digest.
4. **Sentinelle** — le CronJob de détection d'écart de révision (moule
   reconciler 0103, conservé d'ADR 0106 §1-détection) : compare le SHA amont
   (Gitea) au digest déployé, et sur écart **déclenche le Job (3)** au lieu de
   l'ancien timer node-side. Reprend la doctrine anti-amplification/coalescing
   d'ADR 0106 §2-§3, adaptée au Job (`concurrencyPolicy: Forbid` + état par
   code-location).
5. **Amender ADR 0106** — repointer le timer node-side sur la **pré-image**
   (secours), acter la Sentinelle sur le Job in-pod. (Peut se faire au lot 0 si
   la revue le préfère.)
6. **Preuve de bout en bout** (ADR 0034) — un merge → Sentinelle détecte → Job
   build in-pod → write-back digest → Argo CD déploie la code-location fraîche.
   Consigner dans `bench/lima/RESULTS.md`. C'est la preuve du « push = auto » (à
   l'astérisque `uv.lock` près, cf. ADR 0110).

## Validation

`pnpm lint` (format, yamllint, shellcheck, kubeconform, ansible-lint, jscpd,
bats), `pnpm audit:docs` (liens, compteurs ADR), `pnpm check:gouvernance`.
kubeconform valide les manifestes. Conventional Commits sujet minuscule, hooks
lefthook jamais bypassés, merge commit (chaque commit propre). Un lot = une PR,
re-prouvée sur banc avant la suivante (ADR 0034). Les lots 2 et 6 exigent un run
de banc consigné.

## Suivi (ADR 0057)

Issue de pilotage : [#637](https://github.com/univ-lehavre/cluster/issues/637)
(les lots ci-dessous y sont des cases à cocher).

> **Relu 2026-07-12 (ADR 0112).** Le moteur et la preuve bout-en-bout sont
> **acquis**, mais par une chaîne **différente** de celle planifiée : le
> déclencheur retenu est **Gitea Actions** (ADR 0112), pas la Sentinelle/Job des
> lots 3-4 (qui deviennent **caducs**). États réels ci-dessous.

| Lot                                          | État                                                                      |
| -------------------------------------------- | ------------------------------------------------------------------------- |
| 0. Acter l'ADR 0110 (`Accepted`)             | ✅ fait (2026-07-11) — débloque le reste                                  |
| 1. Socle `buildkitd` + netpol + graphe       | ✅ fait — `platform/buildkit/` rétabli (ADR 0112)                         |
| 2. Preuve « un pod qui build » (fuse/native) | ✅ prouvé au banc (ADR 0112 ; snapshotter `auto`/overlayfs, **pas** fuse) |
| 3. Job de build (moule reconciler)           | ⛔ caduc — remplacé par Gitea Actions (ADR 0112)                          |
| 4. Sentinelle (détection → Job)              | ⛔ caduc — remplacé par Gitea Actions (ADR 0112)                          |
| 5. Amender ADR 0106 (timer → pré-image)      | 🔲 à faire                                                                |
| 6. Preuve bout-en-bout (`RESULTS.md`)        | ✅ prouvé — scénario 35, PR #650 (via Gitea Actions)                      |

**Achèvement** : quand les lots 1-6 sont livrés sur `main` et les runs de preuve
(2, 6) consignés, l'en-tête `## État` passe **Achevé**. Le passage **Brouillon →
Actif** a eu lieu au lot 0 (acceptation de l'ADR 0110, 2026-07-11).
