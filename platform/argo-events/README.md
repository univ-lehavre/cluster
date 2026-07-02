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

> **EventBus NATS** : le CR `EventBus` natif (étape 7) tirera `nats:2.10.29` +
> `natsio/nats-server-config-reloader:0.14.0` (versions référencées dans le
> ConfigMap `argo-events-controller-config`). Ces images seront **à épingler par
> digest quand le CR `EventBus` sera écrit** — hors périmètre de ce vendoring.

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

## Décisions assumées

- **Argo Events ≠ self-managed par Argo CD** : c'est de l'infra (frontière
  0022/0095).
- **Images à mirrorer** (cluster sans Internet, 0011) — TODO d'intégration.
- **Épinglage par digest** (ADR 0006), tag conservé pour lisibilité.
- **Images NATS de l'EventBus** épinglées plus tard (étape 7), avec le CR
  `EventBus`.
