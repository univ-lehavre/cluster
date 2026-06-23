#!/usr/bin/env python3
"""Garde-fou ADR 0043 — le contrat d'interface cluster→atlas colle au socle réel.

Le dépôt publie un CONTRAT (`contract/*.example.yaml`, valeurs génériques ADR
0023) décrivant ce que `cluster` expose à `atlas` : endpoints (Service/ns/FQDN),
namespaces & Secrets, StorageClasses. L'e2e du banc n'est pas CI-able (nested
virt / arm64), donc ce check STATIQUE est le vrai garde-fou : il attrape en REVUE
une dérive (rename de Service, rotation de clé de Secret, endpoint déplacé) qui,
sinon, ne se verrait qu'au run. Il lève la duplication assumée de l'ADR 0043 :
le contrat n'est plus une copie qui se périme en silence, il est vérifié.

Subtilité centrale (le piège du check naïf) : le champ `service` du contrat ne se
matérialise PAS toujours en `kind: Service` littéral dans `source`. Cinq formes
coexistent, qu'on prouve par l'ANCRAGE du nom dans la source (jamais « le fichier
existe », qui serait un faux-vert) :

  A. littéral   — `kind: Service` `name: <service>` présent tel quel
                  (gitea-http, registry, marquez*, dagster-*, seaweedfs).
  B. dérivé     — un CR d'opérateur engendre le Service par convention :
                  CNPG `Cluster pg` → pg-rw/pg-ro ; Rook `CephObjectStore datalake`
                  → rook-ceph-rgw-datalake. Le Service n'est PAS écrit.
  C. route      — le Service est référencé par `backendRefs[].name` d'une
                  HTTPRoute ; le Service réel vient du chart d'install, pas de
                  `source`. Renommer sans toucher la Route casse le routage réel
                  → on veut que ça casse le check aussi.
  D. helm-only  — `source` est un répertoire (chart figé) SANS aucun manifeste
                  `kind: Service` : la vérif d'ancrage n'est pas possible depuis le
                  code seul → WARNING, jamais bloquant.
  E. nodeport   — exposition L4 (ADR 0092) : le backend est servi par un chart figé
                  mais un Service NodePort SÉPARÉ `<service>-nodeport`
                  (platform/<brique>/nodeport.yaml) ancre l'exposition versionnée
                  (k8s-dashboard via kong). Renommer le NodePort casse le check.

Strictness (cf. docstring de `main`) : BLOQUANT = vérifiable depuis les
`.example.yaml` + manifestes versionnés SEULS, et un écart = un bug réel pour
atlas. WARNING = non vérifiable de façon fiable (helm amputé) ou légitimement
dynamique (StorageClass par défaut posée au banc par `set_default_sc`, ADR
0035/0036). Ne jamais produire de faux-rouge sur du runtime.

La logique est isolée en fonctions PURES (résolution de service, dérivation
d'opérateur, cohérence FQDN, comparaison contrat↔manifeste) testées par
tests/test_check_contract.py (ADR 0017 : tout script de logique est testé). Les
lectures disque (fichier / glob de répertoire) sont injectées, donc le cœur est
testable sans toucher au disque. Python plutôt que bash : parsing YAML multi-doc
+ jointures inter-fichiers (ADR 0017).

Usage : python3 scripts/check_contract.py   (via `pnpm lint:contract`).
Sort en code 1 dès qu'un constat BLOQUANT est trouvé, 0 sinon (warnings inclus),
2 sur erreur de configuration (contrat introuvable, PyYAML absent).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dépendance déclarée dans pyproject
    print(
        "check-contract: PyYAML manquant. `uv sync` (dépendance déclarée dans "
        "pyproject.toml) avant de lancer ce garde-fou.",
        file=sys.stderr,
    )
    raise SystemExit(2) from None


# ─────────────────────────────────────────────────────────────────────────────
# Registre des conventions d'opérateurs (ADR 0043, table-driven, §2 du design)
#
# On ne hardcode JAMAIS un cas (« pg-rw existe ») : on déclare la RÈGLE de
# dérivation par `kind` de CR. La reconnaissance « généré » = présence réelle du
# CR dans la source ; renommer le CR casse la dérivation → le rename est détecté.
# Étendre = ajouter UNE ligne (futur opérateur générateur de Service).
# ─────────────────────────────────────────────────────────────────────────────
OPERATOR_CONVENTIONS: dict[str, Callable[[str], set[str]]] = {
    # CNPG : un Cluster `X` engendre les Services X-rw / X-ro / X-r.
    "Cluster": lambda n: {f"{n}-rw", f"{n}-ro", f"{n}-r"},
    # Rook : un CephObjectStore `X` engendre le Service rook-ceph-rgw-X.
    "CephObjectStore": lambda n: {f"rook-ceph-rgw-{n}"},
}

CLUSTER_DNS_SUFFIX = "svc.cluster.local"

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    """Un constat du check. `level` ∈ {error, warning}; `error` ⇒ exit 1."""

    level: str
    message: str


# ═════════════════════════════════════════════════════════════════════════════
# FONCTIONS PURES (testées sans disque)
# ═════════════════════════════════════════════════════════════════════════════


def expected_fqdn(service: str, namespace: str) -> str:
    """FQDN intra-cluster déterministe d'un Service (forme Kubernetes standard)."""
    return f"{service}.{namespace}.{CLUSTER_DNS_SUFFIX}"


