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
    classify_stuck,
    delete_targets,
    from_probe,
    is_noise,
    prune_noise,
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


class IsNoise(unittest.TestCase):
    def test_event_is_noise(self):
        self.assertTrue(is_noise(_r("Event", "pod.abc", "u-ev")))

    def test_controller_managed_kinds_are_noise(self):
        for kind in ("EndpointSlice", "Endpoints", "CiliumEndpoint"):
            self.assertTrue(is_noise(_r(kind, "x", f"u-{kind}")), kind)

    def test_k8s_injected_named_resources_are_noise(self):
        self.assertTrue(is_noise(_r("ConfigMap", "kube-root-ca.crt", "u-ca")))
        self.assertTrue(is_noise(_r("ServiceAccount", "default", "u-sa")))

    def test_applicative_resources_are_not_noise(self):
        # un ConfigMap/SA applicatif (autre nom) n'est PAS du bruit.
        self.assertFalse(is_noise(_r("ConfigMap", "dagster-instance", "u-cm")))
        self.assertFalse(is_noise(_r("ServiceAccount", "dagster", "u-sa2")))
        self.assertFalse(is_noise(_r("Deployment", "dagster", "u-d")))


class PruneNoise(unittest.TestCase):
    def test_drops_only_noise_keeps_order(self):
        items = [
            _r("Event", "e1", "u-e1"),
            _DEPLOY,
            _r("Event", "e2", "u-e2"),
            _r("Service", "svc", "u-svc"),
        ]
        kept = [r.uid for r in prune_noise(items)]
        self.assertEqual(kept, ["u-deploy", "u-svc"])


class DeleteTargets(unittest.TestCase):
    def test_only_root_of_a_chain(self):
        # Deployment→ReplicaSet→Pod : on ne cible QUE le Deployment (le GC cascade le reste).
        targets = [r.uid for r in delete_targets([_DEPLOY, _RS, _POD])]
        self.assertEqual(targets, ["u-deploy"])

    def test_operator_cr_is_the_root_not_its_children(self):
        # un CR (Cluster CNPG) possède un Pod + un PVC → cible = le CR seul.
        cr = _r("Cluster", "pg", "u-cr", ns="postgres")
        pod = _r("Pod", "pg-1", "u-pgpod", owners=["u-cr"], ns="postgres")
        pvc = _r("PersistentVolumeClaim", "pg-1", "u-pvc", owners=["u-cr"], ns="postgres")
        targets = [r.uid for r in delete_targets([cr, pod, pvc])]
        self.assertEqual(targets, ["u-cr"])

    def test_independent_roots_both_targeted(self):
        svc = _r("Service", "a", "u-a")
        sec = _r("Secret", "b", "u-b")
        targets = {r.uid for r in delete_targets([svc, sec])}
        self.assertEqual(targets, {"u-a", "u-b"})

    def test_orphan_pod_is_a_target(self):
        # un Pod dont l'owner est HORS périmètre (absent) est une vraie racine → cible.
        orphan = _r("Pod", "orphan", "u-orph", owners=["u-absent"])
        targets = [r.uid for r in delete_targets([orphan])]
        self.assertEqual(targets, ["u-orph"])

    def test_noise_never_targeted_even_orphan(self):
        # un Event orphelin ne devient JAMAIS une racine cible (filtré avant).
        ev = _r("Event", "e", "u-e")
        targets = delete_targets([ev, _DEPLOY, _RS, _POD])
        self.assertEqual([r.uid for r in targets], ["u-deploy"])


class ClassifyStuck(unittest.TestCase):
    def test_terminating_pod_with_live_container_forces(self):
        self.assertEqual(
            classify_stuck(terminating=True, has_finalizers=False, container_alive=True),
            "force_grace0",
        )

    def test_finalizers_without_operator_stripped(self):
        self.assertEqual(
            classify_stuck(terminating=False, has_finalizers=True, container_alive=False),
            "strip_finalizers",
        )

    def test_force_delete_takes_precedence_over_finalizers(self):
        # un pod coincé (conteneur vivant) bloque le ns → forcer prime sur strip.
        self.assertEqual(
            classify_stuck(terminating=True, has_finalizers=True, container_alive=True),
            "force_grace0",
        )

    def test_normal_resource_no_gesture(self):
        self.assertEqual(
            classify_stuck(terminating=False, has_finalizers=False, container_alive=False),
            "none",
        )


if __name__ == "__main__":
    unittest.main()
