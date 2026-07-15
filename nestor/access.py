"""Logique PURE de l'accès développeur au banc (ADR 0048/0092 ; ex-`access.sh`).

Porté de `bench/lima/access.sh` (ADR 0101) : la décision pure — quel port hôte par
UI, quelles lignes d'URL/`.env`, quelles UI exposer du contrat — vit ici (testée sans
cluster). L'I/O (kubectl, port-forward, lecture des Secrets, écriture du `.env`) reste
la façade `scripts/topology.py:cmd_access`, qui réutilise `_kubectl`/`_b64decode`.

Exposition L4 NodePort (ADR 0092) : chaque UI `exposed: true` du contrat est servie par
un Service `<service>-nodeport`. Au BANC le réseau Lima est isolé du Mac → un
`kubectl port-forward 127.0.0.1:<BASE+i>` rend l'UI cliquable ; en PROD le poste atteint
directement `http://<IP-nœud>:<nodePort>` (aucun forward). Valeurs génériques (ADR 0023).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import yaml

# Port hôte de base du port-forward banc : la i-ème UI exposée écoute sur BASE+i
# (8443, 8444…). Non privilégié (aucun sudo). N'a de sens QU'AU BANC — en prod on
# vise directement `<IP-nœud>:<nodePort>`.
BASE_PORT = 8443


def host_port_for(index: int, base: int = BASE_PORT) -> int:
    """Port hôte local du port-forward de la i-ème UI exposée (`base + index`)."""
    return base + index


def url_line(layer: str, url: str, auth: str) -> str:
    """Ligne d'affichage alignée d'une UI : `    [<layer>] <url>   (auth: <auth>)`."""
    return f"    [{layer:<10}] {url}   (auth: {auth})\n"


def env_line(key: str, value: str | None) -> str:
    """Ligne `KEY=VALUE` du `.env` (valeur vide tolérée)."""
    return f"{key}={value or ''}\n"


# ── Cible de LIVRAISON atlas (GITEA_PUSH_URL) ────────────────────────────────
# Le geste de mise en production atlas (`dataops/deploy.sh`, ADR atlas 0104) pousse le
# `main` revu vers la forge de l'instance : `git push $GITEA_PUSH_URL main`. Le dépôt
# cible est le dépôt atlas COMPLET — celui que suit l'`Application` Argo CD
# (`repoURL …/<org>/<repo_livraison>.git`, `targetRevision: deploy`). À NE PAS confondre
# avec le dépôt JOUET du socle (`gitea.repo`, défaut `workflows` — ADR 0111/0086) : le
# jouet sert à prouver l'usine (scénario 35), il n'est jamais la cible de livraison.
# Défauts génériques (ADR 0023/0035, pas de marque) : org=`atlas`, repo de livraison=`atlas`.
LIVRAISON_ORG = "atlas"
LIVRAISON_REPO = "atlas"


def push_endpoint_for(
    *,
    declared: str | None,
    exposition_mode: str,
    access_host: str,
    node_port: str,
    local_port: int,
) -> str:
    """`host:port` par lequel le POSTE joint la forge git, dérivé de la TOPOLOGIE (PUR).

    Un seul chemin, paramétré par la topo (plus de dualité banc/prod — que des topologies,
    ADR 0108) :
    - `declared` (champ topo `gitea.push_endpoint`) l'emporte TOUJOURS s'il est renseigné :
      l'instance a déclaré explicitement son endpoint de forge externe (le contrat prime la
      déduction — robustesse, ADR 0090/0102) ;
    - sinon on DÉDUIT de `exposition.mode` (ADR 0092) : `nodeport`/`gateway` → la forge est
      jointe DIRECTEMENT en `<access_host>:<node_port>` (host côté navigateur = `portal.
      access_host`, port = nodePort réel du Service) ; tout autre mode (réseau isolé, ex.
      Lima) → un port-forward local `127.0.0.1:<local_port>` que la façade maintient.
    Rend `""` si l'endpoint déductible manque (nodePort absent) — l'appelant décide."""
    if declared:
        return declared.strip()
    if exposition_mode in ("nodeport", "gateway"):
        if access_host and node_port:
            return f"{access_host}:{node_port}"
        return ""
    # Réseau non joignable directement (Lima isolé, ADR 0092) : port-forward local.
    return f"127.0.0.1:{local_port}"


def gitea_push_url(endpoint: str, user: str, token: str, *, org: str, repo: str) -> str:
    """Assemble `GITEA_PUSH_URL = http://<user>:<token>@<endpoint>/<org>/<repo>.git` (PUR).

    `user`/`token` sont URL-encodés (un token peut porter des caractères réservés). HTTP
    clair : la forge est en réseau privé (ADR 0011) et le `.env` est gitignoré ; embarquer
    `user:token@` suit la pratique existante (le `.env` porte déjà des mots de passe en
    clair, faux positif CodeQL assumé). Rend `""` si un morceau requis manque (endpoint ou
    token) — l'appelant n'écrit alors pas la variable plutôt que d'émettre une URL cassée."""
    if not endpoint or not token:
        return ""
    cred = f"{quote(user, safe='')}:{quote(token, safe='')}"
    return f"http://{cred}@{endpoint}/{org}/{repo}.git"