def derive_operator_services(kind: str, name: str) -> set[str]:
    """Services qu'un CR `(kind, name)` engendre selon le registre, sinon ∅."""
    convention = OPERATOR_CONVENTIONS.get(kind)
    return convention(name) if convention else set()


def index_source_docs(
    docs: Iterable[dict],
) -> tuple[dict[str, dict], set[str], list[tuple[str, str]]]:
    """Indexe les docs YAML d'une source en trois vues utiles à la résolution.

    Retourne :
      literal_services : {name -> doc Service}  (kind == Service)
      route_backends   : {tout backendRefs[].name d'une HTTPRoute}
      operator_crs     : [(kind, name) de chaque CR dont le kind est dans le registre]

    Fonction pure : on lui passe des dicts déjà parsés (aucun accès disque).
    """
    literal_services: dict[str, dict] = {}
    route_backends: set[str] = set()
    operator_crs: list[tuple[str, str]] = []

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        name = (doc.get("metadata") or {}).get("name")
        if kind == "Service" and name:
            literal_services[name] = doc
        elif kind == "HTTPRoute":
            for rule in doc.get("spec", {}).get("rules", []) or []:
                for ref in rule.get("backendRefs", []) or []:
                    ref_name = ref.get("name")
                    if ref_name:
                        route_backends.add(ref_name)
        elif kind in OPERATOR_CONVENTIONS and name:
            operator_crs.append((kind, name))

    return literal_services, route_backends, operator_crs


def resolve_service(
    service: str,
    literal_services: dict[str, dict],
    route_backends: set[str],
    operator_crs: Iterable[tuple[str, str]],
) -> str | None:
    """Prouve l'ANCRAGE d'un `service` dans une source, dans l'ordre A → C → B → E.

    Retourne le mode de preuve ("literal" | "route" | "generated" | "nodeport") ou
    None si le service n'est ancré par aucune voie reconnue (→ dérive bloquante côté
    appelant). Jamais basé sur l'`id`/le nom de fichier : seulement sur ce qui est
    présent.
    """
    if service in literal_services:
        return "literal"  # A
    if service in route_backends:
        return "route"  # C
    for kind, name in operator_crs:
        if service in derive_operator_services(kind, name):
            return "generated"  # B
    # E (ADR 0092) : le service est exposé en L4 par un Service NodePort SÉPARÉ nommé
    # par convention `<service>-nodeport` (platform/<brique>/nodeport.yaml). Pour les
    # UI helm-only (chart figé, pas de Service littéral du backend), ce NodePort EST
    # la preuve d'ancrage versionnée de l'exposition.
    if f"{service}-nodeport" in literal_services:
        return "nodeport"
    return None


