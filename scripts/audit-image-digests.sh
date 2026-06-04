#!/usr/bin/env bash
#
# Audit des images épinglées par digest : vérifie que CHAQUE `@sha256:` versionné
# pointe un INDEX multi-arch (application/vnd.{oci.image.index|docker…manifest.list})
# et NON un manifeste single-arch — invariant ADR 0006.
#
# Motivation (#140) : un digest pris sur le manifeste amd64 au lieu de l'index
# passe inaperçu tant que le banc est amd64, puis casse en `exec format error`
# sur arm64. Ce script débusque ces digests AVANT qu'ils n'atteignent un nœud
# arm64.
#
# Usage : scripts/audit-image-digests.sh
# Sortie : liste les images NON-index (exit 1 si au moins une), sinon « OK ».
# Pré-requis : docker (manifest inspect), jq, git.
#
# Note : `docker manifest inspect` interroge le registre distant → réseau requis.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "${HERE}/.." && pwd)
cd "${REPO}"

command -v jq > /dev/null || { echo "jq requis" >&2; exit 2; }

# Inspecteur de MediaType : `crane` (plus rapide/fiable) s'il est présent, sinon
# `docker manifest inspect` (toujours dispo, aucun outil à installer). `mediatype`
# affiche le mediaType du manifeste référencé par le digest.
if command -v crane > /dev/null; then
    inspect_mediatype() { crane manifest "$1" 2> /dev/null | jq -r '.mediaType // empty' || true; }
    INSPECTOR=crane
elif command -v docker > /dev/null; then
    inspect_mediatype() { docker manifest inspect "$1" 2> /dev/null | jq -r '.mediaType // empty' || true; }
    INSPECTOR="docker manifest inspect"
else
    echo "crane OU docker requis" >&2
    exit 2
fi

# MediaTypes considérés comme des INDEX multi-arch (acceptés).
INDEX_TYPES=(
    'application/vnd.oci.image.index.v1+json'
    'application/vnd.docker.distribution.manifest.list.v2+json'
)

# Toutes les images `…:tag@sha256:…` des YAML VERSIONNÉS (git ls-files → ignore
# node_modules, artefacts gitignorés, etc.). Uniques. (Boucle `while read` plutôt
# que `mapfile` : compatible bash 3.2, le bash par défaut de macOS.)
images=$(
    git ls-files -z -- '*.yaml' '*.yml' \
        | xargs -0 grep -hoE 'image: *"?[a-zA-Z0-9._/-]+:[a-zA-Z0-9._-]+@sha256:[0-9a-f]{64}' 2> /dev/null \
        | sed -E 's/image: *"?//' \
        | sort -u
)

n=$(printf '%s\n' "${images}" | grep -c .)
echo "Audit de ${n} image(s) épinglée(s) par digest (invariant index multi-arch, ADR 0006)…"
echo "Inspecteur : ${INSPECTOR}"
echo

fail=0
while IFS= read -r img; do
    [ -n "${img}" ] || continue
    # MediaType du digest épinglé (le manifeste réellement référencé).
    # Un inspect en échec (réseau/auth) ne tue pas l'audit (la fonction renvoie
    # vide) — on le traite comme « illisible » plus bas.
    mt=$(inspect_mediatype "${img}")
    if [ -z "${mt}" ]; then
        printf '  ?  %-90s (mediaType illisible — réseau ? auth ?)\n' "${img}"
        continue
    fi
    if printf '%s\n' "${INDEX_TYPES[@]}" | grep -qxF "${mt}"; then
        printf '  ✓  %-90s %s\n' "${img%@*}" "${mt##*.}"
    else
        printf '  ✗  %-90s %s  ← SINGLE-ARCH, attendu un index !\n' "${img%@*}" "${mt}"
        fail=1
    fi
done <<< "${images}"

echo
if [ "${fail}" -eq 0 ]; then
    echo "OK — toutes les images épinglées pointent un index multi-arch."
else
    echo "ÉCHEC — au moins un digest pointe un manifeste single-arch (cf. ✗ ci-dessus)." >&2
    echo "Correctif : ré-épingler sur le digest d'INDEX (docker buildx imagetools inspect <ref> --format '{{.Manifest.Digest}}')." >&2
fi
exit "${fail}"
