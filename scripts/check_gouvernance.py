#!/usr/bin/env python3
"""Audit du respect des conventions de gouvernance (ADR 0060).

Vérifie, sur le code seul, que les conventions documentaires sont tenues :
conformité ADR ↔ plan ↔ issue ↔ drift (ADR 0057/0058), cohérence des index,
fraîcheur des passages d'audit. Produit aussi les statistiques de gouvernance
(« le dépôt en chiffres »).

NON bloquant par destination : lancé par un cron hebdomadaire
(.github/workflows/conventions-freshness.yml) qui consigne les manquements dans une
issue ; lançable à la main via `pnpm check:gouvernance`.

Usage :
  python3 scripts/check_gouvernance.py            # rapport humain + code 0/1
  python3 scripts/check_gouvernance.py --report   # idem (défaut)
  python3 scripts/check_gouvernance.py --stats     # bloc « le dépôt en chiffres »
  python3 scripts/check_gouvernance.py --audit-max-days 180

La LOGIQUE (parsing + règles de conformité) est isolée dans des fonctions PURES
testées par tests/test_check_gouvernance.py (ADR 0017 : tout code de logique est
testé). Python plutôt que bash : parsing YAML/Markdown + croisements d'index.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass

import yaml

# ── Emplacements (relatifs à la racine du dépôt) ────────────────────────────
DECISIONS_DIR = "docs/decisions"
PLANS_DIR = "docs/plans"
AUDIT_DIR = "docs/audit"
DRIFTS_FILE = "docs/architecture/registre-drifts.yaml"
DECISIONS_INDEX = "docs/decisions/README.md"

PLAN_ETATS = {"Brouillon", "Actif", "Achevé", "Abandonné"}
ADR_STATUTS = {"Accepted", "Proposed", "Superseded", "Deprecated"}
DRIFT_OPEN_STATUTS = {"ouvert", "en-cours"}
DEFAULT_AUDIT_MAX_DAYS = 180


# ── Modèle de violation ─────────────────────────────────────────────────────
@dataclass
class Finding:
    """Un manquement détecté. `famille` regroupe pour le rapport."""

    famille: str
    cible: str
    message: str


# ── Fonctions PURES de parsing (testées) ────────────────────────────────────
def adr_number_from_filename(name: str) -> str | None:
    """`0057-...md` → `0057` ; renvoie None si le nom n'est pas un ADR numéroté."""
    m = re.match(r"^(\d{4})-.*\.md$", os.path.basename(name))
    return m.group(1) if m else None


def parse_adr_statut(text: str) -> str | None:
    """Extrait le statut (1er mot après `## Statut`) : Accepted/Proposed/…

    Le statut est sur la 1re ligne non vide après le titre `## Statut`.
    """
    m = re.search(r"^##\s+Statut\s*$", text, re.MULTILINE)
    if not m:
        return None
    rest = text[m.end() :]
    for line in rest.splitlines():
        line = line.strip()
        if not line:
            continue
        word = re.match(r"([A-Za-zé]+)", line)
        return word.group(1) if word else None
    return None


def adr_has_checklist(text: str) -> bool:
    """Heuristique : un ADR ne doit pas contenir de checklist d'implémentation
    (ADR 0057 §2). Signaux (volontairement stricts pour éviter les faux positifs
    sur la prose qui *cite* un palier `P6` d'audit) :
      - une LIGNE DE TABLEAU de paliers : `| **P0** | … |` / `| P0 | … |` ;
      - une colonne `Palier` dans un tableau ;
      - des cases à cocher `- [ ]` / `- [x]`.
    """
    if re.search(r"^\s*\|\s*\*{0,2}P\d\b.*\|", text, re.MULTILINE):
        return True
    if re.search(r"^\s*-\s+\[[ xX]\]\s", text, re.MULTILINE):
        return True
    return bool(re.search(r"\bPalier\b\s*\|", text))


def parse_plan_etat(text: str) -> str | None:
    """Extrait la valeur de l'en-tête `## État` d'un plan : `> **État : Actif**…`.

    Renvoie None si l'en-tête `## État` ou la valeur sont absents.
    """
    if not re.search(r"^##\s+État\s*$", text, re.MULTILINE):
        return None
    m = re.search(r"\*\*\s*État\s*:\s*([A-Za-zé]+)\s*\*\*", text)
    return m.group(1) if m else None


def plan_has_suivi(text: str) -> bool:
    return bool(re.search(r"^##\s+Suivi\b", text, re.MULTILINE))


def plan_refs_adr(text: str) -> bool:
    """Le plan référence-t-il un ADR fondateur (lien `decisions/NNNN` ou `ADR NNNN`) ?"""
    return bool(re.search(r"decisions/\d{4}", text) or re.search(r"\bADR\s+\d{4}\b", text))


def is_living_plan(filename: str) -> bool:
    """Un plan VIVANT suit `plan-<thème>.md` ; un `AAAA-MM-JJ-audit-*` est un
    audit de session (figé), exempté des règles de plan (ADR 0057 §4)."""
    base = os.path.basename(filename)
    return base.startswith("plan-") and base.endswith(".md")


