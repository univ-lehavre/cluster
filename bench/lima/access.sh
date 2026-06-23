#!/usr/bin/env bash
#
# Accès développeur au banc Lima — UNE commande pour « git push et ça marche »
# (#232, ADR 0048). Le développeur data travaille dans le dépôt `atlas` ; il ne
# doit PAS opérer le cluster. Ce script rend le banc consommable depuis l'hôte :
#
#   1. lit le CONTRAT : les endpoints `exposed: true` (UI exposées en L4) ;
#   2. pour chacun, lit le nodePort RÉEL du Service NodePort `<service>-nodeport`
#      et l'IP interne d'un nœud Ready ;
#   3. rend l'UI cliquable depuis le Mac (cf. NUANCE BANC ci-dessous) ;
#   4. récupère et regroupe les secrets/tokens (un seul écran) ;
#   5. génère `../atlas/.env.cluster.local` (gitignoré) consommable par atlas.
#
# EXPOSITION L4 NodePort (ADR 0092, remplace le Gateway L7 d'ADR 0071) — plus de
# DNS, plus de SNI, plus de TLS de bordure : un Service `type: NodePort`
# (`<service>-nodeport`) sert l'UI en HTTP clair sur `http://<IP-nœud>:<nodePort>`.
# Plus AUCUN Gateway, plus AUCUN forward SSH, plus AUCUN bloc /etc/hosts.
#
# NUANCE BANC LIMA (cruciale) : le réseau Lima (vmnet/vz) est ISOLÉ du Mac → le
# poste de contrôle n'atteint PAS l'IP interne du nœud (`10.x` user-v2). Pour
# rendre l'UI cliquable DEPUIS LE MAC, on ouvre donc un
# `kubectl port-forward svc/<service>-nodeport <localport>:<port>` en arrière-plan
# (PAS de forward SSH, PAS de Gateway) et on affiche `http://127.0.0.1:<localport>`.
#   → EN PROD le poste atteint directement le réseau des nœuds : l'accès se fait
#     en `http://<IP-nœud>:<nodePort>` SANS port-forward (cf. node_internal_ip /
#     le nodePort affichés en complément). Ce script tourne AU BANC, donc il pose
#     le port-forward ; la prod est en accès direct (ADR 0092 §«topologie d'accès»).
#
# Source de vérité : contract/endpoints.example.yaml (`exposed`/layer/auth) —
# rien n'est codé en dur (ADR 0023). Orchestration de CLIs → bash (ADR 0017) ;
# la LOGIQUE DE DÉCISION pure (port hôte par index, ligne d'URL, lignes .env)
# est isolée en fonctions testables (bench/unit/access.bats), sans cluster.
#
# Tout l'état (port-forwards) est posé par du CODE reproductible — pas de
# `kubectl apply`/`port-forward` manuel laissé en place (ADR 0046).
#
# Usage :
#   bench/lima/access.sh            # ouvre les port-forwards + affiche URLs/secrets + .env
#   bench/lima/access.sh --stop     # arrête les kubectl port-forward
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=bench/lima/lib.sh
. "${HERE}/lib.sh" # log/ok/warn/die/need + REPO

KUBECONFIG_LOCAL="${KUBECONFIG_LOCAL:-${HERE}/.work/kubeconfig}"
KUBECTL=(kubectl --kubeconfig "${KUBECONFIG_LOCAL}")
CONTRACT="${CONTRACT:-${REPO}/contract/endpoints.example.yaml}"
ATLAS_DIR="${ATLAS_DIR:-${REPO}/../atlas}" # dépôt applicatif voisin (../atlas)
# Port hôte de base du port-forward banc : la i-ème UI écoute sur BASE+i (8443,
# 8444, …). Non privilégié → aucun sudo. NB : c'est un port LOCAL du Mac ; il ne
# vaut QU'AU BANC (en prod on vise directement <IP-nœud>:<nodePort>, cf. en-tête).
BASE_PORT="${BASE_PORT:-8443}"

# ════════════════════════════════════════════════════════════════════════════
# Fonctions PURES (aucun kubectl / réseau / sudo) — testées en bats.
# ════════════════════════════════════════════════════════════════════════════

# host_port_for INDEX → port hôte local du port-forward de la i-ème UI
# (BASE_PORT + INDEX). Au banc uniquement (cf. en-tête).
host_port_for() { printf '%s\n' "$((BASE_PORT + $1))"; }

# url_line LAYER URL AUTH → ligne d'affichage alignée d'une UI (pure, testable).
# Forme : `    [<layer>] <url>   (auth: <auth>)`.
url_line() {
    printf '    [%-10s] %s   (auth: %s)\n' "$1" "$2" "$3"
}

# env_line KEY VALUE → ligne `KEY=VALUE` pour le .env (valeur vide tolérée).
env_line() { printf '%s=%s\n' "$1" "${2:-}"; }

