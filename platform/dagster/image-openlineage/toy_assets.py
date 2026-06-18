# Code-location JOUET pour la validation e2e de la chaîne DataOps/MLOps (#148, ADR 0086).
#
# Deux preuves, sans code métier (le métier vit dans atlas) :
#   1. lineage : `toy_dataset` émet un événement OpenLineage RÉEL (START + COMPLETE)
#      vers Marquez (OPENLINEAGE_URL) — chaîne Dagster → OpenLineage → Marquez ;
#   2. suivi de modèle : `toy_drift` logge un `drift_score` JOUET dans MLflow
#      (MLFLOW_TRACKING_URI) — chaîne Dagster → MLflow (jumeau trivial de la chaîne
#      drift/CT d'atlas, #404). Le calcul de drift est ici une formule TRIVIALE maison
#      (écart de moyennes sur deux petits jeux codés en dur) — PAS le vrai Evidently
#      (réservé à une étape ultérieure : évite d'alourdir l'image jouet). Le but est de
#      prouver le CHEMIN (un run logge une métrique dans MLflow), pas le calcul.
#
# Invoqué via `dagster asset materialize -m toy_assets` (CLI) ou chargé comme
# code-location gRPC (`dagster api grpc -m toy_assets`, scénario 27/29). Tout est
# best-effort : si OPENLINEAGE_URL / MLFLOW_TRACKING_URI sont absents, on n'échoue pas
# (dev local). Valeurs génériques uniquement (ADR 0023) : aucune PII.

import os
import uuid
from datetime import datetime, timezone

from dagster import Definitions, asset, define_asset_job

from openlineage.client import OpenLineageClient
from openlineage.client.event_v2 import Job, Run, RunEvent, RunState
from openlineage.client.facet_v2 import nominal_time_run
from openlineage.client.uuid import generate_new_uuid


def _namespace() -> str:
    # Namespace OpenLineage = espace logique du producteur (générique, ADR 0023).
    return os.environ.get("OPENLINEAGE_NAMESPACE", "dagster")


def _emit_openlineage(job_name: str) -> None:
    """Émet START puis COMPLETE pour `job_name` vers Marquez (OPENLINEAGE_URL)."""
    # Le client lit OPENLINEAGE_URL / OPENLINEAGE_ENDPOINT / OPENLINEAGE_API_KEY
    # de l'environnement (pas d'URL en dur — surcharge par topologie, ADR 0023).
    client = OpenLineageClient.from_environment()

    run_id = str(generate_new_uuid())
    now = datetime.now(timezone.utc).isoformat()
    run = Run(
        runId=run_id,
        facets={"nominalTime": nominal_time_run.NominalTimeRunFacet(nominalStartTime=now)},
    )
    job = Job(namespace=_namespace(), name=job_name)
    producer = "https://github.com/univ-lehavre/cluster/platform/dagster/image-openlineage"

    for state in (RunState.START, RunState.COMPLETE):
        client.emit(
            RunEvent(
                eventType=state,
                eventTime=datetime.now(timezone.utc).isoformat(),
                run=run,
                job=job,
                producer=producer,
                inputs=[],
                outputs=[],
            )
        )


@asset
def toy_dataset():
    """Asset trivial : matérialise une valeur et émet le lineage OpenLineage.

    Le harnais dataops-chain vérifie ensuite côté Marquez que le job
    `toy_dataset` apparaît dans le namespace OpenLineage (preuve d'ingestion).
    """
    _emit_openlineage(job_name="toy_dataset")
    # Valeur de retour symbolique (l'asset n'a pas d'IO manager configuré ici).
    return {"rows": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "id": str(uuid.uuid4())}


def _toy_drift_score() -> tuple[float, bool]:
    """Calcule un `drift_score` JOUET (déterministe, sans dépendance lourde).

    Deux petits jeux codés en dur (référence vs courant) ; le score est l'écart
    ABSOLU de leurs moyennes, normalisé. C'est une formule TRIVIALE maison — pas le
    vrai EmbeddingsDriftMetric d'Evidently (étape ultérieure, ADR 0086). Le verdict
    `drift_detected` applique un seuil simple. Objectif : produire une métrique
    plausible à logger dans MLflow, pour prouver le CHEMIN Dagster → MLflow."""
    reference = [0.10, 0.12, 0.09, 0.11, 0.10]
    current = [0.42, 0.45, 0.40, 0.44, 0.41]  # décalé volontairement → drift attendu
    mean_ref = sum(reference) / len(reference)
    mean_cur = sum(current) / len(current)
    drift_score = round(abs(mean_cur - mean_ref) / (abs(mean_ref) + 1e-9), 4)
    return drift_score, drift_score > 0.5


def _log_drift_to_mlflow(run_id: str, drift_score: float, drift_detected: bool) -> bool:
    """Logge le drift dans MLflow (best-effort, calqué sur atlas `_log_to_mlflow`).

    Lit MLFLOW_TRACKING_URI de l'environnement (injecté par la code-location, comme
    atlas) ; si absent, no-op silencieux (dev local). Experiment `toy_embeddings_drift`,
    métriques `drift_score` + `drift_detected` — MÊMES noms que la chaîne atlas (#404),
    pour que le scénario de vérification soit transposable. Toute erreur → False."""
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        return False
    try:
        import mlflow  # mlflow-skinny : client seul, pas de serveur (image jouet légère)

        mlflow.set_experiment("toy_embeddings_drift")
        with mlflow.start_run(run_name=run_id):
            mlflow.log_param("run_id", run_id)
            mlflow.log_metric("drift_score", drift_score)
            mlflow.log_metric("drift_detected", int(drift_detected))
        return True
    except Exception:
        return False


@asset
def toy_drift():
    """Asset jouet : calcule un drift_score trivial et le logge dans MLflow.

    Prouve la chaîne Dagster → MLflow (jumeau trivial du drift/CT atlas, #404). Le
    scénario de vérification interroge ensuite l'API MLflow pour l'experiment
    `toy_embeddings_drift`."""
    run_id = str(uuid.uuid4())
    drift_score, drift_detected = _toy_drift_score()
    logged = _log_drift_to_mlflow(run_id, drift_score, drift_detected)
    return {
        "run_id": run_id,
        "drift_score": drift_score,
        "drift_detected": drift_detected,
        "mlflow_logged": logged,
    }


# Job nommé matérialisant les assets — lançable par `launchRun` (GraphQL) quand ce
# module est chargé comme code-location gRPC (ADR 0086, `dagster api grpc -m toy_assets`).
# Le scénario 29 lance `CODELOC_JOB=toy_job` ; `selection="*"` matérialise toy_dataset
# (lineage Marquez) ET toy_drift (métrique MLflow). (Le harnais CLI `materialize -m
# toy_assets` reste valable : il découvre les assets directement.)
toy_job = define_asset_job(name="toy_job", selection="*")

# `Definitions` : point d'entrée que `dagster api grpc -m toy_assets` charge pour exposer
# la code-location. Sans lui, le module n'expose pas de job nommé au workspace.
defs = Definitions(assets=[toy_dataset, toy_drift], jobs=[toy_job])
