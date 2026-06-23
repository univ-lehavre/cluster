# Monter le banc local et rejouer la boucle

Ce tutoriel vous fait monter, **de zéro**, un banc local représentatif de la
plateforme, puis y rejouer la boucle complète : pousser un manifeste, le voir
réconcilié, et observer le lineage d'un run. En développement, vous ne consommez
pas un cluster de production : vous montez ce banc et vous y travaillez.

> **Une fois le banc monté et compris**, pour le détail _par brique_ de comment
> brancher votre code (PostgreSQL, Marquez, registry, S3…), voir le mode
> d'emploi [Se brancher sur la plateforme](se-brancher.md). Pour _pourquoi_
> chaque choix, les [ADR](decisions/) ; pour _quoi_ chaque brique,
> [composants](composants.md).

## 1. Monter le banc

La topologie locale de référence est **`multi-node-3`** (1 control plane + 2
workers, banc [Lima](glossaire.md#kubeadm) — ADR
[0030](decisions/0030-nomenclature-bancs-topologies.md)/[0040](decisions/0040-terrains-x-topologies.md)).
`atlas` est un **alias de couches** (layers) : la chaîne MLOps complète
`[metrics, obs, gitops, dataops, gitops-seed, mlflow]`, montée sur un profil
léger `local-path` (pas de [Ceph](composants.md#rook-ceph) — ADR
[0044](decisions/0044-topologie-deploiement-banc-atlas.md)/[0045](decisions/0045-chemins-installation-banc-couches.md)).
Depuis l'[ADR 0083](decisions/0083-layers-source-unique-de-l-ordre.md), `atlas`
n'est **plus la cible dérivée par défaut** (c'est `layers`, dont l'ordre vient
d'un graphe atomique) : on le déclare via `layers: [atlas]` dans la
`topology.yaml`, ou on le rejoue tel quel via `--target atlas` (alias
rétrocompatible) :

```bash
# socle léger → monitoring → gitops (Gitea + Argo CD) → dataops → gitops-seed → mlflow
bench/lima/run-phases.sh atlas
# (variante stockage réel : bench/lima/run-phases.sh atlas-ceph)
```

La dernière phase, **`gitops-seed`**
([`bench/lima/gitea-init.sh`](../bench/lima/gitea-init.sh)), initialise le dépôt
Gitea du banc : elle crée l'organisation `atlas` + le dépôt `workflows`, y
pousse un **workflow jouet**, pose le **webhook** Gitea → Argo CD et
l'`Application` `atlas-workflows`. À partir de là, tout `push` sur ce dépôt
déclenche une réconciliation. État du banc et UIs disponibles :

```bash
bench/lima/run-phases.sh status   # VMs, nœuds, phases franchies, UIs, dernier run
```

> **`kubectl top` (usage CPU/mémoire).** Le chemin `atlas` pose
> **metrics-server** (palier 1, [ADR 0016](decisions/0016-observabilite.md)) :
> `kubectl top nodes` / `kubectl top pods -A` sont opérants sans étape manuelle.

Ces noms (`atlas`, `workflows`, `atlas-admin`) sont des **exemples génériques**
surchargeables par l'environnement (`GITEA_ORG`, `GITEA_REPO`,
`GITEA_ADMIN_USER`… —
[ADR 0023](decisions/0023-plateforme-exemple-generique.md)). Adaptez aux valeurs
de votre déploiement.

## 2. Tout brancher en une commande : `access.sh`

Vous ne devez pas **opérer le cluster** pour travailler. Après le banc monté,
une commande rend tout consommable depuis votre poste
([ADR 0048](decisions/0048-acces-local-developpeur.md)). L'exposition des UI est
en **L4 NodePort** ([ADR 0092](decisions/0092-exposition-hostport-l4.md)) : un
Service `type: NodePort` (`<service>-nodeport`) sert chaque UI en **HTTP clair**
sur `http://<IP-nœud>:<nodePort>`. Plus aucun Gateway, plus aucun DNS, plus
aucun TLS de bordure dans le chemin.

```bash
bench/lima/access.sh
```

Elle fait, en une fois :

- **expose les UIs** : lit du contrat les endpoints `exposed: true`, et pour
  chacun ouvre un `kubectl port-forward svc/<service>-nodeport` vers
  `127.0.0.1:<port-local>` (ports locaux non privilégiés, **aucun sudo**). Les
  URLs deviennent **cliquables** : `http://127.0.0.1:<port-local>` (Argo CD,
  Gitea, Grafana, Dagster, MLflow… — les ports exacts sont affichés à la fin).
  Aucun Gateway, aucun forward SSH, aucun bloc `/etc/hosts`.
- **affiche les secrets** d'un coup (Argo CD, Gitea, Grafana, rôles Postgres).
- **génère `../atlas/.env.cluster.local`** (gitignoré) : un `.env` prêt à
  consommer côté applicatif (Postgres, OpenLineage, registry). Patron versionné
  :
  [`contract/atlas.env.cluster.example`](../contract/atlas.env.cluster.example).

Pour tout arrêter (les `kubectl port-forward`) : `bench/lima/access.sh --stop`.

> **Pourquoi un `port-forward` au banc ?** Le réseau de la VM Lima est **isolé
> du Mac** : le poste n'atteint pas l'IP interne du nœud. `access.sh` ouvre donc
> un `kubectl port-forward` par UI (rien à installer, rien à rebooter), et
> affiche `http://127.0.0.1:<port-local>`. **En déploiement réel**, rien de tout
> ça : le poste atteint directement le réseau des nœuds, et l'accès se fait en
> `http://<IP-nœud>:<nodePort>` **sans aucun forward** (le script rappelle l'URL
> prod en complément). C'est le verrou que lève l'exposition L4 : zéro DNS, zéro
> LB-IPAM ([ADR 0092](decisions/0092-exposition-hostport-l4.md)).

## 3. Pousser sur Gitea

C'est l'acte central de la
[boucle GitOps](composants.md#la-boucle-gitops-de-bout-en-bout) : **vous poussez
vos manifestes dans le dépôt Gitea du banc**, Argo CD les réconcilie — vous ne
faites **jamais** de `kubectl apply` de vos workflows (frontière
[ADR 0022](decisions/0022-argocd-gitops-applicatif.md)). `access.sh` a déjà
ouvert un `port-forward` vers Gitea et affiché son URL
(`http://127.0.0.1:<port-gitea>`) ainsi que les identifiants admin. Composez
l'URL de push à partir de ce port et de ces creds :

```bash
# <port-gitea> : le port local affiché par access.sh pour l'UI Gitea.
# <user>/<password> : les identifiants Gitea affichés par access.sh.
git clone "http://<user>:<password>@127.0.0.1:<port-gitea>/atlas/workflows.git" workflows
cd workflows
# Modifier/ajouter un manifeste (Application, patch de workspace…), puis :
git add . && git commit -m "feat: nouveau workflow"
git push origin main          # → le webhook déclenche Argo CD
```

> **Authentification.** Glisser le mot de passe dans l'URL est commode pour un
> banc jetable ; pour un usage répété, préférez un **token d'accès personnel**
> (UI Gitea → _Settings → Applications_). Le push passe par le `port-forward`
> ouvert par `access.sh` : s'il a été arrêté (`--stop`), relancez `access.sh`
> avant de pousser. Le webhook `push` → Argo CD est posé par `gitops-seed` : un
> `push` réussi déclenche la réconciliation (visible dans l'UI Argo CD,
> `Synced/Healthy`) ; à défaut, Argo CD repolle périodiquement.

**Vérifier le résultat** : l'`Application` passe `Synced/Healthy` (UI Argo CD),
le run s'exécute ([`K8sRunLauncher`](glossaire.md#k8srunlauncher) → Job K8s) et
**émet du lineage** ingéré par Marquez — visible dans son UI. Vous venez de
rejouer, en local, la chaîne complète que la production exécutera à l'identique.

## 4. Accès bas-niveau (dépannage)

> Le **tutoriel** s'arrête à l'étape 3 — vous avez monté le banc et bouclé la
> chaîne GitOps. Cette section est un **appendice how-to** (dépannage), gardé
> ici par commodité ; le mode d'emploi général des accès vit dans
> [`docs/outils.md`](outils.md) et [`docs/se-brancher.md`](se-brancher.md).

Si vous préférez un accès manuel sans `access.sh` (ou pour diagnostiquer), un
`kubectl port-forward` par service reste possible :

```bash
export KUBECONFIG=bench/lima/.work/kubeconfig
# Argo CD sert en HTTP clair (server.insecure) : http, pas https.
kubectl -n argocd      port-forward svc/argocd-server 8080:80
kubectl -n gitea       port-forward svc/gitea-http 3000:80
kubectl -n monitoring  port-forward svc/kube-prometheus-stack-grafana 3003:80  # pas svc/grafana
```

Lire un secret à la main :
`kubectl -n <ns> get secret <nom> -o jsonpath='{.data.<clé>}' | base64 -d`.

## Et ensuite

- Brancher chaque brique depuis votre code (référence par brique) :
  [Se brancher sur la plateforme](se-brancher.md).
- La référence des endpoints (table consolidée) :
  [guide du développeur data](guide-dev-data.md).
- Le détail des combinaisons de banc et des épreuves :
  [matrice du catalogue](architecture/matrice-catalogue.md).
