"""Tests du garde-fou check-gouvernance (ADR 0060 / ADR 0017 : logique testée).

unittest (stdlib). Les fonctions testées sont PURES : le contenu (texte ADR/plan,
entrée de drift) est injecté, aucun accès disque/git.

Lancé par `python3 -m unittest discover tests` (cible `test:python` + CI).
"""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_gouvernance import (  # noqa: E402
    adr_has_checklist,
    adr_number_from_filename,
    days_since,
    drift_issue_ok,
    extract_stats_bullets,
    is_living_plan,
    normalize_statut,
    parse_adr_statut,
    parse_index_statuts,
    parse_plan_etat,
    plan_has_suivi,
    plan_refs_adr,
)


class AdrNumber(unittest.TestCase):
    def test_extracts_number(self):
        self.assertEqual(adr_number_from_filename("0057-gouvernance.md"), "0057")
        self.assertEqual(adr_number_from_filename("docs/decisions/0001-x.md"), "0001")

    def test_non_adr_returns_none(self):
        self.assertIsNone(adr_number_from_filename("README.md"))
        self.assertIsNone(adr_number_from_filename("plan-x.md"))


class AdrStatut(unittest.TestCase):
    def test_reads_first_word_after_heading(self):
        text = "# 0001 — X\n\n## Statut\n\nAccepted (2026-01-01).\n\n## Conséquences\n"
        self.assertEqual(parse_adr_statut(text), "Accepted")

    def test_proposed(self):
        text = "## Statut\n\nProposed (2026-06-12). **Précise**\n"
        self.assertEqual(parse_adr_statut(text), "Proposed")

    def test_superseded_with_suffix(self):
        text = "## Statut\nSuperseded by 0049.\n"
        self.assertEqual(parse_adr_statut(text), "Superseded")

    def test_missing_statut(self):
        self.assertIsNone(parse_adr_statut("# 0001\n\n## Contexte\n\nblah\n"))

    def test_normalize_keeps_first_word(self):
        self.assertEqual(normalize_statut("Superseded by 0049"), "Superseded")
        self.assertIsNone(normalize_statut(None))


class AdrChecklist(unittest.TestCase):
    def test_detects_palier_table_row(self):
        self.assertTrue(adr_has_checklist("| **P0** | socle | 1-5 |\n"))
        self.assertTrue(adr_has_checklist("| P7 | étendre | 4 |\n"))

    def test_detects_checkbox(self):
        self.assertTrue(adr_has_checklist("- [ ] faire X\n"))
        self.assertTrue(adr_has_checklist("- [x] fait\n"))

    def test_detects_palier_column(self):
        self.assertTrue(adr_has_checklist("| Palier | État |\n"))

    def test_clean_adr_has_no_checklist(self):
        text = "## Décision\n\nOn fait X parce que Y.\n\n## Conséquences\n\n- gain\n"
        self.assertFalse(adr_has_checklist(text))

    def test_prose_citing_palier_is_not_checklist(self):
        # « P6 #23) » dans une phrase ne doit PAS être pris pour un palier (faux positif réel).
        self.assertFalse(adr_has_checklist("Le durcissement audité (P6 #23) est posé.\n"))
        self.assertFalse(adr_has_checklist("- exposition réseau (palier P3 du plan)\n"))


class PlanEtat(unittest.TestCase):
    def test_reads_etat_value(self):
        text = "# Plan\n\n## État\n\n> **État : Actif** (depuis 2026-06-13) · …\n"
        self.assertEqual(parse_plan_etat(text), "Actif")

    def test_acheve_with_accent(self):
        text = "## État\n\n> **État : Achevé** (2026-06-13)\n"
        self.assertEqual(parse_plan_etat(text), "Achevé")

    def test_missing_etat_heading(self):
        self.assertIsNone(parse_plan_etat("# Plan\n\n## Objectif\n\nfaire X\n"))

    def test_heading_without_value(self):
        # en-tête présent mais pas de `**État : …**`
        self.assertIsNone(parse_plan_etat("## État\n\ntexte libre\n"))

    def test_suivi_and_adr_ref(self):
        text = "## Suivi\n\nblah [ADR 0054](../decisions/0054-x.md)\n"
        self.assertTrue(plan_has_suivi(text))
        self.assertTrue(plan_refs_adr(text))
        self.assertTrue(plan_refs_adr("met en œuvre ADR 0026\n"))
        self.assertFalse(plan_refs_adr("aucune référence ici\n"))


