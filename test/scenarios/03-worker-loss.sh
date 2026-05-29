#!/usr/bin/env bash
#
# Scénario 03 — Perte d'un worker : drain + halt d'un nœud, vérifier
# que Ceph passe en HEALTH_WARN mais reste opérationnel (I/O continuent
# tant que `failureDomain: host` + `min_size = 2` sont respectés sur ×3),
# puis restore le worker et vérifier la convergence HEALTH_OK.
#
# Variables :
#   VICTIM       — nom du worker à perdre (défaut: dirqual3)
#   VAGRANT_DIR  — dossier du Vagrantfile pour halt/up (défaut: test/multi-node)
#   DOWNTIME_S   — durée du downtime (défaut: 60)
#   KEEP=1       — pas de cleanup
#
# Sortie : `0` si HEALTH revient à OK après restore.
set -euo pipefail

VICTIM=${VICTIM:-dirqual3}
VAGRANT_DIR=${VAGRANT_DIR:-test/multi-node}
DOWNTIME_S=${DOWNTIME_S:-60}
KEEP=${KEEP:-0}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
ceph() { kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph "$@"; }

log "État initial Ceph"
ceph status | head -10

log "Drain le worker $VICTIM (pods déplaçables)"
kubectl drain "$VICTIM" --ignore-daemonsets --delete-emptydir-data --force --timeout=60s || \
    log "WARN drain incomplet — on continue"

log "Halt $VICTIM via vagrant"
(cd "$VAGRANT_DIR" && vagrant halt "$VICTIM")

log "Attendre Ceph HEALTH_WARN (${DOWNTIME_S}s)"
sleep 10
ceph status | head -10

log "Attendre $DOWNTIME_S s — observer comportement"
sleep "$DOWNTIME_S"
ceph status | head -10
ceph osd tree | head -15

log "Restore $VICTIM"
(cd "$VAGRANT_DIR" && vagrant up "$VICTIM")

log "Uncordon $VICTIM"
sleep 30
kubectl uncordon "$VICTIM" 2>/dev/null || true

log "Attendre HEALTH_OK (5 min max)"
for _ in $(seq 1 30); do
    health=$(ceph health 2>/dev/null | awk '{print $1}')
    if [ "$health" = "HEALTH_OK" ]; then
        log "✓ Ceph revenu HEALTH_OK"
        ceph status | head -10
        exit 0
    fi
    sleep 10
done

log "✗ Ceph toujours pas HEALTH_OK après 5 min"
ceph status
exit 1
