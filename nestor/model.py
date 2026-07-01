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

# `TopologyError` est défini dans le module-feuille `errors` (sans dépendance) et
# ré-exporté ici : `layers`/`profile` l'importent sans tirer `model` (casse le cycle
# py/cyclic-import). `from nestor.model import TopologyError` reste valide.
from nestor.errors import TopologyError

VALID_ROLES = {"control", "worker", "storage"}
# `target_kind` = la CRITICITÉ (la garde d'isolation, ADR 0099) : `bench` (parc jetable,
# on peut tout casser) | `prod` (parc réel, mutation encadrée). NE PAS confondre avec la
# TECHNO d'infra (`catalog.terrain` : local/cloud/baremetal) ni avec le TRANSPORT de
# connexion (`lima`=limactl / `ssh`, dérivé en aval). `bench` a remplacé l'ancien `lima`
# (qui nommait l'outil, pas la sûreté).
VALID_TARGET_KINDS = {"prod", "bench"}
# Modes du point d'entrée HA devant les CP (ADR 0047/0055). kube-vip-arp =
# bare-metal/local (pod statique, annonce ARP) ; kube-vip-lb = via LB-IPAM ;
# external = LB fourni par le terrain (cloud, ADR 0040).
VALID_LB_MODES = {"kube-vip-arp", "kube-vip-lb", "external"}
# Modes d'exposition applicative (ADR 0092, qui SUPERSEDE 0071). `nodeport` = exposition
# L4 par un port du nœud (`http://<IP-nœud>:<port>`, Cilium-eBPF, ZÉRO DNS / ZÉRO LB-IPAM /
# ZÉRO Gateway) — c'est le mode CANONIQUE et le DÉFAUT depuis ADR 0092. `gateway` = ancien
# monde : bordure L7 Cilium en hostNetwork (Envoy bind 80/443 sur l'IP du nœud, SNI/TLS de
# bordure) — conservé comme mode LEGACY DÉCLARABLE explicitement (rétrocompat), mais ce
# n'est PLUS le défaut. `none` = ClusterIP seuls (accès par port-forward). Alias :
# `hostport` (« le hostPort L4 sur l'IP du nœud ») → `nodeport` (c'est le mécanisme même de
# l'ADR 0092) ; `lb-ipam` → `gateway` (lb-ipam reste l'ancien monde L7, inchangé).
VALID_EXPOSITION_MODES = {"nodeport", "gateway", "none"}
_EXPOSITION_ALIASES = {"hostport": "nodeport", "lb-ipam": "gateway"}
# Défaut d'exposition GLOBAL (ADR 0092) : `nodeport` partout. Le L4 sur le port du nœud ne
# réclame ni DNS, ni plage LB-IPAM, ni interface L2 annonçable → aussi reproductible sur le
# banc Lima que sur une VM publique mono-NIC (plus de défaut par terrain, plus de défaut
# gateway). `gateway` ne s'arme que si la topologie le DÉCLARE explicitement.
_EXPOSITION_DEFAULT = "nodeport"


# Ressources VM par défaut (LOT 8, ADR 0097 §3) — remontent les VM_CPUS/VM_MEMORY/VM_DISK
# que `bench/lima/run-phases.sh:117-125` lisait de l'ENV. Désormais LE YAML porte ces
# valeurs (`resources:` global + surcharge optionnelle par node) ; nestor les LIT du YAML
# et le moteur (path.py) les passe au provisioning (`lima_render_node` bash garde le RENDU,
# Python décide les VALEURS). Défauts = ceux du bash (4 vCPU, 12 GiB, 40 GiB — la chaîne
# MLOps complète sature 2 vCPU / 8 GiB, et 20 GiB de disque déclenche DiskPressure ; cf.
# le commentaire dimensionnant de run-phases.sh). PLUS de lecture VM_* côté Python.
_DEFAULT_CPUS = 4
_DEFAULT_MEMORY = "12GiB"
_DEFAULT_DISK = "40GiB"

