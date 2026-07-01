"""Tests de la FAÇADE du moteur de chemin Python (`nestor.path.run_path`) — LOT 6 (ADR 0097).

Câblage façade du SEUL moteur de montage (`scripts/topology.py:_run_path_engine` /
`_path_context` / `_provision_via_bash`) : depuis le retrait du filet bash, `nestor up`
MONTE TOUJOURS via ce moteur Python. Ces tests sont PURS (I/O injectée : runner stubé,
gates stubées, run-phases.sh espionné) — ZÉRO cluster, ZÉRO provisionnement réel (filet
de sécurité hérité de test_topology_cli).

Ils couvrent la LOGIQUE de câblage (le moteur lui-même est testé dans test_path.py) :
  - `_path_context` dérive PathContext de la topo (cp = 1er control, PAS codé en dur) ;
  - `cmd_up` route vers `_run_path_engine` (seul moteur ; run-phases.sh PAS appelé) ;
  - les callbacks appellent les BONNES briques (launch_phase_idempotent, gate, provision) ;
  - assert_safe REFUSE une cible non-banc (garde d'isolation à chaque phase) ;
  - les hooks e2e (dataops) LÈVENT (stub honnête) → le montage s'arrête net (pas de fallback).

⚠️ HONNÊTETÉ (ADR 0034) : ces tests prouvent la LOGIQUE de câblage, PAS le montage réel au
banc. La preuve définitive du chemin Python est un run banc mono-nœud du mainteneur
(cf. `nestor.path.banc_todo`). NE PRÉTENDS JAMAIS l'avoir prouvé ici.
"""

import base64
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_ROOT = os.path.join(os.path.dirname(__file__), "..")

# scripts/topology.py : point d'entrée chargé par CHEMIN (dossier scripts/ sans __init__),
# comme test_topology_cli — la façade vit ICI (closures sur les fonctions privées de cette
# façade), d'où le chargement par chemin plutôt qu'un import de paquet.
_SPEC = importlib.util.spec_from_file_location(
    "topology_cli_facade", os.path.join(_ROOT, "scripts", "topology.py")
)
cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cli)

from nestor import phases as _phases  # noqa: E402
from nestor import runner as _runner  # noqa: E402
from nestor.model import topology_from_dict  # noqa: E402

# VRAI subprocess.run capté AVANT tout stub (les tests qui espionnent le réinstallent).
_REAL_SUBPROCESS_RUN = cli.subprocess.run

# ── Blindage anti-provisionnement (filet de sécurité module, copié de test_topology_cli) ──
# Le mainteneur PEUT avoir un banc Lima RÉEL (`.kubeconfigs/banc.config` présent) : sans
# ce filet, un test qui atteint cmd_up/`provision` lancerait un VRAI `run-phases.sh up`
# (limactl) et provisionnerait des VMs en silence. setUpModule installe un DEFAULT-DENY : tout
# appel subprocess de provisionnement RÉEL échoue bruyamment (CI rouge). Les tests qui veulent
# observer un argv réinstallent leur _spy par-dessus ; leur addCleanup restaure ce garde-fou.
_FORBIDDEN_TOKENS = ("run-phases.sh", "limactl", "ansible-runner")


def _deny_run(argv, *a, **k):
    flat = " ".join(map(str, argv)) if isinstance(argv, (list, tuple)) else str(argv)
    if any(tok in flat for tok in _FORBIDDEN_TOKENS) or ("kubectl" in flat and "scale" in flat):
        raise AssertionError(
            f"TEST NON BLINDÉ : appel subprocess RÉEL de provisionnement intercepté — {flat!r}."
        )
    return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")


def _engine(*a, **k):
    """Appelle `cli._run_path_engine` en AVALANT son stdout (la façade `print` le plan/les
    phases — légitime en vrai `nestor up`, parasite dans la sortie de test). Renvoie le code."""
    with contextlib.redirect_stdout(io.StringIO()):
        return cli._run_path_engine(*a, **k)


def setUpModule():
    cli.subprocess.run = _deny_run


def tearDownModule():
    cli.subprocess.run = _REAL_SUBPROCESS_RUN


