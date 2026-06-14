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
  uv run python scripts/topology.py stack new <nom> [--activate] [--no-input]
  uv run python scripts/topology.py stack ls                              (calque pulumi stack)
  uv run python scripts/topology.py stack select <nom>
  uv run python scripts/topology.py stack validate [-f topology.yaml]
  uv run python scripts/topology.py stack refresh             (calque pulumi refresh)
  uv run python scripts/topology.py generate [--kind prod|lima] [--what inventory|run-params]
  uv run python scripts/topology.py status [--real [--hosts cp1 node1]]
  uv run python scripts/topology.py diff [--kind prod|lima --against PATH]
  uv run python scripts/topology.py epreuves [--all] [--type unit|intég|chaos]   (P4)
  uv run python scripts/topology.py runs [--target atlas|storage-real|…]          (P4)
  uv run python scripts/topology.py preview [--target …]            (calque pulumi preview)
  uv run python scripts/topology.py destroy [--yes]                (calque pulumi destroy)
  uv run python scripts/topology.py next [--target …] [--apply]                   (P5)
  uv run python scripts/topology.py metrics [--last]                               (P6)
  uv run python scripts/topology.py smoke [--namespace …]                          (P6)
  uv run python scripts/topology.py roundtrip --phase monitoring|gitops|…          (P6+)

P4 ajoute deux commandes READ-ONLY : `epreuves` (liste filtrée par la topologie,
exig. 6 — ne lance rien) et `runs` (lit l'historique + fraîcheur, exig. 10-12 —
ne réécrit rien). P5 ajoute `next` : suggère la prochaine phase (diff voulu−réel) ;
`--apply` la LANCE via ansible-runner — décision humaine explicite, jamais
d'auto-apply (ADR 0063). Sans --apply, `next` est informatif (code 0). P6 ajoute
`metrics` (expose les métriques DÉJÀ consignées, exig. 8 — ne mesure rien de neuf)
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
import datetime as dt
import difflib
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml  # noqa: E402

