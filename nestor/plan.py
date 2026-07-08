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
    # gitops-seed-citation (ADR 0095 §1.a) : le vrai flux App-of-Apps citation joué au banc
    # (git push arbre atlas + apps/citation.yaml par digest + Applications). DONNÉES, pas un
    # play — portée par nestor/seed.py (kind banc-citation) + façade _seed_do_banc_citation.
    "gitops-seed-citation": PhaseSpec(
        None,
        "app-of-apps citation réel (données, ADR 0095 §1.a — seed)",
        "déploiement citation (App-of-Apps)",
    ),
    # Portail (ADR 0091/0092) : layer AUTONOME monté via le chemin générique `layers`.
    # Le portail observe les Services NodePort des autres couches (lecture seule) — il
    # n'a pas de dépendance dure (marche dès le socle, SKIP par endpoint absent), juste
    # son image registry:80/portal:dev (registry + build-images, graphe atomique).
    "portal": PhaseSpec(
        "bootstrap/portal.yaml",
        "portail d'accès aux UI (NodePort L4, lecture seule)",
        "portail d'accès aux UI",
    ),
    # Citation (ADR 0094/0095 §1.a) : layer AUTONOME node-side qui BUILD l'image
    # applicative de la code-location atlas `citation` (contexte multi-dossier dataops/,
    # comme portal) et lit son digest. Le DÉPLOIEMENT est GitOps (Argo CD tire par
    # digest), pas un signal de couche ici. Montée via le chemin générique `layers`.
    "citation": PhaseSpec(
        "bootstrap/citation.yaml",
        "build de l'image applicative citation (code-location atlas)",
        "image citation (build applicatif)",
    ),
    # NB (ADR 0105) : la phase `eventful` (chaîne événementielle Argo Workflows/Events,
    # ADR 0095 §1.b) est RETIRÉE — le build node-side (platform-build-images) est le
    # mécanisme terminal. Plus aucune PhaseSpec associée.
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

