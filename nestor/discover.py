"""Reconstruction d'un `topology.yaml` depuis un cluster réel (`nestor discover`, ADR 0074).

INVERSE de `generate` : à partir de sondes du réel (fournies par la façade —
kubectl/SSH = I/O bash, ADR 0049), assemble (1) une topologie déclarative, (2) la
liste de l'INCONNU (ce que le catalogue ne mappe pas — jamais ignoré, ADR 0052),
(3) un bilan de SANTÉ. Logique PURE ici (dict en entrée, dict en sortie) : aucun
kubectl, testable sans cluster. La façade `cmd_discover` orchestre les sondes.

Le catalogue des couches CONNUES est `LAYER_NAMESPACES`/`LAYER_DEPLOYMENTS` (miroir
de `_LAYER_SIGNAL` côté façade) : un namespace/Deployment qui n'y figure pas est
classé `unknown` (ex. un ns/pod posé à la main hors modèle).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Namespaces que le catalogue CONNAÎT (mappés à une couche). Tout ns hors de cette
# table → unknown (ADR 0074 §2). Miroir de _LAYER_SIGNAL + ns d'infra socle.
KNOWN_NAMESPACES: dict[str, str] = {
    "kube-system": "socle",  # k8s + Cilium + metrics-server
    "kube-public": "socle",
    "kube-node-lease": "socle",
    "default": "socle",
    "local-path-storage": "storage-simple",
    "monitoring": "monitoring",
    "argocd": "gitops",
    "gitea": "gitops",
    "dagster": "dataops",
    "marquez": "dataops",
    "postgres": "dataops",
    "cnpg-system": "dataops",
    "registry": "dataops",
    "rook-ceph": "ceph",
    "s3": "storage",  # SeaweedFS (backing S3 local-path)
    "mail": "obs",  # mailpit (alerte)
}

# Préfixes de groupes de CRD → plateforme installée (le PIVOT, ADR 0074 §1). La
# présence de la CRD est le signal le plus fiable « telle plateforme tourne ».
KNOWN_CRD_GROUPS: dict[str, str] = {
    "cilium.io": "cni-cilium",
    "ceph.rook.io": "ceph",
    "objectbucket.io": "ceph",
    "postgresql.cnpg.io": "dataops",
    "argoproj.io": "gitops",
    "gateway.networking.k8s.io": "exposition-gateway",
    "monitoring.coreos.com": "monitoring",
}

# StorageClass → backend (ADR 0074 §1). Un provisioner `rook-ceph` ⇒ ceph ;
# `rancher.io/local-path` ⇒ local-path. La sonde lit `kubectl get storageclass`.
_CEPH_SC_MARKERS = ("rook-ceph", "ceph.com", "rbd.csi.ceph.com", "cephfs.csi.ceph.com")
_LOCALPATH_SC_MARKERS = ("rancher.io/local-path", "local-path")


def provisioner_is_ceph(provisioner: str) -> bool:
    """True si `provisioner` désigne une StorageClass Ceph (Rook), par ses marqueurs (PUR).

    Source UNIQUE du critère « cette SC appartient à Ceph » — partagée par `detect_backend`
    (sonde de backend, ADR 0074) ET le retrait cluster-scoped de `remove ceph` (une SC est
    découvrable SANS ambiguïté par son provisioner, contrairement aux CRD)."""
    return any(m in provisioner for m in _CEPH_SC_MARKERS)


@dataclass
class Unknown:
    """Une ressource du réel que le catalogue ne mappe pas (ADR 0074 §2)."""

    kind: str
    name: str
    namespace: str | None = None


@dataclass
class HealthItem:
    """Verdict de santé d'une dimension : sain | dégradé | absent (ADR 0074 §3)."""

    dimension: str
    verdict: str  # "sain" | "dégradé" | "absent"
    detail: str = ""


@dataclass
class DiscoverResult:
    """Sortie de discover : topologie reconstruite + inconnu + bilan de santé."""

    topology: dict
    unknown: list[Unknown] = field(default_factory=list)
    health: list[HealthItem] = field(default_factory=list)


