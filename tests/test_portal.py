"""Tests de nestor/portal.py (ADR 0091 / ADR 0017 : logique pure testée sans cluster).

Croisement contrat ↔ état observé : verdicts (MATCH/MISSING/DRIFT/EXTRA), génération
des commandes secret (jamais la valeur), groupage par couche. Aucun I/O cluster.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nestor import portal_server  # noqa: E402
from nestor.portal import (  # noqa: E402
    DRIFT,
    EXTRA,
    LAYER_ORDER,
    MATCH,
    MISSING,
    Observed,
    build_view,
    login_for,
    render_html,
    secret_command,
)

# Endpoints d'exemple (sous-ensemble du contrat réel, formes variées d'auth).
_EP = [
    {
        "id": "grafana-ui",
        "service": "kube-prometheus-stack-grafana",
        "namespace": "monitoring",
        "port": 80,
        "auth": "secret-admin",
        "layer": "monitoring",
        "exposed": True,
    },
    {
        "id": "argocd-ui",
        "service": "argocd-server",
        "namespace": "argocd",
        "port": 80,
        "auth": "secret-admin",
        "layer": "gitops",
        "exposed": True,
    },
    {
        "id": "mlflow-tracking",
        "service": "mlflow",
        "namespace": "mlflow",
        "port": 5000,
        "auth": "none",
        "layer": "dataops",
    },
    {
        "id": "mailpit-ui",
        "service": "mailpit",
        "namespace": "mailpit",
        "port": 8025,
        "auth": "none",
        "layer": "monitoring",
        "profil": "local-path",
    },
    {
        "id": "k8s-dashboard-ui",
        "service": "kubernetes-dashboard",
        "namespace": "kubernetes-dashboard",
        "port": 443,
        "auth": "token",
        "layer": "socle",
        "exposed": True,
    },
]


class SecretCommand(unittest.TestCase):
    def test_none_returns_no_command(self):
        self.assertIsNone(secret_command({"id": "mlflow", "auth": "none"}))
        self.assertIsNone(secret_command({"id": "x"}))  # auth absent = none

    def test_secret_admin_known_refs(self):
        cmd = secret_command({"id": "argocd-ui", "namespace": "argocd", "auth": "secret-admin"})
        self.assertIn("kubectl -n argocd get secret argocd-initial-admin-secret", cmd)
        self.assertIn("base64 -d", cmd)

    def test_grafana_admin_password_key(self):
        cmd = secret_command(
            {"id": "grafana-ui", "namespace": "monitoring", "auth": "secret-admin"}
        )
        self.assertIn("admin-password", cmd)

    def test_token_uses_create_token(self):
        cmd = secret_command(
            {"id": "k8s-dashboard-ui", "namespace": "kubernetes-dashboard", "auth": "token"}
        )
        self.assertIn("create token", cmd)

    def test_secret_role_derives_pg_role(self):
        cmd = secret_command(
            {"id": "postgres-rw", "namespace": "postgres", "auth": "secret-role", "role": "dagster"}
        )
        self.assertIn("pg-role-dagster", cmd)

    def test_obc_secret_key(self):
        cmd = secret_command({"id": "s3", "namespace": "rook-ceph", "auth": "secret-obc"})
        self.assertIn("AWS_SECRET_ACCESS_KEY", cmd)

    def test_never_contains_a_value(self):
        # Le portail montre la COMMANDE, jamais une valeur de secret (ADR 0091 §3).
        cmd = secret_command({"id": "gitea-ui", "namespace": "gitea", "auth": "secret-admin"})
        self.assertIn("jsonpath", cmd)  # une commande de lecture, pas un littéral


class LoginFor(unittest.TestCase):
    def test_none_for_no_auth(self):
        self.assertIsNone(login_for({"id": "x", "auth": "none"}))
        self.assertIsNone(login_for({"id": "x"}))  # auth absent = none

    def test_none_for_token(self):
        # token : le jeton EST l'identité, pas de login à saisir.
        self.assertIsNone(login_for({"id": "k8s-dashboard-ui", "auth": "token"}))

    def test_known_logins(self):
        self.assertEqual(login_for({"id": "argocd-ui", "auth": "secret-admin"}), "admin")
        self.assertEqual(login_for({"id": "grafana-ui", "auth": "secret-admin"}), "admin")
        self.assertEqual(login_for({"id": "gitea-ui", "auth": "secret-admin"}), "gitea_admin")

    def test_contract_login_overrides(self):
        # le champ `login` du contrat prime sur la convention.
        ep = {"id": "argocd-ui", "auth": "secret-admin", "login": "root"}
        self.assertEqual(login_for(ep), "root")

    def test_secret_role_login_is_the_role(self):
        self.assertEqual(
            login_for({"id": "pg", "auth": "secret-role", "role": "dagster"}), "dagster"
        )


class Verdicts(unittest.TestCase):
    def test_match_when_present_ready_with_nodeport(self):
        obs = {
            ("monitoring", "kube-prometheus-stack-grafana"): Observed(
                present=True, ready=True, node_port=31234, node_ip="10.0.2.11"
            )
        }
        v = build_view(_EP, obs)
        grafana = next(e for e in v.all_entries() if e.id == "grafana-ui")
        self.assertEqual(grafana.verdict, MATCH)
        self.assertEqual(grafana.ui_url, "http://10.0.2.11:31234")

    def test_scheme_https_for_tls_terminating_ui(self):
        # Une UI qui termine elle-même le TLS (ex. dashboard Ceph mgr 8443) déclare
        # `scheme: https` au contrat → l'URL générée est https://, pas http://.
        eps = [
            {
                "id": "ceph-dashboard-ui",
                "service": "rook-ceph-mgr-dashboard",
                "namespace": "rook-ceph",
                "layer": "socle",
                "auth": "secret-admin",
                "scheme": "https",
                "exposed": True,
            }
        ]
        obs = {
            ("rook-ceph", "rook-ceph-mgr-dashboard"): Observed(
                present=True, ready=True, node_port=30352, node_ip="10.0.2.11"
            )
        }
        v = build_view(eps, obs)
        ceph = next(e for e in v.all_entries() if e.id == "ceph-dashboard-ui")
        self.assertEqual(ceph.verdict, MATCH)
        self.assertEqual(ceph.ui_url, "https://10.0.2.11:30352")

    def test_missing_when_absent(self):
        v = build_view(_EP, {})  # rien observé
        argocd = next(e for e in v.all_entries() if e.id == "argocd-ui")
        self.assertEqual(argocd.verdict, MISSING)

    def test_drift_when_present_not_ready(self):
        obs = {("argocd", "argocd-server"): Observed(present=True, ready=False)}
        v = build_view(_EP, obs)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "argocd-ui").verdict, DRIFT)

    def test_drift_when_exposed_but_no_nodeport(self):
        # déclaré exposed mais aucun NodePort observé (Service NodePort manquant) → DRIFT.
        obs = {
            ("monitoring", "kube-prometheus-stack-grafana"): Observed(
                present=True, ready=True, node_port=None
            )
        }
        v = build_view(_EP, obs)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "grafana-ui").verdict, DRIFT)

    def test_no_url_when_node_ip_unknown(self):
        # NodePort observé mais IP nœud inconnue → pas d'URL inventée (mais MATCH).
        obs = {
            ("monitoring", "kube-prometheus-stack-grafana"): Observed(
                present=True, ready=True, node_port=31234, node_ip=None
            )
        }
        v = build_view(_EP, obs)
        grafana = next(e for e in v.all_entries() if e.id == "grafana-ui")
        self.assertEqual(grafana.verdict, MATCH)
        self.assertIsNone(grafana.ui_url)

    def test_banc_only_absent_in_prod_is_match(self):
        # mailpit (profil local-path) absent en prod → MATCH (attendu), pas MISSING.
        v = build_view(_EP, {}, target_is_prod=True)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "mailpit-ui").verdict, MATCH)

    def test_banc_only_absent_on_bench_is_missing(self):
        # sur le banc (target_is_prod=False), un banc-only absent EST manquant.
        v = build_view(_EP, {}, target_is_prod=False)
        self.assertEqual(next(e for e in v.all_entries() if e.id == "mailpit-ui").verdict, MISSING)

    def test_extra_for_observed_outside_contract(self):
        v = build_view(
            _EP,
            {},
            extras=[{"id": "rogue", "service": "rogue", "namespace": "x", "layer": "dataops"}],
        )
        rogue = next(e for e in v.all_entries() if e.id == "rogue")
        self.assertEqual(rogue.verdict, EXTRA)


class Grouping(unittest.TestCase):
    def test_grouped_by_layer_in_canonical_order(self):
        v = build_view(_EP, {})
        # les couches présentes apparaissent dans l'ordre canonique (socle avant dataops).
        present = [layer for layer in v.layers]
        canonical = [layer for layer in LAYER_ORDER if layer in present]
        self.assertEqual(present[: len(canonical)], canonical)

    def test_each_entry_in_its_layer(self):
        v = build_view(_EP, {})
        self.assertIn("argocd-ui", [e.id for e in v.layers["gitops"]])
        self.assertIn("mlflow-tracking", [e.id for e in v.layers["dataops"]])

    def test_no_auth_no_secret_cmd(self):
        v = build_view(_EP, {})
        mlflow = next(e for e in v.all_entries() if e.id == "mlflow-tracking")
        self.assertIsNone(mlflow.secret_cmd)
        argocd = next(e for e in v.all_entries() if e.id == "argocd-ui")
        self.assertIsNotNone(argocd.secret_cmd)


class RenderHtml(unittest.TestCase):
    def test_page_has_layers_links_and_no_iframe(self):
        obs = {
            ("argocd", "argocd-server"): Observed(
                present=True, ready=True, node_port=30808, node_ip="10.0.2.11"
            )
        }
        html = render_html(build_view(_EP, obs))
        self.assertIn("<!doctype html>", html)
        self.assertIn("gitops", html)  # une couche
        self.assertIn('target="_blank"', html)  # lien nouvel onglet
        self.assertNotIn("<iframe", html)  # JAMAIS d'iframe (ADR 0091 §2)
        self.assertIn("http://10.0.2.11:30808", html)  # URL L4 (ADR 0092)

    def test_page_shows_secret_command_not_value(self):
        html = render_html(build_view(_EP, {}))
        # la COMMANDE kubectl est affichée…
        self.assertIn("kubectl -n argocd get secret", html)
        # …jamais une valeur de secret (pas de bloc « = <valeur> » décodée).
        self.assertIn("jsonpath", html)

    def test_html_is_escaped(self):
        ep = [
            {"id": "x<script>", "service": "s", "namespace": "n", "layer": "socle", "auth": "none"}
        ]
        html = render_html(build_view(ep, {}))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_page_shows_login_next_to_password(self):
        # Le portail affiche l'identifiant À CÔTÉ de la commande mot de passe (#login).
        html = render_html(build_view(_EP, {}))
        self.assertIn("identifiant", html)
        self.assertIn("<code>admin</code>", html)  # login argocd/grafana affiché
        self.assertIn("mot de passe", html)  # le libellé bascule quand un login existe


class _FakeApiException(Exception):
    def __init__(self, status):
        self.status = status


class ObserveCluster(unittest.TestCase):
    """observe_cluster avec une API k8s STUBÉE (aucun cluster)."""

    def _fake_apis(self, present, ready, node_ports, node_ip="10.0.2.11"):
        # core_v1 stub : read_namespaced_service rend un Service typé (spec.type/ports
        # avec node_port) ou lève 404 ; list_node rend un nœud Ready avec InternalIP.
        # Discovery : list_namespaced_endpoint_slice (objets typés).
        # FakeExc HÉRITE de la vraie ApiException (catchée par les `except ApiException`
        # des helpers) — on NE remplace PAS la classe globale (sinon pollution de
        # test_smoke qui construit de vraies ApiException).
        from kubernetes.client.exceptions import ApiException

        class FakeExc(ApiException):
            def __init__(self, status=404):
                self.status = status

        from types import SimpleNamespace as NS

        class CoreV1:
            def read_namespaced_service(self, svc, ns):
                # Un Service existe s'il est dans `present` (backend ClusterIP) OU s'il a
                # un nodePort déclaré (Service d'exposition `<svc>-nodeport`, ADR 0092).
                np = node_ports.get((ns, svc))
                if (ns, svc) not in present and np is None:
                    raise FakeExc(404)
                if np is not None:
                    spec = NS(type="NodePort", ports=[NS(node_port=np)])
                else:
                    spec = NS(type="ClusterIP", ports=[NS(node_port=None)])
                return NS(spec=spec)

            def list_node(self):
                ready_cond = NS(type="Ready", status="True")
                addr = NS(type="InternalIP", address=node_ip)
                node = NS(status=NS(conditions=[ready_cond], addresses=[addr]))
                return NS(items=[node] if node_ip else [])

        class Discovery:
            def list_namespaced_endpoint_slice(self, ns, label_selector=""):
                svc = label_selector.split("=")[-1]
                if (ns, svc) in ready:
                    ep = NS(conditions=NS(ready=True))
                    return NS(items=[NS(endpoints=[ep])])
                return NS(items=[])

        return (CoreV1(), Discovery())

    def test_present_ready_and_nodeport(self):
        eps = [
            {
                "id": "argocd-ui",
                "service": "argocd-server",
                "namespace": "argocd",
                "layer": "gitops",
                "auth": "secret-admin",
                "exposed": True,
            }
        ]
        apis = self._fake_apis(
            present={("argocd", "argocd-server")},
            ready={("argocd", "argocd-server")},
            node_ports={("argocd", "argocd-server"): 30808},
        )
        obs = portal_server.observe_cluster(eps, apis=apis)
        o = obs[("argocd", "argocd-server")]
        self.assertTrue(o.present)
        self.assertTrue(o.ready)
        self.assertEqual(o.node_port, 30808)
        self.assertEqual(o.node_ip, "10.0.2.11")

    def test_nodeport_on_separate_service(self):
        # ADR 0092 : pour une UI vendored, le ClusterIP du contrat (argocd-server) n'a
        # PAS de nodePort — il vit sur un Service SÉPARÉ `<svc>-nodeport`. Le portail
        # doit lire le port sur argocd-server-nodeport, pas sur argocd-server (sinon DRIFT
        # à tort, le bug observé sur dirqual).
        eps = [
            {
                "id": "argocd-ui",
                "service": "argocd-server",
                "namespace": "argocd",
                "layer": "gitops",
                "exposed": True,
            }
        ]
        apis = self._fake_apis(
            present={("argocd", "argocd-server")},  # ClusterIP présent (backend)
            ready={("argocd", "argocd-server")},
            node_ports={("argocd", "argocd-server-nodeport"): 32747},  # port sur le Service séparé
        )
        obs = portal_server.observe_cluster(eps, apis=apis)
        o = obs[("argocd", "argocd-server")]
        self.assertTrue(o.present)
        self.assertTrue(o.ready)
        self.assertEqual(o.node_port, 32747)  # lu sur argocd-server-nodeport
        self.assertEqual(o.node_ip, "10.0.2.11")

    def test_clusterip_service_has_no_nodeport(self):
        eps = [{"id": "x", "service": "internal", "namespace": "ns", "layer": "socle"}]
        apis = self._fake_apis(
            present={("ns", "internal")},
            ready=set(),
            node_ports={},  # ClusterIP
        )
        obs = portal_server.observe_cluster(eps, apis=apis)
        o = obs[("ns", "internal")]
        self.assertTrue(o.present)
        self.assertIsNone(o.node_port)
        self.assertIsNone(o.node_ip)  # pas de node_ip si pas de node_port

    def test_absent_service(self):
        eps = [{"id": "x", "service": "ghost", "namespace": "nope", "layer": "socle"}]
        apis = self._fake_apis(present=set(), ready=set(), node_ports={})
        obs = portal_server.observe_cluster(eps, apis=apis)
        self.assertFalse(obs[("nope", "ghost")].present)

    def test_build_page_end_to_end_with_stub(self):
        eps = [
            {
                "id": "argocd-ui",
                "service": "argocd-server",
                "namespace": "argocd",
                "layer": "gitops",
                "auth": "secret-admin",
                "exposed": True,
            }
        ]
        apis = self._fake_apis(
            present={("argocd", "argocd-server")},
            ready={("argocd", "argocd-server")},
            node_ports={("argocd", "argocd-server"): 30808},
        )
        # stub load_endpoints pour ne pas dépendre d'un fichier
        orig = portal_server.load_endpoints
        portal_server.load_endpoints = lambda path=None: eps
        try:
            html = portal_server.build_page(apis=apis)
        finally:
            portal_server.load_endpoints = orig
        self.assertIn("<!doctype html>", html)
        self.assertIn("http://10.0.2.11:30808", html)


if __name__ == "__main__":
    unittest.main()
