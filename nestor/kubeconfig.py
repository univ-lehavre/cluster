"""Transformation PURE d'un kubeconfig rapatrié d'un nœud (ADR 0081 étape 2).

`discover` rapatrie `/etc/kubernetes/admin.conf` du control-plane (via la brique node_exec,
façade I/O). Ce fichier pointe l'endpoint INTERNE du cluster (`cluster-api:6443` en banc
Lima, résolu seulement dans la VM ; l'IP interne en prod) — inutilisable tel quel depuis le
poste. Ce module RÉÉCRIT le kubeconfig pour qu'il soit joignable depuis l'extérieur :
endpoint, et (optionnel) noms uniques de cluster/user/contexte pour ne pas écraser un autre
kubeconfig fusionné (multi-cluster).

PUR : prend le TEXTE du kubeconfig + les paramètres, rend le TEXTE réécrit. Aucun I/O,
aucun kubectl — testable sans nœud ni cluster. Le portage de la logique `sed` de
`fetch_kubeconfig_node` (bench/lima/lib.sh) en données structurées (ADR 0049 : Python pour
la logique non triviale ; on ne grappille plus du YAML au `sed`).
"""

from __future__ import annotations

import yaml


def rewrite_kubeconfig(
    text: str,
    *,
    server: str,
    context_name: str | None = None,
    tls_server_name: str | None = None,
) -> str:
    """Réécrit un kubeconfig rapatrié (PUR, ADR 0081). Rend le YAML transformé.

    - `server` : nouvel endpoint de TOUS les clusters (ex. `https://127.0.0.1:6443` pour le
      port-forward Lima, ou `https://<ip-cp>:6443` en prod). C'est la réécriture INDISPENSABLE
      (l'endpoint interne n'est pas joignable du poste).
    - `context_name` : si fourni, renomme le cluster/user/contexte sur des noms UNIQUES dérivés
      (kubeadm pose toujours `kubernetes`/`kubernetes-admin` → deux kubeconfigs fusionnés
      s'écraseraient ; cf. `fetch_kubeconfig_node`). None → noms inchangés.
    - `tls_server_name` : si fourni, pose `tls-server-name` sur chaque cluster (la validation
      TLS se fait contre ce SAN, pas contre l'IP réécrite — ex. `cluster-api` en banc Lima).

    Lève `ValueError` si le texte n'est pas un kubeconfig exploitable (pas de clusters)."""
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"kubeconfig illisible : {exc}") from exc
    if not isinstance(cfg, dict) or not cfg.get("clusters"):
        raise ValueError("kubeconfig sans `clusters` — pas un admin.conf valide")

    for entry in cfg.get("clusters", []):
        cluster = entry.setdefault("cluster", {})
        cluster["server"] = server
        if tls_server_name:
            cluster["tls-server-name"] = tls_server_name

    if context_name:
        _rename_identifiers(cfg, context_name)

    return yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False)


def _rename_identifiers(cfg: dict, ctx: str) -> None:
    """Renomme cluster `kubernetes`→`ctx`, user `kubernetes-admin`→`ctx-admin`, contexte
    `kubernetes-admin@kubernetes`→`ctx`, et recâble les références (PUR). Idempotent sur des
    noms déjà uniques (un nom ≠ défaut kubeadm n'est pas touché)."""
    cluster_map = {"kubernetes": ctx}
    user_map = {"kubernetes-admin": f"{ctx}-admin"}

    for entry in cfg.get("clusters", []):
        if entry.get("name") in cluster_map:
            entry["name"] = cluster_map[entry["name"]]
    for entry in cfg.get("users", []):
        if entry.get("name") in user_map:
            entry["name"] = user_map[entry["name"]]
    for entry in cfg.get("contexts", []):
        if entry.get("name") == "kubernetes-admin@kubernetes":
            entry["name"] = ctx
        ctx_block = entry.get("context", {})
        if ctx_block.get("cluster") in cluster_map:
            ctx_block["cluster"] = cluster_map[ctx_block["cluster"]]
        if ctx_block.get("user") in user_map:
            ctx_block["user"] = user_map[ctx_block["user"]]
    if cfg.get("current-context") == "kubernetes-admin@kubernetes":
        cfg["current-context"] = ctx
