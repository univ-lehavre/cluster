"""Tests de la dérivation `topology.layers` (cluster_topology/layers.py, ADR 0069).

`resolve_layers` PROJETTE le graphe atomique réel de rollback-lib.sh (source unique
ADR 0066) — on l'exerce donc CONTRE le vrai graphe (bash), pas un stub : c'est ce
qui prouve la parité avec les arms (un stub mentirait sur l'ordre). Pas de banc, pas
de cluster : `topo_sort`/`component_expand_alias` sont des fonctions PURES du shell.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.layers import (  # noqa: E402
    layers_from_profile,
    resolve_layers,
)
from cluster_topology.model import TopologyError  # noqa: E402


class ResolveLayersLocalPath(unittest.TestCase):
    """Ordre dérivé == ordre figé des arms (local-path) — le stockage en tête."""

    def test_base_is_empty(self):
        self.assertEqual(resolve_layers(["base"], "local-path"), [])

    def test_empty_defaults_to_base(self):
        self.assertEqual(resolve_layers([], "local-path"), [])

    def test_metrics_alone_no_storage(self):
        # metrics-server n'a AUCUNE dépendance stockage (le cœur d'ADR 0069).
        self.assertEqual(resolve_layers(["metrics"], "local-path"), ["metrics-server"])

    def test_store_resolves_to_storage_simple(self):
        self.assertEqual(resolve_layers(["store"], "local-path"), ["storage-simple"])

    def test_obs_pulls_storage_first(self):
        # monitoring consomme des PVC → storage-simple est tiré ET placé en tête.
        self.assertEqual(resolve_layers(["obs"], "local-path"), ["storage-simple", "monitoring"])

    def test_dataops_pulls_storage_and_monitoring(self):
        # dataops → monitoring (SeaweedFS) + stockage ; PAS de datalake en local-path.
        seq = resolve_layers(["dataops"], "local-path")
        self.assertEqual(seq, ["storage-simple", "monitoring", "dataops"])
        self.assertNotIn("datalake", seq)

    def test_atlas_equivalent_order_matches_arm(self):
        # [dataops, gitops, metrics] reproduit l'ordre de l'arm atlas (hors gitops-seed,
        # posé par l'arm en queue) : storage → metrics → monitoring → gitops → dataops.
        self.assertEqual(
            resolve_layers(["dataops", "gitops", "metrics"], "local-path"),
            ["storage-simple", "metrics-server", "monitoring", "gitops", "dataops"],
        )

    def test_non_prefix_palier(self):
        # gitops + metrics SANS monitoring — IMPOSSIBLE via le profil scalaire.
        seq = resolve_layers(["gitops", "metrics"], "local-path")
        self.assertEqual(seq, ["storage-simple", "metrics-server", "gitops"])
        self.assertNotIn("monitoring", seq)

    def test_phase_name_accepted_directly(self):
        # On peut déclarer un nom de phase brut (pas qu'un alias de profil).
        self.assertEqual(resolve_layers(["metrics-server"], "local-path"), ["metrics-server"])


class ResolveLayersCeph(unittest.TestCase):
    def test_dataops_ceph_includes_datalake(self):
        seq = resolve_layers(["dataops"], "ceph")
        self.assertEqual(seq, ["ceph", "sc", "datalake", "dataops"])

    def test_store_ceph_is_ceph_sc(self):
        self.assertEqual(resolve_layers(["store"], "ceph"), ["ceph", "sc"])


class BackendGuard(unittest.TestCase):
    def test_datalake_rejected_on_local_path(self):
        with self.assertRaises(TopologyError):
            resolve_layers(["datalake"], "local-path")

    def test_unknown_layer_rejected(self):
        with self.assertRaises(TopologyError):
            resolve_layers(["frobnicate"], "local-path")


class LayersFromProfile(unittest.TestCase):
    """Rétrocompat : un profil = le préfixe cumulatif (ADR 0039/0068)."""

    def test_dataops_prefix(self):
        self.assertEqual(
            layers_from_profile("dataops"),
            ["base", "metrics", "store", "obs", "dataops"],
        )

    def test_metrics_prefix(self):
        self.assertEqual(layers_from_profile("metrics"), ["base", "metrics"])

    def test_profile_then_resolve_matches(self):
        # profile=obs → layers [base,metrics,store,obs] → resolve == socle+metrics+store+obs.
        seq = resolve_layers(layers_from_profile("obs"), "local-path")
        self.assertEqual(seq, ["storage-simple", "metrics-server", "monitoring"])


if __name__ == "__main__":
    unittest.main()
