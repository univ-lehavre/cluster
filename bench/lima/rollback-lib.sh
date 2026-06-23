#!/usr/bin/env bash
#
# Primitives du ROLLBACK PAR PHASE du banc (ADR 0054, issue #274). Défait UNE
# phase montée par run-phases.sh : efface namespaces + CRD + PVC + état node-side,
# force les finalizers récalcitrants (banc JETABLE → destructif total, pas de
# ménagement des données). Sourcé par bench/lima/run-phases.sh (dispatch
# `rollback <phase>`). Distinct du rollback transactionnel #236 (rescue auto).
#
# Deux familles ici :
#  - FONCTIONS PURES (table de périmètre, ordre des dépendances, verdict d'état
#    propre) : NI kubectl NI ssh, prennent des valeurs déjà collectées, renvoient
#    un verdict `STATUS|message` ou une valeur. Testées par bench/unit/rollback.bats
#    (comme state-classify.sh / bootstrap-fault-assert.sh).
#  - PRIMITIVES kubectl/ssh (k8s_force_delete_ns…) : font le réseau, NON pures.
#    Elles attendent les fonctions log/ok/die/vm_sh/KUBECTL de lib.sh/run-phases.sh.
#
# Convention verdict : une ligne "STATUS|message" (STATUS ∈ {ok, fail, skip}),
# découpée sur le premier '|'.

# ─── PARTIE PURE (testable bats, aucun réseau) ──────────────────────────────

# rollback_phase_namespaces PHASE
#   Namespaces qu'un rollback de PHASE doit effacer (séparés par des espaces),
#   ou vide si la phase n'a pas de namespace dédié. Table de périmètre (ADR 0054
#   §3), valeurs génériques banc (ADR 0023).
rollback_phase_namespaces() {
    case "${1:-}" in
        # SEUL `ceph` possède le ns rook-ceph → lui seul le supprime. `sc` et
        # `datalake` PARTAGENT rook-ceph (Ceph y vit) : ils ne doivent PAS le
        # supprimer (ça tuerait Ceph) — ils effacent des ressources CIBLÉES
        # (cf. rollback_phase_targeted_resources).
        ceph)            printf 'rook-ceph\n' ;;
        monitoring)      printf 'monitoring\n' ;;
        dataops)         printf 'postgres dagster marquez\n' ;;
        mlflow)          printf 'mlflow\n' ;;  # layer autonome : son seul ns (la base CNPG `mlflow` reste à dataops)
        gitops)          printf 'argocd gitea\n' ;;
        *)               printf '\n' ;;  # sc, datalake, metrics-server, gitops-seed : pas de ns à supprimer
    esac
}

# rollback_phase_targeted_resources PHASE
#   Ressources CIBLÉES à supprimer (kind/name ou kind par ns), pour les phases
#   qui n'ont PAS de ns propre mais des ressources précises (partage rook-ceph,
#   deploy dans kube-system…). Une ressource par ligne, forme « -n NS KIND NAME »
#   ou « KIND NAME » (cluster-scoped). Vide sinon.
rollback_phase_targeted_resources() {
    case "${1:-}" in
        datalake)
            # CephObjectStore + sa SC bucket (rook-ceph), SANS toucher le ns.
            printf -- '-n rook-ceph cephobjectstore.ceph.rook.io datalake\n'
            printf 'storageclass.storage.k8s.io rook-ceph-datalake\n' ;;
        sc)
            # StorageClasses bloc/fs + leurs CephBlockPool/CephFilesystem.
            printf 'storageclass.storage.k8s.io rook-ceph-block-replicated\n'
            printf 'storageclass.storage.k8s.io rook-ceph-block-ec-delete\n'
            printf 'storageclass.storage.k8s.io rook-ceph-block-ec\n'
            printf 'storageclass.storage.k8s.io rook-cephfs\n' ;;
        metrics-server)
            printf -- '-n kube-system deployment.apps metrics-server\n' ;;
        monitoring)
            # OBC du backing S3 de Loki, posée par platform-loki DANS rook-ceph
            # (ns ≠ monitoring). Sans elle, le CephObjectStore datalake reste bloqué
            # en Deleting (finalizer : un bucket dépendant subsiste). #319-suite.
            # CONDITIONNEL au backend : l'OBC n'existe QU'en ceph. En local-path le
            # backing est SeaweedFS (creds statiques, pas d'OBC) et la CRD
            # objectbucketclaim est ABSENTE → un `kubectl delete` échouerait (« the
            # server doesn't have a resource type ») au lieu d'un no-op → on n'émet rien.
            [ "$(_rb_backend)" = ceph ] \
                && printf -- '-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets\n'
            : ;;
        dataops)
            # OBC du backing S3 de CNPG/Barman, posée par platform-cnpg DANS rook-ceph
            # (ns ≠ postgres). Même raison que monitoring : libère le datalake.
            # CONDITIONNEL au backend (cf. monitoring) : pas d'OBC ni de CRD en local-path.
            [ "$(_rb_backend)" = ceph ] \
                && printf -- '-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups\n'
            : ;;
        mlflow)
            # OBC de l'artefact store MLflow, posée par platform-s3-bucket DANS rook-ceph
            # (ns ≠ mlflow). Même raison que dataops/monitoring : libère le datalake.
            # CONDITIONNEL au backend : pas d'OBC ni de CRD objectbucket en local-path.
            [ "$(_rb_backend)" = ceph ] \
                && printf -- '-n rook-ceph objectbucketclaim.objectbucket.io mlflow-artifacts\n'
            : ;;
        gitops-seed)
            # Données dans Gitea (org/repo) + Application Argo CD seed — best-effort.
            # L'Application posée par le seed s'appelle `atlas-workflows` (PAS `atlas` :
            # ça, c'est l'AppProject, défait par le composant argocd). Cf. le manifeste
            # atlas-workflow-sample/application.example.yaml + le scénario 27.
            printf -- '-n argocd applications.argoproj.io atlas-workflows\n' ;;
        *) printf '\n' ;;
    esac
}

# rollback_phase_crd_groups PHASE
#   Groupes API dont les CRD doivent être supprimés (séparés par des espaces).
#   Supprimer un groupe CRD GC les CR restants. Vide si la phase n'installe pas
#   de CRD propres.
rollback_phase_crd_groups() {
    case "${1:-}" in
        # SEUL `ceph` supprime les CRD ceph.rook.io (partagés par sc/datalake) :
        # les retirer depuis sc/datalake casserait Ceph. sc/datalake passent par
        # rollback_phase_targeted_resources (CR ciblés, pas les CRD).
        ceph)                 printf 'ceph.rook.io\n' ;;
        monitoring)           printf 'monitoring.coreos.com\n' ;;
        dataops)              printf 'postgresql.cnpg.io\n' ;;
        gitops)               printf 'argoproj.io\n' ;;
        *)                    printf '\n' ;;
    esac
}

