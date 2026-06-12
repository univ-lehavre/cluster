#!/usr/bin/env bash
#
# État du cluster — passe en revue chaque couche du déploiement face à l'état
# attendu et propose la prochaine étape (ou lève un drift).
#
# Usage :
#   bootstrap/state.sh                              # tous les hôtes par défaut
#   bootstrap/state.sh cp1 node1                    # subset
#   SSH_OPTS='-p 2222 -i ~/key' bootstrap/state.sh 127.0.0.1   # banc/dev
#
# Variables d'env :
#   USER_REMOTE      utilisateur SSH                (défaut: debian)
#   SSH_OPTS         options ssh additionnelles     (défaut: vide)
#   NO_COLOR=1       désactive les couleurs ANSI
#   EXPECT_CLUSTER   garde-fou de cible (ADR 0053 issue P1) — confirme quel
#                    cluster les couches kubectl auditent. Valeur attendue :
#                    l'empreinte rendue par cluster_fingerprint() (sha256/12 du
#                    CA du contexte courant, ou du server: en fallback), OU une
#                    étiquette libre (ex. `prod`, `lima`) comme confirmation
#                    consciente. ABSENTE → les couches cluster (CNI, Rook-Ceph,
#                    StorageClasses, plateforme…) refusent tout verdict ok/fail
#                    et passent en skip bruyant « cible non confirmée ». Évite
#                    d'auditer le banc en croyant auditer la prod (kubectl nu →
#                    KUBECONFIG ambiant). L'empreinte prod est une config LOCALE
#                    non versionnée (ADR 0023) — jamais codée en dur ici.
#
# Codes de sortie :
#   0 — tout est conforme
#   1 — drift détecté (au moins un check ✗) ; voir « Prochaine étape »
#   2 — aucun hôte joignable (exécuter first-access.sh d'abord)

set -euo pipefail

# Primitives SSH partagées (USER_REMOTE, SSH_OPTS, ssh_q, ssh_ok, ssh_script) —
# factorisées dans lib/ssh-report.sh (#296), sourcées comme state-classify.sh.
# shellcheck source=bootstrap/lib/ssh-report.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/ssh-report.sh"

