#!/usr/bin/env bats
#
# Tests des fonctions pures de classification du HEALTHCHECK cluster (ADR 0053).
# Aucun cluster requis : on source la lib partagée et on vérifie les verdicts
# `STATUS|message` (STATUS ∈ {ok, fail, skip}) sur des fixtures fixes. Même
# patron que state-classify.bats (setup source la lib ; run classify_x ARGS ;
# asserts sur status et output ok|/fail|/skip|).

setup() {
    # shellcheck source=../../bootstrap/lib/health-classify.sh
    source "${BATS_TEST_DIRNAME}/../../bootstrap/lib/health-classify.sh"
}

# ─── classify_cilium_operator ──────────────────────────────────────────────

@test "classify_cilium_operator readyReplicas==1 → ok" {
    run classify_cilium_operator 1
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "classify_cilium_operator readyReplicas==0 → fail" {
    run classify_cilium_operator 0
    [[ "$output" == fail\|* ]]
}

@test "classify_cilium_operator vide → fail" {
    run classify_cilium_operator
    [[ "$output" == fail\|* ]]
}

# ─── classify_cilium_daemonset ─────────────────────────────────────────────

@test "classify_cilium_daemonset ready==desired → ok" {
    run classify_cilium_daemonset 4 4
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"4/4"* ]]
}

@test "classify_cilium_daemonset ready<desired → fail" {
    run classify_cilium_daemonset 3 4
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"3/4"* ]]
}

@test "classify_cilium_daemonset desired==0 → skip" {
    run classify_cilium_daemonset 0 0
    [[ "$output" == skip\|* ]]
}

@test "classify_cilium_daemonset desired illisible → skip" {
    run classify_cilium_daemonset 1 ''
    [[ "$output" == skip\|* ]]
}

@test "classify_cilium_daemonset ready non numérique → fail" {
    run classify_cilium_daemonset '' 4
    [[ "$output" == fail\|* ]]
}

# ─── classify_nodes_ready ──────────────────────────────────────────────────

@test "classify_nodes_ready liste vide → ok" {
    run classify_nodes_ready ''
    [[ "$output" == ok\|* ]]
}

@test "classify_nodes_ready espaces de bord seuls → ok (normalisation)" {
    run classify_nodes_ready '   '
    [[ "$output" == ok\|* ]]
}

@test "classify_nodes_ready compte Ready affiché si fourni" {
    run classify_nodes_ready '' 4
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"4"* ]]
}

@test "classify_nodes_ready nœuds non Ready → fail" {
    run classify_nodes_ready 'node2 node3'
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"node2"* ]]
}

# ─── classify_pod_cidr ─────────────────────────────────────────────────────

@test "classify_pod_cidr défaut 10.244.0.0/16 → ok" {
    run classify_pod_cidr 10.244.0.0/16
    [[ "$output" == ok\|* ]]
}

@test "classify_pod_cidr EXPECTED explicite concordant → ok" {
    run classify_pod_cidr 10.42.0.0/16 10.42.0.0/16
    [[ "$output" == ok\|* ]]
}

@test "classify_pod_cidr divergent → fail" {
    run classify_pod_cidr 10.0.0.0/22
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"10.244.0.0/16"* ]]
}

@test "classify_pod_cidr vide → skip" {
    run classify_pod_cidr ''
    [[ "$output" == skip\|* ]]
}

# ─── classify_ceph_operator ────────────────────────────────────────────────

@test "classify_ceph_operator readyReplicas==1 → ok" {
    run classify_ceph_operator 1
    [[ "$output" == ok\|* ]]
}

@test "classify_ceph_operator readyReplicas==0 → fail" {
    run classify_ceph_operator 0
    [[ "$output" == fail\|* ]]
}

@test "classify_ceph_operator vide → fail" {
    run classify_ceph_operator
    [[ "$output" == fail\|* ]]
}

# ─── classify_ceph_health ──────────────────────────────────────────────────

@test "classify_ceph_health HEALTH_OK → ok" {
    run classify_ceph_health HEALTH_OK
    [[ "$output" == ok\|* ]]
}

@test "classify_ceph_health HEALTH_WARN → fail" {
    run classify_ceph_health HEALTH_WARN
    [[ "$output" == fail\|* ]]
}

@test "classify_ceph_health HEALTH_ERR → fail" {
    run classify_ceph_health HEALTH_ERR
    [[ "$output" == fail\|* ]]
}

@test "classify_ceph_health vide → skip" {
    run classify_ceph_health ''
    [[ "$output" == skip\|* ]]
}

@test "classify_ceph_health état inattendu → fail" {
    run classify_ceph_health HEALTH_BOGUS
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"HEALTH_BOGUS"* ]]
}

# ─── classify_ceph_osd ─────────────────────────────────────────────────────