# rollback_phase_has_nodeside PHASE
#   "yes" si la phase laisse un état NODE-SIDE que le delete Kubernetes ne couvre
#   pas (disques Ceph + /var/lib/rook). Seul `ceph` en a.
rollback_phase_has_nodeside() {
    case "${1:-}" in
        ceph) printf 'yes\n' ;;
        *)    printf 'no\n' ;;
    esac
}

# rollback_phase_downstream PHASE
#   Phases AVAL qui dépendent de PHASE (séparées par des espaces) : on ne défait
#   pas une phase socle tant qu'une de ses phases aval est encore montée
#   (ordre inverse, ADR 0054 §4). Vide si aucune.
rollback_phase_downstream() {
    case "${1:-}" in
        ceph)     printf 'sc datalake wordpress\n' ;;
        # MLflow dépend de la base CNPG `mlflow` (posée par dataops) → on ne défait
        # pas dataops tant que mlflow est monté (ordre inverse, ADR 0054 §4).
        dataops)  printf 'mlflow\n' ;;
        gitops)   printf 'gitops-seed\n' ;;
        *)        printf '\n' ;;
    esac
}

# rollback_known_phase PHASE
#   0 (vrai) si PHASE est une phase connue qui a un rollback défini. Sert au
#   dispatch à rejeter un nom inconnu.
rollback_known_phase() {
    case "${1:-}" in
        ceph | sc | datalake | metrics-server | monitoring | dataops | mlflow | gitops | gitops-seed)
            return 0 ;;
        *) return 1 ;;
    esac
}

# classify_clean_state RESIDUAL
#   Verdict d'état propre après un rollback (ADR 0054 preuve). RESIDUAL = liste
#   (séparée par des espaces) des traces ENCORE présentes (ns/CRD/PVC/disque
#   sale) collectées par l'appelant ; vide = aucune trace.
#   - RESIDUAL vide → ok (rollback complet : zéro trace)
#   - sinon         → fail (liste les résidus → table de périmètre à compléter)
classify_clean_state() {
    local residual=${1:-}
    residual=${residual#"${residual%%[![:space:]]*}"}
    residual=${residual%"${residual##*[![:space:]]}"}
    if [ -z "$residual" ]; then
        printf 'ok|Rollback complet : aucune trace résiduelle\n'
    else
        printf 'fail|Traces résiduelles après rollback : %s (compléter la table de périmètre, ADR 0054 §3)\n' "$residual"
    fi
}

# classify_downstream_block PHASE PRESENT_DOWNSTREAM
#   Verdict du garde-fou d'ordre (ADR 0054 §4). PRESENT_DOWNSTREAM = liste des
#   phases aval ENCORE présentes (collectée par l'appelant).
#   - vide → ok (aucune phase aval → on peut défaire PHASE)
#   - sinon → fail (défaire PHASE laisserait les phases aval orphelines)
classify_downstream_block() {
    local phase=${1:-} present=${2:-}
    present=${present#"${present%%[![:space:]]*}"}
    present=${present%"${present##*[![:space:]]}"}
    if [ -z "$present" ]; then
        printf 'ok|Aucune phase aval présente — %s peut être défaite\n' "$phase"
    else
        printf 'fail|Phases AVAL encore montées (%s) : défaire %s d'\''abord (ordre inverse, ADR 0054 §4)\n' "$present" "$phase"
    fi
}

# classify_hardening_signal AUDITD FAIL2BAN
#   Verdict de l'ÉTAT de durcissement de l'hôte (ADR 0065 §2 : le durcissement est
#   un état CONSTATABLE, pas un flag à re-saisir). Le durcissement du banc = les
#   tags `audit,detection` de secure.yml → auditd + fail2ban ACTIFS (les seules
#   couches que phase_hardening pose ; le sshd drop-in vient de first-access et est
#   toujours là, donc NON discriminant). AUDITD/FAIL2BAN ∈ {active, inactive,
#   unknown} (collectés par l'appelant via `systemctl is-active`).
#   - les deux active            → ok|hardened (l'hôte EST durci → suffixe +hardening)
#   - les deux inactive          → ok|plain    (l'hôte n'est PAS durci → pas de suffixe)
#   - un signal `unknown`        → skip        (injoignable/illisible → l'appelant die,
#                                               « détection fiable ou refus franc »)
#   - état PARTIEL (un seul actif) → fail       (durcissement incohérent à corriger)
classify_hardening_signal() {
    local auditd=${1:-unknown} fail2ban=${2:-unknown}
    case "${auditd}/${fail2ban}" in
        active/active)     printf 'ok|hardened : auditd+fail2ban actifs (hôte durci, +hardening)\n' ;;
        inactive/inactive) printf 'ok|plain : auditd+fail2ban inactifs (hôte non durci)\n' ;;
        *unknown*)         printf 'skip|état de durcissement illisible (auditd=%s fail2ban=%s) — hôte injoignable ?\n' "${auditd}" "${fail2ban}" ;;
        *)                 printf 'fail|durcissement PARTIEL (auditd=%s fail2ban=%s) — couche incohérente à corriger\n' "${auditd}" "${fail2ban}" ;;
    esac
}

# ─── GRAPHE ATOMIQUE (ADR 0066, Lot 0 : à CÔTÉ des rollback_phase_*) ─────────
#
# L'unité du périmètre descend de la PHASE (composite, fragile) vers le COMPOSANT
# ATOMIQUE (ADR 0066). Un composant a AU PLUS un namespace propre + ses CRD
# propres + ses ressources hors-ns explicitement attachées ; un SEUL graphe
# atomique (component_deps) est la source de vérité — il dérive l'ordre de
# montage (tri topo), de rollback (inverse) et la clôture du roundtrip.
#
# Lot 0 = CI seule : ces fonctions vivent À CÔTÉ des rollback_phase_* (rien
# retiré), prouvées par les invariants bats (bench/unit/rollback.bats). La bascule
# du rollback réel (Lot 3) et du montage (Lot 4) viendra après preuve banc.
# Périmètres VÉRIFIÉS contre le code réel (workflow consigné 2026-06-13,
# docs/audit/workflows/). Valeurs génériques banc (ADR 0023).
#
# Mêmes signatures/forme que les rollback_phase_* : case sur $1, stdout, une
# ressource/ligne. Convention « possesseur vs locataire » d'un ns partagé : SEUL
# le possesseur a component_namespace=NS ; un locataire qui dépose dans le ns
# d'autrui a ns_propre=∅ + des targeted explicites (c'est CE qui rend l'oubli
# cnpg-system structurellement impossible — ADR 0066 §Contexte).

