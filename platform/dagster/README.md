# Dagster

Orchestrateur DataOps (étape 1.7,
[ADR 0026](/cluster/docs/decisions/0026-orchestration-dagster/)) : webserver,
daemon et run workers (`K8sRunLauncher` — 1 run = 1 Job K8s).
L'event/run/schedule storage est persisté dans la base `dagster` de
[CloudNativePG](/cluster/platform/cloudnative-pg/) (étape 1.6).

**Orchestrateur « vide »** : aucune code-location ici. Le code métier (assets,
IO managers DuckDB↔S3) vit dans le dépôt `atlas` (Phase 2+). Géré par
`kubectl apply` (patron addon,
[ADR 0022](/cluster/docs/decisions/0022-argocd-gitops-applicatif/)).

## Fichiers

| Fichier                  | Rôle                                                           | Lint  |
| ------------------------ | -------------------------------------------------------------- | ----- |
| `image/Dockerfile`       | image Dagster **arm64** construite en interne (cf. ci-dessous) | —     |
| `values.bench.yaml`      | source du rendu helm (storage CNPG, K8sRunLauncher, vide)      | linté |
| `dagster.yaml`           | helm template **figé** (chart 1.13.7)                          | exclu |
| `namespace.yaml`         | Namespace `dagster`                                            | linté |
| `pg-secret.example.yaml` | patron Secret de connexion Postgres (`.example`)               | linté |
| `gateway.yaml`           | exposition webserver (Gateway Cilium + TLS interne)            | linté |
| `reconciler.yaml`        | reconciler du workspace multi-code-location (ADR 0103)         | linté |

## Workspace multi-code-location (reconciler — ADR 0103)

Le webserver et le daemon chargent **toutes** les code-locations depuis **un
seul** `-w /workspace/workspace.yaml` (ConfigMap `dagster-workspace`). Chaque
code-location étant déployée par une Application Argo CD **distincte** (chaîne
de build événementiel, ADR 0095), elles ne peuvent pas co-éditer ce ConfigMap
partagé (la dernière synchronisée écrase les autres → code-location invisible).

**`reconciler.yaml`** (CronJob ns `dagster`) résout ça : chaque code-location
atlas pose un ConfigMap **disjoint** `dagster-workspace-<nom>` labellisé
`dagster.io/role: code-location` (son fragment `grpc_server`, host **court**) ;
le reconciler les DÉCOUVRE par label, les AGRÈGE dans le `load_from:` central,
et `rollout restart`e webserver+daemon **si** le workspace a changé (idempotent
: rejeu sans changement = `changed=0`, aucun redémarrage).

Le ConfigMap `dagster-workspace` n'est **plus** dans `dagster.yaml` (un
`load_from: []` réappliqué l'écraserait) : le rôle `platform-dagster` le
**seed** vide une fois (`when` absent), le reconciler en est ensuite
propriétaire. Ceci **supersede** le patch per-CL + le hook PostSync reload
d'ADR 0086. Image du reconciler : `dtzar/helm-kubectl` (kubectl + jq + sh),
mirrorée au registry interne par `platform-build-images` (`mirror_only`, ADR
0011/0006). Détail complet :
[ADR 0103](/cluster/docs/decisions/0103-workspace-dagster-multi-code-location-reconciler/).

## Image arm64 construite en interne

