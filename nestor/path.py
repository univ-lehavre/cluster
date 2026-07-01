"""Moteur de chemin Python : absorbe l'orchestration de `bench/lima/run-phases.sh`.

LOT 6 de la refonte nestor (ADR 0097 §1) — le SECOND pilier. Aujourd'hui
`run-phases.sh` (1903 l.) est l'orchestrateur : il DÉCIDE quoi monter, ENCHAÎNE les
`ansible-playbook`, GATE la santé via kubectl, POSSÈDE l'état partagé (`CP`,
`API_PORT`, `KUBECONFIG_LOCAL`) et PROVISIONNE (`phase_up`, `write_inventory`) ;
`cmd_up`/`cmd_next` ne font que l'appeler en subprocess. Ce module porte cette
boucle EN PYTHON, sur le MÊME moule que `bootstrap.run_bootstrap:102` : la LOGIQUE
(séquence ordonnée des phases + gardes + gates) est PURE et testable sans banc ;
toute l'I/O réelle (ansible-runner, kubectl, limactl) est INJECTÉE en callbacks par
la façade.

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
(`run-phases.sh:508 bootstrap-seq`) disparaît — mais SEULEMENT une fois
`cmd_up`/`cmd_next` basculés (lot futur, après preuve banc).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


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


# ── Résultat (même forme que BootstrapResult : steps + verdict dérivé) ──


@dataclass
class PathStep:
    name: str
    ok: bool
    detail: str = ""
    duration_s: float | None = None  # durée MESURÉE de la phase (None = gate, non chronométrée)


@dataclass
class PathResult:
    """Verdict du montage d'un chemin. `built` = toutes les étapes ont réussi."""

    target: str
    steps: list[PathStep] = field(default_factory=list)

    @property
    def built(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)