# Défauts de taille des disques bruts Ceph (ADR 0102 volet C — ex-HDD_SIZE/BLOCKDB_SIZE
# de run-phases.sh). `data` = OSD (10 GiB) ; `metadata` = block.db NVMe (5 GiB).
_DEFAULT_DATA_DISK_SIZE = "10GiB"
_DEFAULT_META_DISK_SIZE = "5GiB"
VALID_DISK_ROLES = {"data", "metadata"}


@dataclass(frozen=True)
class NodeResources:
    """Dimensionnement de la VM (banc Lima) : cpus / mémoire / disque SYSTÈME (LOT 8,
    ADR 0097 §3). Remplace les env `VM_CPUS`/`VM_MEMORY`/`VM_DISK`.

    `disk` = taille du **disque système** de la VM (le `vda` : OS + containerd + images +
    logs), TOUJOURS présent, un par VM. À NE PAS confondre avec `Node.disks` (les disques
    BRUTS additionnels `vd[b-z]` pour Ceph — cf. `DiskSpec`). Deux notions orthogonales :
    ici on dimensionne la VM ; là on attache du stockage brut.

    Bloc `resources:` du YAML = défaut GLOBAL (niveau topologie) ; un node le surcharge
    champ par champ via `nodes[].resources`. IMMUABLE — dérivé à la lecture, pas muté."""

    cpus: int = _DEFAULT_CPUS
    memory: str = _DEFAULT_MEMORY
    disk: str = _DEFAULT_DISK  # disque SYSTÈME (vda), ≠ Node.disks (bruts Ceph)


@dataclass(frozen=True)
class DiskSpec:
    """Un disque BRUT ADDITIONNEL déclaré d'un nœud (ADR 0102 volet C) : `name` = device
    attendu dans la VM (`vdb`, `vdc`… — jamais `vda`, réservé au disque système), `size`,
    `role` (`data` OSD | `metadata` block.db). La topo les DÉCLARE → le provisioning les
    crée et les attache (fin de `WITH_CEPH`). IMMUABLE.

    ≠ `NodeResources.disk` (le disque SYSTÈME `vda`, dimensionnement de la VM) : ici c'est
    du stockage BRUT pour Ceph, pas l'OS. ≠ `nodeside.Disk` (la SONDE lsblk : ce que le nœud
    EXPOSE réellement) — ici, la DÉCLARATION de ce qu'on veut."""

    name: str
    size: str = _DEFAULT_DATA_DISK_SIZE
    role: str = "data"


