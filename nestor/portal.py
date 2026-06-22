"""Portail d'accès aux UI — logique PURE de croisement contrat ↔ état (ADR 0091).

Le portail (serveur in-cluster, étape 2+) affiche une sidebar des UI/endpoints de la
plateforme, groupée par couche, avec pour chacune : son lien (nouvel onglet), son
verdict vis-à-vis de l'état réel, et — si auth requise — la COMMANDE `kubectl` pour
récupérer le credential (JAMAIS sa valeur, ADR 0023/0014).

Ce module est PUR (ADR 0017) : il prend le CONTRAT (le « DEVRAIT ») et un ÉTAT OBSERVÉ
(le « EST », injecté — l'I/O API k8s vit en bordure, étape 2) et rend la vue. Aucun
accès cluster, aucune lecture de Secret : testable sans cluster.

Verdicts (ADR 0091) :
- MATCH   : le contrat le déclare ET l'état le confirme (Service présent + endpoints).
- MISSING : le contrat le déclare mais l'état ne le trouve pas (sauf banc-only en prod).
- DRIFT   : présent mais incohérent (hostname réel ≠ attendu, endpoints non prêts).
- EXTRA   : exposé/observé mais absent du contrat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Verdicts (cf. ADR 0091).
MATCH = "MATCH"
MISSING = "MISSING"
DRIFT = "DRIFT"
EXTRA = "EXTRA"


@dataclass(frozen=True)
class Observed:
    """État RÉEL d'un service, injecté par la bordure (API k8s) — PUR ici.

    `present`  : un Service `(namespace, service)` existe.
    `ready`    : au moins un endpoint prêt (EndpointSlice non vide).
    `hostname` : hostname réellement exposé (HTTPRoute), None si non exposé en bordure.
    """

    present: bool = False
    ready: bool = False
    hostname: str | None = None


@dataclass(frozen=True)
class Entry:
    """Une entrée de la sidebar du portail (un endpoint/UI du contrat, jugé)."""

    id: str
    layer: str
    service: str
    namespace: str
    verdict: str
    ui_url: str | None  # https://<ui_hostname> si exposé, sinon None
    secret_cmd: str | None  # commande kubectl pour le credential, None si auth=none
    note: str = ""


@dataclass
class View:
    """La vue rendue : entrées groupées par couche, dans l'ordre canonique."""

    layers: dict[str, list[Entry]] = field(default_factory=dict)

    def all_entries(self) -> list[Entry]:
        return [e for entries in self.layers.values() for e in entries]


# Ordre d'affichage canonique des couches (sidebar).
LAYER_ORDER = ["socle", "monitoring", "gitops", "dataops"]


def secret_command(endpoint: dict, secrets: dict | None = None) -> str | None:
    """Commande `kubectl` à exécuter pour récupérer le credential d'un endpoint.

    Dérivée du champ `auth` du contrat (JAMAIS la valeur du Secret — le portail
    affiche la commande, l'opérateur l'exécute avec ses droits, ADR 0091 §3).
    `auth: none` → None (pas de credential). Pour les types adossés à un Secret, on
    construit la commande de lecture ; `secrets` (namespaces-secrets) précise nom/clé
    quand le contrat ne les porte pas inline. Renvoie None si rien à afficher.
    """
    auth = endpoint.get("auth", "none")
    if auth in (None, "none"):
        return None
    ns = endpoint.get("namespace", "")
    if auth == "token":
        # Jeton d'un ServiceAccount (Dashboard, ADR 0010) — créé à la demande.
        return f"kubectl -n {ns} create token admin-user"
    if auth == "secret-obc":
        # Creds générés par l'ObjectBucketClaim (clé AWS_SECRET_ACCESS_KEY).
        return (
            f"kubectl -n {ns} get secret <obc-name> "
            "-o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d"
        )
    # secret-admin / secret-role / secret-static : un Secret nommé + une clé.
    name, key = _secret_ref(endpoint, secrets)
    return f"kubectl -n {ns} get secret {name} -o jsonpath='{{.data.{key}}}' | base64 -d"


