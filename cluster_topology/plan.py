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
    note: str = ""  # note DÉVELOPPEUR (diagnostic --apply : « script, pas un play »…)
    label: str = ""  # libellé MÉTIER lisible de la couche installée (pour `preview`)


PHASE_PLAYBOOK: dict[str, PhaseSpec] = {
    "up": PhaseSpec(None, "provision Lima (script, pas un play)", "créer les VMs"),
    "bootstrap": PhaseSpec(
        None,
        "socle k8s complet (enchaînement de plays)",
        "Kubernetes + CRI containerd + CNI Cilium",
    ),
    "bootstrap-ha": PhaseSpec(
        None, "amorçage HA (kube-vip + init derrière la VIP)", "Kubernetes HA (kube-vip)"
    ),
    "join-cp": PhaseSpec(
        None, "promotion des CP additionnels (join + quorum etcd)", "control-planes additionnels"
    ),
    "ceph": PhaseSpec(
        "bootstrap/ceph-cluster.yaml", "operator + cluster Rook-Ceph", "stockage Ceph (Rook)"
    ),
    "sc": PhaseSpec(
        "bootstrap/ceph-storageclasses.yaml", "StorageClasses Ceph", "StorageClasses Ceph"
    ),
    "storage-simple": PhaseSpec(
        "bootstrap/local-path.yaml", "local-path provisioner", "stockage local-path"
    ),
    "metrics-server": PhaseSpec(
        "bootstrap/metrics-server.yaml", "", "metrics-server (kubectl top)"
    ),
    "datalake": PhaseSpec(
        "bootstrap/ceph-datalake.yaml", "RGW + bucket datalake", "datalake S3 (RGW)"
    ),
    "monitoring": PhaseSpec(
        "bootstrap/monitoring.yaml",
        "kube-prometheus-stack + Loki",
        "observabilité (Prometheus + Grafana + Loki)",
    ),
    "gitops": PhaseSpec("bootstrap/gitops.yaml", "Gitea + Argo CD", "GitOps (Gitea + Argo CD)"),
    "dataops": PhaseSpec(
        "bootstrap/dataops.yaml",
        "registry + CNPG + Dagster + Marquez",
        "DataOps (registry + CNPG + Dagster + Marquez)",
    ),
    "gitops-seed": PhaseSpec(
        None, "init Gitea (données, ADR 0044 — script)", "init GitOps (seed Gitea)"
    ),
    # hardening lance bootstrap/security/secure.yml AVEC --tags audit,detection et
    # un préflight d'env (phase_hardening, run-phases.sh) que `--apply` ne pose pas
    # — non lançable comme play unitaire ici, déléguée au chemin nommé run-phases.sh.
    "hardening": PhaseSpec(
        None, "durcissement hôte (secure.yml + tags/env, via run-phases.sh)", "durcissement hôte"
    ),
    "smoke-s3": PhaseSpec(None, "épreuve S3 jetable (harnais)", "épreuve S3 (jetable)"),
    "wordpress": PhaseSpec(None, "montage WordPress jetable (harnais)", "WordPress (jetable)"),
}


def phase_label(phase: str) -> str:
    """Libellé MÉTIER lisible d'une phase (couche installée), pour `preview`.

    Repli sur le nom technique si aucun label n'est défini (phase inconnue de la
    table) — préserve l'information plutôt que de masquer."""
    spec = PHASE_PLAYBOOK.get(phase)
    return spec.label if spec and spec.label else phase


# ── Séquences ordonnées des chemins nommés (transcription de run-phases.sh) ──
# Le socle de BASE = up → bootstrap (k8s + CNI SEULS). Le STOCKAGE n'en fait PAS
# partie : c'est la brique du profil `store` (ADR 0039 : base ⊂ store ; PROFILE_BRICKS
# rattache `storage` à store, pas à base). En mode Ceph le socle pose ceph+sc (le
# stockage Ceph est indissociable du socle de ce backend) ; en local-path, la couche
# `storage-simple` est ajoutée par les chemins qui en ont besoin (cf. _STORAGE_LAYER).
# `hardening` s'insère APRÈS le socle (run_hardening_if_requested) si demandé.
_SOCLE_CEPH = ["up", "bootstrap", "ceph", "sc"]
_SOCLE_LIGHT = ["up", "bootstrap"]
# Couche stockage local-path, insérée APRÈS le socle léger pour les chemins dont le
# profil consomme du stockage (store+). Le chemin `socle` (profil base) ne la pose PAS.
_STORAGE_LAYER = ["storage-simple"]
# Chemins local-path qui EXIGENT le stockage (profil store+ : leurs apps créent des PVC).
_LOCAL_PATH_NEEDS_STORAGE = {"atlas"}

