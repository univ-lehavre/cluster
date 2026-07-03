# La chaîne de build événementiel — de `git push` au pod, sans un geste

Cette page décrit **en entier** la chaîne qui, à partir d'un simple `git push`
sur le dépôt applicatif `atlas`, **construit une image, la pousse, et la déploie
sur le cluster** — sans aucune intervention manuelle. C'est l'implémentation de
l'[ADR 0095 §1.b](../decisions/0095-build-applicatif-evenementiel-in-cluster.md)
(« cible événementielle ») et de la frontière de déploiement
[ADR 0094](../decisions/0094-frontiere-deploiement-applicatif.md).

La chaîne est **longue et non triviale** : sept maillons, deux webhooks, trois
namespaces, un build container-in-container. Cette page prend le temps de tout
expliciter — le flux, chaque maillon, les pièges rencontrés (tous prouvés au
banc), et un exemple de bout en bout.

> **Objectif en une phrase.** _La détection d'une code-location poussée sur
> `atlas` entraîne l'installation automatisée de sa version buildée sur le
> cluster_ — « zéro geste ».
>
> **Valeurs génériques (ADR 0023).** `citation` / `mediawatch` sont des
> code-locations d'exemple ; `registry:80`, `gitea-http.gitea.svc…` sont les
> noms internes du banc/prod. Le mécanisme est **paramétré** (`codeLocation`,
> `revision`) — il ne connaît aucun nom en dur.

---

## 1. Vue d'ensemble — le flux complet

```text
   DÉVELOPPEUR
      │  git push atlas (branche main, touche dataops/<cl>-dagster/…)
      ▼
 ┌─────────┐   webhook #2         ┌──────────────────┐    EventBus     ┌──────────────────┐
 │  Gitea  │ ───────────────────▶ │  EventSource     │ ─── NATS ─────▶ │  Sensor          │
 │ (forge) │  POST /push          │  gitea-push      │  (publish)      │ code-location-   │
 └─────────┘  (ns argo-events)    │  (ns argo-events)│                 │ build            │
      ▲                           └──────────────────┘                 └────────┬─────────┘
      │ webhook #1                                                               │ dérive codeLocation
      │ (push cluster/apps)                                                      │ du CHEMIN, SOUMET
      │                                                                          ▼
 ┌─────────┐        reconcile      ┌──────────────────────────────────────────────────────┐
 │ Argo CD │ ◀──────────────────── │  WorkflowTemplate image-builder (ns argo)            │
 │ (ns     │   app-of-apps         │  ┌────────┐  ┌────────────┐  ┌────────┐  ┌──────────┐ │
 │ argocd) │   cluster-apps        │  │ clone  │─▶│ build-push │─▶│ digest │─▶│write-back│ │
 └────┬────┘   lit apps/<cl>.yaml  │  │(init   │  │ (BuildKit  │  │(curl   │  │(Contents │ │
      │        écrit par write-back│  │ Ctr)   │  │  rootless) │  │ HEAD)  │  │ API)     │ │
      │                            │  └────────┘  └─────┬──────┘  └────────┘  └────┬─────┘ │
      ▼                            └────────────────────┼─────────────────────────┼───────┘
 ┌─────────────┐                                        │ push image              │ écrit
 │ Application │                            ┌────────────▼──────┐      ┌───────────▼─────────┐
 │ <cl>-dagster│ ───── pod dagster ───────▶ │ registry interne  │      │ Gitea repo          │
 │ (projet     │       image PAR DIGEST     │ registry:80       │      │ cluster/apps        │
 │  atlas)     │                            └───────────────────┘      │ apps/<cl>.yaml      │
 └─────────────┘                                                       └─────────────────────┘
```

**Le point clé de séparation (ADR 0094).** _Build_ et _déploiement_ sont deux
chaînes distinctes reliées par **un seul fichier écrit** : `apps/<cl>.yaml` dans
le dépôt `cluster/apps`. Le builder ne déploie jamais rien ; il **écrit une
déclaration** que l'app-of-apps existant matérialise. C'est ce qui rend une
code-location _nouvelle_ déployable « zéro geste » : un fichier neuf →
l'app-of-apps (`prune: true`) crée l'Application, sans énumération.

