# Développeur atlas — le point d'entrée

Page récapitulative pour le **développeur data** qui travaille dans le dépôt
applicatif `atlas` et consomme la plateforme. Tout ce qui est utile, en un
endroit.

> **Frontière (ADR [0022](decisions/0022-argocd-gitops-applicatif.md) /
> [0023](decisions/0023-plateforme-exemple-generique.md)).** Vous écrivez le
> **code métier** (assets, pipelines, requêtes) dans `atlas` ;
> l'**infrastructure** (générique) vit dans ce dépôt. Vous poussez du _contenu_
> ; le socle fournit le _contenant vide_. Vous ne faites **jamais** de
> `kubectl apply` de vos workflows — Argo CD les réconcilie depuis Gitea.

## Démarrer en deux commandes (banc local)

```bash
# 1. Monter le banc (topologie multi-node-3, chemin atlas, profil léger)
bench/lima/run-phases.sh atlas

# 2. Tout brancher : URLs cliquables + secrets regroupés + ../atlas/.env.cluster.local
bench/lima/access.sh
```

Puis travaillez dans `atlas` et `git push` : **zéro geste**, l'image se
construit et se déploie toute seule. Vous ne buildez **plus** l'image à la main.
Détail pas à pas : [guide du développeur data](guide-dev-data.md) ; mécanique
complète ci-dessous.

## Ce qui se passe quand vous poussez (build événementiel)

_Mise en place — la preuve banc de bout en bout (run from-scratch) est en
cours._

Deux webhooks Gitea **distincts** se déclenchent selon _ce_ que vous poussez :

