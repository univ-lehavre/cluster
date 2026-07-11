"""Garde d'isolation de CIBLE ANSIBLE (ADR 0053, 0108) : une action visant une instance
ne doit JAMAIS s'exécuter sur l'inventaire d'une AUTRE instance.

Pourquoi ce module. `nestor next <couche applicative>` lance un playbook via
ansible-runner sur l'inventaire dérivé de la topologie active. Les plays `hosts: cloud`
SSHent sur les nœuds de l'inventaire, un chemin INDÉPENDANT du KUBECONFIG. Un kubeconfig
d'une instance + un inventaire d'une AUTRE instance = mutation de la mauvaise cible
(faille du 2026-06-16 : un montage visant une instance jetable a reconfiguré containerd
sur l'instance massive en service).

Ce module est PUR : il CLASSE un inventaire déjà chargé (dict YAML) + l'IDENTITÉ visée
(`stack_id` de la topo) en un verdict. La LECTURE du fichier et le REFUS restent à la
façade. Le marqueur de vérité est l'`stack_id` porté par le groupe `cloud` de
l'inventaire (ADR 0108, remplaçant l'ancien `target_kind` de catégorie) : chaque
inventaire est DÉRIVÉ d'une topo, il porte donc l'identité de CETTE instance. Défaut
prudent : un inventaire SANS marqueur, ou dont les hôtes ne sont pas tous locaux, est
traité comme non prouvé (fail-closed). Le TRANSPORT (limactl/ssh) est porté par un
marqueur `transport:` DÉDIÉ, distinct de l'identité (ADR 0108) — un signal, un rôle.
"""

from __future__ import annotations

from dataclasses import dataclass

# Marqueurs d'un hôte LOCAL (instance pilotée depuis le poste, pas de SSH distant). Un
# inventaire dont TOUS les hôtes distants sont locaux ne peut muter aucune instance distante.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _inventory_group_var(inventory: dict, key: str) -> str | None:
    """Valeur d'une var au niveau du groupe `cloud` puis `all` (repli), ou None (PUR)."""
    for group in ("cloud", "all"):
        node = inventory.get(group)
        if isinstance(node, dict):
            val = node.get("vars", {}).get(key)
            if val:
                return str(val)
    return None


def _inventory_stack_id(inventory: dict) -> str | None:
    """`stack_id` déclaré par l'inventaire (vars du groupe `cloud`), ou None si absent.

    Marqueur d'IDENTITÉ de l'ADR 0108, émis par le générateur/le banc au niveau du groupe
    `cloud`. Comme l'inventaire est dérivé de la topologie de l'instance, cet `stack_id`
    lie l'inventaire aux VRAIS hôtes de cette instance — sans jamais deviner."""
    return _inventory_group_var(inventory, "stack_id")


def _inventory_transport(inventory: dict) -> str | None:
    """`transport` déclaré par l'inventaire (`lima` | `ssh`), ou None (PUR).

    Marqueur DÉDIÉ de l'ADR 0108, distinct de l'identité : il dit COMMENT atteindre les
    nœuds (limactl pour une classe locale, SSH direct sinon), pas QUI ils sont. Séparer ce
    signal de l'identité évite que la disparition de `target_kind` ne perde le transport."""
    return _inventory_group_var(inventory, "transport")


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


def classify_inventory_target(inventory: dict, intended_stack_id: str) -> tuple[bool, str]:
    """L'inventaire est-il SÛR pour l'instance `intended_stack_id` ? (PUR, ADR 0108).

    Renvoie `(ok, raison)`. Règles, du plus sûr au plus risqué :

    1. Aucun hôte distant (que des `localhost`/connexion locale) → SÛR : rien à SSHer,
       quelle que soit l'intention (les plays `hosts: cloud` n'auraient aucune cible).
    2. L'inventaire déclare `stack_id` ET il == `intended_stack_id` → SÛR (marqueur
       d'identité concordant, comme l'assert du rôle audit-log). L'inventaire étant dérivé
       de la topo de cette instance, un `stack_id` concordant prouve que les hôtes SSHés
       sont bien ceux de l'instance visée.
    3. Sinon (marqueur absent, OU marqueur ≠ intention, avec des hôtes distants) →
       REFUSÉ : on ne peut pas prouver que l'inventaire vise l'instance voulue, et il
       PEUT SSHer sur des nœuds (potentiellement une AUTRE instance). Fail-closed.

    Exemple de la faille du 2026-06-16 : intention=`banc-citation`, inventaire
    `stack_id: dirqual` + hôtes de dirqual (cp1/node1…) → règle 3 → REFUSÉ (ce qui aurait
    stoppé le montage qui a frappé l'instance massive)."""
    remote = _remote_hosts(inventory)
    if not remote:
        return True, "inventaire local (aucun hôte distant à SSHer)"
    declared = _inventory_stack_id(inventory)
    if declared is not None and declared == intended_stack_id:
        return True, f"stack_id concordant ({declared})"
    hosts_str = ", ".join(remote[:4]) + ("…" if len(remote) > 4 else "")
    if declared is None:
        return (
            False,
            f"inventaire SANS marqueur stack_id mais avec des hôtes distants "
            f"({hosts_str}) — instance non prouvée",
        )
    return (
        False,
        f"inventaire stack_id={declared} ≠ instance visée {intended_stack_id} ; "
        f"hôtes distants ({hosts_str}) — risque de muter la mauvaise instance",
    )


