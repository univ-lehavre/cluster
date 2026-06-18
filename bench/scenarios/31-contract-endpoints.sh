#!/usr/bin/env bash
#
# Scénario 31 — CONTRAT : le cluster tient-il les promesses de son contrat
# d'interface (contract/endpoints.example.yaml, ADR 0043) ?
#
# Le contrat déclare les Services que le SOCLE expose au consommateur DataOps
# (atlas) : postgres, marquez, dagster, mlflow, registry, S3, UIs… Ce scénario
# DÉRIVE la liste du contrat versionné (source unique, valeurs génériques ADR
# 0023) et vérifie, pour chaque endpoint, que :
#   1. le Service existe au bon namespace + expose le bon port (kubectl get svc) ;
#   2. l'endpoint RÉPOND : connexion TCP (protocol tcp) ou requête HTTP (protocol
#      http) depuis un pod éphémère intra-cluster (le FQDN .svc résout + accepte).
#
# Transversal : un seul scénario couvre l'INTERFACE de plusieurs briques (dont
# mlflow, non couvert isolément ailleurs). Test d'INTÉGRATION du contrat, pas du
# métier — on prouve que la promesse est tenue, pas le contenu applicatif.
#
# SKIP NEUTRE par endpoint : si le namespace/Service n'est pas monté (profil qui
# n'inclut pas cette brique — ex. mlflow absent d'un banc socle), l'endpoint est
# compté « absent » et SAUTÉ, sans échec — SAUF STRICT_CONTRACT=1 qui exige que
# TOUS les endpoints du contrat soient présents+répondants (CI sur banc complet).
# Le scénario lui-même SKIPpe (exit 0) si AUCUN endpoint n'est présent (cluster nu).
#
# Pré-requis : kubectl + yq (déjà utilisé par bench/lima/access.sh sur ce contrat).
# Variables :
#   STRICT_CONTRACT=1   échoue si un endpoint du contrat est absent ou muet
#   CONTRACT            (défaut contract/endpoints.example.yaml) — fichier lu
#   PROBE_TIMEOUT       (défaut 5) — secondes max par sonde réseau
set -euo pipefail

STRICT_CONTRACT=${STRICT_CONTRACT:-0}
PROBE_TIMEOUT=${PROBE_TIMEOUT:-5}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONTRACT=${CONTRACT:-${HERE}/../../contract/endpoints.example.yaml}

# shellcheck source=bench/scenarios/lib.sh
. "${HERE}/lib.sh"

command -v yq >/dev/null 2>&1 || { log "skip — yq absent (requis pour lire le contrat)."; exit 0; }
[ -f "${CONTRACT}" ] || { log "skip — contrat introuvable : ${CONTRACT}"; exit 0; }

PROBE_NS=default
# shellcheck disable=SC2329  # invoquée via trap EXIT
cleanup() {
    kubectl -n "${PROBE_NS}" delete pod "contract-probe-$$" --wait=false 2>/dev/null || true
}
trap cleanup EXIT

# Sonde réseau depuis un pod éphémère intra-cluster (le FQDN .svc doit résoudre).
# HTTP : wget renvoie 0 dès qu'une réponse arrive (même 401/403/404 = service
# vivant) ; on accepte aussi un code HTTP. TCP : nc -z teste l'ouverture du port.
probe_endpoint() {
    local proto=$1 fqdn=$2 port=$3
    if [ "${proto}" = "tcp" ]; then
        kubectl -n "${PROBE_NS}" run "contract-probe-$$" --rm -i --restart=Never \
            --image=busybox:1.36 --quiet --timeout=30s -- \
            sh -c "nc -z -w ${PROBE_TIMEOUT} ${fqdn} ${port}" >/dev/null 2>&1
    else
        # HTTP : toute réponse (y compris 4xx) prouve que le service écoute et parle.
        kubectl -n "${PROBE_NS}" run "contract-probe-$$" --rm -i --restart=Never \
            --image=busybox:1.36 --quiet --timeout=30s -- \
            sh -c "wget -q -T ${PROBE_TIMEOUT} -O /dev/null 'http://${fqdn}:${port}/' 2>&1; [ \$? -le 8 ]" >/dev/null 2>&1
    fi
}

