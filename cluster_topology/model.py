"""Modèle de données d'une topologie (ADR 0056 §1).

Chargement + validation minimale de `topology.yaml`. Pas de pydantic à ce
palier (P0-P1) : un dataclass + des dérivations pures suffisent ; la validation
de schéma riche viendra en P2 (graphe de dépendances de profil). On reste sur
la stdlib + pyyaml (ADR 0049 : pas de dépendance avant le besoin).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


class TopologyError(ValueError):
    """topology.yaml invalide (champ manquant, rôle inconnu, incohérence)."""


VALID_ROLES = {"control", "worker", "storage"}
VALID_TARGET_KINDS = {"prod", "lima"}
# Modes du point d'entrée HA devant les CP (ADR 0047/0055). kube-vip-arp =
# bare-metal/local (pod statique, annonce ARP) ; kube-vip-lb = via LB-IPAM ;
# external = LB fourni par le terrain (cloud, ADR 0040).
VALID_LB_MODES = {"kube-vip-arp", "kube-vip-lb", "external"}
# Modes d'exposition applicative (ADR 0020/0071). `gateway` = bordure L7 Cilium
# (LB-IPAM + Gateway API) ; `hostport` = 80/443 sur l'IP de l'hôte (eBPF, VM publique) ;
# `none` = ClusterIP seuls. `lb-ipam` est un ALIAS déprécié-doux de `gateway` (ADR 0071 §3).
VALID_EXPOSITION_MODES = {"gateway", "hostport", "none"}
_EXPOSITION_ALIASES = {"lb-ipam": "gateway"}
# Défaut d'exposition par terrain (ADR 0071 §6) : le banc Lima en `hostport` (le plus
# reproductible, sans plage IP/L2) ; ailleurs `gateway` (bordure L7 de référence).
_EXPOSITION_DEFAULT = {"lima": "hostport"}


@dataclass
class Node:
    name: str
    roles: list[str]
    ansible_host: str | None = None
    disks: list[str] | None = None

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass
class Topology:
    """Vue typée d'un topology.yaml. Les dérivations (listes control/worker…)
    sont des PROPRIÉTÉS pures, testables sans I/O."""

    catalog: dict[str, Any]
    nodes: list[Node]
    network: dict[str, Any] = field(default_factory=dict)
    exposition: dict[str, Any] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)
    hardening: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] | None = None
    target_kind: str = "prod"
    # `layers` (ADR 0069) : ENSEMBLE de couches déclaré au top-level, ordonné par le
    # DAG (resolve_layers). Vide → rétrocompat : dérivé de `catalog.profile` (alias
    # déprécié-doux). Voir la propriété `declared_layers`.
    layers: list[str] = field(default_factory=list)

    # ── Dérivations pures (le cœur de la génération sans état) ──────────────
    @property
    def control_nodes(self) -> list[str]:
        """Noms des nœuds portant le rôle `control`, dans l'ordre déclaré."""
        return [n.name for n in self.nodes if n.has_role("control")]

    @property
    def worker_nodes(self) -> list[str]:
        """Noms des nœuds portant le rôle `worker` (et PAS `control`), ordre déclaré.

        Un nœud hyperconvergé (control+worker) est un control-plane qui schedule ;
        dans l'inventaire Ansible il vit dans le groupe `control` (le détaint le
        rend schedulable, ADR 0007). Le groupe `workers` ne liste donc que les
        nœuds worker-PURS — sinon double appartenance et drift d'inventaire.
        """
        return [n.name for n in self.nodes if n.has_role("worker") and not n.has_role("control")]

    @property
    def hyperconverged_nodes(self) -> list[str]:
        """Noms des nœuds control qui portent AUSSI `worker` (hyperconvergés, ADR 0055).

        Ils vivent dans `control_nodes` (control prime) et PAS dans `worker_nodes`
        (workers purs) — d'où un affichage `workers: —` trompeur si on ne signale
        pas qu'un control schedule. Cette liste rend l'hyperconvergence visible
        sans changer le classement des groupes (inventaire inchangé)."""
        return [n.name for n in self.nodes if n.has_role("control") and n.has_role("worker")]

    @property
    def is_ha_control_plane(self) -> bool:
        """> 1 control-plane → exige un control_plane_lb (VIP), ADR 0047/0055."""
        return len(self.control_nodes) > 1

    @property
    def exposition_mode(self) -> str:
        """Mode d'exposition CANONIQUE (ADR 0020/0071) : gateway | hostport | none.

        `exposition.mode` déclaré (alias `lb-ipam` → `gateway` résolu) prime ; sinon
        défaut PAR TERRAIN (banc Lima → `hostport`, ailleurs → `gateway`, ADR 0071 §6)."""
        declared = self.exposition.get("mode") if isinstance(self.exposition, dict) else None
        if declared:
            return _EXPOSITION_ALIASES.get(declared, declared)
        return _EXPOSITION_DEFAULT.get(self.target_kind, "gateway")

    @property
    def declared_layers(self) -> list[str]:
        """Couches déclarées (ADR 0069). `layers` s'il est posé (il PRIME) ; sinon
        rétrocompat : on dérive du `catalog.profile` (préfixe cumulatif, alias
        déprécié-doux). `base` par défaut. La traduction profil→layers vit dans
        `layers.layers_from_profile` (import LOCAL pour éviter un cycle model↔layers)."""
        if self.layers:
            return list(self.layers)
        from cluster_topology.layers import layers_from_profile

        return layers_from_profile(self.catalog.get("profile", "base"))


