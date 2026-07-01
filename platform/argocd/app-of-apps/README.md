# App-of-Apps — instanciation déclarative des Application applicatives

Implémente
l'[ADR 0094 §2](/cluster/docs/decisions/0094-frontiere-deploiement-applicatif/).
**Ajouter une app = pousser un fichier.** Plus besoin d'éditer un script bash
pour créer l'`Application` Argo CD d'une nouvelle app applicative.

## Le mécanisme en une phrase

cluster **pousse** une déclaration d'`Application` dans le repo Gitea de prod
dédié `cluster/apps` → l'`Application` **racine** (« app-of-apps ») réconcilie
ce repo et **crée** l'`Application` fille → celle-ci réconcilie le repo
**atlas** (le code applicatif).

```text
  cluster (socle)                 Gitea: cluster/apps            Argo CD
  ───────────────                 ────────────────────           ───────
  push apps/citation.yaml  ───►   apps/                  ◄──────  Application RACINE
  (repoURL atlas injecté)         ├── citation.yaml               (cluster-apps)
                                  └── mediawatch.yaml                  │ crée
                                                                       ▼
                                  Gitea: atlas (le code)  ◄──────  Application FILLE
                                  dataops/citation-dagster/        (citation-dagster,
                                  deploy/overlays/prod              projet atlas)
```

Deux repos Gitea **distincts**, deux rôles :

- **`cluster/apps`** (nouveau, prod) : ne contient QUE des déclarations
  d'`Application`. C'est l'état déclaratif des apps installées. Possédé par
  cluster.
- **`atlas`** (existant,
  [ADR 0044](/cluster/docs/decisions/0044-topologie-deploiement-banc-atlas/)) :
  le CODE applicatif (manifestes, overlays, `.sql`). Possédé par atlas.

## Fichiers de ce dossier (patrons `*.example`, ADR 0023)

| Fichier                                | Rôle                                                                             |
| -------------------------------------- | -------------------------------------------------------------------------------- |
| `appproject-cluster-apps.example.yaml` | `AppProject cluster-apps` — cadre la SEULE Application racine (privilège isolé). |
| `root-application.example.yaml`        | L'`Application` RACINE : surveille `cluster/apps`, `path: apps`, prune activé.   |
| `apps/citation.example.yaml`           | La déclaration d'`Application` citation que cluster POUSSE dans `cluster/apps`.  |

Aucune de ces valeurs (`repoURL`, `targetRevision`) n'est réelle : ce sont des
exemples génériques. Les URL réelles sont des **valeurs de déploiement injectées
au seed** (ci-dessous), jamais gravées en versionné (ADR 0023). C'est la
généralisation du pattern déjà livré dans
[`bench/lima/gitea-init.sh`](/cluster/bench/lima/gitea-init/) (`Application`
`atlas-workflows`, codée en dur pour un seul cas) vers un **chemin déclaratif**.

## Flux d'ajout d'une app

1. atlas fournit le code + un `code-location.manifest.yaml` (déclaration
   montante,
   [ADR 0094 §3](/cluster/docs/decisions/0094-frontiere-deploiement-applicatif/)).