@dataclass
class Node:
    name: str
    roles: list[str]
    ansible_host: str | None = None
    disks: list[DiskSpec] | None = None
    # Surcharge des ressources VM PROPRE à ce node (LOT 8) : un dict partiel
    # (`{cpus, memory, disk}` — chaque champ optionnel) qui prime sur le `resources:`
    # global. None → le node hérite intégralement du défaut global de la topologie.
    resources: dict[str, Any] | None = None

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
    # ── Blocs de config remontés de l'ENV vers le YAML (LOT 8, ADR 0097 §3) ──────
    # Chaque bloc regroupe par DOMAINE les paramètres qui étaient des variables d'env
    # éparses du bash (run-phases.sh) ou du Python. nestor LIT ces blocs du YAML, plus
    # de l'env. Tous optionnels — un défaut documenté par accesseur quand absent.
    #   ceph    : {block_device, hdd_glob, data_device_glob, nvme_block_device, min_hdd}
    #             (ex-CEPH_BLOCK_DEVICE/CEPH_HDD_GLOB/… de run-phases.sh:139-143).
    #   ha      : {vip, iface} (ex-HA_VIP/HA_VIP_IFACE de run-phases.sh:1632-1642).
    #   gitea   : {org, repo, ns, admin_user, admin_email, svc, api,
    #             org_cluster, repo_apps, org_atlas, repo_atlas} (ex-GITEA_*).
    #   cilium  : {cluster_name, cluster_id} (ex-CILIUM_CLUSTER_*).
    #   atlas   : {repo_dir, citation_revision, citation_image_digest,
    #             citation_image_name, expected_cluster} (ex-ATLAS_REPO_DIR/CITATION_*/
    #             EXPECTED_CLUSTER du seed prod).
    #   portal  : {contract, listen_port, seuil_jours} (ex-PORTAL_*/SEUIL_JOURS Python).
    ceph: dict[str, Any] = field(default_factory=dict)
    ha: dict[str, Any] = field(default_factory=dict)
    gitea: dict[str, Any] = field(default_factory=dict)
    cilium: dict[str, Any] = field(default_factory=dict)
    atlas: dict[str, Any] = field(default_factory=dict)
    portal: dict[str, Any] = field(default_factory=dict)
    target_kind: str = "prod"
    # Chemin du kubeconfig de la cible (ADR 0090) — UNIQUEMENT pour la PROD. QUI décide :
    #   • BANC   → nestor IMPOSE : le provisioning génère `.kubeconfigs/banc.config`
    #              (phase cni, ADR 0102 volet B — le banc EST la stack `banc`) et
    #              `_bench_kubeconfig` le trouve seul → laisser ce champ à None (le
    #              déclarer serait redondant).
    #   • PROD   → l'UTILISATEUR DÉCLARE ici la cible que nestor ne peut PAS deviner :
    #              `~/.kube/<stack>.config`, HORS dépôt (credentials réels, jamais commités).
    #              SOURCE DE VÉRITÉ pour viser une prod en LECTURE (`preview`/état réel) sans
    #              dépendre du contexte ambigu du poste.
    #   • Toujours → `export KUBECONFIG=…` surcharge tout (intention explicite, ADR 0053/0065).
    # None → résolution par défaut (banc si présent, sinon /dev/null — JAMAIS ~/.kube/config).
    kubeconfig: str | None = None
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
        """Mode d'exposition CANONIQUE (ADR 0092, supersede 0071) : `nodeport` | `gateway`
        | `none`.

        `exposition.mode` déclaré (alias résolus : `hostport` → `nodeport`, `lb-ipam` →
        `gateway`) prime ; sinon défaut GLOBAL `nodeport` (exposition L4 sur le port du
        nœud, reproductible partout sans DNS ni LB-IPAM — ADR 0092). `gateway` (ancien
        monde L7 en hostNetwork) reste DÉCLARABLE pour rétrocompat, mais n'est plus le
        défaut."""
        declared = self.exposition.get("mode") if isinstance(self.exposition, dict) else None
        if declared:
            return _EXPOSITION_ALIASES.get(declared, declared)
        return _EXPOSITION_DEFAULT

    @property
    def default_resources(self) -> NodeResources:
        """Ressources VM par DÉFAUT de la topologie (LOT 8, ADR 0097 §3).

        Lit le bloc `resources:` GLOBAL du YAML (ex-VM_CPUS/VM_MEMORY/VM_DISK de l'env).
        Champs absents → défauts du bash (4 vCPU / 12 GiB / 40 GiB). PUR : aucune lecture
        d'environnement — la source unique est le YAML."""
        return _resources_from(self.resources or {}, NodeResources())

    def node_resources(self, node_name: str) -> NodeResources:
        """Ressources EFFECTIVES d'un node : défaut global SURCHARGÉ par `nodes[].resources`.

        C'est ce que le moteur (path.py) passera à `lima_render_node` — Python décide les
        VALEURS depuis le YAML, le bash garde le rendu du template. Le défaut global
        (`default_resources`) sert de base ; la surcharge per-node prime champ par champ
        (un node sans `resources:` hérite intégralement du global). Lève `TopologyError`
        si le node est inconnu (fail-closed : on ne dimensionne pas une VM inexistante)."""
        for n in self.nodes:
            if n.name == node_name:
                return _resources_from(n.resources or {}, self.default_resources)
        raise TopologyError(f"node `{node_name}` inconnu dans la topologie")

    @property
    def declared_layers(self) -> list[str]:
        """Couches déclarées (ADR 0069). `layers` s'il est posé (il PRIME) ; sinon
        rétrocompat : on dérive du `catalog.profile` (préfixe cumulatif, alias
        déprécié-doux). `base` par défaut. La traduction profil→layers vit dans
        `layers.layers_from_profile` (import LOCAL pour éviter un cycle model↔layers)."""
        if self.layers:
            return list(self.layers)
        from nestor.layers import layers_from_profile

        return layers_from_profile(self.catalog.get("profile", "base"))


