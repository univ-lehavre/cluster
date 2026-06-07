# Asset Dagster JETABLE pour la validation e2e de la chaîne DataOps (#148).
#
# Émet un événement OpenLineage RÉEL (START + COMPLETE) vers Marquez lors de la
# matérialisation, prouvant la chaîne Dagster → OpenLineage → Marquez. Ce n'est PAS
# du code de production : le code métier (assets atlas) vit ailleurs (Phase 2+).
#
# Invoqué par le harnais via :
#   dagster asset materialize --select '*' -m toy_assets
# avec les variables d'env OPENLINEAGE_URL / OPENLINEAGE_ENDPOINT /
# OPENLINEAGE_NAMESPACE (pointant l'API Marquez interne).
#
# On émet l'événement explicitement avec le client openlineage-python (plutôt que
# via un sensor, qui exigerait le daemon Dagster) : robuste pour un run CLI
# one-shot. Valeurs génériques uniquement (ADR 0023) : aucune PII, noms d'assets
# techniques.

import os
import uuid
from datetime import datetime, timezone

from dagster import asset

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
