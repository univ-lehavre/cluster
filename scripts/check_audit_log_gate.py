#!/usr/bin/env python3
"""Garde-fou ADR 0108/0053 — tout play SSHant un parc DISTANT importe `audit-log`.

Deux instances déclarent les MÊMES groupes/noms d'hôtes (`cp1`, `node1`…) ; seul le
`stack_id` (porté par l'inventaire au niveau du groupe `cloud`, dérivé de la topo)
les distingue. Le rôle `audit-log`, importé en `pre_tasks` AVANT toute tâche distante,
asserte que l'instance ciblée correspond à l'intention (`stack_id == EXPECTED_STACK_ID`,
posé par nestor). Un mauvais `-i` (inventaire d'une AUTRE instance) échoue alors
immédiatement, zéro tâche mutante — au lieu d'un faux-résultat silencieux (ADR 0052).

SANS ce garde par-play, un montage banc a déjà SSHé sur la PROD (dataops play 2 +
`rollback.yaml` orphelins, faille du 2026-06-16) ; les playbooks `hosts: all/control`
(secure/upgrade/etcd-fetch) étaient un angle mort élargi le 2026-06-30. Ce check
STATIQUE attrape en REVUE l'ajout d'un play distant NON gardé (l'e2e du banc n'est pas
CI-able : nested virt / arm64 — cf. check_topology.py).

Calqué LIGNE À LIGNE sur [`scripts/check_topology.py`](check_topology.py), le modèle du
garde-fou statique : `Finding(level, message)`, fonctions PURES testées (ADR 0017)
séparées des lectures disque (injectées), `_report()` qui sort 0/1/2, branché en CI.

POURQUOI Python plutôt que le bats qu'il remplace (bench/unit/audit-log-guard.bats) :
le bats ne PARSE pas le YAML — il compte, PAR FICHIER, les `hosts: cloud|all|control`
(grep) vs les `name: audit-log`. Deux angles morts que le parsing PAR PLAY corrige :

  1. Comptage PAR FICHIER, pas par play : un fichier à 2 plays distants et 1 seul
     audit-log MAL PLACÉ (dans le mauvais play) passerait si les nombres collent par
     hasard. Ici on vérifie que CHAQUE play distant a SON propre audit-log.
  2. `hosts` en LISTE : le grep `hosts: (cloud|all|control)` en fin de ligne rate la
     forme liste (`hosts:` puis `- cloud` en dessous, ex. os-upgrade.yaml) — le YAML
     parsé la voit. On garde tout play dont `hosts` (scalaire OU liste) touche un
     groupe distant `{cloud, all, control}`.

`localhost` n'est PAS gardé (pas de SSH distant : les plays plateforme pilotent l'API
k8s depuis le poste de contrôle). Les valeurs templatées non résolues
(`"{{ dataops_k8s_host | default('localhost') }}"`) ne sont pas des groupes distants
statiques : hors périmètre (le play cible localhost par défaut).

Usage : python3 scripts/check_audit_log_gate.py   (via CI, job Python).
Sort en code 1 dès qu'un play distant N'IMPORTE PAS `audit-log`, 0 sinon, 2 sur erreur
de configuration (PyYAML absent).
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
        "check-audit-log-gate: PyYAML manquant. `uv sync` (dépendance déclarée dans "
        "pyproject.toml) avant de lancer ce garde-fou.",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Groupes d'inventaire qui atteignent un parc DISTANT par SSH (ADR 0108). Un play
# qui les cible MUTE des nœuds → il DOIT asserter l'identité de l'instance avant.
# `workers`/`vm` ne sont pas dans l'unité de garde (aligné sur le bats remplacé, qui
# ne grepait que cloud|all|control) ; ils n'apparaissent qu'aux côtés de `cloud` dans
# des plays déjà gardés (join-workers, os-upgrade). L'ajout d'un play `hosts: workers`
# NON gardé serait à couvrir en élargissant cet ensemble.
REMOTE_HOST_GROUPS = frozenset({"cloud", "all", "control"})

# Le rôle d'assertion d'identité à importer en pre_tasks (ADR 0108).
AUDIT_LOG_ROLE = "audit-log"

# Mots-clés des tâches qui IMPORTENT un rôle. On scanne l'arbre YAML : un
# import_role/include_role peut être imbriqué (block, when…). Ré-implémenté À
# L'IDENTIQUE de check_topology.py pour l'AUTONOMIE de ce check (comme
# check_topology est autonome : aucun import croisé entre garde-fous).
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


def _play_hosts(play: object) -> list[str]:
    """Groupes ciblés par un play : `hosts` normalisé en liste de chaînes. Pure.

    `hosts` est soit un scalaire (`cloud`), soit une LISTE (`[cloud, vm]`, forme que
    le grep du bats ratait). Un scalaire non-str (None, template déjà parsé) est
    ignoré. On ne résout PAS les templates Jinja (`{{ … }}`) : ce ne sont pas des
    groupes statiques (ils défaultent à localhost — hors périmètre du garde distant).
    """
    if not isinstance(play, dict):
        return []
    hosts = play.get("hosts")
    if isinstance(hosts, str):
        return [hosts]
    if isinstance(hosts, list):
        return [h for h in hosts if isinstance(h, str)]
    return []


def is_remote_play(play: object) -> bool:
    """Le play cible-t-il un parc DISTANT (∩ REMOTE_HOST_GROUPS ≠ ∅) ? Pure.

    Un play en LISTE (`[cloud, vm]`) est distant dès qu'UN de ses groupes l'est.
    Un play `localhost` (ou un template non résolu) n'est PAS distant → non gardé.
    """
    return any(h in REMOTE_HOST_GROUPS for h in _play_hosts(play))


def remote_plays(docs: Iterable) -> list[dict]:
    """Plays d'un flux YAML qui ciblent un parc distant. Pure.

    Un playbook Ansible est une LISTE de plays au top-level (un document YAML). On
    déplie chaque document liste en ses plays, et on ne garde que les plays distants.
    Un document non-liste (dict isolé, ou None filtré en amont) n'est pas un playbook
    de plays : ignoré.
    """
    plays: list[dict] = []
    for doc in docs:
        if isinstance(doc, list):
            plays.extend(p for p in doc if is_remote_play(p))
        elif isinstance(doc, dict) and is_remote_play(doc):
            plays.append(doc)
    return plays


def collect_role_imports(node: object) -> set[str]:
    """Tous les `name:` sous un import_role/include_role d'un sous-arbre YAML. Pure.

    Parcourt l'arbre récursivement : un import peut être imbriqué (pre_tasks, block,
    when, rescue…). Ré-implémenté À L'IDENTIQUE de check_topology.py, mais scopé à UN
    play (pas au fichier entier) : c'est cette granularité PAR PLAY qui corrige
    l'angle mort du bats (comptage par fichier).
    """
    roles: set[str] = set()

    def walk(current: object) -> None:
        if isinstance(current, dict):
            for key, value in current.items():
                if key in _ROLE_IMPORT_KEYS and isinstance(value, dict) and value.get("name"):
                    roles.add(value["name"])
                walk(value)
        elif isinstance(current, list):
            for item in current:
                walk(item)

    walk(node)
    return roles


def check_play_has_audit_log(play: dict, source: str) -> list[Finding]:
    """Un play DISTANT importe le rôle `audit-log` (idéalement en pre_tasks). Pure.

    Tolère l'import n'importe où DANS le play (pre_tasks, tasks, roles, block) — comme
    le bats comptait au niveau fichier — mais scopé au SEUL play : un audit-log placé
    dans un AUTRE play du même fichier ne compte pas. ERREUR si absent : un play
    distant sans garde d'identité peut SSHer sur la mauvaise instance (faille
    2026-06-16). L'appelant ne passe ici que des plays déjà filtrés distants.
    """
    findings: list[Finding] = []
    if AUDIT_LOG_ROLE not in collect_role_imports(play):
        name = play.get("name", "(play sans nom)")
        hosts = ", ".join(_play_hosts(play))
        findings.append(
            Finding(
                ERROR,
                f"{source}: le play '{name}' (hosts: {hosts}) cible un parc DISTANT mais "
                f"n'importe PAS le rôle '{AUDIT_LOG_ROLE}' (import_role/include_role). Sans "
                "cette garde d'identité en pre_tasks, un mauvais inventaire SSHe sur la "
                "mauvaise instance AVANT toute assertion (ADR 0108, faille 2026-06-16). "
                "Ajouter le pre_task audit-log (cf. bootstrap/cri.yaml).",
            )
        )
    return findings


def check_docs(docs: Iterable, source: str) -> list[Finding]:
    """Tous les plays distants d'un flux YAML ont leur audit-log. Pure.

    Orchestre les deux fonctions pures PAR PLAY : extrait les plays distants, puis
    vérifie que CHACUN importe audit-log. C'est la robustesse > bats : un fichier à 2
    plays distants dont un seul gardé émet 1 ERREUR (le bats, comptant par fichier,
    pouvait ne rien voir si le total d'audit-log ≥ total de plays distants).
    """
    findings: list[Finding] = []
    for play in remote_plays(docs):
        findings.extend(check_play_has_audit_log(play, source))
    return findings


# ═════════════════════════════════════════════════════════════════════════════
# I/O — chargement des sources Ansible (NON pur ; injecté dans main)
# ═════════════════════════════════════════════════════════════════════════════


def load_yaml_docs(text: str) -> list:
    """Tous les documents d'un flux YAML multi-doc (None filtrés).

    Garde les LISTES (un playbook Ansible est une liste de plays au top-level, pas un
    dict) : `remote_plays` déplie chaque document liste en ses plays. Ré-implémenté à
    l'identique de check_topology.py pour l'autonomie du check.
    """
    return [d for d in yaml.safe_load_all(text) if d is not None]


def _read_yaml(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            return load_yaml_docs(handle.read())
    except (OSError, yaml.YAMLError):
        return []


def scan_playbooks(repo_root: str) -> list[Finding]:
    """Confronte chaque playbook au garde-fou par-play. NON pur (lit le disque).

    Scanne `bootstrap/*.yaml` ET `bootstrap/security/*.yml` (comme le bats remplacé).
    Le cœur (`check_docs` et ses fonctions pures) est testé sans disque (ADR 0017).
    """
    findings: list[Finding] = []
    bootstrap = os.path.join(repo_root, "bootstrap")
    if os.path.isdir(bootstrap):
        for entry in sorted(os.listdir(bootstrap)):
            if entry.endswith((".yaml", ".yml")):
                path = os.path.join(bootstrap, entry)
                findings.extend(check_docs(_read_yaml(path), f"bootstrap/{entry}"))
    security = os.path.join(bootstrap, "security")
    if os.path.isdir(security):
        for entry in sorted(os.listdir(security)):
            if entry.endswith((".yaml", ".yml")):
                path = os.path.join(security, entry)
                findings.extend(check_docs(_read_yaml(path), f"bootstrap/security/{entry}"))
    return findings


# ═════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═════════════════════════════════════════════════════════════════════════════


def main() -> int:
    """Confronte chaque playbook bootstrap au garde-fou audit-log PAR PLAY (ADR 0108).

    BLOQUANT (exit 1) : un play qui cible un parc distant (`hosts` ∩ {cloud, all,
    control} ≠ ∅) sans importer le rôle `audit-log` — il pourrait SSHer sur la mauvaise
    instance avant toute assertion d'identité (faille 2026-06-16). Le comptage est PAR
    PLAY (pas par fichier comme le bats remplacé), donc un play distant non gardé au
    milieu d'un fichier autrement conforme est bien attrapé.
    """
    return _report(scan_playbooks(_REPO_ROOT))


def _report(findings: list[Finding]) -> int:
    warnings = [f for f in findings if f.level == WARNING]
    errors = [f for f in findings if f.level == ERROR]

    for finding in warnings:
        print(f"check-audit-log-gate: AVERTISSEMENT — {finding.message}", file=sys.stderr)
    for finding in errors:
        print(f"check-audit-log-gate: ERREUR — {finding.message}", file=sys.stderr)

    if errors:
        print(
            f"\ncheck-audit-log-gate: {len(errors)} play(s) distant(s) SANS garde audit-log "
            f"(ADR 0108/0053, #359), {len(warnings)} avertissement(s). Ajouter le pre_task "
            "audit-log au(x) play(s) concerné(s) (cf. bootstrap/cri.yaml).",
            file=sys.stderr,
        )
        return 1

    print(
        f"check-audit-log-gate: OK — chaque play distant (cloud/all/control) importe "
        f"audit-log ({len(warnings)} avertissement(s), 0 play non gardé)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
