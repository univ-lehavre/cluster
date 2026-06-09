#!/usr/bin/env bash
#
# Fonctions PURES d'assertion pour le scénario GitOps → workflows atlas (#231).
#
# Comme dataops-assert.sh / state-classify.sh : ces fonctions ne font NI kubectl,
# NI réseau. Elles prennent en entrée des valeurs déjà collectées et renvoient un
# verdict `STATUS|message` sur stdout (STATUS ∈ {ok, fail, skip}). But : rendre la
# logique de décision testable sans cluster (test/unit/gitops-assert.bats).
#
# Convention : une ligne "STATUS|message". L'appelant découpe sur le premier '|'.
# Aucune fonction n'appelle `exit` ni n'écrit ailleurs que sur stdout.

# classify_argocd_app SYNC HEALTH
# Classe l'état d'une Application Argo CD à partir de son sync status et de son
# health status. L'objectif d'un déploiement GitOps réussi est Synced + Healthy.
classify_argocd_app() {
    local sync=$1 health=$2
    if [ -z "${sync}" ] || [ -z "${health}" ]; then
        printf 'fail|Application introuvable (sync=%s health=%s) — Argo CD a-t-il réconcilié ?\n' \
            "${sync:-∅}" "${health:-∅}"
        return 0
    fi
    if [ "${sync}" = "Synced" ] && [ "${health}" = "Healthy" ]; then
        printf 'ok|Application Synced/Healthy — Argo CD a déployé les workflows\n'
        return 0
    fi
    printf 'fail|Application %s/%s (attendu Synced/Healthy)\n' "${sync}" "${health}"
}

# classify_webhook_trigger SYNC_REVISION_BEFORE SYNC_REVISION_AFTER
# Vérifie qu'un push a bien déclenché une NOUVELLE réconciliation (la révision
# synchronisée a changé) — preuve que le webhook a agi, pas seulement le polling
# différé. BEFORE/AFTER = la révision git que reflète status.sync.revision.
classify_webhook_trigger() {
    local before=$1 after=$2
    if [ -z "${after}" ]; then
        printf 'fail|aucune révision synchronisée après le push (Argo CD a-t-il reçu le webhook ?)\n'
        return 0
    fi
    if [ "${before}" = "${after}" ]; then
        printf 'fail|révision inchangée (%s) — le push n''a pas déclenché de réconciliation\n' "${after}"
        return 0
    fi
    printf 'ok|réconciliation sur nouvelle révision (%s → %s)\n' "${before:-∅}" "${after}"
}
