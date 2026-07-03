"""Tests du graphe Python figé (`nestor/graph.py`, ADR 0096 §1, lot 2).

Invariants du graphe atomique, en Python pur : possesseurs de ns distincts, unicité
du possesseur, complétude par ownership (OBC → producteur), déterminisme/acyclicité de
`topo_sort`, garde-fou anti-GC des CRD partagées, clôtures par phase, variante backend
local-path.

`graph.py` est la SOURCE UNIQUE de l'ordre et des composants (ADR 0096). La preuve de
byte-identité au bash (ex-`RealBashParity`, qui sourçait `rollback-lib.sh`) a disparu
AVEC le bash (ADR 0101 — rollback-lib.sh supprimé) : il n'y a plus de référence bash à
comparer, le graphe Python n'a plus de jumeau.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import graph  # noqa: E402

_REPO = os.path.join(os.path.dirname(__file__), "..")


class NamespacePossessors(unittest.TestCase):
    """component_namespace : possesseurs distincts (atom/ns du bats)."""

    def test_cnpg_operator_owns_cnpg_system(self):
        # ≠ postgres — l'oubli historique.
        self.assertEqual(graph.component_namespace("cnpg-operator"), "cnpg-system")

    def test_cnpg_cluster_pg_owns_postgres(self):
        self.assertEqual(graph.component_namespace("cnpg-cluster-pg"), "postgres")

    def test_prometheus_owns_monitoring_loki_is_tenant(self):
        self.assertEqual(graph.component_namespace("prometheus-stack"), "monitoring")
        self.assertEqual(graph.component_namespace("loki"), "")

    def test_barman_plugin_is_tenant(self):
        self.assertEqual(graph.component_namespace("barman-plugin"), "")


class Invariant1Trivialite(unittest.TestCase):
    """INVARIANT 1 : ≤1 ns par composant + unicité du possesseur."""

    def test_at_most_one_ns_per_component(self):
        for c in graph.COMPONENT_ALL:
            ns = graph.component_namespace(c)
            self.assertLessEqual(len(ns.split()), 1, f"{c} possède plusieurs ns: {ns}")

    def test_no_ns_claimed_by_two_components(self):
        owned = [graph.component_namespace(c) for c in graph.COMPONENT_ALL]
        owned = [ns for ns in owned if ns]
        self.assertEqual(len(owned), len(set(owned)), f"ns réclamé par >1 composant: {owned}")

    def test_dataops_owns_cnpg_system_and_postgres(self):
        owned = {graph.component_namespace(c) for c in graph.component_expand_alias("dataops")}
        for ns in ("cnpg-system", "postgres", "dagster", "marquez"):
            self.assertIn(ns, owned)


class Invariant2Ownership(unittest.TestCase):
    """INVARIANT 2 : OBC hors-ns → targeted du PRODUCTEUR (jamais de ceph)."""

    def test_obc_cnpg_is_targeted_of_producer(self):
        self.assertIn(
            "-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups",
            graph.component_targeted("s3-backing-cnpg"),
        )
        # ceph (possesseur de rook-ceph) ne porte PAS l'OBC d'autrui.
        self.assertNotIn(
            "cnpg-backups",
            " ".join(graph.component_targeted("ceph")),
        )

    def test_obc_loki_is_targeted_of_producer(self):
        self.assertIn(
            "-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets",
            graph.component_targeted("s3-backing-loki"),
        )


class Invariant3Determinism(unittest.TestCase):
    """INVARIANT 3 : topo_sort déterministe (même liste → même sortie)."""

    def test_topo_sort_deterministic(self):
        comps = graph.component_expand_alias("atlas-ceph")
        self.assertEqual(graph.topo_sort(comps), graph.topo_sort(comps))


class Acyclicite(unittest.TestCase):
    """topo_sort sur tout le catalogue réussit ; un cycle est détecté."""

    def test_all_components_sortable_30(self):
        order = graph.topo_sort(list(graph.COMPONENT_ALL))
        # 30 composants (27 + citation + gitops-seed-citation + eventful, ADR 0094/0095/0103),
        # tous émis.
        self.assertEqual(len(order), 30)
        self.assertEqual(set(order), set(graph.COMPONENT_ALL))

    def test_injected_cycle_detected(self):
        # Le graphe réel est acyclique ; on prouve la détection sur une instance
        # cyclique construite à la main (monkeypatch de component_deps).
        original = graph.component_deps
        try:
            graph.component_deps = lambda comp, backend=graph.CEPH: (  # type: ignore[assignment]
                ["b"] if comp == "a" else ["a"] if comp == "b" else []
            )
            with self.assertRaises(graph.TopoCycleError):
                graph.topo_sort(["a", "b"])
        finally:
            graph.component_deps = original  # type: ignore[assignment]


class Invariant5OrdreCode(unittest.TestCase):
    """INVARIANT 5 : topo_sort REPRODUIT l'ordre codé (pré-condition lot 4)."""

    def test_each_dep_before_its_dependent(self):
        order = graph.topo_sort(graph.component_expand_alias("atlas-ceph"))
        pos = {c: i for i, c in enumerate(order)}
        for c in order:
            for d in graph.component_deps(c):
                if d in pos:
                    self.assertLess(pos[d], pos[c], f"{c} avant sa dep {d}")

    def test_projected_on_aliases_equals_coded_order(self):
        weight_to_alias = {
            0: "socle",
            1: "ceph",
            2: "sc",
            3: "datalake",
            4: "monitoring",
            5: "gitops",
            6: "dataops",
            7: "gitops-seed",
        }
        proj: list[str] = []
        for c in graph.topo_sort(graph.component_expand_alias("atlas-ceph")):
            a = weight_to_alias.get(graph.component_alias_weight(c), "autre")
            if a not in proj:
                proj.append(a)
        self.assertEqual(
            proj,
            ["socle", "ceph", "sc", "datalake", "monitoring", "gitops", "dataops", "gitops-seed"],
        )


