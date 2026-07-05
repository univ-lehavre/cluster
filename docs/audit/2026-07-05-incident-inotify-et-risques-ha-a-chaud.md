# Passage d'audit — incident dirqual1 (inotify) & risques d'un passage HA à chaud

> **Type** : passage d'audit ciblé (ADR 0058) — deux angles liés par l'incident
> : (1) la **cause racine** de l'indisponibilité de dirqual1 le 2026-07-05, (2)
> les **risques réels d'un passage HA à chaud** du control-plane (demande
> opérateur déclenchée par l'incident). Pas la grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : dirqual1 (**control-plane unique**) est devenu non-réactif
> (apiserver + sshd stallés, ping OK) → **cluster entier gelé** jusqu'au reboot
> manuel. L'incident a relancé la question « faut-il passer le control-plane en
> HA, et peut-on le faire à chaud ? ».
>
> **Méthode** : lecture des logs kernel/journald de dirqual1 (boot précédent) +
> dump `kubectl` de 247 conteneurs + investigation adversariale (workflows : 3
> volets incident/capacité, 3 lentilles de risque HA + verdict, effort high).
> Toute affirmation est ancrée sur une preuve (log, fichier, ADR).

## 1. Cause racine de l'incident — épuisement inotify (mes 1res hypothèses étaient FAUSSES)

**Honnêteté (ADR 0052/0058)** : mes deux premières hypothèses étaient erronées
et sont réfutées par les logs — je les consigne pour ne pas les reproduire.

- ❌ « emballement I/O du bootstrap de 687 GiB » — **aucune** trace d'erreur I/O
  dans la fenêtre de l'incident (13:00-13:25).
- ❌ « OOM mémoire (mlflow) » — l'OOM `mlflow` de la console était **daté du 04
  juil 19:59** (pas 13:20), en `CONSTRAINT_MEMCG` (**contenu au cgroup mlflow**,
  limite 1536Mi), et n'a **jamais menacé le nœud**. Les nœuds ont 251 GiB à ~4
  %.

**Cause réelle établie** : **épuisement des instances inotify.**

- `fs.inotify.max_user_instances = 128` — le **défaut Linux, jamais relevé**
  (grep `bootstrap/` : aucun tuning inotify). `max_user_watches = 1048576` (OK).
- `failed to create inotify fd: too many open files` : **198 occurrences**,
  première le **22 juin** → saturation **lente sur ~2 semaines**, touchant
  `buildkitd` puis `containerd`.
- Au stall (13:15+) : containerd ne peut plus créer d'inotify fd →
  `context deadline exceeded`, `ttrpc inactive stream` → il ne gère plus les
  conteneurs → **apiserver et sshd (sous ce containerd) deviennent
  non-réactifs**. Le nœud répond au ping (kernel) mais tous les services
  userspace stallent.

**Facteur aggravant, pas cause** : le CronJob `dagster-workspace-reconciler`
(ADR 0103, `*/5`, 628 exécutions/boot) crée/détruit des pods → churn qui nourrit
la consommation inotify.

**Nuance honnête (incertitude résiduelle)** : « sous-dimensionnement (128 trop
bas) » ET « fuite (un process ne libère pas ses watchers) » sont tous deux
plausibles ; la **fuite domine** (saturation progressive sur 2 semaines), mais
la mesure live post-reboot n'a pas pu **nommer le process fautif** (uptime trop
court). → relever le plafond est **nécessaire mais insuffisant sans
surveillance**.

### Prévention (P0) — codifier le tuning inotify dans le bootstrap

- **`fs.inotify.max_user_instances = 8192`** (128 → 8192) + `max_user_watches`
  figé, en **sysctl node-level** sur les **4 nœuds**, persistant aux reboots. À
  poser dans `bootstrap/roles/k8s-CRI-install/tasks/main.yaml` (à côté du tuning
  `ip_forward` existant), avec l'**assertion de vérification** analogue
  (`sysctl --values fs.inotify.max_user_instances`).
- **Instrumenter** (P1) : scrape/alerte Prometheus sur la saturation inotify
  pour **trancher fuite vs pic** et **nommer** le process coupable si ça
  remonte.
- **Réduire le churn** (P2) : espacer le CronJob reconciler `*/5` → `*/15`
  (`platform/dagster/reconciler.yaml:146`).

