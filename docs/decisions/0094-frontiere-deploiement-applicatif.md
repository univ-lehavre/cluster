# 0094 — Frontière de déploiement applicatif : qui orchestre, qui fournit (cluster ↔ atlas)

## Statut

Accepted (2026-06-24 ; passé en Accepted le 2026-07-01, après validation du
diagnostic cluster et amorçage de l'implémentation — App-of-Apps posé
[`platform/argocd/app-of-apps/`](../../platform/argocd/app-of-apps/) + seed prod
[`bootstrap/seed-app-of-apps.sh`](../../bootstrap/seed-app-of-apps.sh) ; plan de
mise en œuvre [Actif](../plans/plan-build-evenementiel-gitops.md)).

Comble un **implicite** des ADR [0022](0022-argocd-gitops-applicatif.md) (Argo
CD déploie l'applicatif), [0033](0033-orchestration-ansible-platform-dataops.md)
(Ansible converge l'infra), [0043](0043-contrat-interface-cluster-atlas.md)
(contrat d'interface `cluster → atlas`) et
[0044](0044-topologie-deploiement-banc-atlas.md) (flux GitOps Gitea → Argo CD,
`sourceRepos` surchargeable). Ces ADR posent **où** atlas se branche et **par
quel canal** son code arrive ; aucun ne dit **qui instancie l'`Application` Argo
CD d'une nouvelle app applicative ni comment atlas DÉCLARE ce qu'il consomme**.
Cet ADR ne **déplace pas** la frontière de répartition
([ADR 0022](0022-argocd-gitops-applicatif.md)/[ADR 0023](0023-plateforme-exemple-generique.md))
— il **comble le trou** révélé par l'audit de la mise en prod du pipeline
citation (issue atlas #499 ; diagnostic cluster validant l'audit et amendant la
proposition). Toutes les valeurs ci-dessous sont des exemples génériques
([ADR 0023](0023-plateforme-exemple-generique.md)) : `cluster/apps`,
`citation.yaml`, `mediawatch.yaml`, `atlas-datalake`, `researchers`.

## Contexte

La mise en prod du pipeline citation a été **auditée** côté atlas (issue #499).
Le diagnostic cluster (multi-agents + vérification adversariale) **valide
l'audit** — les **7 claims runtime sur 7 sont exacts** — mais en tire une
lecture différente de la cause racine et **amende** la proposition d'ADR
montante. Deux faits, vérifiés, cadrent la décision :

- **`pgvector-pg-auth` absent en prod = un DRIFT, pas un bug.** Le Secret dérivé
  `pgvector-pg-auth` (recopie de `username`/`password` du rôle CNPG `pgvector`
  dans le ns `dagster`, pour qu'une code-location atlas atteigne Postgres
  cross-namespace) **existe dans le code** :
  [`bootstrap/roles/platform-dagster/`](../../bootstrap/roles/platform-dagster/)
  (commit `ac0faab`, « feat(dagster): dériver pgvector-pg-auth pour les
  code-locations atlas », documenté à
  [`contract/namespaces-secrets.example.yaml`](../../contract/namespaces-secrets.example.yaml),
  section dérivés). Son absence constatée en prod n'est pas une omission du code
  : c'est que le commit **n'a pas été rejoué** sur l'environnement. C'est un
  manquement de **reproductibilité**
  ([ADR 0052](0052-reproductibilite-des-resultats.md) /
  [ADR 0046](0046-corriger-le-code-pas-l-etat.md)), pas un trou de conception.
- **L'`Application` Argo CD applicative est DÉJÀ instanciée côté cluster — un
  pattern existe.** L'audit suppose qu'aucun mécanisme ne crée l'`Application`
  d'une app atlas. C'est inexact :
  [`bench/lima/gitea-init.sh`](https://github.com/univ-lehavre/cluster/blob/b522133b7cea/bench/lima/gitea-init.sh)
  (l. 172-198) crée l'`Application` `atlas-workflows` par `kubectl apply`, en
  injectant le `repoURL` **réel** (URL Gitea intra-banc) — valeur de déploiement
  jamais versionnée — tandis que le **template** versionné
  ([`bench/lima/atlas-workflow-sample/application.example.yaml`](../../bench/lima/atlas-workflow-sample/application.example.yaml))
  porte la forme générique ([ADR 0023](0023-plateforme-exemple-generique.md)).
  **Déclarer la CR `Application` côté cluster/harnais est donc déjà le modèle
  livré** — pas une nouveauté, pas une inversion du flux push de
  [ADR 0044](0044-topologie-deploiement-banc-atlas.md).

Reste **un implicite réel** : ce pattern est **codé une seule fois**, en dur,
pour `atlas-workflows`. Ajouter une **deuxième** app applicative (un service
`citation`, un `mediawatch`…) n'a **aucun chemin déclaratif** : il faut éditer
un script bash. Et surtout, **atlas n'a aucun moyen de DÉCLARER ce qu'une app
consomme** (base, secrets, bucket, migration) ni **contre quelle version du
contrat**. La proposition montante corrigeait cela en faisant **copier** le
contrat cluster côté atlas — or **la copie figée silencieuse est précisément la
cause racine de l'audit** : un contrat dupliqué dérive sans bruit.

## Décision

### 1. Frontière — atlas DÉCLARE + FOURNIT, cluster VALIDE + INSTANCIE + ORCHESTRE

La frontière de répartition ([ADR 0022](0022-argocd-gitops-applicatif.md) /
[ADR 0023](0023-plateforme-exemple-generique.md)) est **inchangée**. On en
explicite la déclinaison « déploiement applicatif » :

- **atlas** (applicatif/métier) **DÉCLARE et FOURNIT** : les manifestes de
  l'app, l'OBC en tant que **dépendance déclarée**, le `.sql` de migration
  (schéma métier), le code de la code-location, et un **manifeste de déclaration
  montant** (§3).
- **cluster** (socle) **VALIDE, INSTANCIE et ORCHESTRE** : il **lit** la
  déclaration atlas, **vérifie/provisionne** les dépendances, **crée**
  l'`Application` Argo CD, **applique** la migration (orchestration),
  **fournit** l'infra (base, secret dérivé, bucket).

C'est l'application directe du principe déjà en vigueur dans
[ADR 0093](0093-cache-flux-cnpg.md) (« le cluster fournit l'infra ; atlas
branche le code ») et [ADR 0086](0086-code-location-jouet-du-socle.md) (la
code-location est applicative ; le socle l'**héberge et l'instancie** via
GitOps). On ne déplace pas la frontière : on **nomme** qui fait quoi de part et
d'autre du déploiement.

### 2. App-of-Apps côté cluster, via un repo Gitea dédié `cluster/apps`

L'instanciation des `Application` Argo CD applicatives passe par un
**App-of-Apps côté cluster**, adossé à un **repo Gitea de prod dédié** (exemple
générique : `cluster/apps`) :

- cluster **pousse** dans ce repo Gitea les déclarations d'`Application`
  (`citation.yaml`, `mediawatch.yaml`…) ;
- une **`Application` racine** (« app-of-apps ») surveille ce repo : **ajouter
  une app = pousser un fichier**, Argo CD réconcilie et **crée** l'`Application`
  correspondante ;
- celle-ci surveille à son tour le **repo atlas** (le code applicatif).

**Ce n'est PAS une inversion du flux push de
[ADR 0044](0044-topologie-deploiement-banc-atlas.md).** Le flux push de 0044
régit le **CONTENU applicatif** (le code atlas que l'`Application` réconcilie) ;
**déclarer la CR `Application` côté cluster/harnais est déjà le modèle livré**
(cf. §Contexte,
[`gitea-init.sh`](https://github.com/univ-lehavre/cluster/blob/b522133b7cea/bench/lima/gitea-init.sh)
l. 172-198). On **généralise** le pattern existant — template `*.example.yaml`
versionné + injection du `repoURL` réel au seed — d'**un cas codé en dur** à
**un repo déclaratif** : le `repoURL` reste une **valeur de déploiement
injectée, jamais gravée** ([ADR 0023](0023-plateforme-exemple-generique.md)).

**ApplicationSet generic REJETÉ.** Un `ApplicationSet` (générateur git/list)
graverait des **conventions et des valeurs atlas** (motif de découverte,
chemins, noms d'apps) dans un manifeste **versionné côté cluster** — violation
de [ADR 0023](0023-plateforme-exemple-generique.md) (une spécificité de
déploiement ne vit jamais en défaut versionné). L'App-of-Apps + repo Gitea garde
la déclaration **dans le repo de déploiement** (non versionné dans `cluster`),
pas dans le code générique.

### 3. Manifeste de déclaration montant (atlas → cluster)

atlas **fournit**, **versionné dans son dépôt**, un
`code-location.manifest.yaml` qui DÉCLARE ce qu'une app applicative apporte et
consomme :

```yaml
codeLocation: citation # nom de la code-location / app
ready: true # atlas atteste : code mergé, taggé, testé
revision: a3f9c1d # SHA git court = SIGNAL CANONIQUE d'évolution.
# L'image registry:80/citation-dagster:a3f9c1d en DÉRIVE (même tag).
# Une nouvelle révision (nouveau SHA poussé) = nouvelle version à réconcilier.
contractVersion: 3 # version du contrat cluster ciblée
resources: # besoins déclarés → cluster valide la capacité AVANT de déployer
  cpu: 500m # requests indicatifs des pods (run Dagster)
  memory: 1Gi
  disk: 20Gi # volume BLOC (PVC RBD) attaché au pod, si la code-location en a besoin
dependsOn:
  # Autres code-locations atlas requises (ex. citation consomme les marts de
  # mediawatch). cluster ORDONNE le déploiement (sync-waves Argo CD : la dépendance
  # déployée et ready AVANT) et REFUSE de créer l'app si une code-location requise
  # est absente ou non-`ready`.
  codeLocations: [mediawatch]
  database: [pgvector] # bases logiques requises
  secrets: [pgvector-pg-auth] # secrets (dérivés inclus) requis
  # OBC = stockage OBJET (S3 RGW Ceph), distinct du `disk` bloc ci-dessus :
  # marts/parquets/artefacts. Chaque bucket déclare sa taille et sa classe.
  buckets:
    - name: atlas-datalake # OBC requise
      size: 100Gi # capacité attendue (dimensionnement Ceph)
      storageClass: rook-ceph-datalake
  migrations: [001-researchers-hnsw.sql] # migrations à appliquer avant l'app
```

cluster **LIT** ce manifeste pour faire des **choix éclairés** : avant de créer
l'`Application` (§2), il **vérifie/provisionne** les dépendances déclarées (base
présente, secret dérivé posé, OBC instanciée, migration appliquée) **et valide
la capacité** — les `resources` déclarées (cpu/memory, volume **bloc** `disk` en
PVC RBD) et les `buckets` (stockage **objet** S3 RGW, taille + classe) sont
confrontés à la capacité réelle du cluster ; un besoin qui dépasse la marge
**échoue bruyamment** plutôt que de saturer Ceph en silence. Le manifeste
distingue donc **deux stockages** que cluster provisionne différemment : le
**bloc** (PVC `disk`, RBD) et l'**objet** (OBC `buckets`, RGW).

Les **`dependsOn.codeLocations`** déclarent les dépendances
**inter-applicatives** (une code-location qui en consomme une autre — ex.
`citation` lit les marts de `mediawatch`). cluster **ordonne** alors le
déploiement via les **sync-waves Argo CD** (la dépendance déployée et `ready`
**avant** le dépendant) et **refuse** de créer l'`Application` si une
code-location requise est **absente ou non-`ready`**. C'est le pendant inter-app
de la validation des dépendances infra : un graphe de déploiement cohérent, pas
un ordre au hasard de la réconciliation.

La **`revision`** (SHA git) est le **signal d'évolution** : une code-location
qui change pousse un nouveau SHA → nouvelle `revision` ici **et** nouveau tag
d'image dans les overlays atlas → l'`Application` (§2) le voit et réconcilie.
Pas de détection magique : le SHA est la source unique de « quelque chose a
changé ».

**Ce manifeste FUSIONNE le garde-fou de synchronisation** (l'ex-« D3 » de la
proposition montante, qui faisait **copier** le contrat cluster côté atlas). Au
lieu qu'atlas **duplique** le contrat, atlas **DÉCLARE ce qu'il consomme** +
**contre quelle `contractVersion`** ; cluster **valide la cohérence** (version
connue **et** existence effective des dépendances). On **supprime la copie figée
silencieuse** — la **cause racine** de l'audit : un contrat copié dérive sans
bruit ; un contrat **déclaré + validé à l'instanciation** échoue **bruyamment**
dès que la version ou une dépendance manque. C'est un **diff-able** de plus,
cohérent avec [ADR 0043](0043-contrat-interface-cluster-atlas.md) (« le contrat
est diff-able ; tout changement est visible en revue »).

### 4. OBC `atlas-datalake` — manifeste CÔTÉ CLUSTER, déclarée comme dépendance par atlas

L'`ObjectBucketClaim` `atlas-datalake` est un **manifeste versionné côté
cluster**, instancié via l'App-of-Apps Argo CD (§2). C'est **cohérent avec le
stockage déjà côté cluster** : le bucket `mlflow-artifacts`
([`platform/mlflow/mlflow.yaml`](../../platform/mlflow/mlflow.yaml)) et le
backing S3 de Loki ([`platform/loki/`](../../platform/loki/)) sont **déjà** des
OBC fournies par le socle — un bucket est de l'**infra de stockage**, pas du
métier (forme générique :
[`object-bucket-claim-example.yaml`](../../storage/ceph/storageClass/datalake/object-bucket-claim-example.yaml)).
atlas **DÉCLARE** ce bucket comme dépendance (`buckets: [atlas-datalake]` dans
son manifeste, §3) ; **cluster le fournit** (provisionné par le RGW datalake en
prod, SeaweedFS au banc — [ADR 0036](0036-backing-s3-unique-rgw.md)).

### 5. Migrations SQL applicatives — atlas FOURNIT le `.sql`, cluster l'APPLIQUE

Une migration de schéma métier (exemple générique : table `researchers`, colonne
`vector(384)`, index HNSW) est du **schéma applicatif** : atlas **FOURNIT** le
`.sql`. cluster l'**APPLIQUE** via un **Job Kubernetes** orchestré par
l'`Application`, en **hook `PreSync` Argo CD** — la migration tourne **avant**
que les workloads de l'app ne démarrent. C'est exactement « atlas fournit,
cluster orchestre » (§1), et cohérent avec
[ADR 0086](0086-code-location-jouet-du-socle.md) (orchestration GitOps du chemin
applicatif). La migration est déclarée dans `dependsOn.migrations` (§3) ;
cluster n'invente pas le schéma, il l'exécute.

## Conséquences

**Le trou est fermé.** Toute app applicative — pas seulement `atlas-workflows` —
se déploie par l'**App-of-Apps** : ajouter une app = pousser un fichier dans
`cluster/apps`. Le pattern codé en dur dans
[`gitea-init.sh`](https://github.com/univ-lehavre/cluster/blob/b522133b7cea/bench/lima/gitea-init.sh)
devient un **chemin déclaratif** généralisé.

**La doc redevient fiable.** La procédure de mise en prod d'une app vit **côté
cluster** — le dépôt qui **possède l'état** (Argo CD, les dépendances, le repo
`cluster/apps`). Plus de procédure tributaire d'un savoir implicite réparti sur
deux dépôts.

**La dérive est attrapée.** Le **manifeste de déclaration + `contractVersion`**
remplace la **copie figée** : cluster valide version **et** existence des
dépendances à l'instanciation. Une `contractVersion` inconnue ou une dépendance
absente **échoue bruyamment** au lieu de dériver en silence — la cause racine de
l'audit est neutralisée.

**Coût assumé (porté par cluster).** Le socle porte désormais : (a) un **repo
Gitea `cluster/apps`** de prod, (b) l'**`Application` racine app-of-apps**, (c)
un **validateur** du `code-location.manifest.yaml` (version + dépendances ;
langage selon [ADR 0049](0049-doctrine-choix-outil-par-action.md)), (d) le **Job
de migration** en hook `PreSync`. Briques minimales, mais réelles, à outiller et
à garder idempotentes ([ADR 0034](0034-validation-e2e-from-scratch.md)).

**La frontière 0022/0023 est préservée.** atlas reste l'unique siège du métier
(manifestes, `.sql`, code, déclaration) ; cluster reste l'unique siège de
l'infra et de l'orchestration. Aucune valeur de déploiement (`repoURL`, noms
d'apps atlas, conventions de découverte) n'est gravée dans un manifeste
versionné de `cluster` — `ApplicationSet` generic **rejeté** pour cette raison
précise.

**Actions de mise en œuvre.**

- **Rejouer le drift `pgvector-pg-auth`** côté cluster (commit `ac0faab` non
  appliqué en prod) — pas une livraison de code, un **rejeu**
  ([ADR 0052](0052-reproductibilite-des-resultats.md) /
  [ADR 0046](0046-corriger-le-code-pas-l-etat.md)).
- **Créer** le repo Gitea `cluster/apps`, l'**`Application` racine app-of-apps**
  et le **template** d'`Application` applicative (`*.example.yaml` versionné,
  `repoURL` injecté au seed — généralisation de
  [`application.example.yaml`](../../bench/lima/atlas-workflow-sample/application.example.yaml)).
- **Définir** le schéma `code-location.manifest.yaml` (§3) **et son validateur**
  côté cluster (cohérence `contractVersion` + existence des dépendances).
- **Outiller** le **Job de migration** en hook `PreSync` (§5), idempotent,
  prouvé au banc.

## Voir aussi

- [ADR 0022](0022-argocd-gitops-applicatif.md) — Argo CD applicatif / frontière
  infra-app (la frontière que cet ADR décline, non déplacée).
- [ADR 0023](0023-plateforme-exemple-generique.md) — Valeurs génériques
  (`repoURL` injecté, `ApplicationSet` generic rejeté).
- [ADR 0033](0033-orchestration-ansible-platform-dataops.md) — Ansible converge
  l'infra (la moitié « cluster orchestre l'infra » de la frontière).
- [ADR 0043](0043-contrat-interface-cluster-atlas.md) — Contrat d'interface
  diff-able (le `code-location.manifest.yaml` en est le pendant montant).
- [ADR 0044](0044-topologie-deploiement-banc-atlas.md) — Flux GitOps Gitea →
  Argo CD (le push de contenu **non** inversé par l'app-of-apps).
- [ADR 0086](0086-code-location-jouet-du-socle.md) — Code-location déployée par
  GitOps (la vraie code-location atlas instanciée par le socle).
- [ADR 0036](0036-backing-s3-unique-rgw.md) — Backing S3 par profil (l'OBC
  `atlas-datalake` provisionnée RGW/SeaweedFS).
- [ADR 0052](0052-reproductibilite-des-resultats.md) /
  [ADR 0046](0046-corriger-le-code-pas-l-etat.md) — Reproductibilité / corriger
  le code (le drift `pgvector-pg-auth` à rejouer).

---
