"""Filet de PARITÉ : plan.expected_phase_sequence == ce que les arms run-phases.sh font.

`plan.py` AFFIRME être une « transcription fidèle des arms de run-phases.sh » (ADR
0063 G3). Ce test le PROUVE au lieu de l'affirmer : pour chaque chemin nommé, on
compare la séquence dérivée par Python à la séquence ORDONNÉE attendue de l'arm bash
correspondant (table de référence figée ci-dessous, transcrite des arms
test/lima/run-phases.sh).

Garde-fou anti-dérive pendant l'inversion de frontière (topology.py devient l'entrée) :
tant que les arms agrégés existent, ce test garantit que le plan AFFICHÉ par `up`/
`preview` == ce que le banc EXÉCUTE. À la coupe finale, il fige le snapshot de
l'intention historique.

Transcription (run_* dépliés, vérifiée dans run-phases.sh) :
  run_socle (local-path)  = up, bootstrap
  run_socle (ceph)        = up, bootstrap, ceph, sc
  run_hardening_if_requested = hardening (si demandé), APRÈS le socle
  run_storage_simple      = storage-simple (local-path, chemins store+)
Ordre dans les arms : run_socle → run_hardening → run_storage_simple → queue applicative.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.model import topology_from_dict  # noqa: E402
from cluster_topology.plan import expected_phase_sequence  # noqa: E402

# ── Table de référence : la séquence ORDONNÉE de chaque arm (transcription bash) ──
# Sans hardening.
_ARMS = {
    # chemin : (profile, backend, séquence attendue)
    "socle": ("base", "local-path", ["up", "bootstrap"]),
    # metrics (ADR 0068) : socle léger + metrics-server seul (arm `metrics)` run-phases.sh).
    "metrics": ("metrics", "local-path", ["up", "bootstrap", "metrics-server"]),
    "atlas": (
        "dataops",
        "local-path",
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
    ),
    "storage-real": (
        "dataops",
        "ceph",
        ["up", "bootstrap", "ceph", "sc", "datalake", "smoke-s3", "wordpress"],
    ),
    "cluster-dataops": (
        "dataops",
        "ceph",
        ["up", "bootstrap", "ceph", "sc", "datalake", "monitoring", "dataops"],
    ),
    "atlas-ceph": (
        "dataops",
        "ceph",
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
    ),
}


def _topo(profile, backend):
    return topology_from_dict(
        {
            "catalog": {"topology": "x", "profile": profile},
            "nodes": [
                {"name": "cp1", "roles": ["control"]},
                {"name": "node1", "roles": ["worker"]},
            ],
            "storage": {"backend": backend},
            "target_kind": "lima",
        }
    )


class ParityArms(unittest.TestCase):
    """expected_phase_sequence == la séquence de l'arm run-phases.sh, chemin par chemin."""

    def test_every_arm_matches_plan(self):
        for target, (profile, backend, expected) in _ARMS.items():
            with self.subTest(target=target):
                seq = expected_phase_sequence(_topo(profile, backend), target)
                self.assertEqual(
                    seq,
                    expected,
                    f"chemin `{target}` : plan.py diverge de l'arm run-phases.sh",
                )


class ParityHardening(unittest.TestCase):
    """Le durcissement s'insère APRÈS le socle, AVANT la queue (run_hardening_if_requested
    est appelé juste après run_socle dans chaque arm — atlas : avant storage-simple)."""

    def _topo_hard(self, profile, backend):
        d = {
            "catalog": {"topology": "x", "profile": profile},
            "nodes": [
                {"name": "cp1", "roles": ["control"]},
                {"name": "node1", "roles": ["worker"]},
            ],
            "storage": {"backend": backend},
            "hardening": {"enabled": True},
            "target_kind": "lima",
        }
        return topology_from_dict(d)

    def test_hardening_after_socle_before_storage_atlas(self):
        # atlas : run_socle → hardening → storage-simple → apps (ordre exact de l'arm).
        seq = expected_phase_sequence(self._topo_hard("dataops", "local-path"), "atlas")
        self.assertEqual(seq[:4], ["up", "bootstrap", "hardening", "storage-simple"])
        self.assertEqual(seq[4], "metrics-server")

    def test_hardening_after_ceph_socle(self):
        # atlas-ceph : run_socle(ceph)=up,bootstrap,ceph,sc → hardening → queue.
        seq = expected_phase_sequence(self._topo_hard("dataops", "ceph"), "atlas-ceph")
        self.assertEqual(seq[:5], ["up", "bootstrap", "ceph", "sc", "hardening"])
        self.assertEqual(seq[5], "datalake")


if __name__ == "__main__":
    unittest.main()
