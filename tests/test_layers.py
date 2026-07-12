"""Tests de la dérivation `topology.layers` (nestor/layers.py, ADR 0069).

`resolve_layers` PROJETTE le graphe atomique réel de rollback-lib.sh (source unique
ADR 0066) — on l'exerce donc CONTRE le vrai graphe (bash), pas un stub : c'est ce
qui prouve la parité avec les arms (un stub mentirait sur l'ordre). Pas de banc, pas
de cluster : `topo_sort`/`component_expand_alias` sont des fonctions PURES du shell.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.layers import (  # noqa: E402
    layers_from_profile,
    phase_deps,
    resolve_layers,
)
from nestor.model import TopologyError  # noqa: E402


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
        # ADR 0112 : `registry` (phase autonome) est tiré par la clôture de dataops.
        seq = resolve_layers(["dataops"], "local-path")
        self.assertEqual(seq, ["storage-simple", "monitoring", "registry", "dataops"])
        self.assertNotIn("datalake", seq)

    def test_atlas_equivalent_order_matches_arm(self):
        # [dataops, gitops, metrics] reproduit l'ordre de l'arm atlas (hors gitops-seed,
        # posé par l'arm en queue) : storage → metrics → monitoring → gitops → dataops.
        self.assertEqual(
            resolve_layers(["dataops", "gitops", "metrics"], "local-path"),
            ["storage-simple", "metrics-server", "monitoring", "gitops", "registry", "dataops"],
        )

    def test_non_prefix_palier(self):
        # gitops + metrics SANS monitoring — IMPOSSIBLE via le profil scalaire.
        seq = resolve_layers(["gitops", "metrics"], "local-path")
        self.assertEqual(seq, ["storage-simple", "metrics-server", "gitops"])
        self.assertNotIn("monitoring", seq)

    def test_phase_name_accepted_directly(self):
        # On peut déclarer un nom de phase brut (pas qu'un alias de profil).
        self.assertEqual(resolve_layers(["metrics-server"], "local-path"), ["metrics-server"])

    def test_atlas_alias_is_full_mlops_chain(self):
        # ADR 0083 : `atlas` = alias COMPOSITE de la chaîne MLOps complète. Reproduit
        # l'ancien preset atlas (storage-simple → metrics-server → monitoring → gitops
        # → dataops → gitops-seed) PLUS mlflow (ADR 0082) et portail (ADR 0091) en queue.
        # L'ordre vient du graphe atomique (resolve_layers), pas d'une table figée.
        # FILET anti-drift.
        self.assertEqual(
            resolve_layers(["atlas"], "local-path"),
            [
                "storage-simple",
                "metrics-server",
                "monitoring",
                "gitops",
                "registry",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
            ],
        )

    def test_atlas_alias_dedups_redundant_layer(self):
        # Déclarer une couche DÉJÀ dans atlas (ex. mlflow) ne la double pas.
        self.assertEqual(
            resolve_layers(["atlas", "mlflow"], "local-path"),
            resolve_layers(["atlas"], "local-path"),
        )


class ResolveLayersCeph(unittest.TestCase):
    def test_dataops_ceph_includes_datalake(self):
        seq = resolve_layers(["dataops"], "ceph")
        # ADR 0112 : `registry` (phase autonome) est tiré par la clôture de dataops.
        self.assertEqual(seq, ["ceph", "sc", "datalake", "registry", "dataops"])

    def test_store_ceph_is_ceph_sc_datalake(self):
        # `store` en ceph = pile stockage COMPLÈTE : bloc (ceph+sc) ET objet RGW (datalake).
        # ADR 0039 : le profil store offre bloc + objet, pas seulement le bloc.
        self.assertEqual(resolve_layers(["store"], "ceph"), ["ceph", "sc", "datalake"])

    def test_store_local_path_is_storage_simple(self):
        # en local-path : pas de RGW (datalake ceph-only) → provisioner bloc seul.
        self.assertEqual(resolve_layers(["store"], "local-path"), ["storage-simple"])

    def test_atlas_alias_ceph_full_chain(self):
        # ADR 0083 : `atlas` en ceph = ancien atlas-ceph (ceph+sc+datalake → monitoring
        # → gitops → dataops → gitops-seed) PLUS metrics-server (sur-ensemble assumé,
        # inoffensif), mlflow (ADR 0082) et portail (ADR 0091). Ordre du graphe atomique.
        self.assertEqual(
            resolve_layers(["atlas"], "ceph"),
            [
                "ceph",
                "sc",
                "datalake",
                "metrics-server",
                "monitoring",
                "gitops",
                "registry",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
            ],
        )


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


class PhaseDeps(unittest.TestCase):
    """`phase_deps` : dépendances PHASE→PHASE dérivées du VRAI graphe atomique.

    C'est la base de `plan.installable_now` (le menu de `next`) : on PROUVE ici,
    contre le bash réel (pas un stub), que `metrics-server` et `storage-simple` sont
    des RACINES indépendantes (le cœur du besoin : choisir l'un avant l'autre), et
    que monitoring/gitops/dataops/gitops-seed portent bien leurs vraies arêtes.
    """

    def test_local_path_storage_and_metrics_are_independent_roots(self):
        deps = phase_deps("local-path")
        # Aucune arête entre eux : montables dans n'importe quel ordre (ADR 0066).
        self.assertEqual(deps["storage-simple"], set())
        self.assertEqual(deps["metrics-server"], set())

    def test_local_path_apps_depend_on_storage(self):
        deps = phase_deps("local-path")
        # gitea/prometheus consomment des PVC → monitoring/gitops dépendent du stockage
        # (arête perdue si on oubliait le repli storage-simple = sa propre phase).
        self.assertIn("storage-simple", deps["monitoring"])
        self.assertIn("storage-simple", deps["gitops"])

    def test_local_path_dataops_needs_monitoring(self):
        deps = phase_deps("local-path")
        self.assertIn("monitoring", deps["dataops"])

    def test_local_path_gitops_seed_needs_gitops(self):
        deps = phase_deps("local-path")
        self.assertEqual(deps["gitops-seed"], {"gitops"})

    def test_local_path_excludes_ceph_only_phases(self):
        # datalake/ceph/sc n'existent pas en local-path → absentes de la carte.
        deps = phase_deps("local-path")
        for ceph_only in ("datalake", "ceph", "sc"):
            self.assertNotIn(ceph_only, deps)

    def test_ceph_storage_chain(self):
        deps = phase_deps("ceph")
        # En ceph le stockage est ceph→sc→datalake ; metrics reste une racine.
        self.assertEqual(deps["ceph"], set())
        self.assertEqual(deps["sc"], {"ceph"})
        self.assertEqual(deps["datalake"], {"ceph", "sc"})
        self.assertEqual(deps["metrics-server"], set())


if __name__ == "__main__":
    unittest.main()
