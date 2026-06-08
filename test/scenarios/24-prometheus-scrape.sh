#!/usr/bin/env bash
#
# Scénario 24 — OBSERVABILITÉ : Prometheus scrape-t-il ses targets, Grafana est-il up ?
#
# Éprouve la stack métriques montée par `run-phases.sh monitoring` (#158,
# kube-prometheus-stack). Monté ≠ éprouvé : ici on vérifie que Prometheus a des
# targets UP réelles (il scrape vraiment) et que Grafana répond à son health.
#
# INDÉPENDANT du déploiement : assume la stack déjà montée. SKIP NEUTRE (exit 0)
# si la stack est absente — sauf STRICT_MON=1 qui fait alors ÉCHOUER (CI sur un
# banc où monitoring tourne ; calque STRICT_OL du scénario 23).
#
# Pré-requis : kubectl (kube-prometheus-stack déployé).
# Variables :
#   STRICT_MON=1   échoue (au lieu de skip) si la stack n'est pas montée
#   MON_NS         (défaut monitoring) — namespace de la stack
set -euo pipefail

STRICT_MON=${STRICT_MON:-0}
MON_NS=${MON_NS:-monitoring}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

PROM_SVC="kube-prometheus-stack-prometheus.${MON_NS}.svc.cluster.local:9090"
GRAFANA_SVC="kube-prometheus-stack-grafana.${MON_NS}.svc.cluster.local:80"

# ── Pré-requis : la stack est-elle montée ? ──
stack_present=1
kubectl -n "${MON_NS}" get sts prometheus-kube-prometheus-stack-prometheus >/dev/null 2>&1 || stack_present=0
kubectl -n "${MON_NS}" get deploy kube-prometheus-stack-grafana >/dev/null 2>&1 || stack_present=0

if [ "$stack_present" != "1" ]; then
    if [ "$STRICT_MON" = "1" ]; then
        log "✗ STRICT_MON=1 et stack monitoring non montée (Prometheus et/ou Grafana absents)."
        log "  Attendu après 'test/lima/run-phases.sh monitoring'."
        exit 1
    fi
    log "skip — stack monitoring non montée (Prometheus et/ou Grafana absents)."
    log "  Monter d'abord : test/lima/run-phases.sh monitoring"
    exit 0
fi
log "✓ Prometheus + Grafana déployés — vérification du scrape et du health"

# ── Probe HTTP depuis le cluster (Service ClusterIP) ──
# $1 = URL ; renvoie le corps. Pod jetable busybox (comme le scénario 23).
cluster_get() {
    kubectl -n "${MON_NS}" run mon-probe-$$ --rm -i --restart=Never \
        --image=busybox:1.36 --quiet -- \
        sh -c "wget -qO- '$1' 2>/dev/null" 2>/dev/null
}

# ── 1. Prometheus a-t-il des targets UP ? (preuve qu'il scrape réellement) ──
log "[1/2] Prometheus : targets actives (api/v1/targets)…"
targets_json=$(cluster_get "http://${PROM_SVC}/api/v1/targets?state=active" || true)
# Compte les targets dont health == "up" (sans jq dans busybox : grep sur le JSON).
up_count=$(printf '%s' "${targets_json}" | grep -o '"health":"up"' | wc -l | tr -d ' ')
log "  targets UP : ${up_count}"

if [ "${up_count:-0}" -lt 1 ]; then
    log "✗ Aucune target Prometheus UP — la stack est montée mais ne scrape rien."
    log "  Vérifier les ServiceMonitor/PodMonitor et la découverte des endpoints."
    exit 1
fi

# ── 2. Grafana répond-il à son endpoint de santé ? ──
log "[2/2] Grafana : /api/health…"
health_json=$(cluster_get "http://${GRAFANA_SVC}/api/health" || true)
if printf '%s' "${health_json}" | grep -q '"database":[[:space:]]*"ok"'; then
    log "✓ Grafana health = database ok"
else
    log "✗ Grafana ne rapporte pas database=ok (réponse : ${health_json:-<vide>})"
    exit 1
fi

log "✓ Observabilité métriques opérationnelle : Prometheus scrape ${up_count} target(s), Grafana up."
exit 0
