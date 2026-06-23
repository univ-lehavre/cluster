#!/usr/bin/env bats
#
# Tests des fonctions PURES de bench/lima/access.sh (accès dev, ADR 0048/0092) :
# host_port_for, url_line, env_line, read_lines. Aucun cluster, aucun réseau : on
# source le script (le garde BASH_SOURCE != $0 empêche `main`) et on vérifie les
# sorties. L'exposition est en L4 NodePort (ADR 0092) : plus de Gateway, plus de
# forward SSH, plus de bloc /etc/hosts (fonctions render_/strip_hosts_block
# retirées).

setup() {
    # shellcheck source=../../bench/lima/access.sh
    source "${BATS_TEST_DIRNAME}/../../bench/lima/access.sh"
}

@test "host_port_for : index 0 → BASE_PORT" {
    run host_port_for 0
    [ "$status" -eq 0 ]
    [ "$output" = "8443" ]
}

@test "host_port_for : index 4 → BASE_PORT+4" {
    run host_port_for 4
    [ "$output" = "8447" ]
}

@test "url_line : ligne alignée [layer] url (auth: ...)" {
    run url_line gitops http://127.0.0.1:8443 secret-admin
    [ "$status" -eq 0 ]
    [[ "${output}" == *"[gitops"* ]]
    [[ "${output}" == *"http://127.0.0.1:8443"* ]]
    [[ "${output}" == *"(auth: secret-admin)"* ]]
}

@test "url_line : auth none tolérée" {
    run url_line socle http://127.0.0.1:8450 none
    [[ "${output}" == *"(auth: none)"* ]]
}

@test "env_line : KEY=VALUE" {
    run env_line FOO bar
    [ "$output" = "FOO=bar" ]
}

@test "env_line : valeur vide tolérée (KEY=)" {
    run env_line EMPTY ""
    [ "$output" = "EMPTY=" ]
}

@test "read_lines : peuple un tableau, une entrée par ligne" {
    read_lines arr < <(printf 'a\nb c\nd\n')
    [ "${#arr[@]}" -eq 3 ]
    [ "${arr[1]}" = "b c" ]
}
