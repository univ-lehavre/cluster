"""Catalogue d'épreuves + filtrage par la topologie (palier P4, ADR 0056 §8.6).

Un *scénario* (`bench/scenarios/NN-*.sh`) est une **épreuve** passée à un banc
déjà monté — il **requiert** une catégorie, une topologie (mono/multi/agnostique)
et un terrain (SSH hôte, offensif…). L'outil **FILTRE** ce catalogue selon
l'intention déclarée (`topology.yaml` : profil, backend, nombre de nœuds,
target_kind) et liste ce qui est **jouable**. Il n'en LANCE aucun (lancer relève
de P5 / ansible-runner) : la frontière du palier est *décrire et filtrer*.

`EPREUVES` est le **miroir machine** de la table prose
`docs/architecture/matrice-catalogue.md §2` ; la classification destructif /
SSH / offensif reprend `bench/scenarios/run-all.sh` (`is_destructive`,
`needs_ssh`, terrains offensifs ADR 0025). Un test de parité
(tests/test_epreuves.py) casse si l'un dérive de l'autre.

Pur : aucune I/O, aucun subprocess. Le verdict porte sur l'INTENTION (la
topologie déclarée) ; l'état RUNTIME réel (Mailpit câblé, Prometheus déployé)
n'est pas constaté ici — un scénario « jouable » peut encore être *skip* au
lancement (P5).
"""

from __future__ import annotations

from dataclasses import dataclass

from nestor.model import Topology
from nestor.profile import required_profiles

# Terrains particuliers (run-all.sh) : un scénario offensif ne se joue que sur un
# banc jetable, JAMAIS en prod (ADR 0025) ; un scénario SSH/etcdctl exige l'accès
# hôte (hors périmètre d'un simple `topology.yaml`, mais jouable sur un banc).
TERRAIN_AGNOSTIQUE = "—"
TERRAIN_SSH = "ssh"  # SSH hôte / etcdctl / state.sh
TERRAIN_OFFENSIF = "offensif"  # offensif ou chaos host-side (BANC=1, ADR 0025)
TERRAIN_API = "api"  # sonde une API in-cluster (Prometheus/Marquez/Gateway…)

# Topologie requise.
TOPO_AGNOSTIQUE = "agnostique"
TOPO_MONO = "mono-nœud"
TOPO_MULTI = "multi-nœuds"


@dataclass(frozen=True)
class Epreuve:
    """Une épreuve du catalogue. Champs = colonnes de la matrice + classification
    run-all.sh. `profil_min` : le profil cumulatif (ADR 0039) sous lequel les
    briques testées existent ; `backend_req` : 'ceph' si l'épreuve exige Rook-Ceph
    (RGW, réplication), None sinon."""

    num: str
    nom: str
    type: str  # unit | intég | chaos
    categorie: str
    topo_req: str
    terrain: str
    profil_min: str  # base | store | obs | dataops
    backend_req: str | None  # 'ceph' | None