## 2. Requests/limits — prolongement de l'audit du 2026-07-04

Dump de **247 conteneurs** croisé avec l'usage réel :

- **164/247 (66 %) sans limite mémoire**, **152/247 sans requests.**
- **MAIS aucun nouveau risque de capacité/OOM** : les nœuds sont à ~4-5 % (251
  GiB), et les 4 corrections OOM du
  [passage 2026-07-04](2026-07-04-audit-ressources-requests-limits.md)
  (Prometheus 3Gi, Grafana 512Mi, MLflow 1536Mi, Marquez 1536Mi) sont bien
  posées — **aucun pod n'est proche de son plafond**. Top conso réelle :
  apiserver 1571Mi, cilium 1520Mi, ~40 OSD Ceph à ~1Gi (élastiques :
  `osd_memory_target` FIXE, « plus on leur donne, plus ils prennent » — **ne
  pas** relever).
- **Seul manque notable** (P1) : le **postgres applicatif** (`pg-1/2/3`, ns
  `postgres`) n'a pas de requests/limits mémoire — à poser (3 réplicas, base
  critique).
- **Ne PAS** ouvrir de chantier right-sizing générique : l'absence de limite sur
  un cluster à 4 % n'est pas urgente ; hygiène P2 sur les contrôleurs non bornés
  du plan de pilotage (argocd/cilium) qui vivent sur le CP unique.

## 3. Risques d'un passage HA à chaud — VERDICT : **attendre le rebuild**

L'incident **prouve que le control-plane unique est un SPOF réel et grave** : 1
nœud gelé = cluster entier gelé. Un CP HA aurait transformé « gel total » en «
dégradation d'un nœud, API toujours servie ». La demande HA est donc **fondée**.
Mais le **passage à chaud** (promotion in-place 1→3 CP sur le parc prod vivant)
n'est **pas un risque acceptable maintenant**.

### Faisabilité — structurellement prêt à ~70 %, mais 3 trous de code

**Prêt** : `controlPlaneEndpoint: cluster-api:6443` est un **hostname** posé dès
l'init ([ADR 0002](../decisions/0002-control-plane-unique-avec-endpoint.md)) —
_précisément_ pour ajouter des CP sans réinstaller les workers ; LV `etcd`
dédiée sur les 4 nœuds ; taint CP déjà retiré ; briques Ansible bien conçues
(`k8s-join-control-plane` avec rescue etcd). La cible est déjà décidée
([ADR 0055](../decisions/0055-ha-3cp-hyperconverge-promotion-in-place.md)) et
planifiée ([plan-ha-3cp](../plans/plan-ha-3cp-control-plane.md)).

**Trois trous bloquants pour un à-chaud propre** :

1. **L'orchestrateur HA a été RÉELLEMENT SUPPRIMÉ** du code (commit `fd04ee0` :
   355 lignes de `path.py` — `run_ha_3cp`/`promote_control_plane`, plus
   `gate_etcd`/`gate_vip`). La **gate « etcd healthy entre deux joins »**, que
   le rôle délègue explicitement au « chemin codé », **n'existe donc plus**.
   Piloter la séquence à la main = anti-pattern interdit
   ([ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md)).
2. **Le cert apiserver prod n'a PAS la VIP en certSAN** (init 1-CP,
   `control_plane_vip` vide → bloc `certSANs` conditionnel non émis). Dès qu'un
   client résout `cluster-api → VIP`, le TLS échoue (x509 sans cette IP) →
   **tous les workers perdent l'API**. L'étape « régénérer le cert avec la VIP
   avant de repointer » est **absente des rôles**.
3. **`placement.mon` absent du code actif** (`storage/ceph/cluster.yaml` :
   stanzas commentées) → le découplage etcd/mon exigé par ADR 0055 §1 n'est pas
   posé.

### Risques critiques (qui feraient PERDRE le cluster)

- **Quorum figé en fenêtre N=2** : entre le 1er et le 2e join, etcd a 2 membres,
  majorité 2/2 → la perte d'**un** membre **fige le quorum** (apiserver
  read-only) — **pire qu'à N=1**. Or l'incident du jour est **exactement** un
  gel node-level sur un CP : le subir pendant N=2 = **cluster mort**. La gate
  qui gardait cette fenêtre a été supprimée.
