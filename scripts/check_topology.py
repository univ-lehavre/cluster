#!/usr/bin/env python3
"""Garde-fou ADR 0096 — le graphe Python figé colle aux rôles/playbooks Ansible.

Le dépôt déclare le graphe de topologie en Python FIGÉ (`nestor/graph.py`, source
unique ADR 0096) : composants atomiques, arêtes, périmètre de rollback, profil. Ce
graphe est la SOURCE ; Ansible (rôles `bootstrap/roles/platform-*`, playbooks
`bootstrap/*.yaml`) est l'IMPLÉMENTATION. Quand les deux divergent — un rôle ajouté
sans composant, un composant retiré du graphe alors que son rôle déploie encore —
personne ne le voit : c'est l'erreur récurrente du « Marquez oublié » (ADR 0096
§Contexte). L'e2e du banc n'est pas CI-able (nested virt / arm64), donc ce check
STATIQUE est le garde-fou : il attrape en REVUE la dérive graphe↔Ansible.

Calqué LIGNE À LIGNE sur [`scripts/check_contract.py`](check_contract.py), le modèle
du check-qui-notifie : `Finding(level, message)`, fonctions PURES testées (ADR 0017),
`_report()` qui sort 0/1/2, branché en CI (`pnpm lint:topology`).

Quatre familles de constats BLOQUANTS (exit 1), depuis ADR 0096 §2 :

  1. Composant → rôle : tout `Component(role≠None)` a son `bootstrap/roles/<role>/`
     ET est importé par un playbook (ancrage anti-faux-vert).
  2. Rôle → composant — LE notifieur « Marquez oublié » : tout `platform-X` importé
     est référencé par ≥1 `Component`, sinon ERREUR. Allowlist
     EXPECTED_NON_GRAPH_ROLES justifiée pour les rôles socle. Tolère le mapping NON
     1:1 (un rôle porte N composants : `platform-cnpg`→4, `platform-s3-bucket`→3) et
     vérifie que CHAQUE composant du rôle est référencé. Scanne aussi les
     `include_role` RÔLE→RÔLE (`platform-s3-bucket` n'est tiré que par
     `platform-{loki,cnpg,mlflow}`, jamais par un playbook direct).
  3. Signal : chaque phase roundtrip a un signal (`_LAYER_SIGNAL`) qui résout vers
     EXACTEMENT un composant, présent dans `PHASE_COMPONENTS[phase]`, et qui est une
     FEUILLE de la phase (aucun autre composant de la phase n'en dépend). C'est ce
     qu'un nom de phase ne tranche pas quand la phase a plusieurs feuilles (`dataops`
     en a deux : dagster ET marquez — le signal DOIT pointer la bonne).
  4. Cohérence interne : acyclicité du graphe, arêtes vers des composants connus,
     jetons de stockage `@sc`/`@s3` résolus pour les DEUX backends.

La logique est isolée en fonctions PURES (résolution rôle↔composant, parité des
imports, résolution du signal vers une feuille, invariants du graphe) testées par
tests/test_check_topology.py (ADR 0017). Les lectures disque (rôles, scan des
playbooks) sont injectées, donc le cœur est testable sans toucher au disque. Python
plutôt que bash : jointures inter-fichiers graphe↔Ansible (ADR 0017).

Usage : python3 scripts/check_topology.py   (via `pnpm lint:topology`).
Sort en code 1 dès qu'un constat BLOQUANT est trouvé, 0 sinon (warnings inclus),
2 sur erreur de configuration (graphe introuvable, PyYAML absent).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dépendance déclarée dans pyproject
    print(
        "check-topology: PyYAML manquant. `uv sync` (dépendance déclarée dans "
        "pyproject.toml) avant de lancer ce garde-fou.",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# Le graphe (nestor/graph.py) et le signal de santé (scripts/topology.py) sont les
# deux MIROIRS confrontés à Ansible : on les importe depuis la racine du dépôt.
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from nestor import graph
except ModuleNotFoundError:  # pragma: no cover - module du dépôt
    print(
        "check-topology: nestor/graph.py introuvable (graphe figé ADR 0096 absent).",
        file=sys.stderr,
    )
    raise SystemExit(2) from None


# ─────────────────────────────────────────────────────────────────────────────
# Allowlist des rôles SOCLE hors graphe (ADR 0096 §2, justifiée par chemin comme
# .trivyignore.yaml). Un rôle Ansible qui N'EST PAS un composant de topologie : il
# prépare le NŒUD ou le control-plane (kubeadm, CRI, kube-vip…), pas une brique de
# plateforme du graphe. Y figurer = « volontairement hors graphe », pas « oublié ».
#
# Seuls les rôles `platform-*` sont confrontés au graphe par la famille 2 ; cette
# allowlist sert de garde-fou explicite si un futur rôle `platform-*` devait rester
# socle (cas non présent aujourd'hui — la liste platform-* est vide). Les rôles
# non `platform-*` (k8s-*, audit-log, …) ne sont PAS des composants de topologie et
# ne passent pas par la famille 2.
# ─────────────────────────────────────────────────────────────────────────────
# Vide aujourd'hui : tous les rôles `platform-*` sont des Components du graphe. (platform-eventful
# a été enregistré comme Component(role='platform-eventful') — ADR 0095 §1.b / 0103 follow-up #564 —
# donc retiré de cette allowlist.) Y ajouter une entrée = « rôle platform-* volontairement hors
# graphe » (socle), à justifier par chemin.
EXPECTED_NON_GRAPH_ROLES: dict[str, str] = {}

# Mots-clés des tâches qui IMPORTENT un rôle (playbook ou rôle→rôle). On scanne
# l'arbre YAML : un `import_role`/`include_role` peut être imbriqué (block, when…).
_ROLE_IMPORT_KEYS = frozenset(
    {
        "ansible.builtin.import_role",
        "ansible.builtin.include_role",
        "import_role",
        "include_role",
    }
)

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


def role_to_components(components: Iterable) -> dict[str, list[str]]:
    """Index `role -> [noms de composants qui le portent]` (mapping NON 1:1). Pure.

    Un rôle peut porter PLUSIEURS composants (`platform-cnpg`→4,
    `platform-s3-bucket`→3) : on agrège. Les composants socle (`role is None`) ne
    figurent pas dans l'index (pas de rôle dédié).
    """
    index: dict[str, list[str]] = {}
    for comp in components:
        if comp.role:
            index.setdefault(comp.role, []).append(comp.name)
    return index


def collect_role_imports(docs: Iterable) -> set[str]:
    """Tous les `name:` sous un import_role/include_role d'un flux YAML. Pure.

    Parcourt l'arbre récursivement : un import peut être imbriqué (block/when/rescue).
    Couvre les imports de PLAYBOOK comme les `include_role` RÔLE→RÔLE (ADR 0096 §2 :
    `platform-s3-bucket` n'est tiré QUE rôle→rôle, jamais par un playbook direct).
    """
    roles: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _ROLE_IMPORT_KEYS and isinstance(value, dict) and value.get("name"):
                    roles.add(value["name"])
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for doc in docs:
        walk(doc)
    return roles


def phase_leaves(phase: str, backend: str = graph.CEPH) -> list[str]:
    """Feuilles d'une phase : composants dont AUCUN autre composant de la phase ne
    dépend (= maillons terminaux du montage). Pure.

    Une phase peut avoir plusieurs feuilles (`dataops` : dagster ET marquez) — c'est
    précisément pourquoi le signal de santé est une donnée HUMAINE (« quelle feuille
    atteste la phase »), pas dérivable du seul graphe.
    """
    comps = graph.component_expand_alias(phase, backend)
    comp_set = set(comps)
    depended: set[str] = set()
    for comp in comps:
        for dep in graph.component_deps(comp, backend):
            if dep in comp_set:
                depended.add(dep)
    return [c for c in comps if c not in depended]


def resolve_signal_component(
    phase: str,
    signal_name: str,
    signal_namespace: str | None,
    backend: str = graph.CEPH,
) -> list[str]:
    """Composant(s) de `phase` que le signal `_LAYER_SIGNAL` (name, ns) désigne. Pure.

    Le signal nomme une ressource kubectl (Deployment/StatefulSet/CR…), pas un
    composant : on le résout vers le composant du graphe par ordre de spécificité —
      1. nom EXACT du composant (`marquez`, `loki`, `mlflow`, `portal`…) ;
      2. préfixe `<composant>-…` (`argocd-server` → `argocd`) ;
      3. ressource CIBLÉE du composant qui se termine par ce nom
         (`sc` cible `…rook-ceph-block-replicated` ; `gitops-seed` cible
         `…applications.argoproj.io atlas-workflows`) ;
      4. possesseur du NAMESPACE en dernier recours (`ceph` possède rook-ceph).
    Retourne la liste des candidats (idéalement 1 ; 0 ou >1 = dérive à signaler).
    """
    comps = graph.component_expand_alias(phase, backend)

    exact = [c for c in comps if c == signal_name]
    if exact:
        return exact

    prefix = [c for c in comps if signal_name != c and signal_name.startswith(c + "-")]
    if prefix:
        return prefix

    targeted = sorted(
        {
            c
            for c in comps
            for t in graph.component_targeted(c)
            if t.split() and t.split()[-1] == signal_name
        }
    )
    if targeted:
        return targeted

    if signal_namespace:
        owners = [c for c in comps if graph.component_namespace(c) == signal_namespace]
        if owners:
            return owners

    return []


def check_component_role(
    comp,
    role_dir_exists: bool,
    imported_roles: set[str],
) -> list[Finding]:
    """FAMILLE 1 — un `Component(role≠None)` a son rôle sur disque ET importé. Pure.

    `role_dir_exists` = `bootstrap/roles/<role>/` existe (injecté). `imported_roles` =
    union des rôles importés (playbooks + rôle→rôle). Un composant socle (role None)
    n'est pas concerné (rien à ancrer côté Ansible).
    """
    findings: list[Finding] = []
    if not comp.role:
        return findings
    if not role_dir_exists:
        findings.append(
            Finding(
                ERROR,
                f"composant '{comp.name}': son rôle '{comp.role}' n'a pas de répertoire "
                f"bootstrap/roles/{comp.role}/ (rôle disparu ou renommé sans toucher le graphe).",
            )
        )
    if comp.role not in imported_roles:
        findings.append(
            Finding(
                ERROR,
                f"composant '{comp.name}': son rôle '{comp.role}' n'est importé par AUCUN "
                "playbook ni rôle (import_role/include_role) — composant non monté (faux-vert).",
            )
        )
    return findings


def check_role_components(
    role: str,
    role_to_comps: dict[str, list[str]],
    referenced_components: set[str],
) -> list[Finding]:
    """FAMILLE 2 — LE notifieur « Marquez oublié » : un `platform-X` importé est
    référencé par ≥1 composant, ET CHAQUE composant qu'il porte est référencé. Pure.

    `role_to_comps` = index role→composants du graphe. `referenced_components` = noms
    de composants effectivement présents dans le catalogue (le graphe LIVE). Un rôle
    importé absent de l'index = rôle mort/hors graphe (sauf allowlist, géré par
    l'appelant). Tolère le mapping NON 1:1 : on vérifie CHAQUE composant du rôle,
    sinon un rôle multi-composant masquerait l'oubli d'un seul de ses composants.
    """
    findings: list[Finding] = []
    comps = role_to_comps.get(role)
    if not comps:
        findings.append(
            Finding(
                ERROR,
                f"rôle '{role}': importé par un playbook/rôle mais référencé par AUCUN "
                "Component du graphe (nestor/graph.py) — rôle hors graphe « Marquez oublié ». "
                "Ajouter un Component(role='" + role + "') ou justifier dans "
                "EXPECTED_NON_GRAPH_ROLES.",
            )
        )
        return findings
    for comp_name in comps:
        if comp_name not in referenced_components:
            findings.append(
                Finding(
                    ERROR,
                    f"rôle '{role}': porte le composant '{comp_name}' dans le graphe mais ce "
                    "composant a disparu du catalogue (régression « Marquez oublié » : un "
                    "composant d'un rôle multi-composant retiré sans retirer le rôle).",
                )
            )
    return findings


def check_phase_signal(
    phase: str,
    signal_name: str,
    signal_namespace: str | None,
    backend: str = graph.CEPH,
) -> list[Finding]:
    """FAMILLE 3 — le signal d'une phase pointe une FEUILLE du graphe. Pure.

    Vérifie : le signal résout vers EXACTEMENT un composant, ce composant est dans
    `PHASE_COMPONENTS[phase]` (= la phase le monte bien) ET c'est une feuille de la
    phase (aucun autre composant de la phase n'en dépend). Le « Marquez oublié »
    surface ici aussi : sonder une feuille NON terminale (`dagster` au lieu de
    `marquez`) laisserait passer un drift de l'autre feuille.
    """
    findings: list[Finding] = []
    candidates = resolve_signal_component(phase, signal_name, signal_namespace, backend)

    if not candidates:
        findings.append(
            Finding(
                ERROR,
                f"phase '{phase}': le signal de santé (ressource '{signal_name}'"
                f"{' ns ' + signal_namespace if signal_namespace else ''}) ne résout vers "
                "AUCUN composant de la phase (nom/préfixe/ressource ciblée/namespace). "
                "Signal désynchronisé du graphe (rename de ressource ?).",
            )
        )
        return findings
    if len(candidates) > 1:
        findings.append(
            Finding(
                ERROR,
                f"phase '{phase}': le signal '{signal_name}' résout vers PLUSIEURS composants "
                f"{sorted(candidates)} — ambigu ; préciser la ressource discriminante.",
            )
        )
        return findings

    component = candidates[0]
    phase_components = set(graph.component_expand_alias(phase, backend))
    if component not in phase_components:
        findings.append(
            Finding(
                ERROR,
                f"phase '{phase}': le signal pointe le composant '{component}' qui n'est PAS "
                f"monté par la phase (composants : {sorted(phase_components)}).",
            )
        )
        return findings

    leaves = set(phase_leaves(phase, backend))
    if component not in leaves:
        findings.append(
            Finding(
                ERROR,
                f"phase '{phase}': le signal pointe '{component}' qui n'est PAS une feuille de "
                f"la phase (feuilles : {sorted(leaves)}) — un drift de la vraie feuille terminale "
                "passerait inaperçu (« Marquez oublié »).",
            )
        )
    return findings


def check_graph_internal(backend: str = graph.CEPH) -> list[Finding]:
    """FAMILLE 4 — cohérence interne du graphe pour un `backend`. Pure.

    Acyclicité (topo_sort de TOUT le catalogue ne lève pas), arêtes vers des
    composants CONNUS, jetons de stockage `@sc`/`@s3` résolus (pas de sentinelle
    résiduelle). Portage des invariants de `bench/unit/rollback.bats`.
    """
    findings: list[Finding] = []
    all_components = list(graph.COMPONENT_ALL)

    # Acyclicité : topo_sort de tout le catalogue ne doit pas lever TopoCycleError.
    try:
        graph.topo_sort(all_components, backend)
    except graph.TopoCycleError as exc:
        findings.append(
            Finding(ERROR, f"graphe (backend {backend}): cycle de dépendances détecté — {exc}.")
        )

    # Arêtes connues + jetons résolus : chaque dep résolue est un composant du catalogue.
    known = set(all_components)
    for name in all_components:
        for dep in graph.component_deps(name, backend):
            if dep.startswith("@"):
                findings.append(
                    Finding(
                        ERROR,
                        f"composant '{name}' (backend {backend}): jeton de stockage NON résolu "
                        f"'{dep}' dans ses arêtes (sentinelle @sc/@s3 oubliée).",
                    )
                )
            elif dep not in known:
                findings.append(
                    Finding(
                        ERROR,
                        f"composant '{name}' (backend {backend}): arête vers un composant "
                        f"INCONNU '{dep}' (typo ou composant supprimé sans mettre à jour l'arête).",
                    )
                )
    return findings


# ═════════════════════════════════════════════════════════════════════════════
# I/O — chargement des sources Ansible (NON pur ; injecté dans main)
# ═════════════════════════════════════════════════════════════════════════════


def load_yaml_docs(text: str) -> list:
    """Tous les documents d'un flux YAML multi-doc (None filtrés).

    Garde les LISTES (un playbook Ansible est une liste de plays au top-level, pas un
    dict) : `collect_role_imports` parcourt l'arbre récursivement, listes incluses.
    """
    return [d for d in yaml.safe_load_all(text) if d is not None]


def _read_yaml(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            return load_yaml_docs(handle.read())
    except (OSError, yaml.YAMLError):
        return []


def scan_imported_roles(repo_root: str) -> set[str]:
    """Union des rôles importés par les playbooks ET par les rôles (rôle→rôle).

    Playbooks : `bootstrap/*.yaml`. Rôle→rôle : `bootstrap/roles/*/tasks/*.yaml` (où
    vit l'`include_role` imbriqué de `platform-s3-bucket`). NON pur (lit le disque) ;
    le cœur (`collect_role_imports`) est pur et testé.
    """
    roles: set[str] = set()
    bootstrap = os.path.join(repo_root, "bootstrap")
    if os.path.isdir(bootstrap):
        for entry in sorted(os.listdir(bootstrap)):
            if entry.endswith((".yaml", ".yml")):
                roles |= collect_role_imports(_read_yaml(os.path.join(bootstrap, entry)))
    roles_dir = os.path.join(bootstrap, "roles")
    if os.path.isdir(roles_dir):
        for role in sorted(os.listdir(roles_dir)):
            tasks_dir = os.path.join(roles_dir, role, "tasks")
            if not os.path.isdir(tasks_dir):
                continue
            for entry in sorted(os.listdir(tasks_dir)):
                if entry.endswith((".yaml", ".yml")):
                    roles |= collect_role_imports(_read_yaml(os.path.join(tasks_dir, entry)))
    return roles


def role_dir_exists(role: str, repo_root: str) -> bool:
    """`bootstrap/roles/<role>/` existe (ancrage anti-faux-vert de la famille 1)."""
    return os.path.isdir(os.path.join(repo_root, "bootstrap", "roles", role))


def load_layer_signals() -> dict[str, tuple[str, str, str | None, object]]:
    """Charge `_LAYER_SIGNAL` de `scripts/topology.py` (3e miroir : santé par phase).

    Importé (pas re-déclaré) : c'est la table que la famille 3 confronte au graphe.
    L'import de `topology` est sûr (le travail est gardé par `if __name__`).
    """
    try:
        import topology  # noqa: PLC0415 - import tardif pour isoler la dép disque
    except ModuleNotFoundError:  # pragma: no cover - module du dépôt
        return {}
    return dict(topology._LAYER_SIGNAL)


# ═════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═════════════════════════════════════════════════════════════════════════════


def main() -> int:
    """Confronte le graphe (nestor/graph.py) aux rôles/playbooks Ansible et au signal.

    Niveau de strictness (les 4 familles ADR 0096 §2 sont BLOQUANTES, exit 1) :

      FAMILLE 1 — Composant → rôle : `Component(role≠None)` sans répertoire de rôle,
        ou non importé par un playbook/rôle (composant non monté = faux-vert).
      FAMILLE 2 — Rôle → composant (« Marquez oublié ») : `platform-X` importé absent
        du graphe (hors allowlist), ou un composant d'un rôle multi-composant disparu.
      FAMILLE 3 — Signal : une phase roundtrip dont le signal ne résout pas vers une
        unique FEUILLE du graphe présente dans la phase.
      FAMILLE 4 — Cohérence interne : cycle, arête inconnue, jeton @sc/@s3 non résolu
        (pour les DEUX backends ceph + local-path).

      WARNING (n'échoue pas) : un rôle `platform-*` importé mais explicitement
        allowlisté (EXPECTED_NON_GRAPH_ROLES) — tracé sans bloquer ; une phase de
        `_LAYER_SIGNAL` hors ROUNDTRIP_PHASES (signal d'une couche socle : signalé,
        non bloquant).
    """
    repo_root = _REPO_ROOT
    if not graph.COMPONENT_ALL:
        print("check-topology: graphe vide (nestor/graph.py sans composant).", file=sys.stderr)
        return 2

    findings: list[Finding] = []

    components = list(graph.COMPONENTS.values())
    referenced_components = set(graph.COMPONENT_ALL)
    role_to_comps = role_to_components(components)
    imported_roles = scan_imported_roles(repo_root)

    # ── FAMILLE 1 : Composant → rôle ─────────────────────────────────────────
    for comp in components:
        if not comp.role:
            continue
        findings.extend(
            check_component_role(
                comp,
                role_dir_exists(comp.role, repo_root),
                imported_roles,
            )
        )

    # ── FAMILLE 2 : Rôle → composant (LE notifieur « Marquez oublié ») ────────
    # On confronte chaque rôle `platform-*` IMPORTÉ au graphe. Un rôle allowlisté
    # (socle volontairement hors graphe) → WARNING. Les rôles non `platform-*`
    # (k8s-*, audit-log…) ne sont pas des composants de topologie : hors périmètre.
    for role in sorted(imported_roles):
        if not role.startswith("platform-"):
            continue
        if role in EXPECTED_NON_GRAPH_ROLES:
            findings.append(
                Finding(
                    WARNING,
                    f"rôle '{role}': importé mais allowlisté hors graphe "
                    f"(EXPECTED_NON_GRAPH_ROLES : {EXPECTED_NON_GRAPH_ROLES[role]}).",
                )
            )
            continue
        findings.extend(check_role_components(role, role_to_comps, referenced_components))

    # ── FAMILLE 3 : Signal de santé → feuille du graphe ──────────────────────
    layer_signals = load_layer_signals()
    for phase, signal in layer_signals.items():
        _kind, name, namespace = signal[0], signal[1], signal[2]
        if phase not in graph.ROUNDTRIP_PHASES:
            # Signal d'une couche SOCLE (storage-simple : pas une phase roundtrip).
            # Pas une feuille de phase à éprouver → tracé en WARNING, non bloquant.
            findings.append(
                Finding(
                    WARNING,
                    f"signal '{phase}': phase hors ROUNDTRIP_PHASES "
                    f"({sorted(graph.ROUNDTRIP_PHASES)}) — couche socle, non confrontée aux "
                    "feuilles de phase (non bloquant).",
                )
            )
            continue
        findings.extend(check_phase_signal(phase, name, namespace))

    # Une phase roundtrip SANS signal connu : sa santé n'est pas sondée (« Marquez
    # oublié » au niveau de la couverture du signal). BLOQUANT.
    for phase in graph.ROUNDTRIP_PHASES:
        if phase not in layer_signals:
            findings.append(
                Finding(
                    ERROR,
                    f"phase '{phase}': aucune entrée dans _LAYER_SIGNAL (scripts/topology.py) — "
                    "la santé de la couche n'est pas sondée (verdict potentiellement mensonger).",
                )
            )

    # ── FAMILLE 4 : Cohérence interne (les DEUX backends) ────────────────────
    for backend in (graph.CEPH, graph.LOCAL_PATH):
        findings.extend(check_graph_internal(backend))

    return _report(findings)


def _report(findings: list[Finding]) -> int:
    warnings = [f for f in findings if f.level == WARNING]
    errors = [f for f in findings if f.level == ERROR]

    for finding in warnings:
        print(f"check-topology: AVERTISSEMENT — {finding.message}", file=sys.stderr)
    for finding in errors:
        print(f"check-topology: ERREUR — {finding.message}", file=sys.stderr)

    if errors:
        print(
            f"\ncheck-topology: {len(errors)} dérive(s) BLOQUANTE(S) graphe↔Ansible "
            f"(ADR 0096), {len(warnings)} avertissement(s). Corriger le graphe "
            "(nestor/graph.py), le rôle/playbook bootstrap/ ou le signal "
            "(_LAYER_SIGNAL) concerné.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check-topology: OK — graphe aligné sur bootstrap/ et _LAYER_SIGNAL "
        f"({len(warnings)} avertissement(s), 0 dérive bloquante)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
