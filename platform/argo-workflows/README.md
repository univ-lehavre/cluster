# Argo Workflows — moteur de build in-pod (cible événementielle)

Exécute des **workflows conteneurisés** dans le cluster : dans la chaîne
événementielle (ADR 0095 §1.b), c'est le moteur de **build in-pod** déclenché en
bout de chaîne (un `Sensor` Argo Events soumet un `Workflow` qui
construit/publie une image ou un artefact, sans runner externe). Décision et
frontière :
[ADR 0095](/cluster/docs/decisions/0095-build-applicatif-evenementiel-in-cluster/),
étapes 5-8 du
[plan build événementiel](/cluster/docs/plans/plan-build-evenementiel-gitops/).

| Fichier                                                                                                                | Rôle                                                                                                          |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| [`argo-workflows.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-workflows/argo-workflows.yaml) | Bundle officiel v4.0.6 (CRDs Workflow/CronWorkflow/WorkflowTemplate… + RBAC + Deployments), images par digest |

Namespace : `argo`. Images épinglées par **digest d'index multi-arch** (ADR
0006, banc arm64 / prod x86) : `workflow-controller` et `argocli` (argo-server).

## Rôle dans la chaîne événementielle

Argo Events (voir [`../argo-events/`](/cluster/platform/argo-events/))
transforme un **webhook Gitea** en `Sensor` → ce `Sensor` soumet un `Workflow` ;
**Argo Workflows** exécute ce `Workflow` **in-pod** (build/publication
d'artefact), puis Argo CD réconcilie l'applicatif publié. Les
`WorkflowTemplate`/`Sensor` concrets sont posés aux **étapes 6-7** (hors
périmètre de ce vendoring).

## Frontière Ansible / GitOps (anti-bootstrap-circulaire)

**Argo Workflows est de l'INFRA** : posé par **Ansible/kubectl**
(`kubectl apply --server-side`), **PAS réconcilié par Argo CD** — même règle que
Argo CD lui-même (ADR 0022) : un opérateur + ses CRDs dont dépend la chaîne de
déploiement va dans Ansible, pas en GitOps.

## Déploiement

```bash
# Pré-requis SANS Internet : mirrorer les 2 images (workflow-controller, argocli)
# dans le registry interne — ADR 0011 — sinon ImagePullBackOff. (TODO intégration.)
kubectl create namespace argo
# --server-side OBLIGATOIRE : les CRD Workflows dépassent la limite d'annotation
# de l'apply client-side.
kubectl apply --server-side -n argo -f platform/argo-workflows/argo-workflows.yaml
kubectl -n argo rollout status deploy/workflow-controller deploy/argo-server
```

## Décisions assumées

- **Argo Workflows ≠ self-managed par Argo CD** : c'est de l'infra (frontière
  0022/0095).
- **Images à mirrorer** (cluster sans Internet, 0011) — TODO d'intégration.
- **Épinglage par digest** (ADR 0006), tag conservé pour lisibilité.
- **`--server-side` obligatoire** (CRDs volumineuses).

## Builder BuildKit-in-pod (étape 6)

Le `WorkflowTemplate` `image-builder`
([`workflowtemplate-builder.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-workflows/workflowtemplate-builder.yaml))
est la **traduction in-pod du build node-side** (rôle `platform-build-images`) :
générique, paramétré
`{codeLocation, revision, atlasRepoURL, giteaWritebackURL}`, en **3 steps
séquentiels** — **build-push** (BuildKit rootless, contexte `dataops/` +
`-f <cl>-dagster/Dockerfile`, avec le **clone en initContainer** partageant
l'`emptyDir` du même pod) → **digest** (lecture `curl -I` du
`Docker-Content-Digest`, garde `^sha256:[0-9a-f]{64}$`) → **write-back** de
`apps/<cl>.yaml` par digest dans `cluster/apps` (Contents API, patron
`push_contents_file` du seed). Le nom d'image poussé est **`<cl>-dagster`** (le
nom que l'overlay kustomize d'atlas attend). Décision et frontière :
[ADR 0095 §1.b](/cluster/docs/decisions/0095-build-applicatif-evenementiel-in-cluster/).

> **Vue d'ensemble détaillée** (flux complet, chaque maillon, pièges prouvés au
> banc, exemple de bout en bout) :
> [Chaîne de build événementiel](/cluster/docs/architecture/chaine-build-evenementiel/).

Dépendances posées avec lui :

| Fichier                                                                                                                                              | Rôle                                                                            |
| ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| [`configmap-buildkitd-toml.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-workflows/configmap-buildkitd-toml.yaml)           | ConfigMap `buildkitd-config` (`registry:80` http/insecure) — **point dur 1**    |
| [`gitea-writeback-token.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-workflows/gitea-writeback-token.example.yaml) | Patron `*.example` du token Gitea scopé `cluster/apps` — **point dur 3**        |
| [`../network-policies/argo-workflows/`](/cluster/platform/network-policies/argo-workflows/)                                                          | `00-default-deny` + `allow-build-egress` (egress build ciblé) — **point dur 2** |

### Les 4 points durs

