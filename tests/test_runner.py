"""Tests de la couche d'exécution (nestor/runner.py, P5).

On _stubbe_ l'indirection `_runner_run` (qui wrappe ansible_runner.run) : aucun
play réel, aucun SSH, aucun cluster en CI. On vérifie le mapping rc/status et que
les envvars (ANSIBLE_CONFIG/KUBECONFIG/EXPECTED_TARGET_KIND) + l'inventaire fourni
sont bien passés (pas l'ambiant).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import runner  # noqa: E402


class _FakeRun:
    def __init__(self, rc, status, stats=None):
        self.rc = rc
        self.status = status
        self.stats = stats  # {'changed': {host: n}, …} ou None (échec avant recap)


class LaunchPhase(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake(**kwargs):
            self.calls.append(kwargs)
            return _FakeRun(0, "successful")

        self._orig = runner._runner_run
        runner._runner_run = fake
        self.addCleanup(setattr, runner, "_runner_run", self._orig)

    def test_maps_rc_and_status(self):
        res = runner.launch_phase("bootstrap/dataops.yaml", {"k": "v"}, "/data", "/data/inv.yaml")
        self.assertEqual(res.rc, 0)
        self.assertEqual(res.status, "successful")

    def test_passes_inventory_and_extravars(self):
        runner.launch_phase("bootstrap/monitoring.yaml", {"sc": "ceph"}, "/d", "/d/inv")
        call = self.calls[0]
        self.assertEqual(call["playbook"], "bootstrap/monitoring.yaml")
        self.assertEqual(call["inventory"], "/d/inv")
        self.assertEqual(call["extravars"], {"sc": "ceph"})
        self.assertEqual(call["private_data_dir"], "/d")

    def test_envvars_set_when_provided(self):
        runner.launch_phase(
            "bootstrap/ceph-cluster.yaml",
            {},
            "/d",
            "/d/inv",
            ansible_config="/d/project/bootstrap/ansible.cfg",
            kubeconfig="/home/u/.kube/config",
            target_kind="lima",
        )
        env = self.calls[0]["envvars"]
        self.assertEqual(env["EXPECTED_TARGET_KIND"], "lima")
        self.assertEqual(env["ANSIBLE_CONFIG"], "/d/project/bootstrap/ansible.cfg")
        self.assertEqual(env["KUBECONFIG"], "/home/u/.kube/config")

    def test_failed_status_propagates(self):
        runner._runner_run = lambda **k: _FakeRun(2, "failed")
        res = runner.launch_phase("bootstrap/dataops.yaml", {}, "/d", "/d/inv")
        self.assertEqual(res.rc, 2)
        self.assertEqual(res.status, "failed")

    def test_changed_read_from_stats(self):
        runner._runner_run = lambda **k: _FakeRun(0, "successful", {"changed": {"localhost": 3}})
        res = runner.launch_phase("bootstrap/dataops.yaml", {}, "/d", "/d/inv")
        self.assertEqual(res.changed, 3)


class PurgeRunnerEnv(unittest.TestCase):
    """Anti-contamination : les env/* d'un run précédent sont purgés avant le suivant."""

    def test_removes_residual_extravars(self):
        import tempfile

        pdd = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(pdd, ignore_errors=True))
        env = os.path.join(pdd, "env")
        os.makedirs(env)
        # Résidu d'un run HA : extravars avec la VIP.
        with open(os.path.join(env, "extravars"), "w", encoding="utf-8") as f:
            f.write('{"control_plane_host_ip": "192.168.104.40"}')
        with open(os.path.join(env, "cmdline"), "w", encoding="utf-8") as f:
            f.write("--syntax-check")
        runner._purge_runner_env(pdd)
        self.assertFalse(os.path.exists(os.path.join(env, "extravars")))
        self.assertFalse(os.path.exists(os.path.join(env, "cmdline")))

    def test_no_env_dir_is_noop(self):
        import tempfile

        pdd = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(pdd, ignore_errors=True))
        # Pas de dossier env/ → ne lève pas.
        runner._purge_runner_env(pdd)

    def test_launch_phase_purges_before_run(self):
        # launch_phase purge AVANT de lancer : un extravars résiduel ne survit pas.
        import tempfile

        pdd = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(pdd, ignore_errors=True))
        env = os.path.join(pdd, "env")
        os.makedirs(env)
        residual = os.path.join(env, "extravars")
        with open(residual, "w", encoding="utf-8") as f:
            f.write('{"vip": "old"}')
        orig = runner._runner_run
        runner._runner_run = lambda **k: _FakeRun(0, "successful")
        self.addCleanup(setattr, runner, "_runner_run", orig)
        runner.launch_phase("p.yaml", {"control_plane_ip": "10.0.0.3"}, pdd, "/inv")
        self.assertFalse(os.path.exists(residual))  # purgé avant le run


class ClassifyIdempotence(unittest.TestCase):
    """Portage fidèle de dataops-assert.sh:classify_idempotence (3 cas)."""

    def test_zero_is_ok(self):
        self.assertEqual(runner.classify_idempotence(0)[0], "ok")

    def test_none_is_skip(self):
        self.assertEqual(runner.classify_idempotence(None)[0], "skip")

    def test_positive_is_fail(self):
        verdict, msg = runner.classify_idempotence(2)
        self.assertEqual(verdict, "fail")
        self.assertIn("2 tâche", msg)


class StatsChanged(unittest.TestCase):
    def test_sums_over_hosts(self):
        self.assertEqual(runner._stats_changed(_FakeRun(0, "ok", {"changed": {"a": 2, "b": 3}})), 5)

    def test_no_stats_is_none(self):
        self.assertIsNone(runner._stats_changed(_FakeRun(0, "ok", None)))

    def test_no_changed_key_is_none(self):
        self.assertIsNone(runner._stats_changed(_FakeRun(0, "ok", {"ok": {"a": 1}})))


class LaunchPhaseIdempotent(unittest.TestCase):
    """Double-passage : déploie + rejeu prouvant changed=0 (ADR 0052)."""

    def _stub(self, results):
        # results : liste de _FakeRun renvoyés successivement (1 par appel).
        seq = iter(results)
        orig = runner._runner_run
        runner._runner_run = lambda **k: next(seq)
        self.addCleanup(setattr, runner, "_runner_run", orig)

    def test_deploy_then_replay_clean_is_ok(self):
        # 1er run déploie (changed=5), 2e rejeu propre (changed=0) → ok.
        self._stub(
            [
                _FakeRun(0, "successful", {"changed": {"h": 5}}),
                _FakeRun(0, "successful", {"changed": {"h": 0}}),
            ]
        )
        res = runner.launch_phase_idempotent("bootstrap/ceph-cluster.yaml", {}, "/d", "/d/inv")
        self.assertTrue(res.ok)
        self.assertEqual(res.verdict, "ok")

    def test_replay_changed_is_fail(self):
        # Rejeu avec changed>0 → idempotence cassée.
        self._stub(
            [
                _FakeRun(0, "successful", {"changed": {"h": 5}}),
                _FakeRun(0, "successful", {"changed": {"h": 2}}),
            ]
        )
        res = runner.launch_phase_idempotent("bootstrap/sc.yaml", {}, "/d", "/d/inv")
        self.assertEqual(res.verdict, "fail")
        self.assertIn("CASSÉE", res.message)

    def test_deploy_failure_skips_replay(self):
        # 1er run échoue (rc≠0) → pas de rejeu (replayed None), verdict fail.
        calls = []

        def fake(**k):
            calls.append(1)
            return _FakeRun(2, "failed")

        orig = runner._runner_run
        runner._runner_run = fake
        self.addCleanup(setattr, runner, "_runner_run", orig)
        res = runner.launch_phase_idempotent("bootstrap/datalake.yaml", {}, "/d", "/d/inv")
        self.assertEqual(res.verdict, "fail")
        self.assertIsNone(res.replayed)
        self.assertEqual(calls, [1])  # UN seul run (pas de rejeu)

    def test_unreadable_stats_is_skip(self):
        # Rejeu sans stats lisibles → skip (non mesuré), pas fail.
        self._stub(
            [
                _FakeRun(0, "successful", {"changed": {"h": 1}}),
                _FakeRun(0, "successful", None),
            ]
        )
        res = runner.launch_phase_idempotent("bootstrap/local-path.yaml", {}, "/d", "/d/inv")
        self.assertEqual(res.verdict, "skip")


if __name__ == "__main__":
    unittest.main()