@dataclass(frozen=True)
class ExposedUI:
    """Une UI à exposer, lue du contrat (`exposed: true`)."""

    namespace: str
    service: str
    layer: str
    auth: str


def exposed_uis(contract_text: str) -> list[ExposedUI]:
    """Les endpoints `exposed: true` du contrat, TRIÉS (ordre stable → port hôte par
    index déterministe). Pur : parse le YAML du contrat, aucune I/O réseau."""
    data = yaml.safe_load(contract_text) or {}
    rows = [
        ExposedUI(
            namespace=str(e.get("namespace", "")),
            service=str(e.get("service", "")),
            layer=str(e.get("layer") or "-"),
            auth=str(e.get("auth") or "none"),
        )
        for e in data.get("endpoints", [])
        if e.get("exposed") is True
    ]
    # Tri sur (namespace, service) = l'ordre `sort` du bash → index déterministe.
    return sorted(rows, key=lambda u: (u.namespace, u.service))


# Les Secrets à afficher (un seul écran). (libellé, namespace, secret, clé-user, clé-pwd).
# clé-user None = compte fixe « admin » (Argo CD/Grafana n'exposent pas l'user en Secret).
SECRET_ROWS = (
    ("Argo CD", "argocd", "argocd-initial-admin-secret", None, "password"),
    ("Gitea", "gitea", "gitea-admin", "username", "password"),
    ("Grafana", "monitoring", "kube-prometheus-stack-grafana", None, "admin-password"),
    ("pg/dagster", "postgres", "pg-role-dagster", "username", "password"),
    ("pg/pgvector", "postgres", "pg-role-pgvector", "username", "password"),
    ("pg/marquez", "postgres", "pg-role-marquez", "username", "password"),
)


def env_content(pg_user: str, pg_pwd: str, *, gitea_push_url: str = "") -> str:
    """Contenu de `atlas/.env.cluster.local` (consommé par atlas). Pur : ne lit pas les
    Secrets (l'appelant les fournit déjà décodés) ; rend le texte exact à écrire.

    Postgres : FQDN intra-pod (le code atlas tourne DANS le cluster) ; OpenLineage et
    registry pointent les services internes. Valeurs de déploiement génériques (ADR 0023).
    `gitea_push_url` (optionnel) : la cible de LIVRAISON atlas (ADR atlas 0104) — émise
    seulement si l'appelant a pu la dériver (endpoint joignable + token) ; vide → ligne
    non écrite (le geste `deploy.sh` refuse alors bruyamment, plutôt qu'une URL cassée)."""
    header = (
        "# Généré par nestor (ex-access.sh) — NE PAS COMMITER (gitignoré).\n"
        "# Valeurs de déploiement de l'instance (ADR 0023). Régénérer après un run.\n"
        "# Postgres : FQDN intra-pod (le code atlas tourne dans le cluster) ou via un\n"
        "# kubectl port-forward dédié si exécuté depuis l'hôte.\n"
    )
    lines = [
        env_line("POSTGRES_HOST", "pg-rw.postgres.svc.cluster.local"),
        env_line("POSTGRES_PORT", "5432"),
        env_line("POSTGRES_DB", "pgvector"),
        env_line("POSTGRES_USER", pg_user),
        env_line("POSTGRES_PASSWORD", pg_pwd),
        env_line("OPENLINEAGE_URL", "http://marquez.marquez.svc.cluster.local:5000"),
        env_line("OPENLINEAGE_ENDPOINT", "api/v1/lineage"),
        env_line("OPENLINEAGE_NAMESPACE", "dagster"),
        env_line("REGISTRY", "registry:80"),
    ]
    if gitea_push_url:
        lines.append("# Cible de mise en production atlas (ADR atlas 0104 ; deploy.sh).\n")
        lines.append(env_line("GITEA_PUSH_URL", gitea_push_url))
    return header + "".join(lines)
