#!/usr/bin/env bash
#
# Primitives du ROLLBACK PAR PHASE du banc (ADR 0054, issue #274). Défait UNE
# phase montée par run-phases.sh : efface namespaces + CRD + PVC + état node-side,
# force les finalizers récalcitrants (banc JETABLE → destructif total, pas de
# ménagement des données). Sourcé par test/lima/run-phases.sh (dispatch
# `rollback <phase>`). Distinct du rollback transactionnel #236 (rescue auto).
#
# Deux familles ici :
#  - FONCTIONS PURES (table de périmètre, ordre des dépendances, verdict d'état
#    propre) : NI kubectl NI ssh, prennent des valeurs déjà collectées, renvoient
#    un verdict `STATUS|message` ou une valeur. Testées par test/unit/rollback.bats
#    (comme state-classify.sh / bootstrap-fault-assert.sh).
#  - PRIMITIVES kubectl/ssh (k8s_force_delete_ns…) : font le réseau, NON pures.
#    Elles attendent les fonctions log/ok/die/vm_sh/KUBECTL de lib.sh/run-phases.sh.
#
# Convention verdict : une ligne "STATUS|message" (STATUS ∈ {ok, fail, skip}),
# découpée sur le premier '|'.

# ─── PARTIE PURE (testable bats, aucun réseau) ──────────────────────────────

# rollback_phase_namespaces PHASE
#   Namespaces qu'un rollback de PHASE doit effacer (séparés par des espaces),
#   ou vide si la phase n'a pas de namespace dédié. Table de périmètre (ADR 0054
#   §3), valeurs génériques banc (ADR 0023).
rollback_phase_namespaces() {
    case "${1:-}" in
        # SEUL `ceph` possède le ns rook-ceph → lui seul le supprime. `sc` et
        # `datalake` PARTAGENT rook-ceph (Ceph y vit) : ils ne doivent PAS le
        # supprimer (ça tuerait Ceph) — ils effacent des ressources CIBLÉES
        # (cf. rollback_phase_targeted_resources).
        ceph)            printf 'rook-ceph\n' ;;
        monitoring)      printf 'monitoring\n' ;;
        dataops)         printf 'postgres dagster marquez\n' ;;
        gitops)          printf 'argocd gitea\n' ;;
        *)               printf '\n' ;;  # sc, datalake, metrics-server, gitops-seed : pas de ns à supprimer
    esac
}

# rollback_phase_targeted_resources PHASE
#   Ressources CIBLÉES à supprimer (kind/name ou kind par ns), pour les phases
#   qui n'ont PAS de ns propre mais des ressources précises (partage rook-ceph,
#   deploy dans kube-system…). Une ressource par ligne, forme « -n NS KIND NAME »
#   ou « KIND NAME » (cluster-scoped). Vide sinon.
rollback_phase_targeted_resources() {
    case "${1:-}" in
        datalake)
            # CephObjectStore + sa SC bucket (rook-ceph), SANS toucher le ns.
            printf -- '-n rook-ceph cephobjectstore.ceph.rook.io datalake\n'
            printf 'storageclass.storage.k8s.io rook-ceph-datalake\n' ;;
        sc)
            # StorageClasses bloc/fs + leurs CephBlockPool/CephFilesystem.
            printf 'storageclass.storage.k8s.io rook-ceph-block-replicated\n'
            printf 'storageclass.storage.k8s.io rook-ceph-block-ec-delete\n'
            printf 'storageclass.storage.k8s.io rook-ceph-block-ec\n'
            printf 'storageclass.storage.k8s.io rook-cephfs\n' ;;
        metrics-server)
            printf -- '-n kube-system deployment.apps metrics-server\n' ;;
        monitoring)
            # OBC du backing S3 de Loki, posée par platform-loki DANS rook-ceph
            # (ns ≠ monitoring). Sans elle, le CephObjectStore datalake reste bloqué
            # en Deleting (finalizer : un bucket dépendant subsiste). #319-suite.
            printf -- '-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets\n' ;;
        dataops)
            # OBC du backing S3 de CNPG/Barman, posée par platform-cnpg DANS
            # rook-ceph (ns ≠ postgres). Même raison que monitoring : libère le
            # datalake. (Sans incidence en profil léger : pas d'OBC → no-op delete.)
            printf -- '-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups\n' ;;
        gitops-seed)
            # Données dans Gitea (org/repo) + Application Argo CD seed — best-effort.
            printf -- '-n argocd applications.argoproj.io atlas\n' ;;
        *) printf '\n' ;;
    esac
}

