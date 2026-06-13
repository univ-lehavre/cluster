"""Tests de la couche d'exécution (cluster_topology/runner.py, P5).

On _stubbe_ l'indirection `_runner_run` (qui wrappe ansible_runner.run) : aucun
play réel, aucun SSH, aucun cluster en CI. On vérifie le mapping rc/status et que
les envvars (ANSIBLE_CONFIG/KUBECONFIG/EXPECTED_TARGET_KIND) + l'inventaire fourni
sont bien passés (pas l'ambiant).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology import runner  # noqa: E402


class _FakeRun:
    def __init__(self, rc, status):
        self.rc = rc
        self.status = status


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


if __name__ == "__main__":
    unittest.main()
