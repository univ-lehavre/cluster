#!/usr/bin/env bash
#
# Scénario 15 — Chiffrement at-rest des Secrets etcd + audit-policy (ADR 0014).
#
# Vérifie, sur le control plane (via SSH, comme le scénario 09) :
#   1. un Secret témoin est RÉELLEMENT chiffré dans etcd — sa valeur brute lue
#      par `etcdctl` commence par `k8s:enc:secretbox:` (et non en clair) ;
#   2. l'audit-log de l'API server est produit et contient des entrées
#      `Metadata` (qui/quoi/quand) ;
#   3. la ROTATION de clé fonctionne : on ajoute une 2ᵉ clé en tête, on
#      redémarre l'API server, on réécrit les Secrets, et le témoin reste
#      lisible (preuve qu'une rotation ne perd pas les données).
#
# Pourquoi c'est valable en prod : ce sont des propriétés du datapath etcd/API
# server, identiques banc/prod. Le scénario LIT etcd et réécrit des Secrets ; il
# ne reconfigure pas le cluster (sauf l'étape 3, optionnelle et réversible).
#
# Pré-requis : control plane joignable par SSH (cf. variables ci-dessous),
# kubeadm --config avec EncryptionConfiguration appliqué (bootstrap k8s-init).
# Variables :
#   CP_IP   (défaut 192.168.67.11)   CP_PORT (défaut 22)
#   SSH_KEY (défaut clé insecure Vagrant)   USER_REMOTE (défaut debian)
#   ROTATE=1  déroule en plus le test de rotation (étape 3) — réversible
set -uo pipefail

CP_IP=${CP_IP:-192.168.67.11}
CP_PORT=${CP_PORT:-22}
SSH_KEY=${SSH_KEY:-${HOME}/.vagrant.d/insecure_private_keys/vagrant.key.rsa}
USER_REMOTE=${USER_REMOTE:-debian}
ROTATE=${ROTATE:-0}
NS=${NAMESPACE:-default}
SECRET=scenario15-witness
ENC_DIR=/etc/kubernetes/enc

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o BatchMode=yes)
cp_ssh() { ssh "${SSH_OPTS[@]}" -p "${CP_PORT}" -i "${SSH_KEY}" "${USER_REMOTE}@${CP_IP}" "$@"; }
kc() { cp_ssh "sudo KUBECONFIG=/etc/kubernetes/admin.conf kubectl $*"; }

# etcdctl sur le control plane, avec les certs kubeadm.
etcd_get() {
    cp_ssh "sudo ETCDCTL_API=3 etcdctl \
        --cacert=/etc/kubernetes/pki/etcd/ca.crt \
        --cert=/etc/kubernetes/pki/etcd/server.crt \
        --key=/etc/kubernetes/pki/etcd/server.key \
        get '$1' --print-value-only 2>/dev/null | head -c 60"
}

log "[1/3] Chiffrement at-rest — créer un Secret témoin et le lire dans etcd"
kc "create secret generic $SECRET -n $NS --from-literal=probe=topsecret --dry-run=client -o yaml | sudo KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f -" >/dev/null
raw=$(etcd_get "/registry/secrets/$NS/$SECRET")
printf '    etcd brut : %s…\n' "$raw"
if printf '%s' "$raw" | grep -q 'k8s:enc:secretbox:'; then
    log "✓ Secret chiffré dans etcd (préfixe k8s:enc:secretbox:)"
elif printf '%s' "$raw" | grep -q 'topsecret'; then
    log "✗ Secret EN CLAIR dans etcd — chiffrement NON actif (EncryptionConfiguration absente ?)"
    kc "delete secret $SECRET -n $NS" >/dev/null 2>&1 || true
    exit 1
else
    log "✗ Lecture etcd inattendue — etcdctl/certs ? (valeur: $raw)"
    exit 1
fi

