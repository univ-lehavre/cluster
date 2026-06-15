"""Dérivation du scaling applicatif (`cluster scale`, ADR 0072).

Logique PURE (aucune I/O, aucun kubectl) : à partir du nombre de **workers Ready**
(lu par la façade) et d'une **allowlist** de workloads scalables, calcule la cible
de replicas par workload. Le scaling est une capacité **runtime** (le bon nombre
dépend de l'état réel), distincte du cycle déclaratif `up`/`next` (ADR 0072) — d'où
une COMMANDE, pas une couche du DAG.

Garde-fous (ADR 0072 §4), tous portés ici en pur :
  - **allowlist explicite** : on ne scale QUE les Deployments stateless déclarés
    (jamais « tous les Deployments ») ; StatefulSets/CNPG/opérateurs/control-plane
    sont hors table par construction ;
  - **clamp** : `replicas = max(1, min(workers_ready, max_replicas))` — jamais 0
    (service coupé), jamais plus de replicas que de nœuds pour les exécuter ;
  - **ArgoCD** : un workload réconcilié par ArgoCD est REFUSÉ (un `kubectl scale`
    serait écrasé au prochain sync → drift éphémère, pas un résultat reproductible,
    ADR 0046/0052). La façade marque le workload `argocd_managed` ; on l'exclut ici.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Workload:
    """Un workload scalable de l'allowlist. `name`/`namespace` = le Deployment ciblé ;
    `max_replicas` = plafond (borne la cible, ADR 0072 §4)."""

    name: str
    namespace: str
    max_replicas: int


# Allowlist (ADR 0072 §3) : Deployments STATELESS à replicas pilotables, vérifiés
# présents dans le catalogue (platform/*). On EXCLUT par construction StatefulSets
# (loki, argocd), clusters d'opérateur (CNPG instances:3), singletons, control-plane.
# Plafond = 3 par défaut (au-delà, rendement applicatif marginal sur un banc).
SCALABLE_WORKLOADS: tuple[Workload, ...] = (
    Workload("gitea", "gitea", max_replicas=3),
    Workload("registry", "registry", max_replicas=3),
    Workload("mailpit", "mail", max_replicas=2),
)


@dataclass(frozen=True)
class ScalePlan:
    """Plan de scaling d'UN workload : cible dérivée + verdict d'action."""

    workload: Workload
    target: int  # replicas cible (clamp appliqué)
    skipped: str | None = None  # raison de NON-action (ArgoCD managé…), sinon None

    @property
    def actionable(self) -> bool:
        return self.skipped is None


def target_replicas(workers_ready: int, max_replicas: int) -> int:
    """Cible de replicas (PUR) : `max(1, min(workers_ready, max_replicas))` (ADR 0072).

    Jamais 0 (un service ne se coupe pas par scaling), jamais > workers Ready (pas de
    pod Pending faute de nœud), jamais > plafond du workload."""
    return max(1, min(workers_ready, max_replicas))


def plan_scale(workers_ready: int, argocd_managed: frozenset[str] = frozenset()) -> list[ScalePlan]:
    """Plan de scaling de l'allowlist (PUR). `workers_ready` : capacité d'exécution
    réelle (workers purs + hyperconvergés schedulables, fournie par la façade).
    `argocd_managed` : noms de workloads réconciliés par ArgoCD → REFUSÉS (ADR 0046).

    Renvoie un ScalePlan par workload de l'allowlist (target + verdict)."""
    plans: list[ScalePlan] = []
    for wl in SCALABLE_WORKLOADS:
        if wl.name in argocd_managed:
            plans.append(
                ScalePlan(
                    wl,
                    target=target_replicas(workers_ready, wl.max_replicas),
                    skipped="managé par ArgoCD (un scale direct serait écrasé au sync — ADR 0046)",
                )
            )
        else:
            plans.append(ScalePlan(wl, target=target_replicas(workers_ready, wl.max_replicas)))
    return plans
