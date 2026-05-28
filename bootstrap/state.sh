#!/usr/bin/env bash
#
# État du cluster — passe en revue chaque couche du déploiement face à l'état
# attendu et propose la prochaine étape (ou lève un drift).
#
# Usage :
#   bootstrap/state.sh                              # tous les hôtes par défaut
#   bootstrap/state.sh dirqual1 dirqual2            # subset
#   SSH_OPTS='-p 2222 -i ~/key' bootstrap/state.sh 127.0.0.1   # banc/dev
#
# Variables d'env :
#   USER_REMOTE      utilisateur SSH                (défaut: debian)
#   SSH_OPTS         options ssh additionnelles     (défaut: vide)
#   NO_COLOR=1       désactive les couleurs ANSI
#
# Codes de sortie :
#   0 — tout est conforme
#   1 — drift détecté (au moins un check ✗) ; voir « Prochaine étape »
#   2 — aucun hôte joignable (exécuter first-access.sh d'abord)

set -euo pipefail

USER_REMOTE=${USER_REMOTE:-debian}
SSH_OPTS=${SSH_OPTS:-}

hosts=("$@")
if [ ${#hosts[@]} -eq 0 ]; then
    hosts=(dirqual1 dirqual2 dirqual3 dirqual4)
fi

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[34m'
    C=$'\033[36m'; D=$'\033[2m';  N=$'\033[0m'
else
    G=''; R=''; Y=''; B=''; C=''; D=''; N=''
fi

declare -i ok_n=0 fail_n=0 skip_n=0 reachable_n=0
next_step=""

ssh_q() {
    # ssh_q HOST CMD — best effort, stderr muet, retourne stdout.
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" 2>/dev/null
}

ssh_ok() {
    # ssh_ok HOST CMD — exit 0 si la commande distante renvoie 0.
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" "$2" >/dev/null 2>&1
}

ssh_script() {
    # ssh_script HOST — lit un script bash depuis stdin et l'exécute via
    # `sudo bash -s` sur HOST. Utile pour les vérifications multi-lignes
    # qui touchent à /etc/shadow ou autres fichiers privilégiés.
    # shellcheck disable=SC2086 # we want word splitting on $SSH_OPTS
    ssh $SSH_OPTS -o ConnectTimeout=5 -o BatchMode=yes \
        "${USER_REMOTE}@$1" 'sudo bash -s' 2>/dev/null
}

kubectl_q() { kubectl "$@" 2>/dev/null; }

kubectl_ready() {
    command -v kubectl >/dev/null 2>&1 && kubectl version --request-timeout=3s >/dev/null 2>&1
}

mark() {
    # mark ok|fail|skip "label" ["remedy"]
    local status=$1 label=$2 remedy=${3:-}
    case "$status" in
        ok)   printf '  %s✓%s %s\n' "$G" "$N" "$label"; ok_n+=1 ;;
        fail) printf '  %s✗%s %s\n' "$R" "$N" "$label"; fail_n+=1
              if [ -n "$remedy" ] && [ -z "$next_step" ]; then
                  next_step="$remedy"
              fi ;;
        skip) printf '  %s⏭ %s%s\n' "$D" "$label" "$N"; skip_n+=1 ;;
    esac
    return 0
}

section() { printf '\n%s── %s ──%s\n' "$B" "$1" "$N"; }

# ─── Joignabilité ──────────────────────────────────────────────────────────
section "Joignabilité SSH"
reachable=()
for h in "${hosts[@]}"; do
    if ssh_ok "$h" true; then
        mark ok "$h joignable (clé SSH OK)"
        reachable+=("$h")
        reachable_n+=1
    else
        mark skip "$h non joignable — install OS + bootstrap/first-access.sh $h"
    fi
done

if [ "$reachable_n" -eq 0 ]; then
    printf '\n%sAucun hôte joignable.%s Étape : installer l'\''OS + déposer la clé.\n' "$R" "$N"
    exit 2
fi

