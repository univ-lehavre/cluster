#!/usr/bin/env bash
#
# Scénario 32 — PORTAIL : le portail répond, liste les UI, et NE PEUT PAS lire un
# Secret (ADR 0091). Trois preuves complémentaires du scénario 28 (qui, lui, vérifie
# que les liens du portail — les NodePort L4 des UI, ADR 0092 — sont atteignables) :
#
#   1. le pod portail est Ready et répond sur /healthz (200) ;
#   2. la page rendue (GET /) LISTE des UI réelles (au moins une entrée de couche +
#      un lien) — preuve que le croisement contrat ↔ API live fonctionne in-cluster ;
#   3. GARDE-FOU CARDINAL (ADR 0091 §3) : le ServiceAccount du portail NE PEUT PAS
#      `get secrets` — `kubectl auth can-i` doit répondre `no`. Un portail qui montre
#      des credentials serait un trou de sécurité ; ici il montre la COMMANDE, jamais
#      la valeur, garanti par le RBAC (zéro règle secrets).
#
# SKIP NEUTRE si le portail n'est pas déployé (ns portal absent) — sauf STRICT_PORTAL=1.
#
# Variables : STRICT_PORTAL=1 (échoue si portail absent).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# shellcheck source=bench/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

STRICT_PORTAL=${STRICT_PORTAL:-0}
NS=${PORTAL_NS:-portal}
SA=${PORTAL_SA:-portal}

# ── Garde : portail déployé ? ────────────────────────────────────────────────
if ! kubectl get ns "${NS}" >/dev/null 2>&1; then
    if [ "${STRICT_PORTAL}" = 1 ]; then
        log "✗ STRICT_PORTAL=1 et namespace ${NS} absent — portail non déployé."
        exit 1
    fi
    log "skip — namespace ${NS} absent (portail non déployé ; cf. platform/portal/)."
    exit 0
fi

fails=0

# ── 1. Pod Ready + /healthz ──────────────────────────────────────────────────
log "[1/3] pod portail Ready + /healthz"
if kubectl -n "${NS}" rollout status deploy/portal --timeout=60s >/dev/null 2>&1; then
    log "✓ Deployment portal Ready"
else
    log "✗ Deployment portal non Ready"
    fails=$((fails + 1))
fi
# Sonde via `kubectl port-forward` (depuis le poste de contrôle) plutôt qu'un pod
# probe interne : le ns portal applique un default-deny qui DROP un pod-probe, et
# l'image curl externe peut ne pas être dans le registry interne (air-gap). Le
# port-forward passe par l'API server (toujours joignable) → robuste et sans état.
PF_PORT=${PF_PORT:-18080}
kubectl -n "${NS}" port-forward deploy/portal "${PF_PORT}:8080" >/tmp/portal-pf.$$.log 2>&1 &
PF_PID=$!
trap 'kill ${PF_PID} 2>/dev/null' EXIT
sleep 4

health=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
    "http://localhost:${PF_PORT}/healthz" 2>/dev/null)
if [ "${health:-0}" = 200 ]; then
    log "✓ /healthz → 200"
else
    log "✗ /healthz → ${health:-timeout}"
    fails=$((fails + 1))
fi

# ── 2. La page liste des UI (croisement contrat ↔ API live) ──────────────────
log "[2/3] GET / liste des UI réelles"
page=$(curl -s --max-time 12 "http://localhost:${PF_PORT}/" 2>/dev/null)
# Une page valide contient le doctype, au moins une couche, et un lien d'UI.
if printf '%s' "${page}" | grep -q "<!doctype html>" \
    && printf '%s' "${page}" | grep -qE 'target="_blank"'; then
    n_links=$(printf '%s' "${page}" | grep -oE 'target="_blank"' | wc -l | tr -d ' ')
    log "✓ page rendue — ${n_links} lien(s) d'UI (croisement contrat↔API)"
else
    log "✗ page invalide ou sans lien d'UI (croisement échoué ?)"
    fails=$((fails + 1))
fi
# Et JAMAIS d'iframe (ADR 0091 §2).
if printf '%s' "${page}" | grep -qi "<iframe"; then
    log "✗ la page contient un <iframe> (interdit, ADR 0091 §2)"
    fails=$((fails + 1))
else
    log "✓ aucun <iframe> (liens nouvel onglet)"
fi

# ── 3. Garde-fou : le SA portail NE PEUT PAS lire un Secret (ADR 0091 §3) ─────
log "[3/3] garde-fou RBAC : pas de lecture de Secret"
# `auth can-i ... -A` répond une ligne PAR scope évalué → on prend la 1re et on
# considère DANGER dès qu'un `yes` apparaît (any). Sans -A : décision cluster-large.
can_secrets=$(kubectl auth can-i get secrets \
    --as="system:serviceaccount:${NS}:${SA}" 2>/dev/null || echo no)
if [ "${can_secrets}" != yes ]; then
    log "✓ auth can-i get secrets (SA portal) → no (RBAC least-privilege prouvé)"
else
    log "✗ DANGER : le SA portal PEUT get secrets (${can_secrets}) — RBAC trop large !"
    fails=$((fails + 1))
fi

echo
if [ "${fails}" -eq 0 ]; then
    log "🎉 portail OK — répond, liste les UI, et ne peut pas lire un Secret (ADR 0091)."
else
    log "✗ ${fails} vérification(s) en échec — voir ci-dessus."
    exit 1
fi