**Les DEUX webhooks (à ne pas confondre) :**

| Webhook | Déclencheur             | Cible                                  | Rôle                                                     |
| ------- | ----------------------- | -------------------------------------- | -------------------------------------------------------- |
| **#1**  | push sur `cluster/apps` | `argocd-server`                        | déploiement (Argo CD réconcilie) — _préexistant_         |
| **#2**  | push sur `atlas/atlas`  | `EventSource gitea-push` (Argo Events) | **build** (déclenche cette chaîne) — _nouveau, ADR 0095_ |

---

## 2. Chaque maillon, en détail

### 2.0 — Le déclencheur : `git push` sur `atlas`

Un développeur pousse sur la branche `main` d'`atlas`, en touchant un fichier
sous `dataops/<cl>-dagster/` (le code d'une code-location : Dockerfile, `src/`,
`code-location.manifest.yaml`…). **Rien d'autre à faire.** Gitea émet alors,
vers l'EventSource, la livraison du webhook n°2.

> Le filtre du Sensor n'accepte que `refs/heads/main` **et** un chemin
> `dataops/…-dagster/…` : un push sur une autre branche, ou hors code-location,
> n'entraîne aucun build.

### 2.1 — EventSource `gitea-push` (ns `argo-events`)

Un endpoint webhook HTTP (`:12000/push`) qui **reçoit** le POST de Gitea et
**publie** l'événement sur l'EventBus. Il ne filtre rien lui-même.

Fichier :
[`platform/argo-events/eventsource-gitea.example.yaml`](../../platform/argo-events/eventsource-gitea.example.yaml).

> **Piège prouvé au banc — pas de `authSecret`.** Gitea signe ses webhooks avec
> `X-Gitea-Signature` (HMAC du corps). Argo Events `authSecret` compare, lui, un
> en-tête `Authorization` littéral — **incompatible**. On retire `authSecret` ;
> la sécurité vient de **l'isolement réseau** (seul Gitea peut atteindre
> `:12000`, cf. NetworkPolicy) et de l'air-gap (ADR 0003).

### 2.2 — EventBus NATS (ns `argo-events`)

Un bus NATS `replicas: 1` (SPOF assumé, ADR 0095 §SPOF) qui découple
l'EventSource du Sensor. Un événement perdu pile pendant un redémarrage de NATS
n'est jamais construit — d'où le **filet CronWorkflow** (§2.7).

### 2.3 — Sensor `code-location-build` (ns `argo-events`) — _le cœur de la découverte_

Le Sensor fait **une seule chose** : sur un push valide, il **dérive le
`codeLocation` du chemin modifié** et **soumet** le WorkflowTemplate
`image-builder`. Il ne déploie rien, n'énumère aucune liste.

Fichier :
[`platform/argo-events/sensor-code-location.example.yaml`](../../platform/argo-events/sensor-code-location.example.yaml).

La **dérivation** transforme `dataops/citation-dagster/README.md` → `citation` :

```yaml
dataTemplate: >-
  {{ (index (index .Input.body.commits 0).modified 0)
     | regexFind "dataops/[^/]+-dagster"
     | regexFind "[^/]+-dagster"
     | trimSuffix "-dagster" }}
```

Une code-location **neuve** `dataops/newthing-dagster/…` donnerait
`codeLocation=newthing` **sans aucune modification** du Sensor. _La découverte
EST la dérivation du chemin._

> **Piège prouvé au banc — `.Input` est le payload RACINE, pas la valeur.** En
> Argo Events v1.9.10, quand `dataTemplate` est présent, `.Input` **n'est pas**
> la valeur pointée par `dataKey` : c'est **la map du payload entier**. Un naïf
> `{{ .Input | regexFind … }}` échoue (« expected string; got map ») et Argo
> **retombe sur `dataKey` brut** → le `codeLocation` valait le chemin _entier_
> `dataops/citation-dagster/README.md`. Le correctif **navigue** explicitement
> dans `.Input` avec `index` (ci-dessus).

