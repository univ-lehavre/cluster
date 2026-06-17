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

Puis travaillez dans `atlas` et `git push` (le webhook Gitea → Argo CD
réconcilie). Détail pas à pas :
[guide du développeur data](guide-dev-data.md#travailler-en-local-sur-le-banc-multi-node-3-chemin-atlas).

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
  [`bench/lima/gitea-init.sh`](../bench/lima/gitea-init.sh)

## Décisions qui vous concernent (ADR)

| ADR                                                         | Sujet                                                  |
| ----------------------------------------------------------- | ------------------------------------------------------ |
| [0022](decisions/0022-argocd-gitops-applicatif.md)          | Frontière infra (Ansible) / applicatif (Argo CD)       |
| [0043](decisions/0043-contrat-interface-cluster-atlas.md)   | Contrat d'interface cluster → atlas                    |
| [0044](decisions/0044-topologie-deploiement-banc-atlas.md)  | Topologie du banc atlas (Gitea intra-banc, webhook)    |
| [0045](decisions/0045-chemins-installation-banc-couches.md) | Chemins d'installation nommés (`atlas`, `atlas-ceph`…) |
| [0048](decisions/0048-acces-local-developpeur.md)           | Accès local développeur (`access.sh`)                  |
| [0023](decisions/0023-plateforme-exemple-generique.md)      | Valeurs génériques, config locale non versionnée       |

Index complet : [décisions (ADR)](decisions/).

## Où vit quoi

- **Code métier, images, workflows** → dépôt `atlas` (assets Dagster, services,
  PWA).
- **Infra, manifestes, socle** → ce dépôt (`platform/`, `storage/`,
  `bootstrap/`).
- **Secrets / valeurs réelles** → config locale **non versionnée** (le `.env`
  généré par `access.sh`, gitignoré) — jamais commitées (ADR 0023).
