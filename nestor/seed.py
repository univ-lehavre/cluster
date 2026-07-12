"""Seed des DONNÉES post-bootstrap du JOUET du socle (LOT 8, ADR 0097 §2/§3).

Une étape de DONNÉES (pas d'infra : Gitea/Argo CD sont posés par les playbooks) que le
bash portait, désormais en Python testable (ADR 0017) :

- BANC : `bench/lima/gitea-init.sh` (207 l.) — crée l'admin Gitea, un token API, l'org +
  le dépôt des workflows atlas, pousse la code-location JOUET `atlas-workflows`, pose le
  webhook et l'Application Argo CD `atlas-workflows`. Garde **banc** :
  `_assert_target_identity` (la cible DOIT être le banc Lima, jamais la prod).

Ce seed pose UNIQUEMENT le jouet du socle (ADR 0086), artefact plateforme. Il ne touche
PLUS aucune code-location APPLICATIVE (citation, mediawatch…) : depuis ADR 0111,
l'INSTANCIATION de l'Application Argo CD d'une code-location applicative — et le flux
App-of-Apps `cluster/apps` associé — est un GESTE côté dépôt `atlas` (build + push de
l'Application). Le portage prod `bootstrap/seed-app-of-apps.sh` a donc été RETIRÉ.

⚠️  HONNÊTETÉ (ADR 0034) — ce seed MUTE un cluster réel (Gitea, Argo CD). Sa preuve
DÉFINITIVE est un RUN BANC (banc) que CE PALIER NE FAIT PAS. Ici : la LOGIQUE (ordre des
étapes, garde banc, paramétrage 100 % YAML) est PURE et prouvée par tests STUBÉS — toute
l'I/O (kubectl exec, curl Gitea) est INJECTÉE (zéro appel Gitea réel). Le câblage réel +
la preuve restent dans `_BANC_TODO`.

PARAMÉTRAGE 100 % YAML (ADR 0097 §3) : `SeedConfig.from_topology(topo)` lit le bloc
`gitea` du YAML — PLUS de `GITEA_*` lus de l'env. Les valeurs d'exemple (ADR 0023)
restent les défauts quand le bloc est absent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ── Défauts GÉNÉRIQUES (ADR 0023) — repris à l'identique des deux scripts bash. Le YAML
#    (blocs gitea:/atlas:) les surcharge ; PLUS de variables d'env.
_DEFAULTS = {
    "ns": "gitea",
    "admin_user": "atlas-admin",
    "admin_email": "atlas-admin@example-org.lan",
    "svc": "http://gitea-http.gitea.svc.cluster.local",
    # API : kubectl exec DANS le pod gitea → localhost:3000 (évite le piège FQDN, cf.
    # gitea-init.sh:38 et le drift DNS constaté sur dirqual).
    "api": "http://localhost:3000",
    "argocd_ns": "argocd",
    # Banc (gitea-init.sh) : org/repo des workflows atlas (jouet du socle).
    "org": "atlas",
    "repo": "workflows",
}


class SeedError(RuntimeError):
    """Le seed a échoué : garde refusée, étape Gitea/Argo CD en erreur, cible invalide."""


class SeedGuardRefused(SeedError):
    """La GARDE (banc ou prod) a refusé : la cible n'est pas celle attendue (ADR 0053/0046).

    Sous-classe distincte pour que l'appelant/les tests distinguent un REFUS de sécurité
    (cible non prouvée) d'un échec d'étape ordinaire — un refus = on n'a RIEN muté."""


@dataclass(frozen=True)
class SeedConfig:
    """Paramètres du seed du JOUET LUS DU YAML (LOT 8) — plus de variables d'environnement.

    `from_topology` dérive du bloc `gitea:` du YAML ; les défauts génériques (ADR 0023)
    comblent un bloc absent. IMMUABLE. Depuis ADR 0111, ne porte PLUS les paramètres du
    flux prod App-of-Apps (org/repo déclaratif, code atlas, code-locations applicatives) —
    l'instanciation d'une code-location applicative est un geste côté dépôt atlas."""

    ns: str = _DEFAULTS["ns"]
    admin_user: str = _DEFAULTS["admin_user"]
    admin_email: str = _DEFAULTS["admin_email"]
    svc: str = _DEFAULTS["svc"]
    api: str = _DEFAULTS["api"]
    argocd_ns: str = _DEFAULTS["argocd_ns"]
    # Banc (jouet du socle) : org/repo des workflows atlas.
    org: str = _DEFAULTS["org"]
    repo: str = _DEFAULTS["repo"]

    @classmethod
    def from_topology(cls, topo: Any) -> SeedConfig:
        """Construit une SeedConfig depuis le bloc `gitea:` d'une Topology (PUR).

        LIT le YAML, jamais l'env (ADR 0097 §3). Un bloc/champ absent → défaut générique
        (ADR 0023). C'est l'unique pont topologie → seed du jouet : aucune autre source."""
        gitea = getattr(topo, "gitea", {}) or {}

        def g(key: str) -> Any:
            return gitea.get(key, _DEFAULTS[key])

        return cls(
            ns=g("ns"),
            admin_user=g("admin_user"),
            admin_email=g("admin_email"),
            svc=g("svc"),
            api=g("api"),
            argocd_ns=gitea.get("argocd_ns", _DEFAULTS["argocd_ns"]),
            org=g("org"),
            repo=g("repo"),
        )

    # ── URL dérivée (PUR) — jouet du socle ───────────────────────────────────────
    def workflows_repo_url(self) -> str:
        """repoURL intra-cluster du dépôt de workflows jouet (banc, gitea-init.sh:176)."""
        return f"{self.svc}/{self.org}/{self.repo}.git"


