"""Tests de la reconstruction de topologie (nestor/discover.py, ADR 0074).

INVERSE de `generate` : à partir de sondes du réel (dicts en entrée), `discover`
assemble (1) une topologie déclarative, (2) l'INCONNU (jamais ignoré, ADR 0052),
(3) un bilan de santé. Toute la logique testée ici est PURE — aucun kubectl, aucun
cluster : les sondes I/O vivent dans la façade `cmd_discover` (bash, ADR 0049).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.discover import (  # noqa: E402
    ABSENT,
    DEGRADE,
    SAIN,
    Unknown,
    assemble,
    build_topology,
    classify_backend_drift,
    classify_health,
    classify_namespaces,
    detect_backend,
    detect_exposition,
    detect_platforms,
)
from nestor.model import topology_from_dict  # noqa: E402


class ClassifyNamespaces(unittest.TestCase):
    def test_known_ns_maps_to_layer(self):
        layers, unknown = classify_namespaces(["argocd", "gitea", "dagster"])
        self.assertEqual(layers, {"gitops", "dataops"})
        self.assertEqual(unknown, [])

    def test_unknown_ns_is_enumerated_never_dropped(self):
        # ADR 0074 §2 : un ns hors catalogue est signalé, pas perdu.
        layers, unknown = classify_namespaces(["kube-system", "squat-ns"])
        self.assertEqual(layers, set())
        self.assertEqual(unknown, [Unknown("Namespace", "squat-ns")])

    def test_socle_storage_obs_are_not_addressable_layers(self):
        # kube-system (socle), s3 (storage), mail (obs) ne remontent PAS comme layers.
        layers, unknown = classify_namespaces(["kube-system", "s3", "mail"])
        self.assertEqual(layers, set())
        self.assertEqual(unknown, [])


class DetectPlatforms(unittest.TestCase):
    def test_crd_group_suffix_match(self):
        # match par suffixe : cephclusters.ceph.rook.io → ceph
        plats = detect_platforms(["cephclusters.ceph.rook.io", "applications.argoproj.io"])
        self.assertEqual(plats, {"ceph", "gitops"})

    def test_gateway_crd_detected(self):
        self.assertIn(
            "exposition-gateway",
            detect_platforms(["httproutes.gateway.networking.k8s.io"]),
        )

    def test_no_crd_no_platform(self):
        self.assertEqual(detect_platforms([]), set())


class DetectBackend(unittest.TestCase):
    def test_ceph_provisioner(self):
        self.assertEqual(detect_backend(["rook-ceph.rbd.csi.ceph.com"]), "ceph")

    def test_localpath_provisioner(self):
        self.assertEqual(detect_backend(["rancher.io/local-path"]), "local-path")

    def test_ceph_wins_when_both_present(self):
        # un cluster ceph garde souvent local-path en secours → ceph prime.
        self.assertEqual(
            detect_backend(["rancher.io/local-path", "rook-ceph.rbd.csi.ceph.com"]),
            "ceph",
        )

    def test_nothing_defaults_to_localpath(self):
        self.assertEqual(detect_backend([]), "local-path")


class ClassifyBackendDrift(unittest.TestCase):
    """#356 : signaler un backend réel qui CONTREDIT le déclaré (≠ detect_backend)."""

    def test_ceph_sc_but_declared_localpath_is_drift(self):
        # Le cas vécu : bascule ceph→local-path, rook-ceph résiduel orphelin.
        self.assertEqual(
            classify_backend_drift("local-path", ["rook-ceph.rbd.csi.ceph.com"]), "ceph"
        )

    def test_localpath_sc_but_declared_ceph_is_drift(self):
        self.assertEqual(classify_backend_drift("ceph", ["rancher.io/local-path"]), "local-path")

    def test_real_matches_declared_no_drift(self):
        self.assertIsNone(classify_backend_drift("ceph", ["rook-ceph.rbd.csi.ceph.com"]))
        self.assertIsNone(classify_backend_drift("local-path", ["rancher.io/local-path"]))

    def test_no_recognized_sc_no_drift(self):
        # Cluster vide/injoignable (aucune SC reconnue) → pas de drift AFFIRMABLE (vs
        # detect_backend qui retombe sur local-path et confondrait).
        self.assertIsNone(classify_backend_drift("ceph", []))
        self.assertIsNone(classify_backend_drift("local-path", []))
        self.assertIsNone(classify_backend_drift("local-path", ["some.unknown/provisioner"]))

    def test_ceph_residual_alongside_localpath_declared_localpath_is_drift(self):
        # ceph ET local-path présents, déclaré local-path → ceph résiduel = drift.
        self.assertEqual(
            classify_backend_drift(
                "local-path", ["rancher.io/local-path", "rook-ceph.rbd.csi.ceph.com"]
            ),
            "ceph",
        )


class DetectExposition(unittest.TestCase):
    def test_gateway_present(self):
        self.assertEqual(detect_exposition(gateways_present=True, crd_groups=[]), "gateway")

    def test_gateway_crd_only(self):
        self.assertEqual(
            detect_exposition(
                gateways_present=False,
                crd_groups=["gateways.gateway.networking.k8s.io"],
            ),
            "gateway",
        )

    def test_none_when_no_gateway(self):
        # ADR 0020 : mode unique gateway ; sans bordure → none (plus de hostport L4).
        self.assertEqual(detect_exposition(gateways_present=False, crd_groups=[]), "none")


