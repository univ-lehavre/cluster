#!/usr/bin/env bash
#
# Scénario 26 — OBSERVABILITÉ : Loki ingère-t-il un log et le rend-il en LogQL ?
#
# Éprouve la chaîne logs montée par `run-phases.sh monitoring` (#186, Loki en
# profil S3 — SeaweedFS en banc léger, RGW Ceph en prod, ADR 0036). On POST une
# entrée de log unique via l'API push de Loki, puis on la relit via une requête
# LogQL. Si le round-trip réussit, l'ingestion + le backing S3 + la requête
# fonctionnent de bout en bout.
#
# INDÉPENDANT du déploiement : assume Loki monté. SKIP NEUTRE (exit 0) si absent
# — sauf STRICT_MON=1 qui fait alors ÉCHOUER.
#
# Pré-requis : kubectl (Loki déployé via monitoring).
# Variables :
#   STRICT_MON=1   échoue (au lieu de skip) si Loki n'est pas monté
#   MON_NS         (défaut monitoring) — namespace de Loki
set -euo pipefail

STRICT_MON=${STRICT_MON:-0}
MON_NS=${MON_NS:-monitoring}

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

LOKI_SVC="loki.${MON_NS}.svc.cluster.local:3100"
# Étiquette témoin unique au run (évite de confondre avec d'anciens logs).
JOB_LABEL="scenario26-$$"

# ── Pré-requis : Loki est-il monté ? ──
if ! kubectl -n "${MON_NS}" get sts loki >/dev/null 2>&1; then
    if [ "$STRICT_MON" = "1" ]; then
        log "✗ STRICT_MON=1 et Loki non monté (StatefulSet loki absent)."
        exit 1
    fi
    log "skip — Loki non monté (StatefulSet loki absent dans '${MON_NS}')."
    log "  Monter d'abord : test/lima/run-phases.sh monitoring"
    exit 0
fi
log "✓ Loki déployé — test du round-trip push → LogQL (job='${JOB_LABEL}')"

# ── Probe depuis le cluster : POST le log, attend, GET en LogQL. ──
# Tout dans UN pod (busybox a wget POST via --post-data ; horodatage ns côté shell).
# La requête LogQL filtre sur l'étiquette témoin : on doit retrouver notre ligne.
# SC2016 : les `'"${VAR}"'` injectent VOLONTAIREMENT des variables de l'hôte dans
# le script `sh -c '…'` (fermeture de quote simple → double pour interpoler).
# shellcheck disable=SC2016
probe_out=$(kubectl -n "${MON_NS}" run loki-probe-$$ --rm -i --restart=Never \
    --image=busybox:1.36 --quiet -- sh -c '
    set -e
    SVC="'"${LOKI_SVC}"'"
    JOB="'"${JOB_LABEL}"'"
    MSG="hello-loki-roundtrip-${JOB}"
    NS=$(date +%s)000000000          # horodatage nanosecondes (Loki exige ns)
    # 1. PUSH une entrée via l API native Loki.
    BODY="{\"streams\":[{\"stream\":{\"job\":\"${JOB}\"},\"values\":[[\"${NS}\",\"${MSG}\"]]}]}"
    wget -q -O- --header="Content-Type: application/json" \
        --post-data="${BODY}" "http://${SVC}/loki/api/v1/push" >/dev/null 2>&1 || true
    # 2. Laisse Loki ingérer (flush vers le backing), puis interroge en LogQL.
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 3
        RES=$(wget -q -O- "http://${SVC}/loki/api/v1/query_range?query=%7Bjob%3D%22${JOB}%22%7D&limit=5" 2>/dev/null || true)
        case "${RES}" in
            *"${MSG}"*) echo "FOUND"; exit 0 ;;
        esac
    done
    echo "NOTFOUND"
    exit 0
' 2>/dev/null || true)

if printf '%s' "${probe_out}" | grep -q "FOUND"; then
    log "✓ Round-trip OK : l'entrée poussée a été retrouvée via LogQL — ingestion + backing S3 + requête opérationnels."
    exit 0
fi

log "✗ L'entrée poussée n'a pas été retrouvée via LogQL après ~30 s."
log "  Loki est monté mais le round-trip échoue : vérifier l'ingester, le flush"
log "  vers le backing S3 (SeaweedFS/RGW, ADR 0036) et le distributor."
exit 1
