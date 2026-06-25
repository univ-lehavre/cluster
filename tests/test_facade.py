"""Tests de la FAÇADE du moteur de chemin Python (`nestor.path.run_path`) — LOT 6 (ADR 0097).

Câblage façade exposé derrière le FLAG opt-in `nestor up --engine=python` (cf.
`scripts/topology.py:_run_path_engine` / `_path_context` / `_provision_via_bash`). Ces
tests sont PURS (I/O injectée : runner stubé, gates stubées, run-phases.sh espionné) —
ZÉRO cluster, ZÉRO provisionnement réel (filet de sécurité hérité de test_topology_cli).

Ils couvrent la LOGIQUE de câblage (le moteur lui-même est testé dans test_path.py) :
  - `_path_context` dérive PathContext de la topo (cp = 1er control, PAS codé en dur) ;
  - le FLAG route bien (python → run_path ; défaut/absent → run-phases.sh) ;
  - non-régression : SANS `--engine`, cmd_up délègue EXACTEMENT à run-phases.sh (inchangé) ;
  - les callbacks appellent les BONNES briques (launch_phase_idempotent, gate, provision) ;
  - assert_safe REFUSE une cible non-banc (garde d'isolation à chaque phase) ;
  - les hooks e2e (dataops) LÈVENT (stub honnête) → le montage s'arrête net (pas de fallback).

⚠️ HONNÊTETÉ (ADR 0034) : ces tests prouvent la LOGIQUE de câblage, PAS le montage réel au
banc. La preuve définitive du chemin `--engine=python` est un run banc mono-nœud du
mainteneur (cf. `nestor.path.banc_todo`). NE PRÉTENDS JAMAIS l'avoir prouvé ici.
"""

import contextlib
import importlib.util
import io
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
# Le mainteneur PEUT avoir un banc Lima RÉEL (`bench/lima/.work/kubeconfig` présent) : sans
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


# Topo BANC mono-nœud (target_kind: lima) : cp1 control+worker, local-path, AVEC une couche
# applicative (storage-simple) déclarée → la séquence a un play unitaire (storage-simple) APRÈS
# le socle (up, bootstrap). Le chemin `--engine=python` se TESTE au banc mono-nœud (ADR 0097).
_LIMA_SOLO = (
    "catalog: {topology: solo}\n"
    "layers: [storage-simple]\n"
    "nodes:\n  - {name: cp1, roles: [control, worker]}\n"
    "storage: {backend: local-path}\ntarget_kind: lima\n"
)

# Topo BANC à DEUX nœuds (cp choisi PARMI eux) : node-a worker, cp-b control. Sert à
# prouver que `_path_context.cp` = 1er CONTROL (pas le 1er nœud), DÉRIVÉ, jamais `cp1` codé.
_LIMA_CP_SECOND = (
    "catalog: {topology: duo, profile: base}\n"
    "nodes:\n"
    "  - {name: node-a, roles: [worker]}\n"
    "  - {name: cp-b, roles: [control, worker]}\n"
    "storage: {backend: local-path}\ntarget_kind: lima\n"
)


def _topo(yaml_text: str):
    import yaml

    return topology_from_dict(yaml.safe_load(yaml_text))


