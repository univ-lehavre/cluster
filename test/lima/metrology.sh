#!/usr/bin/env bash
#
# Métrologie du banc Lima — historique des runs, métriques (durée, CPU×temps,
# RAM, Prometheus) et helpers de fraîcheur. SOURCÉ par run-phases.sh.
#
# Séparé de lib.sh (plomberie Lima) et de run-phases.sh (orchestration) pour
# isoler les FONCTIONS PURES (parsing, calcul, sérialisation YAML d'une entrée)
# qui sont testées par bats (test/unit/metrology.bats) sans monter de VM.
#
# Artefacts :
#   - test/lima/runs-history.yaml  : VERSIONNÉ (preuve datée, ADR 0042/0034).
#                                    Une entrée append par run `all` complété.
#   - test/lima/.work/metrics.txt  : éphémère, en-tête matériel + durées (existant).
#
# Schéma d'une entrée (cf. #216) :
#   - id, date (ISO 8601 UTC), branche, commit, profil, topologie, arch,
#     hote, phases (nom: durée_s), total_s, et — si Prometheus échantillonné
#     (#217) — metriques (cpu_core_s, ram_peak_mib, ram_mean_mib).
#
# Pourquoi un fichier YAML versionné plutôt que le mtime Git : le checkout CI ne
# préserve pas les dates de fichiers (ADR 0042 §3) — la date vit DANS le contenu.

# ── Fonctions pures (testées bats) ───────────────────────────────────────────

# Identifiant de run stable et citable : <date compacte>-<profil>-<commit court>.
# Déterministe (pas de hasard) : dérivé des arguments, pas de l'horloge interne.
# Usage : metro_run_id <iso_date> <profil> <commit_court>
metro_run_id() {
    local iso=$1 profil=$2 commit=$3 compact
    # Garde la date + l'heure lisibles : "AAAA-MM-JJTHH" (13 premiers caractères
    # de l'ISO), suivies du profil et du commit court.
    compact=$(printf '%s' "${iso}" | cut -c1-13)
    printf '%s-%s-%s' "${compact}" "${profil}" "${commit}"
}

# Profil du run, dérivé de WITH_CEPH (la source de vérité du harnais).
# Usage : metro_profil <with_ceph>
metro_profil() {
    [ "${1:-0}" = 1 ] && printf 'ceph' || printf 'local-path'
}

# Nombre de jours entiers entre deux dates epoch (secondes). Négatif borné à 0.
# Usage : metro_age_days <epoch_passe> <epoch_maintenant>
metro_age_days() {
    local past=$1 now=$2 diff
    diff=$(( (now - past) / 86400 ))
    [ "${diff}" -lt 0 ] && diff=0
    printf '%d' "${diff}"
}

# Verdict de fraîcheur : "frais" si age <= seuil, sinon "perime".
# Usage : metro_freshness_verdict <age_jours> <seuil_jours>
metro_freshness_verdict() {
    local age=$1 seuil=$2
    [ "${age}" -le "${seuil}" ] && printf 'frais' || printf 'perime'
}

# Extrait la date (champ `date:`) de la DERNIÈRE entrée d'un runs-history.yaml
# passé sur stdin. Renvoie la valeur brute ISO, ou vide si aucune entrée.
# Pur : ne lit pas le filesystem (le fichier est caté par l'appelant).
metro_last_date() {
    # Tolère `date:` sur sa propre ligne (`    date: …`, format réel) comme en
    # tête de liste (`  - date: …`). On capture la valeur après `date:`.
    grep -oE 'date:[[:space:]]*[^[:space:]"'\'']+' | tail -1 \
        | sed -E 's/^date:[[:space:]]*//'
}

# Convertit une durée en secondes au format lisible "<m>m<ss>s".
# Usage : metro_fmt_dur <secondes>
metro_fmt_dur() {
    local s=$1
    printf '%dm%02ds' "$((s / 60))" "$((s % 60))"
}