def classify_namespaces(namespaces: list[str]) -> tuple[set[str], list[Unknown]]:
    """Partitionne les namespaces : (couches connues présentes, ns inconnus).

    Un ns mappé par KNOWN_NAMESPACES → sa couche ; sinon → Unknown (ADR 0074 §2).
    PUR : liste de noms en entrée."""
    layers: set[str] = set()
    unknown: list[Unknown] = []
    for ns in namespaces:
        couche = KNOWN_NAMESPACES.get(ns)
        if couche is None:
            unknown.append(Unknown("Namespace", ns))
        elif couche not in ("socle", "storage", "obs"):
            # `socle`/`storage`/`obs` ne sont pas des couches de queue addressables
            # telles quelles (storage→storage-simple via backend) ; on ne les remonte
            # pas comme `layers`. Les vraies couches applicatives, si.
            layers.add(couche)
    return layers, unknown


def detect_platforms(crd_groups: list[str]) -> set[str]:
    """Plateformes installées, déduites des groupes de CRD présents (PUR, ADR 0074 §1).

    Le pivot : une CRD `cilium.io`/`ceph.rook.io`/… ⇒ la plateforme tourne. On match
    par SUFFIXE de groupe (ex. `ciliumnetworkpolicies.cilium.io` → `cilium.io`)."""
    platforms: set[str] = set()
    for grp in crd_groups:
        for known, platform in KNOWN_CRD_GROUPS.items():
            if grp == known or grp.endswith("." + known):
                platforms.add(platform)
    return platforms


def build_topology(
    *,
    nodes: list[dict],
    layers: list[str],
    backend: str,
    exposition: str,
    topology_name: str = "discovered",
    target_kind: str = "prod",
) -> dict:
    """Assemble un dict `topology.yaml` VALIDE depuis le réel sondé (PUR, ADR 0074 §4).

    `nodes` : [{name, roles}] (rôles dérivés des labels par la façade). `layers` :
    couches applicatives présentes (set ordonné). `backend`/`exposition` : dérivés du
    réel. Le résultat passe `topology_from_dict` (clés génériques, ADR 0023)."""
    topo: dict = {
        "catalog": {"topology": topology_name, "status": "cible"},
        "nodes": nodes,
        "storage": {"backend": backend},
        "target_kind": target_kind,
    }
    if layers:
        topo["layers"] = sorted(layers)
    if exposition and exposition != "gateway":
        # `gateway` = mode de référence implicite (ADR 0020) ; on n'écrit `exposition`
        # que s'il diffère (ex. `none`), pour la lisibilité du fichier reconstruit.
        topo["exposition"] = {"mode": exposition}
    return topo


def detect_backend(storageclass_provisioners: list[str]) -> str:
    """Backend de stockage déduit des provisioners de StorageClass (PUR, ADR 0074 §1).

    Un provisioner ceph (`rook-ceph`/`*.csi.ceph.com`) ⇒ `ceph` ; `local-path` ⇒
    `local-path` ; rien de reconnu ⇒ `local-path` (défaut du socle léger). Ceph prime
    si les deux coexistent (un cluster ceph garde souvent local-path en secours)."""
    if any(provisioner_is_ceph(p) for p in storageclass_provisioners):
        return "ceph"
    has_local = any(any(m in p for m in _LOCALPATH_SC_MARKERS) for p in storageclass_provisioners)
    if has_local:
        return "local-path"
    return "local-path"


