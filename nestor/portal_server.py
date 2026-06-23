"""Portail d'accès aux UI — serveur in-cluster (étape 2, ADR 0091).

Mince couche d'I/O autour de la logique pure `nestor.portal` :
1. CHARGE le contrat (`endpoints.example.yaml`, embarqué dans l'image) ;
2. OBSERVE l'API k8s (Services + EndpointSlices + Nodes) — lecture seule, RBAC SANS
   secrets (ADR 0091 §3). L'accès UI est en L4 (ADR 0092) : on lit le NodePort réel
   des Services type=NodePort + l'IP d'un nœud Ready (plus de HTTPRoutes/hostnames) ;
3. CROISE via `portal.build_view`, REND via `portal.render_html` ;
4. SERT la page sur `/` (et `/healthz`) avec http.server (stdlib, image mince).

L'observation k8s est ISOLÉE dans `observe_cluster` (point d'injection unique pour les
tests, comme `nestor.smoke._core_v1`). Le reste (build_view, render_html) est PUR.
"""

from __future__ import annotations

import os

from nestor import portal

CONTRACT_PATH = os.environ.get(
    "PORTAL_CONTRACT", "/etc/portal/endpoints.yaml"
)  # monté/embarqué : le contrat versionné
TARGET_IS_PROD = os.environ.get("PORTAL_TARGET", "prod") != "lima"


class PortalUnavailable(RuntimeError):
    """Client kubernetes introuvable ou cluster injoignable (message actionnable)."""


def load_endpoints(path: str = CONTRACT_PATH) -> list[dict]:
    """Charge la liste `endpoints:` du contrat (YAML). Pur (lecture fichier embarqué)."""
    import yaml

    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("endpoints", []) or []


def _apis():
    """Clients k8s (CoreV1 + Discovery) — in-cluster ou kubeconfig. Injectable.

    Mappe ImportError / erreur de config en PortalUnavailable. Modèle nestor.smoke.
    """
    try:
        from kubernetes import client, config
    except ImportError as exc:  # pragma: no cover - dépendance épinglée
        raise PortalUnavailable("client kubernetes introuvable — `uv sync`") from exc
    try:
        config.load_incluster_config()
    except Exception:  # noqa: BLE001 - fallback kubeconfig hors cluster (dev)
        try:
            config.load_kube_config()
        except Exception as exc:  # noqa: BLE001
            raise PortalUnavailable("aucune configuration kubernetes") from exc
    cfg = client.Configuration.get_default_copy()
    cfg.retries = 0
    api = client.ApiClient(cfg)
    # 2 clients TYPÉS : Core (services + nodes), Discovery (endpointslices).
    return client.CoreV1Api(api), client.DiscoveryV1Api(api)


def observe_cluster(endpoints: list[dict], apis=None) -> dict[tuple[str, str], portal.Observed]:
    """Construit l'état observé {(ns, svc): Observed} pour les endpoints du contrat.

    LECTURE SEULE : Services (présence + NodePort attribué), EndpointSlices (readiness),
    Nodes (IP d'un nœud Ready). JAMAIS de Secret (le RBAC ne l'autorise pas, ADR 0091 §3).
    L'accès UI est en L4 (ADR 0092) : http://<node_ip>:<node_port observé>.
    `apis` injectable (tuple (core_v1, discovery)) pour les tests sans cluster.
    """
    core_v1, discovery = apis if apis is not None else _apis()
    observed: dict[tuple[str, str], portal.Observed] = {}
    node_ip = _ready_node_ip(core_v1)  # une fois pour tous : IP d'un nœud Ready
    for ep in endpoints:
        ns, svc = ep.get("namespace", ""), ep.get("service", "")
        if not ns or not svc:
            continue
        # Présence + nodePort du Service du contrat (`svc`). Le nodePort peut y vivre
        # directement (brique maison exposée en NodePort, ex. portal) OU sur un Service
        # d'exposition SÉPARÉ `<svc>-nodeport` (UI vendored — ADR 0092 : on ne touche
        # pas le ClusterIP du chart, on pose un NodePort à côté). On lit donc le port
        # sur `svc` ET, à défaut, sur `<svc>-nodeport`.
        present, node_port = _service_state(core_v1, ns, svc)
        if node_port is None:
            _np_present, np = _service_state(core_v1, ns, f"{svc}-nodeport")
            node_port = np
        ready = present and _endpoints_ready(discovery, ns, svc)
        observed[(ns, svc)] = portal.Observed(
            present=present,
            ready=ready,
            node_port=node_port,
            node_ip=node_ip if node_port else None,
        )
    return observed


def _service_state(core_v1, ns: str, svc: str) -> tuple[bool, int | None]:
    """(présent, nodePort) d'un Service. nodePort = le premier port type=NodePort
    attribué (ADR 0092), None si le Service n'est pas exposé en NodePort ou absent."""
    from kubernetes.client.exceptions import ApiException

    try:
        s = core_v1.read_namespaced_service(svc, ns)
    except ApiException:
        return False, None  # 404 absent, 403/autre : on ne peut pas affirmer présent
    node_port = None
    spec = getattr(s, "spec", None)
    if spec is not None and getattr(spec, "type", None) == "NodePort":
        for p in getattr(spec, "ports", None) or []:
            if getattr(p, "node_port", None):
                node_port = p.node_port
                break
    return True, node_port


def _ready_node_ip(core_v1) -> str | None:
    """IP interne d'un nœud Ready (cible des NodePort, ADR 0092). None si inconnue."""
    from kubernetes.client.exceptions import ApiException

    try:
        nodes = core_v1.list_node()
    except ApiException:
        return None
    for n in getattr(nodes, "items", None) or []:
        conds = getattr(getattr(n, "status", None), "conditions", None) or []
        if not any(c.type == "Ready" and c.status == "True" for c in conds):
            continue
        for addr in getattr(n.status, "addresses", None) or []:
            if addr.type == "InternalIP":
                return addr.address
    return None


def _endpoints_ready(discovery, ns: str, svc: str) -> bool:
    """Au moins une adresse prête dans les EndpointSlices du service (API typée)."""
    from kubernetes.client.exceptions import ApiException

    try:
        slices = discovery.list_namespaced_endpoint_slice(
            ns, label_selector=f"kubernetes.io/service-name={svc}"
        )
    except ApiException:
        return False
    for sl in slices.items or []:
        for ep in sl.endpoints or []:
            if ep.conditions and ep.conditions.ready:
                return True
    return False


def build_page(apis=None, *, contract_path: str = CONTRACT_PATH) -> str:
    """Pipeline complet : contrat → observe → build_view → render_html. Page HTML."""
    endpoints = load_endpoints(contract_path)
    observed = observe_cluster(endpoints, apis=apis)
    view = portal.build_view(endpoints, observed, target_is_prod=TARGET_IS_PROD)
    return portal.render_html(view)


def serve(port: int = 8080) -> None:  # pragma: no cover - boucle réseau
    """Sert le portail (stdlib http.server). La page est recalculée à chaque GET /."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/healthz":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return
            try:
                page = build_page().encode("utf-8")
            except PortalUnavailable as exc:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(str(exc).encode("utf-8"))
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *_args):  # silence l'access log par défaut
            return

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104


if __name__ == "__main__":  # pragma: no cover
    # NE PAS lire `PORTAL_PORT` : Kubernetes injecte automatiquement une variable
    # `<SVCNAME>_PORT` par Service (le Service `portal` → PORTAL_PORT=tcp://IP:80),
    # qui collisionnerait. On lit une variable HORS de ce pattern.
    serve(int(os.environ.get("PORTAL_LISTEN_PORT", "8080")))
