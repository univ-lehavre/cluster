"""Moteur de chemin Python : absorbe l'orchestration de `bench/lima/run-phases.sh`.

LOT 6 de la refonte nestor (ADR 0097 §1) — le SECOND pilier. Aujourd'hui
`run-phases.sh` (1903 l.) est l'orchestrateur : il DÉCIDE quoi monter, ENCHAÎNE les
`ansible-playbook`, GATE la santé via kubectl, POSSÈDE l'état partagé (`CP`,
`API_PORT`, `KUBECONFIG_LOCAL`) et PROVISIONNE (`phase_up`, `write_inventory`) ;
`cmd_up`/`cmd_next` ne font que l'appeler en subprocess. Ce module porte cette
boucle EN PYTHON, sur le MÊME moule éprouvé 2× (`bootstrap.run_bootstrap:102`,
`ha.run_ha_3cp`) : la LOGIQUE (séquence ordonnée des phases + gardes + gates) est
PURE et testable sans banc ; toute l'I/O réelle (ansible-runner, kubectl, limactl)
est INJECTÉE en callbacks par la façade.

═══════════════════════════════════════════════════════════════════════════════
⚠️  FRONTIÈRE CODE-ÉCRIT / PREUVE-BANC (ADR 0034 — HONNÊTETÉ)

Ce module touche le MONTAGE RÉEL (lance des playbooks, gate sur cluster live,
provisionne des VM). Sa preuve DÉFINITIVE est un RUN BANC from-scratch consigné
(`bench/lima/RESULTS.md`) + rejeu `changed=0` — qui RESTE À FAIRE AVANT TOUT MERGE.
Le code ci-dessous est PROUVÉ par tests unitaires STUBÉS (briques injectées, zéro
cluster) pour sa LOGIQUE d'orchestration UNIQUEMENT — PAS pour le comportement réel
au montage. Les parties trop liées au montage réel pour être écrites sans banc
(provisioning exact via limactl, write_inventory byte-stable) sont des STUBS avec
un TODO « à câbler+prouver au banc » — voir `_BANC_TODO` en bas de fichier.

ATTENTION COEXISTENCE (plan invariant 4) : ce module N'EST PAS ENCORE BRANCHÉ sur
`cmd_up`/`cmd_next`. Le chemin par défaut reste le subprocess `run-phases.sh`. La
bascule réelle se fera lot par lot AVEC la preuve banc en main. Voir `run_path`.
═══════════════════════════════════════════════════════════════════════════════

Un SEUL sens d'appel — Python → bash (ADR 0097 §1). `run_path` NE rappelle JAMAIS
`topology.py`/`run-phases.sh` : il pousse les artefacts irréductibles (`cni.sh`,
`cleanup.sh`) comme on applique un manifeste (Python pousse, consomme un `rc`, ne
lit jamais leur logique, ADR 0097 §2.a) et lance les playbooks via
`runner.launch_phase_idempotent`. La circularité `Python→bash→Python→bash`
(`run-phases.sh:508 bootstrap-seq`, `:1650 ha-3cp`) disparaît — mais SEULEMENT une
fois `cmd_up`/`cmd_next` basculés (lot futur, après preuve banc).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nestor.gates import GateError, gate_etcd, gate_nodes_ready, gate_vip
from nestor.ha_probes import (
    bootstrap_extravars,
    cp_join_order,
    etcd_health_output,
    join_extravars,
    vip_healthz,
)


class PathError(RuntimeError):
    """Le montage d'un chemin a échoué : phase KO, gate non tenue, garde refusée."""


class IsolationRefused(PathError):
    """La garde d'isolation a REFUSÉ une phase (cible non prouvée-banc, ADR 0053).

    Sous-classe distincte pour que l'appelant (et les tests) distinguent un REFUS de
    sécurité (la cible n'est pas sûre) d'un échec de montage ordinaire — un REFUS ne
    doit JAMAIS être confondu avec « la phase a planté » (on n'a rien touché)."""


# ── État partagé du chemin (ADR 0097 §5.a — path.py POSSÈDE ce que run-phases.sh
#    tenait en globales bash). Aujourd'hui `CP`, `API_PORT`, `KUBECONFIG_LOCAL`,
#    `REPO` sont des variables globales du script bash (run-phases.sh:83/90/148,
#    lib.sh:23) consultées partout. Le moteur Python doit les POSSÉDER, sinon il
#    re-rappelle bash pour les lire et la circularité persiste (réserve R-ÉTAT). On
#    les réunit dans un dataclass IMMUABLE construit UNE fois par la façade (à partir
#    de la topologie), passé à `run_path` — plus de globale ambiante.


