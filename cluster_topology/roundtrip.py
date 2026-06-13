"""Round-trip de réversibilité par CLÔTURE de dépendances (détruire → vérifier →
reconstruire → vérifier sain). Généralisation « grandeur nature » du smoke-test
P6 : au lieu d'un namespace jetable, on éprouve la réversibilité d'une couche ET
de toute sa **clôture descendante** (ce qui dépend d'elle).

Le scénario donne l'ORDRE (« détruire la couche X ») ; l'outil **déduit** la
clôture à défaire. Détruire une couche de base cascade sur tout ce qui en dépend :
détruire `sc` orphelinerait monitoring/dataops/gitea (leurs PVC sont sur la
StorageClass) ; détruire `ceph` reconstruit tout le socle de stockage.

La clôture et l'ordre de montage NE SONT PLUS codés ici : ils sont DÉRIVÉS du
**graphe atomique unique** de `rollback-lib.sh` (`phase_closure` / `topo_sort`,
ADR 0066) — fin de la 2ᵉ source de vérité (l'ancien `_DEPENDENTS`/`_MOUNT_ORDER`
en dur, « validé à la main », divergeait du graphe de rollback). Les arêtes de
stockage BLOC (`gitea`/`registry`/`prometheus-stack`/`cnpg`/`loki` → `sc`, PVC sur
la StorageClass) sont désormais dans le graphe (workflow consigné 2026-06-13).

Cycle, pour la clôture `[X, …descendants]` :
  1. détruire : `run-phases.sh rollback <p>` pour chaque p, en ordre INVERSE de
     montage (aval→amont) — la dérivation du périmètre par phase vit dans
     rollback-lib.sh (ADR 0054), non dupliquée ici ;
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
import subprocess
import sys
from dataclasses import dataclass, field

_REPO = os.path.join(os.path.dirname(__file__), "..")
_RUN_PHASES = os.path.join(_REPO, "test", "lima", "run-phases.sh")
_ROLLBACK_LIB = os.path.join(_REPO, "test", "lima", "rollback-lib.sh")

# Phases qui ont un rollback défini (rollback_known_phase, rollback-lib.sh).
KNOWN_PHASES = (
    "ceph",
    "sc",
    "datalake",
    "metrics-server",
    "monitoring",
    "dataops",
    "gitops",
    "gitops-seed",
)


class RoundtripError(RuntimeError):
    """Phase inconnue, opt-in manquant, confirmation refusée, ou banc indisponible."""


# ── Périmètre & clôture : DÉRIVÉS du graphe atomique de rollback-lib.sh ──────
# Source UNIQUE (ADR 0066) : ni _DEPENDENTS ni _MOUNT_ORDER ne sont codés ici.


def _rollback_lib_call(func: str, phase: str = "") -> str:
    """Appelle une fonction de rollback-lib.sh et renvoie sa stdout (source unique).

    `phase` est passé en argument seulement s'il est non vide (certaines fonctions,
    comme `phase_closure`, prennent un argument ; d'autres pas).
    """
    call = f"{func} {phase!r}" if phase else func
    try:
        out = subprocess.run(  # noqa: S603 — chemin codé, func/phase contrôlés
            ["bash", "-c", f'. "{_ROLLBACK_LIB}" && {call}'],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RoundtripError(f"lecture du périmètre de `{phase}` impossible : {exc}") from exc
    return out.stdout


def closure(phase: str) -> list[str]:
    """Clôture descendante de `phase`, en ordre de MONTAGE (amont→aval).

    = `phase` + tout ce qui en dépend (transitivement). DÉRIVÉE du graphe atomique
    (`phase_closure`, rollback-lib.sh) — plus de graphe en dur ici (ADR 0066).
    """
    if phase not in KNOWN_PHASES:
        raise RoundtripError(f"phase `{phase}` inconnue (connues : {list(KNOWN_PHASES)})")
    return _rollback_lib_call("phase_closure", phase).split()


def involves_storage(phase: str) -> bool:
    """La clôture de `phase` touche-t-elle une couche de stockage (→ opt-in `full`) ?

    Délègue à `phase_involves_storage` (rollback-lib.sh) : code de retour 0 = oui.
    """
    if phase not in KNOWN_PHASES:
        raise RoundtripError(f"phase `{phase}` inconnue (connues : {list(KNOWN_PHASES)})")
    completed = subprocess.run(  # noqa: S603 — chemin codé, phase contrôlée
        ["bash", "-c", f'. "{_ROLLBACK_LIB}" && phase_involves_storage {phase!r}'],
        check=False,
    )
    return completed.returncode == 0


def phase_namespaces(phase: str) -> list[str]:
    """Namespaces dédiés d'une phase (rollback_phase_namespaces)."""
    return _rollback_lib_call("rollback_phase_namespaces", phase).split()


def phase_targeted_resources(phase: str) -> list[str]:
    """Ressources ciblées d'une phase (une par ligne, format kubectl)."""
    return [
        ln
        for ln in _rollback_lib_call("rollback_phase_targeted_resources", phase).splitlines()
        if ln.strip()
    ]


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
        from cluster_topology import smoke

        api = smoke._core_v1()
    for item in signal:
        if item.startswith("ns/"):
            from cluster_topology import smoke

            if smoke._ns_exists(api, item[3:]):
                present.append(item)
        elif _kubectl_present(item):
            present.append(item)
    return present


def _kubectl_present(line: str) -> bool:
    """True si la ressource ciblée existe (`kubectl get <line> --ignore-not-found -o name`)."""
    try:
        out = subprocess.run(  # noqa: S603 — ligne issue de rollback-lib
            ["bash", "-c", f"kubectl get {line} --ignore-not-found -o name 2>/dev/null"],
            check=False,
            capture_output=True,
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
    signal_present=_signal_present,
    confirm_fn=confirm,
) -> RoundtripResult:
    """Détruire la clôture → vérifier → reconstruire → vérifier sain.

    `allow_full` : autorise les clôtures qui touchent le stockage (≈ rebuild du
    socle). `assume_yes` : saute la confirmation TTY (CI/script). Les couches d'I/O
    (`run_phase`/`signal_present`/`confirm_fn`) sont injectables (tests sans banc).

    La RECONSTRUCTION utilise le profil RÉEL du cluster : les phases bash
    (monitoring/dataops/gitops) AUTO-DÉTECTENT leur storageClass (présence de la SC
    Ceph) — plus de `WITH_CEPH` à passer (drift L44 / #319 fermé). Le roundtrip ne
    thread donc aucun flag de profil ; il délègue à `run-phases.sh`.
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

    # 1. Détruire chaque couche de la clôture (ordre inverse).
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
