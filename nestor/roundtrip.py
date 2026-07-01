"""Round-trip de réversibilité par CLÔTURE de dépendances (détruire → vérifier →
reconstruire → vérifier sain). Généralisation « grandeur nature » du smoke-test
P6 : au lieu d'un namespace jetable, on éprouve la réversibilité d'une couche ET
de toute sa **clôture descendante** (ce qui dépend d'elle).

Le scénario donne l'ORDRE (« détruire la couche X ») ; l'outil **déduit** la
clôture à défaire. Détruire une couche de base cascade sur tout ce qui en dépend :
détruire `sc` orphelinerait monitoring/dataops/gitea (leurs PVC sont sur la
StorageClass) ; détruire `ceph` reconstruit tout le socle de stockage.

La clôture et l'ordre de montage NE SONT PLUS codés ici : ils sont DÉRIVÉS du
**graphe atomique unique** FIGÉ `nestor/graph.py` (ADR 0096 §1, porté byte-identique
de `rollback-lib.sh`, ADR 0066 ; `phase_closure` / `topo_sort`) — fin de la 2ᵉ source
de vérité (l'ancien `_DEPENDENTS`/`_MOUNT_ORDER` en dur, « validé à la main »,
divergeait du graphe de rollback). Les arêtes de stockage BLOC (`gitea`/`registry`/
`prometheus-stack`/`cnpg`/`loki` → `sc`, PVC sur la StorageClass) sont dans le graphe
(workflow consigné 2026-06-13). Plus de sous-process bash pour le périmètre/la clôture
(lot 3 du plan de refonte : le pont `rollback-lib.sh` est remplacé par `graph.py`).

DESTRUCTION par DÉCOUVERTE (ADR 0101) : défaire une couche ne shelle PLUS
`run-phases.sh rollback` (l'ancien chemin « table » de `rollback-lib.sh`, supprimé) ;
elle passe par la DÉCOUVERTE d'appartenance (`remove`, `cmd_remove` /
`_remove_by_discovery` dans `scripts/topology.py`) qui cascade tout l'aval k8s ET le
node-side Ceph en UN geste. `run-phases.sh` n'est plus shellé ici que pour le MONTAGE
(reconstruction d'une phase) — bash légitime.

Cycle, pour la clôture `[X, …descendants]` :
  1. détruire : un `remove` (injecté en `destroy_layer`) défait TOUTE la
     clôture (aval cascadé + node-side Ceph) en UN geste ;
  2. vérifier détruit : le signal d'infra (namespaces + ressources ciblées) de
     chaque couche a DISPARU ;
  3. reconstruire : `run-phases.sh <p>` en ordre de montage (amont→aval) ;
  4. vérifier sain : le signal est REVENU.

Garde-fous :
  - les couches de STOCKAGE (ceph/sc/datalake) entraînent une clôture LARGE
    (≈ rebuild du socle) → réservées à l'opt-in `allow_full` ;
  - avant toute suppression DÉFINITIVE de données, on demande CONFIRMATION sur un
    TTY (sinon `assume_yes` requis) — voir `confirm`.

Couches d'I/O ISOLÉES et stubables (mêmes patrons que runner.py / smoke.py).
Aucun cluster en CI ; la preuve réelle passe par un run de banc (ADR 0034/0052).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field

from nestor import graph

_REPO = os.path.join(os.path.dirname(__file__), "..")
_RUN_PHASES = os.path.join(_REPO, "bench", "lima", "run-phases.sh")

# Phases qui ont un rollback défini (rollback_known_phase, rollback-lib.sh).
KNOWN_PHASES = (
    "ceph",
    "sc",
    "datalake",
    "metrics-server",
    "monitoring",
    "dataops",
    "mlflow",
    "gitops",
    "gitops-seed",
    "portal",
)


class RoundtripError(RuntimeError):
    """Phase inconnue, opt-in manquant, confirmation refusée, ou banc indisponible."""


# ── Périmètre & clôture : DÉRIVÉS du graphe atomique FIGÉ `nestor/graph.py` ──
# Source UNIQUE (ADR 0066/0096 §1) : ni _DEPENDENTS ni _MOUNT_ORDER ne sont codés ici.
# Plus de pont subprocess vers rollback-lib.sh (lot 3) : `graph.py` porte le graphe
# byte-identique (prouvé par tests/test_graph.py contre le VRAI bash, les 2 backends).


def closure(phase: str) -> list[str]:
    """Clôture descendante de `phase`, en ordre de MONTAGE (amont→aval).

    = `phase` + tout ce qui en dépend (transitivement). DÉRIVÉE du graphe atomique
    figé (`graph.phase_closure`, ADR 0066/0096) — plus de graphe en dur ici.
    """
    if phase not in KNOWN_PHASES:
        raise RoundtripError(f"phase `{phase}` inconnue (connues : {list(KNOWN_PHASES)})")
    return graph.phase_closure(phase)


def involves_storage(phase: str) -> bool:
    """La clôture de `phase` touche-t-elle une couche de stockage (→ opt-in `full`) ?

    Délègue à `graph.phase_involves_storage` : True = oui (clôture ceph/sc/datalake).
    """
    if phase not in KNOWN_PHASES:
        raise RoundtripError(f"phase `{phase}` inconnue (connues : {list(KNOWN_PHASES)})")
    return graph.phase_involves_storage(phase)


def phase_namespaces(phase: str) -> list[str]:
    """Namespaces dédiés d'une phase (= graph.rollback_phase_namespaces, table ADR 0054)."""
    return graph.rollback_phase_namespaces(phase)


