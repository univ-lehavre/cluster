"""Seed des DONNÉES post-bootstrap (LOT 8, ADR 0097 §2/§3) — porte les DEUX scripts bash.

Deux étapes de DONNÉES (pas d'infra : Gitea/Argo CD sont posés par les playbooks) que
le bash portait, désormais en Python testable (ADR 0017) :

- BANC : `bench/lima/gitea-init.sh` (207 l.) — crée l'admin Gitea, un token API, l'org +
  le dépôt des workflows atlas, pousse la code-location jouet, pose le webhook et
  l'Application Argo CD. Garde **banc** : `_assert_bench_target` (la cible DOIT être le
  banc Lima, jamais la prod).
- PROD : `bootstrap/seed-app-of-apps.sh` (595 l.) — généralise le pattern en PROD (flux
  App-of-Apps citation : org/repo déclaratif, push de l'arbre atlas figé, déclaration
  `citation`, AppProject + Application racine). Garde **prod** : `assert_prod_target` (la
  cible DOIT être le cluster prod attendu — `seed-app-of-apps.sh:255`).

⚠️  HONNÊTETÉ (ADR 0034) — ces seeds MUTENT un cluster réel (Gitea, Argo CD). Leur preuve
DÉFINITIVE est un RUN BANC (banc) / RUN PROD (dirqual) que CE PALIER NE FAIT PAS. Ici :
la LOGIQUE (ordre des étapes, les DEUX gardes opposées, paramétrage 100 % YAML) est PURE
et prouvée par tests STUBÉS — toute l'I/O (kubectl exec, curl Gitea, git push) est
INJECTÉE (zéro appel Gitea réel). Le câblage réel + la preuve restent dans `_BANC_TODO`.

PARAMÉTRAGE 100 % YAML (ADR 0097 §3) : `SeedConfig.from_topology(topo)` lit les blocs
`gitea`/`atlas` du YAML — PLUS de `GITEA_*`/`CITATION_*`/`EXPECTED_CLUSTER`/`ATLAS_REPO_DIR`
lus de l'env. Les valeurs d'exemple (ADR 0023) restent les défauts quand le bloc est absent.
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
    # Banc (gitea-init.sh) : org/repo des workflows atlas.
    "org": "atlas",
    "repo": "workflows",
    # Prod (seed-app-of-apps.sh) : org/repo déclaratif + org/repo de code atlas.
    "org_cluster": "cluster",
    "repo_apps": "apps",
    "org_atlas": "atlas",
    "repo_atlas": "atlas",
    # Cible prod attendue (garde anti-mauvaise-cible, seed-app-of-apps.sh:157).
    "expected_cluster": "cluster-prod",
    # Image citation (ADR 0095) — nom générique cible des substitutions de digest.
    "citation_image_name": "registry:80/citation-dagster",
}


class SeedError(RuntimeError):
    """Le seed a échoué : garde refusée, étape Gitea/Argo CD en erreur, cible invalide."""


class SeedGuardRefused(SeedError):
    """La GARDE (banc ou prod) a refusé : la cible n'est pas celle attendue (ADR 0053/0046).

    Sous-classe distincte pour que l'appelant/les tests distinguent un REFUS de sécurité
    (cible non prouvée) d'un échec d'étape ordinaire — un refus = on n'a RIEN muté."""


