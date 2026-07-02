# Argo Events — passerelle événementielle (webhook → Sensor → Workflow)

Transforme des **événements externes** en actions dans le cluster : dans la
chaîne événementielle (ADR 0095 §1.b), c'est la **passerelle** qui reçoit le
**webhook Gitea** (via un `EventSource`), le route par un `EventBus` NATS, et le
matérialise en `Sensor` qui **déclenche un `Workflow`** Argo Workflows. Décision
et frontière :
[ADR 0095](/cluster/docs/decisions/0095-build-applicatif-evenementiel-in-cluster/),
étapes 5-8 du
[plan build événementiel](/cluster/docs/plans/plan-build-evenementiel-gitops/).

| Fichier                                                                                                       | Rôle                                                                                             |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [`argo-events.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-events/argo-events.yaml) | Bundle officiel v1.9.10 (CRDs EventBus/EventSource/Sensor + RBAC + controller), image par digest |

Namespace : `argo-events`. Image `argo-events` épinglée par **digest d'index
multi-arch** (ADR 0006, banc arm64 / prod x86), aux deux endroits (container du
controller + env `ARGO_EVENTS_IMAGE` propagé aux pods eventsource/sensor).

## Rôle dans la chaîne événementielle

**Webhook Gitea** → `EventSource` → `EventBus` (NATS) → `Sensor` → soumission
d'un `Workflow` à **Argo Workflows**
([`../argo-workflows/`](/cluster/platform/argo-workflows/)) qui **build
in-pod**, puis Argo CD réconcilie l'applicatif publié. Les CR concrets
(`EventBus`, `EventSource`, `Sensor`, `WorkflowTemplate`) sont posés aux
**étapes 6-7** (hors périmètre de ce vendoring).

> **EventBus NATS** : le CR `EventBus` natif (étape 7,
> [`eventbus-nats.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-events/eventbus-nats.yaml))
> tire `nats:2.10.29` + `natsio/nats-server-config-reloader:0.14.0` +
> `natsio/prometheus-nats-exporter:0.14.0` (versions référencées dans le
> ConfigMap `argo-events-controller-config`), **épinglées par digest d'index
> multi-arch** (cf. « Chaîne de découverte » ci-dessous).

## Frontière Ansible / GitOps (anti-bootstrap-circulaire)

**Argo Events est de l'INFRA** : posé par **Ansible/kubectl**
(`kubectl apply --server-side`), **PAS réconcilié par Argo CD** — même règle que
Argo CD lui-même (ADR 0022) : l'opérateur + ses CRDs dont dépend la chaîne de
déploiement va dans Ansible, pas en GitOps.

## Déploiement

```bash
# Pré-requis SANS Internet : mirrorer l'image argo-events (et, à l'étape 7, les
# images NATS) dans le registry interne — ADR 0011 — sinon ImagePullBackOff.
kubectl create namespace argo-events
kubectl apply --server-side -n argo-events -f platform/argo-events/argo-events.yaml
kubectl -n argo-events rollout status deploy/controller-manager
```

## Chaîne de découverte (étape 7)

Les CR concrets de la chaîne événementielle (posés par
`kubectl apply --server-side`, comme le bundle) transforment un **`git push`
atlas** en **build** puis, via le write-back du builder et l'App-of-Apps
existante, en **déploiement** — **zéro geste** (ADR 0095 §1.b ; plan build
événementiel §4 « Mécanisme de DÉCOUVERTE », voie C).

| Fichier                                                                                                                                         | CR            | Rôle dans la chaîne                                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| [`eventbus-nats.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-events/eventbus-nats.yaml)                               | `EventBus`    | Bus NATS natif `default`, `replicas: 1` (**SPOF assumé, TRACÉ**). 3 images NATS épinglées par digest.                                   |
| [`eventsource-gitea.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-events/eventsource-gitea.example.yaml)       | `EventSource` | **Webhook #2 (build)** : endpoint `/push` (port 12000), secret HMAC injecté au seed (patron `*.example`). DISTINCT du #1 (déploiement). |
| [`sensor-code-location.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-events/sensor-code-location.example.yaml) | `Sensor`      | **CŒUR de la découverte** : filtre branche + chemin, DÉRIVE `codeLocation` du chemin, SOUMET le WorkflowTemplate `image-builder`.       |

**Flux** : `git push atlas` → **EventSource** (webhook #2) → **EventBus** NATS →
**Sensor** (découverte) → **soumet `image-builder`** (Argo Workflows, ns `argo`)
→ build+push+write-back `apps/<cl>.yaml` par digest dans `cluster/apps` → **Argo
CD** (webhook #1, déjà câblé) réconcilie la racine App-of-Apps → pod gRPC.

**Découverte = `codeLocation` DÉRIVÉ du chemin, jamais énuméré.** Le Sensor
filtre le push sur (a) `ref == refs/heads/main` ET (b) un chemin modifié sous
`dataops/<x>-dagster/` (regex, pas de liste), puis extrait `codeLocation` du
chemin (`dataops/<name>-dagster/…` → `<name>`) et `revision` de `body.after`
(SHA, signal canonique ADR 0094 §3). Une code-location **NOUVELLE**
`dataops/newthing-dagster/…` donne `codeLocation=newthing` →
`apps/newthing.yaml` → Application `newthing`, **sans énumération ni geste**.
Garde-fou amont :
[`check_code_location_manifest.py`](/cluster/scripts/check_code_location_manifest.py)
échoue bruyamment sur un manifeste incohérent.

**Filet event-loss** :
[`cronworkflow-reconcile.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-workflows/cronworkflow-reconcile.yaml)
(ns `argo`) compare périodiquement le HEAD atlas au tag déployé et resoumet le
builder si un event NATS a été perdu (`replicas: 1`). **Honnêteté** : filet de
rattrapage à latence = période du Cron, **PAS** le rejeu `changed=0` d'Ansible
(ADR 0052).

**Webhook #2 au seed** : le handler `webhook_build()`
([`scripts/topology.py`](/cluster/scripts/topology.py)) pose ce hook Gitea sur
le repo **atlas/atlas** vers l'endpoint de l'EventSource
(`gitea-push-eventsource-svc.argo-events.svc.cluster.local:12000/push`), avec le
secret HMAC partagé `gitea-webhook-build-hmac`. Câblé mais pas encore dans la
séquence de seed (à brancher quand le socle événementiel est monté — cf.
`_SEED_BANC_TODO`).

Détail :
[ADR 0095 §1.b](/cluster/docs/decisions/0095-build-applicatif-evenementiel-in-cluster/),
[plan build événementiel §4](/cluster/docs/plans/plan-build-evenementiel-gitops/).

## Décisions assumées

- **Argo Events ≠ self-managed par Argo CD** : c'est de l'infra (frontière
  0022/0095).
- **Images à mirrorer** (cluster sans Internet, 0011) — TODO d'intégration.
- **Épinglage par digest** (ADR 0006), tag conservé pour lisibilité.
- **Images NATS de l'EventBus** épinglées (étape 7) dans
  [`eventbus-nats.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argo-events/eventbus-nats.yaml)
  : `nats:2.10.29` + `nats-server-config-reloader:0.14.0` +
  `prometheus-nats-exporter:0.14.0`, par digest d'index multi-arch.
