# Image Dagster + OpenLineage + MLflow JETABLE — code-location jouet (#148, ADR 0086).
#
# Le module toy_assets.py expose : `toy_dataset` (émet du lineage OpenLineage vers
# Marquez) et `toy_drift` (logge un drift_score jouet dans MLflow). Sert au harnais
# (`dataops-chain`) et à la code-location gRPC jouet (scénario 27/29). Ce n'est PAS
# une brique de production (l'orchestrateur Dagster livré reste vide — métier dans atlas).
#
# arm64 (banc Lima) : tout est du Python (wheels manylinux/aarch64 pour les deps natives
# d'evidently) → l'image se construit sur python:3.10-slim (même base que
# platform/dagster/image/). Hard-pin de dagster sur la version du chart (verrou
# chart↔package 1:1, ADR 0006). mlflow-skinny (client seul) + evidently (drift réel,
# #428) : l'image n'est plus « légère » (~+300 Mo via pandas/scipy/sklearn) — assumé pour
# prouver la couche drift en autonomie ; le build reste idempotent (force_rebuild).
#
# Build (depuis ce dossier) :
#   docker buildx build --platform linux/arm64 \
#     -t registry:80/dagster-openlineage-emit:dev --push platform/dagster/image-openlineage/
FROM python:3.10-slim

ARG DAGSTER_VERSION=1.13.7

# dagster-postgres + dagster-k8s : REQUIS quand la code-location est lancée par le
# webserver via le K8sRunLauncher (chemin réel, scénario 29) — le pod de run se connecte
# au PostgresRunStorage de l'instance Dagster. Sans eux : « Couldn't import module
# dagster_postgres.run_storage » → run FAILURE (vécu au banc). L'ancien usage CLI
# (`dagster asset materialize`, local) ne les exigeait pas. Non épinglés : sous-packages
# au schéma de version distinct, résolus depuis `dagster==X` (modèle platform/dagster/image).
# evidently : VRAI calcul de drift (EmbeddingsDriftMetric, ADR 0086 étape 2, #428) —
# réplique la chaîne drift/CT d'atlas EN AUTONOMIE. Lourd (tire pandas/numpy/scipy/
# scikit-learn/plotly, ~+300 Mo) mais buildable arm64 (wheels manylinux/aarch64) ; pinné
# comme atlas. Résolution sans conflit avec dagster 1.13.7 + mlflow-skinny (vérifié uv).
RUN pip install --no-cache-dir -U uv
RUN python -m uv pip install --system \
    dagster==${DAGSTER_VERSION} \
    dagster-postgres \
    dagster-k8s \
    openlineage-python \
    mlflow-skinny==2.17.2 \
    evidently==0.4.40

# Le module d'asset jetable (chargé par `dagster asset materialize -m toy_assets`).
WORKDIR /opt/dagster/app
COPY toy_assets.py /opt/dagster/app/toy_assets.py
ENV PYTHONPATH=/opt/dagster/app
