# Image Dagster + OpenLineage JETABLE pour la validation e2e de la chaîne (#148).
#
# Émetteur de lineage : matérialise un asset trivial (toy_assets.py) qui POST des
# événements OpenLineage RÉELS vers Marquez. Sert UNIQUEMENT au harnais
# `test/lima/run-phases.sh dataops-chain` ; ce n'est pas une brique de production
# (l'orchestrateur Dagster livré reste vide — le code métier vit dans atlas).
#
# arm64 (banc Lima) : Dagster + openlineage sont du pur Python → l'image se
# construit trivialement sur python:3.10-slim (même base que l'image Dagster
# maison, platform/dagster/image/). Hard-pin de dagster sur la version du chart
# (verrou chart↔package 1:1, ADR 0006).
#
# Build (depuis ce dossier) :
#   docker buildx build --platform linux/arm64 \
#     -t registry:80/dagster-openlineage-emit:dev --push platform/dagster/image-openlineage/
FROM python:3.10-slim

ARG DAGSTER_VERSION=1.13.7

RUN pip install --no-cache-dir -U uv
RUN python -m uv pip install --system \
    dagster==${DAGSTER_VERSION} \
    openlineage-python

# Le module d'asset jetable (chargé par `dagster asset materialize -m toy_assets`).
WORKDIR /opt/dagster/app
COPY toy_assets.py /opt/dagster/app/toy_assets.py
ENV PYTHONPATH=/opt/dagster/app