# component_namespace COMP
#   Le (≤1) namespace que COMP POSSÈDE, ou vide s'il n'en possède aucun (racine,
#   locataire d'un ns d'autrui, ou ressource purement node-side). Invariant de
#   TRIVIALITÉ + UNICITÉ DU POSSESSEUR (un ns ↦ un seul composant).
component_namespace() {
    case "${1:-}" in
        cert-manager)     printf 'cert-manager\n' ;;
        ceph)             printf 'rook-ceph\n' ;;
        seaweedfs)        printf 's3\n' ;;
        # storage-simple : le local-path-provisioner vit dans kube-system (ns NON
        # supprimable) → ne POSSÈDE aucun ns (∅, comme metrics-server) → branche *).
        prometheus-stack) printf 'monitoring\n' ;;       # POSSESSEUR du ns monitoring
        registry)         printf 'registry\n' ;;
        cnpg-operator)    printf 'cnpg-system\n' ;;       # ≠ postgres (l'oubli historique)
        cnpg-cluster-pg)  printf 'postgres\n' ;;          # POSSESSEUR unique de postgres
        dagster)          printf 'dagster\n' ;;
        marquez)          printf 'marquez\n' ;;
        mlflow)           printf 'mlflow\n' ;;           # POSSESSEUR du ns mlflow (layer autonome)
        portal)           printf 'portal\n' ;;           # POSSESSEUR du ns portal (layer autonome)
        gitea)            printf 'gitea\n' ;;
        argocd)           printf 'argocd\n' ;;
        # ∅ : racines (bootstrap→kube-system NON supprimable, build-images,
        # metrics-server, gateway-api) ; locataires (loki, barman-plugin,
        # cnpg-secrets, s3-backing-*) ; gitops-seed (données).
        *)                printf '\n' ;;
    esac
}

# component_targeted COMP
#   Ressources CIBLÉES que COMP crée (dont dans le ns d'AUTRUI — invariant de
#   COMPLÉTUDE PAR OWNERSHIP : une OBC dans rook-ceph est un targeted de son
#   PRODUCTEUR, jamais un résidu de ceph). Une par ligne, « -n NS KIND NAME » ou
#   « KIND NAME » (cluster-scoped). Vide sinon.
component_targeted() {
    case "${1:-}" in
        cert-manager)
            printf 'clusterissuer.cert-manager.io selfsigned-bootstrap\n'
            printf 'clusterissuer.cert-manager.io internal-ca\n' ;;
        metrics-server)
            printf -- '-n kube-system deployment.apps metrics-server\n'
            printf 'apiservice.apiregistration.k8s.io v1beta1.metrics.k8s.io\n' ;;
        sc)
            printf 'storageclass.storage.k8s.io rook-ceph-block-replicated\n'
            printf 'storageclass.storage.k8s.io rook-ceph-block-ec-delete\n'
            printf 'storageclass.storage.k8s.io rook-ceph-block-ec\n'
            printf 'storageclass.storage.k8s.io rook-cephfs\n' ;;
        storage-simple)
            # SC local-path + le provisioner dans kube-system (ns non supprimable).
            printf 'storageclass.storage.k8s.io local-path\n'
            printf -- '-n kube-system deployment.apps local-path-provisioner\n' ;;
        datalake)
            printf -- '-n rook-ceph cephobjectstore.ceph.rook.io datalake\n'
            printf -- '-n rook-ceph cephobjectstoreuser.ceph.rook.io datalake\n'
            printf 'storageclass.storage.k8s.io rook-ceph-datalake\n' ;;
        loki)
            printf -- '-n monitoring statefulset.apps loki\n'
            printf -- '-n monitoring configmap loki\n'
            printf -- '-n monitoring secret loki-s3-creds\n' ;;
        s3-backing-loki)
            # OBC dans rook-ceph (ns d'autrui) → targeted du PRODUCTEUR.
            printf -- '-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets\n' ;;
        barman-plugin)
            printf -- '-n cnpg-system deployment.apps barman-cloud\n' ;;
        cnpg-cluster-pg)
            printf -- '-n postgres cluster.postgresql.cnpg.io pg\n'
            printf -- '-n postgres objectstore.barmancloud.cnpg.io pg-backup\n'
            printf -- '-n postgres scheduledbackup.postgresql.cnpg.io pg-daily\n' ;;
        s3-backing-cnpg)
            printf -- '-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups\n' ;;
        s3-backing-mlflow)
            # OBC de l'artefact store MLflow dans rook-ceph (ns d'autrui) → targeted
            # du PRODUCTEUR (n'existe QU'en Ceph ; en local-path c'est SeaweedFS, pas
            # d'OBC). component_profile=ceph le filtre hors du graphe local-path.
            printf -- '-n rook-ceph objectbucketclaim.objectbucket.io mlflow-artifacts\n' ;;
        # gitea/argocd : depuis la bascule L4 (ADR 0092) les UI sont des Services
        # NodePort dans le ns du composant (plus de HTTPRoute/Gateway — gateway.yaml
        # retirés). Ces Services sont GC par la suppression du ns que gitea/argocd
        # POSSÈDENT (component_namespace) → aucun targeted L4 à émettre.
        argocd)
            printf -- '-n argocd appproject.argoproj.io atlas\n' ;;
        gitops-seed)
            # Application `atlas-workflows` (PAS `atlas` = l'AppProject, cf. composant argocd).
            printf -- '-n argocd applications.argoproj.io atlas-workflows\n' ;;
        *) printf '\n' ;;
    esac
}

# component_crd_groups COMP
#   Groupes API dont COMP POSSÈDE les CRD (jamais ceux qu'il EMPRUNTE). Une CRD
#   PARTAGÉE (gateway.networking.k8s.io, ceph.rook.io, objectbucket.io,
#   barmancloud.cnpg.io, postgresql.cnpg.io, argoproj.io quand un autre la
#   possède) n'est listée QUE chez son possesseur — la lister chez un emprunteur
#   casserait les autres (garde-fou anti-GC partagé, invariant bats #6).
component_crd_groups() {
    case "${1:-}" in
        gateway-api)      printf 'gateway.networking.k8s.io\n' ;;  # possédé ici, EMPRUNTÉ par registry/gitea/argocd
        cert-manager)     printf 'cert-manager.io acme.cert-manager.io\n' ;;
        ceph)             printf 'ceph.rook.io objectbucket.io\n' ;; # EMPRUNTÉ par sc/datalake/s3-backing-*
        prometheus-stack) printf 'monitoring.coreos.com\n' ;;
        cnpg-operator)    printf 'postgresql.cnpg.io\n' ;;          # EMPRUNTÉ par cnpg-cluster-pg
        barman-plugin)    printf 'barmancloud.cnpg.io\n' ;;         # EMPRUNTÉ par cnpg-cluster-pg
        argocd)           printf 'argoproj.io\n' ;;                 # EMPRUNTÉ par gitops-seed
        *)                printf '\n' ;;
    esac
}

