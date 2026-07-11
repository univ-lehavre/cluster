"""Seed des DONNÉES post-bootstrap (LOT 8, ADR 0097 §2/§3) — porte les DEUX scripts bash.

Deux étapes de DONNÉES (pas d'infra : Gitea/Argo CD sont posés par les playbooks) que
le bash portait, désormais en Python testable (ADR 0017) :

- BANC : `bench/lima/gitea-init.sh` (207 l.) — crée l'admin Gitea, un token API, l'org +
  le dépôt des workflows atlas, pousse la code-location jouet, pose le webhook et
  l'Application Argo CD. Garde **banc** : `_assert_target_identity` (la cible DOIT être le
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

import re
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
    # Registry intra-cluster (ADR 0095/0023) : préfixe DÉRIVÉ des noms d'image code-location
    # (`<registry>/<name>-dagster`). Un code-location NOUVEAU n'exige AUCUN champ ici.
    "registry": "registry:80",
}


class SeedError(RuntimeError):
    """Le seed a échoué : garde refusée, étape Gitea/Argo CD en erreur, cible invalide."""


class SeedGuardRefused(SeedError):
    """La GARDE (banc ou prod) a refusé : la cible n'est pas celle attendue (ADR 0053/0046).

    Sous-classe distincte pour que l'appelant/les tests distinguent un REFUS de sécurité
    (cible non prouvée) d'un échec d'étape ordinaire — un refus = on n'a RIEN muté."""


@dataclass(frozen=True)
class CodeLocationSpec:
    """UNE code-location applicative atlas à seeder (ex : `citation`, `mediawatch`).

    Le seed n'est PLUS mono-citation : il porte une LISTE de ces specs (frontière ADR 0094 :
    atlas FOURNIT des code-locations `dataops/<name>-dagster/`, cluster les INSTANCIE). Le
    Sensor Argo Events (sensor-code-location.example.yaml) dérive DÉJÀ le `codeLocation` du
    chemin `dataops/<name>-dagster/` ; le SEED s'aligne sur ce modèle GÉNÉRIQUE.

    - `name`      : le nom court GÉNÉRIQUE (`citation`, `mediawatch`, ADR 0023) — signal
                    canonique dont dérivent l'image, les placeholders et le path de l'overlay.
    - `revision`  : le SHA git figé (`code-location.manifest.yaml:revision`, ADR 0094 §3).
    - `image_digest` : le digest immuable `sha256:…` (ADR 0095 §2). None au banc (overlay
                    `bench` sans placeholder de digest) → substitution best-effort (no-op)."""

    name: str
    revision: str | None = None
    image_digest: str | None = None
    registry: str = _DEFAULTS["registry"]

    @property
    def image_name(self) -> str:
        """Nom d'image DÉRIVÉ du name (`<registry>/<name>-dagster`) — jamais codé en dur.

        Convention atlas : `dataops/<name>-dagster/` ⇒ image `<registry>/<name>-dagster`
        (parité citation/mediawatch). Un code-location NOUVEAU n'exige aucun champ image."""
        return f"{self.registry}/{self.name}-dagster"


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
    # atlas (prod) : dépôt de code atlas COMMUN à toutes les code-locations (frontière 0094).
    atlas_repo_dir: str | None = None
    # LISTE des code-locations à seeder (citation, mediawatch…). PLUS de champs mono
    # `citation_*` : le seed est MULTI-code-location (ADR 0094/0095). Vide si le bloc atlas
    # ne déclare rien (un run banc-citation sans code-location déclarée échouera à l'étape
    # push-atlas-tree, honnête). `field(default_factory=tuple)` → immuable, hashable.
    code_locations: tuple[CodeLocationSpec, ...] = field(default_factory=tuple)

    @classmethod
    def from_topology(cls, topo: Any) -> SeedConfig:
        """Construit une SeedConfig depuis les blocs `gitea:`/`atlas:` d'une Topology (PUR).

        LIT le YAML, jamais l'env (ADR 0097 §3). Un bloc/champ absent → défaut générique
        (ADR 0023). C'est l'unique pont topologie → seed : aucune autre source.

        CODE-LOCATIONS (multi, ADR 0094/0095) — deux formes lues, avec RÉTROCOMPAT :
          • FORME MULTI (préférée) : `atlas.code_locations: [{name, revision, image_digest}, …]`
            — une entrée par code-location (citation ET mediawatch…). Le `name` dérive l'image
            et le path d'overlay ; aucun champ image en dur.
          • FORME MONO (héritée, banc.yaml existant) : `atlas.{citation_revision,
            citation_image_digest}` (SANS `code_locations`) → RECONSTRUITE en UNE code-location
            `name='citation'`. Ne casse NI les topos existantes NI le banc prouvé.
        Si `code_locations` est présent, il PRIME (la forme mono héritée est ignorée)."""
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
            # Cible prouvée de la garde prod (assert_prod_target). DÉRIVÉE du `stack_id`
            # (identité de l'instance, ADR 0108) quand `atlas.expected_cluster` n'est pas
            # déclaré : le `clusterName` kubeadm vaut désormais le stack_id (kubeadm-config.j2),
            # donc la garde prod (cluster == expected_cluster) et la garde d'identité
            # (contexte == stack_id) partagent UNE SEULE source de vérité. Explicite prime ;
            # sinon stack_id ; sinon fail-safe legacy `cluster-prod` (stack_id absent).
            expected_cluster=atlas.get(
                "expected_cluster",
                getattr(topo, "stack_id", "") or _DEFAULTS["expected_cluster"],
            ),
            atlas_repo_dir=atlas.get("repo_dir"),
            code_locations=_code_locations_from_atlas(atlas),
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