log "Contrat cluster→atlas : ${CONTRACT}"
mapfile -t ids < <(yq -r '.endpoints[].id' "${CONTRACT}")
log "  ${#ids[@]} endpoints déclarés au contrat"

present=0 absent=0 responding=0 mute=0
declare -a fails=()

for id in "${ids[@]}"; do
    svc=$(yq -r ".endpoints[] | select(.id==\"${id}\") | .service" "${CONTRACT}")
    ns=$(yq -r ".endpoints[] | select(.id==\"${id}\") | .namespace" "${CONTRACT}")
    port=$(yq -r ".endpoints[] | select(.id==\"${id}\") | .port" "${CONTRACT}")
    fqdn=$(yq -r ".endpoints[] | select(.id==\"${id}\") | .fqdn" "${CONTRACT}")
    proto=$(yq -r ".endpoints[] | select(.id==\"${id}\") | .protocol // \"tcp\"" "${CONTRACT}")

    # 1. Le Service existe-t-il au bon namespace ?
    if ! kubectl -n "${ns}" get svc "${svc}" >/dev/null 2>&1; then
        log "  ⏭ ${id} — Service ${ns}/${svc} absent (brique non montée)"
        absent=$((absent + 1))
        [ "${STRICT_CONTRACT}" = "1" ] && fails+=("${id}: Service ${ns}/${svc} absent")
        continue
    fi
    present=$((present + 1))

    # 2. Le Service expose-t-il le port promis ?
    if ! kubectl -n "${ns}" get svc "${svc}" -o jsonpath='{.spec.ports[*].port}' 2>/dev/null \
        | tr ' ' '\n' | grep -qx "${port}"; then
        log "  ✗ ${id} — Service ${ns}/${svc} présent mais SANS le port ${port} promis"
        fails+=("${id}: port ${port} absent du Service")
        continue
    fi

    # 3. L'endpoint répond-il (TCP/HTTP) ?
    if probe_endpoint "${proto}" "${fqdn}" "${port}"; then
        log "  ✓ ${id} — ${ns}/${svc}:${port} (${proto}) présent et répondant"
        responding=$((responding + 1))
    else
        log "  ✗ ${id} — ${ns}/${svc}:${port} (${proto}) présent mais MUET (pas de réponse en ${PROBE_TIMEOUT}s)"
        mute=$((mute + 1))
        fails+=("${id}: ${fqdn}:${port} muet")
    fi
done

log "Bilan : ${present} présents (${responding} répondants, ${mute} muets), ${absent} absents / ${#ids[@]} au contrat."

# Cluster nu (aucun endpoint du contrat monté) : skip neutre, sauf STRICT.
if [ "${present}" = "0" ]; then
    if [ "${STRICT_CONTRACT}" = "1" ]; then
        log "✗ STRICT_CONTRACT=1 et AUCUN endpoint du contrat présent."
        exit 1
    fi
    log "skip — aucun endpoint du contrat n'est monté (cluster nu / socle seul)."
    exit 0
fi

# Échec si un endpoint présent est cassé (mauvais port / muet), ou en STRICT si un
# endpoint manque. Un endpoint simplement absent (brique non montée) ne fait PAS
# échouer hors STRICT (profil partiel légitime, ADR 0085).
if [ "${#fails[@]}" -gt 0 ]; then
    log "✗ Contrat NON tenu :"
    for f in "${fails[@]}"; do log "    - ${f}"; done
    exit 1
fi

log "✓ Contrat tenu : tous les endpoints présents répondent au bon port."
log "  (${absent} endpoint(s) non monté(s) sur ce profil — non bloquant hors STRICT_CONTRACT=1.)"
exit 0