def _tmp(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _capture(argv):
    """Lance cli.main(argv) ; renvoie (code, stdout, stderr). Isole os.environ (la façade
    peut poser KUBECONFIG, qui fuiterait vers les tests suivants et fausserait la garde)."""
    saved_env = os.environ.copy()
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
    return code, out.getvalue(), err.getvalue()


# Topo BANC mono-nœud (target_kind: bench) : cp1 control+worker, local-path, AVEC une couche
# applicative (storage-simple) déclarée → la séquence a un play unitaire (storage-simple) APRÈS
# le socle (up, bootstrap). Le chemin du moteur Python se TESTE au banc mono-nœud (ADR 0097).
_LIMA_SOLO = (
    "catalog: {topology: solo}\n"
    "layers: [storage-simple]\n"
    "nodes:\n  - {name: cp1, roles: [control, worker]}\n"
    "storage: {backend: local-path}\ntarget_kind: bench\n"
)

# Topo BANC à DEUX nœuds (cp choisi PARMI eux) : node-a worker, cp-b control. Sert à
# prouver que `_path_context.cp` = 1er CONTROL (pas le 1er nœud), DÉRIVÉ, jamais `cp1` codé.
_LIMA_CP_SECOND = (
    "catalog: {topology: duo, profile: base}\n"
    "nodes:\n"
    "  - {name: node-a, roles: [worker]}\n"
    "  - {name: cp-b, roles: [control, worker]}\n"
    "storage: {backend: local-path}\ntarget_kind: bench\n"
)


def _topo(yaml_text: str):
    import yaml

    return topology_from_dict(yaml.safe_load(yaml_text))


class PathContextDerivation(unittest.TestCase):
    """`_path_context` dérive PathContext de la TOPOLOGIE (PUR, ADR 0097 §5.a)."""

    def test_cp_is_first_control_not_hardcoded(self):
        # cp = 1er nœud `control`, même s'il n'est PAS le 1er nœud déclaré (jamais `cp1` codé).
        # `_path_context` reçoit l'inventaire EN PARAMÈTRE (ADR 0098) — il reste pur.
        ctx = cli._path_context(_topo(_LIMA_CP_SECOND), cli._BENCH_INVENTORY)
        self.assertEqual(ctx.cp, "cp-b")

    def test_cp_solo(self):
        ctx = cli._path_context(_topo(_LIMA_SOLO), cli._BENCH_INVENTORY)
        self.assertEqual(ctx.cp, "cp1")

    def test_api_port_and_repo_and_nodes(self):
        ctx = cli._path_context(_topo(_LIMA_CP_SECOND), cli._BENCH_INVENTORY)
        self.assertEqual(ctx.api_port, 6443)
        # repo = racine ABSOLUE du dépôt (pour résoudre les playbooks).
        self.assertTrue(os.path.isabs(ctx.repo))
        # nodes = tuple des nœuds attendus Ready (ordre déclaré).
        self.assertEqual(ctx.nodes, ("node-a", "cp-b"))

    def test_inventory_is_passed_through_kubeconfig_local_is_bench(self):
        # `inventory` est le chemin PASSÉ par l'appelant (ADR 0098 : dérivé du `with
        # _inventory_for`) ; `kubeconfig_local` reste le chemin banc figé.
        ctx = cli._path_context(_topo(_LIMA_SOLO), cli._BENCH_INVENTORY)
        self.assertEqual(ctx.kubeconfig_local, cli._BENCH_KUBECONFIG)
        self.assertEqual(ctx.inventory, cli._BENCH_INVENTORY)


class EngineRouting(unittest.TestCase):
    """`cmd_up` MONTE TOUJOURS via le moteur Python `_run_path_engine` — le filet bash
    `--engine=bash`/run-phases.sh a été RETIRÉ (un seul moteur, ADR 0097)."""

    def setUp(self):
        # Garde d'isolation banc : on neutralise pour que cmd_up atteigne le routage (la
        # garde elle-même est testée à part). On rend la cible "banc" et le confirm auto.
        self._patch(cli, "_assert_bench_target", lambda *_a, **_k: None)
        # Sondes RÉELLES du plan annoté (preview) → neutres (pas de cluster en test).
        self._patch(cli, "_ready_nodes", lambda *_a, **_k: [])
        self._patch(cli, "_real_vms", lambda *_a, **_k: [])

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def _spy_runphases(self, rc=0):
        """Espionne run-phases.sh ; laisse passer le GRAPHE (rollback-lib) au vrai subprocess
        (déterministe, local) pour que `expected_phase_sequence` dérive la séquence."""
        calls = []
        real = _REAL_SUBPROCESS_RUN

        def _spy(cmd, *a, **k):
            argv = cmd if isinstance(cmd, (list, tuple)) else [cmd]
            if any("run-phases.sh" in str(c) for c in argv):
                calls.append(list(argv))
                return subprocess.CompletedProcess(args=cmd, returncode=rc)
            return real(cmd, *a, **k)

        orig = cli.subprocess.run
        cli.subprocess.run = _spy
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        return calls

    def _spy_engine(self):
        """Espionne `_run_path_engine` (le SEUL moteur) : renvoie les appels."""
        calls = []

        def _spy(topo, target, seq, stack_name, a_appliquer=None):
            calls.append((target, list(seq), stack_name, a_appliquer))
            return 0

        orig = cli._run_path_engine
        cli._run_path_engine = _spy
        self.addCleanup(setattr, cli, "_run_path_engine", orig)
        return calls

    def test_up_routes_to_python_engine_not_run_phases(self):
        # `nestor up` route vers le moteur Python (`_run_path_engine`) et n'appelle PAS
        # run-phases.sh pour le montage (le filet bash a été retiré — un seul moteur).
        rp_calls = self._spy_runphases()
        eng_calls = self._spy_engine()
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["up", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(eng_calls), 1)  # moteur python appelé (seul moteur)
        self.assertEqual(rp_calls, [])  # run-phases.sh PAS appelé pour le montage

    def test_engine_receives_derived_sequence(self):
        # Le moteur reçoit la séquence DÉRIVÉE de la topo (graphe atomique) : topo lima →
        # commence par `up`, et la layer déclarée (storage-simple) y figure.
        self._spy_runphases()
        eng_calls = self._spy_engine()
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["up", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(eng_calls), 1)
        target, seq, _stack, _a_appliquer = eng_calls[0]
        self.assertEqual(target, "layers")
        self.assertEqual(seq[0], "up")  # topo lima → la séquence commence par `up`
        self.assertIn("storage-simple", seq)  # layer déclarée → couche storage-simple


class CallbacksWireRealBricks(unittest.TestCase):
    """Les callbacks de `_run_path_engine` appellent les BONNES briques (I/O stubée)."""

    def setUp(self):
        # Garde neutralisée (testée à part), gates stubées (pas de cluster).
        self._patch(cli, "_assert_bench_target", lambda *_a, **_k: None)
        self._patch(cli, "_assert_inventory_safe", lambda *_a, **_k: None)
        # gate de santé → toujours saine (le moteur veut un bool ; pas de kubectl en test).
        self._patch(cli, "_wait_layer_healthy", lambda *_a, **_k: True)

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def _stub_idempotent(self, calls):
        """Stub `runner.launch_phase` (UN passage + gate, parité bash — plus de double-passage
        `changed=0` qui faussait les builds à tag mutable). Enregistre (playbook, extravars)."""

        def _fake(playbook, extravars, private_data_dir, inventory, **kw):
            calls.append({"playbook": playbook, "extravars": extravars, "inventory": inventory})
            return _runner.RunResult(rc=0, status="successful", changed=0)

        orig = cli._runner.launch_phase
        cli._runner.launch_phase = _fake
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)

    def test_launch_calls_idempotent_with_restricted_extravars(self):
        # Une séquence d'UNE seule couche applicative (storage-simple) : le callback `launch`
        # doit appeler launch_phase (un passage) avec les `-e` RESTREINTS de la phase.
        launch_calls = []
        self._stub_idempotent(launch_calls)
        topo = _topo(_LIMA_SOLO)
        code = _engine(topo, "layers", ["storage-simple"], "solo")
        self.assertEqual(code, 0)
        self.assertEqual(len(launch_calls), 1)
        # Playbook = celui du plan (storage-simple → bootstrap/local-path.yaml), RÉSOLU
        # relatif à private_data_dir (bootstrap/) → `local-path.yaml` (comme _monter_phase).
        expected_pb = os.path.relpath(
            os.path.join(_ROOT, _phases.phase_plan("storage-simple").playbook),
            os.path.join(_ROOT, "bootstrap"),
        )
        self.assertEqual(launch_calls[0]["playbook"], expected_pb)
        # extravars = ceux de extravars_for (dataops_k8s_host=localhost commun ; storage-simple
        # n'a aucune clé dérivée → seul le commun).
        self.assertEqual(launch_calls[0]["extravars"], _phases.extravars_for("storage-simple", {}))
        # Inventaire = celui du banc (PathContext), pas la prod.
        self.assertEqual(launch_calls[0]["inventory"], cli._BENCH_INVENTORY)

    def test_provision_up_delegates_to_run_phases_up(self):
        # La phase amont `up` → provision → STUB `run-phases.sh up` (limactl bash, §5.b).
        rp_calls = []

        def _spy(cmd, *a, **k):
            argv = cmd if isinstance(cmd, (list, tuple)) else [cmd]
            if any("run-phases.sh" in str(c) for c in argv):
                rp_calls.append({"argv": list(argv), "env": k.get("env", {})})
                return subprocess.CompletedProcess(args=cmd, returncode=0)
            return _REAL_SUBPROCESS_RUN(cmd, *a, **k)

        orig = cli.subprocess.run
        cli.subprocess.run = _spy
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        topo = _topo(_LIMA_SOLO)
        code = _engine(topo, "layers", ["up"], "solo")
        self.assertEqual(code, 0)
        self.assertEqual(len(rp_calls), 1)
        self.assertIn("up", rp_calls[0]["argv"])
        # ADR 0102 volet C : plus de VM_CPUS/VM_MEMORY/VM_DISK ni WITH_CEPH globaux en
        # env — les ressources (et disques) sont PAR NŒUD dans le canal NODES_OVERRIDE.
        env = rp_calls[0]["env"]
        self.assertNotIn("VM_CPUS", env)
        self.assertNotIn("VM_MEMORY", env)
        self.assertNotIn("WITH_CEPH", env)
        # NODES_OVERRIDE porte le format enrichi `nom|role|cpus,memory,disk|disques`.
        # _LIMA_SOLO = 1 nœud control+worker, local-path (pas de disque → 4e champ vide).
        self.assertEqual(env["NODES_OVERRIDE"], "cp1|control|4,12GiB,40GiB|")

    def test_provision_propagates_failure(self):
        # `run-phases.sh up` échoue → PathError fail-fast → code 1 (jamais de fallback).
        def _spy(cmd, *a, **k):
            argv = cmd if isinstance(cmd, (list, tuple)) else [cmd]
            if any("run-phases.sh" in str(c) for c in argv):
                return subprocess.CompletedProcess(args=cmd, returncode=7)
            return _REAL_SUBPROCESS_RUN(cmd, *a, **k)

        orig = cli.subprocess.run
        cli.subprocess.run = _spy
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        topo = _topo(_LIMA_SOLO)
        code = _engine(topo, "layers", ["up"], "solo")
        self.assertEqual(code, 1)

    def test_e2e_hook_stubbed_stops_net(self):
        # dataops joue DEUX hooks e2e : `chain_emit_and_verify` (CÂBLÉ) puis
        # `egress_internet_check` (encore STUBÉ → LÈVE). Même si le 1er passe, le 2nd stoppe
        # NET le montage (code 1) — PAS de verdissement à tort (honnêteté ADR 0034). On stube
        # le hook CÂBLÉ en succès (pas d'I/O kubectl en test) pour isoler le rôle du stub.
        self._stub_idempotent([])
        self._patch(cli, "_chain_emit_and_verify_banc", lambda *_a, **_k: None)
        topo = _topo(_LIMA_SOLO)
        code = _engine(topo, "layers", ["dataops"], "solo")
        self.assertEqual(code, 1)

    def test_chain_hook_routed_to_real_facade_impl(self):
        # Le moteur SUBSTITUE l'implémentation RÉELLE de façade (`_chain_emit_and_verify_banc`)
        # au STUB du registre pour `dataops_chain_emit_and_verify` — il ne joue plus le stub
        # `phases.E2E_HOOKS` (qui lèverait E2EHookStubbed). On espionne l'impl façade : si le
        # play réussit, elle est appelée ; on neutralise l'egress (stub) pour s'arrêter avant.
        self._stub_idempotent([])
        called = []
        self._patch(cli, "_chain_emit_and_verify_banc", lambda *_a, **_k: called.append(True))
        # On laisse l'egress lever (code 1) ; ce qui compte : le hook CÂBLÉ a bien été joué.
        topo = _topo(_LIMA_SOLO)
        _engine(topo, "layers", ["dataops"], "solo")
        self.assertEqual(called, [True], "le hook chain réel (façade) doit être joué, pas le stub")


