"""Tests de l'anonymiseur .env (bootstrap/security/blur_env.py, ADR 0049/0023).

unittest (stdlib), comme le reste du dépôt (cible `test:python` + CI). Les
fonctions testées sont PURES : l'IP « aléatoire » est injectée via `ip_gen` pour
un résultat déterministe, aucun accès disque.

Lancé par `python3 -m unittest discover tests`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bootstrap", "security"))

from blur_env import (  # noqa: E402
    anonymise_line,
    anonymise_value,
    fake_path,
    random_ip,
)

# Générateur d'IP déterministe pour les tests.
FIXED_IP = "10.0.0.1"


def fixed_ip() -> str:
    return FIXED_IP


class AnonymiseValueFormat(unittest.TestCase):
    """Dérivation par le FORMAT de la valeur (priorité haute)."""

    def test_single_ip(self):
        self.assertEqual(anonymise_value("X", "192.168.1.5", fixed_ip), FIXED_IP)

    def test_ip_list(self):
        self.assertEqual(
            anonymise_value("X", "1.2.3.4, 5.6.7.8", fixed_ip), f"{FIXED_IP},{FIXED_IP}"
        )

    def test_email(self):
        self.assertEqual(anonymise_value("X", "a.b@corp.fr", fixed_ip), "john.doe@example.com")

    def test_integer(self):
        self.assertEqual(anonymise_value("X", "12345", fixed_ip), "42")

    def test_localhost_substring(self):
        self.assertEqual(anonymise_value("X", "http://localhost:9000", fixed_ip), "localhost")

    def test_absolute_path(self):
        # /home/alice/secret.txt → segments non standard remplacés, ext gardée.
        self.assertEqual(
            anonymise_value("X", "/home/alice/secret.txt", fixed_ip), "/exemple/exemple/exemple.txt"
        )


class AnonymiseValueByKey(unittest.TestCase):
    """Dérivation par le NOM de clé quand le format ne tranche pas."""

    def test_mail_key(self):
        self.assertEqual(anonymise_value("ADMIN_MAIL", "x", fixed_ip), "john.doe@example.com")

    def test_ip_key(self):
        self.assertEqual(anonymise_value("NODE_IP", "x", fixed_ip), FIXED_IP)

    def test_user_key(self):
        self.assertEqual(anonymise_value("DB_USER", "alice", fixed_ip), "bob")

    def test_port_key(self):
        self.assertEqual(anonymise_value("LISTEN_PORT", "x", fixed_ip), "8080")

    def test_host_key(self):
        self.assertEqual(anonymise_value("SMTP_HOST", "x", fixed_ip), "localhost")

    def test_secret_key(self):
        self.assertEqual(anonymise_value("API_TOKEN", "x", fixed_ip), "changeme123")

    def test_id_key(self):
        self.assertEqual(anonymise_value("COUNT", "x", fixed_ip), "42")

    def test_fallback(self):
        self.assertEqual(anonymise_value("FOO", "bar", fixed_ip), "valeur_exemple")

    def test_format_wins_over_key(self):
        # Valeur entière + clé IP : le FORMAT (entier → 42) prime sur le nom.
        self.assertEqual(anonymise_value("SERVER_IP", "7", fixed_ip), "42")


class FakePath(unittest.TestCase):
    def test_keeps_known_segments(self):
        self.assertEqual(fake_path("/etc/passwd"), "/etc/passwd")

    def test_relative_prefix_kept(self):
        self.assertEqual(fake_path("./data/projet"), "./exemple/exemple")

    def test_home_prefix(self):
        self.assertEqual(fake_path("~/projets/app"), "~/exemple/exemple")

    def test_non_path_returned_asis(self):
        self.assertEqual(fake_path("pas-un-chemin"), "pas-un-chemin")


class AnonymiseLine(unittest.TestCase):
    def test_comment_unchanged(self):
        self.assertEqual(anonymise_line("# un commentaire", fixed_ip), "# un commentaire")

    def test_blank_unchanged(self):
        self.assertEqual(anonymise_line("   ", fixed_ip), "   ")

    def test_no_equals_unchanged(self):
        self.assertEqual(anonymise_line("export FOO", fixed_ip), "export FOO")

    def test_kv_anonymised(self):
        self.assertEqual(anonymise_line("DB_USER=alice", fixed_ip), "DB_USER=bob")


class RandomIp(unittest.TestCase):
    def test_format_and_range(self):
        import random as _random

        ip = random_ip(_random.Random(0))
        octets = ip.split(".")
        self.assertEqual(len(octets), 4)
        for o in octets:
            self.assertTrue(1 <= int(o) <= 223)


if __name__ == "__main__":
    unittest.main()
