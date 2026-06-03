# Spike — banc léger applicatif (kind HA + local-path + SeaweedFS S3)

> **Spike jetable.** But : disposer d'un banc d'essai **léger et rapide** pour
> la couche **plateforme/applicative** (Argo CD, Prometheus, Grafana, Loki,
> Dagster, Great Expectations, Mailpit…) **sans le poids ni la fragilité de
> Vagrant/Ceph**.

## Pourquoi

Le banc lourd [`test/multi-node`](../../multi-node/) (Vagrant + VirtualBox +
Ceph) est nécessaire pour valider le **stockage bloc/objet réel** (Rook/Ceph,
disques bruts), mais il est lourd (~15 GiB RAM, ~15 min) et **fragile** : la
mise en veille de l'hôte arrête les VMs et le démon Docker en plein run.

Beaucoup de briques **n'ont pas besoin de Ceph**. Ce banc léger les sépare :

| Monde                                | Banc             | Stockage                  |
| ------------------------------------ | ---------------- | ------------------------- |
| Applicatif / plateforme (hors Ceph)  | **léger (kind)** | local-path + SeaweedFS S3 |
| Stockage bloc/objet réel (Ceph/Rook) | lourd (Vagrant)  | disques bruts             |

Conséquence de conception : les addons gagnent à avoir un **stockage
paramétrable** (StorageClass + backend S3) pour être validables sur les **deux**
bancs — `rook-ceph-block-replicated` + RGW Ceph en prod, `standard`
(local-path) + SeaweedFS sur le banc léger.

## Topologie

- **kind HA** : 3 nœuds control-plane (etcd quorum 3) + 1 worker.
- **Volumes** : `local-path-provisioner` (inclus dans kind, StorageClass
  `standard` par défaut) — zéro install.
- **Objectstore S3** : **SeaweedFS** (mode server tout-en-un, S3 sur `:8333`),
  image épinglée par digest d'index multi-arch (ADR 0006).
- CNI/kube-proxy : kindnet par défaut (ce banc cible l'applicatif, pas le réseau
  — le tout-Cilium est validé ailleurs :
  [`clustermesh-latency`](../clustermesh-latency/)).

## Prérequis

`docker` (démon lancé), `kind` (v0.24.0), `kubectl` (v1.34.x).

## Utilisation

```bash
./up.sh      # crée le cluster kind HA, vérifie local-path, déploie SeaweedFS
./probe.sh   # vérifie HA (3 CP), PVC local-path, et S3 (bucket + put/get)
./down.sh    # détruit le cluster (jetable)
```

Accès S3 depuis un pod : endpoint `http://seaweedfs.s3.svc.cluster.local:8333`,
access key `seaweedadmin` / secret `seaweedadmin-secret` (identifiants de
**test**, génériques — banc jetable, jamais de vraies clés).

## Résultats observés (2026-06-03)

Banc monté et validé **du premier coup**, en ~90 s (vs ~15 min pour Vagrant) :

- ✅ cluster kind HA créé : **3 control-plane (etcd quorum 3) + 1 worker**, tous
  Ready ;
- ✅ StorageClass `standard` (local-path) présente, **PVC Bound** ;
- ✅ **SeaweedFS S3** déployé et opérationnel : bucket créé, put/get vérifiés
  via aws-cli.

Découplage d'avec Vagrant réussi : aucun disque brut, ~quelques GiB RAM,
résistant à la veille de l'hôte (kind redémarre ses conteneurs au réveil).

## Suite

Valider la couche applicative dessus — à commencer par le **monitoring (étape
1.5, ADR 0016)** : Loki avec chunks sur SeaweedFS S3, Prometheus/Grafana sur
local-path, alertes routées vers Mailpit. Si concluant → industrialiser ce banc
en profil de catalogue.
