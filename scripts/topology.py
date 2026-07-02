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
  uv run python scripts/topology.py artifact generate [--kind prod|bench] [--what …]
  uv run python scripts/topology.py artifact diff [--kind prod|bench --against PATH]
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
import base64
import contextlib
import datetime as dt
import difflib
import glob
import json
import os
import shlex
import subprocess
import sys
import tempfile
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
    ceph_wipe_env,
    classify_refresh,
    compute_plan_state,
    consumes_storage,
    default_target,
    derive_run_params,
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
from nestor import access as _access  # noqa: E402
from nestor import bootstrap as _bootstrap  # noqa: E402
from nestor import discover as _discover  # noqa: E402
from nestor import graph as _graph  # noqa: E402
from nestor import isolation as _isolation  # noqa: E402
from nestor import kube_context as _kube_context  # noqa: E402
from nestor import path as _path  # noqa: E402
from nestor import prod_target as _prod_target  # noqa: E402
from nestor import refresh_fuse as _refresh_fuse  # noqa: E402
from nestor import refresh_plan as _refresh_plan  # noqa: E402
from nestor import roundtrip as _roundtrip  # noqa: E402
from nestor import runner as _runner  # noqa: E402
from nestor import runrecord as _runrecord  # noqa: E402
from nestor import scale as _scale  # noqa: E402
from nestor import seed as _seed  # noqa: E402
from nestor import smoke as _smoke  # noqa: E402
from nestor.history import (  # noqa: E402
    FRESHNESS_OBLIGATOIRES,
    FRESHNESS_OPTIONNELS,
    SEUIL_GLOBAL_DEFAUT,
    Run,
    _matches_stack,
    date_from_log_name,
    last_run_for_target,
    last_run_for_topology,
    latest_run,
    path_freshness,
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
_RUNS_DIR = os.path.join(_ROOT, "bench", "lima", "runs")


def _stack_id(path: str) -> str:
    """Identité de STACK = nom de FICHIER de la topologie (ADR 0102 volet B), source
    UNIQUE de l'identité SYSTÈME (kubeconfig `.kubeconfigs/<stack>.config` + contexte
    kubectl nommé). PUR (os.path seulement, ne lit AUCUN champ YAML → robuste à une
    topo illisible).

    On RÉSOUT le symlink d'abord (`os.path.realpath`) : `topology.yaml` (le symlink
    d'activation) pointe la topo active — sans realpath, son basename serait `topology`,
    jamais `ceph`. Puis on retire l'extension COMPOSÉE `.example.yaml` (modèle générique
    versionné, ADR 0023) AVANT `.yaml`/`.yml` (ordre critique : sinon `ceph.example.yaml`
    → `ceph.example`). Conséquence VOULUE : `ceph.example.yaml` et `ceph.yaml` (surcharge
    locale) partagent le MÊME `stack_id` `ceph` — c'est UNE stack, deux variantes de contenu
    (une seule active à la fois).

    NB : distinct de `catalog.topology` (désormais un champ DESCRIPTIF : la classe de topo,
    `multi-node-3`…) qui, lui, reste la clé de l'HISTORIQUE de runs (jamais réécrit, ADR 0052 ;
    réconcilié en lecture via `history.STACK_ID_ALIASES`)."""
    base = os.path.basename(os.path.realpath(path))
    for suffix in (".example.yaml", ".example.yml", ".yaml", ".yml"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


# Kubeconfig d'un banc = `.kubeconfigs/<stack>.config` (ADR 0102 volet B) : un banc EST une
# stack (nommée par le FICHIER de sa topologie, cf. `_stack_id`) ; son kubeconfig vit à
# l'emplacement UNIQUE nommé par la stack (in-repo, gitignoré fail-safe), UNIFORME banc ET
# prod (la prod le fait déjà : `.kubeconfigs/dirqual.config`). Écrit par run-phases.sh
# (KUBECONFIG_LOCAL, qui reçoit CE chemin par env — Python décide, bash l'utilise, ADR 0102).
# `preview` lit l'état RÉEL du cluster via kubectl ; sans KUBECONFIG exporté, il retombe
# ICI (sinon il interroge ~/.kube/config — pas le banc — et voit 0 nœud Ready alors que
# le socle est monté : faux « à installer », scorie de fidélité du RÉEL).
def _bench_kubeconfig_path(stack: str | None) -> str:
    """Chemin du kubeconfig d'un banc, NOMMÉ PAR LA STACK (ADR 0102 volet B) :
    `.kubeconfigs/<stack>.config`. `stack=None` (aucune stack activée) → fallback "banc"
    (le banc générique historique). Uniforme banc ET prod (prod = `dirqual.config`)."""
    return _prod_target.default_kubeconfig_path(stack or "banc", repo_root=_ROOT)


# Inventaire Ansible du BANC Lima, écrit par run-phases.sh (write_inventory → WORKDIR/
# inventory.yaml ; target_kind: bench, hôtes node1/node2). DISTINCT de bootstrap/hosts.yaml
# (l'inventaire PROD). `next` doit viser CELUI-CI pour une topo lima — sinon un montage
# banc SSH sur la prod (faille ADR 0053). Choisi par `_inventory_for(topo)`.
_BENCH_INVENTORY = os.path.join(_ROOT, "bench", "lima", ".work", "inventory.yaml")
# Manifestes de la code-location JOUET poussés dans Gitea par le seed banc (Contents API ;
# step `push-code-location`, parité gitea-init.sh:SAMPLE_DIR). VERSIONNÉS dans le dépôt (pas
# dans le pod) → on les LIT côté hôte puis on les base64-encode côté Python (le `base64` du
# bash agissait sur l'hôte aussi : le fichier n'est pas dans le pod gitea).
_SEED_SAMPLE_DIR = os.path.join(_ROOT, "bench", "lima", "atlas-workflow-sample")
# Borne l'attente du scan réel (preview/up) sur limactl/kubectl : un cluster injoignable ou
# un démon Lima bloqué ne doit JAMAIS figer le refresh (un `limactl shell`/SSH peut pendre
# indéfiniment sans borne — sous-process qui ne rend jamais la main, constaté au banc).
_REFRESH_TIMEOUT_S = 8


def _warn(message: str) -> None:
    """Avertissement sur STDERR, en JAUNE GRAS si stderr est un terminal (sinon brut,
    pour ne pas polluer pipes/CI). Même convention que `warn()` de bench/lima/lib.sh."""
    if sys.stderr.isatty():
        print(f"\033[1;33m⚠ {message}\033[0m", file=sys.stderr)
    else:
        print(f"⚠ {message}", file=sys.stderr)


def _bench_kubeconfig(declared: str | None = None) -> str:
    """Le kubeconfig que `cluster` doit RÉELLEMENT utiliser, par priorité (ADR 0053/0090) :

    1. `KUBECONFIG` exporté → intention EXPLICITE de l'opérateur (respectée) ;
    2. `declared` = `kubeconfig:` de la topologie (ADR 0090) → cible DÉCLARÉE pour
       une stack prod, source de vérité (expansion `~`) ;
    3. le banc Lima s'il existe → la cible nominale de l'outil ;
    4. sinon → `/dev/null` (kubeconfig VIDE), JAMAIS `~/.kube/config`.

    Le point (4) est le correctif de fond (ADR 0053) : `cluster` ne retombe PAS
    silencieusement sur le contexte du poste (= la prod). Pointer `/dev/null` fait
    échouer kubectl proprement → lectures « vides » (honnête), au lieu de lire/muter
    la prod par accident. Le point (2) (ADR 0090) ajoute la cible prod déclarée :
    une stack prod vise SON kubeconfig (`~/.kube/<stack>.config`), pas le banc."""
    explicit = os.environ.get("KUBECONFIG")
    if explicit:
        return explicit
    if declared:
        return os.path.expanduser(declared)
    # Banc de la STACK ACTIVE (ADR 0102 volet B) : `.kubeconfigs/<stack>.config` — pas de
    # topo en scope ici (résolveur nu), on lit la stack activée (`topology.yaml` → stack_id).
    bench = _bench_kubeconfig_path(_active_stack_name(None))
    if os.path.exists(bench):
        return bench
    return os.devnull  # vide : kubectl échoue → "pas de banc", jamais la prod


def _operator_kubeconfig() -> str | None:
    """Le `KUBECONFIG` de l'ENV s'il est RÉELLEMENT EXPLOITABLE, sinon `None`.

    Un `KUBECONFIG` exporté matérialise une intention opérateur PRIORITAIRE (ADR 0090) —
    MAIS seulement s'il pointe un kubeconfig utilisable. `/dev/null` (garde ADR 0053 :
    `nestor stack select` sur un banc absent pose `export KUBECONFIG=/dev/null`, souvent
    `eval`é dans le shell), un fichier VIDE ou INEXISTANT sont des valeurs « poison » :
    truthy pour un `or`, mais inutilisables pour un play (le module k8s d'Ansible lève
    « Invalid kube-config. /dev/null file is empty »). On les traite comme ABSENTS → le
    `or` du site d'appel retombe sur le kubeconfig banc rapatrié (`ctx.kubeconfig_local`),
    au lieu de laisser `/dev/null` faire échouer une phase alors que le banc est joignable.

    Rend le chemin uniquement s'il existe ET n'est pas vide (donc jamais `/dev/null`,
    qui a une taille de 0). Sinon `None` (intention non exploitable → défaut du site)."""
    kc = os.environ.get("KUBECONFIG")
    if not kc:
        return None
    try:
        usable = os.path.getsize(kc) > 0  # exclut /dev/null (0) et un fichier vide
    except OSError:
        return None  # inexistant / illisible → non exploitable
    return kc if usable else None


def _kubectl_env(declared: str | None = None) -> dict[str, str]:
    """Env pour un appel kubectl : force KUBECONFIG vers la cible sûre
    (`_bench_kubeconfig`) — jamais le ~/.kube/config implicite de la prod. `declared`
    = `kubeconfig:` de la topologie (ADR 0090), propagé pour viser une cible prod."""
    return {**os.environ, "KUBECONFIG": _bench_kubeconfig(declared)}


def cmd_kubectl(args: argparse.Namespace) -> int:
    """`nestor kubectl <args…>` : lance kubectl sur la cible de la STACK ACTIVE.

    Remplaçant ergonomique de l'ancien `nestor env` (supprimé LOT 8) : au lieu d'imprimer
    `export KUBECONFIG=<banc>` à `eval`, `nestor` EXÉCUTE kubectl avec le bon kubeconfig —
    résolu par `_bench_kubeconfig` (ADR 0053/0090 : KUBECONFIG explicite → `kubeconfig:` de
    la topo → banc Lima → `/dev/null`, JAMAIS `~/.kube/config` = la prod par accident). Donc
    `nestor kubectl get pods -A` vise TOUJOURS la cible déclarée, sans manipuler l'env du
    shell. Les arguments résiduels sont passés tels quels à kubectl (passthrough).

    Code = celui de kubectl. Pas de cible sûre (banc absent, prod sans `kubeconfig:`) →
    `_bench_kubeconfig` rend `/dev/null` et kubectl échoue proprement (honnête, ADR 0053).

    NB : `main()` pose un KUBECONFIG=banc par DÉFAUT (`_default_kubeconfig_to_bench`) pour
    les sondes « état réel ». Ce défaut AUTO (≠ intention opérateur, `_KUBECONFIG_AUTO_BENCH`)
    NE doit PAS écraser la cible DÉCLARÉE de la stack : si la stack prod est active, `nestor
    kubectl` doit viser la PROD (sinon il taperait le banc même prod sélectionnée). On
    neutralise donc le défaut auto avant de résoudre depuis la topo (un KUBECONFIG posé
    EXPLICITEMENT par l'opérateur, lui, reste prioritaire — intention respectée, ADR 0090)."""
    topo = load_topology(_resolve(args.file))
    if _KUBECONFIG_AUTO_BENCH:
        # défaut posé par nestor lui-même → on le retire pour que _bench_kubeconfig résolve
        # la cible DÉCLARÉE (prod via topo.kubeconfig), pas le banc auto.
        os.environ.pop("KUBECONFIG", None)
    env = _kubectl_env(topo.kubeconfig)
    passthrough = list(getattr(args, "kubectl_args", []) or [])
    # Retire un `--` de tête résiduel : le passthrough est DÉJÀ brut (`_split_passthrough`),
    # un `nestor kubectl -- -n …` explicite ne doit pas transmettre le `--` à kubectl (qui
    # l'interpréterait comme « fin des options » et afficherait l'aide).
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    proc = subprocess.run(  # noqa: S603 — kubectl + args opérateur, cible sûre (env)
        ["kubectl", *passthrough], env=env, check=False
    )
    return proc.returncode


def _resolve_playbook(name: str) -> str:
    """Chemin absolu d'un playbook : accepte `checks.yaml` (→ bootstrap/checks.yaml)
    ou un chemin déjà relatif au dépôt (`bootstrap/checks.yaml`, `bootstrap/security/secure.yml`).
    `_UsageError` (code 2) si introuvable — AVANT de dériver le moindre inventaire."""
    for candidate in (name, os.path.join("bootstrap", name)):
        path = os.path.join(_ROOT, candidate)
        if os.path.isfile(path):
            return path
    raise _UsageError(f"playbook introuvable : {name} (ni {name} ni bootstrap/{name})")


def cmd_ansible(args: argparse.Namespace) -> int:
    """`nestor ansible <playbook> [args ansible…]` : lance un playbook sur la STACK ACTIVE
    avec un inventaire DÉRIVÉ de la topologie — jamais un inventaire statique pointable.

    Source unique d'inventaire (ADR 0098) : `bootstrap/hosts.yaml` n'existe plus. Au lieu de
    `ansible-playbook -i bootstrap/hosts.yaml <play>` (le vecteur de l'incident Rook-Ceph),
    on dérive l'inventaire de la topo active (`render_prod_inventory`/`render_lima_inventory`)
    dans un TEMPORAIRE, on passe le garde `_assert_inventory_safe` (Python, AVANT ansible —
    le filet décisif d'isolation banc/prod, ADR 0053), on pose `EXPECTED_TARGET_KIND` pour
    réarmer l'assert audit-log par-play, on lance, et on nettoie le temp en `finally`.

    Les arguments résiduels (`--limit cp1`, `--tags os`, `--check`, `-e k=v`…) sont passés
    tels quels à ansible-playbook. Code de sortie = celui d'ansible-playbook.
    """
    topo = load_topology(_resolve(args.file))
    playbook_abs = _resolve_playbook(args.playbook)
    passthrough = list(getattr(args, "ansible_args", []) or [])

    # Inventaire DÉRIVÉ de la cible active (`_inventory_for` : temp éphémère côté prod,
    # fichier réel côté banc) — jamais un `hosts.yaml` statique (ADR 0098).
    with _inventory_for(topo) as inv_path:
        if topo.target_kind == "bench" and not os.path.isfile(inv_path):
            raise _UsageError(
                f"inventaire banc absent ({inv_path}) — monter le banc d'abord (`nestor up`)"
            )
        # Garde d'isolation (ADR 0053) AVANT ansible : refuse un inventaire qui SSHerait
        # sur une cible non conforme à l'intention déclarée (topo.target_kind).
        _assert_inventory_safe(f"nestor ansible ({args.playbook})", inv_path, topo)
        env = {
            **os.environ,
            "EXPECTED_TARGET_KIND": topo.target_kind,
            "ANSIBLE_CONFIG": os.path.join(_ROOT, "bootstrap", "ansible.cfg"),
        }
        proc = subprocess.run(  # noqa: S603 — playbook du dépôt + args opérateur, inventaire sûr
            ["ansible-playbook", "-i", inv_path, playbook_abs, *passthrough],
            cwd=os.path.join(_ROOT, "bootstrap"),
            env=env,
            check=False,
        )
        return proc.returncode


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
    """Identité (`stack_id`, ADR 0102 volet B) de la stack ciblée : le NOM DE FICHIER de
    la topologie (`ceph`), pas `catalog.topology` (`multi-node-3`, désormais descriptif).

    `-f` explicite → la topo donnée ; sinon la stack active (le symlink `topology.yaml`).
    On NE retombe PAS sur l'exemple silencieusement : si aucune stack n'est activée, renvoie
    None (l'appelant bascule sur la vue globale). Purement dérivé du CHEMIN (`_stack_id`,
    `realpath` résout le symlink) — plus de `load_topology` : l'identité est le nom de
    fichier, pas un champ YAML. Un chemin absent → None.

    Sert de clé au kubeconfig/contexte ET aux artefacts d'historique (`runs`/`metrics`) —
    l'historique keyé par l'ancien `catalog.topology` est réconcilié en LECTURE via
    `history.STACK_ID_ALIASES` (jamais réécrit, ADR 0052)."""
    path = (
        file_arg if file_arg else (_DEFAULT_TOPOLOGY if os.path.exists(_DEFAULT_TOPOLOGY) else None)
    )
    if path is None:
        return None
    return _stack_id(path)


def _render_inventory(topo, kind: str, lima_home: str | None) -> str:
    """Rend l'inventaire selon le `kind` (prod ou lima). Façade sur le paquet."""
    if kind == "bench":
        if not lima_home:
            raise _UsageError("--kind bench exige --lima-home (chemin du $HOME du poste)")
        return render_lima_inventory(topo, lima_home)
    return render_prod_inventory(topo)


@contextlib.contextmanager
def _inventory_for(topo: Topology):
    """Gestionnaire de contexte qui YIELD le chemin de l'inventaire de la TOPOLOGIE
    active (ADR 0053), DÉRIVÉ et éphémère côté prod (ADR 0098).

    Le cœur de l'isolation : un montage vise l'inventaire de SA cible —
    `bench/lima/.work/inventory.yaml` (target_kind: bench, posé par le provisioning banc)
    pour une topo lima ; pour la prod, un TEMPORAIRE `mkstemp` (`0o600`) rendu depuis la
    topo (`render_prod_inventory`) et supprimé en sortie. Plus de `bootstrap/hosts.yaml`
    statique pointable (ADR 0098 : source unique d'inventaire ; le fichier persistant
    était le vecteur de l'incident Rook-Ceph). Sans ce choix d'inventaire, un montage
    SSHait TOUJOURS sur la prod codée en dur (faille constatée). La garde
    `_assert_inventory_safe` reste le filet en aval.

    Usage : `with _inventory_for(topo) as inv_path: …`. Le banc rend un chemin réel
    (non supprimé) ; la prod un temp anonyme supprimé en `finally`. Le temp prod doit
    vivre toute la durée du geste (montage entier pour `cmd_up`) → enrouler le `with`
    autour de TOUT le geste, pas juste de l'appel ansible."""
    if topo.target_kind == "bench":
        yield _BENCH_INVENTORY
        return
    rendered = _render_inventory(topo, "prod", None)
    fd, tmp = tempfile.mkstemp(prefix="nestor-inv-", suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(rendered)
    os.chmod(tmp, 0o600)
    try:
        yield tmp
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


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
    hint = "OUI/non" if default else "oui/NON"
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

    `choix` est ordonné selon le chemin (le 1er = ordre conventionnel). `libelle(phase)`
    rend le texte humain affiché. Renvoie la phase choisie, ou None si l'opérateur annule.

    Principe « par défaut, nestor ne fait rien » : en interactif (TTY), une Entrée vide
    ANNULE (renvoie None) — PLUS de « défaut 1 ». L'opérateur DOIT choisir un numéro.

    Sous `no_input`, le seul appelant (`cmd_next`) ne l'active QUE pour `--yes` (hors TTY
    SANS --yes, il refuse AVANT d'atteindre le menu) : `--yes` est une demande EXPLICITE
    d'agir → on retient l'ordre conventionnel (`choix[0]`), déterministe pour la CI. Le
    « rien par défaut » vaut pour l'interactif ; `--yes` a dit oui."""
    if no_input:
        return choix[0]
    print("Plusieurs couches sont installables maintenant — laquelle monter ?", file=sys.stderr)
    for i, phase in enumerate(choix, 1):
        print(f"  {i}) {libelle(phase)}", file=sys.stderr)
    while True:
        rep = input(f"Numéro [1-{len(choix)}] (Entrée = annuler) : ").strip()
        if not rep:
            return None
        if rep.isdigit() and 1 <= int(rep) <= len(choix):
            return choix[int(rep) - 1]
        print(
            f"    réponds un numéro entre 1 et {len(choix)} (ou Entrée pour annuler)",
            file=sys.stderr,
        )


def _activate_symlink(target_rel: str) -> None:
    """Repointe le symlink d'activation topology.yaml → <target_rel> (relatif, gitignoré).

    Remplace un lien/fichier existant. Chemin RELATIF au dépôt (le symlink vit à la
    racine, à côté de topologies/) — robuste à un déplacement du clone."""
    link = os.path.join(_ROOT, "topology.yaml")
    if os.path.islink(link) or os.path.exists(link):
        os.unlink(link)
    os.symlink(target_rel, link)  # poste Unix (macOS/Linux) — symlink natif, ADR 0100


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

    # Activation : on la PROPOSE une fois la topo créée plutôt que de l'exiger en flag.
    # `--activate` force le oui sans demander ; `--no-input` ne touche RIEN (défaut False,
    # déterministe en CI). Principe « par défaut, nestor ne fait rien » : Entrée vide =
    # NE PAS activer (le symlink d'activation pointe la PROD ; ne jamais le repointer à
    # l'aveugle). L'opérateur active explicitement (« oui ») ou via `stack select`.
    if args.activate:
        activate = True
    elif args.no_input:
        activate = False
    else:
        activate = _confirm(
            f"Activer `{plan.name}` maintenant (topology.yaml → {plan.target}) ?",
            default=False,
            no_input=False,
        )

    if activate:
        _activate_symlink(plan.target)
        print(f"✓ activée : topology.yaml → {plan.target} (chemin dérivé : {default_target(topo)})")
    else:
        print(f"  pour l'activer : topology.py stack select {plan.name}")
    return 0


def _select_prod_kubeconfig(topo: Topology, topo_path: str, stack: str, *, no_input: bool) -> str:
    """Détermine le kubeconfig d'une stack PROD à l'activation (ADR 0090). Renvoie le
    chemin KUBECONFIG à poser (jamais `~/.kube/config` implicite).

    `stack select` doit rester RAPIDE et NON BLOQUANT (souvent appelé via
    `eval "$(nestor stack select …)"`) : on ne SONDE PAS le réseau et on ne PROMPTE
    PAS ici. Si la topo ne déclare pas `kubeconfig:` (et pas de KUBECONFIG exporté),
    on l'ÉCRIT directement avec la valeur conventionnelle `~/.kube/<stack>.config`
    (ADR 0090 : « nestor corrige la topologie » ; écriture d'un fichier LOCAL, pas du
    cluster — confirmation non requise car valeur déterministe et réversible). Le
    rapatriement éventuel et la vérif d'accès sont du ressort de `preview` (qui les
    PROPOSE quand il lit l'état réel), pas de l'activation."""
    # Un KUBECONFIG pointant le BANC (résidu d'un `nestor env`/select banc) n'est PAS une
    # intention prod : on l'ignore pour une stack prod (sinon on viserait le banc et on
    # n'écrirait pas le champ). Seul un KUBECONFIG vers une AUTRE cible compte comme
    # intention explicite. Le résidu vise le banc de la stack ACTIVE (ADR 0102 volet B :
    # `.kubeconfigs/<stack>.config`) — c'est ce chemin qu'on écarte.
    env_kc = os.environ.get("KUBECONFIG")
    bench_kc = _bench_kubeconfig_path(_active_stack_name(None))
    if env_kc and os.path.abspath(env_kc) == os.path.abspath(bench_kc):
        env_kc = None
    if topo.kubeconfig or env_kc:
        return os.path.expanduser(
            _prod_target.resolve_kubeconfig(
                env_kubeconfig=env_kc, declared=topo.kubeconfig, stack=stack, repo_root=_ROOT
            )
        )
    # Topo sans cible : compléter (déterministe). En --no-input on signale seulement
    # (rester strict en CI : ne pas modifier de fichier versionné/local sans intention).
    default = _prod_target.default_kubeconfig_path(stack, repo_root=_ROOT)
    if no_input:
        _warn(
            f"topologie sans `kubeconfig:` — la déclarer (ex. `{default}`) pour que "
            "`nestor preview` lise l'état réel du cluster prod (ADR 0090)."
        )
        return os.path.expanduser(default)
    with open(topo_path, encoding="utf-8") as f:
        edited = _prod_target.add_kubeconfig_field(f.read(), default)
    with open(topo_path, "w", encoding="utf-8") as f:
        f.write(edited)
    _warn(
        f"`kubeconfig: {default}` ajouté à la topologie « {stack} ». "
        f"Si le fichier n'existe pas encore, `nestor preview` proposera de le rapatrier."
    )
    return os.path.expanduser(default)


def cmd_stack_select(args: argparse.Namespace) -> int:
    """`stack select` : active une topologie EXISTANTE et POSE le KUBECONFIG de la cible.

    Calque `pulumi stack select` : choisit la stack courante parmi le catalogue,
    repointe le symlink `topology.yaml`, POSE un CONTEXTE kubectl nommé `<stack>`
    dans le kubeconfig de la cible (LOT 8, ADR 0097 §3 — remplace `nestor env`), et
    imprime sur STDOUT une ligne `export KUBECONFIG=…` à `eval` dans le shell :

        eval "$(nestor stack select banc)"

    Le KUBECONFIG posé est celui de la cible (ADR 0053) : le **banc de la stack**
    s'il est monté (`.kubeconfigs/banc.config`, ADR 0102 volet B), sinon **`/dev/null`** (vide) —
    JAMAIS `~/.kube/config` (la prod). Un `kubectl`/`cilium` direct dans le shell
    vise alors la bonne cible, ou échoue proprement (« pas de banc »), au lieu de
    taper la prod par accident. Le contexte nommé permet AUSSI `kubectl --context
    <stack> …` sans aucune variable d'env (mécanisme standard k8s). Un process NE
    PEUT PAS exporter dans le shell PARENT (invariant Unix) → le patron `eval`,
    comme `ssh-agent`.

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

    # CONTEXTE kubectl nommé (LOT 8, ADR 0097 §3) : remplace `nestor env`. On pose un
    # contexte `<stack>` dans le kubeconfig de la cible (best-effort, non bloquant) — le
    # mécanisme STANDARD k8s (`kubectl --context <stack>`) supplante l'export de KUBECONFIG.
    _pose_named_context(topo, args.name)

    # PROD (ADR 0090) : la cible n'est pas le banc Lima mais le cluster déclaré. Si la
    # topo ne déclare pas encore son `kubeconfig:`, c'est ICI (à l'activation — déjà une
    # écriture, pas une lecture) qu'on COMPLÈTE la topologie : proposer le champ
    # `~/.kube/<stack>.config` + le rapatriement, puis poser ce KUBECONFIG. Sous
    # `--no-input` : on n'écrit rien (action opérateur), on signale.
    if topo.target_kind != "bench":
        cible = _select_prod_kubeconfig(
            topo, target_abs, args.name, no_input=getattr(args, "no_input", False)
        )
    # BANC : le kubeconfig du banc DE CETTE STACK s'il est monté ET JOIGNABLE, sinon
    # /dev/null (jamais la prod, ADR 0053). Chemin nommé par la stack SÉLECTIONNÉE (ADR 0102
    # volet B : `.kubeconfigs/<stack>.config`, `stack_id` du fichier `target_abs`). On NE
    # supprime PAS le kubeconfig (le détruire casserait l'accès à un banc vivant ; il sera
    # de toute façon réécrit par le prochain up/bootstrap). On vise /dev/null seulement s'il
    # n'existe pas OU ne répond plus (banc d'une autre stack, ou API tombée) —
    # `_context_targets_bench` le sonde sans toucher au fichier.
    elif os.path.exists(bench_kc := _bench_kubeconfig_path(_stack_id(target_abs))) and (
        _kubeconfig_reaches_api(bench_kc)
    ):
        cible = os.path.abspath(bench_kc)
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


def _real_vms(target_kind: str = "bench") -> list[str]:
    """Noms des VMs Lima EXISTANTES (toute stack), via `limactl list --format json`.

    GATÉE par `target_kind` (ADR 0084) : `limactl` n'a de sens qu'en `lima`. Pour une
    topo `prod` (baremetal), il n'existe AUCUNE « VM » créable localement (les nœuds
    préexistent) → on rend `[]` sans lancer `limactl` (sinon `preview` prod listait les
    VMs du banc Lima coexistant comme « orphelines » — faux RÉEL, ADR 0053/0084).

    Lecture seule du réel (ADR 0056 §7 : on ne stocke pas de state, on le lit). Une
    sortie illisible / `limactl` absent → liste vide (le refresh reste informatif,
    il ne plante pas le poste sans Lima)."""
    if target_kind != "bench":
        return []
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


def _ready_nodes(target_kind: str = "bench", declared: str | None = None) -> list[str]:
    """Noms des nœuds k8s à l'état Ready (`kubectl get nodes`). Vide si injoignable.

    GATÉE par `target_kind` (ADR 0084) et la cible déclarée (ADR 0090) :
    - `lima` : kubeconfig sûr (`_kubectl_env` → `KUBECONFIG` exporté, sinon banc, sinon
      VIDE — jamais `~/.kube/config`, ADR 0053). Un banc absent rend une liste vide.
    - `prod` : on sonde si une cible PROD est connue — soit `KUBECONFIG` EXPORTÉ
      explicitement (intention, ADR 0053 (a)), soit `declared` = `kubeconfig:` de la
      topologie (ADR 0090). Sinon `[]` — un `preview` prod sans cible déclarée ne lit
      JAMAIS le kubeconfig banc (qui afficherait `lima-*` Ready à tort) ni
      `~/.kube/config`."""
    # En prod : sonder UNIQUEMENT si une cible prod est connue (KUBECONFIG exporté OU
    # kubeconfig déclaré dans la topo, ADR 0090). `_KUBECONFIG_AUTO_BENCH` distingue le
    # défaut auto-posé vers le BANC par `main()` (≠ intention prod) : un KUBECONFIG
    # auto-banc ne doit PAS faire sonder le banc pour une stack prod (bug #405, ADR 0084).
    explicit_kubeconfig = bool(os.environ.get("KUBECONFIG")) and not _KUBECONFIG_AUTO_BENCH
    if target_kind != "bench" and not explicit_kubeconfig and not declared:
        return []
    try:
        out = subprocess.run(  # noqa: S603 — argv fixe, pas d'entrée shell
            # --request-timeout borne l'attente côté kubectl (cluster injoignable) ;
            # `timeout=` borne le subprocess lui-même (double garde-fou anti-blocage).
            ["kubectl", "get", "nodes", "--no-headers", "--request-timeout=5s"],
            check=False,
            capture_output=True,
            text=True,
            env=_kubectl_env(declared),
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
#   dataops    → Deployment marquez Ready (DERNIER maillon : registry + CNPG + Dagster PUIS
#                Marquez ; avec Dagster seul la couche passait « ✓ » alors que Marquez manquait) ;
#   metrics-server / storage-simple → leur Deployment Ready.
# Format : phase → (kind, name, namespace|None, ready). `ready=True` (workloads) exige
# readyReplicas≥1 ; `ready=False` (Application Argo : CRD sans replicas) = présence.
# Constaté sur le cluster (comme « nœud Ready ») pour que `preview`/`next` reflètent le
# RÉEL — une couche à moitié posée n'est PAS « à-jour ». Miroir des gates de rôles et de
# `gate_pred` (run-phases.sh) — même ressource, même critère Ready.
# 4e champ = critère de SANTÉ : True → readyReplicas≥1 (workload répliqué) ; False →
# présence seule (CRD type Application, ou StorageClass cluster-scoped) ; "phase" →
# status.phase == "Ready" (CR opérateur sans replicas : CephCluster, CephObjectStore Rook).
#
# PROJECTION du GRAPHE (lot 4 refonte nestor) : cette table n'est PLUS définie ici en dur,
# elle DÉRIVE de `nestor.graph` — le signal est porté par le composant qui EST le dernier
# maillon (champ `Component.signal`), et `graph.LAYER_SIGNAL` le projette par phase. UNE
# seule source de vérité, plus DEUX tables à tenir cohérentes (tests/test_graph.py prouve
# l'égalité graph.LAYER_SIGNAL ↔ Component.signal de chaque dernier maillon). Le détail
# humain (POURQUOI tel maillon : Loki absent si SeaweedFS manque, Marquez = dernier de
# dataops, #227 pour ceph/sc/datalake, atlas-workflows ≠ atlas…) vit désormais en commentaire
# sur chaque `signal=` du catalogue `nestor/graph.py`.
_LAYER_SIGNAL: dict[str, tuple[str, str, str | None, bool | str]] = dict(_graph.LAYER_SIGNAL)

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


def _resource_healthy(kind: str, name: str, namespace: str | None, ready: bool | str) -> bool:
    """La ressource est-elle posée ET saine ? Trois critères selon `ready` :
    - `"phase"` → `status.phase == "Ready"` (CR opérateur Rook : CephCluster, CephObjectStore
      — pas de replicas, la santé est dans la phase) ;
    - `True` → workload répliqué, readyReplicas≥1 (le DERNIER maillon : un Loki à 0/1 n'est
      PAS sain) ;
    - `False` → présence seule (CRD type Application, StorageClass cluster-scoped).
    Lecture bornée, fail-closed (toute incertitude → False)."""
    if ready == "phase":
        out = _kubectl_resource(kind, name, namespace, jsonpath="{.status.phase}")
        if out is None or out.returncode != 0:
            return False
        return (out.stdout or "").strip() == "Ready"
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


def _probe_observed_layers(seq: list[str], nodes_ready: list[str]) -> set[str]:
    """Sonde RÉELLE des couches applicatives, partagée par preview/next/up (ADR 0090).

    Renvoie `observed_layers` que `compute_plan_state` consomme : les couches de `seq`
    à signal connu OBSERVÉES saines (kubectl). C'est la moitié du RÉEL (avec le socle)
    dont `done` dérive ENTIÈREMENT depuis la refonte lot 6 (`done` = réel seul) : une
    couche à signal NON confirmée par le réel n'y figure PAS → elle est « à appliquer »
    naturellement (plus de ré-injection ad hoc d'un set `signal_phases`).

    Sonde UNIQUEMENT si le cluster ciblé répond (`nodes_ready`) : sinon `_observed_layers`
    (kubeconfig banc) lirait le banc Lima pour une stack prod sans cible (ADR 0084) — on
    rend alors ∅ (le RÉEL n'a honnêtement rien à dire : tout l'aval est « à appliquer »)."""
    if not nodes_ready:
        return set()
    signal_phases = {p for p in seq if p in _LAYER_SIGNAL}
    return _observed_layers(list(signal_phases))


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

    Garde-fou anti-destruction silencieuse : sur un TTY, on invite l'opérateur (liste
    les VMs) via `_confirm` (hint « oui/NON », défaut False = Entrée vide ne détruit
    RIEN) ; sans TTY (CI/script), on EXIGE --yes (sinon on ne détruit RIEN)."""
    if assume_yes:
        return True
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "destruction refusée hors TTY sans --yes (pas de suppression silencieuse).",
            file=sys.stderr,
        )
        return False
    return _confirm(
        f"⚠️  DÉTRUIRE définitivement les VMs {vms} (+ disques) ?",
        default=assume_yes,
        no_input=assume_yes,
    )


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
    _assert_bench_target("nestor down")
    path = _resolve(args.file)
    topo = load_topology(path)
    stack = _stack_id(path)  # identité = nom de fichier (ADR 0102 volet B)
    declared = topo.control_nodes + topo.worker_nodes
    state = classify_refresh(stack, declared, _real_vms(topo.target_kind), [])
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

    # Délégation à run-phases.sh down <vm…> (bash garde limactl, ADR 0049). On passe l'ENV
    # DÉRIVÉ de la topo (`_runphases_env` → NODES_OVERRIDE) : `phase_down` en dérive les
    # DISQUES déclarés de chaque VM (`node_disk_specs`) pour les supprimer. SANS cet env,
    # NODES est vide côté bash → aucun `lima_disk_delete` → les disques SURVIVENT en silence
    # (« rien ne subsiste » mensonger, vécu au banc ceph : 9 disques orphelins après `down`).
    rc = subprocess.run(  # noqa: S603 — chemin codé, noms de VM contrôlés (topo validée)
        ["bash", os.path.join(_ROOT, "bench", "lima", "run-phases.sh"), "down", *targets],
        check=False,
        env=_runphases_env(topo, stack),
    ).returncode
    if rc != 0:
        print(f"échec de la destruction (run-phases.sh down rc={rc}).", file=sys.stderr)
        return 1
    # Kubeconfig de la stack (ADR 0102 volet B) : le supprimer après les VMs — sinon il reste
    # ORPHELIN (pointe le forward API 127.0.0.1:6443 d'un banc mort) et devient un « KUBECONFIG
    # poison » si `eval`é dans un shell (kubectl tombe sur localhost:8080 / un cluster disparu).
    # Cohérent avec « rien ne subsiste » : la stack détruite ne laisse pas son kubeconfig. Le
    # prochain `up` le réécrit (fetch au bootstrap). N'est retiré QUE pour un banc (garde 0053).
    kubeconfig = _bench_kubeconfig_path(stack)
    removed_kc = ""
    if topo.target_kind == "bench" and os.path.exists(kubeconfig):
        try:
            os.unlink(kubeconfig)
            removed_kc = " + kubeconfig"
        except OSError as exc:
            _warn(f"kubeconfig `{os.path.relpath(kubeconfig, _ROOT)}` non supprimé : {exc}")
    print(f"✓ stack `{stack}` détruite ({len(targets)} VM(s){removed_kc}).")
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
                "--kind bench exige --against (l'inventaire Lima est un artefact de "
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
    # Banc de la stack visée par CETTE commande (ADR 0102 volet B) : `.kubeconfigs/<stack>.config`,
    # `stack_id` du fichier passé (`path`, déjà résolu) — cohérent avec ce que sondent
    # `_ready_nodes`/observed (via `_bench_kubeconfig`, même résolution de stack).
    bench_kc = _bench_kubeconfig_path(_stack_id(path))
    runtime = not args.declared and os.path.exists(bench_kc) and bool(_ready_nodes())
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

    if getattr(args, "run", False):
        return _run_scenarios(jouables, _pretes if runtime else None, full=args.full, topo=topo)
    return 0


# Une épreuve est DESTRUCTIVE/OFFENSIVE si elle touche les nœuds (ssh), attaque (offensif),
# ou est du chaos — réservée à `--full` (+ BANC=1). Les non-destructives (terrain agnostique/
# API : sondes kubectl in-cluster) sont jouées par défaut. Dérivé du modèle, pas codé.
_SCENARIO_DESTRUCTIF_TERRAINS = frozenset({"ssh", "offensif"})


def _run_scenarios(jouables, pretes_fn, *, full: bool, topo) -> int:
    """LANCE les scénarios PRÊTS via bench/scenarios/run-all.sh (ADR 0049 : run-all.sh est
    l'irréductible bash — kubectl/ceph/ssh ; Python le PILOTE, ne le réimplémente pas, #227).

    Sélection DÉRIVÉE : seules les épreuves PRÊTES (couche montée — `pretes_fn`) sont jouées,
    et sans `--full` on exclut les destructives/offensives (terrain ssh/offensif, type chaos).
    `nestor` calcule donc le `ONLY=` au lieu d'un SKIP composé à la main. Garde banc imposée."""
    if pretes_fn is None:
        raise _UsageError(
            "`--run` exige un banc joignable (état réel) — `nestor stack select <banc>` "
            "(pose le contexte), ou monter le banc (`nestor up`)."
        )
    _assert_bench_target("nestor test scenarios --run")
    pretes = [e for e in jouables if pretes_fn(e)]

    def _destructif(e) -> bool:
        return e.terrain in _SCENARIO_DESTRUCTIF_TERRAINS or e.type == "chaos"

    a_jouer = pretes if full else [e for e in pretes if not _destructif(e)]
    if not a_jouer:
        ecartees = [e.num for e in pretes if _destructif(e)]
        suff = f" ({len(ecartees)} destructives/offensives derrière `--full`)" if ecartees else ""
        print(f"→ aucune épreuve prête à jouer{suff}.")
        return 0
    nums = sorted(e.num for e in a_jouer)
    ecartees = [e.num for e in pretes if _destructif(e)] if not full else []
    print(f"Lancement de {len(nums)} scénario(s) prêt(s) via run-all.sh : {' '.join(nums)}")
    if ecartees:
        print(f"  (exclus sans --full : {' '.join(sorted(ecartees))} — destructifs/offensifs)")
    runner = os.path.join(_ROOT, "bench", "scenarios", "run-all.sh")
    env = {**os.environ, "ONLY": " ".join(nums)}
    if full:
        env["BANC"] = "1"  # les gardes banc-only des scénarios offensifs (ADR 0025) l'exigent
    rc = subprocess.run(  # noqa: S603 — chemin codé, ONLY dérivé du modèle (numéros validés)
        ["bash", runner], check=False, env=env
    ).returncode
    if rc == 0:
        print("→ tous les scénarios joués sont PASS. Consigner le run (RESULTS.md, ADR 0042).")
    else:
        print(f"→ au moins un scénario a ÉCHOUÉ (rc={rc}) — voir le tableau ci-dessus.")
    return rc


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


def _freshness_fallback(runs: list, now: int, seuil_global: int) -> int:
    """Repli GLOBAL (ADR 0042 §4) : pas d'historique exploitable → on lit la date du
    log le plus récent sous `runs/<date>-*.log` et on applique le seuil global. Codes :
    0 frais, 1 périmé, 2 aucune preuve. I/O fichier ICI (la dérivation de date est pure)."""
    last_iso = None
    if os.path.isdir(_RUNS_DIR):
        logs = sorted(f for f in os.listdir(_RUNS_DIR) if f.endswith(".log"))
        if logs:
            last_iso = date_from_log_name(logs[-1])
    if last_iso is None:
        print("::warning::Aucune preuve de banc trouvée (ni runs-history.yaml ni runs/*.log).")
        print("Aucun run consigné — lancer `nestor up` (chemin atlas) et committer la preuve.")
        return 2
    # Réutilise path_freshness via un Run synthétique (date seule) sur le chemin global.
    etat, _ = path_freshness(Run(id="repli", date=last_iso), "global", now)
    age_msg = f"dernier log {last_iso} / seuil {seuil_global} j"
    if etat == "frais":
        print(f"Repli (pas d'historique) : {age_msg}\n✓ Preuve de banc fraîche (repli log).")
        return 0
    print(f"::warning::Preuve de banc périmée (repli, {age_msg}).")
    return 1


def cmd_check_freshness(args: argparse.Namespace) -> int:
    """`check-freshness` : verdict BLOQUANT de fraîcheur des preuves de banc, PAR CHEMIN
    (ex-`check-freshness.sh`, ADR 0042 §2 / 0045 §6). Porté en Python natif (ADR 0101) :
    la décision pure (seuil/âge/verdict par chemin, repli log) vit dans `history.py` ;
    ICI l'orchestration — boucle les chemins OBLIGATOIRES (un périmé → échec) et
    OPTIONNELS (warn-only), repli global si l'historique manque.

    Read-only (jamais de réécriture d'historique — honnêteté des Runs, ADR 0023). Codes :
    0 = chemins obligatoires frais ; 1 = au moins un périmé ; 2 = aucune preuve du tout.
    Appelé par le cron `bench-freshness.yml`, jamais en pre-push (non bloquant côté PR)."""
    history = args.history or _RUNS_HISTORY
    now = int(dt.datetime.now(tz=dt.UTC).timestamp())
    seuil_global = args.seuil_jours or SEUIL_GLOBAL_DEFAUT
    # Repli si aucun historique exploitable : fichier absent OU aucune entrée datée
    # (ADR 0042 §4). load_runs lève sur fichier absent → on garde une liste vide.
    runs = load_runs(history) if os.path.isfile(history) else []
    if not any(r.date for r in runs):
        return _freshness_fallback(runs, now, seuil_global)

    print("Fraîcheur des preuves de banc — par chemin (ADR 0045 §6) :")
    perimes: list[str] = []
    for target in FRESHNESS_OBLIGATOIRES:
        etat, ligne = path_freshness(last_run_for_target(runs, target), target, now)
        print(ligne)
        if etat != "frais":
            perimes.append(target)
    for target in FRESHNESS_OPTIONNELS:
        etat, ligne = path_freshness(last_run_for_target(runs, target), target, now)
        print(ligne)
        if etat == "perime":
            print(f"    ({target} périmé : avertissement seulement, non bloquant)")

    if not perimes:
        print("✓ Chemins obligatoires frais.")
        return 0
    print(
        f"::warning::Preuve de banc périmée pour : {' '.join(perimes)} — "
        "relancer ce(s) chemin(s) et committer le run."
    )
    return 1


def _run_for_target(runs, target: str | None):
    """Le run de référence pour un chemin : le dernier de ce `target` si l'historique
    porte le champ, sinon le dernier run global (rétrocompat — mêmes phases/fraîcheur
    servent au diff). Garantit que diff et fraîcheur s'appuient sur LE MÊME run."""
    run = last_run_for_target(runs, target) if target else None
    return run if run is not None else latest_run(runs)


def _pose_named_context(topo: Topology, stack: str) -> None:
    """Pose/met à jour le CONTEXTE kubectl nommé `stack` dans son kubeconfig (LOT 8).

    REMPLACE `nestor env` (ADR 0097 §3) : au lieu d'imprimer `export KUBECONFIG=<banc>`
    (paramétrage-par-env aboli), `nestor` maintient un contexte nommé par topologie (banc,
    dirqual…) dérivé du champ `kubeconfig:` du YAML (prod) / du kubeconfig du banc (lima).
    L'opérateur branche `kubectl --context <stack>` SANS variable d'env (mécanisme standard
    k8s, cohérent ADR 0090).

    Best-effort, NON BLOQUANT (appelé depuis `stack select`, qui doit rester rapide) :
    une topo prod sans `kubeconfig:`, un banc non monté, ou un kubectl en échec → on
    SIGNALE sur stderr et on continue (le contexte n'est pas vital à l'activation)."""
    try:
        plan = _kube_context.context_plan(
            stack,
            kubeconfig=topo.kubeconfig,
            target_kind=topo.target_kind,
            # Kubeconfig du banc nommé par la stack (ADR 0102 volet B) :
            # `.kubeconfigs/<stack>.config`. `stack` = entrée de catalogue (= `stack_id`, fichier).
            bench_kubeconfig=_bench_kubeconfig_path(stack),
        )
        _kube_context.apply_context(plan)
    except _kube_context.ContextError as exc:
        _warn(f"contexte kubectl « {stack} » non posé : {exc}")
        return
    print(
        f"  contexte kubectl « {stack} » à jour — `kubectl --context {stack} …` "
        "(plus de `nestor env`, ADR 0097 §3).",
        file=sys.stderr,
    )


def cmd_access(args: argparse.Namespace) -> int:
    """`access` : ouvre l'accès développeur au banc (URLs + secrets + `.env` atlas).

    Porté de `bench/lima/access.sh` (ADR 0101) : la DÉCISION pure (port hôte par UI,
    lignes URL/`.env`, UI exposées du contrat) vit dans `nestor/access.py` (testé) ; ICI
    l'I/O — lit le contrat, ouvre un `kubectl port-forward` par UI exposée (BANC : réseau
    Lima isolé du Mac, ADR 0092), lit les Secrets, génère `atlas/.env.cluster.local`. Plus
    de double subprocess vers run-phases.sh. `--stop` tue les port-forward. Banc-only (la
    garde refuse la prod). Code 2 si le banc n'a pas de kubeconfig (socle non monté)."""
    _assert_bench_target("nestor access")
    if args.stop:
        return _access_stop_forwards()
    kubeconfig = _bench_kubeconfig()
    if not os.path.isfile(kubeconfig):
        _warn(f"kubeconfig banc absent ({kubeconfig}) — monter le banc d'abord (`nestor up`).")
        return 2
    with open(os.path.join(_ROOT, "contract", "endpoints.example.yaml"), encoding="utf-8") as f:
        uis = _access.exposed_uis(f.read())
    node_ip = _access_node_internal_ip()
    if not node_ip:
        _warn("pas d'IP nœud control-plane (banc démarré ?).")
        return 1
    _access_open_forwards_and_print(uis, node_ip)
    _access_print_secrets()
    _access_generate_env()
    print("\nPrêt. Travaillez dans atlas/ ; `git push` (Gitea → Argo CD réconcilie).")
    print("Pour tout arrêter : `nestor access --stop`")
    return 0


def _access_stop_forwards() -> int:
    """Tue les `kubectl port-forward` ouverts par `nestor access` (équiv. `pkill`)."""
    proc = subprocess.run(  # noqa: S603 — motif fixe, lecture seule
        ["pkill", "-f", "kubectl.*port-forward"], check=False
    )
    if proc.returncode == 0:
        print("✓ kubectl port-forwards arrêtés")
    else:
        _warn("aucun kubectl port-forward actif")
    return 0


def _access_node_internal_ip() -> str:
    """InternalIP d'un nœud control-plane Ready (vide si introuvable). Au banc c'est l'IP
    interne non routable depuis le Mac (d'où le port-forward) ; le rappel prod l'affiche."""
    out = _kubectl(
        "get",
        "nodes",
        "-l",
        "node-role.kubernetes.io/control-plane",
        "-o",
        'jsonpath={.items[0].status.addresses[?(@.type=="InternalIP")].address}',
    )
    return out.stdout.strip() if out and out.returncode == 0 else ""


def _access_node_port_of(namespace: str, service: str) -> str:
    """nodePort RÉEL du Service NodePort `<service>-nodeport` (vide si absent)."""
    out = _kubectl(
        "-n",
        namespace,
        "get",
        "svc",
        f"{service}-nodeport",
        "-o",
        "jsonpath={.spec.ports[0].nodePort}",
    )
    return out.stdout.strip() if out and out.returncode == 0 else ""


def _access_open_forward(lport: int, namespace: str, service: str, port: str) -> None:
    """Ouvre un `kubectl port-forward 127.0.0.1:<lport> → svc/<service>-nodeport:<port>` en
    arrière-plan (détaché : `start_new_session` + flux fermés, sinon un pipe en aval reste
    bloqué). BANC : le réseau Lima est isolé du Mac (ADR 0092 — pas de forward SSH/Gateway)."""
    subprocess.run(  # noqa: S603 — nettoyage d'un éventuel forward résiduel sur ce port
        ["pkill", "-f", f"kubectl.*port-forward.*127.0.0.1:{lport}:"], check=False
    )
    with open(os.devnull, "wb") as devnull:
        subprocess.Popen(  # noqa: S603 — argv contrôlé ; détaché volontairement (banc)
            [
                "kubectl",
                "--kubeconfig",
                _bench_kubeconfig(),
                "-n",
                namespace,
                "port-forward",
                f"svc/{service}-nodeport",
                f"127.0.0.1:{lport}:{port}",
            ],
            stdin=devnull,
            stdout=devnull,
            stderr=devnull,
            start_new_session=True,
        )


def _access_open_forwards_and_print(uis: list, node_ip: str) -> None:
    """Pour chaque UI exposée : ouvre le port-forward banc (BASE+index) + imprime l'URL
    cliquable (banc) et le rappel d'accès direct prod. Index déterministe (uis triées)."""
    print("UI exposées en L4 NodePort (HTTP clair, réseau privé — ADR 0092/0003).")
    print("  Au BANC : http://127.0.0.1:<port> (port-forward kubectl). En PROD : accès")
    print("  DIRECT http://<IP-nœud>:<nodePort> (aucun forward).")
    for i, ui in enumerate(uis):
        nodeport = _access_node_port_of(ui.namespace, ui.service)
        if not nodeport:
            _warn(f"{ui.namespace}/{ui.service} : nodePort introuvable — UI ignorée")
            continue
        lport = _access.host_port_for(i)
        _access_open_forward(lport, ui.namespace, ui.service, nodeport)
        print(
            f"  ✓ {ui.namespace}/{ui.service} → http://127.0.0.1:{lport} "
            f"(prod : http://{node_ip}:{nodeport})"
        )
        print(_access.url_line(ui.layer, f"http://127.0.0.1:{lport}", ui.auth), end="")


def _access_secret(namespace: str, name: str, key: str) -> str:
    """Lit une clé d'un Secret (base64 → clair). Vide si le Secret/la clé manquent."""
    out = _kubectl("-n", namespace, "get", "secret", name, "-o", f"jsonpath={{.data.{key}}}")
    return _b64decode(out.stdout.strip()) if out and out.returncode == 0 and out.stdout else ""


def _access_print_secrets() -> None:
    """Affiche les secrets/tokens regroupés (un seul écran ; lus des Secrets du cluster).

    AFFICHER les identifiants EST la fonction de `access` (outil de dev local, banc-only,
    ADR 0048) : l'opérateur veut les credentials pour se connecter aux UI. Comportement
    repris à l'identique de l'ex-`access.sh` (`print_secrets`). Le clear-text vers stdout
    interactif est VOULU, pas une fuite — CodeQL `py/clear-text-logging` est ici un faux
    positif fonctionnel (alerte dismissée « by design »)."""
    print("\nSecrets & tokens (lus des Secrets du cluster — ne pas partager)")
    for label, ns, secret, user_key, pwd_key in _access.SECRET_ROWS:
        pwd = _access_secret(ns, secret, pwd_key)
        user = _access_secret(ns, secret, user_key) if user_key else "admin"
        print(f"    {label:<11} {user} / {pwd}")  # affichage des credentials VOULU (cf. docstring)


def _access_generate_env() -> None:
    """Génère `atlas/.env.cluster.local` (gitignoré) consommable par atlas, si le dépôt
    voisin existe. Réutilise `access.env_content` (pur) pour le rendu exact.

    ÉCRIRE les credentials dans le `.env` EST la fonction de `access` (« git push et ça
    marche », ADR 0048) — comme l'ex-`access.sh` (`generate_env`). Le fichier est
    gitignoré côté atlas (jamais commité). Le clear-text storage est VOULU — CodeQL
    `py/clear-text-storage` est ici un faux positif fonctionnel (alerte dismissée)."""
    atlas_dir = os.path.abspath(os.path.join(_ROOT, "..", "atlas"))
    if not os.path.isdir(atlas_dir):
        _warn(f"dépôt atlas absent ({atlas_dir}) — .env non généré")
        return
    out_path = os.path.join(atlas_dir, ".env.cluster.local")
    pg_user = _access_secret("postgres", "pg-role-pgvector", "username")
    pg_pwd = _access_secret("postgres", "pg-role-pgvector", "password")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_access.env_content(pg_user, pg_pwd))
    print(f"\n✓ {os.path.basename(out_path)} généré (PG, OpenLineage, registry)")
    _warn("Vérifier qu'il est bien ignoré par git côté atlas (/.env.cluster.local).")


def _kubectl(*args: str, timeout: int = _REFRESH_TIMEOUT_S):
    """Lance `kubectl <args>` sur le banc (kubeconfig en repli sûr), borné. Renvoie le
    CompletedProcess (rc/stdout) ou None si injoignable — l'appelant décide. Le
    kubeconfig vise le banc, sinon un kubeconfig VIDE — jamais la prod (ADR 0053)."""
    try:
        # `--request-timeout` est un flag GLOBAL kubectl : il DOIT précéder la commande et
        # surtout le `--` d'un `exec` (sinon il est passé à la commande du conteneur — un
        # `kubectl exec pod -- gitea …` voyait `gitea … --request-timeout=5s` → « flag not
        # defined », tout geste seed cassé). On l'insère juste après `kubectl`, où kubectl le
        # consomme toujours, quelle que soit la sous-commande (get/exec/apply/rollout).
        return subprocess.run(  # noqa: S603 — argv contrôlé (table de workloads)
            ["kubectl", "--request-timeout=5s", *args],
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
    # Banc de la stack ACTIVE (ADR 0102 volet B) : `.kubeconfigs/<stack>.config` — pas de
    # topo en scope (garde nue), on lit la stack activée (`topology.yaml` → stack_id).
    bench = _bench_kubeconfig_path(_active_stack_name(None))
    return os.environ.get("KUBECONFIG") or (bench if os.path.exists(bench) else None)


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


def _assert_bench_target(action: str, topo: Topology | None = None) -> None:
    """Garde d'isolation (ADR 0053) : une commande BANC mutante ne s'exécute QUE sur
    une cible prouvée-banc. Si le kubeconfig du banc est absent ET que le contexte
    courant ne vise pas le banc, REFUS (code 2) — protège la prod d'une mutation par
    erreur. Échappatoire prod EXPLICITE : `KUBECONFIG` exporté = intention assumée
    (ADR 0065) — la garde ne bloque alors pas (et `discover` n'est jamais gardé,
    ADR 0074).

    PROVISIONNING FROM-SCRATCH (`up`) : quand `topo` est fourni ET déclare
    `target_kind: bench`, le banc n'existe PAS ENCORE (c'est `up` qui le CRÉE) — exiger
    un kubeconfig de banc bloquerait le cas légitime du montage depuis zéro (vécu : un
    `down` puis `up` était refusé). La TOPOLOGIE qui déclare `lima` est alors le signal
    sûr (= `EXPECTED_TARGET_KIND=bench` du bash), tant qu'aucun `KUBECONFIG` prod n'est
    exporté. Une topo `prod` reste soumise à la garde stricte (jamais de from-scratch
    prod sans cible prouvée)."""
    if os.environ.get("KUBECONFIG"):
        return  # intention explicite assumée par l'opérateur
    if topo is not None and topo.target_kind == "bench":
        return  # `up` from-scratch d'un banc déclaré : la topo lima EST le signal sûr
    # Banc de la stack ACTIVE (ADR 0102 volet B) : `.kubeconfigs/<stack>.config`. La branche
    # `topo bench` from-scratch est déjà sortie ci-dessus ; ici `topo` est None (garde nue)
    # ou prod → on sonde le banc de la stack activée (`topology.yaml` → stack_id).
    bench_kc = _bench_kubeconfig_path(_active_stack_name(None))
    if os.path.exists(bench_kc) and _context_targets_bench():
        return  # banc présent ET contexte = banc : nominal
    raise _UsageError(
        f"REFUS : `{action}` est une commande BANC mais le kubeconfig du banc est "
        f"absent ({os.path.relpath(bench_kc, _ROOT)}) et le contexte kubectl "
        "courant ne vise pas le banc Lima (127.0.0.1). Cette commande pourrait MUTER "
        "la PRODUCTION par erreur (ADR 0053).\n"
        "  • Monter le banc d'abord : `bench/lima/run-phases.sh up`\n"
        "  • Ou, si l'intention est délibérée hors-banc, exporter KUBECONFIG "
        "explicitement (ex. `export KUBECONFIG=~/.kube/<topo>.config`, ADR 0097 §3)"
    )


def _assert_inventory_safe(action: str, inventory_path: str, topo: Topology) -> None:
    """Garde de CIBLE ANSIBLE (ADR 0053) : un montage qui vise le banc (target_kind=bench)
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
            "  • Banc : utiliser l'inventaire Lima (target_kind: bench) — il est généré "
            "par le montage du banc (`bench/lima/run-phases.sh up`).\n"
            "  • Prod : lancer le geste via `nestor ansible <playbook>`, qui dérive "
            "l'inventaire de la stack active (ADR 0098 — plus de `hosts.yaml` à régénérer)."
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
    cmd = _node_transport_cmd(target, argv)
    try:
        return subprocess.run(  # noqa: S603 — argv contrôlé ; transport résolu de l'inventaire
            cmd, check=False, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _node_transport_cmd(target, argv: list[str]) -> list[str]:
    """Préfixe de transport (PUR) pour exécuter `argv` sur un nœud (ADR 0081) :
    `lima` → `limactl shell <host> -- argv` ; `ssh` → `ssh [args] user@host -- argv`."""
    if target.transport == "lima":
        return ["limactl", "shell", target.host, "--", *argv]
    dest = f"{target.user}@{target.host}" if target.user else target.host
    ssh_opts = shlex.split(target.ssh_args) if target.ssh_args else []
    return ["ssh", *ssh_opts, dest, "--", *argv]


def _node_exec_script(
    node: str,
    script_path: str,
    *,
    inventory_path: str,
    env: dict[str, str] | None = None,
    timeout: int = 600,
):
    """POUSSE un script bash dans la VM `node` et l'y exécute (`bash -s` + stdin), transport
    résolu de l'inventaire (ADR 0081). Équivalent Python de `vm_sh <vm> sudo env … bash -s <
    script` (ex-`phase_rollback`). Le script (ex. `storage/ceph/cleanup.sh`) RESTE bash : il
    s'exécute DANS la VM (node-side irréductible, ADR 0049/0101) — Python ne fait que le
    TRANSPORTER en stdin, jamais en réécrire la logique. `env` est passé via `env K=V …` AVANT
    `bash` (les valeurs vues par le script). Renvoie le CompletedProcess ou None si injoignable.
    `timeout` large par défaut (un wipe disques + apt peut durer)."""
    try:
        with open(inventory_path, encoding="utf-8") as f:
            inv = yaml.safe_load(f) or {}
        with open(script_path, encoding="utf-8") as f:
            script = f.read()
    except (OSError, yaml.YAMLError) as exc:
        raise _UsageError(f"node_exec_script : fichier illisible — {exc}") from exc
    try:
        target = _isolation.resolve_node_target(inv, node)
    except _isolation.IsolationError as exc:
        raise _UsageError(str(exc)) from exc
    # `sudo env K=V … bash -s` : sudo pour le wipe, env pour les VAR vues par le script,
    # `bash -s` lit le corps en stdin. argv FIXE (pas d'interpolation du contenu du script).
    env_pairs = [f"{k}={v}" for k, v in (env or {}).items()]
    argv = ["sudo", "env", *env_pairs, "bash", "-s"]
    cmd = _node_transport_cmd(target, argv)
    try:
        return subprocess.run(  # noqa: S603 — argv contrôlé ; script poussé en stdin (node-side)
            cmd, check=False, capture_output=True, text=True, timeout=timeout, input=script
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
    os.chmod(out_path, 0o600)  # POSIX : kubeconfig = secret, rw owner seul (poste Unix, ADR 0100)
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
        out_path = (
            args.kubeconfig_out
            or os.environ.get("KUBECONFIG")
            or os.path.join(os.path.expanduser("~"), ".kube", "config")
        )
        with _inventory_for(load_topology(_resolve(args.file))) as inv:
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
            "banc injoignable (aucun nœud Ready) — `nestor stack select <banc>` (pose "
            "le contexte) ou monter le cluster (`nestor up`)"
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
        with _inventory_for(load_topology(_resolve(args.file))) as inv:
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
            "cluster injoignable (aucun nœud Ready / aucune couche lue) — "
            "`nestor stack select <topo>` (pose le contexte) ou monter le cluster (`nestor up`)"
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


def _offer_kubeconfig_repatriation_to(topo: Topology, target: str, *, no_input: bool) -> None:
    """ADR 0090 : si le kubeconfig prod `target` est absent/injoignable, PROPOSER de le
    rapatrier depuis le control-plane (réutilise `_fetch_kubeconfig` de `discover`).

    Lecture seule vis-à-vis du cluster : rapatrier un kubeconfig n'est pas muter la prod
    (ADR 0053). Sous `--no-input` (CI) : on NE prompte pas (action opérateur) — l'appelant
    affichera honnêtement « nœuds Ready : — ». Toute erreur de rapatriement est non
    bloquante. `target` est le chemin déjà résolu/expansé."""
    if not target or _kubeconfig_reaches_api(target):
        return  # cible joignable → rien à faire
    if no_input:
        _warn(
            f"kubeconfig `{target}` absent/injoignable — le rapatrier : "
            "`nestor discover --cp <control-plane> --server https://<ip-cp>:6443 "
            f"--kubeconfig-out {target}` (cf. ADR 0090)."
        )
        return
    cp = topo.control_nodes[0] if topo.control_nodes else None
    if not cp:
        return
    endpoint = topo.network.get("control_plane_endpoint")
    port = topo.network.get("control_plane_port", 6443)
    server_hint = f"https://{endpoint}:{port}" if endpoint else None
    if not _confirm(
        f"kubeconfig `{target}` injoignable. Le rapatrier depuis `{cp}` "
        f"(/etc/kubernetes/admin.conf) ?",
        default=False,
        no_input=no_input,
    ):
        return
    server = server_hint or _ask(
        "endpoint API joignable depuis ce poste (ex. https://10.0.0.11:6443)",
        no_input=no_input,
    )
    try:
        with _inventory_for(topo) as inv:
            _fetch_kubeconfig(
                cp,
                inventory_path=inv,
                server=server,
                out_path=os.path.expanduser(target),
            )
        print(f"✓ kubeconfig rapatrié dans `{target}` (depuis `{cp}`).")
    except _UsageError as exc:
        _warn(f"rapatriement échoué : {exc}. La commande reste informative (état réel vide).")


def _offer_kubeconfig_repatriation(topo: Topology, topo_path: str, *, no_input: bool) -> None:
    """Variante pour `preview` : cible = le `KUBECONFIG` posé (déjà résolu en amont)."""
    _offer_kubeconfig_repatriation_to(topo, os.environ.get("KUBECONFIG", ""), no_input=no_input)


def _resolve_prod_kubeconfig_into_env(topo: Topology, topo_path: str, *, no_input: bool) -> None:
    """Pose le `KUBECONFIG` de la cible PROD dans l'environnement, pour que les sondes de
    lecture (`_ready_nodes`, `_observed_layers`, `_resource_healthy`…) visent le bon
    cluster (ADR 0090). Partagé par `preview` ET `next`/`up` : sans ça, ces commandes
    sont AVEUGLES en prod (kubeconfig non résolu → `_ready_nodes` vide → l'état réel
    semble vide → on RE-propose des couches déjà installées — DANGEREUX sur prod saine).

    - Si la topo DÉCLARE `kubeconfig:` (et qu'on ne suit pas déjà un KUBECONFIG exporté) :
      on le pose + propose le rapatriement si absent/injoignable.
    - Si la topo prod n'a PAS de `kubeconfig:` ni KUBECONFIG exporté : on RÉORIENTE vers
      `stack select` (qui complète la topo, ADR 0090) plutôt que de mentir sur l'état.
    No-op pour une stack `lima` (le banc garde sa résolution, ADR 0053)."""
    if topo.target_kind == "bench":
        return
    follows_export = bool(os.environ.get("KUBECONFIG")) and not _KUBECONFIG_AUTO_BENCH
    if follows_export:
        return  # un KUBECONFIG explicite est déjà en place : intention de l'opérateur
    if topo.kubeconfig:
        os.environ["KUBECONFIG"] = os.path.expanduser(topo.kubeconfig)
        globals()["_KUBECONFIG_AUTO_BENCH"] = False  # cible prod EXPLICITE désormais
        _offer_kubeconfig_repatriation(topo, topo_path, no_input=no_input)
    else:
        _warn(
            f"topologie prod « {topo.catalog.get('topology', '—')} » sans `kubeconfig:` "
            "déclaré → l'état réel ne peut pas être lu. Active la stack pour le déclarer "
            "et le rapatrier : `nestor stack select <stack>` (ADR 0090)."
        )


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
    path = _resolve(args.file)
    topo = load_topology(path)
    # ADR 0090 : en prod, pointer KUBECONFIG vers le kubeconfig DÉCLARÉ de la topo (sauf
    # KUBECONFIG déjà exporté), pour que TOUTES les sondes en aval (`_ready_nodes`,
    # `_observed_layers`, `_resource_healthy`…) visent le bon cluster. Helper PARTAGÉ avec
    # `next` (sans lui, ces commandes seraient aveugles en prod et re-proposeraient des
    # couches déjà installées). Réoriente vers `stack select` si la topo n'a pas de cible.
    _resolve_prod_kubeconfig_into_env(topo, path, no_input=getattr(args, "no_input", False))
    # Avertissements d'ALIGNEMENT SHELL — propres au BANC (ADR 0053). Une stack
    # `target_kind: prod` ne lit PAS le banc (gating ADR 0084) : ces messages, pensés
    # pour le banc, seraient TROMPEURS en prod (ils invitent à aligner le shell sur le
    # banc, sans objet en prod). On ne les émet donc que pour une stack lima.
    # Lecture seule : on ne BLOQUE pas. Quand aucun banc n'est monté, la sonde vise
    # /dev/null (jamais la prod, ADR 0053) → la section RÉEL est VIDE. On le DIT simplement
    # plutôt que de laisser croire à un cluster éteint. Émis SEULEMENT pour une stack lima
    # (une stack prod ne lit pas le banc, ADR 0084 — le message serait trompeur).
    # NB : plus de warning « ton shell n'a pas KUBECONFIG » : `preview` lit DÉJÀ le bon banc
    # (process ≠ shell), et `nestor kubectl …` rend obsolète le `kubectl` nu qu'on prémunissait.
    if (
        topo.target_kind == "bench"
        and _active_kubeconfig() is None
        and not _context_targets_bench()
    ):
        _warn(
            "cluster non installé — pas de connexion possible pour l'instant "
            "(le monter : `nestor up`). L'état réel ci-dessous est vide."
        )
    runs = load_runs(args.history or _RUNS_HISTORY)
    now = int(dt.datetime.now(tz=dt.UTC).timestamp())
    target = args.target  # None → default_target le déduit
    try:
        seq = expected_phase_sequence(topo, target)
    except PlanError as exc:
        raise _UsageError(str(exc)) from exc
    resolved_target = target or default_target(topo)
    stack_name = _stack_id(path)  # identité = nom de fichier (ADR 0102 volet B)

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
    # `nodeport` (L4 sur le port du nœud, ADR 0092 qui supersede 0071). On annote
    # « (défaut) » quand rien n'est déclaré.
    expo_declare = isinstance(topo.exposition, dict) and topo.exposition.get("mode")
    expo_label = topo.exposition_mode + ("" if expo_declare else " (défaut)")
    print(f"  couches        : {couches_label}{storage_part}  ·  exposition : {expo_label}")

    # ── RÉEL (ex-`refresh`) : l'état lu du réel (non stocké, ADR 0056 §7) ─────────
    declared = topo.control_nodes + topo.worker_nodes
    # État réel POLYMORPHE selon target_kind (ADR 0090) :
    # - lima : VMs limactl + nœuds Ready (le banc EST provisionné par nestor) ;
    # - prod : les machines existent HORS de nestor (bare-metal provisionné en
    #   amont, RUNBOOK) → on n'affiche PAS de section VMs (« à créer : dirqual* »
    #   serait FAUX et dangereux). On lit l'état réel du cluster K8s par kubectl,
    #   via le kubeconfig DÉCLARÉ dans la topo (`topo.kubeconfig`).
    ready = _ready_nodes(topo.target_kind, topo.kubeconfig)
    print("RÉEL (lu, non stocké) :")
    if topo.target_kind == "bench":
        real = classify_refresh(stack_name, declared, _real_vms(topo.target_kind), ready)
        print(f"  VMs présentes  : {', '.join(real.vms_present) or '—'}")
        print(f"  VMs à créer    : {', '.join(real.vms_missing) or '—'}")
        if real.vms_orphan:
            print(f"  ⚠ orphelines   : {', '.join(real.vms_orphan)} (d'une autre stack)")
        nodes_ready = real.nodes_ready
        vms_present = real.vms_present
        vms_orphan = real.vms_orphan
    else:
        # prod : pas de VMs nestor ; l'état des machines = nœuds K8s Ready (kubectl).
        # Les nœuds Ready PROUVENT que le socle (up+bootstrap) est monté → ils servent
        # aussi de proxy `vms_present` pour observed_done_phases (machines existantes).
        nodes_ready = ready
        vms_present = ready
        vms_orphan = []  # pas de notion de VM orpheline en prod (machines hors nestor)
    print(f"  nœuds Ready    : {', '.join(nodes_ready) or '—'}")

    # Drift de BACKEND (#356, ADR 0046) : le stockage RÉEL (StorageClass observées) peut
    # CONTREDIRE le backend déclaré — typiquement un rook-ceph résiduel orphelin après
    # bascule ceph→local-path. On ne sonde QUE si le cluster répond (nœuds Ready) ;
    # `classify_backend_drift` ne renvoie un backend que sur un signal RECONNU qui
    # contredit la déclaration (sinon None → pas de bruit).
    if nodes_ready:
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
    observed_socle = observed_done_phases(declared, vms_present, nodes_ready)
    # Couches applicatives observées saines (signaux kubectl) : ne sonder QUE si le
    # cluster ciblé répond (nœuds Ready) — sinon `_observed_layers` (kubeconfig banc)
    # lirait les couches du banc Lima pour une stack prod sans cible (ADR 0084).
    # nodes_ready vide en prod sans KUBECONFIG → on ne sonde rien (RÉEL honnêtement vide).
    observed_layers = _probe_observed_layers(seq, nodes_ready)
    # LE calcul partagé (preview == next == up) — `done` dérive du RÉEL SEUL (refonte
    # lot 6) : observed_socle ∪ observed_layers, PLUS de l'historique. Si Kubernetes est
    # mort, observed_layers est vide → toutes les couches aval sont « à appliquer » (la
    # cohérence de dépendance est naturelle). La fraîcheur (ci-dessus) reste calculée à
    # part (verdict_for_run) et n'influence QUE l'affichage rejeu/inédit, pas `done`.
    state = compute_plan_state(seq, observed_socle, observed_layers)
    a_appliquer = set(state.a_appliquer)
    # jamais monté ≠ rejeu : `jamais` (aucun run de la stack) → « à installer » (inédit) ;
    # `perime` (run existant mais plus frais) → « à rejouer ».
    rejeu = freshness == "perime"
    inedit = freshness == "jamais"
    print("PLAN (à monter) :")
    if vms_orphan:
        for vm in vms_orphan:
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
    if vms_orphan:
        head.append(f"{len(vms_orphan)} VM(s) à détruire d'abord")
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
    silencieux). Sur TTY : invite explicite via `_confirm` (hint « oui/NON », défaut
    False = Entrée vide ne monte RIEN ; --yes force le défaut à True et saute)."""
    if assume_yes:
        return True
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("montage refusé hors TTY sans --yes (pas de montage silencieux).", file=sys.stderr)
        return False
    return _confirm(
        f"Monter TOUTE la séquence du chemin `{target}` ?",
        default=assume_yes,
        no_input=assume_yes,
    )


def _nodes_override(topo) -> str:
    """Canal ENRICHI `nom|role|cpus,memory,disk|disques` des nœuds (ADR 0102 volet C).

    La TOPOLOGIE pilote le banc PAR NŒUD (fin de WITH_CEPH et des ressources globales,
    ADR 0056/0102) : chaque nœud porte SON rôle, SES ressources VM et SES disques bruts.

    Format (imposé, consommé par run-phases.sh) — 4 champs séparés par `|` :
      1. `nom`   — nom du nœud (`n.name`).
      2. `role`  — `control` (même control+worker, le banc le détaint) sinon `worker`.
      3. ressources — `cpus,memory,disk` (de `topo.node_resources(nom)`).
      4. disques — `name=size=role` séparés par `,` ; VIDE si le nœud n'en déclare pas
                   (le « mode Ceph » = la PRÉSENCE de disques déclarés, plus de WITH_CEPH).
    Nœuds séparés par `;`. Exemple :
      `node1|control|4,12GiB,40GiB|vdb=10GiB=data,vdd=5GiB=metadata;node2|worker|4,12GiB,40GiB|vdb=10GiB=data`
    Un nœud sans disque a un 4e champ vide : `node1|control|4,12GiB,40GiB|`.

    PUR (aucune I/O). Partagé par `up` et `next` (délégation socle)."""
    entries = []
    for n in topo.nodes:
        role = "control" if n.has_role("control") else "worker"
        r = topo.node_resources(n.name)
        resources = f"{r.cpus},{r.memory},{r.disk}"
        disks = ",".join(f"{d.name}={d.size}={d.role}" for d in n.disks) if n.disks else ""
        entries.append(f"{n.name}|{role}|{resources}|{disks}")
    return ";".join(entries)


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
    avec les MÊMES paramètres dérivés. `stack_name` = `stack_id` (nom de fichier, ADR 0102
    volet B) fourni par l'appelant — sert de nom de stack ET de clé du kubeconfig."""
    return {
        **os.environ,
        "NODES_OVERRIDE": _nodes_override(topo),
        "STACK_NAME": stack_name,
        # exposition.mode CONSÉQUENT (ADR 0092, supersede 0071) : `nodeport` (L4 sur le
        # port du nœud) est le défaut ; `gateway` n'arme l'ancienne bordure L7 hostNetwork
        # que s'il est déclaré ; `none` n'arme rien. Alias hostport→nodeport, lb-ipam→
        # gateway déjà résolus par exposition_mode.
        "EXPOSITION_MODE": topo.exposition_mode,
        # Chemin d'écriture du kubeconfig banc, NOMMÉ PAR LA STACK (ADR 0102 volet B) :
        # PYTHON décide (`.kubeconfigs/<stack>.config`, `stack_id`), run-phases.sh l'UTILISE
        # comme `KUBECONFIG_LOCAL` (fetch du CP). Une seule source de vérité pour le chemin —
        # la lecture Python (ctx.kubeconfig_local) et l'écriture bash coïncident.
        "KUBECONFIG_LOCAL": _bench_kubeconfig_path(stack_name),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CÂBLAGE FAÇADE du moteur de chemin Python (`nestor.path.run_path`) — LOT 6 (ADR 0097).
#
# POURQUOI ICI et non dans un module `nestor/facade.py` séparé : les callbacks RÉELS sont
# des closures sur des fonctions PRIVÉES de CETTE façade (`_wait_layer_healthy`,
# `_assert_bench_target`, `_assert_inventory_safe`, `_runner`, `_kubectl`, `_inventory_for`).
# Un module `nestor/facade.py` devrait les ré-importer depuis `scripts/topology.py` — qui
# n'est PAS un module de paquet (dossier `scripts/` sans `__init__`, chargé par chemin) →
# import bancal/circulaire. Le PRÉCÉDENT du dépôt (`cmd_bootstrap_seq`) construit DÉJÀ
# ses callbacks réels en closures ICI, à côté de l'I/O qu'ils enveloppent.
# On suit ce moule : `nestor.path` reste PUR (logique d'orchestration testée stubée), la
# façade ICI branche les callbacks sur le réel (runner/kubectl/limactl). La construction de
# `PathContext` (PURE, dérivée de la topo) est isolée dans `_path_context` → testable sans I/O.
#
# ⚠️ MOTEUR UNIQUE (ADR 0097, bascule achevée) : `cmd_up` MONTE TOUJOURS via ce câblage
# (`_run_path_engine`) — l'ancien filet bash `--engine=bash`/run-phases.sh a été RETIRÉ
# (plus de double source de vérité). AUCUN fallback bash : un échec du moteur Python
# s'ARRÊTE NET (corriger-le-code-pas-l-état, ADR 0046), il n'est JAMAIS masqué par un repli.
# ═══════════════════════════════════════════════════════════════════════════════


def _path_context(topo: Topology, inventory: str, stack: str | None = None) -> _path.PathContext:
    """Construit `PathContext` depuis la TOPOLOGIE (PUR — aucune I/O, ADR 0097 §5.a).

    Remplace les globales bash de run-phases.sh (CP:83 / API_PORT:90 / KUBECONFIG_LOCAL:116
    / REPO / INVENTORY) par un dataclass IMMUABLE dérivé de la topo, plus de globale ambiante :
    - `cp` : 1er nœud `control` (run-phases.sh:83-87 : 1er `:control` de NODES, sinon 1er
      nœud). DÉRIVÉ, jamais codé en dur (`cp1`).
    - `api_port` : 6443 (= run-phases.sh:90 `API_PORT`).
    - `kubeconfig_local` : chemin du kubeconfig du BANC, NOMMÉ PAR LA STACK
      (`.kubeconfigs/<stack>.config`, ADR 0102 volet B) — `stack` = `stack_id` (nom de fichier)
      fourni par l'appelant (`cmd_up`, depuis son `path`). Python le décide, `KUBECONFIG_LOCAL`
      de run-phases.sh le reçoit par env (une seule source de vérité pour le chemin). `None` →
      fallback banc générique.
    - `inventory` : passé PAR L'APPELANT (le chemin dérivé du `with _inventory_for(topo)`,
      ADR 0098) — `_path_context` reste PUR, il n'écrit ni ne supprime rien ; l'appelant
      (`cmd_up`) possède le cycle de vie du temporaire prod.
    - `repo` : racine du dépôt (= `REPO` de lib.sh) — pour résoudre les playbooks.
    - `nodes` : tuple des nœuds attendus Ready (compte du gate socle `nodes_ready_all`)."""
    controls = topo.control_nodes
    cp = controls[0] if controls else (topo.nodes[0].name if topo.nodes else "")
    return _path.PathContext(
        cp=cp,
        api_port=6443,
        kubeconfig_local=_bench_kubeconfig_path(stack),
        repo=os.path.abspath(_ROOT),
        inventory=inventory,
        nodes=tuple(n.name for n in topo.nodes),
    )


def _provision_via_bash(topo: Topology, stack_name: str) -> int:
    """STUB DOCUMENTÉ du provisioning amont `up` (ADR 0097 §5.b) : délègue à `run-phases.sh up`.

    Le provisioning VM (limactl render/start, disques déclarés par nœud, gate disques,
    dérivation cp_ip/iface) ET `write_inventory` byte-stable sont l'artefact node-side
    IRRÉDUCTIBLE (ADR 0049 — Lima/limactl reste bash). On NE le réécrit PAS en Python ici :
    on POUSSE `run-phases.sh up` comme on applique un manifeste (Python pousse, consomme un
    `rc`, ne lit pas la logique bash, ADR 0097 §2.a).

    ADR 0102 volet C : ressources ET disques sont PAR NŒUD, portés par le canal enrichi
    `NODES_OVERRIDE` (cf. `_nodes_override`) — PLUS de VM_CPUS/VM_MEMORY/VM_DISK globaux (du
    CP) ni de WITH_CEPH en env. Chaque nœud rend SA VM avec SES ressources et crée SES disques.

    RESTE BANC (§5.b) : portage RÉEL du callback (limactl render/start + write_inventory) — non
    inventé ici (un faux provisioning serait pire que rien). Voir `_path.banc_todo`."""
    env = _runphases_env(topo, stack_name)
    runphases = os.path.join(_ROOT, "bench", "lima", "run-phases.sh")
    print("→ up : provisioning des VMs via run-phases.sh (limactl, ADR 0049)…")
    return subprocess.run(  # noqa: S603 — chemin codé, env dérivé d'une topo validée
        ["bash", runphases, "up"],
        check=False,
        env=env,
    ).returncode


# ═══════════════════════════════════════════════════════════════════════════════
# SEED GITOPS (phase DÉLÉGUÉE `gitops-seed`) — câblage façade du LOT 8 (ADR 0097 §2/§3).
#
# `nestor/seed.py:run_seed` est PUR (logique : gardes opposées banc/prod + ordre des
# étapes ; I/O injectée). ICI la façade BRANCHE l'I/O RÉELLE sur le banc : chaque étape
# de `seed_steps('banc')` exécute le geste de `bench/lima/gitea-init.sh`, via
# `kubectl exec DANS le pod gitea` (Gitea écoute `localhost:3000` — JAMAIS le FQDN
# `*.svc.cluster.local`, qui timeoute côté glibc/curl quand un search domain externe est
# présent, drift dirqual 2026-06-22) + `kubectl` pour les Secrets / l'apply de l'Application.
#
# ⚠️ HONNÊTETÉ (ADR 0034) : ce câblage MUTE un Gitea/Argo CD vivant — sa preuve DÉFINITIVE
# est un RUN BANC du mainteneur (impossible dans cette session). Les tests (test_facade.py)
# stubent TOUTE l'I/O (kubectl espionné, do() injecté) : ils prouvent le ROUTAGE + la garde,
# pas le seed réel. Les 7 steps sont désormais CÂBLÉS pour de vrai (admin/token/org-repo/
# push-code-location/webhook-secret/webhook/application) — y compris la Contents API
# create-or-update (push-code-location), dont le PARSING de réponse (SHA existant, présence
# de `"commit"`) reste à PROUVER au banc (format réel de Gitea) sans plus lever de STUB.
# ═══════════════════════════════════════════════════════════════════════════════

# Ce que le câblage RÉEL du seed banc ne couvre PAS encore (à câbler+prouver au banc,
# ADR 0034) — frontière déclarée, exposée par `_seed_banc_todo()` (testable).
_SEED_BANC_TODO = (
    "étape `push-code-location` CÂBLÉE (Contents API create-or-update : GET du SHA, "
    'PUT-avec-sha vs POST, vérif `"commit"`) — le PARSING de la réponse réelle de Gitea '
    "(objet vs liste de `GET /contents`, forme du PUT/POST) reste à PROUVER au banc "
    "(gitea-init.sh:109-143) : le step TENTE le vrai push et échoue honnêtement si un détail "
    "de format cloche, il ne lève plus de STUB à l'aveugle",
    "dédup du webhook par URL (gitea-init.sh:163-166) : le comptage parse la réponse "
    "`GET /hooks` réelle — ici on POST best-effort (Gitea refuse un doublon) ; affiner+prouver",
    "run banc gitops-seed (gitea-init réel : admin/token/org-repo/push-code-location/"
    "webhook/application) consigné — PREUVE DÉFINITIVE, reste à faire au banc",
)


def _seed_banc_todo() -> tuple[str, ...]:
    """Frontière code-écrit / preuve-banc du seed (honnêteté ADR 0034). Testable."""
    return _SEED_BANC_TODO


class _SeedLaunchResult:
    """Résultat d'un montage de phase DÉLÉGUÉE (seed), au moule de `IdempotenceResult`.

    `run_path` lit `getattr(res, "ok")` / `.message` du callback `launch` ; on expose donc
    `.ok` (bool) + `.message` pour qu'une phase seed s'intègre comme une phase à play."""

    def __init__(self, ok: bool, message: str = "") -> None:
        self.ok = ok
        self.message = message


def _gitea_pod(ns: str) -> str:
    """Nom du pod gitea (réplica unique, Recreate) — parité `gitea_pod()` de gitea-init.sh.

    Lecture seule (kubectl get, cible sûre `_kubectl_env`). Lève `_path.PathError` si absent
    (le seed n'a pas de sens sans Gitea posé — fail-fast honnête, ADR 0046)."""
    out = _kubectl(
        "-n",
        ns,
        "get",
        "pod",
        "-l",
        "app=gitea",
        "-o",
        "jsonpath={.items[0].metadata.name}",
    )
    pod = out.stdout.strip() if out and out.returncode == 0 else ""
    if not pod:
        raise _path.PathError(
            f"seed gitops : pod gitea introuvable (ns `{ns}`) — Gitea est-il posé "
            "(phase `gitops`) sur la cible banc ? (gitea-init.sh:49)"
        )
    return pod


def _seed_api_ok(code: str) -> bool:
    """Verdict d'idempotence d'un appel API Gitea du seed (parité du `|| true` ciblé du bash).

    `code` = code HTTP rendu par `_api` (vide si l'exec a échoué : curl absent / pod
    injoignable). Succès = 2xx (créé) OU « existe déjà » (409 conflit / 422 unprocessable —
    idempotent au rejeu). Un code vide (exec KO) ou une vraie erreur (401 token invalide,
    5xx) = ÉCHEC → le step échoue (fail-fast, pas de faux-vert — correctif d'audit)."""
    if not code:
        return False  # exec KO (out None / rc≠0) → pas un succès
    return code.startswith("2") or code in ("409", "422")


def _seed_contents_sha(resp_body: str) -> str:
    """Extrait le `sha` d'une réponse `GET /repos/.../contents/<path>` de Gitea.

    Parse JSON PROPRE (préférable au grep bash) + ROBUSTE : `GET /contents/<path>` rend un
    OBJET pour un fichier, mais une LISTE pour un répertoire (et un message d'erreur pour un
    404 — le fichier n'existe pas encore). On renvoie le `sha` du 1er objet plausible, sinon
    une chaîne VIDE (= « pas de fichier existant » → l'appelant fera un POST de création,
    parité du `sha` vide du bash). Un corps illisible → vide (l'appelant décide)."""
    if not resp_body or not resp_body.strip():
        return ""
    try:
        data = json.loads(resp_body)
    except (ValueError, TypeError):
        return ""
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return ""
    sha = data.get("sha")
    return sha if isinstance(sha, str) else ""


def _seed_resp_has_commit(resp_body: str) -> bool:
    """Vrai si la réponse d'un PUT/POST `/contents` contient un objet `commit` (parité du
    `grep -q '"commit"'` du bash). Un PUT/POST réussi de la Contents API renvoie
    `{"content": …, "commit": {…}}` ; sans `commit`, l'écriture A ÉCHOUÉ (l'ancienne version
    resterait dans Gitea → Argo CD déploierait un manifeste périmé : drift à éviter).

    Parse JSON propre ; on tolère qu'un corps non-JSON contienne malgré tout le marqueur
    (fail-safe identique au grep du bash) → l'appelant échoue (return False) si rien."""
    if not resp_body:
        return False
    try:
        data = json.loads(resp_body)
        if isinstance(data, dict) and isinstance(data.get("commit"), dict):
            return True
    except (ValueError, TypeError):
        # Corps non-JSON : on n'échoue PAS ici — on retombe sur le fallback texte
        # ci-dessous (parité du `grep -q '"commit"'` du bash, fail-safe).
        pass
    return '"commit"' in resp_body


def _gitea_exec(ns: str, pod: str, argv: list[str], *, timeout: int = 60):
    """Exécute `argv` DANS le pod gitea (`kubectl exec`) — parité `gitea_cli()` de
    gitea-init.sh. C'est le MOULE anti-FQDN : la CLI/curl tape Gitea sur `localhost:3000`
    DEPUIS le pod, donc AUCUNE résolution `*.svc.cluster.local` côté hôte (piège DNS).

    Renvoie le CompletedProcess (cible sûre `_kubectl_env`, jamais la prod) ou None si
    injoignable. L'appelant DÉCIDE (idempotence : un `user already exists` n'est pas une erreur)."""
    return _kubectl("-n", ns, "exec", pod, "--", *argv, timeout=timeout)


def _seed_do_banc(topo: Topology, config) -> Callable[[str], bool]:
    """Construit le `do(step)` RÉEL du seed banc (porte `bench/lima/gitea-init.sh`).

    Pour CHAQUE étape de `seed.seed_steps('banc')`, exécute le geste correspondant via
    `kubectl exec DANS le pod gitea` (localhost:3000, JAMAIS le FQDN) + `kubectl` pour les
    Secrets / l'apply de l'Application. Idempotent (un step déjà fait = ok, pas d'erreur).

    Le token API (étape 2) doit être réutilisé par les étapes API suivantes (3/6) : le
    `do(step) -> bool` étant sans état, on le THREADE via une closure `state` mutable —
    exactement comme la variable `token` du `main()` bash, locale au run. La cible kube est
    la cible SÛRE (`_kubectl`/`_kubectl_env`) ; le pod est résolu une fois au 1er besoin."""
    ns, argocd_ns = config.ns, config.argocd_ns
    org, repo = config.org, config.repo
    api_base = f"{config.api}/api/v1"
    state: dict[str, str] = {}

    def pod() -> str:
        if "pod" not in state:
            state["pod"] = _gitea_pod(ns)
        return state["pod"]

    def _api_full(method: str, path: str, body: str | None = None):
        """Appel REST à Gitea DEPUIS le pod (curl localhost:3000) — parité `api()` bash, CORPS
        INCLUS. Renvoie `(out, code, resp_body)`.

        `kubectl exec pod -- curl -sS -w '\\n%{http_code}' …` (PAS de `-o /dev/null`) : curl
        écrit le CORPS de la réponse puis, sur une DERNIÈRE ligne, le code HTTP (moule du bash
        `-w '\\n%{http_code}'`). On sépare la dernière ligne (code) du reste (corps) pour
        DÉCIDER (idempotence) ET LIRE la réponse (SHA d'un fichier, présence de `"commit"`)
        sans parser un FQDN ni résoudre du DNS côté hôte.

        Le CORPS est nécessaire à `push-code-location` (Contents API : lire le SHA existant,
        vérifier `"commit"`) ; les steps org-repo/webhook n'en ont besoin que du code → ils
        passent par le wrapper `_api` (corps ignoré)."""
        url = f"{api_base}{path}"
        argv = [
            "curl",
            "-sS",
            "-w",
            "\n%{http_code}",
            "-X",
            method,
            "-H",
            f"Authorization: token {state.get('token', '')}",
            "-H",
            "Content-Type: application/json",
            url,
        ]
        if body is not None:
            argv += ["-d", body]
        out = _gitea_exec(ns, pod(), argv)
        if not (out and out.returncode == 0):
            return out, "", ""
        # Le code HTTP est sur la DERNIÈRE ligne ; le corps est tout ce qui précède (le `-w
        # '\\n%{http_code}'` ajoute UNE ligne après le corps, exactement comme le bash).
        raw = out.stdout or ""
        resp_body, _sep, code = raw.rpartition("\n")
        return out, code.strip(), resp_body

    def _api(method: str, path: str, body: str | None = None):
        """Variante CODE-SEUL de `_api_full` (corps ignoré) — pour org-repo/webhook qui ne
        décident que sur le code HTTP. Renvoie `(out, code)` (parité de l'API d'origine)."""
        out, code, _resp = _api_full(method, path, body)
        return out, code

    def admin() -> bool:
        # 1/7 — admin Gitea (idempotent). Le mot de passe vit dans le Secret K8s `gitea-admin`
        # (créé s'il manque) ; `gitea admin user create` échoue si l'utilisateur existe → on
        # AVALE ce cas (idempotent), comme le `|| true` du bash (gitea-init.sh:69-84).
        chk = _kubectl("-n", ns, "get", "secret", "gitea-admin")
        if not (chk and chk.returncode == 0):
            # Mot de passe : généré dans le cluster (jamais versionné, ADR 0023). On le laisse
            # à kubectl `create secret --from-literal` ; le banc le (re)lira au besoin.
            _kubectl(
                "-n",
                ns,
                "create",
                "secret",
                "generic",
                "gitea-admin",
                "--from-literal=username=" + config.admin_user,
                "--from-literal=password=" + _seed_gen_secret(),
            )
        pw = _kubectl(
            "-n",
            ns,
            "get",
            "secret",
            "gitea-admin",
            "-o",
            "jsonpath={.data.password}",
        )
        admin_pw = _b64decode(pw.stdout.strip()) if pw and pw.returncode == 0 else ""
        if not admin_pw:
            return False
        created = _gitea_exec(
            ns,
            pod(),
            [
                "gitea",
                "admin",
                "user",
                "create",
                "--username",
                config.admin_user,
                "--password",
                admin_pw,
                "--email",
                config.admin_email,
                "--admin",
                "--must-change-password=false",
            ],
        )
        # rc=0 → créé. rc≠0 → idempotent SEULEMENT si « user already exists » (parité du
        # `|| true` CIBLÉ du bash). Tout autre échec (pod pas prêt, mdp refusé, exec KO) =
        # ÉCHEC réel : sinon `token` échouera après, sans que la cause soit signalée ICI
        # (constaté au banc : admin avalait un échec → token KO trompeur). On VÉRIFIE.
        if created and created.returncode == 0:
            return True
        blob = ((created.stdout or "") + (created.stderr or "")) if created else ""
        return "already exists" in blob

    def token() -> bool:
        # 2/7 — token API. `--raw` n'affiche QUE la valeur (pas de préfixe à parser) ;
        # nom unique par run (un nom pris ferait échouer). On CAPTURE le stdout et on strippe
        # le whitespace (parité gitea-init.sh:90-94) ; vide → échec (fail-fast).
        token_name = f"atlas-init-{os.getpid()}-{int(time.time())}"
        out = _gitea_exec(
            ns,
            pod(),
            [
                "gitea",
                "admin",
                "user",
                "generate-access-token",
                "--username",
                config.admin_user,
                "--token-name",
                token_name,
                "--scopes",
                "all",
                "--raw",
            ],
        )
        tok = "".join((out.stdout or "").split()) if out and out.returncode == 0 else ""
        if not tok:
            return False
        state["token"] = tok
        return True

    def org_repo() -> bool:
        # 3/7 — organisation + dépôt des workflows (idempotent : un 422 « existe déjà » est OK,
        # parité du `|| true` bash, gitea-init.sh:127-131). On POST les deux ; un code 2xx OU
        # un « already exists » (409/422) = succès idempotent. Un ÉCHEC réel (token invalide
        # 401, Gitea 500, exec KO → code vide) = échec (fail-fast, pas de faux-vert — audit).
        _, c_org = _api("POST", "/orgs", f'{{"username":"{org}"}}')
        _, c_repo = _api(
            "POST",
            f"/orgs/{org}/repos",
            f'{{"name":"{repo}","auto_init":true,"default_branch":"main"}}',
        )
        return _seed_api_ok(c_org) and _seed_api_ok(c_repo)

    def push_code_location() -> bool:
        # 4/7 — push de la code-location jouet (Contents API create-or-update, idempotent).
        # Parité gitea-init.sh:109-143 (push_gitea_file) pour les 3 manifestes versionnés de
        # `bench/lima/atlas-workflow-sample/` (_SEED_SAMPLE_DIR). Pour CHAQUE fichier :
        #   1. base64 du CONTENU lu côté HÔTE (le fichier est versionné, PAS dans le pod : on
        #      l'encode en Python, jamais via un `base64` exécuté dans le pod) ;
        #   2. GET /contents/<path> → SHA du fichier existant (vide au 1er passage / 404) ;
        #   3. sha présent → PUT-avec-sha (MAJ) ; absent → POST (création) ;
        #   4. VÉRIFIER `"commit"` dans la réponse — un PUT/POST raté laisse l'ANCIENNE version
        #      dans Gitea → Argo CD déploierait un manifeste périmé (drift). Sans `commit` =
        #      ÉCHEC → return False (fail-fast : run_seed s'arrête net, aucun faux-vert).
        for fname in ("code-location.yaml", "workspace-patch.yaml", "reload-hook.yaml"):
            try:
                with open(os.path.join(_SEED_SAMPLE_DIR, fname), "rb") as fh:
                    content_b64 = base64.b64encode(fh.read()).decode("ascii")
            except OSError:
                return False  # fichier sample illisible → fail-fast (le seed n'a pas de sens)
            contents_path = f"/repos/{org}/{repo}/contents/{fname}"
            # GET du SHA existant (404 si absent → sha vide, on créera par POST). Le code HTTP
            # n'est PAS gaté ici (un 404 est attendu au 1er passage) : on lit le corps.
            _, _get_code, get_body = _api_full("GET", contents_path)
            sha = _seed_contents_sha(get_body)
            if sha:
                body = json.dumps(
                    {"content": content_b64, "sha": sha, "message": f"update {fname} (atlas-init)"}
                )
                _, _code, resp = _api_full("PUT", contents_path, body)
            else:
                body = json.dumps({"content": content_b64, "message": f"add {fname} (atlas-init)"})
                _, _code, resp = _api_full("POST", contents_path, body)
            if not _seed_resp_has_commit(resp):
                return False  # PUT/POST raté → return False (fail-fast, drift évité)
        return True

    def webhook_secret() -> bool:
        # 5/7 — secret partagé `webhook.gitea.secret` (argocd-secret). Idempotent : on lit le
        # secret partagé `argocd-webhook-shared` (créé s'il manque), puis on patche
        # `argocd-secret` (parité gitea-init.sh:145-158). Le secret vit dans le cluster.
        chk = _kubectl("-n", argocd_ns, "get", "secret", "argocd-webhook-shared")
        if not (chk and chk.returncode == 0):
            _kubectl(
                "-n",
                argocd_ns,
                "create",
                "secret",
                "generic",
                "argocd-webhook-shared",
                "--from-literal=secret=" + _seed_gen_secret(),
            )
        got = _kubectl(
            "-n",
            argocd_ns,
            "get",
            "secret",
            "argocd-webhook-shared",
            "-o",
            "jsonpath={.data.secret}",
        )
        wh = _b64decode(got.stdout.strip()) if got and got.returncode == 0 else ""
        if not wh:
            return False
        state["wh_secret"] = wh
        patch = _kubectl(
            "-n",
            argocd_ns,
            "patch",
            "secret",
            "argocd-secret",
            "--type",
            "merge",
            "-p",
            '{"stringData":{"webhook.gitea.secret":"' + wh + '"}}',
        )
        return bool(patch and patch.returncode == 0)

    def webhook() -> bool:
        # 6/7 — webhook Gitea → argocd-server/api/webhook. On POST le hook (events push,
        # content_type json, secret partagé). _BANC : la DÉDUP par URL (compter les hooks
        # existants en parsant `GET /hooks`) dépend du format de réponse réel — ici on POST
        # best-effort (Gitea refuse un doublon, idempotent de fait) ; affinage au banc
        # (_SEED_BANC_TODO). Le repoURL du hook est intra-cluster (résolu par Gitea, pas l'hôte).
        hooks_url = f"http://argocd-server.{argocd_ns}.svc.cluster.local/api/webhook"
        body = (
            '{"type":"gitea","active":true,"events":["push"],"config":{"url":"'
            + hooks_url
            + '","content_type":"json","secret":"'
            + state.get("wh_secret", "")
            + '"}}'
        )
        _, c_hook = _api("POST", f"/repos/{org}/{repo}/hooks", body)
        # 2xx OU « existe déjà » (Gitea refuse un doublon) = ok ; échec réel (token/exec) = KO.
        return _seed_api_ok(c_hook)

    def application() -> bool:
        # 7/7 — Application Argo CD `atlas-workflows` (repoURL Gitea injecté, valeur de
        # déploiement, ADR 0023). `kubectl apply -f -` du manifeste rendu (parité
        # gitea-init.sh:172-198). Pur kubectl (aucun token, aucune réponse API à parser).
        manifest = _seed_application_manifest(config)
        out = _kubectl_apply_stdin(manifest)
        return bool(out and out.returncode == 0)

    handlers = {
        "admin": admin,
        "token": token,
        "org-repo": org_repo,
        "push-code-location": push_code_location,
        "webhook-secret": webhook_secret,
        "webhook": webhook,
        "application": application,
    }

    def do(step: str) -> bool:
        handler = handlers.get(step)
        if handler is None:
            raise _path.PathError(f"seed gitops : étape banc inconnue `{step}` (façade)")
        return handler()

    return do


def _seed_gen_secret() -> str:
    """Secret aléatoire (32 alnum) — parité `gen_secret()` de gitea-init.sh (jamais versionné,
    ADR 0023 ; vit uniquement dans le cluster). `secrets` (stdlib) plutôt que /dev/urandom."""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(32))