@dataclass(frozen=True)
class PathContext:
    """État partagé que `run-phases.sh` détenait en globales bash (ADR 0097 §5.a).

    - `cp` : nom du CP primaire (= run-phases.sh:83 `CP`, 1er nœud `control`). Dérivé
      de la topologie par la façade (pas codé en dur), pas lu depuis bash.
    - `api_port` : port hôte du forward de l'API (= run-phases.sh:90 `API_PORT`=6443).
    - `kubeconfig_local` : kubeconfig du banc rapatrié (= run-phases.sh:148
      `KUBECONFIG_LOCAL`, `<WORKDIR>/kubeconfig`). Posé par le provisioning.
    - `repo` : racine du dépôt (= lib.sh:23 `REPO`) — pour résoudre les playbooks.
    - `inventory` : chemin de l'inventaire actif (write_inventory l'écrit ; le moteur
      le LIT pour la garde `_assert_inventory_safe`, jamais ambiant — ADR 0063 G3).
    - `nodes` : nœuds attendus Ready (compte du gate socle nodes_ready_all).

    IMMUABLE : construit UNE fois (la façade le dérive de la topologie), jamais muté
    en cours de boucle — l'inverse de la globale bash réécrite en place."""

    cp: str
    api_port: int = 6443
    kubeconfig_local: str = ""
    repo: str = ""
    inventory: str = ""
    nodes: tuple[str, ...] = ()


# ── Résultat (même forme que BootstrapResult/HaResult : steps + verdict dérivé) ──


@dataclass
class PathStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class PathResult:
    """Verdict du montage d'un chemin. `built` = toutes les étapes ont réussi."""

    target: str
    steps: list[PathStep] = field(default_factory=list)

    @property
    def built(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)


# ── Phases AMONT à orchestration NON-Ansible (provisioning / artefacts bash) ─────
# `up` (créer les VM via limactl), `bootstrap` (socle k8s + CNI) et `ha` (montage
# HA `ha-3cp`) ne sont PAS un `launch_phase(<playbook>)` : `up` provisionne les VM,
# `bootstrap` enchaîne les 6 playbooks du socle PUIS pose la CNI (cni.sh, artefact
# irréductible ADR 0097 §2.a), et `ha` est une SÉQUENCE Python complète (bootstrap du
# primaire derrière la VIP + promotion des CP un à un, gate etcd entre chaque) — c'est
# `run_ha_3cp` (plus bas dans CE module, ex-`nestor.ha`, fusionné). Le moteur les
# délègue à des callbacks DÉDIÉS (`provision`, `bootstrap`, `ha`) injectés par la façade
# — qui les branche sur le provisioning Python (à câbler, §5.b),
# `nestor.bootstrap.run_bootstrap` et `path.run_ha_3cp` (déjà portés). Les phases du
# socle Ceph (`ceph`, `sc`) ONT un playbook
# (PHASE_PLAYBOOK) → elles passent par `launch`.
#
# LOT 9 (ADR 0097 §2.b — exception nommée HA LEVÉE) : brancher `ha` ICI fait du chemin
# `ha-3cp` une SÉQUENCE Python comme les autres (`up` → `ha` → `storage-simple`), au lieu
# d'un sous-process bash (`run-phases.sh ha-3cp`) qui rappelle Python (`topology.py ha-3cp`)
# qui rerappelle bash (`ha-cni`) — la circularité `Python→bash→Python→bash` de `:1650`. Le
# callback `ha` porte le DOUBLE GESTE de `phase_ha_cni` (run_cni PUIS fetch_kubeconfig,
# ADR 0097 §2.b) : la façade couvre LES DEUX gestes, sinon le pont `ha-cni` resterait
# appelé pour le kubeconfig et la circularité résiduelle subsisterait.
_NON_ANSIBLE_AMONT = frozenset({"up", "bootstrap", "ha"})