- **Webhook #1 — déploiement (déjà là).** Un push dans le repo Gitea
  `cluster/apps` (le manifeste d'une `Application`) réveille **Argo CD**, qui
  réconcilie l'App-of-Apps. C'est le canal GitOps historique
  ([ADR 0022](decisions/0022-argocd-gitops-applicatif.md) /
  [0044](decisions/0044-topologie-deploiement-banc-atlas.md)).
- **Webhook #2 — build (nouveau).** Un `git push` de **code** dans `atlas/atlas`
  déclenche la chaîne de fabrique d'image, in-cluster et sans intervention.

La chaîne du webhook #2 fonctionne ainsi :

1. `git push` sur `atlas/atlas` → **webhook Gitea #2** (distinct du #1) →
   **EventSource** Argo Events → **EventBus** NATS.
2. Le **Sensor** « code-location-build » **dérive** la `codeLocation` du
   **chemin modifié** (`dataops/<X>-dagster/`, jamais énuméré) et prend
   `revision = body.after`.
3. Il soumet le **WorkflowTemplate** « image-builder » (BuildKit rootless, sur
   un worker) : build + push vers `registry:80/<cl>:<revision>`.
4. Le workflow **lit le digest** de l'image poussée et fait un **write-back**
   dans `apps/<cl>.yaml` du repo Gitea `cluster/apps`, **épinglé par
   `@sha256`**.
5. Ce write-back **est** un push sur `cluster/apps` → **webhook #1** → **Argo
   CD** réconcilie → le pod gRPC (code-location Dagster) tourne sur la nouvelle
   image.

**Découverte, pas énumération.** Créer une **nouvelle** code-location revient à
ajouter un dossier `dataops/<X>-dagster/` dans `atlas` et à le pousser : le
Sensor dérive `<X>` du chemin, aucune liste à tenir côté cluster. Un filet
anti-perte d'évènement (**CronWorkflow**) compare périodiquement le `HEAD`
d'atlas au tag déployé et rattrape un push manqué.

**Déploiement par digest, jamais par tag.** Le SHA court (`revision`) est le tag
**lisible** (traçabilité commit → image) ; le `@sha256` est l'**ancre**
d'immuabilité effectivement déployée
([ADR 0006](decisions/0006-matrice-de-versions-et-politique-de-bump.md),
épinglage par digest ; [0052](decisions/0052-reproductibilite-des-resultats.md),
reproductibilité).

**Frontière atlas ↔ cluster
([ADR 0094](decisions/0094-frontiere-deploiement-applicatif.md)).** atlas
**déclare + fournit** (le manifeste montant, avec ses placeholders
`__CITATION_IMAGE__` / `__CITATION_IMAGE_DIGEST__`) ; cluster **valide +
instancie + remplit** (lit le manifeste, build, injecte le digest, crée
l'`Application`). Design complet :
[ADR 0095](decisions/0095-build-applicatif-evenementiel-in-cluster.md) et son
[plan de mise en œuvre](plans/plan-build-evenementiel-gitops.md).

## Comprendre la plateforme

| Page                                                              | Pour quoi                                                                                                                    |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| [Composants — la pile technologique](composants.md)               | Ce que fait chaque brique (PostgreSQL/CNPG, Dagster, Marquez, MLflow, Argo CD, Gitea, Ceph, Cilium…) et pourquoi elle est là |
| [Guide du développeur data](guide-dev-data.md)                    | Comment se brancher : endpoints, secrets, paramétrage, boucle GitOps, accès local                                            |
| [Glossaire](glossaire.md)                                         | Définitions courtes des termes techniques                                                                                    |
| [Chaîne DataOps (accès & vérifs)](architecture/chaine-dataops.md) | Vue d'ensemble Dagster → CNPG → Marquez + suivi de modèles MLflow                                                            |

## Se brancher — le contrat d'interface

Source **machine-lisible** de ce que le socle expose
([ADR 0043](decisions/0043-contrat-interface-cluster-atlas.md)) :

| Artefact                                                                                  | Contenu                                                      |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| [`contract/`](../contract/)                                                               | Vue d'ensemble du contrat                                    |
| [`contract/endpoints.example.yaml`](../contract/endpoints.example.yaml)                   | Services : FQDN, port, auth, UI                              |
| [`contract/storage-classes.example.yaml`](../contract/storage-classes.example.yaml)       | StorageClasses par profil                                    |
| [`contract/namespaces-secrets.example.yaml`](../contract/namespaces-secrets.example.yaml) | Namespaces de destination + conventions de secrets           |
| [`contract/atlas.env.cluster.example`](../contract/atlas.env.cluster.example)             | Patron du `.env` consommé par atlas (généré par `access.sh`) |

## Commandes utiles (banc Lima)

```bash
bench/lima/run-phases.sh atlas      # monter le socle complet (GitOps + DataOps)
bench/lima/run-phases.sh status     # état du banc (VMs, nœuds, phases, UIs)
bench/lima/access.sh                # URLs + secrets + .env atlas
bench/lima/access.sh --stop         # arrêter les tunnels + retirer le bloc /etc/hosts
bench/lima/run-phases.sh down       # détruire le banc
```

- Harnais du banc : [`bench/lima/`](../bench/lima/) · validations :
  [`bench/lima/RESULTS.md`](../bench/lima/RESULTS.md)
- Init du dépôt Gitea (org/repo + webhook) :
  [`bench/lima/gitea-init.sh`](https://github.com/univ-lehavre/cluster/blob/b522133b7cea/bench/lima/gitea-init.sh)

## Décisions qui vous concernent (ADR)

| ADR                                                                | Sujet                                                                 |
| ------------------------------------------------------------------ | --------------------------------------------------------------------- |
| [0022](decisions/0022-argocd-gitops-applicatif.md)                 | Frontière infra (Ansible) / applicatif (Argo CD)                      |
| [0043](decisions/0043-contrat-interface-cluster-atlas.md)          | Contrat d'interface cluster → atlas                                   |
| [0044](decisions/0044-topologie-deploiement-banc-atlas.md)         | Topologie du banc atlas (Gitea intra-banc, webhook)                   |
| [0045](decisions/0045-chemins-installation-banc-couches.md)        | Chemins d'installation nommés (`atlas`, `atlas-ceph`…)                |
| [0048](decisions/0048-acces-local-developpeur.md)                  | Accès local développeur (`access.sh`)                                 |
| [0094](decisions/0094-frontiere-deploiement-applicatif.md)         | Frontière de déploiement : atlas déclare, cluster instancie           |
| [0095](decisions/0095-build-applicatif-evenementiel-in-cluster.md) | Build applicatif événementiel in-cluster (push → image → déploiement) |
| [0023](decisions/0023-plateforme-exemple-generique.md)             | Valeurs génériques, config locale non versionnée                      |

Index complet : [décisions (ADR)](decisions/).

## Où vit quoi

- **Code métier, images, workflows** → dépôt `atlas` (assets Dagster, services,
  PWA).
- **Infra, manifestes, socle** → ce dépôt (`platform/`, `storage/`,
  `bootstrap/`).
- **Secrets / valeurs réelles** → config locale **non versionnée** (le `.env`
  généré par `access.sh`, gitignoré) — jamais commitées (ADR 0023).