class LivingPlan(unittest.TestCase):
    def test_plan_theme_is_living(self):
        self.assertTrue(is_living_plan("docs/plans/plan-dagster.md"))

    def test_dated_audit_is_not_living(self):
        self.assertFalse(is_living_plan("docs/plans/2026-06-04-audit-realignement.md"))


class DriftIssue(unittest.TestCase):
    def test_corrige_needs_no_issue(self):
        self.assertTrue(drift_issue_ok({"id": "L1", "statut": "corrige"}))

    def test_caduc_needs_no_issue(self):
        self.assertTrue(drift_issue_ok({"id": "L1", "statut": "caduc"}))

    def test_ouvert_with_issue_ok(self):
        self.assertTrue(drift_issue_ok({"id": "L1", "statut": "ouvert", "issue": "#251"}))

    def test_ouvert_without_issue_fails(self):
        self.assertFalse(drift_issue_ok({"id": "L1", "statut": "ouvert"}))

    def test_ouvert_with_todo_fails(self):
        self.assertFalse(drift_issue_ok({"id": "L1", "statut": "ouvert", "issue": "TODO"}))

    def test_en_cours_needs_issue(self):
        self.assertFalse(drift_issue_ok({"id": "L1", "statut": "en-cours"}))
        self.assertTrue(drift_issue_ok({"id": "L1", "statut": "en-cours", "issue": "#232"}))


class IndexStatuts(unittest.TestCase):
    def test_parses_table_rows(self):
        index = (
            "| #    | Titre | Statut |\n"
            "| ---- | ----- | ------ |\n"
            "| 0001 | [X](0001-x.md) | Accepted |\n"
            "| 0017 | [Y](0017-y.md) | Superseded by 0049 |\n"
        )
        out = parse_index_statuts(index)
        self.assertEqual(out["0001"], "Accepted")
        self.assertEqual(out["0017"], "Superseded by 0049")

    def test_ignores_separator_and_header(self):
        out = parse_index_statuts("| #    | Titre | Statut |\n| ---- | --- | --- |\n")
        self.assertEqual(out, {})


class DaysSince(unittest.TestCase):
    def test_counts_days(self):
        today = dt.date(2026, 6, 13)
        self.assertEqual(days_since("2026-06-03", today), 10)

    def test_invalid_date(self):
        self.assertIsNone(days_since("pas-une-date", dt.date(2026, 6, 13)))


class ExtractStatsBullets(unittest.TestCase):
    _BLOCK = (
        "# Titre\n\n"
        "<!-- STATS:DEBUT — bloc régénéré -->\n\n"
        "- **88 ADR** (80 Accepted, 6 Proposed, 2 Superseded)\n"
        "- **8 plans** vivants (4 Achevé)\n\n"
        "<!-- STATS:FIN -->\n\n"
        "## Suite\n"
        "- une puce hors bloc, à ignorer\n"
    )

    def test_extracts_only_bullets_between_markers(self):
        self.assertEqual(
            extract_stats_bullets(self._BLOCK),
            [
                "- **88 ADR** (80 Accepted, 6 Proposed, 2 Superseded)",
                "- **8 plans** vivants (4 Achevé)",
            ],
        )

    def test_missing_marker_returns_none(self):
        self.assertIsNone(extract_stats_bullets("# Titre\n\n- pas de marqueurs\n"))

    def test_empty_block(self):
        self.assertEqual(extract_stats_bullets("<!-- STATS:DEBUT -->\n\n<!-- STATS:FIN -->\n"), [])


if __name__ == "__main__":
    unittest.main()
