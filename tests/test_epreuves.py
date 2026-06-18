"""Tests du catalogue d'épreuves + filtrage (nestor/epreuves.py, P4).

unittest stdlib. Couvre le filtrage par profil/backend/nœuds/offensif ET deux
garde-fous de PARITÉ anti-dérive (ADR 0058) :
  - catalogue ↔ glob bench/scenarios/NN-*.sh (le code couvre exactement les 29) ;
  - classification offensive ↔ run-all.sh (`is_destructive`/`needs_ssh`).
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.epreuves import (  # noqa: E402
    EPREUVES,
    TERRAIN_OFFENSIF,
    epreuve_jouable,
    filter_epreuves,
)
from nestor.model import topology_from_dict  # noqa: E402

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_SCENARIOS_DIR = os.path.join(_ROOT, "bench", "scenarios")


def _topo(profile="dataops", backend="ceph", nodes=None, kind="prod"):
    nodes = nodes or [
        {"name": "cp1", "roles": ["control"]},
        {"name": "node1", "roles": ["worker"]},
        {"name": "node2", "roles": ["worker"]},
    ]
    return topology_from_dict(
        {
            "catalog": {"topology": "t", "profile": profile},
            "nodes": nodes,
            "storage": {"backend": backend},
            "target_kind": kind,
        }
    )


class Catalogue(unittest.TestCase):
    def test_couvre_les_scenarios_du_glob(self):
        # Garde-fou anti-dérive : EPREUVES doit couvrir EXACTEMENT les fichiers
        # bench/scenarios/NN-*.sh (ajouter un scénario 31 force une entrée ici).
        on_disk = {
            re.match(r"(\d{2})-", f).group(1)
            for f in os.listdir(_SCENARIOS_DIR)
            if re.match(r"\d{2}-.*\.sh$", f)
        }
        in_catalog = {e.num for e in EPREUVES}
        self.assertEqual(in_catalog, on_disk)

    def test_entrees_uniques(self):
        self.assertEqual(len(EPREUVES), 31)
        self.assertEqual(len({e.num for e in EPREUVES}), 31)

    def test_champs_dans_le_vocabulaire(self):
        for e in EPREUVES:
            self.assertIn(e.type, {"unit", "intég", "chaos"})
            self.assertIn(e.profil_min, {"base", "store", "obs", "dataops"})
            self.assertIn(e.backend_req, {None, "ceph"})


class Filtrage(unittest.TestCase):
    def test_dataops_ceph_multi_joue_la_quasi_totalite(self):
        jouables, exclues = filter_epreuves(_topo())
        nums_ex = {e.num for e, _ in exclues}
        # En prod, seuls les offensifs (17/18/19/20/21) sont exclus.
        self.assertEqual(nums_ex, {"17", "18", "19", "20", "21"})
        # 26 jouables : +30 (ha-3cp, jouable au catalogue car multi/local-path ;
        # se SKIP au runtime si le banc n'a pas 3 CP) +31 (contrat, topo-agnostique).
        self.assertEqual(len(jouables), 26)

    def test_backend_local_path_exclut_les_ceph(self):
        _, exclues = filter_epreuves(_topo(backend="local-path"))
        nums_ex = {e.num for e, _ in exclues}
        # 01 (RBD), 03/05/06 (RGW/rebalance), 19 (résilience Ceph) exigent ceph.
        self.assertTrue({"01", "03", "05", "06", "19"}.issubset(nums_ex))

    def test_tous_les_backend_req_ceph_sont_exclus_sur_local_path(self):
        # Garde-fou : chaque épreuve backend_req=ceph DOIT être exclue sur local-path.
        _, exclues = filter_epreuves(_topo(backend="local-path"))
        nums_ex = {e.num for e, _ in exclues}
        ceph_only = {e.num for e in EPREUVES if e.backend_req == "ceph"}
        self.assertTrue(ceph_only.issubset(nums_ex))

    def test_profil_base_exclut_obs_et_dataops(self):
        _, exclues = filter_epreuves(_topo(profile="base", backend="local-path"))
        nums_ex = {e.num for e, _ in exclues}
        # 22/24/25/26 (obs) et 23/27/29 (dataops) hors d'un profil base.
        self.assertTrue({"22", "23", "24", "25", "26", "29"}.issubset(nums_ex))

    def test_mono_noeud_exclut_les_multi(self):
        mono = _topo(nodes=[{"name": "cp1", "roles": ["control", "worker"]}])
        _, exclues = filter_epreuves(mono)
        nums_ex = {e.num for e, _ in exclues}
        # 03/05/14/19 exigent multi-nœuds.
        self.assertTrue({"03", "05", "14", "19"}.issubset(nums_ex))

    def test_offensif_autorise_sur_banc_jetable(self):
        # En target_kind=lima (banc), les offensifs ne sont PLUS exclus pour ce motif.
        jouables, _ = filter_epreuves(_topo(kind="lima"))
        nums = {e.num for e in jouables}
        self.assertIn("20", nums)  # chaos kill pods, agnostique → jouable sur banc
        self.assertIn("21", nums)

    def test_offensif_interdit_en_prod(self):
        ep_17 = next(e for e in EPREUVES if e.num == "17")
        ok, raison = epreuve_jouable(ep_17, _topo(kind="prod"))
        self.assertFalse(ok)
        self.assertIn("offensif", raison)


class ParityRunAll(unittest.TestCase):
    """Parité de la classification offensive avec bench/scenarios/run-all.sh."""

    def test_offensifs_correspondent_a_run_all(self):
        # run-all.sh : terrains offensifs (BANC=1) = 17 18 20 21 (offensif côté
        # cluster) + 19 (chaos VM). Le catalogue marque TERRAIN_OFFENSIF les mêmes.
        offensifs_catalog = {e.num for e in EPREUVES if e.terrain == TERRAIN_OFFENSIF}
        self.assertEqual(offensifs_catalog, {"17", "18", "19", "20", "21"})


if __name__ == "__main__":
    unittest.main()
