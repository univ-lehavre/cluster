#!/usr/bin/env python3
"""Façade CLI/CI de l'outil déclaratif des topologies (ADR 0056 §2, palier P3).

Le paquet `cluster_topology/` porte la LOGIQUE PURE (chargement, validation,
dérivation, rendu byte-identique) ; ce script n'est qu'une FAÇADE FINE par-dessus :
il lit `argv`, appelle la surface publique du paquet, formate la sortie et mappe
les exceptions en codes de sortie. Aucune logique de dérivation nouvelle ici
(ADR 0017 : la logique testable vit dans le paquet, pas dans l'entrée d'exécution).

Read-only / sans état (frontière de palier) : on GÉNÈRE des artefacts et on
CONSTATE un état, on ne CONVERGE jamais. `generate` n'exécute aucun play ;
Ansible reste le seul moteur idempotent (ADR 0056 §7). Lancer un playbook via
`ansible-runner`, suggérer « la prochaine étape », lire l'historique des runs,
exposer des métriques → paliers P4/P5/P6, hors de cette façade.

argparse stdlib (sous-parsers) plutôt que typer/click : « pas de dépendance avant
le besoin » (model.py / ADR 0049 — lisibilité néophyte, coût de diversité). Quatre
sous-commandes triviales n'en justifient aucune ; l'ADR 0056 §2 cite « typer/click »
comme illustration de style, pas comme exigence d'outillage.

Usage :
  uv run python scripts/topology.py validate [-f topology.yaml]
  uv run python scripts/topology.py generate [--kind prod|lima] [--what inventory|run-params]
  uv run python scripts/topology.py status [--real [--hosts cp1 node1]]
  uv run python scripts/topology.py diff [--kind prod|lima --against PATH]
  uv run python scripts/topology.py epreuves [--all] [--type unit|intég|chaos]   (P4)
  uv run python scripts/topology.py runs [--target atlas|storage-real|…]          (P4)

P4 ajoute deux commandes READ-ONLY : `epreuves` (liste filtrée par la topologie,
exig. 6 — ne lance rien) et `runs` (lit l'historique + fraîcheur, exig. 10-12 —
ne réécrit rien). Lancer une épreuve ou converger relève de P5 (ansible-runner).

Codes de sortie (contrat CI) : 0 = succès / invariant tenu / lecture ; 1 = erreur
métier (topology invalide ou introuvable, dérive byte-identique détectée) ; 2 =
usage (flag manquant, référence absente, destination `-o` invalide). `runs` rend
TOUJOURS 0 (lecture informative ; le verdict bloquant CI reste check-freshness.sh).
Pour `status --real`, on PROPAGE le code de bootstrap/state.sh (0 conforme /
1 drift / 2 aucun hôte joignable — mêmes codes).

La logique de mapping exception→code est testée par tests/test_topology_cli.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml  # noqa: E402

from cluster_topology import (  # noqa: E402
    TopologyError,
    derive_run_params,
    filter_epreuves,
    load_runs,
    load_topology,
    render_lima_inventory,
    render_prod_inventory,
    verdict_for_run,
)
from cluster_topology.history import last_run_for_target, latest_run  # noqa: E402

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_DEFAULT_TOPOLOGY = os.path.join(_ROOT, "topology.yaml")
_EXAMPLE_TOPOLOGY = os.path.join(_ROOT, "topology.example.yaml")
_PROD_INVENTORY = os.path.join(_ROOT, "bootstrap", "hosts.example.yaml")
_STATE_SH = os.path.join(_ROOT, "bootstrap", "state.sh")
_RUNS_HISTORY = os.path.join(_ROOT, "test", "lima", "runs-history.yaml")
# Chemins nommés connus de l'historique (ADR 0045 §6) pour le verdict par chemin.
_CHEMINS_NOMMES = ["atlas", "storage-real", "cluster-dataops"]


def _resolve(path: str | None) -> str:
    """Chemin du topology.yaml à charger.

    Source de vérité : `topology.yaml` (config locale gitignorée, ADR 0023). En
    son absence on retombe sur `topology.example.yaml` (exemple générique
    versionné) AVEC un avis explicite sur stderr — sinon un opérateur croirait
    générer depuis sa topo réelle et obtiendrait l'exemple.
    """
    if path is not None:
        return path
    if os.path.exists(_DEFAULT_TOPOLOGY):
        return _DEFAULT_TOPOLOGY
    print(
        "topology.yaml absent — utilisation de topology.example.yaml "
        "(exemple générique versionné, ADR 0023).",
        file=sys.stderr,
    )
    return _EXAMPLE_TOPOLOGY


def _render_inventory(topo, kind: str, lima_home: str | None) -> str:
    """Rend l'inventaire selon le `kind` (prod ou lima). Façade sur le paquet."""
    if kind == "lima":
        if not lima_home:
            raise _UsageError("--kind lima exige --lima-home (chemin du $HOME du poste)")
        return render_lima_inventory(topo, lima_home)
    return render_prod_inventory(topo)


