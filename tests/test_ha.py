"""Tests de l'orchestration ha-3cp (cluster_topology/ha.py).

Pur/injecté : `launch` (← runner.launch_phase), `run_cni`, les gates et `sleep`
sont stubés — AUCUN banc, AUCUN cluster, AUCUN ansible-runner réel. On valide la
SÉQUENCE des playbooks, l'ordre des gates (etcd AVANT chaque promotion), le
faisceau `-e` (subtilité cluster-api↔VIP), et les échecs.

La PREUVE réelle (VIP qui bascule, survie à 1 panne) reste un run de banc consigné
(ADR 0034/0052, #250) — ces tests prouvent la LOGIQUE d'orchestration, pas le banc.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology import ha  # noqa: E402


class PureFunctions(unittest.TestCase):
    def test_cp_join_order_excludes_primary(self):
        self.assertEqual(ha.cp_join_order(["cp1", "cp2", "cp3"]), ["cp2", "cp3"])

    def test_cp_join_order_single_is_empty(self):
        self.assertEqual(ha.cp_join_order(["cp1"]), [])

    def test_etcd_all_healthy_ok(self):
        out = "https://a:2379 is healthy\nhttps://b:2379 is healthy"
        self.assertEqual(ha.classify_etcd_health(out, 2)[0], "ok")

    def test_etcd_one_unhealthy_fail(self):
        out = "https://a:2379 is healthy\nhttps://b:2379 is unhealthy"
        statut, msg = ha.classify_etcd_health(out, 2)
        self.assertEqual(statut, "fail")
        self.assertIn("DÉGRADÉ", msg)

    def test_etcd_empty_skip(self):
        self.assertEqual(ha.classify_etcd_health("", 2)[0], "skip")

    def test_etcd_incomplete_skip(self):
        self.assertEqual(ha.classify_etcd_health("https://a:2379 is healthy", 2)[0], "skip")

    def test_bootstrap_extravars_endpoint_is_hostname_not_vip(self):
        # Le bug clé : l'endpoint reste le HOSTNAME, la VIP va dans host_ip/vip ;
        # l'advertiseAddress (control_plane_ip) est l'IP RÉELLE du nœud.
        ev = ha.bootstrap_extravars("10.0.0.1", "10.0.0.40", "eth0")
        self.assertEqual(ev["control_plane_endpoint"], "cluster-api")
        self.assertEqual(ev["control_plane_host_ip"], "10.0.0.40")
        self.assertEqual(ev["control_plane_ip"], "10.0.0.1")  # advertise = nœud réel
        self.assertEqual(ev["control_plane_vip"], "10.0.0.40")

    def test_join_extravars_has_vip_for_gate(self):
        ev = ha.join_extravars("10.0.0.40", "eth0")
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

        out = ha.etcd_health_output("cp1", vm_exec=vm_exec)
        self.assertIn("is healthy", out)
        # 2e appel = crictl exec <cid> etcdctl … endpoint health (PAS de sh -c).
        exec_call = calls[1]
        self.assertEqual(exec_call[:4], ["sudo", "crictl", "exec", "ETCDCID123"])
        self.assertEqual(exec_call[4], "etcdctl")
        self.assertNotIn("sh", exec_call)

    def test_no_etcd_container_returns_empty(self):
        # CP sans conteneur etcd (pas encore sain) → sortie vide → gate patiente.
        out = ha.etcd_health_output("cp1", vm_exec=lambda *_a: self._Res(stdout=""))
        self.assertEqual(out, "")


class _Launch:
    """Stub de launch_phase : enregistre les (playbook, kubeconfig_path) lancés ;
    renvoie un succès, ou un échec ciblé sur un playbook donné."""

    class _Res:
        def __init__(self, rc, status):
            self.rc = rc
            self.status = status

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, playbook, extravars):
        self.calls.append((playbook, extravars.get("kube_vip_kubeconfig_path")))
        if self.fail_on and playbook == self.fail_on:
            return self._Res(1, "failed")
        return self._Res(0, "successful")


def _noop(*_a, **_k):
    return None


class BootstrapPrimary(unittest.TestCase):
    def _run(self, launch, **over):
        kw = dict(
            launch=launch,
            run_cni=_noop,
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 1,
            sleep=_noop,
        )
        kw.update(over)
        return ha.bootstrap_primary("10.0.0.1", "10.0.0.40", "eth0", **kw)

    def test_sequence_order_and_kube_vip_pivot(self):
        launch = _Launch()
        self._run(launch)
        playbooks = [p for p, _ in launch.calls]
        # Ordre prouvé : pré-init → kube-vip(super-admin) → init → kube-vip(admin).
        self.assertEqual(
            playbooks,
            [
                "checks.yaml",
                "cri.yaml",
                "kubeadm.yaml",
                "control-planes.yaml",
                "kube-vip.yaml",
                "initialisation.yaml",
                "kube-vip.yaml",
            ],
        )
        # La bascule super-admin → admin (le piège k8s ≥ 1.29).
        kube_vip_confs = [c for p, c in launch.calls if p == "kube-vip.yaml"]
        self.assertEqual(
            kube_vip_confs,
            ["/etc/kubernetes/super-admin.conf", "/etc/kubernetes/admin.conf"],
        )

    def test_init_failure_raises(self):
        with self.assertRaises(ha.HaError):
            self._run(_Launch(fail_on="initialisation.yaml"))

    def test_vip_gate_failure_raises(self):
        with self.assertRaises(ha.HaError):
            self._run(_Launch(), vip_responds=lambda *_a, **_k: False)


class RunHa3cp(unittest.TestCase):
    def _etcd_healthy(self, n):
        return lambda _cp: "\n".join("x is healthy" for _ in range(n))

    def test_full_build_promotes_two_cps_with_etcd_gates(self):
        launch = _Launch()
        # ready_count croît : assez pour passer toutes les gates.
        res = ha.run_ha_3cp(
            ["cp1", "cp2", "cp3"],
            "10.0.0.1",
            "10.0.0.40",
            "eth0",
            launch=launch,
            run_cni=_noop,
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 3,
            etcd_output=self._etcd_healthy(3),
            sleep=_noop,
        )
        self.assertTrue(res.built, [s.detail for s in res.steps if not s.ok])
        # Les deux CP additionnels sont promus (join-control-plane lancé 2×).
        joins = [p for p, _ in launch.calls if p == "join-control-plane.yaml"]
        self.assertEqual(len(joins), 2)
        # Étape quorum final présente.
        self.assertTrue(any(s.name == "quorum final" for s in res.steps))

    def test_degraded_etcd_aborts_before_promotion(self):
        launch = _Launch()
        res = ha.run_ha_3cp(
            ["cp1", "cp2", "cp3"],
            "10.0.0.1",
            "10.0.0.40",
            "eth0",
            launch=launch,
            run_cni=_noop,
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 1,
            etcd_output=lambda _cp: "a is healthy\nb is unhealthy",  # quorum dégradé
            sleep=_noop,
        )
        self.assertFalse(res.built)
        # Aucune promotion lancée (la gate etcd a coupé avant).
        joins = [p for p, _ in launch.calls if p == "join-control-plane.yaml"]
        self.assertEqual(joins, [])
        self.assertEqual(res.steps[-1].name, "échec")


if __name__ == "__main__":
    unittest.main()
