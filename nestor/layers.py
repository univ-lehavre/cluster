"""Dérivation de la séquence de couches depuis `topology.layers` (ADR 0069).

`layers` déclare un ENSEMBLE de couches (grain phase) ; l'outil en DÉRIVE l'ordre
par tri topologique du DAG de dépendances RÉELLES — pas par une chaîne totale
(ADR 0039) qui imposait de fausses dépendances (déclarer `store` forçait `metrics`).

**Source UNIQUE de l'ordre** : le graphe atomique FIGÉ `nestor/graph.py` (ADR 0096 §1,
porté byte-identique de `rollback-lib.sh`, ADR 0066 ; `topo_sort`/`component_expand_alias`/
`phase_of_component`). On NE code PAS un second graphe phase→phase en Python (ce serait
recréer le double-graphe que 0066 a tué) : `resolve_layers` APPELLE `graph.py` et PROJETTE
le résultat au grain phase. Le graphe est CONDITIONNEL au backend (ADR 0069) : on lui passe
le `backend` et il émet déjà la bonne variante de stockage (storage-simple + seaweedfs en
local-path, ceph+sc+datalake en ceph) — aucun filtrage côté Python. Plus aucun sous-process
bash ici (lot 3 du plan de refonte : le pont `rollback-lib.sh` est remplacé par `graph.py`).

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

from nestor import graph
from nestor.errors import TopologyError

# Alias de profil → phases qu'il apporte (projection de PROFILE_BRICKS, ADR 0039/0068).
# `store` se projette en `storage`, jeton ABSTRAIT que le graphe atomique résout par
# backend (storage-simple en local-path, ceph+sc en ceph) via _expand_alias.
LAYER_PHASES: dict[str, list[str]] = {
    "base": [],  # socle nu (up/bootstrap), aucune couche de queue
    "metrics": ["metrics-server"],
    "store": ["storage"],
    "obs": ["monitoring"],
    "dataops": ["dataops"],
    # `atlas` (ADR 0083) : alias de la CHAÎNE MLOps complète — ancien preset atlas
    # (metrics-server + monitoring + gitops + gitops-seed + dataops) PLUS mlflow
    # (ADR 0082). Alias COMPOSITE : il référence d'autres alias (metrics/obs/store)
    # → _expand_to_phases se déplie récursivement. L'ORDRE vient de resolve_layers
    # (graphe atomique) ; ici un simple ENSEMBLE. `gitops-seed` est listé explicitement
    # (phase de QUEUE non tirée par la clôture de [gitops]). N'EST PAS un profil
    # (profile reste le préfixe cumulatif base⊂…⊂dataops, ADR 0039) : `layers: [atlas]`.
    "atlas": ["metrics", "store", "obs", "gitops", "dataops", "gitops-seed", "mlflow", "portal"],
}

# Phases applicatives composables au grain phase (queue, hors socle up/bootstrap).
# `storage` est le jeton abstrait du stockage (résolu par backend en storage-simple,
# ou ceph+sc+datalake — bloc ET objet RGW). smoke-s3/wordpress n'existent qu'en ceph.
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
        "mlflow",
        "gitops-seed",
        "gitops-seed-citation",
        "portal",
    }
)

# Phases de STOCKAGE (placées en tête de queue — montées avant leurs consommateurs).
_STORAGE_PHASES = frozenset({"storage-simple", "ceph", "sc", "datalake"})

# Jetons acceptés dans `layers` : alias de profil OU noms de phase de queue.
VALID_LAYERS = frozenset(LAYER_PHASES) | _QUEUE_PHASES | {"storage"}

# Phases qui n'existent QU'EN backend ceph (RGW) — refusées en local-path.
_CEPH_ONLY = frozenset({"datalake", "ceph", "sc"})


def _expand_to_phases(declared: list[str], _seen: frozenset[str] = frozenset()) -> list[str]:
    """Normalise les jetons `layers` en phases/jetons (alias de profil → ses phases).

    Dépliage RÉCURSIF : un alias peut référencer d'autres alias (ex. `atlas` →
    `metrics`/`obs`/`store` → leurs phases). `_seen` borne la récursion (anti-cycle :
    un alias qui se référence, direct ou transitif, lève TopologyError). Lève aussi
    TopologyError sur un jeton inconnu. Le jeton `storage` (abstrait) et les phases
    brutes (non-alias) sont laissés tels quels : le graphe les résout dans _expand_alias."""
    phases: list[str] = []
    for token in declared:
        if token not in VALID_LAYERS:
            raise TopologyError(
                f"couche `{token}` inconnue (valides : {sorted(VALID_LAYERS)}, ADR 0069)"
            )
        expansion = LAYER_PHASES.get(token, [token])
        # Jeton terminal (phase brute ou `storage`) : LAYER_PHASES rend [token] inchangé.
        if expansion == [token]:
            phases.append(token)
            continue
        if token in _seen:
            raise TopologyError(f"alias `{token}` cyclique (chaîne : {sorted(_seen)}, ADR 0083)")
        # Alias (composite) : déplier récursivement ses jetons (qui peuvent être des alias).
        phases.extend(_expand_to_phases(expansion, _seen | {token}))
    return phases


def _expand_alias(phase: str, backend: str) -> list[str]:
    """Composants d'une phase via component_expand_alias (backend-conditionnel), ou
    [phase] si la phase est hors graphe roundtrip. Le jeton abstrait `storage` (profil
    `store`) se résout en la pile stockage COMPLÈTE du backend : en local-path le
    provisioner `storage-simple` (bloc seul, pas de RGW) ; en ceph le bloc (`ceph`+`sc`)
    ET l'objet (`datalake` = RGW S3) — `store` offre bloc + objet (ADR 0039). Le tri
    topologique (resolve_layers) ordonne ceph→sc→datalake."""
    if phase == "storage":
        return ["storage-simple"] if backend != "ceph" else ["ceph", "sc", "datalake"]
    comps = graph.component_expand_alias(phase, backend)
    return comps or [phase]


def resolve_layers(declared: list[str], backend: str = "local-path") -> list[str]:
    """Séquence ORDONNÉE des phases de queue dérivée de `layers` (ADR 0069).

    Étapes : (1) défaut `base` si vide ; (2) normaliser alias→phases ; (3) refuser une
    phase ceph-only en local-path ; (4) fermer en composants + trier via le graphe
    atomique backend-conditionnel (graph.py) ; (5) projeter au grain phase,
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
    ordered = graph.topo_sort(components, backend)
    result: list[str] = []
    for comp in ordered:
        # Projeter le composant sur sa phase de queue. `phase_of_component` couvre les
        # phases du roundtrip (monitoring/dataops/…) ; `storage-simple`/`metrics-server`
        # SONT eux-mêmes des phases de queue (hors _ROUNDTRIP_PHASES) → repli sur le nom.
        ph = graph.phase_of_component(comp, backend)
        if not ph and comp in _QUEUE_PHASES:
            ph = comp
        if ph and ph in _QUEUE_PHASES and ph not in result:
            result.append(ph)
    # Le STOCKAGE précède toute couche applicative (convention de montage : storage
    # AVANT metrics/monitoring/apps — même quand metrics n'en dépend pas). Partition
    # STABLE (préserve l'ordre topo dans chaque groupe), pas un re-tri → ordre de
    # montage déterministe sans toucher aux poids du graphe.
    storage = [p for p in result if p in _STORAGE_PHASES]
    rest = [p for p in result if p not in _STORAGE_PHASES]
    return storage + rest