def _code_locations_from_atlas(atlas: dict[str, Any]) -> tuple[CodeLocationSpec, ...]:
    """Dérive la LISTE de CodeLocationSpec du bloc `atlas` YAML (PUR, avec rétrocompat).

    FORME MULTI `atlas.code_locations: [{name, revision, image_digest}, …]` → une spec par
    entrée (PRIME si présente). FORME MONO héritée `atlas.{citation_revision,
    citation_image_digest}` → UNE spec `name='citation'` (rétrocompat banc.yaml). Aucune des
    deux → tuple vide. Une entrée `code_locations` SANS `name` lève (un code-location doit
    porter son nom : c'est le signal canonique dont dérivent image/overlay, ADR 0094)."""
    entries = atlas.get("code_locations")
    if entries:
        specs = []
        for entry in entries:
            name = (entry or {}).get("name")
            if not name:
                raise SeedError(
                    f"code-location sans `name` dans atlas.code_locations : {entry!r} "
                    "(le name est le signal canonique dont dérivent image/overlay, ADR 0094)"
                )
            specs.append(
                CodeLocationSpec(
                    name=name,
                    revision=entry.get("revision"),
                    image_digest=entry.get("image_digest"),
                )
            )
        return tuple(specs)
    # Rétrocompat : bloc mono `citation_*` (SANS code_locations) → 1 code-location `citation`.
    revision = atlas.get("citation_revision")
    digest = atlas.get("citation_image_digest")
    if revision is not None or digest is not None:
        return (CodeLocationSpec(name="citation", revision=revision, image_digest=digest),)
    return ()


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
    # NB (ADR 0105) : les étapes `writeback-token` (Secret gitea-writeback-token, ns argo)
    # et `webhook-build` (webhook Gitea #2 → EventSource) — qui câblaient la chaîne
    # ÉVÉNEMENTIELLE (ADR 0095 §1.b) — sont RETIRÉES : le build node-side lit lui-même le
    # digest de ce qu'il pousse (aucun token de write-back), et il n'y a plus d'EventSource.
    "org-repo-apps",  # org/repo déclaratif cluster/apps
    "org-repo-atlas",  # org/repo de code atlas/atlas
    "push-atlas-tree",  # push GIT de l'arbre atlas figé (révision + digest injecté, overlay prod)
    # push-citation : nom HISTORIQUE d'une étape désormais MULTI-code-location — son handler
    # façade BOUCLE sur `config.code_locations` (rend/pousse apps/<name>.yaml pour chacun).
    # Une seule étape (la boucle est dans le handler, pas dans les steps → ordre stable).
    "push-citation",  # rendu + push apps/<name>.yaml pour CHAQUE code-location (repoURL/rev)
    "appproject-root",  # AppProject cluster-apps + Application racine
)