# Catalogue — miroir de matrice-catalogue.md §2 (01-26) + en-têtes 27-29.
# profil_min : base=socle k8s ; store=stockage (Ceph/local-path) ; obs=monitoring ;
# dataops=chaîne DataOps. backend_req='ceph' quand l'épreuve teste une propriété
# propre à Rook-Ceph (RGW objet, rebalance de réplication) qu'un banc local-path
# ne peut pas honorer.
EPREUVES: list[Epreuve] = [
    Epreuve(
        "01",
        "RBD block write-read",
        "unit",
        "stockage",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "store",
        "ceph",  # RBD exige rook-ceph-block-replicated (01-block-rwx-write-read.sh)
    ),
    Epreuve(
        "02",
        "Pod rescheduling (persistance)",
        "intég",
        "stockage",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "store",
        None,
    ),
    Epreuve(
        "03",
        "Perte worker + Ceph HEALTH",
        "chaos",
        "résilience",
        TOPO_MULTI,
        TERRAIN_SSH,
        "store",
        "ceph",
    ),
    Epreuve(
        "04",
        "Perte control plane + snapshot",
        "chaos",
        "résilience",
        TOPO_MONO,
        TERRAIN_SSH,
        "base",
        None,
    ),
    Epreuve(
        "05",
        "Bump réplication pool",
        "intég",
        "stockage",
        TOPO_MULTI,
        TERRAIN_AGNOSTIQUE,
        "store",
        "ceph",
    ),
    Epreuve(
        "06",
        "Object store (RGW) smoke",
        "intég",
        "stockage",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "store",
        "ceph",
    ),
    Epreuve(
        "07",
        "Connectivité Cilium",
        "unit",
        "réseau",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "base",
        None,
    ),
    Epreuve(
        "08",
        "Audit requests/limits",
        "unit",
        "observabilité",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "base",
        None,
    ),
    Epreuve(
        "09", "Restore snapshot etcd", "intég", "résilience", TOPO_MONO, TERRAIN_SSH, "base", None
    ),
    Epreuve(
        "10",
        "Pod Security Admission",
        "unit",
        "sécurité",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "base",
        None,
    ),
    Epreuve(
        "11",
        "NetworkPolicy default-deny",
        "unit",
        "sécurité",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "base",
        None,
    ),
    Epreuve(
        "12",
        "securityContext runtime",
        "unit",
        "sécurité",
        TOPO_AGNOSTIQUE,
        TERRAIN_AGNOSTIQUE,
        "base",
        None,
    ),
    Epreuve(
        "13",
        "Durcissement host/node",
        "unit",
        "sécurité",
        TOPO_AGNOSTIQUE,
        TERRAIN_SSH,
        "base",
        None,
    ),
    Epreuve(
        "14",
        "Chiffrement Cilium + Hubble",
        "unit",
        "sécurité",
        TOPO_MULTI,
        TERRAIN_AGNOSTIQUE,
        "base",
        None,
    ),
    Epreuve(
        "15",
        "Chiffrement at-rest etcd + audit",
        "intég",
        "sécurité",
        TOPO_MONO,
        TERRAIN_SSH,
        "base",
        None,
    ),
    Epreuve(
        "16",
        "Brute-force SSH → fail2ban",
        "intég",
        "sécurité",
        TOPO_AGNOSTIQUE,
        TERRAIN_SSH,
        "base",
        None,
    ),
    Epreuve(
        "17",
        "Évasion pod → PSA rejette",
        "unit",
        "sécurité",
        TOPO_AGNOSTIQUE,
        TERRAIN_OFFENSIF,
        "base",
        None,
    ),
    Epreuve(
        "18",
        "Exfiltration → NetworkPolicy",
        "intég",
        "sécurité",
        TOPO_AGNOSTIQUE,
        TERRAIN_OFFENSIF,
        "base",
        None,
    ),
    Epreuve(
        "19",
        "Chaos perte paquets/partition",
        "chaos",
        "chaos",
        TOPO_MULTI,
        TERRAIN_OFFENSIF,
        "store",
        "ceph",  # éprouve la résilience Ceph (réplica ×3, min_size 2) sous partition réseau
    ),
    Epreuve(
        "20", "Chaos kill pods", "chaos", "chaos", TOPO_AGNOSTIQUE, TERRAIN_OFFENSIF, "base", None
    ),
    Epreuve(
        "21",
        "Chaos saturation CPU/mém",
        "chaos",
        "chaos",
        TOPO_AGNOSTIQUE,
        TERRAIN_OFFENSIF,
        "base",
        None,
    ),
    Epreuve(
        "22",
        "Alerte détecteurs → Mailpit",
        "intég",
        "observabilité",
        TOPO_AGNOSTIQUE,
        TERRAIN_SSH,
        "obs",
        None,
    ),
    Epreuve(
        "23",
        "Marquez OpenLineage",
        "intég",
        "dataops",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "dataops",
        None,
    ),
    Epreuve(
        "24",
        "Prometheus scrape + Grafana up",
        "intég",
        "observabilité",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "obs",
        None,
    ),
    Epreuve(
        "25",
        "PrometheusRule → alerte tirée",
        "intég",
        "observabilité",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "obs",
        None,
    ),
    Epreuve(
        "26",
        "Loki : ingest logs + requête LogQL",
        "intég",
        "observabilité",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "obs",
        None,
    ),
    Epreuve(
        "27",
        "GitOps : push Gitea → déploiement",
        "intég",
        "gitops",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "dataops",
        None,
    ),
    Epreuve(
        "28",
        "Portail : UI atteignables (Gateway)",
        "intég",
        "gitops",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "base",
        None,
    ),
    Epreuve(
        "29",
        "Code-location externe (Dagster)",
        "intég",
        "dataops",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "dataops",
        None,
    ),
    # ha-3cp : survie du control-plane à 1 panne (VIP kube-vip + quorum etcd).
    # chaos/résilience comme 19-21 ; terrain SSH (limactl + etcdctl host-side) ;
    # exige multi-nœuds (3 CP — la topologie ha-3cp ; se SKIP au runtime hors
    # ha-3cp). Local-path (HA ⊥ stockage) → backend_req=None. ADR 0047/0055, #250.
    Epreuve(
        "30",
        "ha-3cp : survie à 1 panne CP (VIP + quorum etcd)",
        "chaos",
        "résilience",
        TOPO_MULTI,
        TERRAIN_SSH,
        "base",
        None,
    ),
    # Contrat d'interface cluster→atlas (ADR 0043) : dérive contract/endpoints
    # et vérifie chaque endpoint (Service + port + réponse). Transversal, agnostique
    # de topologie ; le scénario SKIP par endpoint absent (profil partiel) → profil_min
    # base (jouable dès le socle ; plus le profil est complet, plus d'endpoints sont
    # vérifiés). backend_req=None (lit le contrat, jamais Ceph-obligatoire). #407/0043.
    Epreuve(
        "31",
        "Contrat cluster→atlas : endpoints tenus",
        "intég",
        "gitops",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "base",
        None,
    ),
    # Portail (ADR 0091) : répond, liste les UI réelles, et NE PEUT PAS lire un Secret
    # (RBAC least-privilege). SKIP neutre si le portail n'est pas déployé. base/agnostique
    # (lit le contrat + l'API, indépendant du backend) ; terrain API.
    Epreuve(
        "32",
        "Portail : répond, liste les UI, pas de lecture de Secret",
        "intég",
        "socle",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "base",
        None,
    ),
    # Cache CNPG (ADR 0093) : prouve les PRIMITIVES Postgres du cache partagé des
    # flux atlas (connexion rôle/base cache + UPSERT atomique + pg_advisory_lock),
    # depuis un pod éphémère via psql vers pg-rw.postgres. L'adaptateur (SQL) vit
    # côté atlas (frontière §5 ADR). dataops (exige le Cluster CNPG du profil
    # dataops) ; terrain api (sonde la base in-cluster) ; topo-agnostique.
    # backend_req=None : preuve e2e sur local-path mono-nœud (ADR 0085). SKIP
    # neutre si la base cache / le Secret pg-role-cache est absent. #150.
    Epreuve(
        "33",
        "Cache CNPG : connexion + UPSERT atomique + advisory lock",
        "intég",
        "dataops",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "dataops",
        None,
    ),
    Epreuve(
        "34",
        "Build → digest → GitOps : déploiement par @sha256 immuable",
        "intég",
        "gitops",
        TOPO_AGNOSTIQUE,
        TERRAIN_API,
        "dataops",
        None,
    ),
]


