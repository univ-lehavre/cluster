# Architecture Decision Records (ADR)

Trace **pourquoi** chaque choix de conception du cluster — pas le _comment_
(couvert par les README/RUNBOOK), mais le contexte, l'alternative écartée et les
conséquences assumées.

> 🗺️ **Lecture par thème.** Cet index est **chronologique** (un ADR = une
> décision datée, immuable). Pour une lecture **par domaine** (stockage, réseau,
> sécurité, plan de contrôle, plateforme/GitOps, conventions), voir les
> [vues d'architecture](../architecture/) qui agrègent et relient les ADR.

Format léger inspiré de Michael Nygard :

- **Contexte** — ce qui a forcé une décision.
- **Décision** — ce qui a été acté.
- **Statut** — Accepted / Superseded by `NNNN` / Deprecated.
- **Conséquences** — gain, prix à payer, garde-fous à connaître.

## Index

| #    | Titre                                                                                                                                             | Statut             |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| 0001 | [Réplication ×3 pour les workloads bloc (vs EC)](0001-replication-x3-pour-workloads-bloc.md)                                                      | Accepted           |
| 0002 | [Control plane unique avec `--control-plane-endpoint`](0002-control-plane-unique-avec-endpoint.md)                                                | Accepted           |
| 0003 | [Pas de chiffrement Ceph — sécurité du réseau déléguée](0003-pas-de-chiffrement-ceph-tailscale.md)                                                | Accepted           |
| 0004 | [Erasure coding 2+1 réservé au datalake](0004-erasure-coding-2plus1-datalake.md)                                                                  | Accepted           |
| 0005 | [CRI = `containerd.io` depuis le dépôt Docker](0005-cri-containerd-via-depot-docker.md)                                                           | Accepted           |
| 0006 | [Matrice de versions et politique de bump](0006-matrice-de-versions-et-politique-de-bump.md)                                                      | Accepted           |
| 0007 | [Hyperconvergence : control plane portant OSDs](0007-hyperconvergence-control-plane-osd.md)                                                       | Accepted           |
| 0008 | [`metadataDevice` NVMe unique — SPOF par nœud assumé](0008-metadatadevice-nvme-spof-par-noeud.md)                                                 | Accepted           |
| 0009 | [Pourquoi 4 nœuds ?](0009-pourquoi-4-noeuds.md)                                                                                                   | Accepted           |
| 0010 | [Dashboard Kubernetes en `cluster-admin`](0010-dashboard-cluster-admin.md)                                                                        | Accepted           |
| 0011 | [Registry interne HTTP sans authentification](0011-registry-http-sans-auth.md)                                                                    | Accepted           |
| 0012 | [RStudio sans authentification (`DISABLE_AUTH=true`)](0012-rstudio-disable-auth.md)                                                               | Accepted           |
| 0013 | [Sauvegarde des données applicatives (VolumeSnapshots CSI)](0013-sauvegarde-donnees-applicatives.md)                                              | Accepted           |
| 0014 | [Durcissement du plan de contrôle (`kubeadm init` nu)](0014-durcissement-kubeadm-init.md)                                                         | Accepted           |
| 0015 | [Stratégie d'upgrade Kubernetes (in-place vs rebuild)](0015-strategie-upgrade-kubernetes.md)                                                      | Accepted           |
| 0016 | [Observabilité (metrics-server maintenant, Prometheus plus tard)](0016-observabilite.md)                                                          | Accepted           |
| 0017 | [Langage des scripts (bash / jq / Python / bats)](0017-langage-des-scripts.md)                                                                    | Superseded by 0049 |
| 0018 | [Rook-Ceph plutôt que Longhorn](0018-rook-ceph-vs-longhorn.md)                                                                                    | Accepted           |
| 0019 | [Durcissement réseau Cilium (WireGuard + Hubble)](0019-durcissement-reseau-cilium.md)                                                             | Accepted           |
| 0020 | [Exposition réseau tout-Cilium (LB-IPAM + L2 + Gateway API)](0020-exposition-reseau-tout-cilium.md)                                               | Accepted           |
| 0021 | [cert-manager + CA interne (TLS de bordure)](0021-cert-manager-ca-interne.md)                                                                     | Accepted           |
| 0022 | [Argo CD (GitOps applicatif)](0022-argocd-gitops-applicatif.md)                                                                                   | Accepted           |
| 0023 | [Dépôt multi-topologies (plusieurs infra déclarées, une activée)](0023-plateforme-exemple-generique.md)                                           | Accepted           |
| 0024 | [PostgreSQL managé via CloudNativePG (+ pgvector)](0024-postgres-manage-cloudnative-pg.md)                                                        | Accepted           |
| 0025 | [Sécurité active : chaos + attaques contrôlées (D/A/R)](0025-securite-active-chaos-attaques-controlees.md)                                        | Accepted           |
| 0026 | [Orchestration des pipelines via Dagster](0026-orchestration-dagster.md)                                                                          | Accepted           |
| 0027 | [Bootstrap paramétré multi-cluster (Cilium Cluster Mesh)](0027-bootstrap-parametre-multi-cluster.md)                                              | Accepted           |
| 0028 | [Store de lineage OpenLineage via Marquez](0028-orchestration-openlineage-marquez.md)                                                             | Accepted           |
| 0029 | [Toute page Markdown est atteignable depuis la doc](0029-markdown-atteignable-doc.md)                                                             | Accepted           |
| 0030 | [Nomenclature des bancs et topologies](0030-nomenclature-bancs-topologies.md)                                                                     | Accepted           |
| 0031 | [Terrain d'exécution cloud ARM (cadrage)](0031-terrain-cloud-arm.md)                                                                              | Accepted           |
| 0032 | [OpenTofu pour le provisioning des VM cloud](0032-opentofu-provisioning-cloud.md)                                                                 | Accepted           |
| 0033 | [Orchestration Ansible des addons plateforme DataOps](0033-orchestration-ansible-platform-dataops.md)                                             | Accepted           |
| 0034 | [La validation = un run e2e from-scratch (pas le lint)](0034-validation-e2e-from-scratch.md)                                                      | Accepted           |
| 0035 | [Stratégie de bancs : fidélité vs vitesse](0035-strategie-bancs-fidelite-vitesse.md)                                                              | Accepted           |
| 0036 | [Backing S3 par topologie : SeaweedFS (léger) / RGW (prod)](0036-backing-s3-unique-rgw.md)                                                        | Accepted           |
| 0037 | [Stratégie de merge : merge commit (préserver les références)](0037-strategie-merge-commit.md)                                                    | Accepted           |
| 0038 | [Lima seul banc local ; provisioning n'est plus un axe](0038-lima-seul-banc-local.md)                                                             | Accepted           |
| 0039 | [Nomenclature des axes du catalogue (codes par valeur)](0039-nomenclature-axes-catalogue.md)                                                      | Accepted           |
| 0040 | [Stratégie terrains × topologies (quel terrain monte quoi)](0040-terrains-x-topologies.md)                                                        | Accepted           |
| 0041 | [Gouvernance & complétude DataOps (dbt, Airflow, catalogue) — cadrage](0041-gouvernance-completude-dataops.md)                                    | Accepted           |
| 0042 | [Fraîcheur des preuves de banc (garde-fou CI)](0042-fraicheur-preuves-banc.md)                                                                    | Accepted           |
| 0043 | [Contrat d'interface cluster → atlas (endpoints, SC, secrets)](0043-contrat-interface-cluster-atlas.md)                                           | Accepted           |
| 0044 | [Topologie du banc atlas (socle consommé, Gitea intra-banc)](0044-topologie-deploiement-banc-atlas.md)                                            | Accepted           |
| 0045 | [Chemins d'installation du banc : couches, dépendances, tests associés](0045-chemins-installation-banc-couches.md)                                | Accepted           |
| 0046 | [Corriger le code d'installation, pas l'état du cluster](0046-corriger-le-code-pas-l-etat.md)                                                     | Accepted           |
| 0047 | [Topologie `ha-3cp` : CP dédié, VIP kube-vip, etcd 2/3](0047-topologie-ha-3cp-control-plane-dedie.md)                                             | Accepted           |
| 0048 | [Accès local développeur (URLs cliquables + secrets + `.env`)](0048-acces-local-developpeur.md)                                                   | Accepted           |
| 0049 | [Doctrine du choix d'outil par action (pondérée)](0049-doctrine-choix-outil-par-action.md)                                                        | Accepted           |
| 0050 | [Modèle de reprise / transactionnalité d'un rôle Ansible](0050-modele-reprise-role-ansible.md)                                                    | Accepted           |
| 0051 | [Options natives Ansible (idempotence, check_mode, server-side, handlers)](0051-options-natives-ansible.md)                                       | Accepted           |
| 0052 | [Reproductibilité des résultats (principe-chapeau)](0052-reproductibilite-des-resultats.md)                                                       | Accepted           |
| 0053 | [Isolation multi-cible : banc Lima et prod sur le même poste](0053-isolation-multi-cible-banc-prod.md)                                            | Accepted           |
| 0054 | [Rollback par phase sur le banc (désinstallation ciblée, jetable)](0054-rollback-par-phase-banc.md)                                               | Accepted           |
| 0055 | [`ha-3cp` hyperconvergé : 3 control planes sur 4 nœuds, promotion in-place](0055-ha-3cp-hyperconverge-promotion-in-place.md)                      | Superseded by 0097 |
| 0056 | [Modèle déclaratif unifié des topologies (un fichier décrit, Ansible converge)](0056-modele-declaratif-topologies.md)                             | Accepted           |
| 0057 | [Gouvernance documentaire : un ADR décide, un plan met en œuvre, une issue exécute](0057-gouvernance-documentaire-adr-plan-issue.md)              | Accepted           |
| 0058 | [Doctrine de l'audit : une grille permanente, des passages datés](0058-doctrine-audit-grille-passages.md)                                         | Accepted           |
| 0059 | [Diátaxis : typologie des quatre modes de documentation + câblage inline](0059-diataxis-typologie-documentation.md)                               | Accepted           |
| 0060 | [Audit régulier du respect des conventions de gouvernance](0060-audit-conventions-gouvernance.md)                                                 | Accepted           |
| 0061 | [Posture d'adoption des bonnes pratiques (principe-chapeau)](0061-posture-adoption-bonnes-pratiques.md)                                           | Accepted           |
| 0062 | [Cultures d'ingénierie revendiquées (principe-chapeau)](0062-cultures-ingenierie.md)                                                              | Accepted           |
| 0063 | [`ansible-runner` pour la boucle « suggère → lance » (P5)](0063-ansible-runner-boucle-p5.md)                                                      | Accepted           |
| 0064 | [Longhorn comme option de stockage du catalogue (3ᵉ profil)](0064-longhorn-option-stockage-catalogue.md)                                          | Proposed           |
| 0065 | [Variables d'environnement : intention vs état détectable](0065-variables-env-intention-vs-etat.md)                                               | Accepted           |
| 0066 | [Rollback atomique : composants + graphe de dépendances unique](0066-rollback-atomique-graphe-composants.md)                                      | Accepted           |
| 0067 | [Workflows multi-agents consignés : 4ᵉ trace empirique](0067-workflows-consignes-4e-trace-empirique.md)                                           | Superseded by 0078 |
| 0068 | [Profil `metrics` : palier fin entre `base` et `store`](0068-profil-metrics-palier-fin.md)                                                        | Accepted           |
| 0069 | [`topology.layers` : déclaration explicite des couches (DAG, grain phase)](0069-topology-layers-dag-grain-phase.md)                               | Accepted           |
| 0070 | [Renommer `test/` en `bench/` ; garder `bootstrap/` à plat](0070-renommer-test-en-bench-bootstrap-plat.md)                                        | Accepted           |
| 0071 | [Exposition `gateway` en hostNetwork (80/443 sur l'IP du nœud)](0071-exposition-gateway-hostnetwork.md)                                           | Superseded         |
| 0072 | [`cluster scale` : ajuster les replicas au nombre de nœuds](0072-cluster-scale-replicas-noeuds.md)                                                | Accepted           |
| 0073 | [Hubble UI : activer l'observabilité réseau (opt-in)](0073-hubble-ui-observabilite-reseau.md)                                                     | Proposed           |
| 0074 | [`cluster discover` : reconstruire un `topology.yaml` depuis un cluster réel](0074-cluster-discover-reconstruire-topologie.md)                    | Accepted           |
| 0075 | [Kyverno CLI en CI : valider nos invariants de manifeste en statique](0075-kyverno-cli-statique-ci.md)                                            | Proposed           |
| 0076 | [`cluster refresh` : matérialiser une évolution voulue du réel dans la déclaration](0076-cluster-refresh-reel-vers-declaration.md)                | Accepted           |
| 0077 | [`cluster next` : menu des couches montables (dépendances réelles vs convention)](0077-cluster-next-menu-couches-montables.md)                    | Accepted           |
| 0078 | [Passages d'audit : une seule famille, la méthode est une propriété](0078-passages-audit-famille-unique.md)                                       | Accepted           |
| 0079 | [Découverte de l'appartenance réelle : socle commun `health` + `remove`](0079-rollback-par-decouverte-appartenance.md)                            | Accepted           |
| 0080 | [Notations externes & badges README : doctrine d'affichage](0080-notations-et-badges-readme.md)                                                   | Accepted           |
| 0081 | [Socle d'exécution node-side : une brique `node_exec`, deux usages (`discover`, `remove`)](0081-socle-execution-node-side.md)                     | Accepted           |
| 0082 | [Suivi de modèles via MLflow](0082-suivi-modeles-mlflow.md)                                                                                       | Proposed           |
| 0083 | [`layers` source unique de l'ordre : presets en alias, plus de chemins nommés par défaut](0083-layers-source-unique-de-l-ordre.md)                | Accepted           |
| 0084 | [Sondes de lecture gatées par `target_kind` (isolation banc/prod, suite de 0053)](0084-sondes-de-lecture-gatees-par-target-kind.md)               | Proposed           |
| 0085 | [Preuves applicatives sur local-path par défaut ; Ceph validé sur installation seule](0085-preuves-applicatives-local-path.md)                    | Proposed           |
| 0086 | [Code-location jouet du socle : pipeline Dagster minimal branché en permanence](0086-code-location-jouet-du-socle.md)                             | Accepted           |
| 0087 | [Property-based testing des fonctions pures de `nestor` (Hypothesis)](0087-property-based-testing-nestor.md)                                      | Accepted           |
| 0088 | [Signer les releases : tarball source + cosign keyless + provenance SLSA](0088-signature-releases-cosign-slsa.md)                                 | Accepted           |
| 0089 | [Migration de la documentation : VitePress → Astro Starlight](0089-migration-doc-vitepress-astro-starlight.md)                                    | Accepted           |
| 0090 | [`nestor` lit l'état réel d'un cluster prod (état = K8s, pas VMs)](0090-nestor-pilote-la-prod.md)                                                 | Accepted           |
| 0091 | [Portail d'accès aux UI de la plateforme](0091-portail-acces-ui.md)                                                                               | Accepted           |
| 0092 | [Exposition des UI par `hostPort`/`NodePort` L4 (zéro DNS)](0092-exposition-hostport-l4.md)                                                       | Accepted           |
| 0093 | [Cache partagé des flux atlas servi par CloudNativePG (pas de Redis)](0093-cache-flux-cnpg.md)                                                    | Accepted           |
| 0094 | [Frontière de déploiement applicatif : qui orchestre, qui fournit (cluster ↔ atlas)](0094-frontiere-deploiement-applicatif.md)                    | Proposed           |
| 0095 | [Build applicatif événementiel in-cluster : fabrique d'images et déploiement GitOps zéro-touch](0095-build-applicatif-evenementiel-in-cluster.md) | Accepted           |
| 0096 | [Graphe de topologie Python figé, vérifié contre Ansible](0096-graphe-topologie-python-verifie-ansible.md)                                        | Accepted           |
| 0097 | [Moteur de chemin Python ; bash réduit aux artefacts node-side](0097-moteur-chemin-python-bash-artefacts.md)                                      | Accepted           |
| 0098 | [Source unique d'inventaire : `nestor` dérive l'inventaire, `hosts.yaml` supprimé](0098-source-unique-inventaire-nestor-derive.md)                | Proposed           |
| 0099 | [Les axes du modèle de topologie : terrain, criticité, exposition, archi](0099-axes-du-modele-topologie.md)                                       | Proposed           |
| 0100 | [Périmètre OS & architecture : poste Unix, nœuds Linux, Windows → WSL](0100-perimetre-os-poste-et-noeuds.md)                                      | Accepted           |
| 0101 | [Migration de la zone grise bash → Python (`bench/lima/` confort)](0101-migration-zone-grise-bash-python.md)                                      | Proposed           |
