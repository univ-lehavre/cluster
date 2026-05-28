#!/usr/bin/env bash
#
# Génère un token d'authentification éphémère pour le compte
# `admin-user` du Kubernetes Dashboard.
#
# Choix de conception (ADR 0010 — dashboard = cluster-admin assumé) :
# - pas de Secret `kubernetes.io/service-account-token` persistant dans
#   `etcd` (anti-pattern depuis K8s 1.24, jamais rotaté) ;
# - token TokenRequest API à durée limitée (8 h par défaut) à coller dans
#   l'écran de login du dashboard.
#
# Usage :
#   ./credentials.sh                 # token 8 h
#   ./credentials.sh 30m             # token 30 min (durée Go : ex. 1h30m)
set -euo pipefail

DURATION=${1:-8h}

kubectl -n kubernetes-dashboard create token admin-user --duration="${DURATION}"