log "[2/3] Audit-policy — l'audit-log existe et contient des entrées Metadata"
if cp_ssh "sudo test -s /var/log/kubernetes/audit/audit.log"; then
    n=$(cp_ssh "sudo grep -c '\"level\":\"Metadata\"' /var/log/kubernetes/audit/audit.log 2>/dev/null" | tr -d '[:space:]')
    if [ "${n:-0}" -gt 0 ]; then
        log "✓ Audit-log produit (${n} entrées Metadata)"
    else
        log "✗ Audit-log présent mais sans entrée Metadata — policy mal chargée ?"
        exit 1
    fi
else
    log "✗ Audit-log absent (/var/log/kubernetes/audit/audit.log) — audit-policy non appliquée"
    exit 1
fi

if [ "$ROTATE" != "1" ]; then
    log "[3/3] Rotation : non jouée (ROTATE=1 pour l'exercer). Nettoyage."
    kc "delete secret $SECRET -n $NS" >/dev/null 2>&1 || true
    log "✓ Chiffrement etcd + audit-policy vérifiés (ADR 0014)."
    exit 0
fi

log "[3/3] Rotation de clé — la dérouler et prouver que le témoin survit"
# Sauvegarde de l'EncryptionConfiguration courante (rollback en cas d'échec).
cp_ssh "sudo cp $ENC_DIR/encryption-config.yaml /tmp/enc-config.bak"
rollback() {
    log "  rollback de l'EncryptionConfiguration"
    cp_ssh "sudo cp /tmp/enc-config.bak $ENC_DIR/encryption-config.yaml"
    restart_apiserver
}

# Redémarre l'API server (static pod) en touchant son manifeste, et attend qu'il
# réponde de nouveau.
restart_apiserver() {
    cp_ssh "sudo touch /etc/kubernetes/manifests/kube-apiserver.yaml"
    for _ in $(seq 1 30); do
        kc "version --request-timeout=3s" >/dev/null 2>&1 && return 0
        sleep 4
    done
    return 1
}

# Étape A : insérer une nouvelle clé key2 EN TÊTE (chiffre), key1 reste (déchiffre).
log "  → ajout d'une 2ᵉ clé (key2) en tête, key1 conservée"
key2=$(cp_ssh "openssl rand -base64 32")
cp_ssh "sudo tee $ENC_DIR/encryption-config.yaml >/dev/null" <<EOF
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources: [secrets]
    providers:
      - secretbox:
          keys:
            - name: key2
              secret: $key2
            - name: key1
              secret: $(cp_ssh "sudo cat $ENC_DIR/key1.b64 | tr -d '\n'")
      - identity: {}
EOF
if ! restart_apiserver; then log "✗ API server ne redémarre pas après ajout key2"; rollback; exit 1; fi
log "  ✓ API server redémarré avec key2+key1"

# Étape B : réécrire tous les Secrets → ils basculent sur key2.
log "  → réécriture de tous les Secrets (bascule sur key2)"
kc "get secrets -A -o json | sudo KUBECONFIG=/etc/kubernetes/admin.conf kubectl replace -f -" >/dev/null 2>&1 || true

# Étape C : le témoin doit toujours être lisible ET chiffré (avec key2).
val=$(kc "get secret $SECRET -n $NS -o jsonpath='{.data.probe}'" | base64 -d 2>/dev/null)
raw2=$(etcd_get "/registry/secrets/$NS/$SECRET")
if [ "$val" = "topsecret" ] && printf '%s' "$raw2" | grep -q 'k8s:enc:secretbox:'; then
    log "✓ Après rotation : témoin lisible (valeur intacte) ET toujours chiffré"
else
    log "✗ Témoin perdu/illisible après rotation (val='$val')"
    rollback; exit 1
fi

# Restaurer la config d'origine (key1 seule) pour laisser le banc dans l'état initial.
log "  → restauration de l'EncryptionConfiguration d'origine (key1)"
rollback
kc "get secrets -A -o json | sudo KUBECONFIG=/etc/kubernetes/admin.conf kubectl replace -f -" >/dev/null 2>&1 || true
kc "delete secret $SECRET -n $NS" >/dev/null 2>&1 || true
log "✓ Rotation déroulée et réversible — le témoin a survécu (ADR 0014)."
exit 0
