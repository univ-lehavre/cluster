#!/usr/bin/env bash
#
# Scénario 09 — Restauration etcd : prouve qu'un snapshot etcd est
# RESTAURABLE (un backup non restauré n'est pas un backup). Exerce la
# procédure du RUNBOOK (bootstrap/RUNBOOK.md « Restauration etcd »).
#
# Principe (témoin) :
#   1. Créer un ConfigMap témoin unique dans le cluster.
#   2. Prendre un snapshot etcd (le témoin est dedans).
#   3. SUPPRIMER le témoin (l'état actuel d'etcd ne le contient plus).
#   4. Restaurer le snapshot sur le control plane (etcdctl snapshot restore
#      + remplacement du data-dir + restart kubelet).
#   5. Vérifier que le témoin RÉAPPARAÎT → l'état d'etcd a bien été rechargé
#      depuis le snapshot. C'est la preuve de restaurabilité.
#
# IMPORTANT — pas de vagrant halt/up : la procédure tourne *sur* le control
# plane via SSH (stop kubelet → restore → start kubelet). On n'exerce donc
# PAS le reboot de VM, qui sur ce banc bute sur des artefacts Vagrant/arm64
# (route ClusterIP perdue, clock skew, vboxsf) sans valeur prod. Cf.
# test/RESULTS.md et test/scenarios/README.md (note 03/04).
#
# Variables :
#   CP_IP        — IP du control plane (défaut: 192.168.67.11, banc)
#   SSH_KEY      — clé SSH (défaut: clé insecure Vagrant)
#   KEEP=1       — ne pas supprimer le ConfigMap témoin en fin
#
# Sortie : `0` si le témoin réapparaît après restore, `1` sinon.
set -euo pipefail

CP_IP=${CP_IP:-192.168.67.11}
CP_PORT=${CP_PORT:-22} # 22 en prod/multi-node IP privée ; 2222 sur single-node (NAT)
SSH_KEY=${SSH_KEY:-${HOME}/.vagrant.d/insecure_private_keys/vagrant.key.ed25519}
KEEP=${KEEP:-0}
NS=default
WITNESS="etcd-restore-witness"
WITNESS_KEY="proof"

SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
ok() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
die() {
    printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2
    exit 1
}
cp_ssh() { ssh "${SSH_OPTS[@]}" -p "${CP_PORT}" -i "${SSH_KEY}" "debian@${CP_IP}" "$@"; }

cleanup() {
    [ "$KEEP" = "1" ] && {
        log "KEEP=1 — témoin conservé"
        return 0
    }
    kubectl -n "$NS" delete configmap "$WITNESS" --ignore-not-found > /dev/null 2>&1 || true
}
trap cleanup EXIT

# ─── 1. Témoin unique ─────────────────────────────────────────────────────
# Valeur datée (epoch distant) pour qu'elle soit non ambiguë et traçable.
WITNESS_VAL="restored-$(cp_ssh 'date +%s')"
log "Créer le ConfigMap témoin ${NS}/${WITNESS} (${WITNESS_KEY}=${WITNESS_VAL})"
kubectl -n "$NS" create configmap "$WITNESS" \
    --from-literal="${WITNESS_KEY}=${WITNESS_VAL}" \
    --dry-run=client -o yaml | kubectl apply -f - > /dev/null
kubectl -n "$NS" get configmap "$WITNESS" > /dev/null || die "témoin non créé"
ok "témoin présent"

# ─── 2. Snapshot etcd (via le script de prod) ─────────────────────────────
log "Snapshot etcd (etcd-snapshot.sh, le témoin est capturé dedans)"
cp_ssh 'sudo /usr/local/sbin/etcd-snapshot.sh' || die "snapshot etcd échoué"
# /var/lib/etcd-backups est root:root 0700 → le `ls` doit tourner sous root
# (sinon Permission denied → substitution vide → faux « aucun snapshot »,
# même piège que le drift #15 du gate Phase 6 de run-phases.sh).
SNAP=$(cp_ssh "sudo sh -c 'ls -1t /var/lib/etcd-backups/etcd-*.db 2>/dev/null | head -1'")
[ -n "$SNAP" ] || die "aucun snapshot produit"
ok "snapshot : ${SNAP}"

# ─── 3. Supprimer le témoin (l'état courant d'etcd ne le contient plus) ───
log "Supprimer le témoin (pour prouver qu'il revient PAR le restore)"
kubectl -n "$NS" delete configmap "$WITNESS" > /dev/null
if kubectl -n "$NS" get configmap "$WITNESS" > /dev/null 2>&1; then
    die "témoin toujours présent après delete"
fi
ok "témoin supprimé"

# ─── 4. Restaurer le snapshot (procédure RUNBOOK, sur le control plane) ───
log "Restauration etcd sur ${CP_IP} (stop kubelet → restore → start kubelet)"
cp_ssh "sudo cp '${SNAP}' /tmp/etcd-snapshot.db"
# Tout le bloc en root distant. La restauration utilise l'etcdctl de l'HÔTE
# (etcd est arrêté → pas de `crictl exec` dans le conteneur comme au snapshot).
# `etcd-client` est normalement posé par le rôle etcd-backup ; s'il manque, on
# l'installe en AVERTISSANT (signe que le rôle n'a pas tourné sur ce nœud).
cp_ssh 'sudo bash -s' <<'REMOTE' || die "procédure de restauration échouée"
set -euo pipefail
if ! command -v etcdctl >/dev/null 2>&1; then
  echo "WARN: etcdctl absent — le rôle etcd-backup aurait dû poser etcd-client. Installation de secours."
  apt-get update -qq && apt-get install -y -qq etcd-client
fi
systemctl stop kubelet
crictl ps -q 2>/dev/null | xargs -r crictl stop >/dev/null 2>&1 || true
crictl ps -q 2>/dev/null | xargs -r crictl rm >/dev/null 2>&1 || true
rm -rf /var/lib/etcd-restore
ETCDCTL_API=3 etcdctl snapshot restore /tmp/etcd-snapshot.db \
  --name "$(hostname)" \
  --initial-cluster "$(hostname)=https://$(hostname -I | awk '{print $1}'):2380" \
  --initial-advertise-peer-urls "https://$(hostname -I | awk '{print $1}'):2380" \
  --data-dir /var/lib/etcd-restore
mv /var/lib/etcd "/var/lib/etcd.before-restore-$(date +%s)"
mv /var/lib/etcd-restore /var/lib/etcd
systemctl start kubelet
REMOTE
ok "restauration appliquée"

# ─── 5. Vérifier que le témoin réapparaît ─────────────────────────────────
log "Attendre le retour de l'API + du témoin (max 5 min)"
restored=""
for _ in $(seq 1 30); do
    if val=$(kubectl -n "$NS" get configmap "$WITNESS" \
        -o jsonpath="{.data.${WITNESS_KEY}}" 2> /dev/null) && [ -n "$val" ]; then
        restored="$val"
        break
    fi
    sleep 10
done

[ -n "$restored" ] || die "témoin NON revenu après restore — snapshot non restaurable ?"
[ "$restored" = "$WITNESS_VAL" ] \
    || die "témoin revenu mais valeur inattendue ('${restored}' ≠ '${WITNESS_VAL}')"
ok "témoin restauré à l'identique : ${restored}"
log "✓ Snapshot etcd RESTAURABLE — backup prouvé."
