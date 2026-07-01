"""Tests du validateur code-location.manifest (ADR 0094 §3 / ADR 0017 : logique testée).

unittest (stdlib) — c'est ce qu'utilise le dépôt (`test:python` =
`python -m unittest discover -s tests`). Les fonctions testées sont PURES : on
leur injecte le manifeste déjà parsé (dict) + les « faits » du contrat (sets),
donc aucun accès disque/git.

Couvre : le schéma (champs requis, types de `ready`/`revision`, quantités
`resources`), la `contractVersion` connue/inconnue, la résolution des dépendances
(base/secret/storageClass fournies → OK, absentes → BLOQUANT), les dépendances
non vérifiables statiquement (codeLocations/migrations → WARNING), `ready: false`
→ WARNING, et l'extraction des faits du contrat.

Lancé par `python3 -m unittest discover -s tests` (cible `test:python` + CI).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_code_location_manifest import (  # noqa: E402
    ERROR,
    WARNING,
    check_contract_version,
    check_dependencies,
    check_ready,
    check_schema,
    cnpg_role_names,
    contract_databases,
    contract_secrets,
    contract_versions,
    is_valid_quantity,
    storage_class_names,
    validate_manifest,
)


def valid_manifest(**overrides):
    """Un manifeste minimal VALIDE (déps résolubles par les faits ci-dessous)."""
    base = {
        "codeLocation": "citation",
        "ready": True,
        "revision": "a3f9c1d",
        "contractVersion": "1.0",
        "resources": {"cpu": "500m", "memory": "1Gi", "disk": "20Gi"},
        "dependsOn": {
            "database": ["pgvector"],
            "secrets": ["pgvector-pg-auth"],
            "buckets": [{"name": "atlas-datalake", "storageClass": "rook-ceph-datalake"}],
        },
    }
    base.update(overrides)
    return base


# Faits du contrat cluster (ce que gather_cluster_facts extrait en prod).
KNOWN_VERSIONS = {"1.0"}
KNOWN_DATABASES = {"dagster", "pgvector", "marquez", "mlflow", "cache"}
KNOWN_SECRETS = {"pgvector-pg-auth", "dagster-pg-auth", "pg-role-pgvector", "pg-backup-s3"}
KNOWN_SCS = {"rook-ceph-datalake", "rook-ceph-block-replicated"}


def levels(findings):
    return [f.level for f in findings]


def messages(findings):
    return " || ".join(f.message for f in findings)


class SchemaTests(unittest.TestCase):
    def test_valid_manifest_has_no_schema_finding(self):
        self.assertEqual(check_schema(valid_manifest()), [])

    def test_missing_required_field_is_error(self):
        m = valid_manifest()
        del m["revision"]
        findings = check_schema(m)
        self.assertIn(ERROR, levels(findings))
        self.assertIn("revision", messages(findings))

    def test_ready_must_be_boolean(self):
        findings = check_schema(valid_manifest(ready="true"))  # str, pas bool
        self.assertIn(ERROR, levels(findings))
        self.assertIn("ready", messages(findings))

    def test_revision_main_rejected(self):
        # `main`/`HEAD` ne sont pas des révisions figées (ADR 0094 §3).
        findings = check_schema(valid_manifest(revision="main"))
        self.assertIn(ERROR, levels(findings))
        self.assertIn("revision", messages(findings))

    def test_revision_full_sha_accepted(self):
        findings = check_schema(valid_manifest(revision="a3f9c1d2b4e6f8a0c2d4e6f8a0b2c4d6e8f0a2b4"))
        self.assertEqual(findings, [])

    def test_malformed_quantity_is_error(self):
        findings = check_schema(valid_manifest(resources={"cpu": "500x"}))
        self.assertIn(ERROR, levels(findings))

    def test_valid_quantities(self):
        for q in ("500m", "2", "1Gi", "20Gi", "1.5", "512Mi", "100M"):
            self.assertTrue(is_valid_quantity(q), q)
        for bad in ("500x", "", "Gi", None, 5):
            self.assertFalse(is_valid_quantity(bad), bad)


class ContractVersionTests(unittest.TestCase):
    def test_known_version_ok(self):
        self.assertEqual(check_contract_version(valid_manifest(), KNOWN_VERSIONS), [])

    def test_unknown_version_is_error(self):
        findings = check_contract_version(valid_manifest(contractVersion="9.9"), KNOWN_VERSIONS)
        self.assertIn(ERROR, levels(findings))
        self.assertIn("9.9", messages(findings))

    def test_integer_version_coerced_to_str(self):
        # ADR 0094 §3 montre `contractVersion: 3` (int) ; on compare en str.
        findings = check_contract_version(valid_manifest(contractVersion=1.0), {"1.0"})
        self.assertEqual(findings, [])


class DependencyTests(unittest.TestCase):
    def test_all_dependencies_resolved(self):
        findings = check_dependencies(valid_manifest(), KNOWN_DATABASES, KNOWN_SECRETS, KNOWN_SCS)
        self.assertNotIn(ERROR, levels(findings))

    def test_missing_database_is_error(self):
        m = valid_manifest(dependsOn={"database": ["ghost-db"]})
        findings = check_dependencies(m, KNOWN_DATABASES, KNOWN_SECRETS, KNOWN_SCS)
        self.assertIn(ERROR, levels(findings))
        self.assertIn("ghost-db", messages(findings))

    def test_missing_secret_is_error(self):
        m = valid_manifest(dependsOn={"secrets": ["ghost-secret"]})
        findings = check_dependencies(m, KNOWN_DATABASES, KNOWN_SECRETS, KNOWN_SCS)
        self.assertIn(ERROR, levels(findings))

    def test_unknown_storage_class_is_error(self):
        m = valid_manifest(dependsOn={"buckets": [{"name": "b", "storageClass": "ghost-sc"}]})
        findings = check_dependencies(m, KNOWN_DATABASES, KNOWN_SECRETS, KNOWN_SCS)
        self.assertIn(ERROR, levels(findings))
        self.assertIn("ghost-sc", messages(findings))

    def test_inter_app_and_migration_are_warnings(self):
        m = valid_manifest(dependsOn={"codeLocations": ["mediawatch"], "migrations": ["001.sql"]})
        findings = check_dependencies(m, KNOWN_DATABASES, KNOWN_SECRETS, KNOWN_SCS)
        self.assertNotIn(ERROR, levels(findings))
        self.assertEqual(levels(findings), [WARNING, WARNING])


class ReadyTests(unittest.TestCase):
    def test_ready_true_no_finding(self):
        self.assertEqual(check_ready(valid_manifest(ready=True)), [])

    def test_ready_false_is_warning(self):
        findings = check_ready(valid_manifest(ready=False))
        self.assertEqual(levels(findings), [WARNING])


class ValidateManifestTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        findings = validate_manifest(
            valid_manifest(), KNOWN_VERSIONS, KNOWN_DATABASES, KNOWN_SECRETS, KNOWN_SCS
        )
        self.assertNotIn(ERROR, levels(findings))

    def test_invalid_manifest_fails_bloquant(self):
        m = valid_manifest(contractVersion="9.9", dependsOn={"database": ["ghost"]})
        findings = validate_manifest(m, KNOWN_VERSIONS, KNOWN_DATABASES, KNOWN_SECRETS, KNOWN_SCS)
        self.assertIn(ERROR, levels(findings))


class ContractFactsTests(unittest.TestCase):
    def test_contract_versions_extraction(self):
        docs = [{"contract_version": "1.0"}, {"contract_version": "1.0"}, {"other": 1}]
        self.assertEqual(contract_versions(docs), {"1.0"})

    def test_cnpg_role_names(self):
        cluster = {
            "kind": "Cluster",
            "spec": {"managed": {"roles": [{"name": "pgvector"}, {"name": "dagster"}]}},
        }
        self.assertEqual(cnpg_role_names([cluster]), {"pgvector", "dagster"})

    def test_contract_databases_unions_contract_and_cnpg(self):
        nss = {"secrets": {"postgres_roles": {"items": [{"role": "cache"}]}}}
        self.assertEqual(
            contract_databases(nss, {"pgvector", "dagster"}),
            {"pgvector", "dagster", "cache"},
        )

    def test_contract_secrets_all_sections(self):
        nss = {
            "secrets": {
                "postgres_roles": {"items": [{"secret": "pg-role-pgvector"}]},
                "derived": [{"secret": "pgvector-pg-auth"}],
                "s3_backup": {"secret": "pg-backup-s3"},
            }
        }
        self.assertEqual(
            contract_secrets(nss),
            {"pg-role-pgvector", "pgvector-pg-auth", "pg-backup-s3"},
        )

    def test_storage_class_names(self):
        docs = [
            {"kind": "StorageClass", "metadata": {"name": "rook-ceph-datalake"}},
            {"kind": "Service", "metadata": {"name": "not-a-sc"}},
        ]
        self.assertEqual(storage_class_names(docs), {"rook-ceph-datalake"})


if __name__ == "__main__":
    unittest.main()