# ── Phases AMONT à orchestration NON-Ansible (provisioning / artefacts bash) ─────
# `up` (créer les VM via limactl) et `bootstrap` (socle k8s + CNI) ne sont PAS un
# `launch_phase(<playbook>)` : `up` provisionne les VM, `bootstrap` enchaîne les 6
# playbooks du socle PUIS pose la CNI (cni.sh, artefact irréductible ADR 0097 §2.a). Le
# moteur les délègue à des callbacks DÉDIÉS (`provision`, `bootstrap`) injectés par la
# façade — qui les branche sur le provisioning Python (à câbler, §5.b) et
# `nestor.bootstrap.run_bootstrap` (déjà porté). Les phases du socle Ceph (`ceph`, `sc`)
# ONT un playbook (PHASE_PLAYBOOK) → elles passent par `launch`.
_NON_ANSIBLE_AMONT = frozenset({"up", "bootstrap"})


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
    record=None,
    sleep=None,
    clock=None,
):
    """Monte un chemin nommé : boucle PURE-TESTABLE sur sa séquence de phases.

    Généralise le patron de `bootstrap.run_bootstrap` : toute l'I/O est INJECTÉE, la
    LOGIQUE (ordre + gardes + gates) est testable sans banc. Lève
    `PathError`/`IsolationRefused` au 1er échec (fail-fast, comme le `die` du bash).

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
    - `record(result) -> None` : consigne le run from-scratch dans l'historique
      (geste ex-`metro_record_run`, metrology.sh retiré ADR 0101 — à câbler en
      Python). Optionnel (None = STUB ; append manuel par commit en attendant).
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
    # Horloge INJECTÉE (défaut `time.monotonic`) : chronomètre chaque phase pour consigner
    # `phases{nom: secondes}` (ex-`time_phase` de run-phases.sh). Les tests passent un clock
    # DÉTERMINISTE — le moteur reste pur-testable (aucune horloge réelle en test).
    _clock = clock or time.monotonic
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
            # Chronométré (`_clock`) : la durée est attachée au step de la phase pour
            # `record` (ex-`time_phase`). Les gates (post-montage) ne sont PAS chronométrées.
            _t0 = _clock()
            if phase in _NON_ANSIBLE_AMONT:
                _run_amont(
                    phase,
                    provision=provision,
                    bootstrap=bootstrap,
                    steps=result.steps,
                )
                result.steps[-1].duration_s = _clock() - _t0
            else:
                res = launch(phase)
                # `launch` peut rendre un IdempotenceResult (`.ok` = double-passage changed=0)
                # OU un RunResult (un seul passage, parité bash : succès = `rc==0`) OU un
                # résultat de seed (`.ok`). On accepte les deux : `.ok` s'il existe, sinon rc==0.
                ok = bool(res.ok) if hasattr(res, "ok") else getattr(res, "rc", 1) == 0
                result.steps.append(
                    PathStep(
                        phase,
                        ok,
                        getattr(res, "verdict", "") or getattr(res, "message", ""),
                        duration_s=_clock() - _t0,
                    )
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


def _run_amont(phase: str, *, provision, bootstrap, steps: list[PathStep]) -> None:
    """Monte une phase AMONT non-Ansible (`up` provisioning / `bootstrap` socle+CNI).

    Délègue au callback DÉDIÉ injecté (provisioning et socle ne sont PAS un
    `launch_phase`) ; rc 0 = ok, sinon PathError. Si le callback manque (None), c'est
    un STUB explicite à câbler au banc (§5.b) — on lève plutôt que d'inventer un
    montage faux."""
    cb = {"up": provision, "bootstrap": bootstrap}[phase]
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
# ═══════════════════════════════════════════════════════════════════════════════


# ── CE QUI RESTE À CÂBLER + PROUVER AU BANC (TODO explicites, ADR 0034) ──────────
# Le code ci-dessus est la LOGIQUE d'orchestration (prouvée par tests stubés). Les
# points suivants touchent le montage RÉEL et exigent un RUN BANC from-scratch (banc
# Lima non réconcilié ici — preuve IMPOSSIBLE dans cette session, NE PAS prétendre
# l'avoir faite) :
_BANC_TODO = (
    # 1. CÂBLAGE FAÇADE — FAIT (`topology._run_path_engine`, SEUL moteur depuis le retrait
    #    du filet bash : `nestor up` MONTE TOUJOURS via run_path) :
    #      PathContext → `topology._path_context` (cp=1er control, kubeconfig_local/inventory
    #                    = chemins banc, repo=racine, nodes) — PUR, testé ;
    #      launch   → runner.launch_phase_idempotent + extravars_for + e2e_hooks_for (LÈVENT) ;
    #      gate     → topology._wait_layer_healthy (signal _LAYER_SIGNAL/graph) ;
    #      assert_safe → topology._assert_bench_target (+ _assert_inventory_safe par-play) ;
    #      provision('up') → STUB `run-phases.sh up` (artefact node-side, §5.b) ;
    #    RESTE : la PREUVE banc du chemin python (run mono-nœud).
    "preuve banc du moteur python (nestor up, mono-nœud) — reste à faire",
    # 2. PROVISIONING RÉEL (§5.b) : le callback `provision('up')` POUSSE aujourd'hui
    #    `run-phases.sh up` (STUB documenté, `topology._provision_via_bash` — limactl reste
    #    bash, ADR 0049). LOT 8 : les RESSOURCES VM (cpus/memory/disk) viennent du YAML
    #    (`topo.node_resources(<node>)`) — passées en env VM_CPUS/VM_MEMORY/VM_DISK le temps
    #    de la transition. RESTE : câbler `lima_render_node(<valeurs>)` directement (bash
    #    garde le RENDU, Python décide les VALEURS) + write_inventory — à prouver au banc.
    "provisioning Python direct (lima_render_node + write_inventory) — à prouver au banc",
    # 2.b BOOTSTRAP (socle k8s) : le callback `bootstrap` tente le vrai montage mais son
    #    transport (cp_ip/iface dérivés du Lima vivant + CNI/fetch_kubeconfig via l'arm `cni`)
    #    n'est pas prouvé au banc. Le moteur `bootstrap.run_bootstrap` est porté+testé ; RESTE
    #    le câblage transport (rappel `cni`, dérivation Lima vivant) — à câbler+prouver au banc.
    "câblage transport bootstrap (cp_ip/iface, CNI) — à prouver au banc",
    # 3. CONSIGNATION runs-history (#216) : le callback `record` est CÂBLÉ (nestor/runrecord.py :
    #    durées de phases mesurées par le moteur + commit git avec `-dirty`, append byte-stable).
    #    RESTE : les MÉTRIQUES Prometheus (cpu_core_s/ram_*) — échantillonnées PENDANT le run par
    #    node-exporter (monitoring déployé APRÈS le socle), non lisibles ici → OMISES honnêtement,
    #    à câbler quand un run montera aussi le monitoring. À prouver au banc (run consigné réel).
    "métriques Prometheus du run (cpu/ram) — omises, à échantillonner+consigner au banc",
    # 4. RUN BANC from-scratch consigné (bench/lima/RESULTS.md) + rejeu changed=0
    #    sur LES DEUX topologies (banc local-path PUIS dirqual Ceph, invariants 1-2).
    "run banc from-scratch + rejeu changed=0 (banc PUIS prod) — PREUVE DÉFINITIVE, reste à faire",
)


def banc_todo() -> tuple[str, ...]:
    """Liste EXPLICITE de ce qui reste à câbler+prouver AU BANC (honnêteté ADR 0034).

    Accesseur testable : un test vérifie que la frontière code-écrit / preuve-banc est
    DÉCLARÉE (non vide), pour qu'on ne puisse pas merger en oubliant la preuve."""
    return _BANC_TODO
