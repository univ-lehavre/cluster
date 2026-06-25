"""Tests des sondes/fonctions pures HA (nestor/ha_probes.py).

Migrés de l'ex-tests/test_ha.py après la fusion de nestor/ha.py : la mécanique de
promotion est partie dans path.py (cf. tests/test_path.py), les gates dans gates.py
(cf. tests/test_gates.py), et les FONCTIONS PURES + SONDES I/O dans ha_probes.py —
testées ici.

Pur/injecté : `vm_exec` (limactl/crictl) est stubé — AUCUN banc, AUCUN cluster. On
valide le faisceau `-e` (subtilité cluster-api↔VIP), la classification etcd, l'ordre
de join, et le câblage `crictl exec` (etcdctl DANS le conteneur, sans sh -c).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import ha_probes  # noqa: E402


class PureFunctions(unittest.TestCase):
    def test_cp_join_order_excludes_primary(self):
        self.assertEqual(ha_probes.cp_join_order(["cp1", "cp2", "cp3"]), ["cp2", "cp3"])

    def test_cp_join_order_single_is_empty(self):
        self.assertEqual(ha_probes.cp_join_order(["cp1"]), [])

    def test_etcd_all_healthy_ok(self):
        out = "https://a:2379 is healthy\nhttps://b:2379 is healthy"
        self.assertEqual(ha_probes.classify_etcd_health(out, 2)[0], "ok")

    def test_etcd_one_unhealthy_fail(self):
        out = "https://a:2379 is healthy\nhttps://b:2379 is unhealthy"
        statut, msg = ha_probes.classify_etcd_health(out, 2)
        self.assertEqual(statut, "fail")
        self.assertIn("DÉGRADÉ", msg)

    def test_etcd_empty_skip(self):
        self.assertEqual(ha_probes.classify_etcd_health("", 2)[0], "skip")

    def test_etcd_incomplete_skip(self):
        self.assertEqual(ha_probes.classify_etcd_health("https://a:2379 is healthy", 2)[0], "skip")

    def test_bootstrap_extravars_endpoint_is_hostname_not_vip(self):
        # Le bug clé : l'endpoint reste le HOSTNAME, la VIP va dans host_ip/vip ;
        # l'advertiseAddress (control_plane_ip) est l'IP RÉELLE du nœud.
        ev = ha_probes.bootstrap_extravars("10.0.0.1", "10.0.0.40", "eth0")
        self.assertEqual(ev["control_plane_endpoint"], "cluster-api")
        self.assertEqual(ev["control_plane_host_ip"], "10.0.0.40")
        self.assertEqual(ev["control_plane_ip"], "10.0.0.1")  # advertise = nœud réel
        self.assertEqual(ev["control_plane_vip"], "10.0.0.40")

    def test_join_extravars_has_vip_for_gate(self):
        ev = ha_probes.join_extravars("10.0.0.40", "eth0")
        self.assertEqual(ev["control_plane_endpoint"], "cluster-api")
        self.assertEqual(ev["control_plane_vip"], "10.0.0.40")


class EtcdHealthWiring(unittest.TestCase):
    """etcdctl n'est PAS sur l'hôte : etcd_health_output passe par `crictl exec`
    dans le conteneur etcd (DIRECTEMENT, sans sh -c). On stub vm_exec."""

    class _Res:
        def __init__(self, stdout="", stderr=""):
            self.stdout, self.stderr, self.returncode = stdout, stderr, 0

    def test_resolves_cid_then_exec_etcdctl(self):
        calls = []

        def vm_exec(cp, command):
            calls.append(command)
            if command[:3] == ["sudo", "crictl", "ps"]:
                return self._Res(stdout="ETCDCID123\n")  # le CID
            return self._Res(stdout="https://a:2379 is healthy")  # le crictl exec

        out = ha_probes.etcd_health_output("cp1", vm_exec=vm_exec)
        self.assertIn("is healthy", out)
        # 2e appel = crictl exec <cid> etcdctl … endpoint health (PAS de sh -c).
        exec_call = calls[1]
        self.assertEqual(exec_call[:4], ["sudo", "crictl", "exec", "ETCDCID123"])
        self.assertEqual(exec_call[4], "etcdctl")
        self.assertNotIn("sh", exec_call)

    def test_no_etcd_container_returns_empty(self):
        # CP sans conteneur etcd (pas encore sain) → sortie vide → gate patiente.
        out = ha_probes.etcd_health_output("cp1", vm_exec=lambda *_a: self._Res(stdout=""))
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
