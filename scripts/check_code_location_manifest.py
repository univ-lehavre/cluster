#!/usr/bin/env python3
"""Validateur du manifeste de déclaration montant atlas → cluster (ADR 0094 §3).

Une code-location applicative atlas FOURNIT un `code-location.manifest.yaml` qui
DÉCLARE ce qu'elle apporte et consomme (base, secret dérivé, OBC, migration,
dépendances inter-apps) et CONTRE QUELLE version du contrat cluster elle code.
Avant de créer l'`Application` Argo CD (App-of-Apps, ADR 0094 §2), cluster LIT et
VALIDE ce manifeste. Ce validateur EST cette étape « cluster VALIDE » : il attrape
EN REVUE une déclaration incohérente (version de contrat inconnue, dépendance
absente du socle, schéma cassé) qui, sinon, ne se verrait qu'au run — ou pire,
dériverait en silence (la copie figée = cause racine de l'audit #499).

Ce qu'il REMPLACE : la proposition montante initiale faisait COPIER le contrat
cluster côté atlas (« D3 »). On supprime la copie figée : atlas DÉCLARE ce qu'il
consomme + `contractVersion` ; cluster VALIDE version ET existence des
dépendances. Un contrat déclaré + validé à l'instanciation échoue BRUYAMMENT dès
qu'une version ou une dépendance manque (ADR 0094 §3, Conséquences).

Périmètre de vérification (le piège du check naïf) : ce qui est vérifiable
STATIQUEMENT depuis le seul dépôt cluster est BLOQUANT ; ce qui relève d'atlas
(migration `.sql`, code d'une autre code-location) ou du runtime (capacité réelle
du cluster) est WARNING, jamais un faux-rouge.

  BLOQUANT (exit 1) — vérifiable depuis le manifeste + `contract/*.example.yaml`
  + manifestes versionnés cluster SEULS, et un écart = un bug réel :
    • schéma : champ requis manquant, mauvais type (`ready` non booléen,
      `revision` vide/absente, `codeLocation` absent) ;
    • `contractVersion` absente ou INCONNUE du contrat cluster courant
      (contract/*.example.yaml : `contract_version`) ;
    • `dependsOn.database` : base logique non déclarée par le contrat
      (postgres_roles) ni par le Cluster CNPG versionné ;
    • `dependsOn.secrets` : secret non déclaré par le contrat
      (postgres_roles / derived / s3_backup) ;
    • `dependsOn.buckets[].storageClass` : StorageClass absente du dépôt ;
    • `resources` : valeur de quantité Kubernetes malformée (cpu/memory/disk).

  WARNING (n'échoue pas) — non vérifiable de façon fiable depuis le code cluster
  seul, ou légitimement dynamique :
    • `dependsOn.codeLocations` : dépendance INTER-APP (le code de l'autre
      code-location vit dans atlas, hors dépôt cluster) — cluster l'ORDONNE au
      déploiement (sync-waves), pas vérifiable ici ;
    • `dependsOn.migrations` : le `.sql` est FOURNI par atlas (schéma métier),
      absent du dépôt cluster par conception (ADR 0094 §5) ;
    • `ready: false` : atlas n'atteste pas encore — cluster ne déploiera pas,
      mais ce n'est pas une erreur de manifeste ;
    • capacité (`resources`/`buckets[].size`) : confrontée à la capacité RÉELLE
      du cluster au seed, pas statiquement.

La logique est isolée en fonctions PURES (validation de schéma, de version, de
dépendances), testées par tests/test_check_code_location_manifest.py (ADR 0017 :
tout script de logique est testé). Les lectures disque sont injectées, donc le
cœur est testable sans toucher au disque. Python plutôt que bash : parsing YAML +
jointures inter-fichiers contrat↔manifeste (ADR 0049 « logique non triviale »).

Usage : python3 scripts/check_code_location_manifest.py [MANIFESTE...]
  (via `pnpm lint:code-location` — défaut : le patron
  contract/code-location.manifest.example.yaml).
Sort en 1 dès qu'un constat BLOQUANT est trouvé, 0 sinon (warnings inclus),
2 sur erreur de configuration (contrat/manifeste introuvable, PyYAML absent).
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dépendance déclarée dans pyproject
    print(
        "check-code-location: PyYAML manquant. `uv sync` (dépendance déclarée dans "
        "pyproject.toml) avant de lancer ce garde-fou.",
        file=sys.stderr,
    )
    raise SystemExit(2) from None


ERROR = "error"
WARNING = "warning"

# Champs requis à la racine du manifeste (ADR 0094 §3).
REQUIRED_FIELDS = ("codeLocation", "ready", "revision", "contractVersion")

# Quantité Kubernetes (cpu: 500m / 2, memory: 1Gi, disk: 20Gi) — forme tolérante :
# nombre décimal + suffixe optionnel (m, k/M/G/T/P/E, ou binaire Ki/Mi/…/Ei).
_QUANTITY_RE = re.compile(r"^\d+(\.\d+)?(m|[kKMGTPE]i?)?$")

# Un SHA git court/long : hex, 7 à 40 caractères. `main`/`HEAD` ne sont PAS des
# révisions figées (ADR 0094 §3 : le SHA est le signal canonique) → rejetés.
_REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True)
class Finding:
    """Un constat du check. `level` ∈ {error, warning}; `error` ⇒ exit 1."""

    level: str
    message: str


# ═════════════════════════════════════════════════════════════════════════════
# FONCTIONS PURES (testées sans disque)
# ═════════════════════════════════════════════════════════════════════════════


def is_valid_quantity(value: object) -> bool:
    """Une valeur de `resources` est-elle une quantité Kubernetes bien formée ?"""
    return isinstance(value, str) and bool(_QUANTITY_RE.match(value))


def check_schema(manifest: dict) -> list[Finding]:
    """Champs requis présents et bien typés (ADR 0094 §3). Fonction pure."""
    findings: list[Finding] = []
    cl = manifest.get("codeLocation", "<sans-codeLocation>")

    for field in REQUIRED_FIELDS:
        if field not in manifest:
            findings.append(
                Finding(ERROR, f"manifeste '{cl}': champ requis '{field}' absent (ADR 0094 §3).")
            )

    if "ready" in manifest and not isinstance(manifest["ready"], bool):
        findings.append(
            Finding(
                ERROR,
                f"manifeste '{cl}': `ready` doit être un booléen (true/false), "
                f"trouvé {type(manifest['ready']).__name__}.",
            )
        )

    revision = manifest.get("revision")
    if revision is not None and not (isinstance(revision, str) and _REVISION_RE.match(revision)):
        findings.append(
            Finding(
                ERROR,
                f"manifeste '{cl}': `revision` '{revision}' n'est pas un SHA git "
                "(hex 7-40 car.) — `main`/`HEAD` interdits : le SHA est le signal "
                "canonique d'évolution (ADR 0094 §3).",
            )
        )

    # `resources` : chaque quantité déclarée doit être bien formée (bloquant : une
    # requête malformée ferait échouer la validation de capacité au seed).
    for key, value in (manifest.get("resources") or {}).items():
        if not is_valid_quantity(value):
            findings.append(
                Finding(
                    ERROR,
                    f"manifeste '{cl}': resources.{key} '{value}' n'est pas une quantité "
                    "Kubernetes valide (ex. 500m, 1Gi, 20Gi).",
                )
            )

    return findings


def check_contract_version(manifest: dict, known_versions: set[str]) -> list[Finding]:
    """La `contractVersion` ciblée existe-t-elle dans le contrat cluster ? Pure.

    `known_versions` = les `contract_version` déclarés par contract/*.example.yaml.
    Une version inconnue ÉCHOUE BRUYAMMENT (ADR 0094 §3 : remplace la copie figée).
    """
    if "contractVersion" not in manifest:
        return []  # déjà signalé par check_schema
    cl = manifest.get("codeLocation", "<sans-codeLocation>")
    declared = str(manifest["contractVersion"])
    if declared not in known_versions:
        return [
            Finding(
                ERROR,
                f"manifeste '{cl}': contractVersion '{declared}' inconnue du contrat cluster "
                f"courant (versions publiées : {sorted(known_versions)}). atlas code contre une "
                "version que cluster ne fournit pas — dérive attrapée au lieu d'un run cassé.",
            )
        ]
    return []


def check_dependencies(
    manifest: dict,
    known_databases: set[str],
    known_secrets: set[str],
    known_storage_classes: set[str],
) -> list[Finding]:
    """Chaque dépendance déclarée est-elle FOURNIE par le socle cluster ? Pure.

    Vérifiable statiquement (→ BLOQUANT) : database, secrets, buckets[].storageClass.
    Non vérifiable depuis cluster seul (→ WARNING) : codeLocations (code atlas),
    migrations (`.sql` atlas, ADR 0094 §5).
    """
    findings: list[Finding] = []
    cl = manifest.get("codeLocation", "<sans-codeLocation>")
    depends = manifest.get("dependsOn") or {}

    for db in depends.get("database", []) or []:
        if db not in known_databases:
            findings.append(
                Finding(
                    ERROR,
                    f"manifeste '{cl}': base '{db}' requise mais non fournie par le socle "
                    "(absente des postgres_roles du contrat et du Cluster CNPG versionné).",
                )
            )

    for secret in depends.get("secrets", []) or []:
        if secret not in known_secrets:
            findings.append(
                Finding(
                    ERROR,
                    f"manifeste '{cl}': secret '{secret}' requis mais non déclaré par le contrat "
                    "cluster (postgres_roles / derived / s3_backup). cluster ne le dérivera pas.",
                )
            )

    for bucket in depends.get("buckets", []) or []:
        sc = (bucket or {}).get("storageClass")
        name = (bucket or {}).get("name", "<sans-nom>")
        if sc and sc not in known_storage_classes:
            findings.append(
                Finding(
                    ERROR,
                    f"manifeste '{cl}': bucket '{name}' réclame la storageClass '{sc}' absente du "
                    f"dépôt (connues : {sorted(known_storage_classes)}).",
                )
            )

    # WARNING : dépendances non vérifiables depuis le seul dépôt cluster.
    for other in depends.get("codeLocations", []) or []:
        findings.append(
            Finding(
                WARNING,
                f"manifeste '{cl}': dépend de la code-location '{other}' — code hors dépôt "
                "cluster ; cluster l'ORDONNE au déploiement (sync-waves Argo CD, ADR 0094 §3), "
                "non vérifiable statiquement ici.",
            )
        )
    for migration in depends.get("migrations", []) or []:
        findings.append(
            Finding(
                WARNING,
                f"manifeste '{cl}': migration '{migration}' FOURNIE par atlas (schéma métier, "
                "ADR 0094 §5) — absente du dépôt cluster par conception ; appliquée en hook "
                "PreSync, non vérifiable ici.",
            )
        )

    return findings


def check_ready(manifest: dict) -> list[Finding]:
    """`ready: false` = atlas n'atteste pas encore → WARNING (pas une erreur). Pure."""
    if manifest.get("ready") is False:
        cl = manifest.get("codeLocation", "<sans-codeLocation>")
        return [
            Finding(
                WARNING,
                f"manifeste '{cl}': `ready: false` — atlas n'atteste pas (code non mergé/taggé/"
                "testé). cluster ne créera pas l'Application tant que ready ≠ true.",
            )
        ]
    return []


def validate_manifest(
    manifest: dict,
    known_versions: set[str],
    known_databases: set[str],
    known_secrets: set[str],
    known_storage_classes: set[str],
) -> list[Finding]:
    """Agrège toutes les vérifs pour un manifeste. Fonction pure (racine testable)."""
    findings = check_schema(manifest)
    findings += check_contract_version(manifest, known_versions)
    findings += check_dependencies(manifest, known_databases, known_secrets, known_storage_classes)
    findings += check_ready(manifest)
    return findings


# ── Extraction des « faits » du contrat cluster (pures : dicts déjà parsés) ──


def contract_versions(contract_docs: Iterable[dict]) -> set[str]:
    """Les `contract_version` publiés par contract/*.example.yaml. Pure."""
    return {
        str(doc["contract_version"])
        for doc in contract_docs
        if isinstance(doc, dict) and doc.get("contract_version") is not None
    }


def contract_databases(nss_doc: dict, cnpg_role_names: set[str]) -> set[str]:
    """Bases logiques fournies : rôles postgres du contrat + rôles CNPG versionnés.

    Le contrat (`postgres_roles.items[].role`) nomme les rôles/bases logiques
    exposés ; le Cluster CNPG versionné les porte (managed.roles). L'union est la
    surface réelle. Pure.
    """
    names: set[str] = set(cnpg_role_names)
    pg_roles = (nss_doc.get("secrets", {}) or {}).get("postgres_roles", {}) or {}
    for item in pg_roles.get("items", []) or []:
        role = item.get("role")
        if role:
            names.add(role)
    return names


def contract_secrets(nss_doc: dict) -> set[str]:
    """Tous les Secrets déclarés par le contrat : postgres_roles + derived + s3_backup. Pure."""
    secrets_section = nss_doc.get("secrets", {}) or {}
    names: set[str] = set()
    pg_roles = secrets_section.get("postgres_roles", {}) or {}
    for item in pg_roles.get("items", []) or []:
        if item.get("secret"):
            names.add(item["secret"])
    for item in secrets_section.get("derived", []) or []:
        if item.get("secret"):
            names.add(item["secret"])
    s3_backup = secrets_section.get("s3_backup", {}) or {}
    if s3_backup.get("secret"):
        names.add(s3_backup["secret"])
    return names


def cnpg_role_names(cluster_docs: Iterable[dict]) -> set[str]:
    """Noms de rôles managés déclarés par le Cluster CNPG versionné. Pure."""
    names: set[str] = set()
    for doc in cluster_docs:
        if not isinstance(doc, dict) or doc.get("kind") != "Cluster":
            continue
        for role in doc.get("spec", {}).get("managed", {}).get("roles", []) or []:
            if role.get("name"):
                names.add(role["name"])
    return names


def storage_class_names(docs: Iterable[dict]) -> set[str]:
    """Noms des kind:StorageClass présents dans un ensemble de docs. Pure."""
    return {
        (d.get("metadata") or {}).get("name")
        for d in docs
        if isinstance(d, dict) and d.get("kind") == "StorageClass"
    } - {None}


# ═════════════════════════════════════════════════════════════════════════════
# I/O — chargement des sources (NON pur ; injecté dans main)
# ═════════════════════════════════════════════════════════════════════════════


def load_yaml_docs(text: str) -> list[dict]:
    """Tous les documents d'un flux YAML multi-doc (docs None/scalaires filtrés)."""
    return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]


def _read_yaml_docs(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            return load_yaml_docs(handle.read())
    except (OSError, yaml.YAMLError):
        return []


def _read_yaml_dir(path: str) -> list[dict]:
    docs: list[dict] = []
    if os.path.isdir(path):
        for entry in sorted(os.listdir(path)):
            if entry.endswith((".yaml", ".yml")):
                docs.extend(_read_yaml_docs(os.path.join(path, entry)))
    return docs


def _read_single_doc(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle.read())
            return loaded if isinstance(loaded, dict) else None
    except (OSError, yaml.YAMLError):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═════════════════════════════════════════════════════════════════════════════


def gather_cluster_facts(repo_root: str) -> tuple[set[str], set[str], set[str], set[str]] | None:
    """Charge contract/ + platform/ + storage/ et en extrait les faits vérifiables.

    Retourne (known_versions, known_databases, known_secrets, known_storage_classes)
    ou None si le contrat est introuvable (erreur de configuration → exit 2).
    """
    contract_dir = os.path.join(repo_root, "contract")
    contract_paths = [
        os.path.join(contract_dir, name)
        for name in (
            "endpoints.example.yaml",
            "namespaces-secrets.example.yaml",
            "storage-classes.example.yaml",
        )
    ]
    contract_docs = [doc for path in contract_paths for doc in _read_yaml_docs(path)]
    if not contract_docs:
        return None

    nss_doc = _read_single_doc(os.path.join(contract_dir, "namespaces-secrets.example.yaml")) or {}
    cnpg_docs = _read_yaml_docs(os.path.join(repo_root, "platform/cloudnative-pg/cluster.yaml"))
    role_names = cnpg_role_names(cnpg_docs)

    # StorageClasses connues : profils Ceph (datalake + bloc) + local-path.
    sc_docs: list[dict] = []
    for rel in (
        "storage/ceph/storageClass/datalake/",
        "storage/ceph/storageClass/",
    ):
        sc_docs.extend(_read_yaml_dir(os.path.join(repo_root, rel)))
    known_scs = storage_class_names(sc_docs)

    return (
        contract_versions(contract_docs),
        contract_databases(nss_doc, role_names),
        contract_secrets(nss_doc),
        known_scs,
    )


def main(argv: list[str] | None = None) -> int:
    """Valide un ou plusieurs manifestes (défaut : le patron du contrat)."""
    argv = argv if argv is not None else sys.argv[1:]
    repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    facts = gather_cluster_facts(repo_root)
    if facts is None:
        print("check-code-location: contrat introuvable dans contract/.", file=sys.stderr)
        return 2
    known_versions, known_databases, known_secrets, known_scs = facts

    manifests = argv or [os.path.join(repo_root, "contract", "code-location.manifest.example.yaml")]

    findings: list[Finding] = []
    for path in manifests:
        manifest = _read_single_doc(path)
        if manifest is None:
            print(
                f"check-code-location: manifeste introuvable ou vide : {path}.",
                file=sys.stderr,
            )
            return 2
        for f in validate_manifest(
            manifest, known_versions, known_databases, known_secrets, known_scs
        ):
            # Préfixe le chemin pour situer le constat quand plusieurs manifestes.
            findings.append(Finding(f.level, f"[{os.path.basename(path)}] {f.message}"))

    return _report(findings)


def _report(findings: list[Finding]) -> int:
    warnings = [f for f in findings if f.level == WARNING]
    errors = [f for f in findings if f.level == ERROR]

    for finding in warnings:
        print(f"check-code-location: AVERTISSEMENT — {finding.message}", file=sys.stderr)
    for finding in errors:
        print(f"check-code-location: ERREUR — {finding.message}", file=sys.stderr)

    if errors:
        print(
            f"\ncheck-code-location: {len(errors)} déclaration(s) INVALIDE(S) (ADR 0094 §3), "
            f"{len(warnings)} avertissement(s). Corriger le manifeste atlas ou compléter le "
            "socle (base/secret/OBC) avant d'instancier l'Application.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check-code-location: OK — manifeste(s) de déclaration valide(s) "
        f"({len(warnings)} avertissement(s), 0 déclaration bloquante)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