# HA (ADR 0097, voie 2) : le TARGET nommé `ha-3cp` est SUPPRIMÉ — son chemin
# d'exécution (run_ha_3cp / callback `ha`) a été retiré (commit fd04ee0), plus aucune
# séquence ne le produit ni ne le route. Le MODELAGE HA GÉNÉRIQUE survit intact et
# resservira au rebuild dirqual HA (prod 3 control-planes, #486) : `model.is_ha_control_plane`
# (dérivé du nombre de control-planes) + sa validation VIP, et les phases génériques
# `bootstrap-ha` / `join-cp` de PHASE_PLAYBOOK. Le chemin d'exécution HA sera recâblé
# dans path.py sous sa propre PR (ADR 0083 §2 : « la HA est une propriété de la topologie,
# pas un chemin nommé »).

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
# + le générique `layers`. Le target `ha-3cp` a été RETIRÉ (ADR 0097, voie 2 : chemin
# d'exécution HA supprimé ; le modelage HA générique reste, cf. note plus haut).
KNOWN_TARGETS = frozenset(_PRESET_LAYERS) | set(_PRESET_EPREUVES) | {"layers"}


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

    TOUJOURS `layers` — la séquence vient EXCLUSIVEMENT du graphe atomique
    (`resolve_layers`) + le socle dérivé. Plus de mapping vers des presets applicatifs
    (`atlas`/`socle`/`metrics`/`atlas-ceph`), seconde source de vérité de l'ordre
    supprimée. Les noms de preset restent acceptés via `--target <nom>` (KNOWN_TARGETS,
    rétrocompat) mais ne sont plus DÉRIVÉS. `atlas` est désormais un alias de LAYERS
    (`layers: [atlas]`), pas un chemin.

    HA (ADR 0097, voie 2) : plus de dérivation vers un target `ha-3cp` (supprimé — son
    chemin d'exécution n'existe plus). Le modelage HA générique (`is_ha_control_plane`,
    phases `bootstrap-ha`/`join-cp`) est préservé pour le rebuild dirqual HA (#486) ; son
    câblage dans le moteur reviendra sous sa PR dédiée."""
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

    if target in _CEPH_PRESETS and backend != "ceph":
        raise PlanError(f"chemin `{target}` exige le backend ceph (déclaré : `{backend}`)")
    # Socle DÉRIVÉ : ceph (bloc dans le socle) ou léger. Le stockage local-path n'est
    # PAS dans le socle (ADR 0039) : il vient des layers déclarés (resolve_layers).
    seq = list(_SOCLE_CEPH if backend == "ceph" else _SOCLE_LIGHT)
    # `up` = PROVISIONNER les VMs (limactl) : propre au banc Lima. En prod (target_kind:
    # prod), les nœuds baremetal PRÉEXISTENT → pas de phase `up`, le socle commence à
    # `bootstrap` (k8s sur les nœuds existants), ADR 0084.
    if topo.target_kind != "bench":
        seq = [p for p in seq if p != "up"]
    if _hardening_requested(topo):
        seq.append("hardening")
    # Queue DÉRIVÉE du graphe : layers déclarés (target=layers) ou l'alias du preset.
    declared = topo.declared_layers if target == "layers" else _PRESET_LAYERS[target]
    queue = [p for p in resolve_layers(declared, backend) if p not in seq]
    seq.extend(queue)
    # Épreuves jetables (hors graphe atomique) ajoutées en queue par certains presets.
    seq.extend(_PRESET_EPREUVES.get(target, []))
    return seq


def diff_phases(
    expected: list[str], done: set[str], freshness: str, observed: set[str] | None = None
) -> list[str]:
    """Phases du `expected` non encore satisfaites, dans l'ordre.

    Si la fraîcheur est `perime`/`jamais` (verdict de history.py — RÉUTILISÉ, pas
    redérivé), toute la séquence est candidate au rejeu (le chemin n'a pas de run
    frais) — SAUF les phases que le RÉEL prouve déjà faites (`observed`). Sinon, on ne
    retient que les phases absentes de `done`.

    `observed` (état RÉEL : nœuds Ready, couches déployées) PRIME TOUJOURS sur la
    fraîcheur de l'historique (ADR 0052/0056 §7) : un cluster prod sain mais sans run
    nestor consigné a `freshness="jamais"` ; sans cette soustraction, `next`
    proposerait de RÉINSTALLER bootstrap/des couches déjà en place — ce que `preview`
    (qui soustrait l'observé) ne fait pas. Les deux DOIVENT rendre le même verdict.
    """
    observed = observed or set()
    if freshness in ("perime", "jamais"):
        return [p for p in expected if p not in observed]
    return [p for p in expected if p not in (done | observed)]


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


@dataclass(frozen=True)
class PlanState:
    """État du plan dérivé : phases tenues pour FAITES et phases À APPLIQUER.

    Résultat PUR (aucune I/O) de `compute_plan_state` — la source UNIQUE consommée
    par `cmd_preview`/`cmd_next`/`cmd_up` (fin de la divergence preview≠next : les
    trois dérivent du MÊME calcul). `done` = socle/couches que le RÉEL SEUL confirme
    (refonte lot 6 : plus d'historique) ; `a_appliquer` = ce qui reste à monter
    (ordonner via `seq` à l'affichage)."""

    done: frozenset[str]
    a_appliquer: frozenset[str]


def compute_plan_state(
    seq: list[str],
    observed_socle: set[str],
    observed_layers: set[str],
) -> PlanState:
    """Calcule `done`/`a_appliquer` d'un chemin — LE calcul partagé (ADR 0052/0056 §7).

    Fonction PURE : tout l'état RÉEL arrive en PARAMÈTRES (aucun kubectl ici). La
    façade (qui sonde le cluster) fournit :
    - `seq` : la séquence ORDONNÉE attendue (`expected_phase_sequence`) ;
    - `observed_socle` : socle PROUVÉ par le réel (`observed_done_phases` : VMs/nœuds
      Ready), ∅ quand le réel ne confirme rien (VMs détruites, Kubernetes mort) ;
    - `observed_layers` : couches applicatives observées SAINES (`_observed_layers`),
      ∅ quand on NE sonde PAS le cluster (pas de nœud Ready / cible prod sans cible).

    `done` DÉRIVE DU RÉEL SEUL — PLUS DE L'HISTORIQUE (décision mainteneur, refonte
    lot 6). `done = observed_socle ∪ observed_layers` : EXACTEMENT ce que le cluster
    CONFIRME (VMs/nœuds Ready pour up/bootstrap, couches saines pour les layers à
    signal). L'historique (`runs-history.yaml`) ne décide PLUS `done` : il ne sert
    qu'à la FRAÎCHEUR (`verdict_for_run`, dérivée SÉPARÉMENT en amont, #216) et au
    cache socle (#219) — usages préservés, hors de ce calcul.

    CONSÉQUENCE COHÉRENTE (le bug du mainteneur) : si `bootstrap` n'est pas observé
    (Kubernetes mort), AUCUNE couche aval n'entre dans `observed_layers` (le kubectl
    échoue) → toutes sont « à appliquer ». La cohérence de dépendance devient NATURELLE
    (le réel ne ment pas) : plus besoin du garde ad hoc `if "up" not in done` — un
    socle absent rend `observed_layers` vide, donc rien aval n'est tenu fait.

    Le RÉEL fait AUTORITÉ DANS LES DEUX SENS : une couche observée saine est `done` (et
    hors de `a_appliquer`), même sans run consigné ; une couche que le réel NE confirme
    PAS est « à appliquer », même si un vieux run la disait faite (l'historique ne
    survit plus au réel).
    """
    # `done` = RÉEL SEUL : socle prouvé (VMs/nœuds) ∪ couches saines observées. PLUS de
    # `set(run_phases)` : l'historique n'entre PLUS dans le calcul de `done` (refonte lot 6).
    done = set(observed_socle) | set(observed_layers)
    # `a_appliquer` = tout ce que le réel NE confirme PAS, dans l'ordre de `seq`. Comme
    # `done` ne vient QUE du réel, la cohérence de dépendance est intrinsèque : un socle
    # absent (observed_layers vide) laisse TOUTES les couches aval « à appliquer ».
    a_appliquer = {p for p in seq if p not in done}
    return PlanState(done=frozenset(done), a_appliquer=frozenset(a_appliquer))


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
    observed: set[str] | None = None,
) -> Suggestion:
    """Suggère la PROCHAINE phase manquante (1er drift, parité state.sh #107-109).

    `done` : phases déjà jouées (fournies par la façade depuis l'historique/state).
    `freshness` : verdict de history.verdict_for_run. `observed` : phases que l'ÉTAT
    RÉEL prouve faites (nœuds Ready, couches déployées) — PRIME sur la fraîcheur
    (ADR 0052/0056 §7), sinon un cluster sain sans run consigné se ferait re-proposer
    le rejeu de phases déjà en place (incohérent avec `preview`). `run_params` : le
    faisceau `-e` dérivé (profile.derive_run_params) à attacher à la phase, pour que
    `--apply` lance le MÊME play avec les MÊMES `-e` que run-phases.sh (ADR 0063 G3).
    """
    target = target or default_target(topo)
    seq = expected_phase_sequence(topo, target)
    manquantes = diff_phases(seq, done, freshness, observed)
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
    a_appliquer: set[str] | None = None,
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

    `a_appliquer` : ensemble des phases manquantes DÉJÀ calculé par `compute_plan_state`
    (le calcul PARTAGÉ preview/next/up). Quand il est fourni, `installable_now` ne
    RECALCULE PAS « ce qui reste » (il hérite ainsi du garde `if "up" not in done` ET
    du 2e sens du RÉEL — une couche à signal que le réel contredit RESTE à monter) ; il
    ne fait plus que TRIER ces manquantes par satisfaction des dépendances. C'est ce
    qui garantit `next == preview`. `observed_done`/`freshness` ne servent alors qu'à
    déterminer `done` (deps satisfaites). `a_appliquer` None → repli legacy (recalcul
    interne via `diff_phases`, conservé pour les appelants/tests existants).

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
    if a_appliquer is not None:
        # Source PARTAGÉE (compute_plan_state) : on hérite du garde + du 2e sens du réel,
        # on ne recalcule PAS « ce qui reste » → next == preview. Ordre = celui de `seq`.
        manquantes = [p for p in seq if p in a_appliquer]
    else:
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
