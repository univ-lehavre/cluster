#!/usr/bin/env bats
#
# Tests des fonctions PURES du rollback par phase (#274, ADR 0054). Aucun banc :
# on source la lib et on vérifie la table de périmètre + les verdicts sur des
# fixtures fixes (patron state-classify.bats / bootstrap-fault.bats).

setup() {
    # shellcheck source=../../test/lima/rollback-lib.sh
    source "${BATS_TEST_DIRNAME}/../../test/lima/rollback-lib.sh"
}

# ─── rollback_phase_namespaces ──────────────────────────────────────────────

@test "namespaces : ceph → rook-ceph" {
    run rollback_phase_namespaces ceph
    [ "$output" = "rook-ceph" ]
}

@test "namespaces : dataops → postgres dagster marquez" {
    run rollback_phase_namespaces dataops
    [ "$output" = "postgres dagster marquez" ]
}

@test "namespaces : gitops → argocd gitea" {
    run rollback_phase_namespaces gitops
    [ "$output" = "argocd gitea" ]
}

@test "namespaces : sc → vide (pas de ns dédié)" {
    run rollback_phase_namespaces sc
    [ -z "$output" ]
}

@test "namespaces : datalake → vide (PARTAGE rook-ceph, ne le supprime PAS)" {
    run rollback_phase_namespaces datalake
    [ -z "$output" ]
}

# ─── rollback_phase_targeted_resources (phases sans ns propre) ──────────────

@test "targeted : datalake → CephObjectStore + SC bucket (pas le ns rook-ceph)" {
    run rollback_phase_targeted_resources datalake
    [[ "$output" == *"cephobjectstore.ceph.rook.io datalake"* ]]
    [[ "$output" == *"rook-ceph-datalake"* ]]
    [[ "$output" != *"namespace"* ]]
}

@test "targeted : sc → StorageClasses bloc/fs ciblées" {
    run rollback_phase_targeted_resources sc
    [[ "$output" == *"rook-ceph-block-replicated"* ]]
}

@test "targeted : metrics-server → deploy kube-system" {
    run rollback_phase_targeted_resources metrics-server
    [[ "$output" == *"-n kube-system deployment.apps metrics-server"* ]]
}

@test "targeted : ceph → vide (ceph passe par ns + CRD, pas ciblé)" {
    run rollback_phase_targeted_resources ceph
    [ -z "$output" ]
}

@test "targeted : monitoring → OBC loki-buckets dans rook-ceph (libère datalake)" {
    # L'OBC du backing S3 de Loki vit dans rook-ceph (ns ≠ monitoring) : sans elle,
    # le CephObjectStore datalake reste bloqué en Deleting. #319-suite.
    run rollback_phase_targeted_resources monitoring
    [[ "$output" == *"-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets"* ]]
}

@test "targeted : dataops → OBC cnpg-backups dans rook-ceph (libère datalake)" {
    run rollback_phase_targeted_resources dataops
    [[ "$output" == *"-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups"* ]]
}

# ─── rollback_phase_crd_groups ──────────────────────────────────────────────

@test "crd : ceph → ceph.rook.io" {
    run rollback_phase_crd_groups ceph
    [ "$output" = "ceph.rook.io" ]
}

@test "crd : dataops → postgresql.cnpg.io" {
    run rollback_phase_crd_groups dataops
    [ "$output" = "postgresql.cnpg.io" ]
}

@test "crd : metrics-server → vide" {
    run rollback_phase_crd_groups metrics-server
    [ -z "$output" ]
}

@test "crd : sc/datalake → vide (ne PAS supprimer les CRD ceph.rook.io partagés)" {
    run rollback_phase_crd_groups sc
    [ -z "$output" ]
    run rollback_phase_crd_groups datalake
    [ -z "$output" ]
}

# ─── rollback_phase_has_nodeside ────────────────────────────────────────────

@test "nodeside : ceph → yes (disques + /var/lib/rook)" {
    run rollback_phase_has_nodeside ceph
    [ "$output" = "yes" ]
}

