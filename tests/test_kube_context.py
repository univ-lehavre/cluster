"""Tests des contextes kubectl nommés (nestor/kube_context.py) — LOT 8 refonte nestor.

unittest stdlib, kubectl TOTALEMENT STUBÉ (runner injecté) — AUCUN kubectl réel, AUCUN
cluster, AUCUN `~/.kube/config` touché. Ce module REMPLACE `nestor env` (ADR 0097 §3) :
on prouve la LOGIQUE PURE (quel contexte poser, quel argv `set-context`) et l'I/O isolée
(refus si kubeconfig absent / kubectl en échec).
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import kube_context as kc  # noqa: E402

_BENCH = "/some/bench/.work/kubeconfig"


def _proc(returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=["kubectl"], returncode=returncode, stderr=stderr)


class Plan(unittest.TestCase):
    """context_plan : décide CE QU'IL FAUT poser, PUR (pas d'I/O)."""

    def test_lima_targets_bench_kubeconfig(self):
        plan = kc.context_plan(
            "banc", kubeconfig=None, target_kind="bench", bench_kubeconfig=_BENCH
        )
        self.assertEqual(plan.name, "banc")
        self.assertEqual(plan.kubeconfig, _BENCH)
        self.assertEqual(plan.cluster, "banc")
        self.assertEqual(plan.user, "banc-admin")

    def test_prod_targets_declared_kubeconfig_expanded(self):
        plan = kc.context_plan(
            "dirqual",
            kubeconfig="~/.kube/dirqual.config",
            target_kind="prod",
            bench_kubeconfig=_BENCH,
        )
        self.assertEqual(plan.kubeconfig, os.path.expanduser("~/.kube/dirqual.config"))
        self.assertNotIn("~", plan.kubeconfig)

    def test_prod_without_kubeconfig_raises(self):
        with self.assertRaises(kc.ContextError):
            kc.context_plan("dirqual", kubeconfig=None, target_kind="prod", bench_kubeconfig=_BENCH)

    def test_set_context_argv_is_idempotent_set_context(self):
        plan = kc.context_plan(
            "banc", kubeconfig=None, target_kind="bench", bench_kubeconfig=_BENCH
        )
        argv = plan.set_context_argv()
        self.assertEqual(argv[:3], ["kubectl", "config", "set-context"])
        self.assertIn("banc", argv)
        self.assertIn("--cluster=banc", argv)
        self.assertIn("--user=banc-admin", argv)
        self.assertIn(f"--kubeconfig={_BENCH}", argv)


class Apply(unittest.TestCase):
    """apply_context : I/O isolée, kubectl STUBÉ (jamais réel)."""

    def setUp(self):
        # Un kubeconfig source qui EXISTE (apply refuse un fichier absent).
        fd, self.kubeconfig = tempfile.mkstemp(suffix=".config")
        os.close(fd)
        self.addCleanup(os.unlink, self.kubeconfig)

    def _plan(self):
        return kc.ContextPlan(
            name="banc", kubeconfig=self.kubeconfig, cluster="banc", user="banc-admin"
        )

    def test_apply_invokes_runner_with_set_context(self):
        calls = []

        def runner(argv):
            calls.append(argv)
            return _proc(0)

        name = kc.apply_context(self._plan(), runner=runner)
        self.assertEqual(name, "banc")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], ["kubectl", "config", "set-context"])

    def test_apply_refuses_absent_kubeconfig(self):
        plan = kc.ContextPlan(
            name="banc", kubeconfig="/does/not/exist", cluster="banc", user="banc-admin"
        )
        called = []
        with self.assertRaises(kc.ContextError):
            kc.apply_context(plan, runner=lambda argv: called.append(argv) or _proc(0))
        self.assertEqual(called, [])  # kubectl jamais appelé sur une cible absente

    def test_apply_raises_on_kubectl_failure(self):
        with self.assertRaises(kc.ContextError):
            kc.apply_context(self._plan(), runner=lambda argv: _proc(1, "boom"))

    def test_devnull_kubeconfig_allowed(self):
        # /dev/null (banc non monté placeholder) ne déclenche PAS le refus « absent ».
        plan = kc.ContextPlan(name="banc", kubeconfig=os.devnull, cluster="banc", user="banc-admin")
        name = kc.apply_context(plan, runner=lambda argv: _proc(0))
        self.assertEqual(name, "banc")


if __name__ == "__main__":
    unittest.main()
