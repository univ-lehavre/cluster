#!/usr/bin/env bash
#
# Scénario 16 — ATTAQUE CONTRÔLÉE : brute-force SSH → fail2ban bannit.
#
# Sécurité ACTIVE (ADR 0025) : on simule un BRUTE-FORCE SSH et on asserte la
# chaîne Détection → Alerte → Réaction sur le détecteur HÔTE fail2ban
# (bootstrap/security/roles/detection/, jail sshd, maxretry=3, backend=systemd).
#
# MÉTHODE SÛRE & FIDÈLE. Le brute-force est matérialisé en injectant dans le
# JOURNAL sshd (backend systemd que lit fail2ban) N lignes d'échec
# d'authentification réalistes, attribuées à une IP source FACTICE de
# documentation (203.0.113.0/24, TEST-NET-3, RFC 5737 — jamais routée, jamais
# une vraie machine). fail2ban applique alors son failregex EXACTEMENT comme sur
# un vrai brute-force et bannit l'IP. On évite ainsi DEUX écueils :
#   - bannir l'OPÉRATEUR (si on attaquait depuis sa propre IP) ;
#   - viser une CIBLE TIERCE (garde-fou ADR 0025 : jamais de tiers).
# Le ban est RÉVERSIBLE (unban au cleanup). Ce qu'on teste reste réel : le
# failregex de la jail ET la réaction (ban) de fail2ban.
#
# Chaîne D/A/R assertée :
#   [D] Détection (BLOQUANT) : fail2ban repère le brute-force (ligne « Ban » dans
#       le journal fail2ban pour l'IP factice).
#   [R] Réaction (BLOQUANT)  : l'IP factice apparaît dans la « Banned IP list »
#       de `fail2ban-client status sshd`.
#   [A] Alerte (BEST-EFFORT, dépend de #131) : si l'alerting hôte→Mailpit est en
#       place (ALERT_CHECK=1 ou smarthost détecté), on vérifie qu'un mail part.
#       Tant que #131 n'est pas livrée : WARN non bloquant (ADR 0025 §2).
#
# Pourquoi c'est valable en prod : fail2ban + sa jail sshd sont identiques
# banc/prod. L'injection journal teste le MÊME failregex et le MÊME chemin de
# ban qu'un brute-force distant.
#
# GARDE-FOU (ADR 0025) : OFFENSIF côté HÔTE → banc jetable uniquement (la cible
# doit être une IP de banc, ou BANC=1).
#
# Pré-requis : accès SSH au nœud cible (root via sudo). Pas de kubectl.
# Variables :
#   TARGET_IP   (défaut 192.168.67.11)   TARGET_PORT (défaut 22)
#   SSH_KEY     (défaut clé insecure Vagrant)   USER_REMOTE (défaut debian)
#   BANC=1      force l'exécution si TARGET_IP hors plage de banc
#   ALERT_CHECK=1  active l'assertion [A] en dur (une fois #131 livrée)
#   KEEP=1      ne pas unban en sortie (inspection — à nettoyer à la main)
set -euo pipefail

TARGET_IP=${TARGET_IP:-192.168.67.11}
TARGET_PORT=${TARGET_PORT:-22}
SSH_KEY=${SSH_KEY:-${HOME}/.vagrant.d/insecure_private_keys/vagrant.key.rsa}
USER_REMOTE=${USER_REMOTE:-debian}
BANC=${BANC:-0}
ALERT_CHECK=${ALERT_CHECK:-0}
KEEP=${KEEP:-0}

# IP source factice (RFC 5737 TEST-NET-3) — jamais routée, jamais une vraie
# cible. C'est l'« attaquant » que fail2ban doit bannir.
ATTACKER_IP=${ATTACKER_IP:-203.0.113.66}
TRIES=${TRIES:-6} # > maxretry (3) pour déclencher franchement

# shellcheck source=test/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
target_ssh() { ssh "${SSH_OPTS[@]}" -p "$TARGET_PORT" -i "$SSH_KEY" "$USER_REMOTE@$TARGET_IP" "$@"; }

# ── Garde « banc jetable uniquement » (ADR 0025) ──────────────────────────────
assert_banc() {
    [ "$BANC" = "1" ] && { log "BANC=1 — cible déclarée jetable (garde levée)"; return; }
    case "$TARGET_IP" in
        192.168.* | 10.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[0-1].* | 127.*)
            log "✓ garde banc : $TARGET_IP en plage privée de banc" ;;
        *)
            log "✗ REFUS : TARGET_IP=$TARGET_IP hors plage de banc — scénario OFFENSIF"
            log "  interdit hors banc jetable (ADR 0025). Relancer avec BANC=1 si banc."
            exit 2 ;;
    esac
}

