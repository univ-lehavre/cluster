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
