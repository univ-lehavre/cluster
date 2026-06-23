#!/usr/bin/env python3
"""Migration de la documentation VitePress → Astro Starlight (ADR 0089).

Transforme le contenu pour Astro Starlight en préservant les URL VitePress :

1. Copie `docs/**/*.md` → `docs/src/content/docs/docs/**` (préserve l'URL
   /docs/..., ajoute le frontmatter `title:` requis par Starlight, dérivé du
   premier H1). Les fichiers colocalisés (README/RUNBOOK hors docs/) ne sont PAS
   copiés : ils sont lus EN PLACE par la collection glob + src/pages/[...slug].astro
   (source unique, ADR 0023). Mais leurs LIENS sont réécrits sur place.

2. Réécrit les liens Markdown dans TOUS les fichiers servis :
   - lien `.md` vers une cible SERVIE par le site → URL absolue `/cluster/<url>`
     (sans `.md`, avec trailing slash, casse VitePress préservée) ;
   - lien vers un fichier de CODE (.sh/.py/.yaml/roles/…, non servi) → URL GitHub
     absolue `https://github.com/univ-lehavre/cluster/blob/main/<chemin>` ;
   - lien externe http(s) ou ancre pure (#...) → inchangé.

Idempotent : relancer ne change rien (les liens déjà en /cluster/ ou github.com
sont reconnus et laissés tels quels). Le build `astro build` valide le résultat
(starlight-links-validator bloquant).

Usage :
    uv run python scripts/migrate_docs_to_astro.py            # applique
    uv run python scripts/migrate_docs_to_astro.py --dry-run  # montre sans écrire
"""

from __future__ import annotations

import argparse
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE = "/cluster"
GH_BLOB = "https://github.com/univ-lehavre/cluster/blob/main"
CONTENT_DOCS = REPO / "docs" / "src" / "content" / "docs"

# Extensions considérées comme du CODE (non servi par le site → lien GitHub).
CODE_EXT = {
    ".sh",
    ".py",
    ".pl",
    ".j2",
    ".tmpl",
    ".yaml",
    ".yml",
    ".toml",
    ".cff",
    ".conf",
    ".log",
    ".example",
    ".json",
    ".ts",
    ".mjs",
    ".cjs",
    ".lock",
}
# Fichiers de code sans extension reconnue (par nom).
CODE_NAMES = {"Justfile", "Vagrantfile", "Dockerfile"}

LINK_RE = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)]+)\)")  # [texte](cible), hors images


def list_tracked_md() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    res = []
    for p in out:
        if any(seg in p for seg in ("node_modules", "redcap/source", "redcap/image/source")):
            continue
        # .github/ : templates (issue/PR) lus DANS l'UI GitHub, jamais servis par
        # le site → leurs liens relatifs restent corrects sur GitHub, ne pas réécrire.
        if p.startswith(".github/"):
            continue
        if p.endswith(("CHANGELOG.md", "LICENSE.md")):
            continue
        if p == "README.md":  # README racine : hors documentation (demande explicite)
            continue
        res.append(Path(p))
    return res


def url_for_served(repo_rel: str) -> str | None:
    """URL Starlight (avec base, sans .md, trailing slash) d'un .md servi, ou None.

    Reproduit le routage VitePress srcDir='..' :
      docs/architecture/x.md       → /cluster/docs/architecture/x/
      docs/decisions/README.md     → /cluster/docs/decisions/
      storage/ceph/README.md       → /cluster/storage/ceph/
      bootstrap/RUNBOOK.md         → /cluster/bootstrap/RUNBOOK/
      SECURITY.md                  → /cluster/SECURITY/
    """
    if repo_rel == "README.md":
        return None  # racine, non servi
    if repo_rel == "docs/index.md":
        return f"{BASE}/"  # ancienne home VitePress → racine du site Starlight
    if not repo_rel.endswith(".md"):
        return None
    slug = repo_rel[:-3]  # retire .md (casse préservée)
    slug = re.sub(r"(^|/)README$", r"\1", slug)  # README → index de dossier
    slug = slug.rstrip("/")
    return f"{BASE}/{slug}/" if slug else f"{BASE}/"


def is_code(repo_rel: str) -> bool:
    name = posixpath.basename(repo_rel)
    if name in CODE_NAMES:
        return True
    suf = Path(repo_rel).suffix
    return suf in CODE_EXT


def resolve_target(raw: str, src_repo_rel: str, served: set[str]) -> str | None:
    """Calcule le remplacement d'une cible de lien, ou None si on n'y touche pas.

    src_repo_rel : chemin du fichier SOURCE depuis la racine (pour résoudre le
    relatif). served : ensemble des chemins .md servis (repo-relatifs).
    """
    target = raw.strip()
    # ne pas toucher : externes, ancres pures, mailto, déjà migrés
    if re.match(r"^(https?:|mailto:|#|/cluster/)", target):
        return None
    # séparer ancre / query
    frag = ""
    m = re.search(r"[#?]", target)
    if m:
        frag = target[m.start() :]
        target = target[: m.start()]
    if not target:
        return None  # ancre pure
    # chemin absolu depuis la racine repo (commence par /) ou relatif
    if target.startswith("/"):
        repo_rel = posixpath.normpath(target.lstrip("/"))
    else:
        base_dir = posixpath.dirname(src_repo_rel)
        repo_rel = posixpath.normpath(posixpath.join(base_dir, target))
    if repo_rel.startswith(".."):
        return None  # hors repo, on laisse

    # cible .md servie → URL Starlight
    if repo_rel.endswith(".md"):
        if repo_rel in served:
            url = url_for_served(repo_rel)
            return (url.rstrip("/") + "/" + frag) if frag and url else (url + frag if url else None)
        # .md non servi (ex. README racine) → GitHub
        return f"{GH_BLOB}/{repo_rel}{frag}"
    # dossier (lien vers /storage/ceph/ ou roles/…) : servi si <dir>/README.md servi
    dir_readme = posixpath.join(repo_rel, "README.md")
    if dir_readme in served:
        return f"{BASE}/{repo_rel.rstrip('/')}/{frag}"
    # sinon : code ou dossier non-doc → GitHub
    return f"{GH_BLOB}/{repo_rel}{frag}"


