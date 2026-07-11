"""Création assistée d'une topologie dans le catalogue (`topology.py init`, ADR 0056).

Module PUR (aucune I/O, aucun subprocess, aucun `input()`) : il DÉCIDE des chemins,
des garde-fous et de la STRUCTURE du YAML minimal à partir de RÉPONSES déjà
collectées. La collecte des réponses (prompts interactifs) et l'écriture (fichier +
symlink) restent à la façade `scripts/topology.py` — séparation testable/I/O (ADR 0017).

Le modèle (ADR 0056 + 0023) : le catalogue `topologies/` versionne les modèles
`*.example.yaml` et abrite les topologies RÉELLES `topologies/<nom>.yaml`
(gitignorées) ; `topology.yaml` (racine) est un SYMLINK d'activation.

L'ASSISTANT pose le MINIMUM décisionnel (ADR 0056 : « minimum à écrire : profil,
terrain ; tout le reste se dérive ») dans les ENUMS connus du modèle, puis
`build_topology_dict` en construit un dict de topologie VALIDE — qui passera
`model.load_topology` (réutilisé pour valider, jamais redupliqué). On n'invente
aucune dimension dérivable (storageClass, inventaire…) : ces champs se dérivent en
aval (`profile.derive_run_params`), pas ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Enums connus (alignés sur model.py / profile.py — source de vérité du schéma) ──
# Profils : inclusion cumulative base ⊂ store ⊂ obs ⊂ dataops (ADR 0039).
VALID_PROFILES = ["base", "store", "obs", "dataops"]
# Backends de stockage (profile.PROFILE_BY_BACKEND).
VALID_BACKENDS = ["local-path", "ceph"]
# Terrain (catalog ADR 0039/0040) — classe MATÉRIELLE de l'infra : local (banc
# jetable) | cloud | baremetal. Pivot qui gate en aval le transport/provisionning
# et la jetabilité (ADR 0108) — remplace l'ancien couple prod/bench (retiré).
VALID_TERRAINS = ["local", "cloud", "baremetal"]
# Mode du load-balancer de control-plane si HA (model.VALID_LB_MODES).
VALID_LB_MODES = ["kube-vip-arp", "kube-vip-lb", "external"]


class ScaffoldError(ValueError):
    """Nom de topologie invalide, modèle introuvable, ou réponse hors enum."""


@dataclass(frozen=True)
class InitPlan:
    """Chemins RÉSOLUS d'un `init` (relatifs au catalogue), prêts pour l'I/O."""

    name: str
    target: str  # topologies/<nom>.yaml
    activate: bool


@dataclass(frozen=True)
class Question:
    """Une question de l'assistant. `choices` non vide = choix dans un enum ;
    `default` = valeur retenue sous `--no-input` (et proposée à l'opérateur)."""

    key: str
    prompt: str
    default: str
    choices: list[str] = field(default_factory=list)
    help: str = ""


# Le MINIMUM décisionnel demandé (ADR 0056). L'ordre est pédagogique : ce qui
# dimensionne (profil, backend) puis le terrain, puis la taille du control-plane
# (1 → mono ; ≥ 3 → HA, exige un LB). Le nombre de workers et le mode LB sont
# demandés CONDITIONNELLEMENT par la façade selon control_planes (cf. QUESTIONS_HA).
QUESTIONS = [
    Question(
        "profile",
        "Profil applicatif",
        "base",
        VALID_PROFILES,
        "base ⊂ store ⊂ obs ⊂ dataops (inclusion cumulative, ADR 0039)",
    ),
    Question(
        "backend",
        "Backend de stockage",
        "local-path",
        VALID_BACKENDS,
        "local-path (léger) ou ceph (bloc + objet S3)",
    ),
    Question(
        "terrain",
        "Terrain",
        "local",
        VALID_TERRAINS,
        "local (banc Lima jetable) | cloud | baremetal",
    ),
    Question(
        "control_planes",
        "Nombre de control-planes",
        "1",
        [],
        "1 = mono-CP ; ≥ 3 = HA (quorum etcd, exige une VIP)",
    ),
    Question(
        "workers",
        "Nombre de workers",
        "2",
        [],
        "nœuds applicatifs (hors control-plane)",
    ),
]

# Question additionnelle posée UNIQUEMENT si control_planes ≥ 2 (HA → LB requis).
QUESTION_LB_MODE = Question(
    "lb_mode",
    "Mode du load-balancer de control-plane (HA)",
    "kube-vip-arp",
    VALID_LB_MODES,
    "kube-vip-arp (L2, banc) | kube-vip-lb | external (LB du terrain)",
)


def validate_name(name: str) -> str:
    """Vérifie qu'un `<nom>` de topologie est SÛR et donnera un fichier gitignoré.

    Refuse (AVANT toute écriture) : vide ; traversée de chemin (`/`, `\\`, `..`) ;
    un nom suffixé (`.yaml`/`.example`) — `init` crée une topo RÉELLE gitignorée
    `topologies/<nom>.yaml` ; un `.example` serait VERSIONNÉ (fuite de valeurs
    réelles, anti ADR 0023). On veut `init ha-prod`, pas `init ha-prod.example`.
    """
    stripped = name.strip()
    if not stripped:
        raise ScaffoldError("nom de topologie vide")
    if "/" in stripped or "\\" in stripped or ".." in stripped:
        raise ScaffoldError(
            f"nom `{stripped}` invalide : pas de séparateur de chemin ni `..` "
            "(la topologie est créée DANS topologies/)"
        )
    lowered = stripped.lower()
    if lowered.endswith((".example", ".yaml", ".yml")) or ".example." in lowered:
        raise ScaffoldError(
            f"nom `{stripped}` invalide : ne pas suffixer (.yaml/.example) — `init` crée "
            "une topo RÉELLE gitignorée `topologies/<nom>.yaml` ; un `.example` serait "
            "versionné (ADR 0023). Donne juste le nom : `init ha-prod`."
        )
    return stripped


def plan_init(name: str, *, activate: bool) -> InitPlan:
    """Calcule l'InitPlan (chemin cible relatif au catalogue) d'un `init`. PUR."""
    canonical = validate_name(name)
    return InitPlan(
        name=canonical,
        target=f"topologies/{canonical}.yaml",
        activate=activate,
    )


def catalog_entry(name: str) -> str:
    """Chemin relatif (DANS topologies/) d'une entrée du catalogue À ACTIVER. PUR.

    Sert `activate <nom>` : contrairement à `init`, on ACCEPTE un modèle versionné
    (`<nom>.example`) comme cible d'activation — activer un `.example` est légitime
    (banc générique). On normalise donc le suffixe :
    - `dirqual`        → topologies/dirqual.yaml
    - `dirqual.example`→ topologies/dirqual.example.yaml
    - `local.example.yaml` (suffixe complet) → topologies/local.example.yaml

    Garde-fou conservé : refus d'une traversée de chemin (`/`, `\\`, `..`). L'EXISTENCE
    réelle du fichier est vérifiée par la façade (I/O), pas ici.
    """
    stripped = name.strip()
    if not stripped:
        raise ScaffoldError("nom de topologie vide")
    if "/" in stripped or "\\" in stripped or ".." in stripped:
        raise ScaffoldError(
            f"nom `{stripped}` invalide : pas de séparateur de chemin ni `..` "
            "(l'entrée vit DANS topologies/)"
        )
    # Normalise le suffixe : on tolère `<nom>`, `<nom>.example`, `<nom>(.example).yaml`.
    leaf = stripped
    if not leaf.endswith((".yaml", ".yml")):
        leaf = f"{leaf}.yaml"
    return f"topologies/{leaf}"


def _as_positive_int(raw: str, label: str) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ScaffoldError(f"{label} : entier attendu, reçu `{raw}`") from exc
    if value < 0:
        raise ScaffoldError(f"{label} : doit être ≥ 0 (reçu {value})")
    return value


def _check_choice(value: str, choices: list[str], label: str) -> str:
    if choices and value not in choices:
        raise ScaffoldError(f"{label} : `{value}` hors enum (valides : {choices})")
    return value


def build_topology_dict(name: str, answers: dict[str, str]) -> dict:
    """Construit un dict de topologie MINIMAL et VALIDE à partir des réponses.

    Mappe les réponses de l'assistant vers le schéma attendu par `model.load_topology` :
    - `catalog` : topologie (= nom), profil, terrain (+ arch/status d'exemple) ;
    - `nodes` : control-planes `cp1..cpN` puis workers `node1..nodeM`. En HA (≥ 2 CP)
      hyperconvergé, chaque CP cumule control+worker n'est PAS supposé ici : on déclare
      des CP `control` purs + des workers `worker` purs (variante CP dédiés) — le
      modèle accepte les deux ; l'opérateur ajuste les rôles ensuite ;
    - `storage.backend` ; `network.control_plane_lb.mode` si HA (≥ 2 CP, ADR 0047/0055).

    Le champ prod/bench de criticité N'EST PLUS scaffolé (retiré du modèle, ADR 0108) :
    la classe matérielle est portée par `catalog.terrain` (local/cloud/baremetal).

    Lève ScaffoldError sur une réponse hors enum / un entier invalide. La validation
    de SCHÉMA finale (cohérence HA↔VIP, rôles) reste à `load_topology` (réutilisé).
    """
    profile = _check_choice(answers.get("profile", "base"), VALID_PROFILES, "profil")
    backend = _check_choice(answers.get("backend", "local-path"), VALID_BACKENDS, "backend")
    terrain = _check_choice(answers.get("terrain", "local"), VALID_TERRAINS, "terrain")
    n_cp = _as_positive_int(answers.get("control_planes", "1"), "control_planes")
    n_workers = _as_positive_int(answers.get("workers", "2"), "workers")
    if n_cp < 1:
        raise ScaffoldError("au moins 1 control-plane est requis")

    nodes: list[dict] = [{"name": f"cp{i}", "roles": ["control"]} for i in range(1, n_cp + 1)]
    nodes += [{"name": f"node{i}", "roles": ["worker"]} for i in range(1, n_workers + 1)]

    topo: dict = {
        "catalog": {
            "topology": name,
            "profile": profile,
            "terrain": terrain,
            "status": "cible",  # NON prouvé tant qu'un run ne l'a pas monté (ADR 0030/0052)
        },
        "nodes": nodes,
        "storage": {"backend": backend},
    }
    if n_cp >= 2:  # HA → un control_plane_lb (VIP) est EXIGÉ par le modèle (ADR 0047/0055)
        lb_mode = _check_choice(answers.get("lb_mode", "kube-vip-arp"), VALID_LB_MODES, "lb_mode")
        topo["network"] = {"control_plane_lb": {"mode": lb_mode}}
    return topo