def endpoint_matches_stack(
    current_context: str | None,
    current_server: str | None,
    expected_stack_id: str,
    expected_endpoint: str | None,
) -> tuple[bool, str]:
    """Le kubeconfig courant vise-t-il bien l'instance `expected_stack_id` ? (PUR, ADR 0108).

    Preuve d'identité du chemin `kubectl`, à deux crans, du plus fort au plus faible :

    1. `current_context == expected_stack_id` — DISCRIMINANT CARDINAL. L'activation
       estampille le contexte du kubeconfig au nom de l'instance (rewrite). Un kubeconfig
       étranger (`kubernetes-admin@kubernetes`, `~/.kube/config`…) ou visant une AUTRE
       instance ne porte pas ce nom → refus. C'est ce qui remplace l'échappatoire
       `KUBECONFIG` (ADR 0065) : un `KUBECONFIG` exporté est COMPARÉ, jamais accepté en
       aveugle.
    2. Si `expected_endpoint` est concret (non vide, non placeholder), l'host:port de
       `current_server` doit l'égaler — second verrou, décisif pour une instance sur
       nœuds préexistants (endpoint réel et unique). Pour une classe locale, l'endpoint
       (127.0.0.1) n'est pas discriminant : seul le cran 1 protège.

    Cette fonction ne prouve PAS la VIVACITÉ (l'API répond, les nœuds sont Ready) : c'est
    à la façade de la vérifier après cette classification statique (ADR 0108, anti-
    tautologie — on ne valide pas une identité qu'on a soi-même écrite)."""
    if not current_context or current_context != expected_stack_id:
        got = current_context or "(aucun contexte courant)"
        return (
            False,
            f"contexte kubeconfig « {got} » ≠ instance visée « {expected_stack_id} » "
            f"— cible non prouvée",
        )
    if expected_endpoint and not _is_placeholder_endpoint(expected_endpoint):
        got_hp = _host_port(current_server)
        want_hp = _host_port(expected_endpoint)
        if got_hp != want_hp:
            return (
                False,
                f"endpoint kubeconfig {got_hp or '(absent)'} ≠ endpoint déclaré "
                f"{want_hp} pour « {expected_stack_id} »",
            )
    return True, f"contexte et endpoint concordants pour « {expected_stack_id} »"


# Hôtes d'endpoint jamais concrets : le placeholder générique du modèle d'exemple ne
# doit jamais servir de preuve (il neutraliserait le second cran). ADR 0108, contrainte
# de modèle : une instance réelle sur nœuds préexistants déclare un endpoint concret.
_PLACEHOLDER_ENDPOINT_HOSTS = frozenset({"cluster-api", ""})


def _is_placeholder_endpoint(endpoint: str) -> bool:
    host = _host_port(endpoint)
    host = host.rsplit(":", 1)[0] if host else host
    return host in _PLACEHOLDER_ENDPOINT_HOSTS


def _host_port(server: str | None) -> str:
    """`host:port` d'un `server:` de kubeconfig (schéma retiré, port implicite ignoré) (PUR)."""
    if not server:
        return ""
    s = server.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    return s.rstrip("/")


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
    """Résout `node` → `NodeTarget` depuis l'inventaire (PUR, ADR 0081, 0108).

    Le transport est DÉRIVÉ du marqueur `transport:` DÉDIÉ de l'inventaire (ADR 0108,
    `lima` → `limactl shell` ; sinon `ssh` direct) — plus de l'ancien `target_kind` : le
    transport est un signal propre (comment atteindre), distinct de l'identité (qui). Un
    inventaire sans marqueur `transport` retombe sur `ssh` (défaut prudent : le SSH direct
    vaut pour toute classe sur nœuds préexistants). Coordonnées prises sur l'hôte
    (`ansible_host`/`ansible_user`/`ansible_ssh_common_args`) ; `user` remonte en repli des
    vars du groupe `cloud`/`all`. Lève `IsolationError` si le nœud est absent (fail-closed :
    on ne devine pas une cible)."""
    attrs = _find_host_attrs(inventory, node)
    if attrs is None:
        raise IsolationError(f"nœud `{node}` absent de l'inventaire")
    transport = "lima" if _inventory_transport(inventory) == "lima" else "ssh"
    user = attrs.get("ansible_user") or _inventory_group_var(inventory, "ansible_user")
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
