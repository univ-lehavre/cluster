# Marquez

Store de lineage **OpenLineage** (étape 1.8,
[ADR 0028](../../docs/decisions/0028-orchestration-openlineage-marquez.md)) :
API de collecte/agrégation des métadonnées + UI web de visualisation du lineage.
Le store persiste dans la base `marquez` de [CloudNativePG](../cloudnative-pg/)
(étape 1.6) — migrations **Flyway** au démarrage, d'où une base **dédiée** (pas
un schéma partagé).

Le lineage est **émis** par Dagster (sensor OpenLineage) et, en Phase 2+, par le
code `atlas`. Marquez ne fait qu'**ingérer et visualiser**. Géré par
`kubectl apply` (patron addon,
[ADR 0022](../../docs/decisions/0022-argocd-gitops-applicatif.md)).

## Fichiers

| Fichier                  | Rôle                                                  | Lint  |
| ------------------------ | ----------------------------------------------------- | ----- |
| `image/Dockerfile`       | image API Marquez **arm64** construite en interne     | —     |
| `image-web/Dockerfile`   | image UI web **arm64** construite en interne          | —     |
| `values.bench.yaml`      | source du rendu helm (store CNPG externe, web activé) | linté |
| `marquez.yaml`           | helm template **figé** (chart 0.51.1)                 | exclu |
| `namespace.yaml`         | Namespace `marquez`                                   | linté |
| `pg-secret.example.yaml` | patron Secret de connexion Postgres (`.example`)      | linté |
| `gateway.yaml`           | exposition de l'UI web (Gateway Cilium + TLS interne) | linté |

## Images arm64 construites en interne

Les images Marquez officielles (`docker.io/marquezproject/marquez` **et**
`marquez-web`) sont **amd64 uniquement** (vérifié Docker Hub, 0.51.1). Leurs
bases sont multi-arch (`eclipse-temurin:17` pour l'API Java, `node:18-alpine`
pour l'UI React) → les images **arm64** se reconstruisent depuis le source au
tag, sans modification. Selon la topologie :

- **Topologie bare-metal (x86)** : images **officielles** 0.51.1 (re-taguées
  `registry:80/marquez{,-web}:0.51.1`).
- **Banc léger Lima (arm64)** : images **maison** construites + poussées dans le
  registry interne
  ([ADR 0011](../../docs/decisions/0011-registry-http-sans-auth.md)).

Le manifeste référence `registry:80/marquez:0.51.1` et
`registry:80/marquez-web:0.51.1` ; on y pousse les images de l'arch voulue.

```bash
# Construire les images arm64 (banc) depuis le source Marquez au tag 0.51.1 :
git clone --depth 1 --branch 0.51.1 https://github.com/MarquezProject/marquez.git
docker buildx build --platform linux/arm64 \
  -t registry:80/marquez:0.51.1 --push marquez/            # API (contexte = racine source)
docker buildx build --platform linux/arm64 \
  -t registry:80/marquez-web:0.51.1 --push marquez/web/    # UI  (contexte = web/)
```

> Les Dockerfiles versionnés ici (`image/`, `image-web/`) sont la **copie
> fidèle** des Dockerfiles upstream du tag 0.51.1, pour tracer la provenance et
> l'invariant arm64 côté dépôt.

## Prérequis

1. **CloudNativePG** déployé, Cluster `pg` Healthy, base `marquez` créée (étape
   1.6 — cf. `cloudnative-pg/database.yaml`).
2. **Secret dérivé** `marquez-pg-auth` (clé `marquez-db-password`) — recopier le
   mot de passe du rôle `marquez` depuis le Secret CNPG `pg-marquez` (cf.
   `pg-secret.example.yaml`). Jamais le Secret CNPG brut (mauvaises clés).
3. **Registry interne** avec les images Marquez API + web de la bonne arch.
4. cert-manager (pour le TLS du Gateway).

> **Banc Lima.** Les pré-requis transverses (CRDs Gateway API, containerd vers
> le registry HTTP `registry:80`) sont posés par
> `test/lima/run-phases.sh platform-prereqs`. La validation e2e assemblée
> (chaîne `monitoring → CNPG → Dagster → Marquez` + lineage réel) est portée par
> `test/lima/run-phases.sh dataops-chain` — cf.
> [`test/lima/RESULTS.md`](../../test/lima/RESULTS.md) (#148).

## Déploiement — ordre

Le `marquez.yaml` (helm template figé) ne porte PAS `metadata.namespace` →
**toujours `-n marquez`** sinon les ressources atterrissent dans `default`.

```bash
kubectl apply -f platform/marquez/namespace.yaml
kubectl apply -n marquez -f platform/network-policies/marquez/
kubectl apply -n marquez -f platform/marquez/pg-secret.example.yaml  # ou le vrai Secret dérivé
kubectl apply -n marquez -f platform/marquez/marquez.yaml
kubectl -n marquez rollout status deploy/marquez
kubectl -n marquez rollout status deploy/marquez-web
kubectl apply -n marquez -f platform/marquez/gateway.yaml            # UI sur marquez.cluster.lan
```

## Points de surcharge par topologie (jamais de valeur réelle versionnée — ADR 0023)

| Paramètre                | Banc léger (Lima)                   | Topologie bare-metal                        |
| ------------------------ | ----------------------------------- | ------------------------------------------- |
| images Marquez API/web   | maison arm64 (registry interne)     | officielles amd64 (registry interne)        |
| Secret `marquez-pg-auth` | `pg-secret.example.yaml` (test)     | Secret dérivé non versionné (config locale) |
| hostname Gateway         | `marquez.cluster.lan` (placeholder) | hostname réel (admin réseau)                |

## Adaptations

- **Store Postgres CNPG** (base `marquez`), migrations Flyway au démarrage
  (`MIGRATE_ON_STARTUP=true`) — jamais le subchart bitnami/postgresql.
- **InitContainer wait-for-db** ajouté (le chart ne le rend que pour le subchart
  postgres) ; image `postgres` épinglée par digest d'index multi-arch (ADR
  0006).
- **Seule l'UI web est exposée** (Gateway) ; l'**API reste interne** — les
  émetteurs OpenLineage la joignent par `marquez.marquez.svc:5000`.
- **Sans auth** (réseau interne de confiance, ADR 0003) ; auth en bordure =
  évolution ultérieure.
- **Aucune PII dans le lineage** : noms d'assets/colonnes techniques uniquement,
  jamais de donnée nominative (ADR 0023).

## Validation

Sur le banc léger : API + web Ready, migration Flyway OK (tables dans la base
`marquez`), un événement OpenLineage émis par un **vrai run Dagster** (sensor)
visible dans l'UI Marquez. Cf. [`bootstrap/state.sh`](../../bootstrap/state.sh)
(section Marquez) et le harnais `dataops-chain` (#148).

## Régénérer le manifeste vendored

```bash
# Le chart vit dans le dépôt source (pas un repo Helm publié) :
git clone --depth 1 --branch 0.51.1 --filter=blob:none --sparse \
  https://github.com/MarquezProject/marquez.git && cd marquez && \
  git sparse-checkout set chart && helm dependency build chart
helm template marquez ./chart --version 0.51.1 --namespace marquez \
  -f platform/marquez/values.bench.yaml > platform/marquez/marquez.yaml
# puis réappliquer les retouches locales (init wait-for-db + digest postgres, port
# Service web 3000, retrait des Pods helm-test) — cf. en-tête de marquez.yaml.
```
