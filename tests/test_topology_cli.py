"""Tests de la façade CLI de l'outil déclaratif (scripts/topology.py, ADR 0056 P3).

unittest stdlib (lancé par `pnpm test:python` = unittest discover -s tests). La
CLI est conçue ARGV-INJECTABLE (`main(argv)`) : on appelle `main([...])` et on
asserte la valeur de RETOUR (code de sortie) + la sortie capturée, SANS subprocess
(rapide, pur). La logique métier est déjà testée dans test_nestor.py ;
ici on couvre la façade : dispatch, codes de sortie, mapping des exceptions,
garde-fou byte-identique de `diff`.
"""

import contextlib
import datetime as dt
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def dt_today() -> str:
    """Date ISO d'aujourd'hui (UTC) — pour fabriquer un run FRAIS dans une fixture."""
    return dt.datetime.now(tz=dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# scripts/topology.py n'est pas un module importable par nom (dossier scripts/
# sans __init__) : on le charge par chemin, comme un point d'entrée.
_SPEC = importlib.util.spec_from_file_location(
    "topology_cli", os.path.join(_ROOT, "scripts", "topology.py")
)
cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cli)

# Sondes RÉELLES captées au chargement, AVANT tout stub de test — pour vérifier le
# gating par terrain (ADR 0084/0108) indépendamment de l'ordre des tests (les setUp
# remplacent cli._real_vms/_ready_nodes ; ces références-ci restent les vraies).
_PRISTINE_REAL_VMS = cli._real_vms
_PRISTINE_READY_NODES = cli._ready_nodes

# ── Blindage anti-provisionnement (filet de sécurité module) ──────────────────
# Aucun test ne doit JAMAIS lancer un VRAI run-phases.sh / limactl / ansible-runner
# (un test mal stubé a déjà provisionné 4 VMs Lima en démarrant un montage réel).
# setUpModule remplace cli.subprocess.run par un DEFAULT-DENY : tout appel touchant
# le provisioning ÉCHOUE bruyamment (CI rouge) au lieu de monter un banc en silence.
# Les tests qui veulent observer un argv réinstallent leur _spy par-dessus ; leur
# addCleanup restaure ce garde-fou (jamais le vrai subprocess.run).
_REAL_SUBPROCESS_RUN = cli.subprocess.run  # capturé une fois, JAMAIS rendu aux tests
_FORBIDDEN_TOKENS = ("run-phases.sh", "limactl", "ansible-runner")


def _deny_run(argv, *a, **k):
    """Default-deny : intercepte tout appel subprocess de provisioning réel."""
    flat = " ".join(map(str, argv)) if isinstance(argv, (list, tuple)) else str(argv)
    if any(tok in flat for tok in _FORBIDDEN_TOKENS) or ("kubectl" in flat and "scale" in flat):
        raise AssertionError(
            f"TEST NON BLINDÉ : appel subprocess RÉEL de provisionnement intercepté — {flat!r}. "
            "Le test doit stuber cli.subprocess.run (et toutes les closures internes "
            "_runphases/run_cni de cmd_bootstrap_seq)."
        )
    # kubectl get / config view (lecture) : neutralisé en CompletedProcess vide (déterminisme).
    return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")


def _install_graph_passthrough(test):
    """ADR 0083 : `expected_phase_sequence` shelle MAINTENANT le graphe atomique
    (rollback-lib.sh via `bash -c`) pour DÉRIVER l'ordre des couches — y compris pour
    les chemins qui utilisaient avant une table figée (`_PATH_TAIL`, supprimée). Le
    default-deny du module (`_deny_run`) rendrait un `stdout` vide à ces appels → le
    graphe résoudrait une queue VIDE (preview/next ne verraient que le socle). Ce helper
    installe un spy qui LAISSE PASSER les appels au graphe vers le VRAI subprocess (local,
    déterministe, sans banc) et ne DÉNIE que les tokens de provisionnement réel.

    `cli.subprocess` est le MÊME objet module que `nestor.layers.subprocess` : poser
    `cli.subprocess.run` suffit pour les deux. Restauré au `_deny_run` du module."""
    real_run = _REAL_SUBPROCESS_RUN

    def _spy(argv, *a, **k):
        flat = " ".join(map(str, argv)) if isinstance(argv, (list, tuple)) else str(argv)
        if any(tok in flat for tok in _FORBIDDEN_TOKENS) or ("kubectl" in flat and "scale" in flat):
            return _deny_run(argv, *a, **k)  # provisionnement réel : refus bruyant
        return real_run(argv, *a, **k)  # tout le reste (le GRAPHE) tourne pour de vrai

    orig = cli.subprocess.run
    cli.subprocess.run = _spy
    test.addCleanup(setattr, cli.subprocess, "run", orig)


_REAL_ASSERT_IDENTITY = cli._assert_target_identity  # garde d'isolation réelle
_REAL_WAIT_HEALTHY = cli._wait_layer_healthy  # gate de santé réelle (#355)


def setUpModule():
    cli.subprocess.run = _deny_run
    # Garde d'isolation neutralisée PAR DÉFAUT : les tests métier (install/next/destroy/…)
    # n'ont pas de contexte kubectl estampillé et ne doivent pas être bloqués par elle.
    # La classe `TargetIdentityGuard` la RÉACTIVE explicitement pour la tester
    # (cf. _REAL_ASSERT_IDENTITY).
    cli._assert_target_identity = lambda *a, **k: None
    # Gate de santé (#355) neutralisée PAR DÉFAUT (renvoie sain) : sans banc, sonder le
    # dernier maillon bouclerait 30×4s. Les tests de `next` stubent déjà launch_phase ;
    # la gate elle-même est testée à part (NextHealthGate) avec sa propre stub.
    cli._wait_layer_healthy = lambda phase, **kw: True


def tearDownModule():
    cli.subprocess.run = _REAL_SUBPROCESS_RUN
    cli._assert_target_identity = _REAL_ASSERT_IDENTITY
    cli._wait_layer_healthy = _REAL_WAIT_HEALTHY


from nestor import (  # noqa: E402
    derive_run_params,
    load_topology,
    render_lima_inventory,
    render_prod_inventory,
)
from nestor.model import topology_from_dict  # noqa: E402

_EXAMPLE = os.path.join(_ROOT, "topologies", "dirqual.example.yaml")


def _example_as_lima(test):
    """Copie temporaire de _EXAMPLE forcée en terrain `local` (nettoyée en cleanup).

    Les tests du comportement BANC (créer les VMs `up`, warning d'alignement shell,
    délégation `run-phases.sh up`) doivent viser une topo lima : depuis ADR 0084/0108, une
    topo prod (terrain non local) n'a plus la phase `up` ni le warning banc. _EXAMPLE est prod
    (`terrain: baremetal`) → on flippe `catalog.terrain` vers `local` pour ces cas."""
    with open(_EXAMPLE, encoding="utf-8") as f:
        body = f.read().replace("terrain: baremetal", "terrain: local")
    path = _tmp(body)
    test.addCleanup(os.unlink, path)
    return path


_INVALID_TOPO = """\
catalog:
  topology: bancal
  terrain: baremetal
nodes:
  - name: x
    roles: [master]
"""

_HA_NO_VIP = """\
catalog:
  topology: ha
  terrain: baremetal
nodes:
  - name: cp1
    roles: [control]
  - name: cp2
    roles: [control]
"""


def _capture(argv):
    """Lance main(argv) ; renvoie (code, stdout, stderr).

    Isole os.environ : `main()` appelle `_default_kubeconfig_to_bench()` qui POSE
    `os.environ["KUBECONFIG"]` quand le banc « existe » (stub) — sans restauration,
    ce KUBECONFIG fuiterait vers les _capture suivants et fausserait la garde
    d'isolation (qui retourne tôt si KUBECONFIG est exporté). On restaure l'env."""
    saved_env = os.environ.copy()
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
    return code, out.getvalue(), err.getvalue()


def _tmp(content):
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


@contextlib.contextmanager
def _stdin(text):
    """Alimente sys.stdin avec `text` le temps du bloc (réponses d'un assistant)."""
    saved = sys.stdin
    sys.stdin = io.StringIO(text)
    try:
        yield
    finally:
        sys.stdin = saved


class StackValidate(unittest.TestCase):
    """`stack validate` : verdict de schéma (0 valide / 1 invalide ou absent)."""

    def test_example_is_valid(self):
        code, out, _ = _capture(["stack", "validate", "-f", _EXAMPLE])
        self.assertEqual(code, 0)
        self.assertIn("valide", out)

    def test_invalid_role_rejected(self):
        path = _tmp(_INVALID_TOPO)
        self.addCleanup(os.unlink, path)
        code, _, err = _capture(["stack", "validate", "-f", path])
        self.assertEqual(code, 1)
        self.assertIn("erreur", err)

    def test_ha_without_vip_rejected(self):
        path = _tmp(_HA_NO_VIP)
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["stack", "validate", "-f", path])
        self.assertEqual(code, 1)

    def test_missing_file_is_business_error(self):
        code, _, err = _capture(["stack", "validate", "-f", "/nope/topology.yaml"])
        self.assertEqual(code, 1)
        self.assertIn("erreur", err)