# ─── Couche 1 — Premier accès / sshd hardening ─────────────────────────────
section "Premier accès SSH (bootstrap/first-access.sh)"
for h in "${reachable[@]}"; do
    # shellcheck disable=SC2016 # $VERSION_ID expanded on the remote shell
    if [ "$(ssh_q "$h" '. /etc/os-release; echo "$VERSION_ID"')" = "13" ]; then
        mark ok "$h : Debian 13"
    else
        mark fail "$h : pas en Debian 13" "réinstaller en Debian 13 (cf. RUNBOOK)"
    fi

    if ssh_ok "$h" 'sudo -n true'; then
        mark ok "$h : sudo NOPASSWD"
    else
        mark fail "$h : sudo demande encore un mot de passe" \
                  "bash bootstrap/first-access.sh $h"
    fi

    if ssh_ok "$h" 'sudo test -f /etc/ssh/sshd_config.d/00-hardening.conf'; then
        mark ok "$h : sshd drop-in présent"
    else
        mark fail "$h : sshd drop-in absent" "bash bootstrap/first-access.sh $h"
    fi

    if [ "$(ssh_q "$h" "sudo sshd -T 2>/dev/null | awk '/^passwordauthentication/{print \$2}'")" = "no" ]; then
        mark ok "$h : PasswordAuthentication=no"
    else
        mark fail "$h : PasswordAuthentication toujours autorisé" \
                  "bash bootstrap/first-access.sh $h"
    fi

    # Mot de passe debian modifié depuis l'install ? On compare la date de
    # dernier `passwd` (chage) à celle de création de /etc/machine-id
    # (= premier boot post-install). L'arithmétique se fait côté serveur
    # (GNU date) pour rester compatible avec un poste de contrôle macOS.
    pw_result=$(ssh_script "$h" <<'REMOTE'
last=$(chage -l debian 2>/dev/null | awk -F: '/Last password change/{print $2}' | xargs)
install=$(stat -c '%y' /etc/machine-id 2>/dev/null | cut -d' ' -f1)
le=$(date -d "$last" +%s 2>/dev/null || echo 0)
ie=$(date -d "$install" +%s 2>/dev/null || echo 0)
if [ "$le" -eq 0 ] || [ "$ie" -eq 0 ]; then
    echo "UNKNOWN 0"
else
    days=$(( (le - ie) / 86400 ))
    if [ "$days" -le 1 ]; then
        echo "NEVER $days"
    else
        echo "MOD $days"
    fi
fi
REMOTE
    )
    read -r pw_status pw_days <<<"$pw_result"
    case "$pw_status" in
        MOD)
            mark ok "$h : mot de passe debian modifié (~${pw_days} j après install)"
            ;;
        NEVER)
            mark fail "$h : mot de passe debian JAMAIS modifié depuis l'install" \
                      "ssh $h sudo passwd debian (ou NEW_DEBIAN_PASSWORD=... bash bootstrap/first-access.sh $h)"
            ;;
        *)
            mark skip "$h : impossible de lire les dates passwd/install (sudo ? chage ? machine-id ?)"
            ;;
    esac
done

# ─── Couche 2 — Hardening OS (opt-in par couche) ───────────────────────────
# Le hardening est volontairement OPT-IN (voir bootstrap/security/IMPLICATIONS.md) :
# un service absent n'est PAS un drift, c'est une couche non encore activée.
# Le drift n'arrive que si la couche est partiellement activée (ex. paquet
# installé mais service inactif), ou si une protection a régressé.
section "Hardening OS (opt-in — bootstrap/security/secure.yml)"
for h in "${reachable[@]}"; do
    for svc in unattended-upgrades postfix auditd fail2ban; do
        local_tag="os"
        case "$svc" in
            postfix) local_tag=alert ;;
            auditd)  local_tag=audit ;;
            fail2ban) local_tag=detection ;;
        esac
        if ssh_ok "$h" "systemctl is-active --quiet $svc"; then
            mark ok "$h : $svc actif (couche $local_tag)"
        elif ssh_ok "$h" "systemctl list-unit-files --no-legend $svc.service | grep -q ."; then
            mark fail "$h : $svc installé mais inactif" \
                      "(cd bootstrap/security && ansible-playbook -i ../hosts.yaml secure.yml --tags $local_tag --limit $h)"
        else
            mark skip "$h : $svc non installé — opt-in : --tags $local_tag (voir IMPLICATIONS.md)"
        fi
    done
done

