# 0045 — Chemins d'installation du banc : couches, dépendances, tests associés

## Contexte

Le harnais de banc [`test/lima/run-phases.sh`](../../test/lima/run-phases.sh)
expose une douzaine de phases (`up`, `bootstrap`, `storage-simple`, `ceph`,
`sc`, `datalake`, `dataops`, `gitops`, `monitoring`…) et un agrégat `all`. Au
fil des ajouts (DataOps #173, métrologie #219, socle GitOps #230), `all` a pris
un rôle **ambigu** : il sert à la fois de **smoke-test rapide du socle**
(`up → bootstrap → storage-simple`) et de point d'entrée vers un **banc
utilisable**, sans que les **chemins** ni l'**ordre des couches** soient
explicitement décidés.

Trois constats motivent une clarification :

1. **L'ordre entre briques applicatives n'est pas trivial.** `monitoring`,
   `gitops`, `dataops` sont **sœurs** (aucune ne dépend d'une autre) — l'ordre
   entre elles est un **choix**, pas une contrainte. Or l'observabilité
   (Prometheus/Loki) ne capte le démarrage des autres briques que si elle est
   **en place avant elles**.
2. **`monitoring` est autonome mais piégeux.** Il déploie lui-même son backing
   S3 (SeaweedFS en mode léger, `when: loki_s3_backing == seaweedfs`) ; sa seule
   dépendance est un cluster Ready + une StorageClass. Mais lancé sans propager
   le profil, il choisit le mauvais backing (drift L44).
3. **Le branchement de stockage est le vrai point de divergence** (mode léger
   `local-path` / mode Ceph), et tout l'applicatif en dépend (StorageClass +
   backing S3).

Sans décision, l'ordre des phases est gravé au coup par coup dans un script, et
`all` veut dire deux choses à la fois.

## Décision

**Modèle en couches explicite, observabilité posée tôt, et chemins
d'installation nommés.**

### 1. Couches et dépendances (l'ordre vient des dépendances, pas de l'habitude)

```text
socle           : up → bootstrap → platform-prereqs
  └─ stockage    : [léger] storage-simple        | [ceph] ceph → sc → datalake
       └─ backing S3 : [léger] SeaweedFS (rôle conditionnel)  | [ceph] RGW (déjà via datalake)
            └─ applicatif (briques SŒURS, dépendent du stockage/backing, pas l'une de l'autre) :
                 monitoring   (cluster + SC + backing S3 pour Loki)
                 gitops       (cluster + SC ; PVC Gitea)
                 dataops      (cluster + SC + backing S3 pour Barman)
```

`monitoring`, `gitops`, `dataops` ne dépendent que des couches **stockage** et
**backing S3** (cluster Ready + StorageClass `default` + un endpoint S3 pour
celles qui font du S3) — **jamais l'une de l'autre**. L'ordre entre elles est
donc libre, et se décide par un critère : **l'observabilité d'abord**.

**SeaweedFS est découplé du monitoring.** Le backing S3 du profil léger est une
**dépendance partagée** (Loki _et_ Barman/CNPG l'utilisent), pas un sous-produit
de l'observabilité. Il est fourni par le rôle conditionnel `platform-seaweedfs`,
appelé par les couches qui en ont besoin **`when` le backing vaut `seaweedfs`**
(profil léger) — et **jamais en mode Ceph**, où le **RGW** (posé par `datalake`)
joue ce rôle. Conséquence : sur le profil Ceph, SeaweedFS n'est pas installé du
tout ; sur le profil léger, il l'est une fois, en amont des consommateurs. (Pas
de phase dédiée : c'est un rôle invoqué sous condition, pour ne pas dupliquer le
backing.)

### 2. Observabilité précoce

`monitoring` est posé **juste après la couche stockage**, **avant** `gitops` et
`dataops` : Prometheus/Loki captent alors les métriques et logs du démarrage des
autres briques (et du futur applicatif `atlas` réconcilié par Argo CD) dès le
premier instant, pas après coup.

### 3. Chemins d'installation nommés (lève l'ambiguïté de `all`)

- **`socle`** — `up → bootstrap → storage-simple` : smoke-test rapide du socle
  (le rôle « rapide » historique de `all`, inchangé).
- **`atlas`** (mode léger, ADR 0044) — `socle → monitoring → gitops → dataops`.
  La phase Ansible **`dataops`** monte **toute l'infrastructure DataOps**
  (CNPG + orchestrateurs Dagster/Marquez, **livrés vides**,
  [ADR 0026](0026-orchestration-dagster.md)). **Argo CD ne déploie PAS cette
  infra** : il déploie uniquement les **workflows implémentés par `atlas`**
  (code-locations, assets, jobs) depuis Gitea (scénario 27, #231).
- **`cluster`** (mode Ceph, preuve stockage réel) —
  `up → bootstrap → ceph → sc → datalake → monitoring → dataops` : même phase
  Ansible `dataops`, sur stockage Ceph ; ici sans GitOps (pas d'Argo CD dans ce
  chemin).

> **Frontière `dataops` Ansible vs Argo CD (ADR 0022/0026).** Ansible
> (`dataops`) pose **l'infrastructure DataOps** : la base CNPG et les
> orchestrateurs Dagster/ Marquez **sans workflow**. Argo CD **ne touche pas à
> cette infra** ; il déploie seulement les **workflows d'`atlas`**
> (code-locations, assets, jobs), poussés dans Gitea. Ansible monte donc la
> _plateforme_, Argo CD y injecte les _workflows métier_ — aucune ressource
> n'est gérée par les deux.

`all` est conservé pour compatibilité mais documenté comme **alias du chemin
selon `WITH_CEPH`** ; les noms ci-dessus sont la référence.

### 4. Chaque couche porte ses tests (gate + assertion + scénario)

Un chemin n'est pas qu'une séquence de phases : **chaque couche déclare ce qui
prouve qu'elle a réussi**. Trois niveaux complémentaires, recensés ensemble dans
le [plan de tests](../architecture/plan-de-tests.md) (couverture par couche +
lacunes à combler) :

- **Unitaire** — assertion pure (logique de décision isolée, hors cluster,
  `test/unit/*.bats`, ADR 0017).
- **Intégration** — **gate de phase** (`run-phases.sh`) : vérification bloquante
  en fin de phase (exit ≠ 0 sinon), sur cluster réel.
- **Scénario** — comportement de bout en bout (`test/scenarios/NN-*.sh`) :
  résilience, sécurité, observabilité, **et la chaîne GitOps→DataOps** (sc. 27).

Synthèse par couche (le détail des 3 niveaux est dans le plan de tests) :

| Couche / phase   | Gate de phase (preuve sur banc)                                                                      | Assertion (test unitaire) |
| ---------------- | ---------------------------------------------------------------------------------------------------- | ------------------------- |
| `up`             | disques attendus présents (`vdb..vde` si Ceph)                                                       | —                         |
| `bootstrap`      | N nœuds **Ready** (Cilium up)                                                                        | `state-classify.bats`     |
| `storage-simple` | provisioner Ready + **PVC `local-path` Bound** (`gate_test_pvc`)                                     | —                         |
| `ceph`           | operator Ready + **`HEALTH_OK`**                                                                     | —                         |
| `sc`             | **PVC Bound** sur la SC Ceph par défaut                                                              | —                         |
| `datalake`       | **RGW Ready** (cible S3 Barman)                                                                      | —                         |
| `monitoring`     | Prometheus + Grafana + Loki (S3/backing) **Ready**                                                   | `metrology.bats`          |
| `gitops`         | `deploy/gitea` + `deploy/argocd-server` **Ready** (rollout)                                          | — (e2e à venir #231)      |
| `dataops`        | CNPG sain, Dagster/Marquez Ready, **lineage d'un run réel ingéré** (`dataops_chain_emit_and_verify`) | `dataops-assert.bats`     |

Règle : **toute nouvelle couche ajoute son gate** (et une assertion pure si la
décision est non triviale) ; un chemin n'est « validé » que si **tous les gates
de ses couches passent**, et le run est **consigné** (ADR 0034/0042). Les
chemins diffèrent donc aussi par leur **batterie de preuves** :

- `socle` : gates `up` → `bootstrap` → `storage-simple`.
- `atlas` : ceux de `socle` + `monitoring` + `gitops` + `dataops` (infra DataOps
  vide), **scellés par le scénario 27** (push Gitea → Argo CD `Synced/Healthy` →
  run Dagster + lineage Marquez) — c'est lui qui prouve que les _workflows
  atlas_ arrivent bien _par un push_ sur l'infra DataOps montée. Implémentation
  #231.
- `cluster` : `up` → `bootstrap` → `ceph` → `sc` → `datalake` → `monitoring` →
  `dataops` (jusqu'au lineage réel), + les scénarios 01–26.

**Scénario 27 — chaîne GitOps→DataOps (le test qui scelle le chemin `atlas`).**
Un **push sur Gitea** doit provoquer un **déploiement par Argo CD** qui **lance
toute la chaîne DataOps**. Étapes (chacune un gate) : (1) push d'un manifeste
`Application` + code-location atlas dans Gitea ; (2) le **webhook** déclenche la
réconciliation (pas le polling) ; (3) l'`Application` atteint `Synced/Healthy` ;
(4) la chaîne tourne : run Dagster réussi + **lineage ingéré par Marquez**. Spec
détaillée : [plan de tests](../architecture/plan-de-tests.md) ; implémentation
[#231](https://github.com/univ-lehavre/cluster/issues/231).

### 5. Le profil de stockage se propage

Toute phase applicative reçoit explicitement StorageClass + backing S3 du profil
courant (déjà fait dans le harnais via `-e …`). Le drift L44 (monitoring sans
profil) est un invariant à ne pas régresser.

## Statut

Accepted (2026-06-09).

## Conséquences

- **Ordre justifié, pas coutumier** : l'observabilité précède ce qu'elle observe
  ; les briques sœurs sont reconnues comme telles (réordonnables sans casse).
- **`all` désambiguïsé** : « smoke rapide » (`socle`) vs « banc utilisable »
  (`atlas`/`cluster`) ne sont plus confondus.
- **Frontière ADR 0022/0044 préservée** : `dataops` par Ansible **uniquement**
  dans le chemin `cluster` ; sur `atlas`, la chaîne vient de GitOps (#231) — pas
  de double déploiement.
- **Prix à payer** : le chemin `atlas` est plus lourd que l'ancien `all` rapide
  (monitoring = Prometheus + Loki + SeaweedFS, quelques minutes). D'où la
  distinction `socle` (rapide) vs `atlas` (complet), pour ne pas alourdir le
  smoke.
- **À faire (suite)** : implémenter les cibles nommées dans
  [`test/lima/run-phases.sh`](../../test/lima/run-phases.sh) (insérer
  `monitoring` avant `gitops` dans le chemin léger ; cibles `socle`/`atlas`/
  `cluster`), mettre à jour la doc du harnais, et consigner un run de chaque
  chemin (ADR 0034/0042). Hors périmètre de #230 (qui livre la brique GitOps).
