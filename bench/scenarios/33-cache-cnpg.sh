#!/usr/bin/env bash
#
# Scénario 33 — CACHE CNPG : la brique « cache partagé des flux atlas » servie par
# RÉUTILISATION de CloudNativePG (ADR 0093) tient-elle ses PRIMITIVES ?
#
# ADR 0093 tranche : pas de Redis — le cache est une base logique `cache` de plus
# sur le Cluster `pg` (ADR 0024), avec un rôle managé `cache` et le Secret
# pg-role-cache. Le SQL de l'adaptateur (table clé-valeur horodatée, UPSERT
# atomique, pg_advisory_lock) vit côté ATLAS (frontière, §5 ADR — hors ce dépôt).
# Ce scénario ne prouve donc PAS un cache applicatif complet, mais les PRIMITIVES
# Postgres que l'adaptateur utilisera, depuis un pod éphémère intra-cluster :
#
#   1. CONNEXION : le rôle `cache` se connecte à la base `cache` (preuve que
#      base + rôle + Secret existent et sont cohérents — un rôle managé sans
#      passwordSecret aurait rolpassword NULL, connexion impossible).
#   2. UPSERT ATOMIQUE : INSERT ... ON CONFLICT (key) DO UPDATE sur une table
#      clé-valeur de test → après N upserts d'une même clé, UNE SEULE ligne
#      (atomicité « dernier écrivain gagne », garantie par le moteur, pas le code,
#      ADR atlas 0040). La table de test est DROPée à la fin (ne pas polluer).
#   3. PG_ADVISORY_LOCK : pg_try_advisory_lock(k) → true la 1re fois ; une 2e
#      session NE l'obtient PAS tant qu'il est tenu (false), puis l'obtient après
#      pg_advisory_unlock — le verrou distribué / dédup en vol qu'une `Promise`
#      locale ne peut offrir entre répliques (ADR 0093 §2).
#
# Le psql tourne dans un POD ÉPHÉMÈRE (kubectl run --rm, image postgres pinnée du
# dépôt) car la base n'est joignable qu'en intra-cluster (NetworkPolicy + réseau
# pods). Le mot de passe est lu du Secret pg-role-cache et passé par PGPASSWORD
# (env), JAMAIS en clair dans la ligne de commande ni journalisé.
#
# DNS — nom COURT `pg-rw.postgres`, jamais le FQDN *.svc.cluster.local (ADR 0093 :
# un search domain externe fait timeouter le FQDN complet en prod). Le pod résout
# le nom court via son `search` namespace.
#
# SKIP NEUTRE (exit 0) si la brique cache n'est pas montée (base `cache` ou Secret
# pg-role-cache absent — profil sans cache) — SAUF STRICT_CACHE=1 (CI banc atlas).
#
# Pré-requis : kubectl + un banc avec le Cluster CNPG (profil dataops, ADR 0085).
# Variables :
#   STRICT_CACHE=1   échoue (au lieu de skip) si la brique cache est absente
#   PG_NS            (défaut postgres) — namespace du Cluster CNPG + Secret
#   CACHE_DB         (défaut cache) — base logique du cache
#   CACHE_HOST       (défaut pg-rw.postgres) — Service rw (nom COURT)
#   CACHE_PORT       (défaut 5432)
#   UPSERTS          (défaut 5) — nombre d'upserts concourants de la même clé
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# shellcheck source=bench/scenarios/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

STRICT_CACHE=${STRICT_CACHE:-0}
PG_NS=${PG_NS:-postgres}
CACHE_DB=${CACHE_DB:-cache}
CACHE_HOST=${CACHE_HOST:-pg-rw.postgres}
CACHE_PORT=${CACHE_PORT:-5432}
UPSERTS=${UPSERTS:-5}
SECRET=pg-role-cache
# Image psql = celle déjà pinnée par le dépôt pour les init-containers pg_isready
# des chaînes dagster/marquez/mlflow (digest d'index multi-arch, ADR 0006).
PG_IMAGE=docker.io/library/postgres:14.6@sha256:f565573d74aedc9b218e1d191b04ec75bdd50c33b2d44d91bcd3db5f2fcea647

skip_or_fail() {
    if [ "${STRICT_CACHE}" = 1 ]; then
        log "✗ STRICT_CACHE=1 et prérequis manquant : $1"
        exit 1
    fi
    log "skip — $1 (profil sans cache CNPG ; cf. platform/cloudnative-pg/, ADR 0093)."
    exit 0
}