def classify_backend_drift(
    declared_backend: str, storageclass_provisioners: list[str]
) -> str | None:
    """Backend RÉEL s'il CONTREDIT le déclaré, sinon None (PUR, #356 / ADR 0046).

    `detect_backend` retombe sur `local-path` qu'il VOIE une SC local-path OU rien — donc
    inutilisable pour un drift (on confondrait « cluster vide » et « vraie local-path »).
    Ici on ne signale QUE sur un signal RECONNU qui contredit la déclaration :

    - des SC ceph présentes (`rook-ceph`…) alors que `declared` ≠ ceph → renvoie `ceph`
      (le cas vécu : backend basculé ceph→local-path, rook-ceph résiduel orphelin) ;
    - des SC local-path SANS aucune SC ceph alors que `declared` == ceph → `local-path`.

    Aucune SC reconnue (cluster vide/injoignable) → None (pas de drift affirmable). Le
    backend réel == déclaré → None. Read-only ; la façade `preview` AVERTIT sur non-None."""
    has_ceph = any(any(m in p for m in _CEPH_SC_MARKERS) for p in storageclass_provisioners)
    has_local = any(any(m in p for m in _LOCALPATH_SC_MARKERS) for p in storageclass_provisioners)
    if has_ceph and declared_backend != "ceph":
        return "ceph"
    if has_local and not has_ceph and declared_backend == "ceph":
        return "local-path"
    return None


def classify_digest_drift(
    declared_digests: dict[str, str], deployed_digests: dict[str, str]
) -> list[tuple[str, str, str]]:
    """Code-locations dont le digest DÉPLOYÉ contredit le digest DÉCLARÉ (PUR, ADR 0046/0095).

    Le seed (`_seed_do_prod`) substitue le digest de la topo dans l'overlay poussé vers
    Gitea `cluster/apps` → Argo déploie. Mais un BUILD MANUEL node-side (`nestor next` sur
    la couche image) écrit le nouveau digest dans la TOPO sans re-seeder — et le signal de
    couche `gitops-seed-citation` (présence de l'Application, pas le digest) tient le
    déploiement « à-jour ». Le manifeste garde alors l'ANCIEN digest silencieusement.
    Ce comparateur rend la divergence VISIBLE (la façade `preview` AVERTIT).

    `declared_digests` : {code-location: digest} de la topo (`atlas.code_locations[].image_digest`),
    filtré aux entrées qui EN portent un (None/absent = rien à comparer, ex. mediawatch overlay).
    `deployed_digests` : {code-location: digest} lu du cluster (image du Deployment).

    Renvoie la liste `(name, declared, deployed)` des divergences — vide si tout concorde
    (ou si un côté manque : on ne signale QUE deux digests présents qui DIFFÈRENT, pas une
    absence). Read-only ; PUR (aucune I/O) → testable sans cluster."""
    drifts: list[tuple[str, str, str]] = []
    for name, declared in declared_digests.items():
        if not declared:
            continue
        deployed = deployed_digests.get(name)
        if deployed and deployed != declared:
            drifts.append((name, declared, deployed))
    return drifts


def detect_exposition(*, gateways_present: bool, crd_groups: list[str]) -> str:
    """Mode d'exposition constaté (PUR, ADR 0074 §1, aligné ADR 0020 « gateway unique »).

    Depuis la décision du mode d'exposition UNIQUE (`gateway` via hostNetwork, ADR
    0020/0071), il n'y a plus de mode `hostport` distinct à reconstruire : soit la
    bordure Gateway tourne (`Gateway` posé OU CRD `gateway.networking.k8s.io`
    installée) → `gateway`, soit rien → `none`. Inverse de la dérivation
    `exposition_mode`."""
    if gateways_present or "exposition-gateway" in detect_platforms(crd_groups):
        return "gateway"
    return "none"


# Verdicts de santé (ADR 0074 §3). Miroir prose de health-classify.sh côté façade.
SAIN = "sain"
DEGRADE = "dégradé"
ABSENT = "absent"


