"""Contextes kubectl nommés — REMPLACE `nestor env` (LOT 8, ADR 0097 §3).

`nestor env` imprimait `export KUBECONFIG=<banc>` à `eval` dans le shell : il INCARNAIT
le paramétrage-par-variable-d'environnement que l'ADR 0097 §3 abolit. À sa place, `nestor`
maintient des **contextes nommés dans `~/.kube/config`** (un par topologie : `banc`,
`dirqual`…), dérivés du champ `kubeconfig:` du YAML. L'opérateur branche son `kubectl`
par le mécanisme STANDARD k8s — `kubectl --context <topo> …` ou `kubectl config
use-context <topo>` — SANS aucune variable d'environnement (cohérent ADR 0090).

Découpage (ADR 0017/0049) :
- la LOGIQUE est PURE : `context_plan(topo)` décide CE QU'IL FAUT poser (nom de contexte,
  kubeconfig source, le `kubectl config set-context` à lancer) — testable sans kubectl ;
- l'I/O (lancer `kubectl`, artefact OK du dépôt) est ISOLÉE dans `apply_context`, qui
  prend un `runner` injectable (stub en test). On NE réécrit JAMAIS `~/.kube/config` à la
  main (un parseur YAML maison casserait les merges/credentials) — kubectl est le seul à
  le muter.

KUBECONFIG reste l'EXCEPTION documentée (ADR 0097 §3) : sa sémantique d'override (« intention
explicite assumée », ADR 0065) est conservée AILLEURS (gardes d'isolation). Ce module ne
touche pas à KUBECONFIG ; il pose un contexte dans le fichier kubeconfig par défaut.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass


class ContextError(RuntimeError):
    """Le contexte n'a pas pu être posé (topologie sans cible, kubectl en échec)."""


@dataclass(frozen=True)
class ContextPlan:
    """Ce qu'il faut faire pour qu'un contexte nommé `name` existe (PUR).

    - `name` : nom du contexte = nom de la topologie (`banc`, `dirqual`…).
    - `kubeconfig` : chemin du kubeconfig SOURCE de la cible (champ `kubeconfig:` du YAML
      pour la prod, expansé ; kubeconfig du banc pour une topo lima). C'est de LUI qu'on
      dérive le cluster/user à câbler dans le contexte.
    - `cluster`, `user` : noms du cluster/user que le contexte référence. On dérive du
      nom de la topologie (`<name>` / `<name>-admin`) pour des identifiants UNIQUES
      stables (deux topos fusionnées ne s'écrasent pas), parité `kubeconfig.rewrite`.
    """

    name: str
    kubeconfig: str
    cluster: str
    user: str

    def set_context_argv(self) -> list[str]:
        """`kubectl config set-context` IDEMPOTENT qui crée/met à jour le contexte (PUR).

        Vise le kubeconfig source (`--kubeconfig`) pour lire/écrire le contexte AU BON
        endroit (le fichier de la cible — banc ou prod), pas un `~/.kube/config` ambigu.
        `set-context` est create-or-update : rejoué, il ne casse rien (idempotent)."""
        return [
            "kubectl",
            "config",
            "set-context",
            self.name,
            f"--cluster={self.cluster}",
            f"--user={self.user}",
            f"--kubeconfig={self.kubeconfig}",
        ]


def context_plan(
    name: str,
    *,
    kubeconfig: str | None,
    target_kind: str,
    bench_kubeconfig: str,
) -> ContextPlan:
    """Décide le contexte à poser pour la topologie `name` (PUR, LOT 8).

    - PROD (`target_kind != "bench"`) : la cible est le `kubeconfig:` DÉCLARÉ (ADR 0090).
      Absent → `ContextError` (on ne devine pas une cible prod ; `stack select` complète
      déjà le champ). `~` est expansé.
    - BANC (`target_kind == "bench"`) : la cible est le kubeconfig du banc Lima
      (`bench_kubeconfig`, écrit par le montage). On ne vérifie PAS son existence ici
      (logique pure) — l'I/O `apply_context` le fera.

    Les noms cluster/user dérivent du nom de la topologie (uniques, parité
    `nestor.kubeconfig._rename_identifiers`)."""
    if target_kind == "bench":
        source = bench_kubeconfig
    elif kubeconfig:
        source = os.path.expanduser(kubeconfig)
    else:
        raise ContextError(
            f"topologie « {name} » sans `kubeconfig:` — impossible de poser un contexte "
            "prod nommé (ADR 0090). La déclarer (ex. `kubeconfig: ~/.kube/<topo>.config`)."
        )
    return ContextPlan(name=name, kubeconfig=source, cluster=name, user=f"{name}-admin")


# Type du runner injecté : prend l'argv et rend un objet à `.returncode`/`.stderr`
# (parité subprocess.CompletedProcess). Stub en test, `subprocess.run` en prod.
Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Lance `kubectl` (artefact OK, ADR 0049) borné, capture rc/stderr. I/O isolée."""
    return subprocess.run(  # noqa: S603 — argv construit (ContextPlan), pas d'entrée shell
        argv, check=False, capture_output=True, text=True, timeout=15
    )


def apply_context(plan: ContextPlan, *, runner: Runner | None = None) -> str:
    """Pose/MET À JOUR le contexte nommé via `kubectl config set-context` (I/O isolée).

    `runner` injecté (stub en test, jamais kubectl réel sous unittest). Lève `ContextError`
    si le kubeconfig source est absent (banc non monté → rien à câbler) ou si kubectl
    échoue. Renvoie le nom du contexte posé (pour le message de la façade)."""
    run = runner or _default_runner
    # Le kubeconfig source doit exister : `set-context` y lit/écrit. Un banc non monté
    # (`/dev/null` ou fichier absent) → on refuse plutôt que de poser un contexte mort.
    if plan.kubeconfig != os.devnull and not os.path.exists(plan.kubeconfig):
        raise ContextError(
            f"kubeconfig cible absent ({plan.kubeconfig}) — monter la cible d'abord "
            f"(`nestor up`) avant de poser le contexte « {plan.name} »."
        )
    proc = run(plan.set_context_argv())
    if proc.returncode != 0:
        raise ContextError(
            f"`kubectl config set-context {plan.name}` a échoué "
            f"(rc={proc.returncode}) : {(proc.stderr or '').strip()}"
        )
    return plan.name