class Invariant6CrdPartagee(unittest.TestCase):
    """INVARIANT 6 : garde-fou anti-GC des CRD PARTAGÉES."""

    def test_gateway_crd_only_on_gateway_api(self):
        self.assertIn("gateway.networking.k8s.io", graph.component_crd_groups("gateway-api"))
        for c in ("registry", "gitea", "argocd"):
            self.assertNotIn(
                "gateway.networking.k8s.io",
                graph.component_crd_groups(c),
                f"{c} liste gateway.* (GC partagé !)",
            )

    def test_ceph_crd_only_on_ceph(self):
        self.assertIn("ceph.rook.io", graph.component_crd_groups("ceph"))
        self.assertIn("objectbucket.io", graph.component_crd_groups("ceph"))
        for c in ("sc", "datalake", "s3-backing-loki", "s3-backing-cnpg"):
            self.assertNotIn("ceph.rook.io", graph.component_crd_groups(c))
            self.assertNotIn("objectbucket.io", graph.component_crd_groups(c))

    def test_cnpg_crd_on_operator_not_on_cluster(self):
        self.assertIn("postgresql.cnpg.io", graph.component_crd_groups("cnpg-operator"))
        self.assertNotIn("postgresql.cnpg.io", graph.component_crd_groups("cnpg-cluster-pg"))
        self.assertNotIn("barmancloud.cnpg.io", graph.component_crd_groups("cnpg-cluster-pg"))


class CatalogueKnown(unittest.TestCase):
    """component_known : catalogue."""

    def test_known_and_unknown(self):
        self.assertTrue(graph.component_known("cnpg-operator"))
        self.assertFalse(graph.component_known("n-importe-quoi"))


