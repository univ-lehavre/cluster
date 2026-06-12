#!/usr/bin/env bash
#
# Scénario 22 — ALERTE : les détecteurs alertent-ils VRAIMENT ? (→ Mailpit)
#
# Sécurité ACTIVE (ADR 0025) : ferme le maillon [A] Alerte de la chaîne D/A/R,
# de bout en bout. Détection et réaction sont déjà prouvées (fail2ban bannit —
# scénario 16 ; PSA rejette — 17 ; NetworkPolicy coupe — 18). Reste à vérifier
# qu'un événement de sécurité PRODUIT BIEN UNE ALERTE qui arrive dans le puits
# mail de test (platform/mailpit/, Service mailpit.mail.svc, API HTTP sur :80).
#
# DÉPENDANCE #131 (alerting hôte → Mailpit/Mailgun). Tant que #131 n'est pas
# livrée, la chaîne d'alerte n'existe pas → ce scénario SKIP NEUTREMENT (exit 0
# avec message), sauf STRICT_ALERT=1 qui le fait alors ÉCHOUER (utile en CI une
# fois #131 mergée — calque le STRICT_OPTIN=1 du scénario 13).
#
# Mécanique :
#   1. déclenche un événement détectable côté hôte (ban fail2ban d'une IP
#      factice, même technique sûre que le 16 — RFC 5737, réversible) ;
#   2. interroge l'API Mailpit (depuis un pod busybox dans le cluster) ;
#   3. PASS si un mail d'alerte correspondant à l'événement est arrivé.
#
# GARDE-FOU (ADR 0025) : banc jetable uniquement (TARGET_IP en plage banc / BANC=1).
#
# Pré-requis : kubectl (Mailpit déployé) + accès SSH au nœud cible (déclencheur).
# Variables :
#   TARGET_IP (défaut 192.168.67.11)   TARGET_PORT (22)   SSH_KEY / USER_REMOTE
#   STRICT_ALERT=1  échoue (au lieu de skip) si la chaîne d'alerte est absente
#   MAILPIT_SVC     (défaut mailpit.mail.svc.cluster.local) — API HTTP :80
#   BANC=1          force l'exécution hors plage de banc
#   KEEP=1          ne pas unban l'IP factice en sortie
set -euo pipefail

TARGET_IP=${TARGET_IP:-192.168.67.11}
TARGET_PORT=${TARGET_PORT:-22}
SSH_KEY=${SSH_KEY:-${HOME}/.vagrant.d/insecure_private_keys/vagrant.key.rsa}
USER_REMOTE=${USER_REMOTE:-debian}
STRICT_ALERT=${STRICT_ALERT:-0}
MAILPIT_SVC=${MAILPIT_SVC:-mailpit.mail.svc.cluster.local}
BANC=${BANC:-0}
KEEP=${KEEP:-0}
ATTACKER_IP=${ATTACKER_IP:-203.0.113.77} # RFC 5737 TEST-NET-3, jamais routée
TRIES=${TRIES:-6}

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
target_ssh() { ssh "${SSH_OPTS[@]}" -p "$TARGET_PORT" -i "$SSH_KEY" "$USER_REMOTE@$TARGET_IP" "$@"; }

# ── Garde « banc jetable uniquement » (ADR 0025) ──
assert_banc() {
    [ "$BANC" = "1" ] && { log "BANC=1 — cible déclarée jetable (garde levée)"; return; }
    case "$TARGET_IP" in
        192.168.* | 10.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[0-1].* | 127.*)
            log "✓ garde banc : $TARGET_IP en plage privée de banc" ;;
        *) log "✗ REFUS : TARGET_IP=$TARGET_IP hors plage de banc (ADR 0025). BANC=1 si banc."; exit 2 ;;
    esac
}

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    [ "$KEEP" = "1" ] && { log "KEEP=1 — IP $ATTACKER_IP laissée bannie (unban manuel)"; return; }
    log "Cleanup - unban de l'IP factice $ATTACKER_IP"
    target_ssh "sudo fail2ban-client set sshd unbanip $ATTACKER_IP >/dev/null 2>&1 || true" 2>/dev/null || true
}
trap cleanup EXIT

assert_banc