class PathContextDerivation(unittest.TestCase):
    """`_path_context` dérive PathContext de la TOPOLOGIE (PUR, ADR 0097 §5.a)."""

    def test_cp_is_first_control_not_hardcoded(self):
        # cp = 1er nœud `control`, même s'il n'est PAS le 1er nœud déclaré (jamais `cp1` codé).
        ctx = cli._path_context(_topo(_LIMA_CP_SECOND))
        self.assertEqual(ctx.cp, "cp-b")

    def test_cp_solo(self):
        ctx = cli._path_context(_topo(_LIMA_SOLO))
        self.assertEqual(ctx.cp, "cp1")

    def test_api_port_and_repo_and_nodes(self):
        ctx = cli._path_context(_topo(_LIMA_CP_SECOND))
        self.assertEqual(ctx.api_port, 6443)
        # repo = racine ABSOLUE du dépôt (pour résoudre les playbooks).
        self.assertTrue(os.path.isabs(ctx.repo))
        # nodes = tuple des nœuds attendus Ready (ordre déclaré).
        self.assertEqual(ctx.nodes, ("node-a", "cp-b"))

    def test_kubeconfig_local_and_inventory_are_bench_paths(self):
        # IDENTIQUES à run-phases.sh (KUBECONFIG_LOCAL / INVENTORY du banc Lima).
        ctx = cli._path_context(_topo(_LIMA_SOLO))
        self.assertEqual(ctx.kubeconfig_local, cli._BENCH_KUBECONFIG)
        self.assertEqual(ctx.inventory, cli._BENCH_INVENTORY)


