"""Dérivation de profil (palier P2, ADR 0056 §2 / ADR 0039).

Un `profile` déclaré dans topology.yaml est une **intention de haut niveau** ;
l'outil en DÉDUIT, par des fonctions PURES :

  1. les **briques requises**, par inclusion cumulative `base ⊂ metrics ⊂ store ⊂
     obs ⊂ dataops` (ADR 0039/0068) — déclarer `dataops` exige metrics + store +
     obs + base, dans l'ordre (graphe de dépendances) ;
  2. les **paramètres fins dérivés** du backend de stockage (storageClass,
     backing S3, endpoint, ceph_osd_expected) — ce que `run-phases.sh` calcule
     aujourd'hui en bash et passe en `-e` de run. L'outil reproduit CES MÊMES
     valeurs (invariant P2 : parité avec le bash, pas un fichier byte-exact —
     le banc ne versionne aucun group_vars de profil, tout part en `-e`).

Aucune I/O ici : tout dérive d'une Topology (déjà chargée). Testé par
tests/test_nestor.py (ADR 0017).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nestor.errors import TopologyError

if TYPE_CHECKING:  # `Topology` n'est utilisé qu'en annotation (différée) → pas de cycle
    from nestor.model import Topology

# ── Inclusion cumulative des profils (ADR 0039) ─────────────────────────────
# Chaque profil inclut les précédents. L'ordre EST le graphe de dépendances de
# déploiement (un store avant l'obs qui le consomme, etc.).
PROFILE_CHAIN = ["base", "metrics", "store", "obs", "dataops"]

# Briques (phases) qu'apporte CHAQUE niveau, au-delà du précédent (ADR 0039 table).
# `metrics` (ADR 0068) : metrics-server seul, sans dépendance stockage → placé AVANT
# `store` ; `obs` en hérite (le monitoring suppose l'API ressources présente).
PROFILE_BRICKS = {
    "base": ["bootstrap"],
    "metrics": ["metrics-server"],  # API kubectl top (ADR 0068)
    "store": ["storage"],  # local-path OU ceph+sc+datalake (selon storage.backend)
    "obs": ["monitoring"],
    "dataops": ["dataops"],
}


def required_profiles(profile: str) -> list[str]:
    """Chaîne cumulative jusqu'à `profile` inclus, dans l'ordre de déploiement.

    `dataops` → ['base', 'store', 'obs', 'dataops'] (ADR 0039 inclusion).
    """
    if profile not in PROFILE_CHAIN:
        raise TopologyError(
            f"profile `{profile}` inconnu "
            f"(valides : {PROFILE_CHAIN}, inclusion cumulative ADR 0039)"
        )
    idx = PROFILE_CHAIN.index(profile)
    return PROFILE_CHAIN[: idx + 1]


def consumes_storage(profile: str) -> bool:
    """Le profil pose-t-il une couche de STOCKAGE ? (brique `storage` ∈ `store`).

    `base` = Kubernetes + CRI (containerd) + CNI (Cilium), SANS stockage (ADR 0039 :
    `storage` est rattaché à `store`, pas à `base`). Un profil ≥ store consomme du
    stockage. Sert à ne montrer le backend que là où il est ACTIF (preview/VOULU)."""
    return "store" in required_profiles(profile)


# ── Dimensions fines dérivées du backend de stockage (run-phases.sh) ────────
# Le bash dérive ces valeurs de WITH_CEPH ; on les centralise comme source de
# vérité unique de la dérivation (mêmes valeurs, mêmes clés).
_STORAGE_PARAMS = {
    "ceph": {
        "storage_class": "rook-ceph-block-replicated",
        "s3_backing": "rgw",
        "s3_endpoint": "http://rook-ceph-rgw-datalake.rook-ceph:80",
        "argocd_apply_gateway": True,
    },
    "local-path": {
        "storage_class": "local-path",
        "s3_backing": "seaweedfs",
        "s3_endpoint": "http://seaweedfs.s3.svc.cluster.local:8333",
        "argocd_apply_gateway": False,
    },
}


def storage_params(backend: str) -> dict:
    """Paramètres fins (storageClass/backing/endpoint/gateway) du backend.

    Reproduit la dérivation `if WITH_CEPH` de run-phases.sh (dataops/gitops).
    """
    if backend not in _STORAGE_PARAMS:
        raise TopologyError(
            f"storage.backend `{backend}` inconnu (valides : {sorted(_STORAGE_PARAMS)})"
        )
    return dict(_STORAGE_PARAMS[backend])


def derive_osd_expected(topo: Topology) -> int | None:
    """Nombre d'OSD attendus = #nœuds-stockage × #disques data (banc/prod Ceph).

    Dérivé uniquement si backend=ceph ET les disques sont déclarés (banc) ou un
    `osd_expected` explicite est posé. Renvoie None si non dérivable (prod
    générique : le défaut du rôle / la valeur réelle de hosts.yaml gitignoré
    s'appliquent — la valeur réelle 47 est dérivée-du-terrain, jamais générée).
    """
    if topo.storage.get("backend") != "ceph":
        return None
    explicit = topo.storage.get("osd_expected")
    if explicit is not None:
        return int(explicit)
    disks_per_node = topo.storage.get("disks_per_node")
    if disks_per_node is None:
        return None
    storage_nodes = [n for n in topo.nodes if n.has_role("storage")]
    if not storage_nodes:
        # hyperconvergence : à défaut de rôle `storage` explicite, tout nœud
        # worker/control porte des OSD (ADR 0007). On compte les nœuds non vides.
        storage_nodes = topo.nodes
    return len(storage_nodes) * int(disks_per_node)


def derive_run_params(topo: Topology) -> dict:
    """Le faisceau de paramètres dérivés qu'un déploiement consomme (= les `-e`
    que run-phases.sh calcule en bash). Source de vérité unique de la dérivation.

    Invariant P2 : pour un profil/backend donné, ces valeurs == celles du bash.
    """
    backend = topo.storage.get("backend", "local-path")
    params = storage_params(backend)
    sc = params["storage_class"]
    out = {
        "profiles": required_profiles(topo.catalog.get("profile", "base")),
        "storage_backend": backend,
        # storageClass : même valeur consommée par chaque brique (dataops,
        # monitoring, gitops) — le bash la passe sous des clés distinctes.
        "registry_storage_class": sc,
        "cnpg_storage_class": sc,
        "monitoring_storage_class": sc,
        "loki_storage_class": sc,
        "gitea_storage_class": sc,
        # backing S3 (CNPG + Loki) et endpoint — MÊME backing pour les deux
        # consommateurs (parité run-phases.sh:1035/1153 qui passe les deux jeux de
        # clés). SANS `loki_s3_backing`, le play monitoring retombe sur le défaut
        # `rgw` (when: …| default('rgw')) → SeaweedFS SKIPPÉ en local-path → Loki
        # casse (S3 RGW inexistant). Cf. bootstrap/monitoring.yaml tag seaweedfs.
        "cnpg_s3_backing": params["s3_backing"],
        "cnpg_s3_endpoint": params["s3_endpoint"],
        "loki_s3_backing": params["s3_backing"],
        "loki_s3_endpoint": params["s3_endpoint"],
        # MLflow (layer autonome, ADR 0082) consomme le MÊME backing S3 (artefact
        # store) que Loki/CNPG : rgw (banc Ceph/prod) ou seaweedfs (banc léger).
        # SANS ces clés, platform-mlflow retombe sur le défaut `rgw` → OBC sur un
        # CRD objectbucketclaim ABSENT en local-path → échec (vécu au banc léger).
        "mlflow_s3_backing": params["s3_backing"],
        "mlflow_s3_endpoint": params["s3_endpoint"],
        "argocd_apply_gateway": params["argocd_apply_gateway"],
    }
    osd = derive_osd_expected(topo)
    if osd is not None:
        out["ceph_osd_expected"] = osd
    # Émetteur OpenLineage jetable (preuve e2e dataops_chain_emit_and_verify) : le banc Lima
    # build l'image `dagster-openlineage-emit:dev` au play dataops (parité run-phases.sh:1031,
    # `build_emitter_image=true` INCONDITIONNEL au banc). La PROD ne build PAS cet émetteur e2e
    # (image jetable de validation, pas un livrable). Sans ce flag, le hook e2e lèverait sur un
    # ImagePullBackOff (image absente du registry). Gardé au target_kind bench.
    if topo.target_kind == "bench":
        out["build_emitter_image"] = "true"
    return out


# Défauts banc Lima du wipe node-side Ceph (virtio-blk → /dev/vd* : vda = OS, vd[b-d] =
# data HDD, vde = NVMe block.db). En PROD les devices DIFFÈRENT (sd*/nvme*) → la topo les
# DÉCLARE via `ceph.{nvme_block_device,data_device_glob}` (model.py). Ce sont les ex-valeurs
# CODÉES de phase_rollback (rollback-lib.sh) ; on les DÉRIVE désormais (jamais en dur).
_CEPH_WIPE_DEFAULTS = {"nvme_block_device": "/dev/vde", "data_device_glob": "/dev/vd[b-d]"}


def ceph_wipe_env(topo: Topology, *, skip_reboot: bool = True) -> dict[str, str]:
    """Variables d'env du wipe node-side Ceph (`storage/ceph/cleanup.sh`), DÉRIVÉES de la
    topo (PUR). `ceph.nvme_block_device`/`ceph.data_device_glob` si déclarés, sinon les
    défauts banc Lima. `SKIP_REBOOT=1` par défaut (le wipe d'un rollback ne reboote pas —
    on re-monte derrière ; le reboot du cleanup prod est un autre geste). Aucune I/O."""
    ceph = topo.ceph or {}
    nvme = ceph.get("nvme_block_device") or _CEPH_WIPE_DEFAULTS["nvme_block_device"]
    data_glob = ceph.get("data_device_glob") or _CEPH_WIPE_DEFAULTS["data_device_glob"]
    env = {"NVME_BLOCK_DEVICE": str(nvme), "DATA_DEVICE_GLOB": str(data_glob)}
    if skip_reboot:
        env["SKIP_REBOOT"] = "1"
    return env
