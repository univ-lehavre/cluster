"""« Que faire ensuite » : séquence de phases attendue, diff, suggestion (P5).

Module PUR (aucune I/O, aucun subprocess) : il calcule, pour une topologie
donnée, la **séquence ordonnée de phases** d'un chemin nommé, la confronte à
l'état réel fourni par l'appelant (phases déjà jouées + verdict de fraîcheur),
et **suggère** la prochaine phase manquante. Il ne LANCE rien — le lancement est
l'affaire de la couche d'exécution `runner.py` (ADR 0063 G5), appelée par la
façade `next` sur décision humaine explicite (`--apply`).

L'ordre des phases est une **transcription fidèle** des arms de
`test/lima/run-phases.sh` (chemins nommés `socle`/`atlas`/`storage-real`/
`cluster-dataops`/`atlas-ceph`) — il ne le réinvente pas (ADR 0063 G3 / ADR 0045).
La fraîcheur réutilise `history.verdict_for_run` ; le faisceau `-e` réutilise
`profile.derive_run_params` (zéro logique dupliquée).

Suivant `state.sh` (#107-109), la suggestion ne retient que le **1er drift** : on
propose UNE phase — la première manquante de la séquence ordonnée —, jamais une
phase aval avant son amont.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cluster_topology.model import Topology


# ── Mapping phase → playbook bootstrap + clés `-e` (ADR 0063 G3) ─────────────
# Source de vérité unique du mapping, alignée sur run-phases.sh. Les phases SANS
# playbook unitaire (montées par un script ou un enchaînement, pas un play seul)
# valent None : `--apply` ne les lance pas isolément (déléguées au chemin nommé).
@dataclass(frozen=True)
class PhaseSpec:
    playbook: str | None  # chemin relatif au repo, ou None si pas un play unitaire
    note: str = ""


PHASE_PLAYBOOK: dict[str, PhaseSpec] = {
    "up": PhaseSpec(None, "provision Lima (script, pas un play)"),
    "bootstrap": PhaseSpec(None, "socle k8s complet (enchaînement de plays)"),
    "ceph": PhaseSpec("bootstrap/ceph-cluster.yaml", "operator + cluster Rook-Ceph"),
    "sc": PhaseSpec("bootstrap/ceph-storageclasses.yaml", "StorageClasses Ceph"),
    "storage-simple": PhaseSpec("bootstrap/local-path.yaml", "local-path provisioner"),
    "metrics-server": PhaseSpec("bootstrap/metrics-server.yaml"),
    "datalake": PhaseSpec("bootstrap/ceph-datalake.yaml", "RGW + bucket datalake"),
    "monitoring": PhaseSpec("bootstrap/monitoring.yaml", "kube-prometheus-stack + Loki"),
    "gitops": PhaseSpec("bootstrap/gitops.yaml", "Gitea + Argo CD"),
    "dataops": PhaseSpec("bootstrap/dataops.yaml", "registry + CNPG + Dagster + Marquez"),
    "gitops-seed": PhaseSpec(None, "init Gitea (données, ADR 0044 — script)"),
    # hardening lance bootstrap/security/secure.yml AVEC --tags audit,detection et
    # un préflight d'env (phase_hardening, run-phases.sh) que `--apply` ne pose pas
    # — non lançable comme play unitaire ici, déléguée au chemin nommé run-phases.sh.
    "hardening": PhaseSpec(None, "durcissement hôte (secure.yml + tags/env, via run-phases.sh)"),
    "smoke-s3": PhaseSpec(None, "épreuve S3 jetable (harnais)"),
    "wordpress": PhaseSpec(None, "montage WordPress jetable (harnais)"),
}

# ── Séquences ordonnées des chemins nommés (transcription de run-phases.sh) ──
# Le socle préfixe chaque chemin : up → bootstrap → (ceph+sc | storage-simple).
# `hardening` s'insère APRÈS le socle (run_hardening_if_requested) si demandé.
_SOCLE_CEPH = ["up", "bootstrap", "ceph", "sc"]
_SOCLE_LIGHT = ["up", "bootstrap", "storage-simple"]

# Phases propres à chaque chemin, APRÈS le socle (+ hardening éventuel).
_PATH_TAIL: dict[str, list[str]] = {
    "socle": [],
    "atlas": ["metrics-server", "monitoring", "gitops", "dataops", "gitops-seed"],
    "storage-real": ["datalake", "smoke-s3", "wordpress"],
    "cluster-dataops": ["datalake", "monitoring", "dataops"],
    "atlas-ceph": ["datalake", "monitoring", "gitops", "dataops", "gitops-seed"],
}

# Chemins qui exigent le backend Ceph (WITH_CEPH=1 dans run-phases.sh).
_CEPH_PATHS = {"storage-real", "cluster-dataops", "atlas-ceph"}

KNOWN_TARGETS = frozenset(_PATH_TAIL)


class PlanError(ValueError):
    """Chemin nommé inconnu ou incohérent avec la topologie."""


def _backend_of(topo: Topology) -> str:
    return topo.storage.get("backend", "local-path")


def _hardening_requested(topo: Topology) -> bool:
    """Le durcissement est-il demandé ? (équivalent de WITH_HARDENING=1).

    `hardening.enabled: true` l'active ; un bloc absent ou `enabled: false` ne
    l'active pas (l'exemple prod déclare le bloc désactivé — durcissement piloté
    séparément). On ne se contente PAS de la présence du bloc.
    """
    return bool(topo.hardening.get("enabled", False))


def default_target(topo: Topology) -> str:
    """Chemin nommé déduit du profil + backend si l'appelant n'en fournit pas.

    `dataops` + ceph → `atlas-ceph` (chaîne complète Ceph) ; `dataops` + local-path
    → `atlas` ; un profil non-dataops → `socle` (on ne présume pas d'un chemin
    applicatif). Heuristique de confort : l'opérateur peut toujours forcer `--target`.
    """
    profile = topo.catalog.get("profile", "base")
    backend = _backend_of(topo)
    if profile == "dataops":
        return "atlas-ceph" if backend == "ceph" else "atlas"
    return "socle"


def expected_phase_sequence(topo: Topology, target: str | None = None) -> list[str]:
    """Séquence ORDONNÉE de phases d'un chemin nommé, selon le backend de `topo`.

    Transcription fidèle des arms de run-phases.sh (ADR 0063 G3) : socle (ceph ou
    léger) + `hardening` si demandé + la queue propre au chemin. Lève PlanError si
    le chemin est inconnu, ou si un chemin Ceph est demandé sur un backend non-ceph
    (incohérence que run-phases.sh refuse aussi).
    """
    target = target or default_target(topo)
    if target not in KNOWN_TARGETS:
        raise PlanError(f"chemin `{target}` inconnu (connus : {sorted(KNOWN_TARGETS)})")
    backend = _backend_of(topo)
    if target in _CEPH_PATHS and backend != "ceph":
        raise PlanError(f"chemin `{target}` exige le backend ceph (déclaré : `{backend}`)")
    if target == "atlas" and backend == "ceph":
        # run-phases.sh refuse atlas + WITH_CEPH (utiliser atlas-ceph).
        raise PlanError("chemin `atlas` = profil local-path ; pour Ceph utiliser `atlas-ceph`")
    socle = _SOCLE_CEPH if backend == "ceph" else _SOCLE_LIGHT
    seq = list(socle)
    if _hardening_requested(topo):
        seq.append("hardening")
    seq.extend(_PATH_TAIL[target])
    return seq


def diff_phases(expected: list[str], done: set[str], freshness: str) -> list[str]:
    """Phases du `expected` non encore satisfaites, dans l'ordre.

    Si la fraîcheur est `perime`/`jamais` (verdict de history.py — RÉUTILISÉ, pas
    redérivé), toute la séquence est candidate au rejeu (le chemin n'a pas de run
    frais). Sinon, on ne retient que les phases absentes de `done`.
    """
    if freshness in ("perime", "jamais"):
        return list(expected)
    return [p for p in expected if p not in done]


@dataclass
class Suggestion:
    """Verdict « que faire ensuite ». `phase` None = rien à lancer (à jour)."""

    target: str
    phase: str | None
    playbook: str | None
    etat: str  # à-jour | manquante | rejeu
    message: str
    run_params: dict = field(default_factory=dict)


def suggest_next(
    topo: Topology,
    target: str | None,
    done: set[str],
    freshness: str,
    run_params: dict | None = None,
) -> Suggestion:
    """Suggère la PROCHAINE phase manquante (1er drift, parité state.sh #107-109).

    `done` : phases déjà jouées (fournies par la façade depuis l'historique/state).
    `freshness` : verdict de history.verdict_for_run. `run_params` : le faisceau
    `-e` dérivé (profile.derive_run_params) à attacher à la phase, pour que
    `--apply` lance le MÊME play avec les MÊMES `-e` que run-phases.sh (ADR 0063 G3).
    """
    target = target or default_target(topo)
    seq = expected_phase_sequence(topo, target)
    manquantes = diff_phases(seq, done, freshness)
    if not manquantes:
        return Suggestion(
            target=target,
            phase=None,
            playbook=None,
            etat="à-jour",
            message=f"{target} : à jour (run frais, séquence complète) — rien à lancer.",
        )
    phase = manquantes[0]
    spec = PHASE_PLAYBOOK.get(phase, PhaseSpec(None))
    etat = "rejeu" if freshness in ("perime", "jamais") else "manquante"
    raison = {
        "rejeu": "pas de run frais sur ce chemin → rejeu de la séquence",
        "manquante": "phase suivante non encore jouée",
    }[etat]
    return Suggestion(
        target=target,
        phase=phase,
        playbook=spec.playbook,
        etat=etat,
        message=f"Prochaine étape (1er drift) : {phase} sur le chemin {target} — {raison}.",
        run_params=dict(run_params or {}),
    )