def check_endpoint(
    endpoint: dict,
    literal_services: dict[str, dict],
    route_backends: set[str],
    operator_crs: list[tuple[str, str]],
    source_has_doc: bool,
) -> list[Finding]:
    """Vérifie un endpoint contre les docs de sa `source`. Fonction pure.

    `source_has_doc` indique si la source a livré au moins un manifeste parsable
    (sert à distinguer le cas D « répertoire helm sans Service » d'une source vide
    suspecte). Couvre : ancrage du service (A/B/C/D), cohérence du namespace quand
    le Service littéral le porte, et auto-cohérence du FQDN.
    """
    findings: list[Finding] = []
    ep_id = endpoint.get("id", "<sans-id>")
    service = endpoint.get("service")
    namespace = endpoint.get("namespace")
    fqdn = endpoint.get("fqdn")
    source = endpoint.get("source", "<source absente>")

    # ── 1. Ancrage du service (cœur anti-rename) ─────────────────────────────
    mode = resolve_service(service, literal_services, route_backends, operator_crs)
    if mode is None:
        # Cas D : source = répertoire de chart figé SANS aucun Service littéral,
        # backendRef ni CR opérateur → non vérifiable depuis le code (helm-only).
        # On ne sait pas inventer une preuve fiable → WARNING (pas un faux-rouge).
        if not literal_services and not route_backends and not operator_crs and source_has_doc:
            findings.append(
                Finding(
                    WARNING,
                    f"endpoint {ep_id}: service '{service}' non vérifiable dans {source} "
                    "(aucun kind:Service / HTTPRoute / CR opérateur — Service créé par le "
                    "chart, hors dépôt). Ancrage non prouvable statiquement.",
                )
            )
        else:
            # Au moins un générateur potentiel existe dans la source mais aucun ne
            # produit ce service → rename non répercuté. BLOQUANT.
            unknown_crs = [
                (k, n)
                for k, n in _all_crs(literal_services, route_backends, operator_crs)
                if k not in OPERATOR_CONVENTIONS
            ]
            hint = ""
            if unknown_crs:
                kinds = ", ".join(sorted({k for k, _ in unknown_crs}))
                hint = (
                    f" (un CR de kind générateur potentiel mais NON enregistré "
                    f"dans OPERATOR_CONVENTIONS est présent : {kinds} — compléter le registre "
                    "si ce kind engendre bien un Service)"
                )
            findings.append(
                Finding(
                    ERROR,
                    f"endpoint {ep_id}: service '{service}' introuvable dans {source} "
                    "(ni kind:Service littéral, ni backendRef d'HTTPRoute, ni CR opérateur "
                    f"dérivable){hint}.",
                )
            )

    # ── 2. Cohérence du namespace (uniquement si prouvable depuis le manifeste) ─
    # mode "nodeport" : on lit le ns du Service `<service>-nodeport` (ADR 0092).
    ns_doc_key = (
        service if mode == "literal" else (f"{service}-nodeport" if mode == "nodeport" else None)
    )
    if ns_doc_key is not None:
        svc_doc = literal_services[ns_doc_key]
        svc_ns = (svc_doc.get("metadata") or {}).get("namespace")
        if svc_ns is None:
            # Helm figé (Marquez) : le rendu n'a pas de metadata.namespace.
            findings.append(
                Finding(
                    WARNING,
                    f"endpoint {ep_id}: namespace '{namespace}' non vérifiable — le "
                    f"manifeste Service '{ns_doc_key}' de {source} n'a pas de metadata.namespace "
                    "(template helm figé).",
                )
            )
        elif svc_ns != namespace:
            findings.append(
                Finding(
                    ERROR,
                    f"endpoint {ep_id}: namespace contrat '{namespace}' ≠ "
                    f"metadata.namespace '{svc_ns}' du Service '{ns_doc_key}' dans {source}.",
                )
            )

    # ── 3. Auto-cohérence du FQDN (cohérence interne pure, déterministe) ──────
    if service and namespace and fqdn:
        wanted = expected_fqdn(service, namespace)
        if fqdn != wanted:
            findings.append(
                Finding(
                    ERROR,
                    f"endpoint {ep_id}: fqdn '{fqdn}' ≠ forme attendue "
                    f"'{wanted}' (service.namespace.{CLUSTER_DNS_SUFFIX}).",
                )
            )

    return findings