@dataclass(frozen=True)
class SeedConfig:
    """Paramètres du seed LUS DU YAML (LOT 8) — plus de variables d'environnement.

    Réunit les paramètres des deux scripts bash (banc gitea-init / prod app-of-apps).
    `from_topology` dérive du YAML ; les défauts génériques (ADR 0023) comblent un bloc
    absent. IMMUABLE."""

    ns: str = _DEFAULTS["ns"]
    admin_user: str = _DEFAULTS["admin_user"]
    admin_email: str = _DEFAULTS["admin_email"]
    svc: str = _DEFAULTS["svc"]
    api: str = _DEFAULTS["api"]
    argocd_ns: str = _DEFAULTS["argocd_ns"]
    # Banc
    org: str = _DEFAULTS["org"]
    repo: str = _DEFAULTS["repo"]
    # Prod
    org_cluster: str = _DEFAULTS["org_cluster"]
    repo_apps: str = _DEFAULTS["repo_apps"]
    org_atlas: str = _DEFAULTS["org_atlas"]
    repo_atlas: str = _DEFAULTS["repo_atlas"]
    expected_cluster: str = _DEFAULTS["expected_cluster"]
    # atlas (prod) : code applicatif figé à une révision + digest immuable (ADR 0094/0095).
    atlas_repo_dir: str | None = None
    citation_revision: str | None = None
    citation_image_digest: str | None = None
    citation_image_name: str = _DEFAULTS["citation_image_name"]

    @classmethod
    def from_topology(cls, topo: Any) -> SeedConfig:
        """Construit une SeedConfig depuis les blocs `gitea:`/`atlas:` d'une Topology (PUR).

        LIT le YAML, jamais l'env (ADR 0097 §3). Un bloc/champ absent → défaut générique
        (ADR 0023). C'est l'unique pont topologie → seed : aucune autre source."""
        gitea = getattr(topo, "gitea", {}) or {}
        atlas = getattr(topo, "atlas", {}) or {}

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
            org_cluster=g("org_cluster"),
            repo_apps=g("repo_apps"),
            org_atlas=g("org_atlas"),
            repo_atlas=g("repo_atlas"),
            expected_cluster=atlas.get("expected_cluster", _DEFAULTS["expected_cluster"]),
            atlas_repo_dir=atlas.get("repo_dir"),
            citation_revision=atlas.get("citation_revision"),
            citation_image_digest=atlas.get("citation_image_digest"),
            citation_image_name=atlas.get("citation_image_name", _DEFAULTS["citation_image_name"]),
        )

    # ── URLs dérivées (PUR) — parité des deux scripts bash ───────────────────────
    def workflows_repo_url(self) -> str:
        """repoURL intra-cluster du dépôt de workflows (banc, gitea-init.sh:176)."""
        return f"{self.svc}/{self.org}/{self.repo}.git"

    def atlas_repo_url(self) -> str:
        """repoURL intra-cluster du dépôt de code atlas (prod, seed-app-of-apps.sh)."""
        return f"{self.svc}/{self.org_atlas}/{self.repo_atlas}.git"

    def apps_repo_url(self) -> str:
        """repoURL intra-cluster du dépôt déclaratif cluster/apps (prod)."""
        return f"{self.svc}/{self.org_cluster}/{self.repo_apps}.git"


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


# ── Étapes ORDONNÉES (les noms transcrivent les `echo "[gitea-init] N/7 …"` du bash et
#    les blocs ÉTAPE du seed prod). La LOGIQUE = l'ordre + les gardes ; les actions sont
#    déléguées au callback `do(step) -> bool` injecté (stub en test).
_BANC_STEPS = (
    "admin",  # 1 — admin Gitea (idempotent)
    "token",  # 2 — token API
    "org-repo",  # 3 — organisation + dépôt des workflows
    "push-code-location",  # 4 — push de la code-location jouet (Contents API)
    "webhook-secret",  # 5 — secret partagé webhook.gitea.secret (argocd-secret)
    "webhook",  # 6 — webhook Gitea → argocd-server/api/webhook
    "application",  # 7 — Application Argo CD atlas-workflows
)
_PROD_STEPS = (
    "admin-token",  # admin + token API (idempotent)
    "org-repo-apps",  # org/repo déclaratif cluster/apps
    "org-repo-atlas",  # org/repo de code atlas/atlas
    "push-atlas-tree",  # push GIT de l'arbre atlas figé (révision + digest injecté)
    "push-citation",  # rendu + push apps/citation.yaml (repoURL/targetRevision injectés)
    "appproject-root",  # AppProject cluster-apps + Application racine
)

# ── Variante « banc-citation » : le VRAI flux App-of-Apps citation, joué AU BANC.
#    C'est l'étape 1 « premier pas » de l'ADR 0095 (§1.a) prouvée au banc mono-nœud
#    local-path (ADR 0085) AVANT la prod, comme l'exige ADR 0034. Elle réutilise la
#    SÉQUENCE `_PROD_STEPS` — car le flux citation EST le flux App-of-Apps (org/repo
#    atlas, push de l'arbre atlas figé, apps/citation.yaml par digest, AppProject +
#    racine) ; ce qui DIFFÈRE de la prod n'est PAS l'ordre des étapes mais deux choses
#    INJECTÉES par la façade (topology.py), jamais gravées ici :
#      • la GARDE — `_assert_bench_target` (cible = banc Lima), OPPOSÉE à `assert_prod_target`
#        de la prod. On ne rend JAMAIS la garde prod franchissable par paramètre (ADR
#        0053/0084) : c'est une 3e variante à part entière, garde banc en propre.
#      • la CIBLE de déploiement — l'overlay kustomize `overlays/bench` (Secret SeaweedFS,
#        pas d'OBC Ceph) au lieu d'`overlays/prod` : au banc local-path la StorageClass
#        `rook-ceph-datalake` n'existe pas ; atlas fournit DÉJÀ cet overlay bench (frontière
#        ADR 0094 : cluster CHOISIT l'overlay, atlas FOURNIT les deux).
#    Partager la séquence garantit qu'une preuve banc VALIDE réellement le chemin prod
#    (même ordre, mêmes gardes de digest) — pas un chemin cousin qui divergerait.
_BANC_CITATION_STEPS = _PROD_STEPS