### 2.4 — WorkflowTemplate `image-builder` (ns `argo`) — _le build in-cluster_

Le remplacement in-pod du vieux build node-side. **Trois steps séquentiels** (le
clone est un **initContainer**, cf. piège ci-dessous), paramétrés par
`codeLocation` et `revision` :

Fichier :
[`platform/argo-workflows/workflowtemplate-builder.yaml`](../../platform/argo-workflows/workflowtemplate-builder.yaml).

1. **clone** (initContainer) — `git clone atlas@<revision>` dans `/work`
   (contexte de build). Image `alpine/git`.
2. **build-push** — `buildctl` (BuildKit **rootless**) construit `/work/dataops`
   avec `-f <cl>-dagster/Dockerfile`, pousse
   `registry:80/<cl>-dagster:<revision>`.
3. **digest** — lit le digest poussé via `curl -I` sur
   `/v2/<cl>-dagster/manifests/<revision>` (en-tête `Docker-Content-Digest`).
4. **write-back** — écrit `apps/<cl>.yaml` dans `cluster/apps` (Contents API
   Gitea), référençant l'image **par digest**.

Cinq pièges, tous prouvés au banc (2026-07-03) :

- **Clone en initContainer, pas un step Argo.** Chaque step Argo est un **pod
  distinct** ; un volume `emptyDir` n'est **pas** partagé entre pods. Un
  clone-step aurait écrit `/work` dans son pod, laissant build-push avec un
  `/work` vide (`lstat /work/dataops: no such file`). Le clone est donc un
  **initContainer du pod build-push** — l'`emptyDir` intra-pod est partagé.
- **AppArmor.** BuildKit rootless exige `seccomp` **et** `appArmor` `Unconfined`
  (il crée des user-namespaces imbriqués). On utilise le **champ natif**
  `securityContext.appArmorProfile: {type: Unconfined}` (k8s ≥ 1.30) —
  **jamais** l'annotation legacy
  `container.apparmor.security.beta.kubernetes.io/<name>` qui référence un nom
  de conteneur qu'Argo ne crée pas (« container not found », pod invalide).
- **Digest via `curl`, pas `crane`.** L'image `crane` est _distroless_ (pas de
  `sh`) → inutilisable en step `command: [sh, -c]`. On lit le même
  `Docker-Content-Digest` via `curl -I` (`curlimages/curl`, déjà présent pour le
  write-back) → une image publique de moins à mirrorer.