# component_has_nodeside COMP
#   "yes" si COMP laisse un état NODE-SIDE hors d'atteinte du delete k8s (disques
#   Ceph + /var/lib/rook ; images containerd du registry). Métadonnée portée même
#   si un rollback k8s-only ne le nettoie pas (banc).
component_has_nodeside() {
    case "${1:-}" in
        bootstrap | build-images | ceph) printf 'yes\n' ;;
        *)                               printf 'no\n' ;;
    esac
}

# component_profile COMP
#   Profil de stockage qui CONDITIONNE COMP (ADR 0066 : le when: vit dans le
#   composant, pas dans l'alias). always|ceph|leger.
#   - ceph  : ceph/sc/datalake/s3-backing-* (n'existent qu'en profil Ceph)
#   - leger : seaweedfs (alternative S3) + storage-simple (SC local-path), EXCLUSIFS
#             de la pile Ceph
#   - always: tout le reste
component_profile() {
    case "${1:-}" in
        ceph | sc | datalake | s3-backing-loki | s3-backing-cnpg | s3-backing-mlflow) printf 'ceph\n' ;;
        seaweedfs | storage-simple)                               printf 'leger\n' ;;
        *)                                                        printf 'always\n' ;;
    esac
}

# _rb_backend — backend de stockage du graphe (STORAGE_BACKEND, défaut ceph). Les
# arêtes de stockage sont BACKEND-CONDITIONNELLES (ADR 0069) : le « when: » vit dans
# le composant (ADR 0066). DÉFAUT ceph → graphe BYTE-IDENTIQUE à l'historique quand
# aucun env n'est exporté (bats/rollback ceph prouvé intacts). Lu via $() : la valeur
# est vue même non exportée (le subshell hérite de l'état complet du shell).
_rb_backend() {
    case "${STORAGE_BACKEND:-ceph}" in
        local-path) printf 'local-path\n' ;;
        *) printf 'ceph\n' ;;
    esac
}
# Primitive STOCKAGE BLOC résolue par backend : sc (StorageClass Ceph) | storage-simple
# (provisioner local-path). Toute arête « → SC » est une consommation de PVC bloc.
_rb_sc() { case "$(_rb_backend)" in local-path) printf 'storage-simple\n' ;; *) printf 'sc\n' ;; esac; }
# Primitive BACKING S3 résolue par backend : datalake (RGW Ceph) | seaweedfs (local-path).
_rb_s3() { case "$(_rb_backend)" in local-path) printf 'seaweedfs\n' ;; *) printf 'datalake\n' ;; esac; }

# component_deps COMP
#   Dépendances DIRECTES de COMP (séparées par des espaces) — le GRAPHE ATOMIQUE
#   UNIQUE (ADR 0066 §invariant 3). Source de vérité dont dérivent : l'ordre de
#   montage (tri topo), de rollback (inverse) et la clôture du roundtrip. Vide =
#   racine. Arêtes vérifiées contre le code (workflow consigné 2026-06-13). Les
#   arêtes de stockage (SC/S3) sont résolues par backend (ADR 0069, _rb_sc/_rb_s3).
component_deps() {
    local SC S3
    SC=$(_rb_sc)   # sc (ceph) | storage-simple (local-path)
    S3=$(_rb_s3)   # datalake (ceph) | seaweedfs (local-path)
    case "${1:-}" in
        bootstrap)        printf '\n' ;;
        build-images)     printf '\n' ;;
        gateway-api)      printf '\n' ;;
        cert-manager)     printf '\n' ;;
        metrics-server)   printf '\n' ;;
        ceph)             printf '\n' ;;
        sc)               printf 'ceph\n' ;;
        datalake)         printf 'ceph sc\n' ;;
        storage-simple)   printf '\n' ;;
        seaweedfs)        printf 'storage-simple\n' ;;
        # Arêtes « → SC » = consommation de stockage BLOC : le composant monte un PVC
        # sur la StorageClass du backend (rook-ceph-block-replicated en ceph,
        # local-path en local-path). Détruire la SC orphelinerait ces PVC → ils en
        # dépendent. (`gitea → SC` est load-bearing : seule arête qui fait entrer
        # gitops/gitops-seed dans la clôture de la SC/du socle.)
        registry)         printf 'gateway-api %s\n' "$SC" ;;
        s3-backing-loki)  printf '%s\n' "$S3" ;;
        prometheus-stack) printf 'cert-manager %s\n' "$SC" ;;
        loki)             printf 'prometheus-stack s3-backing-loki %s\n' "$SC" ;;
        cnpg-operator)    printf 'cert-manager\n' ;;
        barman-plugin)    printf 'cnpg-operator cert-manager\n' ;;
        cnpg-secrets)     printf '\n' ;;
        s3-backing-cnpg)  printf '%s\n' "$S3" ;;
        s3-backing-mlflow) printf '%s\n' "$S3" ;;
        cnpg-cluster-pg)  printf 'cnpg-operator barman-plugin cnpg-secrets s3-backing-cnpg %s\n' "$SC" ;;
        dagster)          printf 'cnpg-cluster-pg registry build-images\n' ;;
        marquez)          printf 'cnpg-cluster-pg registry build-images\n' ;;
        # MLflow (layer autonome ADR 0082, amendé) : base CNPG `mlflow` (cnpg-cluster-pg)
        # + artefact store S3 (s3-backing-mlflow, résout $S3 = datalake|seaweedfs) + une
        # IMAGE MAISON (officielle + psycopg2, le driver PostgreSQL manque à l'officielle)
        # → registry + build-images requis AVANT mlflow (push/pull registry:80/mlflow),
        # comme dagster/marquez. Le ns mlflow n'expose pas d'UI L4 dans le graphe banc.
        mlflow)           printf 'cnpg-cluster-pg s3-backing-mlflow registry build-images\n' ;;
        # Portail (layer autonome ADR 0091/0092) : image MAISON (code + contrat embarqués)
        # poussée dans le registry interne → registry + build-images requis AVANT portal
        # (push/pull registry:80/portal:dev), comme dagster/marquez/mlflow. PAS de CNPG/S3
        # (le portail n'a ni base ni stockage) ; il observe les Services des autres couches
        # à la demande — aucune arête de données vers elles (SKIP neutre si absentes).
        portal)           printf 'registry build-images\n' ;;
        gitea)            printf 'cert-manager gateway-api %s\n' "$SC" ;;
        argocd)           printf 'cert-manager gateway-api gitea\n' ;;
        gitops-seed)      printf 'argocd gitea build-images\n' ;;
        *)                printf '\n' ;;
    esac
}