# ── Variante « banc-citation » : le VRAI flux App-of-Apps citation, joué AU BANC.
#    C'est l'étape 1 « premier pas » de l'ADR 0095 (§1.a) prouvée au banc mono-nœud
#    local-path (ADR 0085) AVANT la prod, comme l'exige ADR 0034. Elle REPREND la SÉQUENCE
#    `_PROD_STEPS` (le flux citation EST le flux App-of-Apps : org/repo atlas, push de
#    l'arbre atlas figé, apps/<cl>.yaml par digest, AppProject + racine).
#
#    banc-citation et prod PARTAGENT le cœur de séquence ; les SEULES divergences
#    (INJECTÉES par la façade topology.py, jamais gravées dans les steps) sont :
#      • la GARDE — `_assert_target_identity` (cible = banc Lima) au banc, OPPOSÉE à
#        `assert_prod_target` (cible = cluster-prod) en prod. On ne rend JAMAIS la garde
#        prod franchissable par paramètre (ADR 0053/0084) : deux façades distinctes.
#      • la CIBLE de déploiement — l'overlay kustomize `overlays/bench` (SeaweedFS, pas
#        d'OBC Ceph) au banc vs `overlays/prod` (OBC Ceph rook-ceph-datalake) en prod. Au
#        banc local-path la StorageClass `rook-ceph-datalake` n'existe pas ; atlas fournit
#        DÉJÀ les deux overlays (frontière ADR 0094 : cluster CHOISIT, atlas FOURNIT).
#    Partager le cœur de séquence garantit qu'une preuve banc VALIDE le chemin prod.
#    NB (ADR 0105) : le webhook #2 (build) et le token de write-back ont DISPARU du seed —
#    le build node-side (platform-build-images) lit lui-même le digest de ce qu'il pousse et
#    le seed l'injecte dans l'overlay ; plus aucune chaîne événementielle à amorcer.
_BANC_CITATION_STEPS = (
    "admin-token",  # admin + token API (idempotent)
    "org-repo-apps",  # org/repo déclaratif cluster/apps
    "org-repo-atlas",  # org/repo de code atlas/atlas
    "push-atlas-tree",  # push GIT de l'arbre atlas figé (révision + digest injecté)
    # NB (ADR 0105) : `webhook-build` (webhook #2 → EventSource) RETIRÉ — plus de chaîne
    # événementielle ; le build node-side + seed suffisent au déploiement par digest.
    "push-citation",  # rendu + push apps/<name>.yaml pour CHAQUE code-location (handler boucle)
    "appproject-root",  # AppProject cluster-apps + Application racine
)


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
      y branche `_assert_target_identity` (cible = banc) ; pour `kind="prod"`, `assert_prod_target`
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


# Jetons d'injection qu'atlas EXPOSE délibérément (frontière ADR 0094 : atlas FOURNIT les
# trous, cluster les REMPLIT ; cluster n'édite aucun champ qu'atlas n'a pas prévu d'offrir).
# Ils sont PROPRES à chaque code-location — atlas nomme `__CITATION_IMAGE__` /
# `__MEDIAWATCH_IMAGE__` (préfixe = nom en MAJUSCULES). On les DÉRIVE du nom, jamais énumérés.
def _placeholders_for(code_location_name: str) -> tuple[str, str]:
    """(placeholder_digest, placeholder_image) DÉRIVÉS du nom de code-location (PUR).

    `citation` → `(__CITATION_IMAGE_DIGEST__, __CITATION_IMAGE__)` ; `mediawatch` de même.
    Parité des jetons posés par atlas dans `deploy/overlays/prod/` (kustomization + patch)."""
    prefix = code_location_name.upper().replace("-", "_")
    return f"__{prefix}_IMAGE_DIGEST__", f"__{prefix}_IMAGE__"


def substitute_image_placeholders(
    text: str, code_location_name: str, image_name: str, digest: str
) -> tuple[str, int]:
    """Remplace, dans UN contenu de fichier, les 2 placeholders d'image d'un code-location (PUR).

    GÉNÉRIQUE (multi-code-location) : les jetons sont DÉRIVÉS de `code_location_name`
    (`__<NAME>_IMAGE_DIGEST__` / `__<NAME>_IMAGE__`) — parité citation ET mediawatch. Porte
    `substitute_image_digest` de seed-app-of-apps.sh SANS l'I/O (le bash faisait grep/sed sur
    le clone ; ici on transforme du TEXTE, la façade lit/écrit les fichiers). Renvoie
    `(texte_transformé, nb_substitutions)`. L'ORDRE importe : le placeholder DIGEST d'abord
    (sinon la substitution du préfixe `__<NAME>_IMAGE__` l'amputerait) — parité du commentaire
    bash. `digest` doit être un `sha256:…` (validé par `citation_image_ref`)."""
    ref = citation_image_ref(image_name, digest)  # valide le digest AVANT toute substitution
    ph_digest, ph_image = _placeholders_for(code_location_name)
    n = text.count(ph_digest) + text.count(ph_image)
    # DIGEST d'abord (le sha256 seul), puis IMAGE (la ref complète) — ordre critique.
    text = text.replace(ph_digest, digest)
    text = text.replace(ph_image, ref)
    return text, n