@test "classify_ceph_osd up==total>0 → ok" {
    run classify_ceph_osd 3 3
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"3/3"* ]]
}

@test "classify_ceph_osd up<total → fail" {
    run classify_ceph_osd 2 3
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"2/3"* ]]
}

@test "classify_ceph_osd total==0 → skip" {
    run classify_ceph_osd 0 0
    [[ "$output" == skip\|* ]]
}

@test "classify_ceph_osd total illisible → skip" {
    run classify_ceph_osd 0 ''
    [[ "$output" == skip\|* ]]
}

@test "classify_ceph_osd up non numérique → fail" {
    run classify_ceph_osd '' 3
    [[ "$output" == fail\|* ]]
}

# ─── classify_sc_default ───────────────────────────────────────────────────

@test "classify_sc_default défaut rook-ceph-block-replicated → ok" {
    run classify_sc_default rook-ceph-block-replicated
    [[ "$output" == ok\|* ]]
}

@test "classify_sc_default EXPECTED explicite concordant → ok" {
    run classify_sc_default ma-sc ma-sc
    [[ "$output" == ok\|* ]]
}

@test "classify_sc_default autre SC → fail" {
    run classify_sc_default rook-ceph-block-ec
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"rook-ceph-block-replicated"* ]]
}

@test "classify_sc_default vide → fail (aucune SC par défaut)" {
    run classify_sc_default ''
    [[ "$output" == fail\|* ]]
}

# ─── classify_pvc_bound ────────────────────────────────────────────────────

@test "classify_pvc_bound toutes Bound → ok" {
    run classify_pvc_bound '' 5
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"5"* ]]
}

@test "classify_pvc_bound espaces de bord seuls → ok (normalisation)" {
    run classify_pvc_bound '   ' 5
    [[ "$output" == ok\|* ]]
}

@test "classify_pvc_bound certaines non Bound → fail" {
    run classify_pvc_bound 'default/data-0' 5
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"default/data-0"* ]]
}

@test "classify_pvc_bound total==0 → skip (aucune PVC)" {
    run classify_pvc_bound '' 0
    [[ "$output" == skip\|* ]]
}

@test "classify_pvc_bound total illisible → skip" {
    run classify_pvc_bound '' ''
    [[ "$output" == skip\|* ]]
}

# ─── classify_pvc_no_ec ────────────────────────────────────────────────────

@test "classify_pvc_no_ec aucune PVC sur EC → ok" {
    run classify_pvc_no_ec ''
    [[ "$output" == ok\|* ]]
}

@test "classify_pvc_no_ec espaces de bord seuls → ok (normalisation)" {
    run classify_pvc_no_ec '   '
    [[ "$output" == ok\|* ]]
}

@test "classify_pvc_no_ec PVC résiduelle sur EC → fail" {
    run classify_pvc_no_ec 'default/app-data'
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"default/app-data"* ]]
}

# ─── classify_deploy_ready ─────────────────────────────────────────────────

@test "classify_deploy_ready ready==desired → ok" {
    run classify_deploy_ready registry 1 1
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"registry"* ]]
    [[ "$output" == *"1/1"* ]]
}

@test "classify_deploy_ready ready<desired → fail" {
    run classify_deploy_ready cert-manager 0 1
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"0/1"* ]]
}

@test "classify_deploy_ready desired==0 → skip (mis à l'échelle 0)" {
    run classify_deploy_ready dagster 0 0
    [[ "$output" == skip\|* ]]
}

@test "classify_deploy_ready desired illisible → skip (déploiement absent)" {
    run classify_deploy_ready marquez '' ''
    [[ "$output" == skip\|* ]]
}

@test "classify_deploy_ready ready non numérique → fail" {
    run classify_deploy_ready prometheus '' 1
    [[ "$output" == fail\|* ]]
}

# ─── classify_target_match (garde-fou ADR 0053) ────────────────────────────

@test "classify_target_match concordant → ok" {
    run classify_target_match abc123 abc123
    [[ "$output" == ok\|* ]]
    [[ "$output" == *"abc123"* ]]
}

@test "classify_target_match étiquette libre concordante → ok" {
    run classify_target_match prod prod
    [[ "$output" == ok\|* ]]
}

@test "classify_target_match divergent → skip bruyant (jamais fail)" {
    run classify_target_match abc123 deadbeef
    [[ "$output" == skip\|* ]]
    [[ "$output" != fail\|* ]]
    [[ "$output" == *"KUBECONFIG"* ]]
}

@test "classify_target_match EXPECTED vide → skip (cible non confirmée)" {
    run classify_target_match '' abc123
    [[ "$output" == skip\|* ]]
    [[ "$output" == *"EXPECT_CLUSTER"* ]]
}