def rewrite_links(text: str, src_repo_rel: str, served: set[str]) -> tuple[str, int]:
    n = 0

    def repl(mobj: re.Match) -> str:
        nonlocal n
        label, raw = mobj.group(1), mobj.group(2)
        # garder un éventuel titre "cible "titre""
        title = ""
        tm = re.match(r'^(\S+)(\s+".*")$', raw.strip())
        core = raw.strip()
        if tm:
            core, title = tm.group(1), tm.group(2)
        new = resolve_target(core, src_repo_rel, served)
        if new is None:
            return mobj.group(0)
        n += 1
        return f"[{label}]({new}{title})"

    return LINK_RE.sub(repl, text), n


def first_h1_title(text: str) -> str | None:
    m = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).replace("`", "").strip()


def strip_first_h1(text: str) -> str:
    """Retire le PREMIER titre H1 (`# …`) du corps + la ligne vide qui le suit.

    Starlight rend déjà le `title` du frontmatter comme H1 de la page : conserver le
    `# H1` du contenu le DUPLIQUE. On ne retire que le premier (les `#` suivants, rares,
    sont du contenu légitime). Pur ; n'agit que sur la copie générée (cf. main)."""
    m = re.search(r"^#\s+.+?\s*$", text, re.MULTILINE)
    if not m:
        return text
    before, after = text[: m.start()], text[m.end() :]
    after = after.lstrip("\n")  # absorbe la/les ligne(s) vide(s) après le H1 retiré
    return (before.rstrip("\n") + ("\n\n" if before.strip() else "") + after).lstrip("\n")


def has_frontmatter(text: str) -> bool:
    return text.lstrip().startswith("---")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--content-only",
        action="store_true",
        help="régénère seulement src/content/docs/docs/ (étape de build idempotente) ; "
        "NE réécrit PAS les liens des fichiers colocalisés (migration one-shot, déjà commitée)",
    )
    args = ap.parse_args()

    md_files = list_tracked_md()
    served = {p.as_posix() for p in md_files}  # tous les .md servis (repo-relatifs)
    # docs/ sont copiés ; les colocalisés sont réécrits en place.
    docs_files = [p for p in md_files if p.as_posix().startswith("docs/")]
    coloc_files = [p for p in md_files if not p.as_posix().startswith("docs/")]

    # Purge de la copie générée (un fichier retiré de docs/ ne doit pas rester
    # fantôme). La copie est gitignorée et régénérée à chaque build (modèle atlas).
    gen_dir = CONTENT_DOCS / "docs"
    if not args.dry_run and gen_dir.exists():
        shutil.rmtree(gen_dir)

    copied = links_total = 0

    # 1. docs/ → src/content/docs/docs/ (+ frontmatter title), liens réécrits
    for p in docs_files:
        rel = p.as_posix()
        # docs/index.md (ancienne home VitePress `layout: home`) NE devient PAS
        # /docs/ : son contenu est transposé à la main dans la home Starlight
        # src/content/docs/index.mdx (servie à /). On ne le copie donc pas.
        if rel == "docs/index.md":
            continue
        src = REPO / p
        text = src.read_text(encoding="utf-8")
        new_text, n = rewrite_links(text, rel, served)
        links_total += n
        if not has_frontmatter(new_text):
            title = first_h1_title(new_text) or p.stem
            # échapper les guillemets et : dans le title YAML
            safe = title.replace('"', '\\"')
            # Starlight REND le `title` du frontmatter comme H1 de la page. Si le corps
            # garde son propre `# H1` (celui d'où vient le title), le titre est DUPLIQUÉ.
            # On retire donc CE premier H1 de la COPIE générée — les fichiers SOURCES
            # gardent leur `# H1` (README lisibles isolément hors du site, par choix).
            new_text = strip_first_h1(new_text)
            new_text = f'---\ntitle: "{safe}"\n---\n\n{new_text}'
        # Starlight sert `index.md` comme index de dossier (PAS `README.md`).
        # docs/architecture/README.md → .../docs/architecture/index.md → /docs/architecture/
        rel_dest = p.relative_to("docs")
        if rel_dest.name == "README.md":
            rel_dest = rel_dest.with_name("index.md")
        dest = CONTENT_DOCS / "docs" / rel_dest
        copied += 1
        if args.dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(new_text, encoding="utf-8")

    # 2. colocalisés : réécriture des liens EN PLACE (one-shot de migration).
    # Sautée en --content-only (étape de build) : ces fichiers sont déjà migrés
    # et versionnés, on ne re-touche pas le working tree à chaque build.
    coloc_rewritten = 0
    if not args.content_only:
        for p in coloc_files:
            rel = p.as_posix()
            src = REPO / p
            text = src.read_text(encoding="utf-8")
            new_text, n = rewrite_links(text, rel, served)
            if n:
                links_total += n
                coloc_rewritten += 1
                if not args.dry_run:
                    src.write_text(new_text, encoding="utf-8")

    print(f"docs/ copiés       : {copied}")
    print(f"colocalisés modifiés: {coloc_rewritten}")
    print(f"liens réécrits     : {links_total}")
    if args.dry_run:
        print("(dry-run : aucune écriture)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
