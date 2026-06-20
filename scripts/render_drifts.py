#!/usr/bin/env python3
"""Rend le registre des drifts en page Markdown navigable (ADR 0017).

Le registre de vérité est `docs/architecture/registre-drifts.yaml` (source
unique, honnêteté des Runs — ADR 0023/0034/0058). Ce script en dérive une PAGE
`docs/architecture/registre-drifts.md` : tableau par portée + compteurs, pour
que le registre soit **explorable** dans le site (pas seulement lisible en YAML
brut). La page est GÉNÉRÉE — ne pas l'éditer à la main.

Usage :
  python3 scripts/render_drifts.py            # régénère la page
  python3 scripts/render_drifts.py --check    # vérifie qu'elle est à jour (exit 1 sinon)

La logique de rendu (pure) est testable sans I/O via `render_markdown`.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH = os.path.join("docs", "architecture", "registre-drifts.yaml")
MD_PATH = os.path.join("docs", "architecture", "registre-drifts.md")

# Ordre et libellés des portées (ADR 0058 §6).
PORTEES = {
    "livrable": "Livrable (bug — vaut pour tous les bancs ET la prod)",
    "code": "Code (défaut du livrable révélé au run)",
    "env": "Environnement (artefact d'un banc précis)",
    "harnais": "Harnais (outillage de test, pas le livrable)",
}
STATUT_ICONE = {"corrige": "✅", "caduc": "🗑️", "en-cours": "🔄", "ouvert": "🔴"}

BANNER = (
    "<!-- PAGE GÉNÉRÉE par scripts/render_drifts.py depuis registre-drifts.yaml.\n"
    "     NE PAS ÉDITER À LA MAIN — modifier le YAML puis régénérer "
    "(`uv run python scripts/render_drifts.py`). -->"
)


def render_markdown(drifts: list[dict]) -> str:
    """Rend la page Markdown depuis la liste des drifts (PURE, testable)."""
    from collections import Counter

    par_statut = Counter(d.get("statut") for d in drifts)
    par_portee = Counter(d.get("portee") for d in drifts)

    out: list[str] = [BANNER, "", "# Registre des drifts — vue navigable", ""]
    out.append(
        "Un **drift** = un écart révélé par un run e2e que le lint ne voyait pas "
        "(honnêteté des Runs, "
        "[ADR 0052](../decisions/0052-reproductibilite-des-resultats.md) / "
        "[ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md) §6). La "
        "**source de vérité** reste "
        "[`registre-drifts.yaml`](registre-drifts.yaml) ; cette page en est le "
        "rendu navigable, **généré** (ne pas l'éditer)."
    )
    out += ["", "## En chiffres", ""]
    total = len(drifts)
    statut_txt = ", ".join(f"{n} {s}" for s, n in sorted(par_statut.items()))
    portee_txt = ", ".join(f"{n} {p}" for p, n in sorted(par_portee.items()))
    out.append(f"- **{total} drifts** indexés — statut : {statut_txt}.")
    out.append(f"- Par portée : {portee_txt}.")

    for portee, titre in PORTEES.items():
        rows = [d for d in drifts if d.get("portee") == portee]
        if not rows:
            continue
        out += ["", f"## {titre} ({len(rows)})", ""]
        out.append("| Id | Statut | Campagne | Symptôme → correctif |")
        out.append("| --- | --- | --- | --- |")
        for d in rows:
            icone = STATUT_ICONE.get(d.get("statut"), "")
            sym = _clean(d.get("symptome", ""))
            cor = _clean(d.get("correctif", ""))
            issue = d.get("issue")
            issue_txt = f" ({issue})" if issue else ""
            out.append(
                f"| `{d.get('id')}` | {icone} {d.get('statut')}{issue_txt} "
                f"| {_clean(d.get('campagne', ''))} | {sym} → {cor} |"
            )
    # Normalise : jamais deux lignes vides consécutives (markdownlint MD012).
    normalised: list[str] = []
    for line in out:
        if line == "" and normalised and normalised[-1] == "":
            continue
        normalised.append(line)
    return "\n".join(normalised)


def _clean(s: str) -> str:
    """Aplatit un champ multi-lignes en une cellule de tableau.

    - effondre les espaces (pas de saut de ligne dans une cellule) ;
    - échappe `|` (séparateur de colonne) ;
    - **neutralise les URL** `http(s)://…` en les mettant en code inline : sans
      ça, le vérificateur de liens (lychee) tenterait de résoudre un fragment
      d'URL cité dans le SYMPTÔME d'un drift (ex. `gitea-http…/atlas.git`) comme
      un vrai lien et échouerait. En backticks, c'est du texte inerte.
    """
    flat = " ".join(str(s).split()).replace("|", "\\|")
    # N'envelopper que les URL PAS déjà en code inline (le texte source en met
    # parfois déjà entre backticks → éviter le double backtick qui rouvre l'URL).
    return re.sub(r"(?<!`)(https?://\S+?)(?!`)(?=[\s)\]]|\\\||$)", r"`\1`", flat)


def load_drifts() -> list[dict]:
    with open(os.path.join(ROOT, YAML_PATH), encoding="utf-8") as fh:
        return yaml.safe_load(fh)["drifts"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rend le registre des drifts en Markdown (ADR 0017).")
    ap.add_argument("--check", action="store_true", help="vérifier sans écrire (exit 1 si périmé)")
    args = ap.parse_args(argv)

    rendered = render_markdown(load_drifts()) + "\n"
    path = os.path.join(ROOT, MD_PATH)

    if args.check:
        current = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                current = fh.read()
        if current != rendered:
            print(
                f"{MD_PATH} périmé — régénérer via `uv run python scripts/render_drifts.py`.",
                file=sys.stderr,
            )
            return 1
        print(f"{MD_PATH} : à jour.")
        return 0

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    print(f"{MD_PATH} régénéré ({len(load_drifts())} drifts).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
