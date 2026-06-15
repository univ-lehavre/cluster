# 0039 — Nomenclature des axes du catalogue (codes par valeur)

## Contexte

L'[ADR 0030](0030-nomenclature-bancs-topologies.md) a doté **un** axe — la
topologie — de noms de code stables (`multi-node-3`, `multi-node-4`, `ha-3cp`,
`multisite`). Le succès de cette convention (clé de jointure entre la
[matrice](../architecture/matrice-catalogue.md) et les `RESULTS.md`, écart
`cible`/`buildé` lisible) appelle la même chose pour les **autres axes**.

Aujourd'hui une combinaison se décrit en prose (« le banc arm64 local 3-nœuds
avec Ceph et la chaîne DataOps »), ce qui est long et ambigu. Avec un code par
valeur d'axe, une combinaison devient un **tuple** non équivoque.

Le catalogue a quatre axes ([ADR 0038](0038-lima-seul-banc-local.md)) : matériel
× topologie × terrain × briques. La topologie est déjà nommée (0030) ; il reste
**matériel (architecture)**, **terrain** et **briques**.

## Décision

**Donner un code court, stable et en kebab-case à chaque valeur des axes
restants**, sur le modèle de l'ADR 0030. Une configuration se désigne par le
tuple `arch/terrain/topologie/profil-briques`.

### Architecture (axe matériel)

| Code    | Architecture   | Statut            |
| ------- | -------------- | ----------------- |
| `arm64` | ARM 64 bits    | **buildé**        |
| `x86`   | x86_64 / amd64 | cible, non buildé |

> Seule l'**architecture** est codée (dimension discriminante, à 2 valeurs). Les
> sous-dimensions matérielles (CPU, RAM, réseau, disques — cf.
> [matrice §1.1](../architecture/matrice-catalogue.md)) restent **descriptives**
> : les coder serait prématuré tant qu'on n'en teste qu'un point.

### Terrain d'exécution

| Code        | Terrain                    | Provisioner         | Statut             |
| ----------- | -------------------------- | ------------------- | ------------------ |
| `local`     | machine de dev             | Lima                | **buildé**         |
| `cloud`     | IaaS (VM cloud)            | OpenTofu (ADR 0032) | cible              |
| `baremetal` | serveurs physiques (lames) | manuel / PXE        | cible, non outillé |

### Profil de briques

Un **profil** = une combinaison cohérente et cumulative de briques (chaque
profil inclut les précédents), pas une brique isolée. Reflète les paliers réels
du banc (`run-phases.sh`).

> **Amendé par [ADR 0069](0069-topology-layers-dag-grain-phase.md)** : un profil
> est désormais un cas particulier (un **préfixe** de la chaîne) de
> `topology.layers`, qui déclare un **ensemble** de couches ordonné par le DAG
> de dépendances réelles (et non par la chaîne totale). `profile` reste un alias
> rétrocompatible.

| Code      | Contenu (cumulatif)                                           | Phase banc                                |
| --------- | ------------------------------------------------------------- | ----------------------------------------- |
| `base`    | socle : k8s + Cilium (+WireGuard)                             | `bootstrap`                               |
| `metrics` | + API ressources : metrics-server (`kubectl top`)             | `metrics-server`                          |
| `store`   | + stockage : local-path **ou** Rook-Ceph (+SC, +RGW datalake) | `storage-simple` / `ceph`+`sc`+`datalake` |
| `obs`     | + observabilité : Prometheus + Grafana + Loki                 | `monitoring`                              |
| `dataops` | + chaîne DataOps : CNPG, Dagster, Marquez                     | `dataops`                                 |

> `metrics` ([ADR 0068](0068-profil-metrics-palier-fin.md)) est le plus petit
> palier d'observabilité : metrics-server n'a aucune dépendance stockage (placé
> **avant** `store`) et `obs` en hérite (monitoring le suppose présent).
>
> `store` et `obs` portent leurs **dimensions fines** (storageClass, backing S3
> — [matrice §1.5](../architecture/matrice-catalogue.md)) : `store=ceph`
> implique `rook-ceph` + RGW, `store=local-path` implique SeaweedFS pour l'obs.
> Le tuple peut donc se préciser (`…/obs(ceph)`), mais le code de base suffit le
> plus souvent.

### Notation d'une combinaison

`arch/terrain/topologie/profil` — ex. les deux bancs validés :

- **banc léger** : `arm64/local/multi-node-3/obs` (store=local-path) ;
- **banc Ceph** : `arm64/local/multi-node-3/dataops` (store=ceph) + `obs`.

## Statut

Accepted. (Étend [ADR 0030](0030-nomenclature-bancs-topologies.md) — qui ne
nommait que la topologie — aux trois autres axes.)

## Conséquences

- **Gain** : toute combinaison du catalogue se nomme par un tuple non ambigu ;
  la matrice et les `RESULTS.md` gagnent un vocabulaire commun pour tous les
  axes, pas seulement la topologie.
- **Prix à payer** : un code de plus à tenir à jour quand un axe gagne une
  valeur (ex. un nouveau profil de briques). Léger : la table de cet ADR fait
  foi.
- **Sobriété** : on **ne code pas** les sous-dimensions matérielles (CPU/RAM/
  réseau/disques) ni brique par brique — seulement les valeurs discriminantes
  réellement utilisées, pour éviter une nomenclature spéculative.
- **Évolution** : `x86`, `cloud`, `baremetal` sont nommés d'avance (comme
  `ha-3cp`/`multisite` en 0030) pour que les issues de cadrage s'y réfèrent dès
  maintenant.