- **DNS `registry`.** Un pod ne résout pas le nom court `registry` (search
  domain du ns). On ajoute `dnsConfig.searches: [registry.svc.cluster.local]`
  **au niveau du Workflow** (Argo refuse `dnsConfig` par template). Le step
  digest, en image _alpine_ (musl, qui n'itère pas les search domains), utilise
  le **FQDN** `registry.registry.svc.cluster.local`.
- **Nom d'image `<cl>-dagster`.** Le builder pousse `registry:80/<cl>-dagster`
  (pas `<cl>`) — c'est le nom que l'overlay kustomize d'`atlas` attend
  (`images: - name: registry:80/citation-dagster`). Sinon la substitution
  kustomize n'a pas lieu et le déploiement reste figé sur l'image mutable `:dev`
  du seed.

### 2.5 — Le registre interne `registry:80`

Le build **pousse** l'image ici (HTTP, insecure — ADR 0011), et le déploiement
la **tire** ici. `buildkitd.toml` déclare `registry:80` en
`http = true / insecure = true`.

> **Piège prouvé au banc — egress du pool `argo`.** Le pod builder est le
> **premier** consommateur du registre _depuis un pod soumis aux
> NetworkPolicies_ (le runtime dagster, lui, _tire_ via le kubelet, hors NP).
> Deux ports manquaient dans `allow-build-egress`
> ([`allow-build-egress.yaml`](../../platform/network-policies/argo-workflows/allow-build-egress.yaml))
> :
>
> - vers le **registre** : ouvrir **5000** (le pod écoute 5000 ; le Service
>   mappe 80→5000 ; sous Cilium la NP filtre le port du pod) ;
> - vers **Internet** (apt) : ouvrir **80** en plus de 443 — `deb.debian.org`
>   répond en **HTTP:80** (paquets signés GPG, HTTP est le transport apt
>   standard). PyPI/HuggingFace restent en 443.

### 2.6 — write-back → `cluster/apps` → Argo CD

Le write-back écrit `apps/<cl>.yaml` : une **Application Argo CD** dans le
**projet `atlas`** (pas `cluster-apps`), référençant l'image **par digest**.

> **Piège prouvé au banc — projet applicatif.** `cluster-apps` est le périmètre
> **restreint** de l'app-of-apps (ADR 0094) : il n'autorise que des
> `Application` dans le ns `argocd`, sources `cluster/**`. Un **workload
> métier** (repo atlas, ns dagster, tout kind) doit vivre dans le projet
> **`atlas`** — sinon Argo CD refuse la sync (« namespace dagster / repo atlas
> not permitted in project cluster-apps »).

Le nom d'Application écrit est `<cl>-dagster` — **le même** que la déclaration
posée par le seed au bootstrap. Le premier build **remplace** donc la
déclaration bootstrap (image mutable `:dev`) par la version **par digest**, sous
le même nom, sans doublon.

L'app-of-apps `cluster-apps` (qui surveille `cluster/apps` path `apps/`)
matérialise ce fichier en Application ; le webhook #1 (ou le polling Argo CD ~3
min) déclenche la réconciliation → pod dagster mis à jour.

### 2.7 — Le filet event-loss : CronWorkflow `builder-reconcile`

L'EventBus est un SPOF (`replicas: 1`) et le build n'a pas de polling natif. Le
CronWorkflow `builder-reconcile` (toutes les 30 min) compare le HEAD atlas au
tag déployé et resoumet le build si écart — un **rattrapage** (latence = période
du Cron), **pas** une preuve d'idempotence (ADR 0052).

Fichier :
[`platform/argo-workflows/cronworkflow-reconcile.yaml`](../../platform/argo-workflows/cronworkflow-reconcile.yaml).

---

## 3. RBAC & montage

- **`builder-sa`** (ns `argo`) — le SA d'exécution des Workflows. Sans lui, le
  Workflow tourne avec le SA `default` (sans RBAC Argo) et son _executor_ échoue
  (« cannot create workflowtaskresults »). Porte aussi la soumission (pour le
  CronWorkflow filet). Fichier :
  [`platform/argo-workflows/builder-rbac.yaml`](../../platform/argo-workflows/builder-rbac.yaml).
- **`operate-workflow-sa`** (ns `argo-events`) — le SA du **Sensor** (soumet
  depuis argo-events). Fichier :
  [`platform/argo-events/operate-workflow-rbac.yaml`](../../platform/argo-events/operate-workflow-rbac.yaml).
- **Secret `gitea-writeback-token`** (ns `argo`) — un token API Gitea scopé
  `write:repository` sur `cluster/apps`, monté dans le step write-back. C'est un
  **vrai** token (créé au montage), pas un placeholder — un placeholder donne
  `401`.

Le tout est monté par le rôle Ansible **`platform-eventful`**
([`bootstrap/roles/platform-eventful/`](../../bootstrap/roles/platform-eventful/tasks/main.yaml)),
calqué sur `platform-argocd` : namespaces, bundles server-side, RBAC,
NetworkPolicies ordonnées, ConfigMap buildkitd, WorkflowTemplate, CronWorkflow,
EventBus/EventSource/Sensor, gates, rescue. Les 4 images publiques du builder
sont mirrorées node-side par
[`bootstrap/eventful-mirror.yaml`](../../bootstrap/eventful-mirror.yaml) (3
images depuis le retrait de `crane`).

