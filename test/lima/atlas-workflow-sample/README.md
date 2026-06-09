# Workflow atlas — échantillon jouet (scénario 27, #231)

Contenu **d'exemple générique** (ADR 0023) que l'init Gitea
([`../gitea-init.sh`](../gitea-init.sh)) **pousse dans le dépôt Gitea du banc**,
pour prouver la chaîne GitOps → workflows atlas
([ADR 0044](../../../docs/decisions/0044-topologie-deploiement-banc-atlas.md)/[0045](../../../docs/decisions/0045-chemins-installation-banc-couches.md)).

Ce n'est **pas** un workflow atlas réel : c'est un **substitut jouet** qui joue
le rôle du contenu qu'`atlas` poussera (un asset Dagster trivial qui émet du
lineage). Il réutilise l'image émetteur du banc
(`registry:80/dagster-openlineage-emit:dev`).

| Fichier                                  | Rôle                                                                                    |
| ---------------------------------------- | --------------------------------------------------------------------------------------- |
| [`workflow-job.yaml`](workflow-job.yaml) | Le « workflow » : Job Dagster qui matérialise un asset → lineage OpenLineage → Marquez. |

Frontière (ADR 0022/0045) : Argo CD déploie **ce workflow**, jamais l'infra
DataOps (CNPG/Dagster/Marquez sont montés par Ansible, livrés vides). L'image
est buildée par la phase `dataops` ; ici on ne déploie que le manifeste qui la
lance.

Le manifeste de l'`Application` Argo CD qui réconcilie ce dépôt est généré par
l'init (il porte l'URL Gitea réelle du banc — valeur de déploiement, non
versionnée).