class ClassifyHealth(unittest.TestCase):
    def test_all_nodes_ready_is_sain(self):
        h = {i.dimension: i.verdict for i in classify_health(nodes_ready=3, nodes_total=3)}
        self.assertEqual(h["nœuds"], SAIN)

    def test_partial_nodes_is_degrade(self):
        h = {i.dimension: i.verdict for i in classify_health(nodes_ready=2, nodes_total=3)}
        self.assertEqual(h["nœuds"], DEGRADE)

    def test_no_nodes_is_absent(self):
        h = {i.dimension: i.verdict for i in classify_health(nodes_ready=0, nodes_total=0)}
        self.assertEqual(h["nœuds"], ABSENT)

    def test_degraded_workload_flagged(self):
        # un layer présent mais en CrashLoop → DÉGRADÉ (ADR 0074 §3).
        h = {
            i.dimension: i.verdict
            for i in classify_health(
                nodes_ready=1, nodes_total=1, workloads_degraded=["dagster/run-coord"]
            )
        }
        self.assertEqual(h["workloads"], DEGRADE)

    def test_pvc_pending_is_degrade(self):
        h = {
            i.dimension: i.verdict
            for i in classify_health(nodes_ready=1, nodes_total=1, pvc_pending=2, pvc_total=5)
        }
        self.assertEqual(h["stockage (PVC)"], DEGRADE)

    def test_osd_health_when_ceph(self):
        items = classify_health(nodes_ready=3, nodes_total=3, osds_up=3, osds_expected=3)
        osd = [i for i in items if i.dimension == "stockage (OSD)"]
        self.assertEqual(len(osd), 1)
        self.assertEqual(osd[0].verdict, SAIN)

    def test_cr_status_read_not_exec(self):
        # santé d'un CR lue sur son .status (pas par exec) — [[k8s-exec-vs-k8s-info-gate]].
        items = classify_health(
            nodes_ready=1,
            nodes_total=1,
            cr_status={"CephCluster/rook-ceph": "HEALTH_OK", "CNPG/pg": "Pending"},
        )
        verdicts = {i.dimension: i.verdict for i in items}
        self.assertEqual(verdicts["CR CephCluster/rook-ceph"], SAIN)
        self.assertEqual(verdicts["CR CNPG/pg"], DEGRADE)


class BuildTopology(unittest.TestCase):
    def test_gateway_exposition_is_implicit(self):
        # gateway = mode de référence (ADR 0020) → non écrit dans le YAML reconstruit.
        topo = build_topology(
            nodes=[{"name": "node1", "roles": ["control"]}],
            layers=["gitops"],
            backend="local-path",
            exposition="gateway",
        )
        self.assertNotIn("exposition", topo)

    def test_non_gateway_exposition_written(self):
        topo = build_topology(
            nodes=[{"name": "node1", "roles": ["control"]}],
            layers=[],
            backend="local-path",
            exposition="none",
        )
        self.assertEqual(topo["exposition"], {"mode": "none"})


class Assemble(unittest.TestCase):
    def _probe_gitops_localpath(self):
        return dict(
            nodes=[{"name": "node1", "roles": ["control", "worker"]}],
            namespaces=["kube-system", "argocd", "gitea", "squat"],
            crd_groups=[
                "applications.argoproj.io",
                "gateways.gateway.networking.k8s.io",
            ],
            storageclass_provisioners=["rancher.io/local-path"],
            gateways_present=True,
        )

    def test_assemble_reconstructs_layers_backend_and_keeps_unknown(self):
        res = assemble(**self._probe_gitops_localpath())
        self.assertEqual(res.topology["layers"], ["gitops"])
        self.assertEqual(res.topology["storage"]["backend"], "local-path")
        self.assertNotIn("exposition", res.topology)  # gateway implicite
        self.assertEqual(res.unknown, [Unknown("Namespace", "squat")])

    def test_assembled_topology_is_valid(self):
        # ADR 0074 §5 : la sortie passe topology_from_dict (boucle discover→validate).
        res = assemble(**self._probe_gitops_localpath())
        topo = topology_from_dict(res.topology)  # ne lève pas
        self.assertEqual(topo.exposition_mode, "gateway")

    def test_extra_unknown_merged(self):
        # un Deployment hors catalogue repéré par la façade s'ajoute à l'inconnu.
        probe = self._probe_gitops_localpath()
        res = assemble(**probe, extra_unknown=[Unknown("Deployment", "rogue", "default")])
        kinds = {(u.kind, u.name) for u in res.unknown}
        self.assertIn(("Namespace", "squat"), kinds)
        self.assertIn(("Deployment", "rogue"), kinds)

    def test_ceph_backend_from_storageclass(self):
        probe = self._probe_gitops_localpath()
        probe["storageclass_provisioners"] = ["rook-ceph.rbd.csi.ceph.com"]
        res = assemble(**probe)
        self.assertEqual(res.topology["storage"]["backend"], "ceph")


if __name__ == "__main__":
    unittest.main()
