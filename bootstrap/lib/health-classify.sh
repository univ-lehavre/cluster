#!/usr/bin/env bash
#
# Fonctions PURES de classification du HEALTHCHECK cluster (ADR 0053).
#
# Lib PARTAGÉE consommée par deux frontaux :
#   - bootstrap/state.sh           (prod  : collecte SSH + kubectl, puis classe)
#   - test/lima/run-phases.sh      (banc  : collecte kubectl --kubeconfig, puis classe)
#
# Comme bootstrap/lib/state-classify.sh, ces fonctions ne font NI SSH, NI
# kubectl : elles prennent en entrée des valeurs DÉJÀ collectées par le frontal
# (compteurs, chaînes, champs jsonpath) et renvoient un verdict `STATUS|message`
# sur stdout, où STATUS ∈ {ok, fail, skip}. Le frontal collecte (réseau), la
# fonction classe (décision testable). But : rendre la logique de verdict de
# l'audit cluster testable SANS cluster (bats — test/unit/health-classify.bats).
#
# Convention de sortie : une ligne "STATUS|message". L'appelant découpe sur le
# premier '|' (cf. mark_classified dans state.sh). Aucune fonction n'écrit
# ailleurs que sur stdout, ni n'appelle `exit` (testabilité).
#
# Robustesse : un compteur attendu mais vide (collecte qui a échoué, ressource
# absente) vaut 0 ; toute comparaison numérique est gardée pour ne jamais lever
# d'erreur arithmétique sur une valeur non numérique (skip plutôt que crash).

# _is_num VALUE
#   Vrai (0) si VALUE est un entier décimal non signé (chaîne de chiffres).
#   Helper interne : sécurise les comparaisons `-eq`/`-ge` sur des champs
#   collectés qui peuvent être vides ou non numériques.
_is_num() {
    case "${1:-}" in
        '' | *[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

# ─── Cilium ─────────────────────────────────────────────────────────────────

# classify_cilium_operator READY_REPLICAS
#   cilium-operator : .status.readyReplicas du Deployment kube-system/cilium-operator.
#   - readyReplicas == 1 → ok
#   - sinon              → fail
classify_cilium_operator() {
    local ready=${1:-}
    if [ "$ready" = "1" ]; then
        printf 'ok|cilium-operator Ready\n'
    else
        printf 'fail|cilium-operator non Ready (readyReplicas=%s)\n' "${ready:-0}"
    fi
}

# classify_cilium_daemonset READY DESIRED
#   cilium DaemonSet : .status.numberReady / .status.desiredNumberScheduled.
#   - desired illisible (vide/non num.)        → skip
#   - desired == 0                             → skip (DaemonSet pas encore planifié)
#   - ready == desired (!= 0)                  → ok
#   - sinon                                    → fail
classify_cilium_daemonset() {
    local ready=${1:-} desired=${2:-}
    if ! _is_num "$desired"; then
        printf 'skip|cilium DaemonSet : desiredNumberScheduled illisible\n'
        return
    fi
    if [ "$desired" -eq 0 ]; then
        printf 'skip|cilium DaemonSet : aucun agent planifié (desired=0)\n'
        return
    fi
    if _is_num "$ready" && [ "$ready" -eq "$desired" ]; then
        printf 'ok|cilium DaemonSet : %s/%s agents Ready\n' "$ready" "$desired"
    else
        printf 'fail|cilium DaemonSet : %s/%s agents Ready\n' "${ready:-0}" "$desired"
    fi
}

# classify_nodes_ready NOT_READY [READY_N]
#   Nœuds tous Ready ? NOT_READY = liste (séparée par des espaces) des nœuds dont
#   la colonne STATUS != Ready ; vide = tous Ready. READY_N (optionnel) = nombre
#   de nœuds Ready (affiché si fourni).
#   - NOT_READY vide → ok
#   - sinon          → fail (liste les nœuds)
classify_nodes_ready() {
    local not_ready=${1:-} ready_n=${2:-}
    # On normalise les espaces de bord pour qu'une liste « vide mais avec espace »
    # (ex. issue d'un `tr '\n' ' '` sur 0 ligne) compte bien comme vide.
    not_ready=${not_ready#"${not_ready%%[![:space:]]*}"}
    not_ready=${not_ready%"${not_ready##*[![:space:]]}"}
    if [ -z "$not_ready" ]; then
        if [ -n "$ready_n" ]; then
            printf 'ok|tous les nœuds Ready (%s)\n' "$ready_n"
        else
            printf 'ok|tous les nœuds Ready\n'
        fi
    else
        printf 'fail|nœuds non Ready : %s\n' "$not_ready"
    fi
}

# classify_pod_cidr CIDR [EXPECTED]
#   Pod CIDR Cilium (cilium-config .data.cluster-pool-ipv4-cidr) attendu disjoint
#   des plages nœuds. EXPECTED par défaut 10.244.0.0/16 (cf. state.sh).
#   - CIDR vide        → skip (cilium-config absent)
#   - CIDR == EXPECTED → ok
#   - sinon            → fail
classify_pod_cidr() {
    local cidr=${1:-} expected=${2:-10.244.0.0/16}
    if [ -z "$cidr" ]; then
        printf 'skip|pod CIDR Cilium illisible (cilium-config absent ?)\n'
    elif [ "$cidr" = "$expected" ]; then
        printf 'ok|pod CIDR Cilium = %s (disjoint nœuds)\n' "$expected"
    else
        printf 'fail|pod CIDR = %s (attendu %s)\n' "$cidr" "$expected"
    fi
}

# ─── Rook-Ceph ──────────────────────────────────────────────────────────────

# classify_ceph_operator READY_REPLICAS
#   rook-ceph-operator : .status.readyReplicas du Deployment rook-ceph/rook-ceph-operator.
#   - readyReplicas == 1 → ok
#   - sinon              → fail
classify_ceph_operator() {
    local ready=${1:-}
    if [ "$ready" = "1" ]; then
        printf 'ok|rook-ceph-operator Ready\n'
    else
        printf 'fail|rook-ceph-operator non Ready (readyReplicas=%s)\n' "${ready:-0}"
    fi
}

# classify_ceph_health HEALTH
#   Santé Ceph : CephCluster .status.ceph.health.
#   - HEALTH_OK   → ok
#   - HEALTH_WARN → fail
#   - HEALTH_ERR  → fail
#   - vide        → skip (CephCluster non créé)
#   - autre       → fail (état inattendu)
classify_ceph_health() {
    local health=${1:-}
    case "$health" in
        HEALTH_OK)   printf 'ok|CephCluster HEALTH_OK\n' ;;
        HEALTH_WARN) printf 'fail|CephCluster HEALTH_WARN\n' ;;
        HEALTH_ERR)  printf 'fail|CephCluster HEALTH_ERR\n' ;;
        '')          printf 'skip|CephCluster non créé (kubectl create -f storage/ceph/cluster.yaml)\n' ;;
        *)           printf 'fail|CephCluster état inattendu (%s)\n' "$health" ;;
    esac
}