class _UsageError(Exception):
    """Erreur d'usage → code de sortie 2 (mauvais flags, référence absente)."""


# ── Sous-commandes (chacune renvoie un code de sortie) ──────────────────────


def cmd_validate(args: argparse.Namespace) -> int:
    """Charge + valide topology.yaml et force la dérivation backend/profil.

    Porte d'entrée CI du contrat : tout verdict de schéma (rôle inconnu,
    HA-sans-VIP, backend/profil inconnu) est levé par le paquet (TopologyError)
    avec un message déjà rédigé en clair. Verdict au premier échec.
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    # Forcer la dérivation : un backend/profil inconnu n'échoue qu'ici.
    derive_run_params(topo)
    print(
        f"{os.path.relpath(path, _ROOT)} valide "
        f"({len(topo.control_nodes)} control / {len(topo.worker_nodes)} worker, "
        f"kind={topo.target_kind})."
    )
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Dérive l'artefact voulu et l'écrit (stdout ou -o). Ne lance aucun play.

    Un `-o` vers un répertoire absent est une erreur d'USAGE (code 2 :
    destination invalide fournie en argument), pas une erreur métier — on la
    distingue du chargement de topology.yaml (code 1).
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    kind = args.kind or topo.target_kind
    if args.what == "run-params":
        out = yaml.safe_dump(derive_run_params(topo), sort_keys=True, allow_unicode=True)
    else:
        out = _render_inventory(topo, kind, args.lima_home)
    if not args.output:
        sys.stdout.write(out)
        return 0
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    except OSError as exc:
        raise _UsageError(f"écriture impossible vers {args.output} : {exc}") from exc
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Vérifie l'invariant byte-identique (P1) : régénéré vs versionné.

    Garde-fou CI anti-dérive. Codes : 0 si identique (stdout vide) ; 1 si dérive
    (émet un diff unifié) ; 2 (usage) si la référence est absente OU si
    `--kind lima` est demandé sans `--against`/`--lima-home`. DÉCRIT la
    différence ; ne propose AUCUNE action de convergence (frontière P5).
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    kind = args.kind or topo.target_kind
    against = args.against
    if against is None:
        if kind != "prod":
            raise _UsageError(
                "--kind lima exige --against (l'inventaire Lima est un artefact de "
                "run, jamais versionné — aucun golden par défaut)"
            )
        against = _PROD_INVENTORY
    # Lecture en un seul appel : une référence absente (y compris disparue après
    # un check, TOCTOU) est TOUJOURS une erreur d'usage (code 2), jamais 1.
    try:
        with open(against, encoding="utf-8") as f:
            expected = f.read()
    except FileNotFoundError as exc:
        raise _UsageError(f"fichier de référence absent : {against}") from exc
    generated = _render_inventory(topo, kind, args.lima_home)
    if generated == expected:
        return 0
    rel = os.path.relpath(against, _ROOT)
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile=f"{rel} (versionné)",
        tofile="généré (topology)",
    )
    sys.stdout.writelines(diff)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    """État VOULU (lu depuis topology.yaml) ; --real délègue l'état réel à state.sh.

    Sans --real : résumé de l'intention (nœuds, HA, backend, profil, exposition,
    kind). Avec --real : subprocess vers bootstrap/state.sh (lecture seule, on ne
    le réimplémente pas) en héritant l'environnement (EXPECT_CLUSTER/SSH_OPTS) ;
    on ré-émet sa sortie et on PROPAGE son code (0/1/2 déjà alignés).
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    lines = [
        f"topologie       : {topo.catalog.get('topology', '—')} (kind={topo.target_kind})",
        f"control-planes  : {', '.join(topo.control_nodes) or '—'}"
        f"{'  [HA → VIP requise]' if topo.is_ha_control_plane else ''}",
        f"workers         : {', '.join(topo.worker_nodes) or '—'}",
        f"profil          : {topo.catalog.get('profile', 'base')}",
        f"stockage        : {topo.storage.get('backend', 'local-path')}",
        f"exposition      : {topo.exposition.get('mode', '—')}",
    ]
    print("\n".join(lines))
    if not args.real:
        return 0
    # État réel : déléguer à state.sh (SSH+kubectl). Hérite l'env du shell.
    # shell=False : args.hosts est passé LITTÉRALEMENT à bash (pas d'expansion
    # shell), donc pas d'injection même si --hosts vient de la ligne de commande.
    cmd = ["bash", _STATE_SH, *(args.hosts or [])]
    completed = subprocess.run(cmd, check=False)  # noqa: S603 — shell=False, args littéraux
    return completed.returncode


