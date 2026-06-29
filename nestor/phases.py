"""Mapping PHASE → (playbook, extravars, gate de santé, hooks e2e) — LOT 7 (ADR 0097).

Porte en données PURES ce que les `phase_*` de `bench/lima/run-phases.sh` font : pour
chaque phase de plateforme, QUEL playbook lancer (`run_ansible_phase <playbook>`), QUELS
`-e` lui passer, et COMMENT gater sa santé après montage. `nestor/path.py:run_path` (le
moteur du lot 6) boucle déjà sur la séquence en appelant des callbacks `launch`/`gate`
ABSTRAITS ; ce module fournit la TABLE que la façade consomme pour CÂBLER ces callbacks
sur le réel (runner.launch_phase_idempotent + topology._wait_layer_healthy) — sans que le
moteur connaisse une seule phase nommée (il reste générique, la table est la donnée).

La plupart des phases sont TRIVIALES (un playbook + une gate de santé sur le dernier
maillon, déjà portée par `_wait_layer_healthy` via `graph.LAYER_SIGNAL`). DEUX familles
ne le sont PAS et sont traitées EXPLICITEMENT (réserve critique du lot 6 / ADR 0097) :

  1. `dataops` : après le playbook, deux HARNAIS e2e que `_wait_layer_healthy` ne couvre
     PAS — `dataops_chain_emit_and_verify` (Job émetteur OpenLineage + poll + delta
     Marquez, run-phases.sh:1213) et `dataops_egress_internet_check` (preuve NetworkPolicy
     egress 443, run-phases.sh:1312). Ils sont DÉCLARÉS comme des HOOKS post-montage
     (`PhasePlan.e2e_hooks`), mais leur CONTENU réel est STUBÉ (TODO « à câbler+prouver au
     banc ») : un faux émetteur OpenLineage serait pire que rien (il « verdirait » à tort).

  2. `ceph`/`sc`/`datalake` : leur gate de santé porte sur `status.phase == "Ready"` des CR
     Rook (CephCluster, CephObjectStore), PAS sur `readyReplicas` d'un Deployment. Cette
     distinction vit DÉJÀ dans `graph.LAYER_SIGNAL` (4e champ `"phase"`) et est honorée par
     `_resource_healthy` ; on l'EXPOSE ici (`gate_kind="cr-phase"`) pour que la table soit
     auto-portante, mais la PREUVE banc (OSD up, HEALTH_OK) reste un STUB documenté.

═══════════════════════════════════════════════════════════════════════════════
⚠️  FRONTIÈRE CODE-ÉCRIT / PREUVE-BANC (ADR 0034 — HONNÊTETÉ)

Ce module touche le MONTAGE RÉEL (il décrit QUELS playbooks lancer et COMMENT les
gater). Sa preuve DÉFINITIVE est un RUN BANC from-scratch consigné + rejeu `changed=0` —
qui RESTE À FAIRE AVANT TOUT MERGE. Le code est PROUVÉ par tests unitaires STUBÉS
(`tests/test_phases.py`, briques injectées, zéro cluster) pour sa LOGIQUE de mapping
UNIQUEMENT. Les harnais e2e (`dataops`) et les gates Ceph ne sont PAS exécutés ici : leur
câblage réel est listé dans `_BANC_TODO`. NE PRÉTENDS JAMAIS avoir prouvé au banc.

COEXISTENCE (plan invariant 4) : ni `run_path` ni `cmd_up`/`cmd_next` ne sont basculés
sur cette table — le chemin par défaut reste le subprocess `run-phases.sh`. On enrichit
la donnée À CÔTÉ ; la bascule se fera AVEC la preuve banc en main (lot 6/7 mergé).
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from nestor import graph
from nestor.plan import phase_playbook

# `dataops_k8s_host=localhost` : le faisceau `-e` que TOUTES les phases plateforme
# passent (run-phases.sh:run_ansible_phase:246 le fixe pour CHAQUE play, pilotage de
# l'API depuis l'hôte via le kubeconfig banc). On le pose une fois ici.
_K8S_HOST_LOCALHOST = {"dataops_k8s_host": "localhost"}


@dataclass(frozen=True)
class PhasePlan:
    """Plan de montage d'UNE phase plateforme (donnée PURE, pas d'I/O).

    - `phase` : nom de la phase (clé de la séquence, ADR 0083).
    - `playbook` : chemin du playbook relatif au repo (= `run_ansible_phase <playbook>`),
      ou None si la phase n'est PAS un play unitaire (script/seed/node-side — déléguée).
    - `extravars_keys` : clés `-e` que la phase consomme du faisceau dérivé
      (`profile.derive_run_params`) — la façade RESTREINT le faisceau à ces clés (parité
      run-phases.sh, qui ne passe à chaque play QUE ses `-e` pertinents). `None` =
      « tout le faisceau » (phases qui consomment plusieurs clés croisées) ; `()` = aucun
      `-e` dérivé (au-delà de `dataops_k8s_host`). Toujours en plus de `_K8S_HOST_LOCALHOST`.
    - `gate_kind` : NATURE de la gate de santé après montage (la façade la branche sur
      `_wait_layer_healthy`, qui lit `graph.LAYER_SIGNAL`). `"ready-replicas"` = workload
      répliqué (readyReplicas≥1) ; `"cr-phase"` = `status.phase == "Ready"` d'un CR Rook
      (ceph/datalake) ; `"presence"` = présence seule (StorageClass, Application) ; `"none"`
      = aucune gate (phase sans maillon discriminant). Ce N'EST PAS une 2ᵉ source de vérité
      du signal (la cible kubectl exacte vit dans `graph.LAYER_SIGNAL`) — c'est l'ÉTIQUETTE
      lisible de la nature de la gate, pour la table et les tests.
    - `e2e_hooks` : harnais e2e à jouer APRÈS la gate de santé (preuve au-delà du
      `_wait_layer_healthy` : OpenLineage→Marquez, egress 443). VIDE pour les phases
      triviales. Voir `E2E_HOOKS` (stubs avec TODO).
    - `note` : note développeur (POURQUOI une phase n'est pas triviale)."""

    phase: str
    playbook: str | None
    extravars_keys: tuple[str, ...] | None = ()
    gate_kind: str = "none"
    e2e_hooks: tuple[str, ...] = ()
    note: str = ""


# ── Gate de santé : DÉRIVÉE de graph.LAYER_SIGNAL (source unique, lot 4) ──────
# On ne RE-déclare PAS la cible kubectl ici (anti-double-source, ADR 0096 §1) : on
# CLASSE le 4e champ du signal (ready) en une étiquette lisible. Une phase sans signal
# connu (amont, gitops-seed côté seed…) → "none" (rien à gater, parité _wait_layer_healthy).
def gate_kind_for(phase: str) -> str:
    """Étiquette de la nature de la gate de santé d'une phase (dérivée de LAYER_SIGNAL).

    `"phase"` (CR Rook : CephCluster/CephObjectStore) → "cr-phase" ; `True` (workload
    répliqué) → "ready-replicas" ; `False` (présence seule : StorageClass, Application) →
    "presence" ; signal absent → "none". PUR — la cible exacte reste dans graph.LAYER_SIGNAL."""
    sig = graph.LAYER_SIGNAL.get(phase)
    if sig is None:
        return "none"
    ready = sig[3]
    if ready == "phase":
        return "cr-phase"
    if ready is True:
        return "ready-replicas"
    return "presence"


# ── Preuve e2e OpenLineage→Marquez : LOGIQUE PURE (ADR 0017) ─────────────────────
# Le geste de `dataops_chain_emit_and_verify` (run-phases.sh:1213) se décompose en
# (a) de l'I/O kubectl/API Marquez — câblée DANS LA FAÇADE (scripts/topology.py, ADR 0049),
# et (b) de la DÉCISION PURE — portée ICI, testable sans cluster : QUEL manifeste de Job
# émetteur appliquer, COMMENT compter les jobs d'une réponse Marquez, et QUEL verdict tirer
# du compteur avant/après. Ce sont les ports des fonctions PURES bash `parse_ol_job_count`
# (dataops-assert.sh:119) et `classify_marquez_ingest` (dataops-assert.sh:62).

# Image de l'émetteur OpenLineage jetable (user-code maison), poussée au registry interne
# par le rôle `platform-build-images` SOUS `build_emitter_image=true` (banc e2e seulement,
# JAMAIS en prod). Le Job la matérialise (`dagster asset materialize`) → START/COMPLETE
# OpenLineage vers Marquez. Le play `dataops` du moteur Python PASSE désormais
# `build_emitter_image=true` au banc (derive_run_params le pose si target_kind==lima ; clé
# dans extravars_keys de dataops) → l'image est buildée au montage, le hook e2e la trouve.
# Si pour une raison le build manque, le hook échoue HONNÊTEMENT (Job ImagePullBackOff →
# poll non `succeeded`), jamais un faux vert.
EMITTER_IMAGE = "registry:80/dagster-openlineage-emit:dev"
EMITTER_JOB_NAME = "ol-emit-toy"
EMITTER_NAMESPACE = "dagster"
EMITTER_OL_NAMESPACE = "dagster"
# URL de l'API Marquez INTRA-CLUSTER : le Job tourne DANS le cluster → le FQDN
# `*.svc.cluster.local` est LÉGITIME pour LUI (résolu par le DNS du cluster). Le compteur
# de jobs, lui, est lu DEPUIS L'HÔTE → la façade NE tape JAMAIS ce FQDN directement (piège
# DNS, mémoire dns-fqdn-timeout) : elle exec/run un pod qui le résout intra-cluster.
MARQUEZ_URL = "http://marquez.marquez.svc.cluster.local:5000"
MARQUEZ_ENDPOINT = "api/v1/lineage"


def emit_toy_job_manifest(
    *,
    name: str = EMITTER_JOB_NAME,
    namespace: str = EMITTER_NAMESPACE,
    ol_namespace: str = EMITTER_OL_NAMESPACE,
    image: str = EMITTER_IMAGE,
    marquez_url: str = MARQUEZ_URL,
    endpoint: str = MARQUEZ_ENDPOINT,
) -> str:
    """Manifeste du Job émetteur OpenLineage jetable (DONNÉE PURE — parité run-phases.sh:1222).

    Un Job K8s qui matérialise un asset Dagster en process local (sans webserver), sensor
    OpenLineage configuré par env : `OPENLINEAGE_URL` pointe l'API Marquez interne. backoff
    1, ttl 600 s (auto-nettoyage), `restartPolicy: Never`. `command` matérialise l'asset
    jouet (`toy_assets`), ce qui émet START/COMPLETE OpenLineage. Rendu en YAML littéral
    (pas de dépendance à un sérialiseur) pour rester byte-stable et trivialement testable."""
    return (
        "apiVersion: batch/v1\n"
        "kind: Job\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {namespace}\n"
        "spec:\n"
        "  backoffLimit: 1\n"
        "  ttlSecondsAfterFinished: 600\n"
        "  template:\n"
        "    spec:\n"
        "      restartPolicy: Never\n"
        "      containers:\n"
        "        - name: emit\n"
        f"          image: {image}\n"
        "          imagePullPolicy: IfNotPresent\n"
        "          env:\n"
        "            - name: OPENLINEAGE_URL\n"
        f'              value: "{marquez_url}"\n'
        "            - name: OPENLINEAGE_ENDPOINT\n"
        f'              value: "{endpoint}"\n'
        "            - name: OPENLINEAGE_NAMESPACE\n"
        f'              value: "{ol_namespace}"\n'
        '          command: ["dagster", "asset", "materialize", "--select", "*", '
        '"-m", "toy_assets"]\n'
    )


def parse_marquez_job_count(json_text: str | None) -> int | None:
    """Nombre de jobs d'une réponse Marquez `GET /api/v1/namespaces/<ns>/jobs` (PUR).

    Port de `parse_ol_job_count` (dataops-assert.sh:119) : l'objet `{"jobs":[…],
    "totalCount":N}` → `totalCount` s'il est entier, sinon `len(jobs)`. Renvoie `None`
    (≈ le `"?"` du bash) si le JSON est vide / illisible / sans champ exploitable —
    l'appelant le classe en `skip` (Marquez injoignable, pas un échec d'ingestion)."""
    if not json_text or not json_text.strip():
        return None
    try:
        data = json.loads(json_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    total = data.get("totalCount")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    jobs = data.get("jobs")
    if isinstance(jobs, list):
        return len(jobs)
    return None


def classify_marquez_ingest(before: int | None, after: int | None) -> tuple[str, str]:
    """Verdict d'ingestion OpenLineage d'après le compteur de jobs Marquez avant/après (PUR).

    Port FIDÈLE de `classify_marquez_ingest` (dataops-assert.sh:62) — verdict `(status,
    message)`, `status ∈ {ok, fail, skip}` :
      - `before` ou `after` illisible (`None`) → `skip` (API joignable ? — pas un échec) ;
      - `after >= 1` → `ok` (lineage PRÉSENT ; `before` = info du message) ;
      - `after == 0` → `fail` (rien ingéré).

    NB (parité bash, bats L56) : on teste la PRÉSENCE (`after >= 1`), PAS un delta strict :
    le run est IDEMPOTENT (Marquez ne vide pas le namespace), donc un 2ᵉ passage laisse
    `after == before` alors que l'ingestion a bien eu lieu. Un delta `> 0` exigé donnerait
    un faux `fail` au rejeu. Le compteur `before` n'est qu'informatif."""
    if before is None or after is None:
        return ("skip", "Marquez : compteur de jobs illisible (API joignable ?)")
    if after >= 1:
        return ("ok", f"Marquez : lineage présent ({before} → {after} jobs)")
    return ("fail", f"Marquez : aucun job ingéré ({before} → {after})")


# ── Harnais e2e (réserve critique ADR 0097 §5 / lot 7) : 1 câblé, 1 STUB ─────────
# Ces harnais PROUVENT le maillon final que _wait_layer_healthy ne couvre PAS (un
# Deployment Marquez Ready ne prouve PAS qu'un run Dagster émet du lineage ingéré). Ils
# sont DÉCLARÉS comme hooks de la phase `dataops`. `dataops_chain_emit_and_verify` est
# désormais CÂBLÉ DANS LA FAÇADE (Job émetteur + poll + delta Marquez, I/O kubectl) ; le
# STUB ci-dessous reste le DÉFAUT du registre (appelé sans I/O injectée → lève, honnêteté).
# `dataops_egress_internet_check` reste STUBÉ (bascule NetworkPolicy + probe egress 443).


class E2EHookStubbed(RuntimeError):
    """Un harnais e2e est appelé sans être câblé au réel (STUB) — refuse de verdir.

    Lever (plutôt que rendre True) est l'HONNÊTETÉ : un harnais e2e non câblé NE PROUVE
    RIEN ; le faire passer pour « ok » fabriquerait une fausse preuve (ADR 0034). La façade
    ne branchera ces hooks sur le réel qu'avec un banc en main (cf. `_BANC_TODO`)."""


def _hook_chain_emit_and_verify(**_kw) -> None:
    """DÉFAUT du registre pour `dataops_chain_emit_and_verify` (run-phases.sh:1213, ~62 l.).

    Le geste RÉEL (Job émetteur OpenLineage `registry:80/dagster-openlineage-emit:dev` +
    `dagster asset materialize`, poll `status.succeeded == 1` ~5 min, puis vérif d'ingestion
    Marquez par le compteur de jobs avant/après — `parse_marquez_job_count` /
    `classify_marquez_ingest` ci-dessus — enfin teardown du Job) exige de l'I/O kubectl :
    il est CÂBLÉ DANS LA FAÇADE (`scripts/topology.py:_chain_emit_and_verify_banc`, ADR 0049)
    et substitué à ce défaut par le moteur (`_E2E_HOOK_IMPL`). Ce défaut N'A PAS l'I/O
    injectée → il LÈVE (jamais un faux « ok », honnêteté ADR 0034) : il n'est atteint que si
    quelqu'un joue le registre nu sans passer par la façade."""
    raise E2EHookStubbed(
        "dataops_chain_emit_and_verify appelé SANS I/O injectée (défaut registre) : le geste "
        "réel (Job émetteur + delta Marquez) vit dans la façade — voir "
        "scripts/topology.py:_chain_emit_and_verify_banc (run-phases.sh:1213, ADR 0097 §5)"
    )


def _hook_egress_internet_check(**_kw) -> None:
    """STUB de `dataops_egress_internet_check` (run-phases.sh:1312).

    RÉEL à câbler (à PROUVER au banc) : probe egress 443 d'un pod du ns `dagster`
    (`curl https://1.1.1.1/`) AVEC la NetworkPolicy `allow-internet-egress` (doit
    aboutir), RETIRER la NP et re-probe (doit timeouter `000`), RÉAPPLIQUER la NP depuis
    le manifeste versionné (corriger l'état, ADR 0046 ; trap de garantie), verdict
    `classify_egress_probe`. Stub qui LÈVE tant que ce n'est pas prouvé au banc."""
    raise E2EHookStubbed(
        "dataops_egress_internet_check NON câblé (STUB) : bascule NetworkPolicy egress 443 "
        "+ probe avec/sans à porter et PROUVER au banc (run-phases.sh:1312, ADR 0097 §5)"
    )


# Registre des hooks e2e par NOM (référencés par PhasePlan.e2e_hooks). La façade y branche
# le réel quand il sera câblé ; ici ce sont des STUBS qui lèvent E2EHookStubbed.
E2E_HOOKS: dict[str, Callable[..., None]] = {
    "dataops_chain_emit_and_verify": _hook_chain_emit_and_verify,
    "dataops_egress_internet_check": _hook_egress_internet_check,
}


# ── LA TABLE : phase plateforme → plan de montage (ADR 0097 §1, alignée run-phases.sh) ─
# Le `playbook` DÉRIVE de `plan.PHASE_PLAYBOOK` (source unique, lot 6) via `phase_playbook`
# — on ne RE-saisit PAS le chemin ici (anti-double-source). Le `gate_kind` DÉRIVE de
# `graph.LAYER_SIGNAL` via `gate_kind_for`. Cette table n'AJOUTE que ce qui est PROPRE au
# montage : quelles clés `-e` la phase consomme et quels hooks e2e elle déclenche.


def _plan(
    phase: str,
    *,
    extravars_keys: tuple[str, ...] | None = (),
    e2e_hooks: tuple[str, ...] = (),
    note: str = "",
) -> PhasePlan:
    """Construit un `PhasePlan` en DÉRIVANT playbook + gate des sources uniques."""
    return PhasePlan(
        phase=phase,
        playbook=phase_playbook(phase),
        extravars_keys=extravars_keys,
        gate_kind=gate_kind_for(phase),
        e2e_hooks=e2e_hooks,
        note=note,
    )


# Clés `-e` que chaque phase consomme du faisceau `derive_run_params` (parité
# run-phases.sh : chaque play ne reçoit QUE ses `-e`). Phases storage-only (ceph/sc/…)
# reçoivent leurs surcharges banc à la façade (non dérivées du profil — metadataDevice,
# OSD mémoire — propres au banc Lima, restent côté provisioning/harnais).
_PHASE_PLANS: dict[str, PhasePlan] = {
    # ── Stockage (socle backend-conditionnel, ADR 0083) ──────────────────────
    # storage-simple : local-path (banc léger). Pas de `-e` dérivé (le rôle porte tout).
    "storage-simple": _plan("storage-simple", extravars_keys=()),
    # ceph/sc/datalake : socle Ceph. Gate sur status.phase des CR Rook (cr-phase) pour
    # ceph/datalake, présence de la SC pour sc. Les surcharges banc (ceph_metadata_device,
    # ceph_osd_memory_request, ceph_osd_expected, dossier dé-épinglé arm64) sont des
    # paramètres de PROVISIONNEMENT propres au banc Lima → posées par la façade/harnais,
    # PAS dérivées du profil applicatif. STUB de la PREUVE banc (OSD up, HEALTH_OK).
    "ceph": _plan(
        "ceph",
        extravars_keys=("ceph_osd_expected",),
        note="gate cr-phase (CephCluster status.phase=Ready) ; OSD up/HEALTH_OK = preuve banc",
    ),
    "sc": _plan("sc", note="gate présence SC ; gate_test_pvc (PVC Bound) = preuve banc (STUB)"),
    "datalake": _plan(
        "datalake",
        note="gate cr-phase (CephObjectStore Ready) ; RGW S3 PUT/GET = preuve banc (STUB)",
    ),
    # ── metrics-server : API ressources (kubectl top), aucun -e dérivé ────────
    "metrics-server": _plan("metrics-server", extravars_keys=()),
    # ── monitoring : Prometheus + Grafana + Loki (S3). Consomme storageClass +
    #    backing S3 + endpoint (Loki TOUJOURS en S3, backing détecté). ─────────
    "monitoring": _plan(
        "monitoring",
        extravars_keys=(
            "monitoring_storage_class",
            "loki_storage_class",
            "loki_s3_backing",
            "loki_s3_endpoint",
        ),
    ),
    # ── gitops : Gitea (forge) + Argo CD (moteur). Consomme gitea_storage_class. ─
    "gitops": _plan("gitops", extravars_keys=("gitea_storage_class",)),
    # ── dataops : chaîne registry → CNPG → Dagster → Marquez. NON TRIVIALE :
    #    après le playbook + gate Marquez, DEUX harnais e2e (OpenLineage→Marquez,
    #    egress 443) que _wait_layer_healthy NE couvre PAS → hooks explicites (STUBÉS). ─
    "dataops": _plan(
        "dataops",
        extravars_keys=(
            "registry_storage_class",
            "cnpg_storage_class",
            "cnpg_s3_backing",
            "cnpg_s3_endpoint",
            # banc Lima seulement (derive_run_params le pose si target_kind==lima) : build
            # l'émetteur OpenLineage jetable requis par le hook e2e dataops_chain_emit_and_verify.
            "build_emitter_image",
        ),
        e2e_hooks=("dataops_chain_emit_and_verify", "dataops_egress_internet_check"),
        note="playbook + gate Marquez Ready, PUIS 2 harnais e2e (OpenLineage→Marquez, "
        "egress NP 443) STUBÉS — preuve e2e à câbler+prouver au banc (ADR 0097 §5)",
    ),
    # ── mlflow : suivi de modèles (backend CNPG + artefacts S3). ──────────────
    "mlflow": _plan("mlflow", extravars_keys=("mlflow_s3_backing", "mlflow_s3_endpoint")),
    # ── portal : portail d'accès aux UI (NodePort L4, lecture seule). NI stockage
    #    NI S3 → aucun -e dérivé (run-phases.sh:1184 ne passe que dataops_k8s_host). ─
    "portal": _plan("portal", extravars_keys=()),
}

# ── Phases NON PORTÉES dans cette table (déléguées / stubées ailleurs) ────────
# `gitops-seed` (init Gitea : DONNÉES, gitea-init.sh:207 l.) n'est PAS un playbook — son
# portage est le lot 8 (`nestor/seed.py`, gardes opposés banc/prod). On le DÉCLARE ici
# comme « délégué » pour que `phase_plan` ne mente pas (PhasePlan playbook=None + note),
# mais sa logique réelle n'est pas dans ce module.
# `up`/`bootstrap` : phases AMONT non-Ansible (provisioning/socle) — portées par
# `path._run_amont` (callbacks `provision`/`bootstrap`), JAMAIS par cette table.
_DELEGATED_PHASES: dict[str, PhasePlan] = {
    "gitops-seed": PhasePlan(
        phase="gitops-seed",
        playbook=None,
        extravars_keys=(),
        gate_kind=gate_kind_for("gitops-seed"),  # "presence" (Application atlas-workflows)
        note="init Gitea (DONNÉES, gitea-init.sh) — porté par nestor/seed.py au lot 8, pas ici",
    ),
}

# Phases AMONT à orchestration non-Ansible (provisioning VM / socle k8s+CNI) : portées
# par `path._run_amont`, EXCLUES de cette table (parité path._NON_ANSIBLE_AMONT).
_AMONT_PHASES = frozenset({"up", "bootstrap", "bootstrap-ha", "join-cp"})


class PhaseUnknownError(KeyError):
    """Phase sans plan de montage connu (ni plateforme, ni amont, ni déléguée)."""


def phase_plan(phase: str) -> PhasePlan:
    """Plan de montage d'une phase plateforme (ou déléguée). Lève si inconnue.

    Accesseur de la table (source unique du mapping plateforme). Une phase AMONT
    (`up`/`bootstrap`…) n'a PAS de plan ici (portée par `path._run_amont`) → lève
    PhaseUnknownError pour que l'appelant ne la route pas par erreur via `launch`."""
    if phase in _PHASE_PLANS:
        return _PHASE_PLANS[phase]
    if phase in _DELEGATED_PHASES:
        return _DELEGATED_PHASES[phase]
    if phase in _AMONT_PHASES:
        raise PhaseUnknownError(
            f"phase amont `{phase}` : portée par path._run_amont (provisioning/socle), "
            "PAS un plan de montage plateforme"
        )
    raise PhaseUnknownError(f"phase `{phase}` : aucun plan de montage connu (lot 7)")


def has_phase_plan(phase: str) -> bool:
    """`True` si `phase` a un plan plateforme/délégué dans cette table (pas amont)."""
    return phase in _PHASE_PLANS or phase in _DELEGATED_PHASES


def all_platform_phases() -> tuple[str, ...]:
    """Toutes les phases PLATEFORME portées par un playbook (hors déléguées/amont).

    L'ensemble que `path.run_path` route via `launch` (le reste va à `_run_amont` ou
    `seed.py`). Ordre stable (insertion) pour des tests déterministes."""
    return tuple(_PHASE_PLANS)


def extravars_for(phase: str, derived: dict) -> dict:
    """Restreint le faisceau `-e` dérivé (`derive_run_params`) aux clés de `phase`.

    Reproduit run-phases.sh : chaque play ne reçoit QUE ses `-e` pertinents (+ le commun
    `dataops_k8s_host=localhost`). `extravars_keys=None` → tout le faisceau ; `()` → aucun
    `-e` dérivé. Une clé déclarée mais absente de `derived` est IGNORÉE (la façade fournit
    le faisceau complet ; un manque viendrait d'un backend sans cette dimension)."""
    plan = phase_plan(phase)
    out = dict(_K8S_HOST_LOCALHOST)
    keys = plan.extravars_keys
    if keys is None:
        out.update(derived)
        return out
    for k in keys:
        if k in derived:
            out[k] = derived[k]
    return out


def e2e_hooks_for(phase: str) -> tuple[Callable[..., None], ...]:
    """Callables des harnais e2e d'une phase (résolus depuis E2E_HOOKS).

    VIDE pour les phases triviales. Pour `dataops` : les deux STUBS qui LÈVENT
    E2EHookStubbed tant qu'ils ne sont pas câblés+prouvés au banc (honnêteté ADR 0034)."""
    plan = phase_plan(phase)
    return tuple(E2E_HOOKS[name] for name in plan.e2e_hooks)


# ── CE QUI RESTE À CÂBLER + PROUVER AU BANC (TODO explicites, ADR 0034) ──────────
# La table ci-dessus est la LOGIQUE du mapping (prouvée par tests stubés). Les points
# suivants touchent le montage RÉEL et exigent un RUN BANC from-scratch (impossible dans
# cette session — NE PAS prétendre l'avoir fait) :
_BANC_TODO = (
    # 1. `dataops_chain_emit_and_verify` est CÂBLÉ (Job OpenLineage + delta Marquez, façade
    #    `_chain_emit_and_verify_banc`) — RESTE À PROUVER AU BANC (run-phases.sh:1213) +
    #    GARANTIR l'image émetteur : le play `dataops` du moteur Python NE passe PAS encore
    #    `build_emitter_image=true` (le bash si, run-phases.sh:1031) → sans build, le Job
    #    ImagePullBackOff → le hook échoue honnêtement. `_hook_egress_internet_check` reste
    #    STUBÉ (bascule NetworkPolicy + probe 443 — à câbler+prouver au banc, run-phases.sh:1312).
    "harnais e2e dataops : chain_emit CÂBLÉ (prouver au banc + garantir l'image émetteur) ; "
    "egress 443 encore STUBÉ — à câbler+prouver au banc",
    # 2. SURCHARGES banc des phases Ceph (ceph_metadata_device=vde, ceph_osd_memory_request,
    #    dossier dé-épinglé arm64, /var/lib/rook node-side) : paramètres de PROVISIONNEMENT
    #    propres au banc Lima, à poser par la façade et PROUVER (OSD up, HEALTH_OK).
    "surcharges banc Ceph (metadataDevice/OSD/undigest/var-lib-rook) — à câbler+prouver au banc",
    # 3. CÂBLER la façade : brancher `launch(phase)` sur runner.launch_phase_idempotent avec
    #    `extravars_for(phase, derive_run_params(topo))`, `gate(phase)` sur
    #    _wait_layer_healthy, et JOUER `e2e_hooks_for(phase)` APRÈS la gate (post-montage).
    "câblage façade (launch/gate/e2e_hooks dans run_path) — à écrire+prouver au banc",
    # 4. RUN BANC from-scratch consigné (bench/lima/RESULTS.md) + rejeu changed=0 sur LES
    #    DEUX topologies (banc local-path PUIS dirqual Ceph, invariants 1-2 du plan).
    "run banc from-scratch + rejeu changed=0 (banc PUIS prod) — PREUVE DÉFINITIVE, reste à faire",
)


def banc_todo() -> tuple[str, ...]:
    """Liste EXPLICITE de ce qui reste à câbler+prouver AU BANC (honnêteté ADR 0034).

    Accesseur testable : un test vérifie que la frontière code-écrit / preuve-banc est
    DÉCLARÉE (non vide), pour qu'on ne puisse pas merger en oubliant la preuve."""
    return _BANC_TODO
