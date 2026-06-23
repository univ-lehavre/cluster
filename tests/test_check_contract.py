"""Tests du garde-fou check-contract (ADR 0043 / ADR 0017 : logique testée).

unittest (stdlib) — c'est ce qu'utilise le dépôt (`test:python` =
`python -m unittest discover -s tests`). Les fonctions testées sont PURES : on
leur injecte des docs YAML déjà parsés (dicts), donc aucun accès disque/git.

Couvre le piège central : un `service` du contrat se prouve par 4 voies (Service
littéral, backendRef d'HTTPRoute, dérivation d'opérateur CNPG/Rook, helm-only).
Chaque voie est testée OK + son rename → rouge, plus la cohérence FQDN, le drift
de provisioner de StorageClass, le rename de Secret de rôle CNPG et la clé STRICTE
des secrets dérivés.

Lancé par `python3 -m unittest discover -s tests` (cible `test:python` + CI).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_contract import (  # noqa: E402
    ERROR,
    WARNING,
    appproject_destination_namespaces,
    check_endpoint,
    check_postgres_role_secrets,
    check_storage_class,
    cnpg_role_secret_names,
    derive_operator_services,
    expected_fqdn,
    index_source_docs,
    resolve_service,
    scan_unknown_generator_crs,
    secret_keys,
)


def service_doc(name, namespace=None):
    meta = {"name": name}
    if namespace is not None:
        meta["namespace"] = namespace
    return {"apiVersion": "v1", "kind": "Service", "metadata": meta}


def httproute_doc(name, backends):
    return {
        "kind": "HTTPRoute",
        "metadata": {"name": name},
        "spec": {"rules": [{"backendRefs": [{"name": b, "port": 80} for b in backends]}]},
    }


def cnpg_cluster_doc(name, role_secrets=()):
    return {
        "apiVersion": "postgresql.cnpg.io/v1",
        "kind": "Cluster",
        "metadata": {"name": name, "namespace": "postgres"},
        "spec": {
            "managed": {
                "roles": [{"name": r, "passwordSecret": {"name": s}} for r, s in role_secrets]
            }
        },
    }


def levels(findings):
    return [f.level for f in findings]


def has_error(findings):
    return any(f.level == ERROR for f in findings)


def has_warning(findings):
    return any(f.level == WARNING for f in findings)


# ─────────────────────────────────────────────────────────────────────────────
# Fonctions élémentaires
# ─────────────────────────────────────────────────────────────────────────────
class ExpectedFqdn(unittest.TestCase):
    def test_standard_form(self):
        self.assertEqual(expected_fqdn("pg-rw", "postgres"), "pg-rw.postgres.svc.cluster.local")


class DeriveOperatorServices(unittest.TestCase):
    def test_cnpg_cluster_generates_rw_ro_r(self):
        self.assertEqual(derive_operator_services("Cluster", "pg"), {"pg-rw", "pg-ro", "pg-r"})

    def test_rook_objectstore_generates_rgw(self):
        self.assertEqual(
            derive_operator_services("CephObjectStore", "datalake"),
            {"rook-ceph-rgw-datalake"},
        )

    def test_unknown_kind_generates_nothing(self):
        self.assertEqual(derive_operator_services("Deployment", "x"), set())


class IndexSourceDocs(unittest.TestCase):
    def test_classifies_three_views(self):
        docs = [
            service_doc("gitea-http", "gitea"),
            httproute_doc("argocd-server", ["argocd-server"]),
            cnpg_cluster_doc("pg", [("dagster", "pg-role-dagster")]),
            {"kind": "ConfigMap", "metadata": {"name": "noise"}},
        ]
        literal, backends, crs = index_source_docs(docs)
        self.assertIn("gitea-http", literal)
        self.assertEqual(backends, {"argocd-server"})
        self.assertEqual(crs, [("Cluster", "pg")])


# ─────────────────────────────────────────────────────────────────────────────
# resolve_service : les 4 voies + leurs renames
# ─────────────────────────────────────────────────────────────────────────────
class ResolveService(unittest.TestCase):
    def test_literal_match(self):
        literal, backends, crs = index_source_docs([service_doc("gitea-http", "gitea")])
        self.assertEqual(resolve_service("gitea-http", literal, backends, crs), "literal")

    def test_literal_renamed_is_unresolved(self):
        # Manifeste renommé gitea-http -> gitea-web sans MAJ du contrat → None.
        literal, backends, crs = index_source_docs([service_doc("gitea-web", "gitea")])
        self.assertIsNone(resolve_service("gitea-http", literal, backends, crs))

    def test_route_backend_match(self):
        literal, backends, crs = index_source_docs([httproute_doc("r", ["argocd-server"])])
        self.assertEqual(resolve_service("argocd-server", literal, backends, crs), "route")

    def test_route_backend_renamed_is_unresolved(self):
        literal, backends, crs = index_source_docs([httproute_doc("r", ["argocd-srv"])])
        self.assertIsNone(resolve_service("argocd-server", literal, backends, crs))

    def test_cnpg_generated_match(self):
        literal, backends, crs = index_source_docs([cnpg_cluster_doc("pg")])
        self.assertEqual(resolve_service("pg-rw", literal, backends, crs), "generated")
        self.assertEqual(resolve_service("pg-ro", literal, backends, crs), "generated")

    def test_cnpg_cluster_renamed_breaks_derivation(self):
        # Cluster pg -> pgsql : derive ne produit plus pg-rw → None (rename détecté).
        literal, backends, crs = index_source_docs([cnpg_cluster_doc("pgsql")])
        self.assertIsNone(resolve_service("pg-rw", literal, backends, crs))

    def test_rook_generated_match(self):
        docs = [{"kind": "CephObjectStore", "metadata": {"name": "datalake"}}]
        literal, backends, crs = index_source_docs(docs)
        self.assertEqual(
            resolve_service("rook-ceph-rgw-datalake", literal, backends, crs), "generated"
        )

    def test_nodeport_anchor_match(self):
        # ADR 0092 : un Service `<service>-nodeport` séparé ancre l'exposition L4
        # d'une UI helm-only (le backend lui-même n'est pas un Service littéral).
        literal, backends, crs = index_source_docs(
            [service_doc("kubernetes-dashboard-nodeport", "kubernetes-dashboard")]
        )
        self.assertEqual(
            resolve_service("kubernetes-dashboard", literal, backends, crs), "nodeport"
        )

    def test_nodeport_renamed_is_unresolved(self):
        # NodePort renommé (hors convention `<service>-nodeport`) → plus d'ancrage.
        literal, backends, crs = index_source_docs(
            [service_doc("dashboard-np", "kubernetes-dashboard")]
        )
        self.assertIsNone(resolve_service("kubernetes-dashboard", literal, backends, crs))


# ─────────────────────────────────────────────────────────────────────────────
# check_endpoint : ancrage, namespace, fqdn, cas helm-only
# ─────────────────────────────────────────────────────────────────────────────
class CheckEndpoint(unittest.TestCase):
    def _endpoint(self, **over):
        ep = {
            "id": "gitea-ui",
            "service": "gitea-http",
            "namespace": "gitea",
            "fqdn": "gitea-http.gitea.svc.cluster.local",
            "source": "platform/gitea/service.yaml",
        }
        ep.update(over)
        return ep

    def test_literal_ok_no_findings(self):
        literal, backends, crs = index_source_docs([service_doc("gitea-http", "gitea")])
        findings = check_endpoint(self._endpoint(), literal, backends, crs, True)
        self.assertEqual(findings, [])

    def test_literal_rename_is_error(self):
        literal, backends, crs = index_source_docs([service_doc("gitea-web", "gitea")])
        findings = check_endpoint(self._endpoint(), literal, backends, crs, True)
        self.assertTrue(has_error(findings))

    def test_namespace_mismatch_is_error(self):
        literal, backends, crs = index_source_docs([service_doc("gitea-http", "autre-ns")])
        findings = check_endpoint(self._endpoint(), literal, backends, crs, True)
        self.assertTrue(has_error(findings))

    def test_service_without_namespace_is_warning(self):
        # Cas Marquez : Service littéral sans metadata.namespace → warning, pas erreur.
        ep = self._endpoint(
            id="marquez-api",
            service="marquez",
            namespace="marquez",
            fqdn="marquez.marquez.svc.cluster.local",
            source="platform/marquez/marquez.yaml",
        )
        literal, backends, crs = index_source_docs([service_doc("marquez")])  # pas de namespace
        findings = check_endpoint(ep, literal, backends, crs, True)
        self.assertTrue(has_warning(findings))
        self.assertFalse(has_error(findings))

    def test_fqdn_incoherent_is_error(self):
        ep = self._endpoint(fqdn="gitea-http.WRONG.svc.cluster.local")
        literal, backends, crs = index_source_docs([service_doc("gitea-http", "gitea")])
        findings = check_endpoint(ep, literal, backends, crs, True)
        self.assertTrue(has_error(findings))

    def test_cnpg_generated_endpoint_ok(self):
        ep = self._endpoint(
            id="postgres-rw",
            service="pg-rw",
            namespace="postgres",
            fqdn="pg-rw.postgres.svc.cluster.local",
            source="platform/cloudnative-pg/cluster.yaml",
        )
        literal, backends, crs = index_source_docs([cnpg_cluster_doc("pg")])
        findings = check_endpoint(ep, literal, backends, crs, True)
        self.assertEqual(findings, [])

    def test_helm_only_directory_is_warning_not_error(self):
        # k8s-dashboard : source = répertoire de chart SANS aucun kind:Service.
        ep = self._endpoint(
            id="k8s-dashboard-ui",
            service="kubernetes-dashboard",
            namespace="kubernetes-dashboard",
            fqdn="kubernetes-dashboard.kubernetes-dashboard.svc.cluster.local",
            source="platform/k8s-dashboard/",
        )
        docs = [{"kind": "ServiceAccount", "metadata": {"name": "admin-user"}}]
        literal, backends, crs = index_source_docs(docs)
        findings = check_endpoint(ep, literal, backends, crs, source_has_doc=True)
        self.assertTrue(has_warning(findings))
        self.assertFalse(has_error(findings))


# ─────────────────────────────────────────────────────────────────────────────
# Garde anti-régression du registre d'opérateurs
# ─────────────────────────────────────────────────────────────────────────────
class ScanUnknownGeneratorCrs(unittest.TestCase):
    def test_flags_unknown_objectstore_kind(self):
        docs = [{"kind": "MinioObjectStore", "metadata": {"name": "ml"}}]
        self.assertEqual(scan_unknown_generator_crs(docs), [("MinioObjectStore", "ml")])

    def test_known_kinds_not_flagged(self):
        docs = [cnpg_cluster_doc("pg"), {"kind": "CephObjectStore", "metadata": {"name": "d"}}]
        self.assertEqual(scan_unknown_generator_crs(docs), [])


# ─────────────────────────────────────────────────────────────────────────────
# StorageClass : nom, provisioner, default sans annotation
# ─────────────────────────────────────────────────────────────────────────────
class CheckStorageClass(unittest.TestCase):
    def _sc_doc(self, name, provisioner, default_annot=False):
        meta = {"name": name}
        if default_annot:
            meta["annotations"] = {"storageclass.kubernetes.io/is-default-class": "true"}
        return {"kind": "StorageClass", "metadata": meta, "provisioner": provisioner}

    def test_match_ok(self):
        contract = {
            "name": "local-path",
            "provisioner": "rancher.io/local-path",
            "source": "storage/local-path/local-path-storage.yaml",
        }
        findings = check_storage_class(
            contract, [self._sc_doc("local-path", "rancher.io/local-path")]
        )
        self.assertEqual(findings, [])

    def test_name_absent_is_error(self):
        contract = {"name": "local-path", "provisioner": "rancher.io/local-path"}
        findings = check_storage_class(contract, [self._sc_doc("autre", "rancher.io/local-path")])
        self.assertTrue(has_error(findings))

    def test_provisioner_drift_is_error(self):
        contract = {"name": "local-path", "provisioner": "rancher.io/local-path"}
        findings = check_storage_class(contract, [self._sc_doc("local-path", "autre.io/x")])
        self.assertTrue(has_error(findings))

    def test_default_without_annotation_is_warning(self):
        contract = {
            "name": "rook-ceph-block-replicated",
            "provisioner": "rook-ceph.rbd.csi.ceph.com",
            "default": True,
        }
        findings = check_storage_class(
            contract, [self._sc_doc("rook-ceph-block-replicated", "rook-ceph.rbd.csi.ceph.com")]
        )
        self.assertTrue(has_warning(findings))
        self.assertFalse(has_error(findings))


# ─────────────────────────────────────────────────────────────────────────────
# Secrets : pg-role ↔ CNPG, clés des patrons
# ─────────────────────────────────────────────────────────────────────────────
class PostgresRoleSecrets(unittest.TestCase):
    def test_role_secret_present_in_cnpg_ok(self):
        cluster = cnpg_cluster_doc("pg", [("dagster", "pg-role-dagster")])
        names = cnpg_role_secret_names([cluster])
        self.assertEqual(check_postgres_role_secrets(["pg-role-dagster"], names), [])

    def test_role_secret_renamed_in_cnpg_is_error(self):
        # CNPG renomme pg-role-dagster -> pg-creds-dagster ; le contrat ne suit pas.
        cluster = cnpg_cluster_doc("pg", [("dagster", "pg-creds-dagster")])
        names = cnpg_role_secret_names([cluster])
        findings = check_postgres_role_secrets(["pg-role-dagster"], names)
        self.assertTrue(has_error(findings))


class SecretKeys(unittest.TestCase):
    def test_strict_key_present_in_example(self):
        doc = {
            "kind": "Secret",
            "metadata": {"name": "dagster-pg-auth"},
            "stringData": {"postgresql-password": "x"},
        }
        self.assertIn("postgresql-password", secret_keys([doc], "dagster-pg-auth"))

    def test_strict_key_absent_when_renamed(self):
        doc = {
            "kind": "Secret",
            "metadata": {"name": "dagster-pg-auth"},
            "stringData": {"password": "x"},  # clé non stricte
        }
        self.assertNotIn("postgresql-password", secret_keys([doc], "dagster-pg-auth"))


# ─────────────────────────────────────────────────────────────────────────────
# AppProject : namespaces de destination
# ─────────────────────────────────────────────────────────────────────────────
class AppProjectDestinations(unittest.TestCase):
    def test_extracts_destination_namespaces(self):
        doc = {
            "kind": "AppProject",
            "metadata": {"name": "atlas"},
            "spec": {
                "destinations": [
                    {"namespace": "dagster"},
                    {"namespace": "marquez"},
                ]
            },
        }
        self.assertEqual(appproject_destination_namespaces([doc]), {"dagster", "marquez"})


if __name__ == "__main__":
    unittest.main()