def _secret_ref(endpoint: dict, secrets: dict | None) -> tuple[str, str]:
    """(nom de Secret, clé) pour un endpoint à auth Secret. Heuristique par convention
    (ADR 0023, contract/namespaces-secrets) ; `<secret>`/`password` en repli explicite."""
    sid = endpoint.get("id", "")
    # Conventions connues du contrat (noms stables, valeurs hors dépôt).
    known = {
        "argocd-ui": ("argocd-initial-admin-secret", "password"),
        "gitea-ui": ("gitea-admin", "password"),
        "grafana-ui": ("kube-prometheus-stack-grafana", "admin-password"),
    }
    if sid in known:
        return known[sid]
    if endpoint.get("auth") == "secret-role":
        # Rôle CNPG : Secret pg-role-<rôle>, clé password (basic-auth).
        role = endpoint.get("role", "<rôle>")
        return (f"pg-role-{role}", "password")
    return ("<secret>", "password")


def _ui_url(endpoint: dict, observed: Observed) -> str | None:
    """URL cliquable de l'UI : https://<hostname réel observé> si exposé en bordure,
    sinon https://<ui_hostname attendu> si déclaré, sinon None (pas d'UI)."""
    host = observed.hostname or endpoint.get("ui_hostname")
    return f"https://{host}" if host else None


def _verdict(endpoint: dict, observed: Observed, *, target_is_prod: bool) -> str:
    """Verdict d'un endpoint déclaré vs son état observé (ADR 0091)."""
    # Un endpoint banc-only (profil local-path) absent d'une cible prod n'est pas un
    # défaut : c'est attendu (ex. seaweedfs, mailpit). MATCH par convention.
    if not observed.present:
        if target_is_prod and endpoint.get("profil") == "local-path":
            return MATCH
        return MISSING
    # Présent mais endpoints pas prêts, OU exposé sous un hostname ≠ attendu → DRIFT.
    expected_host = endpoint.get("ui_hostname")
    if not observed.ready:
        return DRIFT
    if expected_host and observed.hostname and observed.hostname != expected_host:
        return DRIFT
    return MATCH


def build_view(
    endpoints: list[dict],
    observed: dict[tuple[str, str], Observed] | None = None,
    *,
    secrets: dict | None = None,
    target_is_prod: bool = True,
    extras: list[dict] | None = None,
) -> View:
    """Croise le CONTRAT (`endpoints`) avec l'ÉTAT observé → la vue du portail.

    `endpoints` : la liste `endpoints:` de contract/endpoints.example.yaml.
    `observed`  : {(namespace, service): Observed} fourni par la bordure (vide = tout
                  MISSING ; le contrat seul, mode hors-cluster).
    `extras`    : services observés HORS contrat (verdict EXTRA), optionnel.
    `target_is_prod` : un endpoint banc-only absent en prod est MATCH (pas MISSING).

    Pur : aucune I/O. Groupé par couche dans l'ordre canonique (LAYER_ORDER), les
    couches inconnues après, triées."""
    observed = observed or {}
    view = View()

    def add(entry: Entry) -> None:
        view.layers.setdefault(entry.layer, []).append(entry)

    for ep in endpoints:
        ns, svc = ep.get("namespace", ""), ep.get("service", "")
        obs = observed.get((ns, svc), Observed())
        add(
            Entry(
                id=ep.get("id", svc),
                layer=ep.get("layer", "socle"),
                service=svc,
                namespace=ns,
                verdict=_verdict(ep, obs, target_is_prod=target_is_prod),
                ui_url=_ui_url(ep, obs),
                secret_cmd=secret_command(ep, secrets),
                note=ep.get("note", "") or "",
            )
        )

    for ex in extras or []:
        add(
            Entry(
                id=ex.get("id", ex.get("service", "?")),
                layer=ex.get("layer", "socle"),
                service=ex.get("service", "?"),
                namespace=ex.get("namespace", ""),
                verdict=EXTRA,
                ui_url=_ui_url(ex, Observed(hostname=ex.get("hostname"))),
                secret_cmd=None,
                note="exposé/observé mais absent du contrat",
            )
        )

    # Réordonner les couches : canoniques d'abord, le reste trié.
    ordered = {layer: view.layers[layer] for layer in LAYER_ORDER if layer in view.layers}
    for layer in sorted(view.layers):
        if layer not in ordered:
            ordered[layer] = view.layers[layer]
    view.layers = ordered
    return view


