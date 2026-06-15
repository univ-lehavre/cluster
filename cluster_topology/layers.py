"""Dérivation de la séquence de couches depuis `topology.layers` (ADR 0069).

`layers` déclare un ENSEMBLE de couches (grain phase) ; l'outil en DÉRIVE l'ordre
par tri topologique du DAG de dépendances RÉELLES — pas par une chaîne totale
(ADR 0039) qui imposait de fausses dépendances (déclarer `store` forçait `metrics`).

**Source UNIQUE de l'ordre** : le graphe atomique de `rollback-lib.sh` (ADR 0066,
`topo_sort`/`component_expand_alias`/`phase_of_component`). On NE code PAS un second
graphe phase→phase en Python (ce serait recréer le double-graphe que 0066 a tué) :
`resolve_layers` APPELLE le bash (même pont que `roundtrip.py`) et PROJETTE le
résultat au grain phase. Le graphe est CONDITIONNEL au backend (ADR 0069) : on lui
passe `STORAGE_BACKEND` et il émet déjà la bonne variante de stockage (storage-simple
+ seaweedfs en local-path, ceph+sc+datalake en ceph) — aucun filtrage côté Python.

Deux vocabulaires acceptés dans `layers`, normalisés ici :
  - des **alias de profil** (`metrics`/`store`/`obs`/`dataops`/`base`) → projetés
    en phases via `LAYER_PHASES` (compat ADR 0039/0068 : un profil = un préfixe) ;
  - des **noms de phase** directs (`metrics-server`/`monitoring`/`gitops`…) → pris
    tels quels. C'est ce qui rend `layers: [gitops, metrics-server]` (palier
    non-préfixe, impossible via `profile`) exprimable.

Le socle (`up`/`bootstrap`, + `ceph`/`sc` en backend ceph) est TOUJOURS premier et
n'est pas une couche composable : il est préfixé par l'appelant (run_socle / arm),
pas par `resolve_layers`. Ici on ordonne la QUEUE applicative.
"""

from __future__ import annotations

import os
import subprocess

from cluster_topology.model import TopologyError

_REPO = os.path.join(os.path.dirname(__file__), "..")
_ROLLBACK_LIB = os.path.join(_REPO, "test", "lima", "rollback-lib.sh")

# Alias de profil → phases qu'il apporte (projection de PROFILE_BRICKS, ADR 0039/0068).
# `store` se projette en `storage`, jeton ABSTRAIT que le graphe atomique résout par
# backend (storage-simple en local-path, ceph+sc en ceph) via _expand_alias.
LAYER_PHASES: dict[str, list[str]] = {
    "base": [],  # socle nu (up/bootstrap), aucune couche de queue
    "metrics": ["metrics-server"],
    "store": ["storage"],
    "obs": ["monitoring"],
    "dataops": ["dataops"],
}

# Phases applicatives composables au grain phase (queue, hors socle up/bootstrap).
# `storage` est le jeton abstrait du stockage (résolu par backend en storage-simple
# ou ceph/sc). datalake/smoke-s3/wordpress n'existent qu'en backend ceph.
_QUEUE_PHASES = frozenset(
    {
        "storage-simple",
        "metrics-server",
        "ceph",
        "sc",
        "datalake",
        "monitoring",
        "gitops",
        "dataops",
        "gitops-seed",
    }
)

# Phases de STOCKAGE (placées en tête de queue — montées avant leurs consommateurs).
_STORAGE_PHASES = frozenset({"storage-simple", "ceph", "sc", "datalake"})

# Jetons acceptés dans `layers` : alias de profil OU noms de phase de queue.
VALID_LAYERS = frozenset(LAYER_PHASES) | _QUEUE_PHASES | {"storage"}

# Phases qui n'existent QU'EN backend ceph (RGW) — refusées en local-path.
_CEPH_ONLY = frozenset({"datalake", "ceph", "sc"})


def _backend_env(backend: str) -> dict[str, str]:
    """Env du sous-shell bash : pose STORAGE_BACKEND pour que le graphe atomique
    (rollback-lib.sh) résolve ses arêtes de stockage par backend (ADR 0069)."""
    return {**os.environ, "STORAGE_BACKEND": backend}


