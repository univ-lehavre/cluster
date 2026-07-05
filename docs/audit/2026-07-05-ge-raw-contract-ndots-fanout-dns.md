# Passage d'audit — `ge_raw_contract` : « Could not resolve hostname » (amplification ndots)

> **Type** : passage d'audit ciblé, issu d'un **workflow multi-agents**
> ([ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md) /
> [0078](../decisions/0078-passages-audit-famille-unique.md)) — 4 hypothèses
> adversariales en parallèle + synthèse (source primaire cpp-httplib). Pas la
> grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : après une **ingestion complète RÉUSSIE** (raw_snapshot
> STEP_SUCCESS en 3h34m), le contrat qualité `ge_raw_contract` (asset check
> DuckDB) échoue en `_duckdb.IOException: Could not resolve hostname` — alors
> que rclone venait de résoudre **le même endpoint** 3h34m sans erreur. Run
> `c1d30af4`, prod dirqual.
>
> **Enjeu** : c'est le dernier verrou avant l'**uplift prédictif**. Un mauvais
> diagnostic (ex. « DNS cassé » → changer l'endpoint) aurait empiré le problème.
>
> **Consigné aussi** comme drifts [L74](../architecture/registre-drifts.md) (le
> bug) et [L75](../architecture/registre-drifts.md) (l'artefact d'index RGW de
> diagnostic). Raffine [L58](../architecture/registre-drifts.md) (piège FQDN
> prod).

## Réponse — la cause n'est PAS un DNS cassé

**Le nom résout parfaitement.** Mesuré depuis un pod dagster :
`rook-ceph-rgw-datalake.rook-ceph` → `10.97.223.85` (glibc, 3 formes OK). Le bug
est une **amplification** `ndots:5` × **HEAD-par-fichier**, qui **sature** le
DNS sous volume — pas un nom irrésolvable.

### Le mécanisme, à la source primaire

1. **`ndots:5`** (défaut k8s) : un host à `< 5` points est traité comme
   **relatif** → `getaddrinfo` parcourt **toute la search-list** avant la forme
   absolue. Le fix [#550](https://github.com/univ-lehavre/atlas/pull/550) (drift
   L58) a raccourci l'endpoint DuckDB au **nom court ns-qualifié**
   `rook-ceph-rgw-datalake.rook-ceph` (**1 point** < 5) → il retombe **dans** le
   fan-out : 5-6 lookups par résolution, incluant les domaines **externes** du
   `resolv.conf` (`tahr-boga.ts.net`, `dix.univ-lehavre.fr`).
2. **DuckDB httpfs = `getaddrinfo` glibc, PAS c-ares** — vérifié à la source :
   httpfs passe par **cpp-httplib**, dont le seul hook DNS est `getaddrinfo`
   (aucune référence c-ares ; c-ares est le résolveur de **gRPC**, pas de
   httpfs). L'image est `python:3.10-slim` = Debian/glibc, **le même résolveur
   que rclone**. La mémoire projet « c-ares timeoute le FQDN » (workspace
   Dagster/gitea, gRPC) a été **indûment généralisée** à DuckDB.
3. **HEAD-par-fichier** : `check_raw` fait
   `read_json_auto('s3://…/raw/works/**/*.gz', union_by_name=true)` — un glob
   récursif qui force un **HTTP HEAD par objet** sur des milliers de
   `part_*.gz`, chacun ouvrant un client neuf → un `getaddrinfo` neuf. **Ampli
   ×5-6 × milliers de HEAD** → CoreDNS/conntrack sature → **`EAI_AGAIN`
   transitoires** rapportés « Could not resolve hostname ». L'erreur tombe sur
   `part_0949.gz`, loin dans le glob → **intermittent**, pas déterministe
   (signature de saturation, pas d'un nom irrésolvable).

### Pourquoi rclone a réussi et pas DuckDB

**Même résolveur (glibc), régime d'accès opposé.** rclone **réutilise ses
connexions** (keep-alive) → une poignée de `getaddrinfo`, sous le seuil. DuckDB
en glob fait un HEAD-par-fichier en éventail → des milliers de `getaddrinfo`
neufs. Ce n'est **pas** une divergence de config dbt vs lakehouse (la parité de
[#550](https://github.com/univ-lehavre/atlas/pull/550) tient : les deux
calculent le même endpoint) — c'est le **volume**.

## Le fix retenu — `ndots:1` sur les pods de run

`dnsConfig: {options: [{name: ndots, value: "1"}]}` via `pod_spec_config` du tag
`dagster-k8s/config`, sur **ingestion ET transform** (constante `_DNS_NDOTS_1`
partagée, `definitions.py`). Tout nom ≥ 1 point est tenté **en absolu d'abord**
→ **1 lookup**, aucune search-list. Bénéficie à **tous** les accès DNS du pod
(DuckDB, S3, Postgres).
[atlas#551](https://github.com/univ-lehavre/atlas/pull/551), 3 tests, 42 verts.

**Préféré au FQDN-absolu (trailing dot)** — l'autre fix candidat (émettre
`…svc.cluster.local.` avec point final) était plus ciblé mais **non prouvé** (un
client S3 path-style strict pourrait rejeter le `.` dans l'ENDPOINT, ou casser
la signature S3 v4). `ndots:1` est sans ce risque et couvre tout le pod.

## Ce qui reste incertain (honnêteté ADR 0052)

- **La saturation CoreDNS/conntrack n'est pas observée directement** — le
  mécanisme (fan-out × HEAD × race A/AAAA) est cohérent avec **tous** les faits
  et la source primaire, mais le compteur exact de lookups/drops n'a pas été
  relevé sur ce run.
- **Le fix reste à RE-PROUVER par un run** : rejouer `ge_raw_contract` en prod
  après rebuild + re-seed, et vérifier **0** « Could not resolve hostname ». Un
  test unitaire ne suffit pas — c'est un phénomène de **charge** (ADR 0052 : le
  réel prouve, pas la déduction).

## Notes de méthode (pièges rencontrés)

- **Le `list_objects_v2` boto SOUS-COMPTE** (2446 objets) après une grosse
  ingestion → aurait fait croire « ingestion ratée ». Le **réel** est dans
  `ceph df` : pool `datalake.rgw.buckets.data` = **691 GiB / 261k objets**
  (artefact d'index RGW, drift L75). _Croiser deux sondes ; le pool ne ment
  pas._
- **Tester DuckDB sur le pod de prod l'a OOM-killé 2×** (exit 137) — DuckDB en
  glob est gourmand et le pod code-location a des ressources serrées. _Arrêté de
  stresser la prod ; fait confiance au raisonnement + à la mesure Ceph._