def layers_from_profile(profile: str) -> list[str]:
    """Projette un `profile` (ADR 0039, alias déprécié-doux) en `layers` équivalents.

    Un profil = le PRÉFIXE cumulatif de la chaîne jusqu'à lui. On renvoie les alias
    de ce préfixe (resolve_layers fera la fermeture/tri). Import LOCAL de
    required_profiles pour éviter un cycle profile↔layers."""
    from nestor.profile import required_profiles

    return list(required_profiles(profile))


def _phase_of(comp: str, backend: str) -> str:
    """Phase de QUEUE qui contient le composant `comp`, ou '' s'il relève du socle.

    `phase_of_component` (graphe atomique) couvre les phases du roundtrip ; les
    phases de queue qui n'y figurent pas (`storage-simple`/`metrics-server`) SONT
    elles-mêmes leur phase → même repli que `resolve_layers` (ligne 155). Sans ce
    repli, l'arête `gitea → storage-simple` serait perdue (storage-simple hors
    _ROUNDTRIP_PHASES) et `gitops` paraîtrait à tort sans dépendance de stockage."""
    ph = graph.phase_of_component(comp, backend)
    if not ph and comp in _QUEUE_PHASES:
        ph = comp
    return ph


def phase_deps(backend: str = "local-path") -> dict[str, set[str]]:
    """Dépendances PHASE→PHASE des couches de queue, DÉRIVÉES du graphe atomique.

    Pour chaque phase de queue, l'ensemble des AUTRES phases de queue dont un de ses
    composants dépend (directement) — projeté au grain phase via `_phase_of`. C'est
    la VRAIE dépendance (ADR 0066, source unique), pas l'ordre conventionnel de
    montage (`resolve_layers` met le stockage en tête même quand metrics n'en
    dépend pas). Backend-conditionnel : en local-path le stockage est `storage-simple`,
    en ceph `ceph`/`sc`/`datalake` (le graphe émet déjà la bonne variante).

    Sert à `plan.installable_now` : une couche est montable dès que TOUTES ses
    dépendances ici sont satisfaites — ce qui rend `metrics-server` montable AVANT
    `storage-simple` (aucune arête entre eux), au choix de l'opérateur."""
    deps: dict[str, set[str]] = {}
    for phase in _QUEUE_PHASES:
        # Une phase ceph-only n'existe pas en local-path : pas d'entrée (le graphe
        # ne la monterait pas). On la saute proprement plutôt que d'inventer une arête.
        if backend != "ceph" and phase in _CEPH_ONLY:
            continue
        direct: set[str] = set()
        for comp in _expand_alias(phase, backend):
            for dep in graph.component_deps(comp, backend):
                pd = _phase_of(dep, backend)
                if pd and pd != phase and pd in _QUEUE_PHASES:
                    direct.add(pd)
        deps[phase] = direct
    return deps