from cluster_topology import (  # noqa: E402
    QUESTION_LB_MODE,
    QUESTIONS,
    PlanError,
    ScaffoldError,
    TopologyError,
    build_topology_dict,
    catalog_entry,
    classify_refresh,
    default_target,
    derive_run_params,
    diff_phases,
    expected_phase_sequence,
    filter_epreuves,
    format_metrics,
    load_runs,
    load_topology,
    metrics_of,
    phase_label,
    plan_init,
    render_lima_inventory,
    render_prod_inventory,
    suggest_next,
    verdict_for_run,
)
from cluster_topology import ha as _ha  # noqa: E402
from cluster_topology import roundtrip as _roundtrip  # noqa: E402
from cluster_topology import runner as _runner  # noqa: E402
from cluster_topology import smoke as _smoke  # noqa: E402
from cluster_topology.history import (  # noqa: E402
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
_STATE_SH = os.path.join(_ROOT, "bootstrap", "state.sh")
_RUNS_HISTORY = os.path.join(_ROOT, "test", "lima", "runs-history.yaml")
# Borne l'attente de `stack refresh` sur limactl/kubectl : un cluster injoignable ou
# un démon Lima bloqué ne doit JAMAIS figer le refresh (leçon du timeout ha._vm_exec).
_REFRESH_TIMEOUT_S = 8
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
            f"{plan.target} existe déjà — `--force` pour l'écraser "
            "(ou choisis un autre nom)"
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
    """`stack select` : active une topologie EXISTANTE (repointe le symlink topology.yaml).

    Calque `pulumi stack select` : choisit la stack courante parmi le catalogue.

    Résout `topologies/<nom>(.example).yaml` → VALIDE le schéma (garde-fou : on
    n'active pas un fichier cassé, contrairement à `ln -sf`) → repointe le symlink →
    confirme le chemin dérivé. Accepte un modèle versionné (`<nom>.example`) comme
    cible (activer le banc générique est légitime).

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
            f"erreur : {target_rel} introuvable dans le catalogue.\n"
            f"  disponibles : {dispo}",
            file=sys.stderr,
        )
        return 1

    # Garde-fou : valider AVANT d'activer (ne pas pointer le symlink sur un fichier cassé).
    topo = load_topology(target_abs)
    _activate_symlink(target_rel)
    print(f"✓ activée : topology.yaml → {target_rel} (chemin dérivé : {default_target(topo)})")
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
    """Noms des nœuds k8s à l'état Ready (`kubectl get nodes`). Vide si injoignable."""
    kubeconfig = os.environ.get("KUBECONFIG")
    try:
        out = subprocess.run(  # noqa: S603 — argv fixe, pas d'entrée shell
            # --request-timeout borne l'attente côté kubectl (cluster injoignable) ;
            # `timeout=` borne le subprocess lui-même (double garde-fou anti-blocage).
            ["kubectl", "get", "nodes", "--no-headers", "--request-timeout=5s"],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **({"KUBECONFIG": kubeconfig} if kubeconfig else {})},
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


def cmd_stack_refresh(args: argparse.Namespace) -> int:
    """`stack refresh` : resynchronise l'état RÉEL de la stack active depuis le réel.

    Calque `pulumi refresh` : lit les VMs Lima (`limactl`) + les nœuds k8s (`kubectl`)
    et CLASSE (classify_refresh, pur) l'état de la stack active : VMs présentes, VMs
    ORPHELINES (réelles mais hors stack → à détruire d'abord), VMs manquantes (à créer),
    nœuds Ready. Read-only : ne STOCKE aucun state (ADR 0056 §7), ne lance rien. Code 0
    toujours (informatif). C'est la base que `preview` consomme pour dire quoi détruire
    avant d'installer."""
    path = _resolve(args.file)
    topo = load_topology(path)
    stack = topo.catalog.get("topology", "—")
    declared = topo.control_nodes + topo.worker_nodes
    state = classify_refresh(stack, declared, _real_vms(), _ready_nodes())

    print(f"stack : {stack}  (état réel lu — non stocké, ADR 0056 §7)")
    if state.vms_orphan:
        print(
            f"  ⚠ VMs ORPHELINES (hors stack, à détruire d'abord) : {', '.join(state.vms_orphan)}"
        )
    print(f"  VMs de la stack présentes : {', '.join(state.vms_present) or '—'}")
    print(f"  VMs à créer (déclarées, absentes) : {', '.join(state.vms_missing) or '—'}")
    print(f"  nœuds k8s Ready : {', '.join(state.nodes_ready) or '—'}")
    if state.is_empty:
        print("→ terrain vierge (aucune VM) — montage propre depuis zéro.")
    elif state.must_destroy_first:
        print("→ détruire les VMs orphelines avant un montage propre de cette stack.")
    return 0


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
        ["bash", os.path.join(_ROOT, "test", "lima", "run-phases.sh"), "down", *targets],
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
    """Routeur du groupe `stack` (new | ls | select | validate | refresh). Façade de dispatch.

    Calque `pulumi stack`. argparse garantit `stack_cmd` ∈ {new, ls, select, validate, refresh}
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


def cmd_status(args: argparse.Namespace) -> int:
    """État VOULU (lu depuis topology.yaml) ; --real délègue l'état réel à state.sh.

    Sans --real : résumé de l'intention (nœuds, HA, backend, profil, exposition,
    kind). Avec --real : subprocess vers bootstrap/state.sh (lecture seule, on ne
    le réimplémente pas) en héritant l'environnement (EXPECT_CLUSTER/SSH_OPTS) ;
    on ré-émet sa sortie et on PROPAGE son code (0/1/2 déjà alignés).
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    # Hyperconvergence : un nœud control qui porte aussi `worker` schedule des pods
    # mais vit dans control_nodes (pas worker_nodes) — on l'annote pour que
    # `workers: —` ne donne pas l'illusion d'un cluster sans capacité de calcul.
    hc = set(topo.hyperconverged_nodes)
    control_disp = ", ".join(
        f"{n}+worker" if n in hc else n for n in topo.control_nodes
    )
    workers_disp = ", ".join(topo.worker_nodes) or (
        "— (control hyperconvergés schedulent)" if hc else "—"
    )
    lines = [
        f"topologie       : {topo.catalog.get('topology', '—')} (kind={topo.target_kind})",
        f"control-planes  : {control_disp or '—'}"
        f"{'  [HA → VIP requise]' if topo.is_ha_control_plane else ''}",
        f"workers         : {workers_disp}",
        f"profil          : {topo.catalog.get('profile', 'base')}",
        f"stockage        : {topo.storage.get('backend', 'local-path')}",
        f"exposition      : {topo.exposition.get('mode', '—')}",
    ]
    print("\n".join(lines))
    if not args.real:
        return 0
    # État réel : déléguer à state.sh (SSH+kubectl). Hérite l'env du shell.
    # Les hôtes interrogés sont ceux de la TOPO ACTIVE (control + workers dérivés),
    # pas la liste codée en dur de state.sh (cp1 node1 node2 node3) — sinon `--real`
    # constate une réalité décorrélée du déclaré (ADR 0056). `--hosts` force une
    # liste explicite (diagnostic ciblé). control_nodes d'abord (le 1er porte kubectl).
    hosts = args.hosts or (topo.control_nodes + topo.worker_nodes)
    # shell=False : `hosts` est passé LITTÉRALEMENT à bash (pas d'expansion shell),
    # donc pas d'injection même si --hosts vient de la ligne de commande.
    cmd = ["bash", _STATE_SH, *hosts]
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


