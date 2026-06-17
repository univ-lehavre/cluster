"""« Que faire ensuite » : séquence de phases attendue, diff, suggestion (P5).

Module PUR (aucune I/O, aucun subprocess) : il calcule, pour une topologie
donnée, la **séquence ordonnée de phases** d'un chemin nommé, la confronte à
l'état réel fourni par l'appelant (phases déjà jouées + verdict de fraîcheur),
et **suggère** la prochaine phase manquante. Il ne LANCE rien — le lancement est
l'affaire de la couche d'exécution `runner.py` (ADR 0063 G5), appelée par la
façade `next` sur décision humaine explicite (`--apply`).

L'ordre des phases est une **transcription fidèle** des arms de
`bench/lima/run-phases.sh` (chemins nommés `socle`/`atlas`/`storage-real`/
`cluster-dataops`/`atlas-ceph`) — il ne le réinvente pas (ADR 0063 G3 / ADR 0045).
La fraîcheur réutilise `history.verdict_for_run` ; le faisceau `-e` réutilise
`profile.derive_run_params` (zéro logique dupliquée).

Suivant `state.sh` (#107-109), la suggestion ne retient que le **1er drift** : on
propose UNE phase — la première manquante de la séquence ordonnée —, jamais une
phase aval avant son amont.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from nestor.model import Topology

if TYPE_CHECKING:
    from collections.abc import Callable


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
    # MLflow (ADR 0082) : layer AUTONOME (hors _PATH_TAIL) — montée à la demande
    # via le chemin générique `layers`. Dépend de dataops (base CNPG `mlflow`) et
    # du backing S3 (SeaweedFS de monitoring en local-path / RGW datalake en Ceph) —
    # ces dépendances sont déclarées dans le graphe atomique (rollback-lib.sh).
    "mlflow": PhaseSpec(
        "bootstrap/mlflow.yaml",
        "serveur MLflow (suivi de modèles, backend CNPG + artefacts S3)",
        "MLflow (suivi de modèles)",
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


def phase_playbook(phase: str) -> str | None:
    """Playbook unitaire d'une phase (chemin relatif au repo), ou None si la phase
    n'est pas un play lançable isolément (amont/script/enchaînement délégué).

    Accesseur de la table PHASE_PLAYBOOK (source unique du mapping, alignée sur
    run-phases.sh) — évite d'exposer la table mutable à la façade."""
    spec = PHASE_PLAYBOOK.get(phase)
    return spec.playbook if spec else None


# ── Socle dérivé + alias de chemins nommés (ADR 0083) ────────────────────────
# Le socle de BASE = up → bootstrap (k8s + CNI SEULS). Le STOCKAGE n'en fait PAS
# partie (ADR 0039 : base ⊂ store) : il vient des layers déclarés. En mode Ceph le
# socle pose ceph+sc (stockage Ceph indissociable du socle de ce backend).
# `hardening` s'insère APRÈS le socle (run_hardening_if_requested) si demandé.
_SOCLE_CEPH = ["up", "bootstrap", "ceph", "sc"]
_SOCLE_LIGHT = ["up", "bootstrap"]

# ha-3cp : chemin HA à séquence PROPRE (amorçage VIP + joins etcd), NON réductible à
# des layers. Son refactor (HA = propriété de la topologie) est DIFFÉRÉ à une PR dédiée
# (ADR 0083 §À revoir) — ici on le conserve tel quel pour ne pas casser le HA existant.
_HA_3CP_SEQUENCE = ["up", "bootstrap-ha", "join-cp", "storage-simple"]

# Alias de chemins nommés → ENSEMBLE de layers (ADR 0083). PLUS de séquence figée
# (`_PATH_TAIL` supprimé) : l'ORDRE vient TOUJOURS de resolve_layers (graphe atomique).
# Ces noms ne sont plus DÉRIVÉS par défaut (default_target rend `layers`) ; ils restent
# acceptés via `--target <nom>` (rétrocompat CLI/scénarios). `atlas` vit dans
# LAYER_PHASES (alias composite, nestor/layers.py) — ici les presets de CHEMIN restants.
_PRESET_LAYERS: dict[str, list[str]] = {
    "socle": ["base"],
    "metrics": ["metrics"],
    "atlas": ["atlas"],  # alias composite (LAYER_PHASES) : chaîne MLOps complète
    "storage-real": ["store"],  # pile stockage + épreuves S3/wordpress (cf. _PRESET_EPREUVES)
    "cluster-dataops": ["store", "obs", "dataops"],
    "atlas-ceph": ["atlas"],  # même alias ; le backend ceph donne la pile Ceph
}
# Épreuves jetables (hors graphe atomique) ajoutées EN QUEUE par certains presets :
# storage-real = pile stockage (store) + smoke-s3 + wordpress (harnais — pas des layers).
_PRESET_EPREUVES: dict[str, list[str]] = {
    "storage-real": ["smoke-s3", "wordpress"],
}
# Presets qui exigent le backend Ceph (refusés en local-path, parité run-phases.sh).
_CEPH_PRESETS = {"storage-real", "cluster-dataops", "atlas-ceph"}