# ── Rendu HTML (PUR) ─────────────────────────────────────────────────────────
# Le serveur (portal_server) collecte l'état (I/O) puis appelle render_html(view) :
# une page autonome (sidebar par couche, liens nouvel onglet, commandes secret
# copiables). Pas d'iframe (ADR 0091 §2). Pur → testable sans cluster.

_VERDICT_BADGE = {
    MATCH: ("✓", "ok"),
    MISSING: ("∅", "missing"),
    DRIFT: ("⚠", "drift"),
    EXTRA: ("＋", "extra"),
}

_CSS = """
body{font:14px/1.5 system-ui,sans-serif;margin:0;color:#1a1a1a;background:#fafafa}
header{padding:1rem 1.5rem;background:#1a2b4a;color:#fff}
header h1{margin:0;font-size:1.2rem}
header p{margin:.3rem 0 0;opacity:.8;font-size:.85rem}
main{display:flex;flex-wrap:wrap;gap:1rem;padding:1.5rem}
section{flex:1 1 320px;background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:1rem}
section h2{margin:0 0 .6rem;font-size:.95rem;text-transform:uppercase;color:#555}
section h2{letter-spacing:.04em}
.entry{border-top:1px solid #f0f0f0;padding:.6rem 0}
.entry:first-of-type{border-top:0}
.entry a{font-weight:600;color:#1a5fb4;text-decoration:none}
.entry a:hover{text-decoration:underline}
.entry .name{font-weight:600}
.badge{display:inline-block;font-size:.7rem;padding:.05rem .4rem;border-radius:4px}
.badge{margin-left:.4rem;vertical-align:middle}
.badge.ok{background:#e6f4ea;color:#1e7e34}
.badge.missing{background:#eee;color:#777}
.badge.drift{background:#fff3cd;color:#9a6700}
.badge.extra{background:#e7e0fb;color:#5a32a3}
.note{color:#666;font-size:.82rem;margin:.2rem 0 0}
.secret{margin:.3rem 0 0}
.secret code{display:block;background:#1e1e1e;color:#d4d4d4;padding:.4rem .6rem}
.secret code{border-radius:4px;font-size:.78rem;overflow-x:auto;white-space:pre}
.secret span{font-size:.78rem;color:#666}
"""


def _esc(text: str) -> str:
    """Échappe le HTML (pas de dépendance ; entrées = contrat versionné, mais sûr)."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_entry(e: Entry) -> str:
    glyph, css = _VERDICT_BADGE.get(e.verdict, ("?", "missing"))
    badge = f'<span class="badge {css}" title="{e.verdict}">{glyph} {e.verdict}</span>'
    if e.ui_url:
        title = f'<a href="{_esc(e.ui_url)}" target="_blank" rel="noopener">{_esc(e.id)}</a>'
    else:
        title = f'<span class="name">{_esc(e.id)}</span>'
    parts = [f'<div class="entry">{title}{badge}']
    if e.note:
        parts.append(f'<p class="note">{_esc(e.note)}</p>')
    if e.secret_cmd:
        parts.append(
            f'<div class="secret"><span>credential :</span><code>{_esc(e.secret_cmd)}</code></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_html(view: View, *, title: str = "Portail — plateforme") -> str:
    """Rend la page HTML autonome du portail depuis une View. PUR (ADR 0091)."""
    sections = []
    for layer, entries in view.layers.items():
        rows = "".join(_render_entry(e) for e in entries)
        sections.append(f"<section><h2>{_esc(layer)}</h2>{rows}</section>")
    body = "".join(sections) or "<p style='padding:1.5rem'>Aucun endpoint au contrat.</p>"
    return (
        "<!doctype html><html lang=fr><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head><body>"
        f"<header><h1>{_esc(title)}</h1>"
        "<p>UI et endpoints de la plateforme — cliquer ouvre dans un nouvel onglet. "
        "Les commandes affichées récupèrent les credentials (jamais leur valeur ici).</p>"
        f"</header><main>{body}</main></body></html>"
    )