def _resources_from(raw: dict[str, Any], base: NodeResources) -> NodeResources:
    """Fusionne un dict `resources` PARTIEL sur une base (PUR, LOT 8).

    Chaque champ absent du dict hérite de `base` (le défaut global, ou les défauts
    constants pour le global lui-même). `cpus` est COERCÉ en int (le YAML peut le
    porter en chaîne) ; lève `TopologyError` s'il n'est pas convertible."""
    cpus = raw.get("cpus", base.cpus)
    try:
        cpus = int(cpus)
    except (TypeError, ValueError) as exc:
        raise TopologyError(f"`resources.cpus` = {cpus!r} non entier") from exc
    return NodeResources(
        cpus=cpus,
        memory=str(raw.get("memory", base.memory)),
        disk=str(raw.get("disk", base.disk)),
    )


def _parse_disk(raw: Any, node_name: str) -> DiskSpec:
    """Un item `disks[]` → `DiskSpec` (ADR 0102 volet C). Accepte un objet
    `{name, size?, role?}` (forme canonique) OU une string nue `vdb` (rétrocompat :
    taille/rôle par défaut). Lève `TopologyError` sur item mal formé / rôle inconnu.
    Défaut de taille dérivé du rôle (data 10 GiB, metadata 5 GiB)."""
    if isinstance(raw, str):
        return DiskSpec(name=raw)
    if not isinstance(raw, dict) or "name" not in raw:
        raise TopologyError(f"nœud `{node_name}` : disque mal formé {raw!r} (attendu {{name, …}})")
    role = str(raw.get("role", "data"))
    if role not in VALID_DISK_ROLES:
        raise TopologyError(
            f"nœud `{node_name}` : disque `{raw['name']}` rôle `{role}` inconnu "
            f"(valides : {sorted(VALID_DISK_ROLES)})"
        )
    default_size = _DEFAULT_META_DISK_SIZE if role == "metadata" else _DEFAULT_DATA_DISK_SIZE
    return DiskSpec(name=str(raw["name"]), size=str(raw.get("size", default_size)), role=role)


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
    raw_disks = raw.get("disks")
    disks = [_parse_disk(d, raw["name"]) for d in raw_disks] if raw_disks else None
    return Node(
        name=raw["name"],
        roles=list(roles),
        ansible_host=raw.get("ansible_host"),
        disks=disks,
        resources=raw.get("resources"),  # LOT 8 : surcharge VM per-node (None → global)
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
        # LOT 8 (ADR 0097 §3) : blocs de config remontés de l'env vers le YAML. Tous
        # optionnels — un `{}` quand absent, l'accesseur de domaine porte le défaut.
        ceph=data.get("ceph", {}) or {},
        ha=data.get("ha", {}) or {},
        gitea=data.get("gitea", {}) or {},
        cilium=data.get("cilium", {}) or {},
        atlas=data.get("atlas", {}) or {},
        portal=data.get("portal", {}) or {},
        target_kind=target_kind,
        kubeconfig=data.get("kubeconfig"),  # ADR 0090 ; None → résolution par défaut
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
    # exposition.mode : enum validé si déclaré (ADR 0092, supersede 0071). Les alias sont
    # résolus AVANT validation (`hostport` → `nodeport`, `lb-ipam` → `gateway`) ; un mode
    # inconnu lève (sinon étiquette morte).
    expo = topo.exposition.get("mode") if isinstance(topo.exposition, dict) else None
    if expo is not None:
        canonical = _EXPOSITION_ALIASES.get(expo, expo)
        if canonical not in VALID_EXPOSITION_MODES:
            raise TopologyError(
                f"`exposition.mode` = {expo!r} inconnu "
                f"(valides : {sorted(VALID_EXPOSITION_MODES)} ; "
                f"alias hostport → nodeport, lb-ipam → gateway — ADR 0092)"
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
