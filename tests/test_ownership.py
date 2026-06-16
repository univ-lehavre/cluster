"""Tests du graphe d'appartenance (nestor/ownership.py, ADR 0079).

Pur : ressources sondées (dicts) → graphe + ordre de teardown. Aucun cluster.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.ownership import (  # noqa: E402
    Resource,
    build_ownership,
    from_probe,
    teardown_order,
)


def _r(kind, name, uid, owners=(), ns="dataops"):
    return Resource(kind=kind, name=name, uid=uid, namespace=ns, owners=tuple(owners))


# Chaîne k8s classique : Deployment → ReplicaSet → Pod (le GC cascade ainsi).
_DEPLOY = _r("Deployment", "dagster", "u-deploy")
_RS = _r("ReplicaSet", "dagster-abc", "u-rs", owners=["u-deploy"])
_POD = _r("Pod", "dagster-abc-1", "u-pod", owners=["u-rs"])


class FromProbe(unittest.TestCase):
    def test_derives_owners_from_ownerReferences(self):
        items = [
            {
                "kind": "Pod",
                "name": "p",
                "uid": "u1",
                "namespace": "x",
                "ownerReferences": [{"kind": "ReplicaSet", "name": "rs", "uid": "u2"}],
            },
        ]
        res = from_probe(items)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].owners, ("u2",))
        self.assertEqual(res[0].ref, "Pod/p")

    def test_item_without_uid_is_skipped(self):
        # sans uid, on ne peut pas situer la ressource → ignorée (façade garantit l'uid).
        self.assertEqual(from_probe([{"kind": "Pod", "name": "p"}]), [])

    def test_no_owner_refs_is_root(self):
        res = from_probe([{"kind": "ConfigMap", "name": "c", "uid": "u9"}])
        self.assertEqual(res[0].owners, ())


class BuildOwnership(unittest.TestCase):
    def test_edges_owner_to_owned(self):
        g = build_ownership([_DEPLOY, _RS, _POD])
        self.assertEqual(g.owned["u-deploy"], ["u-rs"])
        self.assertEqual(g.owned["u-rs"], ["u-pod"])
        self.assertEqual(g.owned["u-pod"], [])

    def test_root_is_owner_without_present_owner(self):
        g = build_ownership([_DEPLOY, _RS, _POD])
        self.assertEqual([r.uid for r in g.roots], ["u-deploy"])

    def test_owner_absent_makes_resource_a_root(self):
        # le Pod référence un RS absent de l'ensemble → le Pod devient une racine.
        g = build_ownership([_POD])  # u-rs pas dans l'ensemble
        self.assertEqual([r.uid for r in g.roots], ["u-pod"])


class TeardownOrder(unittest.TestCase):
    def test_owned_before_owner(self):
        # Pod (le plus profond) avant ReplicaSet avant Deployment.
        order = [r.uid for r in teardown_order([_DEPLOY, _RS, _POD])]
        self.assertEqual(order, ["u-pod", "u-rs", "u-deploy"])

    def test_input_order_irrelevant(self):
        # quel que soit l'ordre d'entrée, l'ordre de teardown suit la profondeur.
        order = [r.uid for r in teardown_order([_POD, _DEPLOY, _RS])]
        self.assertEqual(order, ["u-pod", "u-rs", "u-deploy"])

    def test_independent_roots_keep_stable_order(self):
        a = _r("Service", "a", "u-a")
        b = _r("Secret", "b", "u-b")
        order = [r.uid for r in teardown_order([a, b])]
        self.assertEqual(order, ["u-a", "u-b"])  # même profondeur → ordre d'entrée

    def test_cycle_does_not_loop(self):
        # ownerReferences pathologiques (cycle) → ne boucle pas, émet tout.
        x = _r("A", "x", "u-x", owners=["u-y"])
        y = _r("B", "y", "u-y", owners=["u-x"])
        order = teardown_order([x, y])
        self.assertEqual({r.uid for r in order}, {"u-x", "u-y"})


if __name__ == "__main__":
    unittest.main()
