# Plan — Étape 1.7 : orchestrateur Dagster (event log dans CloudNativePG)

## État

> **État : Achevé** (2026-06-13) · **Fonde :
> [ADR 0026](../decisions/0026-orchestration-dagster.md)** (Accepted) · **Issues
> : #129, #130, #137, #140, #141, #144** (toutes fermées/mergées)
>
> Date du plan : 2026-06-04. Socle décisionnel :
> [ADR 0026](../decisions/0026-orchestration-dagster.md) (orchestration
> Dagster) + [ADR 0024](../decisions/0024-postgres-manage-cloudnative-pg.md)
> (PostgreSQL managé, étape 1.6) +
> [ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)
> (matrice de versions) +
> [ADR 0023](../decisions/0023-plateforme-exemple-generique.md) (valeurs
> génériques). Issue de suivi : #129.

## Contexte

Suite du socle DataOps (après 1.5 monitoring et 1.6 CloudNativePG). On déploie
l'**orchestrateur Dagster « vide »** : webserver + daemon + run workers
(`K8sRunLauncher`), avec event/run/schedule storage **persisté dans la base
`dagster` de CloudNativePG** (jamais SQLite éphémère). Le **code métier**
(assets, IO managers) vit dans un dépôt applicatif séparé — ici on pose
l'**orchestrateur seul**.

> **Note (ADR [0092](../decisions/0092-exposition-hostport-l4.md),
> 2026-06-23).** Plan **achevé** : les mentions ci-dessous de l'exposition par
> **Gateway Cilium + TLS** (webserver Dagster) décrivent l'état au moment de la
> réalisation. L'exposition des UI a depuis basculé en **L4** (`NodePort`,
> `http://<IP-nœud>:<port>`, sans DNS ni TLS de bordure) : le `gateway.yaml` de
> l'addon est retiré au profit d'un Service `NodePort`. Conservé tel quel comme
> historique.

Méthode identique à 1.5/1.6 : addon `platform/dagster/` (helm template figé +
values), déployé par **`kubectl apply`** (patron addon,
[ADR 0022](../decisions/0022-argocd-gitops-applicatif.md) — pas Argo CD), validé
sur le **banc léger Lima** (K8s v1.34).

## Arbitrages (tranchés)

1. **Livraison vide, validation par exemple trivial jetable.** L'addon livré n'a
   aucune code-location (`dagster-user-deployments` désactivé). Pour la
   validation banc, on déploie temporairement un asset jouet pour prouver e2e
   qu'un run via `K8sRunLauncher` crée un Job et touche le run/event storage
   CNPG, puis on le retire.
2. **`kubectl apply`** (pas Argo CD).
3. **Webserver sans auth** (réseau interne de confiance, comme
   registry/dashboard,
   [ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md)) — exposé
   via Gateway Cilium + TLS interne. Auth en bordure = chantier ultérieur.
4. **Pas d'egress S3** (l'orchestrateur vide n'a pas d'IO manager → reporté).

## Versions / images (épinglées par digest d'index multi-arch, ADR 0006)

- **Chart `dagster/dagster` 1.13.7** (appVersion 1.13.7 ; verrou chart↔package
  1:1).
