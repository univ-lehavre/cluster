"""Tests des gates d'infra (nestor/gates.py).

unittest stdlib, prédicats INJECTÉS (read_phase/ready_count/osd_up_count stubés) +
sleep no-op — aucune attente réelle, aucun cluster. Vérifie l'attente bornée et le
verdict ok/timeout.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.gates import (  # noqa: E402
    GateError,
    gate_etcd,
    gate_nodes_ready,
    gate_osds_up,
    gate_pvc_bound,
    gate_vip,
)

_NOSLEEP = lambda _: None  # noqa: E731 — sleep no-op pour les tests


class PvcBound(unittest.TestCase):
    def test_bound_immediately(self):
        r = gate_pvc_bound("default", "x", read_phase=lambda ns, n: "Bound", sleep=_NOSLEEP)
        self.assertTrue(r.ok)

    def test_becomes_bound_after_pending(self):
        # Pending puis Bound → ok (attente bornée). read_phase est appelé plusieurs
        # fois (predicate + describe) ; on renvoie Pending les 2 premières fois.
        calls = {"i": 0}

        def read(ns, n):
            calls["i"] += 1
            return "Pending" if calls["i"] <= 2 else "Bound"

        r = gate_pvc_bound("default", "x", read_phase=read, retries=5, sleep=_NOSLEEP)
        self.assertTrue(r.ok)

    def test_timeout_if_never_bound(self):
        r = gate_pvc_bound(
            "default", "x", read_phase=lambda ns, n: "Pending", retries=3, sleep=_NOSLEEP
        )
        self.assertFalse(r.ok)
        self.assertIn("timeout", r.detail)

    def test_none_phase_is_not_bound(self):
        r = gate_pvc_bound("default", "x", read_phase=lambda ns, n: None, retries=2, sleep=_NOSLEEP)
        self.assertFalse(r.ok)


class NodesReady(unittest.TestCase):
    def test_enough_ready(self):
        r = gate_nodes_ready(3, ready_count=lambda: 3, sleep=_NOSLEEP)
        self.assertTrue(r.ok)

    def test_at_least_semantics(self):
        # >= attendu : 4 Ready pour 3 attendus → ok.
        r = gate_nodes_ready(3, ready_count=lambda: 4, sleep=_NOSLEEP)
        self.assertTrue(r.ok)

    def test_timeout_if_short(self):
        r = gate_nodes_ready(3, ready_count=lambda: 1, retries=2, sleep=_NOSLEEP)
        self.assertFalse(r.ok)
        self.assertIn("1/3", r.detail)


class OsdsUp(unittest.TestCase):
    def test_exact_count(self):
        r = gate_osds_up(3, osd_up_count=lambda: 3, sleep=_NOSLEEP)
        self.assertTrue(r.ok)

    def test_timeout_if_missing(self):
        r = gate_osds_up(3, osd_up_count=lambda: 2, retries=2, sleep=_NOSLEEP)
        self.assertFalse(r.ok)


# ── Gates HA `ha-3cp` (RAISE-on-failure) — migrées de l'ex-nestor/ha.py vers gates.py
#    avec la fusion. Contrat distinct des gates d'infra : elles LÈVENT GateError (la
#    promotion HA est fail-fast), au lieu de rendre un GateResult.


class GateVip(unittest.TestCase):
    def test_returns_when_vip_responds(self):
        # Aucune levée si la VIP répond (rend None, pas d'exception).
        r = gate_vip("10.0.0.40", "cp1", vip_responds=lambda *_a: True, sleep=_NOSLEEP)
        self.assertIsNone(r)

    def test_raises_if_vip_never_responds(self):
        with self.assertRaises(GateError):
            gate_vip("10.0.0.40", "cp1", vip_responds=lambda *_a: False, retries=2, sleep=_NOSLEEP)


class GateEtcd(unittest.TestCase):
    def _healthy(self, n):
        return lambda _cp: "\n".join("x is healthy" for _ in range(n))

    def test_returns_on_healthy_quorum(self):
        self.assertIsNone(gate_etcd("cp1", 3, etcd_output=self._healthy(3), sleep=_NOSLEEP))

    def test_raises_on_degraded_quorum(self):
        # Un endpoint unhealthy = quorum dégradé → fail FRANC (ne pas promouvoir).
        with self.assertRaises(GateError):
            gate_etcd(
                "cp1", 3, etcd_output=lambda _cp: "a is healthy\nb is unhealthy", sleep=_NOSLEEP
            )

    def test_raises_on_timeout_when_skip(self):
        # Sortie vide (skip) jamais résolue → timeout → GateError.
        with self.assertRaises(GateError):
            gate_etcd("cp1", 3, etcd_output=lambda _cp: "", retries=2, sleep=_NOSLEEP)


if __name__ == "__main__":
    unittest.main()
