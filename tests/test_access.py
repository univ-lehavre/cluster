"""Tests de la logique pure d'accès développeur (nestor/access.py, ADR 0048/0101).

Porte les cas de `bench/unit/access.bats` (host_port_for / url_line / env_line) +
couvre le parsing du contrat (exposed_uis) et le rendu du `.env` (env_content).
Pur : aucun cluster, aucun réseau (l'I/O vit dans la façade cmd_access).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.access import (  # noqa: E402
    BASE_PORT,
    env_content,
    env_line,
    exposed_uis,
    host_port_for,
    url_line,
)


class HostPortFor(unittest.TestCase):
    def test_index_0_is_base_port(self):
        self.assertEqual(host_port_for(0), BASE_PORT)

    def test_index_4_is_base_plus_4(self):
        self.assertEqual(host_port_for(4), BASE_PORT + 4)

    def test_base_override(self):
        self.assertEqual(host_port_for(2, base=9000), 9002)


class UrlLine(unittest.TestCase):
    def test_aligned_line(self):
        # `[layer]` aligné à 10, url, auth — newline final.
        self.assertEqual(
            url_line("gitops", "http://127.0.0.1:8443", "secret-admin"),
            "    [gitops    ] http://127.0.0.1:8443   (auth: secret-admin)\n",
        )

    def test_auth_none_tolerated(self):
        self.assertIn("(auth: none)", url_line("socle", "http://127.0.0.1:8450", "none"))


class EnvLine(unittest.TestCase):
    def test_key_value(self):
        self.assertEqual(env_line("FOO", "bar"), "FOO=bar\n")

    def test_empty_value_tolerated(self):
        self.assertEqual(env_line("EMPTY", ""), "EMPTY=\n")
        self.assertEqual(env_line("EMPTY", None), "EMPTY=\n")


class ExposedUIs(unittest.TestCase):
    _CONTRACT = """
endpoints:
  - {namespace: gitea, service: gitea, layer: gitops, auth: token, exposed: true}
  - {namespace: argocd, service: argocd-server, layer: gitops, exposed: true}
  - {namespace: hidden, service: secret-svc, exposed: false}
  - {namespace: nolayer, service: bare, exposed: true}
"""

    def test_only_exposed_true(self):
        uis = exposed_uis(self._CONTRACT)
        names = {(u.namespace, u.service) for u in uis}
        self.assertIn(("gitea", "gitea"), names)
        self.assertNotIn(("hidden", "secret-svc"), names)  # exposed: false exclu

    def test_sorted_for_deterministic_index(self):
        # Tri (namespace, service) → ordre stable (port hôte par index déterministe).
        uis = exposed_uis(self._CONTRACT)
        self.assertEqual(
            [(u.namespace, u.service) for u in uis],
            sorted((u.namespace, u.service) for u in uis),
        )

    def test_defaults_layer_and_auth(self):
        # layer absent → "-" ; auth absent → "none".
        ui = next(u for u in exposed_uis(self._CONTRACT) if u.service == "bare")
        self.assertEqual(ui.layer, "-")
        self.assertEqual(ui.auth, "none")

    def test_empty_contract_is_empty(self):
        self.assertEqual(exposed_uis(""), [])
        self.assertEqual(exposed_uis("endpoints: []"), [])


class EnvContent(unittest.TestCase):
    def test_renders_pg_and_internal_services(self):
        out = env_content("pgvector_user", "s3cr3t")
        self.assertIn("POSTGRES_USER=pgvector_user\n", out)
        self.assertIn("POSTGRES_PASSWORD=s3cr3t\n", out)
        # FQDN intra-cluster (le code atlas tourne DANS le cluster).
        self.assertIn("POSTGRES_HOST=pg-rw.postgres.svc.cluster.local\n", out)
        self.assertIn("OPENLINEAGE_URL=http://marquez.marquez.svc.cluster.local:5000\n", out)
        self.assertIn("REGISTRY=registry:80\n", out)

    def test_header_warns_not_to_commit(self):
        out = env_content("u", "p")
        self.assertIn("NE PAS COMMITER", out)
        self.assertTrue(out.startswith("#"))

    def test_empty_credentials_tolerated(self):
        out = env_content("", "")
        self.assertIn("POSTGRES_USER=\n", out)
        self.assertIn("POSTGRES_PASSWORD=\n", out)


if __name__ == "__main__":
    unittest.main()