# Phases propres à chaque chemin, APRÈS le socle (+ stockage + hardening éventuel).
_PATH_TAIL: dict[str, list[str]] = {
    "socle": [],
    # `metrics` (ADR 0068) : palier fin = socle + metrics-server seul (sans stockage,
    # sans monitoring). default_target le dérive pour profile=metrics.
    "metrics": ["metrics-server"],
    "atlas": ["metrics-server", "monitoring", "gitops", "dataops", "gitops-seed"],
    "storage-real": ["datalake", "smoke-s3", "wordpress"],
    "cluster-dataops": ["datalake", "monitoring", "dataops"],
    "atlas-ceph": ["datalake", "monitoring", "gitops", "dataops", "gitops-seed"],
}

# Chemins qui exigent le backend Ceph (WITH_CEPH=1 dans run-phases.sh).
_CEPH_PATHS = {"storage-real", "cluster-dataops", "atlas-ceph"}

# ha-3cp : control-plane HA hyperconvergé (ADR 0047/0055). Séquence À PART : le
# « socle » n'est PAS up→bootstrap→storage mais l'amorçage HA (bootstrap du CP
# primaire derrière la VIP + promotion des CP additionnels), porté par le chemin
# nommé run-phases.sh ha-3cp qui DÉLÈGUE l'orchestration Ansible à Python
# (cluster_topology/ha.py). On l'expose comme chemin connu (sélection via
# default_target) avec sa séquence propre — pas un socle+tail.
_HA_3CP_SEQUENCE = ["up", "bootstrap-ha", "join-cp", "storage-simple"]

KNOWN_TARGETS = frozenset(_PATH_TAIL) | {"ha-3cp"}


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
    """Chemin nommé DÉDUIT de la topologie déclarée (ADR 0056 : une topologie se
    déclare dans topology.yaml et l'outil en dérive le chemin — pas une commande
    impérative à flags).

    HA D'ABORD : plus d'un control-plane (`is_ha_control_plane`) → `ha-3cp`, quel
    que soit le profil applicatif (la HA est une propriété du CONTROL-PLANE,
    orthogonale aux apps ; le banc ha-3cp prouve la mécanique en local-path).
    Sinon : `dataops`+ceph → `atlas-ceph` ; `dataops`+local-path → `atlas` ;
    `metrics` → `metrics` (palier fin, ADR 0068) ; un profil sans chemin propre
    (`base`/`store`/`obs` non encore outillés) → `socle`. L'opérateur peut toujours
    forcer `--target`.
    """
    if topo.is_ha_control_plane:
        return "ha-3cp"
    profile = topo.catalog.get("profile", "base")
    backend = _backend_of(topo)
    if profile == "dataops":
        return "atlas-ceph" if backend == "ceph" else "atlas"
    if profile == "metrics":
        return "metrics"  # palier fin : socle + metrics-server (ADR 0068)
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
    if target == "ha-3cp":
        # Chemin HA à séquence propre (amorçage VIP + joins), backend local-path
        # imposé (HA ⊥ stockage, #250). Le durcissement reste appliquable en amont.
        if _backend_of(topo) == "ceph":
            raise PlanError(
                "chemin `ha-3cp` = local-path (HA ⊥ stockage, #250) ; pas de backend ceph"
            )
        seq = list(_HA_3CP_SEQUENCE)
        if _hardening_requested(topo):
            seq.insert(2, "hardening")  # après bootstrap-ha, avant les joins
        return seq
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
    # Couche stockage local-path : ajoutée APRÈS le socle pour les chemins store+ qui
    # en ont besoin (le Ceph l'a déjà dans son socle ; le chemin `socle`/base ne la
    # pose pas — base = k8s+CNI nus, ADR 0039). Avant la queue applicative (les apps
    # consomment le stockage).
    if backend != "ceph" and target in _LOCAL_PATH_NEEDS_STORAGE:
        seq.extend(_STORAGE_LAYER)
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


def observed_done_phases(
    declared_nodes: list[str], real_vms: list[str], ready_nodes: list[str]
) -> set[str]:
    """Phases du socle PROUVÉES faites par l'ÉTAT RÉEL (pas par l'historique).

    L'historique peut manquer (run non consigné, run sous un ancien label de
    topologie) alors que le cluster TOURNE : PLAN doit alors refléter le RÉEL, pas
    mentir « à installer » (ADR 0052/0056 §7 — le réel prime sur l'absence de trace).

    - `up` (créer les VMs) : faite si TOUTES les VMs déclarées existent (rien à créer).
    - `bootstrap` (k8s + CRI + CNI) : faite si AU MOINS un nœud est Ready (l'API
      répond, la CNI tourne) — un cluster Ready ne se « réinstalle » pas.

    PUR (listes en entrée, set en sortie) : testable sans cluster. Ne couvre QUE les
    phases observables côté infra (up/bootstrap) ; les couches applicatives
    (storage/monitoring/…) gardent le verdict par historique (état runtime non lu ici)."""
    done: set[str] = set()
    if declared_nodes and all(n in real_vms for n in declared_nodes):
        done.add("up")
    if ready_nodes:
        done.add("bootstrap")
    return done


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