- **Membre etcd fantôme** sur join avorté (worker déjà `reset`, membre etcd
  enregistré mais apiserver pas sain). Le rescue le compense (member remove),
  mais le matching du membre est « à confirmer au banc » — **jamais confirmé**
  (banc 3-VM abandonné).
- **TLS cassé au repointage** (cert sans VIP, cf. trou #2).
- **`kubeadm reset` d'un worker portant 12 OSD + mon sur Ceph vivant** : pendant
  la fenêtre, `size=3 failureDomain=host` passe à **zéro marge** (perdre 1 nœud
  ôte 1 CP + 1 mon + 12 OSD, ADR 0055:173). Si le join échoue, le nœud reste
  `reset` — la **dé-promotion (retour worker) n'est pas outillée**.
- **Aucune preuve possible + rollback interdit/non-prouvé** : la HA ne se prouve
  QUE sur prod (banc 3-VM abandonné) → une promotion serait le **1er run** de ce
  chemin sur 687 GiB Ceph + Dagster vivants (viole
  [ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)/[0052](../decisions/0052-reproductibilite-des-resultats.md)).
  Le rollback est soit **interdit** (R-DROP du plan), soit non-outillé, soit
  jamais prouvé (restore etcd ramène à N=1 et **perd 1h de RPO**).

### À chaud vs rebuild — le rebuild gagne sur les 5 points qui font mal

Le rebuild from-scratch est **structurellement plus sûr** : (1) **zéro reset**
de worker (chaque nœud naît CP) ; (2) `placement.mon` **gratuit** (Ceph absent
au montage) ; (3) certSAN VIP posé **dès l'init** → le trou TLS disparaît ; (4)
jamais d'état transitoire **1-CP + VIP** (kube-vip ne bascule pas à 1 candidat →
la VIP serait aussi SPOF que cp1) ; (5) le run de preuve **coïncide** avec la
prod → reproductible (ADR 0052). Le seul avantage du à-chaud (pas de
réinstallation des workers) ne compense **aucun** de ces points. Le dépôt
lui-même **recommande d'attendre le rebuild** (plan §8) ; le à-chaud n'y figure
que comme **repli conditionnel**.

### Le fix inotify SUFFIT à tenir jusqu'au rebuild

**La HA n'aurait PAS empêché l'épuisement inotify** — elle aurait seulement
gardé l'API servie ailleurs : un **pansement de disponibilité** sur un bug node
qu'on corrige **directement à la cause**, à moindre risque. Le fix inotify est
**cheap, node-level, réversible, sans effet sur le quorum**. L'urgence de
l'incident ne justifie **pas** le à-chaud non-prouvé, qui importerait un risque
bien pire.

## Plan priorisé

- **P0 — Fix inotify** : sysctl `fs.inotify.max_user_instances=8192` (+ watches)
  node-level sur les 4 nœuds, codifié dans `k8s-CRI-install` + assertion de
  vérif. → une PR cluster dédiée.
- **P1 — Filet & instrumentation** : étendre le backup etcd hors-nœud (déjà
  outillé, `hosts: control`) ; alerte Prometheus saturation inotify ; requests/
  limits sur `pg-1/2/3` ; espacer le reconciler `*/5 → */15`.
- **P2 — Préparer le HA du REBUILD** (~sept 2026,
  [plan-ha-3cp](../plans/plan-ha-3cp-control-plane.md)) : recâbler
  l'orchestrateur HA supprimé (`path.py`, gate etcd) sous PR dédiée ; ajouter la
  régénération cert+VIP ; poser `placement.mon`. Ces trois trous sont **gratuits
  au rebuild** (from-scratch).
- **Repli in-place à chaud** : UNIQUEMENT si dirqual1 devient **récurremment**
  instable ET **après** recâblage + preuve de l'orchestrateur — pas avant.

## Manques → suite

- PR P0 fix inotify (bootstrap) — **prioritaire**.
- Éventuel ADR court « durcissement noyau des nœuds k8s (inotify) » complétant
  [ADR 0014](../decisions/0014-durcissement-kubeadm-init.md).
- La reco HA-au-rebuild alimente le
  [plan-ha-3cp](../plans/plan-ha-3cp-control-plane.md) (§ repli) et le finding
  #486 de l'[audit prod 2026-06-24](2026-06-24-audit-prod-dirqual.md).
