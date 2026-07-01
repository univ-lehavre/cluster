"""Lecture de l'historique des runs + verdicts de fraîcheur (P4, ADR 0056 §8.10-12).

`bench/lima/runs-history.yaml` est la **preuve datée** versionnée du banc (ADR
0034/0042) : une entrée appendée par run `all` complété (champ `date`, `profil`,
`topologie`, `commit`, durées de phases, métriques échantillonnées). Ce module la
**LIT** (read-only) et en dérive, sans la réécrire :

- l'**objectif d'infra** attaché à chaque run (exig. 11 : `profil` + `topologie`
  disent *sur quoi* le résultat a été obtenu ; le champ `target`/chemin nommé est
  lu s'il est présent — rétrocompat avec les entrées antérieures qui n'en ont
  pas) ;
- un **verdict de fraîcheur** (exig. 10 : « ce chemin n'a pas de run frais »),
  calculé À L'IDENTIQUE de `bench/lima/metrology.sh` (seuils ADR 0045 §6 :
  atlas=7 j, storage-real=30 j, cluster-dataops=90 j, défaut 7 j ; surcharge
  `SEUIL_<CHEMIN>` ; le suffixe `+hardening` se replie sur le chemin de base).

Honnêteté des Runs (ADR 0023/0052) : un run `fail` n'est PAS un trou — l'historique
machine ne porte que les succès (un run complet en émet une entrée), les échecs
sont consignés en prose dans `bench/lima/RESULTS.md`. Ce module ne FABRIQUE ni ne
RÉÉCRIT aucun run ; l'append d'une entrée reste un geste du BANC (historiquement
`metro_record_run` ; ce bash a été retiré, ADR 0101 — l'auto-consignation Python
est un STUB à câbler, cf. `record` de `path.py` ; aujourd'hui l'append se fait par
commit `chore(bench)`). Aucune métrique n'est produite ici (P6) — seules celles
déjà consignées sont relues.

Pur (hors `load_runs` qui lit un fichier passé en argument). La parité Python↔bash
des verdicts de fraîcheur (ex-`metrology.sh`) est figée par tests/test_history.py.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

# Seuils de fraîcheur par chemin nommé (jours) — MÊMES valeurs que
# metro_seuil_for_target (metrology.sh, ADR 0045 §6). Un chemin inconnu retombe
# sur le défaut global (SEUIL_JOURS ou 7).
SEUILS_DEFAUT = {"atlas": 7, "storage-real": 30, "cluster-dataops": 90}
SEUIL_GLOBAL_DEFAUT = 7

# Synonymes d'identité de stack (ADR 0102 volet B) : le `stack_id` est DÉSORMAIS le nom de
# FICHIER de la topologie (`ceph`), mais des runs ANTÉRIEURS au renommage ont été keyés par
# la CLASSE de topo alors portée par `catalog.topology` (`multi-node-3`). Réconciliation en
# LECTURE UNIQUEMENT : on NE réécrit JAMAIS runs-history.yaml (honnêteté des Runs, ADR 0052) ;
# on élargit la CORRESPONDANCE de lecture. Table FERMÉE et explicite (pas de dérivation floue) :
# {stack_id: (anciennes clés d'historique équivalentes, …)}. `ceph.example.yaml`/`ceph.yaml`
# portent `topology: multi-node-3` → les 9 runs `multi-node-3` restent visibles pour `ceph`.
# Les stacks dont le nom de fichier == l'ancien `catalog.topology` (banc, dirqual) n'ont pas
# besoin d'alias (correspondance directe).
STACK_ID_ALIASES: dict[str, tuple[str, ...]] = {"ceph": ("multi-node-3",)}


def _matches_stack(run_topologie: str | None, stack: str) -> bool:
    """Un run appartient-il à la stack `stack` ? Match sur le `stack_id` (nom de fichier)
    OU sur l'une de ses clés d'historique héritées (`STACK_ID_ALIASES`, ADR 0102 volet B).
    Réconcilie les runs consignés avant le renommage SANS réécrire l'historique (ADR 0052)."""
    if run_topologie is None:
        return False
    return run_topologie == stack or run_topologie in STACK_ID_ALIASES.get(stack, ())


@dataclass
class Run:
    """Une entrée de runs-history.yaml. `target` (chemin nommé) et `metriques`
    sont optionnels (rétrocompat : les premières entrées n'en ont pas)."""

    id: str
    date: str  # ISO 8601 UTC
    profil: str | None = None
    topologie: str | None = None
    branche: str | None = None
    commit: str | None = None
    target: str | None = None
    arch: str | None = None
    hote: str | None = None
    total_s: int | None = None
    phases: dict[str, Any] = field(default_factory=dict)
    metriques: dict[str, Any] = field(default_factory=dict)

    @property
    def objectif(self) -> str:
        """Objectif d'infra lisible (exig. 11) : `profil` sur `topologie`."""
        prof = self.profil or "?"
        topo = self.topologie or "?"
        return f"{prof} / {topo}"