def run_path(
    topo,
    target: str,
    *,
    sequence,
    launch,
    gate,
    assert_safe,
    provision=None,
    bootstrap=None,
    ha=None,
    record=None,
    sleep=None,
):
    """Monte un chemin nommé : boucle PURE-TESTABLE sur sa séquence de phases.

    Généralise le patron éprouvé 2× (`bootstrap.run_bootstrap`, `ha.run_ha_3cp`) :
    toute l'I/O est INJECTÉE, la LOGIQUE (ordre + gardes + gates) est testable sans
    banc. Lève `PathError`/`IsolationRefused` au 1er échec (fail-fast, comme le `die`
    du bash).

    Callbacks injectés (la façade les branche sur le réel — runner/kubectl/limactl) :
    - `sequence(topo, target) -> list[str]` : la séquence ORDONNÉE de phases (façade →
      `plan.expected_phase_sequence`, déjà la fonction partagée preview/next/up). On
      l'injecte plutôt que de l'importer pour garder le module PUR et le test trivial.
    - `launch(phase) -> objet à .ok/.verdict` : monte UNE phase applicative (façade →
      `runner.launch_phase_idempotent` — le double-passage PROUVE `changed=0`,
      ADR 0052). Idempotence VÉRIFIÉE, pas postulée.
    - `gate(phase) -> bool` : la couche est-elle SAINE après montage (façade →
      `topology._wait_layer_healthy` / `gates.py`). Une phase sans signal connu rend
      True (rien à gater — parité `_wait_layer_healthy`).
    - `assert_safe(phase) -> None` : LA GARDE D'ISOLATION (ADR 0053), traversée AVANT
      CHAQUE phase (INVARIANT DE BOUCLE, ADR 0097 §1 — voir plus bas). Lève sur refus.
    - `provision(phase) -> int` : monte une phase AMONT à orchestration non-Ansible
      (`up` : VM via limactl ; rc 0 = ok). STUB tant que le provisioning Python n'est
      pas câblé (§5.b) — la façade peut y router un rappel transport.
    - `bootstrap(phase) -> int` : monte le socle k8s+CNI (`bootstrap` ; rc 0 = ok)
      (façade → `nestor.bootstrap.run_bootstrap`, déjà porté).
    - `ha(phase) -> int` : monte la HA `ha-3cp` (`ha` ; rc 0 = ok) — la SÉQUENCE
      Python complète `path.run_ha_3cp` (ex-`nestor.ha`, fusionné ici ; bootstrap
      primaire + promotions, gates etcd), portant le DOUBLE GESTE de `phase_ha_cni`
      (run_cni PUIS fetch_kubeconfig,
      ADR 0097 §2.b). La façade y branche `run_ha_3cp` avec ses callbacks réels
      (launch/run_cni/fetch_kubeconfig/set_inventory/gates) — LOT 9, exception HA levée.
    - `record(result) -> None` : consigne le run from-scratch (façade →
      `metro_record_run`/historique, parité `record_full_run`). Optionnel.
    - `sleep` : inutilisé ici (signature homogène avec les autres moteurs ; les
      attentes vivent dans `gate`). Réservé.

    ┌─ INVARIANT DE BOUCLE — la garde d'isolation à CHAQUE phase (ADR 0097 §1, §5.c)
    │  `assert_safe` est appelée AVANT CHAQUE phase, PAS une seule fois en tête. Le
    │  subprocess `run-phases.sh` actuel ne traverse la garde qu'UNE fois (cmd_up la
    │  passe puis délègue tout le chemin) ; un moteur Python bouclant PAR phase DOIT
    │  la ré-affirmer à chaque itération — sinon un montage banc dont le `KUBECONFIG`
    │  prod a été exporté en cours de route taperait la PROD (faille ADR 0053). La
    │  façade y branche `_assert_bench_target` + `_assert_inventory_safe` ; l'ÉCHAPPATOIRE
    │  `KUBECONFIG` exporté (« intention explicite assumée », ADR 0065) est gérée DANS
    │  `_assert_bench_target` (elle rend tôt si `KUBECONFIG` est posé) — le moteur ne
    └─ la court-circuite donc PAS, il appelle la garde et la garde décide.
    """
    _ = sleep  # signature homogène (cf. bootstrap.run_bootstrap) ; gates portent l'attente
    seq = sequence(topo, target)
    result = PathResult(target=target)
    try:
        for phase in seq:
            # INVARIANT DE BOUCLE : garde d'isolation AVANT CHAQUE phase (ADR 0097 §1).
            # Un refus lève IsolationRefused — distinct d'un échec de montage : on n'a
            # RIEN touché (la garde protège la prod en amont du moindre geste).
            try:
                assert_safe(phase)
            except PathError:
                raise
            except Exception as exc:  # noqa: BLE001 — la garde façade lève _UsageError (hors hiérarchie)
                raise IsolationRefused(
                    f"phase `{phase}` REFUSÉE par la garde d'isolation (ADR 0053) : {exc}"
                ) from exc

            # Montage de la phase : amont non-Ansible (provisioning/socle/HA) vs play.
            if phase in _NON_ANSIBLE_AMONT:
                _run_amont(
                    phase,
                    provision=provision,
                    bootstrap=bootstrap,
                    ha=ha,
                    steps=result.steps,
                )
            else:
                res = launch(phase)
                # `launch` peut rendre un IdempotenceResult (`.ok` = double-passage changed=0)
                # OU un RunResult (un seul passage, parité bash : succès = `rc==0`) OU un
                # résultat de seed (`.ok`). On accepte les deux : `.ok` s'il existe, sinon rc==0.
                ok = bool(res.ok) if hasattr(res, "ok") else getattr(res, "rc", 1) == 0
                result.steps.append(
                    PathStep(phase, ok, getattr(res, "verdict", "") or getattr(res, "message", ""))
                )
                if not ok:
                    raise PathError(
                        f"phase `{phase}` : montage en échec "
                        f"({getattr(res, 'message', '') or getattr(res, 'verdict', 'rc≠0')})"
                    )

            # GATE de santé APRÈS le montage (parité `_wait_layer_healthy`, #355) : un
            # play `rc=0` ne prouve pas la couche SAINE (Loki jamais Ready — panne vécue).
            # Une phase sans signal connu rend True (rien à gater). Échec → fail-fast.
            if not gate(phase):
                result.steps.append(
                    PathStep(f"{phase} (gate)", False, "couche montée mais PAS saine")
                )
                raise PathError(f"phase `{phase}` montée mais PAS saine (gate de santé non tenue)")
            result.steps.append(PathStep(f"{phase} (gate)", True, "sain"))
    except PathError:
        # On consigne quand même les étapes franchies pour le diagnostic, puis on relève
        # (fail-fast : le run n'est PAS consigné comme preuve, cf. record_if_fresh bash).
        raise

    # Run from-scratch RÉUSSI : consigné (parité record_full_run, ADR 0034/0042). Un run
    # qui a échoué (exception ci-dessus) n'arrive jamais ici → jamais consigné = jamais
    # une fausse preuve. `record` optionnel (None en test).
    if record is not None:
        record(result)
    return result