# component_known COMP — 0 (vrai) si COMP est un composant atomique connu. Le
# catalogue complet sert au dispatch ET aux invariants bats (itération sur tout).
component_known() {
    case "${1:-}" in
        bootstrap | build-images | gateway-api | cert-manager | metrics-server \
            | ceph | sc | datalake | seaweedfs | storage-simple | registry \
            | s3-backing-loki | prometheus-stack | loki | cnpg-operator \
            | barman-plugin | cnpg-secrets | s3-backing-cnpg | cnpg-cluster-pg \
            | dagster | marquez | mlflow | s3-backing-mlflow | portal \
            | gitea | argocd | gitops-seed)
            return 0 ;;
        *) return 1 ;;
    esac
}

# component_all — liste de TOUS les composants atomiques (ordre lexical stable),
# pour itérer dans les invariants bats. Une source unique du catalogue.
component_all() {
    printf '%s\n' \
        bootstrap build-images gateway-api cert-manager metrics-server \
        ceph sc datalake seaweedfs storage-simple registry s3-backing-loki \
        prometheus-stack loki cnpg-operator barman-plugin cnpg-secrets \
        s3-backing-cnpg cnpg-cluster-pg dagster marquez \
        mlflow s3-backing-mlflow portal gitea argocd gitops-seed
}

# component_expand_alias ALIAS
#   L'ensemble (non ordonné, un par ligne) de composants désignés par un ALIAS de
#   phase (ADR 0066 §« Phase = alias »). Le périmètre composite n'est plus en
#   intension : c'est l'union des composants. Un alias agrégé (atlas-ceph) est la
#   clôture du graphe. Profil porté par component_profile, pas codé ici.
component_expand_alias() {
    case "${1:-}" in
        ceph)         printf '%s\n' ceph ;;
        sc)           printf '%s\n' sc ;;
        datalake)     printf '%s\n' datalake ;;
        storage-simple) printf '%s\n' storage-simple ;;
        metrics-server) printf '%s\n' metrics-server ;;
        # En local-path, monitoring pose AUSSI SeaweedFS (le backing S3 de Loki/CNPG,
        # rôle platform-seaweedfs when loki_s3_backing==seaweedfs) — le « when: » vit
        # dans l'alias (ADR 0066). En ceph l'alias est byte-identique. Le `: ;;` final
        # neutralise le rc≠0 du `[ ] &&` faux (sinon l'alias renverrait rc=1 en ceph).
        monitoring)
            printf '%s\n' prometheus-stack loki s3-backing-loki
            [ "$(_rb_backend)" = local-path ] && printf '%s\n' seaweedfs
            : ;;
        dataops)      printf '%s\n' registry cnpg-operator barman-plugin \
            cnpg-secrets s3-backing-cnpg cnpg-cluster-pg dagster marquez ;;
        # MLflow (layer AUTONOME ADR 0082) : alias = le serveur + son backing S3.
        # Le backing SeaweedFS partagé (composant `seaweedfs`) N'EST PAS dans l'alias
        # (mlflow ne le POSSÈDE pas — il vient en dépendance transitive via
        # s3-backing-mlflow → $S3). En Ceph l'alias est byte-identique.
        mlflow)       printf '%s\n' mlflow s3-backing-mlflow ;;
        # Portail (layer AUTONOME ADR 0091/0092) : alias = le seul composant `portal`
        # (pas de backing/stockage). Le ns portal est GC par la suppression du ns qu'il
        # POSSÈDE (component_namespace) → aucun targeted à émettre.
        portal)       printf '%s\n' portal ;;
        gitops)       printf '%s\n' gitea argocd ;;
        gitops-seed)  printf '%s\n' gitops-seed ;;
        # atlas-ceph = clôture Ceph SANS metrics-server (monté par l'alias léger
        # seulement, run-phases.sh) ; tie-break d'ordre fixé par topo_sort.
        atlas-ceph)   printf '%s\n' \
            bootstrap build-images gateway-api cert-manager \
            ceph sc datalake registry s3-backing-loki prometheus-stack loki \
            cnpg-operator barman-plugin cnpg-secrets s3-backing-cnpg \
            cnpg-cluster-pg dagster marquez gitea argocd gitops-seed ;;
        *)            printf '\n' ;;
    esac
}

# component_alias_weight COMP
#   Poids d'ALIAS (entier) reflétant l'ordre CODÉ des phases (atlas-ceph :
#   socle → ceph → sc → datalake → monitoring → gitops → dataops → gitops-seed).
#   Sert de tie-break PRINCIPAL dans topo_sort : entre deux composants prêts (mêmes
#   contraintes de dépendance), on émet d'abord celui du plus petit poids — ce qui
#   reproduit l'ordre codé que les seules arêtes de données ne fixent pas (ex.
#   monitoring < dataops alors que registry, dans dataops, ne dépend que du socle).
#   Workflow consigné 2026-06-13 : ce tie-break est la pré-condition du Lot 4
#   (ADR 0066) — le topo-sort doit reproduire EXACTEMENT l'ordre codé.
component_alias_weight() {
    case "${1:-}" in
        bootstrap | build-images | gateway-api | cert-manager | metrics-server) printf '0\n' ;;
        ceph)                                                                    printf '1\n' ;;
        sc | storage-simple)                                                     printf '2\n' ;;
        datalake | seaweedfs)                                                    printf '3\n' ;;
        prometheus-stack | loki | s3-backing-loki)                               printf '4\n' ;;
        gitea | argocd)                                                          printf '5\n' ;;
        registry | cnpg-operator | barman-plugin | cnpg-secrets | s3-backing-cnpg | cnpg-cluster-pg | dagster | marquez)
            printf '6\n' ;;
        gitops-seed)                                                             printf '7\n' ;;
        # MLflow (layer autonome) : APRÈS dataops/gitops (dépend de cnpg-cluster-pg,
        # poids 6) — poids 8 le place en queue, avant le repli générique (9).
        mlflow | s3-backing-mlflow)                                              printf '8\n' ;;
        # Portail (layer autonome) : EN DERNIER (il observe les UI des autres couches,
        # placé après dataops/gitops/mlflow dans les chemins) — poids 9, juste avant le
        # repli générique. Ne dépend que de registry/build-images (montés au poids 6).
        portal)                                                                  printf '9\n' ;;
        *)                                                                       printf '9\n' ;;
    esac
}