def _iso_str(value: Any) -> str:
    """Forme ISO 8601 `…Z` d'un datetime (désérialisé par yaml). Repli `str()`."""
    if isinstance(value, dt.datetime):
        base = value if value.tzinfo else value.replace(tzinfo=dt.UTC)
        return base.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def load_runs(path: str) -> list[Run]:
    """Charge les runs depuis un runs-history.yaml (read-only, ordre du fichier).

    Tolère les champs optionnels absents (rétrocompat). Un fichier sans `runs:`
    (ou vide) donne une liste vide — pas une erreur (un banc neuf n'a pas d'historique).
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "runs" not in data or not data["runs"]:
        return []
    runs: list[Run] = []
    for raw in data["runs"]:
        # yaml.safe_load peut désérialiser `date:` en datetime ; on garde la forme
        # brute pour l'affichage mais _parse_iso_epoch accepte les deux.
        raw_date = raw.get("date", "")
        runs.append(
            Run(
                id=raw.get("id", "?"),
                date=raw_date if isinstance(raw_date, str) else _iso_str(raw_date),
                profil=raw.get("profil"),
                topologie=raw.get("topologie"),
                branche=raw.get("branche"),
                commit=raw.get("commit"),
                target=raw.get("target"),
                arch=raw.get("arch"),
                hote=raw.get("hote"),
                total_s=raw.get("total_s"),
                phases=raw.get("phases") or {},
                metriques=raw.get("metriques") or {},
            )
        )
    return runs


def _base_target(target: str | None) -> str | None:
    """Replie le suffixe `+hardening` sur le chemin de base (#244) : pour la
    fraîcheur, `atlas+hardening` compte comme `atlas`."""
    if target is None:
        return None
    return target.split("+", 1)[0]


def seuil_for_target(target: str | None) -> int:
    """Seuil de fraîcheur (jours) d'un chemin nommé — parité metro_seuil_for_target.

    Surcharge `SEUIL_<CHEMIN>` (majuscules, `-`→`_`) prioritaire ; sinon les
    défauts ADR 0045 §6 ; sinon le défaut global (`SEUIL_JOURS` ou 7).
    """
    base = _base_target(target)
    if base is not None:
        # Dérivation identique à `tr 'a-z-' 'A-Z_'` : majuscules + tirets → underscores.
        env_var = "SEUIL_" + base.upper().replace("-", "_")
        override = os.environ.get(env_var)
        if override:
            return int(override)
        if base in SEUILS_DEFAUT:
            return SEUILS_DEFAUT[base]
    return int(os.environ.get("SEUIL_JOURS", SEUIL_GLOBAL_DEFAUT))


def age_days(past_epoch: int, now_epoch: int) -> int:
    """Jours entiers entre deux epochs — parité metro_age_days (floor, borné à 0)."""
    diff = (now_epoch - past_epoch) // 86400
    return max(diff, 0)


def freshness_verdict(age: int, seuil: int) -> str:
    """`frais` si age <= seuil, sinon `perime` — parité metro_freshness_verdict."""
    return "frais" if age <= seuil else "perime"


def _parse_iso_epoch(iso: str) -> int | None:
    """Epoch (s) d'une date ISO 8601 UTC (`…Z`). None si illisible.

    `yaml.safe_load` désérialise un timestamp ISO en `datetime` ; on accepte donc
    aussi bien une chaîne brute qu'un objet date/datetime (tolérance de schéma).
    """
    if not iso:
        return None
    if isinstance(iso, dt.datetime):
        if iso.tzinfo is None:
            iso = iso.replace(tzinfo=dt.UTC)
        return int(iso.timestamp())
    try:
        cleaned = str(iso).replace("Z", "+00:00")
        return int(dt.datetime.fromisoformat(cleaned).timestamp())
    except ValueError:
        return None


def last_run_for_target(runs: list[Run], target: str) -> Run | None:
    """Dernier run d'un chemin nommé (replie `+hardening`). None si aucun.

    Si AUCUN run ne porte de champ `target` (entrées antérieures au schéma), on
    ne filtre pas par chemin : la fonction renvoie None (le chemin est inconnu de
    l'historique). L'historique global se lit alors via le dernier run tout court.
    """
    want = _base_target(target)
    match = None
    for run in runs:
        if _base_target(run.target) == want and run.date:
            match = run  # fichier chronologique → le dernier retenu est le plus récent
    return match


def last_run_for_topology(runs: list[Run], topologie: str) -> Run | None:
    """Dernier run de CETTE stack (match sur le `stack_id` OU ses alias d'historique). None
    si aucun.

    Contrairement à `last_run_for_target` (match par chemin nommé), on match sur l'IDENTITÉ
    de la stack (`stack_id` = nom de fichier, ADR 0102 volet B) — deux stacks dérivant le
    même chemin ne partagent PAS leur verdict. `_matches_stack` réconcilie les runs keyés par
    l'ancien `catalog.topology` via `STACK_ID_ALIASES` (jamais de réécriture, ADR 0052). Aucune
    retombée sur le dernier run global : une stack jamais montée (aucun run à son nom ni alias)
    renvoie None (→ tout est à jouer), pas le run d'une autre topologie. C'est ce que `preview`
    exige pour ne pas mentir (status: cible)."""
    match = None
    for run in runs:
        if _matches_stack(run.topologie, topologie) and run.date:
            match = run  # fichier chronologique → le dernier retenu est le plus récent
    return match


def latest_run(runs: list[Run]) -> Run | None:
    """Dernier run daté du fichier (le plus récent), tous chemins confondus."""
    dated = [r for r in runs if r.date]
    return dated[-1] if dated else None


def verdict_for_run(run: Run | None, target: str | None, now_epoch: int) -> tuple[str, str]:
    """(état, message) de fraîcheur d'un run. État ∈ {frais, perime, jamais}.

    `jamais` : aucun run (chemin sans preuve). Le message porte l'objectif d'infra
    et l'âge — la suggestion « ce chemin n'a pas de run frais » nourrit le « que
    faire ensuite » (exig. 10), en TEXTE informatif : aucune action déclenchée
    (lancer = P5).
    """
    seuil = seuil_for_target(target)
    label = target or "global"
    if run is None:
        return "jamais", f"{label} : aucun run consigné → ce chemin n'a pas de run frais"
    epoch = _parse_iso_epoch(run.date)
    if epoch is None:
        return "jamais", f"{label} : date illisible ({run.date!r})"
    age = age_days(epoch, now_epoch)
    etat = freshness_verdict(age, seuil)
    detail = f"{run.objectif}, commit {run.commit or '?'}, il y a {age} j"
    compare = f"≤ {seuil} j" if etat == "frais" else f"> {seuil} j"
    suffixe = "" if etat == "frais" else " → ce chemin n'a pas de run frais"
    return etat, f"{label} : {etat} (run {run.date}, {detail} {compare}){suffixe}"


# ── Verdict de fraîcheur BLOQUANT par chemin (ex-check-freshness.sh, ADR 0042/0045) ──
# Chemins surveillés par le cron de fraîcheur : OBLIGATOIRES (un périmé → échec
# global) et OPTIONNELS (warn-only). Mêmes chemins/cadences que check-freshness.sh.
FRESHNESS_OBLIGATOIRES = ("atlas", "storage-real")
FRESHNESS_OPTIONNELS = ("cluster-dataops",)


def date_from_log_name(filename: str) -> str | None:
    """Date ISO (`YYYY-MM-DDT00:00:00Z`) extraite d'un nom de log `runs/<date>-*.log`,
    ou None si le préfixe n'est pas une date. Pur — repli ADR 0042 §4 quand
    l'historique YAML est absent (le mtime du checkout CI n'est pas fiable)."""
    base = os.path.basename(filename)
    if len(base) < 10:
        return None
    prefix = base[:10]
    try:
        dt.date.fromisoformat(prefix)
    except ValueError:
        return None
    return f"{prefix}T00:00:00Z"


def path_freshness(run: Run | None, target: str, now_epoch: int) -> tuple[str, str]:
    """(état, ligne de rapport) de fraîcheur d'UN chemin surveillé — parité
    `evaluer_chemin` de check-freshness.sh. État ∈ {frais, perime, absent}.

    Pur : l'appelant fournit le `run` (dernier du chemin) déjà sélectionné. La ligne
    de rapport reprend le format à puces du script (✓/✗/•) pour la sortie CI."""
    seuil = seuil_for_target(target)
    if run is None or not run.date:
        return "absent", f"  • {target} : aucun run consigné (seuil {seuil} j)"
    epoch = _parse_iso_epoch(run.date)
    if epoch is None:
        return "absent", f"  • {target} : date illisible ({run.date!r})"
    age = age_days(epoch, now_epoch)
    if freshness_verdict(age, seuil) == "frais":
        return "frais", f"  ✓ {target} : {age} j ≤ {seuil} j ({run.date})"
    return "perime", f"  ✗ {target} : {age} j > {seuil} j — PÉRIMÉ ({run.date})"
