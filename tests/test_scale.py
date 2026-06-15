"""Tests de la dérivation de scaling (cluster_topology/scale.py, ADR 0072).

Logique PURE : aucun cluster, aucun kubectl. On vérifie le clamp, le plafond, le
plancher (jamais 0), et le refus des workloads ArgoCD-managés.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.scale import (  # noqa: E402
    SCALABLE_WORKLOADS,
    plan_scale,
    target_replicas,
)


class TargetReplicas(unittest.TestCase):
    def test_linear_under_cap(self):
        self.assertEqual(target_replicas(2, 3), 2)

    def test_capped_at_max(self):
        self.assertEqual(target_replicas(5, 3), 3)

    def test_never_zero(self):
        self.assertEqual(target_replicas(0, 3), 1)  # service jamais coupé

    def test_single_node(self):
        self.assertEqual(target_replicas(1, 3), 1)


class PlanScale(unittest.TestCase):
    def test_one_plan_per_workload(self):
        plans = plan_scale(2)
        self.assertEqual(len(plans), len(SCALABLE_WORKLOADS))
        self.assertTrue(all(p.actionable for p in plans))
        self.assertTrue(all(p.target == 2 for p in plans if p.workload.max_replicas >= 2))

    def test_argocd_managed_is_skipped(self):
        plans = plan_scale(2, argocd_managed=frozenset({"gitea"}))
        gitea = next(p for p in plans if p.workload.name == "gitea")
        self.assertFalse(gitea.actionable)
        self.assertIn("ArgoCD", gitea.skipped)
        # les autres restent actionnables
        others = [p for p in plans if p.workload.name != "gitea"]
        self.assertTrue(all(p.actionable for p in others))

    def test_cap_respected_per_workload(self):
        # mailpit plafonne à 2 ; avec 5 workers Ready il reste à 2.
        plans = plan_scale(5)
        mailpit = next(p for p in plans if p.workload.name == "mailpit")
        self.assertEqual(mailpit.target, 2)

    def test_allowlist_excludes_stateful(self):
        # Garde-fou ADR 0072 : aucun StatefulSet/CNPG/operator dans l'allowlist.
        names = {wl.name for wl in SCALABLE_WORKLOADS}
        self.assertFalse(names & {"loki", "argocd", "pg", "cnpg", "rook-ceph"})


if __name__ == "__main__":
    unittest.main()
