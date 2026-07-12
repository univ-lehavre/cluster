"""Graphe de topologie Python FIGÉ (ADR 0096 §1) — porté de `rollback-lib.sh`.

Le graphe atomique des composants (arêtes + 4 dimensions de périmètre de rollback
+ profil + poids de tie-break) vit aujourd'hui en bash dans la partie pure de
[`bench/lima/rollback-lib.sh`](../bench/lima/rollback-lib.sh) (`component_deps`,
`component_namespace`, `component_targeted`, `component_crd_groups`,
`component_has_nodeside`, `component_profile`, `component_alias_weight`,
`component_expand_alias`, `topo_sort`, `phase_of_component`, `phase_closure`). Ce
module en est le PORTAGE Python, **À CÔTÉ** du bash (lot 2 du plan de refonte) : on
ne bascule RIEN, le bash reste la source d'exécution ; ce module est prouvé
BYTE-IDENTIQUE au bash par `tests/test_graph.py` (qui rejoue les invariants de
[`bench/unit/rollback.bats`](../bench/unit/rollback.bats) ET compare au VRAI bash
en subprocess, tous composants, les deux backends).

Pourquoi Python figé et pas YAML : le graphe est DÉJÀ du Python testé (via
rollback.bats) ; le porter en `@dataclass(frozen=True)` garde unittest comme
garde-fou (ADR 0017). Valeurs génériques (ADR 0023).

PIÈGE byte-identité (réserve ADR 0096 §1) : le tie-break de `topo_sort` est une
clé `'%s%03d' % (poids, rang)` comparée lexicalement (opérateur bash ``\\<``, octet à
octet en C locale). On reproduit À L'OCTET : la clé est une `str`, le tri une
comparaison de `str` Python (même collation byte-wise pour de l'ASCII). Le `rang`
est l'index dans `COMPONENT_ALL` (ordre lexical stable du catalogue), zéro-paddé 3.

Les jetons de stockage sont BACKEND-CONDITIONNELS (ADR 0069) : une arête « → SC »
se résout en `sc` (Ceph) ou `storage-simple` (local-path) ; une arête « → S3 » en
`datalake` (Ceph) ou `seaweedfs` (local-path). Ces jetons sont résolus À LA LECTURE
par `backend` (comme `_rb_sc`/`_rb_s3` du bash), pas figés dans le catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# ── Backend de stockage ─────────────────────────────────────────────────────
# DÉFAUT ceph → graphe byte-identique à l'historique quand aucun env n'est exporté
# (cf. _rb_backend du bash : STORAGE_BACKEND non `local-path` → ceph).

CEPH = "ceph"
LOCAL_PATH = "local-path"


def _backend(backend: str | None) -> str:
    """Normalise le backend comme `_rb_backend` : `local-path` ou (tout le reste) `ceph`."""
    return LOCAL_PATH if backend == LOCAL_PATH else CEPH


def _resolve_sc(backend: str) -> str:
    """Jeton STOCKAGE BLOC résolu par backend (= `_rb_sc`) : sc (Ceph) | storage-simple."""
    return "storage-simple" if _backend(backend) == LOCAL_PATH else "sc"


def _resolve_s3(backend: str) -> str:
    """Jeton BACKING S3 résolu par backend (= `_rb_s3`) : datalake (Ceph) | seaweedfs."""
    return "seaweedfs" if _backend(backend) == LOCAL_PATH else "datalake"


# Sentinelles de jeton conditionnel utilisées dans les `deps` du catalogue : résolues
# par `_resolve_sc`/`_resolve_s3` au moment de lire `component_deps(comp, backend)`.
_SC = "@sc"  # → sc (ceph) | storage-simple (local-path)
_S3 = "@s3"  # → datalake (ceph) | seaweedfs (local-path)

# Cible kubectl d'un signal de SANTÉ : (kind, name, namespace|None, ready). `ready` vaut
# True (readyReplicas≥1), False (présence seule) ou "phase" (status.phase == "Ready").
# Consommée par `scripts/topology.py` (_resource_healthy / _LAYER_SIGNAL, qui DÉRIVE de ce
# graphe) — voir `LAYER_SIGNAL` plus bas.
SignalTarget = tuple[str, str, str | None, bool | str]


@dataclass(frozen=True)
class Component:
    """Un composant atomique du graphe (ADR 0096 §1).

    Porte ce qu'Ansible ne dit pas : l'ORDRE inter-composant (`deps`/`weight`), le
    PÉRIMÈTRE de rollback (4 dimensions `namespace`/`targeted`/`crd_groups`/
    `has_nodeside`) et le PROFIL de stockage (`profile`). `role` = rôle Ansible qui
    le porte (None pour un composant socle / une donnée sans rôle dédié) ; métadonnée
    consommée par le futur `check_topology.py` (lot 8), ABSENTE du bash → n'entre PAS
    dans la byte-identité.

    `deps` peut contenir les jetons conditionnels `@sc`/`@s3` (résolus par backend).
    """

    name: str
    deps: tuple[str, ...] = ()
    role: str | None = None
    profile: str = "always"  # always|ceph|leger      (= component_profile)
    weight: int = 9  # tie-break topo lexico   (= component_alias_weight)
    namespace: str | None = None  # périmètre rollback      (= component_namespace)
    targeted: tuple[str, ...] = ()  # ressources ciblées      (= component_targeted)
    crd_groups: tuple[str, ...] = ()  # groupes CRD             (= component_crd_groups)
    has_nodeside: bool = False  # wipe disque node-side   (= component_has_nodeside)
    # Signal de SANTÉ canonique : la ressource k8s du DERNIER maillon dont la PRÉSENCE +
    # l'état READY prouvent que la couche est posée ET saine (cible kubectl complète
    # `(kind, name, namespace|None, ready)` — cf. SignalTarget). PORTÉ sur le composant qui
    # EST ce dernier maillon (loki pour monitoring, marquez pour dataops, argocd pour gitops…) ;
    # None = composant non discriminant (un maillon amont, dont la présence ne PROUVE pas la
    # couche). Métadonnée ABSENTE du bash (comme `role`) → n'entre PAS dans la byte-identité.
    # 4e champ = critère : True → readyReplicas≥1 (workload répliqué) ; False → présence seule
    # (CRD type Application, StorageClass cluster-scoped) ; "phase" → status.phase == "Ready"
    # (CR opérateur Rook sans replicas : CephCluster, CephObjectStore).
    signal: SignalTarget | None = None

    def resolved_deps(self, backend: str) -> tuple[str, ...]:
        """Arêtes directes avec les jetons `@sc`/`@s3` résolus par `backend`."""
        sc = _resolve_sc(backend)
        s3 = _resolve_s3(backend)
        out: list[str] = []
        for d in self.deps:
            if d == _SC:
                out.append(sc)
            elif d == _S3:
                out.append(s3)
            else:
                out.append(d)
        return tuple(out)


# ── CATALOGUE des composants atomiques (porté case par case du bash) ─────────
# L'ORDRE de cette liste EST `component_all` (ordre lexical stable du catalogue) :
# il fixe le `rank` (tie-break 2ⁿᵈ de topo_sort) → ne pas réordonner sans re-prouver
# la byte-identité.

_CATALOGUE: tuple[Component, ...] = (
    Component(
        name="bootstrap",
        role=None,  # socle : bootstrap → kube-system (ns NON supprimable)
        has_nodeside=True,
        weight=0,
    ),
    Component(
        name="build-images",
        role="platform-build-images",  # UN rôle, N builds (ADR 0096 angle mort)
        has_nodeside=True,
        weight=0,
    ),
    Component(
        name="gateway-api",
        role=None,  # CRD gateway posées au socle
        crd_groups=(
            "gateway.networking.k8s.io",
        ),  # possédé ici, EMPRUNTÉ par registry/gitea/argocd
        weight=0,
    ),
    Component(
        name="cert-manager",
        role="platform-cert-manager",
        namespace="cert-manager",
        targeted=(
            "clusterissuer.cert-manager.io selfsigned-bootstrap",
            "clusterissuer.cert-manager.io internal-ca",
        ),
        crd_groups=("cert-manager.io", "acme.cert-manager.io"),
        weight=0,
    ),
    Component(
        name="metrics-server",
        role="platform-metrics-server",
        targeted=(
            "-n kube-system deployment.apps metrics-server",
            "apiservice.apiregistration.k8s.io v1beta1.metrics.k8s.io",
        ),
        # Santé de la couche metrics-server : son Deployment Ready (couche d'infra à part).
        signal=("deployment", "metrics-server", "kube-system", True),
        weight=0,
    ),
    Component(
        name="ceph",
        role="platform-ceph-cluster",
        profile="ceph",
        namespace="rook-ceph",
        crd_groups=("ceph.rook.io", "objectbucket.io"),  # EMPRUNTÉ par sc/datalake/s3-backing-*
        has_nodeside=True,
        # CR Rook : la santé est dans `status.phase` (pas de readyReplicas) — sans ce signal,
        # `_observed_layers` ne voyait JAMAIS ceph monté sur un banc Ceph pourtant up (#227).
        signal=("cephcluster.ceph.rook.io", "rook-ceph", "rook-ceph", "phase"),
        weight=1,
    ),
    Component(
        name="sc",
        role="platform-ceph-storageclasses",
        deps=("ceph",),
        profile="ceph",
        targeted=(
            "storageclass.storage.k8s.io rook-ceph-block-replicated",
            "storageclass.storage.k8s.io rook-ceph-block-ec-delete",
            "storageclass.storage.k8s.io rook-ceph-block-ec",
            "storageclass.storage.k8s.io rook-cephfs",
        ),
        # StorageClass cluster-scoped → présence seule (pas de readyReplicas ni de phase).
        signal=("storageclass", "rook-ceph-block-replicated", None, False),
        weight=2,
    ),
    Component(
        name="datalake",
        role="platform-ceph-datalake",
        deps=("ceph", "sc"),
        profile="ceph",
        targeted=(
            "-n rook-ceph cephobjectstore.ceph.rook.io datalake",
            "-n rook-ceph cephobjectstoreuser.ceph.rook.io datalake",
            "storageclass.storage.k8s.io rook-ceph-datalake",
        ),
        # CR Rook : santé dans `status.phase` (comme ceph).
        signal=("cephobjectstore.ceph.rook.io", "datalake", "rook-ceph", "phase"),
        weight=3,
    ),
    Component(
        name="seaweedfs",
        role="platform-seaweedfs",
        deps=("storage-simple",),
        profile="leger",
        namespace="s3",
        weight=3,
    ),
    Component(
        name="storage-simple",
        role="platform-local-path",
        profile="leger",
        # SC local-path + le provisioner dans kube-system (ns non supprimable).
        targeted=(
            "storageclass.storage.k8s.io local-path",
            "-n kube-system deployment.apps local-path-provisioner",
        ),
        # Santé : le provisioner Deployment Ready (le SC seul ne prouve pas la couche servante).
        signal=("deployment", "local-path-provisioner", "local-path-storage", True),
        weight=2,
    ),
    Component(
        name="registry",
        role="platform-registry",
        deps=("gateway-api", _SC),
        namespace="registry",
        weight=6,
    ),
    Component(
        name="s3-backing-loki",
        role="platform-s3-bucket",  # 1 rôle → 3 composants s3-backing-* (ADR 0096 §2)
        deps=(_S3,),
        profile="ceph",
        # OBC dans rook-ceph (ns d'autrui) → targeted du PRODUCTEUR.
        targeted=("-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets",),
        weight=4,
    ),
    Component(
        name="prometheus-stack",
        role="platform-monitoring",
        deps=("cert-manager", _SC),
        namespace="monitoring",  # POSSESSEUR du ns monitoring
        crd_groups=("monitoring.coreos.com",),
        weight=4,
    ),
    Component(
        name="loki",
        role="platform-loki",
        deps=("prometheus-stack", "s3-backing-loki", _SC),
        targeted=(
            "-n monitoring statefulset.apps loki",
            "-n monitoring configmap loki",
            "-n monitoring secret loki-s3-creds",
        ),
        # DERNIER maillon de la couche monitoring : StatefulSet loki Ready (absent si
        # SeaweedFS/S3 manque) — un ns monitoring présent SANS Loki Ready n'est PAS sain.
        signal=("statefulset", "loki", "monitoring", True),
        weight=4,
    ),
    Component(
        name="cnpg-operator",
        role="platform-cnpg",  # 1 rôle → 4 composants cnpg-* (ADR 0096 §2)
        deps=("cert-manager",),
        namespace="cnpg-system",  # ≠ postgres (l'oubli historique)
        crd_groups=("postgresql.cnpg.io",),  # EMPRUNTÉ par cnpg-cluster-pg
        weight=6,
    ),
    Component(
        name="barman-plugin",
        role="platform-cnpg",
        deps=("cnpg-operator", "cert-manager"),
        targeted=("-n cnpg-system deployment.apps barman-cloud",),
        crd_groups=("barmancloud.cnpg.io",),  # EMPRUNTÉ par cnpg-cluster-pg
        weight=6,
    ),
    Component(
        name="cnpg-secrets",
        role="platform-cnpg",
        weight=6,
    ),
    Component(
        name="s3-backing-cnpg",
        role="platform-s3-bucket",
        deps=(_S3,),
        profile="ceph",
        targeted=("-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups",),
        weight=6,
    ),
    Component(
        name="cnpg-cluster-pg",
        role="platform-cnpg",
        deps=("cnpg-operator", "barman-plugin", "cnpg-secrets", "s3-backing-cnpg", _SC),
        namespace="postgres",  # POSSESSEUR unique de postgres
        targeted=(
            "-n postgres cluster.postgresql.cnpg.io pg",
            "-n postgres objectstore.barmancloud.cnpg.io pg-backup",
            "-n postgres scheduledbackup.postgresql.cnpg.io pg-daily",
        ),
        weight=6,
    ),
    Component(
        name="dagster",
        role="platform-dagster",
        deps=("cnpg-cluster-pg", "registry", "build-images"),
        namespace="dagster",
        weight=6,
    ),
    Component(
        name="marquez",
        role="platform-marquez",
        deps=("cnpg-cluster-pg", "registry", "build-images"),
        namespace="marquez",
        # DERNIER maillon de dataops (registry + CNPG + Dagster PUIS Marquez) : Deployment
        # marquez Ready ⇒ tout l'amont l'est aussi. Avec Dagster seul, la couche passait « ✓ »
        # alors que Marquez manquait → « DataOps complet » mensonger.
        signal=("deployment", "marquez", "marquez", True),
        weight=6,
    ),
    Component(
        name="mlflow",
        role="platform-mlflow",
        deps=("cnpg-cluster-pg", "s3-backing-mlflow", "registry", "build-images"),
        namespace="mlflow",  # POSSESSEUR du ns mlflow (layer autonome)
        # Serveur MLflow : Deployment `mlflow` (nom posé par platform/mlflow/mlflow.yaml) Ready.
        signal=("deployment", "mlflow", "mlflow", True),
        weight=8,
    ),
    Component(
        name="s3-backing-mlflow",
        role="platform-s3-bucket",
        deps=(_S3,),
        profile="ceph",
        # OBC de l'artefact store MLflow dans rook-ceph (ns d'autrui) → targeted du
        # PRODUCTEUR. component_profile=ceph le filtre hors du graphe local-path.
        targeted=("-n rook-ceph objectbucketclaim.objectbucket.io mlflow-artifacts",),
        weight=8,
    ),
    Component(
        name="portal",
        role="platform-portal",
        deps=("registry", "build-images"),
        namespace="portal",  # POSSESSEUR du ns portal (layer autonome)
        # Portail : Deployment `portal` (nom posé par platform/portal/portal.yaml) Ready.
        signal=("deployment", "portal", "portal", True),
        weight=9,
    ),
    # NB (ADR 0110 amendé) : le composant/phase `citation` (BUILD node-side de l'image de
    # code) a été RETIRÉ — l'image de code se build hors cluster (poste, atlas build-code.sh).
    # NB (ADR 0111) : le DÉPLOIEMENT de citation (instanciation de l'Application Argo CD) est
    # désormais porté par ATLAS, pas par cluster (voir la note après le composant `argocd`).
    Component(
        name="gitea",
        role="platform-gitea",
        deps=("cert-manager", "gateway-api", _SC),
        namespace="gitea",
        weight=5,
    ),
    Component(
        name="argocd",
        role="platform-argocd",
        deps=("cert-manager", "gateway-api", "gitea"),
        namespace="argocd",
        targeted=("-n argocd appproject.argoproj.io atlas",),
        crd_groups=("argoproj.io",),  # EMPRUNTÉ par gitops-seed
        # DERNIER maillon de la couche gitops : Deployment argocd-server Ready (platform-argocd).
        signal=("deployment", "argocd-server", "argocd", True),
        weight=5,
    ),
    Component(
        name="gitops-seed",
        role=None,  # données dans Gitea + Application Argo CD (pas de rôle dédié)
        deps=("argocd", "gitea", "build-images"),
        # Application `atlas-workflows` (PAS `atlas` = l'AppProject, cf. composant argocd).
        targeted=("-n argocd applications.argoproj.io atlas-workflows",),
        # Application Argo CD `atlas-workflows` (CRD sans replicas) → présence seule.
        signal=("application", "atlas-workflows", "argocd", False),
        weight=7,
    ),
    # NB (ADR 0111) : le composant `gitops-seed-citation` (instanciation de l'Application Argo
    # CD `citation-dagster` : git push arbre atlas + apps/citation.yaml + Application) a été
    # RETIRÉ. L'instanciation de l'Application d'une code-location APPLICATIVE passe désormais
    # côté ATLAS (le geste de déploiement atlas crée+pousse son Application) — cluster ne
    # l'instancie plus (nestor ne touche pas au code atlas, ADR 0108). Le composant `gitops-seed`
    # (code-location JOUET `atlas-workflows`, un artefact du socle) RESTE ci-dessus.
    # NB (ADR 0110 amendé) : le composant `buildkit` (moteur de build IN-POD) a été RETIRÉ —
    # PodSecurity baseline (k8s ≥ 1.34) refuse le seccomp Unconfined du rootless, et le build
    # de code est déplacé HORS cluster (poste, atlas build-code.sh). Plus de rôle platform-buildkit.
)
# NB (ADR 0105) : la couche `eventful` (build applicatif événementiel in-cluster, Argo Events +
# Argo Workflows + NATS, ADR 0095 §1.b) a été RETIRÉE — le build node-side (platform-build-images,
# §1.a) est le mécanisme terminal ; le seed injecte le digest, Argo CD déploie. Plus de couche ici.

# Index nom → Component, ET ordre stable du catalogue (= component_all).
COMPONENTS: dict[str, Component] = {c.name: c for c in _CATALOGUE}
COMPONENT_ALL: tuple[str, ...] = tuple(c.name for c in _CATALOGUE)
# Rang stable de chaque composant (index dans COMPONENT_ALL) — tie-break 2ⁿᵈ de topo_sort.
_RANK: dict[str, int] = {name: i for i, name in enumerate(COMPONENT_ALL)}


# ── Projections au grain COMPOSANT (= les fonctions pures du bash) ───────────


def component_known(comp: str) -> bool:
    """True si `comp` est un composant atomique connu (= component_known → rc 0)."""
    return comp in COMPONENTS


def component_deps(comp: str, backend: str = CEPH) -> list[str]:
    """Dépendances DIRECTES de `comp`, jetons de stockage résolus par `backend`.

    = `component_deps` du bash. Composant inconnu → liste vide (branche `*` du case).
    """
    c = COMPONENTS.get(comp)
    return list(c.resolved_deps(backend)) if c is not None else []


def component_namespace(comp: str) -> str:
    """Le (≤1) namespace que `comp` POSSÈDE, ou '' (= component_namespace)."""
    c = COMPONENTS.get(comp)
    return c.namespace if c is not None and c.namespace else ""


def component_targeted(comp: str) -> list[str]:
    """Ressources CIBLÉES de `comp` (une par ligne, = component_targeted)."""
    c = COMPONENTS.get(comp)
    return list(c.targeted) if c is not None else []


def component_crd_groups(comp: str) -> list[str]:
    """Groupes API dont `comp` POSSÈDE les CRD (= component_crd_groups)."""
    c = COMPONENTS.get(comp)
    return list(c.crd_groups) if c is not None else []


def component_has_nodeside(comp: str) -> bool:
    """True si `comp` laisse un état NODE-SIDE (= component_has_nodeside == 'yes')."""
    c = COMPONENTS.get(comp)
    return bool(c is not None and c.has_nodeside)


def component_profile(comp: str) -> str:
    """Profil de stockage de `comp` : always|ceph|leger (= component_profile).

    Composant inconnu → 'always' (branche `*` du case bash)."""
    c = COMPONENTS.get(comp)
    return c.profile if c is not None else "always"


def component_alias_weight(comp: str) -> int:
    """Poids d'ALIAS de `comp` (tie-break principal, = component_alias_weight).

    Composant inconnu → 9 (repli générique du case bash)."""
    c = COMPONENTS.get(comp)
    return c.weight if c is not None else 9


# ── Alias de phase (= component_expand_alias, backend-conditionnel) ──────────
# Un alias = l'UNION (non ordonnée) de composants. Les arêtes de stockage du
# graphe les tirent en dépendance ; SEULS les alias eux-mêmes diffèrent par
# backend (monitoring pose AUSSI seaweedfs en local-path — le « when: » de l'alias).

_ALIASES_BASE: dict[str, tuple[str, ...]] = {
    "ceph": ("ceph",),
    "sc": ("sc",),
    "datalake": ("datalake",),
    "storage-simple": ("storage-simple",),
    "metrics-server": ("metrics-server",),
    "monitoring": ("prometheus-stack", "loki", "s3-backing-loki"),
    "dataops": (
        "registry",
        "cnpg-operator",
        "barman-plugin",
        "cnpg-secrets",
        "s3-backing-cnpg",
        "cnpg-cluster-pg",
        "dagster",
        "marquez",
    ),
    "mlflow": ("mlflow", "s3-backing-mlflow"),
    "portal": ("portal",),
    "gitops": ("gitea", "argocd"),
    "gitops-seed": ("gitops-seed",),
    # atlas-ceph = clôture Ceph SANS metrics-server (monté par l'alias léger
    # seulement) ; l'ordre vient de topo_sort, pas de cette énumération.
    "atlas-ceph": (
        "bootstrap",
        "build-images",
        "gateway-api",
        "cert-manager",
        "ceph",
        "sc",
        "datalake",
        "registry",
        "s3-backing-loki",
        "prometheus-stack",
        "loki",
        "cnpg-operator",
        "barman-plugin",
        "cnpg-secrets",
        "s3-backing-cnpg",
        "cnpg-cluster-pg",
        "dagster",
        "marquez",
        "gitea",
        "argocd",
        "gitops-seed",
    ),
}


def component_expand_alias(alias: str, backend: str = CEPH) -> list[str]:
    """Composants désignés par un ALIAS de phase (= component_expand_alias).

    Backend-conditionnel : en local-path, `monitoring` pose AUSSI `seaweedfs` (le
    backing S3 de Loki/CNPG) — le « when: » vit dans l'alias (ADR 0066). En ceph
    l'alias est byte-identique. Alias inconnu → liste vide (branche `*`).
    """
    comps = list(_ALIASES_BASE.get(alias, ()))
    if alias == "monitoring" and _backend(backend) == LOCAL_PATH:
        comps.append("seaweedfs")
    return comps


# ── topo_sort — tri topologique pur, byte-identique au bash ──────────────────


class TopoCycleError(RuntimeError):
    """`topo_sort` a détecté un cycle (composants non ordonnables) — = bash rc 1."""


def topo_sort(wanted: list[str], backend: str = CEPH) -> list[str]:
    """Tri TOPOLOGIQUE de la sous-clôture des composants `wanted` (= topo_sort bash).

    Une dépendance sort AVANT son dépendant (ordre de MONTAGE). Tie-break entre nœuds
    prêts = clé `'%s%03d' % (poids, rang)` comparée lexicalement — reproduit À L'OCTET
    le `\\<` bash (str Python, collation byte-wise sur de l'ASCII). Détecte les cycles
    (lève `TopoCycleError`). Kahn sur l'ensemble fermé par dépendance.
    """
    # 1. Fermeture transitive : BFS sur les deps (même parcours que le bash).
    closed: list[str] = []
    in_closed: set[str] = set()
    stack: list[str] = list(wanted)
    while stack:
        c = stack.pop(0)
        if c in in_closed:
            continue
        in_closed.add(c)
        closed.append(c)
        for d in component_deps(c, backend):
            if d not in in_closed:
                stack.append(d)

    # 2. Degré entrant : nombre de deps de c qui sont dans la clôture.
    indeg: dict[str, int] = {c: 0 for c in closed}
    for c in closed:
        for d in component_deps(c, backend):
            if d in in_closed:
                indeg[c] += 1

    # 3. Kahn : à chaque pas, émettre LE meilleur nœud prêt (indeg 0), trié par la
    #    clé triable (poids 1 chiffre puis rang zéro-paddé 3) — un seul à la fois.
    order: list[str] = []
    emitted: set[str] = set()
    total = len(closed)
    while len(order) < total:
        best: str | None = None
        best_key = ""
        for c in closed:
            if c in emitted:
                continue
            if indeg[c] != 0:
                continue
            key = f"{component_alias_weight(c)}{_RANK.get(c, 999):03d}"
            if best is None or key < best_key:
                best = c
                best_key = key
        if best is None:
            break  # plus aucun nœud prêt → cycle (détecté ci-dessous)
        order.append(best)
        emitted.add(best)
        for x in closed:
            if x in emitted:
                continue
            for d in component_deps(x, backend):
                if d == best:
                    indeg[x] -= 1

    if len(order) != total:
        raise TopoCycleError("topo_sort: cycle détecté (composants non ordonnables)")
    return order


# ── Projection PHASE (= _ROUNDTRIP_PHASES / phase_of_component / phase_closure) ─

# Les phases (alias) que roundtrip éprouve. metrics-server inclus (couche à part).
ROUNDTRIP_PHASES: tuple[str, ...] = (
    "ceph",
    "sc",
    "datalake",
    "metrics-server",
    "monitoring",
    "dataops",
    "mlflow",
    "gitops",
    "gitops-seed",
    "portal",
)


def phase_of_component(comp: str, backend: str = CEPH) -> str:
    """La phase (alias) qui contient `comp`, ou '' si `comp` est un composant SOCLE
    qu'aucune phase roundtrip ne monte seul (= phase_of_component).

    Première phase de ROUNDTRIP_PHASES qui le contient.
    """
    for ph in ROUNDTRIP_PHASES:
        if comp in component_expand_alias(ph, backend):
            return ph
    return ""


# PHASE_COMPONENTS : projection figée alias → composants (les phases roundtrip),
# au backend Ceph par défaut (rétro-compat) — consommée par les lots aval.
PHASE_COMPONENTS: dict[str, list[str]] = {
    ph: component_expand_alias(ph, CEPH) for ph in ROUNDTRIP_PHASES
}


class PhaseUnknownError(RuntimeError):
    """`phase_closure` sur une phase hors ROUNDTRIP_PHASES (= bash rc 1)."""


def phase_closure(phase: str, backend: str = CEPH) -> list[str]:
    """Clôture DESCENDANTE de `phase`, en ordre de MONTAGE (= phase_closure).

    `phase` + toute phase dont un composant dépend transitivement d'un composant de
    `phase`. Dérivée du graphe atomique → reproduit l'ancien `_DEPENDENTS`. Phase
    inconnue → lève `PhaseUnknownError` (= bash rc 1).
    """
    if phase not in ROUNDTRIP_PHASES:
        raise PhaseUnknownError(phase)
    comps_x = set(component_expand_alias(phase, backend))

    # 1. Phases Y dont un composant dépend transitivement d'un composant de X.
    in_closure: list[str] = [phase]
    in_closure_set: set[str] = {phase}
    for y in ROUNDTRIP_PHASES:
        if y == phase:
            continue
        touches = False
        for cy in component_expand_alias(y, backend):
            # Clôture transitive des dépendances de cy.
            seen: set[str] = set()
            stack = [cy]
            while stack:
                c = stack.pop(0)
                if c in seen:
                    continue
                seen.add(c)
                stack.extend(component_deps(c, backend))
            if seen & comps_x:
                touches = True
                break
        if touches and y not in in_closure_set:
            in_closure.append(y)
            in_closure_set.add(y)

    # 2. Ordonner par ordre de MONTAGE : topo_sort des composants de la clôture,
    #    projeté sur les phases (première apparition).
    allcomps: list[str] = []
    for y in in_closure:
        allcomps.extend(component_expand_alias(y, backend))
    emitted: list[str] = []
    emitted_set: set[str] = set()
    for c in topo_sort(allcomps, backend):
        ph = phase_of_component(c, backend)
        if not ph or ph not in in_closure_set:
            continue
        if ph not in emitted_set:
            emitted.append(ph)
            emitted_set.add(ph)
    return emitted


def phase_involves_storage(phase: str, backend: str = CEPH) -> bool:
    """True si la clôture de `phase` touche une couche de STOCKAGE (= phase_involves_storage).

    ceph/sc/datalake dans la clôture → True (clôture large, opt-in `--full`).
    Phase inconnue → False (le bash boucle sur une clôture vide → rc 1)."""
    try:
        cl = phase_closure(phase, backend)
    except PhaseUnknownError:
        return False
    return any(p in ("ceph", "sc", "datalake") for p in cl)


def phase_deps(backend: str = CEPH) -> dict[str, set[str]]:
    """DAG phase→phases-dont-elle-dépend (au grain phase), dérivé du graphe atomique.

    Pour chaque phase roundtrip, l'ensemble des AUTRES phases qui possèdent au moins
    un composant dont un composant de la phase dépend directement. Projection figée
    consommée par `layers.phase_deps` (lot 3) ; ici on la fournit pure (sans bash).
    """
    deps: dict[str, set[str]] = {}
    for phase in ROUNDTRIP_PHASES:
        acc: set[str] = set()
        for comp in component_expand_alias(phase, backend):
            for dep in component_deps(comp, backend):
                dph = phase_of_component(dep, backend)
                if dph and dph != phase:
                    acc.add(dph)
        deps[phase] = acc
    return deps


# ── Projection PHASE du SIGNAL de SANTÉ (= l'ancienne table _LAYER_SIGNAL) ────
# Le signal de santé est PORTÉ par le composant qui EST le DERNIER MAILLON de la couche
# (champ `Component.signal`) ; cette table dit, par PHASE, QUEL composant porte ce signal.
# Pour la plupart des phases le composant homonyme (`ceph`, `mlflow`, `portal`…) ; pour
# `monitoring`/`gitops`/`dataops` le dernier maillon DIFFÈRE du nom de phase (loki/argocd/
# marquez). `scripts/topology.py:_LAYER_SIGNAL` est désormais la PROJECTION de cette table
# (dict phase → Component.signal) — UNE seule source de vérité, plus DEUX (lot 4 refonte
# nestor). L'ORDRE reproduit celui de l'ancien `_LAYER_SIGNAL` (itéré par `_observed_layers`).
_PHASE_SIGNAL_COMPONENT: dict[str, str] = {
    "metrics-server": "metrics-server",
    "storage-simple": "storage-simple",
    "ceph": "ceph",
    "sc": "sc",
    "datalake": "datalake",
    "monitoring": "loki",  # DERNIER maillon ≠ nom de phase
    "gitops": "argocd",  # DERNIER maillon ≠ nom de phase (argocd-server)
    "dataops": "marquez",  # DERNIER maillon ≠ nom de phase
    "mlflow": "mlflow",
    "gitops-seed": "gitops-seed",
    "portal": "portal",
}


def phase_signal_component(phase: str) -> str | None:
    """Le COMPOSANT qui porte le signal de santé de `phase` (son DERNIER maillon), ou None.

    Pour `monitoring`/`gitops`/`dataops` ce composant DIFFÈRE du nom de phase
    (loki/argocd/marquez) ; ailleurs c'est l'homonyme. Phase sans signal connu → None."""
    return _PHASE_SIGNAL_COMPONENT.get(phase)


def layer_signal(phase: str) -> SignalTarget | None:
    """Cible kubectl du signal de SANTÉ de `phase`, lue sur le composant DERNIER MAILLON.

    DÉRIVÉE du graphe (`Component.signal`) — c'est l'unique source de l'ancienne table
    `_LAYER_SIGNAL` de `scripts/topology.py`. Phase sans signal connu → None."""
    comp = _PHASE_SIGNAL_COMPONENT.get(phase)
    return COMPONENTS[comp].signal if comp is not None else None


# Projection figée phase → cible kubectl du signal de santé, dérivée du graphe atomique.
# `scripts/topology.py:_LAYER_SIGNAL` en est une simple copie (mêmes clés, même ordre) :
# il n'y a PLUS deux tables à tenir cohérentes — celle-ci est la source, l'autre la projette.
LAYER_SIGNAL: dict[str, SignalTarget] = {
    phase: sig for phase in _PHASE_SIGNAL_COMPONENT if (sig := layer_signal(phase)) is not None
}


# ── Projection PHASE de ROLLBACK (= rollback_phase_*, table de périmètre ADR 0054) ─
# Ces trois fonctions sont une projection COARSE par phase (pas l'agrégat des
# component_*) : la table de périmètre du rollback par phase (ADR 0054 §3) que le
# bash tenait à part dans `rollback_phase_namespaces`/`_targeted_resources`/
# `_has_nodeside`. On les PORTE à l'octet (case par case) pour clore le pont
# subprocess de `roundtrip.py` (lot 3) ; `tests/test_graph.py` prouve la byte-identité
# au VRAI bash (les deux backends). NOTE : ce N'est PAS l'agrégat de
# `component_namespace`/`component_targeted` sur la phase (cf. dataops : la table
# n'efface PAS le ns registry, le composant `registry` le possède pourtant) — c'est
# une table DISTINCTE, conservée telle quelle (ADR 0054), pas dérivée du graphe atomique.


def rollback_phase_namespaces(phase: str) -> list[str]:
    """Namespaces qu'un rollback de `phase` doit effacer (= rollback_phase_namespaces).

    SEUL `ceph` possède rook-ceph (sc/datalake le PARTAGENT → ne le suppriment pas).
    Table de périmètre ADR 0054 §3 ; phase sans ns dédié → liste vide."""
    return {
        "ceph": ["rook-ceph"],
        "monitoring": ["monitoring"],
        "dataops": ["postgres", "dagster", "marquez"],
        "mlflow": ["mlflow"],
        "gitops": ["argocd", "gitea"],
    }.get(phase, [])


def rollback_phase_targeted_resources(phase: str, backend: str = CEPH) -> list[str]:
    """Ressources CIBLÉES à supprimer pour `phase` (= rollback_phase_targeted_resources).

    Une ressource par entrée, forme « -n NS KIND NAME » ou « KIND NAME » (cluster-scoped).
    Backend-conditionnel : les OBC (loki-buckets/cnpg-backups/mlflow-artifacts) n'existent
    QU'en ceph (en local-path la CRD objectbucketclaim est absente → on n'émet rien)."""
    is_ceph = _backend(backend) == CEPH
    if phase == "datalake":
        return [
            "-n rook-ceph cephobjectstore.ceph.rook.io datalake",
            "storageclass.storage.k8s.io rook-ceph-datalake",
        ]
    if phase == "sc":
        return [
            "storageclass.storage.k8s.io rook-ceph-block-replicated",
            "storageclass.storage.k8s.io rook-ceph-block-ec-delete",
            "storageclass.storage.k8s.io rook-ceph-block-ec",
            "storageclass.storage.k8s.io rook-cephfs",
        ]
    if phase == "metrics-server":
        return ["-n kube-system deployment.apps metrics-server"]
    if phase == "monitoring":
        return ["-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets"] if is_ceph else []
    if phase == "dataops":
        return ["-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups"] if is_ceph else []
    if phase == "mlflow":
        return (
            ["-n rook-ceph objectbucketclaim.objectbucket.io mlflow-artifacts"] if is_ceph else []
        )
    if phase == "gitops-seed":
        return ["-n argocd applications.argoproj.io atlas-workflows"]
    return []


def rollback_phase_has_nodeside(phase: str) -> bool:
    """True si `phase` laisse un état NODE-SIDE (disques Ceph) (= rollback_phase_has_nodeside).

    Seul `ceph` en a (le delete Kubernetes ne couvre pas /var/lib/rook)."""
    return phase == "ceph"


# Réexport pratique : un composant avec ses deps résolues pour un backend donné
# (utile aux lots aval qui veulent un Component « concret »).
def resolved_component(comp: str, backend: str = CEPH) -> Component:
    """Renvoie le `Component` de `comp` avec `deps` résolues par `backend` (jetons figés)."""
    c = COMPONENTS[comp]
    return replace(c, deps=c.resolved_deps(backend))


__all__ = [
    "CEPH",
    "LOCAL_PATH",
    "COMPONENTS",
    "COMPONENT_ALL",
    "Component",
    "PHASE_COMPONENTS",
    "ROUNDTRIP_PHASES",
    "SignalTarget",
    "LAYER_SIGNAL",
    "TopoCycleError",
    "PhaseUnknownError",
    "component_known",
    "component_deps",
    "component_namespace",
    "component_targeted",
    "component_crd_groups",
    "component_has_nodeside",
    "component_profile",
    "component_alias_weight",
    "component_expand_alias",
    "topo_sort",
    "phase_of_component",
    "phase_closure",
    "phase_involves_storage",
    "phase_deps",
    "phase_signal_component",
    "layer_signal",
    "rollback_phase_namespaces",
    "rollback_phase_targeted_resources",
    "rollback_phase_has_nodeside",
    "resolved_component",
]