class BootstrapCallbackWiring(unittest.TestCase):
    """Le callback `bootstrap` câble le socle k8s+CNI (ADR 0097 §5.b) — I/O STUBÉE.

    On NE prouve PAS le montage réel (pas de banc ici, ADR 0034) : on prouve le CÂBLAGE
    (quelles briques sont appelées, dans quel ordre, avec quels arguments dérivés). Le
    runner (Ansible) et run-phases.sh (inventaire/facts/CNI) sont espionnés ; cp_ip est
    dérivé du contrat machine `emit_facts` (stub `CP_IP=…`)."""

    def setUp(self):
        # Gardes neutralisées (testées à part), gates → saines (pas de cluster en test).
        self._patch(cli, "_assert_bench_target", lambda *_a, **_k: None)
        self._patch(cli, "_assert_inventory_safe", lambda *_a, **_k: None)
        self._patch(cli, "_wait_layer_healthy", lambda *_a, **_k: True)

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def _spy(
        self,
        *,
        facts_rc=0,
        facts_out="CP_IP=10.0.0.11\nL2_IFACE=lima0\n",
        inv_rc=0,
        cni_rc=0,
        launch_rc=0,
    ):
        """Espionne run-phases.sh (inventory/facts/cni) ET runner.launch_phase. Renvoie un
        dict de listes d'appels pour les assertions. Le GRAPHE (rollback-lib, déterministe)
        passe au vrai subprocess pour que `expected_phase_sequence` dérive la séquence."""
        rp_calls = []
        launch_calls = []
        real = _REAL_SUBPROCESS_RUN

        def _spy_run(cmd, *a, **k):
            argv = cmd if isinstance(cmd, (list, tuple)) else [cmd]
            if any("run-phases.sh" in str(c) for c in argv):
                arm = argv[2] if len(argv) > 2 else ""
                rp_calls.append(list(argv))
                if arm == "facts":
                    return subprocess.CompletedProcess(argv, facts_rc, stdout=facts_out, stderr="")
                if arm == "inventory":
                    return subprocess.CompletedProcess(argv, inv_rc, stdout="", stderr="")
                if arm == "cni":
                    return subprocess.CompletedProcess(argv, cni_rc, stdout="", stderr="")
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
            return real(cmd, *a, **k)

        def _spy_launch(playbook, extravars, *a, **k):
            launch_calls.append({"playbook": playbook, "extravars": extravars})
            return _runner.RunResult(rc=launch_rc, status="successful", changed=0)

        orig_run, orig_launch = cli.subprocess.run, cli._runner.launch_phase
        cli.subprocess.run = _spy_run
        cli._runner.launch_phase = _spy_launch
        self.addCleanup(setattr, cli.subprocess, "run", orig_run)
        self.addCleanup(setattr, cli._runner, "launch_phase", orig_launch)
        return {"rp": rp_calls, "launch": launch_calls}

    def _arms(self, rp_calls):
        return [c[2] for c in rp_calls if len(c) > 2]

    def test_bootstrap_wires_inventory_facts_socle_cni(self):
        # Le câblage complet : inventaire écrit (bash) → faits dérivés (facts) → 6 playbooks
        # du socle (runner) avec `-e control_plane_ip=<cp_ip dérivé>` → CNI (arm `cni`). Topo
        # DUO (un worker pur) → has_workers=True → join-workers.yaml présent (6 playbooks).
        spy = self._spy()
        code = _engine(_topo(_LIMA_CP_SECOND), "layers", ["bootstrap"], "duo")
        self.assertEqual(code, 0)
        arms = self._arms(spy["rp"])
        # Inventaire écrit AVANT les faits, CNI en dernier (arm `cni` = CNI + kubeconfig).
        self.assertEqual(arms, ["inventory", "facts", "cni"])
        # inventory <control_csv> <workers_csv> : cp-b control, node-a worker (dérivés de la topo).
        inv = next(c for c in spy["rp"] if c[2] == "inventory")
        self.assertEqual(inv[3], "cp-b")
        self.assertEqual(inv[4], "node-a")
        # L'arm `cni` ne prend AUCUN argument (geste 100 % CNI : le vestige `ha-cni <iface>`
        # a été renommé `cni`, plus de VIP/iface — exposition L4 NodePort ADR 0092).
        cni = next(c for c in spy["rp"] if c[2] == "cni")
        self.assertEqual(len(cni), 3)  # ["bash", run-phases.sh, "cni"] — pas d'argument iface
        # 6 playbooks du socle (has_workers=True), dans l'ordre, avec le cp_ip DÉRIVÉ (pas codé).
        self.assertEqual(
            [c["playbook"] for c in spy["launch"]],
            cli._bootstrap.bootstrap_playbooks(has_workers=True),
        )
        for c in spy["launch"]:
            self.assertEqual(c["extravars"], {"control_plane_ip": "10.0.0.11"})

    def test_bootstrap_solo_omits_join_workers(self):
        # Topo SOLO (cp1 control+worker, aucun worker PUR) → has_workers=False → join-workers
        # OMIS (5 playbooks). La DÉCISION est en Python (connaît la topo), ADR 0097.
        spy = self._spy()
        code = _engine(_topo(_LIMA_SOLO), "layers", ["bootstrap"], "solo")
        self.assertEqual(code, 0)
        self.assertEqual(
            [c["playbook"] for c in spy["launch"]],
            cli._bootstrap.bootstrap_playbooks(has_workers=False),
        )
        self.assertNotIn("join-workers.yaml", [c["playbook"] for c in spy["launch"]])
        # Solo : inventory sans CSV worker (un seul control+worker → workers vides côté bash).
        inv = next(c for c in spy["rp"] if c[2] == "inventory")
        self.assertEqual(inv[3], "cp1")
        self.assertEqual(len(inv), 4)  # pas d'argument workers (worker_nodes vide)

    def test_bootstrap_socle_failure_stops_net(self):
        # Un playbook du socle ÉCHOUE (launch_rc=2) → BootstrapError → PathError fail-fast →
        # code 1. AUCUNE couche applicative montée après (sentinelle launch_phase_idempotent).
        def _boom_layer(*_a, **_k):
            raise AssertionError("couche applicative montée malgré l'échec du socle")

        self._patch(cli._runner, "launch_phase", _boom_layer)
        spy = self._spy(launch_rc=2)
        code = _engine(_topo(_LIMA_SOLO), "layers", ["bootstrap", "storage-simple"], "solo")
        self.assertEqual(code, 1)
        # Le 1er playbook échoue → fail-fast : un seul launch, pas de CNI (arm `cni` absent).
        self.assertEqual(len(spy["launch"]), 1)
        self.assertNotIn("cni", self._arms(spy["rp"]))

    def test_bootstrap_facts_failure_stops_net(self):
        # `run-phases.sh facts` échoue (banc non provisionné) → PathError → code 1, AVANT tout
        # playbook (on ne monte pas le socle sans cp_ip).
        spy = self._spy(facts_rc=3, facts_out="")
        code = _engine(_topo(_LIMA_SOLO), "layers", ["bootstrap"], "solo")
        self.assertEqual(code, 1)
        self.assertEqual(spy["launch"], [])

    def test_bootstrap_empty_cp_ip_stops_net(self):
        # facts rend rc=0 mais CP_IP vide (IP user-v2 pas encore posée) → PathError honnête
        # (on n'invente pas un advertiseAddress vide), pas de playbook lancé.
        spy = self._spy(facts_out="L2_IFACE=lima0\n")
        code = _engine(_topo(_LIMA_SOLO), "layers", ["bootstrap"], "solo")
        self.assertEqual(code, 1)
        self.assertEqual(spy["launch"], [])

    def test_cni_failure_stops_net(self):
        # Les 6 playbooks passent mais la CNI (arm `cni`) échoue → BootstrapError → PathError →
        # code 1 (le socle n'est pas « monté » sans CNI).
        spy = self._spy(cni_rc=5)
        code = _engine(_topo(_LIMA_SOLO), "layers", ["bootstrap"], "solo")
        self.assertEqual(code, 1)
        self.assertIn("cni", self._arms(spy["rp"]))

    def test_up_then_bootstrap_then_layer_chains(self):
        # Le chemin up→bootstrap→couche enchaîne : provision (run-phases.sh up, stub) →
        # bootstrap (socle+CNI, stub) → 1re couche applicative (storage-simple, idempotent).
        spy = self._spy()

        # provision : run-phases.sh up renvoyé 0 par le spy ci-dessus (arm "up" → défaut 0).
        # couche applicative : launch_phase (un passage) stubé ok.
        layer_calls = []

        def _fake_idem(playbook, extravars, *a, **k):
            layer_calls.append(playbook)
            return _runner.RunResult(rc=0, status="successful", changed=0)

        self._patch(cli._runner, "launch_phase", _fake_idem)
        code = _engine(_topo(_LIMA_SOLO), "layers", ["up", "bootstrap", "storage-simple"], "solo")
        self.assertEqual(code, 0)
        # provision (up) puis bootstrap (inventory/facts/cni) ont bien été appelés.
        arms = self._arms(spy["rp"])
        self.assertIn("up", arms)
        self.assertEqual(arms[arms.index("up") + 1 :], ["inventory", "facts", "cni"])
        # La couche applicative storage-simple a été montée APRÈS le socle. Les playbooks du
        # bootstrap passent AUSSI par launch_phase (même brique depuis la bascule 1-passage) :
        # 5 playbooks socle (checks/cri/kubeadm/control-planes/initialisation — join-workers
        # OMIS car control unique sans worker) + storage-simple, qui est le DERNIER launch.
        self.assertIn("local-path.yaml", layer_calls[-1])  # storage-simple → local-path.yaml
        self.assertEqual(len(layer_calls), 6)  # 5 playbooks socle + storage-simple


