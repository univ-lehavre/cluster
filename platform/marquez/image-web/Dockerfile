# Image Marquez **web (UI)** arm64 construite en interne (étape 1.8, ADR 0028).
#
# POURQUOI : l'image officielle docker.io/marquezproject/marquez-web est publiée en
# **amd64 uniquement** (vérifié Docker Hub, 0.51.1). L'UI est une appli React buildée
# sous **node:18-alpine** (image de base MULTI-ARCH) : elle se reconstruit en arm64
# sans modification. Sur bare-metal (x86), on utilise l'image OFFICIELLE amd64
# (re-taguée registry:80/marquez-web:0.51.1) ; ce Dockerfile ne sert qu'à l'arm64.
#
# FIDÈLE au Dockerfile officiel `web/Dockerfile` du tag 0.51.1 (reproduit à
# l'identique). Le CONTEXTE de build est le sous-dossier `web/` du source Marquez au
# tag 0.51.1, PAS ce dossier.
#
# Build (depuis un clone du source Marquez au tag 0.51.1) :
#   git clone --depth 1 --branch 0.51.1 https://github.com/MarquezProject/marquez.git
#   docker buildx build --platform linux/arm64 \
#     -t registry:80/marquez-web:0.51.1 --push \
#     -f platform/marquez/image-web/Dockerfile marquez/web/   # contexte = web/ du source
FROM node:18-alpine
WORKDIR /usr/src/app

ARG REACT_APP_ADVANCED_SEARCH

RUN apk update && apk add --virtual bash coreutils
RUN apk add --no-cache git
COPY package*.json ./

ENV REACT_APP_ADVANCED_SEARCH=$REACT_APP_ADVANCED_SEARCH

RUN npm install
COPY . .
RUN REACT_APP_ADVANCED_SEARCH=$REACT_APP_ADVANCED_SEARCH npm run build
COPY docker/entrypoint.sh entrypoint.sh
EXPOSE 3000
ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