# Alias rétrocompat (mono-citation) — même signature enrichie du nom de code-location figé
# à `citation`. Conservé le temps qu'un appelant migre ; la façade utilise déjà le générique.
def substitute_citation_placeholders(text: str, image_name: str, digest: str) -> tuple[str, int]:
    """DÉPRÉCIÉ : `substitute_image_placeholders(text, 'citation', image_name, digest)`."""
    return substitute_image_placeholders(text, "citation", image_name, digest)


def render_code_location_declaration(
    example_text: str,
    code_location_name: str,
    atlas_repo_url: str,
    revision: str,
    *,
    overlay: str | None = None,
) -> str:
    """Rend `apps/<name>.yaml` depuis le patron GÉNÉRIQUE de code-location (PUR, ADR 0023).

    Le patron `citation.example.yaml` sert de PATRON GÉNÉRIQUE (ADR 0023) : il pointe
    `citation-dagster` (name + path). On le RÉÉCRIT pour `code_location_name` — `citation`
    reste un no-op, `mediawatch` réécrit `citation-dagster`→`mediawatch-dagster` PARTOUT
    (metadata.name ET le path `dataops/<name>-dagster/…`). C'est l'alignement sur le Sensor
    Argo Events qui dérive DÉJÀ le `codeLocation` du chemin `dataops/<name>-dagster/`.

    Porte `push_citation_declaration` (seed-app-of-apps.sh) sans l'I/O : injecte le `repoURL`
    atlas réel et le `targetRevision` (SHA figé) dans les lignes `spec.source.*` (indentation
    4 espaces, comme le `sed` ancré du bash). Lève `SeedError` si UNE injection ne matche pas
    (garde anti-injection ratée, parité des `grep -q` du bash), ou si le nom du code-location
    n'apparaît pas dans le rendu (garde : la réécriture `<name>-dagster` DOIT avoir mordu).

    `overlay` (banc-citation : `bench`) RÉÉCRIT le `path:` de l'overlay kustomize — le patron
    pointe `overlays/prod` (SC Ceph, OBC) ; au banc local-path il faut `overlays/bench` (Secret
    SeaweedFS, pas d'OBC — décision D2). None = on garde le path du patron (prod)."""
    # 1) Réécriture GÉNÉRIQUE `citation-dagster` → `<name>-dagster` (metadata.name + path).
    #    `citation` = no-op ; tout autre nom instancie le patron pour SA code-location.
    target = f"{code_location_name}-dagster"
    out = example_text.replace("citation-dagster", target)
    # 2) Injections d'instance (repoURL + targetRevision figé), ancrées 4 espaces.
    out = re.sub(r"(?m)^( {4})repoURL:.*$", rf"\g<1>repoURL: {atlas_repo_url}", out)
    out = re.sub(r"(?m)^( {4})targetRevision:.*$", rf"\g<1>targetRevision: {revision}", out)
    if overlay is not None:
        out = re.sub(
            r"(?m)^( {4})path: (.*/deploy/overlays/)\w+$", rf"\g<1>path: \g<2>{overlay}", out
        )
        if f"/deploy/overlays/{overlay}" not in out:
            raise SeedError(f"injection overlay `{overlay}` ratée dans {target}.yaml (non matché)")
    if f"repoURL: {atlas_repo_url}" not in out:
        raise SeedError("injection repoURL ratée (motif non matché)")
    if f"targetRevision: {revision}" not in out:
        raise SeedError("injection targetRevision ratée (motif non matché)")
    if target not in out:
        raise SeedError(f"réécriture `{target}` ratée : nom du code-location absent du rendu")
    return out


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
    "câblage do(step) banc-citation en façade : do() du flux App-of-Apps ciblant l'overlay "
    "bench + injection digest, garde _assert_target_identity — à prouver au banc (ADR 0095 §1.a)",
    "brancher _assert_target_identity (banc/banc-citation) / assert_prod_target (prod) en façade "
    "(topology.py)",
    "run banc gitea-init + run banc-citation (citation réel) + run prod app-of-apps consignés "
    "— PREUVE DÉFINITIVE, reste à faire",
)


def banc_todo() -> tuple[str, ...]:
    """Frontière code-écrit / preuve-cluster DÉCLARÉE (honnêteté ADR 0034). Testable."""
    return _BANC_TODO