# ─── Couche 3 — Bootstrap Kubernetes (CRI + paquets + endpoint) ────────────
section "Bootstrap Kubernetes (cri / kubeadm / endpoint)"
for h in "${reachable[@]}"; do
    if ssh_ok "$h" 'systemctl is-active --quiet containerd'; then
        if [ "$(ssh_q "$h" 'sudo grep -c "SystemdCgroup = true" /etc/containerd/config.toml')" = "1" ]; then
            mark ok "$h : containerd + SystemdCgroup=true"
        else
            mark fail "$h : containerd actif mais SystemdCgroup pas forcé" \
                      "ansible-playbook -i bootstrap/hosts.yaml bootstrap/cri.yaml --limit $h"
        fi
    else
        mark skip "$h : containerd non installé (cri.yaml à jouer)"
    fi

    if ssh_ok "$h" 'command -v kubeadm'; then
        kver=$(ssh_q "$h" 'kubeadm version -o short')
        mark ok "$h : kubeadm $kver"
    else
        mark skip "$h : kubeadm non installé (kubeadm.yaml à jouer)"
    fi

    if ssh_ok "$h" 'grep -q cluster-api /etc/hosts'; then
        mark ok "$h : entrée /etc/hosts pour cluster-api"
    else
        mark skip "$h : pas d'entrée cluster-api (kubeadm.yaml à jouer)"
    fi

    if ssh_ok "$h" 'sudo test -f /etc/kubernetes/admin.conf'; then
        mark ok "$h : kubeadm init réalisé (admin.conf)"
    else
        mark skip "$h : kubeadm init pas encore joué"
    fi
done

# ─── Couche 4 — CNI Cilium (cluster-level) ─────────────────────────────────
section "CNI Cilium (kubectl)"
if ! kubectl_ready; then
    mark skip "kubectl indisponible (binaire absent ou cluster injoignable)"
else
    if [ "$(kubectl_q -n kube-system get deploy cilium-operator -o jsonpath='{.status.readyReplicas}')" = "1" ]; then
        mark ok "cilium-operator Ready"
    else
        mark fail "cilium-operator non Ready" "scp bootstrap/cni.sh control:/tmp && ssh control 'bash /tmp/cni.sh'"
    fi

    desired=$(kubectl_q -n kube-system get ds cilium -o jsonpath='{.status.desiredNumberScheduled}')
    ready=$(kubectl_q -n kube-system get ds cilium -o jsonpath='{.status.numberReady}')
    if [ -n "$desired" ] && [ "$desired" = "$ready" ] && [ "$desired" != "0" ]; then
        mark ok "cilium DaemonSet : ${ready}/${desired} agents Ready"
    else
        mark fail "cilium DaemonSet : ${ready:-0}/${desired:-?} agents Ready" \
                  "kubectl -n kube-system describe ds cilium"
    fi

    not_ready=$(kubectl_q get nodes --no-headers | awk '$2 != "Ready" {print $1}' | tr '\n' ' ')
    if [ -z "$not_ready" ]; then
        ready_n=$(kubectl_q get nodes --no-headers | wc -l | tr -d ' ')
        mark ok "tous les nœuds Ready (${ready_n})"
    else
        mark fail "nœuds non Ready : $not_ready" "kubectl describe node $not_ready"
    fi

    cilium_cidr=$(kubectl_q -n kube-system get cm cilium-config -o jsonpath='{.data.cluster-pool-ipv4-cidr}')
    if [ "$cilium_cidr" = "10.244.0.0/16" ]; then
        mark ok "pod CIDR Cilium = 10.244.0.0/16 (disjoint nœuds)"
    elif [ -z "$cilium_cidr" ]; then
        mark skip "pod CIDR Cilium non lisible"
    else
        mark fail "pod CIDR = $cilium_cidr (attendu 10.244.0.0/16)" \
                  "réinstaller cilium avec --set ipam.operator.clusterPoolIPv4PodCIDRList=10.244.0.0/16"
    fi
fi

# ─── Couche 5 — Rook-Ceph (cluster-level) ──────────────────────────────────
section "Rook-Ceph (kubectl)"
if ! kubectl_ready; then
    mark skip "kubectl indisponible"
