"""Graphe d'APPARTENANCE des ressources Kubernetes, pour un rollback PAR DÉCOUVERTE.

Implémente le cœur PUR de l'[ADR 0079] : au lieu d'une table de périmètre codée à la
main (`rollback-lib.sh`), on DÉRIVE du réel ce qui appartient à une couche et dans quel
ordre le défaire. Ce module ne fait AUCUN I/O : il prend des ressources DÉJÀ sondées
(la façade les lit via `kubectl get -o json` / `api-resources`, ADR 0049) et calcule
un graphe + un ordre de teardown. Testable sans cluster.

Une ressource sondée est un dict minimal :
    {"kind": str, "name": str, "namespace": str|None, "uid": str,
     "owners": [str, …]}   # uids des ownerReferences (cascade GC k8s)

Le graphe d'appartenance suit `ownerReferences` (le GC k8s s'en sert déjà) : un Pod
pointe son ReplicaSet → son Deployment ; un PVC/Secret créé par un opérateur pointe
son CR. L'ordre de TEARDOWN est l'INVERSE de la possession : on détruit les POSSÉDÉS
avant leurs POSSESSEURS (un Deployment supprimé avant ses Pods les laisserait orphelins
le temps de la cascade ; on veut un retrait déterministe aval→amont).

Ce N'EST PAS un nouveau graphe codé (ADR 0066) : l'arête vient de la ressource RÉELLE
(`ownerReferences`), pas d'une table. Une ressource sans owner connu est une RACINE.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Resource:
    """Ressource k8s sondée, réduite à ce qui sert au graphe (PUR, pas d'I/O)."""

    kind: str
    name: str
    uid: str
    namespace: str | None = None
    owners: tuple[str, ...] = ()  # uids des ownerReferences

    @property
    def ref(self) -> str:
        """Référence lisible `kind/name` (dans son ns implicite) pour l'affichage/delete."""
        return f"{self.kind}/{self.name}"


def from_probe(items: list[dict]) -> list[Resource]:
    """Convertit des dicts sondés (façade) en `Resource` (PUR, tolérant aux champs absents).

    `owners` est dérivé des `ownerReferences[*].uid`. Un item sans `uid` est ignoré (on ne
    peut pas le situer dans le graphe) — la façade garantit l'uid via `-o json`."""
    out: list[Resource] = []
    for it in items:
        uid = it.get("uid")
        if not uid:
            continue
        owners = tuple(o.get("uid") for o in (it.get("ownerReferences") or []) if o.get("uid"))
        out.append(
            Resource(
                kind=it.get("kind", "?"),
                name=it.get("name", "?"),
                uid=uid,
                namespace=it.get("namespace"),
                owners=owners,
            )
        )
    return out


@dataclass
class OwnershipGraph:
    """Graphe d'appartenance : uid → Resource, et arêtes possesseur→possédés."""

    by_uid: dict[str, Resource] = field(default_factory=dict)
    owned: dict[str, list[str]] = field(default_factory=dict)  # uid possesseur → uids possédés

    @property
    def roots(self) -> list[Resource]:
        """Ressources SANS possesseur présent dans le graphe (racines de l'arbre)."""
        return [r for r in self.by_uid.values() if not any(o in self.by_uid for o in r.owners)]


def build_ownership(resources: list[Resource]) -> OwnershipGraph:
    """Construit le graphe d'appartenance depuis les `ownerReferences` (PUR, ADR 0079).

    L'arête va du POSSESSEUR vers le POSSÉDÉ (un Deployment possède ses ReplicaSets, qui
    possèdent leurs Pods). Un owner référencé mais ABSENT de l'ensemble sondé est ignoré
    (la ressource devient une racine — son possesseur est hors périmètre)."""
    g = OwnershipGraph(by_uid={r.uid: r for r in resources})
    g.owned = {uid: [] for uid in g.by_uid}
    for r in resources:
        for owner_uid in r.owners:
            if owner_uid in g.by_uid:  # possesseur présent → arête
                g.owned[owner_uid].append(r.uid)
    return g


def teardown_order(resources: list[Resource]) -> list[Resource]:
    """Ordre de SUPPRESSION : POSSÉDÉS avant POSSESSEURS (aval→amont), déterministe (PUR).

    Tri topologique inverse du graphe d'appartenance : on émet d'abord les feuilles
    (ressources que personne ne possède dans l'ensemble), puis on remonte. Robuste aux
    CYCLES (ownerReferences pathologiques) : un cycle non résolu est émis en fin, dans
    l'ordre stable d'entrée — on ne BOUCLE jamais. Ordre stable (uid d'entrée) pour la
    reproductibilité (ADR 0066 : déterminisme)."""
    g = build_ownership(resources)
    # profondeur = distance à une racine (un possédé est plus PROFOND que son possesseur).
    # On supprime du PLUS profond au moins profond (feuilles d'abord).
    depth: dict[str, int] = {}

    def _depth(uid: str, seen: frozenset[str]) -> int:
        if uid in depth:
            return depth[uid]
        if uid in seen:  # cycle → profondeur 0, ne boucle pas
            return 0
        owners_in = [o for o in g.by_uid[uid].owners if o in g.by_uid]
        d = 0 if not owners_in else 1 + max(_depth(o, seen | {uid}) for o in owners_in)
        depth[uid] = d
        return d

    order_index = {r.uid: i for i, r in enumerate(resources)}
    for r in resources:
        _depth(r.uid, frozenset())
    # plus profond d'abord ; à profondeur égale, ordre d'entrée stable.
    return sorted(resources, key=lambda r: (-depth[r.uid], order_index[r.uid]))


# ── BRUIT : ressources qu'on ne supprime JAMAIS par découverte (ADR 0079) ──────────
# Sondées en masse par `api-resources × ns`, mais NON possédées par la couche : un
# contrôleur k8s/CNI les (re)crée tant que leur racine vit, ou elles sont éphémères. Les
# cibler génère des deletes inutiles/échoués (un SA `default` ne se supprime pas proprement)
# et de FAUSSES racines (un Event sans owner deviendrait une racine → supprimé pour rien).
# Constaté au banc dataops : 252/350 ressources découvertes sont des Event.
_NOISE_KINDS = frozenset(
    {
        "Event",  # éphémère, GC auto k8s — 252/350 au banc
        "EndpointSlice",  # endpointslice-controller, suit le Service (sa racine)
        "Endpoints",  # endpoints-controller, idem
        "CiliumEndpoint",  # CNI Cilium, suit le Pod (sa racine)
    }
)
# Ressources INJECTÉES par k8s dans chaque namespace (pas posées par la couche) : recréées
# si supprimées, et le SA `default` résiste au delete. (kind, name).
_NOISE_NAMED = frozenset(
    {
        ("ConfigMap", "kube-root-ca.crt"),  # root CA publisher, dans chaque ns
        ("ServiceAccount", "default"),  # SA par défaut, dans chaque ns
    }
)


def is_noise(r: Resource) -> bool:
    """`True` si la ressource est du BRUIT à NE JAMAIS supprimer (PUR, ADR 0079).

    Géré par un contrôleur k8s/CNI (recréé tant que sa racine vit), éphémère (Event), ou
    injecté par k8s dans chaque ns (`kube-root-ca.crt`, SA `default`). Voir `_NOISE_*`."""
    return r.kind in _NOISE_KINDS or (r.kind, r.name) in _NOISE_NAMED


def prune_noise(resources: list[Resource]) -> list[Resource]:
    """Retire le BRUIT (`is_noise`) — ordre conservé (PUR). À appeler AVANT le calcul des
    racines : une ressource-bruit orpheline deviendrait une fausse racine sinon."""
    return [r for r in resources if not is_noise(r)]


def delete_targets(resources: list[Resource]) -> list[Resource]:
    """Ressources à SUPPRIMER explicitement : les RACINES du graphe filtré, ordonnées (PUR).

    Cœur du « delete par les racines, laisse le GC k8s cascader » (ADR 0079) : on ne rend
    PAS les ~350 ressources sondées mais les ~15 RACINES (Deployment, CR opérateur, Service
    non-possédé, PVC/Secret/ConfigMap non-possédés…). Supprimer un Deployment efface ses
    ReplicaSets→Pods par cascade GC ; les cibler en plus serait redondant et créerait des
    courses (un Pod recréé entre-temps). On filtre d'ABORD le bruit (`prune_noise`) pour ne
    pas promouvoir un Event/CiliumEndpoint orphelin en racine.

    Ordre = `teardown_order` restreint aux racines (déterministe, ADR 0066). Entre racines
    indépendantes l'ordre est stable (entrée) ; il importe peu pour la cascade (chaque racine
    est autonome) mais reste reproductible."""
    pruned = prune_noise(resources)
    g = build_ownership(pruned)
    root_uids = {r.uid for r in g.roots}
    return [r for r in teardown_order(pruned) if r.uid in root_uids]


# ── CAS DURS : geste de déblocage DÉRIVÉ de l'état d'une ressource qui traîne (ADR 0079) ──
def classify_stuck(
    *,
    terminating: bool,
    has_finalizers: bool,
    container_alive: bool,
) -> str:
    """Verdict PUR du geste à appliquer à une ressource qui ne part pas (ADR 0079 §3).

    DÉRIVÉ de l'état observé, pas d'une liste figée :
      - pod `Terminating` à conteneur encore vivant         → "force_grace0" (force-delete)
      - ressource à finalizer dont le contrôleur est parti  → "strip_finalizers"
      - sinon (part normalement, ou déjà absente)           → "none"
    `container_alive` n'a de sens que pour un Pod ; l'appelant I/O le met à False ailleurs.
    Le force-delete prime (un pod coincé bloque la finalisation du ns)."""
    if terminating and container_alive:
        return "force_grace0"
    if has_finalizers:
        return "strip_finalizers"
    return "none"