def drift_issue_ok(entry: dict) -> bool:
    """Un drift `ouvert`/`en-cours` doit porter une `issue:` non vide ≠ TODO
    (ADR 0058 §6). Un drift corrigé/caduc n'en a pas besoin."""
    if entry.get("statut") not in DRIFT_OPEN_STATUTS:
        return True
    issue = str(entry.get("issue", "")).strip()
    return bool(issue) and issue.upper() != "TODO"


def parse_index_statuts(index_text: str) -> dict[str, str]:
    """Parse le tableau `decisions/README.md` → {num: statut}."""
    out: dict[str, str] = {}
    for line in index_text.splitlines():
        m = re.match(r"^\|\s*(\d{4})\s*\|.*\|\s*([A-Za-z][\w ]*?)\s*\|\s*$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def normalize_statut(s: str | None) -> str | None:
    """Le 1er mot du statut (l'index met `Superseded by 0049` → `Superseded`)."""
    if not s:
        return None
    return s.split()[0]


def days_since(date_str: str, today: dt.date) -> int | None:
    """Nombre de jours entre une date `AAAA-MM-JJ` et `today` (None si invalide)."""
    try:
        d = dt.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None
    return (today - d).days


# ── Collecte (I/O — non pure) ───────────────────────────────────────────────
def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _git_files(pattern: str, root: str) -> list[str]:
    """Fichiers versionnés correspondant à un glob, via le système de fichiers
    (on reste simple : on liste le dossier et on filtre)."""
    import glob

    return sorted(glob.glob(os.path.join(root, pattern)))


@dataclass
class Repo:
    root: str
    today: dt.date

    def adr_files(self) -> list[str]:
        return [
            p
            for p in _git_files(os.path.join(DECISIONS_DIR, "0*.md"), self.root)
            if adr_number_from_filename(p)
        ]

    def plan_files(self) -> list[str]:
        return _git_files(os.path.join(PLANS_DIR, "*.md"), self.root)

    def drifts(self) -> list[dict]:
        path = os.path.join(self.root, DRIFTS_FILE)
        if not os.path.exists(path):
            return []
        data = yaml.safe_load(_read(path)) or {}
        return data.get("drifts", []) or []

    def audit_passages(self) -> list[str]:
        """Dossiers `docs/audit/AAAA-MM-JJ`."""
        base = os.path.join(self.root, AUDIT_DIR)
        if not os.path.isdir(base):
            return []
        return sorted(d for d in os.listdir(base) if re.match(r"^\d{4}-\d{2}-\d{2}$", d))

    def scenarios(self) -> list[str]:
        return _git_files(os.path.join("test", "scenarios", "[0-9]*.sh"), self.root)


# ── Règles (orchestrent les fonctions pures sur le dépôt) ───────────────────
def check_plans(repo: Repo) -> list[Finding]:
    out: list[Finding] = []
    for path in repo.plan_files():
        if os.path.basename(path) == "README.md":
            continue
        if not is_living_plan(path):
            continue  # audit de session daté : exempté (ADR 0057 §4)
        text = _read(path)
        rel = os.path.relpath(path, repo.root)
        etat = parse_plan_etat(text)
        if etat is None:
            out.append(Finding("plan", rel, "en-tête `## État` absent (ADR 0057 §3)"))
        elif etat not in PLAN_ETATS:
            out.append(Finding("plan", rel, f"valeur `## État` invalide : « {etat} » {PLAN_ETATS}"))
        if not plan_has_suivi(text):
            out.append(Finding("plan", rel, "section « Suivi » absente (ADR 0057 §3)"))
        if not plan_refs_adr(text):
            out.append(Finding("plan", rel, "ne référence aucun ADR fondateur"))
    return out


def check_adrs(repo: Repo) -> list[Finding]:
    out: list[Finding] = []
    for path in repo.adr_files():
        text = _read(path)
        rel = os.path.relpath(path, repo.root)
        if parse_adr_statut(text) is None:
            out.append(Finding("adr", rel, "section `## Statut` absente ou illisible"))
        if adr_has_checklist(text):
            out.append(
                Finding("adr", rel, "contient une checklist/paliers — interdit (ADR 0057 §2)")
            )
    return out


def check_drifts(repo: Repo) -> list[Finding]:
    out: list[Finding] = []
    for entry in repo.drifts():
        if not drift_issue_ok(entry):
            out.append(
                Finding(
                    "drift",
                    str(entry.get("id", "?")),
                    f"statut `{entry.get('statut')}` sans `issue:` valide (ADR 0058 §6)",
                )
            )
    return out


def check_index(repo: Repo) -> list[Finding]:
    out: list[Finding] = []
    index_path = os.path.join(repo.root, DECISIONS_INDEX)
    if not os.path.exists(index_path):
        return [Finding("index", DECISIONS_INDEX, "index des décisions absent")]
    index = parse_index_statuts(_read(index_path))
    files = {adr_number_from_filename(p): p for p in repo.adr_files()}
    # tout fichier ADR doit être dans l'index
    for num in files:
        if num not in index:
            out.append(Finding("index", f"ADR {num}", "fichier présent mais absent de l'index"))
    # toute ligne d'index doit avoir un fichier
    for num in index:
        if num not in files:
            out.append(Finding("index", f"ADR {num}", "listé à l'index mais fichier introuvable"))
    # numéros en doublon (détectés par collision de fichiers — glob trie, donc on
    # vérifie l'unicité des numéros)
    nums = [adr_number_from_filename(p) for p in repo.adr_files()]
    dupes = {n for n in nums if nums.count(n) > 1}
    for n in sorted(dupes):
        out.append(Finding("index", f"ADR {n}", "numéro d'ADR en doublon"))
    # statut index ↔ fichier
    for num, path in files.items():
        file_statut = normalize_statut(parse_adr_statut(_read(path)))
        idx_statut = normalize_statut(index.get(num))
        if file_statut and idx_statut and file_statut != idx_statut:
            out.append(
                Finding(
                    "index",
                    f"ADR {num}",
                    f"statut index « {idx_statut} » ≠ fichier « {file_statut} »",
                )
            )
    return out


def check_freshness(repo: Repo, audit_max_days: int) -> list[Finding]:
    out: list[Finding] = []
    passages = repo.audit_passages()
    if not passages:
        return [Finding("fraicheur", AUDIT_DIR, "aucun passage d'audit daté trouvé")]
    latest = max(passages)  # AAAA-MM-JJ trie chronologiquement
    age = days_since(latest, repo.today)
    if age is not None and age > audit_max_days:
        out.append(
            Finding(
                "fraicheur",
                f"audit {latest}",
                f"dernier passage daté de {age} j (> seuil {audit_max_days} j) — un passage est dû",
            )
        )
    return out


# ── Statistiques ────────────────────────────────────────────────────────────
def gather_stats(repo: Repo) -> dict:
    from collections import Counter

    adr_statuts = Counter(
        normalize_statut(parse_adr_statut(_read(p))) or "?" for p in repo.adr_files()
    )
    plans = [p for p in repo.plan_files() if is_living_plan(p)]
    plan_etats = Counter(parse_plan_etat(_read(p)) or "?" for p in plans)
    drift_statuts = Counter(d.get("statut", "?") for d in repo.drifts())
    return {
        "adr_total": len(repo.adr_files()),
        "adr_par_statut": dict(adr_statuts),
        "plans_vivants": len(plans),
        "plans_par_etat": dict(plan_etats),
        "drifts_total": len(repo.drifts()),
        "drifts_par_statut": dict(drift_statuts),
        "scenarios_e2e": len(repo.scenarios()),
    }


def format_stats(stats: dict) -> str:
    lignes = [
        "## Le dépôt en chiffres",
        "",
        f"- **{stats['adr_total']} ADR** "
        f"({', '.join(f'{v} {k}' for k, v in sorted(stats['adr_par_statut'].items()))})",
        f"- **{stats['plans_vivants']} plans** vivants "
        f"({', '.join(f'{v} {k}' for k, v in sorted(stats['plans_par_etat'].items()))})",
        f"- **{stats['drifts_total']} drifts** indexés "
        f"({', '.join(f'{v} {k}' for k, v in sorted(stats['drifts_par_statut'].items()))})",
        f"- **{stats['scenarios_e2e']} scénarios** E2E reproductibles",
    ]
    return "\n".join(lignes)


# ── CLI ─────────────────────────────────────────────────────────────────────
def run_all_checks(repo: Repo, audit_max_days: int) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_plans(repo)
    findings += check_adrs(repo)
    findings += check_drifts(repo)
    findings += check_index(repo)
    findings += check_freshness(repo, audit_max_days)
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "check-gouvernance : OK — toutes les conventions sont respectées."
    by_famille: dict[str, list[Finding]] = {}
    for f in findings:
        by_famille.setdefault(f.famille, []).append(f)
    out = [f"check-gouvernance : {len(findings)} manquement(s).", ""]
    titres = {
        "plan": "Plans (ADR 0057 §3)",
        "adr": "ADR (ADR 0057 §2)",
        "drift": "Drifts (ADR 0058 §6)",
        "index": "Index des décisions",
        "fraicheur": "Fraîcheur des traces (ADR 0058)",
    }
    for famille in ["plan", "adr", "drift", "index", "fraicheur"]:
        items = by_famille.get(famille, [])
        if not items:
            continue
        out.append(f"### {titres.get(famille, famille)}")
        for f in items:
            out.append(f"- **{f.cible}** : {f.message}")
        out.append("")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit des conventions de gouvernance (ADR 0060).")
    ap.add_argument("--stats", action="store_true", help="émettre le bloc « le dépôt en chiffres »")
    ap.add_argument("--report", action="store_true", help="rapport de conformité (défaut)")
    ap.add_argument("--audit-max-days", type=int, default=DEFAULT_AUDIT_MAX_DAYS)
    ap.add_argument("--root", default=".", help="racine du dépôt")
    args = ap.parse_args(argv)

    repo = Repo(root=args.root, today=dt.date.today())

    if args.stats:
        print(format_stats(gather_stats(repo)))
        return 0

    findings = run_all_checks(repo, args.audit_max_days)
    print(format_report(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