> **Écart banc (mono-nœud).** Le WorkflowTemplate porte un
> `nodeSelector: control-plane: DoesNotExist` (posture prod : le builder tourne
> sur un worker, jamais le control-plane, SPOF). Au banc Lima **mono-nœud**, le
> control-plane EST le seul nœud → on **retire** ce nodeSelector par patch (le
> fichier versionné garde la posture prod).

---

## 4. Exemple de bout en bout (prouvé au banc, 2026-07-03)

```console
# 1. Le développeur pousse sur atlas (touche une code-location).
$ git push origin main            # dataops/citation-dagster/… modifié, SHA 50d28ee

# 2. (automatique) EventSource reçoit, Sensor dérive et soumet.
$ kubectl -n argo-events logs deploy/…code-location-build… | grep codeLocation
  codeLocation:  citation                       # ← dérivé du CHEMIN, pas d'une liste

# 3. (automatique) le Workflow build-push → digest → write-back.
$ kubectl -n argo get workflow -o wide
  image-builder-ptd8z   Succeeded                # clone ✅ build-push ✅ digest ✅ write-back ✅

# 4. (automatique) write-back a écrit apps/citation.yaml PAR DIGEST.
$ curl -s …/cluster/apps/raw/apps/citation.yaml | yq '.spec.source.kustomize.images'
  - registry:80/citation-dagster@sha256:49a6ca17…

# 5. (automatique) l'app-of-apps matérialise, Argo CD déploie.
$ kubectl -n argocd get application citation-dagster
  citation-dagster   Synced   Healthy
$ kubectl -n argocd get application citation-dagster \
     -o jsonpath='{.spec.source.targetRevision}'
  50d28ee…                                       # ← le SHA EXACT du push

# 6. (automatique) le pod tourne l'image PAR DIGEST.
$ kubectl -n dagster get deploy citation-dagster \
     -o jsonpath='{.spec.template.spec.containers[0].image}'
  registry:80/citation-dagster@sha256:49a6ca17…
```

**Zéro geste entre l'étape 1 et l'étape 6.** Le SHA du push se retrouve intact
dans le `targetRevision` déployé, et l'image est épinglée par digest.

---

## 5. Réserves & dettes tracées (honnêteté — ADR 0034/0052)

- **Build non bit-reproductible.** `apt`/`pip` non lockés au niveau de base ; un
  rebuild du même SHA peut produire un digest différent. Traçabilité
  commit→image OK, bit-repro NON (tension ADR 0052).
- **Digest single-arch.** Un build in-pod mono-arch produit un digest de
  _manifest_, pas d'_index_ multi-arch (ADR 0006). Acceptable prod x86-only.
- **Registre `replicas: 1`.** SPOF sur les deux chemins (push build, pull
  deploy), PVC RWO (ADR 0011).
- **EventBus `replicas: 1`.** SPOF ; mitigé par le CronWorkflow filet (§2.7),
  pas éliminé.
- **Egress Internet du pool `argo`.** Le builder est la **zone de confiance
  distincte** (air-gap asymétrique, ADR 0095 §0) : lui seul sort vers Internet
  (443 + 80), le runtime dagster et Argo CD restent air-gappés.

---

## 6. Pour aller plus loin

- [ADR 0095 — build applicatif événementiel in-cluster](../decisions/0095-build-applicatif-evenementiel-in-cluster.md)
- [ADR 0094 — frontière de déploiement atlas/cluster](../decisions/0094-frontiere-deploiement-applicatif.md)
- [ADR 0011 — registre HTTP interne](../decisions/0011-registry-http-sans-auth.md)
- [`platform/argo-workflows/README.md`](../../platform/argo-workflows/README.md)
  — détail du WorkflowTemplate
- [`platform/argo-events/README.md`](../../platform/argo-events/README.md) —
  détail EventSource/EventBus/Sensor
- [La chaîne DataOps de bout en bout](./chaine-dataops.md) — le socle applicatif
  que ce build alimente