def _b64decode(b64: str) -> str:
    """Décode un Secret K8s (`{.data.X}` est base64). Vide si illisible (l'appelant décide)."""
    try:
        return base64.b64decode(b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def _seed_application_manifest(config) -> str:
    """Rend le manifeste de l'Application Argo CD `atlas-workflows` (repoURL Gitea injecté).

    Le repoURL intra-cluster est `config.workflows_repo_url()` (résolu par argocd-repo-server
    DANS le cluster, pas par l'hôte). Parité gitea-init.sh:177-198 (template versionné =
    application.example.yaml ; ici la valeur de déploiement, ADR 0023)."""
    return (
        "apiVersion: argoproj.io/v1alpha1\n"
        "kind: Application\n"
        "metadata:\n"
        "  name: atlas-workflows\n"
        f"  namespace: {config.argocd_ns}\n"
        "spec:\n"
        f"  project: {config.org}\n"
        "  source:\n"
        f"    repoURL: {config.workflows_repo_url()}\n"
        "    targetRevision: main\n"
        "    path: .\n"
        "  destination:\n"
        "    server: https://kubernetes.default.svc\n"
        "    namespace: dagster\n"
        "  syncPolicy:\n"
        "    automated:\n"
        "      prune: true\n"
        "      selfHeal: true\n"
        "    syncOptions:\n"
        "      - CreateNamespace=false\n"
    )


def _kubectl_apply_stdin(manifest: str, *, timeout: int = _REFRESH_TIMEOUT_S):
    """`kubectl apply -f -` en passant `manifest` sur STDIN (cible sûre `_kubectl_env`).

    Renvoie le CompletedProcess ou None si injoignable. SÉPARÉ de `_kubectl` (qui ne pousse
    pas de STDIN) — moule de l'apply de l'Application du seed (gitea-init.sh:177)."""
    try:
        return subprocess.run(  # noqa: S603 — argv contrôlé, manifeste rendu d'une config validée
            ["kubectl", "apply", "-f", "-", "--request-timeout=5s"],
            check=False,
            capture_output=True,
            text=True,
            input=manifest,
            env=_kubectl_env(),
            timeout=timeout,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


# ── Harnais e2e dataops : preuve OpenLineage→Marquez (porte run-phases.sh:1213) ───
# I/O kubectl IRRÉDUCTIBLE (ADR 0049) ; toute la DÉCISION (manifeste du Job, comptage des
# jobs, verdict du compteur avant/après) est PURE dans `nestor.phases`. Le moteur substitue
# ce câblage au STUB du registre pour `dataops_chain_emit_and_verify` (cf. `_E2E_HOOK_IMPL`).


def _marquez_job_count(ol_ns: str) -> int | None:
    """Nombre de jobs visibles dans Marquez pour le namespace OpenLineage `ol_ns`.

    Port de `marquez_job_count` (run-phases.sh:1273) : interroge l'API Marquez
    `GET /api/v1/namespaces/<ol_ns>/jobs` DEPUIS UN POD ÉPHÉMÈRE busybox du ns marquez
    (`kubectl run … -- wget`), JAMAIS depuis l'hôte — le FQDN `marquez.marquez.svc.cluster.
    local` ne se résout QUE dans le cluster (piège DNS, mémoire dns-fqdn-timeout). Le JSON
    rendu est compté par la logique PURE `phases.parse_marquez_job_count` (totalCount, sinon
    len(jobs)). Renvoie l'entier, ou `None` si illisible/injoignable (→ verdict `skip`)."""
    from nestor import phases as _phases

    url = f"{_phases.MARQUEZ_URL}/api/v1/namespaces/{ol_ns}/jobs"
    # Pod jetable, nom unique par PID (parité `marquez-count-$$`), auto-supprimé (--rm).
    out = _kubectl(
        "-n",
        "marquez",
        "run",
        f"marquez-count-{os.getpid()}",
        "--rm",
        "-i",
        "--restart=Never",
        "--image=busybox:1.36",
        "--quiet",
        "--",
        "sh",
        "-c",
        f"wget -qO- '{url}' 2>/dev/null",
        # Le pod busybox doit DÉMARRER, requêter, et être nettoyé : on borne large (le
        # défaut _REFRESH_TIMEOUT_S=8s ne suffit pas à un pull/run de pod).
        timeout=120,
    )
    if not (out and out.returncode == 0):
        return None
    return _phases.parse_marquez_job_count(out.stdout)


def _job_succeeded(ns: str, name: str) -> bool:
    """`True` si le Job `ns/name` a `status.succeeded == 1` (port de `emit_done`,
    run-phases.sh:1250). Lecture bornée, cible sûre ; toute incertitude → False."""
    out = _kubectl("-n", ns, "get", "job", name, "-o", "jsonpath={.status.succeeded}")
    return bool(out and out.returncode == 0 and (out.stdout or "").strip() == "1")


def _chain_emit_and_verify_banc(*, sleep=time.sleep) -> None:
    """Preuve e2e de la chaîne Dagster → OpenLineage → Marquez (porte run-phases.sh:1213).

    Le geste RÉEL câblé (I/O kubectl + API Marquez), substitué au STUB du registre pour
    `dataops_chain_emit_and_verify` :
      1. compteur de jobs Marquez AVANT (`_marquez_job_count`) ;
      2. `kubectl apply` du Job émetteur jetable `ol-emit-toy` (ns dagster, image
         `registry:80/dagster-openlineage-emit:dev`, `dagster asset materialize`) — manifeste
         rendu PUR par `phases.emit_toy_job_manifest` ;
      3. poll de `status.succeeded == 1` (max 300 s, intervalle 10 s) ; échec → logs du Job +
         erreur claire (image émetteur poussée ? cf. réserve `build_emitter_image`) ;
      4. `sleep 5` (Marquez traite COMPLETE), compteur APRÈS ;
      5. verdict `phases.classify_marquez_ingest(before, after)` : `ok` (lineage présent) sinon
         on LÈVE (jamais un faux vert, honnêteté ADR 0034) ;
      6. teardown : `kubectl delete job ol-emit-toy --wait=false`.

    ⚠️ RÉSERVE (cf. `phases.banc_todo`) : dépend de l'image émetteur, poussée par le rôle
    `platform-build-images` SOUS `build_emitter_image=true` (banc e2e). Le play `dataops` du
    moteur Python NE passe PAS encore ce drapeau → si l'image manque, le Job reste
    ImagePullBackOff et le poll échoue : on LÈVE (étape 3) plutôt qu'un faux succès. La cible
    kube est la cible SÛRE (`_kubectl`/`_kubectl_env`, jamais la prod) ; le FQDN Marquez n'est
    tapé QUE depuis un pod intra-cluster (Job + busybox), jamais depuis l'hôte (piège DNS)."""
    from nestor import phases as _phases

    ns = _phases.EMITTER_NAMESPACE
    ol_ns = _phases.EMITTER_OL_NAMESPACE
    job = _phases.EMITTER_JOB_NAME

    job_before = _marquez_job_count(ol_ns)

    manifest = _phases.emit_toy_job_manifest()
    applied = _kubectl_apply_stdin(manifest)
    if not (applied and applied.returncode == 0):
        detail = (applied.stderr.strip() if applied else "kubectl injoignable") or "(sans détail)"
        raise _phases.E2EHookStubbed(
            f"dataops e2e : apply du Job émetteur `{job}` échoué ({detail}) — "
            "Dagster posé (ns dagster) sur la cible banc ?"
        )

    print("    attente de la complétion du run émetteur (max 5 min)…")
    # Poll borné (parité `retry 300 10 emit_done`) : succès = status.succeeded==1.
    succeeded = False
    waited = 0
    while waited <= 300:
        if _job_succeeded(ns, job):
            succeeded = True
            break
        sleep(10)
        waited += 10
    if not succeeded:
        logs = _kubectl("-n", ns, "logs", f"job/{job}", "--tail=20")
        tail = (logs.stdout if logs and logs.returncode == 0 else "") or ""
        _kubectl("-n", ns, "delete", "job", job, "--wait=false")  # teardown best-effort
        raise _phases.E2EHookStubbed(
            f"dataops e2e : le run Dagster émetteur n'a pas réussi (image "
            f"`{_phases.EMITTER_IMAGE}` poussée ? `build_emitter_image=true` requis au play "
            f"dataops).\n{tail}"
        )

    print("    vérification de l'ingestion côté Marquez…")
    sleep(5)  # laisse Marquez traiter l'événement COMPLETE
    job_after = _marquez_job_count(ol_ns)
    status, message = _phases.classify_marquez_ingest(job_before, job_after)

    # Teardown de l'émetteur jetable (parité bash : best-effort, --wait=false).
    _kubectl("-n", ns, "delete", "job", job, "--wait=false")

    if status == "ok":
        print(f"    ✓ {message}")
        return
    # skip (compteur illisible) comme fail (rien ingéré) → on LÈVE (pas de faux vert) :
    # un harnais e2e qui ne PEUT PAS prouver l'ingestion n'a pas verdi (honnêteté ADR 0034).
    raise _phases.E2EHookStubbed(
        f"dataops e2e : {message} — sensor OpenLineage → API Marquez à vérifier (verdict={status})"
    )


# Implémentations RÉELLES (façade) des hooks e2e, substituées au STUB du registre
# `phases.E2E_HOOKS` par le moteur (`launch`). SEUL `dataops_chain_emit_and_verify` est
# câblé ; `dataops_egress_internet_check` reste STUBÉ (absent d'ici → le moteur joue le
# stub du registre, qui LÈVE — hors périmètre, à câbler+prouver au banc). On mappe vers le
# NOM de la fonction façade (pas une référence directe) pour une résolution TARDIVE via
# `_e2e_hook_impl` — un test/patch de `_chain_emit_and_verify_banc` (attribut module) est
# alors honoré (une référence figée dans le dict l'ignorerait).
_E2E_HOOK_IMPL: dict[str, str] = {
    "dataops_chain_emit_and_verify": "_chain_emit_and_verify_banc",
}


def _e2e_hook_impl(name: str) -> Callable[..., None] | None:
    """Implémentation RÉELLE (façade) du hook e2e `name`, ou None s'il reste STUBÉ.

    Résolution TARDIVE : on lit l'attribut module nommé dans `_E2E_HOOK_IMPL` au moment de
    l'appel (via `globals()`), pour qu'un patch de test sur la fonction façade soit pris en
    compte. Un hook absent de la table (egress) → None : l'appelant joue le STUB du registre."""
    attr = _E2E_HOOK_IMPL.get(name)
    return globals().get(attr) if attr else None


def _launch_seed(phase: str, topo: Topology, derived: dict) -> _SeedLaunchResult:
    """Monte une phase DÉLÉGUÉE (seed) : route `gitops-seed` vers `seed.run_seed('banc', …)`.

    BRANCHE la garde BANC (`_assert_bench_target`, cible = banc Lima) et le `do(step)` RÉEL
    (`_seed_do_banc`, porté de gitea-init.sh). Mappe les verdicts du seed sur le moule du
    moteur de chemin (FAIL-FAST, AUCUN fallback, ADR 0046) :
      - `SeedGuardRefused` (garde banc refuse une cible prod) → `_path.IsolationRefused` (le
        moteur la re-lève → `_run_path_engine` la mappe en `_UsageError` → code 2) ;
      - `SeedError` (étape KO) → `_path.PathError` (fail-fast → code 1, aucun fallback).
    Un succès → `_SeedLaunchResult(ok=True)` (le moteur l'intègre comme une phase montée).

    Le seed PROD (`kind='prod'`, app-of-apps sur dirqual) N'EST PAS monté ici : le banc
    mono-nœud teste `'banc'` ; la prod se prouve au rebuild dirqual (garde `assert_prod_target`
    + `do()` prod à câbler+prouver, _SEED_BANC_TODO / seed.banc_todo). On ne fabrique PAS un
    faux montage prod (honnêteté ADR 0034) — `run_seed('prod', …)` reste accessible côté
    `nestor/seed.py`, sans montage façade tant que la preuve dirqual n'est pas en main."""
    _ = derived  # le seed lit la config du YAML (SeedConfig.from_topology), pas le faisceau -e
    if phase != "gitops-seed":
        raise _path.PathError(
            f"phase déléguée `{phase}` : aucun câblage seed connu (seul `gitops-seed` est porté)"
        )
    config = _seed.SeedConfig.from_topology(topo)
    # GATE avant le seed : Gitea ET Argo CD doivent être Ready (parité run-phases.sh:1082-1085).
    # Sans cette attente, le 1er geste (`gitea admin user create` via exec) tape un pod qui
    # démarre encore → la création échoue silencieusement et `token` casse APRÈS (constaté au
    # banc). On bloque jusqu'à Ready, comme le bash, avant le moindre geste mutant.
    for ns_dep, dep, to in (("gitea", "gitea", "120s"), ("argocd", "argocd-server", "180s")):
        roll = _kubectl("-n", ns_dep, "rollout", "status", f"deploy/{dep}", f"--timeout={to}")
        if not (roll and roll.returncode == 0):
            raise _path.PathError(
                f"seed gitops (banc) : {ns_dep}/{dep} non Ready avant le seed "
                f"(rollout status timeout {to}) — le socle GitOps doit être prêt (ADR 0046)"
            )
    do = _seed_do_banc(topo, config)
    print(f"→ {phase} : seed des DONNÉES via nestor/seed.py (gitea-init, garde banc)…")
    try:
        _seed.run_seed(
            "banc",
            config,
            assert_target=lambda: _assert_bench_target(f"nestor up ({phase})"),
            do=do,
        )
    except _seed.SeedGuardRefused as exc:
        # REFUS de garde (cible non-banc) = sécurité, PAS un échec de montage → IsolationRefused
        # (le moteur re-lève, _run_path_engine mappe en _UsageError → code 2). Rien n'a muté.
        raise _path.IsolationRefused(str(exc)) from exc
    except _seed.SeedError as exc:
        # Étape KO → fail-fast (ADR 0046), AUCUN fallback : remonte en PathError (code 1).
        raise _path.PathError(f"seed gitops (banc) : {exc}") from exc
    return _SeedLaunchResult(ok=True, message="seed banc gitops appliqué")


def _run_path_engine(
    topo: Topology,
    target: str,
    seq: list[str],
    stack_name: str,
    a_appliquer: set[str] | None = None,
) -> int:
    """Monte le chemin `target` via le moteur Python `nestor.path.run_path` (FLAG opt-in).

    Câble les callbacks ABSTRAITS du moteur sur le RÉEL (runner/kubectl/limactl), sur le
    moule de `cmd_bootstrap_seq` (closures à côté de l'I/O). FAIL-FAST : toute
    PathError/IsolationRefused remonte (mappée en code 1) — AUCUN fallback bash (ADR 0046).

    `a_appliquer` (issu de `compute_plan_state` = le RÉEL) RESTREINT la séquence montée aux
    phases MANQUANTES : le moteur SAUTE ce qui est déjà `done` (cohérence avec le plan ✓/+ ;
    plus de rejeu inutile d'une phase montée). None → monte toute `seq` (rétrocompat/tests).

    Callbacks (cf. `nestor.path.run_path`) :
    - `sequence` : la séquence calculée (`expected_phase_sequence`), FILTRÉE sur `a_appliquer`
      (ordre de `seq` préservé), injectée au moteur.
    - `assert_safe(phase)` : la GARDE d'isolation banc (`_assert_bench_target`) à CHAQUE phase
      (invariant de boucle, ADR 0097 §5.c) ; l'échappatoire KUBECONFIG (ADR 0065) est gérée
      DANS la garde. Pour une phase à play unitaire, on ajoute `_assert_inventory_safe`.
    - `launch(phase)` : montage via `runner.launch_phase` (UN passage + gate, parité bash —
      pas de double-passage `changed=0` qui fausserait les builds à tag mutable ; l'idempotence
      se prouve par le rejeu du chemin entier), `-e` restreints par `phases.extravars_for`.
    - `gate(phase)` : santé post-montage routée par `phases.gate_kind_for` (→ _wait_layer_healthy).
    - `provision('up')` : STUB → `run-phases.sh up` (artefact node-side irréductible, §5.b).
    - `bootstrap` : réutilise `_bootstrap.run_bootstrap` (déjà porté ailleurs) — le câblage
      transport (cp_ip/iface, CNI) reste à prouver au banc (§5.b)."""
    from nestor import phases as _phases

    # Inventaire DÉRIVÉ de la cible (ADR 0098) : pour la prod un temp `mkstemp`
    # éphémère qui vit TOUT le montage (les closures `assert_safe`/`launch` lisent
    # `ctx.inventory` jusqu'au bout), nettoyé en sortie ; banc = fichier réel.
    with _inventory_for(topo) as _inv:
        ctx = _path_context(topo, _inv, stack_name)
        private_data_dir = os.path.join(_ROOT, "bootstrap")
        ansible_cfg = os.path.join(private_data_dir, "ansible.cfg")
        derived = derive_run_params(topo)

        def assert_safe(phase: str) -> None:
            # INVARIANT DE BOUCLE (ADR 0097 §5.c) : garde d'isolation AVANT CHAQUE phase. La
            # garde gère l'échappatoire KUBECONFIG (ADR 0065 — elle rend tôt si exporté). Pour
            # une phase à play unitaire (Ansible SSH/exec), on valide AUSSI l'inventaire.
            _assert_bench_target(f"nestor up ({phase})", topo)
            if _phases.has_phase_plan(phase) and _phases.phase_plan(phase).playbook is not None:
                _assert_inventory_safe(f"nestor up ({phase})", ctx.inventory, topo)

        def launch(phase: str):
            # Montage d'UNE phase (UN SEUL passage + gate de santé) — PARITÉ run-phases.sh, qui
            # lance le playbook une fois puis gate (pas de double-passage `changed=0`). Choix
            # assumé : certaines phases buildent une image à TAG MUTABLE (`force_rebuild=true`,
            # portal/mlflow) → un rejeu est LÉGITIMEMENT `changed` (rebuild voulu). Exiger
            # `changed=0` par phase rendait un faux « idempotence cassée » sur ces builds. L'idem-
            # potence se prouve par le REJEU du CHEMIN entier (`nestor up` 2× → « rien à faire »,
            # ADR 0052), pas par un double-passage par play. Les `-e` sont RESTREINTS aux clés de
            # la phase (parité). Les hooks e2e (dataops) sont joués APRÈS succès du play.
            plan = _phases.phase_plan(phase)
            # PHASE DÉLÉGUÉE (playbook is None) : ce N'EST PAS un play Ansible mais une étape de
            # DONNÉES portée par `nestor/seed.py` (gitops-seed → gitea-init.sh). On NE fait donc
            # PAS `os.path.join(_ROOT, None)` (TypeError au montage) : on route vers le câblage
            # seed (run_seed banc, garde _assert_bench_target). Voir `_launch_seed`.
            if plan.playbook is None:
                return _launch_seed(phase, topo, derived)
            playbook = os.path.relpath(os.path.join(_ROOT, plan.playbook), private_data_dir)
            extravars = _phases.extravars_for(phase, derived)
            print(f"→ {phase} : montage via ansible-runner ({plan.playbook})…")
            # KUBECONFIG du play : le kubeconfig BANC rapatrié par bootstrap (ctx.kubeconfig_local
            # → .kubeconfigs/banc.config, server: 127.0.0.1:6443 — le forward de l'API). En
            # FROM-SCRATCH, os.environ['KUBECONFIG'] est VIDE au démarrage (le banc n'existe pas
            # encore), donc le lire ici ferait taper le module k8s sur l'IP INTERNE de la VM
            # (10.67.x, non routable depuis l'hôte → timeout 6443, vécu sur storage-simple). On
            # passe le kubeconfig du contexte, qui existe dès que bootstrap l'a rapatrié. Un
            # KUBECONFIG opérateur EXPLOITABLE (banc déjà monté) reste prioritaire — mais
            # `_operator_kubeconfig` écarte `/dev/null`/vide (garde 0053 `eval`é dans le shell),
            # sinon le play ceph héritait de `/dev/null` et levait « file is empty ».
            result = _runner.launch_phase(
                playbook,
                extravars,
                private_data_dir,
                ctx.inventory,
                ansible_config=ansible_cfg,
                kubeconfig=_operator_kubeconfig() or ctx.kubeconfig_local,
                target_kind=topo.target_kind,
            )
            # Harnais e2e post-montage (preuve au-delà de _wait_layer_healthy). On ne les joue
            # QUE si le montage a réussi (un hook après un play KO n'a pas de sens). `RunResult`
            # (un passage) n'a pas `.ok` (propre à IdempotenceResult) : succès = rc==0.
            # On route CHAQUE hook (par NOM) vers son IMPLÉMENTATION RÉELLE de façade
            # (`_E2E_HOOK_IMPL`, I/O kubectl) si elle existe, sinon vers le STUB du registre
            # (`phases.E2E_HOOKS`, qui LÈVE E2EHookStubbed). Aujourd'hui :
            #   - `dataops_chain_emit_and_verify` → CÂBLÉ (`_chain_emit_and_verify_banc`) ;
            #   - `dataops_egress_internet_check` → STUB (lève — hors périmètre, à câbler au banc).
            if result.rc == 0:
                for name in _phases.phase_plan(phase).e2e_hooks:
                    impl = _e2e_hook_impl(name) or _phases.E2E_HOOKS[name]
                    impl()  # CÂBLÉ : tente le geste (lève si KO) ; STUB : lève E2EHookStubbed
            return result

        def gate(phase: str) -> bool:
            # Santé post-montage routée par la NATURE de la gate (phases.gate_kind_for) :
            # ready-replicas / cr-phase (CR Rook Ceph) / presence → _wait_layer_healthy (qui lit
            # graph.LAYER_SIGNAL, source unique, et applique le bon critère readyReplicas/phase/
            # présence). `none` (phase sans maillon discriminant) → _wait_layer_healthy rend True.
            return _wait_layer_healthy(phase)

        def provision(_phase: str) -> int:
            return _provision_via_bash(topo, stack_name)

        def _runphases(*cmd: str) -> subprocess.CompletedProcess:
            # Rappel d'une sous-commande run-phases.sh (bash garde VM/CNI/inventaire/facts,
            # ADR 0049). Env DÉRIVÉ de la topo (NODES_OVERRIDE/STACK_NAME/EXPOSITION_MODE
            # + KUBECONFIG_LOCAL) — le bash en dérive le MÊME CP/NODES/WORKDIR que `provision`
            # (un seul WORKDIR `.work` ⇒ inventaire partagé) et écrit le kubeconfig à
            # l'emplacement décidé par Python (`.kubeconfigs/banc.config`, ADR 0102 volet B)
            # ⇒ lecture (ctx.kubeconfig_local) et écriture (KUBECONFIG_LOCAL) coïncident.
            return subprocess.run(  # noqa: S603 — chemin codé, env dérivé d'une topo validée
                ["bash", os.path.join(_ROOT, "bench", "lima", "run-phases.sh"), *cmd],
                check=False,
                env=_runphases_env(topo, stack_name),
                capture_output=True,
                text=True,
            )

        def bootstrap(_phase: str) -> int:
            # CÂBLAGE TRANSPORT du socle k8s+CNI (LOT 6, ADR 0097 §5.b). Même MOULE que
            # `cmd_bootstrap_seq` (déjà éprouvé) : Python orchestre la séquence Ansible via
            # `_bootstrap.run_bootstrap` (logique PURE testée), la façade branche l'I/O réelle
            # sur les briques bash IRRÉDUCTIBLES (limactl/CNI/kubeconfig, ADR 0049). À la
            # différence de `cmd_bootstrap_seq` qui RECEVAIT cp_ip/iface/inventaire déjà dérivés
            # par `phase_bootstrap` (bash), ICI la façade les dérive elle-même du Lima vivant.

            # 1. INVENTAIRE : `phase_up` (provision) NE l'écrit PAS (write_inventory vit dans
            # `phase_bootstrap`). On le pose donc via l'arm bash `inventory <control> [workers]`
            # (write_inventory byte-stable, ADR 0049) — control = nœuds `control`, workers = le
            # reste. La DÉCISION (qui est control/worker) vient de la TOPO ; bash REND le format.
            control_csv = ",".join(topo.control_nodes)
            workers_csv = ",".join(topo.worker_nodes)
            inv = _runphases("inventory", control_csv, *([workers_csv] if workers_csv else []))
            if inv.returncode != 0:
                raise _path.PathError(
                    f"socle (bootstrap) : écriture de l'inventaire (run-phases.sh inventory) "
                    f"en échec (rc={inv.returncode}) — {inv.stderr.strip()}"
                )

            # 2. cp_ip / iface DÉRIVÉS DU LIMA VIVANT via le contrat machine `emit_facts`
            # (run-phases.sh facts ⇒ `CP_IP=…\nL2_IFACE=…`, byte-stable, ADR 0049/0056). Le bash
            # garde la dérivation (vm_uservv2_ip/iface = limactl shell, artefact node-side) ;
            # Python CONSOMME les faits, ne pilote pas limactl. cp_ip = advertiseAddress du CP.
            facts = _runphases("facts")
            if facts.returncode != 0:
                raise _path.PathError(
                    f"socle (bootstrap) : dérivation des faits du banc (run-phases.sh facts) "
                    f"en échec (rc={facts.returncode}) — {facts.stderr.strip()}"
                )
            parsed = dict(
                ln.split("=", 1)
                for ln in facts.stdout.splitlines()
                if "=" in ln and not ln.startswith("#")
            )
            cp_ip = parsed.get("CP_IP", "")
            # NB : `L2_IFACE` n'est plus consommé ici — l'arm `cni` (ex `ha-cni <iface>`) ne
            # prend plus d'argument iface (geste 100 % CNI, exposition L4 NodePort ADR 0092).
            if not cp_ip:
                raise _path.PathError(
                    "socle (bootstrap) : `CP_IP` absent des faits du banc (banc provisionné ? "
                    f"sortie={facts.stdout.strip()!r})"
                )

            # 3. CALLBACK launch : montage d'UN playbook du socle (checks→…→join-workers) via
            # runner.launch_phase (le MÊME montage qu'`ha-3cp`/`cmd_bootstrap_seq`). Les 6
            # playbooks du socle sont à la racine de `private_data_dir` (bootstrap/), résolus
            # par leur nom (checks.yaml…). `-e control_plane_ip=<cp_ip>` (bootstrap_extravars).
            def launch_socle(playbook: str, extravars: dict):
                return _runner.launch_phase(
                    playbook,
                    extravars,
                    private_data_dir,
                    ctx.inventory,
                    ansible_config=ansible_cfg,
                    # Cohérence avec le callback `launch` : en from-scratch KUBECONFIG est vide au
                    # démarrage → repli sur le kubeconfig banc rapatrié (ctx.kubeconfig_local).
                    # `_operator_kubeconfig` écarte `/dev/null`/vide (garde 0053) pour ne pas
                    # hériter d'un kubeconfig poison exporté dans le shell.
                    kubeconfig=_operator_kubeconfig() or ctx.kubeconfig_local,
                    target_kind=topo.target_kind,
                )

            # 4. CALLBACK run_cni : la CNI (Cilium dans la VM) reste un artefact bash (ADR 0049).
            # On POUSSE l'arm `cni` — qui pose Cilium ET fetch le kubeconfig du CP
            # (admin.conf sed-rewrite vers KUBECONFIG_LOCAL == ctx.kubeconfig_local). Python
            # pousse, consomme un rc, ne lit pas la logique CNI/kubeconfig. Le fetch_kubeconfig
            # est donc COUVERT par ce même geste (pas de 2e rappel séparé). Le geste est 100 %
            # CNI (le vestige HA `ha-cni <iface>` a été renommé `cni`, plus d'argument iface).
            def run_cni() -> int:
                return _runphases("cni").returncode

            # 5. has_workers : DÉRIVÉ DE LA TOPO (le moteur connaît la topologie) — un control
            # unique sans worker OMET join-workers.yaml (cf. _bootstrap.bootstrap_playbooks).
            has_workers = bool(topo.worker_nodes)
            n_pb = len(_bootstrap.bootstrap_playbooks(has_workers=has_workers))
            print(f"→ bootstrap : socle k8s ({n_pb} playbooks via runner, CP {ctx.cp} {cp_ip})…")
            try:
                result = _bootstrap.run_bootstrap(
                    cp_ip,
                    launch=launch_socle,
                    run_cni=run_cni,
                    has_workers=has_workers,
                )
            except _runner.RunnerUnavailable as exc:
                raise _UsageError(str(exc)) from exc
            except _bootstrap.BootstrapError as exc:
                # FAIL-FAST (ADR 0046) : un échec du socle remonte en PathError → arrêt net,
                # AUCUN fallback bash, AUCUNE couche applicative montée après.
                raise _path.PathError(f"socle (bootstrap) : {exc}") from exc
            for step in result.steps:
                mark = "✓" if step.ok else "✗"
                print(f"  {mark} {step.name}{f' — {step.detail}' if step.detail else ''}")
            return 0 if result.built else 1
            # _BANC (ADR 0097 §5.b) : la façade TENTE désormais le vrai montage (inventaire +
            # facts + 6 playbooks + cni). Restent à VALIDER au banc mono-nœud (le mainteneur,
            # corriger-le-code-pas-l-état) : (a) que `run-phases.sh facts` rend bien CP_IP non
            # vide APRÈS `provision` (VM démarrée, IP user-v2 posée) ; (b) que l'arm `cni`
            # écrit le kubeconfig à l'emplacement EXACT attendu par les couches suivantes
            # (KUBECONFIG_LOCAL == ctx.kubeconfig_local) et que le forward API 127.0.0.1:6443
            # est joignable. Le format byte-stable de l'inventaire est déjà couvert (bats).

        # Le moteur SAUTE les phases déjà `done` : on monte uniquement `a_appliquer` (le RÉEL,
        # compute_plan_state), dans l'ORDRE de `seq`. None → toute la séquence (rétrocompat/tests).
        monter = [p for p in seq if p in a_appliquer] if a_appliquer is not None else list(seq)
        if a_appliquer is not None and not monter:
            print("→ moteur Python : rien à monter (tout est déjà à-jour, état réel).")
            return 0

        print(
            f"→ moteur Python (run_path) : chemin `{target}` ({len(monter)} phase(s)), CP {ctx.cp}."
        )

        def _record_run(res) -> None:
            # Consigne le run RÉUSSI dans runs-history.yaml (durées mesurées par le moteur +
            # commit git). NON BLOQUANT : une erreur de consignation ne doit PAS transformer un
            # montage réussi en échec (la preuve, c'est le montage ; la consignation l'archive).
            try:
                branche, commit = _runrecord.git_revision(_ROOT)
                entry = _runrecord.build_run_entry(
                    res,
                    topologie=stack_name,
                    profil=topo.catalog.get("profile", "base"),
                    now=dt.datetime.now(dt.UTC),
                    branche=branche,
                    commit=commit,
                    arch=topo.catalog.get("arch"),
                )
                _runrecord.append_run(_RUNS_HISTORY, entry)
                print(f"  ✓ run consigné (runs-history) — commit {commit}, {entry['total_s']}s.")
            except OSError as exc:
                _warn(f"consignation runs-history échouée (non bloquant) : {exc}")

        try:
            result = _path.run_path(
                topo,
                target,
                sequence=lambda _t, _g: list(monter),
                launch=launch,
                gate=gate,
                assert_safe=assert_safe,
                provision=provision,
                bootstrap=bootstrap,
                # record : consignation runs-history (#216, ex-`metro_record_run` de
                # metrology.sh RETIRÉ ADR 0101). Appelé UNIQUEMENT sur un run from-scratch
                # RÉUSSI (le moteur ne l'invoque qu'après succès) → jamais une fausse preuve.
                # Porte le COMMIT git (traçabilité, `-dirty` si arbre sale). Les MÉTRIQUES
                # (cpu/ram Prometheus) sont OMISES (monitoring déployé après le socle, non lisible
                # ici — honnête). Non bloquant : un échec de consignation ne casse pas le montage.
                record=_record_run,
            )
        except _runner.RunnerUnavailable as exc:
            raise _UsageError(str(exc)) from exc
        except _path.IsolationRefused as exc:
            # REFUS d'isolation = garde de sécurité, pas un échec de montage → code usage (2).
            raise _UsageError(str(exc)) from exc
        except _phases.E2EHookStubbed as exc:
            # Hook e2e non câblé : honnêteté (ne pas verdir à tort) → on ARRÊTE NET (ADR 0034).
            print(f"  ✗ _BANC : hook e2e à câbler — {exc}", file=sys.stderr)
            return 1
        except _path.PathError as exc:
            # FAIL-FAST : montage KO → on relève le verdict (jamais de fallback bash, ADR 0046).
            print(f"  ✗ {exc}", file=sys.stderr)
            return 1
        for step in result.steps:
            mark = "✓" if step.ok else "✗"
            print(f"  {mark} {step.name}{f' — {step.detail}' if step.detail else ''}")
        return 0 if result.built else 1


def cmd_up(args: argparse.Namespace) -> int:
    """`up` : monte la stack active de bout en bout (calque `pulumi up`).

    L'ENTRÉE déclarative complète (inversion de frontière, ADR 0049/0056) : lit la
    stack active → DÉRIVE le chemin nommé (default_target) → affiche le PLAN (les
    couches) → CONFIRME → MONTE la séquence via le moteur Python `nestor.path.run_path`
    (`_run_path_engine`, ADR 0097 — SEUL moteur depuis le retrait du filet bash). Le
    code de sortie du montage est propagé.

    Là où `next` monte UNE couche (1er drift), `up` monte TOUTE la séquence. Code 0
    si le montage réussit ; 1 si le montage échoue ; 2 (usage) si confirmation
    refusée / chemin incohérent avec le backend."""
    path = _resolve(args.file)
    topo = load_topology(path)
    # Garde APRÈS le chargement : `up` from-scratch d'un banc (target_kind: bench) est légitime
    # même sans kubeconfig de banc existant (c'est `up` qui le crée) — la topo lima est le
    # signal sûr. Une topo prod reste sous garde stricte (cible prouvée requise).
    _assert_bench_target("nestor up", topo)
    target = args.target or default_target(topo)
    try:
        seq = expected_phase_sequence(topo, target)
    except PlanError as exc:
        raise _UsageError(str(exc)) from exc
    stack_name = _stack_id(path)  # identité = nom de fichier (ADR 0102 volet B)

    # ADR 0083 : l'ordre vient TOUJOURS de `seq` (expected_phase_sequence → graphe
    # atomique) ; le moteur Python (`_run_path_engine`) MONTE cette séquence (un seul
    # moteur depuis le retrait du filet bash). Un `--target <preset>` explicite (atlas,
    # ha-3cp…) ne change que le NOM du chemin, pas l'exécuteur.

    # PLAN annoté — DÉRIVÉ du MÊME calcul que `preview`/`next` (compute_plan_state) pour
    # que les trois rendent le même verdict (fin de la divergence preview≠next≠up). `up`
    # monte TOUTE la séquence (idempotence run-phases.sh) ; l'annotation ✓/+ informe juste
    # l'opérateur de ce qui est DÉJÀ en place. Sonde RÉELLE identique à preview (ADR 0090).
    declared = topo.control_nodes + topo.worker_nodes
    nodes_ready = _ready_nodes(topo.target_kind)
    observed_socle = observed_done_phases(declared, _real_vms(topo.target_kind), nodes_ready)
    observed_layers = _probe_observed_layers(seq, nodes_ready)
    # `done` = RÉEL SEUL (refonte lot 6) — même calcul que preview/next. `cmd_up` monte
    # TOUTE la séquence et n'affiche pas de verdict de fraîcheur (juste +/✓ à-jour) : il
    # ne lit donc PLUS l'historique ici (la fraîcheur, #216, reste lue par preview/next).
    state = compute_plan_state(seq, observed_socle, observed_layers)
    a_appliquer = set(state.a_appliquer)

    # Affiche le PLAN (les couches à monter) avant de confirmer — comme `preview`.
    print(f"stack : {stack_name}  →  chemin : {target}")
    print("Couches à monter (séquence complète) :")
    for phase in seq:
        mark = "+" if phase in a_appliquer else "✓"
        print(f"  {mark} {phase_label(phase)}")

    if not _confirm_apply(target, assume_yes=args.yes):
        print("montage annulé.", file=sys.stderr)
        return 2

    # ── MOTEUR DE MONTAGE (ADR 0097) ───────────────────────────────────────────────
    # Le moteur Python `nestor.path.run_path` est le SEUL moteur : prouvé de bout en bout
    # au banc mono-nœud (from-scratch, 10 couches up→…→portal + preuve e2e OpenLineage→
    # Marquez, ingestion vérifiée). L'ancien filet bash `--engine=bash`/run-phases.sh a été
    # RETIRÉ (un seul moteur, plus de double source de vérité). La garde d'isolation banc
    # s'applique ICI (`_assert_bench_target` en tête) ET à CHAQUE phase (callback
    # `assert_safe`, invariant de boucle ADR 0097 §5.c). Le moteur Python ne porte PAS l'arm
    # HA propre (amorçage VIP/etcd) : un chemin `ha-3cp` lèvera proprement (callback `ha`
    # stubé) plutôt que de monter à moitié — on laisse le moteur trancher (fail-fast).
    # `a_appliquer` (le RÉEL, compute_plan_state) : le moteur SAUTE les phases déjà `done`.
    return _run_path_engine(topo, target, list(seq), stack_name, a_appliquer)


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


def _monter_phase(topo: Topology, phase: str, run_params: dict, stack_name: str) -> int:
    """Monte UNE phase choisie : amont (run-phases.sh up/bootstrap) ou play unitaire
    (ansible-runner). Renvoie 0 (ok) / 1 (échec run) ou lève _UsageError (usage).

    Extrait de cmd_next pour être partagé par le chemin « 1re couche » et le menu
    multi-couches : une fois la phase CHOISIE, son montage est identique. `stack_name` =
    `stack_id` (nom de fichier, ADR 0102 volet B) — l'appelant le dérive de son `path`
    (`_monter_phase` n'a pas le chemin de la topo en scope)."""
    playbook_rel = phase_playbook(phase)
    # Phases SANS playbook unitaire :
    #   - `gitops-seed` (init Gitea, DONNÉES) → câblage Python `_launch_seed` (seed.run_seed),
    #     le MÊME que `_run_path_engine` (un seul moteur depuis le retrait du filet bash) ;
    #   - phases AMONT à arm run-phases.sh node-side IRRÉDUCTIBLE (`up` : provisioning limactl)
    #     → délégation à l'arm bash du MÊME nom (ADR 0049).
    # On DÉRIVE de `playbook is None` (pas d'une liste codée) : sinon le menu propose une
    # couche que `next` refuse ensuite de monter — incohérent.
    if playbook_rel is None:
        if phase == "gitops-seed":
            # Phase DÉLÉGUÉE seed : route vers le câblage Python (parité _run_path_engine), pas
            # un arm bash (retiré). Mappe les verdicts du moteur (PathError/IsolationRefused →
            # fail-fast / usage) comme `_run_path_engine`.
            _assert_bench_target(f"nestor next ({phase})")
            print(f"→ {phase} : {_quoi_couche(phase)} via nestor/seed.py…")
            try:
                _launch_seed(phase, topo, run_params)
            except _path.IsolationRefused as exc:
                raise _UsageError(str(exc)) from exc
            except _path.PathError as exc:
                print(f"échec de la phase `{phase}` : {exc}", file=sys.stderr)
                return 1
            print(f"✓ `{phase}` terminée — relancer `next` pour l'étape suivante ({stack_name}).")
            return 0
        if not _has_runphases_arm(phase):
            raise _UsageError(
                f"la phase `{phase}` n'a ni play unitaire ni câblage Python/arm run-phases.sh — "
                "non lançable via `nestor next`"
            )
        _assert_bench_target(f"nestor next ({phase})")
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
    # Inventaire DÉRIVÉ de la cible (ADR 0098) : temp prod éphémère / fichier banc.
    with _inventory_for(topo) as inventory:
        ansible_cfg = os.path.join(private_data_dir, "ansible.cfg")
        # Côté prod l'inventaire dérivé existe TOUJOURS (`_inventory_for` vient de le
        # rendre). Côté banc, le `.work/inventory.yaml` peut manquer (banc non monté) →
        # sans lui ansible-runner prendrait le chemin pour un nom d'hôte. On l'arrête net.
        if not os.path.exists(inventory):
            rel = os.path.relpath(inventory, _ROOT)
            raise _UsageError(
                f"inventaire du banc absent : {rel} — monter le banc d'abord "
                "(`bench/lima/run-phases.sh up`, qui génère l'inventaire Lima)"
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
    # ADR 0090 : MÊME résolution de cible que `preview` — sans elle, `next` est AVEUGLE
    # en prod (`_ready_nodes`/`_observed_layers` vides → l'état réel semble vide → `next`
    # re-propose la 1re couche, Kubernetes, sur une prod saine : DANGEREUX). Doit précéder
    # tout calcul d'`observed_*`. Réoriente vers `stack select` si la topo n'a pas de cible.
    _resolve_prod_kubeconfig_into_env(topo, path, no_input=getattr(args, "no_input", False))
    runs = load_runs(args.history or _RUNS_HISTORY)
    now = int(dt.datetime.now(tz=dt.UTC).timestamp())
    target = args.target  # None → plan.default_target le déduit
    # Run de référence ANCRÉ SUR LA STACK (sa topologie), comme `preview` (ADR 0052/0056
    # §7) — JAMAIS un fallback `latest_run` global qui attraperait le run d'une AUTRE
    # topologie (ex. un run `atlas-ceph` multi-node servant de référence à un banc
    # `1cp` local-path → `done` pollué par ceph/sc/datalake/gitops-seed → `next`
    # croit gitops-seed fait et dit « à jour » alors que `preview` le voit « à installer »).
    # `last_run_for_topology` ne retombe sur AUCUN run d'une autre stack (cf. son docstring) —
    # mais réconcilie l'ancienne clé `catalog.topology` via `history.STACK_ID_ALIASES` pour ne
    # pas orpheliner les runs consignés avant le renommage (ADR 0102 volet B / ADR 0052).
    stack_name = _stack_id(path)  # identité = nom de fichier (ADR 0102 volet B)
    run = last_run_for_topology(runs, stack_name)
    etat_frais, _ = verdict_for_run(run, target, now)
    # Sonde du RÉEL — IDENTIQUE à `cmd_preview` (ADR 0052/0056 §7, ADR 0090). Le socle
    # observé (VMs présentes / nœud Ready) et les couches applicatives observées saines
    # alimentent LE calcul partagé `compute_plan_state` ci-dessous : `next` dérive ainsi
    # le MÊME `a_appliquer`/`done` que `preview` (fin de la divergence preview≠next).
    declared = topo.control_nodes + topo.worker_nodes
    nodes_ready = _ready_nodes(topo.target_kind)
    observed_socle = observed_done_phases(declared, _real_vms(topo.target_kind), nodes_ready)
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
    # Couches observées saines (gating ADR 0084) — MÊME sonde que preview.
    observed_layers = _probe_observed_layers(seq, nodes_ready)
    # LE calcul partagé : `done`/`a_appliquer` dérivés EXACTEMENT comme `cmd_preview` —
    # du RÉEL SEUL (refonte lot 6), PLUS de l'historique. `installable_now` ne fait plus
    # que TRIER `a_appliquer` par satisfaction des dépendances → next == preview. La
    # fraîcheur (etat_frais) reste séparée : elle ne décide pas `done`, juste l'affichage.
    state = compute_plan_state(seq, observed_socle, observed_layers)
    done = set(state.done)
    observed = observed_socle | observed_layers
    try:
        montables = installable_now(
            topo,
            target,
            done,
            etat_frais,
            deps_fn=lambda: phase_deps(backend),
            observed_done=observed,
            a_appliquer=set(state.a_appliquer),
        )
    except (PlanError, TopologyError) as exc:
        raise _UsageError(str(exc)) from exc

    if not montables:
        # Rien à monter : suggest_next porte le message « à jour » détaillé. Il faut lui
        # passer `done | observed` (PAS `done` seul, l'historique) — sinon `next`
        # CONTREDIT `preview` : une couche faite mais non consignée (run non consigné /
        # cache socle) ressortirait comme « 1er drift non encore joué » alors que preview
        # la voit ✓ à-jour. Le RÉEL prime (ADR 0052/0056 §7), comme dans `cmd_preview`.
        sugg = suggest_next(
            topo, target, done | observed, etat_frais, run_params=run_params, observed=observed
        )
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
    # (un seul geste, pas de double [oui/NON] redondant).
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
    return _monter_phase(topo, phase, run_params, _stack_id(path))


def cmd_bootstrap_seq(args: argparse.Namespace) -> int:
    """Orchestre le socle k8s (`bootstrap`) — la partie ANSIBLE (interne, ADR 0063).

    Migration de bootstrap_node_sequence vers Python : lance les playbooks du socle
    (checks→…→join-workers) via runner.launch_phase, avec
    `-e control_plane_ip=<cp_ip>`. `join-workers` est SAUTÉ si l'inventaire n'a aucun
    worker (control unique). L'inventaire, la dérivation de cp_ip/iface, la CNI
    (Cilium dans la VM) et le kubeconfig restent à run-phases.sh (briques bash, ADR
    0049) ; cette commande reçoit cp_ip/inventaire déjà dérivés du banc et rappelle
    l'arm `cni` pour la CNI. La logique (séquence, fail-fast) est testée sans
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
            target_kind="bench",
        )

    def run_cni() -> int:
        # CNI (+ kubeconfig) : brique bash réutilisée (arm `cni`). L'exposition est en L4
        # NodePort (ADR 0092) → plus de Gateway/LB-IPAM, et l'arm `cni` (ex `ha-cni
        # <iface>`) ne prend plus d'argument iface (geste 100 % CNI). L'arm dérive le CP
        # du 1er nœud `control` de NODES (plus de `CP=cp1` codé) ; NODES vient de
        # NODES_OVERRIDE, posé par `up` et hérité tout au long de la chaîne (up →
        # run-phases.sh → bootstrap-seq → ici).
        return subprocess.run(  # noqa: S603 — chemin codé, arguments contrôlés
            [
                "bash",
                os.path.join(_ROOT, "bench", "lima", "run-phases.sh"),
                "cni",
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
    # `_matches_stack` réconcilie l'ancienne clé `catalog.topology` (STACK_ID_ALIASES,
    # ADR 0102 volet B) — sinon les runs consignés avant le renommage seraient invisibles
    # ici (6ᵉ site d'identité, match INLINE distinct de last_run_for_topology).
    stack = None if args.all else _active_stack_name(args.file)
    scope = [r for r in runs if _matches_stack(r.topologie, stack)] if stack is not None else runs
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
    # Destruction par DÉCOUVERTE (ADR 0101) : `remove` défait toute la clôture en UN geste
    # (aval cascadé + node-side Ceph), au lieu de boucler `run-phases.sh rollback` (ex-bash).
    topo = load_topology(_resolve(args.file))

    def destroy_layer(phase: str) -> int:
        return _remove_by_discovery(
            phase,
            full=args.full,
            assume_yes=True,  # déjà confirmé par run_roundtrip en amont
            topo=topo,
            inventory_path=_BENCH_INVENTORY,
        )

    try:
        result = _roundtrip.run_roundtrip(
            args.phase, allow_full=args.full, assume_yes=args.yes, destroy_layer=destroy_layer
        )
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
    garde mutante ; le rollback effectif (mutant) passe par `remove`, prouvé au banc."""
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
    print("→ dry-run : RIEN détruit (aperçu ADR 0079 ; le delete effectif via `remove`).")
    return 0


# ── Rollback PAR DÉCOUVERTE (mutant) — SEUL chemin (ADR 0079/0101, #372) ─────────────────
# Plus de chemin TABLE (run_remove → rollback-lib.sh, supprimés) : la découverte couvre TOUT.
# Ce chemin défait les ressources NAMESPACÉES par découverte (api-resources + ownerReferences)
# en supprimant les RACINES (le GC k8s cascade), force les CR à finalizer, finalise les ns
# wedgés, PUIS efface le node-side Ceph (wipe des disques) ; il NE touche PAS aux CRD
# cluster-scoped (élidées à dessein, opérateur réutilisable). La LOGIQUE (quoi cibler, quel
# geste de déblocage) est PURE dans nestor/ownership.py ; ici, uniquement l'I/O kubectl borné,
# env banc (jamais la prod, ADR 0053/0049).


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


def _remove_by_discovery(
    phase: str,
    *,
    full: bool,
    assume_yes: bool,
    topo: Topology | None = None,
    inventory_path: str | None = None,
) -> int:
    """`remove` (ADR 0079/0101) : défait la clôture de `phase` PAR DÉCOUVERTE (seul chemin).

    Sonde les ressources réelles (api-resources × ns de la clôture), calcule les CIBLES
    (racines filtrées du bruit, module PUR `ownership`), confirme l'arbre AVANT, puis
    supprime chaque racine — le GC k8s cascade les possédés. NE s'arrête PAS au 1er échec
    (ADR 0079 §4) : agrège les verdicts. Les cibles qui traînent sont ré-sondées et
    débloquées selon `classify_stuck` (force-delete / retrait finalizer). Puis (étape B)
    supprime les CRD cluster-scoped DÉCOUVERTES comme appartenant à la clôture
    (`ownership.deletable_crds` : tous leurs CR dans les ns de la clôture — jamais une CRD
    partagée). Enfin finalise les namespaces possédés (ns wedgé → /finalize). Gardes : cible
    banc (appelant), `--full` pour une clôture de stockage, confirmation. Code 0 si tout
    parti, 1 si résidu / refus."""
    from nestor import ownership

    try:
        layers = _roundtrip.closure(phase)
        if _roundtrip.involves_storage(phase) and not full:
            raise _UsageError(
                f"`remove {phase}` touche une clôture de STOCKAGE {layers} "
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

    # StorageClass CLUSTER-SCOPED de la couche (ADR 0079, début de #392) : la découverte
    # namespacée ci-dessus ne les voit pas (les SC sont cluster-scoped). MAIS une SC est
    # découvrable SANS ambiguïté par son `provisioner` (contrairement aux CRD, dont le lien à
    # l'opérateur n'est pas fiable) : on retire les SC dont le provisioner appartient à la couche
    # de stockage retirée (ceph → `rook-ceph.*`). PV/webhooks/CRD restent hors périmètre (#392).
    if _roundtrip.involves_storage(phase):
        residus.extend(_remove_owned_storage_classes())

    # Node-side Ceph (ex-`phase_rollback`) : APRÈS le retrait k8s, wipe les disques + /var/lib/
    # rook sur chaque nœud (seul `ceph` a du node-side). La topo (devices dérivés) + l'inventaire
    # (transport) sont fournis par l'appelant ; absents (None) en test pur → on saute le node-side.
    if topo is not None and inventory_path is not None:
        node_echecs = _rollback_node_side_ceph(phase, topo, inventory_path=inventory_path)
        residus.extend(f"node/{n}" for n in node_echecs)

    if residus:
        print(f"→ suppression INCOMPLÈTE — résidus : {residus} (relancer pour finir).")
        return 1
    print(f"→ couche supprimée par découverte — re-monter avec `nestor next` ({phase}).")
    return 0


# `storage/ceph/cleanup.sh` RESTE bash (node-side irréductible, ADR 0049/0101) : il wipe les
# disques + `/var/lib/rook` DANS la VM. Python ne fait que le POUSSER (jamais réécrire sa logique).
_CEPH_CLEANUP_SCRIPT = os.path.join(_ROOT, "storage", "ceph", "cleanup.sh")


def _remove_owned_storage_classes() -> list[str]:
    """Supprime les StorageClass CLUSTER-SCOPED appartenant à Ceph (provisioner `rook-ceph.*`),
    résidu que la découverte NAMESPACÉE ne voit pas (début de #392). Renvoie la liste des SC en
    échec de suppression (vide = toutes parties, ou aucune à retirer / cluster injoignable).

    Une SC est découvrable SANS ambiguïté par son `provisioner` (`discover.provisioner_is_ceph`,
    source unique) — contrairement aux CRD/webhooks, laissés hors périmètre (#392 complet). On
    NE touche PAS les SC local-path (secours) ni celles d'un autre provisioner."""
    jsonpath = "jsonpath={range .items[*]}{.metadata.name}={.provisioner}{'\\n'}{end}"
    proc = _kubectl("get", "storageclass", "-o", jsonpath)
    if proc is None or proc.returncode != 0:
        return []  # pas de SC / cluster injoignable → rien à faire (non bloquant)
    echecs: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        name, _, provisioner = line.partition("=")
        if not _discover.provisioner_is_ceph(provisioner):
            continue
        res = _kubectl("delete", "storageclass", name)
        if res is not None and res.returncode == 0:
            print(f"  ✓ delete StorageClass/{name} (cluster-scoped, provisioner {provisioner})")
        else:
            detail = "injoignable" if res is None else f"rc={res.returncode}"
            _warn(f"  ✗ StorageClass/{name} non supprimée ({detail})")
            echecs.append(f"sc/{name}")
    return echecs


def _rollback_node_side_ceph(phase: str, topo: Topology, *, inventory_path: str) -> list[str]:
    """Wipe NODE-SIDE Ceph après le retrait k8s (ex-`phase_rollback`, ADR 0054) : sur CHAQUE
    nœud, pousse `storage/ceph/cleanup.sh` (disques + `/var/lib/rook`) via `_node_exec_script`.
    N'agit QUE si la clôture de `phase` a du node-side (seul `ceph`). Renvoie la liste des nœuds
    en échec (vide = tous propres). Les env (devices) sont DÉRIVÉS de la topo (`ceph_wipe_env`).

    ⚠️ NON PROUVÉ au banc tant qu'un banc Ceph 3-VM (installation) n'a pas rejoué ce chemin
    (ADR 0034) : le k8s est couvert par la découverte, mais le wipe disques exige des OSD réels
    à effacer. Preuve = monter ceph.yaml, `remove ceph --full`, constater lsblk/sgdisk
    vierges (les disques redeviennent sans partition, /var/lib/rook absent)."""
    if not _graph.rollback_phase_has_nodeside(phase):
        return []
    env = ceph_wipe_env(topo)
    nodes = topo.control_nodes + topo.worker_nodes
    print(
        f"  Node-side Ceph : wipe disques + /var/lib/rook sur {len(nodes)} nœud(s) "
        f"(env dérivé : {env.get('DATA_DEVICE_GLOB')}, {env.get('NVME_BLOCK_DEVICE')})."
    )
    echecs: list[str] = []
    for node in nodes:
        proc = _node_exec_script(node, _CEPH_CLEANUP_SCRIPT, inventory_path=inventory_path, env=env)
        if proc is None or proc.returncode != 0:
            detail = "injoignable" if proc is None else f"rc={proc.returncode}"
            _warn(f"  ✗ {node} : cleanup.sh node-side a échoué ({detail}) — résidu disque possible")
            echecs.append(node)
        else:
            print(f"  ✓ {node} : disques + /var/lib/rook nettoyés")
    return echecs


def cmd_remove(args: argparse.Namespace) -> int:
    """`remove` : supprime UNE couche applicative et sa clôture descendante (inverse de `next`).

    DESTRUCTIF (efface la couche + ses données). Détruire une couche entraîne celle de ses
    dépendantes (clôture, ADR 0066) — affichées et confirmées AVANT. Une clôture de STOCKAGE
    (≈ démontage du socle) exige `--full`. `--yes` saute la confirmation (hors TTY).

    Mêmes gardes d'isolation que `next` (ADR 0053) : la suppression vise le banc (kubeconfig
    + node-side ceph) → `_assert_bench_target` (jamais la prod).

    DÉCOUVERTE — SEUL chemin (ADR 0101) : `remove` défait la clôture PAR DÉCOUVERTE
    d'appartenance (api-resources + ownerReferences) — supprime les RACINES namespacées (le GC
    k8s cascade), force les CR à finalizer, finalise les ns wedgés, PUIS efface le node-side
    Ceph (wipe des disques via `_node_exec_script`, topo + inventaire requis). Plus de table
    « nom/kind oublié » à maintenir, et plus de pont bash `run-phases.sh rollback` /
    rollback-lib.sh (supprimés) : la découverte couvre le k8s namespacé + les StorageClass
    cluster-scoped de la couche stockage (retirées par PROVISIONNER, `rook-ceph.*` → sans
    ambiguïté, début de #392) + le node-side. On ne supprime PAS les CRD ni les webhooks
    cluster-scoped (le lien CRD→opérateur n'est pas découvrable de façon fiable — ils restent,
    l'opérateur est réutilisable ; reste de #392).

    `--dry-run` montre l'arbre découvert sans rien détruire. Garde-fou destructif : sans
    `--yes`, on EXIGE une confirmation (l'opérateur voit l'arbre AVANT).

    Code 0 si supprimé/dry-run, 1 si une étape échoue / confirmation refusée, 2 si usage."""
    if args.dry_run:
        return _remove_dry_run(args.phase)
    # DÉCOUVERTE (ADR 0079/0101) : seul chemin. La découverte défait tout le k8s namespacé
    # (CR + finalize ns) PUIS le node-side Ceph (wipe disques via `_node_exec_script`) — plus
    # de chemin table (rollback-lib.sh supprimé). La topo (devices) + l'inventaire (transport)
    # sont requis pour le node-side.
    _assert_bench_target(f"nestor remove ({args.phase}, découverte)")
    topo = load_topology(_resolve(args.file))
    return _remove_by_discovery(
        args.phase,
        full=args.full,
        assume_yes=args.yes,
        topo=topo,
        inventory_path=_BENCH_INVENTORY,
    )


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
    "check-freshness": cmd_check_freshness,
}

# Verbes du groupe `test` : épreuves jouables + réversibilité (scenarios = ex-epreuves).
_TEST_DISPATCH = {
    "scenarios": cmd_epreuves,
    "smoke": cmd_smoke,
    "roundtrip": cmd_roundtrip,
}


def cmd_artifact(args: argparse.Namespace) -> int:
    """Routeur du groupe `artifact` (generate | diff | runs | metrics | check-freshness)."""
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
    # `env` SUPPRIMÉE (LOT 8, ADR 0097 §3) : `nestor` maintient des contextes kubectl
    # nommés (posés par `stack select`). Remplaçant ergonomique = `nestor kubectl …` :
    "kubectl": cmd_kubectl,  # kubectl sur la cible de la stack active (ex-`nestor env`)
    "ansible": cmd_ansible,  # playbook sur la cible active, inventaire DÉRIVÉ (ADR 0098)
    "access": cmd_access,  # accès dev natif (URLs NodePort + secrets + .env) — ADR 0048/0101
    "scale": cmd_scale,  # ajuste les replicas au nb de nœuds Ready (ADR 0072, runtime)
    "discover": cmd_discover,  # reconstruit un topology.yaml depuis le réel (ADR 0074, inverse de generate)  # noqa: E501
    "refresh": cmd_refresh,  # réaligne la topo active sur le réel voulu (ADR 0076, fusion + confirmation)  # noqa: E501
    "up": cmd_up,  # calque `pulumi up` : monte TOUTE la séquence (délègue à run-phases.sh)
    "next": cmd_next,  # applique la PROCHAINE couche (1er drift, granularité fine)
    "remove": cmd_remove,  # supprime UNE couche + sa clôture (inverse de next, ADR 0054)
    "down": cmd_destroy,  # symétrique de `up` (run-phases.sh)
    "destroy": cmd_destroy,  # ALIAS rétrocompat (calque `pulumi destroy`)
    # Groupes noun-verb (annexe rangée) : artefacts dérivés/constatés + épreuves.
    "artifact": cmd_artifact,
    "test": cmd_test,
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
            "  down        supprimer les machines (VMs) de la stack active\n"
            "\n"
            "Commandes annexes :\n"
            "  kubectl     lancer kubectl sur la cible de la stack active (sans export)\n"
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
    p_stack_sel.add_argument(
        "--no-input",
        action="store_true",
        help="mode non interactif (CI) : n'écrit pas le kubeconfig de la topo, ne prompte pas",
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
        choices=["prod", "bench"],
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
        help="$HOME du poste (chemin SSH Lima ; requis si --kind bench)",
    )
    p_gen.add_argument("-o", "--output", default=None, help="fichier de sortie (défaut : stdout)")

    p_diff = artifact_sub.add_parser(
        "diff", help="vérifier que l'inventaire généré n'a pas dérivé (échoue si différence)"
    )
    _add_file(p_diff)
    p_diff.add_argument(
        "--kind",
        choices=["prod", "bench"],
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

    p_fresh = artifact_sub.add_parser(
        "check-freshness",
        help="verdict BLOQUANT de fraîcheur par chemin (cron CI ; 0 frais / 1 périmé / 2 vide)",
    )
    p_fresh.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : bench/lima/)"
    )
    p_fresh.add_argument(
        "--seuil-jours",
        type=int,
        default=None,
        help="seuil global du repli sans historique (défaut : 7)",
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

    # `env` SUPPRIMÉE (LOT 8, ADR 0097 §3) — plus de sous-parser. Remplaçant ergonomique :
    # `nestor kubectl …` exécute kubectl avec le kubeconfig de la cible (stack active),
    # résolu par _bench_kubeconfig (jamais la prod par accident). Plus de `export` à eval.
    p_kubectl = sub.add_parser(
        "kubectl",
        help="lancer kubectl sur la cible de la stack active (remplace `nestor env`)",
    )
    p_kubectl.add_argument(
        "-f", "--file", default=None, help="topology.yaml à viser (défaut : stack active)"
    )
    # REMAINDER : garde le sous-parser cohérent (aide `nestor kubectl -h`). MAIS le vrai
    # découpage se fait dans `main()` via `_split_passthrough` AVANT argparse : REMAINDER est
    # buggé quand un flag est en TÊTE (`nestor kubectl -n …` → « unrecognized -n »), argparse
    # le matchant au parent avant d'activer REMAINDER. L'interception amont couvre ce cas.
    p_kubectl.add_argument(
        "kubectl_args", nargs=argparse.REMAINDER, help="arguments passés à kubectl (bruts)"
    )

    p_ansible = sub.add_parser(
        "ansible",
        help="lancer un playbook sur la stack active (inventaire dérivé, ADR 0098)",
    )
    p_ansible.add_argument(
        "-f", "--file", default=None, help="topology.yaml à viser (défaut : stack active)"
    )
    p_ansible.add_argument(
        "playbook", help="playbook (ex. checks.yaml, security/secure.yml — résolu sous bootstrap/)"
    )
    # REMAINDER : le playbook vient EN PREMIER, les flags ansible APRÈS
    # (`nestor ansible checks.yaml --limit cp1 --tags os --check`). Limite connue :
    # un flag placé AVANT le playbook ne serait pas capturé — le playbook d'abord.
    p_ansible.add_argument(
        "ansible_args", nargs=argparse.REMAINDER, help="arguments passés à ansible-playbook"
    )

    p_access = sub.add_parser(
        "access",
        help="ouvrir l'accès dev : URLs des services + identifiants (--stop pour fermer)",
    )
    p_access.add_argument(
        "--stop", action="store_true", help="ferme les kubectl port-forward ouverts"
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

    # `down` (symétrique de `up`, cf. run-phases.sh) ; `destroy` reste un ALIAS (rétrocompat
    # scénarios/scripts + calque `pulumi destroy`).
    p_destroy = sub.add_parser(
        "down",
        aliases=["destroy"],
        help="supprimer les machines (VMs) de la configuration active",
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
    p_up.add_argument(
        "--history", default=None, help="chemin du runs-history.yaml (défaut : bench/lima/)"
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
    p_epr.add_argument(
        "--run",
        action="store_true",
        help="LANCER les scénarios prêts (couche montée) via run-all.sh, pas seulement lister",
    )
    p_epr.add_argument(
        "--full",
        action="store_true",
        help="avec --run : inclure aussi les scénarios DESTRUCTIFS/OFFENSIFS (ssh/chaos, "
        "BANC=1) — sinon seuls les non-destructifs (kubectl/API) sont joués",
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
    # `cmd_roundtrip` charge la topo (`args.file`) pour bâtir le `destroy_layer` par
    # découverte (devices node-side dérivés de la topo, ADR 0101).
    _add_file(p_rt)

    return ap


def _build_bootstrap_parser() -> argparse.ArgumentParser:
    """Parser DÉDIÉ à la commande interne `bootstrap-seq` (hors du menu public).

    Appelée par run-phases.sh:phase_bootstrap avec --cp-ip/--l2-iface/--inventory
    dérivés du banc — orchestre les 6 playbooks du socle en Python (migration de
    bootstrap_node_sequence). Interne, routée à part dans main()."""
    ap = argparse.ArgumentParser(prog="topology bootstrap-seq")
    ap.add_argument("--cp-ip", required=True, dest="cp_ip", help="IP réelle du CP primaire")
    ap.add_argument("--l2-iface", required=True, dest="l2_iface", help="interface L2 (LB-IPAM/CNI)")
    # L'appelant (run-phases.sh:phase_bootstrap) passe TOUJOURS --inventory explicite
    # (l'inventaire Lima dérivé du banc). Le défaut pointe le `.example` inerte (ADR 0098 :
    # plus de hosts.yaml statique) — un filet, jamais une cible réelle.
    ap.add_argument(
        "--inventory", default="hosts.example.yaml", help="inventaire (relatif à bootstrap/)"
    )
    return ap


# Commandes INTERNES (hors menu) : nom → (builder de parser dédié). Routées à part
# dans main() pour ne PAS polluer le --help / la liste des choix du menu public.
_INTERNAL_PARSERS = {
    "bootstrap-seq": _build_bootstrap_parser,
}


# Posé par `_default_kubeconfig_to_bench` quand IL a dû pointer le banc lui-même (le
# shell de l'opérateur n'avait PAS KUBECONFIG exporté). Signal pour `preview` : le
# process voit le banc, mais le SHELL ne l'a pas → un `kubectl` nu y vise ~/.kube/config
# (souvent la prod). Variable de PROCESS (le défaut process-local ne change pas le shell).
_KUBECONFIG_AUTO_BENCH = False


def _default_kubeconfig_to_bench() -> None:
    """Sans KUBECONFIG exporté, pointe le banc de la STACK ACTIVE par défaut
    (`.kubeconfigs/<stack>.config`, ADR 0102 volet B).

    `topology.py` est l'entrée du banc (ADR 0049/0056) : ses commandes « état réel »
    (smoke/scenarios/roundtrip/preview) interrogent le cluster via le client kubernetes
    OU kubectl, qui lisent `KUBECONFIG`/`~/.kube/config`. Sans ce défaut, elles visent
    le contexte courant du poste (souvent l'endpoint prod-exemple de hosts.example.yaml)
    et échouent/`—` alors que le banc tourne. On NE force PAS si l'opérateur a déjà
    exporté KUBECONFIG (intention explicite respectée). Mémorise dans
    `_KUBECONFIG_AUTO_BENCH` qu'on a posé le défaut (≠ l'opérateur) — le shell, lui,
    reste sans KUBECONFIG (process ≠ parent).

    Appelé par `main()` AVANT le parsing argv : on résout la stack active AU MOMENT de
    l'appel (`topology.yaml` → `stack_id`), pas au chargement du module (le banc est nommé
    par la stack, `realpath` résout le symlink d'activation)."""
    global _KUBECONFIG_AUTO_BENCH
    path = _bench_kubeconfig_path(_active_stack_name(None))
    if not os.environ.get("KUBECONFIG") and os.path.exists(path):
        os.environ["KUBECONFIG"] = path
        _KUBECONFIG_AUTO_BENCH = True


def _split_passthrough(rest: list[str]) -> argparse.Namespace:
    """Découpe les args d'un passthrough `nestor kubectl` : extrait `-f`/`--file <topo>` de
    TÊTE, le reste est BRUT (transmis tel quel à kubectl). Remplace le `nargs=REMAINDER`
    d'argparse — BUGGÉ quand le 1er token du reste est un flag (`-n`) : argparse tente de le
    matcher comme option du parent AVANT d'activer REMAINDER → « unrecognized arguments: -n »
    (vécu : `nestor kubectl -n rook-ceph …`). On ne parse QUE `-f/--file` en tête ; tout ce qui
    suit part inchangé (flags kubectl inclus, `--` d'un exec préservé)."""
    file = None
    i = 0
    # `-f/--file` n'est reconnu qu'en TÊTE (avant les args kubectl) — un `-f` plus loin
    # appartient à kubectl (ex. `kubectl apply -f manifest.yaml`) et reste dans le passthrough.
    while i < len(rest) and rest[i] in ("-f", "--file"):
        if i + 1 >= len(rest):
            raise _UsageError(f"`{rest[i]}` attend un chemin de topologie")
        file = rest[i + 1]
        i += 2
    return argparse.Namespace(file=file, kubectl_args=rest[i:])


def main(argv: list[str] | None = None) -> int:
    _default_kubeconfig_to_bench()
    # Les commandes internes sont interceptées AVANT le parser principal (hors menu).
    args_list = sys.argv[1:] if argv is None else argv
    if args_list and args_list[0] in _INTERNAL_PARSERS:
        cmd = args_list[0]
        args = _INTERNAL_PARSERS[cmd]().parse_args(args_list[1:])
        args.cmd = cmd
        return _run(args)
    # PASSTHROUGH `kubectl` intercepté AVANT argparse : le reste est BRUT (un flag kubectl en
    # tête, `-n …`, casse le `nargs=REMAINDER` — cf. `_split_passthrough`). PAS `ansible` : son
    # 1er argument est le POSITIONNEL `playbook` (jamais un flag) → REMAINDER n'a pas le bug là.
    if args_list and args_list[0] == "kubectl":
        try:
            args = _split_passthrough(args_list[1:])
        except _UsageError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        args.cmd = "kubectl"
        return _run(args)
    args = _build_parser().parse_args(args_list)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
