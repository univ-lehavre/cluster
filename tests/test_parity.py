"""Filet de PARITÉ : plan.expected_phase_sequence == ce que les arms run-phases.sh font.

`plan.py` AFFIRME être une « transcription fidèle des arms de run-phases.sh » (ADR
0063 G3). Ce test le PROUVE au lieu de l'affirmer : pour chaque chemin nommé, on
compare la séquence dérivée par Python à la séquence ORDONNÉE attendue de l'arm bash
correspondant (table de référence figée ci-dessous, transcrite des arms
bench/lima/run-phases.sh).

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

from nestor.model import topology_from_dict  # noqa: E402
from nestor.plan import expected_phase_sequence  # noqa: E402

# ── Table de référence : la séquence ORDONNÉE de chaque arm (transcription bash) ──
# Sans hardening.
_ARMS = {
    # chemin : (profile, backend, séquence attendue)
    "socle": ("base", "local-path", ["up", "bootstrap"]),
    # metrics (ADR 0068) : socle léger + metrics-server seul (arm `metrics)` run-phases.sh).
    "metrics": ("metrics", "local-path", ["up", "bootstrap", "metrics-server"]),
    # ADR 0083 : `atlas` = alias de la chaîne MLOps complète — ancien atlas + mlflow.
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
            "mlflow",
            "portal",
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
    # ADR 0083 : `atlas` en ceph = ancien atlas-ceph + metrics-server (sur-ensemble
    # assumé) + mlflow.
    "atlas-ceph": (
        "dataops",
        "ceph",
        [
            "up",
            "bootstrap",
            "ceph",
            "sc",
            "datalake",
            "metrics-server",
            "monitoring",
            "gitops",
            "dataops",
            "gitops-seed",
            "mlflow",
            "portal",
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


class ParityLayersArm(unittest.TestCase):
    """ADR 0083 : `--target atlas` et `layers: [atlas]` produisent la MÊME séquence —
    l'ordre vient du graphe (resolve_layers), une seule source de vérité. Garde-fou que
    le preset nommé (rétrocompat CLI) ne diverge pas de l'alias de layers."""

    def test_target_atlas_equals_layers_atlas(self):
        # `--target atlas` (preset) == topo déclarant `layers: [atlas]` (alias) :
        # même séquence, dérivée du graphe atomique. C'est le cœur de l'ADR 0083.
        via_target = expected_phase_sequence(_topo("dataops", "local-path"), "atlas")
        topo_layers = topology_from_dict(
            {
                "catalog": {"topology": "x"},
                "layers": ["atlas"],
                "nodes": [
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "node1", "roles": ["worker"]},
                ],
                "storage": {"backend": "local-path"},
                "target_kind": "lima",
            }
        )
        via_layers = expected_phase_sequence(topo_layers, None)  # default_target → layers
        self.assertEqual(via_target, via_layers)


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


class ParityLayerHasBashPhase(unittest.TestCase):
    """Chaque layer DÉCLARABLE (_QUEUE_PHASES) doit avoir sa fonction `phase_<nom>` dans
    run-phases.sh : l'arm `layers` boucle et appelle `phase_${p//-/_}` pour chaque phase.
    Une layer sans fonction → rc=127 au montage (`phase_mlflow: command not found`, vécu
    au banc 2026-06-17 : `mlflow` déclarée côté Python mais sans phase bash). Ce test fige
    l'alignement Python (liste des layers) ↔ bash (exécuteur)."""

    def test_every_declarable_layer_has_a_bash_phase(self):
        from nestor.layers import _QUEUE_PHASES  # noqa: E402

        run_phases = os.path.join(os.path.dirname(__file__), "..", "bench", "lima", "run-phases.sh")
        with open(run_phases, encoding="utf-8") as fh:
            src = fh.read()
        for layer in sorted(_QUEUE_PHASES):
            fn = "phase_" + layer.replace("-", "_")
            with self.subTest(layer=layer):
                self.assertIn(
                    f"{fn}()",
                    src,
                    f"layer `{layer}` déclarable mais `{fn}()` absente de run-phases.sh "
                    f"→ `layers [...,{layer}]` échouerait en rc=127 (command not found)",
                )


if __name__ == "__main__":
    unittest.main()