@test "nodeside : monitoring → no" {
    run rollback_phase_has_nodeside monitoring
    [ "$output" = "no" ]
}

# ─── rollback_phase_downstream ──────────────────────────────────────────────

@test "downstream : ceph → sc datalake wordpress" {
    run rollback_phase_downstream ceph
    [ "$output" = "sc datalake wordpress" ]
}

@test "downstream : gitops → gitops-seed" {
    run rollback_phase_downstream gitops
    [ "$output" = "gitops-seed" ]
}

@test "downstream : monitoring → vide" {
    run rollback_phase_downstream monitoring
    [ -z "$output" ]
}

# ─── rollback_known_phase ───────────────────────────────────────────────────

@test "known : ceph → 0 (connue)" {
    run rollback_known_phase ceph
    [ "$status" -eq 0 ]
}

@test "known : up → 1 (pas de rollback de phase défini)" {
    run rollback_known_phase up
    [ "$status" -ne 0 ]
}

@test "known : nom inconnu → 1" {
    run rollback_known_phase n-importe-quoi
    [ "$status" -ne 0 ]
}

# ─── classify_clean_state ───────────────────────────────────────────────────

@test "clean_state : aucun résidu → ok" {
    run classify_clean_state ""
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "clean_state : espaces seuls → ok (normalisation)" {
    run classify_clean_state "   "
    [[ "$output" == ok\|* ]]
}

@test "clean_state : résidus → fail (les liste)" {
    run classify_clean_state "ns/rook-ceph crd/ceph.rook.io"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"rook-ceph"* ]]
}

# ─── classify_downstream_block ──────────────────────────────────────────────

@test "downstream_block : aucune aval → ok" {
    run classify_downstream_block ceph ""
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "downstream_block : aval présente → fail (refuse l'ordre)" {
    run classify_downstream_block ceph "sc datalake"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"sc datalake"* ]]
    [[ "$output" == *"ordre inverse"* ]]
}

# ─── classify_hardening_signal (ADR 0065 §2 : durcissement = état détecté) ───

@test "hardening : auditd+fail2ban actifs → ok hardened (+hardening)" {
    run classify_hardening_signal active active
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"hardened"* ]]
}

@test "hardening : auditd+fail2ban inactifs → ok plain (pas de suffixe)" {
    run classify_hardening_signal inactive inactive
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"plain"* ]]
}

@test "hardening : un signal unknown → skip (injoignable → l'appelant die)" {
    run classify_hardening_signal active unknown
    [[ "$output" == skip\|* ]]
    run classify_hardening_signal unknown inactive
    [[ "$output" == skip\|* ]]
}

@test "hardening : état PARTIEL (un seul actif) → fail (couche incohérente)" {
    run classify_hardening_signal active inactive
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"PARTIEL"* ]]
    run classify_hardening_signal inactive active
    [[ "$output" == fail\|* ]]
}

@test "hardening : défauts absents → skip (rien collecté = unknown)" {
    run classify_hardening_signal
    [[ "$output" == skip\|* ]]
}

# ═══ GRAPHE ATOMIQUE (ADR 0066, Lot 0) — invariants prouvés sans banc ════════
# Périmètres vérifiés contre le code (workflow consigné 2026-06-13). Ces tests
# sont la garantie que les oublis du modèle par phase (cnpg-system…) deviennent
# STRUCTURELLEMENT impossibles.

# ─── component_namespace : possesseurs distincts ────────────────────────────

@test "atom/ns : cnpg-operator possède cnpg-system (≠ postgres — l'oubli historique)" {
    run component_namespace cnpg-operator
    [ "$output" = "cnpg-system" ]
}

@test "atom/ns : cnpg-cluster-pg possède postgres (POSSESSEUR unique)" {
    run component_namespace cnpg-cluster-pg
    [ "$output" = "postgres" ]
}

@test "atom/ns : prometheus-stack possède monitoring ; loki est LOCATAIRE (∅)" {
    run component_namespace prometheus-stack
    [ "$output" = "monitoring" ]
    run component_namespace loki
    [ -z "$output" ]
}