def phase_targeted_resources(phase: str) -> list[str]:
    """Ressources ciblées d'une phase (une par ligne, format kubectl ; table ADR 0054).

    = `graph.rollback_phase_targeted_resources` au backend ceph par défaut (l'historique
    du pont bash sans STORAGE_BACKEND posé : `_rb_backend` retombe sur ceph)."""
    return graph.rollback_phase_targeted_resources(phase)


def phase_signal(phase: str) -> list[str]:
    """Signal d'infra VÉRIFIABLE d'une phase : ns + ressources ciblées (étiquetés)."""
    return [f"ns/{n}" for n in phase_namespaces(phase)] + phase_targeted_resources(phase)


# ── Couches d'exécution / vérification (isolées, stubables) ─────────────────


def _run_phase(args: list[str], *, env_extra: dict | None = None) -> int:
    """Lance `run-phases.sh <args>` ; renvoie son code (consommé tel quel, ADR 0063 G1)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    completed = subprocess.run(  # noqa: S603 — chemin codé, pas d'entrée shell
        ["bash", _RUN_PHASES, *args], check=False, env=env
    )
    return completed.returncode


def _signal_present(signal: list[str], *, api=None) -> list[str]:
    """Éléments du signal ENCORE présents : ns via le client k8s (smoke), ressources
    ciblées via `kubectl get <ligne> --ignore-not-found` (même ligne que rollback-lib)."""
    present: list[str] = []
    needs_api = any(s.startswith("ns/") for s in signal)
    if needs_api and api is None:
        from nestor import smoke

        api = smoke._core_v1()
    for item in signal:
        if item.startswith("ns/"):
            from nestor import smoke

            if smoke._ns_exists(api, item[3:]):
                present.append(item)
        elif _kubectl_present(item):
            present.append(item)
    return present


def _kubectl_present(line: str) -> bool:
    """True si la ressource ciblée existe (`kubectl get <line> --ignore-not-found -o name`).

    `line` est une ligne au format kubectl issue de rollback-lib (ex.
    `-n rook-ceph cephobjectstore.ceph.rook.io datalake`) : on la découpe en
    arguments avec `shlex.split` et on appelle `kubectl` DIRECTEMENT — pas de
    `bash -c` (supprime la dépendance au shell et le `2>/dev/null` non portable ;
    `stderr=DEVNULL` fait le même office, cf. ADR 0098)."""
    try:
        out = subprocess.run(  # noqa: S603 — argv issu de rollback-lib, pas d'entrée shell
            ["kubectl", "get", *shlex.split(line), "--ignore-not-found", "-o", "name"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return False
    return bool(out.stdout.strip())


# ── Confirmation TTY avant suppression définitive de données ────────────────


def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def confirm(layers: list[str], *, assume_yes: bool, prompt=input, is_tty=_is_tty) -> bool:
    """Demande confirmation avant la destruction DÉFINITIVE des couches `layers`.

    Sur un TTY : invite l'opérateur (oui/non), retourne son choix. Hors TTY
    (CI/script) : exige `assume_yes` (sinon refus — pas de destruction silencieuse).
    """
    if assume_yes:
        return True
    if not is_tty():
        return False  # hors TTY sans --yes : on ne détruit RIEN
    reponse = prompt(
        f"⚠️  SUPPRESSION DÉFINITIVE des couches {layers} (données comprises) — "
        "confirmer ? [oui/non] "
    )
    return reponse.strip().lower() in ("oui", "o", "yes", "y")


# ── Résultat ────────────────────────────────────────────────────────────────


@dataclass
class RoundtripStep:
    nom: str
    ok: bool
    detail: str = ""


@dataclass
class RoundtripResult:
    """Verdict du round-trip. `reversible` = toutes les étapes ont réussi."""

    phase: str
    layers: list[str] = field(default_factory=list)
    steps: list[RoundtripStep] = field(default_factory=list)

    @property
    def reversible(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)


def run_roundtrip(
    phase: str,
    *,
    allow_full: bool = False,
    assume_yes: bool = False,
    run_phase=_run_phase,
    destroy_layer=None,
    signal_present=_signal_present,
    confirm_fn=confirm,
) -> RoundtripResult:
    """Détruire la clôture → vérifier → reconstruire → vérifier sain.

    `allow_full` : autorise les clôtures qui touchent le stockage (≈ rebuild du
    socle). `assume_yes` : saute la confirmation TTY (CI/script). Les couches d'I/O
    (`run_phase`/`destroy_layer`/`signal_present`/`confirm_fn`) sont injectables (tests
    sans banc).

    DESTRUCTION (ADR 0101) : `destroy_layer(phase) -> int` défait TOUTE la clôture en UN
    geste (la découverte `remove` cascade l'aval + le node-side Ceph), rc 0 = ok.
    Injecté par `cmd_roundtrip` ; None = repli legacy `run-phases.sh rollback` couche par
    couche (transitoire, le temps de retirer rollback-lib.sh). La RECONSTRUCTION reste
    `run-phases.sh <phase>` (montage, bash légitime) : les phases AUTO-DÉTECTENT leur
    storageClass (plus de `WITH_CEPH`, #319 fermé).
    """
    layers = closure(phase)  # ordre de montage (amont→aval)
    if involves_storage(phase) and not allow_full:
        raise RoundtripError(
            f"`{phase}` entraîne une clôture de stockage {layers} (≈ rebuild du socle) "
            "— exiger l'opt-in `--full`"
        )
    result = RoundtripResult(phase=phase, layers=layers)

    # Garde-fou données : confirmation avant toute suppression définitive.
    if not confirm_fn(layers, assume_yes=assume_yes):
        result.steps.append(RoundtripStep("confirmation", False, "destruction non confirmée"))
        return result

    destroy_order = list(reversed(layers))  # aval→amont
    rebuild_order = layers  # amont→aval

    # 1. Détruire la clôture. Découverte (destroy_layer) : UN geste défait tout l'aval +
    # le node-side. Repli legacy : couche par couche via `run-phases.sh rollback`.
    if destroy_layer is not None:
        rc = destroy_layer(phase)
        if rc != 0:
            result.steps.append(RoundtripStep("détruire", False, f"remove rc={rc}"))
            return result
    else:
        for p in destroy_order:
            rc = run_phase(["rollback", p], env_extra={"BANC_JETABLE": "1"})
            if rc != 0:
                result.steps.append(RoundtripStep(f"détruire {p}", False, f"rollback rc={rc}"))
                return result
    result.steps.append(RoundtripStep("détruire", True, f"clôture défaite : {destroy_order}"))

    # 2. Vérifier détruit : aucun signal d'infra de la clôture ne subsiste.
    full_signal = [s for p in layers for s in phase_signal(p)]
    still = signal_present(full_signal)
    ok = not still
    result.steps.append(
        RoundtripStep(
            "vérifier détruit", ok, "signal absent" if ok else f"encore présent : {still}"
        )
    )
    if not ok:
        return result

    # 3. Reconstruire chaque couche (ordre de montage). Le profil de stockage est
    # auto-détecté par les phases (plus de WITH_CEPH à passer — #319 fermé).
    for p in rebuild_order:
        rc = run_phase([p])
        if rc != 0:
            result.steps.append(RoundtripStep(f"reconstruire {p}", False, f"phase rc={rc}"))
            return result
    result.steps.append(RoundtripStep("reconstruire", True, f"clôture re-montée : {rebuild_order}"))

    # 4. Vérifier sain : tout le signal est revenu.
    back = signal_present(full_signal)
    manquants = [s for s in full_signal if s not in back]
    ok = not manquants
    result.steps.append(
        RoundtripStep("vérifier sain", ok, "signal revenu" if ok else f"manquant : {manquants}")
    )
    return result
