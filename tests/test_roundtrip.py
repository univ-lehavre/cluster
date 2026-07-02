"""Tests du round-trip par clôture de dépendances (nestor/roundtrip.py).

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

from nestor import roundtrip  # noqa: E402


class Closure(unittest.TestCase):
    def test_leaf_is_itself(self):
        self.assertEqual(roundtrip.closure("monitoring"), ["monitoring"])
        # mlflow est une FEUILLE (rien ne dépend d'elle) — clôture = elle-même.
        self.assertEqual(roundtrip.closure("mlflow"), ["mlflow"])
        # portail (layer autonome ADR 0091) : FEUILLE — rien ne dépend de lui (il
        # OBSERVE les UI des autres couches sans arête de données) → clôture = lui-même.
        self.assertEqual(roundtrip.closure("portal"), ["portal"])

    def test_dataops_pulls_mlflow_and_portal(self):
        # mlflow (layer autonome ADR 0082) dépend de la base CNPG posée par dataops ;
        # le portail (ADR 0091) dépend du registry/build-images de dataops (image maison)
        # → défaire dataops oblige à défaire mlflow ET portail d'abord (ordre inverse,
        # ADR 0054). portail en QUEUE (poids 9, après mlflow poids 8).
        # gitops-seed-citation dépend de citation → registry (∈ dataops) → tiré aussi (ADR 0095).
        self.assertEqual(
            roundtrip.closure("dataops"),
            ["dataops", "mlflow", "portal", "gitops-seed-citation"],
        )

    def test_gitops_pulls_seed(self):
        # gitops-seed-citation dépend d'argocd/gitea (chaîne gitops) → tiré aussi (ADR 0095).
        self.assertEqual(
            roundtrip.closure("gitops"),
            ["gitops", "gitops-seed", "gitops-seed-citation"],
        )

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
        # mlflow (layer autonome ADR 0082) sort en QUEUE : elle dépend de dataops
        # (base CNPG) → tout ce qui tire dataops tire aussi mlflow, défaite en dernier.
        self.assertEqual(
            roundtrip.closure("ceph"),
            [
                "ceph",
                "sc",
                "datalake",
                "monitoring",
                "gitops",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
                "gitops-seed-citation",
            ],
        )
        self.assertEqual(
            roundtrip.closure("sc"),
            [
                "sc",
                "datalake",
                "monitoring",
                "gitops",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
                "gitops-seed-citation",
            ],
        )

    def test_unknown_phase_rejected(self):
        with self.assertRaises(roundtrip.RoundtripError):
            roundtrip.closure("frobnicate")


class StorageGuard(unittest.TestCase):
    def test_storage_layers_involve_storage(self):
        for p in ("ceph", "sc", "datalake"):
            self.assertTrue(roundtrip.involves_storage(p))

    def test_app_layers_do_not(self):
        for p in ("monitoring", "gitops", "dataops", "mlflow", "gitops-seed", "metrics-server"):
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

    def run_phase(self, args):
        # `run_phase` ne sert plus qu'à la RECONSTRUCTION (`run-phases.sh <phase>`) — la
        # destruction passe par `destroy_layer` (découverte). Plus de branche `rollback`.
        self.calls.append(tuple(args))
        for s in roundtrip.phase_signal(args[0]):
            self.present.add(s)
        return 0

    def signal_present(self, signal, *, api=None):
        return [s for s in signal if s in self.present]


def _yes(layers, *, assume_yes):
    return True


def _discovery_destroy(fb):
    # `destroy_layer` = `remove --discover` : UN geste défait TOUTE la clôture (aval +
    # node-side). Modélise la découverte pour les tests (retire le signal de la clôture).
    def destroy_layer(phase):
        for p in roundtrip.closure(phase):
            for s in roundtrip.phase_signal(p):
                fb.present.discard(s)
        return 0

    return destroy_layer


class RoundtripNominal(unittest.TestCase):
    def test_monitoring_reversible(self):
        fb = FakeBench(present=roundtrip.phase_signal("monitoring"))
        res = roundtrip.run_roundtrip(
            "monitoring",
            run_phase=fb.run_phase,
            destroy_layer=_discovery_destroy(fb),
            signal_present=fb.signal_present,
            confirm_fn=_yes,
        )
        self.assertTrue(res.reversible)
        self.assertEqual(
            [s.nom for s in res.steps],
            ["détruire", "vérifier détruit", "reconstruire", "vérifier sain"],
        )

    def test_gitops_closure_rebuilds_gitops_first(self):
        fb = FakeBench(
            present=(
                roundtrip.phase_signal("gitops")
                + roundtrip.phase_signal("gitops-seed")
                + roundtrip.phase_signal("gitops-seed-citation")
            )
        )
        res = roundtrip.run_roundtrip(
            "gitops",
            run_phase=fb.run_phase,
            destroy_layer=_discovery_destroy(fb),
            signal_present=fb.signal_present,
            confirm_fn=_yes,
        )
        self.assertTrue(res.reversible)
        # La destruction est UN geste (découverte) ; les appels run_phase sont les RECONSTRUCTIONS,
        # dans l'ordre de montage (gitops → gitops-seed → gitops-seed-citation, ADR 0095). Plus
        # aucun `rollback` bash.
        self.assertEqual(fb.calls, [("gitops",), ("gitops-seed",), ("gitops-seed-citation",)])

    def test_destroy_layer_discovery_destroys_whole_closure_in_one_call(self):
        # ADR 0101 : destroy_layer injecté (découverte) défait TOUTE la clôture en UN geste
        # (au lieu de boucler run-phases.sh rollback). On NE doit voir AUCUN `rollback` bash,
        # juste l'appel découverte sur la phase racine + les reconstructions.
        fb = FakeBench(
            present=roundtrip.phase_signal("gitops") + roundtrip.phase_signal("gitops-seed")
        )
        destroyed = []

        def destroy_layer(phase):
            destroyed.append(phase)
            for p in roundtrip.closure(phase):  # un geste défait toute la clôture
                for s in roundtrip.phase_signal(p):
                    fb.present.discard(s)
            return 0

        res = roundtrip.run_roundtrip(
            "gitops",
            run_phase=fb.run_phase,
            destroy_layer=destroy_layer,
            signal_present=fb.signal_present,
            confirm_fn=_yes,
        )
        self.assertTrue(res.reversible)
        self.assertEqual(destroyed, ["gitops"])  # UN seul appel découverte (toute la clôture)
        # plus aucun `rollback` bash : les seuls run_phase sont les reconstructions.
        self.assertFalse(any(c[0][0] == "rollback" for c in fb.calls))

    def test_destroy_layer_failure_stops_roundtrip(self):
        fb = FakeBench(present=roundtrip.phase_signal("monitoring"))
        res = roundtrip.run_roundtrip(
            "monitoring",
            run_phase=fb.run_phase,
            destroy_layer=lambda p: 1,  # la découverte échoue
            signal_present=fb.signal_present,
            confirm_fn=_yes,
        )
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[0].nom, "détruire")
        self.assertFalse(res.steps[0].ok)


class StorageOptIn(unittest.TestCase):
    def test_ceph_requires_full(self):
        with self.assertRaises(roundtrip.RoundtripError):
            roundtrip.run_roundtrip(
                "ceph", destroy_layer=lambda p: 0, confirm_fn=_yes
            )  # allow_full défaut False

    def test_sc_requires_full(self):
        with self.assertRaises(roundtrip.RoundtripError):
            roundtrip.run_roundtrip("sc", destroy_layer=lambda p: 0, confirm_fn=_yes)

    def test_ceph_allowed_with_full(self):
        fb = FakeBench(
            present=[s for p in roundtrip.closure("ceph") for s in roundtrip.phase_signal(p)]
        )
        res = roundtrip.run_roundtrip(
            "ceph",
            allow_full=True,
            run_phase=fb.run_phase,
            destroy_layer=_discovery_destroy(fb),
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
            destroy_layer=lambda p: 0,
            signal_present=fb.signal_present,
            confirm_fn=lambda layers, *, assume_yes: False,
        )
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[0].nom, "confirmation")
        self.assertEqual(fb.calls, [])  # rien détruit


class Failures(unittest.TestCase):
    # L'échec de la DESTRUCTION (découverte) qui arrête le roundtrip est couvert par
    # `Reversibility.test_destroy_layer_failure_stops` (destroy_layer rend rc≠0).

    def test_still_present_after_destroy(self):
        sig = roundtrip.phase_signal("monitoring")
        res = roundtrip.run_roundtrip(
            "monitoring",
            run_phase=lambda a: 0,
            destroy_layer=lambda p: 0,
            signal_present=lambda s, **k: sig,  # toujours présent
            confirm_fn=_yes,
        )
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[-1].nom, "vérifier détruit")

    def test_not_back_after_rebuild(self):
        res = roundtrip.run_roundtrip(
            "monitoring",
            run_phase=lambda a: 0,
            destroy_layer=lambda p: 0,
            signal_present=lambda s, **k: [],  # jamais présent → manquant à la fin
            confirm_fn=_yes,
        )
        self.assertFalse(res.reversible)
        self.assertEqual(res.steps[-1].nom, "vérifier sain")


if __name__ == "__main__":
    unittest.main()