# Cibles connues acceptées par `--target` : les alias de chemin + l'épreuve storage-real
# + le générique `layers` + `ha-3cp` (chemin HA conservé, refactor différé, ADR 0083).
KNOWN_TARGETS = frozenset(_PRESET_LAYERS) | set(_PRESET_EPREUVES) | {"layers", "ha-3cp"}


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
    """Chemin DÉDUIT de la topologie déclarée (ADR 0083).

    HA D'ABORD : > 1 control-plane → `ha-3cp` (chemin d'amorçage VIP/etcd à séquence
    propre, NON réductible à des layers ; son refactor est différé à une PR dédiée).
    Sinon : TOUJOURS `layers` — la séquence vient EXCLUSIVEMENT du graphe atomique
    (`resolve_layers`) + le socle dérivé. Plus de mapping vers des presets applicatifs
    (`atlas`/`socle`/`metrics`/`atlas-ceph`), seconde source de vérité de l'ordre
    supprimée. Les noms de preset restent acceptés via `--target <nom>` (KNOWN_TARGETS,
    rétrocompat) mais ne sont plus DÉRIVÉS. `atlas` est désormais un alias de LAYERS
    (`layers: [atlas]`), pas un chemin."""
    if topo.is_ha_control_plane:
        return "ha-3cp"
    return "layers"


def expected_phase_sequence(topo: Topology, target: str | None = None) -> list[str]:
    """Séquence ORDONNÉE de phases, selon le backend et la HA de `topo` (ADR 0083).

    UNE seule logique : socle DÉRIVÉ (léger / ceph / HA) + `hardening` si demandé +
    la queue DÉRIVÉE du graphe atomique (`resolve_layers`) — plus de table figée par
    preset. `target` choisit seulement l'ENSEMBLE de layers : `layers` (défaut) prend
    les couches déclarées de la topo ; un nom de preset (`--target atlas`…) prend son
    alias (`_PRESET_LAYERS`), plus d'éventuelles épreuves jetables en queue
    (`_PRESET_EPREUVES`, hors graphe). Lève PlanError sur un target inconnu ou un
    preset Ceph sur backend non-ceph (parité run-phases.sh).
    """
    from nestor.layers import resolve_layers

    target = target or default_target(topo)
    if target not in KNOWN_TARGETS:
        raise PlanError(f"chemin `{target}` inconnu (connus : {sorted(KNOWN_TARGETS)})")
    backend = _backend_of(topo)

    # ha-3cp : chemin HA à séquence propre (amorçage VIP + joins), conservé tel quel
    # (refactor différé, ADR 0083). Backend local-path imposé (HA ⊥ stockage, #250).
    if target == "ha-3cp":
        if backend == "ceph":
            raise PlanError(
                "chemin `ha-3cp` = local-path (HA ⊥ stockage, #250) ; pas de backend ceph"
            )
        seq = list(_HA_3CP_SEQUENCE)
        if _hardening_requested(topo):
            seq.insert(2, "hardening")  # après bootstrap-ha, avant les joins
        return seq

    if target in _CEPH_PRESETS and backend != "ceph":
        raise PlanError(f"chemin `{target}` exige le backend ceph (déclaré : `{backend}`)")
    # Socle DÉRIVÉ : ceph (bloc dans le socle) ou léger. Le stockage local-path n'est
    # PAS dans le socle (ADR 0039) : il vient des layers déclarés (resolve_layers).
    seq = list(_SOCLE_CEPH if backend == "ceph" else _SOCLE_LIGHT)
    if _hardening_requested(topo):
        seq.append("hardening")
    # Queue DÉRIVÉE du graphe : layers déclarés (target=layers) ou l'alias du preset.
    declared = topo.declared_layers if target == "layers" else _PRESET_LAYERS[target]
    queue = [p for p in resolve_layers(declared, backend) if p not in seq]
    seq.extend(queue)
    # Épreuves jetables (hors graphe atomique) ajoutées en queue par certains presets.
    seq.extend(_PRESET_EPREUVES.get(target, []))
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