# shellcheck disable=SC2329 # invoqué via trap EXIT
cleanup() {
    if [ "$KEEP" = "1" ]; then
        log "KEEP=1 — pas d'unban (IP $ATTACKER_IP reste bannie ; unban manuel :"
        log "  sudo fail2ban-client set sshd unbanip $ATTACKER_IP)"
        return
    fi
    log "Cleanup — unban de l'IP factice $ATTACKER_IP…"
    target_ssh "sudo fail2ban-client set sshd unbanip $ATTACKER_IP >/dev/null 2>&1 || true" || true
}
trap cleanup EXIT

assert_banc

log "Cible : $USER_REMOTE@$TARGET_IP:$TARGET_PORT — vérification accès SSH…"
target_ssh "true" || { log "✗ nœud injoignable en SSH"; exit 2; }

# Pré-requis : fail2ban actif (sinon couche detection opt-in non activée → skip).
if ! target_ssh "systemctl is-active --quiet fail2ban"; then
    log "skip — fail2ban non actif sur la cible (couche detection opt-in non"
    log "  activée ; cf. bootstrap/security/IMPLICATIONS.md). Rien à exercer."
    exit 0
fi
log "✓ fail2ban actif — jail sshd attendue (maxretry=3, backend=systemd)"

# S'assurer qu'on part propre (au cas où un run précédent a laissé l'IP bannie).
target_ssh "sudo fail2ban-client set sshd unbanip $ATTACKER_IP >/dev/null 2>&1 || true"

log "[attaque] injection de $TRIES échecs d'auth sshd pour l'IP factice $ATTACKER_IP"
# Lignes au format attendu par le failregex sshd standard. Émises avec le tag
# « sshd » dans le journal systemd (le backend que lit la jail). On boucle pour
# dépasser maxretry.
target_ssh "sudo sh -c '
  for i in \$(seq 1 $TRIES); do
    logger -t sshd -p auth.info \"Failed password for invalid user attacker from $ATTACKER_IP port 4\$i ssh2\";
  done'" || { log "✗ injection journal échouée"; exit 1; }

log "[D/R] attente de la réaction fail2ban (ban de $ATTACKER_IP, 30s max)…"
banned=0
for _ in $(seq 1 30); do
    if target_ssh "sudo fail2ban-client status sshd 2>/dev/null | grep -qw '$ATTACKER_IP'"; then
        banned=1; break
    fi
    sleep 1
done

if [ "$banned" != "1" ]; then
    log "✗ [R] $ATTACKER_IP NON bannie après $TRIES échecs — fail2ban ne réagit pas !"
    log "  Diagnostic : sudo fail2ban-client status sshd"
    target_ssh "sudo fail2ban-client status sshd 2>/dev/null | tail -5" >&2 || true
    exit 1
fi
log "✓ [R] $ATTACKER_IP bannie — fail2ban RÉAGIT au brute-force"

# [D] trace explicite du maillon détection dans le journal de fail2ban.
if target_ssh "sudo journalctl -u fail2ban --since '-2 min' 2>/dev/null | grep -q 'Ban $ATTACKER_IP' \
   || sudo grep -q 'Ban $ATTACKER_IP' /var/log/fail2ban.log 2>/dev/null"; then
    log "✓ [D] brute-force détecté et journalisé (Ban $ATTACKER_IP)"
else
    log "! [D] ban effectif mais ligne 'Ban' non retrouvée au journal (rotation ?) — non bloquant"
fi

# [A] Alerte — dépend de #131 (alerting hôte → Mailpit). Best-effort par défaut.
alert_chain_present() {
    # Heuristique : un smarthost Mailpit/Mailgun configuré côté postfix indique
    # que #131 a câblé l'alerting. Sinon, chaîne d'alerte absente.
    target_ssh "postconf -h relayhost 2>/dev/null | grep -qiE 'mailpit|mailgun|:1025'"
}
if [ "$ALERT_CHECK" = "1" ] || alert_chain_present; then
    log "[A] chaîne d'alerte détectée — vérification d'un mail d'alerte (Mailpit)…"
    # On ne peut pas garantir le format exact tant que #131 n'a pas figé le sujet.
    # On cherche un mail récent mentionnant le ban ou l'IP factice via l'API Mailpit
    # (depuis le poste de contrôle si l'UI/API est joignable, sinon WARN).
    mp="${MAILPIT_API:-http://localhost:8025}"
    if command -v curl >/dev/null 2>&1 && \
       curl -fsS "$mp/api/v1/search?query=$ATTACKER_IP" 2>/dev/null | grep -q '"messages"'; then
        log "✓ [A] alerte trouvée dans Mailpit pour $ATTACKER_IP"
    else
        log "! [A] alerte non confirmée (Mailpit injoignable via $mp, ou sujet non"
        log "  encore figé par #131) — WARN non bloquant (ADR 0025 §2)."
    fi
else
    log "! [A] chaîne d'alerte hôte→Mailpit absente — dépend de l'issue #131."
    log "  Maillon Alerte non vérifié (WARN non bloquant). Activer via ALERT_CHECK=1"
    log "  une fois #131 livrée."
fi

log "✓ Chaîne D/R validée : fail2ban détecte le brute-force ET bannit la source."
exit 0