@test "atom/ns : barman-plugin LOCATAIRE de cnpg-system (∅, pas possesseur)" {
    run component_namespace barman-plugin
    [ -z "$output" ]
}

# ─── INVARIANT 1 : trivialité (≤1 ns) + unicité du possesseur ───────────────

@test "atom/invariant trivialité : chaque composant possède AU PLUS un ns" {
    local c ns count
    for c in $(component_all); do
        ns=$(component_namespace "$c")
        # Compter les mots (0 ou 1) sans déclencher set -e si vide.
        count=$(printf '%s' "$ns" | wc -w | tr -d ' ')
        [ "$count" -le 1 ] || { echo "composant $c possède plusieurs ns: $ns"; false; }
    done
}

@test "atom/invariant unicité : aucun namespace réclamé par DEUX composants" {
    # Le test qui aurait attrapé l'oubli cnpg-system : cnpg-system ET postgres
    # sont deux ns DISTINCTS, chacun avec un SEUL possesseur. Un doublon = un
    # périmètre composite qui réénumère mal (ADR 0066 §Contexte).
    local c ns dups
    dups=$(for c in $(component_all); do
        ns=$(component_namespace "$c")
        [ -n "$ns" ] && echo "$ns"
    done | sort | uniq -d)
    [ -z "$dups" ] || { echo "ns réclamés par >1 composant: $dups"; false; }
}

@test "atom/invariant complétude : dataops contient bien cnpg-system ET postgres" {
    # L'union de l'alias dataops doit posséder les DEUX ns CNPG (l'oubli prouvé
    # par un run). Via les composants de l'alias + leurs ns possédés.
    local owned
    owned=$(for c in $(component_expand_alias dataops); do component_namespace "$c"; done | tr '\n' ' ')
    [[ "$owned" == *"cnpg-system"* ]]
    [[ "$owned" == *"postgres"* ]]
    [[ "$owned" == *"dagster"* ]]
    [[ "$owned" == *"marquez"* ]]
}

# ─── INVARIANT 2 : complétude par ownership (OBC hors-ns → producteur) ───────

@test "atom/ownership : OBC cnpg-backups est un targeted de s3-backing-cnpg (pas de ceph)" {
    run component_targeted s3-backing-cnpg
    [[ "$output" == *"-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups"* ]]
    # ceph (possesseur de rook-ceph) ne doit PAS porter l'OBC d'autrui.
    run component_targeted ceph
    [[ "$output" != *"cnpg-backups"* ]]
}

@test "atom/ownership : OBC loki-buckets est un targeted de s3-backing-loki" {
    run component_targeted s3-backing-loki
    [[ "$output" == *"-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets"* ]]
}

# ─── INVARIANT 3 : déterminisme du tri ──────────────────────────────────────

@test "atom/déterminisme : topo_sort de la même liste donne deux fois la même sortie" {
    local a b
    a=$(topo_sort $(component_expand_alias atlas-ceph))
    b=$(topo_sort $(component_expand_alias atlas-ceph))
    [ "$a" = "$b" ]
}

# ─── ACYCLICITÉ : le graphe se trie ; un cycle injecté échoue ────────────────

@test "atom/acyclicité : topo_sort sur TOUS les composants réussit (pas de cycle)" {
    run topo_sort $(component_all)
    [ "$status" -eq 0 ]
    # 24 composants (catalogue complet : + storage-simple, ADR 0069), tous émis.
    [ "$(printf '%s\n' "$output" | grep -c .)" -eq 24 ]
}

@test "atom/acyclicité : un cycle injecté est DÉTECTÉ (échec, code ≠0)" {
    # Redéfinir component_deps avec une arête-cycle factice a→b, b→a.
    component_deps() { case "$1" in a) printf 'b\n' ;; b) printf 'a\n' ;; *) printf '\n' ;; esac; }
    component_all() { printf '%s\n' a b; }
    component_alias_weight() { printf '0\n'; }
    run topo_sort a b
    [ "$status" -ne 0 ]
    [[ "$output" == *"cycle"* ]]
}