1. **`buildkitd.toml` insecure (registry HTTP).** Un `buildkitd` rootless en Pod
   n'hérite **PAS** du `hosts.toml` containerd du nœud → sans configuration
   explicite, le `push` vers `registry:80` (HTTP, ADR 0011) échoue en handshake
   TLS. La ConfigMap `buildkitd-config` déclare `registry:80` en `http = true` /
   `insecure = true`, montée dans le conteneur build-push à
   `/home/user/.config/buildkit/buildkitd.toml` (chemin rootless, uid 1000).
2. **Egress build ciblé — air-gap ASYMÉTRIQUE.** `allow-build-egress.yaml` ouvre
   le port **443** vers `0.0.0.0/0` (borne = port + ns) pour les dépendances de
   build révélées par le Dockerfile citation (`deb.debian.org`, PyPI,
   `extensions.duckdb.org`, `huggingface.co`), + DNS + registry:80 + Gitea. **Le
   SEUL ns `argo`** porte cet egress Internet : le **runtime `dagster` et Argo
   CD restent air-gappés** (ADR 0095 §0). Additif sur un `00-default-deny`
   fermé.
3. **Token Gitea scopé `cluster/apps`.** Le step write-back monte le Secret
   `gitea-writeback-token` (patron `*.example` versionné, secret réel généré au
   seed non versionné, ADR 0023) — token à scope `write:repository` **restreint
   au seul repo `cluster/apps`**, jamais le token admin. Surface d'élévation
   cantonnée.
4. **Worker-only.**
   `nodeSelector: {node-role.kubernetes.io/control-plane: DoesNotExist}` — le
   builder tourne sur un **worker, jamais le control-plane** (SPOF unique,
   invariant 5 ADR 0095).

### Écart banc (CP = builder)

Au **banc Lima mono-nœud**, le control-plane **EST** le seul nœud : le
`nodeSelector` `DoesNotExist` ne matcherait aucun nœud (pod `Pending`). Le
manifeste versionné garde la posture **prod** correcte (builder sur worker,
invariant 5) ; **au banc on RETIRE le `nodeSelector`** après avoir appliqué le
`WorkflowTemplate`.

Le dépôt n'a **aucune infra kustomize** (zéro `kustomization.yaml`/`overlays/` —
les écarts banc/prod passent par des `values.bench.yaml` Helm ou des manifestes
distincts). Pour un simple retrait de champ sur un CR, la voie **cohérente** est
un `kubectl patch` documenté (pas un overlay kustomize créé pour ce seul cas) :

```bash
# BANC UNIQUEMENT — mono-nœud : le CP est aussi le builder. À jouer APRÈS
# `kubectl apply` du WorkflowTemplate, AVANT de soumettre un Workflow.
kubectl patch -n argo workflowtemplate image-builder --type json \
  -p '[{"op":"remove","path":"/spec/nodeSelector"}]'
```

Idempotent de fait : un second `patch remove` sur un `nodeSelector` déjà absent
échoue (chemin introuvable) — soit on l'ignore, soit on ne le rejoue pas (le
banc pose le `WorkflowTemplate` une fois). **Ne PAS** jouer ce patch en prod (le
builder DOIT rester worker-only, SPOF unique).

### Mirror des images publiques (banc air-gappé)

Les **3 images publiques** du builder (`alpine/git` pour le clone,
`moby/buildkit` pour le build, `curlimages/curl` pour digest **et** write-back)
sont **épinglées par digest d'index multi-arch** (ADR 0006) **et tirées de
`registry:80`** dans le manifeste (tag conservé pour lisibilité). Au banc
air-gappé, un pod ne peut pas tirer d'Internet → elles doivent d'abord être
**mirrorées au registry interne** (ADR 0011). Le play
[`bootstrap/eventful-mirror.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/eventful-mirror.yaml)
le fait node-side (pull public par digest → tag `registry:80/<img>:<tag>` →
push), idempotent (skip si déjà présente). Les digests du play et du manifeste
sont **liés** : un bump change les deux.

```bash
# Pré-requis banc air-gappé : mirrorer les 3 images publiques du builder.
nestor ansible eventful-mirror.yaml   # inventaire dérivé de la stack active (ADR 0098)
```

> L'image `argocli` du **CronWorkflow** filet (`cronworkflow-reconcile.yaml`)
> vient du **même registre**, épinglée par le digest du bundle
> `argo-workflows.yaml` (v4.0.6) — elle se mirore **avec le bundle**
> (workflow-controller/argocli, cf. « Déploiement » ci-dessus), pas via
> `eventful-mirror.yaml`.

### TODO d'intégration restant

- **KSV-0014 / seccomp Unconfined** du step build-push (requis par BuildKit
  rootless) — à allowlister dans `.trivyignore.yaml` sur ce seul chemin à
  l'intégration.

### Dettes tracées (ADR 0095 §Coût)

- **Registry `replicas:1`** sur le chemin build (push) **et** deploy (pull), PVC
  RWO — SPOF amplifié (ADR 0011).
- **Build non bit-reproductible** : `apt` / base `python:*-slim` non lockés ; un
  rebuild du même SHA peut produire un digest différent (traçabilité commit →
  image OK, bit-repro NON — tension ADR 0052).
- **Digest single-arch** : build in-pod mono-arch = digest de manifest, pas
  d'index multi-arch (acceptable prod x86-only, ADR 0095 §2).
