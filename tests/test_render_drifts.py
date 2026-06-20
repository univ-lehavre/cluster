"""Tests du rendu pur du registre des drifts (scripts/render_drifts.py, ADR 0017).

unittest stdlib. `render_markdown` est PURE : la liste de drifts est injectée,
aucun accès disque.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from render_drifts import render_markdown  # noqa: E402

_DRIFTS = [
    {
        "id": "L1",
        "campagne": "bootstrap (#127)",
        "portee": "harnais",
        "symptome": "ansible_user\nundefined",
        "cause": "x",
        "correctif": "poser ansible_user",
        "statut": "corrige",
    },
    {
        "id": "L48",
        "campagne": "gitops (#230)",
        "portee": "livrable",
        "symptome": "argocd 0/1",
        "cause": "y",
        "correctif": "egress sans to",
        "statut": "ouvert",
        "issue": "#230",
    },
]


class RenderMarkdown(unittest.TestCase):
    def setUp(self):
        self.md = render_markdown(_DRIFTS)

    def test_has_generated_banner(self):
        self.assertTrue(self.md.startswith("<!-- PAGE GÉNÉRÉE"))

    def test_counts_total(self):
        self.assertIn("**2 drifts** indexés", self.md)

    def test_groups_by_portee_with_titles(self):
        # Une section par portée présente, avec son compteur.
        self.assertIn("## Livrable", self.md)
        self.assertIn("## Harnais", self.md)
        self.assertIn("(1)", self.md)  # 1 drift par portée ici

    def test_flattens_multiline_symptome(self):
        # Le saut de ligne du symptôme L1 est aplati (cellule de tableau).
        self.assertIn("ansible_user undefined", self.md)
        self.assertNotIn("ansible_user\nundefined", self.md)

    def test_open_drift_shows_issue(self):
        self.assertIn("ouvert (#230)", self.md)

    def test_known_statut_icon(self):
        self.assertIn("✅ corrige", self.md)
        self.assertIn("🔴 ouvert", self.md)

    def test_urls_neutralised_for_link_checker(self):
        # Une URL citée dans un symptôme est mise en code inline (sinon lychee
        # tente de la résoudre et échoue). Pas de double backtick.
        md = render_markdown(
            [
                {
                    "id": "L9",
                    "campagne": "x",
                    "portee": "code",
                    "symptome": "clone http://gitea-http/atlas.git échoue",
                    "cause": "y",
                    "correctif": "fix",
                    "statut": "corrige",
                }
            ]
        )
        self.assertIn("`http://gitea-http/atlas.git`", md)
        self.assertNotIn("``", md)


if __name__ == "__main__":
    unittest.main()