def classify_health(
    *,
    nodes_ready: int,
    nodes_total: int,
    workloads_degraded: list[str] | None = None,
    pvc_pending: int = 0,
    pvc_total: int = 0,
    osds_up: int | None = None,
    osds_expected: int | None = None,
    cr_status: dict[str, str] | None = None,
) -> list[HealthItem]:
    """Bilan de santé PUR par dimension (ADR 0074 §3) : nœuds, workloads, stockage, CRs.

    Agrège des SONDES déjà réduites (la façade lit health-classify.sh / gates.py /
    les `.status` des CRs — pas d'exec, [[k8s-exec-vs-k8s-info-gate]]). Chaque
    dimension → un HealthItem (`sain`/`dégradé`/`absent`). Read-only, aucune mutation."""
    items: list[HealthItem] = []

    # nœuds — Ready vs total
    if nodes_total == 0:
        items.append(HealthItem("nœuds", ABSENT, "aucun nœud sondé"))
    elif nodes_ready == nodes_total:
        items.append(HealthItem("nœuds", SAIN, f"{nodes_ready}/{nodes_total} Ready"))
    else:
        items.append(HealthItem("nœuds", DEGRADE, f"{nodes_ready}/{nodes_total} Ready"))

    # workloads — un layer présent mais en CrashLoop/Pending est DÉGRADÉ (ADR 0074 §3)
    degraded = workloads_degraded or []
    if degraded:
        items.append(HealthItem("workloads", DEGRADE, ", ".join(sorted(degraded))))
    else:
        items.append(HealthItem("workloads", SAIN, "aucun workload en échec"))

    # stockage — PVC Bound (gate_pvc_bound) ; OSD up si backend ceph (gate_osds_up)
    if pvc_total == 0:
        items.append(HealthItem("stockage (PVC)", ABSENT, "aucune PVC"))
    elif pvc_pending == 0:
        items.append(HealthItem("stockage (PVC)", SAIN, f"{pvc_total} Bound"))
    else:
        items.append(HealthItem("stockage (PVC)", DEGRADE, f"{pvc_pending}/{pvc_total} Pending"))
    if osds_expected is not None and osds_expected > 0:
        up = osds_up or 0
        verdict = SAIN if up >= osds_expected else DEGRADE
        items.append(HealthItem("stockage (OSD)", verdict, f"{up}/{osds_expected} up"))

    # CR d'opérateur — santé lue sur le .status du CR (CephCluster, CNPG Cluster…)
    for name, status in sorted((cr_status or {}).items()):
        ok = status.upper() in ("HEALTH_OK", "READY", "TRUE", "RUNNING")
        items.append(HealthItem(f"CR {name}", SAIN if ok else DEGRADE, status))

    return items


def assemble(
    *,
    nodes: list[dict],
    namespaces: list[str],
    crd_groups: list[str],
    storageclass_provisioners: list[str],
    gateways_present: bool,
    extra_unknown: list[Unknown] | None = None,
    health: list[HealthItem] | None = None,
    topology_name: str = "discovered",
    target_kind: str = "prod",
) -> DiscoverResult:
    """Orchestrateur PUR (ADR 0074 §1+2+6) : compose la topologie reconstruite +
    l'inconnu + le bilan de santé depuis des sondes déjà réduites par la façade.

    Croise les signaux (ADR 0074 §1) : couches via namespaces ET plateformes (CRDs),
    backend via StorageClass, exposition via Gateway/CRD. L'inconnu (§2) agrège les
    ns hors catalogue et tout `extra_unknown` repéré par la façade (Deployments/
    StorageClasses non mappés). N'invente rien : ce qui n'est pas sondé n'est pas écrit."""
    layers_from_ns, unknown_ns = classify_namespaces(namespaces)
    platforms = detect_platforms(crd_groups)
    # Une plateforme = une couche applicative (sauf cni/exposition qui sont du socle/réseau).
    layers_from_platforms = {
        p for p in platforms if p not in ("cni-cilium", "exposition-gateway", "ceph")
    }
    layers = layers_from_ns | layers_from_platforms

    backend = detect_backend(storageclass_provisioners)
    exposition = detect_exposition(gateways_present=gateways_present, crd_groups=crd_groups)

    topo = build_topology(
        nodes=nodes,
        layers=sorted(layers),
        backend=backend,
        exposition=exposition,
        topology_name=topology_name,
        target_kind=target_kind,
    )
    unknown = unknown_ns + list(extra_unknown or [])
    return DiscoverResult(topology=topo, unknown=unknown, health=list(health or []))
