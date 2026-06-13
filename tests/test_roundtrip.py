"""Tests du round-trip par clôture de dépendances (cluster_topology/roundtrip.py).

Pur/injecté : `run_phase`/`signal_present`/`confirm_fn` sont stubés — aucun banc,
aucun cluster. Couvre le graphe de clôture, l'ordre destroy/rebuild, le garde-fou
stockage (--full), la confirmation TTY, et les échecs.

`phase_namespaces`/`phase_targeted_resources` SOURCENT rollback-lib.sh (sous-process
bash rapide, sans cluster) → ces tests valident aussi la parité avec le bash.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology import roundtrip  # noqa: E402


class Closure(unittest.TestCase):
    def test_leaf_is_itself(self):
        self.assertEqual(roundtrip.closure("monitoring"), ["monitoring"])
        self.assertEqual(roundtrip.closure("dataops"), ["dataops"])

    def test_gitops_pulls_seed(self):
        self.assertEqual(roundtrip.closure("gitops"), ["gitops", "gitops-seed"])

    def test_metrics_server_independent(self):
        self.assertEqual(roundtrip.closure("metrics-server"), ["metrics-server"])

    def test_sc_pulls_storage_consumers(self):
        cl = roundtrip.closure("sc")
        # sc → datalake, monitoring, dataops, gitops (+ gitops-seed via gitops).
        self.assertEqual(cl[0], "sc")  # amont d'abord
        for p in ("datalake", "monitoring", "gitops", "dataops", "gitops-seed"):
            self.assertIn(p, cl)

    def test_ceph_pulls_everything_storage(self):
        cl = roundtrip.closure("ceph")
        self.assertEqual(cl[0], "ceph")
        for p in ("sc", "datalake", "monitoring", "gitops", "dataops", "gitops-seed"):
            self.assertIn(p, cl)

    def test_closure_in_mount_order(self):
        # L'ordre est celui du MONTAGE (amont→aval), DÉRIVÉ du graphe atomique
        # (phase_closure, rollback-lib.sh) — déterministe. On vérifie l'invariant
        # structurel : une couche de stockage de base sort avant ce qui la consomme.
        cl = roundtrip.closure("ceph")
        self.assertEqual(cl[:3], ["ceph", "sc", "datalake"])  # socle stockage d'abord
        # gitops/gitops-seed (consommateurs) après le stockage.
        self.assertLess(cl.index("sc"), cl.index("gitops"))
        self.assertLess(cl.index("gitops"), cl.index("gitops-seed"))

    def test_closure_derives_full_dependents(self):
        # La clôture DÉRIVÉE doit reproduire l'ancien graphe validé à la main :
        # détruire `sc` orpheline aussi gitops (PVC gitea sur la StorageClass).
        self.assertEqual(
            roundtrip.closure("ceph"),
            ["ceph", "sc", "datalake", "monitoring", "gitops", "dataops", "gitops-seed"],
        )
        self.assertEqual(
            roundtrip.closure("sc"),
            ["sc", "datalake", "monitoring", "gitops", "dataops", "gitops-seed"],
        )

    def test_unknown_phase_rejected(self):
        with self.assertRaises(roundtrip.RoundtripError):
            roundtrip.closure("frobnicate")


class StorageGuard(unittest.TestCase):
    def test_storage_layers_involve_storage(self):
        for p in ("ceph", "sc", "datalake"):
            self.assertTrue(roundtrip.involves_storage(p))

    def test_app_layers_do_not(self):
        for p in ("monitoring", "gitops", "dataops", "gitops-seed", "metrics-server"):
            self.assertFalse(roundtrip.involves_storage(p))


class Confirm(unittest.TestCase):
    def test_assume_yes_bypasses(self):
        self.assertTrue(roundtrip.confirm(["monitoring"], assume_yes=True))

    def test_non_tty_without_yes_refuses(self):
        ok = roundtrip.confirm(["monitoring"], assume_yes=False, is_tty=lambda: False)
        self.assertFalse(ok)

    def test_tty_accepts_oui(self):
        ok = roundtrip.confirm(
            ["monitoring"], assume_yes=False, is_tty=lambda: True, prompt=lambda _: "oui"
        )
        self.assertTrue(ok)

    def test_tty_refuses_non(self):
        ok = roundtrip.confirm(
            ["monitoring"], assume_yes=False, is_tty=lambda: True, prompt=lambda _: "non"
        )
        self.assertFalse(ok)


class FakeBench:
    """run_phase/signal_present en mémoire, pilotés par les ordres de la clôture."""

    def __init__(self, present=None):
        self.present = set(present or [])
        self.calls = []

    def run_phase(self, args, *, env_extra=None):
        self.calls.append((tuple(args), env_extra))
        if args[0] == "rollback":
            for s in roundtrip.phase_signal(args[1]):
                self.present.discard(s)
        else:
            for s in roundtrip.phase_signal(args[0]):
                self.present.add(s)
        return 0

    def signal_present(self, signal, *, api=None):
        return [s for s in signal if s in self.present]


def _yes(layers, *, assume_yes):
    return True


class RoundtripNominal(unittest.TestCase):
    def test_monitoring_reversible(self):
        fb = FakeBench(present=roundtrip.phase_signal("monitoring"))
        res = roundtrip.run_roundtrip(
            "monitoring", run_phase=fb.run_phase, signal_present=fb.signal_present, confirm_fn=_yes
        )
        self.assertTrue(res.reversible)
        self.assertEqual(
            [s.nom for s in res.steps],
            ["détruire", "vérifier détruit", "reconstruire", "vérifier sain"],
        )

    def test_gitops_closure_destroys_seed_first_rebuilds_gitops_first(self):
        fb = FakeBench(
            present=roundtrip.phase_signal("gitops") + roundtrip.phase_signal("gitops-seed")
        )
        res = roundtrip.run_roundtrip(
            "gitops", run_phase=fb.run_phase, signal_present=fb.signal_present, confirm_fn=_yes
        )
        self.assertTrue(res.reversible)
        rollbacks = [c[0] for c in fb.calls if c[0][0] == "rollback"]
        rebuilds = [c[0] for c in fb.calls if c[0][0] != "rollback"]
        # détruire en ordre inverse (seed avant gitops), reconstruire en ordre direct.
        self.assertEqual(rollbacks, [("rollback", "gitops-seed"), ("rollback", "gitops")])
        self.assertEqual(rebuilds, [("gitops",), ("gitops-seed",)])

    def test_rollback_uses_banc_jetable(self):
        fb = FakeBench(present=roundtrip.phase_signal("monitoring"))
        roundtrip.run_roundtrip(
            "monitoring", run_phase=fb.run_phase, signal_present=fb.signal_present, confirm_fn=_yes
        )
        self.assertEqual(fb.calls[0][1], {"BANC_JETABLE": "1"})


class StorageOptIn(unittest.TestCase):
    def test_ceph_requires_full(self):
        with self.assertRaises(roundtrip.RoundtripError):
            roundtrip.run_roundtrip("ceph", confirm_fn=_yes)  # allow_full défaut False

    def test_sc_requires_full(self):
        with self.assertRaises(roundtrip.RoundtripError):
            roundtrip.run_roundtrip("sc", confirm_fn=_yes)

    def test_ceph_allowed_with_full(self):
        fb = FakeBench(
            present=[s for p in roundtrip.closure("ceph") for s in roundtrip.phase_signal(p)]
        )
        res = roundtrip.run_roundtrip(
            "ceph",
            allow_full=True,
            run_phase=fb.run_phase,
            signal_present=fb.signal_present,
            confirm_fn=_yes,
        )
        self.assertTrue(res.reversible)


class ConfirmationGate(unittest.TestCase):
    def test_refused_confirmation_stops(self):
        fb = FakeBench(present=roundtrip.phase_signal("monitoring"))
        res = roundtrip.run_roundtrip(
            "monitoring",
            run_phase=fb.run_phase,
            signal_present=fb.signal_present,
            confirm_fn=lambda layers, *, assume_yes: False,
        )
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[0].nom, "confirmation")
        self.assertEqual(fb.calls, [])  # rien détruit


class Failures(unittest.TestCase):
    def test_rollback_failure_stops(self):
        def runner(args, *, env_extra=None):
            return 3 if args[0] == "rollback" else 0

        res = roundtrip.run_roundtrip(
            "monitoring", run_phase=runner, signal_present=lambda s, **k: [], confirm_fn=_yes
        )
        self.assertFalse(res.reversible)
        self.assertTrue(res.steps[-1].nom.startswith("détruire"))

    def test_still_present_after_destroy(self):
        sig = roundtrip.phase_signal("monitoring")
        res = roundtrip.run_roundtrip(
            "monitoring",
            run_phase=lambda a, **k: 0,
            signal_present=lambda s, **k: sig,  # toujours présent
            confirm_fn=_yes,
        )
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[-1].nom, "vérifier détruit")

    def test_not_back_after_rebuild(self):
        res = roundtrip.run_roundtrip(
            "monitoring",
            run_phase=lambda a, **k: 0,
            signal_present=lambda s, **k: [],  # jamais présent → manquant à la fin
            confirm_fn=_yes,
        )
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[-1].nom, "vérifier sain")


if __name__ == "__main__":
    unittest.main()