class PhaseClosureCeph(unittest.TestCase):
    """CLÔTURE PAR PHASE (ceph, défaut) — remplace _DEPENDENTS."""

    def test_ceph_pulls_whole_stack(self):
        self.assertEqual(
            graph.phase_closure("ceph"),
            [
                "ceph",
                "sc",
                "datalake",
                "monitoring",
                "gitops",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
                "gitops-seed-citation",
                "eventful",  # dépend d'argocd/gitea/registry/build-images → terminale (ADR 0103)
            ],
        )

    def test_sc_pulls_gitops(self):
        cl = graph.phase_closure("sc")
        self.assertEqual(
            cl,
            [
                "sc",
                "datalake",
                "monitoring",
                "gitops",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
                "gitops-seed-citation",
                "eventful",  # consommateur de gitops (argocd/gitea) + registry → tiré aussi
            ],
        )
        self.assertIn("gitops", cl)

    def test_datalake_pulls_monitoring_dataops_mlflow_not_gitops(self):
        self.assertEqual(
            graph.phase_closure("datalake"),
            ["datalake", "monitoring", "dataops", "mlflow"],
        )

    def test_gitops_pulls_seed(self):
        # gitops-seed-citation dépend d'argocd/gitea (chaîne gitops) → tiré aussi (ADR 0095).
        # eventful dépend AUSSI d'argocd/gitea (write-back → App-of-Apps) → tiré (ADR 0103).
        self.assertEqual(
            graph.phase_closure("gitops"),
            ["gitops", "gitops-seed", "gitops-seed-citation", "eventful"],
        )

    def test_leaves_pull_only_themselves(self):
        self.assertEqual(graph.phase_closure("monitoring"), ["monitoring"])
        self.assertEqual(graph.phase_closure("mlflow"), ["mlflow"])
        self.assertEqual(graph.phase_closure("portal"), ["portal"])
        self.assertEqual(graph.phase_closure("metrics-server"), ["metrics-server"])

    def test_dataops_pulls_mlflow_portal(self):
        # gitops-seed-citation dépend de citation → registry (∈ dataops) → tiré aussi.
        # eventful dépend AUSSI de registry (∈ dataops) + build-images → tiré (parité portal, 0103).
        self.assertEqual(
            graph.phase_closure("dataops"),
            ["dataops", "mlflow", "portal", "gitops-seed-citation", "eventful"],
        )

    def test_mount_order_ceph_first(self):
        cl = graph.phase_closure("ceph")
        self.assertEqual(cl[:3], ["ceph", "sc", "datalake"])

    def test_unknown_phase_raises(self):
        with self.assertRaises(graph.PhaseUnknownError):
            graph.phase_closure("frobnicate")

    def test_involves_storage(self):
        for p in ("ceph", "sc", "datalake"):
            self.assertTrue(graph.phase_involves_storage(p), p)
        for p in ("metrics-server", "monitoring", "dataops", "gitops", "gitops-seed"):
            self.assertFalse(graph.phase_involves_storage(p), p)

    def test_phase_of_component(self):
        self.assertEqual(graph.phase_of_component("cert-manager"), "")  # socle
        self.assertEqual(graph.phase_of_component("prometheus-stack"), "monitoring")
        self.assertEqual(graph.phase_of_component("gitea"), "gitops")


class BackendLocalPath(unittest.TestCase):
    """GRAPHE BACKEND-CONDITIONNEL (ADR 0069) — variante local-path."""

    def test_sc_edges_become_storage_simple_s3_become_seaweedfs(self):
        be = graph.LOCAL_PATH
        self.assertEqual(
            graph.component_deps("loki", be),
            ["prometheus-stack", "s3-backing-loki", "storage-simple"],
        )
        self.assertEqual(graph.component_deps("s3-backing-cnpg", be), ["seaweedfs"])
        self.assertEqual(graph.component_deps("registry", be), ["gateway-api", "storage-simple"])
        self.assertEqual(
            graph.component_deps("gitea", be), ["cert-manager", "gateway-api", "storage-simple"]
        )

    def test_monitoring_alias_adds_seaweedfs(self):
        self.assertIn("seaweedfs", graph.component_expand_alias("monitoring", graph.LOCAL_PATH))

    def test_topo_sort_dataops_orders_ss_sw_pg_without_ceph(self):
        be = graph.LOCAL_PATH
        order = graph.topo_sort(graph.component_expand_alias("dataops", be), be)
        self.assertNotIn("datalake", order)
        self.assertNotIn("sc", order)
        self.assertLess(order.index("storage-simple"), order.index("seaweedfs"))
        self.assertLess(order.index("seaweedfs"), order.index("cnpg-cluster-pg"))

    def test_ceph_default_excludes_storage_simple_seaweedfs(self):
        cl = graph.topo_sort(graph.component_expand_alias("atlas-ceph"))
        self.assertNotIn("storage-simple", cl)
        self.assertNotIn("seaweedfs", cl)
        self.assertIn("datalake", cl)


# ════════════════════════════════════════════════════════════════════════════
# 1bis. SIGNAL de SANTÉ porté par le graphe (lot 4 refonte nestor)
#       Le signal est un attribut du COMPOSANT (dernier maillon) ; `LAYER_SIGNAL`
#       le projette par phase ; `scripts/topology.py:_LAYER_SIGNAL` n'est qu'une
#       COPIE de cette projection (plus DEUX tables, une seule source de vérité).
# ════════════════════════════════════════════════════════════════════════════


