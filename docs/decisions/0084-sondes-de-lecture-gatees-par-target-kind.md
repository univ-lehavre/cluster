# 0084 — Sondes de lecture gatées par `target_kind` (isolation banc/prod, suite de 0053)

## Statut

Proposed (2026-06-17)

> ⚠️ **Amendé par
> [ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md)
> (2026-07-11).** Le gate des sondes de lecture ne repose plus sur la criticité
> `target_kind` (supprimée) mais sur la classe matérielle **`terrain`** : une
> sonde propre au banc (`limactl`, VMs Lima) se gate sur `terrain == "local"`,
> non sur `bench`. Le principe de cet ADR — **borner les sondes qui touchent le
> réel pour ne pas agir sur la mauvaise cible** — est conservé ; seul l'axe de
> gate change (`target_kind` → `terrain`). Lire le titre et le corps comme le
> témoin de l'état au 2026-06-17.

## Contexte

L'[ADR 0053](0053-isolation-multi-cible-banc-prod.md) a isolé banc et prod côté
**mutations** (kubectl nommé, contextes renommés, garde d'inventaire, garde
`_assert_bench_target`). Son point (e) annonçait que la **lecture** (`preview`)
« n'est pas bloquée mais avertit », et que le repli kubeconfig
(`_bench_kubeconfig`) ne lit jamais `~/.kube/config` par accident.

Mais ce point (e) ne couvrait que le **kubeconfig**. Deux sondes de
`scripts/topology.py` restent **codées « banc » en dur**, sans regarder
`topo.target_kind` :

- `_real_vms()` lance **inconditionnellement** `limactl list` — un concept
  **Lima**, sans aucun sens pour une topologie `target_kind: prod` (baremetal :
  pas de « VM » créable localement, les nœuds existent déjà) ;
- `_ready_nodes()` (et la sonde de drift de backend) lit le kubeconfig **banc**.

`cmd_preview`/`cmd_next` les appellent sans passer `target_kind`. Conséquence
**vécue** sur la stack prod `dirqual` (`target_kind: prod`, backend ceph, nœuds
`dirqual1-4`) : la section RÉEL affiche l'état du **banc Lima** — VMs orphelines
`node1/node2`, nœuds `lima-node1/lima-node2` Ready, backend réel `local-path`.
Le VOULU est prod, le RÉEL est banc : **preview ment**, et le PLAN qui en
découle (« VMs à créer : dirqual1-4 », « MLflow à installer ») mélange les deux
cibles.

C'est exactement le **faux-résultat-silencieux** que proscrit
[ADR 0052](0052-reproductibilite-des-resultats.md) : un aperçu de prod n'a de
valeur que s'il a prouvablement regardé la prod. Les mutations sont protégées
(0053) ; la **lecture**, elle, induit en erreur — dangereux juste avant un
montage prod.

## Décision

**Les sondes de l'état RÉEL sont gatées par `topo.target_kind`.** Une commande
qui lit le réel d'une stack ne sonde jamais une cible d'un autre `kind` que
celui déclaré. Précise et étend le point (e) de
l'[ADR 0053](0053-isolation-multi-cible-banc-prod.md).

1. **`_real_vms(target_kind)`** : `limactl list` n'est appelé QUE pour
   `target_kind == "lima"`. Pour `prod`, la fonction rend `[]` — il n'y a pas de
   « VM » créable localement en baremetal (les nœuds préexistent). La ligne «
   VMs à créer » d'un `preview` prod ne désigne donc plus des VMs Lima fantômes.

2. **`_ready_nodes(target_kind)` / sonde de backend** :
   - `target_kind == "lima"` → repli sûr inchangé (`_bench_kubeconfig` : banc,
     sinon vide, jamais `~/.kube/config`) ;
   - `target_kind == "prod"` → on ne sonde QUE si un `KUBECONFIG` est **exporté
     explicitement** (intention, ADR 0053 (a)). Sinon : état vide +
     **avertissement** « cible prod : exporter le KUBECONFIG prod ou
     `nestor discover --cp <nœud>` d'abord ». **Jamais** `~/.kube/config`
     implicite — un `preview` prod sans cible nommée affiche un RÉEL honnêtement
     vide, pas le banc.

