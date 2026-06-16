#!/usr/bin/env python3
"""Façade CLI/CI de l'outil déclaratif des topologies (ADR 0056 §2, palier P3).

Le paquet `nestor/` porte la LOGIQUE PURE (chargement, validation,
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

Usage — gestion des stacks (catalogue, calque `pulumi stack`) :
  uv run python scripts/topology.py stack new <nom> [--activate] [--no-input]
  uv run python scripts/topology.py stack ls
  uv run python scripts/topology.py stack select <nom>
  uv run python scripts/topology.py stack validate [-f topology.yaml]
Usage — cycle de vie (top-level, calque Pulumi) :
  uv run python scripts/topology.py preview [--target …]      (voir : VOULU+RÉEL+PLAN)
  uv run python scripts/topology.py up [--yes]               (monter TOUTE la séquence)
  uv run python scripts/topology.py next [--target …]        (appliquer la couche suivante)
  uv run python scripts/topology.py destroy [--yes]          (calque pulumi destroy)
Usage — artefacts (dériver/constater, groupe `artifact`) :
  uv run python scripts/topology.py artifact generate [--kind prod|lima] [--what …]
  uv run python scripts/topology.py artifact diff [--kind prod|lima --against PATH]
  uv run python scripts/topology.py artifact runs [--target atlas|…]               (P4)
  uv run python scripts/topology.py artifact metrics [--last]                       (P6)
Usage — épreuves & réversibilité (groupe `test`) :
  uv run python scripts/topology.py test scenarios [--all] [--type unit|intég|chaos] (P4)
  uv run python scripts/topology.py test smoke [--namespace …]                       (P6)
  uv run python scripts/topology.py test roundtrip --phase monitoring|gitops|…       (P6+)

P4 ajoute deux commandes READ-ONLY : `test scenarios` (liste filtrée par la
topologie, exig. 6 — ne lance rien) et `artifact runs` (lit l'historique +
fraîcheur, exig. 10-12 — ne réécrit rien). P5 : `preview` MONTRE le plan complet
(VOULU+RÉEL+PLAN, read-only) et `up` l'APPLIQUE — la 1re couche manquante via
ansible-runner ; lancer `up` EST la décision humaine (jamais d'auto-enchaînement,
ADR 0063). P6 ajoute `artifact metrics` (expose les métriques DÉJÀ consignées,
exig. 8 — ne mesure rien de neuf)
et `smoke` (test de réversibilité créer→vérifier→détruire sur un cluster vivant,
exig. 7 — couche kubernetes isolée, code 1 si non réversible). `roundtrip`
généralise `smoke` à une COUCHE entière (détruire→vérifier→reconstruire→vérifier),
en déléguant la dérivation du périmètre à run-phases.sh/rollback-lib (ADR 0054).

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
import contextlib
import datetime as dt
import difflib
import glob
import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml  # noqa: E402

from nestor import (  # noqa: E402
    QUESTION_LB_MODE,
    QUESTIONS,
    PlanError,
    ScaffoldError,
    Topology,
    TopologyError,
    build_topology_dict,
    catalog_entry,
    classify_refresh,
    consumes_storage,
    default_target,
    derive_run_params,
    diff_phases,
    expected_phase_sequence,
    filter_epreuves,
    format_metrics,
    installable_now,
    load_runs,
    load_topology,
    metrics_of,
    observed_done_phases,
    phase_deps,
    phase_label,
    phase_playbook,
    plan_init,
    render_lima_inventory,
    render_prod_inventory,
    resolve_layers,
    suggest_next,
    verdict_for_run,
)
from nestor import bootstrap as _bootstrap  # noqa: E402
from nestor import discover as _discover  # noqa: E402
from nestor import ha as _ha  # noqa: E402
from nestor import isolation as _isolation  # noqa: E402
from nestor import refresh_fuse as _refresh_fuse  # noqa: E402
from nestor import refresh_plan as _refresh_plan  # noqa: E402
from nestor import roundtrip as _roundtrip  # noqa: E402
from nestor import runner as _runner  # noqa: E402
from nestor import scale as _scale  # noqa: E402
from nestor import smoke as _smoke  # noqa: E402
from nestor.history import (  # noqa: E402
    last_run_for_target,
    last_run_for_topology,
    latest_run,
)

_ROOT = os.path.join(os.path.dirname(__file__), "..")
# Catalogue de topologies (ADR 0056 + 0023) : `topologies/` versionne les modèles
# génériques `*.example.yaml` et abrite les topologies réelles gitignorées ;
# `topology.yaml` (racine) est un SYMLINK gitignoré vers l'entrée activée.
_CATALOG_DIR = os.path.join(_ROOT, "topologies")
_DEFAULT_TOPOLOGY = os.path.join(_ROOT, "topology.yaml")
_EXAMPLE_TOPOLOGY = os.path.join(_CATALOG_DIR, "socle.example.yaml")
_PROD_INVENTORY = os.path.join(_ROOT, "bootstrap", "hosts.example.yaml")
_RUNS_HISTORY = os.path.join(_ROOT, "bench", "lima", "runs-history.yaml")
# Kubeconfig du banc Lima, écrit par run-phases.sh (KUBECONFIG_LOCAL = WORKDIR/kubeconfig).
# `preview` lit l'état RÉEL du cluster via kubectl ; sans KUBECONFIG exporté, il retombe
# ICI (sinon il interroge ~/.kube/config — pas le banc — et voit 0 nœud Ready alors que
# le socle est monté : faux « à installer », scorie de fidélité du RÉEL).
_BENCH_KUBECONFIG = os.path.join(_ROOT, "bench", "lima", ".work", "kubeconfig")
# Inventaire Ansible du BANC Lima, écrit par run-phases.sh (write_inventory → WORKDIR/
# inventory.yaml ; target_kind: lima, hôtes node1/node2). DISTINCT de bootstrap/hosts.yaml
# (l'inventaire PROD). `next` doit viser CELUI-CI pour une topo lima — sinon un montage
# banc SSH sur la prod (faille ADR 0053). Choisi par `_inventory_for(topo)`.
_BENCH_INVENTORY = os.path.join(_ROOT, "bench", "lima", ".work", "inventory.yaml")
# Borne l'attente du scan réel (preview/up) sur limactl/kubectl : un cluster injoignable ou
# un démon Lima bloqué ne doit JAMAIS figer le refresh (leçon du timeout ha._vm_exec).
_REFRESH_TIMEOUT_S = 8


def _warn(message: str) -> None:
    """Avertissement sur STDERR, en JAUNE GRAS si stderr est un terminal (sinon brut,
    pour ne pas polluer pipes/CI). Même convention que `warn()` de bench/lima/lib.sh."""
    if sys.stderr.isatty():
        print(f"\033[1;33m⚠ {message}\033[0m", file=sys.stderr)
    else:
        print(f"⚠ {message}", file=sys.stderr)


def _bench_kubeconfig() -> str:
    """Le kubeconfig que `cluster` doit RÉELLEMENT utiliser, par priorité (ADR 0053) :

    1. `KUBECONFIG` exporté → intention EXPLICITE de l'opérateur (respectée) ;
    2. le banc Lima s'il existe → la cible nominale de l'outil ;
    3. sinon → `/dev/null` (kubeconfig VIDE), JAMAIS `~/.kube/config`.

    Le point (3) est le correctif de fond : `cluster` est un outil de BANC ; sans
    banc ni intention explicite, il ne doit PAS retomber silencieusement sur le
    contexte du poste (= la prod). Pointer `/dev/null` fait échouer kubectl
    proprement → les lectures renvoient « vide » (honnête : pas de banc), au lieu de
    lire/muter la prod par accident."""
    explicit = os.environ.get("KUBECONFIG")
    if explicit:
        return explicit
    if os.path.exists(_BENCH_KUBECONFIG):
        return _BENCH_KUBECONFIG
    return os.devnull  # vide : kubectl échoue → "pas de banc", jamais la prod


def _kubectl_env() -> dict[str, str]:
    """Env pour un appel kubectl du banc : force KUBECONFIG vers la cible sûre
    (`_bench_kubeconfig`) — jamais le ~/.kube/config implicite de la prod."""
    return {**os.environ, "KUBECONFIG": _bench_kubeconfig()}


def _kubeconfig_reaches_api(kubeconfig: str) -> bool:
    """`True` si ce kubeconfig joint RÉELLEMENT l'API (pas juste un fichier présent).

    Un kubeconfig peut exister mais être vide/cassé (server absent) ou pointer une API
    tombée (forward mort) → kubectl retombe sur localhost. On sonde `/healthz` borné.
    Read-only, FAIL-CLOSED : toute erreur → False."""
    try:
        out = subprocess.run(  # noqa: S603 — argv fixe, lecture seule
            ["kubectl", "get", "--raw=/healthz", "--request-timeout=4s"],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "KUBECONFIG": kubeconfig},
            timeout=_REFRESH_TIMEOUT_S,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and out.stdout.strip() == "ok"


# Chemins nommés connus de l'historique (ADR 0045 §6) pour le verdict par chemin.
_CHEMINS_NOMMES = ["atlas", "storage-real", "cluster-dataops"]


def _resolve(path: str | None) -> str:
    """Chemin du topology.yaml à charger.

    Source de vérité : `topology.yaml` (config locale gitignorée, ADR 0023), un
    SYMLINK vers l'entrée activée du catalogue `topologies/<x>` — le repointer
    active une autre topologie. Le catalogue `topologies/` versionne les modèles
    génériques `*.example.yaml` et abrite les topologies réelles gitignorées.
    En l'absence du symlink on retombe sur `topologies/socle.example.yaml`
    (exemple générique versionné) AVEC un avis explicite sur stderr — sinon un
    opérateur croirait générer depuis sa topo réelle et obtiendrait l'exemple.
    """
    if path is not None:
        return path
    if os.path.exists(_DEFAULT_TOPOLOGY):
        return _DEFAULT_TOPOLOGY
    print(
        "topology.yaml absent — utilisation de topologies/socle.example.yaml "
        "(exemple générique versionné, ADR 0023).",
        file=sys.stderr,
    )
    return _EXAMPLE_TOPOLOGY


def _active_stack_name(file_arg: str | None) -> str | None:
    """Nom de la stack ciblée pour les artefacts d'historique (`runs`/`metrics`).

    `-f` explicite → la topo donnée ; sinon la stack active (`topology.yaml`). On NE
    retombe PAS sur l'exemple silencieusement : si aucune stack n'est activée, renvoie
    None (l'appelant bascule sur la vue globale). Toute erreur de lecture → None
    (informatif, jamais bloquant — `runs`/`metrics` sont read-only, code 0)."""
    path = (
        file_arg if file_arg else (_DEFAULT_TOPOLOGY if os.path.exists(_DEFAULT_TOPOLOGY) else None)
    )
    if path is None:
        return None
    try:
        return load_topology(path).catalog.get("topology")
    except (TopologyError, FileNotFoundError, OSError):
        return None


def _render_inventory(topo, kind: str, lima_home: str | None) -> str:
    """Rend l'inventaire selon le `kind` (prod ou lima). Façade sur le paquet."""
    if kind == "lima":
        if not lima_home:
            raise _UsageError("--kind lima exige --lima-home (chemin du $HOME du poste)")
        return render_lima_inventory(topo, lima_home)
    return render_prod_inventory(topo)


def _inventory_for(topo: Topology) -> str:
    """Chemin de l'inventaire Ansible de la TOPOLOGIE active (ADR 0053).

    Le cœur de l'isolation : un montage `next` vise l'inventaire de SA cible —
    `bench/lima/.work/inventory.yaml` (target_kind: lima, généré par le banc) pour une
    topo lima, `bootstrap/hosts.yaml` (prod) sinon. Sans ça, `next` utilisait TOUJOURS
    l'inventaire prod codé en dur → un montage banc SSHait sur la prod (faille
    constatée). La garde `_assert_inventory_safe` reste le filet ; ICI on choisit
    d'emblée le BON inventaire."""
    if topo.target_kind == "lima":
        return _BENCH_INVENTORY
    return os.path.join(_ROOT, "bootstrap", "hosts.yaml")


class _UsageError(Exception):
    """Erreur d'usage → code de sortie 2 (mauvais flags, référence absente)."""


# ── Sous-commandes (chacune renvoie un code de sortie) ──────────────────────


def cmd_stack_validate(args: argparse.Namespace) -> int:
    """`stack validate` : charge + valide topology.yaml et force la dérivation backend/profil.

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


def cmd_default_target(args: argparse.Namespace) -> int:
    """Imprime le CHEMIN NOMMÉ dérivé de la topologie ACTIVE (topology.yaml).

    C'est le pont qui rend la SÉLECTION déclarative : run-phases.sh (sans
    argument) lit ce chemin et le monte, au lieu d'exiger le nom en dur. Activer
    une topologie = poser/éditer `topology.yaml` ; l'outil en dérive le chemin
    (ADR 0056). Sortie = le seul nom du chemin (consommable par `$(...)`).
    """
    topo = load_topology(_resolve(args.file))
    print(default_target(topo))
    return 0


def _ask(question, *, no_input: bool) -> str:
    """Pose UNE question de l'assistant et renvoie la réponse (ou le défaut).

    Sous `--no-input` (CI, pas de TTY) : renvoie le défaut sans prompter. Sinon :
    affiche le libellé + l'aide + les choix (avec le défaut entre crochets) ; une
    entrée vide retient le défaut ; un choix hors enum re-demande (la validation
    finale reste à build_topology_dict/load_topology, mais on guide ici)."""
    if no_input:
        return question.default
    choices = f" ({'|'.join(question.choices)})" if question.choices else ""
    suffix = f" [{question.default}]"
    while True:
        if question.help:
            print(f"  — {question.help}", file=sys.stderr)
        answer = input(f"{question.prompt}{choices}{suffix} : ").strip()
        if not answer:
            return question.default
        if question.choices and answer not in question.choices:
            print(f"    `{answer}` hors choix ; valides : {question.choices}", file=sys.stderr)
            continue
        return answer


def _confirm(prompt: str, *, default: bool, no_input: bool) -> bool:
    """Question oui/non. Sous --no-input : renvoie `default` sans prompter (CI).

    Entrée vide → défaut. Accepte o/oui/y/yes (vrai) et n/non/no (faux), insensible
    à la casse ; toute autre saisie re-demande."""
    if no_input:
        return default
    hint = "O/n" if default else "o/N"
    while True:
        answer = input(f"{prompt} [{hint}] : ").strip().lower()
        if not answer:
            return default
        if answer in ("o", "oui", "y", "yes"):
            return True
        if answer in ("n", "non", "no"):
            return False
        print("    réponds o(ui) ou n(on)", file=sys.stderr)


def _choisir_couche(
    choix: list[str], libelle: Callable[[str], str], *, no_input: bool
) -> str | None:
    """Menu numéroté quand PLUSIEURS couches sont montables (choix d'ordre, ADR 0066).

    `choix` est ordonné selon le chemin (le 1er = ordre conventionnel = DÉFAUT).
    `libelle(phase)` rend le texte humain affiché. Renvoie la phase choisie, ou None
    si l'opérateur annule (saisie vide hors défaut interdite : Entrée = défaut). Sous
    `no_input` (CI/non-TTY/--yes) : renvoie le défaut sans prompter — pas de menu
    interactif à l'aveugle."""
    if no_input:
        return choix[0]
    print("Plusieurs couches sont installables maintenant — laquelle monter ?", file=sys.stderr)
    for i, phase in enumerate(choix, 1):
        marque = "  (défaut)" if i == 1 else ""
        print(f"  {i}) {libelle(phase)}{marque}", file=sys.stderr)
    while True:
        rep = input(f"Numéro [1-{len(choix)}, défaut 1] : ").strip()
        if not rep:
            return choix[0]
        if rep.isdigit() and 1 <= int(rep) <= len(choix):
            return choix[int(rep) - 1]
        print(f"    réponds un numéro entre 1 et {len(choix)} (ou Entrée pour 1)", file=sys.stderr)


def _activate_symlink(target_rel: str) -> None:
    """Repointe le symlink d'activation topology.yaml → <target_rel> (relatif, gitignoré).

    Remplace un lien/fichier existant. Chemin RELATIF au dépôt (le symlink vit à la
    racine, à côté de topologies/) — robuste à un déplacement du clone."""
    link = os.path.join(_ROOT, "topology.yaml")
    if os.path.islink(link) or os.path.exists(link):
        os.unlink(link)
    os.symlink(target_rel, link)


def cmd_stack_new(args: argparse.Namespace) -> int:
    """`stack new <nom>` : crée une topologie (stack) dans le catalogue via un ASSISTANT.

    Verbe du groupe `stack` (on n'a pas de notion de « projet » Pulumi, donc pas de
    `new` top-level ambigu — créer une STACK, pas un projet). Pose le minimum
    décisionnel, écrit topologies/<nom>.yaml (réelle, gitignorée, ADR 0023/0056),
    puis propose de l'activer.

    Pose le MINIMUM décisionnel (profil, backend, terrain, cible, nb de CP/workers,
    + mode LB si HA) dans les enums connus, construit un YAML minimal VALIDE
    (build_topology_dict), le valide (load_topology, réutilisé), l'écrit dans
    `topologies/<nom>.yaml` (topo RÉELLE gitignorée, jamais `.example`), puis PROPOSE
    de l'activer (question en fin d'assistant ; `--activate` force le oui sans
    demander). `--no-input` retient les défauts (CI). Refuse d'écraser sans `--force`.

    Codes : 0 succès ; 1 schéma invalide (improbable, l'assistant borne les enums) ;
    2 usage (nom invalide, cible présente sans --force, modèle/écriture impossibles).
    """
    try:
        plan = plan_init(args.name, activate=args.activate)
    except ScaffoldError as exc:
        raise _UsageError(str(exc)) from exc

    target_abs = os.path.join(_ROOT, plan.target)
    if os.path.exists(target_abs) and not args.force:
        raise _UsageError(
            f"{plan.target} existe déjà — `--force` pour l'écraser (ou choisis un autre nom)"
        )

    # Assistant : on collecte les réponses du minimum, puis (si HA) le mode LB.
    print(f"Assistant de création — topologie `{plan.name}` :", file=sys.stderr)
    answers: dict[str, str] = {}
    for question in QUESTIONS:
        answers[question.key] = _ask(question, no_input=args.no_input)
    try:
        n_cp = int(answers.get("control_planes", "1"))
    except ValueError:
        n_cp = 1
    if n_cp >= 2:  # HA → le modèle exige un control_plane_lb : on demande son mode.
        answers[QUESTION_LB_MODE.key] = _ask(QUESTION_LB_MODE, no_input=args.no_input)

    try:
        data = build_topology_dict(plan.name, answers)
    except ScaffoldError as exc:
        raise _UsageError(str(exc)) from exc

    # Bandeau d'en-tête : valeurs GÉNÉRIQUES par défaut (ADR 0023) ; l'opérateur
    # remplace par ses vraies valeurs dans ce fichier gitignoré.
    header = (
        f"# topologies/{plan.name}.yaml — topologie RÉELLE (gitignorée, ADR 0023).\n"
        f"# Générée par `topology.py init` (assistant). Ajuste nœuds/rôles/IP ;\n"
        f"# `topology.py validate` revérifie le schéma. `status: cible` tant qu'aucun\n"
        f"# run ne l'a montée (honnêteté ADR 0052).\n"
    )
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    # Écrire le fichier, puis le VALIDER via load_topology (qui lit un chemin et
    # fait foi : cohérence HA↔VIP, rôles). En cas d'échec on retire le fichier pour
    # ne pas laisser un scaffold invalide dans le catalogue.
    try:
        with open(target_abs, "w", encoding="utf-8") as f:
            f.write(header + body)
    except OSError as exc:
        raise _UsageError(f"écriture impossible vers {plan.target} : {exc}") from exc

    try:
        topo = load_topology(target_abs)
    except TopologyError as exc:
        os.unlink(target_abs)  # ne pas laisser un scaffold invalide dans le catalogue
        print(f"erreur : topologie générée invalide ({exc}) — fichier retiré", file=sys.stderr)
        return 1

    print(
        f"✓ {plan.target} créée "
        f"({len(topo.control_nodes)} control / {len(topo.worker_nodes)} worker)."
    )

    # Activation : on la PROPOSE une fois la topo créée (oui par défaut) plutôt que
    # de l'exiger en flag. `--activate` force le oui sans demander ; `--no-input`
    # retient le défaut (oui que si --activate, pour rester déterministe en CI).
    if args.activate:
        activate = True
    elif args.no_input:
        activate = False
    else:
        activate = _confirm(
            f"Activer `{plan.name}` maintenant (topology.yaml → {plan.target}) ?",
            default=True,
            no_input=False,
        )

    if activate:
        _activate_symlink(plan.target)
        print(f"✓ activée : topology.yaml → {plan.target} (chemin dérivé : {default_target(topo)})")
    else:
        print(f"  pour l'activer : topology.py stack select {plan.name}")
    return 0


def cmd_stack_select(args: argparse.Namespace) -> int:
    """`stack select` : active une topologie EXISTANTE et POSE le KUBECONFIG de la cible.

    Calque `pulumi stack select` : choisit la stack courante parmi le catalogue,
    repointe le symlink `topology.yaml`, et — comme `nestor env` — imprime sur
    STDOUT une ligne `export KUBECONFIG=…` à `eval` dans le shell :

        eval "$(nestor stack select banc)"

    Le KUBECONFIG posé est celui de la cible (ADR 0053) : le **banc de la stack**
    s'il est monté (`bench/lima/.work/kubeconfig`), sinon **`/dev/null`** (vide) —
    JAMAIS `~/.kube/config` (la prod). Un `kubectl`/`cilium` direct dans le shell
    vise alors la bonne cible, ou échoue proprement (« pas de banc »), au lieu de
    taper la prod par accident. Un process NE PEUT PAS exporter dans le shell PARENT
    (invariant Unix) → le patron `eval`, comme `ssh-agent`/`nestor env`.

    TOUS les messages humains vont sur STDERR (inertes pour `eval`) ; seule la ligne
    `export` va sur STDOUT. Sans `eval` (appel nu `nestor stack select`), la stack
    est bien activée et les messages s'affichent ; seul le KUBECONFIG du shell n'est
    pas posé (la ligne export apparaît, inoffensive).

    Codes : 0 succès ; 1 fichier absent / schéma invalide ; 2 usage (nom invalide).
    """
    try:
        target_rel = catalog_entry(args.name)
    except ScaffoldError as exc:
        raise _UsageError(str(exc)) from exc

    target_abs = os.path.join(_ROOT, target_rel)
    if not os.path.exists(target_abs):
        # Aide : lister ce que le catalogue propose réellement.
        catalog = sorted(
            os.path.basename(p) for p in glob.glob(os.path.join(_CATALOG_DIR, "*.y*ml"))
        )
        dispo = ", ".join(catalog) or "(catalogue vide)"
        print(
            f"erreur : {target_rel} introuvable dans le catalogue.\n  disponibles : {dispo}",
            file=sys.stderr,
        )
        return 1

    # Garde-fou : valider AVANT d'activer (ne pas pointer le symlink sur un fichier cassé).
    topo = load_topology(target_abs)
    _activate_symlink(target_rel)
    print(
        f"✓ activée : topology.yaml → {target_rel} (chemin dérivé : {default_target(topo)})",
        file=sys.stderr,
    )

    # KUBECONFIG cible : le banc s'il est monté ET JOIGNABLE, sinon /dev/null (jamais la
    # prod, ADR 0053). On NE supprime PAS le kubeconfig (le détruire casserait l'accès à
    # un banc vivant ; il sera de toute façon réécrit par le prochain up/bootstrap). On
    # vise /dev/null seulement s'il n'existe pas OU ne répond plus (banc d'une autre
    # stack, ou API tombée) — `_context_targets_bench` le sonde sans toucher au fichier.
    if os.path.exists(_BENCH_KUBECONFIG) and _kubeconfig_reaches_api(_BENCH_KUBECONFIG):
        cible = os.path.abspath(_BENCH_KUBECONFIG)
    else:
        cible = os.devnull
        _warn(
            "cluster non installé (ou banc injoignable) — pas de connexion possible "
            "pour l'instant (le monter : `nestor up`)."
        )
    # La ligne `export …` n'est utile QU'à `eval`. En appel direct (stdout = TTY), on
    # ne la déverse pas brute dans le terminal — on suggère plutôt `eval`. Si stdout
    # est capturé (`eval "$(…)"`/pipe), on l'imprime pour que le shell la pose.
    if sys.stdout.isatty():
        print(
            f'  pointer le shell : `eval "$(nestor stack select {args.name})"`',
            file=sys.stderr,
        )
    else:
        print(f"export KUBECONFIG={shlex.quote(cible)}")
    return 0


def _real_vms() -> list[str]:
    """Noms des VMs Lima EXISTANTES (toute stack), via `limactl list --format json`.

    Lecture seule du réel (ADR 0056 §7 : on ne stocke pas de state, on le lit). Une
    sortie illisible / `limactl` absent → liste vide (le refresh reste informatif,
    il ne plante pas le poste sans Lima)."""
    try:
        out = subprocess.run(  # noqa: S603 — argv fixe, pas d'entrée shell
            ["limactl", "list", "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_REFRESH_TIMEOUT_S,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    vms = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # On ne retient que les VMs RUNNING (une VM Stopped n'occupe pas le cluster).
        if obj.get("status") == "Running" and obj.get("name"):
            vms.append(obj["name"])
    return vms


def _ready_nodes() -> list[str]:
    """Noms des nœuds k8s à l'état Ready (`kubectl get nodes`). Vide si injoignable.

    Kubeconfig : `KUBECONFIG` exporté, sinon le banc, sinon un kubeconfig VIDE — jamais
    `~/.kube/config` (la prod). Cf. `_bench_kubeconfig` (ADR 0053) : un banc absent
    rend une liste vide (« pas de banc »), il ne lit pas la prod par accident."""
    try:
        out = subprocess.run(  # noqa: S603 — argv fixe, pas d'entrée shell
            # --request-timeout borne l'attente côté kubectl (cluster injoignable) ;
            # `timeout=` borne le subprocess lui-même (double garde-fou anti-blocage).
            ["kubectl", "get", "nodes", "--no-headers", "--request-timeout=5s"],
            check=False,
            capture_output=True,
            text=True,
            env=_kubectl_env(),
            timeout=_REFRESH_TIMEOUT_S,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    ready = []
    for ln in out.stdout.splitlines():
        cols = ln.split()
        # format : NAME STATUS ROLES AGE VERSION ; STATUS == "Ready" (pas NotReady).
        if len(cols) >= 2 and cols[1] == "Ready":
            ready.append(cols[0])
    return ready


# Signal de SANTÉ canonique par couche applicative : la ressource k8s du DERNIER
# maillon dont la PRÉSENCE + l'état READY prouvent que la couche est posée ET saine.
# Pas le namespace (créé tôt, présent même si la couche a échoué à mi-chemin : un ns
# `monitoring` qui existe mais sans Loki Ready a fait afficher la couche « ✓ » à tort)
# — on vise la ressource DISCRIMINANTE que le rôle lui-même éprouve (sa gate Ready) :
#   monitoring → StatefulSet loki Ready (platform-loki) — absent si SeaweedFS manque ;
#   gitops     → Deployment argocd-server Ready (platform-argocd) ;
#   dataops    → Deployment dagster-dagster-webserver Ready (le chart Dagster nomme ses
#                Deployments `dagster-daemon` + `dagster-dagster-webserver`, JAMAIS `dagster` ;
#                le webserver est l'UI/API — la preuve que la couche RÉPOND) ;
#   metrics-server / storage-simple → leur Deployment Ready.
# Format : phase → (kind, name, namespace|None, ready). `ready=True` (workloads) exige
# readyReplicas≥1 ; `ready=False` (Application Argo : CRD sans replicas) = présence.
# Constaté sur le cluster (comme « nœud Ready ») pour que `preview`/`next` reflètent le
# RÉEL — une couche à moitié posée n'est PAS « à-jour ». Miroir des gates de rôles et de
# `gate_pred` (run-phases.sh) — même ressource, même critère Ready.
_LAYER_SIGNAL: dict[str, tuple[str, str, str | None, bool]] = {
    "metrics-server": ("deployment", "metrics-server", "kube-system", True),
    "storage-simple": ("deployment", "local-path-provisioner", "local-path-storage", True),
    "monitoring": ("statefulset", "loki", "monitoring", True),
    "gitops": ("deployment", "argocd-server", "argocd", True),
    "dataops": ("deployment", "dagster-dagster-webserver", "dagster", True),
    # gitops-seed pose l'Application Argo CD `atlas-workflows` (PAS `atlas` : cf. le
    # manifeste atlas-workflow-sample/application.example.yaml + le scénario 27). Avec le
    # mauvais nom, `_observed_layers` ne la voyait jamais faite → `next` la re-proposait en
    # boucle même après un montage réussi.
    "gitops-seed": ("application", "atlas-workflows", "argocd", False),
}

# Kinds dont la SANTÉ se lit via `status.readyReplicas` (workloads répliqués).
_READY_REPLICAS_KINDS = frozenset({"deployment", "statefulset", "daemonset", "replicaset"})


def _kubectl_resource(kind, name, namespace, jsonpath=None):
    """`kubectl get <kind> <name>` borné, env banc (jamais la prod, ADR 0053).
    Renvoie le CompletedProcess, ou None sur erreur d'exécution (cluster injoignable…)."""
    argv = ["kubectl", "get", kind, name, "--request-timeout=5s"]
    if namespace:
        argv += ["-n", namespace]
    if jsonpath:
        argv += ["-o", f"jsonpath={jsonpath}"]
    try:
        return subprocess.run(  # noqa: S603 — argv fixe (table _LAYER_SIGNAL), pas d'entrée shell
            argv,
            check=False,
            capture_output=True,
            text=True,
            env=_kubectl_env(),
            timeout=_REFRESH_TIMEOUT_S,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _resource_exists(kind: str, name: str, namespace: str | None) -> bool:
    """`True` si la ressource k8s EXISTE sur le banc (présence seule, sans santé).
    Toute erreur (absente, cluster injoignable, kind inconnu) → False (prudent)."""
    out = _kubectl_resource(kind, name, namespace)
    return out is not None and out.returncode == 0


def _resource_healthy(kind: str, name: str, namespace: str | None, ready: bool) -> bool:
    """La ressource est-elle posée ET saine ? `ready=False` → présence seule (CRD type
    Application sans replicas). `ready=True` → pour un workload répliqué, readyReplicas≥1
    (le DERNIER maillon : un Loki à 0/1 réplica n'est PAS sain → la couche n'est pas
    « à-jour »). Lecture bornée, fail-closed (toute incertitude → False)."""
    if not ready or kind not in _READY_REPLICAS_KINDS:
        return _resource_exists(kind, name, namespace)
    out = _kubectl_resource(kind, name, namespace, jsonpath="{.status.readyReplicas}")
    if out is None or out.returncode != 0:
        return False
    try:
        return int((out.stdout or "").strip() or "0") >= 1
    except (ValueError, AttributeError):
        return False


def _wait_layer_healthy(
    phase: str, *, retries: int = 30, delay: float = 4.0, sleep=time.sleep
) -> bool:
    """Attend (borné) que le DERNIER MAILLON de `phase` devienne sain (#355).

    Gate de santé ACTIVE après un montage : `next` ne se contente pas du `rc=0` du play
    (un play peut « réussir » alors que Loki ne devient jamais Ready — panne vécue). On
    sonde `_resource_healthy` (le signal `_LAYER_SIGNAL` de la couche) jusqu'à ce qu'il
    soit vrai ou épuisement (retries×delay, ~120s par défaut). True = sain ; False =
    timeout. Une phase SANS signal connu (amont, gitops-seed…) → True (rien à gater).
    `sleep` injecté → testable sans attente réelle."""
    sig = _LAYER_SIGNAL.get(phase)
    if not sig:
        return True  # pas de maillon discriminant à éprouver pour cette phase
    for _ in range(retries):
        if _resource_healthy(*sig):
            return True
        sleep(delay)
    return _resource_healthy(*sig)  # dernier essai après la dernière attente


def _observed_layers(phases: list[str]) -> set[str]:
    """Couches applicatives PROUVÉES posées ET SAINES par l'état RÉEL du cluster.
    Ne teste QUE les phases de `phases` qui ont un signal connu (_LAYER_SIGNAL) — un
    `kubectl get` borné par couche. Une couche dont le dernier maillon n'est pas Ready
    (ex. monitoring sans Loki) n'est PAS retenue : le RÉEL prime sur l'historique (ADR
    0052/0056 §7), mais « réel » = SAIN, pas « namespace présent »."""
    done: set[str] = set()
    for ph in phases:
        sig = _LAYER_SIGNAL.get(ph)
        if sig and _resource_healthy(*sig):
            done.add(ph)
    return done


# ── Sondes de `discover` (ADR 0074) : I/O kubectl irréductible (ADR 0049). Lisent
#    le réel et le RÉDUISENT à des structures simples ; toute la logique (mapping,
#    backend, exposition, santé) est PURE dans nestor/discover.py.


def _discover_node_roles() -> list[dict]:
    """Nœuds + rôles dérivés des labels (`kubectl get nodes`, ADR 0074 §1).

    Étend `_ready_nodes()` (qui ne lit que Ready) par la lecture des rôles : un nœud
    portant le label `node-role.kubernetes.io/control-plane` est `control` ; sinon
    `worker` ; un control PAS détaint (schedulable) est hyperconvergé (control+worker)."""
    out = _kubectl("get", "nodes", "-o", "json")
    if out is None or out.returncode != 0:
        return []
    try:
        data = json.loads(out.stdout)
    except (ValueError, KeyError):
        return []
    nodes: list[dict] = []
    for item in data.get("items", []):
        name = item.get("metadata", {}).get("name", "")
        labels = item.get("metadata", {}).get("labels", {})
        is_cp = "node-role.kubernetes.io/control-plane" in labels
        # un control schedulable (pas de taint NoSchedule control-plane) porte aussi des
        # workloads → hyperconvergé (control + worker), comme ha-3cp (ADR 0055).
        taints = item.get("spec", {}).get("taints") or []
        cp_tainted = any(t.get("key") == "node-role.kubernetes.io/control-plane" for t in taints)
        if is_cp and cp_tainted:
            roles = ["control"]
        elif is_cp:
            roles = ["control", "worker"]
        else:
            roles = ["worker"]
        if name:
            nodes.append({"name": name, "roles": roles})
    return nodes


def _discover_namespaces() -> list[str]:
    """Noms des namespaces du cluster (`kubectl get ns`). Vide si injoignable."""
    out = _kubectl("get", "namespaces", "-o", "name")
    if out is None or out.returncode != 0:
        return []
    # format `namespace/<nom>` → <nom>
    return [ln.split("/", 1)[-1] for ln in out.stdout.split() if ln]


def _discover_namespaced_kinds() -> list[str]:
    """Types k8s namespacés LISTABLES (`api-resources`, ADR 0079 §6) — le balayage de base.

    On itère ces types × namespace pour énumérer TOUT ce qui vit dans un ns (sans table
    codée). Vide si injoignable. C'est le socle commun découverte (rollback + health)."""
    out = _kubectl("api-resources", "--namespaced", "--verbs=list", "-o", "name")
    if out is None or out.returncode != 0:
        return []
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def _discover_owned(namespaces: list[str]) -> list[dict]:
    """Ressources RÉELLES des `namespaces` (kind/name/uid/ownerReferences), pour le graphe
    d'appartenance (ADR 0079). Façade I/O (ADR 0049) : balaye api-resources × ns via
    `kubectl get <types> -n <ns> -o json`, réduit chaque item au minimum que
    `ownership.from_probe` consomme. Best-effort/borné : un type/ns illisible est sauté.
    La LOGIQUE (graphe, ordre) est PURE dans `nestor/ownership.py`."""
    kinds = _discover_namespaced_kinds()
    if not kinds:
        return []
    items: list[dict] = []
    kinds_csv = ",".join(kinds)
    for ns in namespaces:
        out = _kubectl("get", kinds_csv, "-n", ns, "-o", "json", "--ignore-not-found")
        if out is None or out.returncode != 0 or not out.stdout.strip():
            continue
        try:
            data = json.loads(out.stdout)
        except (ValueError, KeyError):
            continue
        for it in data.get("items", []):
            meta = it.get("metadata", {})
            uid = meta.get("uid")
            if not uid:
                continue
            items.append(
                {
                    "kind": it.get("kind", "?"),
                    "name": meta.get("name", "?"),
                    "uid": uid,
                    "namespace": meta.get("namespace"),
                    "ownerReferences": meta.get("ownerReferences") or [],
                }
            )
    return items


def _discover_crd_groups() -> list[str]:
    """Noms complets des CRD installées (`kubectl get crd`) — le PIVOT (ADR 0074 §1).

    `discover.detect_platforms` les mappe par suffixe de groupe (`*.cilium.io` …)."""
    out = _kubectl("get", "crd", "-o", "name")
    if out is None or out.returncode != 0:
        return []
    return [ln.split("/", 1)[-1] for ln in out.stdout.split() if ln]


def _discover_sc_provisioners() -> list[str]:
    """Provisioners des StorageClass (`kubectl get sc`) → backend (ADR 0074 §1)."""
    out = _kubectl("get", "storageclass", "-o", "jsonpath={.items[*].provisioner}")
    if out is None or out.returncode != 0:
        return []
    return out.stdout.split()


def _discover_gateways_present() -> bool:
    """`True` si au moins un `Gateway` (gateway.networking.k8s.io) est posé (ADR 0074 §1)."""
    out = _kubectl("get", "gateways.gateway.networking.k8s.io", "-A", "-o", "name")
    return out is not None and out.returncode == 0 and bool(out.stdout.strip())


def _confirm_destroy(vms: list[str], *, assume_yes: bool) -> bool:
    """Confirme la DESTRUCTION des VMs `vms`. --yes saute ; hors TTY sans --yes : refus.

    Garde-fou anti-destruction silencieuse : sur un TTY, on invite l'opérateur
    (liste les VMs) ; sans TTY (CI/script), on EXIGE --yes (sinon on ne détruit RIEN)."""
    if assume_yes:
        return True
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "destruction refusée hors TTY sans --yes (pas de suppression silencieuse).",
            file=sys.stderr,
        )
        return False
    rep = input(f"⚠️  DÉTRUIRE définitivement les VMs {vms} (+ disques) ? [oui/non] ")
    return rep.strip().lower() in ("oui", "o", "yes", "y")


def cmd_destroy(args: argparse.Namespace) -> int:
    """`destroy` : détruit les VMs de la stack active (calque `pulumi destroy`).

    Cible les VMs RÉELLES qui appartiennent à la stack active (déclarées ET
    existantes — `refresh`/classify_refresh) et délègue leur suppression à
    `run-phases.sh down <vm…>` (limactl reste du bash, ADR 0049 ; façade fine comme
    `status --real` → state.sh). Confirmation interactive obligatoire (--yes pour la
    CI/non-interactif). NE touche PAS les VMs orphelines (autre stack) — destroy
    défait CE QUE LA STACK a monté, pas le reste.

    Codes : 0 succès (ou rien à détruire) ; 1 échec du down délégué ; 2 confirmation
    refusée / hors TTY sans --yes."""
    _assert_bench_target("nestor destroy")
    path = _resolve(args.file)
    topo = load_topology(path)
    stack = topo.catalog.get("topology", "—")
    declared = topo.control_nodes + topo.worker_nodes
    state = classify_refresh(stack, declared, _real_vms(), [])
    # On ne détruit QUE les VMs de la stack RÉELLEMENT présentes (vms_present) ; les
    # orphelines (autre stack) ne sont pas de notre ressort (destroy ≠ nettoyage).
    targets = state.vms_present
    if not targets:
        print(f"stack `{stack}` : aucune VM à détruire (rien de monté pour cette stack).")
        if state.vms_orphan:
            print(
                f"  (VMs orphelines présentes : {', '.join(state.vms_orphan)} — "
                "d'une AUTRE stack, non détruites par `destroy`)"
            )
        return 0

    print(f"stack `{stack}` — VMs à détruire : {', '.join(targets)}")
    if not _confirm_destroy(targets, assume_yes=args.yes):
        print("destruction annulée.", file=sys.stderr)
        return 2

    # Délégation à run-phases.sh down <vm…> (bash garde limactl, ADR 0049).
    rc = subprocess.run(  # noqa: S603 — chemin codé, noms de VM contrôlés (topo validée)
        ["bash", os.path.join(_ROOT, "bench", "lima", "run-phases.sh"), "down", *targets],
        check=False,
    ).returncode
    if rc != 0:
        print(f"échec de la destruction (run-phases.sh down rc={rc}).", file=sys.stderr)
        return 1
    print(f"✓ stack `{stack}` détruite ({len(targets)} VM(s)).")
    return 0


def _active_target_rel() -> str | None:
    """Cible du symlink d'activation `topology.yaml` (chemin relatif), ou None.

    None = pas de symlink (aucune topo active → l'outil retombe sur l'exemple)."""
    link = os.path.join(_ROOT, "topology.yaml")
    if not os.path.islink(link):
        return None
    return os.readlink(link)


def cmd_stack_ls(args: argparse.Namespace) -> int:
    """`stack ls` : liste le catalogue, marque l'ACTIVE (★), donne le chemin dérivé.

    Calque `pulumi stack ls` : énumère les stacks, repère la courante.

    Read-only : énumère `topologies/*.y*ml` (topos réelles + modèles `.example`),
    repère l'entrée pointée par le symlink `topology.yaml`, et dérive pour chacune
    son chemin nommé (default_target). Une entrée illisible/invalide est signalée
    sans faire échouer la liste (code 0 toujours — informatif)."""
    entries = sorted(glob.glob(os.path.join(_CATALOG_DIR, "*.y*ml")))
    if not entries:
        print("catalogue vide — `topology.py stack new <nom>` pour en créer une.")
        return 0
    active_rel = _active_target_rel()
    active_base = os.path.basename(active_rel) if active_rel else None
    print(f"Catalogue de topologies ({len(entries)}) — ★ = active :")
    for path in entries:
        base = os.path.basename(path)
        name = base[: -len(".yaml")] if base.endswith(".yaml") else base[: -len(".yml")]
        mark = "★" if base == active_base else " "
        try:
            derived = default_target(load_topology(path))
        except (TopologyError, OSError, PlanError) as exc:
            derived = f"(invalide : {exc})"
        print(f"  {mark} {name:<22} → {derived}")
    if active_base is None:
        print("  (aucune active — `stack select <nom>` ; sinon l'outil utilise socle.example)")
    return 0


def cmd_stack(args: argparse.Namespace) -> int:
    """Routeur du groupe `stack` (new | ls | select | validate). Façade de dispatch.

    Calque `pulumi stack`. argparse garantit `stack_cmd` ∈ {new, ls, select, validate}
    (sous-parser `required`) — on route vers la façade dédiée. Un `stack` sans verbe
    est une erreur d'usage (argparse l'arrête en amont avec le help du groupe)."""
    return _STACK_DISPATCH[args.stack_cmd](args)


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

    # Filtre RUNTIME (ADR 0069) : si le banc répond ET sans --declared, on constate
    # quelles COUCHES sont réellement montées et on marque une épreuve « prête » (sa
    # couche tourne) ou « couche à monter » (compatible topo, mais la couche n'est pas
    # là). `profil_min` → phases requises via resolve_layers ; croisé avec _observed_layers.
    backend = topo.storage.get("backend", "local-path")
    runtime = not args.declared and os.path.exists(_BENCH_KUBECONFIG) and bool(_ready_nodes())
    observed = _observed_layers(list(_LAYER_SIGNAL)) if runtime else set()

    def _pretes(ep) -> bool:
        # Couches requises par l'épreuve (hors socle up/bootstrap, toujours là si banc up).
        besoin = set(resolve_layers([ep.profil_min], backend))
        return besoin.issubset(observed)

    mode = "état réel du banc" if runtime else "topologie déclarée"
    print(f"Épreuves jouables ({len(jouables)}) — filtrées par {mode} :")
    for e in jouables:
        if runtime:
            mark = "✓ prête      " if _pretes(e) else "○ couche à monter"
            print(f"  {mark} {e.num} [{e.type:<5}] {e.categorie:<13} {e.nom}")
        else:
            print(f"  {e.num} [{e.type:<5}] {e.categorie:<13} {e.nom}")
    if runtime:
        print("  ✓ prête = sa couche tourne ; ○ = topo OK mais couche à monter (`nestor up`).")
    else:
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
    # PAR DÉFAUT : la STACK ACTIVE (last_run_for_topology sur son nom), pas une liste
    # de chemins codés — `artifact runs` doit parler de TA stack. `--all` rétablit la
    # vue tous-chemins ; sans stack active on y retombe (pas de stack → vue globale).
    stack = None if args.all else _active_stack_name(args.file)
    if stack is not None:
        run = last_run_for_topology(runs, stack)
        _, msg = verdict_for_run(run, run.target if run else None, now)
        print(f"  stack `{stack}` : {msg}")
        return 0
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


def _run_for_target(runs, target: str | None):
    """Le run de référence pour un chemin : le dernier de ce `target` si l'historique
    porte le champ, sinon le dernier run global (rétrocompat — mêmes phases/fraîcheur
    servent au diff). Garantit que diff et fraîcheur s'appuient sur LE MÊME run."""
    run = last_run_for_target(runs, target) if target else None
    return run if run is not None else latest_run(runs)


def cmd_env(args: argparse.Namespace) -> int:
    """`env` : imprime la ligne `export KUBECONFIG=<banc>` à `eval` dans le shell.

    Un process NE PEUT PAS exporter une variable dans le shell PARENT (invariant
    Unix) — d'où le patron `eval "$(topology.py env)"` (comme `ssh-agent`/`docker-env`).
    Cela PERSISTE le kubeconfig du banc dans LE shell courant, pour que `kubectl`/
    `cilium` directs (hors topology.py) visent le banc eux aussi. topology.py lui-même
    n'en a pas besoin (main() pose déjà le défaut par process) — c'est un confort shell.

    Sans `--force`, on respecte un KUBECONFIG déjà exporté (intention explicite) : on
    n'imprime rien d'écrasant, juste un rappel commenté sur stderr. Si le banc n'a pas
    de kubeconfig (pas encore monté), erreur d'usage."""
    if not os.path.exists(_BENCH_KUBECONFIG):
        raise _UsageError(
            f"kubeconfig du banc absent ({_BENCH_KUBECONFIG}) — monter le socle d'abord "
            "(`topology.py up`)"
        )
    bench = os.path.abspath(_BENCH_KUBECONFIG)
    current = os.environ.get("KUBECONFIG")
    # `/dev/null` (placeholder posé par `stack select` quand le banc n'existait pas
    # encore) ou un chemin VIDE/INEXISTANT ne sont PAS une intention explicite de
    # l'utilisateur : on les remplace par le banc sans exiger --force (sinon on reste
    # bloqué sur /dev/null après le montage). Seul un VRAI kubeconfig tiers est respecté.
    placeholder = (
        not current
        or os.path.abspath(current) == os.path.abspath(os.devnull)
        or not os.path.exists(current)
    )
    if current and not args.force and not placeholder and os.path.abspath(current) != bench:
        # KUBECONFIG tiers RÉEL déjà posé : on NE l'écrase PAS (sauf --force). Rappel
        # commenté (sur stdout pour rester `eval`-safe : un commentaire shell est inerte).
        print(f"# KUBECONFIG déjà défini ({current}) — `env --force` pour viser le banc")
        return 0
    # Ligne eval-able. `eval "$(topology.py env)"` exporte dans le shell courant.
    print(f"export KUBECONFIG={shlex.quote(bench)}")
    return 0


def cmd_access(args: argparse.Namespace) -> int:
    """`access` : ouvre l'accès développeur au banc (URLs + secrets) — délègue à access.sh.

    Façade fine (ADR 0049/0017) : l'orchestration (Gateways, forwards SSH, /etc/hosts
    `*.cluster.lan`, secrets/tokens LUS du cluster, `.env` atlas) vit dans
    `bench/lima/access.sh` (ADR 0048), du bash irréductible (limactl/ssh). On délègue
    via l'arm `run-phases.sh access`, en passant les options telles quelles
    (`--stop` / `--print-hosts` / `--no-hosts`). Code 0/1 = celui de access.sh ; 2 si
    le banc n'a pas de kubeconfig (socle non monté)."""
    _assert_bench_target("nestor access")
    # Reconstruit les flags d'access.sh depuis les options parsées (un set fixe, sûr).
    flags = [
        flag
        for flag, on in (
            ("--stop", args.stop),
            ("--print-hosts", args.print_hosts),
            ("--no-hosts", args.no_hosts),
        )
        if on
    ]
    runphases = os.path.join(_ROOT, "bench", "lima", "run-phases.sh")
    return subprocess.run(  # noqa: S603 — chemin codé, flags d'un set fixe
        ["bash", runphases, "access", *flags],
        check=False,
    ).returncode


def _kubectl(*args: str, timeout: int = _REFRESH_TIMEOUT_S):
    """Lance `kubectl <args>` sur le banc (kubeconfig en repli sûr), borné. Renvoie le
    CompletedProcess (rc/stdout) ou None si injoignable — l'appelant décide. Le
    kubeconfig vise le banc, sinon un kubeconfig VIDE — jamais la prod (ADR 0053)."""
    try:
        return subprocess.run(  # noqa: S603 — argv contrôlé (table de workloads)
            ["kubectl", *args, "--request-timeout=5s"],
            check=False,
            capture_output=True,
            text=True,
            env=_kubectl_env(),
            timeout=timeout,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _argocd_managed(name: str, namespace: str) -> bool:
    """Le Deployment est-il réconcilié par ArgoCD ? (label app.kubernetes.io/managed-by).

    Un workload managé ne se scale PAS en impératif (sync l'écrase — ADR 0046)."""
    out = _kubectl(
        "get",
        "deployment",
        name,
        "-n",
        namespace,
        "-o",
        "jsonpath={.metadata.labels.app\\.kubernetes\\.io/managed-by}",
    )
    return out is not None and out.returncode == 0 and out.stdout.strip() == "argocd"


# ── Garde d'isolation banc/prod (ADR 0053) ───────────────────────────────────
# Sans kubeconfig banc, kubectl/le client retombent sur ~/.kube/config = la PROD.
# Une commande BANC mutante (up/next/destroy/scale --apply/ha-3cp/…) ne doit JAMAIS
# s'exécuter sur une cible non prouvée-banc : elle pourrait muter la prod par erreur.


def _active_kubeconfig() -> str | None:
    """Cible kubeconfig EXPLICITE/banc, ou None si ni l'un ni l'autre (= sans cible
    sûre). Sert à la garde/preview pour savoir si on est « hors banc » ; le repli
    réel vers `/dev/null` (jamais la prod) est porté par `_bench_kubeconfig`."""
    return os.environ.get("KUBECONFIG") or (
        _BENCH_KUBECONFIG if os.path.exists(_BENCH_KUBECONFIG) else None
    )


def _context_targets_bench() -> bool:
    """`True` si le contexte kubectl COURANT vise PROUVABLEMENT le banc Lima.

    Marqueur principal (ADR 0053) : le banc expose l'API en port-forward localhost
    (`server: https://127.0.0.1:<port>`, bench/lima/lib.sh) — disjoint de toute prod
    (VIP/hostname réel). Read-only, borné, FAIL-CLOSED : toute incertitude → False
    (on ne peut pas prouver le banc → on traite comme non-banc). Sonde via la cible
    SÛRE (`_kubectl_env` : banc ou vide, jamais la prod)."""
    env = _kubectl_env()
    try:
        out = subprocess.run(  # noqa: S603 — argv fixe, lecture seule
            [
                "kubectl",
                "config",
                "view",
                "--minify",
                "-o",
                "jsonpath={.clusters[0].cluster.server}",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=_REFRESH_TIMEOUT_S,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False  # injoignable → on ne peut PAS prouver le banc → refus
    server = out.stdout.strip()
    return out.returncode == 0 and server.startswith(("https://127.0.0.1:", "https://localhost:"))


def _assert_bench_target(action: str) -> None:
    """Garde d'isolation (ADR 0053) : une commande BANC mutante ne s'exécute QUE sur
    une cible prouvée-banc. Si le kubeconfig du banc est absent ET que le contexte
    courant ne vise pas le banc, REFUS (code 2) — protège la prod d'une mutation par
    erreur. Échappatoire prod EXPLICITE : `KUBECONFIG` exporté = intention assumée
    (ADR 0065) — la garde ne bloque alors pas (et `discover` n'est jamais gardé,
    ADR 0074)."""
    if os.environ.get("KUBECONFIG"):
        return  # intention explicite assumée par l'opérateur
    if os.path.exists(_BENCH_KUBECONFIG) and _context_targets_bench():
        return  # banc présent ET contexte = banc : nominal
    raise _UsageError(
        f"REFUS : `{action}` est une commande BANC mais le kubeconfig du banc est "
        f"absent ({os.path.relpath(_BENCH_KUBECONFIG, _ROOT)}) et le contexte kubectl "
        "courant ne vise pas le banc Lima (127.0.0.1). Cette commande pourrait MUTER "
        "la PRODUCTION par erreur (ADR 0053).\n"
        "  • Monter le banc d'abord : `bench/lima/run-phases.sh up`\n"
        "  • Ou, si l'intention est délibérée hors-banc, exporter KUBECONFIG "
        'explicitement : `eval "$(bench/lima/env.sh export)"`'
    )


def _assert_inventory_safe(action: str, inventory_path: str, topo: Topology) -> None:
    """Garde de CIBLE ANSIBLE (ADR 0053) : un montage qui vise le banc (target_kind=lima)
    ne s'exécute PAS sur un inventaire de PROD.

    Complément INDISPENSABLE de `_assert_bench_target` : celle-ci ne valide que le
    KUBECONFIG (chemin kubectl), mais un play `hosts: cloud` SSHe sur les nœuds de
    L'INVENTAIRE — chemin disjoint du KUBECONFIG. Un banc KUBECONFIG + un inventaire
    prod a déjà reconfiguré des nœuds de PROD (`next dataops`). On valide ICI, en
    Python et AVANT ansible-runner, que l'inventaire vise la même topologie que
    l'intention (`topo.target_kind`) — indépendant de la discipline par-play
    (l'audit-log côté playbook a un trou par play oublié).

    Lève `_UsageError` (REFUS) si l'inventaire peut SSHer sur une cible non prouvée
    conforme. Un inventaire purement local (que `localhost`) passe toujours."""
    try:
        with open(inventory_path, encoding="utf-8") as f:
            inv = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise _UsageError(f"inventaire illisible ({inventory_path}) : {exc}") from exc
    ok, raison = _isolation.classify_inventory_target(inv, topo.target_kind)
    if not ok:
        raise _UsageError(
            f"REFUS : `{action}` vise la topologie `{topo.target_kind}` mais "
            f"l'inventaire `{os.path.relpath(inventory_path, _ROOT)}` n'est pas une cible "
            f"sûre — {raison} (ADR 0053). Risque de MUTER la mauvaise cible (la PROD).\n"
            "  • Banc : utiliser l'inventaire Lima (target_kind: lima) — il est généré "
            "par le montage du banc (`bench/lima/run-phases.sh up`).\n"
            "  • Régénérer l'inventaire de la stack active : "
            "`nestor artifact generate -o bootstrap/hosts.yaml`."
        )


# ── node_exec : exécuter une commande SUR un nœud (ADR 0081) ─────────────────────────────
# Façade I/O qui réunit les DEUX transports (limactl pour le banc Lima, SSH pour la prod)
# derrière une signature unique, consommée par `discover` (rapatrier le kubeconfig, lire le
# node-side) et `remove` (wipe node-side). La RÉSOLUTION <node>→cible est PURE
# (`isolation.resolve_node_target`) ; ici, uniquement le sous-processus borné. C'est
# l'irréductible bash de l'ADR 0049 (exec de CLI) — Python l'APPELLE, ne le réimplémente pas.


def _node_exec(node: str, argv: list[str], *, inventory_path: str, timeout: int = 30):
    """Exécute `argv` SUR le nœud `node`, transport résolu de l'inventaire (ADR 0081).

    `lima` → `limactl shell <host> -- argv` ; `ssh` → `ssh [args] user@host -- argv`. Renvoie
    le CompletedProcess (rc/stdout/stderr) ou None si injoignable/usage. La cible vient de
    `inventory_path` (source UNIQUE, ADR 0053) ; un nœud absent lève `_UsageError`."""
    try:
        with open(inventory_path, encoding="utf-8") as f:
            inv = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise _UsageError(f"inventaire illisible ({inventory_path}) : {exc}") from exc
    try:
        target = _isolation.resolve_node_target(inv, node)
    except _isolation.IsolationError as exc:
        raise _UsageError(str(exc)) from exc
    if target.transport == "lima":
        cmd = ["limactl", "shell", target.host, "--", *argv]
    else:
        dest = f"{target.user}@{target.host}" if target.user else target.host
        ssh_opts = shlex.split(target.ssh_args) if target.ssh_args else []
        cmd = ["ssh", *ssh_opts, dest, "--", *argv]
    try:
        return subprocess.run(  # noqa: S603 — argv contrôlé ; transport résolu de l'inventaire
            cmd, check=False, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _fetch_kubeconfig(
    node: str,
    *,
    inventory_path: str,
    server: str,
    out_path: str,
    context_name=None,
    tls_server_name=None,
) -> None:
    """Rapatrie le kubeconfig depuis le control-plane `node` et le RÉÉCRIT pour le poste
    (ADR 0081 étape 2 — résout le chicken-and-egg : `discover` n'exige plus un kubeconfig).

    Lit `/etc/kubernetes/admin.conf` via `_node_exec` (transport résolu de l'inventaire), le
    transforme par la logique PURE `kubeconfig.rewrite_kubeconfig` (endpoint + noms + SAN), et
    l'écrit en `out_path` (chmod 600). Lève `_UsageError` si la lecture échoue."""
    from nestor import kubeconfig as _kc

    argv = ["sudo", "cat", "/etc/kubernetes/admin.conf"]
    out = _node_exec(node, argv, inventory_path=inventory_path)
    if out is None or out.returncode != 0 or not (out.stdout or "").strip():
        detail = (out.stderr or "").strip() if out else "nœud injoignable"
        raise _UsageError(
            f"kubeconfig introuvable sur `{node}` ({detail}) — le control-plane est-il "
            "bootstrappé, et le nœud joignable via l'inventaire actif ?"
        )
    try:
        rewritten = _kc.rewrite_kubeconfig(
            out.stdout, server=server, context_name=context_name, tls_server_name=tls_server_name
        )
    except ValueError as exc:
        raise _UsageError(f"kubeconfig rapatrié invalide : {exc}") from exc
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(rewritten)
    os.chmod(out_path, 0o600)
    print(f"✓ kubeconfig rapatrié de `{node}` → {out_path} (endpoint {server})")


def _discover_nodeside(node: str, *, inventory_path: str):
    """Sonde l'état NODE-SIDE de `node` via node_exec (ADR 0081 étape 3) → `NodeSide`.

    Lance les commandes node-side (containerd/CNI/lsblk/systemctl) sur le nœud ; le PARSING
    est PUR (`nodeside.assemble_nodeside`). Chaque sonde est best-effort : une commande qui
    échoue donne une chaîne vide → champ None/[] (un nœud peut ne pas répondre à tout sans
    invalider le reste). Renvoie None si le nœud est totalement injoignable (1re sonde None)."""
    from nestor import nodeside

    def probe(argv: list[str]) -> str:
        # On garde stdout dès que la commande a TOURNÉ (out ≠ None), QUEL QUE SOIT le rc :
        # ces sondes ENCODENT l'état dans le rc (`systemctl is-active` rend rc=4 + stdout
        # `inactive`). Filtrer sur rc==0 perdrait l'info (bug vu au banc : `inactive` jeté →
        # durcissement faussement inconnu).
        out = _node_exec(node, argv, inventory_path=inventory_path)
        return (out.stdout or "") if out is not None else ""

    # joignabilité : une 1re sonde None (pas rc≠0) = nœud injoignable → on n'invente rien.
    first = _node_exec(node, ["true"], inventory_path=inventory_path)
    if first is None:
        return None
    # CNI : /etc/cni/net.d est root-only (Permission denied sans sudo) → `sudo ls` (vu au banc).
    return nodeside.assemble_nodeside(
        cri_version=probe(["containerd", "--version"]),
        cni_listing=probe(["sudo", "ls", "/etc/cni/net.d/"]),
        lsblk=probe(["sh", "-c", "lsblk -dno NAME,SIZE 2>/dev/null"]),
        auditd=probe(["systemctl", "is-active", "auditd"]),
        fail2ban=probe(["systemctl", "is-active", "fail2ban"]),
    )


def cmd_scale(args: argparse.Namespace) -> int:
    """`scale` : ajuste les replicas des workloads stateless au nombre de nœuds (ADR 0072).

    Capacité RUNTIME : lit les nœuds Ready, dérive une cible par workload de
    l'allowlist (`scale.plan_scale` — pur), et l'applique avec `--apply`. Sans
    `--apply` : affiche le PLAN (read-only, comme `preview`). REFUSE un workload
    managé par ArgoCD (un scale impératif serait écrasé au sync — ADR 0046). Code 0
    si tout est appliqué/à-jour ; 1 si un `kubectl scale` échoue ; 2 si banc
    injoignable (usage)."""
    if args.apply:
        _assert_bench_target("nestor scale --apply")
    ready = _ready_nodes()
    if not ready:
        raise _UsageError(
            "banc injoignable (aucun nœud Ready) — monter le cluster d'abord (`nestor up`)"
        )
    # Capacité d'exécution = nœuds Ready (le banc détaint les control → schedulables).
    workers_ready = len(ready)
    # Détecter les workloads managés par ArgoCD (refusés). On ne sonde QUE l'allowlist.
    managed = frozenset(
        wl.name for wl in _scale.SCALABLE_WORKLOADS if _argocd_managed(wl.name, wl.namespace)
    )
    plans = _scale.plan_scale(workers_ready, argocd_managed=managed)

    print(f"scale — {workers_ready} nœud(s) Ready → cible de replicas :")
    rc = 0
    for plan in plans:
        wl = plan.workload
        if plan.skipped:
            print(f"  ⊘ {wl.name:<10} (ns {wl.namespace}) — {plan.skipped}")
            continue
        if not args.apply:
            print(f"  + {wl.name:<10} (ns {wl.namespace}) → {plan.target} replica(s)")
            continue
        out = _kubectl(
            "scale", "deployment", wl.name, "-n", wl.namespace, f"--replicas={plan.target}"
        )
        if out is not None and out.returncode == 0:
            print(f"  ✓ {wl.name:<10} → {plan.target} replica(s)")
        else:
            detail = (out.stderr.strip() if out else "kubectl injoignable") or "échec"
            print(f"  ✗ {wl.name:<10} → échec : {detail}", file=sys.stderr)
            rc = 1
    if not args.apply:
        print("→ PLAN (rien appliqué) — `nestor scale --apply` pour exécuter.")
    return rc


def _discover_health() -> list:
    """Bilan de santé du cluster, sondé puis classé par `discover.classify_health` (pur).

    Réduit le réel à des compteurs (nœuds Ready/total, PVC Pending/total) que la
    fonction pure transforme en verdicts. Read-only (ADR 0074 §3)."""
    ready = _ready_nodes()
    nodes_all = _kubectl("get", "nodes", "--no-headers")
    total = len(nodes_all.stdout.splitlines()) if (nodes_all and nodes_all.returncode == 0) else 0
    # PVC : compte Bound vs autres (Pending) sur tous les namespaces.
    pvc = _kubectl("get", "pvc", "-A", "--no-headers")
    pvc_total = pvc_pending = 0
    if pvc is not None and pvc.returncode == 0:
        for ln in pvc.stdout.splitlines():
            cols = ln.split()
            # format -A : NAMESPACE NAME STATUS … → STATUS en colonne 2
            if len(cols) >= 3:
                pvc_total += 1
                if cols[2] != "Bound":
                    pvc_pending += 1
    return _discover.classify_health(
        nodes_ready=len(ready),
        nodes_total=total,
        pvc_pending=pvc_pending,
        pvc_total=pvc_total,
    )


def cmd_discover(args: argparse.Namespace) -> int:
    """`discover` : reconstruit un `topology.yaml` depuis un cluster réel (ADR 0074).

    INVERSE de `artifact generate`. Façade FINE (ADR 0074 §6) : sonde le réel via
    kubectl (rôles, namespaces, CRDs, StorageClass, Gateway) puis assemble par la
    logique PURE (`discover.assemble`). Émet (1) le YAML reconstruit (stdout ou `-o`),
    (2) l'INCONNU (jamais ignoré — ADR 0052/0074 §2), (3) un bilan de SANTÉ (§3).
    Read-only. Code 0 si le cluster est joignable ; 2 (usage) sinon.

    `--cp <node>` (ADR 0081 étape 2) : AVANT de sonder, rapatrie le kubeconfig depuis ce
    control-plane (via node_exec) et l'écrit (`--kubeconfig-out`, défaut le KUBECONFIG actif)
    — résout le chicken-and-egg (plus besoin d'un kubeconfig préalable)."""
    if args.cp:
        inv = _inventory_for(load_topology(_resolve(args.file)))
        out_path = (
            args.kubeconfig_out
            or os.environ.get("KUBECONFIG")
            or os.path.join(os.path.expanduser("~"), ".kube", "config")
        )
        _fetch_kubeconfig(
            args.cp,
            inventory_path=inv,
            server=args.server,
            out_path=out_path,
            context_name=args.name,
        )
        os.environ["KUBECONFIG"] = out_path  # les sondes suivantes l'utilisent
    if not _ready_nodes():
        raise _UsageError(
            "banc injoignable (aucun nœud Ready) — exporter KUBECONFIG ou `nestor env`, "
            "ou monter le cluster (`nestor up`)"
        )
    result = _discover.assemble(
        nodes=_discover_node_roles(),
        namespaces=_discover_namespaces(),
        crd_groups=_discover_crd_groups(),
        storageclass_provisioners=_discover_sc_provisioners(),
        gateways_present=_discover_gateways_present(),
        health=_discover_health(),
        topology_name=args.name,
    )

    # 1. le topology.yaml reconstruit (valide — passe stack validate, ADR 0074 §5)
    header = (
        "# topology.yaml reconstruit par `nestor discover` (ADR 0074) — valeurs\n"
        "# génériques (ADR 0023). Vérifier avant usage : `nestor stack validate`.\n"
    )
    body = yaml.safe_dump(result.topology, sort_keys=False, allow_unicode=True)
    rendered = header + body

    if args.output:
        # 2+3. inconnu & santé en COMMENTAIRE dans le fichier (tracé, jamais perdu).
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered)
            if result.unknown:
                f.write("\n# ── INCONNU (hors catalogue — à expliquer/adopter, ADR 0074 §2) :\n")
                for u in result.unknown:
                    ns = f" (ns {u.namespace})" if u.namespace else ""
                    f.write(f"#   {u.kind}: {u.name}{ns}\n")
        print(f"topology.yaml reconstruit → {args.output}")
    else:
        print(rendered, end="")

    # bilan de santé + inconnu sur stderr (informatif, n'altère pas le YAML sur stdout)
    if result.unknown:
        print("\nInconnu (hors catalogue — signalé, ADR 0074 §2) :", file=sys.stderr)
        for u in result.unknown:
            ns = f" (ns {u.namespace})" if u.namespace else ""
            print(f"  • {u.kind}: {u.name}{ns}", file=sys.stderr)
    if result.health:
        print("\nBilan de santé :", file=sys.stderr)
        for h in result.health:
            mark = {"sain": "✓", "dégradé": "✗", "absent": "○"}.get(h.verdict, "?")
            print(f"  {mark} {h.dimension} : {h.verdict} ({h.detail})", file=sys.stderr)

    # NODE-SIDE (ADR 0081 étape 3) : ce que l'API k8s NE PORTE PAS — CRI/CNI/disques/
    # durcissement, lu par node_exec sur chaque nœud découvert. Sur stderr (informatif,
    # n'altère pas le YAML) : la forme dans le topology.yaml sera figée une fois validée
    # sur un vrai nœud (banc en cours de stabilisation).
    if getattr(args, "node_side", False):
        inv = _inventory_for(load_topology(_resolve(args.file)))
        print("\nNode-side (hors API k8s, ADR 0081) :", file=sys.stderr)
        for n in result.topology.get("nodes", []):
            name = n.get("name")
            if not name:
                continue
            ns = _discover_nodeside(name, inventory_path=inv)
            if ns is None:
                print(f"  {name} : injoignable (node_exec)", file=sys.stderr)
                continue
            disks = ", ".join(f"{d.name}({d.size})" for d in ns.disks) or "—"
            print(
                f"  {name} : CRI={ns.cri or '?'} · CNI={ns.cni or '?'} · "
                f"durcissement={ns.hardening or '?'} · disques={disks}",
                file=sys.stderr,
            )
    return 0


def _real_layers_backend() -> tuple[list[str], str | None]:
    """Couches saines + backend RÉELS du cluster, dérivés des sondes de `discover`.

    Réutilise `_discover.assemble` (façade fine, ADR 0074/0076 §6) : on ne réimplémente
    aucune détection. Renvoie (layers triées, backend) ; backend None si le cluster est
    injoignable / aucune StorageClass reconnue (→ `refresh` ne PROPOSE rien dessus)."""
    if not _ready_nodes():  # cluster injoignable → rien de fiable à rapatrier
        return [], None
    result = _discover.assemble(
        nodes=_discover_node_roles(),
        namespaces=_discover_namespaces(),
        crd_groups=_discover_crd_groups(),
        storageclass_provisioners=_discover_sc_provisioners(),
        gateways_present=_discover_gateways_present(),
    )
    topo = result.topology
    return list(topo.get("layers", [])), topo.get("storage", {}).get("backend")


def cmd_refresh(args: argparse.Namespace) -> int:
    """`refresh` : matérialise une évolution VOULUE du réel dans `topology.yaml` (ADR 0076).

    3ᵉ geste réel↔déclaration (après `preview`=constater, `discover`=adopter de zéro) :
    RÉALIGNE la topo active sur le réel (couche montée, backend changé délibérément).
    Borné par l'ADR 0046 — JAMAIS d'écriture silencieuse : diff AFFICHÉ + confirmation,
    puis FUSION en place (préserve commentaires/`status`, édition texte chirurgicale §4).
    `--dry-run` : diff seul, rien écrit. `--yes` : confirme (CI/hors-TTY).

    Périmètre (ADR 0076 §2) : `layers` (couches saines) + `storage.backend`. Les
    différences de NŒUDS sont SIGNALÉES (pas fusionnées : le nom k8s `lima-node1` ≠ le
    nom déclaré `node1` exige une normalisation — différée). Le SCALE (runtime, ADR 0072)
    n'est jamais rapatrié. Suppression (couche déclarée mais absente du réel) : SIGNALÉE
    par défaut, APPLIQUÉE seulement avec `--prune` (§3) — et jamais pour les nœuds (une
    absence de nœud peut être une panne, pas un retrait voulu).

    Code 0 (à jour, ou fusion appliquée) ; 2 (usage : cluster injoignable, fichier non
    éditable sûrement) ; le refus de confirmation n'est pas une erreur (0, rien fait)."""
    path = _resolve(args.file)
    topo = load_topology(path)
    # Le RÉEL : couches saines + backend (sondes discover). Cluster injoignable → on
    # refuse net (refresh n'a aucun réel à rapatrier — ce n'est pas « rien à faire »).
    real_layers, real_backend = _real_layers_backend()
    if real_backend is None and not real_layers:
        raise _UsageError(
            "cluster injoignable (aucun nœud Ready / aucune couche lue) — exporter "
            "KUBECONFIG ou `nestor env`, ou monter le cluster (`nestor up`)"
        )
    # Le DÉCLARÉ, AU MÊME GRAIN que le réel : `discover` émet des PHASES (storage-simple,
    # monitoring, gitops, dataops…), tandis que `declared_layers` peut être des ALIAS de
    # profil (base/metrics/store/obs). On RÉSOUT le déclaré en phases (resolve_layers, le
    # même graphe qu'`up`) — sinon tout matche faux (aliases ≠ phases). Backend du
    # déclaré pour résoudre la variante stockage (storage-simple vs ceph/sc).
    declared_backend = topo.storage.get("backend", "local-path")
    try:
        declared_phase_layers = resolve_layers(topo.declared_layers, declared_backend)
    except TopologyError as exc:
        raise _UsageError(str(exc)) from exc
    # Les nœuds ne sont PAS fusionnés en v1 : on passe le MÊME jeu en déclaré et réel
    # pour neutraliser leur diff (nom k8s lima-node1 ≠ déclaré node1, #357).
    declared_nodes = [{"name": n.name, "roles": n.roles} for n in topo.nodes]
    plan = _refresh_plan.plan_refresh(
        declared_nodes=declared_nodes,
        declared_layers=declared_phase_layers,
        declared_backend=declared_backend,
        real_nodes=declared_nodes,  # v1 : pas de diff de nœuds (cf. docstring / #357)
        real_layers=real_layers,
        real_backend=real_backend,
    )

    if not plan.has_signals:
        print(f"`{os.path.basename(path)}` : déjà aligné sur le réel — rien à rapatrier.")
        return 0

    # Diff AFFICHÉ (ADR 0046 : on regarde avant d'écrire).
    print("Écart réel ↔ déclaration (refresh) :")
    for line in _refresh_plan.format_plan(plan):
        print(line)

    with open(path, encoding="utf-8") as f:
        source = f.read()

    # `--prune` (ADR 0076 §3) : retire les couches déclarées-mais-absentes RÉELLEMENT
    # écrites dans `layers:`. Suppression PROPOSÉE séparément, défaut prudent (jamais sans
    # le flag). Les nœuds absents ne sont JAMAIS prunés (une absence peut être une panne).
    a_pruner = _refresh_fuse.prunable_layers(source, plan) if args.prune else []
    if a_pruner:
        print(f"--prune : couche(s) à RETIRER de la déclaration : {', '.join(a_pruner)}")

    if not plan.has_additions and not a_pruner:
        # Aucun ajout ET (pas de --prune OU rien à pruner) : on a SIGNALÉ, on n'écrit pas.
        if plan.nodes_absent or plan.layers_absent:
            print(
                "→ rien d'appliqué (seules des absences, signalées ci-dessus ; "
                "`--prune` pour retirer les couches absentes)."
            )
        return 0

    if args.dry_run:
        print("→ --dry-run : aucune écriture (diff seul).")
        return 0

    # --yes confirme (CI) ; hors TTY sans --yes, _confirm renvoie le défaut (False) →
    # refus plutôt qu'écrire à l'aveugle (ADR 0046 : jamais de mutation silencieuse).
    no_input = args.yes or not sys.stdin.isatty()
    gestes = []
    if plan.has_additions:
        gestes.append("matérialiser ces ajouts")
    if a_pruner:
        gestes.append(f"RETIRER {', '.join(a_pruner)}")
    if not _confirm(f"Appliquer ({' ; '.join(gestes)}) ?", default=args.yes, no_input=no_input):
        print("refresh annulé (rien écrit).", file=sys.stderr)
        return 0

    # ÉDITION en place (texte chirurgical, préserve le reste — §4) : ajouts (fuse) PUIS
    # suppressions (prune). Fail-closed : forme inattendue → FuseError → usage, jamais de
    # corruption. On chaîne sur le MÊME texte pour cumuler ajouts + prune en une écriture.
    try:
        edited = _refresh_fuse.fuse_topology(source, plan) if plan.has_additions else source
        if a_pruner:
            edited = _refresh_fuse.prune_topology(edited, plan)
    except _refresh_fuse.FuseError as exc:
        raise _UsageError(f"édition impossible ({exc}) — éditer `{path}` à la main") from exc
    # On REVALIDE avant d'écrire (le résultat doit rester une topo valide). Import local :
    # topology_from_dict n'est pas dans l'API du paquet, on le prend du modèle.
    from nestor.model import topology_from_dict

    try:
        topology_from_dict(yaml.safe_load(edited))
    except (TopologyError, yaml.YAMLError) as exc:
        raise _UsageError(f"l'édition produirait une topo invalide ({exc}) — annulé") from exc
    with open(path, "w", encoding="utf-8") as f:
        f.write(edited)
    bilan = []
    if plan.has_additions:
        bilan.append(f"{len(_refresh_plan.format_plan(plan))} ajout(s)/changement(s) signalés")
    if a_pruner:
        bilan.append(f"{len(a_pruner)} couche(s) retirée(s)")
    print(f"✓ `{os.path.basename(path)}` mis à jour ({' ; '.join(bilan)}).")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    """`preview` : LA vue complète d'une stack — VOULU + RÉEL + PLAN (calque `pulumi preview`).

    Une seule commande « où j'en suis + quoi faire » (absorbe l'ancien `status` et
    l'ancien `refresh`), en trois sections :
    - VOULU  : l'intention déclarée (nœuds/HA, profil, backend, exposition) ;
    - RÉEL   : l'état lu du réel (VMs présentes/orphelines/à créer, nœuds Ready) —
      non stocké (ADR 0056 §7), juste lu ;
    - PLAN   : la séquence de couches à monter, chacune avec son libellé MÉTIER et son
      état (`✓ à-jour`, `+ à installer` si inédit, `~ à rejouer` si run périmé), plus
      les VMs orphelines `- à détruire d'abord`.

    Read-only : ne LANCE ni ne DÉTRUIT rien (`next` applique ; `destroy` détruit). Code 0
    (informatif) ; chemin incohérent avec le backend → usage (2)."""
    # Lecture seule : on ne BLOQUE pas. Quand aucun banc n'est monté, la sonde vise
    # /dev/null (jamais la prod, ADR 0053) → la section RÉEL est VIDE. On le DIT
    # simplement plutôt que de laisser croire à un cluster éteint.
    if _active_kubeconfig() is None and not _context_targets_bench():
        _warn(
            "cluster non installé — pas de connexion possible pour l'instant "
            "(le monter : `nestor up`). L'état réel ci-dessous est vide."
        )
    # MISMATCH SHELL ↔ preview (ADR 0053) : `_default_kubeconfig_to_bench` a posé le banc
    # pour CE process (l'opérateur n'avait pas exporté KUBECONFIG) — mais le shell, lui,
    # reste sans KUBECONFIG (process ≠ parent). preview lit donc le BANC pendant qu'un
    # `kubectl` nu dans le shell vise ~/.kube/config (souvent la PROD). On AVERTIT (non
    # bloquant) d'aligner le shell. Seulement si le banc est JOIGNABLE (sinon le 1er
    # warning « cluster non installé » suffit).
    elif _KUBECONFIG_AUTO_BENCH and _kubeconfig_reaches_api(_BENCH_KUBECONFIG):
        _warn(
            "preview lit le BANC, mais ton shell n'a pas KUBECONFIG exporté — un `kubectl` "
            "direct vise ~/.kube/config (souvent la PROD). Aligne le shell : "
            'eval "$(nestor env)".'
        )
    path = _resolve(args.file)
    topo = load_topology(path)
    runs = load_runs(args.history or _RUNS_HISTORY)
    now = int(dt.datetime.now(tz=dt.UTC).timestamp())
    target = args.target  # None → default_target le déduit
    try:
        seq = expected_phase_sequence(topo, target)
    except PlanError as exc:
        raise _UsageError(str(exc)) from exc
    resolved_target = target or default_target(topo)
    stack_name = topo.catalog.get("topology", "—")

    # ADR 0069 : `layers` explicite débordant le preset → la séquence VRAIE est celle
    # des couches (resolve_layers), pas celle du preset de repli. PLAN reflète ce que
    # `up` monterait réellement via l'arm `layers` (cohérence preview↔up).
    if not target and topo.layers:
        backend = topo.storage.get("backend", "local-path")
        try:
            resolved = resolve_layers(topo.declared_layers, backend)
        except TopologyError as exc:
            raise _UsageError(str(exc)) from exc
        if resolved and not set(resolved).issubset(set(seq)):
            socle = ["up", "bootstrap", "ceph", "sc"] if backend == "ceph" else ["up", "bootstrap"]
            seq = socle + resolved
            resolved_target = "layers"

    print(f"stack : {stack_name}  →  chemin : {resolved_target}")

    # ── VOULU (ex-`status`) : l'intention déclarée ───────────────────────────────
    hc = set(topo.hyperconverged_nodes)
    control_disp = ", ".join(f"{n}+worker" if n in hc else n for n in topo.control_nodes)
    workers_disp = ", ".join(topo.worker_nodes) or (
        "— (control hyperconvergés schedulent)" if hc else "—"
    )
    print("VOULU (déclaré) :")
    print(
        f"  control-planes : {control_disp or '—'}"
        f"{'  [HA → VIP requise]' if topo.is_ha_control_plane else ''}"
    )
    print(f"  workers        : {workers_disp}")
    # Couches voulues : `layers` déclaré (ADR 0069) sinon le `profil` (rétrocompat).
    profile = topo.catalog.get("profile", "base")
    couches_label = ", ".join(topo.layers) if topo.layers else f"profil {profile}"
    # Le STOCKAGE n'est affiché que s'il est CONSOMMÉ par une vraie couche applicative.
    # Profil scalaire : `consumes_storage(profile)` (le profil décide — `base` = nus,
    # même backend ceph déclaré, ADR 0039). Layers : une couche storage-simple/datalake
    # l'est (ceph/sc seuls = socle ceph, pas une consommation applicative → ignorés).
    consomme_stockage = (
        any(p in ("storage-simple", "datalake") for p in seq)
        if topo.layers
        else consumes_storage(profile)
    )
    storage_part = (
        f"  ·  stockage : {topo.storage.get('backend', 'local-path')}" if consomme_stockage else ""
    )
    # exposition : le mode EFFECTIF (dérivé), pas la déclaration brute — un bloc
    # `exposition` absent ne veut pas dire « pas d'exposition » : le défaut global est
    # `gateway` (ADR 0071). On annote « (défaut) » quand rien n'est déclaré.
    expo_declare = isinstance(topo.exposition, dict) and topo.exposition.get("mode")
    expo_label = topo.exposition_mode + ("" if expo_declare else " (défaut)")
    print(f"  couches        : {couches_label}{storage_part}  ·  exposition : {expo_label}")

    # ── RÉEL (ex-`refresh`) : l'état lu du réel (non stocké, ADR 0056 §7) ─────────
    declared = topo.control_nodes + topo.worker_nodes
    real = classify_refresh(stack_name, declared, _real_vms(), _ready_nodes())
    print("RÉEL (lu, non stocké) :")
    print(f"  VMs présentes  : {', '.join(real.vms_present) or '—'}")
    print(f"  VMs à créer    : {', '.join(real.vms_missing) or '—'}")
    if real.vms_orphan:
        print(f"  ⚠ orphelines   : {', '.join(real.vms_orphan)} (d'une autre stack)")
    print(f"  nœuds Ready    : {', '.join(real.nodes_ready) or '—'}")

    # Drift de BACKEND (#356, ADR 0046) : le stockage RÉEL (StorageClass observées) peut
    # CONTREDIRE le backend déclaré — typiquement un rook-ceph résiduel orphelin après
    # bascule ceph→local-path. On ne sonde QUE si le cluster répond (nœuds Ready) ;
    # `classify_backend_drift` ne renvoie un backend que sur un signal RECONNU qui
    # contredit la déclaration (sinon None → pas de bruit).
    if real.nodes_ready:
        backend_reel = _discover.classify_backend_drift(
            topo.storage.get("backend", "local-path"), _discover_sc_provisioners()
        )
        if backend_reel:
            _warn(
                f"backend RÉEL `{backend_reel}` ≠ déclaré "
                f"`{topo.storage.get('backend', 'local-path')}` — résidu d'un backend non "
                "défait (ADR 0046 : corriger en code/détruire l'ancien, pas entériner)."
            )

    # ── PLAN : la séquence de couches à monter ───────────────────────────────────
    run = last_run_for_topology(runs, stack_name)
    freshness, _ = verdict_for_run(run, resolved_target, now)
    done = set(run.phases) if run is not None else set()
    a_appliquer = set(diff_phases(seq, done, freshness))
    # Le RÉEL PRIME sur l'absence de trace (ADR 0052/0056 §7) : un cluster qui TOURNE
    # ne « s'installe » pas, même si l'historique ne le matche pas (run non consigné /
    # ancien label de topologie). On retire les phases socle (up/bootstrap) observées
    # faites du RÉEL, ET les couches applicatives PROUVÉES SAINES sur le banc (dernier
    # maillon Ready : Loki pour monitoring, argocd-server pour gitops…). « Sain », pas
    # « namespace présent » : une couche posée à MOITIÉ (ns créé mais Loki absent)
    # RESTE « à installer » — sinon un montage échoué à mi-chemin s'afficherait « ✓ ».
    a_appliquer -= observed_done_phases(declared, real.vms_present, real.nodes_ready)
    a_appliquer -= _observed_layers([p for p in seq if p in a_appliquer])
    # jamais monté ≠ rejeu : `jamais` (aucun run de la stack) → « à installer » (inédit) ;
    # `perime` (run existant mais plus frais) → « à rejouer ».
    rejeu = freshness == "perime"
    inedit = freshness == "jamais"
    print("PLAN (à monter) :")
    if real.vms_orphan:
        for vm in real.vms_orphan:
            print(f"  - détruire {vm:<22} VM d'une autre stack (à retirer d'abord)")
    for phase in seq:
        label = phase_label(phase)
        if phase in a_appliquer:
            mark, etat = ("~", "à rejouer") if rejeu else ("+", "à installer")
        else:
            mark, etat = "✓", "à-jour"
        print(f"  {mark} {label:<42} ({etat})")
    n = len(a_appliquer)
    head = []
    if real.vms_orphan:
        head.append(f"{len(real.vms_orphan)} VM(s) à détruire d'abord")
    if n:
        verbe = "à rejouer" if rejeu else "à installer"
        head.append(f"{n} couche(s) {verbe}")
    if not head:
        print("→ rien à appliquer (stack à jour, terrain propre).")
    else:
        suffix = "" if inedit else " — `next` pour appliquer la couche suivante"
        print(f"→ {' ; '.join(head)} (rien lancé{suffix}).")
    return 0


def _confirm_apply(target: str, *, assume_yes: bool) -> bool:
    """Confirme le montage COMPLET du chemin `target` avant de déléguer à run-phases.sh.

    --yes saute ; hors TTY sans --yes : refus (un montage complet n'est jamais
    silencieux). Sur TTY : invite explicite (le chemin nommé monte toute la séquence)."""
    if assume_yes:
        return True
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("montage refusé hors TTY sans --yes (pas de montage silencieux).", file=sys.stderr)
        return False
    rep = input(f"Monter TOUTE la séquence du chemin `{target}` ? [oui/non] ")
    return rep.strip().lower() in ("oui", "o", "yes", "y")


def _nodes_override(topo) -> str:
    """csv `nom:rôle` des nœuds déclarés (la TOPOLOGIE pilote le banc, ADR 0056).

    Un nœud `control` (même control+worker, le banc le détaint) → `:control` ; un
    worker pur → `:worker`. Partagé par `up` et `next` (délégation socle)."""
    return ",".join(
        f"{n.name}:{'control' if n.has_role('control') else 'worker'}" for n in topo.nodes
    )


def _has_runphases_arm(phase: str) -> bool:
    """`True` si run-phases.sh a un arm `<phase>)` lançable (ADR 0066 : run-phases.sh reste
    la SOURCE — on ne duplique pas la liste des arms en Python). On grep le case-dispatch du
    script pour l'arm EXACT. Prudent : toute erreur de lecture → False (refus net)."""
    runphases = os.path.join(_ROOT, "bench", "lima", "run-phases.sh")
    try:
        with open(runphases, encoding="utf-8") as fh:
            body = fh.read()
    except OSError:
        return False
    return f"\n    {phase}) " in body or f"\n        {phase}) " in body


def _runphases_env(topo, stack_name: str) -> dict[str, str]:
    """Env passé à run-phases.sh (NODES_OVERRIDE/STACK_NAME/EXPOSITION_MODE) — partagé
    par `up` (chemin complet) et `next` (délégation des phases sans play unitaire :
    up/bootstrap/gitops-seed/hardening/…). Garantit que les deux entrées lancent le banc
    avec les MÊMES paramètres dérivés."""
    return {
        **os.environ,
        "NODES_OVERRIDE": _nodes_override(topo),
        "STACK_NAME": stack_name,
        # exposition.mode CONSÉQUENT (ADR 0020/0071) : Gateway en hostNetwork (80/443
        # sur l'IP du nœud) en mode `gateway` (défaut) ; `none` n'arme rien. Alias
        # lb-ipam/hostport déjà résolus par exposition_mode.
        "EXPOSITION_MODE": topo.exposition_mode,
    }


def cmd_up(args: argparse.Namespace) -> int:
    """`up` : monte la stack active de bout en bout (calque `pulumi up`).

    L'ENTRÉE déclarative complète (inversion de frontière, ADR 0049/0056) : lit la
    stack active → DÉRIVE le chemin nommé (default_target) → affiche le PLAN (les
    couches) → CONFIRME → DÉLÈGUE le montage COMPLET à `run-phases.sh <chemin>` (la
    séquence PROUVÉE au banc, ADR 0034 — Python n'orchestre pas mieux limactl/le
    bootstrap que bash ; il en est l'entrée, pas le moteur). Le code de sortie du
    montage est propagé.

    Là où `next` monte UNE couche (1er drift), `up` monte TOUTE la séquence. Code 0
    si le montage réussit ; 1 si run-phases.sh échoue ; 2 (usage) si confirmation
    refusée / chemin incohérent avec le backend."""
    _assert_bench_target("nestor up")
    path = _resolve(args.file)
    topo = load_topology(path)
    target = args.target or default_target(topo)
    try:
        seq = expected_phase_sequence(topo, target)
    except PlanError as exc:
        raise _UsageError(str(exc)) from exc
    stack_name = topo.catalog.get("topology", "—")

    # ADR 0069 : si les `layers` déclarés veulent des couches que le PRESET dérivé ne
    # monte pas (palier non-préfixe, ex. [gitops, metrics] → preset socle), on bascule
    # sur l'arm GÉNÉRIQUE `layers <seq>` — Python fournit l'ordre (resolve_layers, tri
    # du graphe atomique), bash exécute. Sans --target explicite seulement (un --target
    # force le preset). Le socle (up/bootstrap) préfixe la séquence passée à l'arm.
    # On ne résout les couches (qui interroge le graphe) QUE si `layers` est
    # EXPLICITEMENT déclaré ET qu'aucun --target n'est forcé : un profil scalaire
    # (rétrocompat) passe par son preset sans ce détour.
    layers_seq: list[str] | None = None
    if not args.target and topo.layers:
        backend = topo.storage.get("backend", "local-path")
        try:
            resolved = resolve_layers(topo.declared_layers, backend)
        except TopologyError as exc:
            raise _UsageError(str(exc)) from exc
        # Couches voulues NON couvertes par la séquence du preset → arm `layers`.
        if resolved and not set(resolved).issubset(set(seq)):
            socle = ["up", "bootstrap", "ceph", "sc"] if backend == "ceph" else ["up", "bootstrap"]
            layers_seq = socle + resolved
            seq = layers_seq  # le PLAN affiché reflète la vraie séquence montée

    # Affiche le PLAN (les couches à monter) avant de confirmer — comme `preview`.
    print(f"stack : {stack_name}  →  chemin : {target}")
    print("Couches à monter (séquence complète) :")
    for phase in seq:
        print(f"  + {phase_label(phase)}")

    if not _confirm_apply(target, assume_yes=args.yes):
        print("montage annulé.", file=sys.stderr)
        return 2

    # NODES_OVERRIDE : la TOPOLOGIE pilote les nœuds du banc (inversion de frontière,
    # ADR 0056 — la stack active décide, le harnais exécute). ha-3cp garde son
    # override interne (3 CP). Construit avec `next` via le helper partagé.

    # Délégation à run-phases.sh <chemin> : la séquence prouvée au banc (provisioning
    # VM + bootstrap + orchestration ha-3cp + apps), bash garde le moteur (ADR 0049).
    # STACK_NAME : le NOM de la stack active (= topologie déclarée). run-phases.sh le
    # consigne dans `topologie:` de l'historique — c'est la CLÉ que `last_run_for_topology`
    # matche pour le verdict de fraîcheur PAR STACK (deux stacks dérivant le même chemin
    # ne partagent pas leur verdict). Sans lui, le bash écrivait un littéral générique
    # qui ne matchait jamais la stack → PLAN « à installer » alors que la stack est montée.
    # Preset nommé (run-phases.sh <chemin>) OU arm générique `layers <seq>` (palier
    # non-préfixe) : dans les deux cas bash exécute, Python a décidé l'ordre.
    runphases = os.path.join(_ROOT, "bench", "lima", "run-phases.sh")
    if layers_seq is not None:
        argv = ["bash", runphases, "layers", ",".join(layers_seq)]
        libelle = f"layers [{', '.join(topo.declared_layers)}]"
    else:
        argv = ["bash", runphases, target]
        libelle = f"chemin `{target}`"
    print(f"→ montage {libelle} ({len(topo.nodes)} nœud(s)) via run-phases.sh…")
    rc = subprocess.run(  # noqa: S603 — chemin codé, séquence dérivée d'une topo validée
        argv,
        check=False,
        env=_runphases_env(topo, stack_name),
    ).returncode
    if rc != 0:
        print(f"échec du montage ({libelle} rc={rc}).", file=sys.stderr)
        return 1
    print(f"✓ stack `{stack_name}` montée ({libelle}).")
    return 0


# Libellés HUMAINS des phases AMONT — `next` les distingue comme `preview` : `up` =
# créer les VMs SEULES, `bootstrap` = Kubernetes + CRI + CNI (pas tout le socle d'un
# coup). Sert au message ET à la confirmation (un seul vocabulaire, pas de jargon).
_LIBELLES_AMONT = {
    "up": "créer les VMs",
    "bootstrap": "monter Kubernetes (CRI + kubeadm + CNI Cilium)",
}


def _quoi_couche(phase: str) -> str:
    """Texte humain de l'action de montage d'une `phase` (amont OU couche applicative)."""
    return _LIBELLES_AMONT.get(phase, f"monter la couche `{phase}`")


def _quoi_couche_label(phase: str) -> str:
    """Libellé d'une phase pour le MENU : nom technique + label métier lisible.

    Ex. `storage-simple — stockage local-path`. Réutilise plan.phase_label (source
    unique des libellés métier) ; tombe sur le seul nom si pas de label distinct."""
    label = phase_label(phase)
    return f"{phase} — {label}" if label != phase else phase


def _monter_phase(topo: Topology, phase: str, run_params: dict) -> int:
    """Monte UNE phase choisie : amont (run-phases.sh up/bootstrap) ou play unitaire
    (ansible-runner). Renvoie 0 (ok) / 1 (échec run) ou lève _UsageError (usage).

    Extrait de cmd_next pour être partagé par le chemin « 1re couche » et le menu
    multi-couches : une fois la phase CHOISIE, son montage est identique."""
    playbook_rel = phase_playbook(phase)
    # Phases SANS playbook unitaire (`up`/`bootstrap` : provisioning bash limactl/cni.sh,
    # ADR 0049 ; `gitops-seed` : script d'init Gitea ; `hardening`/`smoke-s3`/`wordpress` :
    # tags/env/harnais) → DÉLÉGUÉES à l'arm run-phases.sh du MÊME nom. On le DÉRIVE de
    # `playbook is None` (et de l'existence d'un arm) au lieu d'une liste codée : sinon le
    # menu propose une couche (gitops-seed) que `next` refuse ensuite de monter — incohérent.
    if playbook_rel is None:
        if not _has_runphases_arm(phase):
            raise _UsageError(
                f"la phase `{phase}` n'a ni play unitaire ni arm run-phases.sh — "
                "non lançable via `nestor next`"
            )
        _assert_bench_target(f"nestor next ({phase})")
        stack_name = topo.catalog.get("topology", "—")
        runphases = os.path.join(_ROOT, "bench", "lima", "run-phases.sh")
        print(f"→ {phase} : {_quoi_couche(phase)} via run-phases.sh…")
        rc = subprocess.run(  # noqa: S603 — chemin codé, env dérivé d'une topo validée
            ["bash", runphases, phase],
            check=False,
            env=_runphases_env(topo, stack_name),
        ).returncode
        if rc != 0:
            print(f"échec de la phase `{phase}` (rc={rc}).", file=sys.stderr)
            return 1
        print(f"✓ `{phase}` terminée — relancer `next` pour l'étape suivante ({stack_name}).")
        return 0
    private_data_dir = os.path.join(_ROOT, "bootstrap")
    # Inventaire de la TOPOLOGIE active (ADR 0053) : banc Lima pour une topo lima, prod
    # sinon. PLUS de chemin prod codé en dur — c'est ce qui faisait SSHer `next` (topo
    # banc) sur la prod. La garde _assert_inventory_safe reste le filet en aval.
    inventory = _inventory_for(topo)
    ansible_cfg = os.path.join(private_data_dir, "ansible.cfg")
    # L'inventaire réel est gitignoré (ADR 0023) — sans lui, ansible-runner
    # prendrait le chemin pour un nom d'hôte (erreur cryptique). On l'arrête net.
    if not os.path.exists(inventory):
        rel = os.path.relpath(inventory, _ROOT)
        if topo.target_kind == "lima":
            raise _UsageError(
                f"inventaire du banc absent : {rel} — monter le banc d'abord "
                "(`bench/lima/run-phases.sh up`, qui génère l'inventaire Lima)"
            )
        raise _UsageError(
            f"inventaire absent : {rel} "
            "— le générer (`nestor artifact generate -o bootstrap/hosts.yaml`) "
            "ou le copier depuis bootstrap/hosts.example.yaml"
        )
    _assert_bench_target(f"nestor next ({phase})")
    # Garde de CIBLE ANSIBLE (ADR 0053) : valide que l'INVENTAIRE vise la topologie
    # voulue AVANT de lancer ansible-runner. _assert_bench_target ne couvre que le
    # KUBECONFIG ; un play `hosts: cloud` SSHe sur les nœuds de l'inventaire (chemin
    # disjoint). Sans ça, un banc KUBECONFIG + un inventaire prod mute la PROD.
    _assert_inventory_safe(f"nestor next ({phase})", inventory, topo)
    playbook = os.path.relpath(os.path.join(_ROOT, playbook_rel), private_data_dir)
    print(f"→ lancement de {phase} ({playbook_rel}) via ansible-runner…")
    try:
        result = _runner.launch_phase(
            playbook,
            run_params,
            private_data_dir,
            inventory,
            ansible_config=ansible_cfg,
            # KUBECONFIG vient de l'environnement du poste (config locale de
            # l'opérateur, comme run-phases.sh/lib.sh) ; transmis explicitement
            # plutôt que laissé ambiant dans le sous-processus runner.
            kubeconfig=os.environ.get("KUBECONFIG"),
            target_kind=topo.target_kind,
        )
    except _runner.RunnerUnavailable as exc:
        raise _UsageError(str(exc)) from exc
    print(f"  rc={result.rc} status={result.status}")
    if result.rc != 0:
        return 1
    # Gate de SANTÉ active (#355) : un play `rc=0` ne prouve pas que la couche est SAINE
    # (Loki peut ne jamais devenir Ready — panne vécue). On attend (borné) que le dernier
    # maillon devienne Ready ; sinon on rend rc≠0 (« montée mais pas saine ») plutôt qu'un
    # faux succès. Phase sans signal connu → pas de gate (True).
    if phase in _LAYER_SIGNAL:
        kind, name, ns, _ = _LAYER_SIGNAL[phase]
        print(f"→ attente que `{phase}` soit sain ({kind}/{name})…")
        if not _wait_layer_healthy(phase):
            print(
                f"couche `{phase}` montée mais PAS saine ({kind}/{name} pas Ready) — "
                "voir les pods/événements ; ré-essayer `nestor next` une fois la cause levée.",
                file=sys.stderr,
            )
            return 1
        print(f"✓ `{phase}` sain.")
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    """`next` : monte une couche montable du plan — au CHOIX si plusieurs le sont.

    PAS le calque `pulumi up` complet (qui monterait TOUTE la séquence) — `next` ne
    monte qu'UNE couche par invocation (parité state.sh). Quand PLUSIEURS couches
    sont montables maintenant (deps réelles satisfaites — p. ex. `metrics-server` et
    `storage-simple`, indépendants, ADR 0066), `next` les PROPOSE en menu et
    l'opérateur choisit l'ordre ; le défaut reste l'ordre conventionnel du chemin.
    Les phases AMONT (créer les VMs, socle k8s) sont des prérequis DURS : jamais un
    menu. Lancer `next` EST la décision humaine (G2, ADR 0063) ; ré-invoquer monte la
    suivante (jamais d'auto-enchaînement silencieux).

    Code 0 si la couche est montée (ou rien à monter) ; 1 si le run échoue ; 2 (usage)
    si la couche n'est pas un play unitaire / inventaire absent / chemin incohérent /
    montage annulé.
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    runs = load_runs(args.history or _RUNS_HISTORY)
    now = int(dt.datetime.now(tz=dt.UTC).timestamp())
    target = args.target  # None → plan.default_target le déduit
    run = _run_for_target(runs, target)
    etat_frais, _ = verdict_for_run(run, target, now)
    done = set(run.phases) if run is not None else set()
    # Le RÉEL prime sur l'historique (même logique que `preview`, ADR 0052/0056 §7) :
    # un vieux run consigne `up`/`bootstrap`, mais si les VMs ont été détruites, ces
    # phases ne sont PLUS faites. On RESTREINT `done` aux phases socle réellement
    # observées (VMs présentes / nœud Ready) — sans ça, `next` saute la création des
    # VMs et propose `storage-simple` sur un banc inexistant. `next` respecte ainsi le
    # PLAN de `preview` (qui fait ce même calcul).
    declared = topo.control_nodes + topo.worker_nodes
    observed_socle = observed_done_phases(declared, _real_vms(), _ready_nodes())
    done -= {"up", "bootstrap"} - observed_socle  # retire le socle que le réel CONTREDIT
    run_params = derive_run_params(topo)
    # Les couches MONTABLES maintenant (deps réelles satisfaites). La carte de
    # dépendances vient du graphe atomique (bash, `phase_deps`) — fournie en PARESSEUX :
    # `installable_now` ne l'invoque QU'au-delà du garde-fou amont (inutile de sheller
    # le graphe pour décider de créer les VMs). En cas d'indisponibilité du graphe, le
    # fournisseur lève → on retombe proprement en erreur d'usage.
    backend = topo.storage.get("backend", "local-path")
    try:
        cible_eff = target or default_target(topo)
        seq = expected_phase_sequence(topo, target)
    except (PlanError, TopologyError) as exc:
        raise _UsageError(str(exc)) from exc
    # Le RÉEL prime AUSSI pour les couches APPLICATIVES (même calcul que `preview`,
    # ADR 0052/0056 §7) : une couche dont le signal d'infra est présent sur le banc
    # (metrics-server déployé, ns monitoring/argocd…) est FAITE, même sans trace
    # d'historique (run non consigné / cache socle) ET même si le run n'est pas frais.
    # Sans ça, `next` re-propose une couche déjà installée. `observed` = socle observé
    # + couches applicatives observées : `installable_now` les retire TOUJOURS (prime
    # sur la fraîcheur — sinon un run `jamais`/`perime` rejouerait toute la séquence).
    observed_layers = _observed_layers([p for p in seq if p not in ("up", "bootstrap")])
    observed = observed_socle | observed_layers
    try:
        montables = installable_now(
            topo,
            target,
            done,
            etat_frais,
            deps_fn=lambda: phase_deps(backend),
            observed_done=observed,
        )
    except (PlanError, TopologyError) as exc:
        raise _UsageError(str(exc)) from exc

    if not montables:
        # Rien à monter : suggest_next porte le message « à jour » détaillé. Il faut lui
        # passer `done | observed` (PAS `done` seul, l'historique) — sinon `next`
        # CONTREDIT `preview` : une couche faite mais non consignée (run non consigné /
        # cache socle) ressortirait comme « 1er drift non encore joué » alors que preview
        # la voit ✓ à-jour. Le RÉEL prime (ADR 0052/0056 §7), comme dans `cmd_preview`.
        sugg = suggest_next(topo, target, done | observed, etat_frais, run_params=run_params)
        print(sugg.message)
        return 0

    # Hors TTY SANS --yes : on ne monte JAMAIS en silence (ni menu auto, ni montage
    # mono-couche à l'aveugle). Refus net — l'opérateur doit voir/choisir, ou passer
    # --yes (CI). Ce garde-fou vaut pour les DEUX chemins (sinon le menu, qui prend le
    # défaut sous no_input, monterait sans confirmation explicite).
    off_tty = not sys.stdin.isatty()
    if off_tty and not args.yes:
        print("montage refusé hors TTY sans --yes (pas de montage silencieux).", file=sys.stderr)
        return 2
    no_input = args.yes  # à ce stade : soit TTY (on prompte), soit --yes (on saute)
    # Menu si PLUSIEURS couches montables ; sinon la seule. Choisir un numéro dans le
    # menu EST déjà la décision explicite → on NE redemande PAS de confirmation ensuite
    # (un seul geste, pas de double [o/N] redondant).
    a_choisi_au_menu = len(montables) > 1
    if a_choisi_au_menu:
        phase = _choisir_couche(montables, _quoi_couche_label, no_input=no_input)
        if phase is None:
            print("montage annulé.", file=sys.stderr)
            return 2
    else:
        phase = montables[0]

    quoi = _quoi_couche(phase)
    print(f"Prochaine étape sur `{cible_eff}` : {quoi}.")
    # Confirmation AVANT de monter (l'étape MUTE le banc) — SEULEMENT s'il n'y a pas eu
    # de menu (chemin mono-couche : la confirmation est l'unique garde-fou). Après un
    # menu, le choix du numéro a déjà valu décision (pas de friction en double). --yes
    # saute la confirmation (CI).
    if not a_choisi_au_menu and not _confirm(
        f"{quoi[0].upper()}{quoi[1:]} ?", default=args.yes, no_input=no_input
    ):
        print("montage annulé.", file=sys.stderr)
        return 2
    return _monter_phase(topo, phase, run_params)


def cmd_ha_3cp(args: argparse.Namespace) -> int:
    """Orchestre le montage HA `ha-3cp` (ADR 0047/0055, #250) — la partie ANSIBLE.

    Les VM (limactl) et la CNI restent à run-phases.sh (orchestration de CLI, bash,
    ADR 0049) ; cette commande reçoit `--cp-ip/--vip/--vip-iface` déjà dérivés du
    banc, câble `ha.run_ha_3cp` au RÉEL : `launch` → runner.launch_phase (le MÊME
    montage que `next --apply`), gates → limactl/kubectl, `run_cni` → un rappel vers
    run-phases.sh. La logique (séquence, super-admin→admin, gates etcd) est testée
    sans banc (tests/test_ha.py) ; ce câblage est la seule I/O réelle.
    """
    _assert_bench_target("ha-3cp")
    import time

    private_data_dir = os.path.join(_ROOT, "bootstrap")
    # L'inventaire du banc est généré par run-phases.sh dans son WORKDIR (chemin
    # ABSOLU passé via --inventory) — pas dans bootstrap/. On l'utilise tel quel ;
    # un chemin relatif est résolu depuis bootstrap/ (compat usage hors banc).
    inventory = (
        args.inventory
        if os.path.isabs(args.inventory)
        else os.path.join(private_data_dir, args.inventory)
    )
    ansible_cfg = os.path.join(private_data_dir, "ansible.cfg")
    if not os.path.exists(inventory):
        raise _UsageError(
            f"inventaire absent : {inventory} (généré par run-phases.sh avant la délégation)"
        )
    kubeconfig = os.environ.get("KUBECONFIG")

    def launch(playbook: str, extravars: dict, limit: str | None = None):
        # playbook = 'kube-vip.yaml' → relatif à private_data_dir/<project> ;
        # bootstrap/*.yaml sont à la racine du private_data_dir.
        return _runner.launch_phase(
            playbook,
            extravars,
            private_data_dir,
            inventory,
            ansible_config=ansible_cfg,
            kubeconfig=kubeconfig,
            target_kind="lima",
            limit=limit,
        )

    def _runphases(*cmd: str) -> int:
        """Rappel d'un sous-commande de run-phases.sh (bash garde VM/CNI/inventaire,
        ADR 0049). Renvoie le code de sortie."""
        return subprocess.run(  # noqa: S603 — chemin codé, arguments contrôlés
            ["bash", os.path.join(_ROOT, "bench", "lima", "run-phases.sh"), *cmd],
            check=False,
        ).returncode

    def set_inventory(control_hosts: list[str]) -> None:
        # L'écriture d'inventaire reste du bash (write_inventory, format byte-stable).
        # On réécrit l'inventaire avec les CP membres (primaire en tête) avant un join.
        rc = _runphases("ha-inventory", ",".join(control_hosts))
        if rc != 0:
            raise _ha.HaError(f"réécriture de l'inventaire (control={control_hosts}) en échec")

    # run_cni : la CNI reste portée par run-phases.sh (bash). On la rappelle via la
    # sous-commande dédiée `ha-cni <vip-iface>` (cf. dispatch). Le Gateway s'expose en
    # hostNetwork (ADR 0071) → plus de préfixe LB-IPAM à passer.
    def run_cni():
        rc = _runphases("ha-cni", args.vip_iface)
        if rc != 0:
            raise _ha.HaError(f"CNI (run-phases.sh ha-cni) en échec (rc={rc})")

    def ready_count() -> int:
        out = subprocess.run(  # noqa: S603 — kubectl, pas d'entrée shell
            ["kubectl", "get", "nodes", "--no-headers"],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **({"KUBECONFIG": kubeconfig} if kubeconfig else {})},
        )
        return sum(1 for ln in out.stdout.splitlines() if " Ready " in f" {ln} ")

    nodes = args.nodes.split(",")
    print(f"→ ha-3cp : {len(nodes)} CP derrière la VIP {args.vip} (Ansible via Python/runner)")
    try:
        result = _ha.run_ha_3cp(
            nodes,
            args.cp_ip,
            args.vip,
            args.vip_iface,
            launch=launch,
            run_cni=run_cni,
            set_inventory=set_inventory,
            ready_count=ready_count,
            sleep=time.sleep,
        )
    except _runner.RunnerUnavailable as exc:
        raise _UsageError(str(exc)) from exc
    for step in result.steps:
        mark = "✓" if step.ok else "✗"
        print(f"  {mark} {step.name}{f' — {step.detail}' if step.detail else ''}")
    return 0 if result.built else 1


def cmd_bootstrap_seq(args: argparse.Namespace) -> int:
    """Orchestre le socle k8s (`bootstrap`) — la partie ANSIBLE (interne, ADR 0063).

    Migration de bootstrap_node_sequence vers Python : lance les playbooks du socle
    (checks→…→join-workers) via runner.launch_phase (le MÊME montage que ha-3cp), avec
    `-e control_plane_ip=<cp_ip>`. `join-workers` est SAUTÉ si l'inventaire n'a aucun
    worker (control unique). L'inventaire, la dérivation de cp_ip/iface, la CNI
    (Cilium dans la VM) et le kubeconfig restent à run-phases.sh (briques bash, ADR
    0049) ; cette commande reçoit cp_ip/inventaire déjà dérivés du banc et rappelle
    `ha-cni <iface>` pour la CNI. La logique (séquence, fail-fast) est testée sans
    banc (tests/test_bootstrap.py)."""
    _assert_bench_target("bootstrap-seq")
    private_data_dir = os.path.join(_ROOT, "bootstrap")
    inventory = (
        args.inventory
        if os.path.isabs(args.inventory)
        else os.path.join(private_data_dir, args.inventory)
    )
    ansible_cfg = os.path.join(private_data_dir, "ansible.cfg")
    if not os.path.exists(inventory):
        raise _UsageError(
            f"inventaire absent : {inventory} (généré par run-phases.sh avant la délégation)"
        )
    kubeconfig = os.environ.get("KUBECONFIG")

    def launch(playbook: str, extravars: dict):
        return _runner.launch_phase(
            playbook,
            extravars,
            private_data_dir,
            inventory,
            ansible_config=ansible_cfg,
            kubeconfig=kubeconfig,
            target_kind="lima",
        )

    def run_cni() -> int:
        # CNI (+ GW API CRDs + kubeconfig) : brique bash réutilisée (ha-cni <iface>).
        # Le Gateway s'expose en hostNetwork (ADR 0071) → plus de préfixe LB-IPAM.
        # L'arm `ha-cni` dérive le CP du 1er nœud `control` de NODES (plus de `CP=cp1`
        # codé) ; NODES vient de NODES_OVERRIDE, posé par `up` et hérité tout au long de
        # la chaîne (up → run-phases.sh → bootstrap-seq → ici).
        return subprocess.run(  # noqa: S603 — chemin codé, arguments contrôlés
            [
                "bash",
                os.path.join(_ROOT, "bench", "lima", "run-phases.sh"),
                "ha-cni",
                args.l2_iface,
            ],
            check=False,
            env={**os.environ},
        ).returncode

    # has_workers dérivé de l'inventaire (source de vérité écrite par run-phases.sh) :
    # un control unique sans worker fait sauter join-workers.yaml (la DÉCISION est en
    # Python, qui connaît la topo — pas en bash qui lance tout en aveugle).
    with open(inventory, encoding="utf-8") as fh:
        has_workers = _bootstrap.inventory_has_workers(fh.read())
    n_pb = len(_bootstrap.bootstrap_playbooks(has_workers=has_workers))
    print(f"→ bootstrap : socle k8s ({n_pb} playbooks via Python/runner, CP {args.cp_ip})")
    try:
        result = _bootstrap.run_bootstrap(
            args.cp_ip, launch=launch, run_cni=run_cni, has_workers=has_workers
        )
    except _runner.RunnerUnavailable as exc:
        raise _UsageError(str(exc)) from exc
    except _bootstrap.BootstrapError as exc:
        print(f"  ✗ {exc}", file=sys.stderr)
        return 1
    for step in result.steps:
        mark = "✓" if step.ok else "✗"
        print(f"  {mark} {step.name}{f' — {step.detail}' if step.detail else ''}")
    return 0 if result.built else 1


def cmd_metrics(args: argparse.Namespace) -> int:
    """Expose les métriques DÉJÀ consignées dans runs-history.yaml (P6, exig. 8).

    LIT et met en forme (durées + cpu_core_s/ram_*) — ne mesure rien de neuf
    (mesurer = le banc via metrology.sh). Read-only, code 0 toujours (informatif).
    """
    runs = load_runs(args.history or _RUNS_HISTORY)
    if not runs:
        print("aucun run consigné — pas de métriques à exposer.")
        return 0
    # PAR DÉFAUT : les runs de la STACK ACTIVE (filtrés par nom de stack), pas tout
    # l'historique. `--all` rétablit tous les runs ; sans stack active on garde tout.
    stack = None if args.all else _active_stack_name(args.file)
    scope = [r for r in runs if r.topologie == stack] if stack is not None else runs
    if not scope:
        print(f"aucun run consigné pour la stack `{stack}` (— `--all` pour tout l'historique).")
        return 0
    selected = [scope[-1]] if args.last else scope  # dernier de la stack (fichier chronologique)
    blocs = [format_metrics(metrics_of(r)) for r in selected if r is not None]
    print("\n\n".join(blocs))
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """Smoke-test de réversibilité (P6, exig. 7) : crée un ns → vérifie → détruit
    → vérifie détruit. Éprouve l'apply ET le rollback (ADR 0054).

    Touche un cluster VIVANT via la couche isolée `smoke.py` (stubable). Code 0 si
    réversible (toutes les étapes OK), 1 si une étape échoue, 2 si le cluster est
    injoignable / client absent (usage).
    """
    try:
        result = _smoke.run_smoke(args.namespace)
    except _smoke.SmokeUnavailable as exc:
        raise _UsageError(str(exc)) from exc
    print(f"Smoke-test de réversibilité (namespace {result.namespace}) :")
    for step in result.steps:
        marque = "✓" if step.ok else "✗"
        print(f"  {marque} {step.nom} — {step.detail}")
    verdict = "réversible" if result.reversible else "NON réversible (voir ci-dessus)"
    print(f"→ {verdict}")
    return 0 if result.reversible else 1


def cmd_roundtrip(args: argparse.Namespace) -> int:
    """Round-trip de réversibilité d'une couche ET de sa CLÔTURE descendante :
    détruire (ordre inverse) → vérifier → reconstruire (ordre de montage) → vérifier.

    DESTRUCTIF (efface les couches + données sur un banc jetable) : délègue à
    `run-phases.sh rollback`/`<phase>` (le périmètre vit dans rollback-lib.sh,
    ADR 0054). Une clôture de STOCKAGE (≈ rebuild du socle) exige `--full`. Avant
    toute suppression définitive, CONFIRMATION sur TTY (ou `--yes` hors TTY). Code 0
    si réversible, 1 si une étape échoue / confirmation refusée, 2 si usage.
    """
    _assert_bench_target("nestor test roundtrip")
    try:
        result = _roundtrip.run_roundtrip(args.phase, allow_full=args.full, assume_yes=args.yes)
    except _roundtrip.RoundtripError as exc:
        raise _UsageError(str(exc)) from exc
    print(f"Round-trip — couche `{result.phase}` → clôture {result.layers} :")
    for step in result.steps:
        marque = "✓" if step.ok else "✗"
        print(f"  {marque} {step.nom} — {step.detail}")
    verdict = "réversible" if result.reversible else "NON réversible (voir ci-dessus)"
    print(f"→ {verdict}")
    return 0 if result.reversible else 1


def _remove_dry_run(phase: str) -> int:
    """`remove --dry-run` (ADR 0079) : DÉCOUVRE et affiche l'ordre de teardown, sans rien
    défaire. Aperçu read-only du rollback par découverte (slice 1, #372) : on sonde les
    ressources réelles des namespaces de la clôture (`api-resources` + ownerReferences) et
    on les ordonne (possédés→possesseurs) via le module PUR `ownership`. Read-only → pas de
    garde mutante ; le rollback effectif (mutant) reste le chemin table, prouvé au banc."""
    from nestor import ownership

    try:
        layers = _roundtrip.closure(phase)
    except _roundtrip.RoundtripError as exc:
        raise _UsageError(str(exc)) from exc
    namespaces = sorted({ns for p in layers for ns in _roundtrip.phase_namespaces(p)})
    print(f"Remove (dry-run) — couche `{phase}` → clôture {layers}")
    if not namespaces:
        print("  (aucun namespace possédé par cette clôture — rien à découvrir ici)")
        return 0
    print(f"  namespaces sondés : {', '.join(namespaces)}")
    resources = ownership.from_probe(_discover_owned(namespaces))
    if not resources:
        print("  → aucune ressource découverte (cluster injoignable ou namespaces vides).")
        return 0
    targets = ownership.delete_targets(resources)
    bruit = len(resources) - len(ownership.prune_noise(resources))
    print(
        f"  {len(resources)} ressources sondées — {bruit} ignorées (bruit : Event, "
        "EndpointSlice, CiliumEndpoint, ressources injectées par k8s)."
    )
    print(f"  CIBLES de suppression (racines ; le GC k8s cascade le reste, {len(targets)}) :")
    for r in targets:
        ns = f"-n {r.namespace} " if r.namespace else ""
        print(f"    - {ns}{r.ref}")
    print("→ dry-run : RIEN détruit (aperçu ADR 0079 ; le delete effectif via `--discover`).")
    return 0


# ── Rollback PAR DÉCOUVERTE (mutant) — chemin `--discover` (ADR 0079, slice 2 #372) ──────
# Coexiste avec le chemin TABLE (run_remove → rollback-lib.sh), QUI RESTE LE DÉFAUT. Ce
# chemin défait les ressources NAMESPACÉES par découverte (api-resources + ownerReferences)
# en supprimant les RACINES (le GC k8s cascade) ; il NE touche PAS aux CRD cluster-scoped, au
# node-side Ceph, ni au force-delete des ns/`/finalize` — ces gestes restent au chemin table.
# La LOGIQUE (quoi cibler, quel geste de déblocage) est PURE dans nestor/ownership.py ; ici,
# uniquement l'I/O kubectl borné, env banc (jamais la prod, ADR 0053/0049).


def _kubectl_delete(kind, name, namespace, *, force_grace0=False) -> tuple[bool, str]:
    """`kubectl delete <kind> <name>` borné, env banc. `--wait=false` (on ne bloque pas :
    le GC cascade en fond ; on ré-sonde ensuite pour les cas durs). `--ignore-not-found`
    rend le geste IDEMPOTENT (rejeu = no-op). Renvoie (ok, detail). `force_grace0` ajoute
    `--force --grace-period=0` (pod Terminating à conteneur vivant, ADR 0079 §3)."""
    argv = ["delete", kind, name, "--ignore-not-found", "--wait=false"]
    if namespace:
        argv += ["-n", namespace]
    if force_grace0:
        argv += ["--force", "--grace-period=0"]
    out = _kubectl(*argv)
    if out is None:
        return False, "cluster injoignable"
    detail = (out.stdout or out.stderr or "").strip().splitlines()
    return out.returncode == 0, (detail[-1] if detail else "supprimé")


def _kubectl_strip_finalizers(kind, name, namespace) -> tuple[bool, str]:
    """Retire les finalizers d'une ressource coincée (opérateur parti, ADR 0079 §3) :
    `kubectl patch --type merge -p '{"metadata":{"finalizers":[]}}'`. Best-effort."""
    patch = '{"metadata":{"finalizers":[]}}'
    argv = ["patch", kind, name, "--type", "merge", "-p", patch]
    if namespace:
        argv += ["-n", namespace]
    out = _kubectl(*argv)
    if out is None:
        return False, "cluster injoignable"
    return out.returncode == 0, "finalizers retirés" if out.returncode == 0 else "patch échoué"


def _lingering_pods(namespace: str) -> list[str]:
    """Noms des Pods de `namespace` EN COURS DE SUPPRESSION mais coincés (deletionTimestamp
    posé) — à force-delete (ADR 0079 étape A). Couvre les pods POSSÉDÉS que la passe par
    racines ne cible pas : un Pod CNPG (grace 1800s) ou à conteneur vivant survit longtemps à
    son Deployment/Cluster supprimé (le GC respecte le grace). Vide si ns absent/injoignable."""
    out = _kubectl("get", "pods", "-n", namespace, "-o", "json", "--ignore-not-found")
    if out is None or out.returncode != 0 or not (out.stdout or "").strip():
        return []
    try:
        data = json.loads(out.stdout)
    except (ValueError, KeyError):
        return []
    return [
        it["metadata"]["name"]
        for it in data.get("items", [])
        if it.get("metadata", {}).get("deletionTimestamp")
    ]


def _probe_resource_stuck(kind, name, namespace) -> dict | None:
    """Sonde l'état d'une cible qui traîne après delete → entrées pour `classify_stuck`
    (PUR). Renvoie {terminating, has_finalizers, container_alive}, ou None si la ressource
    est PARTIE / en cours de GC. `container_alive` : un Pod avec ≥1 conteneur `running`."""
    # Si le NAMESPACE de la cible n'existe plus, la ressource est forcément en cours de GC
    # (un PVC `Terminating` dont le ns est NotFound part avec lui, via la libération node-side
    # du PV local-path — kubectl ne peut pas l'accélérer, et patcher ses finalizers dans un ns
    # absent ÉCHOUE). On la traite comme PARTIE : pas un résidu bloquant (preuve banc #372).
    if namespace:
        ns_chk = _kubectl("get", "ns", namespace)
        if ns_chk is not None and ns_chk.returncode != 0:
            return None
    out = _kubectl("get", kind, name, "-n", namespace or "default", "-o", "json")
    if out is None or out.returncode != 0 or not (out.stdout or "").strip():
        return None  # absente → partie
    try:
        obj = json.loads(out.stdout)
    except (ValueError, KeyError):
        return None
    meta = obj.get("metadata", {})
    statuses = obj.get("status", {}).get("containerStatuses", []) or []
    return {
        "terminating": bool(meta.get("deletionTimestamp")),
        "has_finalizers": bool(meta.get("finalizers")),
        "container_alive": any("running" in (cs.get("state") or {}) for cs in statuses),
    }


def _delete_namespace(ns: str) -> tuple[bool, str]:
    """Supprime un namespace possédé par la couche, en finalisant s'il reste WEDGÉ
    (ADR 0079 §3). `delete --wait=false` ; si le ns traîne en Terminating, retire
    `spec.finalizers` via le sous-ressource `/finalize` (la seule voie pour débloquer un ns
    déjà Terminating — un patch simple est ignoré ; miroir de `_ns_force_finalize`,
    rollback-lib). Renvoie (parti, detail). Idempotent : ns absent → (True, déjà absent)."""
    if _kubectl("get", "ns", ns) is None:
        return False, "cluster injoignable"
    out = _kubectl("get", "ns", ns)
    if out.returncode != 0:
        return True, "déjà absent"
    _kubectl("delete", "ns", ns, "--wait=false", "--ignore-not-found")
    # encore là ? → finalize (retire spec.finalizers via /finalize).
    chk = _kubectl("get", "ns", ns, "-o", "json")
    if chk is None or chk.returncode != 0 or not (chk.stdout or "").strip():
        return True, "supprimé"
    try:
        obj = json.loads(chk.stdout)
    except (ValueError, KeyError):
        return False, "ns illisible"
    obj.get("spec", {}).pop("finalizers", None)
    _kubectl_replace_finalize(ns, json.dumps(obj))
    gone = _kubectl("get", "ns", ns)
    return (gone is not None and gone.returncode != 0), (
        "finalisé" if (gone is not None and gone.returncode != 0) else "encore Terminating"
    )


def _kubectl_replace_finalize(ns: str, body_json: str) -> None:
    """`kubectl replace --raw /api/v1/namespaces/<ns>/finalize -f -` (débloque un ns
    Terminating). Best-effort : on alimente stdin avec le ns SANS spec.finalizers — la seule
    voie pour finaliser un ns déjà Terminating (ADR 0079 §3 ; miroir de _ns_force_finalize)."""
    with contextlib.suppress(OSError, ValueError, subprocess.TimeoutExpired):
        subprocess.run(  # noqa: S603 — argv fixe, ns contrôlé (clôture de la couche)
            ["kubectl", "replace", "--raw", f"/api/v1/namespaces/{ns}/finalize", "-f", "-"],
            check=False,
            capture_output=True,
            text=True,
            input=body_json,
            env=_kubectl_env(),
            timeout=_REFRESH_TIMEOUT_S,
        )


def _remove_by_discovery(phase: str, *, full: bool, assume_yes: bool) -> int:
    """`remove --discover` (ADR 0079) : défait la clôture de `phase` PAR DÉCOUVERTE.

    Sonde les ressources réelles (api-resources × ns de la clôture), calcule les CIBLES
    (racines filtrées du bruit, module PUR `ownership`), confirme l'arbre AVANT, puis
    supprime chaque racine — le GC k8s cascade les possédés. NE s'arrête PAS au 1er échec
    (ADR 0079 §4) : agrège les verdicts. Les cibles qui traînent sont ré-sondées et
    débloquées selon `classify_stuck` (force-delete / retrait finalizer). Puis (étape B)
    supprime les CRD cluster-scoped DÉCOUVERTES comme appartenant à la clôture
    (`ownership.deletable_crds` : tous leurs CR dans les ns de la clôture — jamais une CRD
    partagée). Enfin finalise les namespaces possédés (ns wedgé → /finalize). Gardes
    identiques au chemin table : cible banc (appelant), `--full` pour une clôture de
    stockage, confirmation. Code 0 si tout parti, 1 si résidu / refus."""
    from nestor import ownership

    try:
        layers = _roundtrip.closure(phase)
        if _roundtrip.involves_storage(phase) and not full:
            raise _UsageError(
                f"`remove --discover {phase}` touche une clôture de STOCKAGE {layers} "
                "(≈ démontage du socle) — exiger l'opt-in `--full`."
            )
    except _roundtrip.RoundtripError as exc:
        raise _UsageError(str(exc)) from exc

    namespaces = sorted({ns for p in layers for ns in _roundtrip.phase_namespaces(p)})
    resources = ownership.from_probe(_discover_owned(namespaces))
    targets = ownership.delete_targets(resources)
    print(f"Remove (découverte) — couche `{phase}` → clôture {layers}")
    if not targets:
        print("  → aucune cible découverte (déjà propre, ou cluster injoignable).")
        return 0
    print(f"  namespaces : {', '.join(namespaces)} — {len(targets)} racines à défaire :")
    for r in targets:
        print(f"    - {('-n ' + r.namespace + ' ') if r.namespace else ''}{r.ref}")
    if not _roundtrip.confirm(layers, assume_yes=assume_yes):
        print("→ annulé (pas de confirmation).")
        return 1

    echecs: list[str] = []
    for r in targets:
        ok, detail = _kubectl_delete(r.kind, r.name, r.namespace)
        marque = "✓" if ok else "✗"
        print(f"  {marque} delete {r.ref} — {detail}")
        if not ok:
            echecs.append(r.ref)

    # 2e passe : cibles qui traînent → geste de déblocage DÉRIVÉ de l'état (cas durs).
    residus: list[str] = []
    for r in targets:
        etat = _probe_resource_stuck(r.kind, r.name, r.namespace)
        if etat is None:
            continue  # partie
        geste = ownership.classify_stuck(**etat)
        if geste == "force_grace0":
            ok, detail = _kubectl_delete(r.kind, r.name, r.namespace, force_grace0=True)
            print(f"  ⟳ force {r.ref} (Terminating, conteneur vivant) — {detail}")
        elif geste == "strip_finalizers":
            ok, detail = _kubectl_strip_finalizers(r.kind, r.name, r.namespace)
            print(f"  ⟳ finalizers {r.ref} (opérateur parti) — {detail}")
        else:
            ok = False
        if not ok or _probe_resource_stuck(r.kind, r.name, r.namespace) is not None:
            residus.append(r.ref)

    # NOTE (ADR 0079) : on ne supprime PAS les CRD cluster-scoped par découverte ici. Le banc
    # a montré que le lien CRD→opérateur n'est pas découvrable de façon fiable (managedFields
    # = OpenAPI-Generator/kube-apiserver, pas le nom de l'opérateur) → impossible de savoir si
    # une CRD a un opérateur HORS clôture qu'on orphelinerait. Les CR sont défaits (ci-dessus) ;
    # les CRD restent (opérateur réutilisable par un re-`next`). Le nettoyage des CRD viendra
    # avec un signal d'appartenance opérateur fiable (étape ultérieure). La logique pure
    # `ownership.deletable_crds` est prête mais NON branchée tant que ce signal manque.

    # 3e passe : débloquer les PODS POSSÉDÉS qui traînent (deletionTimestamp posé mais coincés).
    # La passe par racines ne les cible pas — or un Pod CNPG (grace 1800s) ou à conteneur vivant
    # survit longtemps à son Deployment/Cluster supprimé, et BLOQUE la finalisation du ns. On
    # force (--grace-period=0) ; si le pod garde un finalizer dont le contrôleur est parti
    # (ex. `batch.kubernetes.io/job-tracking` d'un Job déjà supprimé), le force ne suffit pas →
    # on retire le finalizer. Dérivé de l'état (cas vécu après remove dataops : pg-1 grace 1800s,
    # marquez conteneur vivant, atlas-workflow-sample finalizer Job orphelin).
    for ns in namespaces:
        for pod in _lingering_pods(ns):
            ok, detail = _kubectl_delete("pod", pod, ns, force_grace0=True)
            print(f"  ⟳ force pod {pod} (Terminating, grace long/conteneur vivant) — {detail}")
            if pod in _lingering_pods(ns):  # toujours là → finalizer récalcitrant
                ok, detail = _kubectl_strip_finalizers("pod", pod, ns)
                print(f"  ⟳ finalizers pod {pod} (contrôleur parti) — {detail}")

    # Dernière passe : supprimer les NAMESPACES possédés (finalize si wedgé). C'est ce qui
    # manquait au chemin table (ns argocd/gitea coincés en Terminating, cas vécu) — ici, dérivé.
    for ns in namespaces:
        ok, detail = _delete_namespace(ns)
        marque = "✓" if ok else "✗"
        print(f"  {marque} namespace {ns} — {detail}")
        if not ok:
            residus.append(f"ns/{ns}")

    if residus:
        print(f"→ suppression INCOMPLÈTE — résidus : {residus} (relancer, ou chemin table).")
        return 1
    print(f"→ couche supprimée par découverte — re-monter avec `nestor next` ({phase}).")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """`remove` : supprime UNE couche applicative et sa clôture descendante (inverse de `next`).

    DESTRUCTIF (efface la couche + ses données) : délègue à `run-phases.sh rollback`
    (périmètre dans rollback-lib.sh, ADR 0054), en ordre aval→amont. Détruire une couche
    entraîne celle de ses dépendantes (clôture, ADR 0066) — affichées et confirmées
    AVANT. Une clôture de STOCKAGE (≈ démontage du socle) exige `--full`. `--yes` saute
    la confirmation (hors TTY).

    Mêmes gardes d'isolation que `next` (ADR 0053) : le rollback vise le banc (kubeconfig
    + node-side ceph) → `_assert_bench_target` ; `BANC_JETABLE=1` est imposé par
    run-phases.sh (jamais la prod). Le backend de la stack est THREADÉ à rollback-lib
    (STORAGE_BACKEND) pour cibler les bonnes ressources : sans lui, le rollback
    retomberait sur `ceph` et tenterait de supprimer une OBC absente en local-path.

    DÉCOUVERTE PAR DÉFAUT (ADR 0079, étape A) : pour une clôture SANS node-side (tout sauf
    `ceph` : disques), `remove` défait PAR DÉCOUVERTE d'appartenance (api-resources +
    ownerReferences) — supprime les RACINES namespacées (le GC k8s cascade), force les CR à
    finalizer, finalise les ns wedgés. Plus de table « nom/kind oublié » à maintenir pour le
    k8s namespacé (la classe de bugs vécue ce soir). On ne supprime PAS les CRD cluster-scoped
    (le lien CRD→opérateur n'est pas découvrable de façon fiable — elles restent, l'opérateur
    est réutilisable). Les clôtures à node-side (`ceph`) restent au chemin TABLE jusqu'à ce
    qu'une étape ultérieure couvre le node-side par SSH — `closure_has_nodeside` DÉRIVE le
    routage de la table (transitoire), pas d'une liste codée. `--table` force le chemin table
    (échappatoire) ; `--discover` force la découverte (diagnostic).

    `--dry-run` montre l'arbre découvert sans rien détruire. Garde-fou destructif : sur la
    découverte, sans `--yes`, on EXIGE une confirmation (l'opérateur voit l'arbre AVANT).

    Code 0 si supprimé/dry-run, 1 si une étape échoue / confirmation refusée, 2 si usage."""
    if args.dry_run:
        return _remove_dry_run(args.phase)
    try:
        par_decouverte = args.discover or (
            not args.table and not _roundtrip.closure_has_nodeside(args.phase)
        )
    except _roundtrip.RoundtripError as exc:
        raise _UsageError(str(exc)) from exc
    if par_decouverte:
        _assert_bench_target(f"nestor remove ({args.phase}, découverte)")
        return _remove_by_discovery(args.phase, full=args.full, assume_yes=args.yes)
    _assert_bench_target(f"nestor remove ({args.phase})")
    topo = load_topology(_resolve(args.file))
    backend = topo.storage.get("backend", "local-path")
    try:
        result = _roundtrip.run_remove(
            args.phase, backend=backend, allow_full=args.full, assume_yes=args.yes
        )
    except _roundtrip.RoundtripError as exc:
        raise _UsageError(str(exc)) from exc
    print(f"Remove — couche `{result.phase}` → clôture {result.layers} :")
    for step in result.steps:
        marque = "✓" if step.ok else "✗"
        print(f"  {marque} {step.nom} — {step.detail}")
    if result.removed:
        print(f"→ couche supprimée — re-monter avec `nestor next` ({result.phase}).")
        return 0
    print("→ suppression INCOMPLÈTE (voir ci-dessus).")
    return 1


# Verbes du groupe `stack` (calque `pulumi stack` : GESTION des stacks).
_STACK_DISPATCH = {
    "new": cmd_stack_new,
    "ls": cmd_stack_ls,
    "select": cmd_stack_select,
    "validate": cmd_stack_validate,
}

# Verbes du groupe `artifact` : dériver/constater les artefacts d'une topologie.
# (`status` absorbé par `preview` — la section VOULU ; retiré du menu.)
_ARTIFACT_DISPATCH = {
    "generate": cmd_generate,
    "diff": cmd_diff,
    "runs": cmd_runs,
    "metrics": cmd_metrics,
}

# Verbes du groupe `test` : épreuves jouables + réversibilité (scenarios = ex-epreuves).
_TEST_DISPATCH = {
    "scenarios": cmd_epreuves,
    "smoke": cmd_smoke,
    "roundtrip": cmd_roundtrip,
}


def cmd_artifact(args: argparse.Namespace) -> int:
    """Routeur du groupe `artifact` (generate | status | diff | runs | metrics)."""
    return _ARTIFACT_DISPATCH[args.artifact_cmd](args)


def cmd_test(args: argparse.Namespace) -> int:
    """Routeur du groupe `test` (scenarios | smoke | roundtrip)."""
    return _TEST_DISPATCH[args.test_cmd](args)


_DISPATCH = {
    "stack": cmd_stack,  # calque `pulumi stack` (new | ls | select | validate)
    # Cycle de vie au TOP-LEVEL. `preview` = voir (VOULU+RÉEL+PLAN, absorbe status+
    # refresh) ; `next` = appliquer LA prochaine couche (le vrai `up` complet — VMs +
    # orchestration de TOUTE la séquence — reste à coder).
    "preview": cmd_preview,  # calque `pulumi preview`
    "env": cmd_env,  # imprime `export KUBECONFIG=<banc>` à eval dans le shell
    "access": cmd_access,  # accès dev (URLs + secrets) — délègue à access.sh (ADR 0048)
    "scale": cmd_scale,  # ajuste les replicas au nb de nœuds Ready (ADR 0072, runtime)
    "discover": cmd_discover,  # reconstruit un topology.yaml depuis le réel (ADR 0074, inverse de generate)  # noqa: E501
    "refresh": cmd_refresh,  # réaligne la topo active sur le réel voulu (ADR 0076, fusion + confirmation)  # noqa: E501
    "up": cmd_up,  # calque `pulumi up` : monte TOUTE la séquence (délègue à run-phases.sh)
    "next": cmd_next,  # applique la PROCHAINE couche (1er drift, granularité fine)
    "remove": cmd_remove,  # supprime UNE couche + sa clôture (inverse de next, ADR 0054)
    "destroy": cmd_destroy,  # calque `pulumi destroy`
    # Groupes noun-verb (annexe rangée) : artefacts dérivés/constatés + épreuves.
    "artifact": cmd_artifact,
    "test": cmd_test,
    "ha-3cp": cmd_ha_3cp,  # interne (routée à part dans main, hors menu)
    "bootstrap-seq": cmd_bootstrap_seq,  # interne : socle k8s en Python (migration)
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


class _GroupedHelp(argparse.RawDescriptionHelpFormatter):
    """Aide du parser RACINE : garde l'epilog (commandes groupées courantes/annexes)
    mais MASQUE la liste détaillée des sous-commandes d'argparse — sinon le menu
    afficherait DEUX listes (la native, à plat et illisible, + notre epilog groupé).
    On neutralise donc le rendu des actions `_SubParsersAction`."""

    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction):
            return ""  # pas de liste détaillée : l'epilog groupé est la seule source
        return super()._format_action(action)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="nestor",
        formatter_class=_GroupedHelp,
        description=(
            "Monte et inspecte un cluster Kubernetes décrit dans un fichier.\n"
            "Tu décris ce que tu veux (nœuds, couches) ; l'outil le construit."
        ),
        # Liste des commandes GROUPÉES par usage (courantes vs annexes). argparse les
        # mettrait sinon dans un seul mur illisible : le formatter `_GroupedHelp` masque
        # la liste brute des sous-commandes et n'affiche QUE cet epilog. Détail d'une
        # commande : `nestor <commande> -h`.
        epilog=(
            "Commandes courantes (dans l'ordre d'un workflow) :\n"
            "  stack       choisir/créer/lister les configurations (new·ls·select·validate)\n"
            "  preview     voir l'état sans rien changer (voulu / réel / à monter)\n"
            "  next        monter UNE couche : la prochaine qui manque\n"
            "  remove      supprimer UNE couche (et ses dépendantes) — inverse de next\n"
            "  up          construire le cluster en entier (machines + couches)\n"
            "  destroy     supprimer les machines (VMs) de la stack active\n"
            "\n"
            "Commandes annexes :\n"
            '  env         brancher kubectl sur le banc : eval "$(nestor env)"\n'
            "  access      ouvrir l'accès dev (URLs des services + identifiants)\n"
            "  scale       ajuster les replicas au nombre de nœuds\n"
            "  discover    reconstruire un topology.yaml depuis un cluster réel\n"
            "  refresh     réaligner la déclaration sur le réel voulu (couche·backend)\n"
            "  artifact    fichiers générés + historique (generate·diff·runs·metrics)\n"
            "  test        vérifier le cluster (scenarios·smoke·roundtrip)\n"
            "\n"
            "Détail d'une commande : `nestor <commande> -h`."
        ),
    )
    # ha-3cp n'est PAS un sous-parser ici (commande interne routée à part dans main) :
    # le menu ne liste donc que les commandes publiques, sans `==SUPPRESS==` parasite.
    # metavar="<commande>" : masque le mur `{stack,artifact,…}` dans la ligne d'usage.
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<commande>")

    def _add_file(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-f",
            "--file",
            default=None,
            help="chemin de la topologie (défaut : symlink topology.yaml, "
            "sinon topologies/socle.example.yaml)",
        )
        # --no-input accepté partout (uniformité CI) ; sans interactivité, no-op.
        p.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")

    # `default-target` reste retiré du menu pour l'instant (reviendra avec topology.py
    # up, son consommateur) ; cmd_default_target reste dans le module, juste plus
    # exposé. La fonction default_target() de plan.py reste utilisée en interne
    # (stack ls/select, new).

    # Groupe `stack` (calque `pulumi stack`) : new | ls | select | validate. Pas de
    # `new` top-level — on n'a pas de notion de « projet » Pulumi, donc créer = créer
    # une STACK (verbe du groupe), pas un projet.
    p_stack = sub.add_parser(
        "stack",
        help="choisir/créer/lister les configurations de cluster (new · ls · select · validate)",
    )
    stack_sub = p_stack.add_subparsers(dest="stack_cmd", required=True)

    p_stack_new = stack_sub.add_parser(
        "new", help="créer une nouvelle configuration (assistant question/réponse)"
    )
    p_stack_new.add_argument(
        "name", help="nom de la topologie (→ topologies/<nom>.yaml, gitignorée)"
    )
    p_stack_new.add_argument(
        "--activate",
        action="store_true",
        help="activer sans demander (sinon la question est posée en fin d'assistant)",
    )
    p_stack_new.add_argument(
        "--force", action="store_true", help="écraser topologies/<nom>.yaml s'il existe"
    )
    p_stack_new.add_argument(
        "--no-input",
        action="store_true",
        help="non interactif : défauts + pas d'activation sauf --activate (CI)",
    )

    stack_sub.add_parser("ls", help="lister les configurations ; ★ = active")

    p_stack_sel = stack_sub.add_parser(
        "select", help="rendre une configuration active (celle que up/preview utiliseront)"
    )
    p_stack_sel.add_argument(
        "name", help="nom de l'entrée du catalogue (ex : 3-nodes-1-cp, socle.example)"
    )

    p_stack_val = stack_sub.add_parser(
        "validate", help="vérifier qu'un fichier de config est valide"
    )
    _add_file(p_stack_val)

    # ── Groupe `artifact` (noun-verb) : dériver/constater les artefacts ───────────
    p_artifact = sub.add_parser(
        "artifact",
        help="fichiers générés + historique : inventaire (generate), écarts (diff), "
        "runs passés (runs), durées/ressources (metrics)",
    )
    artifact_sub = p_artifact.add_subparsers(dest="artifact_cmd", required=True)

    p_gen = artifact_sub.add_parser(
        "generate", help="produire l'inventaire Ansible (ou les paramètres) depuis la config"
    )
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

    p_diff = artifact_sub.add_parser(
        "diff", help="vérifier que l'inventaire généré n'a pas dérivé (échoue si différence)"
    )
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

    p_runs = artifact_sub.add_parser(
        "runs", help="montrer les montages passés de la config active (et s'ils sont récents)"
    )
    p_runs.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")
    p_runs.add_argument("--target", default=None, help="chemin nommé ciblé (atlas, storage-real…)")
    p_runs.add_argument(
        "-f", "--file", default=None, help="topologie (défaut : stack active topology.yaml)"
    )
    p_runs.add_argument(
        "--all", action="store_true", help="tous les chemins nommés (pas que la stack)"
    )
    p_runs.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : bench/lima/)"
    )

    p_prev = sub.add_parser(
        "preview",
        help="voir SANS rien changer : ce qui est voulu, ce qui tourne, ce qu'il reste à monter",
    )
    _add_file(p_prev)
    p_prev.add_argument(
        "--target", default=None, help="chemin nommé visé (défaut : déduit de la stack active)"
    )
    p_prev.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : bench/lima/)"
    )

    p_env = sub.add_parser(
        "env",
        help='brancher kubectl sur le cluster du banc : eval "$(nestor env)" dans ton shell',
    )
    p_env.add_argument(
        "--force", action="store_true", help="imprime le banc même si KUBECONFIG est déjà défini"
    )

    p_access = sub.add_parser(
        "access",
        help="ouvrir l'accès dev : URLs des services + identifiants (--stop pour fermer)",
    )
    # Options déclarées explicitement (apparaissent dans `nestor access --help` ;
    # argparse.REMAINDER ne capture pas les `--flags` en tête — limite connue).
    p_access.add_argument("--stop", action="store_true", help="ferme les forwards SSH ouverts")
    p_access.add_argument(
        "--print-hosts", action="store_true", help="imprime le bloc /etc/hosts à coller"
    )
    p_access.add_argument(
        "--no-hosts",
        action="store_true",
        help="ne touche pas /etc/hosts (forwards + secrets seuls)",
    )

    p_scale = sub.add_parser(
        "scale",
        help="ajuster les replicas des services au nombre de nœuds (PLAN ; --apply exécute)",
    )
    p_scale.add_argument(
        "--apply", action="store_true", help="applique le scaling (sinon : affiche le PLAN seul)"
    )

    p_discover = sub.add_parser(
        "discover",
        help="reconstruire un topology.yaml depuis un cluster réel (l'inverse de construire)",
    )
    p_discover.add_argument(
        "-o", "--output", default=None, help="écrire le topology.yaml ici (défaut : afficher)"
    )
    p_discover.add_argument(
        "--name",
        default="discovered",
        help="nom de la topologie reconstruite (défaut : discovered)",
    )
    _add_file(p_discover)
    p_discover.add_argument(
        "--cp",
        default=None,
        help="rapatrier d'abord le kubeconfig depuis ce control-plane (nœud de l'inventaire, "
        "ADR 0081) — résout le chicken-and-egg",
    )
    p_discover.add_argument(
        "--kubeconfig-out",
        default=None,
        help="où écrire le kubeconfig rapatrié (défaut : $KUBECONFIG ou ~/.kube/config)",
    )
    p_discover.add_argument(
        "--server",
        default="https://127.0.0.1:6443",
        help="endpoint réécrit dans le kubeconfig rapatrié (défaut : port-forward Lima)",
    )
    p_discover.add_argument(
        "--node-side",
        action="store_true",
        help="sonder aussi le node-side (CRI/CNI/disques/durcissement) via node_exec (ADR 0081)",
    )

    p_refresh = sub.add_parser(
        "refresh",
        help="réaligner la déclaration sur une évolution voulue du réel (couche/backend)",
    )
    _add_file(p_refresh)
    p_refresh.add_argument(
        "--dry-run", action="store_true", help="afficher le diff seulement (n'écrit rien)"
    )
    p_refresh.add_argument(
        "--prune",
        action="store_true",
        help="retirer AUSSI les couches déclarées mais absentes du réel (défaut : signalées)",
    )
    p_refresh.add_argument(
        "--yes", action="store_true", help="confirmer la fusion (requis hors TTY)"
    )

    p_destroy = sub.add_parser(
        "destroy", help="supprimer les machines (VMs) de la configuration active"
    )
    _add_file(p_destroy)
    p_destroy.add_argument(
        "--yes", action="store_true", help="sauter la confirmation (requis hors TTY pour détruire)"
    )

    p_up = sub.add_parser(
        "up", help="construire le cluster en entier (machines + toutes les couches)"
    )
    _add_file(p_up)
    p_up.add_argument(
        "--target", default=None, help="chemin nommé visé (défaut : dérivé de la stack active)"
    )
    p_up.add_argument("--yes", action="store_true", help="sauter la confirmation (requis hors TTY)")

    p_next = sub.add_parser(
        "next", help="monter UNE seule couche : la prochaine qui manque (avancée pas à pas)"
    )
    _add_file(p_next)
    p_next.add_argument(
        "--target", default=None, help="chemin nommé visé (défaut : déduit du profil+backend)"
    )
    p_next.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : bench/lima/)"
    )
    p_next.add_argument(
        "--yes", action="store_true", help="monter sans demander confirmation (requis hors TTY)"
    )

    p_remove = sub.add_parser(
        "remove",
        help="supprimer UNE couche et ses dépendantes (inverse de next, DESTRUCTIF banc)",
    )
    _add_file(p_remove)
    p_remove.add_argument(
        "--phase",
        required=True,
        choices=list(_roundtrip.KNOWN_PHASES),
        help="couche à supprimer (sa clôture descendante est retirée avec elle)",
    )
    p_remove.add_argument(
        "--full",
        action="store_true",
        help="autoriser une clôture de STOCKAGE (ceph/sc/datalake → ≈ démontage du socle)",
    )
    p_remove.add_argument(
        "--dry-run",
        action="store_true",
        help="ne rien détruire : DÉCOUVRIR et afficher l'ordre de teardown (ADR 0079)",
    )
    # Routage découverte/table (ADR 0079 étape A). Par défaut : DÉCOUVERTE si la clôture est
    # namespacée seule (ni CRD ni node-side) ; TABLE sinon (ceph/sc/datalake). Les deux flags
    # FORCENT un chemin (diagnostic / échappatoire), mutuellement exclusifs.
    grp = p_remove.add_mutually_exclusive_group()
    grp.add_argument(
        "--discover",
        action="store_true",
        help="forcer la DÉCOUVERTE d'appartenance (api-resources + ownerReferences, ADR 0079)",
    )
    grp.add_argument(
        "--table",
        action="store_true",
        help="forcer le chemin TABLE (rollback-lib.sh) — échappatoire au routage par défaut",
    )
    p_remove.add_argument(
        "--yes",
        action="store_true",
        help="supprimer sans demander confirmation (requis hors TTY)",
    )

    p_met = artifact_sub.add_parser(
        "metrics", help="montrer durées et ressources (CPU/RAM) des montages de la config active"
    )
    p_met.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")
    p_met.add_argument("--last", action="store_true", help="seulement le dernier run (de la stack)")
    p_met.add_argument(
        "-f", "--file", default=None, help="topologie (défaut : stack active topology.yaml)"
    )
    p_met.add_argument("--all", action="store_true", help="tous les runs (pas que la stack active)")
    p_met.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : bench/lima/)"
    )

    # ── Groupe `test` (noun-verb) : épreuves jouables + réversibilité ─────────────
    p_test = sub.add_parser(
        "test",
        help="vérifier le cluster : scénarios jouables (scenarios), test rapide (smoke), "
        "monter→détruire→remonter une couche (roundtrip)",
    )
    test_sub = p_test.add_subparsers(dest="test_cmd", required=True)

    p_epr = test_sub.add_parser(
        "scenarios", help="lister les scénarios de test compatibles avec la config active"
    )
    _add_file(p_epr)
    p_epr.add_argument("--all", action="store_true", help="montrer aussi les exclus + la raison")
    p_epr.add_argument(
        "--declared",
        action="store_true",
        help="filtrer sur la topologie déclarée seule (sans constater l'état réel du banc)",
    )
    p_epr.add_argument(
        "--type", choices=["unit", "intég", "chaos"], default=None, help="filtrer par type"
    )

    p_smk = test_sub.add_parser(
        "smoke", help="test rapide que le cluster répond (crée puis supprime un objet jetable)"
    )
    p_smk.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")
    p_smk.add_argument(
        "--namespace", default=None, help="nom du namespace jetable (défaut : topology-smoke)"
    )

    p_rt = test_sub.add_parser(
        "roundtrip",
        help="éprouver une couche en la détruisant puis la remontant (DESTRUCTIF, banc jetable)",
    )
    p_rt.add_argument(
        "--phase",
        required=True,
        choices=list(_roundtrip.KNOWN_PHASES),
        help="couche à éprouver (DESTRUCTIF : efface la clôture descendante puis la re-monte)",
    )
    p_rt.add_argument(
        "--full",
        action="store_true",
        help="autoriser une clôture de STOCKAGE (ceph/sc/datalake → ≈ rebuild du socle)",
    )
    p_rt.add_argument(
        "--yes",
        action="store_true",
        help="sauter la confirmation interactive (requis hors TTY pour détruire)",
    )

    # ha-3cp : commande INTERNE (appelée par run-phases.sh avec --cp-ip/--vip dérivés
    return ap


def _build_ha_parser() -> argparse.ArgumentParser:
    """Parser DÉDIÉ à la commande interne `ha-3cp` (hors du menu public).

    ha-3cp est appelée par run-phases.sh avec --cp-ip/--vip dérivés du banc — ce
    n'est pas un verbe du menu. On la garde HORS du parser principal (sinon argparse
    l'expose dans le --help et la liste des choix). Routée à part dans main() ; sera
    absorbée par `up` (inversion de frontière, ADR 0063)."""
    ap = argparse.ArgumentParser(prog="topology ha-3cp")
    ap.add_argument("--nodes", default="cp1,cp2,cp3", help="CP, le 1er = primaire (csv)")
    ap.add_argument("--cp-ip", required=True, dest="cp_ip", help="IP réelle du CP primaire")
    ap.add_argument("--vip", required=True, help="VIP de l'API (kube-vip)")
    ap.add_argument("--vip-iface", required=True, dest="vip_iface", help="interface L2 de la VIP")
    ap.add_argument("--inventory", default="hosts.yaml", help="inventaire (relatif à bootstrap/)")
    return ap


def _build_bootstrap_parser() -> argparse.ArgumentParser:
    """Parser DÉDIÉ à la commande interne `bootstrap-seq` (hors du menu public).

    Appelée par run-phases.sh:phase_bootstrap avec --cp-ip/--l2-iface/--inventory
    dérivés du banc — orchestre les 6 playbooks du socle en Python (migration de
    bootstrap_node_sequence). Interne, routée à part dans main() comme ha-3cp."""
    ap = argparse.ArgumentParser(prog="topology bootstrap-seq")
    ap.add_argument("--cp-ip", required=True, dest="cp_ip", help="IP réelle du CP primaire")
    ap.add_argument("--l2-iface", required=True, dest="l2_iface", help="interface L2 (LB-IPAM/CNI)")
    ap.add_argument("--inventory", default="hosts.yaml", help="inventaire (relatif à bootstrap/)")
    return ap


# Commandes INTERNES (hors menu) : nom → (builder de parser dédié). Routées à part
# dans main() pour ne PAS polluer le --help / la liste des choix du menu public.
_INTERNAL_PARSERS = {
    "ha-3cp": _build_ha_parser,
    "bootstrap-seq": _build_bootstrap_parser,
}


# Posé par `_default_kubeconfig_to_bench` quand IL a dû pointer le banc lui-même (le
# shell de l'opérateur n'avait PAS KUBECONFIG exporté). Signal pour `preview` : le
# process voit le banc, mais le SHELL ne l'a pas → un `kubectl` nu y vise ~/.kube/config
# (souvent la prod). Variable de PROCESS (le défaut process-local ne change pas le shell).
_KUBECONFIG_AUTO_BENCH = False


def _default_kubeconfig_to_bench() -> None:
    """Sans KUBECONFIG exporté, pointe le banc Lima par défaut (`_BENCH_KUBECONFIG`).

    `topology.py` est l'entrée du banc (ADR 0049/0056) : ses commandes « état réel »
    (smoke/scenarios/roundtrip/preview) interrogent le cluster via le client kubernetes
    OU kubectl, qui lisent `KUBECONFIG`/`~/.kube/config`. Sans ce défaut, elles visent
    le contexte courant du poste (souvent l'endpoint prod-exemple de hosts.example.yaml)
    et échouent/`—` alors que le banc tourne. On NE force PAS si l'opérateur a déjà
    exporté KUBECONFIG (intention explicite respectée). Mémorise dans
    `_KUBECONFIG_AUTO_BENCH` qu'on a posé le défaut (≠ l'opérateur) — le shell, lui,
    reste sans KUBECONFIG (process ≠ parent)."""
    global _KUBECONFIG_AUTO_BENCH
    if not os.environ.get("KUBECONFIG") and os.path.exists(_BENCH_KUBECONFIG):
        os.environ["KUBECONFIG"] = _BENCH_KUBECONFIG
        _KUBECONFIG_AUTO_BENCH = True


def main(argv: list[str] | None = None) -> int:
    _default_kubeconfig_to_bench()
    # Les commandes internes sont interceptées AVANT le parser principal (hors menu).
    args_list = sys.argv[1:] if argv is None else argv
    if args_list and args_list[0] in _INTERNAL_PARSERS:
        cmd = args_list[0]
        args = _INTERNAL_PARSERS[cmd]().parse_args(args_list[1:])
        args.cmd = cmd
        return _run(args)
    args = _build_parser().parse_args(args_list)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
