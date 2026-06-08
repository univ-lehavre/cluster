# Par où commencer

Cette page est le **point d'entrée** du dépôt pour un nouvel arrivant. Elle dit
à qui ce projet s'adresse, ce qu'il faut savoir avant de plonger, et propose un
**parcours numéroté** pour ne pas se perdre.

> 🔰 Gardez le [**glossaire**](glossaire.md) ouvert à côté : tous les sigles
> (Kubernetes, etcd, OSD, PVC, CNI, erasure coding, quorum…) y sont définis en
> langage simple.

## Public visé

- **Administrateur / exploitant** d'un cluster Kubernetes de recherche
  hyperconvergé (calcul + stockage sur les mêmes machines).
- **Contributeur** au dépôt (manifestes, playbooks, documentation).

Ce dépôt n'est **pas** une distribution clé en main : c'est l'Infrastructure-as-
Code d'**un** cluster précis (4 serveurs HPE, Debian 13, Cilium, Rook-Ceph). Les
valeurs (IP, disques, hostnames) sont celles de ce cluster.

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

1. **Comprendre l'architecture et les choix.** Lire ce fichier, le
   [glossaire](glossaire.md), puis le [README racine](../README.md) (section «
   Structure »). Pour le _pourquoi_ de chaque décision, parcourir les
   [ADR](decisions/) (Architecture Decision Records).
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

- **Tout se valide d'abord sur le banc** Lima ([`test/`](../test/)) — voir
  [SAFEGUARDS.md](../SAFEGUARDS.md) pour les garde-fous (hooks, CI, banc).
- **L'état d'avancement** du durcissement (par rapport à l'audit) est suivi dans
  [`STATUS.md`](../STATUS.md) ; l'audit complet est dans
  [`docs/audit/`](audit/).

## Si quelque chose ne va pas

- `just state` (ou `bootstrap/state.sh`) affiche le **drift** par couche et
  propose la prochaine étape.
- Une **faille de sécurité** ? Ne pas ouvrir d'issue publique — suivre
  [SECURITY.md](../SECURITY.md).
