# Image du PORTAIL d'accès aux UI (ADR 0091). Serveur HTTP MINCE qui lit l'API k8s
# (lecture seule, RBAC SANS secrets) et rend une page sidebar (liens nouvel onglet +
# commandes secret). Logique pure dans nestor/portal.py ; I/O + serveur dans
# nestor/portal_server.py (stdlib http.server → pas de framework, image légère).
#
# Build (depuis la RACINE du dépôt — le contexte inclut nestor/ et contract/) :
#   docker buildx build --platform linux/arm64,linux/amd64 \
#     -t registry:80/portal:dev --push -f platform/portal/image/Dockerfile .
FROM python:3.12-slim@sha256:9c1d9ed7593f2552a4ea47362ec0d2ddf5923458a53d0c8e30edf8b398c94a31

# Deux dépendances seulement : client k8s (lecture API) + pyyaml (charger le contrat).
# Épinglées (ADR 0006) ; alignées sur la matrice du dépôt (kubernetes>=31,<37).
RUN pip install --no-cache-dir kubernetes==31.0.0 pyyaml==6.0.2

# Code : le paquet nestor (portal + portal_server) et le contrat versionné, embarqué.
WORKDIR /app
COPY nestor/portal.py nestor/portal_server.py /app/nestor/
COPY contract/endpoints.example.yaml /etc/portal/endpoints.yaml
# `nestor` doit être importable comme paquet : un __init__ minimal (pas tout le paquet,
# pour garder l'image mince — portal_server n'importe que `from nestor import portal`).
RUN touch /app/nestor/__init__.py
# PORTAL_LISTEN_PORT (hors du pattern `<SVC>_PORT` que k8s injecte par Service —
# `PORTAL_PORT` collisionnerait avec la variable auto du Service `portal`).
ENV PYTHONPATH=/app PORTAL_CONTRACT=/etc/portal/endpoints.yaml PORTAL_LISTEN_PORT=8080

# Durcissement (ADR 0014) : utilisateur non-root dédié (le Deployment ajoute
# runAsNonRoot/seccomp/FS RO — ici on crée l'UID pour cohérence). Pas de shell requis.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin portal
USER 10001

EXPOSE 8080
ENTRYPOINT ["python", "-m", "nestor.portal_server"]