def _run_for_target(runs, target: str | None):
    """Le run de référence pour un chemin : le dernier de ce `target` si l'historique
    porte le champ, sinon le dernier run global (rétrocompat — mêmes phases/fraîcheur
    servent au diff). Garantit que diff et fraîcheur s'appuient sur LE MÊME run."""
    run = last_run_for_target(runs, target) if target else None
    return run if run is not None else latest_run(runs)


def cmd_preview(args: argparse.Namespace) -> int:
    """`preview` : montre le PLAN complet (voulu → réel) sans rien appliquer.

    Calque `pulumi preview`. Confronte la stack active au RÉEL (VMs Lima existantes
    → ce qu'il faut DÉTRUIRE d'abord) ET liste TOUTE la séquence de couches à monter,
    chacune avec son libellé MÉTIER (phase_label) et son état :
    - `- détruire`  : VMs orphelines d'une autre stack (à retirer avant un montage propre) ;
    - `+ à installer`: couche jamais montée (stack neuve — on n'a JAMAIS joué l'inédit) ;
    - `~ à rejouer`  : couche d'un run PÉRIMÉ (déjà montée mais run plus frais) ;
    - `✓ à-jour`     : couche présente et fraîche.

    Read-only : ne LANCE rien, ne DÉTRUIT rien (`next --apply` applique ; détruire = down/
    destroy). Code 0 toujours (informatif) ; chemin incohérent avec le backend → usage (2).
    Là où `next` ne montre QUE le 1er drift, `preview` montre le plan ENTIER.
    """
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
    # Le run de référence est celui de CETTE stack (match par nom, PAS de retombée
    # sur le dernier run global) : une stack jamais montée (status: cible, aucun run
    # à son nom) n'hérite pas du verdict d'une autre topologie — tout est à installer.
    run = last_run_for_topology(runs, stack_name)
    freshness, _ = verdict_for_run(run, resolved_target, now)
    done = set(run.phases) if run is not None else set()
    a_appliquer = set(diff_phases(seq, done, freshness))
    # jamais monté ≠ rejeu : `jamais` (aucun run de la stack) → « à installer » (inédit) ;
    # `perime` (run existant mais plus frais) → « à rejouer ».
    rejeu = freshness == "perime"
    inedit = freshness == "jamais"

    # État réel : les VMs ORPHELINES (d'une autre stack) à détruire AVANT un montage propre.
    declared = topo.control_nodes + topo.worker_nodes
    real = classify_refresh(stack_name, declared, _real_vms(), [])

    print(f"stack : {stack_name}  →  chemin : {resolved_target}")
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
        suffix = "" if inedit else " — `next --apply` pour la 1re couche"
        print(f"→ {' ; '.join(head)} (rien lancé{suffix}).")
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    """Suggère la prochaine phase (diff voulu − réel) ; --apply la LANCE (ADR 0063).

    Sans --apply : lecture informative, code 0 (la suggestion « il manque X » N'EST
    PAS un échec — c'est le travail de `next`). Avec --apply : délègue à la couche
    ansible-runner isolée (runner.launch_phase) ; décision humaine explicite (G2),
    code propagé du run. JAMAIS d'auto-apply ni d'enchaînement de la séquence.
    """
    path = _resolve(args.file)
    topo = load_topology(path)
    runs = load_runs(args.history or _RUNS_HISTORY)
    now = int(dt.datetime.now(tz=dt.UTC).timestamp())
    target = args.target  # None → plan.default_target le déduit
    run = _run_for_target(runs, target)
    etat_frais, _ = verdict_for_run(run, target, now)
    done = set(run.phases) if run is not None else set()
    run_params = derive_run_params(topo)
    try:
        sugg = suggest_next(topo, target, done, etat_frais, run_params=run_params)
    except PlanError as exc:
        raise _UsageError(str(exc)) from exc

    print(sugg.message)
    if sugg.phase is None:
        return 0
    if not args.apply:
        print(f"  pour lancer : topology.py next --target {sugg.target} --apply")
        return 0

    # --apply : décision humaine explicite. La phase doit avoir un playbook unitaire.
    if sugg.playbook is None:
        raise _UsageError(
            f"la phase `{sugg.phase}` n'est pas un play unitaire lançable "
            "(déléguée au chemin nommé run-phases.sh) — la lancer via run-phases.sh"
        )
    private_data_dir = os.path.join(_ROOT, "bootstrap")
    inventory = os.path.join(private_data_dir, "hosts.yaml")
    ansible_cfg = os.path.join(private_data_dir, "ansible.cfg")
    # L'inventaire réel est gitignoré (ADR 0023) — sans lui, ansible-runner
    # prendrait le chemin pour un nom d'hôte (erreur cryptique). On l'arrête net
    # avec un message qui pointe vers l'exemple versionné.
    if not os.path.exists(inventory):
        raise _UsageError(
            f"inventaire absent : {os.path.relpath(inventory, _ROOT)} "
            "— le générer (`topology.py generate -o bootstrap/hosts.yaml`) "
            "ou le copier depuis bootstrap/hosts.example.yaml"
        )
    playbook = os.path.relpath(os.path.join(_ROOT, sugg.playbook), private_data_dir)
    print(f"→ lancement de {sugg.phase} ({sugg.playbook}) via ansible-runner…")
    try:
        result = _runner.launch_phase(
            playbook,
            sugg.run_params,
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
    return 0 if result.rc == 0 else 1


def cmd_ha_3cp(args: argparse.Namespace) -> int:
    """Orchestre le montage HA `ha-3cp` (ADR 0047/0055, #250) — la partie ANSIBLE.

    Les VM (limactl) et la CNI restent à run-phases.sh (orchestration de CLI, bash,
    ADR 0049) ; cette commande reçoit `--cp-ip/--vip/--vip-iface` déjà dérivés du
    banc, câble `ha.run_ha_3cp` au RÉEL : `launch` → runner.launch_phase (le MÊME
    montage que `next --apply`), gates → limactl/kubectl, `run_cni` → un rappel vers
    run-phases.sh. La logique (séquence, super-admin→admin, gates etcd) est testée
    sans banc (tests/test_ha.py) ; ce câblage est la seule I/O réelle.
    """
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
            ["bash", os.path.join(_ROOT, "test", "lima", "run-phases.sh"), *cmd],
            check=False,
        ).returncode

    def set_inventory(control_hosts: list[str]) -> None:
        # L'écriture d'inventaire reste du bash (write_inventory, format byte-stable).
        # On réécrit l'inventaire avec les CP membres (primaire en tête) avant un join.
        rc = _runphases("ha-inventory", ",".join(control_hosts))
        if rc != 0:
            raise _ha.HaError(f"réécriture de l'inventaire (control={control_hosts}) en échec")

    # run_cni : la CNI reste portée par run-phases.sh (bash). On la rappelle via le
    # sous-commande dédiée `ha-cni <vip-iface> <lb-prefix>` (cf. dispatch).
    def run_cni():
        rc = _runphases("ha-cni", args.vip_iface, args.cp_ip.rsplit(".", 1)[0])
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


