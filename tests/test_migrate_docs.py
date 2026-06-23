"""Tests de migrate_docs_to_astro : dérivation du titre + retrait du H1 dupliqué.

Starlight rend le `title:` du frontmatter comme H1 ; conserver le `# H1` du corps le
DUPLIQUE. `strip_first_h1` retire ce premier H1 de la COPIE générée (les sources gardent
le leur). Logique pure, testée sans I/O (ADR 0017).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from migrate_docs_to_astro import first_h1_title, strip_first_h1  # noqa: E402


class FirstH1Title(unittest.TestCase):
    def test_extracts_first_h1(self):
        self.assertEqual(first_h1_title("# Mon titre\n\ncorps"), "Mon titre")

    def test_strips_backticks(self):
        self.assertEqual(first_h1_title("# Le `code` ici\n"), "Le code ici")

    def test_none_when_no_h1(self):
        self.assertIsNone(first_h1_title("## Sous-titre\n\npas de h1"))


class StripFirstH1(unittest.TestCase):
    def test_removes_h1_and_following_blank(self):
        out = strip_first_h1("# Titre\n\nDu contenu.\n")
        self.assertNotIn("# Titre", out)
        self.assertTrue(out.startswith("Du contenu."))

    def test_keeps_subsequent_headings(self):
        # Seul le PREMIER H1 part ; les sous-titres (et un éventuel 2e H1) restent.
        out = strip_first_h1("# Titre\n\n## Section\n\ntexte\n")
        self.assertNotIn("# Titre", out)
        self.assertIn("## Section", out)

    def test_no_h1_unchanged(self):
        src = "## Direct\n\ntexte\n"
        self.assertEqual(strip_first_h1(src), src)

    def test_h1_with_inline_code(self):
        out = strip_first_h1("# Le `truc`\n\nsuite\n")
        self.assertNotIn("Le `truc`", out)
        self.assertTrue(out.startswith("suite"))


if __name__ == "__main__":
    unittest.main()
