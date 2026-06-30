"""Tests de la lecture d'historique + fraîcheur (nestor/history.py, P4).

unittest stdlib. Le test CRITIQUE est la PARITÉ Python↔bash : age_days /
freshness_verdict / seuil_for_target doivent rendre le MÊME verdict que
metro_age_days / metro_freshness_verdict / metro_seuil_for_target (metrology.sh),
sur la même table de cas que bench/unit/metrology.bats — sinon l'outil Python
diverge silencieusement du garde-fou de fraîcheur (check-freshness.sh).
"""

import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.history import (  # noqa: E402
    Run,
    age_days,
    date_from_log_name,
    freshness_verdict,
    last_run_for_target,
    last_run_for_topology,
    latest_run,
    load_runs,
    path_freshness,
    seuil_for_target,
    verdict_for_run,
)

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_REAL_HISTORY = os.path.join(_ROOT, "bench", "lima", "runs-history.yaml")

# Un mini-historique fixture AVEC champ target (le format à venir), pour tester le
# repli +hardening et le filtrage par chemin sans dépendre de l'historique réel.
_FIXTURE = """\
runs:
  - id: r1
    date: 2026-01-01T00:00:00Z
    profil: ceph
    topologie: multi-node-3
    commit: aaa
    target: atlas
  - id: r2
    date: 2026-02-01T00:00:00Z
    profil: ceph
    topologie: multi-node-3
    commit: bbb
    target: atlas+hardening
  - id: r3
    date: 2026-01-15T00:00:00Z
    profil: local-path
    topologie: multi-node-3
    commit: ccc
    target: storage-real
"""

_DAY = 86400


def _tmp(content):
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class AgeDays(unittest.TestCase):
    # Mêmes cas que metrology.bats (metro_age_days).
    def test_7_jours_pile(self):
        self.assertEqual(age_days(0, 7 * _DAY), 7)

    def test_arrondi_entier_inferieur(self):
        self.assertEqual(age_days(0, 700000), 8)  # 8,1 j → 8

    def test_futur_borne_a_zero(self):
        self.assertEqual(age_days(1000, 0), 0)


class FreshnessVerdict(unittest.TestCase):
    # Mêmes cas que metrology.bats (metro_freshness_verdict).
    def test_sous_le_seuil_frais(self):
        self.assertEqual(freshness_verdict(3, 7), "frais")

    def test_au_seuil_pile_frais(self):
        self.assertEqual(freshness_verdict(7, 7), "frais")

    def test_au_dela_perime(self):
        self.assertEqual(freshness_verdict(8, 7), "perime")


class SeuilForTarget(unittest.TestCase):
    # Mêmes cadences que metrology.bats (metro_seuil_for_target, ADR 0045 §6).
    def test_atlas_7(self):
        self.assertEqual(seuil_for_target("atlas"), 7)

    def test_storage_real_30(self):
        self.assertEqual(seuil_for_target("storage-real"), 30)

    def test_cluster_dataops_90(self):
        self.assertEqual(seuil_for_target("cluster-dataops"), 90)

    def test_inconnu_retombe_sur_defaut(self):
        self.assertEqual(seuil_for_target("autre-chemin"), 7)

    def test_hardening_replie_sur_base(self):
        self.assertEqual(seuil_for_target("atlas+hardening"), 7)
        self.assertEqual(seuil_for_target("storage-real+hardening"), 30)

    def test_surcharge_env(self):
        os.environ["SEUIL_STORAGE_REAL"] = "99"
        self.addCleanup(os.environ.pop, "SEUIL_STORAGE_REAL", None)
        self.assertEqual(seuil_for_target("storage-real"), 99)


class LoadRuns(unittest.TestCase):
    def test_real_history_parses(self):
        runs = load_runs(_REAL_HISTORY)
        self.assertGreaterEqual(len(runs), 7)
        # `target` est optionnel : les entrées anciennes n'en ont pas (None), les
        # récentes (consignées par record_full_run avec TARGET) en portent un (str).
        self.assertTrue(all(r.target is None or isinstance(r.target, str) for r in runs))
        self.assertTrue(all(r.date for r in runs))

    def test_empty_or_missing_runs_key(self):
        path = _tmp("# vide\n")
        self.addCleanup(os.unlink, path)
        self.assertEqual(load_runs(path), [])

    def test_objectif_lisible(self):
        runs = load_runs(_REAL_HISTORY)
        # exig. 11 : l'objectif d'infra = profil / topologie.
        self.assertIn(" / ", runs[0].objectif)


class TargetFiltering(unittest.TestCase):
    def setUp(self):
        self.path = _tmp(_FIXTURE)
        self.addCleanup(os.unlink, self.path)
        self.runs = load_runs(self.path)

    def test_atlas_capte_le_run_hardening(self):
        # atlas+hardening (r2) se replie sur atlas → c'est le plus récent.
        run = last_run_for_target(self.runs, "atlas")
        self.assertEqual(run.id, "r2")

    def test_storage_real_isole_de_atlas(self):
        run = last_run_for_target(self.runs, "storage-real")
        self.assertEqual(run.id, "r3")

    def test_chemin_sans_run(self):
        self.assertIsNone(last_run_for_target(self.runs, "cluster-dataops"))

    def test_historique_mixte_avec_et_sans_target(self):
        # Rétrocompat graduelle : certains runs portent un target, d'autres non.
        # last_run_for_target ne doit retenir QUE ceux du chemin demandé.
        mixte = _tmp(
            "runs:\n"
            "  - id: vieux\n    date: 2026-01-01T00:00:00Z\n    profil: ceph\n"
            "  - id: neuf\n    date: 2026-02-01T00:00:00Z\n    profil: ceph\n    target: atlas\n"
        )
        self.addCleanup(os.unlink, mixte)
        runs = load_runs(mixte)
        self.assertEqual(last_run_for_target(runs, "atlas").id, "neuf")
        self.assertIsNone(last_run_for_target(runs, "storage-real"))

    def test_latest_run_global(self):
        # latest_run = dernier EN ORDRE DE FICHIER (comme metro_last_date : tail -1
        # sur un fichier supposé chronologique). r3 est le dernier listé.
        self.assertEqual(latest_run(self.runs).id, "r3")