def _run_amont(phase: str, *, provision, bootstrap, ha, steps: list[PathStep]) -> None:
    """Monte une phase AMONT non-Ansible (`up` provisioning / `bootstrap` socle+CNI /
    `ha` montage HA `ha-3cp`).

    Délègue au callback DÉDIÉ injecté (provisioning, socle et HA ne sont PAS un
    `launch_phase`) ; rc 0 = ok, sinon PathError. Si le callback manque (None), c'est
    un STUB explicite à câbler au banc (§5.b) — on lève plutôt que d'inventer un
    montage faux. Le callback `ha` porte `path.run_ha_3cp` (ex-`nestor.ha`, fusionné),
    DOUBLE GESTE `ha-cni` compris (run_cni PUIS fetch_kubeconfig, ADR 0097 §2.b)."""
    cb = {"up": provision, "bootstrap": bootstrap, "ha": ha}[phase]
    if cb is None:
        raise PathError(
            f"phase amont `{phase}` non câblée : le callback de montage est absent "
            "(STUB — à câbler+prouver au banc, ADR 0097 §5.b)"
        )
    rc = cb(phase)
    ok = rc == 0
    steps.append(PathStep(phase, ok, f"rc={rc}"))
    if not ok:
        raise PathError(f"phase amont `{phase}` en échec (rc={rc})")


# ═══════════════════════════════════════════════════════════════════════════════
# RÉSERVES ADR 0097 §5 — à traiter explicitement (les nommer dans le code) :
#
#   §5.a — ÉTAT PARTAGÉ : path.py POSSÈDE CP/API_PORT/KUBECONFIG_LOCAL/REPO →  ✅ FAIT
#          (dataclass `PathContext` immuable, dérivé par la façade, plus de globale).
#
#   §5.b — PROVISIONING + write_inventory : absorber `phase_up` (VM via limactl) et
#          l'écriture d'inventaire byte-stable.                            →  🟧 STUBÉ
#          `_run_amont('up', provision=…)` route vers un callback DÉDIÉ ; le câblage
#          RÉEL du provisioning (limactl render/start, gate disques Ceph, dérivation
#          cp_ip/iface, write_inventory) RESTE À FAIRE — c'est du montage RÉEL non
#          prouvable sans banc (réserve R-ÉTAT « état shell→Python sous-estimé »). On
#          ne l'INVENTE pas ici (un faux provisioning serait pire que rien). Voir
#          `_BANC_TODO`. Le moteur SAIT qu'il faut une phase `up` (elle est dans la
#          séquence) et la délègue proprement au callback ; ce qui manque, c'est le
#          CONTENU réel du callback, à écrire face à un banc Lima réconcilié.
#
#   §5.c — GARDE D'ISOLATION À CHAQUE PHASE : invariant de boucle.          →  ✅ FAIT
#          `assert_safe(phase)` appelée en tête de CHAQUE itération (pas une fois) ;
#          l'échappatoire KUBECONFIG est gérée DANS la garde façade (ADR 0065), le
#          moteur ne la court-circuite pas. Couvert par test (test_path.py).
#
#   §2.b — HA `ha-3cp` BRANCHÉE AU MOTEUR (exception nommée LEVÉE).          →  🟧 LOT 9
#          La phase `ha` est dans `_NON_ANSIBLE_AMONT` → le moteur la délègue au
#          callback DÉDIÉ `ha` (= `path.run_ha_3cp`, fusionné ici), faisant du chemin `ha-3cp` une
#          SÉQUENCE Python (`up`→`ha`→`storage-simple`) au lieu du sous-process bash qui
#          rappelle Python (circularité `:1650`). Le callback porte le DOUBLE GESTE de
#          `phase_ha_cni` (run_cni PUIS fetch_kubeconfig, §2.b). Couvert par test
#          (test_ha_path.py, stubs purs). RESTE BANC : câbler le callback `ha` réel dans
#          la façade (run_ha_3cp + fetch_kubeconfig transport) ET retirer les rappels
#          `ha-3cp`/`ha-cni` de run-phases.sh — bascule sous preuve banc (voir _BANC_TODO).
# ═══════════════════════════════════════════════════════════════════════════════


