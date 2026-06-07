# 0036 — Backing S3 par topologie : SeaweedFS (banc léger) / RGW Ceph (prod)

## Contexte

Plusieurs briques ont besoin de stockage **objet S3** intra-cluster :

- **Loki** (chunks + ruler) — `platform/loki/`.
- **CloudNativePG / Barman** (sauvegardes WAL + base) —
  `platform/cloudnative-pg/`.

Leurs manifestes pointaient un endpoint **SeaweedFS**
(`seaweedfs.s3.svc.cluster.local:8333`) présenté comme « défaut banc léger »…
mais **aucun déploiement SeaweedFS n'existait** (#186, cause du drift L14). Le
dépôt fournit par ailleurs un S3 de production via le **RGW Ceph**
(`CephObjectStore datalake`).

Tentation initiale : « un seul backing, le RGW ; en banc léger, Loki en mode
**filesystem** ». **Rejeté** — le mode `filesystem` de Loki est un **chemin de
code différent** du mode `s3` de la prod : le banc léger ne validerait alors
**pas** ce qui tourne en production (contraire à
[ADR 0034](0034-validation-e2e-from-scratch.md)). Or tester le **vrai chemin S3
sans monter Ceph** est précisément ce que permet un S3 léger comme SeaweedFS
(déjà inscrit dans la matrice ADR 0006, « objectstore S3 de test », mais jamais
déployé).

## Décision

**Le backing S3 est le même _protocole_ partout (S3), avec deux
_implémentations_ selon la topologie — endpoint et creds paramétrables :**

| Topologie                 | Backing S3                                     | Pourquoi                                                  |
| ------------------------- | ---------------------------------------------- | --------------------------------------------------------- |
| Banc léger (`local-path`) | **SeaweedFS** (`platform/seaweedfs/`, ns `s3`) | S3 réel **sans Ceph** → chemin s3 testable en banc rapide |
| Prod / banc Ceph          | **RGW Ceph** (`rook-ceph-rgw-datalake`)        | S3 résilient, intégré au stockage du cluster              |

1. **Un seul _chemin de code_ : S3.** Loki et CNPG sont **toujours** en profil
   `s3` (jamais `filesystem`) — le banc léger teste donc le **même code** que la
   prod, seul l'endpoint S3 change (variable de rôle). Fin du profil filesystem
   envisagé.
2. **SeaweedFS est déployé** (`platform/seaweedfs/`) : mono-instance, PVC
   local-path, S3 gateway `:8333`, identity `seaweedadmin` — valeurs de test
   génériques (ADR 0023). Réservé au banc léger ; une topologie réelle utilise
   le RGW (pas de SeaweedFS en prod).
3. **Endpoint/creds paramétrables** par topologie : défaut versionné = RGW
   (prod) ; surcharge banc léger = SeaweedFS, via vars d'inventaire. Les creds
   viennent d'un Secret (RGW : dérivés de l'OBC ; SeaweedFS : creds de test).
4. **Conséquence bancs** ([ADR 0035](0035-strategie-bancs-fidelite-vitesse.md))
   : Loki **et** les backups CNPG deviennent **testables en banc léger** (~11
   min, sans Ceph) sur leur vrai chemin s3 — plus besoin du banc Ceph pour
   valider la logique S3.

## Statut

Accepted. (Révise un cadrage intermédiaire « tout-RGW + filesystem » : on garde
le **protocole S3 unique**, avec **deux implémentations** selon la topologie,
car seul SeaweedFS permet de tester le chemin s3 réel sans Ceph.)

## Conséquences

- **Gain** : le banc léger valide le **vrai chemin S3** (même code que prod) ;
  fin de la référence fantôme SeaweedFS (drift L14 clos en le **déployant** au
  lieu de le retirer) ; pas de profil `filesystem` divergent à maintenir.
- **Prix à payer** : un déploiement SeaweedFS à maintenir (banc léger
  uniquement) — léger (mono-instance, image pinnée ADR 0006). Deux endpoints S3
  à garder paramétrables.
- **Discipline** : SeaweedFS reste **banc-léger-only** ; aucune topologie réelle
  ne l'emploie (RGW Ceph). Un changement S3 validé en banc léger (SeaweedFS)
  doit être revalidé en banc Ceph (RGW) avant prod — même protocole, mais
  l'implémentation diffère (ADR 0034).
- **Suite** : rôle `platform-seaweedfs` (banc léger) ; `platform-loki` et
  `platform-cnpg` paramètrent leur endpoint S3 ; init-buckets ciblé sur
  l'endpoint actif (#158/#186).
