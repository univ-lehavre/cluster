"""Tests de nestor/prod_target.py (ADR 0090 / ADR 0017 : logique pure testée).

Aucun I/O cluster : on teste la résolution kubeconfig, la décision de rapatriement,
le message de confirmation et le parsing de réponse — tout pur.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nestor.prod_target import (  # noqa: E402
    TargetConfirmation,
    add_kubeconfig_field,
    default_kubeconfig_path,
    is_affirmative,
    needs_repatriation,
    resolve_kubeconfig,
)

_ROOT = "/repo"  # racine fictive de test


class DefaultPath(unittest.TestCase):
    def test_convention_per_stack_in_repo(self):
        # ADR 0102 : in-repo `<racine>/.kubeconfigs/<stack>.config` (plus ~/.kube/).
        self.assertEqual(
            default_kubeconfig_path("dirqual", repo_root=_ROOT),
            "/repo/.kubeconfigs/dirqual.config",
        )

    def test_banc_and_prod_same_convention(self):
        # banc ET prod suivent la MÊME convention (fin du dédoublement).
        self.assertEqual(
            default_kubeconfig_path("banc", repo_root=_ROOT), "/repo/.kubeconfigs/banc.config"
        )


class ResolveKubeconfig(unittest.TestCase):
    def test_env_wins(self):
        # KUBECONFIG exporté = intention explicite → prime sur tout (ADR 0053/0065).
        got = resolve_kubeconfig(
            env_kubeconfig="/tmp/k", declared="~/.kube/x.config", stack="dirqual", repo_root=_ROOT
        )
        self.assertEqual(got, "/tmp/k")

    def test_declared_when_no_env(self):
        # `declared` = override rare (chemin custom hors convention).
        got = resolve_kubeconfig(
            env_kubeconfig=None, declared="/custom/k.config", stack="dirqual", repo_root=_ROOT
        )
        self.assertEqual(got, "/custom/k.config")

    def test_default_when_nothing_is_in_repo(self):
        got = resolve_kubeconfig(
            env_kubeconfig=None, declared=None, stack="dirqual", repo_root=_ROOT
        )
        self.assertEqual(got, "/repo/.kubeconfigs/dirqual.config")

    def test_never_home_kube_config_garde_0053(self):
        # ANTI-RÉGRESSION garde d'isolation (ADR 0053) : le cran par défaut ne peut JAMAIS
        # être `~/.kube/config` (la prod ambiante du poste). Quel que soit le nom de stack,
        # sans env ni declared, le chemin est TOUJOURS in-repo sous .kubeconfigs/.
        for stack in ("banc", "dirqual", "config", "default", ""):
            got = resolve_kubeconfig(
                env_kubeconfig=None, declared=None, stack=stack, repo_root=_ROOT
            )
            self.assertTrue(got.startswith("/repo/.kubeconfigs/"), f"stack={stack!r} → {got}")
            self.assertNotIn("/.kube/config", got)


class Confirmation(unittest.TestCase):
    def test_prompt_shows_endpoint_and_nodes(self):
        c = TargetConfirmation(
            stack="dirqual", endpoint="https://10.67.2.11:6443", nodes=["dirqual1", "dirqual2"]
        )
        msg = c.prompt()
        self.assertIn("dirqual", msg)
        self.assertIn("10.67.2.11", msg)
        self.assertIn("dirqual1", msg)
        self.assertTrue(c.reachable)

    def test_prompt_handles_unreachable(self):
        c = TargetConfirmation(stack="dirqual", endpoint=None, nodes=[])
        msg = c.prompt()
        self.assertIn("aucun nœud", msg)
        self.assertFalse(c.reachable)


class NeedsRepatriation(unittest.TestCase):
    def test_absent_file_needs_repatriation(self):
        self.assertTrue(
            needs_repatriation(kubeconfig_path="/nope/absent.config", reaches_api=False)
        )

    def test_present_but_unreachable_needs_repatriation(self):
        # Fichier présent mais API injoignable (forward mort / cluster down) → rapatrier.
        self.assertTrue(needs_repatriation(kubeconfig_path=__file__, reaches_api=False))

    def test_present_and_reachable_ok(self):
        self.assertFalse(needs_repatriation(kubeconfig_path=__file__, reaches_api=True))


class AddKubeconfigField(unittest.TestCase):
    def test_appends_when_absent(self):
        src = "catalog:\n  topology: dirqual\ntarget_kind: prod\n"
        out = add_kubeconfig_field(src, "~/.kube/dirqual.config")
        self.assertIn("kubeconfig: ~/.kube/dirqual.config", out)
        self.assertIn("target_kind: prod", out)  # le reste préservé

    def test_replaces_commented_placeholder(self):
        # un placeholder `# kubeconfig: …` (comme dans socle.example) est remplacé,
        # pas dupliqué.
        src = "target_kind: prod\n# kubeconfig: ~/.kube/socle.config\n"
        out = add_kubeconfig_field(src, "~/.kube/dirqual.config")
        self.assertEqual(out.count("kubeconfig:"), 1)
        self.assertIn("kubeconfig: ~/.kube/dirqual.config", out)
        self.assertNotIn("# kubeconfig:", out)

    def test_replaces_active_line(self):
        src = "target_kind: prod\nkubeconfig: ~/.kube/old.config\n"
        out = add_kubeconfig_field(src, "~/.kube/new.config")
        self.assertEqual(out.count("kubeconfig:"), 1)
        self.assertIn("~/.kube/new.config", out)
        self.assertNotIn("old.config", out)

    def test_idempotent(self):
        src = "target_kind: prod\n"
        once = add_kubeconfig_field(src, "~/.kube/dirqual.config")
        twice = add_kubeconfig_field(once, "~/.kube/dirqual.config")
        self.assertEqual(once, twice)

    def test_preserves_comments(self):
        src = "# topo réelle (ADR 0023)\ncatalog:\n  topology: dirqual\ntarget_kind: prod\n"
        out = add_kubeconfig_field(src, "~/.kube/dirqual.config")
        self.assertIn("# topo réelle (ADR 0023)", out)


class Affirmative(unittest.TestCase):
    def test_yes_variants(self):
        for a in ("y", "Y", "yes", "o", "OUI", " oui "):
            self.assertTrue(is_affirmative(a), a)

    def test_default_no(self):
        for a in ("", "n", "non", "nope", "maybe"):
            self.assertFalse(is_affirmative(a), a)


if __name__ == "__main__":
    unittest.main()