# ── Pré-requis : la brique cache est-elle montée ? ───────────────────────────
kubectl get ns "${PG_NS}" >/dev/null 2>&1 \
    || skip_or_fail "namespace ${PG_NS} absent (Cluster CNPG non monté)"
kubectl -n "${PG_NS}" get secret "${SECRET}" >/dev/null 2>&1 \
    || skip_or_fail "Secret ${PG_NS}/${SECRET} absent (rôle cache non provisionné)"

# Lit username/password du Secret (basic-auth). Le password reste en variable,
# n'est JAMAIS imprimé et est passé au pod par PGPASSWORD (env), pas en argument.
CACHE_USER=$(kubectl -n "${PG_NS}" get secret "${SECRET}" \
    -o jsonpath='{.data.username}' 2>/dev/null | base64 -d 2>/dev/null)
CACHE_PASS=$(kubectl -n "${PG_NS}" get secret "${SECRET}" \
    -o jsonpath='{.data.password}' 2>/dev/null | base64 -d 2>/dev/null)
[ -n "${CACHE_USER}" ] && [ -n "${CACHE_PASS}" ] \
    || skip_or_fail "Secret ${SECRET} sans clés username/password exploitables"

log "Cache CNPG : base ${CACHE_DB} @ ${CACHE_HOST}:${CACHE_PORT}, rôle ${CACHE_USER} (ADR 0093)."

# Exécute du SQL dans un pod éphémère intra-cluster via psql. Le mot de passe est
# injecté par variable d'env (--env PGPASSWORD), jamais en clair sur la ligne de
# commande. Renvoie la sortie psql (-tA : tuples-only, non aligné) sur stdout.
TABLE="cache_probe_$$"
psql_run() {
    local sql=$1
    kubectl -n "${PG_NS}" run "cache-probe-$$-${RANDOM}" --rm -i --restart=Never \
        --image="${PG_IMAGE}" --quiet --timeout=60s \
        --env="PGPASSWORD=${CACHE_PASS}" -- \
        psql -h "${CACHE_HOST}" -p "${CACHE_PORT}" -U "${CACHE_USER}" \
        -d "${CACHE_DB}" -v ON_ERROR_STOP=1 -tA -c "${sql}" 2>/dev/null
}

# Nettoyage : la table de test est DROPée même si une étape échoue (ne pas polluer
# la base `cache` du banc). Best-effort — la base peut être muette à ce stade.
# shellcheck disable=SC2329  # invoquée via trap EXIT
cleanup() {
    psql_run "DROP TABLE IF EXISTS ${TABLE};" >/dev/null 2>&1 || true
}
trap cleanup EXIT

fails=0

# ── 1. Connexion : rôle cache → base cache ───────────────────────────────────
log "[1/3] connexion du rôle ${CACHE_USER} à la base ${CACHE_DB}"
who=$(psql_run "SELECT current_user || '/' || current_database();")
if [ "${who}" = "${CACHE_USER}/${CACHE_DB}" ]; then
    log "✓ connecté : ${who} (base + rôle + Secret cohérents)"
else
    log "✗ connexion échouée ou identité inattendue : « ${who:-<vide>} »"
    log "  (attendu ${CACHE_USER}/${CACHE_DB} — vérifier passwordSecret du rôle managé)"
    fails=$((fails + 1))
    # Sans connexion, les épreuves suivantes n'ont pas de sens.
    if [ "${fails}" -gt 0 ]; then
        echo
        if [ "${STRICT_CACHE}" = 1 ]; then
            log "✗ STRICT_CACHE=1 : connexion impossible (voir ci-dessus)."
            exit 1
        fi
        log "✗ connexion au cache impossible — abandon (la brique n'est pas saine)."
        exit 1
    fi
fi

# ── 2. UPSERT atomique : une seule ligne par clé après N upserts ─────────────
log "[2/3] UPSERT atomique (INSERT ... ON CONFLICT DO UPDATE), ${UPSERTS}× la même clé"
# Table clé-valeur horodatée minimale (le SCHÉMA réel vit dans l'adaptateur atlas).
psql_run "CREATE TABLE IF NOT EXISTS ${TABLE} (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now());" >/dev/null
# N upserts de la MÊME clé : le 1er insère, les suivants mettent à jour (ON
# CONFLICT). À la fin, exactement UNE ligne pour cette clé (atomicité du moteur).
for i in $(seq 1 "${UPSERTS}"); do
    psql_run "INSERT INTO ${TABLE} (key, value, saved_at)
        VALUES ('flux:demo', jsonb_build_object('n', ${i}), now())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, saved_at = EXCLUDED.saved_at;" >/dev/null
