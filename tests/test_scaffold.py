"""Tests du module PUR de création de topologie (nestor/scaffold.py).

unittest stdlib, fixtures pures (nom + réponses en dict) — aucun subprocess, aucune
I/O. Vérifie les garde-fous du nom (anti `.example`, anti traversée), la construction
d'un dict MINIMAL et VALIDE (qui passe load_topology), et l'insertion du LB en HA.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.model import load_topology, topology_from_dict  # noqa: E402
from nestor.scaffold import (  # noqa: E402
    ScaffoldError,
    build_topology_dict,
    plan_init,
    validate_name,
)


class ValidateName(unittest.TestCase):
    def test_simple_name_ok(self):
        self.assertEqual(validate_name("ha-prod"), "ha-prod")

    def test_strips_whitespace(self):
        self.assertEqual(validate_name("  site-a  "), "site-a")

    def test_empty_rejected(self):
        with self.assertRaises(ScaffoldError):
            validate_name("   ")

    def test_path_traversal_rejected(self):
        for bad in ["../etc/passwd", "a/b", "a\\b", ".."]:
            with self.assertRaises(ScaffoldError):
                validate_name(bad)

    def test_example_suffix_rejected(self):
        # Un `.example` serait VERSIONNÉ (anti ADR 0023) ; init crée une topo réelle.
        for bad in ["ha-prod.example", "ha.example.yaml", "x.yaml", "x.yml"]:
            with self.assertRaises(ScaffoldError):
                validate_name(bad)


class PlanInit(unittest.TestCase):
    def test_target_is_real_gitignored_path(self):
        plan = plan_init("ha-prod", activate=True)
        self.assertEqual(plan.name, "ha-prod")
        self.assertEqual(plan.target, "topologies/ha-prod.yaml")  # réel, pas .example
        self.assertTrue(plan.activate)

    def test_invalid_name_raises(self):
        with self.assertRaises(ScaffoldError):
            plan_init("x.example", activate=False)


class BuildTopologyDict(unittest.TestCase):
    def _answers(self, **over):
        base = {
            "profile": "base",
            "backend": "local-path",
            "terrain": "local",
            "target_kind": "bench",
            "control_planes": "1",
            "workers": "2",
        }
        base.update(over)
        return base

    def test_mono_cp_is_valid(self):
        data = build_topology_dict("mono", self._answers())
        # Le dict construit passe la validation de schéma du modèle (réutilisée).
        topo = topology_from_dict(data)
        self.assertEqual(len(topo.control_nodes), 1)
        self.assertEqual(len(topo.worker_nodes), 2)
        self.assertFalse(topo.is_ha_control_plane)
        self.assertEqual(data["catalog"]["topology"], "mono")
        self.assertEqual(data["catalog"]["status"], "cible")  # honnêteté ADR 0052

    def test_ha_inserts_control_plane_lb(self):
        data = build_topology_dict(
            "ha", self._answers(control_planes="3", workers="0", lb_mode="kube-vip-arp")
        )
        topo = topology_from_dict(data)  # > 1 CP sans LB lèverait TopologyError
        self.assertTrue(topo.is_ha_control_plane)
        self.assertEqual(data["network"]["control_plane_lb"]["mode"], "kube-vip-arp")
        self.assertEqual(len(topo.control_nodes), 3)

    def test_ha_default_lb_mode_when_absent(self):
        # control_planes ≥ 2 sans lb_mode explicite → défaut kube-vip-arp (toujours valide).
        data = build_topology_dict("ha", self._answers(control_planes="2"))
        self.assertEqual(data["network"]["control_plane_lb"]["mode"], "kube-vip-arp")

    def test_backend_drives_nothing_extra_but_is_recorded(self):
        data = build_topology_dict("c", self._answers(backend="ceph"))
        self.assertEqual(data["storage"]["backend"], "ceph")

    def test_profile_out_of_enum_rejected(self):
        with self.assertRaises(ScaffoldError):
            build_topology_dict("x", self._answers(profile="frobnicate"))

    def test_backend_out_of_enum_rejected(self):
        with self.assertRaises(ScaffoldError):
            build_topology_dict("x", self._answers(backend="nfs"))

    def test_zero_control_plane_rejected(self):
        with self.assertRaises(ScaffoldError):
            build_topology_dict("x", self._answers(control_planes="0"))

    def test_non_integer_count_rejected(self):
        with self.assertRaises(ScaffoldError):
            build_topology_dict("x", self._answers(workers="deux"))


class WrittenFileRoundtrips(unittest.TestCase):
    """Le dict → YAML → load_topology doit tenir (preuve que init produit du valide)."""

    def test_dict_yaml_loads_back(self):
        import tempfile

        import yaml

        data = build_topology_dict(
            "rt",
            {
                "profile": "dataops",
                "backend": "ceph",
                "terrain": "baremetal",
                "target_kind": "prod",
                "control_planes": "1",
                "workers": "3",
            },
        )
        fd, path = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
            topo = load_topology(path)
            self.assertEqual(topo.catalog["profile"], "dataops")
            self.assertEqual(topo.storage["backend"], "ceph")
            self.assertEqual(topo.target_kind, "prod")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
