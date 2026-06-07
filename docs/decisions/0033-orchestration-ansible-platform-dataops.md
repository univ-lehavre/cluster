# 0033 — Orchestration Ansible des addons plateforme DataOps

## Contexte

Le bootstrap Kubernetes est en **Ansible** (`bootstrap/roles/`) ; la couche
**plateforme DataOps** (registry, CloudNativePG, Dagster, Marquez) était, elle,
montée en **shell impératif** (`test/lima/run-phases.sh` + `kubectl apply` +
`sed`/`awk` de surcharge banc). Le run e2e validé (#167/#148) a révélé un écart
net : le bootstrap nu n'a produit **qu'un drift cosmétique**, la couche
plateforme en a cascadé **neuf** (L12–L20,
[`test/lima/RESULTS.md`](../../test/lima/RESULTS.md)) — config containerd,
secrets de rôles, attentes Ready, surcharges par topologie, build d'images.
Chacun est précisément ce qu'Ansible gère nativement (`kubernetes.core`,
`lineinfile` + handler, `k8s_info` + `until`, templating Jinja). La couture
shell/kubectl est la source de friction : on redécouvre les mêmes problèmes à
chaque run.

## Décision

**Porter la couche plateforme DataOps en rôles Ansible idempotents**, orchestrés
par `bootstrap/dataops.yaml`, selon ces partis pris :

1. **Ansible = orchestrateur d'infra impératif des manifestes figés
   `platform/`.** Les manifestes vendored (`helm template` figés, ADR 0026/0028)
   restent la source ; les rôles les **appliquent** via `kubernetes.core.k8s`,
   gèrent l'**ordre inter-briques** (registry → CNPG → Dagster/Marquez), les
   **Secrets** locaux non versionnés, et la **convergence** (gates `k8s_info` +
   `until`).

2. **`kubernetes.core` adopté — rupture assumée avec le bootstrap historique.**
   Le bootstrap nu évite `kubernetes.core` (kubectl en shell, zéro dépendance
   collection). Ici on l'**adopte** (`k8s`, `k8s_info`) : les drifts L14–L20
   sont exactement l'apply server-side idempotent, l'attente Ready et les
   secrets dérivés que cette collection fournit — les réimplémenter en shell
   reproduirait la friction qu'on supprime. Ajouté à
   [`bootstrap/requirements.yml`](../../bootstrap/requirements.yml), version
   pinnée ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)) ; la CI
   installe la collection + ses libs Python.

3. **Surcharge des manifestes figés par patch ciblé, pas par `.j2`.** On
   **n'**emballe **pas** un rendu helm de ~700 lignes dans un template Jinja
   (divergence du rendu, perte des retouches locales documentées). Le banc
   surcharge ce qui doit l'être (image arm64 dé-épinglée) par un **patch
   strategic-merge** `kubernetes.core.k8s` post-apply, ciblé sur le seul champ
   concerné.

4. **Généricité ([ADR 0023](0023-plateforme-exemple-generique.md)) : le défaut
   versionné est la valeur PROD.** `defaults/main.yaml` de chaque rôle porte la
   valeur de production (storageClass `rook-ceph-block-replicated`, Barman
   activé, images par digest d'index) ; la **surcharge banc** (local-path,
   Barman désactivé, image arm64) vit dans un **`group_vars` d'inventaire non
   versionné** (+ `.example` versionné). Les secrets suivent le patron
   `*.example` versionné + valeur locale gitignorée ; le mot de passe d'un rôle
   CNPG et son **secret dérivé** applicatif partagent **une seule source de
   vérité** (leçon des drifts L16/L17).

5. **Frontière GitOps inchangée
   ([ADR 0022](0022-argocd-gitops-applicatif.md)).** Ansible orchestre
   l'**infra** (operators, CRDs, manifestes figés) ; l'orchestrateur **Dagster
   reste vide** (aucune code-location) et l'**émetteur OpenLineage jetable**
   (harnais e2e #148) **n'est pas porté** — ce n'est pas une brique plateforme.
   Le code métier reste applicatif (dépôt `atlas`, Argo CD).

6. **Pinning ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).**
   Versions figées dans les `defaults` des rôles (CNPG 1.29.1, Dagster chart
   1.13.7, Marquez 0.51.1, Gateway API 1.4.1) ; images par digest d'index
   multi-arch hors banc.

### Périmètre

Cinq rôles : `platform-registry`, `platform-build-images`, `platform-cnpg`,
`platform-dagster`, `platform-marquez` ; playbook `bootstrap/dataops.yaml`.
**Hors périmètre** : le monitoring (kube-prometheus-stack, Mailpit — best-effort
du shell) et l'émetteur jetable.

## Statut

Accepted. Livré incrémentalement (un rôle ≈ une PR), chaque rôle validé contre
le run e2e de référence avant le suivant.

## Conséquences

- **Gain** : monter la chaîne DataOps devient **une commande reproductible** ;
  les drifts deviennent des tâches idempotentes, plus des surprises à chaque
  run.
- **Prix à payer** : dépendance `kubernetes.core` (collection + libs Python
  `kubernetes` sur l'exécuteur) ajoutée à la CI ; deux familles de tâches (nœuds
  : containerd/build — cluster : apply/secrets) dans le même chantier.
- **Risque** : régression du run validé si les gates Ansible ne mappent pas
  fidèlement les prédicats shell (timeouts, `readyReplicas`, phase CNPG) —
  chaque rôle est donc revalidé e2e sur le banc avant le suivant.
- **Garde-fou** : tout secret/identité passe par un `*.example` générique
  (ADR 0023) ; un défaut de rôle contenant une valeur réelle serait un défaut.
