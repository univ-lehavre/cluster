# 0086 — Code-location jouet du socle : un pipeline Dagster minimal, branché en permanence

## Statut

Proposed (2026-06-18)

## Contexte

L'orchestrateur Dagster du socle est livré **vide** : son `workspace.yaml` porte
`load_from: []`
([`platform/dagster/dagster.yaml`](../../platform/dagster/dagster.yaml), ADR
0026). Le code métier (assets, jobs, schedules) vit dans une **code-location**
externe — un serveur gRPC qu'un consommateur (atlas, `citation-dagster`) déploie
et branche dans le workspace, par GitOps (frontière infra/applicatif, ADR
0022/0045).

Conséquence : **sans atlas déployé, l'orchestrateur n'a aucun pipeline
jouable.** Or plusieurs preuves de banc en ont besoin :

- le scénario **29** (code-location externe → run via GraphQL → lineage)
  **skippe** faute de `CODELOC_NAME` (aucune location branchée) ;
- la chaîne **drift/CT** (#404) et un **e2e global** (run réel → lineage → drift
  → MLflow) ne peuvent pas être prouvés en autonomie ;
- le banc dépend d'un **second dépôt** (atlas) pour exercer son propre
  orchestrateur.

Aujourd'hui, la seule preuve « un run Dagster réel émet du lineage » est
`dataops_chain_emit_and_verify`
([`bench/lima/run-phases.sh`](../../bench/lima/run-phases.sh)) : un **Job k8s
jetable** qui lance `dagster asset materialize -m toy_assets` (asset jouet
[`platform/dagster/image-openlineage/toy_assets.py`](../../platform/dagster/image-openlineage/toy_assets.py)).
C'est un run **CLI one-shot hors orchestrateur** : il prouve l'émission
OpenLineage, mais **PAS** le chemin réel (webserver → code-location gRPC →
K8sRunLauncher) que suivent atlas et l'UI. Le `toy_assets` existe donc déjà,
mais n'est jamais **chargé** dans le workspace.

## Décision

**Le socle expose une code-location jouet PERMANENTE — un serveur gRPC minimal
(`toy-codeloc`) chargé dans le `workspace.yaml` de l'orchestrateur — qui rend le
banc autonome pour exercer la vraie chaîne Dagster, sans dépendre d'atlas.**

1. **Brique** : un Deployment gRPC `toy-codeloc` dans le ns `dagster`, jumeau
   minimal de la code-location atlas (`citation-dagster`). Il **réutilise
   l'image existante**
   [`registry:80/dagster-openlineage-emit`](../../platform/dagster/image-openlineage/Dockerfile)
   (dagster + openlineage + `toy_assets.py`) — seule la commande change :
   `dagster api grpc -m toy_assets` au lieu du `materialize` CLI. Pas de
   nouvelle image.
2. **Branchement** : le `workspace.yaml` du socle charge cette location
   (`load_from: [{grpc_server: {host: toy-codeloc, port: …, location_name: toy}}]`)
   au lieu de `load_from: []`. L'orchestrateur n'est donc plus vide — il expose
   en permanence l'asset/job `toy_dataset`, jouable par le webserver et le
   daemon.
3. **Frontière (ADR 0022/0045) — déployée PAR GITOPS, comme une vraie
   location.** Une code-location est de l'**applicatif** (assets/jobs) : la
   retirer n'empêche pas Argo CD de réconcilier → elle relève du GitOps, pas
   d'Ansible. On la déploie donc **exactement comme atlas** : son Deployment
   gRPC + Service + patch `workspace.yaml` vivent dans le dépôt Gitea intra-banc
   (org `atlas`), réconciliés par une **Application Argo CD** (AppProject
   `atlas`, ns `dagster` déjà autorisé). C'est le **remplacement du sample jouet
   existant** (`bench/lima/atlas-workflow-sample/` — aujourd'hui un Job
   `materialize` jetable) par une **vraie code-location gRPC**. Valeurs
   génériques (ADR 0023) : `toy_dataset`/`toy_job`, location `toy`, aucun
   métier.

   **Bénéfice décisif vs Ansible** : ce chemin exerce TOUTE la chaîne GitOps en
   plus (push Gitea → webhook → Argo CD Synced → gRPC → run → lineage) — c'est
   précisément ce que le scénario 27 prouve. La location jouet teste donc _plus_
   (GitOps + orchestrateur) et reste _fidèle_ au chemin réel d'atlas, sans
   dépendre d'atlas.