# ── CE QUI RESTE À CÂBLER + PROUVER AU BANC (TODO explicites, ADR 0034) ──────────
# Le code ci-dessus est la LOGIQUE d'orchestration (prouvée par tests stubés). Les
# points suivants touchent le montage RÉEL et exigent un RUN BANC from-scratch (banc
# Lima non réconcilié ici — preuve IMPOSSIBLE dans cette session, NE PAS prétendre
# l'avoir faite) :
_BANC_TODO = (
    # 1. CÂBLAGE FAÇADE — FAIT (derrière le FLAG opt-in `nestor up --engine=python`,
    #    `topology._run_path_engine` ; le DÉFAUT reste run-phases.sh, invariant 4) :
    #      PathContext → `topology._path_context` (cp=1er control, kubeconfig_local/inventory
    #                    = chemins banc, repo=racine, nodes) — PUR, testé ;
    #      launch   → runner.launch_phase_idempotent + extravars_for + e2e_hooks_for (LÈVENT) ;
    #      gate     → topology._wait_layer_healthy (signal _LAYER_SIGNAL/graph) ;
    #      assert_safe → topology._assert_bench_target (+ _assert_inventory_safe par-play) ;
    #      provision('up') → STUB `run-phases.sh up` (artefact node-side, §5.b) ;
    #    RESTE : la PREUVE banc du chemin python (run mono-nœud `--engine=python`).
    "preuve banc du moteur python (nestor up --engine=python, mono-nœud) — reste à faire",
    # 2. PROVISIONING RÉEL (§5.b) : le callback `provision('up')` POUSSE aujourd'hui
    #    `run-phases.sh up` (STUB documenté, `topology._provision_via_bash` — limactl reste
    #    bash, ADR 0049). LOT 8 : les RESSOURCES VM (cpus/memory/disk) viennent du YAML
    #    (`topo.node_resources(<node>)`) — passées en env VM_CPUS/VM_MEMORY/VM_DISK le temps
    #    de la transition. RESTE : câbler `lima_render_node(<valeurs>)` directement (bash
    #    garde le RENDU, Python décide les VALEURS) + write_inventory — à prouver au banc.
    "provisioning Python direct (lima_render_node + write_inventory) — à prouver au banc",
    # 2.b BOOTSTRAP/HA en --engine=python : les callbacks `bootstrap`/`ha` LÈVENT
    #    aujourd'hui (transport cp_ip/iface + CNI/fetch_kubeconfig non prouvés au banc). Les
    #    moteurs `bootstrap.run_bootstrap`/`path.run_ha_3cp` sont portés+testés ; RESTE le
    #    câblage transport (rappel ha-cni, dérivation Lima vivant) — à câbler+prouver au banc.
    "câblage transport bootstrap/ha en --engine=python (cp_ip/iface, CNI) — à prouver au banc",
    # 3. BASCULE DU DÉFAUT cmd_up/cmd_next sur run_path (retrait subprocess run-phases.sh).
    #    Le flag `--engine=python` est COEXISTENCE (run_path à côté, opt-in) ; basculer le
    #    DÉFAUT vient APRÈS la preuve banc (plan invariant 4). Le grep sens-unique
    #    `grep -rn 'uv run python\|topology.py' bench/lima/` doit alors rendre 0 :
    #    retirer le rappel `bootstrap-seq` (:508) ET, LOT 9, le rappel `ha-3cp` (:1650).
    "bascule du DÉFAUT cmd_up/cmd_next sur run_path (retrait run-phases.sh) — après preuve banc",
    # 3.c CONSIGNATION runs-history (#216) en --engine=python : le callback `record` est None
    #    (STUB) — `metro_record_run` (bash) agrège durées + métriques metrology.sh PENDANT le
    #    run, qu'un append Python ne reproduit pas byte-stable (history.py:20). À câbler+prouver.
    "consignation runs-history (record) en --engine=python — à câbler+prouver au banc",
    # 3.b LOT 9 — CÂBLER le callback `ha` réel dans la façade (= path.run_ha_3cp,
    #    déjà porté) + COUVRIR le 2ᵉ geste `fetch_kubeconfig` en Python (ou via l'arm bash
    #    `kubeconfig`, transport pur), pour que le pont `ha-cni` ne soit plus appelé POUR
    #    LE KUBECONFIG (sinon circularité résiduelle, ADR 0097 §2.b). PUIS retirer les
    #    rappels `ha-3cp` (run-phases.sh:1650) et `ha-cni` de run-phases.sh. Le grep
    #    sens-unique allowliste `ha-cni` JUSQU'À cette bascule ; après preuve banc → 0.
    "câblage façade `ha` (run_ha_3cp + fetch_kubeconfig) + retrait ha-3cp/ha-cni — au banc",
    # 4. RUN BANC from-scratch consigné (bench/lima/RESULTS.md) + rejeu changed=0
    #    sur LES DEUX topologies (banc local-path PUIS dirqual Ceph, invariants 1-2).
    "run banc from-scratch + rejeu changed=0 (banc PUIS prod) — PREUVE DÉFINITIVE, reste à faire",
)


