"""Consignation d'un run from-scratch RÉUSSI dans `bench/lima/runs-history.yaml`
(ex-`metro_record_run` de metrology.sh, retiré par ADR 0101 — porté en Python).

Câble le callback `record` de `nestor.path.run_path` : quand un chemin est monté
de bout en bout (aucune phase en échec), on APPEND une entrée datée à l'historique
(preuve, ADR 0034/0042). Chaque entrée porte le COMMIT git du code qui l'a produit
(traçabilité de preuve : un run non attribuable à un SHA n'est pas rejouable).

Découpage (ADR 0017, testable sans banc) :
  - `git_revision(repo_root, run=…)` : SHA court + `-dirty` si l'arbre a des modifs
    non committées (honnêteté : un run sur un arbre sale n'est pas reproductible
    bit-exact). `run` (subprocess.run) INJECTÉ → testable sans vrai dépôt.
  - `build_run_entry(...)` : PUR — assemble le dict d'entrée depuis le PathResult
    (durées de phases mesurées par le moteur), la topo, et les faits système/git
    passés EN ARGUMENT (date/arch/hote/branche/commit). Aucune I/O, aucune horloge.
  - `append_run(path, entry)` : la SEULE I/O — relit runs-history.yaml, ajoute
    l'entrée, réécrit byte-stable (`yaml.safe_dump(sort_keys=False)`, format du fichier).

Les MÉTRIQUES (cpu_core_s/ram_*) sont OMISES : elles étaient échantillonnées via
node-exporter/Prometheus PENDANT le run (monitoring déployé APRÈS le socle) — non
disponibles côté Python au moment du record. On consigne le run SANS métriques
(honnête) plutôt qu'inventer des valeurs ; elles restent ajoutables a posteriori.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import subprocess
from typing import Any

import yaml


def git_revision(repo_root: str, *, run=subprocess.run) -> tuple[str | None, str | None]:
    """(`branche`, `commit`) du dépôt à `repo_root`. `commit` = SHA court, suffixé
    `-dirty` si l'arbre de travail a des modifications non committées (le run n'est
    alors PAS reproductible bit-exact — honnêteté de preuve). `run` (subprocess.run)
    est INJECTÉ pour les tests. Toute erreur git (pas un dépôt, git absent) → (None, None)."""

    def _git(*args: str) -> str | None:
        try:
            proc = run(  # noqa: S603 — argv fixe (pas d'entrée shell), cwd contrôlé
                ["git", *args],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, ValueError):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    branche = _git("rev-parse", "--abbrev-ref", "HEAD")
    commit = _git("rev-parse", "--short", "HEAD")
    if commit is not None:
        dirty = _git("status", "--porcelain")
        if dirty:  # sortie non vide → arbre sale
            commit = f"{commit}-dirty"
    return branche, commit


def _phase_durations(result) -> dict[str, int]:
    """Durées ENTIÈRES (secondes) des phases de MONTAGE (pas les gates) d'un PathResult.
    Une phase = un step SANS suffixe ` (gate)` portant un `duration_s`. PUR."""
    out: dict[str, int] = {}
    for step in result.steps:
        if step.name.endswith(" (gate)") or step.duration_s is None:
            continue
        out[step.name] = round(step.duration_s)
    return out


def host_model(*, run=subprocess.run) -> str:
    """MODÈLE matériel de l'hôte (ex. `Mac15,9`), pas son nom d'hôte. GÉNÉRIQUE (ADR 0023) :
    un modèle de machine ne trahit aucune infra réelle — contrairement à `platform.node()`
    qui rendrait le FQDN interne de l'organisation (fuite dans un fichier VERSIONNÉ). macOS :
    `sysctl -n hw.model` (= ce que consignait metrology.sh). Ailleurs / erreur → repli sur
    `platform.machine()` (arch, générique). `run` injecté pour les tests."""
    try:
        proc = run(  # noqa: S603 — argv fixe, pas d'entrée shell
            ["sysctl", "-n", "hw.model"], capture_output=True, text=True, check=False
        )
    except (OSError, ValueError):
        return platform.machine()  # sysctl absent (Linux/CI) → repli arch générique
    model = proc.stdout.strip()
    if proc.returncode == 0 and model:
        return model
    return platform.machine()


def build_run_entry(
    result,
    *,
    topologie: str | None,
    profil: str | None,
    now: dt.datetime,
    branche: str | None,
    commit: str | None,
    arch: str | None = None,
    hote: str | None = None,
) -> dict[str, Any]:
    """Assemble l'entrée runs-history (dict ordonné) depuis un PathResult RÉUSSI et
    les faits injectés. PUR : `now`/`branche`/`commit`/`arch`/`hote` sont fournis par
    l'appelant (aucune horloge, git ni I/O ici). L'`id` = `<date-heure>-<profil>-<commit>`
    (convention du fichier). `hote` = MODÈLE matériel générique (jamais le FQDN, ADR 0023).
    `metriques` OMISES (cf. docstring module)."""
    date = now.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    id_prefix = now.astimezone(dt.UTC).strftime("%Y-%m-%dT%H")
    id_profil = profil or "run"
    id_commit = commit or "nogit"
    phases = _phase_durations(result)
    entry: dict[str, Any] = {
        "id": f"{id_prefix}-{id_profil}-{id_commit}",
        "date": date,
        "branche": branche,
        "commit": commit,
        "profil": profil,
        "topologie": topologie,
        "target": result.target,
        "arch": arch or platform.machine(),
        "hote": hote or host_model(),
        "total_s": sum(phases.values()),
        "phases": phases,
    }
    return entry


def format_entry(entry: dict[str, Any]) -> str:
    """Rend l'entrée SEULE au style du fichier runs-history.yaml : un item de liste sous
    `runs:`, indenté de 2 espaces (`  - id: …`). PUR (pas d'I/O). On NE réécrit PAS tout le
    fichier via `safe_dump` global — il ré-indenterait l'existant (diff massif) ET
    re-sérialiserait les dates déjà parsées en datetime (`…Z` → `… +00:00`, corruption). On
    formate donc l'entrée seule et on la RÉ-INDENTE de 2 espaces pour l'append en texte."""
    body = yaml.safe_dump(
        [entry], sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000
    )
    # `safe_dump([entry])` rend `- id: …\n  date: …` (item au niveau 0) ; on ré-indente de 2
    # espaces chaque ligne non vide → `  - id: …\n    date: …` (style du fichier).
    return "".join(f"  {line}" if line.strip() else line for line in body.splitlines(keepends=True))


def append_run(path: str, entry: dict[str, Any]) -> None:
    """Append l'entrée à runs-history.yaml EN TEXTE (la SEULE I/O), sans relire/réécrire
    l'existant (préserve byte-pour-byte les runs déjà consignés — dates intactes). Crée le
    fichier avec `runs:` si absent. L'appelant garantit un fichier terminé par un saut de ligne."""
    prefix = ""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        prefix = "runs:\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(prefix + format_entry(entry))