# topo_sort COMP…
#   Tri TOPOLOGIQUE pur (aucun réseau) de la sous-clôture des composants donnés,
#   via component_deps : une dépendance sort AVANT son dépendant (ordre de
#   MONTAGE ; le rollback prend l'inverse). Tie-break DÉTERMINISTE entre nœuds
#   prêts = (poids d'alias, ordre stable component_all) → reproduit l'ordre codé
#   (invariant #5) et reste reproductible (invariant #3). Détecte les cycles
#   (échoue, code 1). Kahn sur l'ensemble fermé par dépendance.
topo_sort() {
    local -a wanted=("$@")
    # Fermeture transitive : inclure toute dépendance des composants demandés.
    local -a closed=()
    local -A in_closed=()
    local -a stack=("${wanted[@]}")
    local c d
    while [ ${#stack[@]} -gt 0 ]; do
        c="${stack[0]}"; stack=("${stack[@]:1}")
        [ -n "${in_closed[$c]:-}" ] && continue
        in_closed[$c]=1; closed+=("$c")
        for d in $(component_deps "$c"); do
            [ -n "${in_closed[$d]:-}" ] || stack+=("$d")
        done
    done
    # Kahn avec tie-break par ordre stable de component_all.
    local -A indeg=() emitted=()
    for c in "${closed[@]}"; do
        indeg[$c]=0
    done
    for c in "${closed[@]}"; do
        for d in $(component_deps "$c"); do
            [ -n "${in_closed[$d]:-}" ] && indeg[$c]=$((indeg[$c] + 1))
        done
    done
    # Index stable de chaque composant (rang dans component_all) — tie-break 2ⁿᵈ.
    local -A rank=(); local i=0
    for c in $(component_all); do rank[$c]=$i; i=$((i + 1)); done
    # Kahn : à chaque pas, émettre LE meilleur nœud prêt (indeg 0), trié par
    # (poids d'alias, rang stable). Un seul à la fois → le tie-break ordonne
    # vraiment (émettre tous les prêts d'un coup perdrait l'ordre d'alias).
    local -a order=()
    local emitted_count=0 total=${#closed[@]}
    while [ "${emitted_count}" -lt "${total}" ]; do
        local best="" best_key="" w key
        for c in "${closed[@]}"; do
            [ -n "${emitted[$c]:-}" ] && continue
            [ "${indeg[$c]}" -eq 0 ] || continue
            w=$(component_alias_weight "$c")
            # Clé triable : poids (1 chiffre) puis rang (zéro-paddé 3).
            key=$(printf '%s%03d' "$w" "${rank[$c]:-999}")
            if [ -z "${best}" ] || [ "${key}" \< "${best_key}" ]; then
                best="$c"; best_key="$key"
            fi
        done
        [ -n "${best}" ] || break  # plus aucun nœud prêt → cycle (détecté plus bas)
        order+=("${best}"); emitted[${best}]=1; emitted_count=$((emitted_count + 1))
        # Décrémenter les dépendants de best.
        local x
        for x in "${closed[@]}"; do
            [ -n "${emitted[$x]:-}" ] && continue
            for d in $(component_deps "$x"); do
                [ "$d" = "${best}" ] && indeg[$x]=$((indeg[$x] - 1))
            done
        done
    done
    [ "${emitted_count}" -eq "${total}" ] || {
        printf 'topo_sort: cycle détecté (composants non ordonnables)\n' >&2
        return 1
    }
    printf '%s\n' "${order[@]}"
}

# ─── CLÔTURE PAR PHASE (dérivée du graphe — remplace roundtrip.py:_DEPENDENTS) ─
#
# roundtrip.py raisonne au grain PHASE (ceph/sc/monitoring…), pas composant. Ces
# fonctions PROJETTENT le graphe atomique sur les phases : fin de la 2ᵉ source de
# vérité (_DEPENDENTS/_MOUNT_ORDER en dur dans roundtrip.py — ADR 0066 §invariant 3).

# Les phases (alias) que roundtrip éprouve. metrics-server inclus (couche à part).
_ROUNDTRIP_PHASES="ceph sc datalake metrics-server monitoring dataops mlflow gitops gitops-seed portal"

# phase_of_component COMP — la phase (alias) qui contient COMP, ou vide si COMP est
# un composant SOCLE (bootstrap/cert-manager/gateway-api/build-images) qu'aucune
# phase roundtrip ne monte seul. Première phase de _ROUNDTRIP_PHASES qui le contient.
phase_of_component() {
    local target=${1:-} ph c
    for ph in ${_ROUNDTRIP_PHASES}; do
        for c in $(component_expand_alias "${ph}"); do
            [ "${c}" = "${target}" ] && { printf '%s\n' "${ph}"; return 0; }
        done
    done
    printf '\n'
}

# phase_closure PHASE
#   Clôture DESCENDANTE de PHASE, en ordre de MONTAGE (amont→aval) : PHASE + toute
#   phase qui en dépend (un de ses composants a une dépendance transitive sur un
#   composant de PHASE). C'est ce qu'un rollback de PHASE oblige à défaire pour
#   rester cohérent. Dérivée du graphe atomique → reproduit l'ancien _DEPENDENTS.
phase_closure() {
    local X=${1:-}
    case " ${_ROUNDTRIP_PHASES} " in *" ${X} "*) : ;; *) return 1 ;; esac
    local compsX
    compsX=" $(component_expand_alias "${X}" | tr '\n' ' ') "
    # 1. Phases Y dont un composant dépend transitivement d'un composant de X.
    local in_closure=" ${X} " Y cy seen stack c d cd
    for Y in ${_ROUNDTRIP_PHASES}; do
        [ "${Y}" = "${X}" ] && continue
        for cy in $(component_expand_alias "${Y}"); do
            # Clôture des dépendances de cy (transitive).
            seen=""; stack="${cy}"
            while [ -n "${stack}" ]; do
                c="${stack%% *}"; stack="${stack#"${c}"}"; stack="${stack# }"
                case " ${seen} " in *" ${c} "*) continue ;; esac
                seen="${seen} ${c}"
                for d in $(component_deps "${c}"); do stack="${stack} ${d}"; done
            done
            for cd in ${seen}; do
                case "${compsX}" in
                    *" ${cd} "*) in_closure="${in_closure}${Y} "; break 2 ;;
                esac
            done
        done
    done
    # 2. Ordonner par ordre de MONTAGE : topo_sort des composants de la clôture,
    #    projeté sur les phases (première apparition).
    local allcomps="" emitted="" ph
    for Y in ${in_closure}; do
        allcomps="${allcomps} $(component_expand_alias "${Y}" | tr '\n' ' ')"
    done
    # shellcheck disable=SC2086 # découpage voulu de la liste de composants
    for c in $(topo_sort ${allcomps}); do
        ph=$(phase_of_component "${c}")
        [ -n "${ph}" ] || continue
        case " ${in_closure} " in *" ${ph} "*) : ;; *) continue ;; esac
        case " ${emitted} " in *" ${ph} "*) : ;; *) emitted="${emitted} ${ph}"; printf '%s\n' "${ph}" ;; esac
    done
}

