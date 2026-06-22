"""Portail d'accès aux UI — serveur in-cluster (étape 2, ADR 0091).

Mince couche d'I/O autour de la logique pure `nestor.portal` :
1. CHARGE le contrat (`endpoints.example.yaml`, embarqué dans l'image) ;
2. OBSERVE l'API k8s (Services + EndpointSlices + HTTPRoutes) — lecture seule, RBAC
   SANS secrets (ADR 0091 §3) ;
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
    """Clients k8s (CoreV1 + CustomObjects) — in-cluster ou kubeconfig. Injectable.

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
    return client.CoreV1Api(api), client.CustomObjectsApi(api)


def observe_cluster(endpoints: list[dict], apis=None) -> dict[tuple[str, str], portal.Observed]:
    """Construit l'état observé {(ns, svc): Observed} pour les endpoints du contrat.

    LECTURE SEULE : Services (présence), EndpointSlices (readiness), HTTPRoutes
    (hostname exposé). JAMAIS de Secret (le RBAC ne l'autorise pas, ADR 0091 §3).
    `apis` injectable (tuple (core_v1, custom)) pour les tests sans cluster.
    """
    core_v1, custom = apis if apis is not None else _apis()
    observed: dict[tuple[str, str], portal.Observed] = {}
    # Hostnames exposés par les HTTPRoutes (gateway.networking.k8s.io), indexés par
    # service backend. Best-effort : si l'API Gateway n'est pas là, on continue.
    host_by_svc = _httproute_hosts(custom)
    for ep in endpoints:
        ns, svc = ep.get("namespace", ""), ep.get("service", "")
        if not ns or not svc:
            continue
        present = _service_exists(core_v1, ns, svc)
        ready = present and _endpoints_ready(core_v1, ns, svc)
        observed[(ns, svc)] = portal.Observed(
            present=present, ready=ready, hostname=host_by_svc.get((ns, svc))
        )
    return observed


def _service_exists(core_v1, ns: str, svc: str) -> bool:
    from kubernetes.client.exceptions import ApiException

    try:
        core_v1.read_namespaced_service(svc, ns)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        return False  # 403/autre : on ne peut pas affirmer présent


def _endpoints_ready(core_v1, ns: str, svc: str) -> bool:
    """Au moins une adresse prête dans les EndpointSlices du service."""
    from kubernetes.client.exceptions import ApiException

    try:
        slices = core_v1.api_client.call_api(
            f"/apis/discovery.k8s.io/v1/namespaces/{ns}/endpointslices",
            "GET",
            query_params=[("labelSelector", f"kubernetes.io/service-name={svc}")],
            response_type="object",
            _return_http_data_only=True,
        )
    except ApiException:
        return False
    for sl in (slices or {}).get("items", []):
        for ep in sl.get("endpoints", []) or []:
            if (ep.get("conditions") or {}).get("ready"):
                return True
    return False


def _httproute_hosts(custom) -> dict[tuple[str, str], str]:
    """{(ns_backend, svc_backend): premier hostname} d'après les HTTPRoutes (best-effort)."""
    from kubernetes.client.exceptions import ApiException

    out: dict[tuple[str, str], str] = {}
    try:
        routes = custom.list_cluster_custom_object("gateway.networking.k8s.io", "v1", "httproutes")
    except ApiException:
        return out
    for r in (routes or {}).get("items", []):
        ns = (r.get("metadata") or {}).get("namespace", "")
        hosts = (r.get("spec") or {}).get("hostnames") or []
        if not hosts:
            continue
        for rule in (r.get("spec") or {}).get("rules", []) or []:
            for ref in rule.get("backendRefs", []) or []:
                svc = ref.get("name")
                bns = ref.get("namespace", ns)
                if svc:
                    out.setdefault((bns, svc), hosts[0])
    return out


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
    serve(int(os.environ.get("PORTAL_PORT", "8080")))
