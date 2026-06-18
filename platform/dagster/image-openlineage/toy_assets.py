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


def _compute_drift() -> dict:
    """Score de drift VIA EVIDENTLY (EmbeddingsDriftMetric), comme atlas (#404, #428).

    Réplique fidèle du `compute_drift` d'atlas, mais sur deux jeux SYNTHÉTIQUES
    générés en mémoire (pas de S3/DuckDB) : `reference` centré sur 0, `current`
    décalé → drift attendu. Le verdict `drift_detected` est celui d'Evidently (test
    statistique : ROC AUC d'un classifieur ref↔cur), PAS un seuil maison.

    Imports LOCAUX : Evidently est lourd (pandas/scipy/sklearn) — chargé seulement à
    l'exécution du check, pas à l'import du module (démarrage gRPC rapide), comme atlas."""
    import numpy as np
    import pandas as pd
    from evidently import ColumnMapping
    from evidently.metrics import EmbeddingsDriftMetric
    from evidently.report import Report

    dim, n = 8, 20
    rng = np.random.default_rng(0)
    cols = [f"e{i}" for i in range(dim)]
    reference = pd.DataFrame(rng.normal(0.0, 1.0, (n, dim)), columns=cols)
    current = pd.DataFrame(rng.normal(0.8, 1.0, (n, dim)), columns=cols)  # décalé → drift

    mapping = ColumnMapping(embeddings={"toy_vectors": cols})
    report = Report(metrics=[EmbeddingsDriftMetric("toy_vectors")])
    report.run(reference_data=reference, current_data=current, column_mapping=mapping)
    result = report.as_dict()["metrics"][0]["result"]
    return {
        "drift_score": float(result["drift_score"]),
        "drift_detected": bool(result["drift_detected"]),
        "method": result.get("method_name", "—"),
    }


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
    """Asset jouet : calcule un drift_score Evidently et le logge dans MLflow.

    Réplique la chaîne drift/CT d'atlas (#404) EN AUTONOMIE (jeux synthétiques, sans
    atlas) : vrai EmbeddingsDriftMetric → drift_score/drift_detected → MLflow. Le
    scénario 29 (VERIFY_MLFLOW=1) interroge ensuite l'API MLflow pour l'experiment
    `toy_embeddings_drift`."""
    run_id = str(uuid.uuid4())
    drift = _compute_drift()
    logged = _log_drift_to_mlflow(run_id, drift["drift_score"], drift["drift_detected"])
    return {
        "run_id": run_id,
        "drift_score": drift["drift_score"],
        "drift_detected": drift["drift_detected"],
        "method": drift["method"],
        "mlflow_logged": logged,
    }


# Tag `dagster-k8s/config` : injecte les variables d'env dans le POD DE RUN créé par le
# K8sRunLauncher (ADR 0086). CRUCIAL — les env du Deployment de la code-location gRPC
# (toy-codeloc) ne se propagent PAS aux pods de run ; il faut les déclarer ici (vécu au
# banc : run SUCCESS mais MLflow vide car MLFLOW_TRACKING_URI absent du pod de run).
# Patron atlas (definitions.py _RUN_K8S_CONFIG). Valeurs génériques = endpoints du
# contrat (ADR 0043) ; egress dagster→mlflow ouvert par allow-mlflow-egress (#407).
_RUN_K8S_CONFIG = {
    "dagster-k8s/config": {
        "container_config": {
            "env": [
                {"name": "OPENLINEAGE_URL", "value": "http://marquez.marquez.svc.cluster.local:5000"},
                {"name": "OPENLINEAGE_ENDPOINT", "value": "api/v1/lineage"},
                {"name": "OPENLINEAGE_NAMESPACE", "value": "dagster"},
                {"name": "MLFLOW_TRACKING_URI", "value": "http://mlflow.mlflow.svc.cluster.local:5000"},
            ],
        },
    },
}

# Job nommé matérialisant les assets — lançable par `launchRun` (GraphQL) quand ce
# module est chargé comme code-location gRPC (ADR 0086, `dagster api grpc -m toy_assets`).
# Le scénario 29 lance `CODELOC_JOB=toy_job` ; `selection="*"` matérialise toy_dataset
# (lineage Marquez) ET toy_drift (métrique MLflow). `tags` injecte l'env dans le pod de run.
toy_job = define_asset_job(name="toy_job", selection="*", tags=_RUN_K8S_CONFIG)

# `Definitions` : point d'entrée que `dagster api grpc -m toy_assets` charge pour exposer
# la code-location. Sans lui, le module n'expose pas de job nommé au workspace.
defs = Definitions(assets=[toy_dataset, toy_drift], jobs=[toy_job])