# classify_ceph_osd UP TOTAL
#   OSD Ceph : UP = pods rook-ceph-osd Running, TOTAL = pods rook-ceph-osd.
#   - total illisible (vide/non num.)  → skip
#   - total == 0                       → skip (CephCluster pas encore appliqué)
#   - up == total (total > 0)          → ok
#   - sinon                            → fail
classify_ceph_osd() {
    local up=${1:-} total=${2:-}
    if ! _is_num "$total"; then
        printf 'skip|OSD : compte illisible\n'
        return
    fi
    if [ "$total" -eq 0 ]; then
        printf 'skip|pas encore d'\''OSD (CephCluster pas appliqué)\n'
        return
    fi
    if _is_num "$up" && [ "$up" -eq "$total" ]; then
        printf 'ok|OSD : %s/%s up\n' "$up" "$total"
    else
        printf 'fail|OSD : %s/%s up\n' "${up:-0}" "$total"
    fi
}

# ─── StorageClasses et PVC ──────────────────────────────────────────────────

# classify_sc_default DEFAULT_SC [EXPECTED]
#   StorageClass par défaut (celle marquée (default)). EXPECTED par défaut
#   rook-ceph-block-replicated (cf. state.sh).
#   - DEFAULT_SC vide        → fail (aucune SC par défaut)
#   - DEFAULT_SC == EXPECTED → ok
#   - sinon                  → fail
classify_sc_default() {
    local sc=${1:-} expected=${2:-rook-ceph-block-replicated}
    if [ -z "$sc" ]; then
        printf 'fail|aucune StorageClass par défaut\n'
    elif [ "$sc" = "$expected" ]; then
        printf 'ok|StorageClass par défaut = %s\n' "$expected"
    else
        printf 'fail|défaut = %s (attendu %s)\n' "$sc" "$expected"
    fi
}

