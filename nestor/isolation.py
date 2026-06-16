"""Garde d'isolation de CIBLE ANSIBLE (ADR 0053) : un montage qui vise le banc ne doit
JAMAIS s'exécuter sur un inventaire de PRODUCTION.

Pourquoi ce module. `nestor next <couche applicative>` lance un playbook via
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

from dataclasses import dataclass

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


# ── Résolution d'une CIBLE node-side depuis l'inventaire (ADR 0081, socle node_exec) ────
# Le MÊME inventaire qui sert la garde d'isolation (ci-dessus) sert à résoudre, pour un
# nœud logique, COMMENT l'atteindre : transport (limactl pour le banc Lima, SSH pour la
# prod) + hôte + user + args SSH. Source UNIQUE (pas de 2e liste de nœuds, ADR 0053/0081).
# PUR : la façade lit le YAML et exécute ; ici on ne fait que CLASSER un dict déjà chargé.


@dataclass(frozen=True)
class NodeTarget:
    """Comment atteindre un nœud (PUR) : transport + coordonnées, pour la brique node_exec."""

    node: str
    transport: str  # "lima" (limactl shell) | "ssh" (ssh direct)
    host: str  # ansible_host (lima-<vm> en banc ; IP/hostname en prod) ; repli = nom du nœud
    user: str | None = None  # ansible_user (lima | debian…) — None si non déclaré
    ssh_args: str | None = None  # ansible_ssh_common_args (ex. -F ~/.lima/<vm>/ssh.config)


class IsolationError(ValueError):
    """Nœud introuvable dans l'inventaire, ou inventaire sans cible résoluble."""


def _find_host_attrs(inventory: dict, node: str) -> dict | None:
    """Attributs (`ansible_host`/`ansible_user`…) du nœud `node`, cherchés dans tout l'arbre
    de groupes (`hosts:` à n'importe quel niveau). None si le nœud n'existe pas (PUR)."""
    found: dict | None = None
    seen: set[int] = set()

    def walk(grp) -> None:
        nonlocal found
        if found is not None or not isinstance(grp, dict) or id(grp) in seen:
            return
        seen.add(id(grp))
        hosts = grp.get("hosts")
        if isinstance(hosts, dict) and node in hosts:
            found = hosts[node] or {}
            return
        for child in (grp.get("children") or {}).values():
            walk(child)

    for value in inventory.values():
        walk(value)
    return found


def resolve_node_target(inventory: dict, node: str) -> NodeTarget:
    """Résout `node` → `NodeTarget` depuis l'inventaire (PUR, ADR 0081).

    Le transport est DÉRIVÉ du `target_kind` de l'inventaire : `lima` → `limactl shell`
    (le banc n'utilise pas SSH brut), sinon `ssh` direct. Coordonnées prises sur l'hôte
    (`ansible_host`/`ansible_user`/`ansible_ssh_common_args`) ; `user` remonte en repli des
    vars du groupe `cloud`/`all` (où l'inventaire pose `ansible_user`). Lève `IsolationError`
    si le nœud est absent (fail-closed : on ne devine pas une cible)."""
    attrs = _find_host_attrs(inventory, node)
    if attrs is None:
        raise IsolationError(f"nœud `{node}` absent de l'inventaire")
    transport = "lima" if _inventory_target_kind(inventory) == "lima" else "ssh"
    user = attrs.get("ansible_user") or _group_var(inventory, "ansible_user")
    # En LIMA, `limactl shell` attend le NOM D'INSTANCE = le nom logique du nœud (`node1`).
    # `ansible_host` (ex. `lima-node1`) est le hostname SSH résolu par ~/.lima/<vm>/ssh.config,
    # PAS le nom d'instance — `limactl shell lima-node1` échoue (« instance does not exist »).
    # En SSH (prod), le host est bien `ansible_host` (IP/hostname joignable). Prouvé au banc.
    host = node if transport == "lima" else str(attrs.get("ansible_host", node))
    return NodeTarget(
        node=node,
        transport=transport,
        host=host,
        user=str(user) if user else None,
        ssh_args=attrs.get("ansible_ssh_common_args"),
    )


def _group_var(inventory: dict, key: str) -> str | None:
    """Valeur d'une var au niveau groupe `cloud` puis `all` (repli), ou None (PUR)."""
    for group in ("cloud", "all"):
        node = inventory.get(group)
        if isinstance(node, dict):
            val = node.get("vars", {}).get(key)
            if val:
                return str(val)
    return None