class TopologyFiltering(unittest.TestCase):
    """last_run_for_topology : match par NOM de stack, JAMAIS de retombée globale."""

    def setUp(self):
        self.path = _tmp(_FIXTURE)
        self.addCleanup(os.unlink, self.path)
        self.runs = load_runs(self.path)

    def test_matches_exact_topology(self):
        # Tous portent topologie multi-node-3 ; comme last_run_for_target, on retient
        # le DERNIER en ordre de fichier (supposé chronologique) → r3.
        run = last_run_for_topology(self.runs, "multi-node-3")
        self.assertEqual(run.id, "r3")

    def test_unknown_topology_is_none_not_global(self):
        # Une stack jamais montée → None (PAS le dernier run global) : c'est ce qui
        # empêche `preview` de mentir (bug « preview faux avec 1cp »).
        self.assertIsNone(last_run_for_topology(self.runs, "1cp"))


class Verdict(unittest.TestCase):
    def test_jamais_si_aucun_run(self):
        etat, msg = verdict_for_run(None, "atlas", 0)
        self.assertEqual(etat, "jamais")
        self.assertIn("pas de run frais", msg)

    def test_frais_sous_seuil(self):
        runs = load_runs(_tmp(_FIXTURE))
        run = last_run_for_target(runs, "atlas")  # 2026-02-01
        now = int(dt.datetime(2026, 2, 4, tzinfo=dt.UTC).timestamp())
        etat, _ = verdict_for_run(run, "atlas", now)
        self.assertEqual(etat, "frais")

    def test_perime_au_dela(self):
        runs = load_runs(_tmp(_FIXTURE))
        run = last_run_for_target(runs, "atlas")  # 2026-02-01, seuil atlas 7 j
        now = int(dt.datetime(2026, 3, 1, tzinfo=dt.UTC).timestamp())
        etat, msg = verdict_for_run(run, "atlas", now)
        self.assertEqual(etat, "perime")
        self.assertIn("pas de run frais", msg)


class DateFromLogName(unittest.TestCase):
    """Repli ADR 0042 §4 : date ISO extraite d'un nom de log `runs/<date>-*.log`."""

    def test_extrait_la_date_prefixe(self):
        self.assertEqual(
            date_from_log_name("2026-06-08-monitoring-ceph.log"), "2026-06-08T00:00:00Z"
        )

    def test_chemin_complet_aussi(self):
        self.assertEqual(
            date_from_log_name("bench/lima/runs/2026-01-15-dataops.log"), "2026-01-15T00:00:00Z"
        )

    def test_prefixe_non_date_renvoie_none(self):
        self.assertIsNone(date_from_log_name("rapport-final.log"))
        self.assertIsNone(date_from_log_name("2026-13-99-mauvaise-date.log"))  # mois/jour invalide

    def test_nom_trop_court_renvoie_none(self):
        self.assertIsNone(date_from_log_name("x.log"))


class PathFreshness(unittest.TestCase):
    """Verdict par chemin (ex-evaluer_chemin de check-freshness.sh) : frais/perime/absent."""

    def _run(self, date):
        return Run(id="r", date=date)

    def test_frais_sous_le_seuil(self):
        # atlas, seuil 7 j ; run d'il y a 3 j.
        now = int(dt.datetime(2026, 1, 10, tzinfo=dt.UTC).timestamp())
        etat, ligne = path_freshness(self._run("2026-01-07T00:00:00Z"), "atlas", now)
        self.assertEqual(etat, "frais")
        self.assertIn("✓ atlas", ligne)
        self.assertIn("≤ 7 j", ligne)

    def test_perime_au_dela_du_seuil(self):
        # atlas, seuil 7 j ; run d'il y a 30 j.
        now = int(dt.datetime(2026, 2, 1, tzinfo=dt.UTC).timestamp())
        etat, ligne = path_freshness(self._run("2026-01-01T00:00:00Z"), "atlas", now)
        self.assertEqual(etat, "perime")
        self.assertIn("✗ atlas", ligne)
        self.assertIn("PÉRIMÉ", ligne)

    def test_absent_sans_run(self):
        etat, ligne = path_freshness(None, "storage-real", 0)
        self.assertEqual(etat, "absent")
        self.assertIn("aucun run consigné", ligne)
        self.assertIn("seuil 30 j", ligne)  # storage-real

    def test_absent_date_illisible(self):
        etat, ligne = path_freshness(self._run("pas-une-date"), "atlas", 0)
        self.assertEqual(etat, "absent")
        self.assertIn("illisible", ligne)


if __name__ == "__main__":
    unittest.main()
