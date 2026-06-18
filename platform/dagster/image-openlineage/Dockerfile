# Image Dagster + OpenLineage + MLflow JETABLE — code-location jouet (#148, ADR 0086).
#
# Le module toy_assets.py expose : `toy_dataset` (émet du lineage OpenLineage vers
# Marquez) et `toy_drift` (logge un drift_score jouet dans MLflow). Sert au harnais
# (`dataops-chain`) et à la code-location gRPC jouet (scénario 27/29). Ce n'est PAS
# une brique de production (l'orchestrateur Dagster livré reste vide — métier dans atlas).
#
# arm64 (banc Lima) : Dagster + openlineage + mlflow-skinny sont du pur Python → l'image
# se construit sur python:3.10-slim (même base que platform/dagster/image/). Hard-pin de
# dagster sur la version du chart (verrou chart↔package 1:1, ADR 0006).
# mlflow-skinny (client seul, ~50 Mo) et NON mlflow complet (serveur + scipy/sklearn) :
# image légère. Le VRAI calcul Evidently (deps lourdes) viendra dans une étape ultérieure.
#
# Build (depuis ce dossier) :
#   docker buildx build --platform linux/arm64 \
#     -t registry:80/dagster-openlineage-emit:dev --push platform/dagster/image-openlineage/
FROM python:3.10-slim

ARG DAGSTER_VERSION=1.13.7

RUN pip install --no-cache-dir -U uv
RUN python -m uv pip install --system \
    dagster==${DAGSTER_VERSION} \
    openlineage-python \
    mlflow-skinny==2.17.2

# Le module d'asset jetable (chargé par `dagster asset materialize -m toy_assets`).
WORKDIR /opt/dagster/app
COPY toy_assets.py /opt/dagster/app/toy_assets.py
ENV PYTHONPATH=/opt/dagster/app