# phase_involves_storage PHASE
#   0 (vrai) si la clôture de PHASE touche une couche de STOCKAGE (ceph/sc/datalake)
#   → clôture large (≈ rebuild du socle), réservée à l'opt-in `--full` du roundtrip.
phase_involves_storage() {
    local p
    for p in $(phase_closure "${1:-}"); do
        case "${p}" in ceph | sc | datalake) return 0 ;; esac
    done
    return 1
}

# component_stuck_cr_kinds COMP…
#   Union DÉRIVÉE des kinds de CR à finalizer des composants donnés (ADR 0066 :
#   remplace _STUCK_CR_KINDS figée par une union calculée — fin d'une 2ᵉ source).
#   Un kind est « bloquant » s'il porte un finalizer qui coince une terminaison de
#   ns : OBC, CR Ceph (Cluster/ObjectStore/BlockPool/Filesystem), Cluster CNPG +
#   ObjectStore Barman. Dérivé des groupes CRD touchés par les composants (propres
#   ou empruntés). Sortie triée → déterministe (invariant #3).
component_stuck_cr_kinds() {
    local c group
    {
        for c in "$@"; do
            for group in $(component_crd_groups "$c"); do
                case "${group}" in
                    objectbucket.io)
                        printf '%s\n' obc.objectbucket.io ;;
                    ceph.rook.io)
                        printf '%s\n' cephcluster.ceph.rook.io \
                            cephobjectstore.ceph.rook.io cephblockpool.ceph.rook.io \
                            cephfilesystem.ceph.rook.io ;;
                    postgresql.cnpg.io)
                        printf '%s\n' cluster.postgresql.cnpg.io ;;
                    barmancloud.cnpg.io)
                        printf '%s\n' objectstore.barmancloud.cnpg.io ;;
                    argoproj.io)
                        # Argo CD : Application + AppProject portent un finalizer
                        # (resources-finalizer.argocd.argoproj.io) que le contrôleur, en
                        # train de mourir avec son ns, ne traite plus → ns `argocd` wedgé
                        # en Terminating (cas vécu). On les force au teardown du banc.
                        printf '%s\n' application.argoproj.io appproject.argoproj.io ;;
                esac
            done
            # Producteurs d'OBC (s3-backing-*) EMPRUNTENT objectbucket.io sans le
            # posséder (crd_groups vide chez eux) → ajouter leur kind bloquant.
            case "$c" in
                s3-backing-loki | s3-backing-cnpg) printf '%s\n' obc.objectbucket.io ;;
            esac
        done
    } | sort -u | paste -sd' ' -
}

# ─── PRIMITIVES kubectl/ssh (NON pures — réseau) ────────────────────────────
# Attendent KUBECTL/vm_sh/log/ok/die/retry de run-phases.sh/lib.sh (sourcées).

# Kinds de CR connus pour bloquer une terminaison de ns par leurs finalizers
# (banc jetable : on les force). Inclut le `Cluster` CNPG ET son `ObjectStore`
# Barman (plugin barman-cloud) — ce dernier coinçait `postgres` en Terminating ;
# et les CR Argo CD (Application/AppProject, finalizer resources-finalizer.argocd…)
# — l'AppProject `atlas` coinçait `argocd` en Terminating (cas vécu, #372).
# (component_stuck_cr_kinds DÉRIVE la même union par composant, ADR 0066 ; cette liste
# reste l'amorce utilisée par k8s_force_delete_ns au grain PHASE — garder les deux alignées.)
_STUCK_CR_KINDS="obc.objectbucket.io objectbucket.io cephcluster.ceph.rook.io \
cephobjectstore.ceph.rook.io cephblockpool.ceph.rook.io cephfilesystem.ceph.rook.io \
cluster.postgresql.cnpg.io objectstore.barmancloud.cnpg.io \
application.argoproj.io appproject.argoproj.io"

# k8s_force_delete_ns NS…
#   Supprime chaque namespace, en FORÇANT les finalizers récalcitrants (banc
#   jetable : on ne ménage pas les deadlocks, ADR 0054 §2). delete non bloquant ;
#   si le ns reste en Terminating, force les finalizers des CR coincés PUIS finalise
#   le ns via le sous-ressource /finalize (le patch du ns ne suffit pas pour un
#   ns déjà Terminating). CONTINUE sur les ns suivants même si l'un échoue (un échec
#   isolé ne doit pas abandonner le reste de la clôture) ; échoue à la fin si résidus.
k8s_force_delete_ns() {
    local ns failed=""
    for ns in "$@"; do
        "${KUBECTL[@]}" get ns "${ns}" > /dev/null 2>&1 || continue
        log "  rollback : suppression du namespace ${ns} (force finalizers si bloqué)"
        "${KUBECTL[@]}" delete ns "${ns}" --wait=false --ignore-not-found > /dev/null 2>&1 || true
        if retry 10 2 _ns_absent "${ns}"; then continue; fi
        # Pods coincés en Terminating (conteneur encore running — ex. pod CNPG dont
        # l'opérateur ne confirme plus l'arrêt) : ils BLOQUENT la finalisation du ns.
        # On les supprime de force (#361 — cas vécu : pg-1 1/2 Terminating 40 min).
        "${KUBECTL[@]}" -n "${ns}" delete pods --all --force --grace-period=0 \
            > /dev/null 2>&1 || true
        # Forcer les finalizers des CR coincés (OBC, CR Rook/CNPG/Barman).
        local kind
        for kind in ${_STUCK_CR_KINDS}; do
            "${KUBECTL[@]}" -n "${ns}" get "${kind}" -o name 2> /dev/null \
                | while read -r res; do
                    "${KUBECTL[@]}" -n "${ns}" patch "${res}" --type merge \
                        -p '{"metadata":{"finalizers":[]}}' > /dev/null 2>&1 || true
                done
        done
        # Finaliser le ns : retirer spec.finalizers via /finalize (fix canonique
        # d'un ns coincé en Terminating ; un patch simple est ignoré à ce stade).
        _ns_force_finalize "${ns}"
        retry 30 2 _ns_absent "${ns}" || failed="${failed} ${ns}"
    done
    [ -z "${failed}" ] || die "rollback : namespace(s) non supprimé(s) :${failed} (finalizers résiduels ?)"
}
_ns_absent() { ! "${KUBECTL[@]}" get ns "$1" > /dev/null 2>&1; }