# rollback_phase_crd_groups PHASE
#   Groupes API dont les CRD doivent être supprimés (séparés par des espaces).
#   Supprimer un groupe CRD GC les CR restants. Vide si la phase n'installe pas
#   de CRD propres.
rollback_phase_crd_groups() {
    case "${1:-}" in
        # SEUL `ceph` supprime les CRD ceph.rook.io (partagés par sc/datalake) :
        # les retirer depuis sc/datalake casserait Ceph. sc/datalake passent par
        # rollback_phase_targeted_resources (CR ciblés, pas les CRD).
        ceph)                 printf 'ceph.rook.io\n' ;;
        monitoring)           printf 'monitoring.coreos.com\n' ;;
        dataops)              printf 'postgresql.cnpg.io\n' ;;
        gitops)               printf 'argoproj.io\n' ;;
        *)                    printf '\n' ;;
    esac
}

# rollback_phase_has_nodeside PHASE
#   "yes" si la phase laisse un état NODE-SIDE que le delete Kubernetes ne couvre
#   pas (disques Ceph + /var/lib/rook). Seul `ceph` en a.
rollback_phase_has_nodeside() {
    case "${1:-}" in
        ceph) printf 'yes\n' ;;
        *)    printf 'no\n' ;;
    esac
}

# rollback_phase_downstream PHASE
#   Phases AVAL qui dépendent de PHASE (séparées par des espaces) : on ne défait
#   pas une phase socle tant qu'une de ses phases aval est encore montée
#   (ordre inverse, ADR 0054 §4). Vide si aucune.
rollback_phase_downstream() {
    case "${1:-}" in
        ceph)     printf 'sc datalake wordpress\n' ;;
        gitops)   printf 'gitops-seed\n' ;;
        *)        printf '\n' ;;
    esac
}

# rollback_known_phase PHASE
#   0 (vrai) si PHASE est une phase connue qui a un rollback défini. Sert au
#   dispatch à rejeter un nom inconnu.
rollback_known_phase() {
    case "${1:-}" in
        ceph | sc | datalake | metrics-server | monitoring | dataops | gitops | gitops-seed)
            return 0 ;;
        *) return 1 ;;
    esac
}

