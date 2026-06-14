"""Tests du module « que faire ensuite » (cluster_topology/plan.py, P5).

unittest stdlib, fixtures pures (Topology + done/freshness en paramètres) — aucun
subprocess, aucun réseau. Vérifie que la séquence de phases est une transcription
FIDÈLE des arms de run-phases.sh (ADR 0063 G3), le diff, et la suggestion (1er
drift, parité state.sh).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.model import topology_from_dict  # noqa: E402
from cluster_topology.plan import (  # noqa: E402
    PHASE_PLAYBOOK,
    PlanError,
    default_target,
    diff_phases,
    expected_phase_sequence,
    suggest_next,
)


def _topo(profile="dataops", backend="ceph", hardening=None, nodes=None):
    nodes = nodes or [
        {"name": "cp1", "roles": ["control"]},
        {"name": "node1", "roles": ["worker"]},
        {"name": "node2", "roles": ["worker"]},
    ]
    d = {
        "catalog": {"topology": "t", "profile": profile},
        "nodes": nodes,
        "storage": {"backend": backend},
        "target_kind": "lima",
    }
    if hardening:
        d["hardening"] = hardening
    return topology_from_dict(d)


class ExpectedSequence(unittest.TestCase):
    def test_atlas_local_path_order(self):
        seq = expected_phase_sequence(_topo(backend="local-path"), "atlas")
        self.assertEqual(
            seq,
            [
                "up",
                "bootstrap",
                "storage-simple",
                "metrics-server",
                "monitoring",
                "gitops",
                "dataops",
                "gitops-seed",
            ],
        )

    def test_atlas_ceph_order(self):
        seq = expected_phase_sequence(_topo(backend="ceph"), "atlas-ceph")
        self.assertEqual(
            seq,
            [
                "up",
                "bootstrap",
                "ceph",
                "sc",
                "datalake",
                "monitoring",
                "gitops",
                "dataops",
                "gitops-seed",
            ],
        )

    def test_storage_real_order(self):
        seq = expected_phase_sequence(_topo(backend="ceph"), "storage-real")
        self.assertEqual(
            seq, ["up", "bootstrap", "ceph", "sc", "datalake", "smoke-s3", "wordpress"]
        )

    def test_cluster_dataops_order(self):
        seq = expected_phase_sequence(_topo(backend="ceph"), "cluster-dataops")
        self.assertEqual(
            seq, ["up", "bootstrap", "ceph", "sc", "datalake", "monitoring", "dataops"]
        )

    def test_socle_light(self):
        # base = socle NU (k8s + CNI) ; le stockage n'est PAS dans base (ADR 0039 :
        # storage ∈ store, pas base). Plus de storage-simple ici.
        seq = expected_phase_sequence(_topo(profile="base", backend="local-path"), "socle")
        self.assertEqual(seq, ["up", "bootstrap"])

    def test_atlas_local_path_keeps_storage_before_apps(self):
        # atlas (dataops, local-path) consomme du stockage → storage-simple est ajouté
        # APRÈS le socle nu, AVANT les apps (monitoring/dataops créent des PVC).
        seq = expected_phase_sequence(_topo(backend="local-path"), "atlas")
        self.assertEqual(seq[:3], ["up", "bootstrap", "storage-simple"])

    def test_hardening_inserted_after_socle(self):
        seq = expected_phase_sequence(
            _topo(backend="ceph", hardening={"enabled": True}), "atlas-ceph"
        )
        # hardening juste après le socle (run_hardening_if_requested), avant la queue.
        self.assertEqual(seq[:5], ["up", "bootstrap", "ceph", "sc", "hardening"])
        self.assertEqual(seq[5], "datalake")


class TargetValidation(unittest.TestCase):
    def test_unknown_target_rejected(self):
        with self.assertRaises(PlanError):
            expected_phase_sequence(_topo(), "frobnicate")

    def test_ceph_path_on_local_path_rejected(self):
        with self.assertRaises(PlanError):
            expected_phase_sequence(_topo(backend="local-path"), "storage-real")

    def test_atlas_on_ceph_rejected(self):
        # run-phases.sh refuse atlas + WITH_CEPH → utiliser atlas-ceph.
        with self.assertRaises(PlanError):
            expected_phase_sequence(_topo(backend="ceph"), "atlas")

    def test_default_target_dataops_ceph(self):
        self.assertEqual(default_target(_topo(backend="ceph")), "atlas-ceph")

    def test_default_target_dataops_local_path(self):
        self.assertEqual(default_target(_topo(backend="local-path")), "atlas")

    def test_default_target_base_is_socle(self):
        self.assertEqual(default_target(_topo(profile="base", backend="local-path")), "socle")

    def _ha_topo(self):
        # Topologie HA déclarée : 3 control-planes hyperconvergés + VIP (la
        # déclaration de #333). Le modèle exige control_plane_lb dès > 1 CP.
        return topology_from_dict(
            {
                "catalog": {"topology": "ha-3cp", "profile": "base"},
                "nodes": [
                    {"name": "cp1", "roles": ["control", "worker"]},
                    {"name": "cp2", "roles": ["control", "worker"]},
                    {"name": "cp3", "roles": ["control", "worker"]},
                ],
                "network": {"control_plane_lb": {"mode": "kube-vip-arp"}},
                "storage": {"backend": "local-path"},
                "target_kind": "lima",
            }
        )

    def test_ha_topology_derives_ha_3cp(self):
        # > 1 CP DÉCLARÉ → default_target dérive ha-3cp (sélection par topologie,
        # pas commande à flags — ADR 0056). HA prime sur le profil applicatif.
        self.assertEqual(default_target(self._ha_topo()), "ha-3cp")

    def test_ha_3cp_sequence(self):
        seq = expected_phase_sequence(self._ha_topo())
        self.assertEqual(seq, ["up", "bootstrap-ha", "join-cp", "storage-simple"])

    def test_ha_3cp_rejects_ceph_backend(self):
        # ha-3cp = local-path (HA ⊥ stockage). Un backend ceph déclaré est refusé.
        ceph_ha = topology_from_dict(
            {
                "catalog": {"topology": "ha-3cp", "profile": "base"},
                "nodes": [
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "cp2", "roles": ["control"]},
                    {"name": "cp3", "roles": ["control"]},
                ],
                "network": {"control_plane_lb": {"mode": "kube-vip-arp"}},
                "storage": {"backend": "ceph"},
                "target_kind": "lima",
            }
        )
        with self.assertRaises(PlanError):
            expected_phase_sequence(ceph_ha, "ha-3cp")


class DiffPhases(unittest.TestCase):
    SEQ = ["up", "bootstrap", "ceph", "sc", "datalake"]

    def test_frais_done_complete_is_empty(self):
        self.assertEqual(diff_phases(self.SEQ, set(self.SEQ), "frais"), [])

    def test_frais_partial_returns_missing_in_order(self):
        done = {"up", "bootstrap"}
        self.assertEqual(diff_phases(self.SEQ, done, "frais"), ["ceph", "sc", "datalake"])

    def test_perime_replays_whole_sequence(self):
        # pas de run frais → toute la séquence candidate, même si 'done' est plein.
        self.assertEqual(diff_phases(self.SEQ, set(self.SEQ), "perime"), self.SEQ)

    def test_jamais_replays_whole_sequence(self):
        self.assertEqual(diff_phases(self.SEQ, set(), "jamais"), self.SEQ)


class SuggestNext(unittest.TestCase):
    def test_first_missing_phase_only(self):
        # 1er drift seulement (parité state.sh #107-109).
        topo = _topo(backend="ceph")
        s = suggest_next(topo, "atlas-ceph", {"up", "bootstrap", "ceph", "sc"}, "frais")
        self.assertEqual(s.phase, "datalake")
        self.assertEqual(s.etat, "manquante")
        self.assertEqual(s.playbook, "bootstrap/ceph-datalake.yaml")

    def test_all_done_fresh_suggests_nothing(self):
        topo = _topo(backend="ceph")
        seq = set(expected_phase_sequence(topo, "atlas-ceph"))
        s = suggest_next(topo, "atlas-ceph", seq, "frais")
        self.assertIsNone(s.phase)
        self.assertEqual(s.etat, "à-jour")
        self.assertIn("à jour", s.message)

    def test_perime_suggests_first_of_sequence_as_rejeu(self):
        topo = _topo(backend="ceph")
        seq = set(expected_phase_sequence(topo, "atlas-ceph"))
        s = suggest_next(topo, "atlas-ceph", seq, "perime")
        self.assertEqual(s.phase, "up")  # rejeu depuis le début
        self.assertEqual(s.etat, "rejeu")

    def test_run_params_attached(self):
        topo = _topo(backend="ceph")
        rp = {"cnpg_storage_class": "rook-ceph-block-replicated"}
        s = suggest_next(topo, "atlas-ceph", {"up"}, "frais", run_params=rp)
        self.assertEqual(s.run_params, rp)


class PhaseTable(unittest.TestCase):
    def test_every_path_phase_is_in_table(self):
        # Garde-fou : chaque phase qui apparaît dans une séquence doit avoir une
        # entrée dans PHASE_PLAYBOOK (playbook ou None explicite).
        topo_ceph = _topo(backend="ceph", hardening={"enabled": True})
        topo_light = _topo(backend="local-path")
        phases = set()
        for tgt in ["socle", "storage-real", "cluster-dataops", "atlas-ceph"]:
            phases.update(expected_phase_sequence(topo_ceph, tgt))
        phases.update(expected_phase_sequence(topo_light, "atlas"))
        self.assertTrue(phases.issubset(set(PHASE_PLAYBOOK)))


if __name__ == "__main__":
    unittest.main()