# ─── INVARIANT 5 : topo_sort REPRODUIT l'ordre codé (pré-condition Lot 4) ────

@test "atom/repro ordre : montage atlas-ceph respecte chaque dépendance" {
    # Chaque composant sort APRÈS toutes ses dépendances directes.
    local order; order=$(topo_sort $(component_expand_alias atlas-ceph))
    local c d pos_c pos_d
    while IFS= read -r c; do
        pos_c=$(printf '%s\n' "$order" | grep -nx "$c" | cut -d: -f1)
        for d in $(component_deps "$c"); do
            pos_d=$(printf '%s\n' "$order" | grep -nx "$d" | cut -d: -f1)
            [ -n "$pos_d" ] || continue  # dep hors clôture
            [ "$pos_d" -lt "$pos_c" ] || { echo "$c (pos $pos_c) avant sa dep $d (pos $pos_d)"; false; }
        done
    done <<< "$order"
}

@test "atom/repro ordre : projeté sur les alias == ordre codé atlas-ceph" {
    # socle ceph sc datalake monitoring gitops dataops gitops-seed (ordre CODÉ).
    local proj="" c w a seen=""
    for c in $(topo_sort $(component_expand_alias atlas-ceph)); do
        w=$(component_alias_weight "$c")
        case "$w" in
            0) a=socle ;; 1) a=ceph ;; 2) a=sc ;; 3) a=datalake ;;
            4) a=monitoring ;; 5) a=gitops ;; 6) a=dataops ;; 7) a=gitops-seed ;;
            *) a=autre ;;
        esac
        case " $seen " in *" $a "*) : ;; *) proj="${proj} ${a}"; seen="${seen} ${a}" ;; esac
    done
    [ "${proj# }" = "socle ceph sc datalake monitoring gitops dataops gitops-seed" ]
}

# ─── INVARIANT 6 : garde-fou anti-GC des CRD PARTAGÉES ──────────────────────

@test "atom/CRD partagée : gateway.networking.k8s.io n'est listée QUE chez gateway-api" {
    run component_crd_groups gateway-api
    [[ "$output" == *"gateway.networking.k8s.io"* ]]
    # Les EMPRUNTEURS (registry/gitea/argocd) ne doivent PAS la lister (la GC
    # casserait les autres) — c'est le garde-fou anti-GC partagé.
    local c
    for c in registry gitea argocd; do
        run component_crd_groups "$c"
        [[ "$output" != *"gateway.networking.k8s.io"* ]] || { echo "$c liste gateway.* (GC partagé !)"; false; }
    done
}

@test "atom/CRD partagée : ceph.rook.io / objectbucket.io QUE chez ceph (pas sc/datalake/s3-*)" {
    run component_crd_groups ceph
    [[ "$output" == *"ceph.rook.io"* ]]
    [[ "$output" == *"objectbucket.io"* ]]
    local c
    for c in sc datalake s3-backing-loki s3-backing-cnpg; do
        run component_crd_groups "$c"
        [[ "$output" != *"ceph.rook.io"* ]] || { echo "$c liste ceph.rook.io partagé"; false; }
        [[ "$output" != *"objectbucket.io"* ]] || { echo "$c liste objectbucket.io partagé"; false; }
    done
}

@test "atom/CRD partagée : postgresql.cnpg.io chez cnpg-operator, PAS chez cnpg-cluster-pg" {
    run component_crd_groups cnpg-operator
    [[ "$output" == *"postgresql.cnpg.io"* ]]
    run component_crd_groups cnpg-cluster-pg
    [[ "$output" != *"postgresql.cnpg.io"* ]]
    [[ "$output" != *"barmancloud.cnpg.io"* ]]
}

# ─── stuck_cr_kinds : union DÉRIVÉE (fin de la liste figée) ──────────────────

@test "atom/stuck : dataops dérive Cluster CNPG + ObjectStore Barman + OBC" {
    run component_stuck_cr_kinds $(component_expand_alias dataops)
    [[ "$output" == *"cluster.postgresql.cnpg.io"* ]]
    [[ "$output" == *"objectstore.barmancloud.cnpg.io"* ]]
    [[ "$output" == *"obc.objectbucket.io"* ]]
}