2. cluster **lit et valide** ce manifeste — validateur
   [`scripts/check_code_location_manifest.py`](https://github.com/univ-lehavre/cluster/blob/main/scripts/check_code_location_manifest.py)
   (`pnpm lint:code-location`, bloquant en CI) : `contractVersion` connue,
   dépendances présentes (base, secret, storageClass d'OBC) vérifiées
   statiquement contre le contrat + les manifestes versionnés ; migration et
   dépendances inter-apps signalées (non vérifiables depuis le seul dépôt
   cluster). Capacité réelle confrontée au seed.
3. cluster **rend** la déclaration d'`Application` à partir du patron
   `apps/<app>.example.yaml` en injectant le `repoURL` atlas réel et le
   `targetRevision` (= champ `revision` du manifeste, le SHA git).
4. cluster **pousse** le fichier `apps/<app>.yaml` dans le repo Gitea
   `cluster/apps`.
5. la racine app-of-apps réconcilie → crée l'`Application` fille → celle-ci
   déploie le code atlas dans `dagster`.

Retirer une app = **supprimer son fichier** de `cluster/apps` : la racine
(`prune: true`) supprime l'`Application` fille, dont le finalizer cascade la
suppression des ressources.

## La frontière (ADR 0094 §1)

| atlas DÉCLARE + FOURNIT             | cluster VALIDE + INSTANCIE + ORCHESTRE            |
| ----------------------------------- | ------------------------------------------------- |
| manifestes de l'app, overlays       | lit le manifeste de déclaration, valide capacité  |
| `.sql` de migration (schéma métier) | applique la migration (Job hook PreSync)          |
| `code-location.manifest.yaml`       | provisionne base/secret dérivé/OBC                |
| le code de la code-location         | crée l'`Application` (pousse dans `cluster/apps`) |

## Seed en prod (généralisation de `gitea-init.sh`)

Le seed n'est **pas encore codé** (proposition). Il généralise le pattern de
[`bench/lima/gitea-init.sh`](/cluster/bench/lima/gitea-init/) (l. 108-200 : crée
org/repo Gitea via l'API, pousse des fichiers par `PUT/POST /contents`, crée
l'`Application` par `kubectl apply` avec `repoURL` injecté). Étapes et **points
d'injection** :

1. **Créer le repo Gitea `cluster/apps`** (org `cluster`, repo `apps`,
   `auto_init: true`, branche `main`) via `POST /orgs` +
   `POST /orgs/cluster/repos` — idempotent, comme l'org/repo atlas aujourd'hui.
   _Injection :_ `GITEA_APPS_ORG` / `GITEA_APPS_REPO` (défauts génériques
   `cluster` / `apps`).
2. **Rendre chaque déclaration fille** depuis `apps/<app>.example.yaml` en
   substituant :
   - `repoURL` → URL Gitea réelle du repo atlas
     (`${GITEA_SVC}/${ATLAS_ORG}/${ATLAS_REPO}.git`) ;
   - `targetRevision` → champ `revision` du `code-location.manifest.yaml` atlas.

   _Injection :_ ces deux valeurs sont des **valeurs de déploiement** (jamais
   versionnées). Réutiliser le helper `push_gitea_file` (Contents API, lecture
   du SHA pour MAJ idempotente, vérification de la réponse — un PUT raté laisse
   une version périmée, drift à ne pas reproduire).

3. **Pousser** les fichiers rendus dans `cluster/apps` sous `apps/<app>.yaml`
   (`PUT/POST /repos/cluster/apps/contents/apps/<app>.yaml`).
4. **Appliquer l'`AppProject cluster-apps`** depuis
   `appproject-cluster-apps.example.yaml` (`kubectl apply`, `sourceRepos`
   surchargé par l'URL Gitea réelle de l'instance — comme l'AppProject atlas).
5. **Appliquer l'`Application` racine** depuis `root-application.example.yaml`
   en injectant `repoURL` = `${GITEA_SVC}/cluster/apps.git` (valeur de
   déploiement, `kubectl apply -f -`, exactement comme `gitea-init.sh` l.
   177-198 pour `atlas-workflows`).
6. **(optionnel) Webhook** Gitea `cluster/apps` → `argocd-server/api/webhook`
   pour la réconciliation immédiate (réutiliser le secret partagé
   `argocd-webhook-shared`, `gitea-init.sh` l. 145-170).

> Le seed pose AUSSI les dépendances que le manifeste déclare (base, secret
> dérivé `pgvector-pg-auth`, OBC `atlas-datalake`) AVANT de pousser la
> déclaration — c'est le « cluster VALIDE/PROVISIONNE » de la frontière. Ces
> briques préexistent en partie (rôle `platform-dagster`, OBC côté cluster).

## Analyse de cohérence (questions de conception)

### AppProject : `cluster-apps` dédié vs réutiliser `atlas` — DÉDIÉ (tranché)

La racine app-of-apps est rattachée à un AppProject **`cluster-apps` distinct**,
pas à `atlas`. Raison **RBAC** : la racine est une `Application` dont la seule
mission est de **créer/supprimer d'autres `Application`** dans le namespace
`argocd`. C'est un privilège que les apps **métier** (projet `atlas`, qui
déploient dans `dagster`/`citation-*`) ne doivent **jamais** posséder — sinon
n'importe quelle code-location pourrait se forger une `Application` arbitraire.
On **isole** donc ce privilège :

- `cluster-apps` : `destinations` = `argocd` seul ; `namespaceResourceWhitelist`
  = `argoproj.io/Application` **uniquement** ; `clusterResourceWhitelist` =
  vide.
- `atlas` (inchangé) : `destinations` = `dagster`/`citation-*`/`marquez` ;
  whitelist `*/*` namespacée pour les workloads, mais **pas** `argocd`.

Moindre privilège, frontière nette — cohérent avec le rôle de garde-fou
multi-tenant de l'AppProject `atlas`.

### Validation du `code-location.manifest.yaml` — CODÉE (statique) + capacité au seed

cluster **LIT** le manifeste de déclaration montant atlas
([ADR 0094 §3](/cluster/docs/decisions/0094-frontiere-deploiement-applicatif/))
**avant** de rendre/pousser la déclaration d'`Application`. Le validateur
[`scripts/check_code_location_manifest.py`](https://github.com/univ-lehavre/cluster/blob/main/scripts/check_code_location_manifest.py)
(Python —
[ADR 0049](/cluster/docs/decisions/0049-doctrine-choix-outil-par-action/), «
logique non triviale » : parse YAML + jointures contrat↔manifeste ; testé par
[`tests/test_check_code_location_manifest.py`](https://github.com/univ-lehavre/cluster/blob/main/tests/test_check_code_location_manifest.py))
**échoue bruyamment** (BLOQUANT, `pnpm lint:code-location` en CI) si :

- `contractVersion` inconnue du contrat cluster (le `contract_version` publié
  par [`contract/*.example.yaml`](/cluster/contract/)) — c'est le remplacement
  de la copie figée (cause racine de l'audit) : déclaration + version validée,
  pas duplication silencieuse ;
- une dépendance **vérifiable statiquement** est absente : `database` (rôles
  CNPG / postgres_roles du contrat), `secrets` (postgres_roles / derived /
  s3_backup), `buckets[].storageClass` (StorageClass du dépôt) ;
- le schéma est cassé : champ requis manquant, `ready` non booléen, `revision`
  non-SHA (`main`/`HEAD` interdits), quantité `resources` malformée.

Sont **signalés sans bloquer** (WARNING) ce qui n'est PAS vérifiable depuis le
seul dépôt cluster : `dependsOn.migrations` (le `.sql` vit dans atlas, ADR 0094
§5), `dependsOn.codeLocations` (code d'une autre code-location, ordonnée au
déploiement par sync-waves), et `ready: false` (atlas n'atteste pas encore).

**Reste au seed (non statique) :** la **capacité réelle** — les `resources`
(cpu/mem, `disk` bloc RBD) et `buckets[].size` (objet RGW) confrontés à la marge
du cluster — se vérifie au moment du seed, pas depuis le code. Le SHA `revision`
est la **source unique** du « quelque chose a changé » : il alimente le
`targetRevision` injecté (point 2 du seed) et le tag d'image.

> **Tranché :** le validateur STATIQUE (schéma + version + existence des
> dépendances) tourne **en CI** (garde-fou de revue, comme `check_contract.py`)
> ; la validation de **capacité** reste au seed (elle a besoin de l'état réel du
> cluster). §3 de l'ADR (« valider AVANT d'instancier ») est ainsi honoré des
> deux côtés : la revue attrape les déclarations incohérentes, le seed attrape
> la saturation.

### Migration SQL (hook PreSync) — où se branche-t-elle ?

[ADR 0094 §5](/cluster/docs/decisions/0094-frontiere-deploiement-applicatif/) :
atlas **FOURNIT** le `.sql` (schéma métier) ; cluster l'**APPLIQUE** via un Job
Kubernetes en **hook `PreSync` Argo CD** — la migration tourne **avant** que les
workloads ne démarrent.

> **Question ouverte (à trancher) :** le Job de migration vit-il (a) dans
> l'**overlay atlas** (le `.sql` et le Job sont au même endroit que le code,
> atlas les versionne, l'`Application` les réconcilie « pour rien » côté
> cluster), ou (b) dans la **déclaration cluster** (`apps/<app>.yaml`
> porte/référence le Job, cluster maîtrise l'orchestration mais doit accéder au
> `.sql` fourni par atlas) ? Le partage de frontière (atlas fournit le `.sql`,
> cluster orchestre le Job) suggère un montage hybride : `.sql` versionné atlas
> (overlay), Job PreSync rendu par cluster pointant ce `.sql`. À instruire au
> banc.

## Validation locale (avant tout apply)

```bash
# Les YAML (Application/AppProject = CRD argoproj.io) — schémas absents en local,
# d'où -ignore-missing-schemas (comme le check kubeconform du dépôt).
kubeconform -strict -ignore-missing-schemas \
  -schema-location default \
  platform/argocd/app-of-apps/*.example.yaml \
  platform/argocd/app-of-apps/apps/*.example.yaml

# Markdown, format YAML : repris par lefthook/CI (markdownlint, prettier, yamllint).
```

## Voir aussi

- [ADR 0094](/cluster/docs/decisions/0094-frontiere-deploiement-applicatif/) —
  frontière de déploiement applicatif (cet ADR).
- [ADR 0022](/cluster/docs/decisions/0022-argocd-gitops-applicatif/) — Argo CD
  applicatif / frontière infra-app.
- [ADR 0044](/cluster/docs/decisions/0044-topologie-deploiement-banc-atlas/) —
  flux GitOps Gitea → Argo CD (le push de CONTENU, non inversé ici).
- [`platform/argocd/`](/cluster/platform/argocd/) — Argo CD + AppProject atlas.
- [`bench/lima/gitea-init.sh`](/cluster/bench/lima/gitea-init/) — le pattern de
  seed généralisé ici.
