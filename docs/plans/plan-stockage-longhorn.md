# Plan d'implémentation — Longhorn, 3ᵉ profil de stockage (ADR 0064)

## État

> **État : Brouillon** (depuis 2026-06-13) · **Fonde :
> [ADR 0064](../decisions/0064-longhorn-option-stockage-catalogue.md)**
> (Proposed) · **Issue :
> [#324](https://github.com/univ-lehavre/cluster/issues/324)** · **Pas
> d'implémentation active** tant que l'ADR n'est pas `Accepted`
> ([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) §6).

Met en œuvre [ADR 0064](../decisions/0064-longhorn-option-stockage-catalogue.md)
: ajouter **Longhorn** comme troisième profil de stockage du catalogue, entre
`local-path` (jetable, zéro résilience) et `ceph` (unifié, datalake). Ce plan
est le **comment** ; la décision (le **pourquoi**) est dans l'ADR. Il reste en
`Brouillon` — **aucune PR de code** ne part tant que l'ADR 0064 est `Proposed`.

## Principe d'architecture

Décliner le **patron existant des deux profils** (`local-path`, `ceph`) pour un
troisième, sans inventer de mécanique nouvelle :

- **Manifeste vendored figé** dans `storage/longhorn/`, à l'image de
  `storage/local-path/local-path-storage.yaml` et `storage/ceph/*` — exclu de
  prettier/yamllint/jscpd (bundle upstream), images **épinglées par digest
  d'index multi-arch**
  ([ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md), le
  banc est arm64).
- **Rôle Ansible** `platform-longhorn` calqué sur `platform-local-path` :
  applique le manifeste figé via `kubernetes.core.k8s` (jamais de `.j2`), attend
  le manager `Ready`, **pose exactement une StorageClass par défaut**
  (`longhorn`), défauts génériques
  ([ADR 0023](../decisions/0023-plateforme-exemple-generique.md)).
- **Profil de déploiement** : une variable `WITH_LONGHORN` (ou un profil nommé
  `longhorn`) dans `test/lima/run-phases.sh`, symétrique de `WITH_CEPH`, qui
  bascule la StorageClass par défaut et dimensionne la VM (réplication ×2/×3
  exige ≥ 2-3 nœuds — la topologie de référence `multi-node-3` convient).
- **Stockage composé** : si le profil Longhorn a besoin d'objet S3 (Loki,
  backups CNPG), il réutilise **SeaweedFS** exactement comme le profil
  `local-path` ([ADR 0036](../decisions/0036-backing-s3-unique-rgw.md)) — pas de
  RGW (qui exige Ceph).

```bash
# Symétrie visée avec les profils existants :
test/lima/run-phases.sh storage-simple          # local-path
WITH_CEPH=1     test/lima/run-phases.sh ceph     # Rook-Ceph
WITH_LONGHORN=1 test/lima/run-phases.sh longhorn # Longhorn (cible de ce plan)
```

## Périmètre — ce que Longhorn fait / ne fait pas (ADR 0064)

| Aspect              | Décision                                                            |
| ------------------- | ------------------------------------------------------------------- |
| Bloc RWO/RWX        | ✅ réplication ×2/×3 synchrone                                      |
| Objet S3            | ❌ — 2ᵉ brique (SeaweedFS/MinIO) si besoin (ADR 0036)               |
| Datalake prod       | ❌ — reste Ceph (ADR 0018 intouché)                                 |
| Nœuds minimum       | 2-3 (réplication réelle) — topologie `multi-node-3`                 |
| StorageClass défaut | `longhorn`, **une seule à la fois** (bascule comme local-path↔Ceph) |

## Découpage en lots (issues)

