#!/usr/bin/env bash
#
# Scénario 13 — Durcissement host/node : transforme le diagnostic d'état
# `bootstrap/state.sh` en une assertion PASS/FAIL sur les couches HÔTE
# (système d'exploitation des nœuds), pour l'intégrer à run-all.sh.
#
# Plutôt que de redupliquer les vérifications (auditd, fail2ban, postfix,
# sshd durci, ufw, smartd), ce scénario RÉUTILISE state.sh — la source de
# vérité du dépôt — et n'échoue que si une couche host présente un drift
# (`✗`). Rappel sémantique de state.sh : une couche opt-in NON activée est
# un `skip` (pas un drift) ; le `✗` n'arrive que si une couche est
# partiellement activée (paquet installé mais service inactif) ou a régressé,
# ou si le durcissement SSH de base manque.
#
# Périmètre = sections « Premier accès SSH » (couche 1) et « Hardening OS »
# (couche 2) de state.sh. Les sections Kubernetes/Ceph ne sont PAS évaluées
# ici (elles sont couvertes par les autres scénarios) : on isole le host.
#
# Pourquoi c'est valable en prod : ce sont des vérifications SSH de l'état
# système des nœuds, identiques banc/prod. Sur le banc, fournir SSH_OPTS et
# la liste des hôtes Vagrant.
#
# Pré-requis : accès SSH aux nœuds (mêmes pré-requis que state.sh).
# Variables :
#   HOSTS='dirqual1 …'   liste des nœuds (défaut: laisse state.sh décider)
#   SSH_OPTS, USER_REMOTE passés tels quels à state.sh (cf. son en-tête)
#   STRICT_OPTIN=1       fait AUSSI échouer si AUCUNE couche OS n'est active
#                        (utile en prod où le durcissement est censé être posé)
set -uo pipefail

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STATE_SH="$HERE/../../bootstrap/state.sh"
HOSTS=${HOSTS:-}
STRICT_OPTIN=${STRICT_OPTIN:-0}

[ -x "$STATE_SH" ] || { log "✗ state.sh introuvable/non exécutable ($STATE_SH)"; exit 2; }

log "Lancement de state.sh (NO_COLOR) pour évaluer les couches host…"
# NO_COLOR pour un parsing fiable (pas de codes ANSI dans les marqueurs).
# state.sh sort 2 si aucun hôte joignable → on relaie tel quel.
# shellcheck disable=SC2086 # HOSTS doit être word-split en arguments
raw=$(NO_COLOR=1 "$STATE_SH" $HOSTS 2>&1)
state_rc=$?
if [ "$state_rc" -eq 2 ]; then
    log "✗ Aucun hôte joignable (state.sh rc=2) — voir bootstrap/first-access.sh"
    printf '%s\n' "$raw" | tail -5 >&2
    exit 2
fi

# Isoler les deux sections host. Les titres de section de state.sh sont émis
# via `section()` : « ── <titre> ── ». On capture des titres jusqu'au titre
# de section SUIVANT, pour borner précisément le bloc host.
host_block=$(printf '%s\n' "$raw" | awk '
    /── Premier accès SSH/      { cap=1 }
    /── Hardening OS/           { cap=1 }
    /^── / && $0 !~ /Premier accès SSH|Hardening OS/ { if (cap) cap=0 }
    cap { print }
')

if [ -z "$host_block" ]; then
    log "✗ Sections host introuvables dans la sortie de state.sh (format changé ?)"
    printf '%s\n' "$raw" | grep -E '^── ' >&2
    exit 2
fi

log "── Extrait des couches host évaluées ──"
printf '%s\n' "$host_block"

# Compter les drifts (✗) et les OK dans le bloc host.
fails=$(printf '%s\n' "$host_block" | grep -c '✗' || true)
oks=$(printf '%s\n' "$host_block"   | grep -c '✓' || true)
# Couches OS opt-in actives = lignes OK mentionnant « (couche … ) ».
os_layers_active=$(printf '%s\n' "$host_block" | grep -c '(couche ' || true)

echo
if [ "${fails:-0}" -gt 0 ]; then
    log "✗ ${fails} drift(s) host détecté(s) (✗ ci-dessus) — corriger via la"
    log "  « Prochaine étape » indiquée par state.sh (relancer bootstrap/state.sh)."
    exit 1
fi

if [ "$STRICT_OPTIN" = "1" ] && [ "${os_layers_active:-0}" -eq 0 ]; then
    log "✗ STRICT_OPTIN=1 et AUCUNE couche de durcissement OS active —"
    log "  attendu en prod. Activer : cd bootstrap/security && ansible-playbook"
    log "  -i ../hosts.yaml secure.yml --tags audit,detection,alert"
    exit 1
fi

log "✓ Aucun drift host (${oks} ✓, ${os_layers_active} couche(s) OS opt-in active(s))."
[ "${os_layers_active:-0}" -eq 0 ] && \
    log "  (Couches OS toutes en opt-in non activé — pas un drift ; cf. IMPLICATIONS.md.)"
exit 0
