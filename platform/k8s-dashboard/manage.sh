#!/usr/bin/env bash
#
# Installe ou met à jour le Kubernetes Dashboard via Helm.
# Version du chart figée (reproductibilité) — voir `CHART_VERSION` ci-dessous.
# Pour bumper, vérifier d'abord la matrice de compatibilité (ADR 0006).
set -euo pipefail

# Chart kubernetes-dashboard : la 7.x est l'architecture multi-container
# (API/Web/Metrics-Scraper/Auth/Kong) ; à bumper conjointement à K8s
# (compat 1.34 vérifiée par le release notes du chart).
CHART_VERSION=${CHART_VERSION:-7.10.0}

helm repo add kubernetes-dashboard https://kubernetes.github.io/dashboard/ 2>/dev/null || true
helm repo update kubernetes-dashboard

# `--wait` : helm bloque jusqu'à ce que tous les pods soient Ready.
# `-f values.yaml` : applique resources + tuning local (versionné dans ce dépôt).
helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard \
    --version "${CHART_VERSION}" \
    --create-namespace --namespace kubernetes-dashboard \
    --values "$(dirname "$0")/values.yaml" \
    --wait

# Exposition L4 NodePort (ADR 0092) : Service SÉPARÉ qui ne touche pas le chart
# (CLAUDE.md interdit d'éditer les bundles vendored). Appliqué APRÈS l'UI Helm
# (le Service sélectionne les endpoints Kong déployés ci-dessus). nodePort
# auto-attribué par Kubernetes (non figé). Lire l'URL avec :
#   kubectl -n kubernetes-dashboard get svc kubernetes-dashboard-nodeport \
#       -o jsonpath='{.spec.ports[0].nodePort}'
kubectl apply -n kubernetes-dashboard -f "$(dirname "$0")/nodeport.yaml"
