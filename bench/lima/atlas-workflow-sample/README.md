# Code-location atlas — échantillon jouet (scénarios 27/29, ADR 0086)

Contenu **d'exemple générique** (ADR 0023) que l'init Gitea
([`../gitea-init.sh`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/gitea-init.sh))
**pousse dans le dépôt Gitea du banc**, pour prouver la chaîne GitOps →
workflows atlas
([ADR 0044](/cluster/docs/decisions/0044-topologie-deploiement-banc-atlas/)/[0045](/cluster/docs/decisions/0045-chemins-installation-banc-couches/)).

Ce n'est **pas** une code-location atlas réelle : c'est un **substitut jouet**
([ADR 0086](/cluster/docs/decisions/0086-code-location-jouet-du-socle/)) qui
joue le rôle du contenu qu'`atlas` pousse (`citation-dagster`). C'est une
**vraie code-location gRPC** — un serveur `dagster api grpc -m toy_assets` que
l'orchestrateur charge via son `workspace.yaml` —, pas un Job jetable. Elle rend
le banc **autonome** pour exercer la chaîne Dagster (run réel via `launchRun`,
lineage) **sans dépendre du dépôt atlas**. Réutilise l'image émetteur du banc
(`registry:80/dagster-openlineage-emit:dev`).

| Fichier                                                                                                                                 | Rôle                                                                                                               |
| --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| [`code-location.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/atlas-workflow-sample/code-location.yaml)           | La code-location : Deployment gRPC `toy-codeloc` (`dagster api grpc -m toy_assets`) + Service :4000.               |
| [`workspace-fragment.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/atlas-workflow-sample/workspace-fragment.yaml) | ConfigMap DISJOINT `dagster-workspace-toy` (labellisé `dagster.io/role: code-location`) portant le fragment `toy`. |

Frontière (ADR 0022/0045) : Argo CD déploie **cette code-location**, jamais
l'infra DataOps (CNPG/Dagster/Marquez sont montés par Ansible, livrés vides).
L'image est buildée par la phase `dataops` ; ici on ne déploie que les
manifestes qui la chargent.

Le manifeste de l'`Application` Argo CD qui réconcilie ce dépôt est généré par
l'init (il porte l'URL Gitea réelle du banc — valeur de déploiement, non
versionnée). Modèle :
[`application.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/atlas-workflow-sample/application.example.yaml).

- **Scénario 27** prouve le _déploiement_ (push → Argo CD Synced → code-location
  gRPC Ready + branchée).
- **Scénario 29** prouve le _run e2e_ (`CODELOC_NAME=toy CODELOC_JOB=toy_job` →
  `launchRun` → lineage Marquez).