def banc_todo() -> tuple[str, ...]:
    """Liste EXPLICITE de ce qui reste à câbler+prouver AU BANC (honnêteté ADR 0034).

    Accesseur testable : un test vérifie que la frontière code-écrit / preuve-banc est
    DÉCLARÉE (non vide), pour qu'on ne puisse pas merger en oubliant la preuve."""
    return _BANC_TODO


# ═══════════════════════════════════════════════════════════════════════════════
# MONTAGE HA `ha-3cp` — l'ALGORITHME de promotion (ex-`nestor/ha.py`, fusionné ici).
#
# Pourquoi ICI et plus dans un module séparé (décision du mainteneur — un seul moteur) :
# le montage HA EST une orchestration de chemin (séquence ordonnée de phases + gardes +
# gates), exactement le patron de `run_path`. Sa place est dans le moteur, à côté du
# moteur de chemin générique qui le DÉLÈGUE (callback `ha`, _NON_ANSIBLE_AMONT). Les
# sondes I/O + fonctions pures vivent dans `nestor.ha_probes` (module-feuille) ; les
# gates `gate_vip`/`gate_etcd`/`gate_nodes_ready` dans `nestor.gates` (maison unique des
# gates — `gate_nodes_ready` n'y est désormais qu'EN UN exemplaire). Ce bloc ne garde
# que la SÉQUENCE de promotion et compose les deux.
#
# Pourquoi Python et non bash : « Python sait parler Ansible » (ADR 0063) — cette
# orchestration LANCE des playbooks via `runner.launch_phase` (ansible-runner), au lieu
# d'enchaîner des `ansible-playbook` en sous-process. La séquence a été PROUVÉE d'abord
# en bash (super-admin→admin, VIP, cluster-api, gates) ; ce portage en est fidèle. La
# PREUVE réelle reste un run de banc consigné (ADR 0034/0052, #250).
# ═══════════════════════════════════════════════════════════════════════════════


class HaError(RuntimeError):
    """Séquence HA interrompue : gate non franchie, playbook en échec, VIP/quorum KO."""


@dataclass
class HaStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class HaResult:
    """Verdict du montage ha-3cp. `built` = toutes les étapes ont réussi."""

    vip: str
    steps: list[HaStep] = field(default_factory=list)

    @property
    def built(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)


# Playbooks du bootstrap primaire, dans l'ORDRE prouvé. kube-vip est lancé deux
# fois (amorçage super-admin.conf AVANT l'init k8s≥1.29, puis bascule admin.conf).
_PRE_INIT_PLAYBOOKS = ("checks", "cri", "kubeadm", "control-planes")


def _gate_nodes_ready(expected: int, *, ready_count, sleep) -> None:
    """Pont RAISE-on-failure vers la gate UNIQUE `gates.gate_nodes_ready` (le doublon
    ex-`ha.gate_nodes_ready` est SUPPRIMÉ — il n'y a plus qu'UNE boucle d'attente, celle
    de `gates.py`, testée). La promotion HA est fail-fast : un timeout DOIT lever, donc
    on adapte le `GateResult` (rendu, jamais levé) en `HaError`. En HA les CP rejoignent
    un à un : chaque étape attend le compte À CE STADE, pas les N finaux."""
    res = gate_nodes_ready(expected, ready_count=ready_count, sleep=sleep)
    if not res.ok:
        raise HaError(f"moins de {expected} nœud(s) Ready (timeout)")


