#!/usr/bin/env bash
#
# Scénario 04 — Perte du control plane (SPOF assumé) : halt dirqual1,
# observer ce qui continue (workloads, Cilium, Ceph mons sur workers)
# et ce qui s'arrête (API K8s, kubectl), puis restore et vérifier que
# la sauvegarde etcd horaire a bien produit un snapshot pendant la
# fenêtre d'arrêt.
#
# Cible : prouver le comportement « SPOF assumé + sauvegarde etcd »
# (cf. ADR 0002 + RUNBOOK section restauration etcd).
#
# Variables : CONTROL=dirqual1, DOWNTIME_S=60, VAGRANT_DIR
set -euo pipefail

CONTROL=${CONTROL:-dirqual1}
DOWNTIME_S=${DOWNTIME_S:-60}
VAGRANT_DIR=${VAGRANT_DIR:-test/multi-node}

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }

log "Pré-snapshot etcd (vérifier que le timer tourne)"
ssh debian@"$CONTROL" 'systemctl is-active etcd-snapshot.timer' || \
    log "WARN etcd-snapshot.timer pas actif"

log "Lister snapshots etcd avant"
ssh debian@"$CONTROL" 'sudo ls -la /var/lib/etcd-backups/ 2>/dev/null | tail -5' || \
    log "WARN pas de répertoire /var/lib/etcd-backups"

log "Workloads avant arrêt :"
kubectl get pods -A --no-headers | wc -l

log "Halt $CONTROL"
(cd "$VAGRANT_DIR" && vagrant halt "$CONTROL")

log "Pendant l'arrêt — API K8s injoignable (attendu) :"
timeout 5 kubectl get nodes 2>&1 | head -3 || log "OK: kubectl HS comme attendu"

log "Cilium reste opérationnel ? (test via SSH worker)"
ssh debian@dirqual2 'cilium status --wait --wait-duration 30s 2>&1 | head -5' || \
    log "WARN Cilium peut être indisponible"

log "Attendre $DOWNTIME_S s pendant l'arrêt"
sleep "$DOWNTIME_S"

log "Restore $CONTROL"
(cd "$VAGRANT_DIR" && vagrant up "$CONTROL")

log "Attendre l'API K8s (5 min max)"
for _ in $(seq 1 30); do
    if kubectl get nodes >/dev/null 2>&1; then
        log "✓ API K8s répond à nouveau"
        kubectl get nodes
        break
    fi
    sleep 10
done

log "Vérifier qu'un snapshot etcd a été produit pendant l'arrêt"
ssh debian@"$CONTROL" 'sudo ls -la /var/lib/etcd-backups/ | tail -5'

log "État final"
kubectl get pods -A --no-headers | wc -l
log "✓ Scénario terminé"
