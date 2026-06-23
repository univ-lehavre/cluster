# Plan — Étape 1.8 : store de lineage OpenLineage (Marquez) + harnais E2E DataOps

## État

> **État : Achevé** (2026-06-13) · **Fonde :
> [ADR 0028](../decisions/0028-orchestration-openlineage-marquez.md)**
> (Accepted) · **Issues : #130, #148, #161, #164** (toutes fermées)
>
> Date du plan : 2026-06-05. Socle décisionnel :
> [ADR 0028](../decisions/0028-orchestration-openlineage-marquez.md) (Marquez) +
> [ADR 0024](../decisions/0024-postgres-manage-cloudnative-pg.md) (PostgreSQL
> managé, 1.6) + [ADR 0026](../decisions/0026-orchestration-dagster.md)
> (Dagster, 1.7, émetteur OpenLineage) +
> [ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)
> (matrice de versions) +
> [ADR 0023](../decisions/0023-plateforme-exemple-generique.md) (valeurs
> génériques). Issues de suivi : #130 (Marquez), #148 (épopée E2E), #161–#164
> (sous-tâches).

## Contexte

Dernière brique du socle DataOps (après 1.5 monitoring, 1.6 CNPG, 1.7 Dagster).
On déploie **Marquez** (API + UI web), store du **lineage OpenLineage**, avec
persistance dans une **base CNPG dédiée `marquez`** du cluster HA **unique
`pg`**. Le lineage est émis par Dagster (sensor) et, en Phase 2+, par le code
`atlas` ; Marquez ne fait qu'ingérer/visualiser. Méthode identique à 1.7 : addon
`platform/marquez/` (helm template figé + values), déployé par
**`kubectl apply`** ([ADR 0022](../decisions/0022-argocd-gitops-applicatif.md)),
validé sur le banc léger Lima (K8s v1.34, arm64).

> **Note (ADR [0092](../decisions/0092-exposition-hostport-l4.md),
> 2026-06-23).** Plan **achevé** : les mentions ci-dessous de l'**UI web exposée
> par Gateway + TLS** (Marquez web) décrivent l'état au moment de la
> réalisation. L'exposition des UI a depuis basculé en **L4** (`NodePort`,
> `http://<IP-nœud>:<port>`, sans DNS ni TLS de bordure) : le `gateway.yaml` de
> l'addon est retiré au profit d'un Service `NodePort` ; l'API Marquez reste
> interne (ClusterIP). Conservé tel quel comme historique.

Ce plan **clôt aussi l'épopée #148** (dette de validation systémique) en livrant
un **harnais E2E reproductible** qui déploie et vérifie la chaîne
`monitoring → CNPG → Dagster → Marquez` assemblée, et prouve la **vraie chaîne**
Dagster → sensor OpenLineage → ingestion Marquez (émetteur jetable réel).

## Arbitrages (tranchés)

1. **Base CNPG dédiée `marquez`** dans le cluster HA **unique `pg`** (pas un
   cluster par appli). Flyway migre au démarrage → base, pas schéma.
2. **Build maison arm64** pour les **deux** images (API + web), amd64-only en
   amont. Topologie bare-metal x86 = images officielles.
3. **UI web exposée** (Gateway) ; **API interne** (les émetteurs la joignent par
   le Service ClusterIP). Sans auth (réseau privé, ADR 0003).
4. **Lien Dagster→Marquez prouvé par émetteur jetable réel** (sensor
   `openlineage-dagster` + asset jouet), pas un POST synthétique.
5. **Tests unitaires = câblage maison** (fonctions shell pures, bats) ; pas de
   pytest sur l'upstream.

## Versions / images (épinglées par digest d'index multi-arch, ADR 0006)

| Composant       | Version                          | Note                                                    |
| --------------- | -------------------------------- | ------------------------------------------------------- |
| Marquez (chart) | **0.51.1** (API + web)           | helm template figé `platform/marquez/marquez.yaml`      |
| marquez (API)   | `registry:80/marquez:0.51.1`     | image maison arm64 (amd64-only amont)                   |
| marquez-web     | `registry:80/marquez-web:0.51.1` | image maison arm64 (amd64-only amont)                   |
| postgres (init) | `14.6@sha256:f565…` (index)      | wait-for-db, digest d'index (= init Dagster)            |
| CNPG            | déjà posé (1.6)                  | base `marquez` + rôle `marquez` ajoutés au cluster `pg` |

## Invariants non négociables

- Images épinglées par **digest d'index multi-arch** ; images maison référencées
  par tag `registry:80/...` (cohérent Dagster). `scripts/audit-image-digests.sh`
  reste vert.
- Store **Postgres CNPG** (base `marquez`), **jamais** le subchart bitnami.
- Secret de connexion = **Secret dérivé** `marquez-pg-auth` (clé
  `marquez-db-password`), jamais le Secret CNPG brut `pg-marquez`.
