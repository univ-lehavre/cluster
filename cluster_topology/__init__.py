"""cluster_topology — outil déclaratif des topologies (ADR 0056).

`topology.yaml` est la source de vérité unique d'une topologie ; ce paquet en
DÉRIVE, SANS ÉTAT, les entrées que les outils consomment déjà (inventaire
Ansible aujourd'hui ; group_vars de profil et table de nœuds Lima ensuite).
Ansible reste le moteur de convergence (ADR 0056 §7) — l'outil ne réimplémente
jamais la convergence ni un état réconcilié.

Paliers P0-P2 (plan-modele-declaratif) : modéliser (`topologies/socle.example.yaml`) ;
générer les DEUX inventaires BYTE-IDENTIQUES à l'existant — prod
(`bootstrap/hosts.example.yaml`) et banc Lima (sortie de `write_inventory`,
test/lima/lib.sh) ; DÉRIVER le profil (inclusion cumulative ADR 0039 + faisceau
`-e` à parité bash : `derive_run_params`, ceph_osd_expected, etc.). La logique
(chargement, dérivation, rendu) est pure et testée (tests/test_cluster_topology.py,
ADR 0017). La FAÇADE CLI/CI qui expose cette surface (generate/validate/status/
diff) relève de P3 et vit dans `scripts/topology.py` (façade fine, hors paquet).
"""

from cluster_topology.epreuves import EPREUVES, Epreuve, filter_epreuves
from cluster_topology.generator import render_lima_inventory, render_prod_inventory
from cluster_topology.history import Run, load_runs, verdict_for_run
from cluster_topology.metrics import RunMetrics, format_metrics, metrics_of
from cluster_topology.model import Topology, TopologyError, load_topology
from cluster_topology.plan import (
    KNOWN_TARGETS,
    PlanError,
    Suggestion,
    default_target,
    expected_phase_sequence,
    suggest_next,
)
from cluster_topology.profile import derive_run_params
from cluster_topology.roundtrip import RoundtripResult, run_roundtrip
from cluster_topology.scaffold import (
    QUESTION_LB_MODE,
    QUESTIONS,
    InitPlan,
    Question,
    ScaffoldError,
    build_topology_dict,
    catalog_entry,
    plan_init,
    validate_name,
)

__all__ = [
    "Topology",
    "TopologyError",
    "load_topology",
    "render_prod_inventory",
    "render_lima_inventory",
    "derive_run_params",
    "Epreuve",
    "EPREUVES",
    "filter_epreuves",
    "Run",
    "load_runs",
    "verdict_for_run",
    "Suggestion",
    "PlanError",
    "KNOWN_TARGETS",
    "default_target",
    "expected_phase_sequence",
    "suggest_next",
    "RunMetrics",
    "metrics_of",
    "format_metrics",
    "RoundtripResult",
    "run_roundtrip",
    "InitPlan",
    "Question",
    "QUESTIONS",
    "QUESTION_LB_MODE",
    "ScaffoldError",
    "build_topology_dict",
    "catalog_entry",
    "plan_init",
    "validate_name",
]