> Tous **gelés** tant que l'ADR 0064 n'est pas `Accepted`. Le lot 0 est le seul
> qui peut avancer sous `Proposed` (il sert à **acter** l'ADR).

0. **Acter l'ADR** — revue de l'ADR 0064 + ce plan ; passage
   `Proposed → Accepted` ; bascule de cet en-tête `Brouillon → Actif`.
   (Pré-requis de tous les autres lots, ADR 0057 §6.)
1. **Manifeste vendored** — `storage/longhorn/longhorn.yaml` (bundle upstream
   figé, images pinnées par digest multi-arch ADR 0006), exclusions
   prettier/yamllint/jscpd, `.trivyignore.yaml` pour le RBAC inhérent avec
   justification par chemin. + `storage/longhorn/RUNBOOK.md` (install,
   diagnostic, désinstallation), dans le style du RUNBOOK Ceph.
2. **Rôle Ansible** `platform-longhorn` (calqué sur `platform-local-path`) :
   applique le manifeste, attend `Ready`, pose la SC par défaut (exactement
   une), défauts génériques ADR 0023. + playbook `bootstrap/longhorn.yaml`.
3. **Profil banc** — `WITH_LONGHORN` / phase `longhorn` dans
   `test/lima/run-phases.sh` (symétrique `WITH_CEPH`), dimensionnement VM,
   bascule SC par défaut. Fonctions pures testables **bats** si logique non
   triviale ([ADR 0017](../decisions/0017-langage-des-scripts.md)).
4. **Rollback** — `rollback longhorn` dans le dispatch existant
   ([plan-rollback-par-phase.md](plan-rollback-par-phase.md) / ADR 0054) :
   namespace `longhorn-system`, CRD `longhorn.io`, PVC, node-side
   (`/var/lib/longhorn`). À garder en phase avec ce que le rôle crée.
5. **Preuve de banc** (ADR 0034/0052) — run e2e : monte `longhorn` → PVC
   répliqué → **tue un nœud, vérifie la survie I/O** → remonte. Consigner un
   cycle dans `test/lima/RESULTS.md`. **Sans ce run, le profil reste déclaré
   mais non prouvé.**
6. **Doc** — câbler le profil dans la doc : `docs/composants.md` (pile briques),
   `docs/architecture/decisions-stockage.md` (bilan 3 options — déjà rédigé),
   `docs/outils.md` (catalogue de commandes),
   `docs/architecture/matrice-catalogue.md` (Longhorn passe de « potentiel » à «
   profil activable »).

## Validation

`pnpm lint` (format, yamllint, shellcheck, kubeconform, ansible-lint, jscpd,
bats), `pnpm docs:build` (liens morts), **markdownlint** et **trivy** (jobs CI
séparés, à reproduire localement). Conventional Commits sujet minuscule, hooks
lefthook jamais bypassés, merge commit (chaque commit propre). Un lot = une PR,
re-prouvée sur banc avant la suivante (ADR 0034).

## Suivi (ADR 0057)

Issue de pilotage : [#324](https://github.com/univ-lehavre/cluster/issues/324)
(les lots ci-dessous y sont des cases à cocher).

| Lot                                    | État                                                           |
| -------------------------------------- | -------------------------------------------------------------- |
| 0. Acter l'ADR 0064 (`Accepted`)       | 🔲 à faire — débloque tout le reste (ADR 0057 §6)              |
| 1. Manifeste vendored + RUNBOOK        | 🔲 gelé tant que 0064 `Proposed`                               |
| 2. Rôle `platform-longhorn` + playbook | 🔲 gelé                                                        |
| 3. Profil banc (`WITH_LONGHORN`)       | 🔲 gelé                                                        |
| 4. Rollback `longhorn`                 | 🔲 gelé                                                        |
| 5. Preuve de banc (`RESULTS.md`)       | 🔲 gelé — survie à la perte d'un nœud (ADR 0034/0052)          |
| 6. Doc (composants, bilan, matrice)    | 🟡 partiel — bilan 3 options posé dans `decisions-stockage.md` |

**Achèvement** : quand les lots 1-6 sont livrés sur `main` et le run de preuve
consigné, l'en-tête `## État` passe **Achevé**. Le passage **Brouillon → Actif**
intervient au lot 0 (acceptation de l'ADR 0064).