@test "atom/stuck : sortie déterministe (triée, stable)" {
    local a b
    a=$(component_stuck_cr_kinds $(component_expand_alias atlas-ceph))
    b=$(component_stuck_cr_kinds $(component_expand_alias atlas-ceph))
    [ "$a" = "$b" ]
}

@test "atom/stuck : la dérivée (atlas-ceph) COUVRE chaque vrai kind de _STUCK_CR_KINDS" {
    # Garde-fou de la bascule Lot 3 : quand component_stuck_cr_kinds remplacera
    # _STUCK_CR_KINDS, la couverture ne doit pas régresser. On vérifie que chaque
    # entrée de la liste figée qui est un VRAI kind (group.kind) est dérivée.
    # EXCEPTION documentée : `objectbucket.io` SEUL (groupe API nu, pas un kind)
    # est une redondance défensive de la figée — `obc.objectbucket.io` est le kind
    # réel et il EST dérivé ; on ne réintroduit pas le groupe nu.
    local derived kind
    derived=$(component_stuck_cr_kinds $(component_expand_alias atlas-ceph))
    for kind in ${_STUCK_CR_KINDS}; do
        [ "$kind" = "objectbucket.io" ] && continue  # groupe nu, cf. ci-dessus
        [[ "$derived" == *"$kind"* ]] || { echo "kind figé non dérivé : $kind"; false; }
    done
}

# ─── component_known : catalogue ────────────────────────────────────────────

@test "atom/known : cnpg-operator connu ; nom inconnu rejeté" {
    run component_known cnpg-operator
    [ "$status" -eq 0 ]
    run component_known n-importe-quoi
    [ "$status" -ne 0 ]
}

# ═══ CLÔTURE PAR PHASE (ADR 0066 Lot 1) — remplace roundtrip.py:_DEPENDENTS ═══
# Garde-fou : la clôture DÉRIVÉE du graphe atomique doit reproduire EXACTEMENT
# l'ancien _DEPENDENTS validé à la main, sinon roundtrip.py régresse. Les arêtes
# « → sc » (PVC bloc) sont load-bearing pour gitops/gitops-seed (workflow consigné
# 2026-06-13, 2ᵉ trace).

@test "phase/closure : ceph dérive TOUTE la pile (== ancien _DEPENDENTS)" {
    run phase_closure ceph
    [ "$(printf '%s' "$output" | tr '\n' ' ')" = "ceph sc datalake monitoring gitops dataops gitops-seed" ]
}

@test "phase/closure : sc tire gitops/gitops-seed (arête gitea→sc load-bearing)" {
    local cl; cl=$(phase_closure sc | tr '\n' ' ')
    [ "$cl" = "sc datalake monitoring gitops dataops gitops-seed " ]
    # Sans l'arête gitea→sc, gitops serait absent — c'est le cœur du fix Lot 1.
    [[ "$cl" == *"gitops"* ]]
}

@test "phase/closure : datalake tire monitoring + dataops, PAS gitops" {
    run phase_closure datalake
    [ "$(printf '%s' "$output" | tr '\n' ' ')" = "datalake monitoring dataops" ]
}

@test "phase/closure : gitops tire gitops-seed" {
    run phase_closure gitops
    [ "$(printf '%s' "$output" | tr '\n' ' ')" = "gitops gitops-seed" ]
}

@test "phase/closure : feuilles ne tirent qu'elles-mêmes" {
    run phase_closure monitoring
    [ "$output" = "monitoring" ]
    run phase_closure dataops
    [ "$output" = "dataops" ]
    run phase_closure metrics-server
    [ "$output" = "metrics-server" ]
}

@test "phase/closure : ordre de MONTAGE (amont→aval, première occurrence)" {
    # Chaque phase de la clôture sort après celles dont elle dépend.
    local cl; cl=$(phase_closure ceph | tr '\n' ' ')
    # ceph avant sc avant datalake avant le reste.
    [[ "$cl" == "ceph sc datalake "* ]]
}