@dataclass
class SeedStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class SeedResult:
    """Verdict d'un seed. `done` = toutes les étapes ont réussi (parité Path/Bootstrap)."""

    kind: str  # "banc" | "prod"
    steps: list[SeedStep] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)


# ── Étapes ORDONNÉES du seed JOUET (les noms transcrivent les `echo "[gitea-init] N/7 …"`
#    du bash). La LOGIQUE = l'ordre + la garde ; les actions sont déléguées au callback
#    `do(step) -> bool` injecté (stub en test).
#    NB (ADR 0111) : les séquences PROD / BANC-CITATION (flux App-of-Apps citation) ont été
#    RETIRÉES — l'instanciation de l'Application d'une code-location applicative est un geste
#    côté dépôt atlas. Seul demeure le seed du jouet `atlas-workflows` (artefact du socle).
_BANC_STEPS = (
    "admin",  # 1 — admin Gitea (idempotent)
    "token",  # 2 — token API
    "org-repo",  # 3 — organisation + dépôt des workflows
    "push-code-location",  # 4 — push de la code-location jouet (Contents API)
    "webhook-secret",  # 5 — secret partagé webhook.gitea.secret (argocd-secret)
    "webhook",  # 6 — webhook Gitea → argocd-server/api/webhook
    "application",  # 7 — Application Argo CD atlas-workflows
)


def seed_steps(kind: str) -> tuple[str, ...]:
    """Séquence ORDONNÉE des étapes du seed `kind` (PUR). Copie défensive.

    Seul le kind `banc` (jouet du socle) subsiste : depuis ADR 0111, les kinds `prod` et
    `banc-citation` (flux App-of-Apps citation) ont été retirés (geste côté atlas)."""
    if kind == "banc":
        return tuple(_BANC_STEPS)
    raise SeedError(f"seed kind inconnu : {kind!r} (attendu : banc)")


def run_seed(
    kind: str,
    config: SeedConfig,
    *,
    assert_target: Callable[[], None],
    do: Callable[[str], bool],
) -> SeedResult:
    """Joue le seed `kind` : GARDE d'abord, puis boucle PURE-TESTABLE sur ses étapes.

    Même moule que `path.run_path` / `bootstrap.run_bootstrap` : toute l'I/O INJECTÉE,
    la LOGIQUE (garde banc + ordre des étapes) testable sans cluster.

    - `assert_target()` : LA GARDE. Pour `kind="banc"` (seul kind subsistant, ADR 0111) la
      façade y branche `_assert_target_identity` (cible = banc Lima, jamais la prod). Un refus
      lève (→ SeedGuardRefused).
    - `do(step) -> bool` : exécute UNE étape (kubectl exec Gitea CLI, curl API…) ; True = ok.
      STUB en test (zéro appel Gitea réel) ; la façade y branche le réel (à câbler+prouver,
      `_BANC_TODO`). Une étape KO → fail-fast (SeedError).

    Renvoie un `SeedResult` (étapes franchies + verdict `done`)."""
    steps = seed_steps(kind)  # valide le kind AVANT de toucher la cible
    result = SeedResult(kind=kind)
    # GARDE en tête : la cible doit être prouvée AVANT le moindre geste mutant (ADR 0046).
    try:
        assert_target()
    except SeedGuardRefused:
        raise
    except Exception as exc:  # noqa: BLE001 — la garde façade peut lever hors hiérarchie
        raise SeedGuardRefused(f"seed `{kind}` REFUSÉ par la garde de cible : {exc}") from exc

    for step in steps:
        ok = bool(do(step))
        result.steps.append(SeedStep(step, ok))
        if not ok:
            raise SeedError(f"seed `{kind}` : étape `{step}` en échec")
    return result


# ── CE QUI RESTE À CÂBLER + PROUVER AU CLUSTER (TODO explicites, ADR 0034) ────────
# La LOGIQUE ci-dessus (garde banc, ordre des étapes, paramétrage YAML) est prouvée par
# tests STUBÉS. Le CONTENU réel de chaque étape (kubectl exec Gitea CLI, token API, Contents
# API, kubectl apply de l'Application jouet) MUTE un cluster vivant → preuve = RUN BANC
# (banc), IMPOSSIBLE dans cette session (NE PAS prétendre l'avoir faite).
_BANC_TODO = (
    "câblage do(step) banc sur gitea-init réel (kubectl exec/curl API) — à prouver au banc",
    "brancher _assert_target_identity (garde banc) en façade (topology.py)",
    "run banc gitea-init (jouet atlas-workflows) consigné — PREUVE DÉFINITIVE, reste à faire",
)


def banc_todo() -> tuple[str, ...]:
    """Frontière code-écrit / preuve-cluster DÉCLARÉE (honnêteté ADR 0034). Testable."""
    return _BANC_TODO