def _profil_couvre(profil_min: str, profil_topo: str) -> bool:
    """Le profil déclaré couvre-t-il `profil_min` ? (inclusion cumulative ADR 0039).

    `dataops` couvre base/store/obs/dataops ; `base` ne couvre que base.
    """
    return profil_min in required_profiles(profil_topo)


def _topo_satisfait(topo_req: str, n_control: int, n_worker: int) -> bool:
    """La topologie déclarée satisfait-elle l'exigence (mono/multi/agnostique) ?

    multi-nœuds = au moins 2 nœuds au total ; mono-nœud = jouable dès 1 nœud
    (un banc plus grand peut aussi rejouer un scénario mono-nœud).
    """
    if topo_req == TOPO_MULTI:
        return (n_control + n_worker) >= 2
    return True  # agnostique et mono-nœud : jouables sur tout banc ≥ 1 nœud


def epreuve_jouable(ep: Epreuve, topo: Topology) -> tuple[bool, str | None]:
    """Verdict (jouable, raison-d'exclusion) d'une épreuve face à une topologie.

    On filtre sur l'INTENTION déclarée — profil cumulatif, backend de stockage,
    nombre de nœuds, et l'interdit prod des épreuves offensives (ADR 0025). On NE
    constate PAS l'état réel du cluster (ça, c'est le lancement, P5).
    """
    profil_topo = topo.catalog.get("profile", "base")
    backend = topo.storage.get("backend", "local-path")
    n_control = len(topo.control_nodes)
    n_worker = len(topo.worker_nodes)

    if ep.terrain == TERRAIN_OFFENSIF and topo.target_kind == "prod":
        return False, "offensif — interdit hors banc jetable (ADR 0025)"
    if not _profil_couvre(ep.profil_min, profil_topo):
        return False, f"profil `{profil_topo}` ne couvre pas `{ep.profil_min}` (ADR 0039)"
    if ep.backend_req == "ceph" and backend != "ceph":
        return False, f"exige le backend ceph (déclaré : `{backend}`)"
    if not _topo_satisfait(ep.topo_req, n_control, n_worker):
        return (
            False,
            f"exige une topologie {ep.topo_req} (déclaré : {n_control + n_worker} nœud(s))",
        )
    return True, None


def filter_epreuves(topo: Topology) -> tuple[list[Epreuve], list[tuple[Epreuve, str]]]:
    """Partitionne le catalogue : (jouables, [(exclue, raison)]) pour une topologie."""
    jouables: list[Epreuve] = []
    exclues: list[tuple[Epreuve, str]] = []
    for ep in EPREUVES:
        ok, raison = epreuve_jouable(ep, topo)
        if ok:
            jouables.append(ep)
        else:
            exclues.append((ep, raison or "non jouable"))
    return jouables, exclues
