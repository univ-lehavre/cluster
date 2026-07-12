# 0111 — Déplacement de frontière : atlas instancie l'`Application` Argo CD de ses code-locations

## Statut

Accepted (2026-07-12). **Amende
[ADR 0094](0094-frontiere-deploiement-applicatif.md)** sur un point précis :
_qui instancie l'`Application` Argo CD_ d'une code-location. 0094 posait «
cluster VALIDE + **INSTANCIE** + ORCHESTRE » ; cet ADR déplace
l'**instanciation** de l'`Application` du côté **atlas**. Le reste de 0094
(cluster valide le manifeste montant, provisionne les dépendances d'infra,
applique la migration, fournit le contenant) est **conservé**.

Touche par ricochet : [ADR 0023](0023-plateforme-exemple-generique.md)
(l'argument « valeurs atlas gravées côté cluster » qui écartait l'`Application`
portée par atlas — il tombe), [ADR 0086](0086-code-location-jouet-du-socle.md)
(« le socle instancie via GitOps » — vrai pour le **jouet** seulement
désormais), [ADR 0095](0095-build-applicatif-evenementiel-in-cluster.md)
(write-back digest dans `cluster/apps` — caduc),
[ADR 0103](0103-workspace-dagster-multi-code-location-reconciler.md) (préambule
« Application créée côté cluster » — le **reconciler reste plateforme**, seul le
préambule s'ajuste). Découle de
[ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md) (« nestor
pilote la plateforme, pas le code atlas ») et de
[ADR 0110](0110-preimage-de-build-et-build-in-pod.md) (le build de l'image de
code est déjà sorti du cluster). Côté atlas, amende
[ADR 0075](https://github.com/univ-lehavre/atlas/blob/main/docs/src/content/docs/decisions/0075-deploiement-prod-par-digest-injecte-cluster.md)
(distinguer « atlas ne build pas l'image de prod » — inchangé — de « atlas crée
désormais l'`Application` » — nouveau).

## Contexte

L'[ADR 0094](0094-frontiere-deploiement-applicatif.md) a tranché la frontière de
déploiement applicatif ainsi : **atlas DÉCLARE + FOURNIT** (les manifestes, le
`code-location.manifest.yaml` montant, le code), **cluster VALIDE + INSTANCIE +
ORCHESTRE** (lit la déclaration, provisionne l'infra, **crée l'`Application`
Argo CD**, applique la migration). L'instanciation de l'`Application` a été
placée côté cluster sur deux arguments :

1. « Un pattern existe déjà côté cluster » (le harnais banc créait
   l'`Application` `atlas-workflows` par `kubectl apply`).
2. « Un `ApplicationSet` ou une `Application` portée par atlas graverait des
   valeurs atlas dans un manifeste versionné **côté cluster** » — interdit par
   [ADR 0023](0023-plateforme-exemple-generique.md) (neutralité du socle).

Depuis, **deux décisions ont érodé ces arguments** :

- [ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md) a posé
  que **nestor pilote la plateforme, pas le code atlas** (« nestor provisionne
  et installe ; il ne déploie plus de code »). Or l'`Application` Argo CD d'une
  code-location — qui pointe le repo atlas, le path de l'overlay atlas, la
  révision atlas — est **un artefact du cycle de vie du code atlas**, pas de la
  plateforme.
- [ADR 0110](0110-preimage-de-build-et-build-in-pod.md) (amendé) a **sorti du
  cluster le build de l'image de code** (il se fait sur le poste, `atlas`
  `deploy/build-code.sh`). Le cycle de vie du code (build → image → déploiement)
  est désormais **majoritairement côté atlas** ; l'instanciation de
  l'`Application` est le dernier maillon resté côté cluster, par pure inertie.

Surtout, le **second argument de 0094 tombe** : si l'`Application` vit dans le
**repo atlas** (et non dans un `cluster/apps` versionné côté cluster), alors
elle contient des valeurs atlas **à leur place légitime** — l'interdiction ADR
0023 ne s'applique plus. De fait, l'`Application` **existe déjà, versionnée côté
atlas**, comme patron `dataops/<cl>-dagster/deploy/application.example.yaml`
(identique pour citation, mediawatch, pageviews) : la copie poussée par cluster
n'en est qu'un doublon.

Le mécanisme actuel côté cluster est bien vivant (il n'a **pas** été retiré par
le pivot 0110/#644, qui n'a touché que le BUILD) :
`bootstrap/seed-app-of-apps.sh` (`push_citation_declaration` +
`apply_appproject_and_root`), les patrons `platform/argocd/app-of-apps/`, et le
nœud de graphe `gitops-seed-citation` (`nestor/graph.py`, `plan.py`,
`phases.py`, `seed.py`). C'est ce mécanisme que le présent ADR retire de cluster
pour le porter dans atlas.

## Décision

> **atlas INSTANCIE l'`Application` Argo CD de chacune de ses code-locations.**
> Le geste de déploiement d'atlas (aujourd'hui `deploy/install.sh` pour le banc)
> crée + pousse l'`Application` (dérivée de
> `deploy/<cl>-dagster/deploy/application.example.yaml`,
> `repoURL`/`targetRevision` injectés) **en plus** de pousser le code. cluster
> n'instancie plus l'`Application` d'une code-location applicative.

La frontière 0094 devient :

- **atlas** DÉCLARE + FOURNIT + **INSTANCIE** : les manifestes, le
  `code-location.manifest.yaml` montant, le code, **et l'`Application` Argo CD**
  qui référence son overlay.
- **cluster** VALIDE + ORCHESTRE + FOURNIT-LE-CONTENANT : lit et **valide** le
  manifeste montant (garde-fou de revue,
  `scripts/check_code_location_manifest.py` — **reste cluster**), **provisionne
  les dépendances d'infra** (base pgvector, secret dérivé, OBC datalake),
  **applique la migration** PreSync (atlas fournit le `.sql`), et fournit la
  **plateforme** (Argo CD, Gitea, Dagster, le **reconciler** de workspace).

### Ce qui reste PLATEFORME (côté cluster) — inchangé

- Le **reconciler de workspace Dagster** (`platform/dagster/reconciler.yaml`,
  ADR 0103) : il découvre les fragments `dagster-workspace-<nom>` **par label**,
  indifférent à qui a créé l'`Application`. Le déplacement ne le perturbe pas —
  c'est le point rassurant.
- Le **ConfigMap central** `dagster-workspace` (orchestrateur vide, posé par
  Ansible).
- Le **provisionnement d'infra** (base, secrets dérivés, OBC), le **Job de
  migration** PreSync (atlas fournit le `.sql`, cluster l'applique).
- Le **validateur** du manifeste montant (`check_code_location_manifest.py`) :
  cluster garde le garde-fou de revue de ce qu'atlas déclare.
- La **code-location JOUET** `atlas-workflows` (`gitops-seed`) : c'est un
  artefact du **socle** (preuve de la couche gitops au banc, ADR 0086), pas du
  code atlas — son `Application` reste instanciée côté cluster. **Ne pas
  confondre** `gitops-seed` (jouet, reste) avec `gitops-seed-citation` (code
  atlas, part).

### Ce qui passe côté atlas

- La création + le push de l'`Application` Argo CD par code-location, généralisé
  aux **trois** code-locations (citation, mediawatch, pageviews — leurs
  `application.example.yaml` existent déjà, à rendre effectifs).
- L'injection `repoURL`/`targetRevision` dans l'`Application` (ce que faisait
  `push_citation_declaration` côté cluster).

### Ce qui est RETIRÉ de cluster

- `bootstrap/seed-app-of-apps.sh` : `push_citation_declaration`,
  `apply_appproject_and_root`.
- `platform/argocd/app-of-apps/` : les patrons `apps/*.example.yaml`,
  `appproject-cluster-apps.example.yaml`, `root-application.example.yaml`, son
  `README`.
- Le nœud `gitops-seed-citation` (`nestor/graph.py`, `plan.py`, `phases.py`) et
  sa façade `nestor/seed.py` (étapes `push-citation`, `appproject-root`,
  `render_code_location_declaration`).
- Le repo Gitea `cluster/apps` (des déclarations d'`Application`) n'a plus lieu
  d'être.

## Conséquences

- **Cohérence doctrinale** : le cycle de vie du code atlas (build → image →
  `Application` → déploiement) est **entièrement** côté atlas ; cluster ne
  pilote que la plateforme et valide les contrats. Aligné 0108/0110.
- **Un seul geste opérateur atlas** déploie une code-location (build + push
  code + push `Application`), au lieu d'un geste atlas (code) + un geste cluster
  (Application).
- **Fin d'un doublon** : l'`Application` n'est plus dupliquée (patron atlas +
  copie `cluster/apps`) ; sa source de vérité unique est le repo atlas.
- **Contrat révisé** : `contract/code-location.manifest.example.yaml` (l'en-tête
  « avant que cluster crée l'`Application` » devient « cluster valide ; atlas
  instancie »), `contract/atlas.env.cluster.example` (`GITEA_PUSH_URL` — voir «
  Points ouverts »), `contract/README.md`. Le validateur reste cluster.
- **Prix à payer** : atlas gagne un geste d'instanciation (création de CR
  `Application` via l'API k8s ou push GitOps) qu'il n'avait pas ; la garde de
  cible (`GITEA_PUSH_URL`, ADR 0073) doit couvrir ce push. La revue de sécurité
  du manifeste montant reste chez cluster (le déplacement ne relâche pas le
  garde-fou de validation).
- **Migration** : cluster et atlas doivent basculer dans la même fenêtre (une
  code-location ne doit pas se retrouver sans instanciateur). Le jouet
  `atlas-workflows` n'est pas concerné (reste cluster).

## Points ouverts (tranchés à l'implémentation)

- **Repo Gitea cible de l'`Application`** : le banc pousse le code dans
  `atlas/workflows` (`GITEA_PUSH_URL`) ; la prod utilisait `atlas/atlas`
  (code) + `cluster/apps` (Application). Avec l'`Application` portée par atlas,
  un seul monde de nommage doit émerger (l'`Application` peut vivre dans le même
  repo atlas que le code, path dédié).
- **Création : push GitOps vs `kubectl apply`** : l'`Application` peut être
  appliquée directement (`kubectl apply` par `install.sh`, comme le jouet
  aujourd'hui) ou poussée dans un repo qu'une `Application` racine surveille. Le
  premier est plus simple au banc ; le second garde l'App-of-Apps. À trancher
  selon le besoin prod.
- **mediawatch / pageviews** : leurs `application.example.yaml` existent mais
  elles n'ont ni `install.sh` ni nœud de déploiement — le geste atlas doit être
  **générique** (les trois code-locations suivent le même moule).

## Alternatives écartées

- **Garder l'instanciation côté cluster (statu quo 0094)** : fonctionne
  (citation se déploie aujourd'hui via `gitops-seed-citation`), mais laisse un
  artefact du code atlas (l'`Application` pointant le repo/overlay atlas) piloté
  par le socle — en tension avec 0108 (« nestor ne touche pas au code ») et avec
  le fait que le build est déjà sorti du cluster (0110). Le doublon patron-atlas
  / copie-`cluster/apps` persiste.
- **`ApplicationSet` générique côté cluster** : déjà écarté par 0094/0023 (grave
  des valeurs atlas côté cluster). Le présent ADR n'y revient pas — il place
  l'`Application` **côté atlas**, où ces valeurs sont légitimes.
