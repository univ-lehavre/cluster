#!/usr/bin/env bash
#
# Scénario 25 — OBSERVABILITÉ : une PrometheusRule déclenche-t-elle bien une alerte ?
#
# Éprouve le pipeline d'alerting (PrometheusRule → évaluation Prometheus →
# Alertmanager) monté par `run-phases.sh monitoring` (#158). On s'appuie sur
# l'alerte `Watchdog` de kube-prometheus-stack : une alerte VOLONTAIREMENT
# toujours `firing` (`expr: vector(1)`), faite pour prouver que la chaîne
# d'alerting est vivante de bout en bout. Si Watchdog ne fire pas, l'alerting
# est cassé — exactement ce qu'on veut détecter.
#
# INDÉPENDANT du déploiement : assume la stack montée. SKIP NEUTRE (exit 0) si
# absente — sauf STRICT_MON=1 qui fait alors ÉCHOUER.
#
# Pré-requis : kubectl (kube-prometheus-stack déployé).
# Variables :
#   STRICT_MON=1   échoue (au lieu de skip) si la stack n'est pas montée
#   MON_NS         (défaut monitoring) — namespace de la stack
#   ALERT_NAME     (défaut Watchdog) — alerte témoin attendue en firing
set -euo pipefail

STRICT_MON=${STRICT_MON:-0}
MON_NS=${MON_NS:-monitoring}
ALERT_NAME=${ALERT_NAME:-Watchdog}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

PROM_SVC="kube-prometheus-stack-prometheus.${MON_NS}.svc.cluster.local:9090"

# ── Pré-requis : la stack est-elle montée ? ──
stack_present=1
kubectl -n "${MON_NS}" get sts prometheus-kube-prometheus-stack-prometheus >/dev/null 2>&1 || stack_present=0
kubectl -n "${MON_NS}" get prometheusrules.monitoring.coreos.com -A >/dev/null 2>&1 || stack_present=0

if [ "$stack_present" != "1" ]; then
    if [ "$STRICT_MON" = "1" ]; then
        log "✗ STRICT_MON=1 et stack monitoring/PrometheusRule non montée."
        exit 1
    fi
    log "skip — stack monitoring non montée (Prometheus et/ou PrometheusRule absents)."
    log "  Monter d'abord : test/lima/run-phases.sh monitoring"
    exit 0
fi
log "✓ Prometheus + PrometheusRule déployés — vérification du firing de '${ALERT_NAME}'"

cluster_get() {
    kubectl -n "${MON_NS}" run alert-probe-$$ --rm -i --restart=Never \
        --image=busybox:1.36 --quiet -- \
        sh -c "wget -qO- '$1' 2>/dev/null" 2>/dev/null
}

# ── L'alerte témoin est-elle firing ? (api/v1/alerts) ──
# Prometheus met ~1 cycle d'évaluation (≈30 s) après démarrage. On retente.
log "[1/1] Prometheus : alerte '${ALERT_NAME}' en état firing ?"
firing=0
for attempt in $(seq 1 10); do
    alerts_json=$(cluster_get "http://${PROM_SVC}/api/v1/alerts" || true)
    # busybox sans jq : on cherche la coïncidence nom d'alerte + state firing.
    if printf '%s' "${alerts_json}" \
        | tr '}' '\n' \
        | grep -A0 "\"alertname\":\"${ALERT_NAME}\"" >/dev/null 2>&1 \
        && printf '%s' "${alerts_json}" | grep -q '"state":"firing"'; then
        firing=1
        break
    fi
    log "  pas encore firing (tentative ${attempt}/10) — attente d'un cycle d'éval…"
    sleep 12
done

if [ "$firing" = "1" ]; then
    log "✓ Alerte '${ALERT_NAME}' est firing — le pipeline PrometheusRule → alerting fonctionne."
    exit 0
fi

log "✗ Alerte '${ALERT_NAME}' jamais vue firing après ~2 min."
log "  Le pipeline d'alerting est cassé : règles non évaluées, ou Prometheus ne"
log "  charge pas les PrometheusRule (vérifier le rule_files / l'operator)."
exit 1
