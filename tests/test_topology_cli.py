"""Tests de la façade CLI de l'outil déclaratif (scripts/topology.py, ADR 0056 P3).

unittest stdlib (lancé par `pnpm test:python` = unittest discover -s tests). La
CLI est conçue ARGV-INJECTABLE (`main(argv)`) : on appelle `main([...])` et on
asserte la valeur de RETOUR (code de sortie) + la sortie capturée, SANS subprocess
(rapide, pur). La logique métier est déjà testée dans test_cluster_topology.py ;
ici on couvre la façade : dispatch, codes de sortie, mapping des exceptions,
garde-fou byte-identique de `diff`.
"""

import contextlib
import datetime as dt
import importlib.util
import io
import os
import sys
import tempfile
import unittest

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

from cluster_topology import (  # noqa: E402
    derive_run_params,
    load_topology,
    render_lima_inventory,
    render_prod_inventory,
)

_EXAMPLE = os.path.join(_ROOT, "topology.example.yaml")

_INVALID_TOPO = """\
catalog:
  topology: bancal
nodes:
  - name: x
    roles: [master]
target_kind: prod
"""

_HA_NO_VIP = """\
catalog:
  topology: ha
nodes:
  - name: cp1
    roles: [control]
  - name: cp2
    roles: [control]
target_kind: prod
"""