@test "phase/closure : phase inconnue → échec (code ≠0)" {
    run phase_closure frobnicate
    [ "$status" -ne 0 ]
}

@test "phase/involves_storage : ceph/sc/datalake → oui (opt-in --full)" {
    for p in ceph sc datalake; do
        run phase_involves_storage "$p"
        [ "$status" -eq 0 ] || { echo "$p devrait toucher le stockage"; false; }
    done
}

@test "phase/involves_storage : couches app → non" {
    for p in metrics-server monitoring dataops gitops gitops-seed; do
        run phase_involves_storage "$p"
        [ "$status" -ne 0 ] || { echo "$p ne devrait PAS toucher le stockage"; false; }
    done
}

@test "phase/of_component : composant socle → vide ; applicatif → sa phase" {
    run phase_of_component cert-manager   # socle, aucune phase roundtrip seule
    [ -z "$output" ]
    run phase_of_component prometheus-stack
    [ "$output" = "monitoring" ]
    run phase_of_component gitea
    [ "$output" = "gitops" ]
}

# ═══ GRAPHE BACKEND-CONDITIONNEL (ADR 0069) — variante LOCAL-PATH ════════════
# Le graphe est ceph-shaped par DÉFAUT (les tests ci-dessus, STORAGE_BACKEND unset).
# En local-path, les arêtes de stockage se reconfigurent : SC→storage-simple,
# S3→seaweedfs, et seaweedfs entre dans l'alias monitoring. Cette variante n'était
# pas couverte (le rollback réel ne tourne qu'en ceph) — on la fige ici.

@test "backend/local-path : les arêtes SC deviennent storage-simple, S3 deviennent seaweedfs" {
    STORAGE_BACKEND=local-path
    [ "$(component_deps loki)" = "prometheus-stack s3-backing-loki storage-simple" ]
    [ "$(component_deps s3-backing-cnpg)" = "seaweedfs" ]
    [ "$(component_deps registry)" = "gateway-api storage-simple" ]
    [ "$(component_deps gitea)" = "cert-manager gateway-api storage-simple" ]
}

@test "backend/local-path : monitoring pose AUSSI seaweedfs (alias)" {
    STORAGE_BACKEND=local-path
    run component_expand_alias monitoring
    [ "$status" -eq 0 ]
    [[ "$output" == *"seaweedfs"* ]]
}

@test "backend/local-path : topo_sort dataops ordonne storage-simple→seaweedfs→cnpg, sans datalake/sc" {
    STORAGE_BACKEND=local-path
    local order; order=$(topo_sort $(component_expand_alias dataops) | tr '\n' ' ')
    [[ "$order" != *" datalake "* ]] || { echo "datalake ne doit PAS apparaître en local-path"; false; }
    [[ "$order" != *" sc "* ]] || { echo "sc (Ceph) ne doit PAS apparaître en local-path"; false; }
    local p_ss p_sw p_pg
    p_ss=$(printf '%s\n' "$order" | tr ' ' '\n' | grep -nx storage-simple | cut -d: -f1)
    p_sw=$(printf '%s\n' "$order" | tr ' ' '\n' | grep -nx seaweedfs | cut -d: -f1)
    p_pg=$(printf '%s\n' "$order" | tr ' ' '\n' | grep -nx cnpg-cluster-pg | cut -d: -f1)
    [ "$p_ss" -lt "$p_sw" ] && [ "$p_sw" -lt "$p_pg" ]
}

@test "backend/ceph (défaut) : storage-simple/seaweedfs ABSENTS de la clôture ceph" {
    # Rétrocompat : sans env (défaut ceph), le graphe reste ceph-shaped.
    local cl; cl=$(topo_sort $(component_expand_alias atlas-ceph) | tr '\n' ' ')
    [[ "$cl" != *" storage-simple "* ]] || { echo "storage-simple fuit en ceph !"; false; }
    [[ "$cl" != *" seaweedfs "* ]] || { echo "seaweedfs fuit en ceph !"; false; }
    [[ "$cl" == *" datalake "* ]]  # datalake bien présent en ceph
}
