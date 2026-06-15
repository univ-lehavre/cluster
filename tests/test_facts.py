"""Tests du parsing du contrat machine (cluster_topology/facts.py).

unittest stdlib, fixtures = sorties KEY=VALUE figées — aucun subprocess, aucun banc.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cluster_topology.facts import parse_facts  # noqa: E402


class ParseFacts(unittest.TestCase):
    def test_nominal_non_ha(self):
        # Cas non-HA : CP_IP + L2_IFACE, pas de VIP.
        out = "CP_IP=192.168.104.5\nL2_IFACE=lima0\n"
        self.assertEqual(parse_facts(out), {"CP_IP": "192.168.104.5", "L2_IFACE": "lima0"})

    def test_nominal_ha(self):
        # Cas HA : VIP + VIP_IFACE émis en plus.
        out = "CP_IP=192.168.104.5\nL2_IFACE=lima0\nVIP=192.168.104.40\nVIP_IFACE=lima0\n"
        self.assertEqual(
            parse_facts(out),
            {
                "CP_IP": "192.168.104.5",
                "L2_IFACE": "lima0",
                "VIP": "192.168.104.40",
                "VIP_IFACE": "lima0",
            },
        )

    def test_ignores_log_noise(self):
        # Lignes parasites (logs bash mêlés) : ignorées, seules les clés connues retenues.
        out = (
            "→ provision Lima…\n"
            "CP_IP=10.0.0.5\n"
            "[ok] VM cp1 démarrée\n"
            "L2_IFACE=eth0\n"
            "BRUIT=valeur inconnue\n"
            "\n"
        )
        self.assertEqual(parse_facts(out), {"CP_IP": "10.0.0.5", "L2_IFACE": "eth0"})

    def test_strips_values(self):
        out = "CP_IP=  10.0.0.5  \nL2_IFACE=\tlima0\t\n"
        self.assertEqual(parse_facts(out), {"CP_IP": "10.0.0.5", "L2_IFACE": "lima0"})

    def test_empty(self):
        self.assertEqual(parse_facts(""), {})

    def test_value_with_equals_kept_whole(self):
        # Une valeur contenant `=` (improbable ici, mais robustesse de partition).
        self.assertEqual(parse_facts("CP_IP=a=b")["CP_IP"], "a=b")


if __name__ == "__main__":
    unittest.main()
