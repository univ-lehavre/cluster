# Image Marquez API **arm64** construite en interne (étape 1.8, ADR 0028).
#
# POURQUOI : les images Marquez officielles (docker.io/marquezproject/marquez) sont
# publiées en **amd64 uniquement** (vérifié Docker Hub, 0.51.1) — pas d'arm64. Or le
# banc léger Lima tourne en arm64. L'API Marquez est une appli **Java** (JAR sur base
# eclipse-temurin:17, image de base MULTI-ARCH) : elle se reconstruit en arm64 sans
# modification. Sur la topologie bare-metal (x86), on utilise l'image OFFICIELLE
# amd64 (re-taguée registry:80/marquez:0.51.1) ; ce Dockerfile ne sert qu'à l'arch
# arm64 (banc).
#
# FIDÈLE au Dockerfile officiel `Dockerfile` du tag 0.51.1 (reproduit ci-dessous à
# l'identique). Le CONTEXTE de build est le dépôt source Marquez au tag 0.51.1 (il
# faut gradle/, api/, clients/java/…), PAS ce dossier.
#
# Build (depuis un clone du source Marquez au tag 0.51.1) :
#   git clone --depth 1 --branch 0.51.1 https://github.com/MarquezProject/marquez.git
#   docker buildx build --platform linux/arm64 \
#     -t registry:80/marquez:0.51.1 --push \
#     -f platform/marquez/image/Dockerfile marquez/   # contexte = clone source
#
# (En pratique : `-f marquez/Dockerfile marquez/` suffit — ce fichier en est la copie
#  versionnée, pour tracer la provenance et l'invariant arm64 côté dépôt.)
FROM eclipse-temurin:17 AS base
WORKDIR /usr/src/app
COPY gradle gradle
COPY gradle.properties gradle.properties
COPY gradlew gradlew
COPY settings.gradle settings.gradle
RUN ./gradlew --version

FROM base AS build
WORKDIR /usr/src/app
COPY build.gradle build.gradle
COPY api ./api
COPY clients/java ./clients/java
RUN ./gradlew --no-daemon clean :api:shadowJar

FROM eclipse-temurin:17
RUN apt-get update && apt-get install -y postgresql-client bash coreutils
WORKDIR /usr/src/app
COPY --from=build /usr/src/app/api/build/libs/marquez-*.jar /usr/src/app
COPY marquez.dev.yml marquez.dev.yml
COPY docker/entrypoint.sh entrypoint.sh
EXPOSE 5000 5001
ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