# ── Détecter la présence de la chaîne d'alerte hôte → Mailpit (issue #131) ──
# Heuristique : un relayhost postfix pointant Mailpit/Mailgun (:1025) indique que
# #131 a câblé l'alerting. Sans accès SSH ou sans relayhost → chaîne absente.
chain_present=0
if target_ssh "true" 2>/dev/null; then
    if target_ssh "postconf -h relayhost 2>/dev/null | grep -qiE 'mailpit|mailgun|:1025'"; then
        chain_present=1
    fi
else
    log "! nœud injoignable en SSH — impossible de déclencher l'événement hôte"
fi

if [ "$chain_present" != "1" ]; then
    if [ "$STRICT_ALERT" = "1" ]; then
        log "✗ STRICT_ALERT=1 et chaîne d'alerte hôte→Mailpit ABSENTE — attendu une fois"
        log "  l'issue #131 livrée (relayhost postfix vers Mailpit/Mailgun non configuré)."
        exit 1
    fi
    log "skip — chaîne d'alerte hôte→Mailpit non configurée (dépend de l'issue #131)."
    log "  Détection et réaction sont prouvées par les scénarios 16/17/18 ; le maillon"
    log "  Alerte sera testable ici une fois #131 mergée (puis STRICT_ALERT=1 en CI)."
    exit 0
fi
log "✓ chaîne d'alerte hôte→Mailpit détectée (relayhost) — test de bout en bout"

# Pré-requis Mailpit côté cluster.
kubectl -n mail get deploy/mailpit >/dev/null 2>&1 \
    || { log "✗ Mailpit non déployé (platform/mailpit/) — pas de puits d'alerte"; exit 2; }

# Helper : interroge l'API Mailpit DEPUIS le cluster (Service ClusterIP :80).
# Renvoie 0 si un message mentionne l'IP factice.
mailpit_has_alert() {
    kubectl -n mail run mailpit-probe-$$ --rm -i --restart=Never \
        --image=busybox:1.36 --quiet -- \
        sh -c "wget -qO- 'http://$MAILPIT_SVC/api/v1/search?query=$ATTACKER_IP' 2>/dev/null" 2>/dev/null \
        | grep -q "$ATTACKER_IP"
}

# Note du nombre de messages avant, pour ne pas confondre avec un mail antérieur :
# on filtre sur l'IP factice unique à ce run, c'est suffisamment discriminant.

log "[déclencheur] brute-force SSH simulé (ban de $ATTACKER_IP) pour générer une alerte…"
target_ssh "sudo fail2ban-client set sshd unbanip $ATTACKER_IP >/dev/null 2>&1 || true"
target_ssh "sudo sh -c '
  for i in \$(seq 1 $TRIES); do
    logger -t sshd -p auth.info \"Failed password for invalid user attacker from $ATTACKER_IP port 4\$i ssh2\";
  done'" || { log "✗ déclenchement échoué"; exit 1; }

# Attendre le ban (réaction) — PRÉ-REQUIS du test d'alerte : sans réaction, pas
# d'alerte à attendre. On asserte donc que le ban a bien eu lieu avant de tester
# le maillon [A] (sinon un échec d'alerte masquerait un échec de réaction).
log "[R] attente du ban (preuve que l'événement est traité)…"
banned=0
for _ in $(seq 1 30); do
    if target_ssh "sudo fail2ban-client status sshd 2>/dev/null | grep -qw '$ATTACKER_IP'"; then
        banned=1; break
    fi
    sleep 1
done
if [ "$banned" != "1" ]; then
    log "✗ [R] $ATTACKER_IP non bannie — la RÉACTION a échoué (pas l'alerte)."
    log "  Le test d'alerte n'a de sens qu'après une réaction réussie. Voir scénario 16."
    exit 1
fi
log "✓ [R] $ATTACKER_IP bannie — réaction OK, on peut tester l'alerte"

log "[A] attente de l'alerte dans Mailpit (90s max)…"
alert_ok=0
for _ in $(seq 1 18); do
    if mailpit_has_alert; then alert_ok=1; break; fi
    sleep 5
done

if [ "$alert_ok" = "1" ]; then
    log "✓ [A] alerte reçue dans Mailpit pour l'événement ($ATTACKER_IP) —"
    log "  la chaîne détection→ALERTE→réaction est COMPLÈTE de bout en bout."
    exit 0
fi

log "✗ [A] aucune alerte Mailpit pour $ATTACKER_IP en 90s — la détection a réagi"
log "  (ban) mais N'A PAS ALERTÉ. Vérifier le câblage #131 (fail2ban → mail →"
log "  relayhost Mailpit) et le filtre de recherche Mailpit."
exit 1
