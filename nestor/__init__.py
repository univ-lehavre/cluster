"""nestor — outil déclaratif des topologies (ADR 0056).

`topology.yaml` est la source de vérité unique d'une topologie ; ce paquet en
DÉRIVE, SANS ÉTAT, les entrées que les outils consomment déjà (inventaire
Ansible aujourd'hui ; group_vars de profil et table de nœuds Lima ensuite).
Ansible reste le moteur de convergence (ADR 0056 §7) — l'outil ne réimplémente
jamais la convergence ni un état réconcilié.

Paliers P0-P2 (plan-modele-declaratif) : modéliser (`topologies/socle.example.yaml`) ;
générer les DEUX inventaires BYTE-IDENTIQUES à l'existant — prod
(`bootstrap/hosts.example.yaml`) et banc Lima (sortie de `write_inventory`,
bench/lima/lib.sh) ; DÉRIVER le profil (inclusion cumulative ADR 0039 + faisceau
`-e` à parité bash : `derive_run_params`, ceph_osd_expected, etc.). La logique
(chargement, dérivation, rendu) est pure et testée (tests/test_nestor.py,
ADR 0017). La FAÇADE CLI/CI qui expose cette surface (generate/validate/status/
diff) relève de P3 et vit dans `scripts/topology.py` (façade fine, hors paquet).
"""

from nestor.discover import (
    DiscoverResult,
    Unknown,
    assemble,
    classify_health,
    classify_namespaces,
    detect_backend,
    detect_exposition,
    detect_platforms,
)
from nestor.epreuves import EPREUVES, Epreuve, filter_epreuves
from nestor.facts import parse_facts
from nestor.gates import (
    GateError,
    GateResult,
    gate_nodes_ready,
    gate_osds_up,
    gate_pvc_bound,
)
from nestor.generator import render_lima_inventory, render_prod_inventory
from nestor.history import Run, load_runs, verdict_for_run
from nestor.kube_context import (
    ContextError,
    ContextPlan,
    apply_context,
    context_plan,
)
from nestor.layers import layers_from_profile, phase_deps, resolve_layers
from nestor.metrics import RunMetrics, format_metrics, metrics_of
from nestor.model import NodeResources, Topology, TopologyError, load_topology
from nestor.plan import (
    KNOWN_TARGETS,
    PlanError,
    PlanState,
    Suggestion,
    compute_plan_state,
    default_target,
    diff_phases,
    expected_phase_sequence,
    installable_now,
    observed_done_phases,
    phase_label,
    phase_playbook,
    suggest_next,
)
from nestor.portal import (
    Entry,
    Observed,
    View,
    build_view,
    secret_command,
)
from nestor.prod_target import (
    TargetConfirmation,
    add_kubeconfig_field,
    default_kubeconfig_path,
    is_affirmative,
    needs_repatriation,
    resolve_kubeconfig,
)
from nestor.profile import ceph_wipe_env, consumes_storage, derive_run_params
from nestor.refresh import RefreshState, classify_refresh
from nestor.roundtrip import (
    RemoveResult,
    RoundtripResult,
    run_remove,
    run_roundtrip,
)
from nestor.scaffold import (
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
from nestor.seed import (
    SeedConfig,
    SeedError,
    SeedGuardRefused,
    SeedResult,
    citation_image_ref,
    run_seed,
    seed_steps,
)

__all__ = [
    "Topology",
    "TopologyError",
    "load_topology",
    "NodeResources",
    "render_prod_inventory",
    "render_lima_inventory",
    "derive_run_params",
    "ceph_wipe_env",
    "consumes_storage",
    "Epreuve",
    "EPREUVES",
    "filter_epreuves",
    "DiscoverResult",
    "Unknown",
    "assemble",
    "classify_health",
    "classify_namespaces",
    "detect_backend",
    "detect_exposition",
    "detect_platforms",
    "parse_facts",
    "GateError",
    "GateResult",
    "gate_pvc_bound",
    "gate_nodes_ready",
    "gate_osds_up",
    "Run",
    "load_runs",
    "verdict_for_run",
    "Suggestion",
    "PlanError",
    "PlanState",
    "KNOWN_TARGETS",
    "compute_plan_state",
    "default_target",
    "diff_phases",
    "expected_phase_sequence",
    "installable_now",
    "layers_from_profile",
    "observed_done_phases",
    "phase_deps",
    "phase_label",
    "phase_playbook",
    "resolve_layers",
    "suggest_next",
    "RunMetrics",
    "metrics_of",
    "format_metrics",
    "RoundtripResult",
    "run_roundtrip",
    "RemoveResult",
    "run_remove",
    "RefreshState",
    "classify_refresh",
    "InitPlan",
    "Question",
    "QUESTIONS",
    "QUESTION_LB_MODE",
    "ScaffoldError",
    "build_topology_dict",
    "catalog_entry",
    "plan_init",
    "validate_name",
    # prod_target (ADR 0090) : ciblage/confirmation/rapatriement kubeconfig prod
    "TargetConfirmation",
    "add_kubeconfig_field",
    "default_kubeconfig_path",
    "is_affirmative",
    "needs_repatriation",
    "resolve_kubeconfig",
    # portal (ADR 0091) : croisement contrat ↔ état observé pour le portail d'accès UI
    "build_view",
    "secret_command",
    "Entry",
    "Observed",
    "View",
    # kube_context (LOT 8, ADR 0097 §3) : contextes kubectl nommés (remplace `nestor env`)
    "ContextError",
    "ContextPlan",
    "apply_context",
    "context_plan",
    # seed (LOT 8, ADR 0097 §2/§3) : seed des données post-bootstrap (gardes banc/prod)
    "SeedConfig",
    "SeedError",
    "SeedGuardRefused",
    "SeedResult",
    "citation_image_ref",
    "run_seed",
    "seed_steps",
]
