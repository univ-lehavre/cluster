"""Garde d'isolation de CIBLE ANSIBLE (ADR 0053) : un montage qui vise le banc ne doit
JAMAIS s'exécuter sur un inventaire de PRODUCTION.

Pourquoi ce module. `cluster next <couche applicative>` lance un playbook via
ansible-runner sur l'inventaire `bootstrap/hosts.yaml`. Cet inventaire est une config
LOCALE non versionnée (ADR 0023) qui, en pratique, porte la PROD. La garde existante
(`_assert_bench_target`) ne valide QUE le KUBECONFIG — or les plays `hosts: cloud`
SSHent sur les nœuds de l'inventaire, un chemin INDÉPENDANT du KUBECONFIG. Un banc
KUBECONFIG + un inventaire prod = mutation de la prod par erreur (faille constatée :
`next dataops` visant le banc a reconfiguré containerd sur les nœuds prod).

Ce module est PUR : il CLASSE un inventaire déjà chargé (dict YAML) + l'intention
(`target_kind` de la topo) en un verdict. La LECTURE du fichier et le REFUS restent à
la façade. Le marqueur de vérité est `target_kind` porté par le groupe `cloud` de
l'inventaire (même marqueur que le rôle audit-log, ADR 0053 (c)) : `prod` côté
production, `lima` côté banc. Défaut prudent : un inventaire SANS marqueur, ou dont les
hôtes ne sont pas tous locaux, est traité comme NON-banc (fail-closed).
"""

from __future__ import annotations

# Marqueurs d'un hôte LOCAL (banc piloté depuis le poste, pas de SSH distant). Un
# inventaire dont TOUS les hôtes distants sont locaux ne peut pas muter une prod.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _inventory_target_kind(inventory: dict) -> str | None:
    """`target_kind` déclaré par l'inventaire (vars du groupe `cloud`), ou None si absent.

    C'est le marqueur de topologie de l'ADR 0053 (c) : `prod` | `lima`. On le lit au
    niveau du groupe `cloud` (où l'inventaire prod et le banc le posent), puis en repli
    dans `all.vars` — sans jamais deviner."""
    for group in ("cloud", "all"):
        node = inventory.get(group)
        if isinstance(node, dict):
            tk = node.get("vars", {}).get("target_kind")
            if tk:
                return str(tk)
    return None


def _remote_hosts(inventory: dict) -> list[str]:
    """Hôtes du groupe `cloud` qui ne sont PAS locaux (→ SSH distant possible).

    Parcourt récursivement les groupes/enfants d'`inventory` à la recherche de blocs
    `hosts:` ; retient les hôtes dont ni le nom ni `ansible_host` ne sont locaux ET dont
    la connexion n'est pas `local`. Liste vide ⇒ l'inventaire ne peut SSHer nulle part."""
    remote: list[str] = []
    seen: set[int] = set()

    def walk(node) -> None:
        if not isinstance(node, dict) or id(node) in seen:
            return
        seen.add(id(node))
        hosts = node.get("hosts")
        if isinstance(hosts, dict):
            for name, attrs in hosts.items():
                attrs = attrs or {}
                if attrs.get("ansible_connection") == "local":
                    continue
                host_ip = str(attrs.get("ansible_host", name))
                if name not in _LOCAL_HOSTS and host_ip not in _LOCAL_HOSTS:
                    remote.append(name)
        for child in (node.get("children") or {}).values():
            walk(child)

    for value in inventory.values():
        walk(value)
    return remote


def classify_inventory_target(inventory: dict, intended_kind: str) -> tuple[bool, str]:
    """L'inventaire est-il SÛR pour l'intention `intended_kind` ? (PUR, ADR 0053).

    Renvoie `(ok, raison)`. Règles, du plus sûr au plus risqué :

    1. Aucun hôte distant (que des `localhost`/connexion locale) → SÛR : rien à SSHer,
       quelle que soit l'intention (les plays `hosts: cloud` n'auraient aucune cible).
    2. L'inventaire déclare `target_kind` ET il == `intended_kind` → SÛR (marqueur ADR
       0053 concordant, comme l'assert du rôle audit-log).
    3. Sinon (marqueur absent, OU marqueur ≠ intention, avec des hôtes distants) →
       REFUSÉ : on ne peut pas prouver que l'inventaire vise la cible voulue, et il
       PEUT SSHer sur des nœuds (potentiellement la prod). Fail-closed.

    Exemple de la faille : intended=`lima` (banc), inventaire `target_kind: prod` +
    hôtes prod (cp1/node1…) → règle 3 → REFUSÉ (ce qui aurait stoppé `next dataops`)."""
    remote = _remote_hosts(inventory)
    if not remote:
        return True, "inventaire local (aucun hôte distant à SSHer)"
    declared = _inventory_target_kind(inventory)
    if declared is not None and declared == intended_kind:
        return True, f"target_kind concordant ({declared})"
    hosts_str = ", ".join(remote[:4]) + ("…" if len(remote) > 4 else "")
    if declared is None:
        return (
            False,
            f"inventaire SANS marqueur target_kind mais avec des hôtes distants "
            f"({hosts_str}) — cible non prouvée",
        )
    return (
        False,
        f"inventaire target_kind={declared} ≠ intention {intended_kind} ; "
        f"hôtes distants ({hosts_str}) — risque de muter la mauvaise cible",
    )
