# Plan — Portail d'accès aux UI de la plateforme

## État

> **État : Actif** (2026-06-22) · **Fonde :**
> [ADR 0091](../decisions/0091-portail-acces-ui.md) (Accepted).

Promu `Brouillon → Actif` (et ADR 0091 `Proposed → Accepted`) au démarrage de
l'étape 1 — logique pure de croisement contrat ↔ état (ADR 0057).

## ADR fondateurs

- [0091](../decisions/0091-portail-acces-ui.md) — la décision (portail
  dynamique, liens nouvel onglet, commandes secrets, RBAC sans secrets, expo
  hostNetwork).
- [0043](../decisions/0043-contrat-interface-cluster-atlas.md) — le contrat
  (source) ; [0048](../decisions/0048-acces-local-developpeur.md) — `access.sh`
  (précédent à réutiliser, pas dupliquer).
- [0014](../decisions/0014-durcissement-kubeadm-init.md) /
  [0071](../decisions/0071-exposition-gateway-hostnetwork.md) /
  [0023](../decisions/0023-plateforme-exemple-generique.md) — durcissement,
  exposition, valeurs génériques.

## Invariants

- **Source = le contrat** (`contract/endpoints.example.yaml`), croisé avec l'API
  k8s live. Aucune liste d'UI codée en dur (ADR 0023/0043).
- **Le pod ne lit jamais un Secret** : RBAC sans verb `secrets` ; il affiche la
  commande `kubectl`, l'opérateur l'exécute avec ses droits.
- **Logique PURE testée sans cluster** (croisement contrat ↔ état), comme
  `nestor`/`check_contract.py` (ADR 0017) ; l'I/O (client k8s, HTTP) en bordure.
- **Banc d'abord** : prouvé sur Lima avant la prod (ADR 0034/0053).

## Étapes

### 1. Logique pure : croisement contrat ↔ état observé

- **CRÉER** `nestor/portal.py` (ou `scripts/portal_view.py`) :
  `build_view(contract, observed) -> list[Entry]` — pur. `contract` = endpoints
  chargés (réutiliser le loader de `scripts/check_contract.py`) ; `observed` =
  dict injecté (services présents, endpoints prêts, hostnames Gateway/HTTPRoute,
  état Applications). Sortie : entrées groupées par `layer`, chacune avec
  `verdict ∈ {MATCH, MISSING, DRIFT, EXTRA}`, `ui_url`, et `secret_cmd` (string
  de commande dérivée de `auth` + `namespaces-secrets`, JAMAIS la valeur).
- **CRÉER** `tests/test_portal.py` : verdicts (contrat∩live cohérent → MATCH ;
  contrat sans live → MISSING ; hostname divergent → DRIFT ; live hors contrat →
  EXTRA), génération des `secret_cmd` par type d'`auth`, groupage par layer.
- **Preuve SANS cluster** : `pnpm test:python` + `ruff`. Aucune brique déployée.

### 2. Serveur HTTP + image maison

- **CRÉER** `platform/portal/app/` : serveur HTTP Python in-cluster (client
  `kubernetes` natif, déjà dépendance) qui lit l'API (services, endpointslices,
  gateways, httproutes, applications), appelle `build_view`, rend la page
  (sidebar par layer, liens `target="_blank"`, blocs `secret_cmd` copiables).
  `Dockerfile` épinglé (modèle `platform/dagster/image-openlineage/`).
- **ÉDITER** `platform-build-images` defaults : ajouter l'image `portal`
  (`build_all_arch: true` — image maison, pas d'officielle à retaguer).
- **Preuve SANS cluster** : build local de l'image (arm64) ; un test de rendu
  (HTML contient les layers/liens/commandes attendus, sur un `observed` stubé).

### 3. Déploiement durci : Deployment + SA + RBAC + NetworkPolicy

- **CRÉER** `platform/portal/portal.yaml` : Namespace, ServiceAccount `portal`,
  `ClusterRole` + `ClusterRoleBinding` (get/list `services`, `endpointslices`,
  `gateways`, `httproutes`, `applications` — **aucune** règle `secrets`),
  Deployment durci (runAsNonRoot, seccomp, FS RO, no caps — ADR 0014), Service.
- **CRÉER** `platform/network-policies/portal/allow-apiserver-egress.yaml`
  (egress apiserver seulement, modèle dagster).
- **Preuve banc** : déployer sur Lima ;
  `kubectl auth can-i get secrets --as=system:serviceaccount:portal:portal` →
  **no** (RBAC prouvé) ; pod Running, durci (kube-bench/PSA ok).

### 4. Exposition Gateway hostNetwork

- **CRÉER** `platform/portal/gateway.yaml` : Gateway + HTTPRoute Cilium
  hostNetwork (hostPort 443, hostname `portail.cluster.lan`, TLS cert-manager) —
  modèle `platform/mailpit/gateway.yaml`.
- **Preuve banc** : `https://portail.cluster.lan` joignable (hostPort), liste
  les UI réelles du banc, verdicts cohérents (Grafana/Argo CD/Gitea/Dagster…),
  les `secret_cmd` affichées correspondent aux vrais Secrets, **aucune valeur**
  exposée.

### 5. Intégration au contrat et à l'accès

- **ÉDITER** `contract/endpoints.example.yaml` : ajouter l'entrée `portal-ui`
  (layer `socle`, `ui_hostname: portail.cluster.lan`, `auth: none`) — le portail
  se liste lui-même (dogfooding du contrat).
- **ÉDITER** `bench/lima/access.sh` / `docs/guide-dev-data.md` : pointer le
  portail comme vue d'ensemble (et acter le remplacement des forwards SSH par
  hostPort).
- **Preuve** : `check_contract.py` reste vert (nouvelle entrée cohérente) ;
  docs:build OK.

### 6. Preuve e2e + bascule prod

- **Scénario** `bench/scenarios/NN-portail.sh` : monte le portail au banc, sonde
  `https://portail.cluster.lan` (HTTP 200 + présence des UI + commandes
  secrets), vérifie via `auth can-i` qu'il ne peut pas lire un Secret.
- **Prod** : déployé par Argo CD (GitOps) ou Ansible selon la frontière retenue
  ; preuve = portail dirqual joignable, reflète les 10 couches réelles. (La
  mutation prod reste pilotée par l'opérateur, cf. cap nestor-prod.)

## Suivi

- [x] Étape 1 — logique pure + tests (`nestor/portal.py`,
      `tests/test_portal.py`)
- [x] Étape 2 — serveur + image (`nestor/portal_server.py`, `render_html` ;
      `platform/portal/image/Dockerfile`)
- [x] Étape 3 — Deployment + RBAC + NetworkPolicy
      (`platform/portal/portal.yaml`, `platform/network-policies/portal/` ;
      ClusterRole **sans** secrets)
- [x] Étape 4 — Gateway hostNetwork (`platform/portal/gateway.yaml`,
      `portail.cluster.lan`)
- [x] Étape 5 — intégration contrat (`portal-ui`) + README brique
- [ ] Étape 6 — preuve e2e au banc + bascule prod (banc à monter : build image,
      `kubectl apply`, sonder `portail.cluster.lan`, `auth can-i get secrets` →
      no)
