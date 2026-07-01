"""Tests de la consignation d'un run (nestor/runrecord.py, #216) — PURS (subprocess/I-O
stubés ou fichiers temporaires). Aucun cluster, aucun git réel exigé."""

import datetime as dt
import os
import subprocess
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.path import PathResult, PathStep  # noqa: E402
from nestor.runrecord import (  # noqa: E402
    append_run,
    build_run_entry,
    format_entry,
    git_revision,
    host_model,
)


def _fake_run(mapping):
    """Fabrique un `run` stub : `mapping[tuple(args_après_git)]` = (returncode, stdout)."""

    def run(argv, **k):
        key = tuple(argv[1:]) if argv and argv[0] == "git" else tuple(argv)
        rc, out = mapping.get(key, (1, ""))
        return subprocess.CompletedProcess(args=argv, returncode=rc, stdout=out, stderr="")

    return run


class GitRevision(unittest.TestCase):
    def test_clean_tree(self):
        run = _fake_run(
            {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "main\n"),
                ("rev-parse", "--short", "HEAD"): (0, "abc1234\n"),
                ("status", "--porcelain"): (0, ""),  # arbre propre
            }
        )
        self.assertEqual(git_revision(".", run=run), ("main", "abc1234"))

    def test_dirty_tree_suffixes_commit(self):
        run = _fake_run(
            {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "feat/x\n"),
                ("rev-parse", "--short", "HEAD"): (0, "abc1234\n"),
                ("status", "--porcelain"): (0, " M nestor/x.py\n"),  # arbre sale
            }
        )
        self.assertEqual(git_revision(".", run=run), ("feat/x", "abc1234-dirty"))

    def test_not_a_repo_returns_none(self):
        run = _fake_run({})  # tout échoue (rc=1)
        self.assertEqual(git_revision(".", run=run), (None, None))

    def test_git_absent_returns_none(self):
        def run(argv, **k):
            raise OSError("git introuvable")

        self.assertEqual(git_revision(".", run=run), (None, None))


class HostModel(unittest.TestCase):
    def test_macos_model_is_generic(self):
        def run(argv, **k):
            if argv[:3] == ["sysctl", "-n", "hw.model"]:
                return subprocess.CompletedProcess(argv, 0, stdout="Mac15,9\n", stderr="")
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

        self.assertEqual(host_model(run=run), "Mac15,9")

    def test_sysctl_absent_falls_back_to_arch(self):
        def run(argv, **k):
            raise OSError("sysctl absent")

        # fallback = platform.machine() (arch générique, non vide)
        self.assertTrue(host_model(run=run))


class BuildEntry(unittest.TestCase):
    def _result(self):
        return PathResult(
            target="atlas",
            steps=[
                PathStep("up", True, "rc=0", duration_s=45.4),
                PathStep("up (gate)", True, "sain"),  # gate : PAS de durée consignée
                PathStep("bootstrap", True, "rc=0", duration_s=300.0),
                PathStep("bootstrap (gate)", True, "sain"),
                PathStep("metrics-server", True, "ok", duration_s=5.0),
            ],
        )

    def test_phases_exclude_gates_and_round(self):
        entry = build_run_entry(
            self._result(),
            topologie="banc",
            profil="dataops",
            now=dt.datetime(2026, 7, 1, 15, 30, tzinfo=dt.UTC),
            branche="b",
            commit="c",
            arch="arm64",
            hote="Mac15,9",
        )
        # gates exclues ; durées arrondies ; total = somme.
        self.assertEqual(entry["phases"], {"up": 45, "bootstrap": 300, "metrics-server": 5})
        self.assertEqual(entry["total_s"], 350)
        self.assertNotIn("up (gate)", entry["phases"])

    def test_id_and_commit_and_no_metrics(self):
        entry = build_run_entry(
            self._result(),
            topologie="banc",
            profil="dataops",
            now=dt.datetime(2026, 7, 1, 15, 30, tzinfo=dt.UTC),
            branche="b",
            commit="abc1234-dirty",
            arch="arm64",
            hote="Mac15,9",
        )
        self.assertEqual(entry["id"], "2026-07-01T15-dataops-abc1234-dirty")
        self.assertEqual(entry["commit"], "abc1234-dirty")  # traçabilité du SHA (+ dirty)
        self.assertEqual(entry["target"], "atlas")
        self.assertNotIn("metriques", entry)  # OMISES honnêtement (monitoring absent au run)


class WriterBytesStable(unittest.TestCase):
    def test_append_preserves_existing_dates_byte_for_byte(self):
        # RÉGRESSION : un `safe_dump` global re-sérialisait les dates parsées en datetime
        # (`…Z` → `… +00:00`) et ré-indentait tout. L'append TEXTE préserve l'existant.
        existing = (
            "runs:\n"
            "  - id: old\n"
            "    date: 2026-06-01T00:00:00Z\n"
            "    commit: abc1234\n"
            "    phases:\n"
            "      up: 100\n"
        )
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.write(fd, existing.encode())
        os.close(fd)
        self.addCleanup(os.unlink, path)
        append_run(path, {"id": "new", "date": "2026-07-01T15:00:00Z", "phases": {"ceph": 50}})
        with open(path, encoding="utf-8") as _f:
            out = _f.read()
        # la date existante NON corrompue (pas de ' +00:00'), toujours '…Z'
        self.assertIn("date: 2026-06-01T00:00:00Z", out)
        # se recharge en YAML valide, 2 runs
        data = yaml.safe_load(out)
        self.assertEqual([r["id"] for r in data["runs"]], ["old", "new"])

    def test_new_entry_indented_like_file(self):
        # l'entrée est indentée de 2 espaces (`  - id:`), style du fichier.
        text = format_entry({"id": "x", "phases": {"up": 10}})
        self.assertTrue(text.startswith("  - id: x\n"))
        self.assertIn("    phases:\n", text)

    def test_creates_runs_header_when_absent(self):
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)
        os.unlink(path)  # fichier absent
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        append_run(path, {"id": "first", "phases": {}})
        with open(path, encoding="utf-8") as _f:
            out = _f.read()
        self.assertTrue(out.startswith("runs:\n"))
        self.assertEqual([r["id"] for r in yaml.safe_load(out)["runs"]], ["first"])


if __name__ == "__main__":
    unittest.main()
