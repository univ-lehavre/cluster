# Par où commencer

Cette page est le **point d'entrée** du dépôt pour un nouvel arrivant. Elle dit
à qui ce projet s'adresse, ce qu'il faut savoir avant de plonger, et propose un
**parcours numéroté** pour ne pas se perdre.

> 🔰 Gardez le [**glossaire**](glossaire.md) ouvert à côté : tous les sigles
> (Kubernetes, etcd, OSD, PVC, CNI, erasure coding, quorum…) y sont définis en
> langage simple. Pour **comprendre** le projet avant de le faire, le
> [**manifeste**](manifeste.md) le raconte de bout en bout.

## Public visé

- **Administrateur / exploitant** d'un cluster Kubernetes de recherche
  hyperconvergé (calcul + stockage sur les mêmes machines).
- **Développeur data** qui veut _consommer_ la plateforme depuis son code (sans
  l'opérer) : commencez par [Se brancher sur la plateforme](se-brancher.md) ou,
  pour développer en local, le tutoriel [Monter le banc local](banc-local.md).
- **Contributeur** au dépôt (manifestes, playbooks, documentation).

Ce dépôt n'est **pas** une distribution clé en main, ni l'infrastructure d'un
déploiement particulier : c'est un **catalogue de topologies** réutilisables
(mono-nœud, multi-nœuds, bare-metal hyperconvergé…), **une activée** par
déploiement, en **valeurs d'exemple génériques**
([ADR 0023](decisions/0023-plateforme-exemple-generique.md)). Les valeurs
réelles (IP, disques, hostnames) vivent dans une config locale non versionnée.
Le [manifeste](manifeste.md) raconte le pourquoi de bout en bout.

## Prérequis de connaissances

Vous serez plus à l'aise avec des notions de base de :

- **Linux / SSH / Ansible** (les serveurs sont préparés par des playbooks) ;
- **Kubernetes** (pods, services, déploiements) — sinon, le glossaire suffit
  pour démarrer ;
- **stockage distribué** (la partie Ceph est la plus spécialisée) ;
- **Git / Pull Requests** (toute modification passe par une PR — cf.
  [CONTRIBUTING](../CONTRIBUTING.md)).

Pas besoin d'être expert : la documentation est conçue pour être suivie pas à
pas. Les sections avancées sont signalées.

## Parcours numéroté

1. **Se repérer.** Lire ce fichier et garder le [glossaire](glossaire.md) ouvert
   à côté. Pas besoin du _pourquoi_ de chaque décision pour démarrer : il est
   raconté dans le [manifeste](manifeste.md), à lire avant ou après, sans
   interrompre l'installation.
2. **Installer le cluster.** Suivre la séquence de référence pas à pas :
   [`bootstrap/RUNBOOK.md`](../bootstrap/RUNBOOK.md) — préparation OS,
   `kubeadm`, CNI Cilium, jonction des workers. Raccourcis :
   [`Justfile`](../Justfile) (`just` pour la liste).
3. **Déployer le stockage.**
   [`storage/ceph/RUNBOOK.md`](../storage/ceph/RUNBOOK.md) — opérateur Rook,
   `CephCluster`, StorageClasses. À faire une fois les nœuds `Ready`.
4. **Déployer les services et applications.** Registry, dashboard
   ([`platform/`](../platform/)), RStudio et exemples ([`apps/`](../apps/),
   [`storage/ceph/wordpress/`](../storage/ceph/wordpress/)).
5. **Exploiter au quotidien.** Vérifier l'état (`just state` ou
   [`bootstrap/state.sh`](../bootstrap/state.sh)), sauvegarder etcd
   ([`etcd-backup`](../bootstrap/etcd-backup.yaml) + copie hors-nœud
   [`etcd-fetch`](../bootstrap/etcd-fetch.yaml)), monter de version
   ([`k8s-upgrade`](../bootstrap/k8s-upgrade.yaml)), surveiller (`kubectl top`
   via metrics-server, SMART via smartd).

## Avant de toucher la production

- **Tout se valide d'abord sur le banc** Lima ([`bench/`](../bench/)) — voir
  [SAFEGUARDS.md](../SAFEGUARDS.md) pour les garde-fous (hooks, CI, banc).
- **Le banc se monte en couches (layers).** L'ordre des couches n'est plus une
  table figée : il est **dérivé d'un graphe atomique** de dépendances
  ([ADR 0083](decisions/0083-layers-source-unique-de-l-ordre.md)). On déclare ce
  qu'on veut via `layers:` dans la `topology.yaml` — `layers: [atlas]` = chaîne
  MLOps complète (metrics → obs → gitops → dataops → gitops-seed → mlflow). Les
  anciens chemins nommés (`atlas`, `atlas-ceph`…) restent des **alias
  rétrocompatibles** rejouables via `--target <nom>`. Détail :
  [Monter le banc local](banc-local.md).
- **L'état d'avancement** se lit dans les plans de mise en œuvre
  ([`docs/plans/`](plans/), ADR 0057) et les passages d'audit datés
  ([`docs/audit/`](audit/), ADR 0058) ; l'état **live** du cluster vient de
  `just state` (ou [`bootstrap/state.sh`](../bootstrap/state.sh)).

## Si quelque chose ne va pas

- `just state` (ou `bootstrap/state.sh`) affiche le **drift** par couche et
  propose la prochaine étape.
- Une **faille de sécurité** ? Ne pas ouvrir d'issue publique — suivre
  [SECURITY.md](../SECURITY.md).
