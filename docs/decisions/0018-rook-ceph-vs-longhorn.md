# 0018 — Rook-Ceph plutôt que Longhorn pour le stockage

## Contexte

L'audit ([11-logiciels-oss](../audit/11-logiciels-oss.md)) note que le choix de
**Rook-Ceph** comme couche de stockage n'est tracé par aucun ADR, alors que
c'est l'un des composants les plus lourds et structurants du cluster.
L'alternative naturelle dans l'écosystème Kubernetes est **Longhorn** (stockage
bloc distribué, plus léger).

Le cluster est **hyperconvergé** (calcul + stockage sur les 4 mêmes nœuds HPE)
et sert de **datalake universitaire** : gros volumes (≈ 264 TiB brut), besoin de
stockage **bloc** (PVC RBD) **et objet** (S3 pour les datasets), sur HDD avec
block.db NVMe.

## Décision

**Rook-Ceph est retenu.** Raisons :

- **Bloc + objet + fichier dans une seule plateforme.** Le datalake a besoin de
  **S3** (RGW) pour les datasets ET de **bloc** (RBD) pour les workloads ET
  potentiellement de **CephFS** (RWX). Longhorn ne fait que du **bloc** → il
  faudrait une 2ᵉ solution pour l'objet. Ceph unifie les trois.
- **Échelle et topologie disque.** Ceph gère nativement des dizaines d'OSDs HDD
  par nœud avec **block.db sur NVMe** (cf.
  [ADR 0008](0008-metadatadevice-nvme-spof-par-noeud.md)) et l'**erasure
  coding** (cf. [ADR 0004](0004-erasure-coding-2plus1-datalake.md)) pour le
  datalake — capacité/durabilité ajustables. Longhorn est pensé pour des volumes
  plus modestes, en réplication simple.
- **`failureDomain: host` + réplicat ×3** (cf.
  [ADR 0001](0001-replication-x3-pour-workloads-bloc.md)) collent au modèle 4
  nœuds (cf. [ADR 0009](0009-pourquoi-4-noeuds.md)).
- **Maturité** sur ce cas d'usage (stockage de recherche hyperconvergé à fort
  volume) ; Rook fournit l'operator Kubernetes.

## Statut

Accepted (2026-06-01).

## Conséquences

**Bénéfices.**

- Une seule plateforme pour bloc + objet + fichier → moins de pièces à opérer.
- Capacité et durabilité finement réglables (réplication vs EC selon le pool).

**Coûts assumés.**

- **Complexité opérationnelle** nettement supérieure à Longhorn : mon/mgr/osd/
  rgw, notions de pools, CRUSH, rééquilibrage. La courbe d'apprentissage est
  réelle (atténuée par les RUNBOOK et le glossaire).
- **Empreinte ressources** plus élevée (mons, mgr, exporters) — acceptable sur
  des nœuds à 251 GiB RAM.

## À revoir si

- Le besoin **objet (S3) disparaît** et seul le bloc reste → Longhorn
  redeviendrait un candidat sérieux (plus simple à opérer).
- L'échelle se réduit drastiquement (petit cluster, faibles volumes).
