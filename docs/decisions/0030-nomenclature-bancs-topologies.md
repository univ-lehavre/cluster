# 0030 — Nomenclature des bancs et topologies

## Contexte

Le dépôt est un catalogue de topologies
([ADR 0023](0023-plateforme-exemple-generique.md)) et porte désormais plusieurs
bancs de test locaux — Vagrant mono-VM, Vagrant multi-VM, banc Lima, spike
Cilium Cluster Mesh — **sans nomenclature**. On les désigne par leur **chemin**
(`test/multi-node/`, `test/lima/`), ce qui mélange deux choses distinctes : la
**topologie** validée (forme du cluster) et l'**outil** qui la monte (Vagrant,
Lima). Un même chemin sous-entend un outil ; or une topologie peut tourner sur
plusieurs outils (le multi-node-3 existe en Vagrant **et** en Lima). Sans noms
stables, la matrice du catalogue
([`docs/architecture/matrice-catalogue.md`](../architecture/matrice-catalogue.md))
et les RESULTS.md se réfèrent aux bancs de façon ambiguë.

## Décision

**Nommer les topologies par un nom technique stable, indépendant de l'outil.**
L'outil de provisioning (Vagrant, Lima) est un **attribut** (une colonne de la
table de référence), **pas** une partie du nom.

Schéma : `topologie[-taille]`, en kebab-case, taille = nombre de nœuds ou de
control planes quand c'est discriminant.

| Nom technique    | Topologie                                                         | Statut            |
| ---------------- | ----------------------------------------------------------------- | ----------------- |
| `multi-node-3`   | 3 nœuds : 1 control plane + 2 workers                             | buildé            |
| `multi-node-4`   | 4 nœuds : 1 control plane + 3 workers (prod bare-metal, ADR 0009) | cible (prod)      |
| `mesh-2clusters` | 2 clusters fédérés par Cilium Cluster Mesh                        | spike (jetable)   |
| `ha-3cp`         | 3 control planes (haute disponibilité)                            | cible, non buildé |
| `multisite`      | plusieurs sites, 1 cluster autonome/site                          | cible, non buildé |

Règles :

- **Le nom décrit la topologie, jamais l'outil.** `multi-node-3` tourne
  aujourd'hui sur Vagrant (`test/multi-node/`) **et** sur Lima (`test/lima/`) :
  même nom, deux lignes dans la table (colonne « Outil » différente).
- **Source de vérité de la table** : [`test/README.md`](../../test/README.md),
  enrichi d'une colonne « Nom technique ». La matrice du catalogue et les
  RESULTS.md référencent ces noms.
- **Pas de renommage de dossiers dans ce chantier.** Les chemins `test/*/`
  restent inchangés (renommer est invasif — chemins dans scripts, CI, docs — et
  fera l'objet d'une décision séparée si besoin). Le nom technique est une
  **étiquette logique**, pas le dossier.
- **Statut explicite** : `buildé` (validé sur banc, cf. RESULTS.md), `spike`
  (exploratoire/jetable), `cible` (déclaré dans le catalogue, pas encore monté).

## Statut

Accepted.

## Conséquences

- **Gain** : un vocabulaire stable et non ambigu pour parler des bancs ; la
  matrice (#171) et les RESULTS.md gagnent une clé de jointure ; l'écart entre
  topologies `cible` et `buildé` devient lisible.
- **Prix à payer** : une indirection nom ↔ dossier tant que les dossiers ne sont
  pas renommés (`multi-node-3` vit sous `test/multi-node/` ou `test/lima/`). La
  colonne « Dossier » de la table lève l'ambiguïté.
- **Évolution** : ajouter une topologie = une ligne dans la table + (si buildée)
  un run consigné. `ha-3cp` et `multisite` sont nommés d'avance pour que les
  issues de cadrage (catalogue, terrain cloud) s'y réfèrent dès maintenant.
  `ha-3cp` est désormais **défini** (3 CP dédiés + 3 workers, VIP kube-vip, etcd
  quorum 2/3) par [ADR 0047](0047-topologie-ha-3cp-control-plane-dedie.md) ;
  reste `cible` tant que le run de preuve n'est pas consigné.
- **Lien** : outillage des bancs et fidélité de version
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)) ; multi-cluster
  paramétré ([ADR 0027](0027-bootstrap-parametre-multi-cluster.md)).