- NetworkPolicies **default-deny** + allow ciblés ; companion postgres-ingress.
- Registry interne **HTTP sans imagePullSecret** (ADR 0011).
- Exposition **Gateway + TLS** (UI web) ; API non exposée.
- **Aucune PII** dans le lineage (ADR 0023).
- 6 listes linters synchronisées pour le vendored `marquez.yaml`.

## Changements

### A. `platform/marquez/` (nouvel addon, patron helm template figé)

`namespace.yaml`, `values.bench.yaml` (linté), `marquez.yaml` (figé, exclu),
`gateway.yaml`, `pg-secret.example.yaml`, `image/Dockerfile` (API),
`image-web/Dockerfile` (web), `README.md`. Retouches locales du rendu : init
wait-for-db (digest postgres), port Service web 3000, retrait des Pods
helm-test.

### B. `platform/network-policies/marquez/` (patron dagster/)

`00-default-deny`, `allow-dns`, `allow-intra-namespace`,
`allow-postgres-egress`, `allow-web-ingress` (UI 3000),
`allow-openlineage-ingress` (API 5000 depuis `dagster`). Companion : ajout de
`marquez` dans `network-policies/postgres/allow-postgres-ingress.yaml`.

### C. CNPG — base et rôle `marquez`

`cloudnative-pg/database.yaml` (objet `Database` `marquez`) +
`cloudnative-pg/cluster.yaml` (rôle `marquez` dans `managed.roles`).

### D. Exclusions linters (6 fichiers) pour `marquez.yaml`

`package.json` + `lefthook.yml` (kubeconform, 2 exclusions sync : `marquez.yaml`
**et** `values.bench.yaml`), `.prettierignore`, `.yamllint.yaml`, `.jscpd.json`
(`marquez.yaml`), `.trivyignore.yaml` (KSV-0014/0118/0109 + DS-0002/0025/0029
par chemin, justifiés posture amont).

### E. ADR 0028 + index + matrice 0006

`docs/decisions/0028-…md`, ligne d'index, ligne + encadré matrice 0006.

### F. `bootstrap/state.sh` — section « Orchestration OpenLineage (Marquez) »

Skip si ns absent ; `mark ok/fail` sur deploy `marquez` (API) et `marquez-web`.

### G. Harnais E2E (clôt #148)

- `bench/lima/run-phases.sh` : phase `dataops-chain` (déploie monitoring → CNPG
  → Dagster → Marquez avec gates `retry`, déploie un émetteur jetable
  Dagster+sensor OpenLineage, lance un run réel, vérifie l'ingestion côté
  Marquez, teardown, récap + bloc RESULTS.md).
- `bench/scenarios/23-marquez-openlineage.sh` (calque du 22 : skip neutre,
  `STRICT_OL`).
- Tests unitaires : `bench/lima/dataops-assert.sh` (classificateurs purs) +
  `bench/unit/dataops-assert.bats`.
- `docs/architecture/chaine-dataops.md` : doc transverse (accès + actions
  vérifiables par brique).

## Vérification

Banc Lima :
`up → bootstrap → storage-simple → platform-prereqs → dataops-chain`, puis
`bench/scenarios/run-all.sh ONLY='23'`. Critère « done » (#148) : API/web Ready,
migration Flyway OK, **lineage d'un run Dagster réel visible dans Marquez**, run
consigné dans `bench/lima/RESULTS.md`. CI : `pnpm lint` (inclut bats) +
`pnpm docs:build` + markdownlint + trivy + `scripts/audit-image-digests.sh`.

## Hors scope (suites)

- **Émetteur OpenLineage de production** = sensor `openlineage-dagster` dans le
  code `atlas` (Phase 2+) ; ici seul un émetteur jetable de validation.
- **Auth en bordure** de l'UI (oauth2-proxy) — ultérieur.
- **ServiceMonitor Marquez** sur le monitoring — ultérieur.
- **Politique de rétention** du lineage à ajuster selon le volume réel.

## Journal d'exécution

- 2026-06-05 — Levée des inconnues amont : chart Marquez dans le dépôt source
  (`MarquezProject/marquez/chart`, pas un repo Helm) ; clé Secret =
  `marquez-db-password` (≠ Dagster) ; API + web **amd64-only** (Docker Hub) →
  deux builds maison arm64 ; init wait-for-db **absent** du rendu quand le
  subchart postgres est désactivé → ajouté à la main. Rendu validé kubeconform,
  trivy clean (invocation CI `scan-ref .`), audit digests vert. Validation banc
  en suivi.

## Suivi (ADR 0057)

État : **Achevé** (cf. en-tête `## État`). Tous les paliers décrits ci-dessus
sont livrés et mergés ; les détails par palier vivent dans le corps du plan.

**Issues rattachées** (toutes fermées) : #130, #148, #161, #164. **Runs de
preuve** : consignés dans
[`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md).
