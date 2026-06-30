"""Tests de la fusion texte (nestor/refresh_fuse.py, ADR 0076 §4).

Pur : texte source + plan → texte fusionné. On vérifie que SEULES les lignes des
ajouts changent (commentaires/status/ordre préservés) et que la sortie reste un YAML
valide qui passe `topology_from_dict`.
"""

import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.model import topology_from_dict  # noqa: E402
from nestor.refresh_fuse import (  # noqa: E402
    FuseError,
    fuse_topology,
    prunable_layers,
    prune_topology,
)
from nestor.refresh_plan import NodeChange, RefreshPlan  # noqa: E402

_SRC = """\
# commentaire d'en-tête à préserver (ADR 0023).
catalog:
  topology: banc
  profile: dataops
  status: cible
nodes:
  - name: node1
    roles:
      - control
      - worker
  - name: node2
    roles:
      - worker
storage:
  backend: local-path
target_kind: bench
"""


class FuseNodes(unittest.TestCase):
    def test_appends_node_preserving_rest(self):
        plan = RefreshPlan(nodes_to_add=[NodeChange("node3", ["worker"])])
        out = fuse_topology(_SRC, plan)
        d = yaml.safe_load(out)
        self.assertEqual([n["name"] for n in d["nodes"]], ["node1", "node2", "node3"])
        self.assertEqual(d["nodes"][2]["roles"], ["worker"])
        # rien d'autre n'a bougé
        self.assertIn("# commentaire d'en-tête à préserver", out)
        self.assertEqual(d["catalog"]["status"], "cible")
        self.assertEqual(d["storage"]["backend"], "local-path")


class FuseLayers(unittest.TestCase):
    def test_creates_layers_key_when_absent(self):
        plan = RefreshPlan(layers_to_add=["monitoring"])
        out = fuse_topology(_SRC, plan)
        d = yaml.safe_load(out)
        self.assertEqual(d["layers"], ["monitoring"])
        # insérée AVANT storage (lisibilité) — vérifie l'ordre textuel
        self.assertLess(out.index("layers:"), out.index("storage:"))

    def test_extends_existing_inline_layers(self):
        src = _SRC.replace("storage:", "layers: [metrics]\nstorage:")
        plan = RefreshPlan(layers_to_add=["monitoring"])
        out = fuse_topology(src, plan)
        d = yaml.safe_load(out)
        self.assertEqual(d["layers"], ["metrics", "monitoring"])

    def test_does_not_duplicate_existing_layer(self):
        src = _SRC.replace("storage:", "layers: [monitoring]\nstorage:")
        plan = RefreshPlan(layers_to_add=["monitoring"])
        out = fuse_topology(src, plan)
        self.assertEqual(yaml.safe_load(out)["layers"], ["monitoring"])


class FuseBackend(unittest.TestCase):
    def test_replaces_backend_value_only(self):
        plan = RefreshPlan(backend_change=("local-path", "ceph"))
        out = fuse_topology(_SRC, plan)
        self.assertEqual(yaml.safe_load(out)["storage"]["backend"], "ceph")
        self.assertIn("backend: ceph", out)
        self.assertNotIn("backend: local-path", out)
        # le reste intact
        self.assertEqual(yaml.safe_load(out)["catalog"]["status"], "cible")

    def test_preserves_trailing_comment_on_backend_line(self):
        src = _SRC.replace("backend: local-path", "backend: local-path  # léger")
        plan = RefreshPlan(backend_change=("local-path", "ceph"))
        out = fuse_topology(src, plan)
        self.assertIn("backend: ceph", out)
        self.assertIn("# léger", out)


class FuseCombined(unittest.TestCase):
    def test_all_three_and_still_valid_topology(self):
        plan = RefreshPlan(
            nodes_to_add=[NodeChange("node3", ["worker"])],
            layers_to_add=["monitoring"],
            backend_change=("local-path", "ceph"),
        )
        out = fuse_topology(_SRC, plan)
        topo = topology_from_dict(yaml.safe_load(out))  # passe le modèle (valide)
        self.assertIn("node3", topo.worker_nodes)
        self.assertEqual(topo.storage["backend"], "ceph")

    def test_empty_plan_returns_source_unchanged(self):
        self.assertEqual(fuse_topology(_SRC, RefreshPlan()), _SRC)

    def test_idempotent_replay(self):
        plan = RefreshPlan(layers_to_add=["monitoring"])
        once = fuse_topology(_SRC, plan)
        # rejouer le MÊME plan sur le fichier déjà fusionné ne duplique pas
        twice = fuse_topology(once, plan)
        self.assertEqual(yaml.safe_load(twice)["layers"], ["monitoring"])


class FuseFailClosed(unittest.TestCase):
    def test_missing_nodes_key_raises(self):
        plan = RefreshPlan(nodes_to_add=[NodeChange("node3", ["worker"])])
        with self.assertRaises(FuseError):
            fuse_topology("catalog:\n  topology: x\n", plan)

    def test_block_style_layers_raises(self):
        # `layers:` en bloc (pas inline) → on refuse plutôt que corrompre.
        src = _SRC.replace("storage:", "layers:\n  - metrics\nstorage:")
        plan = RefreshPlan(layers_to_add=["monitoring"])
        with self.assertRaises(FuseError):
            fuse_topology(src, plan)


class Prune(unittest.TestCase):
    """#357 : `--prune` retire les couches déclarées-mais-absentes (réellement écrites)."""

    _WITH_LAYERS = _SRC.replace("storage:", "layers: [metrics-server, monitoring]\nstorage:")

    def test_prunable_only_literally_present(self):
        # layers_absent au grain phase ; on ne prune QUE ce qui est écrit dans `layers:`.
        plan = RefreshPlan(layers_absent=["monitoring", "gitops"])  # gitops PAS dans le fichier
        self.assertEqual(prunable_layers(self._WITH_LAYERS, plan), ["monitoring"])

    def test_prunable_empty_when_no_layers_key(self):
        plan = RefreshPlan(layers_absent=["monitoring"])
        self.assertEqual(prunable_layers(_SRC, plan), [])  # pas de clé layers → rien

    def test_prune_removes_layer_keeps_rest(self):
        plan = RefreshPlan(layers_absent=["monitoring"])
        out = prune_topology(self._WITH_LAYERS, plan)
        self.assertEqual(yaml.safe_load(out)["layers"], ["metrics-server"])
        self.assertIn("# commentaire d'en-tête à préserver", out)  # reste intact
        self.assertEqual(yaml.safe_load(out)["catalog"]["status"], "cible")

    def test_prune_to_empty_list(self):
        plan = RefreshPlan(layers_absent=["metrics-server", "monitoring"])
        out = prune_topology(self._WITH_LAYERS, plan)
        self.assertEqual(yaml.safe_load(out)["layers"], [])

    def test_prune_noop_when_nothing_to_remove(self):
        plan = RefreshPlan(layers_absent=["gitops"])  # absent du fichier → no-op
        self.assertEqual(prune_topology(self._WITH_LAYERS, plan), self._WITH_LAYERS)

    def test_prune_does_not_touch_nodes(self):
        # nodes_absent ne déclenche AUCUNE suppression (§3 : absence ≠ retrait voulu).
        plan = RefreshPlan(nodes_absent=["node2"], layers_absent=[])
        self.assertEqual(prune_topology(self._WITH_LAYERS, plan), self._WITH_LAYERS)


if __name__ == "__main__":
    unittest.main()