class SignalIsAGraphProperty(unittest.TestCase):
    """Le signal de santé vit dans le graphe (`Component.signal`), pas dans une table à part."""

    # La valeur ATTENDUE de chaque signal (ce que portait l'ancienne table _LAYER_SIGNAL
    # de scripts/topology.py) — gelée ici comme oracle d'égalité de comportement (lot 4).
    EXPECTED: dict[str, tuple] = {
        "metrics-server": ("deployment", "metrics-server", "kube-system", True),
        "storage-simple": ("deployment", "local-path-provisioner", "local-path-storage", True),
        "ceph": ("cephcluster.ceph.rook.io", "rook-ceph", "rook-ceph", "phase"),
        "sc": ("storageclass", "rook-ceph-block-replicated", None, False),
        "datalake": ("cephobjectstore.ceph.rook.io", "datalake", "rook-ceph", "phase"),
        "monitoring": ("statefulset", "loki", "monitoring", True),
        "gitops": ("deployment", "argocd-server", "argocd", True),
        "dataops": ("deployment", "marquez", "marquez", True),
        "mlflow": ("deployment", "mlflow", "mlflow", True),
        "gitops-seed": ("application", "atlas-workflows", "argocd", False),
        "gitops-seed-citation": ("application", "citation-dagster", "argocd", False),
        "portal": ("deployment", "portal", "portal", True),
        "eventful": ("deployment", "workflow-controller", "argo", True),
    }

    def test_layer_signal_matches_frozen_oracle(self):
        # La projection par phase reproduit EXACTEMENT (clés, ORDRE, valeurs) l'oracle gelé.
        self.assertEqual(list(graph.LAYER_SIGNAL), list(self.EXPECTED))
        self.assertEqual(graph.LAYER_SIGNAL, self.EXPECTED)

    def test_layer_signal_is_carried_by_the_last_link_component(self):
        # Pour chaque phase à signal, le tuple projeté EST le `signal` du composant désigné
        # comme dernier maillon — la table n'est PAS une copie parallèle, elle DÉRIVE.
        for phase, sig in graph.LAYER_SIGNAL.items():
            with self.subTest(phase=phase):
                comp = graph.phase_signal_component(phase)
                self.assertIsNotNone(comp, f"{phase} sans composant-signal")
                self.assertEqual(graph.COMPONENTS[comp].signal, sig)
                self.assertEqual(graph.layer_signal(phase), sig)

    def test_signal_component_is_a_real_component_of_its_phase(self):
        # Le composant-signal d'une phase roundtrip appartient bien à l'alias de cette phase
        # (loki ∈ monitoring, argocd ∈ gitops, marquez ∈ dataops…) — pas un nom hors-graphe.
        for phase in graph.LAYER_SIGNAL:
            comp = graph.phase_signal_component(phase)
            with self.subTest(phase=phase, comp=comp):
                self.assertIn(comp, graph.COMPONENTS)
                if phase in graph.ROUNDTRIP_PHASES:
                    self.assertIn(comp, graph.component_expand_alias(phase))

    def test_only_signal_components_carry_a_signal(self):
        # Cohérence inverse : un composant porte un `signal` SSI il est le dernier maillon
        # désigné d'une phase (pas de signal orphelin dans le catalogue).
        carriers = {graph.phase_signal_component(p) for p in graph.LAYER_SIGNAL}
        for name, comp in graph.COMPONENTS.items():
            with self.subTest(comp=name):
                if comp.signal is not None:
                    self.assertIn(name, carriers)

    def test_topology_layer_signal_is_the_graph_projection(self):
        # La table _LAYER_SIGNAL de scripts/topology.py est désormais une COPIE de
        # graph.LAYER_SIGNAL (même contenu, même ordre) — la cohérence graph↔façade exigée.
        sys.path.insert(0, os.path.join(_REPO, "scripts"))
        import topology as cli  # noqa: PLC0415 — import local au test (façade CLI)

        self.assertEqual(list(cli._LAYER_SIGNAL), list(graph.LAYER_SIGNAL))
        self.assertEqual(cli._LAYER_SIGNAL, graph.LAYER_SIGNAL)


if __name__ == "__main__":
    unittest.main()