4. **Remplace le CLI `dataops_chain_emit_and_verify`** : la preuve « un run
   Dagster réel émet du lineage ingéré par Marquez » passe désormais par un
   **run via le chemin réel** (GraphQL `launchRun` sur le webserver, comme
   atlas/l'UI/le scénario 29), pas par un Job k8s `materialize` hors
   orchestrateur. Le harnais bash perd sa construction de Job jetable ; il lance
   la location jouet. Plus fidèle à la prod.

## Conséquences

- **Le banc devient autonome** pour la chaîne Dagster : le scénario 29 ne skippe
  plus (`CODELOC_NAME=toy`), et les scénarios e2e/drift à venir (#404) ont un
  pipeline à exercer sans atlas.
- **Chemin de run fidèle à la prod** : on prouve
  `webserver → gRPC → K8sRunLauncher`, pas un `materialize` CLI qui
  court-circuite l'orchestrateur.
- **L'orchestrateur n'est plus livré vide** : nuance l'ADR 0026 («
  orchestrateurs livrés vides ») — une fois `gitops-seed` joué, le workspace
  charge la location jouet (jamais du métier). Atlas ajoute SA location en plus
  (le workspace en charge plusieurs).
- **Le scénario 27 monte en gamme** : il déployait un Job jetable par GitOps ;
  il déploie désormais une **vraie code-location gRPC** par GitOps → preuve plus
  proche de la prod.
- **Une brique de plus à maintenir** (Deployment + Service + patch workspace
  dans le seed Gitea), mais minimale (image réutilisée, asset déjà écrit).
- **Risque de confusion** : une location `toy` visible dans l'UI Dagster
  pourrait être prise pour du métier. Mitigation : nommage explicite (`toy`),
  documentée comme harnais de test.

## À revoir si

- Atlas (ou tout consommateur) est **toujours** déployé sur les bancs où l'on
  prouve la chaîne → la location jouet devient redondante avec une vraie
  location ; on pourrait la restreindre aux bancs sans consommateur.
- Dagster impose un jour qu'une location de test soit isolée du workspace de
  prod → la conditionner (présente seulement en `target_kind: lima`).

## Alternatives écartées

- **Garder le CLI `materialize` jetable (statu quo).** Écarté : il ne charge
  jamais la location, donc le scénario 29 et la chaîne e2e/drift restent
  inprouvables en autonomie ; et il ne teste pas le chemin réel webserver→gRPC.
- **Dépendre de la code-location atlas pour les preuves.** Écarté : couple le
  banc du cluster à un second dépôt ; le cluster doit pouvoir prouver SON
  orchestrateur seul.
- **Poser la location jouet par Ansible (avec l'orchestrateur).** Écarté : une
  code-location est applicative (ADR 0022/0045 : applicatif = GitOps) ; la poser
  par Ansible serait une exception à la frontière, et surtout n'exercerait PAS
  la chaîne GitOps. Le déploiement GitOps est strictement plus probant (teste
  push→Argo CD→gRPC) et reste fidèle au chemin réel d'atlas — sans coût
  supplémentaire notable (le seed Gitea existe déjà, on remplace son contenu).
- **Une nouvelle image dédiée.** Écarté : l'image émetteur existante porte déjà
  dagster
  - `toy_assets` ; seule la commande de lancement change.