3. **`cmd_env` n'exporte pas le banc pour une stack prod.** Le wrapper `nestor`
   appelle `env --force` après `up`/`next`, qui posait TOUJOURS
   `KUBECONFIG=banc`. Sur une stack active `target_kind: prod`, cet auto-export
   polluait le shell : (a) les `preview` suivants lisaient `lima-*` (KUBECONFIG
   « explicite »), (b) pire, `_assert_bench_target` voyait ce KUBECONFIG et **ne
   bloquait plus** `up`/`next` → `next` proposait de créer des VMs Lima sur une
   cible prod. `cmd_env` lit désormais la topo active (`_active_topology_safe`)
   : si `target_kind != lima`, il n'exporte pas le banc (invite à exporter le
   KUBECONFIG prod / `discover --cp`).

4. **La phase `up` est sautée en prod.** `up` = provisionner les VMs via
   `limactl`, propre au banc Lima. En prod, les nœuds baremetal PRÉEXISTENT →
   `expected_phase_sequence` ne pose pas `up` (le socle commence à `bootstrap`,
   k8s sur les nœuds existants). `next`/`preview` d'une stack prod ne proposent
   donc plus « créer les VMs ».

5. **Les avertissements d'alignement shell sont gatés sur lima.** Les messages «
   preview lit le banc » / « cluster non installé » (pensés pour le banc,
   ADR 0053) ne s'affichent que pour `target_kind: lima` — en prod ils seraient
   trompeurs (ils invitent à `nestor env` qui, en prod, ne pose rien).

6. **Aucune mutation touchée** : `_assert_bench_target` (0053 (e)) reste
   inchangé — il garde les mutations BANC. La prod ne se mute pas via
   `cmd_up`/`cmd_next` Python (voie playbooks/`discover --cp`,
   [ADR 0074](0074-cluster-discover-reconstruire-topologie.md)). Cet ADR ne
   concerne que la **lecture** et l'**alignement d'environnement**.

## Conséquences

- **`preview`/`next` cessent de mélanger banc et prod** : une stack
  `target_kind: prod` affiche soit l'état prod réel (KUBECONFIG prod exporté),
  soit un RÉEL vide explicite — jamais l'état du banc Lima coexistant.
- **ADR 0053 renforcé, pas contredit** : la prod n'est lue que sur intention
  explicite (KUBECONFIG exporté), jamais `~/.kube/config` par défaut. Le
  faux-résultat silencieux devient un état vide + avertissement bruyant (ADR
  0052).
- Coût faible : passer `topo.target_kind` aux deux sondes + 3 sites d'appel
  (`cmd_preview`, `cmd_next`, `cmd_destroy`). Prouvable sans banc (tests stubés
  sur `target_kind: prod`).
- ADR amendé : [0053](0053-isolation-multi-cible-banc-prod.md) (e) — la lecture
  n'est pas seulement « non bloquée + avertit », elle est **gatée par
  target_kind** pour ne pas sonder la mauvaise cible.

## À revoir si

- Le kubeconfig prod rapatrié par `discover --cp` est **mémorisé par stack**
  (notion de « kubeconfig de la stack ») : `_ready_nodes` prod pourrait le
  réutiliser sans exiger un export manuel à chaque `preview`.

## Alternatives écartées

- **Bloquer `preview` prod sans KUBECONFIG** (refus code 2) : plus strict mais
  empêche l'aperçu VOULU/PLAN hors-ligne (utile pour préparer un montage prod
  sans cluster joignable). Rejeté — la lecture doit rester possible, juste
  honnête (RÉEL vide + avertissement).
- **Sonder `~/.kube/config` pour une topo prod** : violerait frontalement l'ADR
  0053 (a) — la cible doit être nommée, jamais ambiante. Rejeté.
- **Laisser `_real_vms` lancer `limactl` partout** (statu quo) : c'est la cause
  du bug ; `limactl` n'a aucun sens en prod. Rejeté.
