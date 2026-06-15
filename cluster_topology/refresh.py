"""État RÉEL d'une stack, resynchronisé à la demande (`stack refresh`, ADR 0056 §7).

On ne STOCKE aucun state (pas de moteur à état par-dessus k8s — ADR 0056 §7) : on
le LIT du réel (VMs Lima via `limactl`, nœuds via `kubectl`) à chaque appel, comme
`pulumi refresh` resynchronise depuis le provider. Ce module est PUR : il CLASSE un
état déjà collecté (listes de VMs réelles + nœuds k8s réels + nœuds déclarés) en un
verdict lisible ; la COLLECTE (subprocess limactl/kubectl) reste à la façade (ADR 0017).

Le verdict distingue ce que `preview` doit annoncer AVANT d'appliquer :
- VMs de la stack DÉJÀ là (ok) ;
- VMs ORPHELINES (réelles mais hors de la stack active) → à DÉTRUIRE d'abord (le
  banc actuel cp1/cp2/cp3 d'une autre stack en est l'exemple) ;
- VMs MANQUANTES (déclarées mais sans VM réelle) → à créer ;
- nœuds k8s Ready (le cluster tourne-t-il ?).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RefreshState:
    """État réel classé d'une stack (verdict pur, sans I/O)."""

    stack: str
    declared_nodes: list[str] = field(default_factory=list)
    vms_present: list[str] = field(default_factory=list)  # VM réelle ∈ stack
    vms_orphan: list[str] = field(default_factory=list)  # VM réelle ∉ stack → à détruire
    vms_missing: list[str] = field(default_factory=list)  # déclarée, pas de VM → à créer
    nodes_ready: list[str] = field(default_factory=list)  # nœuds k8s Ready

    @property
    def must_destroy_first(self) -> bool:
        """Des VMs orphelines existent → un montage propre exige de les détruire."""
        return bool(self.vms_orphan)

    @property
    def is_empty(self) -> bool:
        """Aucune VM réelle (ni de la stack, ni orpheline) : terrain vierge."""
        return not self.vms_present and not self.vms_orphan


def classify_refresh(
    stack: str,
    declared_nodes: list[str],
    real_vms: list[str],
    ready_nodes: list[str],
) -> RefreshState:
    """Classe l'état réel d'une stack à partir de listes déjà collectées. PUR.

    `declared_nodes` : nœuds de la stack active (control + workers, depuis la topo).
    `real_vms` : noms des VMs Lima EXISTANTES (n'importe quelle stack ; collecté par
    la façade via `limactl list`). `ready_nodes` : nœuds k8s à l'état Ready.

    Une VM réelle est `present` si son nom est déclaré par la stack, sinon `orphan`
    (elle appartient à un autre déploiement — à détruire avant un montage propre).
    Une déclaration sans VM réelle est `missing` (à créer)."""
    declared = set(declared_nodes)
    real = set(real_vms)
    return RefreshState(
        stack=stack,
        declared_nodes=list(declared_nodes),
        vms_present=[v for v in real_vms if v in declared],
        vms_orphan=[v for v in real_vms if v not in declared],
        vms_missing=[n for n in declared_nodes if n not in real],
        nodes_ready=list(ready_nodes),
    )