def _check(launch, playbook: str, extravars: dict[str, str], label: str, limit=None) -> None:
    """Lance un playbook via `launch(playbook, extravars, limit=…)` et lève HaError
    si le run échoue. `launch` renvoie un objet exposant `rc`/`status`. `limit`
    restreint le play à un hôte (promotion d'UN CP à la fois)."""
    res = launch(playbook, extravars, limit=limit)
    if getattr(res, "rc", 1) != 0 or getattr(res, "status", "") != "successful":
        raise HaError(
            f"{label} : playbook {playbook} en échec "
            f"(rc={getattr(res, 'rc', '?')}, status={getattr(res, 'status', '?')})"
        )


def _noop_fetch_kubeconfig() -> None:
    """Défaut du 2ᵉ geste `ha-cni` (rapatriement du kubeconfig) : ne rien faire.

    DOUBLE GESTE de `phase_ha_cni` (ADR 0097 §2.b) : la sous-commande-pont bash
    `ha-cni` fait DEUX choses — `run_cni` (Cilium dans la VM, irréductible §2.a)
    PUIS `fetch_kubeconfig_node` (sed-rewrite de `admin.conf` vers le forward hôte,
    transport pur). Tant que le 2ᵉ geste n'est PAS couvert par la façade Python, le
    pont `ha-cni` reste appelé POUR LE KUBECONFIG → circularité résiduelle (§2.b).
    On l'expose donc en callback DÉDIÉ et SÉPARÉ de `run_cni` (la façade le branche
    sur le transport — bash `kubeconfig` ou un portage Python du sed). Défaut no-op
    pour les appelants legacy (cmd_ha_3cp rappelle encore `ha-cni`, qui fait les
    deux) ; le moteur de chemin (`path.py`), lui, EXIGE le geste séparé."""
    return None


def bootstrap_primary(
    cp_ip: str,
    vip: str,
    vip_iface: str,
    *,
    launch,
    run_cni,
    vip_responds,
    ready_count,
    sleep,
    fetch_kubeconfig=_noop_fetch_kubeconfig,
) -> list[HaStep]:
    """Monte le CP PRIMAIRE derrière la VIP (séquence prouvée). `launch(playbook,
    extravars)` lance UN playbook (← runner.launch_phase partiellement appliqué) ;
    `run_cni()` pose Cilium ; `fetch_kubeconfig()` rapatrie le kubeconfig (2ᵉ geste
    de `ha-cni`, ADR 0097 §2.b — SÉPARÉ de la CNI) ; les gates (vip_responds/
    ready_count) et `sleep` sont injectés. Renvoie les étapes franchies ; lève
    HaError au premier échec."""
    steps: list[HaStep] = []
    ev = bootstrap_extravars(cp_ip, vip, vip_iface)

    # 1. Pré-init : checks → cri → kubeadm → control-planes.
    for pb in _PRE_INIT_PLAYBOOKS:
        _check(launch, f"{pb}.yaml", ev, "bootstrap-ha")
    steps.append(HaStep("pré-init", True, " → ".join(_PRE_INIT_PLAYBOOKS)))

    # 2. kube-vip AVANT l'init, en super-admin.conf (amorçage k8s ≥ 1.29).
    _check(
        launch,
        "kube-vip.yaml",
        {**ev, "kube_vip_kubeconfig_path": "/etc/kubernetes/super-admin.conf"},
        "kube-vip (super-admin)",
    )
    # 3. Init du CP primaire (controlPlaneEndpoint = la VIP, via kube-vip).
    _check(launch, "initialisation.yaml", ev, "kubeadm init via VIP")
    # 4. Bascule kube-vip sur admin.conf (régime permanent).
    _check(
        launch,
        "kube-vip.yaml",
        {**ev, "kube_vip_kubeconfig_path": "/etc/kubernetes/admin.conf"},
        "kube-vip (admin)",
    )
    steps.append(HaStep("init via VIP", True, "kube-vip super-admin→admin, init OK"))

    # 4b. GATE VIP : la bascule recrée le pod kube-vip → attendre que la VIP réponde
    # avant la CNI (sinon l'apply des CRDs via la VIP court après une VIP retombée).
    gate_vip(vip, "cp1", vip_responds=vip_responds, sleep=sleep)
    steps.append(HaStep("gate VIP", True, f"VIP {vip} joignable"))

    # 5. DOUBLE GESTE de `phase_ha_cni` (ADR 0097 §2.b), DANS L'ORDRE bash :
    #    a) run_cni() pose Cilium (artefact bash dans la VM, irréductible §2.a) ;
    #    b) fetch_kubeconfig() rapatrie admin.conf vers le forward hôte (transport pur,
    #       sed-rewrite). Couvrir les DEUX ici est ce qui supprime le rappel `ha-cni`
    #       pour le kubeconfig — sinon la circularité résiduelle (Python→bash→Python)
    #       subsiste (§2.b). run_cni d'abord : le kubeconfig n'est valide qu'avec la CNI
    #       posée (les nœuds ne deviennent Ready qu'après Cilium).
    run_cni()
    fetch_kubeconfig()
    _gate_nodes_ready(1, ready_count=ready_count, sleep=sleep)
    steps.append(HaStep("CNI + kubeconfig + primaire Ready", True, "1 CP Ready derrière la VIP"))
    return steps