# Extrait la valeur scalaire d'une réponse Prometheus `query` (API v1).
# Format : {"data":{"result":[[<ts>,"<valeur>"]]}} ou result vide.
# Renvoie la valeur (chaîne), ou vide si absente/illisible. PUR (stdin = JSON).
# Usage : echo "$json" | metro_parse_prom_scalar
metro_parse_prom_scalar() {
    # Le résultat scalaire/instantané est ["<ts>","<valeur>"] ; on prend la
    # 2ᵉ chaîne entre guillemets après le timestamp. grep/sed only (pas de jq).
    grep -oE '\[[0-9.]+,"[^"]*"\]' | head -1 | sed -E 's/.*,"([^"]*)"\].*/\1/'
}

# Arrondit un flottant Prometheus à l'entier le plus proche (ou "?" si NaN/vide).
# Usage : metro_round <valeur>
metro_round() {
    local v=$1
    case "${v}" in
        '' | NaN | null | +Inf | -Inf) printf '?' ;;
        *) printf '%.0f' "${v}" 2>/dev/null || printf '?' ;;
    esac
}

# Rend le bloc YAML `metriques:` (indenté pour une entrée de run) à partir des
# trois agrégats. PUR. Les "?" (métrique indisponible) sont émis tels quels.
# Usage : metro_metrics_block <cpu_core_s> <ram_peak_mib> <ram_mean_mib>
metro_metrics_block() {
    local cpu=$1 peak=$2 mean=$3
    printf '    metriques:\n'
    printf '      cpu_core_s: %s\n' "${cpu}"
    printf '      ram_peak_mib: %s\n' "${peak}"
    printf '      ram_mean_mib: %s\n' "${mean}"
}

# ── Effets de bord (montent/lisent des artefacts ; non testés bats) ───────────

# Chemin du fichier d'historique versionné (sous test/lima/, pas .work/).
# LIMA_DIR est défini par lib.sh (sourcé avant nous).
metro_history_file() { printf '%s/runs-history.yaml' "${LIMA_DIR:-.}"; }

# Initialise l'en-tête du fichier d'historique s'il n'existe pas (idempotent).
metro_history_init() {
    local f
    f=$(metro_history_file)
    [ -f "${f}" ] && return 0
    cat > "${f}" <<'HDR'
# Historique des runs du banc Lima — preuve datée (ADR 0034/0042).
#
# VERSIONNÉ : la date vit dans le contenu (le checkout CI ne préserve pas le
# mtime). Le garde-fou de fraîcheur (.github/workflows/bench-freshness.yml, ADR
# 0042) lit la date de la DERNIÈRE entrée et alerte au-delà du seuil (7 j).
#
# Une entrée est appendée par run `all` COMPLÉTÉ (test/lima/run-phases.sh). Les
# valeurs sont génériques (ADR 0023) : pas d'identifiant réel de déploiement.
#
# Schéma : id, date (ISO 8601 UTC), branche, commit, profil (ceph|local-path),
# topologie, arch, hote, total_s, phases{nom: secondes}, [metriques{…}].

runs:
HDR
    log "historique de runs initialisé : ${f}"
}

