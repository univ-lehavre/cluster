# Image Dagster **arm64** construite en interne (étape 1.7, ADR 0026).
#
# POURQUOI : les images Dagster officielles (docker.io/dagster/dagster-celery-k8s)
# sont publiées en **amd64 uniquement** (cf. dagster-io/dagster#11841, #17167) — pas
# d'arm64. Or le banc léger Lima tourne en arm64 (Mac ARM). Dagster étant du **pur
# Python** (« cross-compiles to ARM, no C changes »), l'image arm64 se reconstruit
# trivialement. Sur la topologie bare-metal (x86), on utilise l'image OFFICIELLE
# amd64 ; cette image-ci ne sert que pour l'arch arm64 (banc).
#
# Fidèle au Dockerfile officiel : même base (python:3.10-slim) + mêmes packages,
# version hard-pinnée sur dagster==1.13.7 (verrou chart↔package 1:1, ADR 0006).
#
# Build (depuis ce dossier) :
#   docker buildx build --platform linux/arm64 \
#     -t <registry-interne>/dagster-celery-k8s:1.13.7-arm64 --push .
FROM python:3.10-slim

ARG DAGSTER_VERSION=1.13.7

# uv pour une résolution/installation rapide et déterministe (comme l'officiel).
# IMPORTANT : seul `dagster` est hard-pinné sur la version ; les sous-packages
# (dagster-postgres, dagster-k8s…) ont un schéma de version DIFFÉRENT — pip/uv
# résout les versions compatibles à partir de `dagster==X` (exactement comme le
# Dockerfile officiel, qui ne pinne que `dagster`).
RUN pip install --no-cache-dir -U uv
RUN python -m uv pip install --system \
    dagster==${DAGSTER_VERSION} \
    dagster-postgres \
    dagster-k8s \
    dagster-celery-k8s \
    dagster-celery \
    dagster-aws \
    dagster-graphql \
    dagster-webserver \
    grpcio==1.57.0