class AssertSafeIsolation(unittest.TestCase):
    """assert_safe REFUSE une cible non-banc (garde d'isolation, ADR 0053, à CHAQUE phase).

    Le mainteneur a un banc Lima RÉEL ici (`_BENCH_KUBECONFIG` présent) — on ne peut donc PAS
    faire refuser `_assert_bench_target` par l'absence du banc sans toucher l'environnement. On
    teste le CÂBLAGE (le moteur route un REFUS vers un arrêt net) en STUBANT `_assert_bench_target`
    pour qu'il LÈVE `_UsageError`, comme il le ferait face à une cible prod (la LOGIQUE de la garde
    elle-même est testée dans test_topology_cli)."""

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def test_refusal_propagates_and_no_play_launched(self):
        # `_assert_bench_target` LÈVE (cible non sûre) → le callback assert_safe lève → le
        # moteur wrappe en IsolationRefused → `_run_path_engine` re-lève en _UsageError.
        # AUCUN play lancé, AUCUNE VM touchée (sentinelles launch + provision).
        def _refuse(action, *_a, **_k):
            raise cli._UsageError(f"REFUS : `{action}` cible non-banc (test)")

        self._patch(cli, "_assert_bench_target", _refuse)
        self._patch(cli, "_wait_layer_healthy", lambda *_a, **_k: True)

        def _boom_launch(*_a, **_k):
            raise AssertionError("launch lancé malgré le REFUS d'isolation")

        def _boom_prov(*_a, **_k):
            raise AssertionError("provision lancé malgré le REFUS d'isolation")

        self._patch(cli._runner, "launch_phase", _boom_launch)
        self._patch(cli, "_provision_via_bash", _boom_prov)
        with self.assertRaises(cli._UsageError):
            _engine(_topo(_LIMA_SOLO), "layers", ["up", "storage-simple"], "solo")

    def test_refusal_via_main_maps_to_code_2(self):
        # Bout-en-bout par main() : la garde top-level de cmd_up (`_assert_bench_target`) LÈVE
        # → main mappe _UsageError en code 2. La garde d'isolation s'applique AVANT le montage
        # (seul moteur Python depuis le retrait du filet bash).
        def _refuse(action, *_a, **_k):
            raise cli._UsageError(f"REFUS : `{action}` cible non-banc (test)")

        self._patch(cli, "_assert_bench_target", _refuse)
        self._patch(cli, "_ready_nodes", lambda *_a, **_k: [])
        self._patch(cli, "_real_vms", lambda *_a, **_k: [])
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        code, _, err = _capture(["up", "-f", path, "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("REFUS", err)


class SeedPhaseWiring(unittest.TestCase):
    """La phase DÉLÉGUÉE `gitops-seed` (playbook=None) est routée vers `seed.run_seed`,
    pas vers un playbook — et ne crashe PLUS au montage (TypeError os.path.join(None)).

    On STUBE le `do(step)` réel (`_seed_do_banc`) et la garde (`_assert_bench_target`) pour
    prouver le CÂBLAGE + le fail-fast, ZÉRO Gitea réel (honnêteté ADR 0034). Le seed banc
    réel (gitea-init) se prouve au banc (cf. `cli._seed_banc_todo`)."""

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def _patch_dict_item(self, mapping, key, value):
        orig = mapping[key]
        mapping[key] = value
        self.addCleanup(mapping.__setitem__, key, orig)

    def setUp(self):
        # Gardes neutralisées (testées à part), gate gitops-seed → saine (pas de cluster).
        self._patch(cli, "_assert_bench_target", lambda *_a, **_k: None)
        self._patch(cli, "_assert_inventory_safe", lambda *_a, **_k: None)
        self._patch(cli, "_wait_layer_healthy", lambda *_a, **_k: True)
        # Gate « gitea/argocd Ready » (rollout status) → succès par défaut (pas de cluster).
        # Un test la fait échouer explicitement pour prouver le blocage avant les steps.
        self._patch(cli, "_kubectl", lambda *_a, **_k: subprocess.CompletedProcess([], 0, "", ""))

    def _stub_do(self, *, verdict_by_step=None):
        """Stub `_seed_do_banc` → un `do(step)` injecté (zéro kubectl/Gitea). Enregistre les
        steps vus ; `verdict_by_step` permet de faire échouer un step précis (fail-fast)."""
        seen = []
        verdicts = verdict_by_step or {}

        def _fake_do_factory(topo, config):
            def do(step):
                seen.append(step)
                return verdicts.get(step, True)

            return do

        self._patch(cli, "_seed_do_banc", _fake_do_factory)
        return seen

    def test_gitops_seed_routes_to_run_seed_not_playbook(self):
        # gitops-seed (playbook=None) → seed.run_seed, JAMAIS launch_phase_idempotent (qui
        # ferait os.path.join(_ROOT, None) → TypeError). Sentinelle sur le runner.
        def _boom_play(*_a, **_k):
            raise AssertionError("gitops-seed routé vers un playbook (launch_phase)")

        self._patch(cli._runner, "launch_phase", _boom_play)
        seen = self._stub_do()
        code = _engine(_topo(_LIMA_SOLO), "layers", ["gitops-seed"], "solo")
        self.assertEqual(code, 0)
        # Les 7 étapes du seed banc ont été jouées DANS L'ORDRE (via run_seed → do).
        from nestor import seed as _seed

        self.assertEqual(seen, list(_seed.seed_steps("banc")))

    def test_playbook_none_does_not_crash(self):
        # Régression directe du crash : la phase à playbook=None ne lève PAS de TypeError ;
        # elle est montée (code 0) via le câblage seed.
        self._stub_do()
        try:
            code = _engine(_topo(_LIMA_SOLO), "layers", ["gitops-seed"], "solo")
        except TypeError as exc:  # pragma: no cover — le bug d'origine
            self.fail(f"playbook=None a crashé (os.path.join(_ROOT, None)) : {exc}")
        self.assertEqual(code, 0)

    def test_banc_guard_is_wired(self):
        # La garde BANC est BRANCHÉE : `_assert_bench_target` est appelée pour gitops-seed
        # (via assert_safe du moteur ET via assert_target du seed). On compte ses appels.
        guard_calls = []
        self._patch(cli, "_assert_bench_target", lambda action, *a, **k: guard_calls.append(action))
        self._stub_do()
        code = _engine(_topo(_LIMA_SOLO), "layers", ["gitops-seed"], "solo")
        self.assertEqual(code, 0)
        # Au moins une fois (assert_safe en tête de phase + assert_target dans run_seed).
        self.assertTrue(guard_calls)
        self.assertTrue(all("gitops-seed" in a for a in guard_calls))

    def test_guard_refused_maps_to_code_2(self):
        # La garde banc REFUSE (cible prod) → SeedGuardRefused → IsolationRefused → _UsageError
        # → code 2. AUCUN step seed exécuté (la garde protège en amont). On prouve le MAPPING
        # SeedGuardRefused → code 2 (le câblage assert_target=_assert_bench_target est prouvé
        # par test_banc_guard_is_wired) : run_seed lève le refus AVANT tout step.
        from nestor import seed as _seed

        seen = self._stub_do()

        def _run_seed_refuses(kind, config, *, assert_target, do):
            self.assertEqual(kind, "banc")  # le seed monté est bien le banc
            raise _seed.SeedGuardRefused("garde banc refuse la prod (test)")

        # `_launch_seed` résout `_seed.run_seed` = attribut du module `nestor.seed` (= cli._seed).
        self._patch(cli._seed, "run_seed", _run_seed_refuses)
        with self.assertRaises(cli._UsageError):
            _engine(_topo(_LIMA_SOLO), "layers", ["gitops-seed"], "solo")
        self.assertEqual(seen, [])

    def test_failed_step_fails_fast_code_1(self):
        # Un step KO → SeedError → PathError fail-fast → code 1 (aucun fallback bash).
        seen = self._stub_do(verdict_by_step={"org-repo": False})
        code = _engine(_topo(_LIMA_SOLO), "layers", ["gitops-seed"], "solo")
        self.assertEqual(code, 1)
        # On s'est arrêté SUR org-repo (3e step) — pas de step au-delà.
        self.assertEqual(seen, ["admin", "token", "org-repo"])

    def test_gate_blocks_seed_until_gitea_argocd_ready(self):
        # Gate avant le seed (parité run-phases.sh) : si gitea/argocd ne sont pas Ready
        # (rollout status rc≠0), le seed s'arrête AVANT le moindre geste mutant (constaté au
        # banc : sans gate, admin tapait un pod pas prêt → token KO trompeur). Code 1, 0 step.
        self._patch(cli, "_kubectl", lambda *_a, **_k: subprocess.CompletedProcess([], 1, "", ""))
        seen = self._stub_do()
        code = _engine(_topo(_LIMA_SOLO), "layers", ["gitops-seed"], "solo")
        self.assertEqual(code, 1)
        self.assertEqual(seen, [])  # AUCUN step joué : la gate bloque en amont

    def test_api_ok_distinguishes_success_from_real_failure(self):
        # Correctif d'audit : org-repo/webhook VALIDENT le code HTTP (plus de `return True`
        # inconditionnel). 2xx (créé) et 409/422 (existe déjà) = idempotent ok ; 401 (token
        # invalide), 5xx, ou code vide (exec KO) = ÉCHEC → le step échoue (pas de faux-vert).
        for code in ("200", "201", "409", "422"):
            self.assertTrue(cli._seed_api_ok(code), f"{code} doit être OK")
        for code in ("401", "403", "500", "", "000"):
            self.assertFalse(cli._seed_api_ok(code), f"{code} doit être un ÉCHEC")

    def test_seed_never_uses_fqdn_in_kubectl_exec(self):
        # Le seed RÉEL (`_seed_do_banc`) ne tape JAMAIS le FQDN svc.cluster.local : il exec
        # DANS le pod gitea (localhost:3000). On espionne `_kubectl` et `_kubectl_apply_stdin`
        # et on vérifie qu'AUCUN argv kubectl exec ne contient 'svc.cluster.local'. La seule
        # occurrence légitime est dans le repoURL d'un Application/hook (résolu DANS le cluster
        # par argocd-repo-server, pas par l'hôte) — jamais dans un `kubectl exec ... curl`.
        from nestor import seed as _seed

        exec_argvs = []
        applied = []

        def _spy_kubectl(*args, **kw):
            argv = list(args)
            # `exec` argv : on capture ce qui suit `--` (la commande DANS le pod).
            if "exec" in argv:
                exec_argvs.append(argv)
            # Stubs de retour pour que le do() avance : pod trouvé, secrets/token non vides.
            if "get" in argv and "pod" in argv:
                return subprocess.CompletedProcess(args, 0, stdout="gitea-0", stderr="")
            if "get" in argv and "secret" in argv:
                # base64('x') = 'eA==' (mot de passe / secret non vide, décodable).
                if any("jsonpath" in str(a) for a in argv):
                    return subprocess.CompletedProcess(args, 0, stdout="eA==", stderr="")
                return subprocess.CompletedProcess(args, 0, stdout="exists", stderr="")
            if "exec" in argv:
                # generate-access-token --raw → un token non vide ; curl → code 200.
                if "generate-access-token" in argv:
                    return subprocess.CompletedProcess(args, 0, stdout="tok123\n", stderr="")
                return subprocess.CompletedProcess(args, 0, stdout="200", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        def _spy_apply(manifest, **kw):
            applied.append(manifest)
            return subprocess.CompletedProcess(["kubectl", "apply"], 0, stdout="", stderr="")

        self._patch(cli, "_kubectl", _spy_kubectl)
        self._patch(cli, "_kubectl_apply_stdin", _spy_apply)
        # Les 7 gestes réels (admin/token/org-repo/push-code-location/webhook-secret/webhook/
        # application) sont exercés et leurs argv inspectés — y compris push-code-location, qui
        # exec `curl localhost:3000/api/v1/.../contents/...` (jamais le FQDN). Son verdict
        # importe peu ICI (le spy curl rend un corps vide → POST sans `commit`) : on n'inspecte
        # que les URL d'API, pas le succès du push (prouvé par les tests dédiés plus bas).
        config = _seed.SeedConfig.from_topology(_topo(_LIMA_SOLO))
        real_do = cli._seed_do_banc(_topo(_LIMA_SOLO), config)

        for step in _seed.seed_steps("banc"):
            real_do(step)
        # AUCUN `kubectl exec … curl …` ne TAPE Gitea via un FQDN : la cible curl est l'URL
        # `http://localhost:3000/api/v1…` (Gitea depuis le pod), jamais `gitea-…svc.cluster.local`
        # (qui timeouterait côté glibc/curl, mémoire dns-fqdn-timeout). Le FQDN argocd-server du
        # CORPS du hook (config.url) est légitime : c'est le callback résolu PAR Gitea DANS le
        # cluster, jamais une cible curl — on vérifie donc l'URL de l'API, pas tout l'argv.
        for argv in exec_argvs:
            if "curl" not in argv:
                continue
            # L'URL de l'API Gitea est l'argument qui commence par http(s):// et contient /api/v1.
            api_urls = [a for a in argv if str(a).startswith("http") and "/api/v1" in str(a)]
            self.assertTrue(api_urls, f"exec curl sans URL d'API Gitea : {argv}")
            for url in api_urls:
                self.assertNotIn("svc.cluster.local", url, f"FQDN Gitea dans la cible curl : {url}")
                self.assertIn("localhost:3000", url)

    # ── push-code-location (step 4/7, Contents API create-or-update) ────────────────
    # CÂBLÉ (plus de STUB) : pour les 3 manifestes de `bench/lima/atlas-workflow-sample/`,
    # base64 (Python) → GET du SHA → PUT-avec-sha (existe) vs POST (404) → vérif `"commit"`.
    # On STUBE `_gitea_exec` (curl DANS le pod) avec un faux Gitea : I/O injectée, zéro cluster.
    _PCL_FILES = ("code-location.yaml", "workspace-patch.yaml", "reload-hook.yaml")

    def _fake_gitea(self, *, existing=False, commit=True):
        """Faux `_gitea_exec` modélisant la Contents API de Gitea pour push-code-location.

        `existing` : le GET /contents rend un fichier avec un `sha` (→ PUT) ou un 404 (→ POST).
        `commit` : le PUT/POST rend (ou non) un objet `commit` (→ succès ou échec fail-fast).
        Enregistre les appels exec curl (method, path, body) dans la liste renvoyée."""
        from nestor import seed as _seed

        config = _seed.SeedConfig.from_topology(_topo(_LIMA_SOLO))
        api_base = f"{config.api}/api/v1"
        calls = []

        def _exec(ns, pod, argv, **kw):
            if "curl" not in argv:
                # generate-access-token --raw → token ; autres exec → ok.
                if "generate-access-token" in argv:
                    return subprocess.CompletedProcess(argv, 0, "tok123\n", "")
                return subprocess.CompletedProcess(argv, 0, "", "")
            # Reconstitue method/url/body de l'argv curl (parité _api_full).
            method = argv[argv.index("-X") + 1]
            url = next(a for a in argv if str(a).startswith("http") and "/api/v1" in str(a))
            path = str(url)[len(api_base) :]
            body = argv[argv.index("-d") + 1] if "-d" in argv else None
            calls.append((method, path, body, str(url)))
            # `-w '\n%{http_code}'` : corps puis DERNIÈRE ligne = code HTTP (moule réel).
            if method == "GET":
                if existing:
                    payload = json.dumps({"name": "x", "sha": "deadbeefsha", "type": "file"})
                    return subprocess.CompletedProcess(argv, 0, payload + "\n200", "")
                # 404 : Gitea rend un message d'erreur JSON, pas de `sha`.
                payload = json.dumps({"message": "object does not exist [id: ...]"})
                return subprocess.CompletedProcess(argv, 0, payload + "\n404", "")
            # PUT/POST : succès = objet content + commit ; échec = pas de commit.
            if commit:
                payload = json.dumps({"content": {"name": "x"}, "commit": {"sha": "c0ffee"}})
                code = "200" if method == "PUT" else "201"
                return subprocess.CompletedProcess(argv, 0, payload + "\n" + code, "")
            payload = json.dumps({"message": "nope"})
            return subprocess.CompletedProcess(argv, 0, payload + "\n422", "")

        self._patch(cli, "_gitea_exec", _exec)
        self._patch(cli, "_gitea_pod", lambda *_a, **_k: "gitea-0")
        # token() doit réussir pour que push_code_location ait un token threadé ; le do() le pose.
        return config, calls

    def _push_only(self, config):
        """Construit le do() réel et joue token (pour le state) puis push-code-location seul."""
        do = cli._seed_do_banc(_topo(_LIMA_SOLO), config)
        self.assertTrue(do("token"), "token doit réussir pour threader l'auth")
        return do

    def test_push_code_location_new_files_post(self):
        # Fichiers ABSENTS (GET → 404, sha vide) → POST de création pour les 3, chacun renvoie
        # un `commit` → succès. On vérifie : 1 GET + 1 POST par fichier, dans l'ordre.
        config, calls = self._fake_gitea(existing=False, commit=True)
        do = self._push_only(config)
        self.assertTrue(do("push-code-location"))
        gets = [c for c in calls if c[0] == "GET"]
        posts = [c for c in calls if c[0] == "POST"]
        puts = [c for c in calls if c[0] == "PUT"]
        self.assertEqual(len(gets), 3)
        self.assertEqual(len(posts), 3)  # 404 → création
        self.assertEqual(puts, [])  # aucun PUT (pas de sha)
        # Les 3 fichiers du sample sont ciblés (path /contents/<fname>) ET le body porte un
        # `content` base64 + le message « add ... », pas de `sha`.
        for fname in self._PCL_FILES:
            post = next(c for c in posts if c[1].endswith(f"/contents/{fname}"))
            payload = json.loads(post[2])
            self.assertIn("content", payload)
            self.assertNotIn("sha", payload)
            self.assertIn("add", payload["message"])
            # Le content est le base64 DU FICHIER lu côté hôte (Python), décodable.
            with open(os.path.join(cli._SEED_SAMPLE_DIR, fname), "rb") as fh:
                self.assertEqual(base64.b64decode(payload["content"]), fh.read())

    def test_push_code_location_existing_files_put_with_sha(self):
        # Fichiers EXISTANTS (GET → 200 avec sha) → PUT-avec-sha (MAJ idempotente) pour les 3.
        config, calls = self._fake_gitea(existing=True, commit=True)
        do = self._push_only(config)
        self.assertTrue(do("push-code-location"))
        puts = [c for c in calls if c[0] == "PUT"]
        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(len(puts), 3)
        self.assertEqual(posts, [])  # sha présent → PUT, jamais POST
        for fname in self._PCL_FILES:
            put = next(c for c in puts if c[1].endswith(f"/contents/{fname}"))
            payload = json.loads(put[2])
            self.assertEqual(payload["sha"], "deadbeefsha")  # le sha du GET est threadé
            self.assertIn("content", payload)
            self.assertIn("update", payload["message"])

    def test_push_code_location_no_commit_fails_fast(self):
        # Une réponse PUT/POST SANS `commit` (écriture ratée → l'ancienne version resterait) →
        # le step échoue (return False) : fail-fast, drift Argo CD évité (ADR 0034).
        config, _calls = self._fake_gitea(existing=False, commit=False)
        do = self._push_only(config)
        self.assertFalse(do("push-code-location"))

    def test_push_code_location_no_longer_raises_stub(self):
        # Régression directe : le step ne lève PLUS de PathError 'STUB' à l'aveugle — il TENTE
        # le vrai push (et échoue honnêtement si un détail cloche). Ici succès nominal.
        config, _calls = self._fake_gitea(existing=False, commit=True)
        do = self._push_only(config)
        try:
            self.assertTrue(do("push-code-location"))
        except cli._path.PathError as exc:  # pragma: no cover — l'ancien STUB
            self.fail(f"push-code-location lève encore un STUB : {exc}")

    def test_push_code_location_never_uses_fqdn(self):
        # Aucun argv curl de push-code-location ne tape le FQDN : cible = localhost:3000.
        config, calls = self._fake_gitea(existing=True, commit=True)
        do = self._push_only(config)
        do("push-code-location")
        self.assertTrue(calls)
        for _method, _path, _body, url in calls:
            self.assertNotIn("svc.cluster.local", url, f"FQDN dans push-code-location : {url}")
            self.assertIn("localhost:3000", url)

    def test_seed_banc_todo_declared(self):
        # La frontière code-écrit / preuve-banc du seed est DÉCLARÉE (honnêteté ADR 0034).
        self.assertTrue(cli._seed_banc_todo())
        self.assertTrue(all(isinstance(t, str) and t for t in cli._seed_banc_todo()))
        # push-code-location N'EST PLUS listé comme STUBÉ : le câblage est fait (preuve = banc).
        self.assertFalse(
            any("STUBÉE" in t and "push-code-location" in t for t in cli._seed_banc_todo()),
            "push-code-location ne doit plus être marqué STUBÉ (il est câblé)",
        )

    def test_gitops_seed_chains_after_dataops(self):
        # Le chemin enchaîne dataops → gitops-seed : la phase déléguée se monte APRÈS la
        # couche dataops (parité de la séquence run-phases.sh). dataops joue 2 hooks e2e ; pour
        # exercer l'ENCHAÎNEMENT de routage (pas les hooks), on neutralise les deux : le hook
        # CÂBLÉ (`_chain_emit_and_verify_banc`, façade) en succès, et le STUB du registre de
        # l'egress (`E2E_HOOKS[...]`, qui sinon lèverait E2EHookStubbed → arrêt net).
        self._patch(cli, "_chain_emit_and_verify_banc", lambda *_a, **_k: None)
        self._patch_dict_item(
            _phases.E2E_HOOKS, "dataops_egress_internet_check", lambda *_a, **_k: None
        )

        def _ok_idem(*_a, **_k):
            return _runner.RunResult(rc=0, status="successful", changed=0)

        self._patch(cli._runner, "launch_phase", _ok_idem)
        seen = self._stub_do()
        code = _engine(_topo(_LIMA_SOLO), "layers", ["dataops", "gitops-seed"], "solo")
        self.assertEqual(code, 0)
        # Le seed (ses 7 steps) a bien été joué APRÈS dataops (sinon `seen` serait vide).
        from nestor import seed as _seed

        self.assertEqual(seen, list(_seed.seed_steps("banc")))


class ChainEmitAndVerifyWiring(unittest.TestCase):
    """Le hook e2e `dataops_chain_emit_and_verify` CÂBLÉ (`_chain_emit_and_verify_banc`,
    porte run-phases.sh:1213) — I/O kubectl INJECTÉE, ZÉRO cluster (honnêteté ADR 0034).

    On prouve le GESTE (Job appliqué avec le bon manifeste, poll succeeded, compteur Marquez
    avant/après, verdict delta, teardown) et l'anti-FQDN (le compteur ne tape JAMAIS le FQDN
    Marquez depuis l'hôte : il run un pod intra-cluster). La preuve d'INGESTION réelle reste
    un run banc du mainteneur (cf. `phases.banc_todo`)."""

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def _run(self):
        """Joue le hook CÂBLÉ en AVALANT son stdout (les `print` de progression sont
        légitimes en vrai run, parasites dans la sortie de test) et SANS attente réelle."""
        with contextlib.redirect_stdout(io.StringIO()):
            cli._chain_emit_and_verify_banc(sleep=lambda _s: None)

    def _harness(self, *, counts, succeeded_after=1):
        """Espionne `_kubectl` et `_kubectl_apply_stdin` pour modéliser un mini-cluster.

        `counts` : suite de réponses (JSON ou None) que `kubectl run … wget` (le compteur
        Marquez) rend successivement (AVANT, APRÈS). `succeeded_after` : nb d'appels `get job`
        avant que `status.succeeded` passe à "1" (≥1 → la poll converge ; 0 → jamais succès).
        Renvoie un dict des appels capturés (`apply`, `run_count`, `get_job`, `delete`, `logs`)."""
        captured = {"apply": [], "run_count": [], "get_job": 0, "delete": [], "logs": 0}
        count_iter = iter(counts)
        get_job_calls = {"n": 0}

        def _spy_kubectl(*args, **kw):
            argv = list(args)
            # Compteur Marquez : `kubectl -n marquez run … -- sh -c 'wget … <url>'`.
            if "run" in argv and "-n" in argv and argv[argv.index("-n") + 1] == "marquez":
                # L'URL wget est le dernier argument du `sh -c`.
                captured["run_count"].append(argv)
                try:
                    payload = next(count_iter)
                except StopIteration:
                    payload = None
                if payload is None:
                    return subprocess.CompletedProcess(args, 1, "", "")
                return subprocess.CompletedProcess(args, 0, payload, "")
            # Poll de complétion : `kubectl -n dagster get job ol-emit-toy -o jsonpath=…`.
            if "get" in argv and "job" in argv:
                get_job_calls["n"] += 1
                captured["get_job"] = get_job_calls["n"]
                done = "1" if get_job_calls["n"] >= succeeded_after >= 1 else ""
                return subprocess.CompletedProcess(args, 0, done, "")
            if "delete" in argv and "job" in argv:
                captured["delete"].append(argv)
                return subprocess.CompletedProcess(args, 0, "", "")
            if "logs" in argv:
                captured["logs"] += 1
                return subprocess.CompletedProcess(args, 0, "boom", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        def _spy_apply(manifest, **kw):
            captured["apply"].append(manifest)
            return subprocess.CompletedProcess(["kubectl", "apply"], 0, "", "")

        self._patch(cli, "_kubectl", _spy_kubectl)
        self._patch(cli, "_kubectl_apply_stdin", _spy_apply)
        return captured

    def test_applies_emit_job_with_correct_image_env_command(self):
        # Le manifeste appliqué est le Job émetteur : image, env OpenLineage, command Dagster.
        cap = self._harness(counts=['{"totalCount":0}', '{"totalCount":1}'])
        self._run()
        self.assertEqual(len(cap["apply"]), 1)
        manifest = cap["apply"][0]
        self.assertIn("kind: Job", manifest)
        self.assertIn("name: ol-emit-toy", manifest)
        self.assertIn("namespace: dagster", manifest)
        self.assertIn("image: registry:80/dagster-openlineage-emit:dev", manifest)
        self.assertIn("OPENLINEAGE_URL", manifest)
        self.assertIn("http://marquez.marquez.svc.cluster.local:5000", manifest)
        self.assertIn("OPENLINEAGE_ENDPOINT", manifest)
        self.assertIn("api/v1/lineage", manifest)
        self.assertIn("OPENLINEAGE_NAMESPACE", manifest)
        self.assertIn('"dagster", "asset", "materialize"', manifest)
        self.assertIn("toy_assets", manifest)
        self.assertIn("backoffLimit: 1", manifest)
        self.assertIn("ttlSecondsAfterFinished: 600", manifest)
        self.assertIn("restartPolicy: Never", manifest)

    def test_delta_present_after_is_ok(self):
        # Compteur 0 → 1 (lineage ingéré) : verdict ok → ne LÈVE PAS. Teardown joué.
        cap = self._harness(counts=['{"totalCount":0}', '{"totalCount":1}'])
        self._run()  # ne lève pas
        self.assertTrue(cap["delete"], "le Job émetteur doit être supprimé (teardown)")

    def test_idempotent_equal_count_still_ok(self):
        # Parité bash (bats L56) : 2 → 2 (rejeu idempotent, Marquez ne vide pas) reste OK,
        # car on teste la PRÉSENCE (after≥1), pas un delta strict.
        self._harness(counts=['{"totalCount":2}', '{"totalCount":2}'])
        self._run()  # ne lève pas

    def test_after_zero_raises(self):
        # after == 0 (rien ingéré) → LÈVE (pas de faux vert, honnêteté ADR 0034).
        self._harness(counts=['{"totalCount":0}', '{"totalCount":0}'])
        with self.assertRaises(_phases.E2EHookStubbed):
            self._run()

    def test_unreadable_count_raises_skip(self):
        # Compteur illisible (Marquez injoignable) → skip → LÈVE (n'a rien PROUVÉ).
        self._harness(counts=[None, None])
        with self.assertRaises(_phases.E2EHookStubbed):
            self._run()

    def test_job_never_succeeds_raises_with_logs(self):
        # Le Job ne réussit jamais (image émetteur absente ? cf. réserve build_emitter_image)
        # → poll épuisé → LÈVE (mention image), logs du Job récupérés, teardown joué.
        cap = self._harness(counts=['{"totalCount":0}'], succeeded_after=0)
        with self.assertRaises(_phases.E2EHookStubbed) as ctx:
            self._run()
        self.assertIn("dagster-openlineage-emit", str(ctx.exception))
        self.assertGreaterEqual(cap["logs"], 1)
        self.assertTrue(cap["delete"])

    def test_apply_failure_raises(self):
        # L'apply du Job échoue (Dagster absent ?) → LÈVE avant tout poll.
        def _spy_apply(manifest, **kw):
            return subprocess.CompletedProcess(["kubectl", "apply"], 1, "", "no ns dagster")

        self._patch(cli, "_kubectl_apply_stdin", _spy_apply)
        self._patch(cli, "_kubectl", lambda *_a, **_k: subprocess.CompletedProcess([], 0, "", ""))
        with self.assertRaises(_phases.E2EHookStubbed):
            self._run()

    def test_marquez_count_never_taps_fqdn_from_host(self):
        # Le compteur Marquez run un pod busybox intra-cluster (`kubectl run … wget`) : c'est
        # le pod qui résout le FQDN, JAMAIS l'hôte (piège DNS, mémoire dns-fqdn-timeout). On
        # vérifie qu'AUCUN argv kubectl du compteur n'est un curl/wget HÔTE — c'est un `run`.
        cap = self._harness(counts=['{"totalCount":0}', '{"totalCount":1}'])
        self._run()
        self.assertTrue(cap["run_count"], "le compteur doit passer par `kubectl run` (pod)")
        for argv in cap["run_count"]:
            # La cible Marquez (FQDN) n'apparaît QUE dans la commande EXÉCUTÉE DANS le pod
            # (`sh -c 'wget … svc.cluster.local …'`), jamais comme cible d'un appel hôte.
            self.assertIn("run", argv)
            self.assertIn("--image=busybox:1.36", argv)
            # Le FQDN est bien présent (dans le `wget` intra-pod), preuve que c'est intra-cluster.
            self.assertTrue(any("svc.cluster.local" in str(a) for a in argv))

    def test_pure_parse_and_classify(self):
        # Les fonctions PURES portées de dataops-assert.sh sont fidèles (testées sans I/O).
        p = _phases.parse_marquez_job_count
        self.assertEqual(p('{"jobs":[],"totalCount":3}'), 3)
        self.assertEqual(p('{"jobs":[{"name":"a"},{"name":"b"}]}'), 2)
        self.assertIsNone(p(""))
        self.assertIsNone(p("pas du json"))
        self.assertIsNone(p('{"namespaces":[]}'))
        c = _phases.classify_marquez_ingest
        self.assertEqual(c(0, 1)[0], "ok")
        self.assertEqual(c(2, 2)[0], "ok")  # idempotence (présence, pas delta)
        self.assertEqual(c(0, 0)[0], "fail")
        self.assertEqual(c(None, 1)[0], "skip")


class NodesOverrideEnrichment(unittest.TestCase):
    """`_nodes_override` émet le canal ENRICHI `nom|role|cpus,memory,disk|disques`
    (ADR 0102 volet C) — PUR, dérivé de la topo (ressources + disques PAR NŒUD)."""

    def test_local_path_mono_node_empty_disks_field(self):
        # Mono-nœud local-path (pas de disque déclaré) → 4e champ VIDE, un seul segment.
        topo = topology_from_dict(
            {
                "catalog": {"topology": "solo"},
                "nodes": [{"name": "cp1", "roles": ["control", "worker"]}],
                "storage": {"backend": "local-path"},
                "target_kind": "bench",
            }
        )
        # control+worker → `control` (le banc détaint) ; ressources = défauts (4/12/40).
        self.assertEqual(cli._nodes_override(topo), "cp1|control|4,12GiB,40GiB|")

    def test_ceph_three_nodes_carries_role_resources_disks(self):
        # Topo Ceph 3 nœuds : rôle + ressources + disques déclarés (objets DiskSpec), par nœud.
        # node1 control avec 2 disques (data + metadata), node2/node3 worker avec 1 disque data
        # (string nue → taille/rôle par défaut : 10GiB=data).
        topo = topology_from_dict(
            {
                "catalog": {"topology": "multi-node-3"},
                "nodes": [
                    {
                        "name": "node1",
                        "roles": ["control", "worker", "storage"],
                        "disks": [
                            {"name": "vdb", "size": "10GiB"},
                            {"name": "vdd", "size": "5GiB", "role": "metadata"},
                        ],
                    },
                    {"name": "node2", "roles": ["worker", "storage"], "disks": ["vdb"]},
                    {"name": "node3", "roles": ["worker", "storage"], "disks": ["vdb"]},
                ],
                "storage": {"backend": "ceph"},
                "target_kind": "bench",
            }
        )
        self.assertEqual(
            cli._nodes_override(topo),
            "node1|control|4,12GiB,40GiB|vdb=10GiB=data,vdd=5GiB=metadata"
            ";node2|worker|4,12GiB,40GiB|vdb=10GiB=data"
            ";node3|worker|4,12GiB,40GiB|vdb=10GiB=data",
        )

    def test_per_node_resources_override_is_carried(self):
        # Une surcharge `nodes[].resources` prime dans le 3e champ (ressources PAR NŒUD).
        topo = topology_from_dict(
            {
                "catalog": {"topology": "duo"},
                "resources": {"cpus": 4, "memory": "12GiB", "disk": "40GiB"},
                "nodes": [
                    {
                        "name": "cp1",
                        "roles": ["control", "worker"],
                        "resources": {"cpus": 8, "memory": "24GiB"},
                    },
                    {"name": "node1", "roles": ["worker"]},
                ],
                "storage": {"backend": "local-path"},
                "target_kind": "bench",
            }
        )
        self.assertEqual(
            cli._nodes_override(topo),
            "cp1|control|8,24GiB,40GiB|;node1|worker|4,12GiB,40GiB|",
        )


if __name__ == "__main__":
    unittest.main()