hosts=("$@")
if [ ${#hosts[@]} -eq 0 ]; then
    # Défaut d'EXEMPLE (ADR 0023) ; surcharger via les arguments (vrais hôtes).
    hosts=(cp1 node1 node2 node3)
fi

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[34m'
    C=$'\033[36m'; D=$'\033[2m';  N=$'\033[0m'
else
    G=''; R=''; Y=''; B=''; C=''; D=''; N=''
fi

declare -i ok_n=0 fail_n=0 skip_n=0 reachable_n=0
next_step=""

# ssh_q / ssh_ok / ssh_script : voir lib/ssh-report.sh (sourcé plus haut).

kubectl_q() { kubectl "$@" 2>/dev/null; }

kubectl_ready() {
    command -v kubectl >/dev/null 2>&1 && kubectl version --request-timeout=3s >/dev/null 2>&1
}

# ─── Garde-fou de cible (ADR 0053 issue P1) ────────────────────────────────
# kubectl_q/kubectl_ready visent le KUBECONFIG AMBIANT (kubectl nu, sans
# --kubeconfig). Risque : auditer le banc en croyant auditer la prod. On exige
# donc que l'opérateur confirme la cible via EXPECT_CLUSTER, comparé à une
# empreinte stable du cluster ambiant. La comparaison pure vit dans la lib
# (classify_target_match) ; le calcul d'empreinte (qui FAIT du kubectl) ici.
_sha12() { if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi | cut -c1-12; }

# Empreinte STABLE du cluster pointé par le contexte courant : CA inline du
# cluster (champ inhérent au cluster, pas au KUBECONFIG) → sha256/12 ; fallback
# sur le server: endpoint si le CA est référencé par fichier. printf (pas echo)
# pour ne pas injecter de newline qui ferait varier l'empreinte.
cluster_fingerprint() {
    local ca server
    ca=$(kubectl config view --raw --minify \
        -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' 2>/dev/null)
    if [ -n "$ca" ]; then printf '%s' "$ca" | _sha12; return 0; fi
    server=$(kubectl config view --raw --minify \
        -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null)
    [ -n "$server" ] && printf '%s' "$server" | _sha12
    return 0
}

# Verdict du garde-fou MÉMOÏSÉ : cluster_fingerprint (donc kubectl) n'est appelé
# qu'UNE fois ; le verdict de cible n'est affiché qu'UNE fois (couche 4).
_TARGET_VERDICT=""
target_verdict() {
    [ -n "$_TARGET_VERDICT" ] || \
        _TARGET_VERDICT=$(classify_target_match "${EXPECT_CLUSTER:-}" "$(cluster_fingerprint)")
    printf '%s' "$_TARGET_VERDICT"
}

# Prédicat des couches CLUSTER : kubectl joignable ET cible confirmée (ok).
cluster_target_ready() {
    kubectl_ready || return 1
    case "$(target_verdict)" in ok\|*) return 0 ;; *) return 1 ;; esac
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

# Fonctions PURES de classification (testées par bats — test/unit/state-classify.bats).
# shellcheck source=lib/state-classify.sh disable=SC1091
. "$(dirname "${BASH_SOURCE[0]}")/lib/state-classify.sh"

# Lib PARTAGÉE du HEALTHCHECK cluster (verdicts kubectl + garde-fou de cible
# ADR 0053). Testée par test/unit/health-classify.bats.
# shellcheck source=lib/health-classify.sh disable=SC1091
. "$(dirname "${BASH_SOURCE[0]}")/lib/health-classify.sh"

# mark_classified "STATUS|message" ["remedy"]
#   Pont entre la sortie des fonctions classify_* et `mark`. Découpe le verdict
#   sur le premier '|'. La remedy (optionnelle) n'est utilisée que si fail.
mark_classified() {
    local verdict=$1 remedy=${2:-} h_prefix=${3:-}
    local status=${verdict%%|*} msg=${verdict#*|}
    mark "$status" "${h_prefix}${msg}" "$remedy"
}

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

# ─── Couche 0 — Registre Ansible (audit-log /var/log/cluster-bootstrap.log) ─
# Le rôle `audit-log` appose chaque exécution de playbook dans
# /var/log/cluster-bootstrap.log. Cette couche affiche le dernier
# enregistrement par nœud et signale les nœuds joignables mais jamais touchés
# par Ansible — drift potentiel entre OS installé et bootstrap appliqué.
section "Registre Ansible (audit-log par nœud)"
for h in "${reachable[@]}"; do
    # `|| true` car ssh_q peut renvoyer non-zero (sudo demande mdp,
    # fichier inexistant) — on veut juste une chaîne vide dans ce cas.
    last_line=$(ssh_q "$h" 'sudo -n tail -n 1 /var/log/cluster-bootstrap.log 2>/dev/null' || true)
    if [ -z "$last_line" ]; then
        mark fail "$h : aucune trace de playbook (audit-log absent)" \
                  "ansible-playbook -i bootstrap/hosts.yaml bootstrap/audit-log-baseline.yaml --limit $h"
        continue
    fi
    last_ts=$(awk '{print $1}' <<<"$last_line")
    last_play=$(awk -F'playbook=' '{print $2}' <<<"$last_line" | awk '{print $1}')
    age=$(ssh_q "$h" "
        last=\$(sudo -n tail -n 1 /var/log/cluster-bootstrap.log 2>/dev/null | awk '{print \$1}')
        if [ -n \"\$last\" ]; then
            now=\$(date -u +%s)
            le=\$(date -d \"\$last\" +%s 2>/dev/null || echo 0)
            if [ \"\$le\" -gt 0 ]; then
                echo \$(( (now - le) / 60 ))
            fi
        fi
    " || true)
    mark ok "$h : dernier playbook=${last_play:-?} à ${last_ts:-?} (il y a ${age:-?} min)"
done

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
# Lecture via `getent shadow` (audit P9 #14) plutôt que la sortie humaine de
# `chage` : le 3ᵉ champ de shadow est le nombre de JOURS depuis epoch du dernier
# changement de mot de passe — un entier directement comparable, insensible à la
# locale (le parsing de `chage -l` cassait sur le format français).
last_days=$(sudo getent shadow debian 2>/dev/null | cut -d: -f3)
# Date d'install = création de /etc/machine-id (premier boot post-install),
# convertie en jours depuis epoch.
install_epoch=$(stat -c '%Y' /etc/machine-id 2>/dev/null || echo 0)
if [ -z "$last_days" ] || ! [ "$last_days" -eq "$last_days" ] 2>/dev/null || [ "$install_epoch" -eq 0 ]; then
    echo "UNKNOWN 0"
    exit 0
fi
install_days=$(( install_epoch / 86400 ))
now_days=$(( $(date +%s) / 86400 ))
install_age_days=$(( now_days - install_days ))
diff_days=$(( last_days - install_days ))
# `chage` stocke la date au jour près (pas l'heure). Si l'install date
# du jour même (ou d'hier), un passwd fait dans la foulée donne la même
# date que machine-id → ambigu. On ne se prononce qu'à partir de
# install_age >= 2 jours.
if [ "$install_age_days" -lt 2 ]; then
    echo "AMBIGUOUS $install_age_days"
elif [ "$diff_days" -le 1 ]; then
    echo "NEVER $diff_days"
else
    echo "MOD $diff_days"
fi
REMOTE
    )
    read -r pw_status pw_days <<<"$pw_result"
    # Verdict via la fonction pure (testée par bats). La remedy reste ici car
    # elle dépend de l'hôte courant.
    mark_classified "$(classify_passwd "$pw_status" "$pw_days")" \
        "ssh $h sudo passwd debian (ou NEW_DEBIAN_PASSWORD=... bash bootstrap/first-access.sh $h)" \
        "$h : "
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
            # postfix actif SANS relayhost = couche alert PARTIELLE (#131) : les
            # alertes restent en local delivery. Drift à corriger (rejouer alert).
            if [ "$svc" = postfix ]; then
                if ssh_ok "$h" "test -n \"\$(postconf -h relayhost 2>/dev/null)\""; then
                    mark ok "$h : postfix relaie vers un smarthost (relayhost posé, #131)"
                else
                    mark fail "$h : postfix actif SANS relayhost — alertes non relayées (#131)" \
                              "(définir MAIL_SMARTHOST puis : cd bootstrap/security && ansible-playbook -i ../hosts.yaml secure.yml --tags alert --limit $h)"
                fi
            fi
        elif ssh_ok "$h" "systemctl list-unit-files --no-legend $svc.service | grep -q ."; then
            mark fail "$h : $svc installé mais inactif" \
                      "(cd bootstrap/security && ansible-playbook -i ../hosts.yaml secure.yml --tags $local_tag --limit $h)"
        else
            mark skip "$h : $svc non installé — opt-in : --tags $local_tag (voir IMPLICATIONS.md)"
        fi
    done

    # UFW (pare-feu) — opt-in `--tags ufw`, à activer APRÈS le bootstrap K8s.
    # Comme les autres couches : absent = opt-in non activé (skip) ; installé
    # mais inactif = drift (fail). En PLUS, si UFW est actif on vérifie que la
    # règle inter-nœuds (plage cluster) est présente : un UFW actif SANS cette
    # règle coupe les flux K8s/Cilium/Ceph → drift critique.
    ufw_status=$(ssh_q "$h" 'sudo ufw status 2>/dev/null | head -1')
    if printf '%s' "$ufw_status" | grep -q "Status: active"; then
        if ssh_ok "$h" "sudo ufw status | grep -Eq '10\\.67\\.|ALLOW.*Anywhere.*30000:32767|${h}'"; then
            mark ok "$h : ufw actif avec règles cluster (couche ufw)"
        else
            mark fail "$h : ufw actif SANS règle inter-nœuds — risque de coupure cluster" \
                      "(cd bootstrap/security && ansible-playbook -i ../hosts.yaml secure.yml --tags ufw --limit $h)"
        fi
    elif ssh_ok "$h" "command -v ufw >/dev/null"; then
        mark fail "$h : ufw installé mais inactif" \
                  "(cd bootstrap/security && ansible-playbook -i ../hosts.yaml secure.yml --tags ufw --limit $h)"
    else
        mark skip "$h : ufw non installé — opt-in : --tags ufw APRÈS bootstrap K8s (voir IMPLICATIONS.md)"
    fi

    # SMART (smartmontools/smartd) — opt-in `--tags smart`. Surveille les disques,
    # dont le NVMe block.db (SPOF par nœud, ADR 0008). Service Debian =
    # `smartmontools` (`smartd` en est un alias). Si actif, on lit en plus la
    # santé SMART du NVMe (`smartctl -H`) : PASSED → ok, sinon → drift critique.
    if ssh_ok "$h" "systemctl is-active --quiet smartmontools"; then
        nvme_health=$(ssh_q "$h" "sudo smartctl -H /dev/${CEPH_BLOCK_DEVICE:-nvme1n1} 2>/dev/null | awk -F: '/overall-health|SMART Health/{print \$2}' | xargs")
        if printf '%s' "$nvme_health" | grep -qi "PASSED\|OK"; then
            mark ok "$h : smartd actif, /dev/${CEPH_BLOCK_DEVICE:-nvme1n1} SMART = ${nvme_health}"
        elif [ -n "$nvme_health" ]; then
            mark fail "$h : smartd actif mais /dev/${CEPH_BLOCK_DEVICE:-nvme1n1} SMART = ${nvme_health}" \
                      "drainer $h, remplacer le NVMe block.db, laisser Rook recréer les OSDs (ADR 0008)"
        else
            mark ok "$h : smartd actif (santé NVMe non lisible — banc sans NVMe ?)"
        fi
    elif ssh_ok "$h" "test -x /usr/sbin/smartctl || command -v smartctl >/dev/null"; then
        # `smartctl` est dans /usr/sbin (hors PATH d'une session SSH non
        # interactive) → on teste le chemin absolu en plus de `command -v`.
        # Installé mais inactif : sur un banc à disques virtuels (sans SMART),
        # smartd refuse de démarrer (exit 17) — c'est attendu, pas un drift.
        # En prod (disques réels), un smartd inactif est en revanche anormal.
        mark skip "$h : smartmontools installé, smartd inactif (normal si disques sans SMART, ex. banc ; à vérifier en prod)"
    else
        mark skip "$h : smartd non installé — opt-in : --tags smart (surveillance SMART, voir IMPLICATIONS.md)"
    fi
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

# ─── Couche 3b — Disques bruts prêts pour Ceph ─────────────────────────────
# Pré-requis Rook (cf. storage/ceph/RUNBOOK.md) : les HDD SAS et le NVMe
# block.db (`nvme1n1`) doivent être BRUTS (aucune table de partitions, aucun
# FS, aucun reste d'OSD précédent) ; `/var/lib/rook` doit être absent.
# Variables d'env :
#   CEPH_MIN_HDD       nombre minimum de HDD bruts (défaut: 1, prod: 12)
#   CEPH_BLOCK_DEVICE  nom du NVMe block.db (défaut: nvme1n1, banc: vde)
#   CEPH_HDD_GLOB      glob /sys/block des disques data HDD (défaut prod:
#                      '/sys/block/sd*'). Sur le banc Vagrant (contrôleur
#                      VirtIO, aucun sd*), surcharger en '/sys/block/vd[b-z]'
#                      — JAMAIS vd[a-z] qui inclurait vda, le disque système.
CEPH_MIN_HDD=${CEPH_MIN_HDD:-1}
CEPH_BLOCK_DEVICE=${CEPH_BLOCK_DEVICE:-nvme1n1}
CEPH_HDD_GLOB=${CEPH_HDD_GLOB:-/sys/block/sd*}
section "Disques bruts Ceph (≥ ${CEPH_MIN_HDD} HDD, /dev/${CEPH_BLOCK_DEVICE}, /var/lib/rook propre)"
for h in "${reachable[@]}"; do
    # On délègue tout l'examen au shell distant : c'est lui qui voit /sys.
    disk_report=$(ssh_script "$h" <<REMOTE
set -u

# 1) HDD bruts (pas le disque OS) : disques data sans partition ni FS.
#    La variable ${CEPH_HDD_GLOB} (défaut prod /sys/block/sd*) est substituée
#    localement dans ce heredoc, mais le GLOB lui-même (ex. vd[b-z]) reste
#    littéral et n'est expansé que par le shell DISTANT — c'est lui qui voit
#    /sys. On considère "brut" si aucune partition ET aucune signature wipefs.
hdd_total=0
hdd_dirty=0
hdd_clean=0
for d in ${CEPH_HDD_GLOB}; do
    [ -e "\$d" ] || continue
    name=\$(basename "\$d")
    hdd_total=\$((hdd_total + 1))
    parts=\$(ls "\$d" | grep -E "^\${name}[0-9]+\$" | wc -l | tr -d ' ')
    sig=\$(wipefs -n "/dev/\$name" 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')
    if [ "\$parts" -eq 0 ] && [ "\$sig" -eq 0 ]; then
        hdd_clean=\$((hdd_clean + 1))
    else
        hdd_dirty=\$((hdd_dirty + 1))
    fi
done

# 2) NVMe block.db : présent ? brut ?
nvme_state=absent
if [ -e "/sys/block/${CEPH_BLOCK_DEVICE}" ]; then
    nparts=\$(ls /sys/block/${CEPH_BLOCK_DEVICE} | grep -E '^${CEPH_BLOCK_DEVICE}p?[0-9]+\$' | wc -l | tr -d ' ')
    nsig=\$(wipefs -n /dev/${CEPH_BLOCK_DEVICE} 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')
    if [ "\$nparts" -eq 0 ] && [ "\$nsig" -eq 0 ]; then
        nvme_state=clean
    else
        nvme_state=dirty
    fi
fi

# 3) /var/lib/rook propre ?
if [ -d /var/lib/rook ] && [ -n "\$(ls -A /var/lib/rook 2>/dev/null)" ]; then
    rook_state=dirty
else
    rook_state=clean
fi

echo "\${hdd_total} \${hdd_clean} \${hdd_dirty} \${nvme_state} \${rook_state}"
REMOTE
    )
    read -r hdd_total hdd_clean hdd_dirty nvme_state rook_state <<<"$disk_report"
    hdd_total=${hdd_total:-?}
    hdd_clean=${hdd_clean:-0}
    hdd_dirty=${hdd_dirty:-0}
    nvme_state=${nvme_state:-?}
    rook_state=${rook_state:-?}

    # HDD bruts — verdict via fonction pure (testée par bats).
    mark_classified "$(classify_hdd "$hdd_total" "$hdd_clean" "$hdd_dirty" "$CEPH_MIN_HDD")" \
        "bash storage/ceph/cleanup.sh (ou wipefs -a /dev/sdX) sur $h ; sinon vérifier l'inventaire matériel" \
        "$h : "

    # NVMe block.db — verdict via fonction pure.
    mark_classified "$(classify_device_state "$nvme_state" "/dev/${CEPH_BLOCK_DEVICE} (block.db)")" \
        "blkdiscard /dev/${CEPH_BLOCK_DEVICE} (ou bash storage/ceph/cleanup.sh)" \
        "$h : "

    # /var/lib/rook — verdict via fonction pure.
    mark_classified "$(classify_device_state "$rook_state" "/var/lib/rook")" \
        "sudo rm -rf /var/lib/rook sur $h (pré-requis avant Phase 3)" \
        "$h : "
done

# ─── Couche 4 — CNI Cilium (cluster-level) ─────────────────────────────────
section "CNI Cilium (kubectl)"
if ! kubectl_ready; then
    mark skip "kubectl indisponible (binaire absent ou cluster injoignable)"
else
    # Garde-fou de cible (ADR 0053 P1) — affiché UNE seule fois, ici en tête de la
    # 1re couche kubectl. ok → on audite ; skip bruyant → toutes les couches
    # cluster suivantes passeront en skip (cible non confirmée / divergente).
    ctx=$(kubectl config current-context 2>/dev/null || echo '?')
    mark_classified "$(target_verdict)" \
        "export EXPECT_CLUSTER=<empreinte|prod|lima> (cf. en-tête state.sh)" \
        "contexte ambiant « ${ctx} » — "

    if cluster_target_ready; then
        op_ready=$(kubectl_q -n kube-system get deploy cilium-operator -o jsonpath='{.status.readyReplicas}')
        mark_classified "$(classify_cilium_operator "$op_ready")" \
            "scp bootstrap/cni.sh control:/tmp && ssh control 'bash /tmp/cni.sh'"

        desired=$(kubectl_q -n kube-system get ds cilium -o jsonpath='{.status.desiredNumberScheduled}')
        ready=$(kubectl_q -n kube-system get ds cilium -o jsonpath='{.status.numberReady}')
        mark_classified "$(classify_cilium_daemonset "$ready" "$desired")" \
            "kubectl -n kube-system describe ds cilium"

        not_ready=$(kubectl_q get nodes --no-headers | awk '$2 != "Ready" {print $1}' | tr '\n' ' ')
        ready_n=$(kubectl_q get nodes --no-headers | wc -l | tr -d ' ')
        mark_classified "$(classify_nodes_ready "$not_ready" "$ready_n")" \
            "kubectl describe node $not_ready"

        cilium_cidr=$(kubectl_q -n kube-system get cm cilium-config -o jsonpath='{.data.cluster-pool-ipv4-cidr}')
        mark_classified "$(classify_pod_cidr "$cilium_cidr")" \
            "réinstaller cilium avec --set ipam.operator.clusterPoolIPv4PodCIDRList=10.244.0.0/16"
    fi
fi

# ─── Couche 5 — Rook-Ceph (cluster-level) ──────────────────────────────────
section "Rook-Ceph (kubectl)"
if ! cluster_target_ready; then
    mark skip "Rook-Ceph : non audité (garde-fou de cible / kubectl indisponible)"
else
    op_ready=$(kubectl_q -n rook-ceph get deploy rook-ceph-operator -o jsonpath='{.status.readyReplicas}')
    mark_classified "$(classify_ceph_operator "$op_ready")" \
        "kubectl create -f storage/ceph/crds.yaml -f storage/ceph/common.yaml -f storage/ceph/operator.yaml"

    health=$(kubectl_q -n rook-ceph get cephcluster -o jsonpath='{.items[0].status.ceph.health}')
    mark_classified "$(classify_ceph_health "$health")" \
        "kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status"

    osd_up=$(kubectl_q -n rook-ceph get pods -l app=rook-ceph-osd --no-headers | grep -c Running || true)
    osd_total=$(kubectl_q -n rook-ceph get pods -l app=rook-ceph-osd --no-headers | wc -l | tr -d ' ')
    mark_classified "$(classify_ceph_osd "$osd_up" "$osd_total")" \
        "kubectl -n rook-ceph get pods -l app=rook-ceph-osd"
fi

# ─── Couche 6 — StorageClasses et PVC applicatives (cluster-level) ─────────
section "StorageClasses et PVC (kubectl)"
if ! cluster_target_ready; then
    mark skip "StorageClasses/PVC : non audité (garde-fou de cible / kubectl indisponible)"
else
    default_sc=$(kubectl_q get storageclass | awk '/\(default\)/ {print $1; exit}')
    mark_classified "$(classify_sc_default "$default_sc")" \
        "kubectl apply -f storage/ceph/storageClass/block-replicated.yaml"

    not_bound=$(kubectl_q get pvc --all-namespaces --no-headers | awk '$3 != "Bound" {print $1"/"$2}' | tr '\n' ' ')
    total_pvc=$(kubectl_q get pvc --all-namespaces --no-headers | wc -l | tr -d ' ')
    mark_classified "$(classify_pvc_bound "$not_bound" "$total_pvc")" \
        "kubectl describe pvc ${not_bound%% *}"

    # PVC applicatives qui devraient être sur la classe par défaut (réplicat ×3)
    apps_on_ec=$(kubectl_q get pvc --all-namespaces -o jsonpath='{range .items[?(@.spec.storageClassName=="rook-ceph-block-ec")]}{.metadata.namespace}/{.metadata.name} {end}')
    mark_classified "$(classify_pvc_no_ec "$apps_on_ec")" \
        "éditer la PVC pour passer storageClassName: rook-ceph-block-replicated (ou recréer)"
fi

# ─── Couche 7 — Plateforme (registry + dashboard) ──────────────────────────
section "Plateforme (registry + Kubernetes Dashboard)"
if ! cluster_target_ready; then
    mark skip "Plateforme : non audité (garde-fou de cible / kubectl indisponible)"
else
    # ── Container registry ───────────────────────────────────────────────
    if kubectl_q get ns registry >/dev/null 2>&1; then
        registry_ready=$(kubectl_q -n registry get deploy registry -o jsonpath='{.status.readyReplicas}')
        registry_desired=$(kubectl_q -n registry get deploy registry -o jsonpath='{.spec.replicas}')
        if [ -n "$registry_ready" ] && [ "$registry_ready" = "$registry_desired" ] && [ "$registry_ready" != "0" ]; then
            mark ok "registry : ${registry_ready}/${registry_desired} Ready"
        else
            mark fail "registry : ${registry_ready:-0}/${registry_desired:-?} Ready" \
                      "kubectl -n registry get pods,events"
        fi

        registry_pvc=$(kubectl_q -n registry get pvc registry-pvc -o jsonpath='{.status.phase}')
        if [ "$registry_pvc" = "Bound" ]; then
            mark ok "registry : PVC registry-pvc Bound"
        else
            mark fail "registry : PVC registry-pvc = ${registry_pvc:-absente}" \
                      "kubectl apply -f platform/container-registry/persistent-volume-claim.yaml"
        fi

        if kubectl_q -n registry get cronjob registry-gc >/dev/null 2>&1; then
            registry_gc_suspended=$(kubectl_q -n registry get cronjob registry-gc -o jsonpath='{.spec.suspend}')
            if [ "$registry_gc_suspended" = "true" ]; then
                mark ok "registry : CronJob registry-gc présent (suspended — validation banc avant activation)"
            else
                mark ok "registry : CronJob registry-gc présent (actif)"
            fi
        else
            mark skip "registry : CronJob registry-gc absent (kubectl apply -f platform/container-registry/garbage-collect-cronjob.yaml)"
        fi
    else
        mark skip "registry : namespace absent (Phase 5 à dérouler)"
    fi

    # ── Kubernetes Dashboard ─────────────────────────────────────────────
    if kubectl_q get ns kubernetes-dashboard >/dev/null 2>&1; then
        dash_not_ready=$(kubectl_q -n kubernetes-dashboard get pods --no-headers 2>/dev/null \
            | awk '$3 != "Running" && $3 != "Completed" {print $1}' | tr '\n' ' ')
        dash_total=$(kubectl_q -n kubernetes-dashboard get pods --no-headers 2>/dev/null | wc -l | tr -d ' ')
        if [ "$dash_total" = "0" ]; then
            mark skip "dashboard : aucun pod (helm install via platform/k8s-dashboard/manage.sh)"
        elif [ -z "$dash_not_ready" ]; then
            mark ok "dashboard : ${dash_total} pods Running"
        else
            mark fail "dashboard : pods non Running : $dash_not_ready" \
                      "kubectl -n kubernetes-dashboard describe pods"
        fi

        if kubectl_q -n kubernetes-dashboard get sa admin-user >/dev/null 2>&1; then
            mark ok "dashboard : ServiceAccount admin-user présent"
        else
            mark fail "dashboard : ServiceAccount admin-user absent" \
                      "kubectl apply -f platform/k8s-dashboard/service-account.yaml"
        fi

        if kubectl_q get clusterrolebinding admin-user >/dev/null 2>&1; then
            mark ok "dashboard : ClusterRoleBinding admin-user (cluster-admin) en place"
        else
            mark fail "dashboard : ClusterRoleBinding admin-user absent" \
                      "kubectl apply -f platform/k8s-dashboard/cluster-role-binding.yaml"
        fi

        # H1 — preuve observable que la migration vers les tokens éphémères
        # est effective : le Secret legacy `admin-user` (type service-account-token)
        # ne doit PAS exister. Cf. ADR 0010.
        if kubectl_q -n kubernetes-dashboard get secret admin-user >/dev/null 2>&1; then
            mark fail "dashboard : Secret legacy admin-user présent (anti-pattern K8s 1.24+)" \
                      "kubectl -n kubernetes-dashboard delete secret admin-user (cf. ADR 0010)"
        else
            mark ok "dashboard : aucun Secret legacy admin-user (tokens éphémères via credentials.sh)"
        fi
    else
        mark skip "dashboard : namespace absent (helm install via platform/k8s-dashboard/manage.sh)"
    fi
fi

# ─── TLS de bordure (cert-manager, CA interne — ADR 0021) ──────────────────
# cert-manager émet/renouvelle le cert du listener HTTPS du Gateway via une CA
# INTERNE (pas ACME, cluster non exposé). On vérifie le déploiement et que la
# chaîne d'émetteurs est prête. Skip propre tant que l'addon n'est pas déployé.
section "TLS de bordure (cert-manager)"
if ! cluster_target_ready; then
    mark skip "non audité (garde-fou de cible / kubectl indisponible)"
elif ! kubectl_q get ns cert-manager >/dev/null 2>&1; then
    mark skip "cert-manager : namespace absent (kubectl apply -f platform/cert-manager/cert-manager.yaml)"
else
    cm_not_ready=$(kubectl_q -n cert-manager get pods --no-headers 2>/dev/null \
        | awk '$3 != "Running" && $3 != "Completed" {print $1}' | tr '\n' ' ')
    cm_total=$(kubectl_q -n cert-manager get pods --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [ "$cm_total" = "0" ]; then
        mark skip "cert-manager : aucun pod (kubectl apply -f platform/cert-manager/cert-manager.yaml)"
    elif [ -z "$cm_not_ready" ]; then
        mark ok "cert-manager : ${cm_total} pods Running"
    else
        mark fail "cert-manager : pods non Running : $cm_not_ready" \
                  "kubectl -n cert-manager describe pods"
    fi

    # Émetteur CA interne prêt (Ready=True) — la racine doit être émise.
    if kubectl_q get clusterissuer internal-ca >/dev/null 2>&1; then
        ca_ready=$(kubectl_q get clusterissuer internal-ca \
            -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
        if [ "$ca_ready" = "True" ]; then
            mark ok "cert-manager : ClusterIssuer internal-ca Ready (CA interne)"
        else
            mark fail "cert-manager : ClusterIssuer internal-ca non Ready (${ca_ready:-?})" \
                      "kubectl describe clusterissuer internal-ca ; vérifier le Secret root-ca-secret"
        fi
    else
        mark skip "cert-manager : ClusterIssuer internal-ca absent (kubectl apply -f platform/cert-manager/issuers.yaml)"
    fi
fi

# ─── Observabilité (kube-prometheus-stack + Loki — ADR 0016 palier 2) ──────
# Monitoring runtime : Prometheus/Alertmanager/Grafana + Loki (logs). Skip propre
# tant que l'addon n'est pas déployé.
section "Observabilité (monitoring — ADR 0016 palier 2)"
if ! cluster_target_ready; then
    mark skip "non audité (garde-fou de cible / kubectl indisponible)"
elif ! kubectl_q get ns monitoring >/dev/null 2>&1; then
    mark skip "monitoring : namespace absent (kubectl apply -f platform/kube-prometheus-stack/)"
else
    mon_not_ready=$(kubectl_q -n monitoring get pods --no-headers 2>/dev/null \
        | awk '$3 != "Running" && $3 != "Completed" {print $1}' | tr '\n' ' ')
    mon_total=$(kubectl_q -n monitoring get pods --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [ "$mon_total" = "0" ]; then
        mark skip "monitoring : aucun pod (kubectl apply -f platform/kube-prometheus-stack/)"
    elif [ -z "$mon_not_ready" ]; then
        mark ok "monitoring : ${mon_total} pods Running (Prometheus/Grafana/Alertmanager + exporters)"
    else
        mark fail "monitoring : pods non Running : $mon_not_ready" \
                  "kubectl -n monitoring get pods"
    fi

    # Prometheus CR Healthy (operator)
    if kubectl_q -n monitoring get prometheus >/dev/null 2>&1; then
        prom_av=$(kubectl_q -n monitoring get prometheus -o jsonpath='{.items[0].status.availableReplicas}' 2>/dev/null)
        if [ -n "$prom_av" ] && [ "$prom_av" -ge 1 ] 2>/dev/null; then
            mark ok "monitoring : Prometheus disponible (${prom_av} replica)"
        else
            mark fail "monitoring : Prometheus CR non disponible" "kubectl -n monitoring get prometheus"
        fi
    fi

    # Loki (logs) — StatefulSet
    if kubectl_q -n monitoring get statefulset loki >/dev/null 2>&1; then
        loki_rd=$(kubectl_q -n monitoring get statefulset loki -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
        if [ "${loki_rd:-0}" -ge 1 ] 2>/dev/null; then
            mark ok "monitoring : Loki Ready (agrégation des logs)"
        else
            mark fail "monitoring : Loki non Ready" "kubectl -n monitoring get statefulset loki"
        fi
    else
        mark skip "monitoring : Loki absent (kubectl apply -f platform/loki/)"
    fi
fi

# ─── PostgreSQL managé (CloudNativePG + pgvector — ADR 0024) ────────────────
# Postgres HA managé par CNPG, deux bases (event log Dagster + index pgvector),
# sauvegardes vers S3 (plugin Barman). Skip propre tant que l'addon est absent.
section "PostgreSQL managé (CloudNativePG — ADR 0024)"
if ! cluster_target_ready; then
    mark skip "non audité (garde-fou de cible / kubectl indisponible)"
elif ! kubectl_q get ns cnpg-system >/dev/null 2>&1; then
    mark skip "CNPG : operator absent (kubectl apply --server-side -f platform/cloudnative-pg/operator.yaml)"
else
    # Operator Ready
    op_rd=$(kubectl_q -n cnpg-system get deploy cnpg-controller-manager -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
    if [ "${op_rd:-0}" -ge 1 ] 2>/dev/null; then
        mark ok "CNPG : operator Ready"
    else
        mark fail "CNPG : operator non Ready" "kubectl -n cnpg-system get deploy cnpg-controller-manager"
    fi

    # Cluster pg Healthy
    if kubectl_q -n postgres get cluster pg >/dev/null 2>&1; then
        cl_ready=$(kubectl_q -n postgres get cluster pg -o jsonpath='{.status.readyInstances}' 2>/dev/null)
        cl_inst=$(kubectl_q -n postgres get cluster pg -o jsonpath='{.spec.instances}' 2>/dev/null)
        cl_phase=$(kubectl_q -n postgres get cluster pg -o jsonpath='{.status.phase}' 2>/dev/null)
        if [ "${cl_ready:-0}" = "${cl_inst:-X}" ] && [ -n "$cl_ready" ]; then
            mark ok "CNPG : Cluster pg Healthy (${cl_ready}/${cl_inst} instances)"
        else
            mark fail "CNPG : Cluster pg non Healthy (${cl_ready:-0}/${cl_inst:-?} — ${cl_phase:-?})" \
                      "kubectl -n postgres get cluster pg"
        fi

        # Archivage continu vers S3 (sauvegardes)
        arch=$(kubectl_q -n postgres get cluster pg \
            -o jsonpath='{.status.conditions[?(@.type=="ContinuousArchiving")].status}' 2>/dev/null)
        if [ "$arch" = "True" ]; then
            mark ok "CNPG : archivage continu (WAL) vers S3 actif"
        else
            mark skip "CNPG : archivage continu non actif (sauvegardes S3 non configurées ?)"
        fi

        # Extension pgvector sur la base d'index
        pgv=$(kubectl_q -n postgres get database pgvector \
            -o jsonpath='{.status.extensions[?(@.name=="vector")].applied}' 2>/dev/null)
        if [ "$pgv" = "true" ]; then
            mark ok "CNPG : extension pgvector (vector) appliquée"
        else
            mark skip "CNPG : extension pgvector non appliquée (feature gate ImageVolume requis — ADR 0006)"
        fi
    else
        mark skip "CNPG : Cluster pg absent (kubectl apply -f platform/cloudnative-pg/cluster.yaml)"
    fi
fi

# ─── Orchestration (Dagster — ADR 0026) ────────────────────────────────────
# Orchestrateur DataOps : webserver + daemon, event log dans CloudNativePG.
# Skip propre tant que l'addon n'est pas déployé.
section "Orchestration (Dagster — ADR 0026)"
if ! cluster_target_ready; then
    mark skip "non audité (garde-fou de cible / kubectl indisponible)"
elif ! kubectl_q get ns dagster >/dev/null 2>&1; then
    mark skip "Dagster : namespace absent (kubectl apply -f platform/dagster/)"
else
    # Webserver Ready
    web_rd=$(kubectl_q -n dagster get deploy dagster-dagster-webserver -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
    if [ "${web_rd:-0}" -ge 1 ] 2>/dev/null; then
        mark ok "Dagster : webserver Ready"
    else
        mark fail "Dagster : webserver non Ready" "kubectl -n dagster get deploy dagster-dagster-webserver"
    fi

    # Daemon Ready
    dmn_rd=$(kubectl_q -n dagster get deploy dagster-daemon -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
    if [ "${dmn_rd:-0}" -ge 1 ] 2>/dev/null; then
        mark ok "Dagster : daemon Ready (schedules/sensors/run queue)"
    else
        mark fail "Dagster : daemon non Ready" "kubectl -n dagster get deploy dagster-daemon"
    fi
fi

# ─── Orchestration OpenLineage (Marquez — ADR 0028) ────────────────────────
# Store de lineage : API Marquez + UI web, store dans CloudNativePG (base marquez,
# migrations Flyway). Skip propre tant que l'addon n'est pas déployé.
section "Orchestration OpenLineage (Marquez — ADR 0028)"
if ! cluster_target_ready; then
    mark skip "non audité (garde-fou de cible / kubectl indisponible)"
elif ! kubectl_q get ns marquez >/dev/null 2>&1; then
    mark skip "Marquez : namespace absent (kubectl apply -f platform/marquez/)"
else
    # API Ready
    api_rd=$(kubectl_q -n marquez get deploy marquez -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
    if [ "${api_rd:-0}" -ge 1 ] 2>/dev/null; then
        mark ok "Marquez : API Ready (lineage OpenLineage, store CNPG)"
    else
        mark fail "Marquez : API non Ready" "kubectl -n marquez get deploy marquez"
    fi

    # UI web Ready
    web_rd=$(kubectl_q -n marquez get deploy marquez-web -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
    if [ "${web_rd:-0}" -ge 1 ] 2>/dev/null; then
        mark ok "Marquez : UI web Ready"
    else
        mark fail "Marquez : UI web non Ready" "kubectl -n marquez get deploy marquez-web"
    fi
fi

# ─── Couche 7b — Exposition réseau (audit P6 #25 / #06) ────────────────────
# Tous les Services applicatifs ont été passés en ClusterIP (#25). Un Service
# de type NodePort ou LoadBalancer expose un port au-delà du cluster → ici,
# c'est un DRIFT (régression de #25 ou exposition non tracée). Exceptions
# TRACÉES :
#   - `kubernetes-dashboard` (le chart Helm peut légitimement varier) ;
#   - les Service LoadBalancer créés par un Gateway de bordure Cilium (label
#     `gateway.networking.k8s.io/gateway-name`) : c'est le point d'entrée unique
#     de l'exposition tout-Cilium (ADR 0020). Le principe #25 reste : services
#     applicatifs en ClusterIP, exposition SEULEMENT via la bordure Gateway.
section "Exposition réseau (Services NodePort / LoadBalancer)"
if ! cluster_target_ready; then
    mark skip "non audité (garde-fou de cible / kubectl indisponible)"
else
    # Allowlist : `ns/nom` des Service portés par un Gateway (bordure ADR 0020).
    gw_svcs=$(kubectl_q get svc -A -l gateway.networking.k8s.io/gateway-name \
        -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' \
        2>/dev/null || true)
    exposed=$(kubectl_q get svc -A \
        -o jsonpath='{range .items[?(@.spec.type=="NodePort")]}{.metadata.namespace}/{.metadata.name} (NodePort){"\n"}{end}{range .items[?(@.spec.type=="LoadBalancer")]}{.metadata.namespace}/{.metadata.name} (LoadBalancer){"\n"}{end}' \
        2>/dev/null | grep -v '^kubernetes-dashboard/' | grep -v '^$' || true)
    # Retirer les Service de bordure Gateway (exception tracée, ADR 0020).
    if [ -n "$gw_svcs" ]; then
        while IFS= read -r gw; do
            [ -n "$gw" ] || continue
            exposed=$(printf '%s\n' "$exposed" | grep -v "^${gw} " || true)
        done <<<"$gw_svcs"
    fi
    exposed=$(printf '%s' "$exposed" | grep -v '^$' || true)
    if [ -z "$exposed" ]; then
        mark ok "aucun Service NodePort/LoadBalancer hors cluster (hors bordure Gateway tracée)"
    else
        while IFS= read -r svc; do
            [ -n "$svc" ] || continue
            mark fail "Service exposé hors cluster : $svc" \
                      "repasser ce Service en ClusterIP (cf. ADR 0003 / audit P6 #25) ou tracer l'exposition"
        done <<<"$exposed"
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

printf '\n%sÉtat conforme%s sur toutes les couches couvertes par ce script.\n' "$G" "$N"
printf 'Consulter %sbootstrap/RUNBOOK.md%s pour la prochaine grande étape.\n' "$C" "$N"