def _capture(argv):
    """Lance main(argv) ; renvoie (code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _tmp(content):
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class Validate(unittest.TestCase):
    def test_example_is_valid(self):
        code, out, _ = _capture(["validate", "-f", _EXAMPLE])
        self.assertEqual(code, 0)
        self.assertIn("valide", out)

    def test_invalid_role_rejected(self):
        path = _tmp(_INVALID_TOPO)
        self.addCleanup(os.unlink, path)
        code, _, err = _capture(["validate", "-f", path])
        self.assertEqual(code, 1)
        self.assertIn("erreur", err)

    def test_ha_without_vip_rejected(self):
        path = _tmp(_HA_NO_VIP)
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["validate", "-f", path])
        self.assertEqual(code, 1)

    def test_missing_file_is_business_error(self):
        code, _, err = _capture(["validate", "-f", "/nope/topology.yaml"])
        self.assertEqual(code, 1)
        self.assertIn("erreur", err)


class Generate(unittest.TestCase):
    def test_prod_inventory_matches_facade(self):
        # generate doit ré-émettre EXACTEMENT render_prod_inventory (invariant P1).
        code, out, _ = _capture(["generate", "-f", _EXAMPLE, "--kind", "prod"])
        self.assertEqual(code, 0)
        self.assertEqual(out, render_prod_inventory(load_topology(_EXAMPLE)))

    def test_lima_inventory_matches_facade(self):
        topo = load_topology(_EXAMPLE)
        # l'exemple est prod ; on force --kind lima avec un HOME fixe.
        code, out, _ = _capture(["generate", "-f", _EXAMPLE, "--kind", "lima", "--lima-home", "/H"])
        self.assertEqual(code, 0)
        self.assertEqual(out, render_lima_inventory(topo, "/H"))

    def test_run_params_yaml_reparses_to_derivation(self):
        import yaml

        code, out, _ = _capture(["generate", "-f", _EXAMPLE, "--what", "run-params"])
        self.assertEqual(code, 0)
        self.assertEqual(yaml.safe_load(out), derive_run_params(load_topology(_EXAMPLE)))

    def test_output_to_file(self):
        dst = _tmp("")
        self.addCleanup(os.unlink, dst)
        code, out, _ = _capture(["generate", "-f", _EXAMPLE, "-o", dst])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")  # rien sur stdout quand -o
        with open(dst, encoding="utf-8") as f:
            self.assertEqual(f.read(), render_prod_inventory(load_topology(_EXAMPLE)))

    def test_output_to_invalid_dir_is_usage_error(self):
        # -o vers un répertoire absent = destination invalide fournie en argument
        # → erreur d'usage (code 2), pas erreur métier (code 1).
        code, _, err = _capture(["generate", "-f", _EXAMPLE, "-o", "/nope/nope/inv.yaml"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class Diff(unittest.TestCase):
    def test_prod_invariant_holds(self):
        # topology.example.yaml régénère hosts.example.yaml à l'octet → code 0, vide.
        code, out, _ = _capture(["diff", "-f", _EXAMPLE, "--kind", "prod"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_drift_detected(self):
        # comparer l'inventaire prod régénéré à une référence DIFFÉRENTE → code 1.
        ref = _tmp("# pas l'inventaire attendu\n")
        self.addCleanup(os.unlink, ref)
        code, out, _ = _capture(["diff", "-f", _EXAMPLE, "--kind", "prod", "--against", ref])
        self.assertEqual(code, 1)
        self.assertIn("généré", out)  # un diff unifié a été émis

    def test_missing_reference_is_usage_error(self):
        code, _, err = _capture(
            ["diff", "-f", _EXAMPLE, "--kind", "prod", "--against", "/nope.yaml"]
        )
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_lima_requires_against(self):
        # pas de golden Lima versionné → --against obligatoire (code 2 sans).
        code, _, err = _capture(["diff", "-f", _EXAMPLE, "--kind", "lima"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_default_reference_is_hosts_example(self):
        # Le garde-fou CI (lint:topology-drift) compare au .EXAMPLE versionné, JAMAIS
        # au hosts.yaml réel (gitignoré). Verrouille la cible du défaut contre une
        # régression silencieuse de _PROD_INVENTORY.
        self.assertTrue(cli._PROD_INVENTORY.endswith("bootstrap/hosts.example.yaml"))

    def test_default_kind_and_against_resolve_to_prod(self):
        # sans --kind ni --against, l'exemple (target_kind: prod) doit tenir
        # l'invariant — garantit que le défaut de la cible CI est exécutable tel quel.
        code, out, _ = _capture(["diff", "-f", _EXAMPLE])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class Status(unittest.TestCase):
    def test_wanted_state_no_real(self):
        code, out, _ = _capture(["status", "-f", _EXAMPLE])
        self.assertEqual(code, 0)
        self.assertIn("control-planes", out)
        self.assertIn("stockage", out)
        self.assertIn("profil", out)

    def test_real_propagates_state_sh_code(self):
        # --real délègue à state.sh (SSH+kubectl) : non lançable en CI. On vérifie
        # que le code de state.sh est PROPAGÉ, sans réseau, en stubant subprocess.run.
        import subprocess

        sentinel = subprocess.CompletedProcess(args=[], returncode=2)
        orig = cli.subprocess.run
        cli.subprocess.run = lambda *a, **k: sentinel
        self.addCleanup(setattr, cli.subprocess, "run", orig)
        code, _, _ = _capture(["status", "-f", _EXAMPLE, "--real"])
        self.assertEqual(code, 2)


class Epreuves(unittest.TestCase):
    def test_lists_playable(self):
        code, out, _ = _capture(["epreuves", "-f", _EXAMPLE])
        self.assertEqual(code, 0)
        self.assertIn("jouables", out)
        self.assertIn("vérifié au lancement, P5", out)  # n'en lance aucune

    def test_all_shows_excluded(self):
        code, out, _ = _capture(["epreuves", "-f", _EXAMPLE, "--all"])
        self.assertEqual(code, 0)
        self.assertIn("exclues", out)
        self.assertIn("offensif", out)  # 17-21 exclus en prod (ADR 0025)

    def test_invalid_topology_is_business_error(self):
        path = _tmp("nodes:\n  - name: x\n    roles: [master]\n")
        self.addCleanup(os.unlink, path)
        code, _, _ = _capture(["epreuves", "-f", path])
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
        # bloquant de CI reste check-freshness.sh, non dupliqué).
        hist = _tmp(self._HIST)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["runs", "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("run(s) consigné", out)

    def test_target_on_history_without_target_falls_back(self):
        # --target sur un historique sans champ `target` (rétrocompat) → avis
        # explicite + état global, code 0 (pas un plantage).
        hist = _tmp(self._HIST)  # _HIST n'a pas de champ target
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["runs", "--history", hist, "--target", "atlas"])
        self.assertEqual(code, 0)
        self.assertIn("aucune entrée ne porte de chemin", out)

    def test_missing_history_is_business_error(self):
        code, _, err = _capture(["runs", "--history", "/nope/runs.yaml"])
        self.assertEqual(code, 1)
        self.assertIn("erreur", err)


class Next(unittest.TestCase):
    _EMPTY_HIST = "runs: []\n"
    # Historique frais où le socle Ceph est joué → la 1re phase manquante de
    # cluster-dataops est `datalake` (qui A un playbook unitaire, donc --apply-able).
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

    def test_suggests_without_apply_is_zero_and_never_launches(self):
        # Sans --apply : informatif, code 0, et le runner n'est JAMAIS appelé.
        called = []
        orig = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: called.append(1)
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(
            ["next", "-f", _EXAMPLE, "--target", "atlas-ceph", "--history", hist]
        )
        self.assertEqual(code, 0)
        self.assertIn("Prochaine étape", out)
        self.assertEqual(called, [])  # aucun lancement sans --apply

    def test_unknown_target_is_usage_error(self):
        code, _, err = _capture(["next", "-f", _EXAMPLE, "--target", "frobnicate"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def _ensure_inventory(self):
        """Garantit un bootstrap/hosts.yaml (gitignoré, absent en CI) pour --apply ;
        le retire ensuite si on l'a créé. Sinon le garde-fou d'inventaire bloque."""
        inv = os.path.join(_ROOT, "bootstrap", "hosts.yaml")
        if not os.path.exists(inv):
            with open(inv, "w", encoding="utf-8") as f:
                f.write("# inventaire de test (créé puis retiré)\n")
            self.addCleanup(os.unlink, inv)

    def test_apply_launches_runner_and_maps_rc(self):
        # --apply appelle runner.launch_phase (stub rc=0) → code 0 ; UNE phase.
        from cluster_topology.runner import RunResult

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
            ["next", "-f", _EXAMPLE, "--target", "cluster-dataops", "--history", hist, "--apply"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)  # UNE phase lancée, pas la séquence
        # 1re phase manquante après le socle = datalake (l'exemple a hardening
        # désactivé) ; le point clé : UNE phase, avec un playbook réel.
        self.assertTrue(calls[0][0].endswith(".yaml"))

    def test_apply_without_inventory_is_usage_error(self):
        # --apply sans bootstrap/hosts.yaml → erreur d'usage claire (code 2),
        # pas une erreur cryptique d'ansible-runner.
        inv = os.path.join(_ROOT, "bootstrap", "hosts.yaml")
        if os.path.exists(inv):
            self.skipTest("bootstrap/hosts.yaml présent localement — cas testé en CI")
        orig = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: None
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._SOCLE_DONE)
        self.addCleanup(os.unlink, hist)
        code, _, err = _capture(
            ["next", "-f", _EXAMPLE, "--target", "cluster-dataops", "--history", hist, "--apply"]
        )
        self.assertEqual(code, 2)
        self.assertIn("inventaire absent", err)

    def test_apply_propagates_failure_rc(self):
        from cluster_topology.runner import RunResult

        self._ensure_inventory()
        orig = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: RunResult(rc=2, status="failed")
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._SOCLE_DONE)
        self.addCleanup(os.unlink, hist)
        code, _, _ = _capture(
            ["next", "-f", _EXAMPLE, "--target", "cluster-dataops", "--history", hist, "--apply"]
        )
        self.assertEqual(code, 1)  # run KO → code 1

    def test_apply_on_non_playbook_phase_is_usage_error(self):
        # Une phase sans play unitaire (up, sur rejeu depuis zéro) ne s'apply pas.
        orig = cli._runner.launch_phase
        cli._runner.launch_phase = lambda *a, **k: None
        self.addCleanup(setattr, cli._runner, "launch_phase", orig)
        hist = _tmp(self._EMPTY_HIST)
        self.addCleanup(os.unlink, hist)
        code, _, err = _capture(
            ["next", "-f", _EXAMPLE, "--target", "cluster-dataops", "--history", hist, "--apply"]
        )
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


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
        code, out, _ = _capture(["metrics", "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("cpu_core_s=272", out)
        self.assertIn("12m39s", out)  # 759 s

    def test_empty_history(self):
        hist = _tmp("runs: []\n")
        self.addCleanup(os.unlink, hist)
        code, out, _ = _capture(["metrics", "--history", hist])
        self.assertEqual(code, 0)
        self.assertIn("aucun run", out)


class Smoke(unittest.TestCase):
    def test_reversible_is_zero(self):
        from cluster_topology.smoke import SmokeResult, SmokeStep

        res = SmokeResult(
            namespace="topo-smoke",
            steps=[SmokeStep("créer", True), SmokeStep("vérifier détruit", True)],
        )
        orig = cli._smoke.run_smoke
        cli._smoke.run_smoke = lambda ns: res
        self.addCleanup(setattr, cli._smoke, "run_smoke", orig)
        code, out, _ = _capture(["smoke"])
        self.assertEqual(code, 0)
        self.assertIn("réversible", out)

    def test_not_reversible_is_one(self):
        from cluster_topology.smoke import SmokeResult, SmokeStep

        res = SmokeResult(namespace="x", steps=[SmokeStep("créer", False, "échec")])
        orig = cli._smoke.run_smoke
        cli._smoke.run_smoke = lambda ns: res
        self.addCleanup(setattr, cli._smoke, "run_smoke", orig)
        code, _, _ = _capture(["smoke"])
        self.assertEqual(code, 1)

    def test_cluster_unavailable_is_usage_error(self):
        def boom(ns):
            raise cli._smoke.SmokeUnavailable("cluster injoignable")

        orig = cli._smoke.run_smoke
        cli._smoke.run_smoke = boom
        self.addCleanup(setattr, cli._smoke, "run_smoke", orig)
        code, _, err = _capture(["smoke"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class Roundtrip(unittest.TestCase):
    def _stub(self, res):
        orig = cli._roundtrip.run_roundtrip
        cli._roundtrip.run_roundtrip = lambda phase, **kw: res
        self.addCleanup(setattr, cli._roundtrip, "run_roundtrip", orig)

    def test_reversible_is_zero(self):
        from cluster_topology.roundtrip import RoundtripResult, RoundtripStep

        self._stub(
            RoundtripResult(
                phase="monitoring",
                layers=["monitoring"],
                steps=[RoundtripStep("détruire", True), RoundtripStep("vérifier sain", True)],
            )
        )
        code, out, _ = _capture(["roundtrip", "--phase", "monitoring", "--yes"])
        self.assertEqual(code, 0)
        self.assertIn("réversible", out)

    def test_not_reversible_is_one(self):
        from cluster_topology.roundtrip import RoundtripResult, RoundtripStep

        self._stub(
            RoundtripResult(
                phase="gitops",
                layers=["gitops", "gitops-seed"],
                steps=[RoundtripStep("détruire gitops", False, "rc=3")],
            )
        )
        code, _, _ = _capture(["roundtrip", "--phase", "gitops", "--yes"])
        self.assertEqual(code, 1)

    def test_storage_without_full_is_usage_error(self):
        # ceph (clôture de stockage) sans --full → RoundtripError → code 2.
        def boom(phase, **kw):
            raise cli._roundtrip.RoundtripError("exiger l'opt-in `--full`")

        orig = cli._roundtrip.run_roundtrip
        cli._roundtrip.run_roundtrip = boom
        self.addCleanup(setattr, cli._roundtrip, "run_roundtrip", orig)
        code, _, err = _capture(["roundtrip", "--phase", "ceph", "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_full_and_yes_flags_passed(self):
        from cluster_topology.roundtrip import RoundtripResult, RoundtripStep

        seen = {}

        def capture(phase, *, allow_full=False, assume_yes=False):
            seen["full"] = allow_full
            seen["yes"] = assume_yes
            return RoundtripResult(phase=phase, layers=[phase], steps=[RoundtripStep("x", True)])

        orig = cli._roundtrip.run_roundtrip
        cli._roundtrip.run_roundtrip = capture
        self.addCleanup(setattr, cli._roundtrip, "run_roundtrip", orig)
        _capture(["roundtrip", "--phase", "ceph", "--full", "--yes"])
        self.assertTrue(seen["full"])
        self.assertTrue(seen["yes"])

    def test_unknown_phase_is_argparse_usage(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["roundtrip", "--phase", "frobnicate"])
        self.assertEqual(ctx.exception.code, 2)  # choices argparse

    def test_phase_required(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["roundtrip"])
        self.assertEqual(ctx.exception.code, 2)


class Dispatch(unittest.TestCase):
    def test_unknown_command_is_usage(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["frobnicate"])
        self.assertEqual(ctx.exception.code, 2)  # argparse usage

    def test_no_command_is_usage(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main([])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