# _ns_force_finalize NS — retire spec.finalizers du ns via le sous-ressource
# /finalize (la seule voie pour débloquer un ns déjà en Terminating). Best-effort.
_ns_force_finalize() {
    local ns=$1 tmp
    tmp=$("${KUBECTL[@]}" get ns "${ns}" -o json 2> /dev/null | jq 'del(.spec.finalizers)' 2> /dev/null) || return 0
    [ -n "${tmp}" ] || return 0
    printf '%s' "${tmp}" \
        | "${KUBECTL[@]}" replace --raw "/api/v1/namespaces/${ns}/finalize" -f - > /dev/null 2>&1 || true
}

# k8s_delete_targeted "LIGNES"
#   Supprime des ressources ciblées (une par ligne, forme « -n NS KIND NAME » ou
#   « KIND NAME » cluster-scoped). --ignore-not-found, force finalizers si bloqué.
k8s_delete_targeted() {
    local line
    while IFS= read -r line; do
        [ -n "${line}" ] || continue
        log "  rollback : suppression ${line}"
        # shellcheck disable=SC2086 # découpage voulu des champs de la ligne
        "${KUBECTL[@]}" delete ${line} --ignore-not-found --wait=false > /dev/null 2>&1 || true
        # Forcer les finalizers si la ressource traîne (CR Rook/OBC).
        # shellcheck disable=SC2086
        "${KUBECTL[@]}" patch ${line} --type merge \
            -p '{"metadata":{"finalizers":[]}}' > /dev/null 2>&1 || true
    done <<EOF
${1}
EOF
}

# k8s_delete_crd GROUP…
#   Supprime les CRD d'un groupe API (ex. ceph.rook.io) — ce qui GC les CR
#   restants. À jouer APRÈS les namespaces (les CR vivent dans des ns).
k8s_delete_crd() {
    local group crd
    for group in "$@"; do
        "${KUBECTL[@]}" get crd -o name 2> /dev/null \
            | grep -E "\.${group}$" | while read -r crd; do
                log "  rollback : suppression CRD ${crd#customresourcedefinition.apiextensions.k8s.io/}"
                "${KUBECTL[@]}" delete "${crd}" --ignore-not-found --wait=false > /dev/null 2>&1 || true
            done
    done
}

# phase_rollback PHASE
#   Défait une phase montée (ADR 0054). Garde BANC_JETABLE=1 + cible banc. Ordre
#   inverse : refuse si une phase aval est encore présente. Efface ns + CRD +
#   node-side (Ceph). DESTRUCTIF TOTAL (données comprises).
phase_rollback() {
    local phase=$1
    [ "${BANC_JETABLE:-0}" = 1 ] || die "rollback DESTRUCTIF (efface données) — exiger BANC_JETABLE=1 sur un banc jetable"
    rollback_known_phase "${phase}" || die "rollback : phase inconnue '${phase}' (ceph|sc|datalake|metrics-server|monitoring|dataops|gitops|gitops-seed)"
    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent — banc non monté ?"

    # Garde-fou d'ordre : aucune phase AVAL encore présente.
    local downstream present="" d verdict
    downstream=$(rollback_phase_downstream "${phase}")
    for d in ${downstream}; do
        _phase_present "${d}" && present="${present} ${d}"
    done
    verdict=$(classify_downstream_block "${phase}" "${present# }")
    case "${verdict%%|*}" in
        ok) : ;;
        *) die "${verdict#*|}" ;;
    esac

    log "Rollback de la phase '${phase}' (BANC_JETABLE — destructif total)"
    # 1. Ressources CIBLÉES (phases sans ns propre : datalake/sc/metrics/seed).
    local targeted; targeted=$(rollback_phase_targeted_resources "${phase}")
    [ -n "${targeted}" ] && k8s_delete_targeted "${targeted}"
    # 2. Namespaces (force finalizers) — phases qui possèdent leur ns.
    local ns_list; ns_list=$(rollback_phase_namespaces "${phase}")
    # shellcheck disable=SC2086
    [ -n "${ns_list}" ] && k8s_force_delete_ns ${ns_list}
    # 3. CRD du groupe (GC les CR) — seul ceph.
    local crd_groups; crd_groups=$(rollback_phase_crd_groups "${phase}")
    # shellcheck disable=SC2086
    [ -n "${crd_groups}" ] && k8s_delete_crd ${crd_groups}
    # 3. Node-side (disques Ceph + /var/lib/rook) — seul `ceph` en a.
    if [ "$(rollback_phase_has_nodeside "${phase}")" = yes ]; then
        local entry vm
        for entry in "${NODES[@]}"; do
            vm="${entry%%:*}"
            log "  rollback : wipe node-side sur ${vm} (cleanup.sh, disques + /var/lib/rook)"
            NVME_BLOCK_DEVICE=/dev/vde DATA_DEVICE_GLOB='/dev/vd[b-d]' SKIP_REBOOT=1 \
                vm_sh "${vm}" sudo env NVME_BLOCK_DEVICE=/dev/vde DATA_DEVICE_GLOB='/dev/vd[b-d]' SKIP_REBOOT=1 \
                bash -s < "${REPO}/storage/ceph/cleanup.sh" || warn "${vm} : cleanup.sh node-side a renvoyé une erreur (résidu ?)"
        done
    fi
    ok "Rollback '${phase}' terminé — re-monter avec : bench/lima/run-phases.sh ${phase}"
}

# _phase_present PHASE — prédicat best-effort : la phase aval est-elle montée ?
# Réutilise les prédicats de présence de phase_status (ceph_present, etc.).
_phase_present() {
    case "$1" in
        sc) sc_default_present ;;
        datalake) "${KUBECTL[@]}" -n rook-ceph get cephobjectstore datalake > /dev/null 2>&1 ;;
        wordpress) "${KUBECTL[@]}" get pvc -A 2> /dev/null | grep -q wordpress ;;
        gitops-seed) "${KUBECTL[@]}" -n argocd get applications.argoproj.io atlas-workflows > /dev/null 2>&1 ;;
        *) return 1 ;;
    esac
}