done
rows=$(psql_run "SELECT count(*) FROM ${TABLE} WHERE key = 'flux:demo';")
last=$(psql_run "SELECT value->>'n' FROM ${TABLE} WHERE key = 'flux:demo';")
if [ "${rows}" = 1 ] && [ "${last}" = "${UPSERTS}" ]; then
    log "✓ une seule ligne après ${UPSERTS} upserts, value->>'n' = ${last} (dernier écrivain gagne)"
else
    log "✗ UPSERT non atomique : ${rows:-?} ligne(s), dernière valeur « ${last:-?} » (attendu 1 / ${UPSERTS})"
    fails=$((fails + 1))
fi

# ── 3. pg_advisory_lock : verrou consultatif (dédup en vol / verrou distribué) ─
log "[3/3] pg_advisory_lock — verrou consultatif inter-sessions"
# Une clé de verrou dérivée (bigint) ; l'adaptateur atlas la dérive du nom du
# cache. On ouvre DEUX sessions psql concourantes (deux pods éphémères) :
#   - S1 prend le verrou (pg_advisory_lock) et le TIENT pendant qu'on sonde S2 ;
#   - S2 tente pg_try_advisory_lock → DOIT échouer (false) tant que S1 le tient ;
#   - S1 libère, S2 réessaie → DOIT réussir (true). Le verrou est bien distribué.
LOCKKEY=424242

# S1 : prend le verrou, dort le temps qu'on sonde S2, puis le verrou tombe à la
# fin de la session (un advisory lock de session se libère à la déconnexion).
kubectl -n "${PG_NS}" run "cache-lock-hold-$$" --restart=Never \
    --image="${PG_IMAGE}" --quiet \
    --env="PGPASSWORD=${CACHE_PASS}" -- \
    psql -h "${CACHE_HOST}" -p "${CACHE_PORT}" -U "${CACHE_USER}" \
    -d "${CACHE_DB}" -v ON_ERROR_STOP=1 -tA \
    -c "SELECT pg_advisory_lock(${LOCKKEY});" \
    -c "SELECT pg_sleep(20);" >/dev/null 2>&1 &
# shellcheck disable=SC2329  # invoquée via trap EXIT
lock_cleanup() {
    kubectl -n "${PG_NS}" delete pod "cache-lock-hold-$$" --wait=false >/dev/null 2>&1 || true
}
trap 'cleanup; lock_cleanup' EXIT
# Laisser S1 acquérir le verrou avant de sonder.
sleep 8

# S2 (pendant que S1 tient) : pg_try_advisory_lock DOIT renvoyer false.
held=$(psql_run "SELECT pg_try_advisory_lock(${LOCKKEY});")
if [ "${held}" = f ]; then
    log "✓ verrou tenu par S1 : pg_try_advisory_lock(2e session) → false"
else
    log "✗ pg_try_advisory_lock(2e session) = « ${held:-?} » (attendu f — verrou non exclusif ?)"
    fails=$((fails + 1))
fi

# Libérer S1 (supprimer le pod détenteur → session fermée → verrou relâché).
lock_cleanup
trap cleanup EXIT
# Attendre la fin effective de la session détentrice côté serveur.
sleep 6

# S3 : le verrou est libre → pg_try_advisory_lock DOIT réussir (true), puis on
# libère proprement (pg_advisory_unlock) dans la même session.
freed=$(psql_run "SELECT pg_try_advisory_lock(${LOCKKEY}) AND pg_advisory_unlock(${LOCKKEY});")
if [ "${freed}" = t ]; then
    log "✓ verrou relâché : pg_try_advisory_lock → true, pg_advisory_unlock → true"
else
    log "✗ verrou non récupérable après libération : « ${freed:-?} » (attendu t)"
    fails=$((fails + 1))
fi

echo
if [ "${fails}" -eq 0 ]; then
    log "🎉 cache CNPG OK — connexion + UPSERT atomique + advisory lock (primitives ADR 0093)."
else
    log "✗ ${fails} vérification(s) en échec — voir ci-dessus."
    exit 1
fi
