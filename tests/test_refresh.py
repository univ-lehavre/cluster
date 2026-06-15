"""Tests du module PUR d'état réel (cluster_topology/refresh.py).

unittest stdlib, fixtures pures (listes de nœuds déclarés / VMs réelles / nœuds
Ready) — aucun subprocess. Vérifie la classification présente/orpheline/manquante
et les verdicts must_destroy_first / is_empty.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.refresh import classify_refresh  # noqa: E402


class ClassifyRefresh(unittest.TestCase):
    def test_present_orphan_missing_split(self):
        # stack déclare node1,node2 ; le réel a node1 (présente) + cpX (orphelines).
        st = classify_refresh("s", ["node1", "node2"], ["node1", "cp1", "cp2"], ["node1"])
        self.assertEqual(st.vms_present, ["node1"])
        self.assertEqual(st.vms_orphan, ["cp1", "cp2"])  # réelles mais hors stack
        self.assertEqual(st.vms_missing, ["node2"])  # déclarée, pas de VM
        self.assertEqual(st.nodes_ready, ["node1"])

    def test_orphans_trigger_must_destroy_first(self):
        st = classify_refresh("s", ["node1"], ["cp1", "cp2", "cp3"], [])
        self.assertTrue(st.must_destroy_first)
        self.assertFalse(st.is_empty)  # il y a des VMs (orphelines)

    def test_empty_terrain(self):
        st = classify_refresh("s", ["node1", "node2"], [], [])
        self.assertTrue(st.is_empty)
        self.assertFalse(st.must_destroy_first)
        self.assertEqual(st.vms_missing, ["node1", "node2"])  # tout à créer

    def test_all_present_no_orphan(self):
        # Le réel correspond exactement à la déclaration → ni orphelin ni manquant.
        st = classify_refresh("ha", ["cp1", "cp2", "cp3"], ["cp1", "cp2", "cp3"], ["cp1"])
        self.assertEqual(st.vms_present, ["cp1", "cp2", "cp3"])
        self.assertEqual(st.vms_orphan, [])
        self.assertEqual(st.vms_missing, [])
        self.assertFalse(st.must_destroy_first)

    def test_order_follows_inputs(self):
        # L'ordre des listes suit l'ordre d'entrée (déterminisme de l'affichage).
        st = classify_refresh("s", ["a", "b"], ["b", "a"], [])
        self.assertEqual(st.vms_present, ["b", "a"])  # ordre du réel


if __name__ == "__main__":
    unittest.main()