def seed_steps(kind: str) -> tuple[str, ...]:
    """Séquence ORDONNÉE des étapes du seed `kind` (PUR). Copie défensive."""
    if kind == "banc":
        return tuple(_BANC_STEPS)
    if kind == "prod":
        return tuple(_PROD_STEPS)
    if kind == "banc-citation":
        return tuple(_BANC_CITATION_STEPS)
    raise SeedError(f"seed kind inconnu : {kind!r} (attendu : banc | prod | banc-citation)")


def run_seed(
    kind: str,
    config: SeedConfig,
    *,
    assert_target: Callable[[], None],
    do: Callable[[str], bool],
) -> SeedResult:
    """Joue le seed `kind` : GARDE d'abord, puis boucle PURE-TESTABLE sur ses étapes.

    Même moule que `path.run_path` / `bootstrap.run_bootstrap` : toute l'I/O INJECTÉE,
    la LOGIQUE (garde opposée banc/prod + ordre des étapes) testable sans cluster.

    - `assert_target()` : LA GARDE. Pour `kind="banc"` ET `kind="banc-citation"` la façade
      y branche `_assert_bench_target` (cible = banc) ; pour `kind="prod"`, `assert_prod_target`
      (cible = cluster prod attendu). DEUX familles de gardes OPPOSÉES, comme l'exige le LOT 8 —
      un seed banc/banc-citation REFUSE la prod, un seed prod REFUSE le banc. Un refus lève
      (→ SeedGuardRefused). `banc-citation` joue la SÉQUENCE prod (le vrai flux App-of-Apps)
      mais sous garde BANC — la garde prod reste `cluster-prod`-only, jamais assouplie
      (ADR 0053/0084).
    - `do(step) -> bool` : exécute UNE étape (kubectl exec Gitea CLI, curl API, git push…) ;
      True = ok. STUB en test (zéro appel Gitea réel) ; la façade y branche le réel (à
      câbler+prouver, `_BANC_TODO`). Une étape KO → fail-fast (SeedError).

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


# ── Substitution de digest (PUR) — porte `substitute_image_digest` de seed-app-of-apps.sh
#    sans l'I/O (le bash faisait du grep/sed sur le clone ; ici on calcule la RÉFÉRENCE et
#    on EXIGE le contrat — atlas factorise ses deux jetons, frontière ADR 0094).


def citation_image_ref(image_name: str, digest: str) -> str:
    """Référence COMPLÈTE de l'image citation par DIGEST (immuable, ADR 0095 §2).

    `registry:80/citation-dagster@sha256:…` — pour `DAGSTER_CURRENT_IMAGE`. Lève
    `SeedError` si le digest n'est pas une chaîne `sha256:…` (frontière : on ne pousse
    PAS un tag mutable en se faisant passer pour un digest)."""
    if not digest.startswith("sha256:"):
        raise SeedError(
            f"digest citation invalide : {digest!r} (attendu `sha256:<hex>`, ADR 0095 §2)"
        )
    return f"{image_name}@{digest}"


# ── CE QUI RESTE À CÂBLER + PROUVER AU CLUSTER (TODO explicites, ADR 0034) ────────
# La LOGIQUE ci-dessus (gardes opposées, ordre des étapes, paramétrage YAML, ref digest)
# est prouvée par tests STUBÉS. Le CONTENU réel de chaque étape (kubectl exec Gitea CLI,
# token API, Contents API, git push de l'arbre atlas via port-forward, kubectl apply des
# Application) MUTE un cluster vivant → preuve = RUN BANC (banc) puis RUN PROD (dirqual),
# IMPOSSIBLE dans cette session (NE PAS prétendre l'avoir faite).
_BANC_TODO = (
    "câblage do(step) banc sur gitea-init réel (kubectl exec/curl API) — à prouver au banc",
    "câblage do(step) prod sur seed-app-of-apps réel (git push port-forward, kubectl apply) "
    "— à prouver sur dirqual",
    "câblage do(step) banc-citation en façade : do() du flux _PROD_STEPS ciblant l'overlay "
    "bench + injection digest, garde _assert_bench_target — à prouver au banc (ADR 0095 §1.a)",
    "brancher _assert_bench_target (banc/banc-citation) / assert_prod_target (prod) en façade "
    "(topology.py)",
    "run banc gitea-init + run banc-citation (citation réel) + run prod app-of-apps consignés "
    "— PREUVE DÉFINITIVE, reste à faire",
)


def banc_todo() -> tuple[str, ...]:
    """Frontière code-écrit / preuve-cluster DÉCLARÉE (honnêteté ADR 0034). Testable."""
    return _BANC_TODO