# Phases AMONT strictement séquentielles : le provisioning (VMs) et l'amorçage du
# socle k8s sont des prérequis DURS de TOUT le reste — jamais un « choix » parmi
# d'autres. Tant qu'une de ces phases manque, c'est la SEULE chose à proposer.
_AMONT_PHASES = frozenset({"up", "bootstrap", "bootstrap-ha", "join-cp"})


def installable_now(
    topo: Topology,
    target: str | None,
    done: set[str],
    freshness: str,
    deps_fn: Callable[[], dict[str, set[str]]] | None = None,
    observed_done: set[str] | None = None,
) -> list[str]:
    """Phases du chemin `target` MONTABLES MAINTENANT, dans l'ordre du chemin.

    « Montable » = phase manquante (cf. `diff_phases`) dont TOUTES les dépendances
    RÉELLES (graphe atomique, `layers.phase_deps`) sont déjà dans `done`. C'est ce
    qui permet à `next` de proposer un MENU : `metrics-server` et `storage-simple`
    n'ayant aucune arête entre eux, les deux sont montables après le socle —
    l'opérateur choisit l'ordre (l'ordre conventionnel du chemin reste le DÉFAUT,
    c.-à-d. le premier de la liste renvoyée).

    Garde-fou amont : si une phase de `_AMONT_PHASES` manque, elle est un prérequis
    DUR (pas de cluster sans VMs ni socle) → on renvoie CETTE seule phase, jamais un
    menu (on ne « choisit » pas de créer les VMs vs monter une couche applicative).

    `observed_done` : phases PROUVÉES présentes par l'ÉTAT RÉEL (signal d'infra observé
    — la façade le calcule via `_observed_layers`/`observed_done_phases`). Elles sont
    TOUJOURS retirées des montables, même quand la fraîcheur est `perime`/`jamais` (où
    `diff_phases` rejouerait toute la séquence) : le RÉEL prime sur la fraîcheur (ADR
    0052/0056 §7) — une couche déjà déployée n'est pas « à monter », sinon `next` la
    re-propose. Même calcul que `preview` (qui soustrait l'observé APRÈS diff_phases).

    `deps_fn` est un FOURNISSEUR PARESSEUX de la carte de dépendances (la façade y
    branche `layers.phase_deps`, qui SHELLE le graphe). Module PUR : `plan` n'appelle
    pas bash lui-même — il invoque `deps_fn` SEULEMENT au-delà du garde-fou amont
    (inutile pour `up`/`bootstrap`, et évite un appel bash quand il n'y a rien à
    désambiguïser). `deps_fn` None → repli SÛR « 1er drift » seul (au plus une phase) :
    sans la carte, on ne PRÉSUME pas l'indépendance de deux couches.
    """
    target = target or default_target(topo)
    seq = expected_phase_sequence(topo, target)
    observed_done = observed_done or set()
    # Le RÉEL prime sur la fraîcheur : une phase observée présente n'est jamais « à
    # monter » (même en rejeu). On la traite comme faite (∈ done) ET on la retire des
    # manquantes — pour les DEUX décisions (ce qui reste à monter, et la satisfaction
    # des dépendances d'une couche aval).
    done = done | observed_done
    manquantes = [p for p in diff_phases(seq, done, freshness) if p not in observed_done]
    if not manquantes:
        return []
    # Prérequis dur : la première phase amont manquante est la seule offre possible.
    # (On NE consulte PAS deps_fn ici — pas de bash pour décider de créer les VMs.)
    for phase in seq:
        if phase in _AMONT_PHASES and phase in manquantes:
            return [phase]
    if deps_fn is None:
        return [manquantes[0]]
    deps = deps_fn()
    # Une phase manquante est montable si aucune de ses dépendances n'est elle-même
    # manquante (⇔ toutes ses deps sont satisfaites). On préserve l'ordre du chemin.
    manquantes_set = set(manquantes)
    return [p for p in manquantes if not (deps.get(p, set()) & manquantes_set)]