class Generate(unittest.TestCase):
    def test_prod_inventory_matches_facade(self):
        # generate doit ré-émettre EXACTEMENT render_prod_inventory (invariant P1).
        code, out, _ = _capture(["artifact", "generate", "-f", _EXAMPLE, "--kind", "prod"])
        self.assertEqual(code, 0)
        self.assertEqual(out, render_prod_inventory(load_topology(_EXAMPLE), "dirqual"))

    def test_lima_inventory_matches_facade(self):
        topo = load_topology(_EXAMPLE)
        # l'exemple est prod ; on force --kind bench avec un HOME fixe.
        code, out, _ = _capture(
            ["artifact", "generate", "-f", _EXAMPLE, "--kind", "bench", "--lima-home", "/H"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, render_lima_inventory(topo, "/H", "dirqual"))

    def test_run_params_yaml_reparses_to_derivation(self):
        import yaml

        code, out, _ = _capture(["artifact", "generate", "-f", _EXAMPLE, "--what", "run-params"])
        self.assertEqual(code, 0)
        self.assertEqual(yaml.safe_load(out), derive_run_params(load_topology(_EXAMPLE)))

    def test_output_to_file(self):
        dst = _tmp("")
        self.addCleanup(os.unlink, dst)
        code, out, _ = _capture(["artifact", "generate", "-f", _EXAMPLE, "-o", dst])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")  # rien sur stdout quand -o
        with open(dst, encoding="utf-8") as f:
            self.assertEqual(f.read(), render_prod_inventory(load_topology(_EXAMPLE), "dirqual"))

    def test_output_to_invalid_dir_is_usage_error(self):
        # -o vers un répertoire absent = destination invalide fournie en argument
        # → erreur d'usage (code 2), pas erreur métier (code 1).
        code, _, err = _capture(
            ["artifact", "generate", "-f", _EXAMPLE, "-o", "/nope/nope/inv.yaml"]
        )
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class Diff(unittest.TestCase):
    def test_prod_invariant_holds(self):
        # topologies/socle.example.yaml régénère hosts.example.yaml à l'octet → code 0, vide.
        code, out, _ = _capture(["artifact", "diff", "-f", _EXAMPLE, "--kind", "prod"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_drift_detected(self):
        # comparer l'inventaire prod régénéré à une référence DIFFÉRENTE → code 1.
        ref = _tmp("# pas l'inventaire attendu\n")
        self.addCleanup(os.unlink, ref)
        code, out, _ = _capture(
            ["artifact", "diff", "-f", _EXAMPLE, "--kind", "prod", "--against", ref]
        )
        self.assertEqual(code, 1)
        self.assertIn("généré", out)  # un diff unifié a été émis

    def test_missing_reference_is_usage_error(self):
        code, _, err = _capture(
            ["artifact", "diff", "-f", _EXAMPLE, "--kind", "prod", "--against", "/nope.yaml"]
        )
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_lima_requires_against(self):
        # pas de golden Lima versionné → --against obligatoire (code 2 sans).
        code, _, err = _capture(["artifact", "diff", "-f", _EXAMPLE, "--kind", "bench"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_default_reference_is_hosts_example(self):
        # Le garde-fou CI (lint:topology-drift) compare au .EXAMPLE versionné, JAMAIS
        # au hosts.yaml réel (gitignoré). Verrouille la cible du défaut contre une
        # régression silencieuse de _PROD_INVENTORY.
        self.assertTrue(cli._PROD_INVENTORY.endswith("bootstrap/hosts.example.yaml"))

    def test_default_kind_and_against_resolve_to_prod(self):
        # sans --kind ni --against, l'exemple (terrain baremetal → rendu prod) doit tenir
        # l'invariant — garantit que le défaut de la cible CI est exécutable tel quel.
        code, out, _ = _capture(["artifact", "diff", "-f", _EXAMPLE])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class Epreuves(unittest.TestCase):
    def test_lists_playable(self):
        # --declared : mode statique déterministe (pas de dépendance au banc réel).
        code, out, _ = _capture(["test", "scenarios", "-f", _EXAMPLE, "--declared"])
        self.assertEqual(code, 0)
        self.assertIn("jouables", out)
        self.assertIn("topologie déclarée", out)
        self.assertIn("vérifié au lancement, P5", out)  # n'en lance aucune

    def test_runtime_marks_layers(self):
        # Banc joignable : marque ✓ prête / ○ couche à monter selon les couches RÉELLES.
        orig_ready, orig_obs, orig_exists = (
            cli._ready_nodes,
            cli._observed_layers,
            cli.os.path.exists,
        )
        cli._ready_nodes = lambda *_a: ["node1"]  # banc up
        cli._observed_layers = lambda phases: {"metrics-server"}  # seul metrics monté
        # `test scenarios -f _EXAMPLE` → stack `socle` : le code sonde `.kubeconfigs/socle.config`.
        _bp = cli._bench_kubeconfig_path(cli._stack_id(_EXAMPLE))
        cli.os.path.exists = lambda p: True if p == _bp else orig_exists(p)
        self.addCleanup(setattr, cli, "_ready_nodes", orig_ready)
        self.addCleanup(setattr, cli, "_observed_layers", orig_obs)
        self.addCleanup(setattr, cli.os.path, "exists", orig_exists)
        code, out, _ = _capture(["test", "scenarios", "-f", _EXAMPLE])
        self.assertEqual(code, 0)
        self.assertIn("état réel du banc", out)
        self.assertIn("prête", out)
        self.assertIn("couche à monter", out)  # une couche non montée → marquée

    def test_all_shows_excluded(self):
        code, out, _ = _capture(["test", "scenarios", "-f", _EXAMPLE, "--all"])
        self.assertEqual(code, 0)
        self.assertIn("exclues", out)
        self.assertIn("offensif", out)  # 17-21 exclus en prod (ADR 0025)

    def _stub_bench_up(self, observed):
        # banc joignable + couches `observed` montées + cible banc OK (pas de vrai SSH).
        orig = {
            "_ready_nodes": cli._ready_nodes,
            "_observed_layers": cli._observed_layers,
            "_assert_target_identity": cli._assert_target_identity,
        }
        cli._ready_nodes = lambda *_a: ["node1"]
        cli._observed_layers = lambda phases: observed
        cli._assert_target_identity = lambda *a, **k: None
        self._orig_exists = cli.os.path.exists
        # les tests qui utilisent ce stub lancent `test scenarios -f _EXAMPLE` → stack `socle`.
        _bp = cli._bench_kubeconfig_path(cli._stack_id(_EXAMPLE))
        cli.os.path.exists = lambda p: True if p == _bp else self._orig_exists(p)
        for k, v in orig.items():
            self.addCleanup(setattr, cli, k, v)
        self.addCleanup(setattr, cli.os.path, "exists", self._orig_exists)
        # capte l'appel run-all.sh sans l'exécuter ; laisse passer les autres subprocess
        # (resolve_layers shelle le graphe atomique → a besoin du vrai .stdout).
        self._sp_calls = []
        orig_run = cli.subprocess.run

        class _CP:
            returncode = 0

        def fake(argv, **kw):
            if isinstance(argv, list) and any("run-all.sh" in str(a) for a in argv):
                self._sp_calls.append((argv, kw.get("env", {})))
                return _CP()
            return orig_run(argv, **kw)

        cli.subprocess.run = fake
        self.addCleanup(setattr, cli.subprocess, "run", orig_run)

    def test_run_plays_only_ready_non_destructive_by_default(self):
        # --run (sans --full) : dérive ONLY des épreuves PRÊTES NON destructives ; délègue
        # à run-all.sh ; les ssh/offensif/chaos sont EXCLUS (pas de BANC=1).
        self._stub_bench_up({"metrics-server", "storage-simple", "ceph", "sc"})
        code, out, _ = _capture(["test", "scenarios", "-f", _EXAMPLE, "--run"])
        self.assertEqual(code, 0)
        self.assertTrue(self._sp_calls, "run-all.sh aurait dû être appelé")
        argv, env = self._sp_calls[-1]
        self.assertEqual(argv[0], "bash")
        self.assertIn("run-all.sh", argv[1])
        self.assertIn("ONLY", env)  # sélection dérivée passée à run-all.sh
        self.assertNotIn("BANC", env)  # pas de --full → pas d'offensif

    def test_run_full_adds_banc_env_for_offensive(self):
        self._stub_bench_up({"metrics-server", "storage-simple", "ceph", "sc"})
        code, _, _ = _capture(["test", "scenarios", "-f", _EXAMPLE, "--run", "--full"])
        self.assertEqual(code, 0)
        _, env = self._sp_calls[-1]
        self.assertEqual(env.get("BANC"), "1")  # --full → BANC=1 (gardes offensifs ADR 0025)

    def test_run_without_bench_is_usage_error(self):
        # --run sans banc joignable (état réel) → erreur d'usage, ne lance rien.
        code, _, err = _capture(["test", "scenarios", "-f", _EXAMPLE, "--run", "--declared"])
        self.assertEqual(code, 2)
        self.assertIn("banc", err.lower())

    def test_invalid_topology_is_business_error(self):
        path = _tmp("nodes:\n  - name: x\n    roles: [master]\n")
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["test", "scenarios", "-f", path])
        self.assertEqual(code, 1)


class Runs(unittest.TestCase):
    _HIST = """\
runs:
  - id: r1
    date: 2026-06-01T00:00:00Z
    profil: ceph
    topologie: multi-node-3
    commit: abc
"""

    def test_reads_history_always_zero(self):
        # 'runs' est informatif : code 0 même si un chemin est périmé (le verdict
        # bloquant de CI reste `artifact check-freshness`, non dupliqué).
        hist = _tmp(self._HIST)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["artifact", "runs", "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("run(s) consigné", out)

    def test_target_on_history_without_target_falls_back(self):
        # --target sur un historique sans champ `target` (rétrocompat) → avis
        # explicite + état global, code 0 (pas un plantage).
        hist = _tmp(self._HIST)  # _HIST n'a pas de champ target
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["artifact", "runs", "--history", hist, "--target", "atlas"])
        self.assertEqual(code, 0)
        self.assertIn("aucune entrée ne porte de chemin", out)

    def test_missing_history_is_business_error(self):
        code, _, err = _capture(["artifact", "runs", "--history", "/nope/runs.yaml"])
        self.assertEqual(code, 1)
        self.assertIn("erreur", err)


class CheckFreshness(unittest.TestCase):
    """`artifact check-freshness` (ex-check-freshness.sh) : verdict BLOQUANT par chemin.
    Codes : 0 frais / 1 périmé / 2 aucune preuve (cron CI, ADR 0042/0045)."""

    def _hist_with_fresh_atlas(self):
        # atlas + storage-real datés d'AUJOURD'HUI → sous les seuils (7 j / 30 j).
        today = dt.datetime.now(tz=dt.UTC).date().isoformat()
        return f"""\
runs:
  - id: a
    date: {today}T00:00:00Z
    profil: ceph
    topologie: multi-node-3
    target: atlas
  - id: s
    date: {today}T00:00:00Z
    profil: local-path
    topologie: multi-node-3
    target: storage-real
"""

    def test_fresh_obligatoires_zero(self):
        hist = _tmp(self._hist_with_fresh_atlas())
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["artifact", "check-freshness", "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("Chemins obligatoires frais", out)

    def test_perime_returns_1(self):
        # atlas daté de 2026-01-01, largement au-delà du seuil 7 j (now = réel).
        hist = _tmp(
            "runs:\n  - id: old\n    date: 2026-01-01T00:00:00Z\n"
            "    profil: ceph\n    topologie: multi-node-3\n    target: atlas\n"
        )
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["artifact", "check-freshness", "--history", hist])
        self.assertEqual(code, 1)
        self.assertIn("::warning::", out)
        self.assertIn("atlas", out)

    def test_no_history_no_logs_returns_2(self):
        # Historique absent ET pas de runs/ accessible (on pointe _RUNS_DIR ailleurs
        # via un cwd neutre n'est pas possible : _RUNS_DIR est codé). On vérifie au
        # moins le code 2 quand le repli ne trouve aucun log — via un history vide ET
        # un _RUNS_DIR temporaire (mock).
        with mock.patch.object(cli, "_RUNS_DIR", "/nope/runs/xyz"):
            code, out, _ = _capture(["artifact", "check-freshness", "--history", "/nope/h.yaml"])
        self.assertEqual(code, 2)
        self.assertIn("Aucune preuve de banc", out)


class Kubectl(unittest.TestCase):
    """`nestor kubectl …` : kubectl sur la cible de la stack active (ex-`nestor env`)."""

    _BANC_TOPO = (
        "catalog: {topology: banc, terrain: local}\n"
        "layers: [storage-simple]\n"
        "nodes:\n  - {name: node1, roles: [control, worker]}\n"
        "storage: {backend: local-path}\n"
    )

    def _topo_file(self) -> str:
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self._BANC_TOPO)
        self.addCleanup(os.unlink, path)
        return path

    def test_passes_args_to_kubectl_with_safe_kubeconfig(self):
        # `nestor kubectl get pods -A` → exécute `kubectl get pods -A` avec un KUBECONFIG
        # forcé vers la cible SÛRE (_bench_kubeconfig), JAMAIS ~/.kube/config (la prod).
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["argv"] = list(argv)
            seen["kubeconfig"] = (k.get("env") or {}).get("KUBECONFIG")
            return subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            code = cli.main(["kubectl", "-f", self._topo_file(), "get", "pods", "-A"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"], ["kubectl", "get", "pods", "-A"])
        # KUBECONFIG forcé (jamais None / ~/.kube/config implicite).
        self.assertIsNotNone(seen["kubeconfig"])
        self.assertNotIn(".kube/config", seen["kubeconfig"] or "")

    def test_returns_kubectl_exit_code(self):
        def _fake_run(argv, *a, **k):
            return subprocess.CompletedProcess(args=argv, returncode=7)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            code = cli.main(["kubectl", "-f", self._topo_file(), "get", "nodes"])
        self.assertEqual(code, 7)

    def test_poison_kubeconfig_env_is_ignored_when_bench_exists(self):
        # RÉGRESSION (banc 2026-07-12) : un `KUBECONFIG=/dev/null` POISON dans le shell
        # (posé par un `stack select` fait avant que le banc soit monté, puis figé) ne doit
        # PAS primer — sinon tout `nestor kubectl` retombe sur localhost:8080 alors que le
        # banc est vivant. `_bench_kubeconfig` l'IGNORE (via `_operator_kubeconfig`) et résout
        # le banc. On crée un kubeconfig de banc valide et on vérifie qu'il l'emporte sur le
        # poison. (Sans banc, /dev/null resterait la cible LÉGITIME du point 4 — autre cas.)
        stack = cli._active_stack_name(None)
        bench = cli._bench_kubeconfig_path(stack)
        os.makedirs(os.path.dirname(bench), exist_ok=True)
        created = not os.path.exists(bench)
        with open(bench, "w", encoding="utf-8") as f:
            f.write("apiVersion: v1\nkind: Config\n")
        if created:
            self.addCleanup(lambda: os.path.exists(bench) and os.unlink(bench))

        with mock.patch.dict(os.environ, {"KUBECONFIG": os.devnull}):
            resolved = cli._bench_kubeconfig()
        # Le poison /dev/null est ignoré → on résout le banc, pas /dev/null.
        self.assertEqual(resolved, bench)
        self.assertNotEqual(resolved, os.devnull)

    def test_valid_kubeconfig_env_is_respected(self):
        # L'inverse : un `KUBECONFIG` exporté RÉELLEMENT exploitable (intention opérateur,
        # ADR 0090) prime toujours — on ne l'ignore pas comme le poison.
        valid = _tmp("apiVersion: v1\nkind: Config\n")
        self.addCleanup(os.unlink, valid)
        with mock.patch.dict(os.environ, {"KUBECONFIG": valid}):
            self.assertEqual(cli._bench_kubeconfig(), valid)

    def test_flag_in_head_passes_through(self):
        # Régression (vécu au banc) : `nestor kubectl -n rook-ceph get pods` échouait
        # « unrecognized arguments: -n » — argparse `nargs=REMAINDER` ne capture pas un flag
        # en TÊTE. Le découpage amont (`_split_passthrough`) le transmet BRUT à kubectl.
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["argv"] = list(argv)
            return subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            code = cli.main(["kubectl", "-n", "rook-ceph", "get", "pods"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"], ["kubectl", "-n", "rook-ceph", "get", "pods"])

    def test_exec_dashdash_preserved_not_consumed_as_file(self):
        # Un `--` d'exec (`exec pod -- ceph …`) n'est PAS un `--` de tête : il doit rester
        # dans le passthrough (transmis à kubectl), pas être avalé par le découpage `-f`.
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["argv"] = list(argv)
            return subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            code = cli.main(["kubectl", "-n", "rook-ceph", "exec", "pod", "--", "ceph", "status"])
        self.assertEqual(code, 0)
        self.assertEqual(
            seen["argv"], ["kubectl", "-n", "rook-ceph", "exec", "pod", "--", "ceph", "status"]
        )

    def test_leading_dashdash_stripped(self):
        # `nestor kubectl -- -n ns get pods` : le `--` de TÊTE (échappement) est retiré, pas
        # transmis à kubectl (qui l'interpréterait comme « fin des options » → aide).
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["argv"] = list(argv)
            return subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            code = cli.main(["kubectl", "--", "-n", "ns", "get", "pods"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"], ["kubectl", "-n", "ns", "get", "pods"])

    def test_request_timeout_flag_precedes_args_not_after_exec_dashdash(self):
        # Régression (constaté au banc) : `_kubectl` ajoutait `--request-timeout` EN FIN
        # d'argv → pour un `exec pod -- gitea …`, le flag atterrissait APRÈS le `--`, donc
        # passé à `gitea` (« flag not defined ») → tout geste seed cassé. Le flag GLOBAL doit
        # précéder la sous-commande.
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["argv"] = list(argv)
            return subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            cli._kubectl("-n", "gitea", "exec", "pod", "--", "gitea", "admin", "user", "list")
        argv = seen["argv"]
        # --request-timeout est juste après `kubectl`, AVANT le `--` de l'exec.
        self.assertEqual(argv[0], "kubectl")
        self.assertTrue(argv[1].startswith("--request-timeout"))
        self.assertLess(argv.index("--request-timeout=5s"), argv.index("--"))

    def test_prod_stack_targets_declared_kubeconfig_not_bench(self):
        # Stack PROD active : `nestor kubectl` doit viser le kubeconfig DÉCLARÉ (ADR 0090),
        # PAS le banc — même si main() pose un défaut banc auto (_KUBECONFIG_AUTO_BENCH).
        # Régression : sinon `nestor kubectl` taperait le banc avec la prod sélectionnée.
        prod = (
            "catalog: {topology: dirqual, terrain: baremetal}\n"
            "nodes:\n  - {name: dirqual1, roles: [control, worker]}\n"
            "storage: {backend: ceph}\n"
            "kubeconfig: ~/.kube/dirqual.config\n"
        )
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prod)
        self.addCleanup(os.unlink, path)
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["kc"] = (k.get("env") or {}).get("KUBECONFIG")
            return subprocess.CompletedProcess(args=argv, returncode=0)

        # Simule le défaut auto-banc posé par main() (le piège que le fix neutralise).
        with (
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(cli, "_KUBECONFIG_AUTO_BENCH", True),
            mock.patch.object(cli.subprocess, "run", _fake_run),
        ):
            # défaut auto-banc en place (banc de la stack active, ADR 0102 volet B)
            os.environ["KUBECONFIG"] = cli._bench_kubeconfig_path(cli._active_stack_name(None))
            cli.cmd_kubectl(
                __import__("argparse").Namespace(file=path, kubectl_args=["get", "nodes"])
            )
        self.assertIn("dirqual.config", seen["kc"])  # vise la PROD, pas le banc
        self.assertNotIn(".kubeconfigs/banc.config", seen["kc"])


class StackIdentity(unittest.TestCase):
    """Identité de stack = NOM DE FICHIER de la topo (ADR 0102 volet B) : `_stack_id`,
    `_bench_kubeconfig_path`, et la réconciliation d'historique `STACK_ID_ALIASES`."""

    def test_stack_id_strips_example_yaml(self):
        # `.example.yaml` (modèle générique) retiré AVANT `.yaml` : ceph.example.yaml → ceph.
        self.assertEqual(cli._stack_id("topologies/ceph.example.yaml"), "ceph")

    def test_stack_id_strips_plain_yaml(self):
        # topo réelle gitignorée : dirqual.yaml → dirqual.
        self.assertEqual(cli._stack_id("topologies/dirqual.yaml"), "dirqual")

    def test_stack_id_resolves_symlink(self):
        # `topology.yaml` (symlink d'activation) → realpath vers la cible réelle, PAS "topology".
        import tempfile

        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        real = os.path.join(d, "ceph.example.yaml")
        with open(real, "w", encoding="utf-8") as f:
            f.write("catalog: {topology: multi-node-3}\n")
        link = os.path.join(d, "topology.yaml")
        os.symlink(real, link)
        self.assertEqual(cli._stack_id(link), "ceph")  # jamais "topology"

    def test_bench_kubeconfig_path_named_by_stack(self):
        self.assertTrue(cli._bench_kubeconfig_path("ceph").endswith("/.kubeconfigs/ceph.config"))
        # stack None → fallback banc générique.
        self.assertTrue(cli._bench_kubeconfig_path(None).endswith("/.kubeconfigs/banc.config"))

    def test_history_alias_reconciles_old_key(self):
        # Les runs consignés avant le renommage (keyés `multi-node-3`) restent visibles pour
        # la stack `ceph` (STACK_ID_ALIASES) — sans réécrire runs-history (ADR 0052).
        from nestor.history import _matches_stack

        self.assertTrue(_matches_stack("multi-node-3", "ceph"))  # ancien alias réconcilié
        self.assertTrue(_matches_stack("ceph", "ceph"))  # correspondance directe
        self.assertFalse(_matches_stack("banc", "ceph"))  # pas de contamination croisée
        self.assertFalse(_matches_stack(None, "ceph"))  # run sans topologie


class OperatorKubeconfig(unittest.TestCase):
    """`_operator_kubeconfig` : le KUBECONFIG de l'env n'est retenu que s'il est EXPLOITABLE.

    Régression (vécue au banc, phase ceph) : un `KUBECONFIG=/dev/null` `eval`é dans le shell
    par `nestor stack select` sur un banc absent (garde ADR 0053) était propagé tel quel aux
    phases Ansible via `os.environ.get("KUBECONFIG") or ctx.kubeconfig_local` — `/dev/null`
    étant truthy, il gagnait le `or` et le module k8s levait « Invalid kube-config. /dev/null
    file is empty », alors que le banc était monté et joignable. Le helper écarte `/dev/null`,
    un fichier vide et un fichier inexistant (valeurs poison) → `None` → le site retombe sur
    le kubeconfig banc rapatrié."""

    def _run_with_env(self, kc_value):
        env = {k: v for k, v in os.environ.items() if k != "KUBECONFIG"}
        if kc_value is not None:
            env["KUBECONFIG"] = kc_value
        with mock.patch.dict(os.environ, env, clear=True):
            return cli._operator_kubeconfig()

    def test_devnull_is_treated_as_absent(self):
        # /dev/null a une taille de 0 → poison, jamais retenu.
        self.assertIsNone(self._run_with_env(os.devnull))

    def test_empty_file_is_treated_as_absent(self):
        fd, path = tempfile.mkstemp(suffix=".config")
        os.close(fd)  # fichier de taille 0
        self.addCleanup(os.unlink, path)
        self.assertIsNone(self._run_with_env(path))

    def test_missing_file_is_treated_as_absent(self):
        self.assertIsNone(self._run_with_env("/n/existe/pas/kube.config"))

    def test_unset_env_returns_none(self):
        self.assertIsNone(self._run_with_env(None))

    def test_usable_kubeconfig_is_returned(self):
        # un fichier non vide (kubeconfig réel exporté par l'opérateur) est retenu tel quel.
        fd, path = tempfile.mkstemp(suffix=".config")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("apiVersion: v1\nkind: Config\n")
        self.addCleanup(os.unlink, path)
        self.assertEqual(self._run_with_env(path), path)


class Ansible(unittest.TestCase):
    """`nestor ansible <playbook>` : playbook sur la stack active, inventaire DÉRIVÉ de la
    topologie (ADR 0098 — `hosts.yaml` supprimé, plus de fichier inventaire pointable)."""

    _PROD_TOPO = (
        "catalog: {topology: dirqual, terrain: baremetal}\n"
        "nodes:\n"
        "  - {name: dirqual1, roles: [control, worker]}\n"
        "  - {name: dirqual2, roles: [worker]}\n"
        "storage: {backend: ceph}\n"
    )

    def _topo_file(self, body: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        self.addCleanup(os.unlink, path)
        return path

    def test_prod_derive_l_inventaire_de_la_topo_dans_un_temp(self):
        # `nestor ansible checks.yaml` sur une topo → l'inventaire passé à ansible-playbook
        # est un TEMP dérivé (contient les nœuds réels), JAMAIS bootstrap/hosts.yaml. Et il
        # porte EXPECTED_STACK_ID=<stack_id> (réarme l'audit-log par identité, ADR 0108).
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["argv"] = list(argv)
            seen["env"] = dict(k.get("env") or {})
            # capture le contenu de l'inventaire AVANT le cleanup (finally).
            inv = argv[argv.index("-i") + 1]
            with open(inv, encoding="utf-8") as f:
                seen["inv_body"] = f.read()
            seen["inv_path"] = inv
            return subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            code = cli.main(["ansible", "-f", self._topo_file(self._PROD_TOPO), "checks.yaml"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"][0], "ansible-playbook")
        self.assertIn("dirqual1", seen["inv_body"])  # nœuds RÉELS dérivés de la topo
        self.assertIn("transport: ssh", seen["inv_body"])  # garde préservée (marqueur ADR 0108)
        self.assertNotIn("hosts.yaml", seen["inv_path"])  # PAS le fichier statique
        # EXPECTED_STACK_ID posé et non vide = l'audit-log est réarmé par identité (ADR 0108).
        # La valeur = le stack_id dérivé du fichier de topo (un temp ici) → on vérifie la
        # présence + la concordance avec le marqueur stack_id de l'inventaire dérivé.
        expected = seen["env"].get("EXPECTED_STACK_ID")
        self.assertTrue(expected)  # posé (non vide)
        self.assertIn(
            f"stack_id: {expected}", seen["inv_body"]
        )  # inventaire et intention concordent
        # le temp est nettoyé après l'exécution (finally).
        self.assertFalse(os.path.exists(seen["inv_path"]))

    def test_passthrough_des_args_ansible(self):
        seen = {}

        def _fake_run(argv, *a, **k):
            seen["argv"] = list(argv)
            return subprocess.CompletedProcess(args=argv, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            cli.main(
                [
                    "ansible",
                    "-f",
                    self._topo_file(self._PROD_TOPO),
                    "checks.yaml",
                    "--limit",
                    "dirqual1",
                    "--check",
                ]
            )
        # les args ansible suivent le playbook, transmis verbatim.
        self.assertIn("--limit", seen["argv"])
        self.assertIn("dirqual1", seen["argv"])
        self.assertIn("--check", seen["argv"])

    def test_retourne_le_code_d_ansible(self):
        def _fake_run(argv, *a, **k):
            return subprocess.CompletedProcess(args=argv, returncode=2)

        with mock.patch.object(cli.subprocess, "run", _fake_run):
            code = cli.main(["ansible", "-f", self._topo_file(self._PROD_TOPO), "checks.yaml"])
        self.assertEqual(code, 2)

    def test_playbook_introuvable_est_une_erreur_d_usage(self):
        # Un playbook inexistant échoue AVANT de dériver le moindre inventaire (code 2).
        def _fail_run(*a, **k):  # ne doit jamais être appelé
            raise AssertionError("ansible-playbook ne doit pas être lancé")

        with mock.patch.object(cli.subprocess, "run", _fail_run):
            code = cli.main(["ansible", "-f", self._topo_file(self._PROD_TOPO), "nexiste-pas.yaml"])
        self.assertEqual(code, 2)  # _UsageError


class Preview(unittest.TestCase):
    """`preview` : LA vue complète VOULU + RÉEL + PLAN (absorbe status + refresh)."""

    _EMPTY_HIST = "runs: []\n"
    # Socle Ceph frais joué SUR LA STACK _EXAMPLE (topologie: multi-node-4) → le
    # match se fait par NOM de stack, donc la fixture doit porter ce nom.
    _SOCLE_FRESH = f"""\
runs:
  - id: r1
    date: {dt_today()}
    target: atlas-ceph
    profil: ceph
    topologie: multi-node-4
    phases:
      up: 1
      bootstrap: 1
      ceph: 1
      sc: 1
"""
    # Run PÉRIMÉ de _EXAMPLE (date vieille → freshness=perime, pas jamais) : le socle
    # est « déjà monté mais pas frais » → « à rejouer », distinct de l'inédit.
    # `topologie` = `stack_id` (nom de fichier, ADR 0102 volet B) : `_EXAMPLE` =
    # `dirqual.example.yaml` → stack `dirqual`. (Un run RÉEL antérieur keyé `multi-node-4`
    # serait réconcilié par `STACK_ID_ALIASES` ; ici on écrit directement la clé actuelle.)
    _SOCLE_STALE = """\
runs:
  - id: r1
    date: 2020-01-01T00:00:00Z
    target: atlas-ceph
    profil: ceph
    topologie: dirqual
    phases:
      up: 1
      bootstrap: 1
      ceph: 1
      sc: 1
"""

    def setUp(self):
        # Stub de l'I/O réelle (limactl/kubectl) : les tests preview NE dépendent PAS
        # du banc réel. Sans VM réelle, pas d'orphelin parasite dans la sortie. On stube
        # AUSSI `_observed_layers` (sondes santé kubectl) → aucune couche applicative vue
        # « saine » par défaut : sinon le test dépend d'un banc en cours de montage.
        self._orig_vms, self._orig_ready = cli._real_vms, cli._ready_nodes
        self._orig_obs = cli._observed_layers
        cli._real_vms = lambda *_a: []
        cli._ready_nodes = lambda *_a: []
        cli._observed_layers = lambda phases: set()
        self.addCleanup(setattr, cli, "_real_vms", self._orig_vms)
        self.addCleanup(setattr, cli, "_ready_nodes", self._orig_ready)
        self.addCleanup(setattr, cli, "_observed_layers", self._orig_obs)
        # ADR 0083 : laisser le graphe atomique (resolve_layers) tourner pour de vrai —
        # sinon `expected_phase_sequence` ne dériverait que le socle (queue vide).
        _install_graph_passthrough(self)

    def test_three_sections_voulu_reel_plan(self):
        # preview absorbe status (VOULU) + refresh (RÉEL) : les 3 sections présentes.
        # Topo LIMA : la section RÉEL affiche les VMs (« VMs à créer ») — propre au
        # banc. En prod, l'état réel = nœuds K8s, pas de VMs (ADR 0090, testé à part).
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["preview", "-f", _example_as_lima(self), "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("VOULU", out)
        self.assertIn("RÉEL", out)
        self.assertIn("PLAN", out)
        # VOULU (ex-status) : nœuds/couches/backend déclarés. La topo dirqual pose `layers`
        # (profil dataops explicite + build, ADR 0112) → la section affiche « couches ».
        self.assertIn("control-planes", out)
        self.assertIn("couches", out)
        # RÉEL (ex-refresh) : les VMs à créer (terrain vierge, stub vms=[]).
        self.assertIn("VMs à créer", out)

    def test_prod_real_is_k8s_nodes_not_vms(self):
        # ADR 0090 : une topo PROD avec `kubeconfig:` déclaré lit l'état RÉEL du
        # cluster K8s (nœuds Ready) et n'affiche AUCUNE section VMs (les machines sont
        # provisionnées hors nestor). preview ne ment plus (« VMs à créer : dirqual* »).
        cli._ready_nodes = lambda *_a, **_k: ["dirqual1", "dirqual2", "dirqual3", "dirqual4"]
        topo_yaml = (
            "catalog: {topology: multi-node-4, profile: dataops, terrain: baremetal}\n"
            "nodes:\n"
            "  - {name: dirqual1, roles: [control, worker]}\n"
            "  - {name: dirqual2, roles: [worker]}\n"
            "storage: {backend: ceph}\n"
            "kubeconfig: ~/.kube/dirqual.config\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        # `--no-input` : le rapatriement assisté (ADR 0090) ne doit JAMAIS prompter en
        # CI (kubeconfig dirqual absent du runner → sinon `input()` bloquerait).
        code, out, _ = _capture(["preview", "-f", path, "--history", hist, "--no-input"])
        self.assertEqual(code, 0)
        self.assertNotIn("VMs à créer", out)  # plus de mensonge VMs en prod
        self.assertNotIn("VMs présentes", out)
        self.assertIn("dirqual1", out)  # nœuds K8s réels affichés
        self.assertIn("nœuds Ready", out)

    def test_prod_without_kubeconfig_reorients_to_stack_select(self):
        # ADR 0090 : preview prod SANS `kubeconfig:` déclaré ne plante pas et ne ment
        # pas — il RÉORIENTE vers `stack select` (qui déclare/rapatrie la cible).
        topo_yaml = (
            "catalog: {topology: multi-node-4, profile: dataops, terrain: baremetal}\n"
            "nodes:\n  - {name: dirqual1, roles: [control, worker]}\n"
            "storage: {backend: ceph}\n"  # PAS de kubeconfig:
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KUBECONFIG", None)
            orig = cli._KUBECONFIG_AUTO_BENCH
            cli._KUBECONFIG_AUTO_BENCH = False
            self.addCleanup(setattr, cli, "_KUBECONFIG_AUTO_BENCH", orig)
            code, _, err = _capture(["preview", "-f", path, "--history", hist, "--no-input"])
        self.assertEqual(code, 0)  # ne plante pas
        self.assertIn("stack select", err)  # réoriente

    def test_hyperconverged_node_annotated_in_voulu(self):
        # Section VOULU : un nœud control+worker s'affiche `<nom>+worker` (ex-status).
        topo_yaml = (
            "catalog: {topology: hc, profile: base, terrain: local}\n"
            "nodes:\n  - {name: node1, roles: [control, worker]}\n"
            "storage: {backend: local-path}\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        code, out, _ = _capture(["preview", "-f", path])
        self.assertEqual(code, 0)
        self.assertIn("node1+worker", out)

    def test_voulu_omits_storage_for_base_profile(self):
        # VOULU : profil base = k8s+CRI+CNI nus → PAS de ligne stockage (ADR 0039).
        topo_yaml = (
            "catalog: {topology: b, profile: base, terrain: local}\n"
            "nodes:\n  - {name: cp1, roles: [control]}\n"
            "storage: {backend: ceph}\n"  # backend déclaré mais inactif en base
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        code, out, _ = _capture(["preview", "-f", path])
        self.assertEqual(code, 0)
        voulu = out.split("RÉEL")[0]  # la section VOULU uniquement
        self.assertIn("profil", voulu)
        self.assertNotIn("stockage", voulu)  # base ne pose pas de stockage

    def test_voulu_shows_storage_for_store_plus(self):
        # VOULU : un profil store+ (dataops) consomme du stockage → backend affiché.
        topo_yaml = (
            "catalog: {topology: d, profile: dataops, terrain: local}\n"
            "nodes:\n  - {name: cp1, roles: [control]}\n"
            "storage: {backend: ceph}\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        code, out, _ = _capture(["preview", "-f", path, "--target", "atlas-ceph"])
        voulu = out.split("RÉEL")[0]
        self.assertIn("stockage : ceph", voulu)

    def test_base_layer_label_mentions_cri(self):
        # La couche base (PLAN) = Kubernetes + CRI containerd + CNI Cilium.
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["preview", "-f", _EXAMPLE, "--target", "socle", "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("CRI containerd", out)

    def test_shows_full_sequence_with_labels(self):
        # Historique frais ET socle RÉELLEMENT présent (VMs + nœud Ready) → socle à-jour,
        # queue à installer ; libellés MÉTIER. Le RÉEL doit confirmer le socle, pas
        # seulement l'historique (sinon « ✓ à-jour » mentirait, cf. le bug VMs détruites).
        cli._real_vms = lambda *_a: ["cp1", "node1", "node2", "node3"]  # nœuds de _EXAMPLE
        cli._ready_nodes = lambda *_a: ["cp1"]
        hist = _tmp(self._SOCLE_FRESH)
        self.addCleanup(os.unlink, hist)
        # `up` (créer les VMs) n'existe qu'en lima (ADR 0084) → topo lima pour ce test banc.
        code, out, _ = _capture(
            ["preview", "-f", _example_as_lima(self), "--target", "atlas-ceph", "--history", hist]
        )
        self.assertEqual(code, 0)
        self.assertIn("créer les VMs", out)  # libellé métier de `up`
        self.assertIn("à-jour", out)  # socle joué ET réel le confirme
        self.assertIn("à installer", out)  # queue
        self.assertIn("datalake", out)  # libellé de queue présent (plan complet)

    def test_fresh_socle_history_but_no_vms_is_all_a_installer(self):
        # Régression (bug vécu) : historique socle FRAIS mais VMs DÉTRUITES (limactl vide) →
        # le plan NE doit PAS afficher « ✓ créer les VMs à-jour » ni « ✓ ceph à-jour ». Le
        # réel prime : socle absent → TOUTE la séquence « à installer ». preview == next.
        cli._real_vms = lambda *_a: []  # aucune VM (banc détruit)
        cli._ready_nodes = lambda *_a: []
        hist = _tmp(self._SOCLE_FRESH)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(
            ["preview", "-f", _EXAMPLE, "--target", "atlas-ceph", "--history", hist]
        )
        self.assertEqual(code, 0)
        # aucune couche du PLAN n'est « à-jour » (lignes commençant par ✓).
        plan_lines = [ln for ln in out.splitlines() if ln.strip().startswith(("✓", "+"))]
        self.assertTrue(plan_lines)  # le plan est bien affiché
        self.assertFalse(
            [ln for ln in plan_lines if ln.strip().startswith("✓")],
            "aucune couche ne doit être à-jour quand les VMs n'existent pas",
        )

    def test_never_run_is_a_installer_not_rejeu(self):
        # Stack jamais montée (historique vide) → « à installer » (inédit), PAS « rejeu ».
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(
            ["preview", "-f", _EXAMPLE, "--target", "atlas-ceph", "--history", hist]
        )
        self.assertEqual(code, 0)
        self.assertIn("à installer", out)
        self.assertNotIn("rejouer", out)  # jamais monté ≠ rejeu

    def test_stale_run_is_a_rejouer(self):
        # Run PÉRIMÉ (date 2020) → « à rejouer » (déjà monté mais pas frais).
        hist = _tmp(self._SOCLE_STALE)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(
            ["preview", "-f", _EXAMPLE, "--target", "atlas-ceph", "--history", hist]
        )
        self.assertEqual(code, 0)
        self.assertIn("à rejouer", out)

    def test_orphan_vms_listed_to_destroy(self):
        # Des VMs réelles hors stack → preview les liste « à détruire d'abord ».
        # Notion propre au BANC (VMs Lima) : en prod, les machines sont hors nestor
        # (ADR 0090) → topo lima pour ce test.
        cli._real_vms = lambda *_a: ["cp9", "cp8"]
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(
            ["preview", "-f", _example_as_lima(self), "--target", "atlas-ceph", "--history", hist]
        )
        self.assertEqual(code, 0)
        self.assertIn("détruire", out)
        self.assertIn("cp9", out)

    def test_prod_probes_return_empty_without_explicit_kubeconfig(self):
        # ADR 0084/0108 (issue #405) : sur terrain NON local (baremetal) sans KUBECONFIG
        # explicite NI kubeconfig rapatrié nommé par la stack, les sondes du RÉEL rendent [] —
        # elles ne sondent PAS le banc Lima (limactl/kubectl banc). `_real_vms("baremetal")`
        # court-circuite avant `limactl` ; `_ready_nodes("baremetal")` avant `kubectl`. Test PUR :
        # pas de subprocess à simuler (le gating retourne [] AVANT tout appel système).
        os.environ.pop("KUBECONFIG", None)
        orig_auto = cli._KUBECONFIG_AUTO_BENCH
        cli._KUBECONFIG_AUTO_BENCH = True  # auto-export banc de main() ≠ intention prod
        self.addCleanup(setattr, cli, "_KUBECONFIG_AUTO_BENCH", orig_auto)
        # PUR + déterministe : on force l'ABSENCE du kubeconfig nommé par la stack (sinon la
        # sonde partirait le lire — cf. le test complémentaire ci-dessous). `_bench_kubeconfig_path`
        # rend un chemin ; on stube `os.path.exists` pour ce chemin uniquement.
        orig_exists = cli.os.path.exists
        cli.os.path.exists = lambda p: False if str(p).endswith(".config") else orig_exists(p)
        self.addCleanup(setattr, cli.os.path, "exists", orig_exists)
        # `_PRISTINE_*` : les vraies sondes captées au chargement du module (avant tout
        # stub) → indépendant de l'ordre des tests. En prod sans cible connue,
        # le gating (ADR 0084) court-circuite AVANT limactl/kubectl → [].
        self.assertEqual(_PRISTINE_REAL_VMS("baremetal"), [])
        self.assertEqual(_PRISTINE_READY_NODES("baremetal"), [])

    def test_prod_probe_reads_stack_named_kubeconfig(self):
        # ADR 0102 volet B : sur terrain prod, si le kubeconfig RAPATRIÉ nommé par la stack
        # active (`.kubeconfigs/<stack>.config`) existe, `_ready_nodes` le SONDE (même cible que
        # `nestor kubectl`) — sans exiger un KUBECONFIG exporté ni un champ `kubeconfig:` déclaré.
        # Régression : sans ça, `nestor kubectl get nodes` voyait la prod mais `preview` la
        # croyait vide (« nœuds Ready : — » → propose de tout réinstaller sur une prod saine).
        os.environ.pop("KUBECONFIG", None)
        orig_auto = cli._KUBECONFIG_AUTO_BENCH
        cli._KUBECONFIG_AUTO_BENCH = True
        self.addCleanup(setattr, cli, "_KUBECONFIG_AUTO_BENCH", orig_auto)
        # Le kubeconfig nommé par la stack EXISTE (on force exists=True pour un *.config) ...
        orig_exists = cli.os.path.exists
        cli.os.path.exists = lambda p: True if str(p).endswith(".config") else orig_exists(p)
        self.addCleanup(setattr, cli.os.path, "exists", orig_exists)
        # ... et kubectl répond avec un nœud Ready (on stube le subprocess, la sonde doit
        # l'ATTEINDRE au lieu de court-circuiter à []).
        orig_run = cli.subprocess.run

        class _R:
            stdout = "dirqual1   Ready   control-plane   32d   v1.34.8\n"

        cli.subprocess.run = lambda *a, **k: _R()
        self.addCleanup(setattr, cli.subprocess, "run", orig_run)
        self.assertEqual(_PRISTINE_READY_NODES("baremetal"), ["dirqual1"])

    def test_never_launches(self):
        # preview est READ-ONLY : le runner ansible n'est JAMAIS appelé.
        called = []
        orig = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: called.append(1)
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        _capture(["preview", "-f", _EXAMPLE, "--target", "atlas-ceph", "--history", hist])
        self.assertEqual(called, [])

    def test_prod_preview_never_mutates(self):
        # ADR 0090/0053 : un preview PROD (kubeconfig déclaré) reste lecture seule —
        # NI mutation (`launch_phase`), NI rapatriement non sollicité (`_fetch_kubeconfig`)
        # sous --no-input. Garde-fou anti-régression d'isolation.
        mutations = []
        orig_launch = cli._runner.launch_phase
        orig_fetch = cli._fetch_kubeconfig
        cli._runner.launch_phase = lambda *a, **k: mutations.append("launch")
        cli._fetch_kubeconfig = lambda *a, **k: mutations.append("fetch")
        self.addCleanup(setattr, cli._runner, "launch_phase", orig_launch)
        self.addCleanup(setattr, cli, "_fetch_kubeconfig", orig_fetch)
        topo_yaml = (
            "catalog: {topology: multi-node-4, profile: dataops, terrain: baremetal}\n"
            "nodes:\n  - {name: dirqual1, roles: [control, worker]}\n"
            "storage: {backend: ceph}\n"
            "kubeconfig: ~/.kube/dirqual.config\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, _, _ = _capture(["preview", "-f", path, "--history", hist, "--no-input"])
        self.assertEqual(code, 0)
        self.assertEqual(mutations, [])  # AUCUNE écriture en chemin lecture prod

    def test_other_topology_run_not_attributed(self):
        # RÉGRESSION (bug « preview faux avec 1cp ») : un run frais d'une AUTRE stack
        # ne doit PAS rendre _EXAMPLE « à-jour ». Match par NOM de stack, sans
        # retombée globale → tout reste « à installer ».
        other = _tmp(self._SOCLE_FRESH.replace("multi-node-4", "multi-node-3"))
        self.addCleanup(os.unlink, other)
        code, out, _ = _capture(
            ["preview", "-f", _EXAMPLE, "--target", "atlas-ceph", "--history", other]
        )
        self.assertEqual(code, 0)
        self.assertNotIn("rien à appliquer", out)
        self.assertIn("à installer", out)  # aucun run de CETTE stack → inédit

    def test_incoherent_target_is_usage_error(self):
        # ADR 0083 : `atlas` est backend-agnostique (plus incohérent sur ceph). Le cas
        # incohérent reste un preset CEPH-ONLY (`storage-real`) sur une topo local-path →
        # erreur d'usage (code 2), comme `next`/`up`.
        topo_yaml = (
            "catalog: {topology: lp, profile: base, terrain: local}\n"
            "nodes:\n  - {name: cp1, roles: [control, worker]}\n"
            "storage: {backend: local-path}\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        code, _, err = _capture(["preview", "-f", path, "--target", "storage-real"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    # (Retiré : test_warns_when_bench_up_but_shell_kubeconfig_unset — le warning
    # « ton shell n'a pas KUBECONFIG » a été supprimé : preview lit déjà le bon banc et
    # `nestor kubectl` rend obsolète le `kubectl` nu qu'on prémunissait.)

    def test_warns_on_backend_drift_ceph_residual(self):
        # #356 : topo local-path (banc.example), mais des SC ceph observées sur le cluster
        # → rook-ceph résiduel orphelin → preview AVERTIT (backend réel ≠ déclaré).
        topo = _tmp(
            "catalog: {topology: t, terrain: local}\n"
            "nodes: [{name: node1, roles: [control, worker]}, {name: node2, roles: [worker]}]\n"
            "storage: {backend: local-path}\n"
        )
        self.addCleanup(os.unlink, topo)
        cli._ready_nodes = lambda *_a: ["node1"]  # cluster joignable → on sonde les SC
        orig_sc = cli._discover_sc_provisioners
        cli._discover_sc_provisioners = lambda: ["rook-ceph.rbd.csi.ceph.com"]
        self.addCleanup(setattr, cli, "_discover_sc_provisioners", orig_sc)
        code, _, err = _capture(["preview", "-f", topo])
        self.assertEqual(code, 0)
        self.assertIn("backend RÉEL `ceph`", err)
        self.assertIn("local-path", err)  # nomme le déclaré
        self.assertIn("0046", err)  # cite la doctrine

    def test_no_backend_drift_warning_when_cluster_down(self):
        # Aucun nœud Ready → on NE sonde pas les SC → pas de faux drift.
        topo = _tmp(
            "catalog: {topology: t, terrain: local}\n"
            "nodes: [{name: node1, roles: [control, worker]}, {name: node2, roles: [worker]}]\n"
            "storage: {backend: local-path}\n"
        )
        self.addCleanup(os.unlink, topo)
        cli._ready_nodes = lambda *_a: []  # cluster down
        orig_sc = cli._discover_sc_provisioners
        cli._discover_sc_provisioners = lambda: ["rook-ceph.rbd.csi.ceph.com"]
        self.addCleanup(setattr, cli, "_discover_sc_provisioners", orig_sc)
        code, _, err = _capture(["preview", "-f", topo])
        self.assertEqual(code, 0)
        self.assertNotIn("backend RÉEL", err)


class Next(unittest.TestCase):
    """`next` : applique LA prochaine couche manquante via runner (1er drift)."""

    def setUp(self):
        # `cmd_next` constate le RÉEL (VMs/nœuds) pour ne pas se fier au seul historique
        # (sinon il sauterait `up`/`bootstrap` sur un banc détruit). Par défaut on simule
        # un SOCLE PRÉSENT : TOUTES les VMs de _EXAMPLE existent + un nœud Ready → up &
        # bootstrap considérés faits (observed_done_phases), et les tests de couches
        # applicatives fonctionnent. Les tests du socle re-stubent vide via _set_real.
        all_vms = ["cp1", "node1", "node2", "node3"]  # nœuds de socle.example
        self._set_real(vms=all_vms, ready=["cp1"])

    def _set_real(self, *, vms, ready):
        orig_vms, orig_ready = cli._real_vms, cli._ready_nodes
        cli._real_vms = lambda *_a: vms
        cli._ready_nodes = lambda *_a: ready
        self.addCleanup(setattr, cli, "_real_vms", orig_vms)
        self.addCleanup(setattr, cli, "_ready_nodes", orig_ready)

    _EMPTY_HIST = "runs: []\n"
    # Historique frais où le socle Ceph est joué → la 1re couche manquante de
    # cluster-dataops est `datalake` (qui A un playbook unitaire, donc applicable).
    _SOCLE_DONE = f"""\
runs:
  - id: r1
    date: {dt_today()}
    profil: ceph
    topologie: multi-node-3
    phases:
      up: 1
      bootstrap: 1
      ceph: 1
      sc: 1
"""

    def test_unknown_target_is_usage_error(self):
        code, _, err = _capture(["next", "-f", _EXAMPLE, "--target", "frobnicate"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_prod_does_not_repropose_installed_layers(self):
        # ADR 0090 (régression du 2026-06-22) : sur une PROD saine (nœuds Ready + socle
        # et couches observés), `next` NE DOIT PAS re-proposer Kubernetes (la 1re couche).
        # Le bug : `next` n'injectait pas le kubeconfig déclaré (contrairement à preview)
        # → `_ready_nodes` vide → état réel « vide » → re-propose K8s sur prod saine.
        self._set_real(vms=["dirqual1"], ready=["dirqual1", "dirqual2", "dirqual3", "dirqual4"])
        orig_obs = cli._observed_layers
        # socle + ceph/sc/datalake/metrics/monitoring/gitops/dataops observés (tout sauf
        # gitops-seed + mlflow), comme le preview prod réel de dirqual.
        cli._observed_layers = lambda phases: {
            p
            for p in phases
            if p in {"ceph", "sc", "datalake", "metrics-server", "monitoring", "gitops", "dataops"}
        }
        self.addCleanup(setattr, cli, "_observed_layers", orig_obs)
        topo_yaml = (
            "catalog: {topology: multi-node-4, profile: dataops, terrain: baremetal}\n"
            "nodes:\n  - {name: dirqual1, roles: [control, worker]}\n"
            "storage: {backend: ceph}\n"
            "kubeconfig: ~/.kube/dirqual.config\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, out, err = _capture(["next", "-f", path, "--history", hist, "--no-input"])
        combined = out + err
        # JAMAIS reproposer Kubernetes/le socle sur une prod saine (le bug).
        self.assertNotIn("Kubernetes", combined)
        self.assertNotIn("CRI", combined)

    def test_prod_all_layers_observed_says_up_to_date(self):
        # RÉGRESSION (prod dirqual 2026-06-22) : prod 100 % installée mais SANS run nestor
        # consigné (freshness="jamais") → `next` doit dire « à jour », PAS « rejeu de la
        # séquence / bootstrap ». diff_phases doit soustraire l'observé même en "jamais".
        self._set_real(vms=["dirqual1"], ready=["dirqual1", "dirqual2", "dirqual3", "dirqual4"])
        orig_obs = cli._observed_layers
        cli._observed_layers = lambda phases: set(phases)  # TOUTES les couches observées
        self.addCleanup(setattr, cli, "_observed_layers", orig_obs)
        topo_yaml = (
            "catalog: {topology: multi-node-4, profile: dataops, terrain: baremetal}\n"
            "nodes:\n  - {name: dirqual1, roles: [control, worker]}\n"
            "storage: {backend: ceph}\n"
            "kubeconfig: ~/.kube/dirqual.config\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        hist = _tmp(self._EMPTY_HIST)  # AUCUN run consigné → freshness "jamais"
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["next", "-f", path, "--history", hist, "--no-input"])
        self.assertEqual(code, 0)
        self.assertIn("à jour", out)
        self.assertNotIn("rejeu", out)  # le bug : « rejeu de la séquence »
        self.assertNotIn("bootstrap", out)

    # Run frais COMPLET (jusqu'à gitops-seed) d'une AUTRE stack (multi-node-3) — ne
    # doit JAMAIS servir de référence à _EXAMPLE (multi-node-4).
    _OTHER_STACK_COMPLETE = f"""\
runs:
  - id: other
    date: {dt_today()}
    target: atlas-ceph
    profil: ceph
    topologie: multi-node-3
    phases:
      up: 1
      bootstrap: 1
      ceph: 1
      sc: 1
      datalake: 1
      monitoring: 1
      gitops: 1
      dataops: 1
      gitops-seed: 1
"""

    def test_other_topology_run_not_attributed(self):
        # RÉGRESSION (divergence next/preview vécue) : `next` ancrait son run de
        # référence sur un fallback `latest_run` GLOBAL → il empruntait le run frais
        # d'une AUTRE topologie (ex. atlas-ceph multi-node-3) et croyait gitops-seed
        # fait → « à jour », alors que `preview` (match par stack) le voyait « à
        # installer ». Comme preview, `next` match par NOM de stack : un run d'une
        # autre topologie ne le rend PAS « à jour ». Réel = socle présent mais aucune
        # couche applicative observée → gitops-seed reste à installer.
        self._set_real(vms=["cp1", "node1", "node2", "node3"], ready=["cp1"])
        orig_obs = cli._observed_layers
        cli._observed_layers = lambda phases: set()
        self.addCleanup(setattr, cli, "_observed_layers", orig_obs)
        hist = _tmp(self._OTHER_STACK_COMPLETE)
        self.addCleanup(os.unlink, hist)
        code, out, err = _capture(
            ["next", "-f", _EXAMPLE, "--target", "atlas-ceph", "--history", hist]
        )
        # AVANT le fix : « à jour » (code 0), le run multi-node-3 attribué à tort.
        # APRÈS : `next` veut monter gitops-seed (manquant) → il NE dit PAS « à jour »
        # et atteint le garde-fou « refusé hors TTY sans --yes » (code 2) — la preuve
        # qu'il a bien VU une couche à monter, là où le run étranger l'aveuglait.
        self.assertNotIn("à jour", out)
        self.assertEqual(code, 2)
        self.assertIn("hors TTY", err)

    def _ensure_inventory(self):
        """Garantit un bootstrap/hosts.yaml (gitignoré, absent en CI) pour `next` ;
        le retire ensuite si on l'a créé. Sinon le garde-fou d'inventaire bloque."""
        inv = os.path.join(_ROOT, "bootstrap", "hosts.yaml")
        if not os.path.exists(inv):
            with open(inv, "w", encoding="utf-8") as f:
                f.write("# inventaire de test (créé puis retiré)\n")
            self.addCleanup(os.unlink, inv)

    def test_applies_one_layer_and_maps_rc(self):
        # `up` appelle runner.launch_phase (stub rc=0) → code 0 ; UNE couche.
        from nestor.runner import RunResult

        self._ensure_inventory()
        calls = []

        def fake(playbook, extravars, pdd, inv, **kw):
            calls.append((playbook, extravars))
            return RunResult(rc=0, status="successful")

        orig = cli._runner.launch_phase
        cli._runner.launch_phase = fake
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._SOCLE_DONE)
        self.addCleanup(os.unlink, hist)
        code, _, _ = _capture(
            ["next", "-f", _EXAMPLE, "--target", "cluster-dataops", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)  # UNE couche montée, pas la séquence
        self.assertTrue(calls[0][0].endswith(".yaml"))

    def test_bench_without_inventory_is_usage_error(self):
        # Topo BANC (lima) sans `.work/inventory.yaml` → erreur d'usage claire (code 2).
        # NB : côté PROD ce cas n'existe plus (ADR 0098 : l'inventaire est dérivé dans un
        # temp à la volée, jamais absent). Seul le banc, dont l'inventaire est posé par le
        # provisioning, peut manquer son fichier (banc non monté).
        if os.path.exists(cli._BENCH_INVENTORY):
            self.skipTest("inventaire banc présent localement — cas testé en CI")
        # VMs présentes (dirqual1-4 déclarés par l'exemple lima) → `next` SAUTE le
        # provisioning `up` et atteint le garde-fou d'inventaire, but du test.
        self._set_real(
            vms=["dirqual1", "dirqual2", "dirqual3", "dirqual4"],
            ready=["dirqual1", "dirqual2", "dirqual3", "dirqual4"],
        )
        orig = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: None
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._SOCLE_DONE)
        self.addCleanup(os.unlink, hist)
        lima = _example_as_lima(self)
        code, _, err = _capture(
            ["next", "-f", lima, "--target", "cluster-dataops", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 2)
        self.assertIn("inventaire du banc absent", err)

    def test_propagates_failure_rc(self):
        from nestor.runner import RunResult

        self._ensure_inventory()
        orig = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: RunResult(rc=2, status="failed")
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._SOCLE_DONE)
        self.addCleanup(os.unlink, hist)
        code, _, _ = _capture(
            ["next", "-f", _EXAMPLE, "--target", "cluster-dataops", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 1)  # run KO → code 1

    def test_upstream_phase_up_delegates_to_run_phases_up(self):
        # PAS de banc (aucune VM) → `next` propose `up` (créer les VMs SEULES, comme le
        # PLAN de preview) et délègue à l'arm `run-phases.sh up` — PAS `socle` (qui
        # monterait tout). Phase par phase : au next suivant, ce serait `bootstrap`.
        import subprocess as sp

        self._set_real(vms=[], ready=[])  # banc inexistant → up est la 1re phase
        # Banc inexistant → aucune couche applicative saine ; neutralise la sonde
        # kubectl pour ne capturer que l'appel `run-phases.sh up`.
        orig_obs = cli._observed_layers
        cli._observed_layers = lambda _phases: set()
        self.addCleanup(setattr, cli, "_observed_layers", orig_obs)
        calls = []
        # ADR 0083 : `expected_phase_sequence` shelle le graphe atomique. On n'intercepte
        # QUE `run-phases.sh` (la délégation observée) et on LAISSE PASSER les appels au
        # graphe (`bash -c`) vers le vrai subprocess — sinon `_rb` planterait sur un retour
        # sans `.stdout`. `_REAL_SUBPROCESS_RUN` = subprocess.run capté avant le deny module.
        real_run = _REAL_SUBPROCESS_RUN

        def fake_run(argv, **kw):
            seq = argv if isinstance(argv, list) else [argv]
            if any("run-phases.sh" in str(c) for c in seq):
                calls.append(argv)
                return sp.CompletedProcess(args=argv, returncode=0)
            return real_run(argv, **kw)  # laisse tourner le GRAPHE pour de vrai

        orig = cli.subprocess.run
        cli.subprocess.run = fake_run
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        # `up` (créer les VMs) n'existe qu'en lima (ADR 0084) → topo lima + target lima.
        code, out, _ = _capture(
            ["next", "-f", _example_as_lima(self), "--target", "atlas", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 0)
        # un appel `run-phases.sh up` (VMs seules), PAS `socle` (tout le socle)
        self.assertTrue(
            any("run-phases.sh" in str(a) and a[-1] == "up" for a in calls),
            f"attendu un appel `run-phases.sh up`, vu : {calls}",
        )
        self.assertFalse(any("socle" in a for a in calls), "ne doit PAS appeler `socle`")

    def test_refuses_without_yes_off_tty(self):
        # Hors TTY sans --yes : la confirmation refuse → code 2, RIEN n'est monté.
        # On neutralise la sonde réelle `_observed_layers` (kubectl) pour ne capturer
        # QUE les appels de montage (sinon les probes kubectl pollueraient `calls`), et
        # `phase_deps` (sinon le pont bash du menu heurterait le stub subprocess ci-dessous).
        orig_obs = cli._observed_layers
        cli._observed_layers = lambda _phases: set()
        self.addCleanup(setattr, cli, "_observed_layers", orig_obs)
        orig_deps = cli.phase_deps
        cli.phase_deps = lambda _backend: {"datalake": set(), "monitoring": set(), "dataops": set()}
        self.addCleanup(setattr, cli, "phase_deps", orig_deps)
        calls = []
        # ADR 0083 : `expected_phase_sequence` shelle le graphe atomique. On LAISSE PASSER
        # le graphe (`bash -c`) vers le vrai subprocess et n'enregistre que les MONTAGES
        # (`run-phases.sh`) dans `calls` — la confirmation refuse AVANT tout montage, donc
        # `calls` doit rester vide même si le graphe a tourné pour de vrai.
        real_run = _REAL_SUBPROCESS_RUN

        def _spy(*a, **k):
            argv = a[0] if a else k.get("args")
            seq = argv if isinstance(argv, list) else [argv]
            if any("run-phases.sh" in str(c) for c in seq):
                calls.append(a)
                return subprocess.CompletedProcess(argv, 0)
            return real_run(*a, **k)  # laisse tourner le GRAPHE pour de vrai

        orig = cli.subprocess.run
        cli.subprocess.run = _spy
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, _, err = _capture(
            ["next", "-f", _EXAMPLE, "--target", "cluster-dataops", "--history", hist]
        )
        self.assertEqual(code, 2)
        self.assertIn("refusé hors TTY", err)  # pas de montage silencieux
        self.assertEqual(calls, [])  # aucun montage lancé


class PreviewNextParityCLI(unittest.TestCase):
    """Parité preview == next AU NIVEAU CLI (cœur de l'étape 1) : pour un MÊME état réel,
    les deux commandes dérivent du MÊME `compute_plan_state` → même verdict. Avant le fix,
    `next` ne faisait que RETIRER l'observé (jamais ré-ajouter une couche que le réel
    contredit) et n'avait pas le garde `if up not in done` → divergence."""

    _ATLAS_LOCAL = """\
catalog:
  topology: atlas-local
  profile: dataops
  terrain: local
nodes:
  - {name: cp1, roles: [control]}
  - {name: node1, roles: [worker]}
  - {name: node2, roles: [worker]}
storage:
  backend: local-path
"""

    def setUp(self):
        # Socle réellement présent (VMs + nœud Ready) → up/bootstrap faits.
        orig_vms, orig_ready = cli._real_vms, cli._ready_nodes
        cli._real_vms = lambda *_a: ["cp1", "node1", "node2"]
        cli._ready_nodes = lambda *_a: ["cp1"]
        self.addCleanup(setattr, cli, "_real_vms", orig_vms)
        self.addCleanup(setattr, cli, "_ready_nodes", orig_ready)
        _install_graph_passthrough(self)
        # Carte de deps DÉTERMINISTE (== ce que phase_deps dérive du graphe).
        orig_deps = cli.phase_deps
        cli.phase_deps = lambda _backend: {
            "storage-simple": set(),
            "metrics-server": set(),
            "monitoring": {"storage-simple"},
            "gitops": {"storage-simple"},
            "dataops": {"monitoring", "storage-simple"},
            "gitops-seed": {"gitops"},
            "mlflow": {"dataops", "monitoring"},
        }
        self.addCleanup(setattr, cli, "phase_deps", orig_deps)
        # Garde inventaire neutralisée (on teste la logique du plan, pas la garde).
        orig_safe = cli._assert_inventory_safe
        cli._assert_inventory_safe = lambda *a, **k: None
        self.addCleanup(setattr, cli, "_assert_inventory_safe", orig_safe)

    def _stub_observed(self, layers):
        orig = cli._observed_layers
        cli._observed_layers = lambda _phases: set(layers)
        self.addCleanup(setattr, cli, "_observed_layers", orig)

    # Historique frais consignant TOUT fait (jusqu'à dataops/mlflow inclus) — mais le réel
    # ne confirmera pas tout (cf. _stub_observed dans chaque test) : c'est le bug à couvrir.
    _ALL_DONE_HIST = f"""\
runs:
  - id: r1
    date: {dt_today()}
    profil: dataops
    topologie: atlas-local
    phases: {{up: 1, bootstrap: 1, storage-simple: 1, metrics-server: 1,
      monitoring: 1, gitops: 1, dataops: 1, mlflow: 1}}
"""

    def _run_both(self, observed, hist_content):
        """Lance preview ET next sur la MÊME fixture/état réel ; renvoie (out_prev, out_next,
        code_next, err_next). `observed` = couches que le cluster confirme saines."""
        self._stub_observed(observed)
        topo = _tmp(self._ATLAS_LOCAL)
        hist = _tmp(hist_content)
        self.addCleanup(os.unlink, topo)
        self.addCleanup(os.unlink, hist)
        code_p, out_p, _ = _capture(["preview", "-f", topo, "--target", "atlas", "--history", hist])
        # next hors TTY sans --yes : s'il VEUT monter une couche → code 2 « refusé hors TTY »
        # (preuve qu'il a VU une couche à monter) ; s'il est à jour → code 0 + « à jour ».
        code_n, out_n, err_n = _capture(
            ["next", "-f", topo, "--target", "atlas", "--history", hist]
        )
        self.assertEqual(code_p, 0)
        return out_p, out_n, code_n, err_n

    def test_history_lies_layer_absent_both_want_to_mount(self):
        # LE BUG (mlflow/marquez) : l'historique dit mlflow fait, mais le cluster ne le
        # confirme PAS (couche à signal absente). preview l'affiche « à installer » ET next
        # veut le monter (n'est PAS « à jour »). Avant le fix : next disait « à jour ».
        observed = {"storage-simple", "metrics-server", "monitoring", "gitops", "dataops"}
        out_p, out_n, code_n, err_n = self._run_both(observed, self._ALL_DONE_HIST)
        # preview : la ligne mlflow doit être marquée « à installer » (pas ✓ à-jour).
        mlflow_line = next(ln for ln in out_p.splitlines() if "MLflow" in ln)
        self.assertIn("à installer", mlflow_line)
        # next : il a VU une couche à monter (mlflow) → refus hors TTY (code 2), PAS « à jour ».
        self.assertNotIn("à jour", out_n)
        self.assertEqual(code_n, 2)
        self.assertIn("hors TTY", err_n)

    def test_all_observed_both_up_to_date(self):
        # Tout est consigné ET le réel confirme TOUT (signal sain) → preview « à-jour »
        # partout (aucun « à installer ») et next dit « à jour » (code 0). Parité positive.
        observed = {
            "storage-simple",
            "metrics-server",
            "monitoring",
            "gitops",
            "registry",
            "buildkit",
            "dataops",
            "mlflow",
            "gitops-seed",
            "portal",
        }
        out_p, out_n, code_n, _ = self._run_both(observed, self._ALL_DONE_HIST)
        self.assertNotIn("à installer", out_p)  # preview : rien à monter
        self.assertEqual(code_n, 0)
        self.assertIn("à jour", out_n)  # next : à jour


class NextInventoryGuard(unittest.TestCase):
    """Garde de CIBLE ANSIBLE (ADR 0053) : `next` visant le banc REFUSE un inventaire
    prod AVANT de lancer ansible-runner. Régression de la faille `next dataops` → prod."""

    # Topo banc (terrain local) visant une couche applicative (dataops local-path).
    _TOPO_LIMA = """\
catalog:
  topology: banc
  profile: dataops
  terrain: local
nodes:
  - {name: node1, roles: [control, worker]}
  - {name: node2, roles: [worker]}
storage:
  backend: local-path
"""
    # Inventaire PROD résiduel (le cas exact de la faille) : identité d'une AUTRE
    # instance (`stack_id: dirqual` + transport ssh, ADR 0108), hôtes génériques
    # cp1/node1 + IP d'exemple 10.0.0.0/22 (ADR 0023).
    _INV_PROD = """\
cloud:
  children:
    control:
    workers:
  vars:
    stack_id: dirqual
    transport: ssh
control:
  hosts:
    cp1: {ansible_host: 10.0.0.11}
workers:
  hosts:
    node1: {ansible_host: 10.0.0.12}
"""

    def setUp(self):
        # Socle présent (up/bootstrap faits) → next vise une couche applicative montée
        # via ansible-runner (le chemin gardé).
        for name, val in (("_real_vms", ["node1", "node2"]), ("_ready_nodes", ["node1"])):
            orig = getattr(cli, name)
            # ADR 0084/0108 : les sondes prennent désormais `terrain` → la lambda doit
            # l'accepter (et l'ignorer), sinon l'arg positionnel écrase la valeur stubée.
            setattr(cli, name, lambda *_a, _v=val: _v)
            self.addCleanup(setattr, cli, name, orig)
        # ADR 0083 : `expected_phase_sequence` shelle le graphe atomique — laisser tourner
        # le graphe pour de vrai (sinon la queue serait vide et `next` ne viserait aucune
        # couche applicative, court-circuitant la garde d'inventaire qu'on teste ici).
        _install_graph_passthrough(self)
        self._stub("_observed_layers", lambda _p: set())
        self._stub("phase_deps", lambda _b: {"storage-simple": set(), "metrics-server": set()})
        # Stub launch_phase : si la garde laissait passer, on le SAURAIT (ne doit JAMAIS
        # être appelé sur un inventaire prod).
        from nestor.runner import RunResult

        self.launched = []
        orig_lp = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: (
            self.launched.append(a) or RunResult(rc=0, status="successful")
        )
        self.addCleanup(setattr, cli._runner, "launch_phase", orig_lp)
        # Une topo lima vise `_BENCH_INVENTORY` : on y écrit un inventaire CONTAMINÉ par
        # des hôtes d'une AUTRE instance (`stack_id: dirqual`, cp1/node1) pour prouver que la
        # garde refuse même via le chemin banc (sauvegarde/restaure l'existant du banc réel).
        self._inv = cli._BENCH_INVENTORY
        self._backup = self._inv + ".test-backup"
        os.makedirs(os.path.dirname(self._inv), exist_ok=True)
        if os.path.exists(self._inv):
            os.rename(self._inv, self._backup)
            self.addCleanup(lambda: os.rename(self._backup, self._inv))
        with open(self._inv, "w", encoding="utf-8") as f:
            f.write(self._INV_PROD)
        if not os.path.exists(self._backup):
            self.addCleanup(lambda: os.path.exists(self._inv) and os.unlink(self._inv))

    def _stub(self, name, fn):
        orig = getattr(cli, name)
        setattr(cli, name, fn)
        self.addCleanup(setattr, cli, name, orig)

    def test_lima_topo_refuses_prod_contaminated_inventory(self):
        # Garde en aval : même si l'inventaire banc est contaminé par des hôtes d'une autre
        # instance, la garde d'identité refuse (filet ultime, indépendant du choix d'inventaire).
        topo = _tmp(self._TOPO_LIMA)
        hist = _tmp("runs: []\n")
        self.addCleanup(os.unlink, topo)
        self.addCleanup(os.unlink, hist)
        code, _, err = _capture(
            ["next", "-f", topo, "--target", "atlas", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 2)  # REFUS (usage)
        self.assertIn("cp1", err)  # nomme les hôtes de l'autre instance menacés
        self.assertIn("0108", err)  # cite la doctrine d'isolation par identité
        self.assertEqual(self.launched, [])  # ansible-runner JAMAIS lancé sur l'autre instance

    def test_lima_topo_uses_bench_inventory(self):
        # CŒUR du fix : une topo lima vise l'inventaire BANC, pas le prod codé en dur. Ici
        # l'inventaire banc est PROPRE et porte l'identité de la stack (`stack_id`, ADR 0108)
        # + le transport `lima` → la garde d'isolation passe (stack_id concordant) et
        # ansible-runner est lancé sur le BANC (inventaire = _BENCH_INVENTORY). L'identité
        # (`stack_id`) est le NOM DE FICHIER de la topo → on l'ancre via un fichier nommé.
        stack = "banc-citation"
        clean_banc_inv = (
            f"cloud:\n  vars:\n    stack_id: {stack}\n    transport: lima\n"
            "control:\n  hosts:\n    node1: {ansible_host: lima-node1}\n"
            "workers:\n  hosts:\n    node2: {ansible_host: lima-node2}\n"
        )
        with open(self._inv, "w", encoding="utf-8") as f:
            f.write(clean_banc_inv)
        topo_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(topo_dir, ignore_errors=True))
        topo = os.path.join(topo_dir, f"{stack}.yaml")  # stack_id == nom de fichier
        with open(topo, "w", encoding="utf-8") as f:
            f.write(self._TOPO_LIMA)
        hist = _tmp("runs: []\n")
        self.addCleanup(os.unlink, hist)
        code, _, _ = _capture(["next", "-f", topo, "--target", "atlas", "--history", hist, "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(self.launched), 1)  # lancé — sur le banc, pas la prod
        # l'inventaire passé à launch_phase est bien celui du BANC
        self.assertIn(".work/inventory.yaml", str(self.launched[0]))


class NextMenu(unittest.TestCase):
    """`next` propose un MENU quand PLUSIEURS couches sont montables (choix d'ordre)."""

    # Topo local-path visant `atlas` : après socle, storage-simple ET metrics-server
    # sont montables (indépendants). Fixture minimale gitignorable.
    _ATLAS_LOCAL = """\
catalog:
  topology: atlas-local
  profile: dataops
  terrain: local
nodes:
  - {name: cp1, roles: [control]}
  - {name: node1, roles: [worker]}
  - {name: node2, roles: [worker]}
storage:
  backend: local-path
"""
    # Socle local-path fait (up+bootstrap), rien d'autre → le menu doit proposer
    # storage-simple (défaut) ET metrics-server.
    _SOCLE_LIGHT_DONE = f"""\
runs:
  - id: r1
    date: {dt_today()}
    profil: dataops
    topologie: atlas-local
    phases: {{up: 1, bootstrap: 1}}
"""

    def setUp(self):
        # Socle réellement présent (toutes VMs + un nœud Ready) → up/bootstrap faits.
        orig_vms, orig_ready = cli._real_vms, cli._ready_nodes
        cli._real_vms = lambda *_a: ["cp1", "node1", "node2"]
        cli._ready_nodes = lambda *_a: ["cp1"]
        self.addCleanup(setattr, cli, "_real_vms", orig_vms)
        self.addCleanup(setattr, cli, "_ready_nodes", orig_ready)
        # ADR 0083 : `expected_phase_sequence` shelle le graphe atomique. Laisser tourner
        # le graphe pour de vrai (sinon la queue serait vide et le menu n'aurait rien à
        # proposer). Les tests qui re-stubent subprocess.run écrasent ce spy mais stubent
        # alors aussi phase_deps (carte figée) → pas de re-shell du graphe.
        _install_graph_passthrough(self)
        # Carte de deps DÉTERMINISTE (== ce que phase_deps dérive du graphe ; prouvé
        # dans test_layers.PhaseDeps) — évite de sheller bash et fige le menu.
        orig_deps = cli.phase_deps
        cli.phase_deps = lambda _backend: {
            "storage-simple": set(),
            "metrics-server": set(),
            "monitoring": {"storage-simple"},
            "gitops": {"storage-simple"},
            "dataops": {"monitoring", "storage-simple"},
            "gitops-seed": {"gitops"},
        }
        self.addCleanup(setattr, cli, "phase_deps", orig_deps)
        # Aucune couche applicative observée par défaut (le banc n'a que le socle) :
        # neutralise la sonde kubectl `_observed_layers` (sinon elle interroge le réel
        # et fausse le menu / capture des appels). Les tests « déjà installé » la
        # re-stubent pour renvoyer la couche présente.
        self._stub_observed(set())
        # Garde de cible Ansible (ADR 0053) : ces tests visent une topo `lima` mais le
        # poste dev peut porter un vrai inventaire PROD (bootstrap/hosts.yaml) que la
        # garde refuse à raison. On la neutralise ici (on teste la logique du menu, pas
        # la garde — celle-ci a ses propres tests, test_isolation + Next).
        orig_safe = cli._assert_inventory_safe
        cli._assert_inventory_safe = lambda *a, **k: None
        self.addCleanup(setattr, cli, "_assert_inventory_safe", orig_safe)
        # Les topos de NextMenu sont en terrain `local` → `_inventory_for` renvoie
        # l'inventaire BANC (`_BENCH_INVENTORY`), pas bootstrap/hosts.yaml. On garantit
        # sa présence (absent en CI où le banc n'existe pas) — créé puis retiré, en
        # sauvegardant un éventuel inventaire banc réel (poste dev).
        inv = cli._BENCH_INVENTORY
        os.makedirs(os.path.dirname(inv), exist_ok=True)
        backup = inv + ".test-backup"
        if os.path.exists(inv):
            os.rename(inv, backup)
            self.addCleanup(lambda: os.rename(backup, inv))
        with open(inv, "w", encoding="utf-8") as f:
            f.write("# inventaire de test (créé puis retiré)\n")
        if not os.path.exists(backup):
            self.addCleanup(lambda: os.path.exists(inv) and os.unlink(inv))

    def _spy_launch(self):
        """Stub launch_phase qui capture la phase (via le playbook) montée."""
        from nestor.runner import RunResult

        mounted = []

        def fake(playbook, extravars, pdd, inv, **kw):
            mounted.append(playbook)
            return RunResult(rc=0, status="successful")

        orig = cli._runner.launch_phase
        cli._runner.launch_phase = fake
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        return mounted

    def _fixtures(self):
        topo = _tmp(self._ATLAS_LOCAL)
        hist = _tmp(self._SOCLE_LIGHT_DONE)
        self.addCleanup(os.unlink, topo)
        self.addCleanup(os.unlink, hist)
        return topo, hist

    def test_yes_picks_default_first_of_path(self):
        # --yes (no_input) : le menu choisit le DÉFAUT = 1er du chemin = storage-simple.
        mounted = self._spy_launch()
        topo, hist = self._fixtures()
        code, out, _ = _capture(
            ["next", "-f", topo, "--target", "atlas", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(mounted), 1)
        self.assertTrue(mounted[0].endswith("local-path.yaml"))  # storage-simple

    def _stub_input(self, reponses):
        """Stube le builtin `input` (le menu et _confirm l'appellent) + force le TTY.
        `reponses` : itérable des saisies successives. Restauré en cleanup."""
        import builtins

        it = iter(reponses)
        orig_input, orig_isatty = builtins.input, sys.stdin.isatty
        builtins.input = lambda _prompt="": next(it)
        sys.stdin.isatty = lambda: True
        self.addCleanup(setattr, builtins, "input", orig_input)
        self.addCleanup(setattr, sys.stdin, "isatty", orig_isatty)

    def _stub_observed(self, layers):
        """Stube la sonde réelle `_observed_layers` (kubectl) → renvoie `layers`.
        Évite d'interroger le banc et fige les couches « déjà installées »."""
        orig = cli._observed_layers
        cli._observed_layers = lambda _phases: set(layers)
        self.addCleanup(setattr, cli, "_observed_layers", orig)

    def test_interactive_choice_picks_metrics_over_storage(self):
        # TTY + saisie « 2 » : l'opérateur choisit metrics-server AVANT storage-simple.
        # Le choix au menu VAUT décision → AUCUNE confirmation [o/N] redondante après.
        mounted = self._spy_launch()
        topo, hist = self._fixtures()
        self._stub_input(["2"])  # 2e du menu = metrics-server ; pas de 2e prompt
        code, out, err = _capture(["next", "-f", topo, "--target", "atlas", "--history", hist])
        self.assertEqual(code, 0)
        self.assertEqual(len(mounted), 1)
        self.assertTrue(mounted[0].endswith("metrics-server.yaml"))  # metrics, pas storage
        self.assertIn("installables", err)  # le menu a bien été affiché

    def test_interactive_empty_cancels_mounts_nothing(self):
        # TTY + Entrée (saisie vide) au menu : « par défaut, nestor ne fait rien » →
        # _choisir_couche renvoie None → montage ANNULÉ (code 2), AUCUNE couche montée.
        # Plus de « défaut 1 » : l'opérateur doit choisir un numéro EXPLICITEMENT.
        mounted = self._spy_launch()
        topo, hist = self._fixtures()
        self._stub_input([""])  # Entrée vide au menu = annuler
        code, _, err = _capture(["next", "-f", topo, "--target", "atlas", "--history", hist])
        self.assertEqual(code, 2)
        self.assertEqual(mounted, [])  # rien monté
        self.assertIn("annulé", err)

    def test_single_installable_no_menu(self):
        # storage-simple déjà fait : seul metrics-server reste montable → PAS de menu
        # (une seule couche), montage direct sous --yes. Le RÉEL doit CONFIRMER
        # storage-simple sain (sinon, parité preview≠next : une couche à signal que le
        # cluster NE confirme PAS est RE-proposée — cf. compute_plan_state, 2e sens).
        self._stub_observed({"storage-simple"})  # le cluster confirme storage-simple sain
        mounted = self._spy_launch()
        topo = _tmp(self._ATLAS_LOCAL)
        hist = _tmp(
            f"runs:\n  - id: r1\n    date: {dt_today()}\n    profil: dataops\n"
            f"    topologie: atlas-local\n    phases: {{up: 1, bootstrap: 1, storage-simple: 1}}\n"
        )
        self.addCleanup(os.unlink, topo)
        self.addCleanup(os.unlink, hist)
        code, out, err = _capture(
            ["next", "-f", topo, "--target", "atlas", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 0)
        self.assertTrue(mounted[0].endswith("metrics-server.yaml"))
        self.assertNotIn("installables", err)  # pas de menu pour une seule couche

    def test_observed_layer_not_reproposed(self):
        # BUG du banc : metrics-server DÉJÀ installé (signal d'infra présent), mais
        # absent de l'historique → `next` le re-proposait. Désormais la sonde réelle
        # (_observed_layers) le retire : le menu ne montre que storage-simple (seule
        # couche restante → PAS de menu), monté direct.
        mounted = self._spy_launch()
        topo, hist = self._fixtures()
        self._stub_observed({"metrics-server"})  # réel : metrics déjà là
        code, out, err = _capture(
            ["next", "-f", topo, "--target", "atlas", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(mounted), 1)
        self.assertTrue(mounted[0].endswith("local-path.yaml"))  # storage-simple, PAS metrics
        self.assertNotIn("installables", err)  # une seule couche restante → pas de menu

    def test_observed_layer_primes_over_stale_history(self):
        # RÉEL prime sur la fraîcheur (ADR 0052) : même sans run frais, metrics observé
        # n'est jamais re-proposé. Historique VIDE (freshness=jamais) + metrics observé.
        mounted = self._spy_launch()
        topo = _tmp(self._ATLAS_LOCAL)
        hist = _tmp("runs: []\n")  # historique vide → freshness=jamais
        self.addCleanup(os.unlink, topo)
        self.addCleanup(os.unlink, hist)
        self._stub_observed({"metrics-server"})
        code, _, err = _capture(
            ["next", "-f", topo, "--target", "atlas", "--history", hist, "--yes"]
        )
        self.assertEqual(code, 0)
        self.assertFalse(
            any("metrics-server" in m for m in mounted), "metrics observé : jamais re-monté"
        )


class LayerHealthSignal(unittest.TestCase):
    """`_resource_healthy` / `_observed_layers` : une couche n'est SAINE que si son
    dernier maillon est READY — pas seulement présent. C'est ce qui empêche `preview`
    d'afficher « ✓ » une couche posée à moitié (ns monitoring créé, Loki absent)."""

    def _stub_kubectl(self, table):
        """Stube `_kubectl_resource` : `table[(kind,name)]` = (returncode, stdout).
        Absent de la table → ressource introuvable (returncode 1)."""
        import subprocess as sp

        def fake(kind, name, namespace, jsonpath=None):
            rc, out = table.get((kind, name), (1, ""))
            return sp.CompletedProcess(args=[], returncode=rc, stdout=out, stderr="")

        orig = cli._kubectl_resource
        cli._kubectl_resource = fake
        self.addCleanup(setattr, cli, "_kubectl_resource", orig)

    def test_workload_ready_is_healthy(self):
        # Deployment présent avec readyReplicas=1 → sain.
        self._stub_kubectl({("deployment", "argocd-server"): (0, "1")})
        self.assertTrue(cli._resource_healthy("deployment", "argocd-server", "argocd", ready=True))

    def test_workload_present_but_zero_replicas_is_not_healthy(self):
        # BUG du banc : ressource PRÉSENTE (returncode 0) mais 0 réplica prêt → PAS saine.
        # Sans le critère Ready, une couche cassée passerait pour « à-jour ».
        self._stub_kubectl({("statefulset", "loki"): (0, "0")})
        self.assertFalse(cli._resource_healthy("statefulset", "loki", "monitoring", ready=True))

    def test_workload_absent_is_not_healthy(self):
        # Loki carrément absent (cas réel : SeaweedFS manquant → Loki jamais créé).
        self._stub_kubectl({})  # rien
        self.assertFalse(cli._resource_healthy("statefulset", "loki", "monitoring", ready=True))

    def test_empty_replicas_field_is_not_healthy(self):
        # readyReplicas absent (champ vide) → 0 → pas sain (fail-closed).
        self._stub_kubectl({("statefulset", "loki"): (0, "")})
        self.assertFalse(cli._resource_healthy("statefulset", "loki", "monitoring", ready=True))

    def test_presence_only_signal_ignores_readiness(self):
        # ready=False (Application Argo : CRD sans replicas) → présence seule suffit.
        self._stub_kubectl({("application", "atlas"): (0, "")})
        self.assertTrue(cli._resource_healthy("application", "atlas", "argocd", ready=False))

    def test_observed_layers_drops_unhealthy_monitoring(self):
        # Le cas de bout en bout : metrics sain, monitoring posé à moitié (Loki 0/1).
        # _observed_layers retient metrics, PAS monitoring → preview ne ment plus.
        self._stub_kubectl(
            {
                ("deployment", "metrics-server"): (0, "1"),
                ("statefulset", "loki"): (0, "0"),  # Loki présent mais pas prêt
            }
        )
        got = cli._observed_layers(["metrics-server", "monitoring"])
        self.assertEqual(got, {"metrics-server"})

    def test_gitops_seed_signal_targets_atlas_workflows(self):
        # Régression : gitops-seed pose l'Application `atlas-workflows`, PAS `atlas`. Avec le
        # mauvais nom, la couche n'était jamais vue faite → next la re-proposait en boucle.
        kind, name, ns, ready = cli._LAYER_SIGNAL["gitops-seed"]
        self.assertEqual((kind, name, ns), ("application", "atlas-workflows", "argocd"))
        self._stub_kubectl({("application", "atlas-workflows"): (0, "")})
        self.assertEqual(cli._observed_layers(["gitops-seed"]), {"gitops-seed"})


class NextHealthGate(unittest.TestCase):
    """#355 : gate de santé ACTIVE après montage — `next` attend le dernier maillon Ready."""

    def setUp(self):
        # setUpModule neutralise `_wait_layer_healthy` (→ True) pour ne pas pendre les
        # autres tests ; ICI on teste la VRAIE gate → on la restaure le temps de la classe.
        orig = cli._wait_layer_healthy
        cli._wait_layer_healthy = _REAL_WAIT_HEALTHY
        self.addCleanup(setattr, cli, "_wait_layer_healthy", orig)

    def test_wait_returns_true_when_healthy_first_try(self):
        orig = cli._resource_healthy
        cli._resource_healthy = lambda *sig: True
        self.addCleanup(setattr, cli, "_resource_healthy", orig)
        slept = []
        ok = cli._wait_layer_healthy("monitoring", retries=5, delay=1, sleep=slept.append)
        self.assertTrue(ok)
        self.assertEqual(slept, [])  # sain au 1er essai → aucune attente

    def test_wait_retries_then_succeeds(self):
        orig = cli._resource_healthy
        calls = {"n": 0}

        def healthy(*sig):
            calls["n"] += 1
            return calls["n"] >= 3  # sain au 3e essai

        cli._resource_healthy = healthy
        self.addCleanup(setattr, cli, "_resource_healthy", orig)
        slept = []
        ok = cli._wait_layer_healthy("monitoring", retries=5, delay=1, sleep=slept.append)
        self.assertTrue(ok)
        self.assertEqual(len(slept), 2)  # 2 attentes avant le 3e essai

    def test_wait_times_out_when_never_healthy(self):
        orig = cli._resource_healthy
        cli._resource_healthy = lambda *sig: False
        self.addCleanup(setattr, cli, "_resource_healthy", orig)
        ok = cli._wait_layer_healthy("monitoring", retries=3, delay=0, sleep=lambda _d: None)
        self.assertFalse(ok)

    def test_phase_without_signal_skips_gate(self):
        # une phase sans _LAYER_SIGNAL (ex. amont up/bootstrap, ou smoke-s3) → True direct.
        ok = cli._wait_layer_healthy("smoke-s3", retries=1, delay=0, sleep=lambda _d: None)
        self.assertTrue(ok)

    def test_monter_phase_returns_1_when_layer_not_healthy(self):
        # Gate intégrée : launch_phase rc=0 MAIS le maillon ne devient pas sain → rc=1.
        from nestor.runner import RunResult

        topo = cli.load_topology(_EXAMPLE)
        orig_lp = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: RunResult(rc=0, status="successful")
        self.addCleanup(setattr, cli._runner, "launch_phase", orig_lp)
        # Restaure la vraie gate (setUpModule l'a neutralisée) mais on la fait échouer vite.
        orig_wait = cli._wait_layer_healthy
        cli._wait_layer_healthy = lambda phase, **kw: False
        self.addCleanup(setattr, cli, "_wait_layer_healthy", orig_wait)
        inv = os.path.join(_ROOT, "bootstrap", "hosts.yaml")
        created = not os.path.exists(inv)
        if created:
            with open(inv, "w", encoding="utf-8") as f:
                f.write("# test\n")
            self.addCleanup(os.unlink, inv)
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli._monter_phase(topo, "monitoring", {}, "banc")
        self.assertEqual(rc, 1)
        self.assertIn("PAS saine", err.getvalue())

    def test_gitops_seed_routes_to_python_seed_not_usage_error(self):
        # `gitops-seed` (playbook None) est une phase DÉLÉGUÉE : `_monter_phase` la route vers
        # le câblage Python `_launch_seed` (seed.run_seed), PARITÉ `_run_path_engine` (un seul
        # moteur depuis le retrait du filet bash). Elle ne lève PLUS « pas un play unitaire »
        # et ne passe PLUS par un arm run-phases.sh. On stube `_launch_seed` (zéro Gitea réel).
        topo = cli.load_topology(_EXAMPLE)
        called = {}

        def fake_seed(phase, t, derived):
            called["phase"] = phase
            return cli._SeedLaunchResult(ok=True, message="stub")

        orig_seed = cli._launch_seed
        cli._launch_seed = fake_seed
        self.addCleanup(setattr, cli, "_launch_seed", orig_seed)
        # Aucun subprocess (ni run-phases.sh, ni ansible-runner) ne doit être lancé.
        orig_run = cli.subprocess.run

        def _no_subprocess(argv, **kw):
            raise AssertionError(f"gitops-seed ne doit PAS sheller un subprocess : {argv!r}")

        cli.subprocess.run = _no_subprocess
        self.addCleanup(setattr, cli.subprocess, "run", orig_run)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli._monter_phase(topo, "gitops-seed", {}, "banc")
        self.assertEqual(rc, 0)
        self.assertEqual(called["phase"], "gitops-seed")  # routé vers le seed Python

    def test_phase_without_playbook_and_without_arm_is_usage_error(self):
        # garde-fou inverse : une phase déléguée sans play unitaire, sans câblage seed NI arm
        # run-phases.sh (le filet bash a été retiré → `hardening` n'a plus d'arm) → usage net.
        topo = cli.load_topology(_EXAMPLE)
        with self.assertRaises(cli._UsageError):
            cli._monter_phase(topo, "hardening", {}, "banc")


class Metrics(unittest.TestCase):
    _HIST = """\
runs:
  - id: r1
    date: 2026-06-01T00:00:00Z
    profil: ceph
    topologie: multi-node-3
    total_s: 759
    phases: {up: 165, bootstrap: 399}
    metriques: {cpu_core_s: 272, ram_peak_mib: 7606, ram_mean_mib: 7489}
"""

    def test_exposes_consigned_metrics(self):
        hist = _tmp(self._HIST)
        self.addCleanup(os.unlink, hist)
        # --all : métriques de TOUT l'historique fourni (sans le filtre stack-active,
        # qui viserait la stack réelle ≠ la topologie de ce fixture).
        code, out, _ = _capture(["artifact", "metrics", "--history", hist, "--all"])
        self.assertEqual(code, 0)
        self.assertIn("cpu_core_s=272", out)
        self.assertIn("12m39s", out)  # 759 s

    def test_defaults_to_active_stack(self):
        # PAR DÉFAUT (-f pointe une topo), metrics ne montre QUE les runs de CETTE stack
        # (filtre par `stack_id` = nom de fichier, ADR 0102 volet B) — pas tout l'historique.
        topo = _tmp(
            "catalog: {topology: multi-node-3, profile: base, terrain: local}\n"
            "nodes:\n  - {name: cp1, roles: [control]}\n"
            "storage: {backend: ceph}\n"
        )
        self.addCleanup(os.unlink, topo)
        stack = cli._stack_id(topo)  # nom de fichier du temp (identité, pas catalog.topology)
        # L'historique de CETTE stack est keyé par le `stack_id` ; un run `other` est exclu.
        hist = _tmp(
            "runs:\n"
            f"  - {{id: a, date: 2026-06-01T00:00:00Z, profil: ceph, topologie: {stack},"
            " total_s: 100, phases: {up: 100}}\n"
            "  - {id: b, date: 2026-06-02T00:00:00Z, profil: local-path, topologie: other,"
            " total_s: 200, phases: {up: 200}}\n"
        )
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["artifact", "metrics", "--history", hist, "-f", topo])
        self.assertEqual(code, 0)
        self.assertIn(stack, out)  # la stack active (nom de fichier)
        self.assertNotIn("topologie: other", out)  # l'autre stack est exclue

    def test_no_run_for_active_stack(self):
        # Stack active sans run consigné → message explicite, code 0 (informatif).
        hist = _tmp(
            "runs:\n  - {id: a, date: 2026-06-01T00:00:00Z, profil: ceph,"
            " topologie: other, total_s: 100, phases: {up: 100}}\n"
        )
        self.addCleanup(os.unlink, hist)
        topo = _tmp(
            "catalog: {topology: absente, profile: base, terrain: local}\n"
            "nodes:\n  - {name: cp1, roles: [control]}\n"
            "storage: {backend: ceph}\n"
        )
        self.addCleanup(os.unlink, topo)
        code, out, _ = _capture(["artifact", "metrics", "--history", hist, "-f", topo])
        self.assertEqual(code, 0)
        self.assertIn("aucun run", out)

    def test_empty_history(self):
        hist = _tmp("runs: []\n")
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["artifact", "metrics", "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("aucun run", out)


class Smoke(unittest.TestCase):
    def test_reversible_is_zero(self):
        from nestor.smoke import SmokeResult, SmokeStep

        res = SmokeResult(
            namespace="topo-smoke",
            steps=[SmokeStep("créer", True), SmokeStep("vérifier détruit", True)],
        )
        orig = cli._smoke.run_smoke
        cli._smoke.run_smoke = lambda ns: res
        self.addCleanup(setattr, cli._smoke, "run_smoke", orig)
        code, out, _ = _capture(["test", "smoke"])
        self.assertEqual(code, 0)
        self.assertIn("réversible", out)

    def test_not_reversible_is_one(self):
        from nestor.smoke import SmokeResult, SmokeStep

        res = SmokeResult(namespace="x", steps=[SmokeStep("créer", False, "échec")])
        orig = cli._smoke.run_smoke
        cli._smoke.run_smoke = lambda ns: res
        self.addCleanup(setattr, cli._smoke, "run_smoke", orig)
        code, _, _ = _capture(["test", "smoke"])
        self.assertEqual(code, 1)

    def test_cluster_unavailable_is_usage_error(self):
        def boom(ns):
            raise cli._smoke.SmokeUnavailable("cluster injoignable")

        orig = cli._smoke.run_smoke
        cli._smoke.run_smoke = boom
        self.addCleanup(setattr, cli._smoke, "run_smoke", orig)
        code, _, err = _capture(["test", "smoke"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class Roundtrip(unittest.TestCase):
    def _stub(self, res):
        orig = cli._roundtrip.run_roundtrip
        cli._roundtrip.run_roundtrip = lambda phase, **kw: res
        self.addCleanup(setattr, cli._roundtrip, "run_roundtrip", orig)

    def test_reversible_is_zero(self):
        from nestor.roundtrip import RoundtripResult, RoundtripStep

        self._stub(
            RoundtripResult(
                phase="monitoring",
                layers=["monitoring"],
                steps=[RoundtripStep("détruire", True), RoundtripStep("vérifier sain", True)],
            )
        )
        code, out, _ = _capture(["test", "roundtrip", "--phase", "monitoring", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("réversible", out)

    def test_not_reversible_is_one(self):
        from nestor.roundtrip import RoundtripResult, RoundtripStep

        self._stub(
            RoundtripResult(
                phase="gitops",
                layers=["gitops", "gitops-seed"],
                steps=[RoundtripStep("détruire gitops", False, "rc=3")],
            )
        )
        code, _, _ = _capture(["test", "roundtrip", "--phase", "gitops", "--yes"])
        self.assertEqual(code, 1)

    def test_storage_without_full_is_usage_error(self):
        # ceph (clôture de stockage) sans --full → RoundtripError → code 2.
        def boom(phase, **kw):
            raise cli._roundtrip.RoundtripError("exiger l'opt-in `--full`")

        orig = cli._roundtrip.run_roundtrip
        cli._roundtrip.run_roundtrip = boom
        self.addCleanup(setattr, cli._roundtrip, "run_roundtrip", orig)
        code, _, err = _capture(["test", "roundtrip", "--phase", "ceph", "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_full_and_yes_flags_passed(self):
        from nestor.roundtrip import RoundtripResult, RoundtripStep

        seen = {}

        def capture(phase, *, allow_full=False, assume_yes=False, destroy_layer=None):
            seen["full"] = allow_full
            seen["yes"] = assume_yes
            seen["has_destroy"] = destroy_layer is not None  # découverte injectée (ADR 0101)
            return RoundtripResult(phase=phase, layers=[phase], steps=[RoundtripStep("x", True)])

        orig = cli._roundtrip.run_roundtrip
        cli._roundtrip.run_roundtrip = capture
        self.addCleanup(setattr, cli._roundtrip, "run_roundtrip", orig)
        _capture(["test", "roundtrip", "--phase", "ceph", "--full", "--yes"])
        self.assertTrue(seen["full"])
        self.assertTrue(seen["yes"])

    def test_unknown_phase_is_argparse_usage(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["test", "roundtrip", "--phase", "frobnicate"])
        self.assertEqual(ctx.exception.code, 2)  # choices argparse

    def test_phase_required(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["test", "roundtrip"])
        self.assertEqual(ctx.exception.code, 2)


class Stack(unittest.TestCase):
    """`new` + `stack ls|select` (calque Pulumi) : crée/active une stack, liste le catalogue.

    Écrit dans le VRAI catalogue topologies/ (la façade y résout les chemins) sous des
    noms jetables nettoyés en teardown ; le symlink topology.yaml réel (stack courante
    de l'opérateur) est sauvegardé en setUp et restauré en tearDown."""

    def setUp(self):
        self._link = os.path.join(_ROOT, "topology.yaml")
        self._prev = os.readlink(self._link) if os.path.islink(self._link) else None

    def tearDown(self):
        if os.path.islink(self._link) or os.path.exists(self._link):
            os.unlink(self._link)
        if self._prev is not None:
            os.symlink(self._prev, self._link)

    def _catalog(self, name):
        return os.path.join(_ROOT, "topologies", f"{name}.yaml")

    def test_create_mono_no_input_writes_valid_gitignored(self):
        name = "zz-test-ctx-mono"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        code, out, _ = _capture(["stack", "new", name, "--no-input"])
        self.assertEqual(code, 0)
        self.assertIn("créée", out)
        self.assertTrue(os.path.exists(target))
        # Le fichier produit est VALIDE (re-validable) et mono-CP par défaut.
        topo = load_topology(target)
        self.assertEqual(len(topo.control_nodes), 1)
        self.assertFalse(topo.is_ha_control_plane)
        # --no-input sans --activate : ne touche PAS le symlink (déterminisme CI).
        self.assertEqual(
            os.readlink(self._link) if os.path.islink(self._link) else None, self._prev
        )

    def test_create_ha_via_answers_inserts_lb(self):
        # 3 CP fournis via stdin → l'assistant demande le mode LB, puis « activer ? » (non).
        # Ordre des prompts (scaffold, ADR 0108) : profil, backend, terrain, control_planes,
        # workers, lb_mode (car HA), puis « activer ? ».
        name = "zz-test-ctx-ha"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        answers = "base\nlocal-path\nlocal\n3\n0\nkube-vip-arp\nn\n"
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
            _stdin(answers),
        ):
            code = cli.main(["stack", "new", name])
        self.assertEqual(code, 0)
        topo = load_topology(target)
        self.assertTrue(topo.is_ha_control_plane)
        self.assertEqual(len(topo.control_nodes), 3)

    def test_create_example_name_rejected_usage(self):
        code, _, err = _capture(["stack", "new", "bad.example", "--no-input"])
        self.assertEqual(code, 2)
        self.assertIn("ADR 0023", err)

    def test_create_existing_without_force_is_usage(self):
        name = "zz-test-ctx-dup"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        self.assertEqual(_capture(["stack", "new", name, "--no-input"])[0], 0)
        code, _, err = _capture(["stack", "new", name, "--no-input"])  # 2e sans --force
        self.assertEqual(code, 2)
        self.assertIn("existe déjà", err)

    def test_create_activate_flag_repoints_symlink(self):
        name = "zz-test-ctx-activate"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        code, out, _ = _capture(["stack", "new", name, "--no-input", "--activate"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.islink(self._link))
        self.assertEqual(os.readlink(self._link), f"topologies/{name}.yaml")
        self.assertIn("activée", out)

    def test_activate_existing_repoints_and_validates(self):
        # `stack select` sur une entrée existante : repointe + dérive le chemin.
        name = "zz-test-ctx-act-existing"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        _capture(["stack", "new", name, "--no-input"])  # sans activer
        code, out, err = _capture(["stack", "select", name])
        self.assertEqual(code, 0)
        self.assertEqual(os.readlink(self._link), f"topologies/{name}.yaml")
        # Messages humains sur stderr (eval-safe) ; ligne `export` eval-able sur stdout.
        self.assertIn("dérivé", err)
        self.assertIn("export KUBECONFIG=", out)

    def test_select_exports_devnull_when_no_bench(self):
        # Pas de banc monté → `export KUBECONFIG=/dev/null` (jamais la prod, ADR 0053).
        name = "zz-test-ctx-devnull"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        _capture(["stack", "new", name, "--no-input"])
        orig_exists = cli.os.path.exists
        _bp = cli._bench_kubeconfig_path(cli._active_stack_name(None))
        cli.os.path.exists = lambda p: False if p == _bp else orig_exists(p)
        self.addCleanup(setattr, cli.os.path, "exists", orig_exists)
        code, out, err = _capture(["stack", "select", name])
        self.assertEqual(code, 0)
        self.assertIn(f"export KUBECONFIG={os.devnull}", out)
        self.assertIn("cluster non installé", err)

    def test_select_exports_bench_when_present(self):
        # Banc monté ET JOIGNABLE → l'export pointe le banc, pas /dev/null. On crée un
        # fichier kubeconfig au banc et on stube `_kubeconfig_reaches_api` à True (select
        # sonde l'API, pas juste la présence du fichier).
        name = "zz-test-ctx-bench"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        _capture(["stack", "new", name, "--activate", "--no-input"])
        # Kubeconfig du banc NOMMÉ PAR LA STACK sélectionnée (ADR 0102 volet B) :
        # `stack new <name>` crée `topologies/<name>.yaml` → `stack_id` == `name`.
        bench = cli._bench_kubeconfig_path(name)
        os.makedirs(os.path.dirname(bench), exist_ok=True)
        if not os.path.exists(bench):
            with open(bench, "w", encoding="utf-8") as f:
                f.write("apiVersion: v1\nkind: Config\n")
            self.addCleanup(lambda: os.path.exists(bench) and os.unlink(bench))
        orig = cli._kubeconfig_reaches_api
        cli._kubeconfig_reaches_api = lambda _kc: True  # banc joignable
        self.addCleanup(setattr, cli, "_kubeconfig_reaches_api", orig)
        code, out, _ = _capture(["stack", "select", name])
        self.assertEqual(code, 0)
        self.assertIn("export KUBECONFIG=", out)
        self.assertNotIn(os.devnull, out)  # le banc, pas /dev/null

    def test_select_bare_name_falls_back_to_example(self):
        # `stack select <nom>` (nom NU) active `topologies/<nom>.example.yaml` quand aucune
        # surcharge locale `<nom>.yaml` n'existe — cas nominal du banc générique versionné.
        name = "zz-test-fallback"
        example = os.path.join(_ROOT, "topologies", f"{name}.example.yaml")
        bare = self._catalog(name)  # <nom>.yaml — ne doit PAS exister
        with open(example, "w", encoding="utf-8") as f:
            f.write(
                "catalog: {terrain: local, profile: base}\n"
                "nodes:\n  - {name: node1, roles: [control]}\n"
            )
        self.addCleanup(lambda: os.path.exists(example) and os.unlink(example))
        self.assertFalse(os.path.exists(bare))
        code, _, err = _capture(["stack", "select", name])
        self.assertEqual(code, 0)  # trouvé via le fallback, plus « introuvable »
        self.assertIn(f"topologies/{name}.example.yaml", err)  # a bien activé le .example

    def test_select_example_name_uses_normalized_stack_id(self):
        # `stack select <nom>.example` doit poser le contexte kubectl + viser le kubeconfig au
        # stack_id NORMALISÉ (`<nom>`), pas au nom tapé (`<nom>.example`) — sinon la garde
        # d'identité (current-context == stack_id) refuse, et le kubeconfig `.example.config`
        # visé n'existe pas (ADR 0102/0108).
        name = "zz-test-normalize"
        example = os.path.join(_ROOT, "topologies", f"{name}.example.yaml")
        with open(example, "w", encoding="utf-8") as f:
            f.write(
                "catalog: {terrain: local, profile: base}\n"
                "nodes:\n  - {name: node1, roles: [control]}\n"
            )
        self.addCleanup(lambda: os.path.exists(example) and os.unlink(example))
        posed = {}
        orig = cli._pose_named_context
        cli._pose_named_context = lambda topo, stack: posed.update(stack=stack)
        self.addCleanup(setattr, cli, "_pose_named_context", orig)
        code, _, _ = _capture(["stack", "select", f"{name}.example"])
        self.assertEqual(code, 0)
        self.assertEqual(posed.get("stack"), name)  # stack_id normalisé, pas "<nom>.example"

    def test_prod_select_no_input_warns_but_does_not_write_kubeconfig(self):
        # ADR 0090 : `stack select` sur une stack PROD sans `kubeconfig:` SIGNALE de le
        # déclarer mais N'ÉCRIT PAS le fichier sous --no-input (action opérateur, CI sûre).
        name = "zz-test-prod-kc"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        with open(target, "w", encoding="utf-8") as f:
            f.write(
                "catalog: {topology: multi-node-4, profile: dataops, terrain: baremetal}\n"
                "nodes:\n  - {name: dirqual1, roles: [control, worker]}\n"
                "storage: {backend: ceph}\n"
            )
        # Pas de banc ET pas de KUBECONFIG hérité (sinon `_default_kubeconfig_to_bench`
        # ou un env pollué sauterait la branche « topo sans kubeconfig »). On force les
        # deux absents pour un test déterministe (indépendant de l'ordre des tests).
        orig_exists = cli.os.path.exists
        _bp = cli._bench_kubeconfig_path(cli._active_stack_name(None))
        cli.os.path.exists = lambda p: False if p == _bp else orig_exists(p)
        self.addCleanup(setattr, cli.os.path, "exists", orig_exists)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KUBECONFIG", None)
            code, _, err = _capture(["stack", "select", name, "--no-input"])
        self.assertEqual(code, 0)
        self.assertIn("kubeconfig", err)  # signale de le déclarer
        with open(target, encoding="utf-8") as f:
            self.assertNotIn("kubeconfig:", f.read())  # rien écrit en --no-input

    def test_prod_select_writes_kubeconfig_field_and_ignores_bench_env(self):
        # ADR 0090 : `stack select` PROD interactif ÉCRIT le champ kubeconfig dans la
        # topo (« nestor corrige la topologie ») et NE BLOQUE PAS (ni sonde ni prompt).
        # Un KUBECONFIG pointant le BANC (résidu d'un select banc) est IGNORÉ — sinon on
        # viserait le banc et on n'écrirait pas le champ.
        name = "zz-test-prod-write-kc"
        target = self._catalog(name)
        self.addCleanup(lambda: os.path.exists(target) and os.unlink(target))
        with open(target, "w", encoding="utf-8") as f:
            f.write(
                "catalog: {topology: multi-node-4, profile: dataops, terrain: baremetal}\n"
                "nodes:\n  - {name: dirqual1, roles: [control, worker]}\n"
                "storage: {backend: ceph}\n"
            )
        # Le résidu à ignorer = le banc de la stack ACTIVE. `stack select` REPOINTE le symlink
        # AVANT `_select_prod_kubeconfig`, donc la stack active y est déjà `name` : le résidu
        # visé est SON banc `.kubeconfigs/<name>.config` (ADR 0102 volet B). On le pose en env
        # (comme un `eval` d'un select banc antérieur) — il doit être IGNORÉ au profit de la
        # cible prod déclarée.
        residu_banc = cli._bench_kubeconfig_path(name)
        with mock.patch.dict(os.environ, {"KUBECONFIG": residu_banc}, clear=False):
            code, out, _ = _capture(["stack", "select", name])  # interactif (pas --no-input)
        self.assertEqual(code, 0)  # ne bloque pas (ni sonde réseau ni prompt)
        with open(target, encoding="utf-8") as f:
            written = f.read()
        # ADR 0102 : le défaut écrit est in-repo `.kubeconfigs/<stack>.config` (plus ~/.kube/).
        # Le champ kubeconfig prod déclaré vaut ce même chemin — donc l'écriture EST la preuve
        # que le résidu banc a été écarté (sinon `_select_prod_kubeconfig` aurait retourné tôt
        # sur l'env sans écrire le champ). Pas d'assert « export ≠ résidu » : les deux chemins
        # coïncident par construction (`.kubeconfigs/<name>.config`), la preuve est l'écriture.
        self.assertIn(
            f"kubeconfig: {os.path.join(cli._ROOT, '.kubeconfigs', name)}.config", written
        )

    def test_activate_absent_is_business_error_with_catalog(self):
        code, _, err = _capture(["stack", "select", "zz-nexistepas"])
        self.assertEqual(code, 1)
        self.assertIn("introuvable", err)
        self.assertIn("disponibles", err)  # aide : liste le catalogue

    def test_list_marks_active_and_derives(self):
        # Active une entrée connue, puis `stack ls` doit la marquer ★ + son chemin.
        # `--no-input` : dirqual.example est prod (ADR 0090) → ne pas prompter/écrire le
        # kubeconfig de la topo en test (on ne teste ici que l'activation).
        _capture(["stack", "select", "dirqual.example", "--no-input"])
        code, out, _ = _capture(["stack", "ls"])
        self.assertEqual(code, 0)
        self.assertIn("dirqual.example", out)
        self.assertIn("★", out)
        # ADR 0083 : `default_target` rend `layers` pour toute topo non-HA (plus de preset
        # dérivé comme `atlas-ceph`) — l'ordre vient du graphe atomique, pas d'un nom figé.
        # La ligne active affiche donc `dirqual.example → layers`.
        self.assertRegex(out, r"★ dirqual\.example\s+→ layers")


class InstallCommand(unittest.TestCase):
    """`install` (ex-`up`, ADR 0108 §4) : dérive le chemin → affiche le plan → confirme →
    MONTE via le moteur Python `_run_path_engine` (SEUL moteur). INVARIANT CARDINAL :
    `install` EXCLUT TOUJOURS le substrat (phase amont `up`), même en terrain local."""

    def _stub_engine(self, rc=0):
        # Espionne `_run_path_engine` (le SEUL moteur) : capture (target, seq, stack_name).
        # Le montage (le moteur) est stubé ; on LAISSE PASSER les appels subprocess au GRAPHE
        # (rollback-lib.sh) pour que `expected_phase_sequence` dérive la séquence. Les sondes
        # réelles _real_vms/_ready_nodes sont neutralisées à ∅ : sur une topo LOCALE elles
        # shelleraient limactl/kubectl (déniés bruyamment par le blindage) — ∅ = plan annoté
        # « tout à installer », neutre en test.
        _install_graph_passthrough(self)
        orig_vms = cli._real_vms
        cli._real_vms = lambda *_a, **_k: []
        self.addCleanup(setattr, cli, "_real_vms", orig_vms)
        orig_ready = cli._ready_nodes
        cli._ready_nodes = lambda *_a, **_k: []
        self.addCleanup(setattr, cli, "_ready_nodes", orig_ready)
        calls = []

        def _spy(topo, target, seq, stack_name, a_appliquer=None):
            calls.append({"target": target, "seq": list(seq), "stack_name": stack_name})
            return rc

        orig = cli._run_path_engine
        cli._run_path_engine = _spy
        self.addCleanup(setattr, cli, "_run_path_engine", orig)
        return calls

    def test_yes_derives_path_and_mounts_via_engine(self):
        # `nestor install` dérive le chemin, affiche le plan, puis MONTE via `_run_path_engine`
        # (un seul moteur). La séquence vient du graphe atomique (ADR 0083).
        calls = self._stub_engine()
        code, out, _ = _capture(["install", "-f", _EXAMPLE, "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("Couches à monter", out)  # le plan affiché
        self.assertEqual(len(calls), 1)  # le moteur Python appelé une fois
        # ADR 0083 : `default_target` rend `layers` (plus de preset dérivé), l'ordre venant
        # du graphe atomique. socle.example (ceph) dérive bootstrap,ceph,sc,datalake,…
        self.assertEqual(calls[0]["target"], "layers")
        seq = calls[0]["seq"]
        # `install` ne monte JAMAIS le substrat → PAS de phase `up` : le socle commence à
        # `bootstrap` (ici _EXAMPLE est baremetal, mais l'exclusion vaut aussi en local).
        self.assertNotIn("up", seq)
        self.assertEqual(seq[0], "bootstrap")
        self.assertIn("ceph", seq)  # backend ceph → socle ceph dans la séquence
        self.assertIn("datalake", seq)

    def test_install_excludes_substrate_even_in_local_terrain(self):
        # INVARIANT CARDINAL (ADR 0108 §4) : même sur une topo LOCALE (où
        # `expected_phase_sequence` PRODUIT la phase `up`), `install` la RETIRE — il ne
        # touche jamais au substrat (c'est le ressort exclusif de `provision`).
        calls = self._stub_engine()
        lima = _example_as_lima(self)  # copie de _EXAMPLE forcée en terrain local
        code, _, _ = _capture(["install", "-f", lima, "--yes"])
        self.assertEqual(code, 0)
        seq = calls[0]["seq"]
        self.assertNotIn("up", seq)  # LE test de l'invariant : jamais le substrat en install
        self.assertEqual(seq[0], "bootstrap")

    def test_explicit_target_overrides_derivation(self):
        calls = self._stub_engine()
        code, _, _ = _capture(["install", "-f", _EXAMPLE, "--target", "atlas-ceph", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(calls[0]["target"], "atlas-ceph")

    def test_passes_stack_name_to_engine(self):
        # Le NOM de la stack active (catalog.topology) est transmis au moteur (clé de
        # fraîcheur PAR STACK). _EXAMPLE (socle.example) déclare une topologie nommée.
        calls = self._stub_engine()
        code, _, _ = _capture(["install", "-f", _EXAMPLE, "--yes"])
        self.assertEqual(code, 0)
        self.assertNotEqual(calls[0]["stack_name"], "—")  # une vraie stack, pas le défaut

    def test_refuses_without_yes_off_tty(self):
        calls = self._stub_engine()
        code, _, err = _capture(["install", "-f", _EXAMPLE])  # hors TTY, pas de --yes
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])  # le moteur JAMAIS appelé (confirmation refusée)
        self.assertIn("refusé", err)

    def test_propagates_mount_failure(self):
        self._stub_engine(rc=1)  # le moteur Python échoue
        code, _, _ = _capture(["install", "-f", _EXAMPLE, "--yes"])
        self.assertEqual(code, 1)

    def test_keeps_identity_guard(self):
        # `install` mute une instance existante (kubectl/Ansible) → il GARDE la garde
        # d'identité (`_assert_target_identity`, ADR 0108). On la fait LEVER : un refus doit
        # arrêter net (code 2), AVANT tout montage (le moteur jamais atteint).
        self._install_engine_boom()

        def _refuse(action, *_a, **_k):
            raise cli._UsageError(f"REFUS : `{action}` cible non prouvée (test)")

        orig = cli._assert_target_identity
        cli._assert_target_identity = _refuse
        self.addCleanup(setattr, cli, "_assert_target_identity", orig)
        code, _, err = _capture(["install", "-f", _EXAMPLE, "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("REFUS", err)

    def _install_engine_boom(self):
        # Sentinelle : le moteur ne DOIT PAS être atteint quand la garde refuse.
        def _boom(*_a, **_k):
            raise AssertionError("moteur atteint malgré le refus de la garde d'identité")

        orig = cli._run_path_engine
        cli._run_path_engine = _boom
        self.addCleanup(setattr, cli, "_run_path_engine", orig)

    def test_incoherent_target_is_usage_error(self):
        # ADR 0083 : `atlas` est backend-agnostique (n'est plus incohérent sur ceph). Le
        # vrai cas incohérent reste un preset CEPH-ONLY (`storage-real`) sur une topo
        # local-path → PlanError → usage (2), avant tout montage.
        topo_yaml = (
            "catalog: {topology: lp, profile: base, terrain: local}\n"
            "nodes:\n  - {name: cp1, roles: [control, worker]}\n"
            "storage: {backend: local-path}\n"
        )
        path = _tmp(topo_yaml)
        self.addCleanup(os.unlink, path)
        calls = self._stub_engine()
        code, _, err = _capture(["install", "-f", path, "--target", "storage-real", "--yes"])
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertIn("usage", err)


class ProvisionCommand(unittest.TestCase):
    """`provision` (ex-`up`, ADR 0108 §4) : crée le SUBSTRAT (VMs). Gate sur le terrain
    (`local` provisionne, `baremetal` no-op, `cloud` non implémenté), monte la SEULE phase
    amont `up`, et n'appelle JAMAIS la garde d'identité kubectl (il fait naître l'instance)."""

    def _stub_engine(self, rc=0):
        _install_graph_passthrough(self)
        calls = []

        def _spy(topo, target, seq, stack_name, a_appliquer=None):
            calls.append(
                {
                    "target": target,
                    "seq": list(seq),
                    "stack_name": stack_name,
                    "a_appliquer": a_appliquer,
                }
            )
            return rc

        orig = cli._run_path_engine
        cli._run_path_engine = _spy
        self.addCleanup(setattr, cli, "_run_path_engine", orig)
        # Sonde des VMs réelles à ∅ → toutes les VMs déclarées sont « à créer » (substrat neuf).
        orig_vms = cli._real_vms
        cli._real_vms = lambda *_a, **_k: []
        self.addCleanup(setattr, cli, "_real_vms", orig_vms)
        return calls

    _LIMA = (
        "catalog: {topology: solo, terrain: local}\n"
        "nodes:\n  - {name: cp1, roles: [control, worker]}\n"
        "storage: {backend: local-path}\n"
    )
    _BAREMETAL = (
        "catalog: {topology: bm, terrain: baremetal}\n"
        "nodes:\n  - {name: n1, roles: [control, worker]}\n"
        "storage: {backend: local-path}\n"
    )
    _CLOUD = (
        "catalog: {topology: cl, terrain: cloud}\n"
        "nodes:\n  - {name: n1, roles: [control, worker]}\n"
        "storage: {backend: local-path}\n"
    )

    def _write(self, body):
        path = _tmp(body)
        self.addCleanup(os.unlink, path)
        return path

    def test_local_mounts_substrate_only(self):
        # Terrain local : `provision` monte la SEULE phase amont `up` (le substrat) via le
        # moteur — jamais l'OS/k8s/plateforme. a_appliquer = {"up"} (substrat seul).
        calls = self._stub_engine()
        code, out, _ = _capture(["provision", "-f", self._write(self._LIMA), "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("substrat", out)  # message orienté substrat, pas « couches »
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["seq"], ["up"])  # SUBSTRAT SEUL
        self.assertEqual(calls[0]["a_appliquer"], {"up"})

    def test_baremetal_is_noop(self):
        # Terrain baremetal : les machines préexistent → NO-OP explicite (code 0), le moteur
        # n'est JAMAIS appelé (rien à provisionner).
        calls = self._stub_engine()
        code, out, _ = _capture(["provision", "-f", self._write(self._BAREMETAL), "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])  # aucun montage
        self.assertIn("préexistent", out)

    def test_cloud_is_usage_error(self):
        # Terrain cloud : provisionnement non implémenté (ADR 0032) → usage (code 2), aucun
        # montage. Message qui pointe l'ADR 0032.
        calls = self._stub_engine()
        code, _, err = _capture(["provision", "-f", self._write(self._CLOUD), "--yes"])
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertIn("non implémenté", err)
        self.assertIn("0032", err)

    def test_refuses_without_yes_off_tty(self):
        # Geste destructif/rare (crée le substrat) : refus hors TTY sans --yes, comme destroy.
        calls = self._stub_engine()
        code, _, err = _capture(["provision", "-f", self._write(self._LIMA)])  # pas de --yes
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])  # le moteur JAMAIS appelé (confirmation refusée)
        self.assertIn("refusé", err)

    def test_all_vms_present_is_noop(self):
        # Terrain local mais TOUTES les VMs déclarées existent déjà → rien à provisionner
        # (code 0), le moteur n'est PAS appelé.
        calls = self._stub_engine()  # stubbe le moteur ET pose _real_vms → ∅ par défaut
        # On surcharge _real_vms pour que la VM déclarée (cp1) soit déjà présente.
        cli._real_vms = lambda *_a, **_k: ["cp1"]
        code, out, _ = _capture(["provision", "-f", self._write(self._LIMA), "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])  # aucun montage (rien à créer)
        self.assertIn("existent déjà", out)

    def test_does_not_call_identity_guard(self):
        # `provision` fait NAÎTRE l'instance → PAS de contexte kubectl à comparer : il
        # n'appelle JAMAIS `_assert_target_identity`. On la rend explosive.
        self._stub_engine()

        def _boom(action, *_a, **_k):
            raise AssertionError(f"provision NE DOIT PAS appeler la garde d'identité ({action})")

        orig = cli._assert_target_identity
        cli._assert_target_identity = _boom
        self.addCleanup(setattr, cli, "_assert_target_identity", orig)
        code, _, _ = _capture(["provision", "-f", self._write(self._LIMA), "--yes"])
        self.assertEqual(code, 0)  # atteint le moteur SANS déclencher la garde


class Destroy(unittest.TestCase):
    """`destroy` : détruit les VMs de la stack active, confirmation, délègue à down."""

    def _stub_vms(self, vms):
        orig = cli._real_vms
        cli._real_vms = lambda *_a: vms
        self.addCleanup(setattr, cli, "_real_vms", orig)

    def _stub_down(self, rc=0):
        # Capture l'appel à run-phases.sh down (cmd ET env — PAS de vraie destruction).
        calls = []

        def _spy(cmd, *a, **k):
            calls.append({"cmd": cmd, "env": k.get("env")})
            return subprocess.CompletedProcess(args=cmd, returncode=rc)

        orig = cli.subprocess.run
        cli.subprocess.run = _spy
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        return calls

    def test_destroys_stack_vms_with_yes(self):
        # destroy ne vise que le terrain local (VMs Lima) → topo forcée local (_example_as_lima).
        # dirqual1 est déclaré par l'exemple et présent → destroy le cible, --yes saute le prompt.
        topo_path = _example_as_lima(self)
        self._stub_vms(["dirqual1"])
        calls = self._stub_down()
        code, out, _ = _capture(["destroy", "-f", topo_path, "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("détruite", out)
        # Délégation à run-phases.sh down dirqual1 (les VMs de la stack passées en args).
        self.assertEqual(len(calls), 1)
        self.assertIn("down", calls[0]["cmd"])
        self.assertIn("dirqual1", calls[0]["cmd"])
        # Régression : l'env DOIT porter NODES_OVERRIDE (sinon `phase_down` ne voit aucun
        # disque déclaré → les disques Lima SURVIVENT au down, vécu au banc ceph).
        env = calls[0]["env"]
        self.assertIsNotNone(env, "destroy doit passer l'env dérivé (NODES_OVERRIDE)")
        self.assertIn("NODES_OVERRIDE", env)

    def test_destroy_removes_stack_kubeconfig(self):
        # ADR 0102 volet B : un `down` réussi supprime le kubeconfig de la stack — sinon il
        # reste orphelin (forward mort) et devient un « KUBECONFIG poison » (kubectl → :8080).
        # Topo BENCH (le kubeconfig d'une stack prod déclarée n'est PAS supprimé, cf. garde).
        topo_path = _example_as_lima(self)
        stack = cli._stack_id(topo_path)
        kc = cli._bench_kubeconfig_path(stack)
        os.makedirs(os.path.dirname(kc), exist_ok=True)
        with open(kc, "w", encoding="utf-8") as f:
            f.write("apiVersion: v1\nkind: Config\n")
        self.addCleanup(lambda: os.path.exists(kc) and os.unlink(kc))
        self._stub_vms(["dirqual1"])
        self._stub_down()  # down réussit (rc=0) → la suppression du kubeconfig est atteinte
        code, out, _ = _capture(["destroy", "-f", topo_path, "--yes"])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(kc), "le down doit supprimer le kubeconfig de la stack")
        self.assertIn("kubeconfig", out)  # le message le mentionne

    def test_no_stack_vm_is_noop(self):
        # Aucune VM de la stack présente (cp9 = orpheline) → rien à détruire, code 0,
        # et l'orpheline n'est PAS touchée (destroy ≠ nettoyage d'orphelines).
        self._stub_vms(["cp9"])
        calls = self._stub_down()
        code, out, _ = _capture(["destroy", "-f", _EXAMPLE, "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("aucune VM à détruire", out)
        self.assertEqual(calls, [])  # down JAMAIS appelé

    def test_refuses_without_yes_off_tty(self):
        # Hors TTY (test) sans --yes : refus (pas de suppression silencieuse), code 2,
        # et down JAMAIS appelé. Topo local (destroy ⇒ terrain local).
        topo_path = _example_as_lima(self)
        self._stub_vms(["dirqual1"])
        calls = self._stub_down()
        code, _, err = _capture(["destroy", "-f", topo_path])
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertIn("refusée", err)

    def test_propagates_down_failure(self):
        topo_path = _example_as_lima(self)
        self._stub_vms(["dirqual1"])
        self._stub_down(rc=3)  # run-phases.sh down échoue
        code, _, err = _capture(["destroy", "-f", topo_path, "--yes"])
        self.assertEqual(code, 1)
        self.assertIn("échec", err)


class Access(unittest.TestCase):
    """`access` : accès dev NATIF Python (ADR 0101 — ex-access.sh) : port-forward des UI
    exposées + secrets + `.env` atlas, via `_kubectl`. Pas de vrai banc en test (stub)."""

    def test_stop_kills_port_forwards(self):
        # `--stop` lance un `pkill kubectl.*port-forward` et n'ouvre rien.
        seen = {}

        def _spy(cmd, *a, **k):
            seen["argv"] = list(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        with mock.patch.object(cli.subprocess, "run", _spy):
            code, out, _ = _capture(["access", "--stop"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"][0], "pkill")
        self.assertIn("kubectl.*port-forward", " ".join(seen["argv"]))
        self.assertIn("arrêtés", out)

    def test_returns_2_when_bench_kubeconfig_absent(self):
        # Banc non monté (kubeconfig absent) → code 2, message clair, rien lancé.
        with (
            mock.patch.object(cli, "_bench_kubeconfig", lambda *a, **k: "/nope/kubeconfig"),
            mock.patch.object(cli.os.path, "isfile", lambda p: False),
        ):
            code, _, err = _capture(["access"])
        self.assertEqual(code, 2)
        self.assertIn("kubeconfig banc absent", err)

    def test_refuses_when_context_targets_other_instance(self):
        # La garde d'isolation par IDENTITÉ (neutralisée par défaut dans setUpModule) est
        # RÉACTIVÉE ici : access refuse quand le contexte kubectl courant ne vise pas
        # l'instance active (ADR 0108). La garde lève AVANT toute I/O (1re ligne de
        # cmd_access). On rend une stack active résoluble + un contexte kubectl qui pointe
        # AILLEURS → REFUS (code 2).
        cli._assert_target_identity = _REAL_ASSERT_IDENTITY
        self.addCleanup(setattr, cli, "_assert_target_identity", lambda *a, **k: None)
        orig_stack = cli._active_stack_name
        cli._active_stack_name = lambda _f: "dirqual"
        self.addCleanup(setattr, cli, "_active_stack_name", orig_stack)
        orig_ctx = cli._current_context_and_server
        cli._current_context_and_server = lambda: ("autre", "https://1.2.3.4:6443")
        self.addCleanup(setattr, cli, "_current_context_and_server", orig_ctx)
        code, _, err = _capture(["access"])
        self.assertEqual(code, 2)  # _UsageError → code 2 (garde d'isolation, ADR 0108)
        self.assertIn("REFUS", err)
        self.assertIn("ADR 0108", err)


class RemoveOwnedStorageClasses(unittest.TestCase):
    """`_remove_owned_storage_classes` : retire les SC cluster-scoped Ceph (par provisioner),
    le résidu que la découverte namespacée ne voit pas (début de #392, constaté au banc)."""

    def _stub_kubectl(self, list_out, delete_ok=True):
        # Stube `_kubectl` : 1er appel (get storageclass) → list_out ; delete → rc selon delete_ok.
        deleted = []

        def fake(*args, **k):
            import subprocess as sp

            if args[:2] == ("get", "storageclass"):
                return sp.CompletedProcess(args=args, returncode=0, stdout=list_out, stderr="")
            if args[:2] == ("delete", "storageclass"):
                deleted.append(args[2])
                rc = 0 if delete_ok else 1
                return sp.CompletedProcess(args=args, returncode=rc, stdout="", stderr="")
            return sp.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        orig = cli._kubectl
        cli._kubectl = fake
        self.addCleanup(setattr, cli, "_kubectl", orig)
        return deleted

    _SC_LIST = (
        "rook-ceph-block-replicated=rook-ceph.rbd.csi.ceph.com\n"
        "rook-cephfs=rook-ceph.cephfs.csi.ceph.com\n"
        "rook-ceph-datalake=rook-ceph.ceph.rook.io/bucket\n"
        "local-path=rancher.io/local-path\n"
    )

    def test_deletes_only_ceph_provisioner_sc(self):
        deleted = self._stub_kubectl(self._SC_LIST)
        echecs = cli._remove_owned_storage_classes()
        self.assertEqual(echecs, [])
        # Les 3 SC ceph supprimées, local-path (secours) PRÉSERVÉE.
        self.assertEqual(
            sorted(deleted),
            ["rook-ceph-block-replicated", "rook-ceph-datalake", "rook-cephfs"],
        )
        self.assertNotIn("local-path", deleted)

    def test_delete_failure_is_reported_as_residu(self):
        self._stub_kubectl(self._SC_LIST, delete_ok=False)
        echecs = cli._remove_owned_storage_classes()
        self.assertTrue(all(e.startswith("sc/") for e in echecs))
        self.assertEqual(len(echecs), 3)  # les 3 ceph en échec

    def test_no_storageclass_is_noop(self):
        self._stub_kubectl("")  # aucune SC
        self.assertEqual(cli._remove_owned_storage_classes(), [])


class TargetIdentityGuard(unittest.TestCase):
    """Garde d'isolation par IDENTITÉ (ADR 0108) : une mutation kubectl ne s'exécute QUE si
    le contexte kubectl COURANT est estampillé au `stack_id` de l'instance visée.

    Teste la VRAIE garde (_REAL_ASSERT_IDENTITY), neutralisée ailleurs par setUpModule. Le
    seul discriminant est le cran contexte (endpoint=None dans la garde) : on STUBE
    `_current_context_and_server` (le contexte courant) et on fournit une topo à `.stack_id`
    (ou une stack active résoluble)."""

    class _Topo:
        def __init__(self, stack_id):
            self.stack_id = stack_id

    def _arm(self, *, current_context, current_server="https://1.2.3.4:6443"):
        cli._assert_target_identity = _REAL_ASSERT_IDENTITY
        self.addCleanup(setattr, cli, "_assert_target_identity", lambda *a, **k: None)
        orig = cli._current_context_and_server
        cli._current_context_and_server = lambda: (current_context, current_server)
        self.addCleanup(setattr, cli, "_current_context_and_server", orig)

    def test_passes_when_context_matches_stack(self):
        # contexte kubectl courant == stack_id de l'instance visée → nominal, pas de refus.
        self._arm(current_context="dirqual")
        cli._assert_target_identity("nestor install", self._Topo("dirqual"))  # ne lève pas

    def test_refuses_when_context_targets_other_instance(self):
        # contexte courant ≠ stack_id (ex. un kubeconfig visant une AUTRE instance) → REFUS.
        self._arm(current_context="autre")
        with self.assertRaises(cli._UsageError) as ctx:
            cli._assert_target_identity("nestor install", self._Topo("dirqual"))
        self.assertIn("REFUS", str(ctx.exception))
        self.assertIn("dirqual", str(ctx.exception))

    def test_refuses_when_context_is_foreign_admin(self):
        # kubeconfig étranger (`kubernetes-admin@kubernetes`, `~/.kube/config`) → refus :
        # il ne porte pas le nom estampillé de l'instance (remplace l'échappatoire KUBECONFIG).
        self._arm(current_context="kubernetes-admin@kubernetes")
        with self.assertRaises(cli._UsageError):
            cli._assert_target_identity("nestor install", self._Topo("dirqual"))

    def test_passes_when_no_current_context(self):
        # aucun contexte courant (instance non montée / kubeconfig absent) → la garde ne
        # bloque pas : l'inventaire (chemin SSH) garde, on n'empêche pas un install from-scratch.
        self._arm(current_context=None, current_server=None)
        cli._assert_target_identity("nestor install", self._Topo("dirqual"))  # ne lève pas

    def test_passes_when_no_resolvable_stack(self):
        # pas d'identité résoluble (topo None + aucune stack active) → rien à prouver, passe.
        self._arm(current_context="autre")
        orig = cli._active_stack_name
        cli._active_stack_name = lambda _f: None
        self.addCleanup(setattr, cli, "_active_stack_name", orig)
        cli._assert_target_identity("nestor install")  # ne lève pas

    def test_uses_active_stack_when_no_topo(self):
        # sans topo, l'identité est la stack ACTIVE (`_active_stack_name`) : contexte ≠ elle
        # → REFUS (prouve le chemin `topo=None` de la garde).
        self._arm(current_context="autre")
        orig = cli._active_stack_name
        cli._active_stack_name = lambda _f: "dirqual"
        self.addCleanup(setattr, cli, "_active_stack_name", orig)
        with self.assertRaises(cli._UsageError):
            cli._assert_target_identity("nestor install")


class EnvCommandRemoved(unittest.TestCase):
    """`env` est SUPPRIMÉE (LOT 8, ADR 0097 §3) — plus dans le parseur ni le dispatch.

    Le branchement de kubectl passe désormais par le contexte nommé que `stack select`
    pose dans le kubeconfig de la cible (`kubectl --context <topo> …`), sans variable
    d'env. On PROUVE l'absence par construction, pas seulement par comportement."""

    def test_env_absent_from_dispatch(self):
        # La table de routage ne connaît plus `env` (cmd_env retiré du module).
        self.assertNotIn("env", cli._DISPATCH)
        self.assertFalse(hasattr(cli, "cmd_env"))

    def test_env_absent_from_parser(self):
        # `nestor env` → argparse refuse une sous-commande inconnue (SystemExit code 2).
        parser = cli._build_parser()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["env"])
        self.assertEqual(ctx.exception.code, 2)

    def test_help_does_not_mention_env(self):
        # Le menu d'aide ne propose plus `env` (retiré de l'epilog).
        parser = cli._build_parser()
        self.assertNotIn(
            "env         brancher", parser.epilog or "", "le menu mentionne encore `env`"
        )


class ModuleGuard(unittest.TestCase):
    """Le filet anti-provisionnement (setUpModule) interdit tout run-phases/limactl réel."""

    def test_deny_run_blocks_real_runphases(self):
        with self.assertRaises(AssertionError) as ctx:
            _deny_run(["bash", "/x/bench/lima/run-phases.sh", "socle"])
        self.assertIn("NON BLINDÉ", str(ctx.exception))

    def test_deny_run_blocks_limactl(self):
        with self.assertRaises(AssertionError):
            _deny_run(["limactl", "start", "node1"])

    def test_deny_run_allows_kubectl_get(self):
        # une lecture kubectl get est neutralisée (CompletedProcess vide), pas bloquée.
        out = _deny_run(["kubectl", "get", "nodes"])
        self.assertEqual(out.returncode, 0)


class WarnHelper(unittest.TestCase):
    """_warn : jaune sur un terminal, brut dans un pipe/CI (pas de codes ANSI)."""

    def _capture_warn(self, *, isatty):
        class _Sink(io.StringIO):
            def isatty(self_inner):
                return isatty

        sink = _Sink()
        orig = sys.stderr
        sys.stderr = sink
        try:
            cli._warn("message de test")
        finally:
            sys.stderr = orig
        return sink.getvalue()

    def test_colored_on_tty(self):
        out = self._capture_warn(isatty=True)
        self.assertIn("\033[1;33m", out)  # jaune gras
        self.assertIn("message de test", out)

    def test_plain_in_pipe(self):
        out = self._capture_warn(isatty=False)
        self.assertNotIn("\033[", out)  # aucun code ANSI dans un pipe/CI
        self.assertIn("⚠ message de test", out)


class Scale(unittest.TestCase):
    """`scale` : PLAN par défaut, --apply exécute, refuse ArgoCD. Pas de vrai cluster."""

    def _stub(self, *, ready, argocd=False, scale_rc=0):
        import subprocess as sp

        cli._ready_nodes = lambda *_a: ready
        self.addCleanup(setattr, cli, "_ready_nodes", cli._ready_nodes)

        def _fake_kubectl(*args, **k):
            if "scale" in args:
                return sp.CompletedProcess(args=args, returncode=scale_rc, stdout="", stderr="boom")
            # _argocd_managed : managed-by label
            return sp.CompletedProcess(
                args=args, returncode=0, stdout=("argocd" if argocd else ""), stderr=""
            )

        orig = cli._kubectl
        cli._kubectl = _fake_kubectl
        self.addCleanup(setattr, cli, "_kubectl", orig)

    def test_plan_by_default(self):
        self._stub(ready=["n1", "n2"])
        code, out, _ = _capture(["scale"])
        self.assertEqual(code, 0)
        self.assertIn("2 nœud(s) Ready", out)
        self.assertIn("→ 2 replica(s)", out)
        self.assertIn("PLAN (rien appliqué)", out)

    def test_refuses_unreachable_bench(self):
        self._stub(ready=[])
        code, _, err = _capture(["scale"])
        self.assertEqual(code, 2)  # _UsageError
        self.assertIn("injoignable", err)

    def test_skips_argocd_managed(self):
        self._stub(ready=["n1"], argocd=True)
        code, out, _ = _capture(["scale", "--apply"])
        self.assertEqual(code, 0)
        self.assertIn("ArgoCD", out)  # workloads managés → ⊘ skipped

    def test_apply_failure_propagates(self):
        self._stub(ready=["n1"], scale_rc=1)
        code, _, err = _capture(["scale", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("échec", err)


class Discover(unittest.TestCase):
    """`discover` : reconstruit un topology.yaml depuis le réel sondé. Pas de cluster.

    On stub les sondes I/O (kubectl) de la façade ; la logique pure est testée à part
    (test_discover). Ici on couvre le dispatch, l'émission YAML, l'inconnu, les codes."""

    def _stub_cluster(self):
        cli._ready_nodes = lambda *_a: ["node1"]
        cli._discover_node_roles = lambda: [{"name": "node1", "roles": ["control", "worker"]}]
        cli._discover_namespaces = lambda: ["kube-system", "argocd", "gitea", "squat-ns"]
        cli._discover_crd_groups = lambda: ["applications.argoproj.io"]
        cli._discover_sc_provisioners = lambda: ["rancher.io/local-path"]
        cli._discover_gateways_present = lambda: False
        cli._discover_health = lambda: []
        for name in (
            "_ready_nodes",
            "_discover_node_roles",
            "_discover_namespaces",
            "_discover_crd_groups",
            "_discover_sc_provisioners",
            "_discover_gateways_present",
            "_discover_health",
        ):
            self.addCleanup(setattr, cli, name, getattr(cli, name))

    def test_refuses_unreachable_bench(self):
        cli._ready_nodes = lambda *_a: []
        self.addCleanup(setattr, cli, "_ready_nodes", cli._ready_nodes)
        code, _, err = _capture(["discover"])
        self.assertEqual(code, 2)  # _UsageError
        self.assertIn("injoignable", err)

    def test_emits_valid_topology_on_stdout(self):
        self._stub_cluster()
        code, out, _ = _capture(["discover"])
        self.assertEqual(code, 0)
        # le YAML reconstruit (parsable, couche gitops, backend local-path)
        topo = yaml.safe_load(out)
        self.assertEqual(topo["layers"], ["gitops"])
        self.assertEqual(topo["storage"]["backend"], "local-path")

    def test_unknown_reported_on_stderr(self):
        self._stub_cluster()
        code, _, err = _capture(["discover"])
        self.assertEqual(code, 0)
        self.assertIn("squat-ns", err)  # ns hors catalogue signalé (ADR 0074 §2)

    def test_writes_to_output_with_unknown_comment(self):
        self._stub_cluster()
        path = tempfile.mktemp(suffix=".yaml")
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        code, out, _ = _capture(["discover", "-o", path])
        self.assertEqual(code, 0)
        self.assertIn(path, out)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # YAML valide + inconnu en commentaire tracé dans le fichier
        self.assertIn("layers:", content)
        self.assertIn("# ", content)
        self.assertIn("squat-ns", content)


class Refresh(unittest.TestCase):
    """`refresh` : réaligne la topo active sur le réel voulu (ADR 0076). Pas de cluster.

    On stub le réel via `_real_layers_backend` (la sonde discover agrégée) ; la logique
    pure (diff/fusion) est testée à part (test_refresh_plan/test_refresh_fuse). Ici :
    dispatch, diff affiché, --dry-run, confirmation, fusion en place, fail-closed."""

    _TOPO = """\
# en-tête à préserver (ADR 0023)
catalog:
  topology: banc
  profile: dataops
  terrain: local
  status: cible
nodes:
  - name: node1
    roles:
      - control
      - worker
  - name: node2
    roles:
      - worker
storage:
  backend: local-path
"""

    # Couches du profil dataops résolues en phases (== ce que resolve_layers rend).
    _DATAOPS = ["storage-simple", "metrics-server", "monitoring", "dataops"]

    def setUp(self):
        # `resolve_layers` shellerait le graphe (bloqué par le blindage) → on le stube
        # sur la résolution connue du profil dataops, pour comparer au MÊME grain.
        orig = cli.resolve_layers
        cli.resolve_layers = lambda _declared, _backend: list(self._DATAOPS)
        self.addCleanup(setattr, cli, "resolve_layers", orig)

    def _stub_real(self, *, layers, backend):
        orig = cli._real_layers_backend
        cli._real_layers_backend = lambda: (list(layers), backend)
        self.addCleanup(setattr, cli, "_real_layers_backend", orig)

    def _topo_file(self):
        path = _tmp(self._TOPO)
        self.addCleanup(os.unlink, path)
        return path

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_refuses_unreachable_cluster(self):
        # Aucun réel lu → usage (refresh n'a rien à rapatrier ≠ « rien à faire »).
        self._stub_real(layers=[], backend=None)
        code, _, err = _capture(["refresh", "-f", self._topo_file(), "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("injoignable", err)

    def test_dry_run_shows_diff_writes_nothing(self):
        # Réel = dataops + gitops monté en plus ; --dry-run montre +gitops sans écrire.
        self._stub_real(layers=[*self._DATAOPS, "gitops"], backend="local-path")
        path = self._topo_file()
        before = self._read(path)
        code, out, _ = _capture(["refresh", "-f", path, "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("+ couche `gitops`", out)
        self.assertIn("dry-run", out)
        self.assertEqual(self._read(path), before)  # RIEN écrit

    def test_backend_change_materialized_with_yes(self):
        # Réel passé en ceph (évolution voulue) → fusion écrit backend: ceph, reste intact.
        self._stub_real(layers=self._DATAOPS, backend="ceph")
        path = self._topo_file()
        code, out, _ = _capture(["refresh", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("mis à jour", out)
        d = yaml.safe_load(self._read(path))
        self.assertEqual(d["storage"]["backend"], "ceph")
        self.assertEqual(d["catalog"]["status"], "cible")  # préservé
        self.assertIn("# en-tête à préserver", self._read(path))

    def test_new_layer_materialized(self):
        # Réel ajoute `gitops` (couche en plus, voulue) → +gitops matérialisé.
        self._stub_real(layers=[*self._DATAOPS, "gitops"], backend="local-path")
        path = self._topo_file()
        code, _, _ = _capture(["refresh", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("gitops", yaml.safe_load(self._read(path))["layers"])

    def test_aligned_reports_nothing(self):
        # Réel == déclaré (profil dataops résolu) → rien à rapatrier, rien écrit.
        self._stub_real(layers=self._DATAOPS, backend="local-path")
        path = self._topo_file()
        before = self._read(path)
        code, out, _ = _capture(["refresh", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("déjà aligné", out)
        self.assertEqual(self._read(path), before)

    def test_refused_confirmation_writes_nothing(self):
        # Hors TTY sans --yes : _confirm renvoie défaut (False) → rien écrit, code 0.
        self._stub_real(layers=self._DATAOPS, backend="ceph")
        path = self._topo_file()
        before = self._read(path)
        code, _, err = _capture(["refresh", "-f", path])  # pas de --yes, _capture hors TTY
        self.assertEqual(code, 0)
        self.assertIn("annulé", err)
        self.assertEqual(self._read(path), before)

    # Topo avec une liste `layers:` LITTÉRALE (pour --prune) : monitoring y est écrit.
    _TOPO_LAYERS = (
        "catalog: {topology: banc, profile: dataops, terrain: local}\n"
        "nodes: [{name: node1, roles: [control, worker]}, {name: node2, roles: [worker]}]\n"
        "layers: [metrics-server, monitoring]\n"
        "storage: {backend: local-path}\n"
    )

    def test_prune_removes_absent_layer(self):
        # Le réel n'a QUE metrics-server (monitoring défait) → --prune retire monitoring.
        self.addCleanup(setattr, cli, "resolve_layers", cli.resolve_layers)
        cli.resolve_layers = lambda _d, _b: ["metrics-server", "monitoring"]
        self._stub_real(layers=["metrics-server"], backend="local-path")
        path = _tmp(self._TOPO_LAYERS)
        self.addCleanup(os.unlink, path)
        code, out, _ = _capture(["refresh", "-f", path, "--prune", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("retirée", out)
        self.assertEqual(yaml.safe_load(self._read(path))["layers"], ["metrics-server"])

    def test_absent_layer_signaled_not_pruned_without_flag(self):
        # SANS --prune : la couche absente est SIGNALÉE, pas retirée (défaut prudent §3).
        self.addCleanup(setattr, cli, "resolve_layers", cli.resolve_layers)
        cli.resolve_layers = lambda _d, _b: ["metrics-server", "monitoring"]
        self._stub_real(layers=["metrics-server"], backend="local-path")
        path = _tmp(self._TOPO_LAYERS)
        self.addCleanup(os.unlink, path)
        before = self._read(path)
        code, out, _ = _capture(["refresh", "-f", path, "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("--prune", out)  # invite à utiliser --prune
        self.assertEqual(self._read(path), before)  # RIEN retiré


class Remove(unittest.TestCase):
    """`remove` : supprime une couche + sa clôture PAR DÉCOUVERTE (ADR 0101, seul chemin)."""

    def test_unknown_phase_is_argparse_usage(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["remove", "--phase", "frobnicate"])
        self.assertEqual(ctx.exception.code, 2)  # argparse refuse le choix

    def test_phase_required(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["remove"])
        self.assertEqual(ctx.exception.code, 2)

    def test_dry_run_discovers_delete_targets_without_destroying(self):
        # #372 : --dry-run DÉCOUVRE les CIBLES (racines ; le GC cascade les possédés) et
        # ne détruit RIEN. On stube la sonde owned (façade I/O) ET les ponts bash de
        # roundtrip (closure/phase_namespaces) que le blindage subprocess neutralise
        # (→ vide sinon).
        orig_cl = cli._roundtrip.closure
        cli._roundtrip.closure = lambda phase: [phase]
        self.addCleanup(setattr, cli._roundtrip, "closure", orig_cl)
        orig_ns = cli._roundtrip.phase_namespaces
        cli._roundtrip.phase_namespaces = lambda phase: ["monitoring"]
        self.addCleanup(setattr, cli._roundtrip, "phase_namespaces", orig_ns)
        orig_owned = cli._discover_owned
        # monitoring possède le ns `monitoring` (closure réelle via rollback-lib) : on
        # renvoie un Deployment + son Pod → ordre attendu Pod avant Deployment.
        cli._discover_owned = lambda namespaces: [
            {
                "kind": "Deployment",
                "name": "loki",
                "uid": "u-d",
                "namespace": "monitoring",
                "ownerReferences": [],
            },
            {
                "kind": "Pod",
                "name": "loki-0",
                "uid": "u-p",
                "namespace": "monitoring",
                "ownerReferences": [{"kind": "Deployment", "name": "loki", "uid": "u-d"}],
            },
        ]
        self.addCleanup(setattr, cli, "_discover_owned", orig_owned)
        code, out, _ = _capture(["remove", "--phase", "monitoring", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        # Seule la RACINE (Deployment) est une cible ; le Pod possédé cascade (GC k8s) →
        # il n'apparaît PAS dans les cibles affichées.
        self.assertIn("Deployment/loki", out)
        self.assertNotIn("Pod/loki-0", out)

    def _stub_discovery(self, namespaces, owned):
        # neutralise les ponts bash de roundtrip + la sonde owned (façade I/O) pour un
        # chemin découverte testable sans cluster. closure = la phase seule ; pas de stockage.
        # _delete_namespace stubé (pas de kubectl).
        for name, val in (
            ("closure", lambda phase: [phase]),
            ("phase_namespaces", lambda phase: namespaces),
            ("involves_storage", lambda phase: False),
        ):
            orig = getattr(cli._roundtrip, name)
            setattr(cli._roundtrip, name, val)
            self.addCleanup(setattr, cli._roundtrip, name, orig)
        orig_owned = cli._discover_owned
        cli._discover_owned = lambda ns: owned
        self.addCleanup(setattr, cli, "_discover_owned", orig_owned)
        self.addCleanup(setattr, cli, "_delete_namespace", cli._delete_namespace)
        cli._delete_namespace = lambda ns: (True, "finalisé")
        self.addCleanup(setattr, cli, "_lingering_pods", cli._lingering_pods)
        cli._lingering_pods = lambda ns: []  # défaut : aucun pod coincé (sondes sans cluster)

    def test_discover_deletes_roots_only(self):
        # La découverte supprime les RACINES (le GC cascade les possédés). Le Pod possédé
        # n'est PAS supprimé explicitement.
        self._stub_discovery(
            ["monitoring"],
            [
                {
                    "kind": "Deployment",
                    "name": "loki",
                    "uid": "u-d",
                    "namespace": "monitoring",
                    "ownerReferences": [],
                },
                {
                    "kind": "Pod",
                    "name": "loki-0",
                    "uid": "u-p",
                    "namespace": "monitoring",
                    "ownerReferences": [{"kind": "Deployment", "name": "loki", "uid": "u-d"}],
                },
                {
                    "kind": "Event",
                    "name": "loki.x",
                    "uid": "u-e",
                    "namespace": "monitoring",
                    "ownerReferences": [],
                },
            ],
        )
        deleted = []
        self.addCleanup(setattr, cli, "_kubectl_delete", cli._kubectl_delete)
        self.addCleanup(setattr, cli, "_probe_resource_stuck", cli._probe_resource_stuck)
        cli._kubectl_delete = lambda k, n, ns, **kw: (deleted.append((k, n)), (True, "supprimé"))[1]
        cli._probe_resource_stuck = lambda k, n, ns: None  # tout est parti
        code, out, _ = _capture(["remove", "--phase", "monitoring", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(deleted, [("Deployment", "loki")])  # racine seule (ni Pod ni Event)
        self.assertIn("supprimée par découverte", out)

    def test_discover_does_not_stop_at_first_failure(self):
        # ADR 0079 §4 : un delete échoué n'empêche PAS de tenter les autres racines.
        self._stub_discovery(
            ["dagster"],
            [
                {
                    "kind": "Deployment",
                    "name": "a",
                    "uid": "u-a",
                    "namespace": "dagster",
                    "ownerReferences": [],
                },
                {
                    "kind": "Deployment",
                    "name": "b",
                    "uid": "u-b",
                    "namespace": "dagster",
                    "ownerReferences": [],
                },
            ],
        )
        tried = []

        def fake_delete(k, n, ns, **kw):
            tried.append(n)
            return (False, "erreur") if n == "a" else (True, "supprimé")

        self.addCleanup(setattr, cli, "_kubectl_delete", cli._kubectl_delete)
        self.addCleanup(setattr, cli, "_probe_resource_stuck", cli._probe_resource_stuck)
        cli._kubectl_delete = fake_delete
        cli._probe_resource_stuck = lambda k, n, ns: None
        code, out, _ = _capture(["remove", "--phase", "dataops", "--yes"])
        # les DEUX ont été tentées malgré l'échec de la 1re.
        self.assertEqual(sorted(tried), ["a", "b"])

    def test_discover_storage_closure_requires_full(self):
        # une clôture de STOCKAGE sans --full → usage (2), comme le chemin table.
        orig = cli._roundtrip.involves_storage
        cli._roundtrip.involves_storage = lambda phase: True
        self.addCleanup(setattr, cli._roundtrip, "involves_storage", orig)
        orig_cl = cli._roundtrip.closure
        cli._roundtrip.closure = lambda phase: [phase]
        self.addCleanup(setattr, cli._roundtrip, "closure", orig_cl)
        code, _, err = _capture(["remove", "--phase", "sc", "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("--full", err)

    def test_ceph_routes_to_discovery_with_nodeside(self):
        # ADR 0101 : `ceph` (node-side disques) route désormais vers la DÉCOUVERTE — qui
        # couvre AUSSI le wipe node-side (cleanup.sh poussé par _node_exec_script), plus de
        # table. On vérifie que la découverte est appelée ET que le node-side est tenté.
        called_discovery = []

        def fake_disco(phase, *, full, assume_yes, topo=None, inventory_path=None):
            called_discovery.append((phase, topo is not None, inventory_path is not None))
            return 0

        orig = cli._remove_by_discovery
        cli._remove_by_discovery = fake_disco
        self.addCleanup(setattr, cli, "_remove_by_discovery", orig)
        code, _, _ = _capture(["remove", "-f", _EXAMPLE, "--phase", "ceph", "--full", "--yes"])
        self.assertEqual(code, 0)
        # découverte appelée pour ceph, AVEC topo + inventaire (requis pour le node-side).
        self.assertEqual(called_discovery, [("ceph", True, True)])

    def test_discover_finalizes_owned_namespaces(self):
        # la découverte finalise les ns possédés (ce qui manquait au chemin table : ns wedgé).
        finalized = []
        self._stub_discovery(
            ["dagster", "postgres"],
            [
                {
                    "kind": "Deployment",
                    "name": "d",
                    "uid": "u-d",
                    "namespace": "dagster",
                    "ownerReferences": [],
                }
            ],
        )
        # remplace le stub _delete_namespace du helper pour CAPTER les ns finalisés.
        cli._delete_namespace = lambda ns: (finalized.append(ns), (True, "finalisé"))[1]
        self.addCleanup(setattr, cli, "_kubectl_delete", cli._kubectl_delete)
        self.addCleanup(setattr, cli, "_probe_resource_stuck", cli._probe_resource_stuck)
        cli._kubectl_delete = lambda k, n, ns, **kw: (True, "supprimé")
        cli._probe_resource_stuck = lambda k, n, ns: None
        code, _, _ = _capture(["remove", "--phase", "dataops", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(finalized), ["dagster", "postgres"])

    def test_discover_force_deletes_lingering_possede_pods(self):
        # Régression (vécu banc) : un Pod POSSÉDÉ qui traîne (grace 1800s CNPG / conteneur
        # vivant) n'est pas une racine → la 3e passe le force-delete AVANT de finaliser le ns.
        self._stub_discovery(
            ["postgres"],
            [
                {
                    "kind": "Cluster",
                    "name": "pg",
                    "uid": "u-c",
                    "namespace": "postgres",
                    "ownerReferences": [],
                }
            ],
        )
        # 1er appel (boucle) → le pod traîne ; 2e appel (re-check post-force) → parti.
        calls = {"postgres": 0}

        def lingering(ns):
            if ns != "postgres":
                return []
            calls["postgres"] += 1
            return ["pg-1"] if calls["postgres"] == 1 else []

        cli._lingering_pods = lingering
        forced = []
        self.addCleanup(setattr, cli, "_kubectl_delete", cli._kubectl_delete)
        self.addCleanup(setattr, cli, "_probe_resource_stuck", cli._probe_resource_stuck)

        def fake_delete(k, n, ns, **kw):
            if k == "pod":
                forced.append((n, kw.get("force_grace0")))
            return (True, "supprimé")

        cli._kubectl_delete = fake_delete
        cli._probe_resource_stuck = lambda k, n, ns: None
        code, out, _ = _capture(["remove", "--phase", "dataops", "--yes"])
        self.assertEqual(code, 0)
        # le pod possédé pg-1 a été force-delete (--grace-period=0), pas seulement la racine.
        self.assertIn(("pg-1", True), forced)
        self.assertIn("force pod pg-1", out)


class NodeExec(unittest.TestCase):
    """ADR 0081 : `_node_exec` exécute sur un nœud, transport résolu de l'inventaire."""

    _LIMA_INV = (
        "cloud:\n"
        "  vars:\n    ansible_user: lima\n    stack_id: banc-citation\n    transport: lima\n"
        "control:\n  hosts:\n    node1:\n      ansible_host: lima-node1\n"
    )
    _PROD_INV = (
        "cloud:\n"
        "  vars:\n    ansible_user: debian\n    stack_id: dirqual\n    transport: ssh\n"
        "control:\n  hosts:\n    cp1:\n      ansible_host: 10.0.0.11\n"
    )

    def _capture_cmd(self, inv_text, node):
        # stub subprocess.run dans le module CLI → capte l'argv sans rien exécuter.
        captured = {}

        class _CP:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return _CP()

        orig = cli.subprocess.run
        cli.subprocess.run = fake_run
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        path = _tmp(inv_text)
        self.addCleanup(os.unlink, path)
        cli._node_exec(node, ["hostname"], inventory_path=path)
        return captured["cmd"]

    def test_lima_node_uses_limactl(self):
        cmd = self._capture_cmd(self._LIMA_INV, "node1")
        # nom d'INSTANCE limactl = nom du nœud (node1), pas ansible_host (lima-node1).
        self.assertEqual(cmd[:3], ["limactl", "shell", "node1"])
        self.assertEqual(cmd[-1], "hostname")

    def test_prod_node_uses_ssh_with_user_host(self):
        cmd = self._capture_cmd(self._PROD_INV, "cp1")
        self.assertEqual(cmd[0], "ssh")
        self.assertIn("debian@10.0.0.11", cmd)
        self.assertEqual(cmd[-1], "hostname")

    def test_unknown_node_is_usage_error(self):
        path = _tmp(self._PROD_INV)
        self.addCleanup(os.unlink, path)
        with self.assertRaises(cli._UsageError):
            cli._node_exec("ghost", ["hostname"], inventory_path=path)

    def test_exec_script_pushes_stdin_with_sudo_env(self):
        # _node_exec_script : `sudo env K=V bash -s` + le script en stdin (input=).
        captured = {}

        class _CP:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            captured["input"] = kw.get("input")
            return _CP()

        orig = cli.subprocess.run
        cli.subprocess.run = fake_run
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        inv = _tmp(self._LIMA_INV)
        self.addCleanup(os.unlink, inv)
        script = _tmp("echo wipe\n")
        self.addCleanup(os.unlink, script)
        cli._node_exec_script(
            "node1", script, inventory_path=inv, env={"NVME_BLOCK_DEVICE": "/dev/vde"}
        )
        cmd = captured["cmd"]
        self.assertEqual(cmd[:3], ["limactl", "shell", "node1"])
        # argv = … -- sudo env NVME_BLOCK_DEVICE=/dev/vde bash -s
        self.assertIn("sudo", cmd)
        self.assertIn("env", cmd)
        self.assertIn("NVME_BLOCK_DEVICE=/dev/vde", cmd)
        self.assertEqual(cmd[-2:], ["bash", "-s"])
        self.assertEqual(captured["input"], "echo wipe\n")  # script poussé EN STDIN


class RollbackNodeSideCeph(unittest.TestCase):
    """ADR 0101 : wipe node-side Ceph (ex-phase_rollback) — boucle nœuds, lance cleanup.sh."""

    def _ceph_topo(self):
        # Topo ceph 3-nœuds EN MÉMOIRE (pas topologies/ceph.yaml, gitignoré → absent en CI).
        return topology_from_dict(
            {
                "catalog": {"topology": "multi-node-3", "terrain": "local"},
                "nodes": [
                    {"name": "node1", "roles": ["control", "worker", "storage"]},
                    {"name": "node2", "roles": ["worker", "storage"]},
                    {"name": "node3", "roles": ["worker", "storage"]},
                ],
                "storage": {"backend": "ceph"},
            }
        )

    def test_skips_when_phase_has_no_nodeside(self):
        # une phase SANS node-side (gitops) → aucun nœud touché, liste d'échecs vide.
        echecs = cli._rollback_node_side_ceph("gitops", self._ceph_topo(), inventory_path="/x")
        self.assertEqual(echecs, [])

    def test_wipes_each_node_on_ceph(self):
        # ceph → cleanup.sh poussé sur CHAQUE nœud ; tout OK → aucun échec.
        calls = []

        class _CP:
            returncode = 0

        def fake_script(node, script, *, inventory_path, env, **kw):
            calls.append(node)
            return _CP()

        orig = cli._node_exec_script
        cli._node_exec_script = fake_script
        self.addCleanup(setattr, cli, "_node_exec_script", orig)
        echecs = cli._rollback_node_side_ceph("ceph", self._ceph_topo(), inventory_path="/x")
        self.assertEqual(echecs, [])
        self.assertEqual(set(calls), {"node1", "node2", "node3"})  # les 3 nœuds wipés

    def test_collects_node_failures(self):
        # un nœud injoignable (None) ou rc≠0 → listé en échec (résidu disque possible).
        class _Fail:
            returncode = 1

        class _Ok:
            returncode = 0

        def fake_script(node, script, *, inventory_path, env, **kw):
            if node == "node2":
                return None  # injoignable
            if node == "node3":
                return _Fail()  # rc≠0
            return _Ok()

        orig = cli._node_exec_script
        cli._node_exec_script = fake_script
        self.addCleanup(setattr, cli, "_node_exec_script", orig)
        echecs = cli._rollback_node_side_ceph("ceph", self._ceph_topo(), inventory_path="/x")
        self.assertEqual(set(echecs), {"node2", "node3"})  # node1 OK, node2 injoignable, node3 rc≠0


class FetchKubeconfig(unittest.TestCase):
    """ADR 0081 étape 2 : _fetch_kubeconfig rapatrie + réécrit le kubeconfig (sans nœud)."""

    _ADMIN = (
        "apiVersion: v1\nkind: Config\n"
        "clusters:\n  - name: kubernetes\n    cluster:\n      server: https://cluster-api:6443\n"
        "users:\n  - name: kubernetes-admin\n    user: {}\n"
        "contexts:\n  - name: kubernetes-admin@kubernetes\n"
        "    context:\n      cluster: kubernetes\n      user: kubernetes-admin\n"
        "current-context: kubernetes-admin@kubernetes\n"
    )
    _INV = "cloud:\n  vars:\n    stack_id: banc\ncontrol:\n  hosts:\n    node1: {}\n"

    def test_fetches_rewrites_and_writes(self):
        inv = _tmp(self._INV)
        self.addCleanup(os.unlink, inv)
        out_path = _tmp("")
        self.addCleanup(os.unlink, out_path)
        admin = self._ADMIN

        class _CP:
            returncode = 0
            stdout = admin
            stderr = ""

        orig = cli._node_exec
        cli._node_exec = lambda node, argv, **kw: _CP()
        self.addCleanup(setattr, cli, "_node_exec", orig)
        with contextlib.redirect_stdout(io.StringIO()):
            cli._fetch_kubeconfig(
                "node1",
                inventory_path=inv,
                server="https://127.0.0.1:6443",
                out_path=out_path,
                context_name="banc",
            )
        with open(out_path, encoding="utf-8") as f:
            written = yaml.safe_load(f)
        # endpoint réécrit + contexte renommé (la transfo pure est testée à part).
        self.assertEqual(written["clusters"][0]["cluster"]["server"], "https://127.0.0.1:6443")
        self.assertEqual(written["clusters"][0]["name"], "banc")
        self.assertEqual(os.stat(out_path).st_mode & 0o777, 0o600)

    def test_unreachable_node_is_usage_error(self):
        inv = _tmp(self._INV)
        self.addCleanup(os.unlink, inv)
        out_path = _tmp("")
        self.addCleanup(os.unlink, out_path)
        orig = cli._node_exec
        cli._node_exec = lambda node, argv, **kw: None  # injoignable
        self.addCleanup(setattr, cli, "_node_exec", orig)
        with self.assertRaises(cli._UsageError):
            cli._fetch_kubeconfig(
                "node1", inventory_path=inv, server="https://x:6443", out_path=out_path
            )


class DiscoverNodeside(unittest.TestCase):
    """ADR 0081 étape 3 : _discover_nodeside sonde le node-side via node_exec (sans nœud)."""

    _INV = "cloud:\n  vars:\n    stack_id: banc\ncontrol:\n  hosts:\n    node1: {}\n"

    def _stub_probes(self, table):
        # table: argv-clé (1er mot après 'sh -c' ou la commande) → stdout. None = injoignable.
        class _CP:
            def __init__(self, out):
                self.returncode = 0
                self.stdout = out
                self.stderr = ""

        def fake(node, argv, **kw):
            # clé = 1er mot de la sonde (containerd/sudo/sh/systemctl) ou la commande sh -c.
            key = argv[-1] if argv[0] == "sh" else argv[0]
            if key not in table:
                return _CP("")  # true / sondes non stubées → ok vide
            val = table[key]
            return None if val is None else _CP(val)

        orig = cli._node_exec
        cli._node_exec = fake
        self.addCleanup(setattr, cli, "_node_exec", orig)

    def test_assembles_nodeside_facts(self):
        inv = _tmp(self._INV)
        self.addCleanup(os.unlink, inv)
        self._stub_probes(
            {
                "containerd": "containerd github.com/... v1.7.27 x",
                "sudo": "05-cilium.conflist",  # sudo ls /etc/cni/net.d (root-only)
                "lsblk -dno NAME,SIZE 2>/dev/null": "vda 40G\nvdb 10G\n",
                "systemctl": "active",  # auditd ET fail2ban → active
            }
        )
        ns = cli._discover_nodeside("node1", inventory_path=inv)
        self.assertEqual(ns.cri, "containerd 1.7.27")
        self.assertEqual(ns.cni, "cilium")
        self.assertEqual([d.name for d in ns.disks], ["vda", "vdb"])
        self.assertEqual(ns.hardening, "hardened")

    def test_unreachable_node_returns_none(self):
        inv = _tmp(self._INV)
        self.addCleanup(os.unlink, inv)
        orig = cli._node_exec
        cli._node_exec = lambda node, argv, **kw: None  # injoignable dès `true`
        self.addCleanup(setattr, cli, "_node_exec", orig)
        self.assertIsNone(cli._discover_nodeside("node1", inventory_path=inv))


class Dispatch(unittest.TestCase):
    def test_unknown_command_is_usage(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["frobnicate"])
        self.assertEqual(ctx.exception.code, 2)  # argparse usage

    def test_no_command_is_usage(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main([])
        self.assertEqual(ctx.exception.code, 2)


class PromptUX(unittest.TestCase):
    """Standardisation UX des prompts interactifs (« par défaut, nestor ne fait rien »).

    Règle 1 — confirmation binaire : hint « oui/NON » (NON majuscule = défaut False),
    Entrée vide = ne PAS faire ; `--yes`/`--no-input` force le défaut (CI). Règle 2 —
    menu de sélection : Entrée vide → None (annuler), PLUS de « défaut 1 »."""

    def _stub_input(self, reponses):
        """Stube `builtins.input` : capte le PROMPT vu + sert `reponses` en file."""
        import builtins

        seen = []
        it = iter(reponses)

        def _fake(prompt=""):
            seen.append(prompt)
            return next(it)

        orig = builtins.input
        builtins.input = _fake
        self.addCleanup(setattr, builtins, "input", orig)
        return seen

    # ── _confirm : hint + défaut ──────────────────────────────────────────────
    def test_confirm_hint_default_false_is_oui_NON(self):
        seen = self._stub_input([""])  # Entrée vide
        self.assertIs(cli._confirm("Agir ?", default=False, no_input=False), False)
        self.assertIn("[oui/NON]", seen[0])  # NON majuscule = défaut

    def test_confirm_hint_default_true_is_OUI_non(self):
        seen = self._stub_input([""])
        self.assertIs(cli._confirm("Agir ?", default=True, no_input=False), True)
        self.assertIn("[OUI/non]", seen[0])  # OUI majuscule = défaut

    def test_confirm_empty_does_not_act(self):
        # Entrée vide avec défaut False = NE PAS faire l'action (sécurité).
        self._stub_input([""])
        self.assertIs(cli._confirm("Détruire ?", default=False, no_input=False), False)

    def test_confirm_accepts_oui_and_non_variants(self):
        for rep in ("o", "oui", "y", "yes", "OUI", "Yes"):
            self._stub_input([rep])
            self.assertIs(cli._confirm("Agir ?", default=False, no_input=False), True, rep)
        for rep in ("n", "non", "no", "NON"):
            self._stub_input([rep])
            self.assertIs(cli._confirm("Agir ?", default=True, no_input=False), False, rep)

    def test_confirm_no_input_returns_default_without_prompt(self):
        # --no-input (CI) : renvoie le défaut SANS prompter (input() jamais appelé).
        def _boom(prompt=""):
            raise AssertionError("input() ne doit pas être appelé sous no_input")

        import builtins

        orig = builtins.input
        builtins.input = _boom
        self.addCleanup(setattr, builtins, "input", orig)
        self.assertIs(cli._confirm("Agir ?", default=False, no_input=True), False)
        self.assertIs(cli._confirm("Agir ?", default=True, no_input=True), True)

    # ── _choisir_couche : Entrée vide → None (rien monté) ─────────────────────
    def test_choisir_empty_returns_none(self):
        seen = self._stub_input([""])  # Entrée vide au menu
        out = cli._choisir_couche(["a", "b", "c"], lambda p: p, no_input=False)
        self.assertIsNone(out)  # annulé : rien à monter
        self.assertIn("annuler", seen[0])  # invite annonce l'annulation
        self.assertNotIn("défaut", seen[0])  # PLUS de « défaut 1 »

    def test_choisir_explicit_number_picks_it(self):
        self._stub_input(["2"])
        self.assertEqual(cli._choisir_couche(["a", "b", "c"], lambda p: p, no_input=False), "b")

    def test_choisir_reprompts_on_invalid_then_accepts(self):
        seen = self._stub_input(["9", "0", "1"])  # hors borne, hors borne, puis valide
        self.assertEqual(cli._choisir_couche(["a", "b"], lambda p: p, no_input=False), "a")
        self.assertGreaterEqual(len(seen), 3)  # a bien re-demandé

    def test_choisir_no_input_keeps_conventional_order(self):
        # no_input (n'est activé QUE pour --yes par cmd_next) = demande explicite d'agir
        # → ordre conventionnel (choix[0]), déterministe en CI. SANS prompter.
        def _boom(prompt=""):
            raise AssertionError("input() ne doit pas être appelé sous no_input")

        import builtins

        orig = builtins.input
        builtins.input = _boom
        self.addCleanup(setattr, builtins, "input", orig)
        self.assertEqual(cli._choisir_couche(["a", "b"], lambda p: p, no_input=True), "a")


if __name__ == "__main__":
    unittest.main()
