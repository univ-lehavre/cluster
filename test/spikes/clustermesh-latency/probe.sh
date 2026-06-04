#!/usr/bin/env bash
#
# Preuve du mesh + mesure du RTT inter-cluster sous latence.
#
#   1. Déploie un echo-server dans site-b, exposé par un Service GLOBAL
#      (annotation service.cilium.io/global=true) → joignable depuis site-a.
#   2. Depuis un pod client dans site-a, curl le service global : s'il répond,
#      le mesh route bien le trafic inter-cluster.
#   3. Mesure le RTT applicatif (utile à coupler avec ./latency.sh pour observer
#      la dégradation sous latence croissante).
#
# Usage :
#   ./probe.sh deploy    # (idempotent) déploie echo-server + service global
#   ./probe.sh test      # vérifie le routage inter-cluster (site-a -> site-b)
#   ./probe.sh rtt [n]   # mesure n requêtes (défaut 10) et affiche le RTT moyen
#   ./probe.sh sweep     # boucle 0/10/50/100 ms via latency.sh et tabule le RTT
#   ./probe.sh           # = deploy + test + rtt

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=test/spikes/clustermesh-latency/lib.sh
. "${HERE}/lib.sh"

need kubectl

# KUBECONFIG fusionné des deux sites (généré par up.sh). Permet le pilotage par
# contexte (--context spike-site-a / spike-site-b) depuis l'hôte.
[ -f "${A_KUBECONFIG}" ] && [ -f "${B_KUBECONFIG}" ] \
    || die "kubeconfigs des sites absents — lancer ./up.sh d'abord"
export KUBECONFIG="${A_KUBECONFIG}:${B_KUBECONFIG}"

NS=mesh-spike
SVC=echo-global
CLIENT=mesh-client

k1() { kubectl --context "${A_CTX}" "$@"; }
k2() { kubectl --context "${B_CTX}" "$@"; }

deploy() {
    log "Déploiement de l'echo-server (service global) dans ${B_NAME}"
    k2 create namespace "${NS}" --dry-run=client -o yaml | k2 apply -f -
    # echo-server : renvoie son hostname → on voit quel cluster a répondu.
    k2 -n "${NS}" apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${SVC}
spec:
  replicas: 1
  selector:
    matchLabels: { app: ${SVC} }
  template:
    metadata:
      labels: { app: ${SVC} }
    spec:
      containers:
        - name: echo
          image: registry.k8s.io/e2e-test-images/agnhost:2.45
          args: ["netexec", "--http-port=8080"]
          ports:
            - containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: ${SVC}
  annotations:
    service.cilium.io/global: "true" # rend le service joignable cross-cluster
spec:
  selector: { app: ${SVC} }
  ports:
    - port: 8080
      targetPort: 8080
EOF
    k2 -n "${NS}" rollout status deploy/"${SVC}" --timeout=120s

    log "Déploiement du pod client dans ${A_NAME}"
    k1 create namespace "${NS}" --dry-run=client -o yaml | k1 apply -f -
    # Le Service global doit exister des DEUX côtés (même nom/namespace) pour que
    # Cilium fusionne les backends. Côté site-a : Service global SANS backend local.
    k1 -n "${NS}" apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${SVC}
  annotations:
    service.cilium.io/global: "true"
spec:
  selector: { app: ${SVC} }
  ports:
    - port: 8080
      targetPort: 8080
EOF
    # Pod immuable (les containers ne se patchent pas) → create seulement si absent.
    if ! k1 -n "${NS}" get pod "${CLIENT}" > /dev/null 2>&1; then
        k1 -n "${NS}" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${CLIENT}
spec:
  containers:
    - name: curl
      image: curlimages/curl:8.10.1
      command: ["sleep", "infinity"]
EOF
    fi
    k1 -n "${NS}" wait --for=condition=Ready pod/"${CLIENT}" --timeout=120s
    ok "echo-server (site-b) + client (site-a) prêts"
}

# Exécute un curl depuis le client de site-a vers le service global.
curl_from_a() {
    k1 -n "${NS}" exec "${CLIENT}" -- \
        curl -s -m 10 "http://${SVC}.${NS}.svc.cluster.local:8080/hostname"
}

test_mesh() {
    log "Test du routage inter-cluster (client site-a → service global)"
    local out
    out=$(curl_from_a) || die "le curl a échoué — le mesh ne route pas (voir cilium clustermesh status)"
    if [ -n "${out}" ]; then
        ok "réponse reçue du backend : '${out}' (servi par site-b via le mesh)"
    else
        die "réponse vide"
    fi
}

measure_rtt() {
    local n="${1:-10}"
    log "Mesure du RTT applicatif sur ${n} requêtes (site-a → site-b)"
    # time_total de curl, moyenné côté pod (évite le bruit kubectl exec).
    local avg
    avg=$(k1 -n "${NS}" exec "${CLIENT}" -- sh -c "
        total=0
        for i in \$(seq 1 ${n}); do
            t=\$(curl -s -o /dev/null -w '%{time_total}' -m 10 \
                http://${SVC}.${NS}.svc.cluster.local:8080/hostname)
            total=\$(awk \"BEGIN{print \$total + \$t}\")
        done
        awk \"BEGIN{printf \\\"%.1f\\\", (\$total/${n})*1000}\"
    ") || die "mesure RTT impossible"
    printf '  RTT applicatif moyen : \033[1;32m%s ms\033[0m (sur %s requêtes)\n' "${avg}" "${n}"
    echo "${avg}"
}

sweep() {
    deploy
    test_mesh
    printf '\n  %-12s %-18s\n' "Latence netem" "RTT applicatif"
    printf '  %-12s %-18s\n' "-------------" "--------------"
    for ms in 0 10 50 100; do
        if [ "${ms}" = 0 ]; then
            "${HERE}/latency.sh" clear > /dev/null
        else
            "${HERE}/latency.sh" "${ms}" > /dev/null
        fi
        sleep 2
        rtt=$(measure_rtt 10 | tail -1)
        printf '  %-12s %-18s\n' "${ms} ms (×2)" "${rtt} ms"
    done
    "${HERE}/latency.sh" clear > /dev/null
    ok "sweep terminé — netem retiré"
}

case "${1:-all}" in
    deploy) deploy ;;
    test) test_mesh ;;
    rtt) measure_rtt "${2:-10}" ;;
    sweep) sweep ;;
    all) deploy; test_mesh; measure_rtt 10 ;;
    *) die "usage : ./probe.sh [deploy|test|rtt [n]|sweep]" ;;
esac
