"""Tests du catalogue d'épreuves + filtrage (nestor/epreuves.py, P4).

unittest stdlib. Couvre le filtrage par profil/backend/nœuds/offensif ET deux
garde-fous de PARITÉ anti-dérive (ADR 0058) :
  - catalogue ↔ glob bench/scenarios/NN-*.sh (le code couvre exactement les 34) ;
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


def _topo(profile="dataops", backend="ceph", nodes=None, terrain="baremetal"):
    nodes = nodes or [
        {"name": "cp1", "roles": ["control"]},
        {"name": "node1", "roles": ["worker"]},
        {"name": "node2", "roles": ["worker"]},
    ]
    return topology_from_dict(
        {
            "catalog": {"topology": "t", "profile": profile, "terrain": terrain},
            "nodes": nodes,
            "storage": {"backend": backend},
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
        self.assertEqual(len(EPREUVES), 34)
        self.assertEqual(len({e.num for e in EPREUVES}), 34)

    def test_champs_dans_le_vocabulaire(self):
        for e in EPREUVES:
            self.assertIn(e.type, {"unit", "intég", "chaos"})
            self.assertIn(e.profil_min, {"base", "store", "obs", "dataops"})
            self.assertIn(e.backend_req, {None, "ceph"})
            self.assertIn(e.statut, {"actif", "caduc"})
            # Un caduc DOIT tracer sa raison (honnêteté des Runs, ADR 0052) ;
            # un actif n'en a pas.
            if e.statut == "caduc":
                self.assertIsNotNone(e.raison_caduc)
            else:
                self.assertIsNone(e.raison_caduc)

    def test_caducs_exclus_sur_toute_topologie(self):
        # Garde-fou : une épreuve caduque (terrain Vagrant multi-node / ha-3cp
        # abandonné, ADR 0097) est exclue QUELLE QUE SOIT la topologie — même
        # celle qui, sans la caducité, la rendrait jouable.
        caducs = {e.num for e in EPREUVES if e.statut == "caduc"}
        self.assertEqual(caducs, {"03", "04", "19", "30"})
        for terrain in ("baremetal", "local"):
            for backend in ("ceph", "local-path"):
                jouables, _ = filter_epreuves(_topo(terrain=terrain, backend=backend))
                nums_j = {e.num for e in jouables}
                self.assertEqual(caducs & nums_j, set(), f"caduc jouable en {terrain}/{backend}")


class Filtrage(unittest.TestCase):
    def test_dataops_ceph_multi_joue_la_quasi_totalite(self):
        jouables, exclues = filter_epreuves(_topo())
        nums_ex = {e.num for e, _ in exclues}
        # En prod, sont exclus : les offensifs (17/18/20/21, interdits prod ADR 0025)
        # ET les 4 caducs (03/04/19/30 — terrain Vagrant multi-node / ha-3cp abandonné,
        # ADR 0097 ; 19 est à la fois offensif ET caduc). Soit {03,04,17,18,19,20,21,30}.
        self.assertEqual(nums_ex, {"03", "04", "17", "18", "19", "20", "21", "30"})
        # 26 jouables : 34 − 8 exclus. Les caducs (03/04/19/30) sortent d'office
        # (epreuve_jouable les rejette AVANT tout autre filtre) ; restent les 26
        # épreuves actives non offensives jouables en prod dataops/ceph/multi (dont la 35,
        # profil_min=base, listée partout — elle SKIP à l'exécution si le socle CI/CD manque).
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
        # Sur un terrain `local` (banc jetable), les offensifs ne sont PLUS exclus (ADR 0108).
        jouables, _ = filter_epreuves(_topo(terrain="local"))
        nums = {e.num for e in jouables}
        self.assertIn("20", nums)  # chaos kill pods, agnostique → jouable sur banc
        self.assertIn("21", nums)

    def test_offensif_interdit_en_prod(self):
        ep_17 = next(e for e in EPREUVES if e.num == "17")
        ok, raison = epreuve_jouable(ep_17, _topo(terrain="baremetal"))
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