def promote_control_plane(
    cp: str,
    member_index: int,
    control_hosts: list[str],
    vip: str,
    vip_iface: str,
    *,
    launch,
    set_inventory,
    ready_count,
    sleep,
) -> HaStep:
    """Promeut UN CP additionnel : ajoute `cp` au groupe control de l'inventaire,
    pose kube-vip (admin.conf) sur lui, puis join --control-plane — les deux
    `--limit cp` (le bootstrap ne mettait que le primaire dans control). Le rôle
    de join lit le PRIMAIRE via groups['control'][0] → il doit rester en tête.
    `member_index` = nombre de CP membres APRÈS cette promotion (gate Ready)."""
    # control = primaire + déjà promus + ce cp (primaire en tête, ADR du rôle).
    set_inventory(control_hosts)
    ev = join_extravars(vip, vip_iface)
    _check(
        launch,
        "kube-vip.yaml",
        {**ev, "kube_vip_kubeconfig_path": "/etc/kubernetes/admin.conf"},
        f"kube-vip {cp}",
        limit=cp,
    )
    _check(launch, "join-control-plane.yaml", ev, f"join {cp}", limit=cp)
    _gate_nodes_ready(member_index, ready_count=ready_count, sleep=sleep)
    return HaStep(f"promotion {cp}", True, f"{member_index} CP membres")


def run_ha_3cp(
    nodes: list[str],
    cp_ip: str,
    vip: str,
    vip_iface: str,
    *,
    launch,
    run_cni,
    set_inventory,
    vip_responds=vip_healthz,
    ready_count,
    etcd_output=etcd_health_output,
    sleep,
    fetch_kubeconfig=_noop_fetch_kubeconfig,
) -> HaResult:
    """Monte la topologie ha-3cp : bootstrap du primaire + promotion des CP
    additionnels un à un (gate etcd entre chaque). `set_inventory(control_hosts)`
    réécrit l'inventaire (le primaire reste en tête — le rôle de join lit
    groups['control'][0]). `run_cni` PUIS `fetch_kubeconfig` couvrent le DOUBLE
    GESTE de `phase_ha_cni` (ADR 0097 §2.b) ; les couvrir tous deux ici supprime le
    rappel `ha-cni` pour le kubeconfig. Toutes les I/O sont injectées → testable
    sans banc."""
    result = HaResult(vip=vip)
    primary = nodes[0]
    try:
        result.steps.extend(
            bootstrap_primary(
                cp_ip,
                vip,
                vip_iface,
                launch=launch,
                run_cni=run_cni,
                vip_responds=vip_responds,
                ready_count=ready_count,
                sleep=sleep,
                fetch_kubeconfig=fetch_kubeconfig,
            )
        )
        # Promotion des CP additionnels, un à un, gate etcd avant chaque.
        members = 1  # le primaire
        control_hosts = [primary]
        for cp in cp_join_order(nodes):
            gate_etcd(primary, members, etcd_output=etcd_output, sleep=sleep)
            members += 1
            control_hosts.append(cp)
            result.steps.append(
                promote_control_plane(
                    cp,
                    members,
                    list(control_hosts),
                    vip,
                    vip_iface,
                    launch=launch,
                    set_inventory=set_inventory,
                    ready_count=ready_count,
                    sleep=sleep,
                )
            )
        gate_etcd(primary, members, etcd_output=etcd_output, sleep=sleep)  # quorum final
        result.steps.append(HaStep("quorum final", True, f"{members} CP membres, quorum sain"))
    except (HaError, GateError) as exc:
        # HaError (playbook/Ready KO) ET GateError (VIP/etcd KO via gates.py) abortent
        # le montage de la même façon : étape « échec » consignée, build NON `built`.
        result.steps.append(HaStep("échec", False, str(exc)))
    return result