- **webserver + daemon** : `dagster/dagster-celery-k8s:1.13.7`. ⚠️ **Images
  officielles amd64 uniquement** (dagster-io/dagster#11841) → **image arm64
  construite en interne**
  ([`platform/dagster/image/Dockerfile`](../../platform/dagster/image/Dockerfile),
  1er build maison du dépôt) pour le banc arm64 ; topologie bare-metal x86 =
  image officielle. Les deux poussées dans le registry interne
  ([ADR 0011](../decisions/0011-registry-http-sans-auth.md)).
- **init wait-for-db** : `postgres` épinglé par digest d'index multi-arch.
- CNPG (existant) : base `dagster` owner `dagster`, Service
  `pg-rw.postgres.svc.cluster.local:5432`, Secret CNPG `pg-dagster`.

## Invariants non négociables

- **Images par digest d'index multi-arch** (ADR 0006), MediaType image.index +
  arm64 vérifiés. Épinglage sur le **manifeste figé** (le chart n'expose pas de
  champ digest — on édite le rendu, comme `loki.yaml`).
- **Event/run/schedule storage dans Postgres CNPG**, jamais SQLite.
- **Secret DÉRIVÉ** versionné `.example` (clé `postgresql-password`, valeur
  générique) ; le password réel vient du Secret CNPG `pg-dagster` via config
  locale non versionnée (ADR 0023). NE PAS pointer `global.postgresqlSecretName`
  sur le Secret CNPG brut (clés `username`/`password` ≠ `postgresql-password`).
- **default-deny** + allow-dns + allow-intra-namespace + egress Postgres 5432 +
  egress registry 80 + egress apiserver 6443.
- **Registry interne HTTP** sans imagePullSecret (ADR 0011) ; référencer le
  **Service:80**, jamais `:5000`.
- **Gateway Cilium** : hostname non vide (`dagster.cluster.lan`), HTTPS
  Terminate avec cluster-issuer interne et Secret `dagster-server-tls` ;
  HTTPRoute → port du Service.
- **2 listes kubeconform synchronisées** (package.json + lefthook.yml).
- Pas de flow YAML ; valeurs génériques (ADR 0023) ; « topologie » pas « prod ».

## Changements

### A. `platform/dagster/` (nouvel addon, patron helm template figé)

| Fichier                  | Rôle                                                     | Lint  |
| ------------------------ | -------------------------------------------------------- | ----- |
| `values.bench.yaml`      | source du rendu (external→CNPG, K8sRunLauncher, vide)    | linté |
| `dagster.yaml`           | helm template **figé** (digests injectés)                | exclu |
| `namespace.yaml`         | Namespace `dagster`                                      | linté |
| `pg-secret.example.yaml` | Secret dérivé `.example` (clé `postgresql-password`)     | linté |
| `gateway.yaml`           | Gateway + HTTPRoute Cilium (`dagster.cluster.lan`, TLS)  | linté |
| `image/Dockerfile`       | image Dagster **arm64** construite en interne            | —     |
| `README.md`              | patron addon (prérequis, déploiement, surcharge, valid.) | md    |

### B. `platform/network-policies/dagster/` (patron postgres/)

`00-default-deny`, `allow-dns`, `allow-intra-namespace`,
`allow-webserver-ingress` (80), `allow-postgres-egress` (→ ns postgres 5432),
`allow-registry-egress` (→ ns registry 80), `allow-apiserver-egress` (6443).
**Pas** d'allow-s3-egress (reporté — pas d'IO manager en 1.7).

### C. Exclusions linters (6 fichiers) pour `dagster.yaml`

`.prettierignore`, `.yamllint.yaml`, `.jscpd.json`, `package.json` et
`lefthook.yml` (listes kubeconform **synchronisées**), `.trivyignore.yaml` (RBAC
chart par chemin, avec justification).

### D. ADR 0026 + index + matrice 0006

Décision Dagster (K8sRunLauncher, storage CNPG, helm template figé, Gateway sans
auth, orchestrateur vide). Index `docs/decisions/README.md` + ligne matrice ADR
0006 (chart 1.13.7 + note amd64-only/build maison).

### E. `bootstrap/state.sh` — section « Orchestration (Dagster — ADR 0026) »

ns dagster ? deploy `dagster-dagster-webserver` Ready ? deploy `dagster-daemon`
Ready ? Skip propre si absent.

## Vérification

- **Banc Lima** (K8s v1.34, CNPG Healthy + base dagster) : webserver répond,
  daemon up, storage dans Postgres (tables Dagster présentes, pas de SQLite),
  exemple trivial jetable → un **Job K8s** créé + run dans l'event log, puis
  retiré.
- **CI reproduite** : `pnpm lint` + `pnpm docs:build` + markdownlint + trivy.

## Hors scope (suites)

- **Code métier** (assets, IO managers, egress S3) → dépôt applicatif.
- **Auth en bordure** du webserver (oauth2-proxy) → ultérieur.
- **1.8 Marquez** (#130, débloqué une fois Dagster posé — émetteur OpenLineage).

## Journal d'exécution

- **2026-06-04** — Réalignement sur `main` avancé pendant l'implémentation
  (release 2.20.0 + ADR 0025 sécurité de #137 + relais SMTP #141). ADR Dagster
  renuméroté **0025 → 0026** (collision de numéro). Détail :
  [audit 2026-06-04 réalignement Dagster](2026-06-04-audit-realignement-main-dagster.md).
- **2026-06-04** — Bug latent découvert : image registry interne épinglée par
  digest **mono-arch** (amd64) → `exec format error` sur banc arm64. Issue #140
  (audit de tous les digests épinglés).
- **2026-06-04** — Code livré et lint-clean, mais **validation banc Lima non
  faite** : la VM avait été détruite entre deux sessions, et un blocage
  `ImagePullBackOff` du registry interne (résolution `registry:80` + HTTP
  insecure) n'avait pas été levé. Validation e2e suivie en **#144** (recréer le
  banc, lever le blocage — cause racine candidate : #140). Le statut « Validé »
  de l'ADR a été corrigé en « validation en suivi » (honnêteté).

## Suivi (ADR 0057)

État : **Achevé** (cf. en-tête `## État`). Tous les paliers décrits ci-dessus
sont livrés et mergés ; les détails par palier vivent dans le corps du plan.

- **Issues rattachées** (toutes fermées/mergées) : #129, #130, #137, #140, #141,
  #144.
- **Runs de preuve** : consignés dans
  [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md).