def cmd_metrics(args: argparse.Namespace) -> int:
    """Expose les métriques DÉJÀ consignées dans runs-history.yaml (P6, exig. 8).

    LIT et met en forme (durées + cpu_core_s/ram_*) — ne mesure rien de neuf
    (mesurer = le banc via metrology.sh). Read-only, code 0 toujours (informatif).
    """
    runs = load_runs(args.history or _RUNS_HISTORY)
    if not runs:
        print("aucun run consigné — pas de métriques à exposer.")
        return 0
    selected = [latest_run(runs)] if args.last else runs
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


# Verbes du groupe `stack` (calque `pulumi stack` : ls | select | validate).
_STACK_DISPATCH = {
    "new": cmd_stack_new,
    "ls": cmd_stack_ls,
    "select": cmd_stack_select,
    "validate": cmd_stack_validate,
    "refresh": cmd_stack_refresh,
}

_DISPATCH = {
    "stack": cmd_stack,  # calque `pulumi stack` (new | ls | select | validate)
    "destroy": cmd_destroy,  # calque `pulumi destroy`
    "generate": cmd_generate,
    "diff": cmd_diff,
    "status": cmd_status,
    "epreuves": cmd_epreuves,
    "runs": cmd_runs,
    "preview": cmd_preview,
    "next": cmd_next,
    "metrics": cmd_metrics,
    "smoke": cmd_smoke,
    "roundtrip": cmd_roundtrip,
    "ha-3cp": cmd_ha_3cp,
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
        help="gère les stacks (new | ls | select | validate | refresh) — calque `pulumi stack`",
    )
    stack_sub = p_stack.add_subparsers(dest="stack_cmd", required=True)

    p_stack_new = stack_sub.add_parser(
        "new", help="crée une topologie (stack) dans le catalogue via un assistant"
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

    stack_sub.add_parser("ls", help="liste le catalogue, marque l'active (★) + chemin dérivé")

    p_stack_sel = stack_sub.add_parser(
        "select", help="active une stack existante (repointe le symlink topology.yaml)"
    )
    p_stack_sel.add_argument(
        "name", help="nom de l'entrée du catalogue (ex : 3-nodes-1-cp, socle.example)"
    )

    p_stack_val = stack_sub.add_parser("validate", help="valide le schéma d'une topologie")
    _add_file(p_stack_val)

    p_stack_ref = stack_sub.add_parser(
        "refresh", help="resynchronise l'état réel (VMs Lima + nœuds k8s) — calque `pulumi refresh`"
    )
    _add_file(p_stack_ref)

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

    p_prev = sub.add_parser(
        "preview", help="montre le plan complet voulu→réel sans appliquer (calque `pulumi preview`)"
    )
    _add_file(p_prev)
    p_prev.add_argument(
        "--target", default=None, help="chemin nommé visé (défaut : déduit de la stack active)"
    )
    p_prev.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : test/lima/)"
    )

    p_destroy = sub.add_parser(
        "destroy", help="détruit les VMs de la stack active (calque `pulumi destroy`)"
    )
    _add_file(p_destroy)
    p_destroy.add_argument(
        "--yes", action="store_true", help="sauter la confirmation (requis hors TTY pour détruire)"
    )

    p_next = sub.add_parser("next", help="suggère la prochaine phase (et --apply la lance)")
    _add_file(p_next)
    p_next.add_argument(
        "--target", default=None, help="chemin nommé visé (défaut : déduit du profil+backend)"
    )
    p_next.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : test/lima/)"
    )
    p_next.add_argument(
        "--apply",
        action="store_true",
        help="LANCER la phase suggérée via ansible-runner (décision humaine, ADR 0063)",
    )

    p_met = sub.add_parser("metrics", help="expose les métriques consignées (durées, cpu/ram)")
    p_met.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")
    p_met.add_argument("--last", action="store_true", help="seulement le dernier run")
    p_met.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : test/lima/)"
    )

    p_smk = sub.add_parser("smoke", help="smoke-test de réversibilité (créer→vérifier→détruire)")
    p_smk.add_argument("--no-input", action="store_true", help="mode non interactif (CI)")
    p_smk.add_argument(
        "--namespace", default=None, help="nom du namespace jetable (défaut : topology-smoke)"
    )

    p_rt = sub.add_parser(
        "roundtrip",
        help="round-trip d'une couche + sa clôture : détruire→vérifier→reconstruire→vérifier",
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

    p_ha = sub.add_parser(
        "ha-3cp",
        help="orchestre le montage HA ha-3cp (Ansible via Python ; VM/CNI restent run-phases.sh)",
    )
    p_ha.add_argument("--nodes", default="cp1,cp2,cp3", help="CP, le 1er = primaire (csv)")
    p_ha.add_argument("--cp-ip", required=True, dest="cp_ip", help="IP réelle du CP primaire")
    p_ha.add_argument("--vip", required=True, help="VIP de l'API (kube-vip)")
    p_ha.add_argument("--vip-iface", required=True, dest="vip_iface", help="interface L2 de la VIP")
    p_ha.add_argument("--inventory", default="hosts.yaml", help="inventaire (relatif à bootstrap/)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