def cmd_epreuves(args: argparse.Namespace) -> int:
    """Liste les épreuves JOUABLES filtrées par la topologie (exig. 6). Ne LANCE rien.

    Filtre sur l'INTENTION déclarée (profil, backend, nœuds, target_kind) ; un
    scénario « jouable » peut encore être skip au lancement selon l'état réel du
    cluster (vérifié en P5). `--all` montre aussi les exclues avec leur raison.
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    jouables, exclues = filter_epreuves(topo)
    if args.type:
        jouables = [e for e in jouables if e.type == args.type]
    print(f"Épreuves jouables ({len(jouables)}) — filtrées par la topologie déclarée :")
    for e in jouables:
        print(f"  {e.num} [{e.type:<5}] {e.categorie:<13} {e.nom}")
    print("  (jouable selon la topologie ; l'état réel est vérifié au lancement, P5)")
    if args.all:
        print(f"\nÉpreuves exclues ({len(exclues)}) :")
        for e, raison in exclues:
            print(f"  {e.num} [{e.type:<5}] {e.nom} — {raison}")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    """LIT runs-history.yaml et imprime, par chemin nommé, fraîcheur + objectif d'infra.

    Read-only (exig. 10-11) : ne réécrit jamais l'historique (honnêteté des Runs,
    ADR 0023). Code 0 TOUJOURS — informatif ; le verdict BLOQUANT de CI reste
    l'apanage de check-freshness.sh (non dupliqué). La suggestion « pas de run
    frais » est du TEXTE : aucune action déclenchée (lancer = P5).
    """
    history = args.history or _RUNS_HISTORY
    runs = load_runs(history)
    now = int(dt.datetime.now(tz=dt.UTC).timestamp())
    if args.target:
        run = last_run_for_target(runs, args.target)
        # Repli : si aucune entrée ne porte de `target` (historique antérieur au
        # champ), on rapporte l'état global avec un avis explicite.
        if run is None and not any(r.target for r in runs):
            _, msg = verdict_for_run(latest_run(runs), None, now)
            print(f"(aucune entrée ne porte de chemin `target` — état global)\n{msg}")
            return 0
        _, msg = verdict_for_run(run, args.target, now)
        print(msg)
        return 0
    print(f"Historique : {len(runs)} run(s) consigné(s) dans {os.path.relpath(history, _ROOT)}")
    any_target = any(r.target for r in runs)
    if any_target:
        for chemin in _CHEMINS_NOMMES:
            _, msg = verdict_for_run(last_run_for_target(runs, chemin), chemin, now)
            print(f"  {msg}")
    else:
        # Historique sans chemins nommés : verdict global sur le dernier run.
        _, msg = verdict_for_run(latest_run(runs), None, now)
        print(f"  {msg}")
        print("  (les entrées ne portent pas encore de chemin `target` — verdict global)")
    return 0


_DISPATCH = {
    "validate": cmd_validate,
    "generate": cmd_generate,
    "diff": cmd_diff,
    "status": cmd_status,
    "epreuves": cmd_epreuves,
    "runs": cmd_runs,
}


def _run(args: argparse.Namespace) -> int:
    """Exécute la sous-commande en mappant les exceptions métier en codes.

    TopologyError / fichier introuvable → 1 (erreur métier) ; _UsageError → 2
    (mauvais usage). Centralisé ici pour que chaque cmd_* reste une façade nue.
    """
    try:
        return _DISPATCH[args.cmd](args)
    except _UsageError as exc:
        print(f"erreur d'usage : {exc}", file=sys.stderr)
        return 2
    except (TopologyError, FileNotFoundError, OSError) as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="topology",
        description="Façade CLI/CI de l'outil déclaratif des topologies (ADR 0056, P3-P4).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _add_file(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-f",
            "--file",
            default=None,
            help="chemin du topology.yaml (défaut : topology.yaml, sinon topology.example.yaml)",
        )
        # --no-input accepté partout (uniformité CI) ; sans interactivité, no-op.
        p.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")

    p_val = sub.add_parser("validate", help="valide le schéma de topology.yaml")
    _add_file(p_val)

    p_gen = sub.add_parser("generate", help="dérive un artefact (inventaire ou run-params)")
    _add_file(p_gen)
    p_gen.add_argument(
        "--kind",
        choices=["prod", "lima"],
        default=None,
        help="cible (défaut : target_kind du fichier)",
    )
    p_gen.add_argument(
        "--what",
        choices=["inventory", "run-params"],
        default="inventory",
        help="artefact à générer (défaut : inventory)",
    )
    p_gen.add_argument(
        "--lima-home",
        default=os.environ.get("HOME"),
        help="$HOME du poste (chemin SSH Lima ; requis si --kind lima)",
    )
    p_gen.add_argument("-o", "--output", default=None, help="fichier de sortie (défaut : stdout)")

    p_diff = sub.add_parser("diff", help="vérifie l'invariant byte-identique (code 1 si dérive)")
    _add_file(p_diff)
    p_diff.add_argument(
        "--kind",
        choices=["prod", "lima"],
        default=None,
        help="cible (défaut : target_kind du fichier)",
    )
    p_diff.add_argument(
        "--against",
        default=None,
        help="fichier de référence (défaut prod : bootstrap/hosts.example.yaml)",
    )
    p_diff.add_argument(
        "--lima-home", default=os.environ.get("HOME"), help="$HOME du poste (si --kind lima)"
    )

    p_sta = sub.add_parser("status", help="état voulu (et --real → state.sh)")
    _add_file(p_sta)
    p_sta.add_argument(
        "--real",
        action="store_true",
        help="constater l'état réel via bootstrap/state.sh (SSH+kubectl)",
    )
    p_sta.add_argument(
        "--hosts", nargs="*", default=None, help="hôtes passés à state.sh (défaut : tous)"
    )

    p_epr = sub.add_parser("epreuves", help="liste les épreuves jouables filtrées par la topologie")
    _add_file(p_epr)
    p_epr.add_argument("--all", action="store_true", help="montrer aussi les exclues + la raison")
    p_epr.add_argument(
        "--type", choices=["unit", "intég", "chaos"], default=None, help="filtrer par type"
    )

    p_runs = sub.add_parser("runs", help="lit l'historique des runs + verdict de fraîcheur")
    p_runs.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")
    p_runs.add_argument("--target", default=None, help="chemin nommé ciblé (atlas, storage-real…)")
    p_runs.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : test/lima/)"
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