def _all_crs(
    literal_services: dict[str, dict],
    route_backends: set[str],
    operator_crs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    # Helper trivial : ici seuls les operator_crs connus sont indexés ; les CR de
    # kind INCONNU n'apparaissent pas dans operator_crs (index_source_docs ne
    # retient que les kinds enregistrés). On les recapte via _scan_unknown_crs.
    return list(operator_crs)


def scan_unknown_generator_crs(docs: Iterable[dict]) -> list[tuple[str, str]]:
    """CR dont le kind ressemble à un générateur mais n'est PAS au registre.

    Heuristique conservatrice : on signale tout `kind` se terminant par les motifs
    d'opérateurs connus (Cluster / ObjectStore) absent d'OPERATOR_CONVENTIONS, pour
    forcer la complétude du registre plutôt que laisser passer un faux-vert. Pure.
    """
    suspects: list[tuple[str, str]] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind") or ""
        name = (doc.get("metadata") or {}).get("name")
        if kind in OPERATOR_CONVENTIONS or not name:
            continue
        if kind.endswith("Cluster") or kind.endswith("ObjectStore"):
            suspects.append((kind, name))
    return suspects


def check_storage_class(
    sc_contract: dict,
    docs: Iterable[dict],
) -> list[Finding]:
    """Vérifie une StorageClass du contrat contre les docs de sa `source`. Pure."""
    findings: list[Finding] = []
    name = sc_contract.get("name")
    source = sc_contract.get("source", "<source absente>")
    contract_provisioner = sc_contract.get("provisioner")
    is_default = bool(sc_contract.get("default"))

    sc_doc = next(
        (
            d
            for d in docs
            if isinstance(d, dict)
            and d.get("kind") == "StorageClass"
            and (d.get("metadata") or {}).get("name") == name
        ),
        None,
    )
    if sc_doc is None:
        findings.append(
            Finding(
                ERROR,
                f"storageClass '{name}': aucun kind:StorageClass de ce nom dans {source}.",
            )
        )
        return findings

    manifest_provisioner = sc_doc.get("provisioner")
    if contract_provisioner and manifest_provisioner != contract_provisioner:
        findings.append(
            Finding(
                ERROR,
                f"storageClass '{name}': provisioner contrat '{contract_provisioner}' ≠ "
                f"manifeste '{manifest_provisioner}' dans {source}.",
            )
        )

    if is_default:
        annotations = (sc_doc.get("metadata") or {}).get("annotations") or {}
        flag = str(annotations.get("storageclass.kubernetes.io/is-default-class", "")).lower()
        if flag != "true":
            findings.append(
                Finding(
                    WARNING,
                    f"storageClass '{name}': contrat default:true mais le manifeste ne porte "
                    "pas l'annotation is-default-class (le défaut actif est posé au banc par "
                    "set_default_sc, ADR 0035/0036 — non bloquant).",
                )
            )
    return findings


def check_postgres_role_secrets(
    contract_secrets: list[str],
    cnpg_role_secret_names: set[str],
) -> list[Finding]:
    """Chaque `pg-role-*` du contrat doit exister comme passwordSecret CNPG. Pure."""
    findings: list[Finding] = []
    for secret in contract_secrets:
        if secret not in cnpg_role_secret_names:
            findings.append(
                Finding(
                    ERROR,
                    f"secret '{secret}': absent des managed.roles[].passwordSecret.name du "
                    "Cluster CNPG (rename de Secret de rôle non répercuté ?).",
                )
            )
    return findings


def cnpg_role_secret_names(cluster_docs: Iterable[dict]) -> set[str]:
    """Noms de passwordSecret déclarés par le Cluster CNPG. Pure."""
    names: set[str] = set()
    for doc in cluster_docs:
        if not isinstance(doc, dict) or doc.get("kind") != "Cluster":
            continue
        for role in doc.get("spec", {}).get("managed", {}).get("roles", []) or []:
            secret_name = (role.get("passwordSecret") or {}).get("name")
            if secret_name:
                names.add(secret_name)
    return names


def secret_keys(secret_docs: Iterable[dict], secret_name: str) -> set[str]:
    """Clés (data + stringData) d'un Secret nommé dans une source. Pure."""
    keys: set[str] = set()
    for doc in secret_docs:
        if not isinstance(doc, dict) or doc.get("kind") != "Secret":
            continue
        if (doc.get("metadata") or {}).get("name") != secret_name:
            continue
        keys.update((doc.get("data") or {}).keys())
        keys.update((doc.get("stringData") or {}).keys())
    return keys


def appproject_destination_namespaces(appproject_docs: Iterable[dict]) -> set[str]:
    """Namespaces de `destinations[]` d'un AppProject Argo CD. Pure."""
    namespaces: set[str] = set()
    for doc in appproject_docs:
        if not isinstance(doc, dict) or doc.get("kind") != "AppProject":
            continue
        for dest in doc.get("spec", {}).get("destinations", []) or []:
            ns = dest.get("namespace")
            if ns:
                namespaces.add(ns)
    return namespaces


# ═════════════════════════════════════════════════════════════════════════════
# I/O — chargement des sources (NON pur ; injecté dans main)
# ═════════════════════════════════════════════════════════════════════════════


def load_yaml_docs(text: str) -> list[dict]:
    """Tous les documents d'un flux YAML multi-doc (docs None/scalaires filtrés)."""
    return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]


