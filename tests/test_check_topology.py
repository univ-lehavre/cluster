"""Tests du garde-fou check-topology (ADR 0096 / ADR 0017 : logique testée).

unittest (stdlib) — c'est ce qu'utilise le dépôt (`test:python` =
`python -m unittest discover -s tests`). Les fonctions testées sont PURES : on leur
injecte des composants/imports/signaux, donc aucun accès disque pour le cœur.

Couvre les 4 familles de l'ADR 0096 §2 :
  1. Composant → rôle (répertoire + import).
  2. Rôle → composant — LE notifieur « Marquez oublié » : un composant retiré du
     graphe (rouge) ET le cas multi-composant (`platform-cnpg`→4) où un SEUL
     composant disparaît.
  3. Signal → feuille du graphe (résolution exacte/préfixe/ciblé, ambiguïté, non-feuille).
  4. Cohérence interne (cycle, arête inconnue, jeton non résolu) — pour les deux backends.

Deux preuves d'ÉTAT RÉEL en plus (subprocess) : le check passe VERT sur l'état
actuel, ET la régression « Marquez oublié » est ROUGE (composant retiré du graphe).

Lancé par `python3 -m unittest discover -s tests` (cible `test:python` + CI).
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from check_topology import (  # noqa: E402
    ERROR,
    WARNING,
    Finding,
    check_component_role,
    check_graph_internal,
    check_phase_signal,
    check_role_components,
    collect_role_imports,
    load_yaml_docs,
    phase_leaves,
    resolve_signal_component,
    role_to_components,
)

from nestor import graph  # noqa: E402

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SCRIPT = os.path.join(_REPO, "scripts", "check_topology.py")


class FakeComponent:
    """Composant minimal pour les tests purs (mêmes attributs que graph.Component)."""

    def __init__(self, name, role=None):
        self.name = name
        self.role = role


def has_error(findings):
    return any(f.level == ERROR for f in findings)


# ─────────────────────────────────────────────────────────────────────────────
# Finding (dataclass-like)
# ─────────────────────────────────────────────────────────────────────────────
class FindingEquality(unittest.TestCase):
    def test_equality_and_hash(self):
        a = Finding(ERROR, "x")
        b = Finding(ERROR, "x")
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertNotEqual(a, Finding(WARNING, "x"))


# ─────────────────────────────────────────────────────────────────────────────
# role_to_components — mapping NON 1:1
# ─────────────────────────────────────────────────────────────────────────────
class RoleToComponents(unittest.TestCase):
    def test_aggregates_multi_component_role(self):
        comps = [
            FakeComponent("cnpg-operator", "platform-cnpg"),
            FakeComponent("cnpg-cluster-pg", "platform-cnpg"),
            FakeComponent("registry", "platform-registry"),
            FakeComponent("bootstrap", None),  # socle, pas de rôle
        ]
        index = role_to_components(comps)
        self.assertEqual(set(index["platform-cnpg"]), {"cnpg-operator", "cnpg-cluster-pg"})
        self.assertEqual(index["platform-registry"], ["registry"])
        self.assertNotIn(None, index)

    def test_real_graph_s3_bucket_carries_three(self):
        index = role_to_components(graph.COMPONENTS.values())
        self.assertEqual(
            set(index["platform-s3-bucket"]),
            {"s3-backing-loki", "s3-backing-cnpg", "s3-backing-mlflow"},
        )
        self.assertEqual(len(index["platform-cnpg"]), 4)


# ─────────────────────────────────────────────────────────────────────────────
# collect_role_imports — scan de l'arbre YAML (playbook ET rôle→rôle)
# ─────────────────────────────────────────────────────────────────────────────
class CollectRoleImports(unittest.TestCase):
    def test_playbook_top_level_list_of_plays(self):
        # Un playbook Ansible est une LISTE de plays au top-level.
        playbook = [
            {
                "name": "play",
                "hosts": "localhost",
                "tasks": [
                    {"ansible.builtin.import_role": {"name": "platform-registry"}},
                    {"ansible.builtin.import_role": {"name": "platform-cnpg"}},
                ],
            }
        ]
        self.assertEqual(
            collect_role_imports([playbook]),
            {"platform-registry", "platform-cnpg"},
        )

    def test_nested_include_role_in_block(self):
        # include_role imbriqué (block) — le cas rôle→rôle de platform-s3-bucket.
        role_tasks = [
            {
                "name": "guarded",
                "block": [
                    {"ansible.builtin.include_role": {"name": "platform-s3-bucket"}},
                ],
            }
        ]
        self.assertEqual(collect_role_imports([role_tasks]), {"platform-s3-bucket"})

    def test_short_keys_without_collection_prefix(self):
        docs = [[{"tasks": [{"import_role": {"name": "platform-loki"}}]}]]
        self.assertEqual(collect_role_imports(docs), {"platform-loki"})

    def test_load_yaml_docs_keeps_lists(self):
        # Régression : un top-level liste (playbook) ne doit PAS être filtré.
        docs = load_yaml_docs("- name: play\n  hosts: localhost\n")
        self.assertEqual(len(docs), 1)
        self.assertIsInstance(docs[0], list)


# ─────────────────────────────────────────────────────────────────────────────
# FAMILLE 1 — Composant → rôle
# ─────────────────────────────────────────────────────────────────────────────
class CheckComponentRole(unittest.TestCase):
    def test_socle_component_no_role_is_ok(self):
        comp = FakeComponent("bootstrap", None)
        out = check_component_role(comp, role_dir_exists=False, imported_roles=set())
        self.assertEqual(out, [])

    def test_role_dir_and_import_present_is_ok(self):
        comp = FakeComponent("registry", "platform-registry")
        out = check_component_role(comp, True, {"platform-registry"})
        self.assertEqual(out, [])

    def test_missing_role_dir_is_error(self):
        comp = FakeComponent("registry", "platform-registry")
        out = check_component_role(comp, False, {"platform-registry"})
        self.assertTrue(has_error(out))
        self.assertIn("n'a pas de répertoire", out[0].message)

    def test_role_not_imported_is_error(self):
        comp = FakeComponent("registry", "platform-registry")
        out = check_component_role(comp, True, set())
        self.assertTrue(has_error(out))
        self.assertIn("AUCUN", out[0].message)


# ─────────────────────────────────────────────────────────────────────────────
# FAMILLE 2 — Rôle → composant (LE notifieur « Marquez oublié »)
# ─────────────────────────────────────────────────────────────────────────────
class CheckRoleComponents(unittest.TestCase):
    def test_role_with_referenced_component_is_ok(self):
        r2c = {"platform-marquez": ["marquez"]}
        out = check_role_components("platform-marquez", r2c, {"marquez", "dagster"})
        self.assertEqual(out, [])

    def test_role_with_no_component_is_error_marquez_oublie(self):
        # Le rôle est importé mais aucun Component ne le porte → rôle hors graphe.
        out = check_role_components("platform-ghost", {}, set())
        self.assertTrue(has_error(out))
        self.assertIn("AUCUN Component", out[0].message)

    def test_multi_component_role_one_removed_is_error(self):
        # platform-cnpg porte 4 composants ; on en RETIRE un du catalogue
        # (referenced_components) → le rôle masquerait l'oubli sans cette vérif.
        r2c = {
            "platform-cnpg": [
                "cnpg-operator",
                "barman-plugin",
                "cnpg-secrets",
                "cnpg-cluster-pg",
            ]
        }
        referenced = {"cnpg-operator", "barman-plugin", "cnpg-secrets"}  # cnpg-cluster-pg retiré
        out = check_role_components("platform-cnpg", r2c, referenced)
        self.assertTrue(has_error(out))
        self.assertIn("cnpg-cluster-pg", out[0].message)

    def test_multi_component_role_all_present_is_ok(self):
        r2c = {"platform-s3-bucket": ["s3-backing-loki", "s3-backing-cnpg", "s3-backing-mlflow"]}
        referenced = set(r2c["platform-s3-bucket"])
        self.assertEqual(check_role_components("platform-s3-bucket", r2c, referenced), [])


# ─────────────────────────────────────────────────────────────────────────────
# FAMILLE 3 — Signal → feuille du graphe
# ─────────────────────────────────────────────────────────────────────────────
class PhaseLeaves(unittest.TestCase):
    def test_dataops_has_two_leaves(self):
        leaves = set(phase_leaves("dataops"))
        self.assertIn("dagster", leaves)
        self.assertIn("marquez", leaves)
        # registry/cnpg-* ne sont PAS feuilles (dagster/marquez en dépendent).
        self.assertNotIn("registry", leaves)
        self.assertNotIn("cnpg-cluster-pg", leaves)


class ResolveSignalComponent(unittest.TestCase):
    def test_exact_name(self):
        self.assertEqual(resolve_signal_component("dataops", "marquez", "marquez"), ["marquez"])

    def test_name_prefix(self):
        # argocd-server → argocd (préfixe).
        self.assertEqual(resolve_signal_component("gitops", "argocd-server", "argocd"), ["argocd"])

    def test_targeted_resource(self):
        # sc cible « …storageclass.storage.k8s.io rook-ceph-block-replicated ».
        self.assertEqual(resolve_signal_component("sc", "rook-ceph-block-replicated", None), ["sc"])
        # gitops-seed cible « …applications.argoproj.io atlas-workflows ».
        self.assertEqual(
            resolve_signal_component("gitops-seed", "atlas-workflows", "argocd"),
            ["gitops-seed"],
        )

    def test_namespace_owner_fallback(self):
        self.assertEqual(resolve_signal_component("ceph", "rook-ceph", "rook-ceph"), ["ceph"])

    def test_unknown_resolves_to_nothing(self):
        self.assertEqual(resolve_signal_component("dataops", "inexistant", "nowhere"), [])


class CheckPhaseSignal(unittest.TestCase):
    def test_dataops_signal_marquez_is_a_leaf_ok(self):
        # Le BON signal (marquez, la feuille terminale) → vert.
        self.assertEqual(check_phase_signal("dataops", "marquez", "marquez"), [])

    def test_dataops_signal_dagster_also_leaf_ok(self):
        # dagster est AUSSI une feuille de dataops → pas une erreur de feuille.
        self.assertEqual(check_phase_signal("dataops", "dagster", "dagster"), [])

    def test_signal_pointing_non_leaf_is_error(self):
        # registry est dans dataops mais N'EST PAS une feuille (dagster en dépend).
        out = check_phase_signal("dataops", "registry", "registry")
        self.assertTrue(has_error(out))
        self.assertIn("feuille", out[0].message)

    def test_signal_unresolved_is_error(self):
        out = check_phase_signal("dataops", "inexistant", "nowhere")
        self.assertTrue(has_error(out))

    def test_all_real_layer_signals_resolve_to_a_leaf(self):
        # Garde-fou d'état réel : chaque signal de phase roundtrip résout vers une
        # unique feuille, sans erreur (l'état sain).
        import topology

        for phase, (_kind, name, ns, _ready) in topology._LAYER_SIGNAL.items():
            if phase not in graph.ROUNDTRIP_PHASES:
                continue
            with self.subTest(phase=phase):
                self.assertEqual(check_phase_signal(phase, name, ns), [])


# ─────────────────────────────────────────────────────────────────────────────
# FAMILLE 4 — Cohérence interne du graphe
# ─────────────────────────────────────────────────────────────────────────────
class CheckGraphInternal(unittest.TestCase):
    def test_real_graph_is_internally_coherent_both_backends(self):
        for backend in (graph.CEPH, graph.LOCAL_PATH):
            with self.subTest(backend=backend):
                self.assertEqual(check_graph_internal(backend), [])


# ─────────────────────────────────────────────────────────────────────────────
# PREUVES D'ÉTAT RÉEL (subprocess) — vert sur l'état sain, rouge sur « Marquez oublié »
# ─────────────────────────────────────────────────────────────────────────────
class RealStateGreen(unittest.TestCase):
    def test_check_passes_on_current_state(self):
        # Le check DOIT sortir 0 sur l'état actuel du dépôt (graphe ↔ Ansible alignés).
        proc = subprocess.run(
            [sys.executable, _SCRIPT],
            cwd=_REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=f"stderr:\n{proc.stderr}")
        self.assertIn("OK", proc.stdout)


class MarquezOublieRegression(unittest.TestCase):
    """Régression « Marquez oublié » : un composant retiré du graphe → ROUGE.

    On lance le check dans un sous-processus avec un nestor/graph.py MONKEYPATCHÉ
    (composant `marquez` retiré du catalogue) : la famille 2 doit alors crier que
    `platform-marquez` est importé mais référencé par aucun composant. C'est la
    régression exacte que l'ADR 0096 veut attraper.
    """

    def test_removed_component_makes_check_red(self):
        injected = (
            "import sys, os;"
            f"sys.path.insert(0, {_REPO!r});"
            f"sys.path.insert(0, {os.path.join(_REPO, 'scripts')!r});"
            "from nestor import graph;"
            # Retire 'marquez' du catalogue (la régression « Marquez oublié »).
            "graph.COMPONENTS.pop('marquez', None);"
            "graph.COMPONENT_ALL = tuple(n for n in graph.COMPONENT_ALL if n != 'marquez');"
            "import check_topology as ct;"
            "sys.exit(ct.main())"
        )
        proc = subprocess.run(
            [sys.executable, "-c", injected],
            cwd=_REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1, msg=f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        # platform-marquez est toujours importé par dataops.yaml mais plus référencé.
        self.assertIn("platform-marquez", proc.stderr)


if __name__ == "__main__":
    unittest.main()
