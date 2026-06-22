"""Cible prod de `nestor` : résolution kubeconfig, confirmation, rapatriement (ADR 0090).

Logique PURE (testable sans cluster ni I/O) du ciblage d'un cluster PROD :
- quel kubeconfig viser (priorité KUBECONFIG exporté → `kubeconfig:` topo → défaut) ;
- faut-il rapatrier (kubeconfig absent) et avec quels paramètres ;
- le message de CONFIRMATION de la cible (endpoint + nœuds) avant toute action.

L'I/O (prompt `input`, `_fetch_kubeconfig`, kubectl) vit dans `scripts/topology.py` ;
ici, on ne fait que DÉCIDER et FORMATER. Garde-fou ADR 0053/0084 : ces fonctions ne
mutent rien — elles cadrent une LECTURE prod sûre.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def default_kubeconfig_path(stack: str) -> str:
    """Chemin par défaut du kubeconfig d'une stack (convention ADR 0090) :
    `~/.kube/<stack>.config`, HORS dépôt (credentials réels jamais commités)."""
    return os.path.join("~", ".kube", f"{stack}.config")


def resolve_kubeconfig(*, env_kubeconfig: str | None, declared: str | None, stack: str) -> str:
    """Chemin du kubeconfig prod à viser, par priorité (ADR 0090) :

    1. `env_kubeconfig` (KUBECONFIG exporté, intention explicite de l'opérateur) ;
    2. `declared` (champ `kubeconfig:` de la topologie) ;
    3. défaut conventionnel `~/.kube/<stack>.config`.

    Toujours un chemin (jamais None) : la cible prod est explicite. `~` non expansé
    (l'appelant expanduser au moment de l'I/O)."""
    if env_kubeconfig:
        return env_kubeconfig
    if declared:
        return declared
    return default_kubeconfig_path(stack)


@dataclass(frozen=True)
class TargetConfirmation:
    """Ce que `nestor` affiche pour faire confirmer la cible prod (ADR 0090)."""

    stack: str
    endpoint: str | None  # endpoint API lu du kubeconfig (None si illisible)
    nodes: list[str]  # nœuds Ready vus (vide si injoignable)

    @property
    def reachable(self) -> bool:
        """La cible répond-elle (au moins un nœud vu) ?"""
        return bool(self.nodes)

    def prompt(self) -> str:
        """Message de confirmation interactif (avant toute action prod)."""
        ep = self.endpoint or "endpoint inconnu"
        noeuds = ", ".join(self.nodes) if self.nodes else "aucun nœud joignable"
        return f"Cible prod « {self.stack} » → {ep} ({noeuds}). Confirmer ? [y/N] "


def needs_repatriation(*, kubeconfig_path: str, reaches_api: bool) -> bool:
    """`True` si le kubeconfig doit être rapatrié : fichier absent OU n'atteint pas
    l'API. `reaches_api` est sondé par l'appelant (I/O). Fail-safe : si on n'est pas
    sûr que la cible répond, on propose le rapatriement plutôt que d'échouer sec."""
    return not os.path.exists(os.path.expanduser(kubeconfig_path)) or not reaches_api


def is_affirmative(answer: str) -> bool:
    """Réponse utilisateur affirmative (confirmation). Strict : seul `y`/`yes`/`o`/`oui`
    (insensible à la casse, trim) vaut oui — défaut N (tout le reste = non)."""
    return answer.strip().lower() in {"y", "yes", "o", "oui"}


def add_kubeconfig_field(source: str, kubeconfig: str) -> str:
    """Ajoute (ou met à jour) la ligne top-level `kubeconfig: <chemin>` dans le TEXTE
    d'une topologie, PUR (préserve le reste — commentaires, ordre, ADR 0076 §4).

    - Une ligne `kubeconfig:` existante (même commentée `# kubeconfig:`) est REMPLACÉE
      par la valeur active (idempotent : ré-appeler ne duplique pas).
    - Sinon, la ligne est AJOUTÉE en fin de fichier (champ top-level, non imbriqué).
    Rend le texte modifié (newline final garanti)."""
    line = f"kubeconfig: {kubeconfig}"
    out: list[str] = []
    replaced = False
    for raw in source.splitlines():
        stripped = raw.lstrip()
        # remplace une déclaration active OU un placeholder commenté `# kubeconfig:`
        if not replaced and (
            stripped.startswith("kubeconfig:") or stripped.startswith("# kubeconfig:")
        ):
            out.append(line)
            replaced = True
        else:
            out.append(raw)
    if not replaced:
        if out and out[-1].strip():
            out.append("")  # une ligne vide de séparation si le fichier ne finit pas par un blanc
        out.append(line)
    return "\n".join(out).rstrip("\n") + "\n"