Les images Dagster officielles (`docker.io/dagster/dagster-celery-k8s`) sont
**amd64 uniquement** (cf. dagster-io/dagster#11841, #17167). Dagster étant du
pur Python, l'image **arm64** se reconstruit trivialement (`image/Dockerfile`,
fidèle à l'officiel). Selon la topologie :

- **Topologie bare-metal (x86)** : image **officielle**
  `dagster/dagster-celery-k8s:1.13.7`.
- **Banc léger Lima (arm64)** : image **maison** construite + poussée dans le
  registry interne
  ([ADR 0011](/cluster/docs/decisions/0011-registry-http-sans-auth/)).

Le manifeste référence `registry:80/dagster-celery-k8s:1.13.7` (registry
interne) ; on y pousse l'image de l'arch voulue.

```bash
# Construire l'image arm64 (banc) :
docker buildx build --platform linux/arm64 \
  -t registry:80/dagster-celery-k8s:1.13.7 --push platform/dagster/image/
```

## Prérequis

1. **CloudNativePG** déployé, Cluster `pg` Healthy, base `dagster` créée (étape
   1.6).
2. **Secret dérivé** `dagster-pg-auth` (clé `postgresql-password`) — recopier le
   mot de passe du rôle `dagster` depuis le Secret CNPG `pg-dagster` (cf.
   `pg-secret.example.yaml`). Jamais le Secret CNPG brut (mauvaises clés).
3. **Registry interne** avec l'image Dagster de la bonne arch (cf. ci-dessus).
4. cert-manager (pour le TLS du Gateway).

> **Banc Lima.** Les pré-requis transverses (CRDs Gateway API exigées par
> cert-manager, et containerd configuré pour tirer le registry HTTP
> `registry:80`) sont posés par `bench/lima/run-phases.sh platform-prereqs`.
> Validé e2e sur arm64 (run `K8sRunLauncher` → Job K8s, storage dans Postgres) —
> cf. [`bench/lima/RESULTS.md`](/cluster/bench/lima/RESULTS/) (#144).

## Déploiement — ordre

Le `dagster.yaml` (helm template figé) ne porte PAS `metadata.namespace`
(`--namespace` n'est qu'un contexte helm, pas inscrit dans le rendu) →
**toujours `-n dagster`** sinon les ressources atterrissent dans `default`.

```bash
kubectl apply -f platform/dagster/namespace.yaml
kubectl apply -n dagster -f platform/network-policies/dagster/
kubectl apply -n dagster -f platform/dagster/pg-secret.example.yaml  # ou le vrai Secret dérivé
kubectl apply -n dagster -f platform/dagster/dagster.yaml
kubectl -n dagster rollout status deploy/dagster-dagster-webserver
kubectl -n dagster rollout status deploy/dagster-daemon
kubectl apply -n dagster -f platform/dagster/gateway.yaml            # UI sur dagster.cluster.lan
```

## Points de surcharge par topologie (jamais de valeur réelle versionnée — ADR 0023)

| Paramètre                | Banc léger (Lima)                   | Topologie bare-metal                        |
| ------------------------ | ----------------------------------- | ------------------------------------------- |
| image Dagster            | maison arm64 (registry interne)     | officielle amd64 (registry interne)         |
| Secret `dagster-pg-auth` | `pg-secret.example.yaml` (test)     | Secret dérivé non versionné (config locale) |
| hostname Gateway         | `dagster.cluster.lan` (placeholder) | hostname réel (admin réseau)                |

## Adaptations

- **Storage Postgres CNPG** (event/run/schedule), jamais SQLite éphémère.
- **K8sRunLauncher** : chaque run = un Job K8s dans le namespace `dagster`.
- **Sans auth** sur le webserver (réseau interne de confiance, ADR 0003) ; auth
  en bordure = évolution ultérieure.
- Image `postgres` (init wait-for-db) épinglée par digest d'index multi-arch
  (ADR 0006).
- Composants Celery/Flower/Redis désactivés (K8sRunLauncher suffit).

## Validation

Sur le banc léger : webserver + daemon Ready, storage dans Postgres (pas
SQLite), un run de test via `K8sRunLauncher` crée un Job et apparaît dans
l'event log Postgres. Cf.
[`bootstrap/state.sh`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/state.sh)
(section Dagster).

## Régénérer le manifeste vendored

```bash
helm repo add dagster https://dagster-io.github.io/helm
helm template dagster dagster/dagster --version 1.13.7 --namespace dagster \
  -f platform/dagster/values.bench.yaml > platform/dagster/dagster.yaml
# puis réinjecter le digest d'index de postgres (cf. ADR 0006).
```