else
    if [ "$(kubectl_q -n rook-ceph get deploy rook-ceph-operator -o jsonpath='{.status.readyReplicas}')" = "1" ]; then
        mark ok "rook-ceph-operator Ready"
    else
        mark fail "rook-ceph-operator non Ready" \
                  "kubectl create -f storage/ceph/crds.yaml -f storage/ceph/common.yaml -f storage/ceph/operator.yaml"
    fi

    health=$(kubectl_q -n rook-ceph get cephcluster -o jsonpath='{.items[0].status.ceph.health}')
    case "$health" in
        HEALTH_OK)
            mark ok "CephCluster HEALTH_OK"
            ;;
        HEALTH_WARN)
            mark fail "CephCluster HEALTH_WARN" \
                      "kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status"
            ;;
        HEALTH_ERR)
            mark fail "CephCluster HEALTH_ERR" \
                      "kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status"
            ;;
        *)
            mark skip "CephCluster non créé (kubectl create -f storage/ceph/cluster.yaml)"
            ;;
    esac

    osd_up=$(kubectl_q -n rook-ceph get pods -l app=rook-ceph-osd --no-headers | grep -c Running || true)
    osd_total=$(kubectl_q -n rook-ceph get pods -l app=rook-ceph-osd --no-headers | wc -l | tr -d ' ')
    if [ "$osd_total" -gt 0 ] && [ "$osd_up" = "$osd_total" ]; then
        mark ok "${osd_up}/${osd_total} OSD Running"
    elif [ "$osd_total" = "0" ]; then
        mark skip "pas encore d'OSD (CephCluster pas appliqué)"
    else
        mark fail "${osd_up}/${osd_total} OSD Running" \
                  "kubectl -n rook-ceph get pods -l app=rook-ceph-osd"
    fi
fi

# ─── Couche 6 — StorageClasses et PVC applicatives (cluster-level) ─────────
section "StorageClasses et PVC (kubectl)"
if ! kubectl_ready; then
    mark skip "kubectl indisponible"
else
    default_sc=$(kubectl_q get storageclass | awk '/\(default\)/ {print $1; exit}')
    if [ "$default_sc" = "rook-ceph-block-replicated" ]; then
        mark ok "StorageClass par défaut = rook-ceph-block-replicated"
    elif [ -z "$default_sc" ]; then
        mark fail "aucune StorageClass par défaut" \
                  "kubectl apply -f storage/ceph/storageClass/block-replicated.yaml"
    else
        mark fail "défaut = $default_sc (attendu rook-ceph-block-replicated)" \
                  "kubectl annotate sc $default_sc storageclass.kubernetes.io/is-default-class-"
    fi

    not_bound=$(kubectl_q get pvc --all-namespaces --no-headers | awk '$3 != "Bound" {print $1"/"$2}' | tr '\n' ' ')
    total_pvc=$(kubectl_q get pvc --all-namespaces --no-headers | wc -l | tr -d ' ')
    if [ "$total_pvc" = "0" ]; then
        mark skip "aucune PVC créée"
    elif [ -z "$not_bound" ]; then
        mark ok "${total_pvc} PVC Bound"
    else
        mark fail "PVC non Bound : $not_bound" "kubectl describe pvc ${not_bound%% *}"
    fi

    # PVC applicatives qui devraient être sur la classe par défaut (réplicat ×3)
    apps_on_ec=$(kubectl_q get pvc --all-namespaces -o jsonpath='{range .items[?(@.spec.storageClassName=="rook-ceph-block-ec")]}{.metadata.namespace}/{.metadata.name} {end}')
    if [ -z "$apps_on_ec" ]; then
        mark ok "aucune PVC applicative résiduelle sur rook-ceph-block-ec"
    else
        mark fail "PVC encore sur rook-ceph-block-ec : $apps_on_ec" \
                  "éditer la PVC pour passer storageClassName: rook-ceph-block-replicated (ou recréer)"
    fi
fi

# ─── Résumé ────────────────────────────────────────────────────────────────
section "Résumé"
printf "  ${G}%d ok${N}   ${R}%d drift${N}   ${D}%d non applicable${N}\n" \
    "$ok_n" "$fail_n" "$skip_n"

if [ "$fail_n" -gt 0 ]; then
    printf '\n%sProchaine étape (1er drift)%s :\n' "$Y" "$N"
    printf '  %s%s%s\n' "$C" "$next_step" "$N"
    exit 1
fi

printf '\n%sÉtat conforme%s sur la couche couverte par ce script.\n' "$G" "$N"
printf 'Couches futures à intégrer ici au fil des phases : '
printf 'Cilium, Rook-Ceph, StorageClasses, workloads.\n'
printf 'Consulter %sbootstrap/RUNBOOK.md%s pour la prochaine grande étape.\n' "$C" "$N"