class FlagRouting(unittest.TestCase):
    """Le FLAG `--engine` route le montage ; le DÉFAUT (bash) reste run-phases.sh."""

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
        """Espionne `_run_path_engine` (la branche python) : renvoie les appels."""
        calls = []

        def _spy(topo, target, seq, stack_name, a_appliquer=None):
            calls.append((target, list(seq), stack_name, a_appliquer))
            return 0

        orig = cli._run_path_engine
        cli._run_path_engine = _spy
        self.addCleanup(setattr, cli, "_run_path_engine", orig)
        return calls

    def test_default_no_flag_delegates_to_run_phases_unchanged(self):
        # NON-RÉGRESSION (invariant 4) : SANS `--engine`, cmd_up délègue à run-phases.sh
        # et n'appelle JAMAIS le moteur python.
        rp_calls = self._spy_runphases()
        eng_calls = self._spy_engine()
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["up", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(eng_calls, [])  # moteur python JAMAIS appelé
        self.assertEqual(len(rp_calls), 1)  # run-phases.sh appelé UNE fois
        self.assertIn("run-phases.sh", " ".join(rp_calls[0]))

    def test_engine_bash_explicit_delegates_to_run_phases(self):
        # `--engine=bash` explicite = même comportement que le défaut.
        rp_calls = self._spy_runphases()
        eng_calls = self._spy_engine()
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["up", "-f", path, "--yes", "--engine", "bash"])
        self.assertEqual(code, 0)
        self.assertEqual(eng_calls, [])
        self.assertEqual(len(rp_calls), 1)

    def test_engine_python_routes_to_run_path(self):
        # `--engine=python` route vers le moteur python ; run-phases.sh PAS appelé (sauf
        # le graphe, laissé passer). Le moteur reçoit la séquence dérivée.
        rp_calls = self._spy_runphases()
        eng_calls = self._spy_engine()
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["up", "-f", path, "--yes", "--engine", "python"])
        self.assertEqual(code, 0)
        self.assertEqual(rp_calls, [])  # run-phases.sh JAMAIS appelé par la branche python
        self.assertEqual(len(eng_calls), 1)
        target, seq, _stack, _a_appliquer = eng_calls[0]
        self.assertEqual(target, "layers")
        self.assertEqual(seq[0], "up")  # topo lima → la séquence commence par `up`
        self.assertIn("storage-simple", seq)  # layer déclarée → couche storage-simple

    def _set_env(self, name, value):
        # Pose une variable d'env le temps du test, restaurée en cleanup (évite la FUITE
        # vers les autres tests/modules — _capture restaure le snapshot PRIS À SON ENTRÉE,
        # qui inclut déjà la variable si on la pose avant lui).
        saved = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(
            lambda: (
                os.environ.__setitem__(name, saved)
                if saved is not None
                else os.environ.pop(name, None)
            )
        )

    def test_env_nestor_engine_python_routes(self):
        # Repli env NESTOR_ENGINE=python (sans flag CLI).
        self._spy_runphases()
        eng_calls = self._spy_engine()
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        self._set_env("NESTOR_ENGINE", "python")
        code, _, _ = _capture(["up", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(eng_calls), 1)

    def test_flag_cli_overrides_env(self):
        # Le flag CLI PRIME sur l'env : `--engine=bash` + NESTOR_ENGINE=python → bash.
        rp_calls = self._spy_runphases()
        eng_calls = self._spy_engine()
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        self._set_env("NESTOR_ENGINE", "python")
        code, _, _ = _capture(["up", "-f", path, "--yes", "--engine", "bash"])
        self.assertEqual(code, 0)
        self.assertEqual(eng_calls, [])
        self.assertEqual(len(rp_calls), 1)


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
        """Stub `runner.launch_phase_idempotent` : enregistre (playbook, extravars) et rend ok."""

        def _fake(playbook, extravars, private_data_dir, inventory, **kw):
            calls.append({"playbook": playbook, "extravars": extravars, "inventory": inventory})
            return _runner.IdempotenceResult(
                deployed=_runner.RunResult(rc=0, status="successful", changed=0),
                replayed=_runner.RunResult(rc=0, status="successful", changed=0),
                verdict="ok",
                message="ok",
            )

        orig = cli._runner.launch_phase_idempotent
        cli._runner.launch_phase_idempotent = _fake
        self.addCleanup(setattr, cli._runner, "launch_phase_idempotent", orig)

    def test_launch_calls_idempotent_with_restricted_extravars(self):
        # Une séquence d'UNE seule couche applicative (storage-simple) : le callback `launch`
        # doit appeler launch_phase_idempotent avec les `-e` RESTREINTS de la phase.
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
        # LOT 8 : les ressources VM passées en env viennent du YAML (defaults ici).
        self.assertIn("VM_CPUS", rp_calls[0]["env"])
        self.assertIn("VM_MEMORY", rp_calls[0]["env"])

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
        # dataops a des hooks e2e STUBÉS qui LÈVENT → le montage s'arrête NET (code 1), PAS
        # de verdissement à tort (honnêteté ADR 0034). Le play réussit, le hook lève.
        self._stub_idempotent([])
        topo = _topo(_LIMA_SOLO)
        code = _engine(topo, "layers", ["dataops"], "solo")
        self.assertEqual(code, 1)


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
        """Espionne run-phases.sh (inventory/facts/ha-cni) ET runner.launch_phase. Renvoie un
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
                if arm == "ha-cni":
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
        # du socle (runner) avec `-e control_plane_ip=<cp_ip dérivé>` → CNI (ha-cni). Topo DUO
        # (un worker pur) → has_workers=True → join-workers.yaml présent (6 playbooks).
        spy = self._spy()
        code = _engine(_topo(_LIMA_CP_SECOND), "layers", ["bootstrap"], "duo")
        self.assertEqual(code, 0)
        arms = self._arms(spy["rp"])
        # Inventaire écrit AVANT les faits, CNI en dernier (ha-cni = CNI + kubeconfig).
        self.assertEqual(arms, ["inventory", "facts", "ha-cni"])
        # inventory <control_csv> <workers_csv> : cp-b control, node-a worker (dérivés de la topo).
        inv = next(c for c in spy["rp"] if c[2] == "inventory")
        self.assertEqual(inv[3], "cp-b")
        self.assertEqual(inv[4], "node-a")
        # ha-cni reçoit l'iface dérivée du contrat machine emit_facts (L2_IFACE).
        cni = next(c for c in spy["rp"] if c[2] == "ha-cni")
        self.assertEqual(cni[3], "lima0")
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

        self._patch(cli._runner, "launch_phase_idempotent", _boom_layer)
        spy = self._spy(launch_rc=2)
        code = _engine(_topo(_LIMA_SOLO), "layers", ["bootstrap", "storage-simple"], "solo")
        self.assertEqual(code, 1)
        # Le 1er playbook échoue → fail-fast : un seul launch, pas de CNI (ha-cni absent).
        self.assertEqual(len(spy["launch"]), 1)
        self.assertNotIn("ha-cni", self._arms(spy["rp"]))

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
        # Les 6 playbooks passent mais la CNI (ha-cni) échoue → BootstrapError → PathError →
        # code 1 (le socle n'est pas « monté » sans CNI).
        spy = self._spy(cni_rc=5)
        code = _engine(_topo(_LIMA_SOLO), "layers", ["bootstrap"], "solo")
        self.assertEqual(code, 1)
        self.assertIn("ha-cni", self._arms(spy["rp"]))

    def test_up_then_bootstrap_then_layer_chains(self):
        # Le chemin up→bootstrap→couche enchaîne : provision (run-phases.sh up, stub) →
        # bootstrap (socle+CNI, stub) → 1re couche applicative (storage-simple, idempotent).
        spy = self._spy()

        # provision : run-phases.sh up renvoyé 0 par le spy ci-dessus (arm "up" → défaut 0).
        # couche applicative : launch_phase_idempotent stubé ok.
        layer_calls = []

        def _fake_idem(playbook, extravars, *a, **k):
            layer_calls.append(playbook)
            return _runner.IdempotenceResult(
                deployed=_runner.RunResult(rc=0, status="successful", changed=0),
                replayed=_runner.RunResult(rc=0, status="successful", changed=0),
                verdict="ok",
                message="ok",
            )

        self._patch(cli._runner, "launch_phase_idempotent", _fake_idem)
        code = _engine(_topo(_LIMA_SOLO), "layers", ["up", "bootstrap", "storage-simple"], "solo")
        self.assertEqual(code, 0)
        # provision (up) puis bootstrap (inventory/facts/ha-cni) ont bien été appelés.
        arms = self._arms(spy["rp"])
        self.assertIn("up", arms)
        self.assertEqual(arms[arms.index("up") + 1 :], ["inventory", "facts", "ha-cni"])
        # La couche applicative storage-simple a été montée APRÈS le socle.
        self.assertEqual(len(layer_calls), 1)


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
        def _refuse(action):
            raise cli._UsageError(f"REFUS : `{action}` cible non-banc (test)")

        self._patch(cli, "_assert_bench_target", _refuse)
        self._patch(cli, "_wait_layer_healthy", lambda *_a, **_k: True)

        def _boom_launch(*_a, **_k):
            raise AssertionError("launch lancé malgré le REFUS d'isolation")

        def _boom_prov(*_a, **_k):
            raise AssertionError("provision lancé malgré le REFUS d'isolation")

        self._patch(cli._runner, "launch_phase_idempotent", _boom_launch)
        self._patch(cli, "_provision_via_bash", _boom_prov)
        with self.assertRaises(cli._UsageError):
            _engine(_topo(_LIMA_SOLO), "layers", ["up", "storage-simple"], "solo")

    def test_refusal_via_main_maps_to_code_2(self):
        # Bout-en-bout par main() : la garde top-level de cmd_up (`_assert_bench_target`) LÈVE
        # → main mappe _UsageError en code 2. Vaut pour le chemin python comme bash (garde
        # AVANT le routage du flag) — la garde d'isolation s'applique aux DEUX engines.
        def _refuse(action):
            raise cli._UsageError(f"REFUS : `{action}` cible non-banc (test)")

        self._patch(cli, "_assert_bench_target", _refuse)
        self._patch(cli, "_ready_nodes", lambda *_a, **_k: [])
        self._patch(cli, "_real_vms", lambda *_a, **_k: [])
        path = _tmp(_LIMA_SOLO)
        self.addCleanup(os.unlink, path)
        code, _, err = _capture(["up", "-f", path, "--yes", "--engine", "python"])
        self.assertEqual(code, 2)
        self.assertIn("REFUS", err)


if __name__ == "__main__":
    unittest.main()