# read_lines VAR < flux → peuple le tableau nommé VAR (une entrée par ligne).
# Substitut portable de `mapfile`/`readarray`, absents du bash 3.2 de macOS
# (le banc tourne sur le poste de contrôle).
read_lines() {
    local __name=$1 __line
    eval "${__name}=()"
    while IFS= read -r __line; do
        eval "${__name}+=(\"\${__line}\")"
    done
}

# ════════════════════════════════════════════════════════════════════════════
# Lecture du contrat (yq) — quelles UI exposer (exposed:true → NodePort L4).
# ════════════════════════════════════════════════════════════════════════════

# exposed_rows → lignes `namespace<TAB>service<TAB>layer<TAB>auth` des endpoints
# `exposed: true`, triées pour un ordre stable (port hôte par index déterministe).
exposed_rows() {
    yq -r '.endpoints[] | select(.exposed == true)
        | [.namespace, .service, (.layer // "-"), (.auth // "none")]
        | @tsv' "${CONTRACT}" | sort
}

# ════════════════════════════════════════════════════════════════════════════
# Actions impures (kubectl, sudo) — orchestration.
# ════════════════════════════════════════════════════════════════════════════

svc_exists() { "${KUBECTL[@]}" -n "$1" get svc "$2" -o name > /dev/null 2>&1; }

# IP interne d'un nœud Ready (status.addresses InternalIP). En PROD c'est l'IP
# que le poste opérateur compose directement (`http://<IP>:<nodePort>`, ADR 0092).
# Banc mono-CP : l'InternalIP du control-plane (non routable depuis le Mac, d'où
# le port-forward — cf. en-tête). Vide si introuvable. `|| true` : sous `set -e`,
# un kubectl non-zéro (hoquet d'API) ne doit pas tuer `ip=$(node_internal_ip)`.
node_internal_ip() {
    "${KUBECTL[@]}" get nodes \
        -l node-role.kubernetes.io/control-plane \
        -o 'jsonpath={.items[0].status.addresses[?(@.type=="InternalIP")].address}' \
        2> /dev/null || true
}

# node_port_of NS SERVICE → nodePort RÉEL du Service NodePort `<service>-nodeport`
# (.spec.ports[0].nodePort). Vide si le Service manque. `|| true` : idem ci-dessus.
node_port_of() {
    "${KUBECTL[@]}" -n "$1" get svc "$2-nodeport" \
        -o 'jsonpath={.spec.ports[0].nodePort}' 2> /dev/null || true
}

# Ouvre un kubectl port-forward 127.0.0.1:<lport> → svc/<service>-nodeport:<port>
# en arrière-plan (BANC : le réseau Lima est isolé du Mac, cf. en-tête). PAS de
# forward SSH, PAS de Gateway (ADR 0092). IMPORTANT : `kubectl port-forward` mis
# en arrière-plan HÉRITE des descripteurs du script — si on ne ferme pas
# stdin/out/err, un `| tail` en aval reste bloqué (le pipe ne se ferme jamais).
# On détache donc explicitement les 3 flux.
open_forward() {
    local lport=$1 ns=$2 svc=$3 port=$4
    pkill -f "kubectl.*port-forward.*127.0.0.1:${lport}:" 2> /dev/null || true
    "${KUBECTL[@]}" -n "${ns}" port-forward "svc/${svc}-nodeport" \
        "127.0.0.1:${lport}:${port}" < /dev/null > /dev/null 2>&1 &
    disown 2> /dev/null || true
}

# Pour chaque UI exposée : lit le nodePort réel → ouvre un port-forward banc sur
# BASE_PORT+index. Mémorise hostname→ligne d'URL dans UI_LINES (affichage/.env).
#
# NB : on COLLECTE d'abord les lignes du contrat dans un tableau, PUIS on itère —
# au lieu de `while … < <(exposed_rows)`. Raison : le `kubectl port-forward`
# détaché hériterait du descripteur du process substitution et le maintiendrait
# ouvert → la boucle `read` ne verrait jamais EOF (script bloqué). Collecte
# préalable = pas de FD hérité par le port-forward d'arrière-plan.
declare -a UI_LINES=()
start_forwards() {
    log "Ouverture des port-forwards (un par UI exposée → Service NodePort)"
    log "  BANC : le réseau Lima est isolé du Mac → port-forward kubectl (pas de"
    log "  forward SSH, pas de Gateway). EN PROD : accès direct http://<IP-nœud>:<nodePort>."
    UI_LINES=()
    local node_ip
    node_ip=$(node_internal_ip)
    [ -n "${node_ip}" ] || die "pas d'IP nœud control-plane (banc démarré ?)"
    local rows
    read_lines rows < <(exposed_rows)
    local i=0 row ns svc layer auth nodeport lport
    for row in "${rows[@]}"; do
        IFS=$'\t' read -r ns svc layer auth <<< "${row}"
        if ! svc_exists "${ns}" "${svc}-nodeport"; then
            warn "${ns}/${svc} : Service ${svc}-nodeport absent — UI ignorée"
            i=$((i + 1))
            continue
        fi
        nodeport=$(node_port_of "${ns}" "${svc}")
        if [ -z "${nodeport}" ]; then
            warn "${ns}/${svc} : nodePort introuvable — UI ignorée"
            i=$((i + 1))
            continue
        fi
        lport=$(host_port_for "${i}")
        if open_forward "${lport}" "${ns}" "${svc}" "${nodeport}"; then
            ok "${ns}/${svc} → http://127.0.0.1:${lport} (prod : http://${node_ip}:${nodeport})"
            # Stocke la ligne d'affichage déjà rendue (banc cliquable + rappel prod).
            UI_LINES+=("$(url_line "${layer}" "http://127.0.0.1:${lport}" "${auth}")")
        else
            warn "${ns}/${svc} : port-forward échoué"
        fi
        i=$((i + 1))
    done
}

stop_forwards() {
    if pkill -f "kubectl.*port-forward" 2> /dev/null; then
        ok "kubectl port-forwards arrêtés"
    else
        warn "aucun kubectl port-forward actif"
    fi
}

# Lit une clé d'un Secret (base64 → clair). Vide si le Secret/la clé manquent.
secret_val() {
    local ns=$1 name=$2 key=$3
    "${KUBECTL[@]}" -n "${ns}" get secret "${name}" -o jsonpath="{.data.${key}}" 2> /dev/null \
        | base64 -d 2> /dev/null || true
}

# Affiche les URLs cliquables (port-forward banc) + l'auth attendue.
print_urls() {
    log "UI exposées en L4 NodePort (HTTP clair, réseau privé — ADR 0092/0003)."
    log "  Au BANC : http://127.0.0.1:<port> (port-forward kubectl ci-dessous)."
    log "  En PROD : http://<IP-nœud>:<nodePort> en accès DIRECT (aucun forward)."
    local line
    for line in "${UI_LINES[@]}"; do
        printf '%s' "${line}"
    done
}

# Affiche les secrets/tokens regroupés (un seul écran).
print_secrets() {
    log "Secrets & tokens (lus des Secrets du cluster — ne pas partager)"
    printf '    Argo CD   admin / %s\n' "$(secret_val argocd argocd-initial-admin-secret password)"
    printf '    Gitea     %s / %s\n' \
        "$(secret_val gitea gitea-admin username)" "$(secret_val gitea gitea-admin password)"
    printf '    Grafana   admin / %s\n' "$(secret_val monitoring kube-prometheus-stack-grafana admin-password)"
    local r
    for r in dagster pgvector marquez; do
        printf '    pg/%-8s %s / %s\n' "${r}" \
            "$(secret_val postgres "pg-role-${r}" username)" "$(secret_val postgres "pg-role-${r}" password)"
    done
}

# Génère ../atlas/.env.cluster.local (gitignoré) consommable par atlas.
generate_env() {
    [ -d "${ATLAS_DIR}" ] || { warn "dépôt atlas absent (${ATLAS_DIR}) — .env non généré"; return 0; }
    local out="${ATLAS_DIR}/.env.cluster.local"
    log "Génération de ${out#"${REPO}/../"} (gitignoré)"
    local pg_user pg_pwd
    pg_user=$(secret_val postgres pg-role-pgvector username)
    pg_pwd=$(secret_val postgres pg-role-pgvector password)
    {
        echo "# Généré par cluster/bench/lima/access.sh — NE PAS COMMITER (gitignoré)."
        echo "# Banc Lima local ; valeurs de déploiement (ADR 0023). Régénérer après un run."
        echo "# Postgres : FQDN intra-pod (le code atlas tourne dans le cluster) ou via"
        echo "# un kubectl port-forward dédié si exécuté depuis l'hôte."
        env_line POSTGRES_HOST "pg-rw.postgres.svc.cluster.local"
        env_line POSTGRES_PORT 5432
        env_line POSTGRES_DB pgvector
        env_line POSTGRES_USER "${pg_user}"
        env_line POSTGRES_PASSWORD "${pg_pwd}"
        env_line OPENLINEAGE_URL "http://marquez.marquez.svc.cluster.local:5000"
        env_line OPENLINEAGE_ENDPOINT "api/v1/lineage"
        env_line OPENLINEAGE_NAMESPACE dagster
        env_line REGISTRY "registry:80"
    } > "${out}"
    ok "${out##*/} généré (PG, OpenLineage, registry)"
    warn "Vérifier qu'il est bien ignoré par git côté atlas (/.env.cluster.local)."
}

# ════════════════════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════════════════════
main() {
    local mode="${1:-up}"
    need yq
    need kubectl
    case "${mode}" in
        --stop)
            stop_forwards
            return 0
            ;;
        up) ;;
        *) die "usage : $0 [--stop]" ;;
    esac

    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent (${KUBECONFIG_LOCAL}) — lancer 'run-phases.sh atlas'"
    require_lima
    start_forwards
    print_urls
    print_secrets
    generate_env
    log "Prêt. Travaillez dans ${ATLAS_DIR##*/} ; 'git push' (Gitea → Argo CD réconcilie)."
    log "Pour tout arrêter : $0 --stop"
}

# Exécutable seul ou sourçable (tests bats des fonctions pures).
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