# classify_clean_state RESIDUAL
#   Verdict d'état propre après un rollback (ADR 0054 preuve). RESIDUAL = liste
#   (séparée par des espaces) des traces ENCORE présentes (ns/CRD/PVC/disque
#   sale) collectées par l'appelant ; vide = aucune trace.
#   - RESIDUAL vide → ok (rollback complet : zéro trace)
#   - sinon         → fail (liste les résidus → table de périmètre à compléter)
classify_clean_state() {
    local residual=${1:-}
    residual=${residual#"${residual%%[![:space:]]*}"}
    residual=${residual%"${residual##*[![:space:]]}"}
    if [ -z "$residual" ]; then
        printf 'ok|Rollback complet : aucune trace résiduelle\n'
    else
        printf 'fail|Traces résiduelles après rollback : %s (compléter la table de périmètre, ADR 0054 §3)\n' "$residual"
    fi
}

# classify_downstream_block PHASE PRESENT_DOWNSTREAM
#   Verdict du garde-fou d'ordre (ADR 0054 §4). PRESENT_DOWNSTREAM = liste des
#   phases aval ENCORE présentes (collectée par l'appelant).
#   - vide → ok (aucune phase aval → on peut défaire PHASE)
#   - sinon → fail (défaire PHASE laisserait les phases aval orphelines)
classify_downstream_block() {
    local phase=${1:-} present=${2:-}
    present=${present#"${present%%[![:space:]]*}"}
    present=${present%"${present##*[![:space:]]}"}
    if [ -z "$present" ]; then
        printf 'ok|Aucune phase aval présente — %s peut être défaite\n' "$phase"
    else
        printf 'fail|Phases AVAL encore montées (%s) : défaire %s d'\''abord (ordre inverse, ADR 0054 §4)\n' "$present" "$phase"
    fi
}

# ─── PRIMITIVES kubectl/ssh (NON pures — réseau) ────────────────────────────
# Attendent KUBECTL/vm_sh/log/ok/die/retry de run-phases.sh/lib.sh (sourcées).

# Kinds de CR connus pour bloquer une terminaison de ns par leurs finalizers
# (banc jetable : on les force). Inclut le `Cluster` CNPG ET son `ObjectStore`
# Barman (plugin barman-cloud) — ce dernier coinçait `postgres` en Terminating.
_STUCK_CR_KINDS="obc.objectbucket.io objectbucket.io cephcluster.ceph.rook.io \
cephobjectstore.ceph.rook.io cephblockpool.ceph.rook.io cephfilesystem.ceph.rook.io \
cluster.postgresql.cnpg.io objectstore.barmancloud.cnpg.io"

# k8s_force_delete_ns NS…
#   Supprime chaque namespace, en FORÇANT les finalizers récalcitrants (banc
#   jetable : on ne ménage pas les deadlocks, ADR 0054 §2). delete non bloquant ;
#   si le ns reste en Terminating, force les finalizers des CR coincés PUIS finalise
#   le ns via le sous-ressource /finalize (le patch du ns ne suffit pas pour un
#   ns déjà Terminating). CONTINUE sur les ns suivants même si l'un échoue (un échec
#   isolé ne doit pas abandonner le reste de la clôture) ; échoue à la fin si résidus.
k8s_force_delete_ns() {
    local ns failed=""
    for ns in "$@"; do
        "${KUBECTL[@]}" get ns "${ns}" > /dev/null 2>&1 || continue
        log "  rollback : suppression du namespace ${ns} (force finalizers si bloqué)"
        "${KUBECTL[@]}" delete ns "${ns}" --wait=false --ignore-not-found > /dev/null 2>&1 || true
        if retry 10 2 _ns_absent "${ns}"; then continue; fi
        # Forcer les finalizers des CR coincés (OBC, CR Rook/CNPG/Barman).
        local kind
        for kind in ${_STUCK_CR_KINDS}; do
            "${KUBECTL[@]}" -n "${ns}" get "${kind}" -o name 2> /dev/null \
                | while read -r res; do
                    "${KUBECTL[@]}" -n "${ns}" patch "${res}" --type merge \
                        -p '{"metadata":{"finalizers":[]}}' > /dev/null 2>&1 || true
                done
        done
        # Finaliser le ns : retirer spec.finalizers via /finalize (fix canonique
        # d'un ns coincé en Terminating ; un patch simple est ignoré à ce stade).
        _ns_force_finalize "${ns}"
        retry 30 2 _ns_absent "${ns}" || failed="${failed} ${ns}"
    done
    [ -z "${failed}" ] || die "rollback : namespace(s) non supprimé(s) :${failed} (finalizers résiduels ?)"
}
_ns_absent() { ! "${KUBECTL[@]}" get ns "$1" > /dev/null 2>&1; }

# _ns_force_finalize NS — retire spec.finalizers du ns via le sous-ressource
# /finalize (la seule voie pour débloquer un ns déjà en Terminating). Best-effort.
_ns_force_finalize() {
    local ns=$1 tmp
    tmp=$("${KUBECTL[@]}" get ns "${ns}" -o json 2> /dev/null | jq 'del(.spec.finalizers)' 2> /dev/null) || return 0
    [ -n "${tmp}" ] || return 0
    printf '%s' "${tmp}" \
        | "${KUBECTL[@]}" replace --raw "/api/v1/namespaces/${ns}/finalize" -f - > /dev/null 2>&1 || true
}

# k8s_delete_targeted "LIGNES"
#   Supprime des ressources ciblées (une par ligne, forme « -n NS KIND NAME » ou
#   « KIND NAME » cluster-scoped). --ignore-not-found, force finalizers si bloqué.
k8s_delete_targeted() {
    local line
    while IFS= read -r line; do
        [ -n "${line}" ] || continue
        log "  rollback : suppression ${line}"
        # shellcheck disable=SC2086 # découpage voulu des champs de la ligne
        "${KUBECTL[@]}" delete ${line} --ignore-not-found --wait=false > /dev/null 2>&1 || true
        # Forcer les finalizers si la ressource traîne (CR Rook/OBC).
        # shellcheck disable=SC2086
        "${KUBECTL[@]}" patch ${line} --type merge \
            -p '{"metadata":{"finalizers":[]}}' > /dev/null 2>&1 || true
    done <<EOF
${1}
EOF
}

# k8s_delete_crd GROUP…
#   Supprime les CRD d'un groupe API (ex. ceph.rook.io) — ce qui GC les CR
#   restants. À jouer APRÈS les namespaces (les CR vivent dans des ns).
k8s_delete_crd() {
    local group crd
    for group in "$@"; do
        "${KUBECTL[@]}" get crd -o name 2> /dev/null \
            | grep -E "\.${group}$" | while read -r crd; do
                log "  rollback : suppression CRD ${crd#customresourcedefinition.apiextensions.k8s.io/}"
                "${KUBECTL[@]}" delete "${crd}" --ignore-not-found --wait=false > /dev/null 2>&1 || true
            done
    done
}

# phase_rollback PHASE
#   Défait une phase montée (ADR 0054). Garde BANC_JETABLE=1 + cible banc. Ordre
#   inverse : refuse si une phase aval est encore présente. Efface ns + CRD +
#   node-side (Ceph). DESTRUCTIF TOTAL (données comprises).
phase_rollback() {
    local phase=$1
    [ "${BANC_JETABLE:-0}" = 1 ] || die "rollback DESTRUCTIF (efface données) — exiger BANC_JETABLE=1 sur un banc jetable"
    rollback_known_phase "${phase}" || die "rollback : phase inconnue '${phase}' (ceph|sc|datalake|metrics-server|monitoring|dataops|gitops|gitops-seed)"
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — banc non monté ?"

    # Garde-fou d'ordre : aucune phase AVAL encore présente.
    local downstream present="" d verdict
    downstream=$(rollback_phase_downstream "${phase}")
    for d in ${downstream}; do
        _phase_present "${d}" && present="${present} ${d}"
    done
    verdict=$(classify_downstream_block "${phase}" "${present# }")
    case "${verdict%%|*}" in
        ok) : ;;
        *) die "${verdict#*|}" ;;
    esac

    log "Rollback de la phase '${phase}' (BANC_JETABLE — destructif total)"
    # 1. Ressources CIBLÉES (phases sans ns propre : datalake/sc/metrics/seed).
    local targeted; targeted=$(rollback_phase_targeted_resources "${phase}")
    [ -n "${targeted}" ] && k8s_delete_targeted "${targeted}"
    # 2. Namespaces (force finalizers) — phases qui possèdent leur ns.
    local ns_list; ns_list=$(rollback_phase_namespaces "${phase}")
    # shellcheck disable=SC2086
    [ -n "${ns_list}" ] && k8s_force_delete_ns ${ns_list}
    # 3. CRD du groupe (GC les CR) — seul ceph.
    local crd_groups; crd_groups=$(rollback_phase_crd_groups "${phase}")
    # shellcheck disable=SC2086
    [ -n "${crd_groups}" ] && k8s_delete_crd ${crd_groups}
    # 3. Node-side (disques Ceph + /var/lib/rook) — seul `ceph` en a.
    if [ "$(rollback_phase_has_nodeside "${phase}")" = yes ]; then
        local entry vm
        for entry in "${NODES[@]}"; do
            vm="${entry%%:*}"
            log "  rollback : wipe node-side sur ${vm} (cleanup.sh, disques + /var/lib/rook)"
            NVME_BLOCK_DEVICE=/dev/vde DATA_DEVICE_GLOB='/dev/vd[b-d]' SKIP_REBOOT=1 \
                vm_sh "${vm}" sudo env NVME_BLOCK_DEVICE=/dev/vde DATA_DEVICE_GLOB='/dev/vd[b-d]' SKIP_REBOOT=1 \
                bash -s < "${REPO}/storage/ceph/cleanup.sh" || warn "${vm} : cleanup.sh node-side a renvoyé une erreur (résidu ?)"
        done
    fi
    ok "Rollback '${phase}' terminé — re-monter avec : test/lima/run-phases.sh ${phase}"
}

# _phase_present PHASE — prédicat best-effort : la phase aval est-elle montée ?
# Réutilise les prédicats de présence de phase_status (ceph_present, etc.).
_phase_present() {
    case "$1" in
        sc) sc_default_present ;;
        datalake) "${KUBECTL[@]}" -n rook-ceph get cephobjectstore datalake > /dev/null 2>&1 ;;
        wordpress) "${KUBECTL[@]}" get pvc -A 2> /dev/null | grep -q wordpress ;;
        gitops-seed) "${KUBECTL[@]}" -n argocd get applications.argoproj.io -o name 2> /dev/null | grep -q . ;;
        *) return 1 ;;
    esac
}