def _rb(call: str, backend: str) -> str:
    """Appelle une fonction de rollback-lib.sh sous le backend voulu, renvoie stdout.

    Même pont que roundtrip.py (`bash -c '. lib && <call>'`), mais avec STORAGE_BACKEND
    posé → le graphe est ceph-shaped ou local-path-shaped selon `backend`."""
    try:
        out = subprocess.run(  # noqa: S603 — chemin codé, call/backend contrôlés
            ["bash", "-c", f'. "{_ROLLBACK_LIB}" && {call}'],
            check=True,
            capture_output=True,
            text=True,
            env=_backend_env(backend),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TopologyError(f"graphe atomique injoignable ({call}) : {exc}") from exc
    return out.stdout


def _expand_to_phases(declared: list[str]) -> list[str]:
    """Normalise les jetons `layers` en phases/jetons (alias de profil → ses phases).

    Lève TopologyError sur un jeton inconnu. Le jeton `storage` (abstrait) est laissé
    tel quel : le graphe le résout par backend dans _expand_alias."""
    phases: list[str] = []
    for token in declared:
        if token not in VALID_LAYERS:
            raise TopologyError(
                f"couche `{token}` inconnue (valides : {sorted(VALID_LAYERS)}, ADR 0069)"
            )
        phases.extend(LAYER_PHASES.get(token, [token]))
    return phases


def _expand_alias(phase: str, backend: str) -> list[str]:
    """Composants d'une phase via component_expand_alias (backend-conditionnel), ou
    [phase] si la phase est hors graphe roundtrip. Le jeton abstrait `storage` se
    résout en la couche stockage du backend (storage-simple | ceph+sc)."""
    if phase == "storage":
        return ["storage-simple"] if backend != "ceph" else ["ceph", "sc"]
    comps = _rb(f"component_expand_alias {phase!r}", backend).split()
    return comps or [phase]


def resolve_layers(declared: list[str], backend: str = "local-path") -> list[str]:
    """Séquence ORDONNÉE des phases de queue dérivée de `layers` (ADR 0069).

    Étapes : (1) défaut `base` si vide ; (2) normaliser alias→phases ; (3) refuser une
    phase ceph-only en local-path ; (4) fermer en composants + trier via le graphe
    atomique backend-conditionnel (rollback-lib.sh) ; (5) projeter au grain phase,
    dédupliquer en préservant l'ordre. NE préfixe PAS le socle (up/bootstrap[,ceph,
    sc]) — c'est l'affaire de run_socle / l'arm appelant. Renvoie la queue
    applicative ordonnée (vide pour `base`)."""
    phases = _expand_to_phases(declared or ["base"])
    if not phases:
        return []
    # Garde-fou backend : pas de phase ceph-only en local-path (datalake/ceph/sc).
    if backend != "ceph":
        bad = sorted({p for p in phases if p in _CEPH_ONLY})
        if bad:
            raise TopologyError(
                f"couche(s) {bad} exige(nt) le backend ceph (déclaré : `{backend}`) — ADR 0069"
            )
    # Fermer chaque phase en composants (graphe backend-conditionnel), trier l'union
    # par le tri topologique du graphe atomique, reprojeter au grain phase.
    components: list[str] = []
    for ph in phases:
        components.extend(_expand_alias(ph, backend))
    ordered = _rb(f"topo_sort {' '.join(repr(c) for c in components)}", backend).split()
    result: list[str] = []
    for comp in ordered:
        # Projeter le composant sur sa phase de queue. `phase_of_component` couvre les
        # phases du roundtrip (monitoring/dataops/…) ; `storage-simple`/`metrics-server`
        # SONT eux-mêmes des phases de queue (hors _ROUNDTRIP_PHASES) → repli sur le nom.
        ph = _rb(f"phase_of_component {comp!r}", backend).strip()
        if not ph and comp in _QUEUE_PHASES:
            ph = comp
        if ph and ph in _QUEUE_PHASES and ph not in result:
            result.append(ph)
    # Le STOCKAGE précède toute couche applicative (convention de montage des arms :
    # storage AVANT metrics/monitoring/apps — même quand metrics n'en dépend pas).
    # Partition STABLE (préserve l'ordre topo dans chaque groupe), pas un re-tri →
    # reproduit l'ordre figé des arms (test_parity) sans toucher aux poids du graphe.
    storage = [p for p in result if p in _STORAGE_PHASES]
    rest = [p for p in result if p not in _STORAGE_PHASES]
    return storage + rest


def layers_from_profile(profile: str) -> list[str]:
    """Projette un `profile` (ADR 0039, alias déprécié-doux) en `layers` équivalents.

    Un profil = le PRÉFIXE cumulatif de la chaîne jusqu'à lui. On renvoie les alias
    de ce préfixe (resolve_layers fera la fermeture/tri). Import LOCAL de
    required_profiles pour éviter un cycle profile↔layers."""
    from cluster_topology.profile import required_profiles

    return list(required_profiles(profile))