def load_source_docs(source: str, repo_root: str) -> list[dict]:
    """Charge les docs YAML d'une `source` du contrat (fichier OU répertoire).

    Répertoire → concatène tous les `*.yaml`/`*.yml` (cas D / source-dossier).
    Source manquante → liste vide (le constat « source introuvable » est levé en
    amont par check_endpoint/check_storage_class via l'absence d'ancrage).
    """
    path = os.path.join(repo_root, source)
    docs: list[dict] = []
    if os.path.isdir(path):
        for entry in sorted(os.listdir(path)):
            if entry.endswith((".yaml", ".yml")):
                docs.extend(_read_yaml(os.path.join(path, entry)))
    elif os.path.isfile(path):
        docs.extend(_read_yaml(path))
    return docs


def _read_yaml(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            return load_yaml_docs(handle.read())
    except (OSError, yaml.YAMLError):
        return []


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═════════════════════════════════════════════════════════════════════════════


def main() -> int:
    """Charge contract/ + platform/ et agrège les constats.

    Niveau de strictness (cf. design §4) :

      BLOQUANT (exit 1) — vérifiable depuis les .example.yaml + manifestes
      versionnés SEULS, et un écart = un bug réel pour atlas :
        • service non ancré dans `source` (aucune voie A/B/C, source non helm-only)
        • kind générateur de Service inconnu du registre (force la complétude)
        • FQDN ≠ service.namespace.svc.cluster.local
        • StorageClass : nom absent de la source, ou provisioner divergent
        • namespace d'endpoint/secret absent de la liste `namespaces` du contrat
        • namespace `applicatif` absent des destinations de l'AppProject atlas
        • `pg-role-*` absent des passwordSecret CNPG
        • example_file de secret inexistant ; clé STRICTE dérivée absente
        • endpoint S3 du contrat incohérent avec object_store.endpoint (storage-classes)

      WARNING (n'échoue pas) — non vérifiable fiablement depuis le code seul, ou
      légitimement dynamique :
        • service helm-only (répertoire de chart sans Service in-repo : k8s-dashboard)
        • namespace non vérifiable (Service sans metadata.namespace : Marquez)
        • default:true sans annotation is-default-class (posé au banc, ADR 0035/0036)
        • namespace autorisé par l'AppProject mais absent du contrat (autorisation plus large)
        • object_store.bucket_storage_class absente du dépôt (drift contrat à corriger)
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    contract_dir = os.path.join(repo_root, "contract")

    endpoints_text = _read_text(os.path.join(contract_dir, "endpoints.example.yaml"))
    nss_text = _read_text(os.path.join(contract_dir, "namespaces-secrets.example.yaml"))
    sc_text = _read_text(os.path.join(contract_dir, "storage-classes.example.yaml"))
    if endpoints_text is None or nss_text is None or sc_text is None:
        print("check-contract: contrat introuvable dans contract/.", file=sys.stderr)
        return 2

    endpoints_doc = yaml.safe_load(endpoints_text) or {}
    nss_doc = yaml.safe_load(nss_text) or {}
    sc_doc = yaml.safe_load(sc_text) or {}

    findings: list[Finding] = []

    # Cache des sources déjà chargées (évite de re-parser un répertoire partagé).
    source_cache: dict[str, list[dict]] = {}

    def docs_for(source: str) -> list[dict]:
        if source not in source_cache:
            source_cache[source] = load_source_docs(source, repo_root)
        return source_cache[source]

    # ── Namespaces déclarés par le contrat (pour les recoupements internes) ──
    declared_namespaces = _declared_namespaces(nss_doc)

    # ── ENDPOINTS ────────────────────────────────────────────────────────────
    endpoints = endpoints_doc.get("endpoints", []) or []
    s3_endpoints: dict[str, str] = {}  # id -> "fqdn:port" pour recoupement storage
    for ep in endpoints:
        source = ep.get("source", "")
        source_docs = docs_for(source) if source else []
        literal, backends, crs = index_source_docs(source_docs)
        findings.extend(
            check_endpoint(ep, literal, backends, crs, source_has_doc=bool(source_docs))
        )
        # Garde anti-régression du registre : CR « générateur » non enregistré.
        for kind, name in scan_unknown_generator_crs(source_docs):
            findings.append(
                Finding(
                    ERROR,
                    f"endpoint {ep.get('id')}: CR {kind}/{name} dans {source} ressemble à un "
                    "générateur de Service mais son kind n'est pas dans OPERATOR_CONVENTIONS "
                    "(compléter le registre).",
                )
            )
        # Namespace de l'endpoint vs liste `namespaces` du contrat. La section
        # `namespaces` est SCOPÉE (applicatif = cibles atlas ; plateforme = socle où
        # un consommateur se branche) : les ns d'UI de bordure (gitea/argocd/mailpit/
        # kubernetes-dashboard) n'y figurent PAS par conception. Un endpoint dont le ns
        # manque n'est donc pas un bug pour atlas → WARNING (signale sans bloquer),
        # jamais un faux-rouge.
        ns = ep.get("namespace")
        if ns and ns not in declared_namespaces:
            findings.append(
                Finding(
                    WARNING,
                    f"endpoint {ep.get('id')}: namespace '{ns}' non listé dans la section "
                    "`namespaces` du contrat (attendu pour les UI de bordure ; à vérifier "
                    "si c'est un ns applicatif/plateforme).",
                )
            )
        if ep.get("id") in ("s3-datalake-ceph", "s3-datalake-light"):
            s3_endpoints[ep["id"]] = f"{ep.get('fqdn')}:{ep.get('port')}"

    # ── NAMESPACES applicatifs ↔ AppProject atlas ────────────────────────────
    findings.extend(_check_appproject(nss_doc, repo_root, docs_for))

    # ── SECRETS ──────────────────────────────────────────────────────────────
    findings.extend(_check_secrets(nss_doc, declared_namespaces, repo_root, docs_for))

    # ── STORAGECLASSES ───────────────────────────────────────────────────────
    findings.extend(_check_storage_classes(sc_doc, s3_endpoints, repo_root, docs_for))

    return _report(findings)


# ── sous-vérifs d'orchestration (gardent main lisible ; logique fine = pure) ──


def _declared_namespaces(nss_doc: dict) -> set[str]:
    namespaces = nss_doc.get("namespaces", {}) or {}
    declared: set[str] = set()
    for section in ("applicatif", "plateforme"):
        for item in (namespaces.get(section, {}) or {}).get("items", []) or []:
            if item.get("name"):
                declared.add(item["name"])
    return declared


def _check_appproject(nss_doc, repo_root, docs_for) -> list[Finding]:
    findings: list[Finding] = []
    namespaces = nss_doc.get("namespaces", {}) or {}
    app = namespaces.get("applicatif", {}) or {}
    appproject_source = app.get("source", "platform/argocd/appproject-atlas.yaml")
    appproject_docs = docs_for(appproject_source)
    allowed = appproject_destination_namespaces(appproject_docs)
    contract_app_ns = {i["name"] for i in (app.get("items") or []) if i.get("name")}

    for ns in sorted(contract_app_ns - allowed):
        findings.append(
            Finding(
                ERROR,
                f"namespace applicatif '{ns}': absent des destinations[] de l'AppProject "
                f"atlas ({appproject_source}) — atlas ne pourra rien y déployer.",
            )
        )
    for ns in sorted(allowed - contract_app_ns):
        findings.append(
            Finding(
                WARNING,
                f"namespace '{ns}': autorisé par l'AppProject atlas mais absent des "
                "namespaces applicatifs du contrat (autorisation plus large que documentée).",
            )
        )
    return findings


def _check_secrets(nss_doc, declared_namespaces, repo_root, docs_for) -> list[Finding]:
    findings: list[Finding] = []
    secrets = nss_doc.get("secrets", {}) or {}

    # postgres_roles : noms ↔ passwordSecret CNPG, + example_file + ns déclaré.
    pg_roles = secrets.get("postgres_roles", {}) or {}
    role_secret_names = [i["secret"] for i in (pg_roles.get("items") or []) if i.get("secret")]
    cnpg_docs = docs_for("platform/cloudnative-pg/cluster.yaml")
    findings.extend(
        check_postgres_role_secrets(role_secret_names, cnpg_role_secret_names(cnpg_docs))
    )
    findings.extend(_check_example_file(pg_roles.get("example_file"), repo_root))
    findings.extend(
        _check_secret_namespace(pg_roles.get("namespace"), "postgres_roles", declared_namespaces)
    )

    # derived : example_file existe + clé STRICTE présente dans l'example + ns déclaré.
    for item in secrets.get("derived", []) or []:
        example_file = item.get("example_file")
        findings.extend(_check_example_file(example_file, repo_root))
        key = item.get("key")
        secret = item.get("secret")
        if example_file and key and secret:
            example_docs = docs_for(example_file)
            if key not in secret_keys(example_docs, secret):
                findings.append(
                    Finding(
                        ERROR,
                        f"secret '{secret}': clé STRICTE '{key}' absente du patron "
                        f"{example_file} (drift de clé consommée par le chart).",
                    )
                )
        findings.extend(
            _check_secret_namespace(
                item.get("namespace"), f"derived[{secret}]", declared_namespaces
            )
        )

    # s3_backup : example_file existe + ns déclaré.
    s3_backup = secrets.get("s3_backup", {}) or {}
    findings.extend(_check_example_file(s3_backup.get("example_file"), repo_root))
    findings.extend(
        _check_secret_namespace(s3_backup.get("namespace"), "s3_backup", declared_namespaces)
    )
    return findings


def _check_example_file(example_file: str | None, repo_root: str) -> list[Finding]:
    if not example_file:
        return []
    if not os.path.isfile(os.path.join(repo_root, example_file)):
        return [
            Finding(
                ERROR,
                f"example_file '{example_file}' introuvable (patron de creds disparu).",
            )
        ]
    return []


def _check_secret_namespace(ns, label, declared_namespaces) -> list[Finding]:
    if ns and ns not in declared_namespaces:
        return [
            Finding(
                ERROR,
                f"secret {label}: namespace '{ns}' non listé dans `namespaces` du contrat "
                "(contradiction interne).",
            )
        ]
    return []


def _check_storage_classes(sc_doc, s3_endpoints, repo_root, docs_for) -> list[Finding]:
    findings: list[Finding] = []
    profils = sc_doc.get("profils", {}) or {}
    for profil_name, profil in profils.items():
        for sc in profil.get("storage_classes", []) or []:
            source = sc.get("source", "")
            findings.extend(check_storage_class(sc, docs_for(source) if source else []))

        # object_store : recoupements inter-fichiers.
        object_store = profil.get("object_store", {}) or {}
        findings.extend(
            _check_object_store(profil_name, object_store, s3_endpoints, repo_root, docs_for)
        )
    return findings


def _check_object_store(profil_name, object_store, s3_endpoints, repo_root, docs_for):
    findings: list[Finding] = []
    # endpoint S3 du store ↔ fqdn:port de l'endpoint S3 homologue (anti-drift dupliqué).
    endpoint = object_store.get("endpoint")
    homolog = {"ceph": "s3-datalake-ceph", "local-path": "s3-datalake-light"}.get(profil_name)
    if endpoint and homolog and homolog in s3_endpoints and endpoint != s3_endpoints[homolog]:
        findings.append(
            Finding(
                ERROR,
                f"object_store[{profil_name}].endpoint '{endpoint}' ≠ fqdn:port de l'endpoint "
                f"'{homolog}' ('{s3_endpoints[homolog]}') — dérive S3 dupliquée entre fichiers "
                "du contrat.",
            )
        )

    # bucket_storage_class : doit exister comme StorageClass dans le dépôt.
    bucket_sc = object_store.get("bucket_storage_class")
    if bucket_sc:
        datalake_docs = docs_for("storage/ceph/storageClass/datalake/")
        names = {
            (d.get("metadata") or {}).get("name")
            for d in datalake_docs
            if isinstance(d, dict) and d.get("kind") == "StorageClass"
        }
        if bucket_sc not in names:
            findings.append(
                Finding(
                    WARNING,
                    f"object_store[{profil_name}].bucket_storage_class '{bucket_sc}' absente des "
                    "kind:StorageClass de storage/ceph/storageClass/datalake/ "
                    f"(présentes : {sorted(n for n in names if n)}) — drift de contrat à corriger.",
                )
            )
    return findings


def _report(findings: list[Finding]) -> int:
    warnings = [f for f in findings if f.level == WARNING]
    errors = [f for f in findings if f.level == ERROR]

    for finding in warnings:
        print(f"check-contract: AVERTISSEMENT — {finding.message}", file=sys.stderr)
    for finding in errors:
        print(f"check-contract: ERREUR — {finding.message}", file=sys.stderr)

    if errors:
        print(
            f"\ncheck-contract: {len(errors)} dérive(s) BLOQUANTE(S) contrat→platform "
            f"(ADR 0043), {len(warnings)} avertissement(s). Corriger le contrat "
            "(contract/*.example.yaml) ou le manifeste platform/ concerné.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check-contract: OK — contrat aligné sur platform/ "
        f"({len(warnings)} avertissement(s), 0 dérive bloquante)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
