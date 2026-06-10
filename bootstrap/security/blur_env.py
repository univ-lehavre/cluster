#!/usr/bin/env python3
"""Anonymise un fichier `.env` en `.env-example` (ADR 0023 — valeurs génériques).

Portage de l'ancien `blur-env.pl` vers Python (ADR 0049 : texte/regex pur →
Python, pas de nouveau Perl). Les fonctions de décision sont PURES (pas d'accès
disque ni d'aléa caché) et testées par `tests/test_blur_env.py` ; seule l'entrée
de programme `main()` touche le système de fichiers et tire l'aléa.

Règle : on conserve commentaires, lignes vides et lignes sans `=` ; pour chaque
`clé=valeur`, on remplace la valeur par un exemple générique dérivé d'abord du
FORMAT de la valeur (IP, liste d'IP, chemin, e-mail, entier, localhost), puis à
défaut du NOM de la clé (MAIL, IP, USER, PATH, PORT, HOST, secret, identifiant).

Usage : python3 blur_env.py            # .env → .env-example
        python3 blur_env.py src dst    # chemins explicites
"""

from __future__ import annotations

import random
import re
import sys
from collections.abc import Callable

# Segments de chemin « standard » conservés tels quels ; les autres → « exemple ».
_KNOWN_PATH_SEGMENTS = frozenset(
    [
        "tmp",
        "log",
        "passwd",
        "shadow",
        "hosts",
        "hostname",
        "resolv.conf",
        "null",
        "zero",
        "random",
        "urandom",
        "bin",
        "etc",
        "usr",
        "var",
        "dev",
        "run",
        "cache",
        "python",
        "perl",
        "sh",
        "bash",
        ".ssh",
        "config",
    ]
)

_IP = r"\d{1,3}(?:\.\d{1,3}){3}"
_RE_SINGLE_IP = re.compile(rf"^{_IP}$")
_RE_IP_LIST = re.compile(rf"^\s*{_IP}\s*(,\s*{_IP}\s*)*$")
_RE_PATH = re.compile(r"^(?:/|\./|\.\./|~/?)[^\0]*$")
_RE_EMAIL = re.compile(r"^[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}$")
_RE_INT = re.compile(r"^\d+$")
_RE_COMMENT_OR_BLANK = re.compile(r"^\s*#|^\s*$")
_RE_KV = re.compile(r"^([^=]+)=(.*)$")
_RE_PATH_PREFIX = re.compile(r"^(~/?|/|\./|\.\./)")
_RE_EXT = re.compile(r"(\.[a-zA-Z0-9]+)$")


def random_ip(rng: random.Random | None = None) -> str:
    """IP IPv4 d'exemple (chaque octet dans 1..223). `rng` injectable (tests)."""
    r = rng or random
    return ".".join(str(r.randint(1, 223)) for _ in range(4))


def fake_path(val: str) -> str:
    """Anonymise un chemin : préfixe et segments « standard » gardés, sinon « exemple »."""
    ext_match = _RE_EXT.search(val)
    ext = ext_match.group(1) if ext_match else ""
    prefix_match = _RE_PATH_PREFIX.match(val)
    if not prefix_match:
        return val
    prefix = prefix_match.group(1)
    body = _RE_PATH_PREFIX.sub("", val, count=1)
    parts = [seg if seg in _KNOWN_PATH_SEGMENTS else "exemple" for seg in body.split("/")]
    fake = prefix + "/".join(parts)
    if ext and not fake.endswith(ext):
        fake += ext
    return fake


def anonymise_value(key: str, val: str, ip_gen: Callable[[], str] = random_ip) -> str:
    """Valeur d'exemple pour `key=val`, dérivée du format puis du nom de clé.

    PURE : `ip_gen` (défaut random_ip) rend l'aléa injectable pour les tests.
    """
    if _RE_IP_LIST.match(val) and "," in val:
        return ",".join(ip_gen() for _ in val.split(","))
    if _RE_PATH.match(val):
        return fake_path(val)
    if _RE_SINGLE_IP.match(val):
        return ip_gen()
    if _RE_EMAIL.match(val):
        return "john.doe@example.com"
    if _RE_INT.match(val):
        return "42"
    if "localhost" in val or "127.0.0.1" in val:
        return "localhost"
    # À défaut du format, on dérive du NOM de la clé (ordre = priorité historique).
    rules: list[tuple[str, Callable[[], str]]] = [
        (r"MAIL|EMAIL", lambda: "john.doe@example.com"),
        (r"IP", ip_gen),
        (r"USER|LOGIN", lambda: "bob"),
        (r"PATH|DIR", lambda: fake_path(val)),
        (r"PORT", lambda: "8080"),
        (r"HOST", lambda: "localhost"),
        (r"PWD|PASS|SECRET|TOKEN", lambda: "changeme123"),
        (r"ID|NUM|COUNT|NB|ENTIER", lambda: "42"),
    ]
    for pattern, producer in rules:
        if re.search(pattern, key, re.IGNORECASE):
            return producer()
    return "valeur_exemple"


def anonymise_line(line: str, ip_gen: Callable[[], str] = random_ip) -> str:
    """Anonymise une ligne `.env` (commentaire/vide/sans-`=` inchangés). PURE."""
    line = line.rstrip("\n")
    if _RE_COMMENT_OR_BLANK.match(line):
        return line
    kv = _RE_KV.match(line)
    if not kv:
        return line
    key, val = kv.group(1), kv.group(2)
    return f"{key}={anonymise_value(key, val, ip_gen)}"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    src = args[0] if len(args) > 0 else ".env"
    dst = args[1] if len(args) > 1 else ".env-example"
    try:
        with open(src, encoding="utf-8") as fin:
            lines = fin.readlines()
    except OSError as exc:
        print(f"Impossible d'ouvrir {src} : {exc}", file=sys.stderr)
        return 1
    out = [anonymise_line(line) for line in lines]
    with open(dst, "w", encoding="utf-8") as fout:
        fout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
