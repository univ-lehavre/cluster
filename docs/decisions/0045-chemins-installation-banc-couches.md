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

### 3. Chemins d'installation nommés (remplacent l'agrégat `all`)

Quatre chemins nommés, chacun avec une **intention de preuve distincte** — aucun
n'est un fourre-tout :

- **`socle`** — `up → bootstrap → storage-simple` : smoke-test rapide du socle
  (le rôle « rapide » historique de `all`, inchangé).
- **`atlas`** (mode léger, ADR 0044) — `socle → monitoring → gitops → dataops`.
  La phase Ansible **`dataops`** monte **toute l'infrastructure DataOps**
  (CNPG + orchestrateurs Dagster/Marquez, **livrés vides**,
  [ADR 0026](0026-orchestration-dagster.md)). **Argo CD ne déploie PAS cette
  infra** : il déploie uniquement les **workflows implémentés par `atlas`**
  (code-locations, assets, jobs) depuis Gitea (scénario 27, #231).
- **`storage-real`** (mode Ceph, **preuve du stockage réel**) —
  `up → bootstrap → ceph → sc → datalake`, puis deux épreuves ciblées du
  stockage Ceph : (1) **montage WordPress** — le PVC bloc `ReadWriteOnce` sur la
  StorageClass Ceph (`rook-ceph-block-replicated`) de
  [`storage/ceph/wordpress/`](../../storage/ceph/wordpress/) est **Bound** et le
  Pod **Ready** ; (2) **smoke-test S3 sur le RGW** — PUT/GET/DELETE réel via
  [`scénario 06`](../../test/scenarios/06-object-store-smoke.sh)
  ([`smoke-test.sh`](../../storage/ceph/storageClass/datalake/smoke-test.sh)).
  **Ni `monitoring` ni `dataops`** dans ce chemin : il prouve le **stockage**
  (bloc + objet), pas la chaîne applicative. C'est aussi le banc Ceph monté qui
  porte les scénarios de résilience/sécurité/chaos (§4).
- **`cluster-dataops`** (mode Ceph, chaîne DataOps sur stockage réel) —
  `up → bootstrap → ceph → sc → datalake → monitoring → dataops` : la même
  chaîne que `atlas` mais sur Ceph et sans GitOps (pas d'Argo CD). Confirme que
  la chaîne DataOps (déjà prouvée en léger par `atlas`) tient sur le stockage
  réel.

> **Frontière `dataops` Ansible vs Argo CD (ADR 0022/0026).** Ansible
> (`dataops`) pose **l'infrastructure DataOps** : la base CNPG et les
> orchestrateurs Dagster/ Marquez **sans workflow**. Argo CD **ne touche pas à
> cette infra** ; il déploie seulement les **workflows d'`atlas`**
> (code-locations, assets, jobs), poussés dans Gitea. Ansible monte donc la
> _plateforme_, Argo CD y injecte les _workflows métier_ — aucune ressource
> n'est gérée par les deux.

L'ancien agrégat **`all` est supprimé** : son double rôle (smoke rapide / banc
utilisable) était la source d'ambiguïté que cet ADR lève. Les quatre noms
ci-dessus sont la **seule** référence ; il n'y a plus d'alias.

#### Deux axes orthogonaux : stockage × durcissement (#240)

Un chemin ne modélise qu'un seul axe — le **stockage** (`local-path` léger /
Ceph réel). Le **durcissement hôte** est un **second axe, orthogonal** : il
s'applique (ou non) à _n'importe quel_ chemin, exactement comme le profil de
stockage. On le pilote par un flag d'environnement **`WITH_HARDENING=1`** (même
modèle que `WITH_CEPH`), qui insère la phase `hardening` juste **après le
socle** (l'hôte est joignable) : elle applique
[`bootstrap/security/secure.yml`](../../bootstrap/security/secure.yml)
(durcissement opt-in par tags, ADR 0025) avec un jeu de tags **adapté au banc**
— `audit,detection` par défaut (auditd + fail2ban), surchargeable par
`HARDENING_TAGS`. On **exclut** délibérément `os` (full-upgrade + reboot) et
`network` (UFW, coupe le réseau K8s) : destructifs pour un banc éphémère.

Conséquences :

- **Combinatoire, pas de nouveaux chemins** : `atlas`, `storage-real`,
  `cluster-dataops` × {durci, non durci}. Le run consigne la variante (suffixe
  `+hardening` sur `TARGET`) pour que la preuve distingue les deux.
- **Rend jouables** les scénarios qui exigent un hôte durci — notamment **16**
  (fail2ban, qui _skippe_ aujourd'hui faute de `detection`) et la famille 10–15
  (durcissement). Sans `WITH_HARDENING`, ces scénarios restent en skip assumé.
- Le durcissement ne **change pas** l'ordre des couches ni les gates de stockage
  : c'est une surcouche idempotente, d'où son traitement comme axe séparé.
- **Variables d'env du rôle `settings`** : `secure.yml` charge toujours le rôle
  `settings` (tag `always`), qui _assert_ cinq variables d'environnement
  (`MAIL_ROOT_REDIRECT`, `HOST_USER`, `PASSWORD_EXPIRATION`, `PUBLIC_SSH_KEY`,
  `MAIL_SMARTHOST`). La phase `hardening` du harnais source d'abord un éventuel
  `bootstrap/security/.env` (surcharge locale gitignorée) puis fournit des
  **défauts d'exemple génériques** (ADR 0023) — `audit,detection` ne les
  consomme pas, mais l'assert les exige.

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
| `datalake`       | **RGW Ready** (cible S3 Barman) + **smoke S3 PUT/GET/DELETE** (sc. 06)                               | —                         |
| WordPress (Ceph) | PVC bloc **RWO Bound** sur la SC Ceph + **Pod Ready** (`storage/ceph/wordpress/`)                    | —                         |
| `monitoring`     | Prometheus + Grafana + Loki (S3/backing) **Ready**                                                   | `metrology.bats`          |
| `gitops`         | `deploy/gitea` + `deploy/argocd-server` **Ready** (rollout)                                          | — (e2e à venir #231)      |
| `dataops`        | CNPG sain, Dagster/Marquez Ready, **lineage d'un run réel ingéré** (`dataops_chain_emit_and_verify`) | `dataops-assert.bats`     |

Règle : **toute nouvelle couche ajoute son gate** (et une assertion pure si la
décision est non triviale) ; un chemin n'est « validé » que si **tous les gates
de ses couches passent**, et le run est **consigné** (ADR 0034/0042). Les
chemins diffèrent donc aussi par leur **batterie de preuves** — gates **et**
scénarios scellants :

- `socle` : gates `up` → `bootstrap` → `storage-simple`. Aucun scénario propre.
- `atlas` : ceux de `socle` + `monitoring` + `gitops` + `dataops` (infra DataOps
  vide), **scellés par le scénario 27** (push Gitea → Argo CD `Synced/Healthy` →
  run Dagster + lineage Marquez) — c'est lui qui prouve que les _workflows
  atlas_ arrivent bien _par un push_ sur l'infra DataOps montée. Implémentation
  #231.
- `storage-real` : `up` → `bootstrap` → `ceph` → `sc` → `datalake`, **scellé par
  le scénario 06** (smoke S3 PUT/GET/DELETE sur le RGW) + le **montage
  WordPress** (PVC bloc RWO Bound + Pod Ready). C'est en outre le **banc Ceph
  monté** qui porte les **scénarios 01–05, 07–22** (résilience, durcissement,
  sécurité active, chaos — tous indépendants d'une chaîne applicative). Ne joue
  **ni** `monitoring` **ni** `dataops`.
- `cluster-dataops` : `up` → `bootstrap` → `ceph` → `sc` → `datalake` →
  `monitoring` → `dataops` (jusqu'au lineage réel), **scellé par les scénarios
  23–26** (intégration DataOps + observabilité). Confirme sur stockage réel la
  chaîne déjà prouvée en léger par `atlas`.

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

### 6. Matrice de couverture : chemins obligatoires / optionnels et cadence

Nommer les chemins (§3) ne dit pas **lesquels doivent rester prouvés**, ni **à
quel rythme**. Sans cette politique, un run `atlas` frais masque un chemin
`storage-real` périmé : le garde-fou de fraîcheur
([ADR 0042](0042-fraicheur-preuves-banc.md)), qui lit la date du **dernier run
toutes topologies confondues**, reste vert alors que la preuve du stockage réel
a vieilli. On distingue donc, par chemin, un **statut** (obligatoire /
optionnel), une **cadence cible** et les **scénarios qu'il scelle** :

| Chemin            | Statut          | Cadence cible (fraîcheur) | Scénarios scellés (§4)         | Justification                                                                                                                                                                                   |
| ----------------- | --------------- | ------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `socle`           | implicite       | — (inclus partout)        | aucun                          | Sous-ensemble de tout autre chemin : jamais joué seul comme preuve, sa fraîcheur découle des chemins qui le contiennent.                                                                        |
| `atlas`           | **obligatoire** | **7 j**                   | **27** (GitOps → DataOps)      | Chemin de référence du banc atlas (ADR 0044) ; le plus exercé, le moins coûteux (~25 min, local-path). C'est lui que le seuil garde frais.                                                      |
| `storage-real`    | **obligatoire** | **30 j**                  | **06** + WordPress + **01–22** | Seule preuve du stockage réel (bloc RWO + objet S3/RGW) **et** banc Ceph des scénarios résilience/sécu/chaos. Coûteux (Ceph + 4 disques, ~45 min) → cadence plus lâche, mais **non optionnel**. |
| `cluster-dataops` | optionnel       | 90 j                      | **23–26** (DataOps + observ.)  | DataOps e2e est déjà prouvé en léger par `atlas` (7 j) ; sur Ceph c'est une confirmation coûteuse → cadence très lâche. Disponible, joué à la demande.                                          |

Conséquences sur le garde-fou (ADR 0042) : le seuil unique global devient un
**seuil par chemin**, lu depuis le champ `TARGET` de chaque entrée de
`runs-history.yaml` (le run consigne déjà sa cible). Le garde-fou alerte si le
**dernier run d'un chemin** dépasse **sa** cadence — `atlas` 7 j, `storage-real`
30 j, `cluster-dataops` 90 j — au lieu d'un unique seuil masquant l'asymétrie.
Un chemin **optionnel** garde une cadence (lâche) : « optionnel » signifie
**joué à la demande, vieillit lentement**, jamais **jamais prouvé**.

> Les cadences (7 / 30 / 90 j) sont des **variables** du garde-fou, ajustables
> comme le seuil unique de l'ADR 0042 — pas des constantes gravées.
> Implémentation du seuil par chemin : amende l'ADR 0042 (suivi côté #226 /
> garde-fou).

## Statut

Accepted (2026-06-09). **Amendé 2026-06-09** : (a) §6 matrice de couverture —
chemins obligatoires/optionnels, cadence et scénarios scellés par chemin
(conséquence : seuil de fraîcheur **par chemin** côté ADR 0042) ; (b) §3
**suppression de l'alias `all`** et **scission de l'ancien `cluster`** en
`storage-real` (preuve stockage Ceph : WordPress + smoke S3) et
`cluster-dataops` (chaîne DataOps sur Ceph) ; (c) §3 **axe orthogonal
`WITH_HARDENING`** (#240) — le durcissement hôte (`secure.yml`) devient un
second axe combinable avec tout chemin, indépendant du stockage.

## Conséquences

- **Ordre justifié, pas coutumier** : l'observabilité précède ce qu'elle observe
  ; les briques sœurs sont reconnues comme telles (réordonnables sans casse).
- **Plus d'agrégat ambigu** : `all` est supprimé ; « smoke rapide » (`socle`), «
  banc utilisable léger » (`atlas`), « preuve stockage réel » (`storage-real`)
  et « DataOps sur Ceph » (`cluster-dataops`) sont quatre intentions distinctes,
  jamais confondues.
- **`storage-real` focalisé** : prouve le **stockage** (bloc RWO via WordPress +
  objet S3 via le smoke RGW) et sert de banc Ceph aux scénarios 01–22 — il ne
  monte **pas** la chaîne DataOps, qui relève de `cluster-dataops`. Le nom
  `cluster`, trop vague, est abandonné.
- **Frontière ADR 0022/0044 préservée** : `dataops` par Ansible dans `atlas` et
  `cluster-dataops` ; sur `atlas`, les **workflows** viennent en plus de GitOps
  (#231) — pas de double déploiement de l'infra.
- **Prix à payer** : le chemin `atlas` est plus lourd que l'ancien `all` rapide
  (monitoring = Prometheus + Loki + SeaweedFS, quelques minutes). D'où la
  distinction `socle` (rapide) vs `atlas` (complet), pour ne pas alourdir le
  smoke.
- **Implémentation (#237)** : cibles nommées dans
  [`test/lima/run-phases.sh`](../../test/lima/run-phases.sh) — `socle`, `atlas`
  (`monitoring` avant `gitops`+`dataops`), `storage-real`, `cluster-dataops` ;
  `all` retiré. Reste à consigner un run from-scratch de chaque chemin (ADR
  0034/0042).
- **Politique de couverture explicite (§6)** : on sait désormais quels chemins
  doivent rester prouvés (`atlas` 7 j, `storage-real` 30 j, `cluster-dataops` 90
  j) et quels scénarios chacun scelle — la dérive « un chemin frais en masque un
  périmé » devient détectable. **Prix à payer** : le garde-fou de fraîcheur doit
  évoluer vers un **seuil par chemin** (amendement ADR 0042) ; tant qu'il lit un
  seuil global, `storage-real` peut vieillir sans alerte distincte.