# Append une entrée de run à l'historique. Appelé en fin de run `all` réussi.
# Lit la date système UNE fois ici (effet de bord assumé, hors fonctions pures).
# Args : $1=profil  $2=topologie  $3=total_s  $4=fichier_durees_phase (tsv: nom\tsec)
# Optionnel via env : METRO_METRICS_BLOCK = bloc YAML "      metriques:\n …" déjà rendu.
metro_record_run() {
    local profil=$1 topo=$2 total=$3 phases_tsv=$4
    local f iso commit branche arch hote id
    f=$(metro_history_file)
    metro_history_init
    iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    commit=$(git -C "${REPO}" rev-parse --short HEAD 2>/dev/null || echo '?')
    branche=$(git -C "${REPO}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')
    arch=$(uname -m)
    hote=$(sysctl -n hw.model 2>/dev/null || uname -s)
    id=$(metro_run_id "${iso}" "${profil}" "${commit}")

    {
        printf '  - id: %s\n' "${id}"
        printf '    date: %s\n' "${iso}"
        printf '    branche: %s\n' "${branche}"
        printf '    commit: %s\n' "${commit}"
        printf '    profil: %s\n' "${profil}"
        printf '    topologie: %s\n' "${topo}"
        printf '    arch: %s\n' "${arch}"
        printf "    hote: '%s'\n" "${hote}"
        printf '    total_s: %s\n' "${total}"
        printf '    phases:\n'
        while IFS=$'\t' read -r name sec; do
            [ -n "${name}" ] || continue
            printf '      %s: %s\n' "${name}" "${sec}"
        done < "${phases_tsv}"
        # Bloc métriques Prometheus (#217), rendu par metro_sample_prometheus.
        # `printf '%s\n'` : la substitution $(...) qui a capturé METRO_METRICS_BLOCK
        # a STRIPPÉ le newline final → sans ce \n, le fichier finit sans newline
        # (yamllint: new-line-at-end-of-file). Le \n est sans effet si le bloc est
        # vide (cas banc sans Prometheus) car la garde -n l'exclut.
        [ -n "${METRO_METRICS_BLOCK:-}" ] && printf '%s\n' "${METRO_METRICS_BLOCK}"
    } >> "${f}"

    ok "run consigné dans $(basename "${f}") : ${id} (${profil}, $(metro_fmt_dur "${total}"))"
}

# Interroge Prometheus (s'il est déployé) pour les métriques de coût du run sur
# la fenêtre [début, maintenant] et renvoie sur stdout le bloc YAML `metriques:`
# (ou rien si Prometheus est absent — banc rapide sans monitoring).
#
# Requêtes (sur la fenêtre <window>s, tous nœuds) :
#   - cpu_core_s   : Σ increase(node_cpu_seconds_total{mode!="idle"}[window])
#                    = cœur·secondes consommés (cumul CPU×temps).
#   - ram_peak_mib : max_over_time du RAM utilisé (total - available) sur window.
#   - ram_mean_mib : avg_over_time du même, même fenêtre.
#
# L'API est jointe depuis un pod busybox ÉPHÉMÈRE ciblant le Service Prometheus
# (`prometheus-operated:9090`) — PAS via `kubectl exec` dans le pod Prometheus :
# son image est DISTROLESS (ni wget ni sh, même piège que le drift #14 etcd). On
# réutilise le pattern busybox de marquez_job_count (run-phases.sh). Best-effort :
# toute erreur → "?" (non bloquant, #217). Args : $1 = fenêtre en secondes.
metro_sample_prometheus() {
    local window=$1 q cpu peak mean svc
    # IMPORTANT : cette fonction écrit le BLOC YAML sur stdout (capturé par
    # l'appelant). Tout message humain (log/warn) DOIT donc partir sur stderr
    # (>&2), sinon il pollue le YAML — bug observé : lignes ANSI dans le fichier.
    # Service stable exposé par kube-prometheus-stack (cluster IP des pods Prom).
    svc=$("${KUBECTL[@]}" -n monitoring get svc prometheus-operated -o name 2>/dev/null)
    [ -n "${svc}" ] || { warn "Prometheus absent — métriques de run non échantillonnées (#217)" >&2; return 0; }

    # Helper local : requête instantanée via busybox éphémère → scalaire.
    _prom() {
        local query=$1 enc
        enc=$(printf '%s' "${query}" | sed 's/ /%20/g; s/"/%22/g; s/{/%7B/g; s/}/%7D/g; s/!/%21/g; s/=/%3D/g; s/\[/%5B/g; s/\]/%5D/g; s/(/%28/g; s/)/%29/g; s/,/%2C/g; s/+/%2B/g; s#/#%2F#g; s/:/%3A/g')
        "${KUBECTL[@]}" -n monitoring run prom-q-$$-"${RANDOM}" --rm -i --restart=Never \
            --image=busybox:1.36 --quiet -- \
            wget -qO- "http://prometheus-operated.monitoring.svc.cluster.local:9090/api/v1/query?query=${enc}" 2>/dev/null \
            | metro_parse_prom_scalar
    }

    q="sum(increase(node_cpu_seconds_total{mode!=\"idle\"}[${window}s]))"
    cpu=$(metro_round "$(_prom "${q}")")
    q="max_over_time((sum(node_memory_MemTotal_bytes-node_memory_MemAvailable_bytes)/1048576)[${window}s:30s])"
    peak=$(metro_round "$(_prom "${q}")")
    q="avg_over_time((sum(node_memory_MemTotal_bytes-node_memory_MemAvailable_bytes)/1048576)[${window}s:30s])"
    mean=$(metro_round "$(_prom "${q}")")

    log "  métriques run : CPU=${cpu} cœur·s · RAM pic=${peak} MiB · RAM moy=${mean} MiB" >&2
    metro_metrics_block "${cpu}" "${peak}" "${mean}"
}

# ── Cache du socle bootstrap (#219) ──────────────────────────────────────────
# Le socle (k8s + Cilium + storage + [Ceph]) est coûteux (~6-15 min) et change
# rarement. On le met en cache pour le RÉUTILISER tant que son CONTENU est
# inchangé. La clé = phase+profil+hash(contenu) : tout changement des inputs
# invalide le cache (sinon il masquerait une régression — interdit ADR 0034).
#
# Mécanisme volontairement CONSERVATEUR : on ne « restaure » pas un snapshot VM
# (fragile) ; on SAUTE le rebuild uniquement si (1) les VMs tournent, (2) le
# cluster est joignable, (3) la clé enregistrée == clé courante. Sinon → rebuild
# complet. Le cache est un ACCÉLÉRATEUR D'ITÉRATION ; la PREUVE reste un run
# from-scratch (NO_CACHE=1 force le rebuild, ADR 0034).

# Fichier marqueur de cache (éphémère, .work/) : contient la dernière clé bâtie.
metro_cache_file() { printf '%s/socle-cache.key' "${WORKDIR:-.work}"; }

# Calcule la clé de cache du socle : phase 'socle' + profil + hash du contenu
# des inputs qui DÉFINISSENT le socle. PUR au sens « déterministe pour un état
# de dépôt donné » (lit des fichiers versionnés via git, pas l'horloge).
# Inputs hachés : rôles bootstrap, cni.sh, manifestes Ceph, template VM, versions
# épinglées (ADR 0006). Args : $1 = profil (ceph|local-path).
metro_socle_key() {
    local profil=$1 h
    # git ls-files + hash-object : robuste au renommage, ignore les fichiers non
    # suivis. On restreint aux chemins qui composent le socle.
    h=$(git -C "${REPO}" ls-files -z -- \
            'bootstrap/roles/k8s-*' \
            'bootstrap/cni.sh' \
            'bootstrap/checks.yaml' 'bootstrap/cri.yaml' \
            'bootstrap/kubeadm.yaml' 'bootstrap/initialisation.yaml' \
            'bootstrap/join-workers.yaml' \
            'storage/ceph/operator.yaml' 'storage/ceph/cluster.yaml' \
            'storage/ceph/common.yaml' 'storage/ceph/crds.yaml' \
            'test/lima/profiles/node.yaml.tmpl' \
            'docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md' \
            2>/dev/null \
        | xargs -0 git -C "${REPO}" hash-object 2>/dev/null \
        | git hash-object --stdin 2>/dev/null | cut -c1-12)
    printf 'socle:%s:%s' "${profil}" "${h:-nohash}"
}

# Le socle en cache est-il RÉUTILISABLE ? Vrai si VMs up + cluster Ready + clé
# courante == clé enregistrée. NO_CACHE=1 désactive (force rebuild — preuve).
# Args : $1 = profil. Effet : lecture seule.
metro_cache_valid() {
    local profil=$1 want have entry vm
    [ "${NO_CACHE:-0}" = 1 ] && return 1
    [ -f "$(metro_cache_file)" ] || return 1
    want=$(metro_socle_key "${profil}")
    have=$(cat "$(metro_cache_file)" 2>/dev/null)
    [ "${want}" = "${have}" ] || return 1
    # Les VMs doivent réellement tourner (sinon rien à réutiliser).
    for entry in "${NODES[@]}"; do
        vm="${entry%%:*}"
        vm_running "${vm}" || return 1
    done
    # Le cluster doit répondre (kubeconfig + nœuds Ready).
    [ -f "${KUBECONFIG_LOCAL}" ] || return 1
    nodes_ready_all || return 1
    return 0
}

# Enregistre la clé du socle courant comme « bâti » (après un build réussi).
# Args : $1 = profil.
metro_cache_save() {
    local profil=$1
    mkdir -p "${WORKDIR}"
    metro_socle_key "${profil}" > "$(metro_cache_file)"
    log "  socle mis en cache (clé $(cat "$(metro_cache_file)")) — réutilisable tant que le contenu ne change pas"
}
