"""Tests de la façade CLI de l'outil déclaratif (scripts/topology.py, ADR 0056 P3).

unittest stdlib (lancé par `pnpm test:python` = unittest discover -s tests). La
CLI est conçue ARGV-INJECTABLE (`main(argv)`) : on appelle `main([...])` et on
asserte la valeur de RETOUR (code de sortie) + la sortie capturée, SANS subprocess
(rapide, pur). La logique métier est déjà testée dans test_cluster_topology.py ;
ici on couvre la façade : dispatch, codes de sortie, mapping des exceptions,
garde-fou byte-identique de `diff`.
"""

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_ROOT = os.path.join(os.path.dirname(__file__), "..")

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
