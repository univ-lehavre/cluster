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


def env_content(pg_user: str, pg_pwd: str) -> str:
    """Contenu de `atlas/.env.cluster.local` (consommé par atlas). Pur : ne lit pas les
    Secrets (l'appelant les fournit déjà décodés) ; rend le texte exact à écrire.

    Postgres : FQDN intra-pod (le code atlas tourne DANS le cluster) ; OpenLineage et
    registry pointent les services internes. Valeurs de déploiement génériques (ADR 0023)."""
    header = (
        "# Généré par nestor (ex-access.sh) — NE PAS COMMITER (gitignoré).\n"
        "# Banc Lima local ; valeurs de déploiement (ADR 0023). Régénérer après un run.\n"
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
    return header + "".join(lines)