# classify_pvc_bound NOT_BOUND TOTAL
#   PVC toutes Bound ? NOT_BOUND = liste (séparée par des espaces) des PVC
#   ns/nom dont la phase != Bound ; TOTAL = nombre total de PVC.
#   - total illisible (vide/non num.) → skip
#   - total == 0                      → skip (aucune PVC)
#   - NOT_BOUND vide                  → ok
#   - sinon                           → fail (liste les PVC)
classify_pvc_bound() {
    local not_bound=${1:-} total=${2:-}
    not_bound=${not_bound#"${not_bound%%[![:space:]]*}"}
    not_bound=${not_bound%"${not_bound##*[![:space:]]}"}
    if ! _is_num "$total"; then
        printf 'skip|PVC : compte illisible\n'
        return
    fi
    if [ "$total" -eq 0 ]; then
        printf 'skip|aucune PVC\n'
        return
    fi
    if [ -z "$not_bound" ]; then
        printf 'ok|%s PVC Bound\n' "$total"
    else
        printf 'fail|PVC non Bound : %s\n' "$not_bound"
    fi
}

# classify_pvc_no_ec APPS_ON_EC
#   Aucune PVC applicative ne doit rester sur rook-ceph-block-ec (pool EC réservé
#   au stockage objet, pas au bloc applicatif). APPS_ON_EC = liste (séparée par
#   des espaces) des PVC ns/nom dont storageClassName == rook-ceph-block-ec.
#   - APPS_ON_EC vide → ok
#   - sinon           → fail (liste les PVC)
classify_pvc_no_ec() {
    local apps=${1:-}
    apps=${apps#"${apps%%[![:space:]]*}"}
    apps=${apps%"${apps##*[![:space:]]}"}
    if [ -z "$apps" ]; then
        printf 'ok|aucune PVC applicative résiduelle sur rook-ceph-block-ec\n'
    else
        printf 'fail|PVC encore sur rook-ceph-block-ec : %s\n' "$apps"
    fi
}

# ─── Plateforme (Deployments / pods Running) ────────────────────────────────

# classify_deploy_ready LABEL READY DESIRED
#   Verdict générique pour une brique plateforme dont la santé se lit comme un
#   Deployment : READY = .status.readyReplicas, DESIRED = .spec.replicas.
#   Sert registry, cert-manager, prometheus, cnpg, dagster, marquez…
#   - DESIRED illisible (vide/non num.)  → skip (déploiement absent)
#   - DESIRED == 0                       → skip (mis à l'échelle 0)
#   - READY == DESIRED (!= 0)            → ok
#   - sinon                              → fail
classify_deploy_ready() {
    local label=${1:-déploiement} ready=${2:-} desired=${3:-}
    if ! _is_num "$desired"; then
        printf 'skip|%s : déploiement absent\n' "$label"
        return
    fi
    if [ "$desired" -eq 0 ]; then
        printf 'skip|%s : mis à l'\''échelle 0\n' "$label"
        return
    fi
    if _is_num "$ready" && [ "$ready" -eq "$desired" ]; then
        printf 'ok|%s : %s/%s Ready\n' "$label" "$ready" "$desired"
    else
        printf 'fail|%s : %s/%s Ready\n' "$label" "${ready:-0}" "$desired"
    fi
}

# ─── Garde-fou de cible (ADR 0053 issue P1) ─────────────────────────────────

# classify_target_match EXPECTED ACTUAL
#   Garde-fou : confirme que les couches kubectl auditent bien la cible voulue.
#   EXPECTED = valeur de la variable d'env EXPECT_CLUSTER (empreinte attendue ou
#   étiquette libre prod/lima), ACTUAL = empreinte du cluster ambiant calculée
#   par le FRONTAL (cluster_fingerprint, qui fait du kubectl et vit donc HORS de
#   cette lib pure). Cette fonction ne fait QUE comparer deux chaînes.
#   - EXPECTED vide            → skip (cible non confirmée : on REFUSE le verdict)
#   - EXPECTED == ACTUAL       → ok   (cible confirmée)
#   - EXPECTED != ACTUAL       → skip (divergence : refus bruyant, jamais fail)
#
#   NB : la divergence est un SKIP bruyant (pas un fail) — un fail signalerait un
#   drift de la cible auditée, or ici on ne sait simplement pas si l'on regarde
#   le bon cluster ; on refuse de rendre un verdict ok/fail (ADR 0053 (a)).
classify_target_match() {
    local expected=${1:-} actual=${2:-}
    if [ -z "$expected" ]; then
        printf 'skip|cible non confirmée : définir EXPECT_CLUSTER (empreinte ou étiquette) avant d'\''auditer via kubectl\n'
    elif [ "$expected" = "$actual" ]; then
        printf 'ok|cible confirmée (EXPECT_CLUSTER=%s)\n' "$expected"
    else
        printf 'skip|cible divergente : EXPECT_CLUSTER=%s mais cluster ambiant=%s — vérifier le KUBECONFIG\n' "$expected" "${actual:-?}"
    fi
}
