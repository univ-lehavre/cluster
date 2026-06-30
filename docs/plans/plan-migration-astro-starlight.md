# Plan — Migration de la documentation : VitePress → Astro Starlight

## État

> **État : Achevé** (migration livrée — le site est servi par Astro Starlight :
> `package.json` (`astro build`, `@astrojs/starlight`), `docs/astro.config.mjs`,
> VitePress retiré). · **Fonde :
> [ADR 0089](../decisions/0089-migration-doc-vitepress-astro-starlight.md)**
> (Accepted) · **S'inspire de** l'ADR 0036 d'atlas (mêmes patterns).
>
> Mise en œuvre **incrémentale, plusieurs PR**, chacune verte. VitePress est
> resté fonctionnel jusqu'à la bascule finale (étape 6), désormais faite.

## Objectif

Remplacer VitePress 1.6.4 par Astro Starlight (ADR 0089) pour : éteindre les **5
GHSA transitives** (devDeps VitePress), **aligner sur atlas**, **découpler de
Vite**. Sans régression : mêmes URL (`/cluster/`), français, `editLink`,
recherche locale, invariant ADR 0029 (tout `.md` atteignable).

## Périmètre mesuré (audit 2026-06-21)

| Métrique              | Valeur            | Point dur                                |
| --------------------- | ----------------- | ---------------------------------------- |
| Fichiers `.md` servis | ~199              | dont colocalisés hors `docs/` (README…)  |
| ADR / audits / archi  | 88 / 32 / 15      | `docs/`                                  |
| Liens internes        | ~3006             | à revalider (validateur bloquant)        |
| Entrées sidebar       | 99 (12 groupes)   | transcription / autogenerate             |
| `srcDir: '..'`        | colocation totale | **le nœud dur** (collection glob)        |
| Garde-fous Python     | 4                 | `check_md_orphans.py` parse `config.mjs` |
| Containers / Mermaid  | 0 / 0             | corps `.md` migre quasi 1:1 (0 image)    |

## Principe directeur

**Reprendre les patterns atlas (ADR 0036), pas réinventer.** Source de référence
: `atlas/docs/astro.config.mjs`, `atlas/docs/src/content.config.ts`,
`atlas/docs/package.json`, `atlas/.github/workflows/docs.yml`. Adapter
`base: '/cluster/'`, la sidebar, et la collection glob aux zones colocalisées de
cluster.

**Invariants non négociables** (sinon migration cassée — observés chez atlas) :

1. Ordre des intégrations Astro : `mermaid` < `starlight` < `mdx`.
2. i18n monolingue : un seul locale `root` (PAS `defaultLocale` → sinon 404 en
   `/fr/`).
3. `starlight-links-validator` bloquant, avec `exclude` des routes non
   introspectables + `errorOnLocalLinks: false`.
4. README colocalisés lus **en place** via collection `glob` (`base: '..'`) —
   pas de copie (source unique, ADR 0023).
5. Artefacts volatils (`dist/`, `.astro/`) gitignorés.

## Étapes (chacune une PR verte, prouvée)

### Étape 1 — POC config Astro (le point dur d'abord)

Monter `docs/` Astro minimal **à côté** de VitePress (sans le supprimer) :
`astro.config.mjs` (base `/cluster/`, Starlight, vue, mdx, validateur),
`package.json` doc, `content.config.ts` avec **une collection `glob`** prouvant
la lecture **en place** d'un README colocalisé (ex. `bootstrap/README.md`) + 2-3
pages `docs/`. **Preuve** : `astro build` vert localement, le README colocalisé
rendu sous `/cluster/...`. Valide le `srcDir='..'` → collection glob.

### Étape 2 — Contenu `docs/` (le gros volume, sans colocation)

Migrer les ~147 `.md` de `docs/` (ADR, audits, architecture, plans, guides) dans
la collection Starlight : ajouter le frontmatter `title:` requis, adapter
`docs/index.md` (`layout: home` → page splash Starlight). **Preuve** :
`astro build` vert, `starlight-links-validator` passe sur les liens internes à
`docs/`.

### Étape 3 — Colocation : README/RUNBOOK hors `docs/`

Généraliser la collection `glob` à toutes les zones colocalisées (`bootstrap/`,
`storage/`, `platform/*/`, `apps/`, `bench/`, `contract/`). Mapper les routes
pour préserver les URL actuelles. **Preuve** : tous les `.md` colocalisés
rendus, liens depuis/vers `docs/` valides.

### Étape 4 — Sidebar + nav + i18n

Transcrire la sidebar (99 entrées, 12 groupes) en config Starlight
(`autogenerate` par dossier là où l'arborescence s'y prête, manuel sinon) ; nav,
`editLink`, social, labels français. **Preuve** : navigation identique à
VitePress (revue visuelle), tous les groupes présents.

### Étape 5 — Garde-fous Python

Réécrire [`check_md_orphans.py`](../../scripts/check_md_orphans.py) pour lire la
config Starlight (sidebar + collections) au lieu de `config.mjs` ; re-vérifier
`check_gouvernance.py`, `render_drifts.py`, `check_contract.py`. **Preuve** :
`pnpm lint:docs-orphans` vert sur le site Astro ; invariant ADR 0029 maintenu.

### Étape 6 — Bascule workflow + suppression VitePress

Basculer [`docs.yml`](../../.github/workflows/docs.yml) sur `astro build`
(artifact `docs/dist/`) ; retirer `vitepress` + `docs/.vitepress/` ; mettre à
jour les scripts `docs:*` du `package.json`. **Preuve** : déploiement Pages
vert, site live identique, **`pnpm audit` sans les 5 GHSA**, check Scorecard
`Vulnerabilities` rétabli au prochain run.

## Vérification (transverse, chaque étape)

- `astro build` (ou `pnpm docs:build`) vert + `starlight-links-validator` sans
  lien mort.
- Garde-fous CI conservés : `prettier`, `markdownlint`, `lychee` (le temps de la
  transition), `check_md_orphans.py` (dès l'étape 5).
- Aucune valeur réelle introduite (ADR 0023) ; commits Conventional, minuscules.

## Risques & parades

- **Régression de liens (~3006)** → `starlight-links-validator` bloquant +
  `lychee` conservé jusqu'à l'étape 6.
- **Colocation** → prouvée dès l'étape 1 (POC) avant tout volume.
- **Big-bang** → exclu : 6 étapes, VitePress vivant jusqu'au bout.

## Suivi

| Étape                                  | État       |
| -------------------------------------- | ---------- |
| 1. POC config Astro                    | ✅ achevée |
| 2. Contenu `docs/`                     | ✅ achevée |
| 3. Colocation README/RUNBOOK           | ✅ achevée |
| 4. Sidebar + nav + i18n                | ✅ achevée |
| 5. Garde-fous Python                   | ✅ achevée |
| 6. Bascule workflow + suppr. VitePress | ✅ achevée |

**Issues rattachées** : aucune. Migration **livrée** — le site est servi par
Astro Starlight (`pnpm docs:build` + `starlight-links-validator` bloquant),
VitePress retiré. Le plan reste versionné comme trace.
