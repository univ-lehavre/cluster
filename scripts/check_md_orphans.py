#!/usr/bin/env python3
"""Garde-fou ADR 0029 — tout Markdown versionné est atteignable depuis la doc.

Atteignable = présent dans le sidebar VitePress OU cible (transitive) d'un lien
Markdown depuis une page elle-même atteignable. Sort en code 1 s'il reste un
orphelin.

Atteignabilité = parcours en largeur (BFS) :
  racines = entrées `link:` du sidebar/nav (docs/.vitepress/config.mjs)
  arêtes  = liens Markdown `](cible)` entre fichiers versionnés

Usage : python3 scripts/check_md_orphans.py   (via `pnpm lint:docs-orphans`)

La logique (résolution de liens + BFS) est isolée dans des fonctions pures
testées par tests/test_check_md_orphans.py (ADR 0017 : tout script de logique
est testé). Python plutôt que bash : parcours de graphe + chemins relatifs.
"""

from __future__ import annotations

import os
import posixpath
import re
import subprocess
import sys
from collections import deque
from collections.abc import Callable, Iterable

# Non rendus par VitePress (alignés sur `srcExclude` du config).
EXCLUDE_RE = re.compile(r"node_modules/|\.github/|CHANGELOG\.md|LICENSE\.md|docs/\.vitepress/")
LINK_RE = re.compile(r"link:\s*['\"]([^'\"]+)['\"]")
MD_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def sidebar_link_to_file(link: str, files: set[str]) -> str | None:
    """Résout une entrée `link:` du sidebar vers un fichier source réel, ou None."""
    link = link.split("#", 1)[0]
    if link == "/":
        return "README.md" if "README.md" in files else None
    link = link.lstrip("/")
    candidates = [link + ".md", link + "/README.md"]
    if link.endswith("/"):
        candidates.append(link + "README.md")
    return next((c for c in candidates if c in files), None)


def resolve_md_link(target: str, from_dir: str, files: set[str]) -> str | None:
    """Résout un lien Markdown `](target)` (relatif ou absolu) vers un fichier, ou None."""
    target = target.split()[0].split("#", 1)[0] if target.split() else ""
    if not target or target.startswith(("http://", "https://", "mailto:")):
        return None
    base = (
        target[1:]
        if target.startswith("/")
        else posixpath.normpath(posixpath.join(from_dir, target))
    )
    candidates = [
        base,
        base + ".md",
        base.rstrip("/") + "/README.md",
        posixpath.join(base, "README.md"),
    ]
    return next((c for c in (x.removeprefix("./") for x in candidates) if c in files), None)


def find_orphans(
    all_files: Iterable[str],
    sidebar_links: Iterable[str],
    read_file: Callable[[str], str],
) -> list[str]:
    """Retourne les fichiers Markdown non atteignables, triés.

    Fonction pure : `read_file(path)` est injecté (le contenu, ou "" si illisible),
    ce qui rend le BFS testable sans toucher au disque.
    """
    files = set(all_files)
    roots = [f for f in (sidebar_link_to_file(link, files) for link in sidebar_links) if f]

    seen: set[str] = set(roots)
    queue: deque[str] = deque(roots)
    while queue:
        current = queue.popleft()
        from_dir = posixpath.dirname(current)
        for match in MD_LINK_RE.finditer(read_file(current)):
            resolved = resolve_md_link(match.group(1), from_dir, files)
            if resolved and resolved not in seen:
                seen.add(resolved)
                queue.append(resolved)

    return sorted(f for f in files if f not in seen)


def _git_markdown_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
    ).stdout
    return [f for f in out.splitlines() if f and not EXCLUDE_RE.search(f)]


def _read_safe(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def main() -> int:
    repo_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    os.chdir(repo_root)

    config = "docs/.vitepress/config.mjs"
    if not os.path.isfile(config):
        print(f"check-md-orphans: {config} introuvable", file=sys.stderr)
        return 2

    all_files = _git_markdown_files()
    sidebar_links = LINK_RE.findall(_read_safe(config))
    orphans = find_orphans(all_files, sidebar_links, _read_safe)

    if orphans:
        print(
            f"check-md-orphans: {len(orphans)} fichier(s) Markdown orphelin(s) (ADR 0029) :",
            file=sys.stderr,
        )
        for orphan in orphans:
            print(f"  - {orphan}", file=sys.stderr)
        print(
            "\nRendez-les atteignables : entrée sidebar (docs/.vitepress/config.mjs) "
            "ou lien depuis une page liée.",
            file=sys.stderr,
        )
        return 1

    print(f"check-md-orphans: OK — {len(all_files)} fichiers Markdown tous atteignables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