def _parse_node(raw: dict[str, Any]) -> Node:
    if "name" not in raw:
        raise TopologyError(f"nœud sans `name` : {raw!r}")
    roles = raw.get("roles") or []
    if not roles:
        raise TopologyError(f"nœud `{raw['name']}` sans `roles`")
    unknown = set(roles) - VALID_ROLES
    if unknown:
        raise TopologyError(
            f"nœud `{raw['name']}` : rôle(s) inconnu(s) {sorted(unknown)} "
            f"(valides : {sorted(VALID_ROLES)})"
        )
    return Node(
        name=raw["name"],
        roles=list(roles),
        ansible_host=raw.get("ansible_host"),
        disks=raw.get("disks"),
    )


def topology_from_dict(data: dict[str, Any]) -> Topology:
    """Construit une Topology depuis un dict (pur, testable sans fichier)."""
    if "nodes" not in data or not data["nodes"]:
        raise TopologyError("topology sans `nodes`")
    nodes = [_parse_node(n) for n in data["nodes"]]
    target_kind = data.get("target_kind", "prod")
    if target_kind not in VALID_TARGET_KINDS:
        raise TopologyError(
            f"target_kind `{target_kind}` invalide (valides : {sorted(VALID_TARGET_KINDS)})"
        )
    topo = Topology(
        catalog=data.get("catalog", {}),
        nodes=nodes,
        network=data.get("network", {}) or {},
        exposition=data.get("exposition", {}) or {},
        storage=data.get("storage", {}) or {},
        hardening=data.get("hardening", {}) or {},
        resources=data.get("resources"),
        target_kind=target_kind,
        layers=list(data.get("layers") or []),  # ADR 0069 ; vide → dérivé du profil
    )
    # Cohérence HA : > 1 CP exige un control_plane_lb déclaré (ADR 0047/0055).
    lb = topo.network.get("control_plane_lb")
    if topo.is_ha_control_plane and not lb:
        raise TopologyError(
            f"{len(topo.control_nodes)} control-planes mais aucun `network.control_plane_lb` "
            "(VIP requise dès > 1 CP — ADR 0047/0055)"
        )
    # Si un control_plane_lb est déclaré, son `mode` doit être connu (sinon le delta
    # d'outillage — kube-vip vs external — n'est pas dérivable, ADR 0047/0055).
    if lb is not None:
        mode = lb.get("mode") if isinstance(lb, dict) else None
        if mode not in VALID_LB_MODES:
            raise TopologyError(
                f"`network.control_plane_lb.mode` = {mode!r} inconnu "
                f"(valides : {sorted(VALID_LB_MODES)} — ADR 0047/0055)"
            )
    # exposition.mode : enum validé si déclaré (ADR 0020/0071). `lb-ipam` est résolu en
    # `gateway` (alias) AVANT validation ; un mode inconnu lève (sinon étiquette morte).
    expo = topo.exposition.get("mode") if isinstance(topo.exposition, dict) else None
    if expo is not None:
        canonical = _EXPOSITION_ALIASES.get(expo, expo)
        if canonical not in VALID_EXPOSITION_MODES:
            raise TopologyError(
                f"`exposition.mode` = {expo!r} inconnu "
                f"(valides : {sorted(VALID_EXPOSITION_MODES)} | alias lb-ipam — ADR 0071)"
            )
    return topo


def load_topology(path: str) -> Topology:
    """Charge un topology.yaml depuis un fichier."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise TopologyError(
            f"{path} : racine YAML attendue = mapping, obtenu {type(data).__name__}"
        )
    return topology_from_dict(data)
