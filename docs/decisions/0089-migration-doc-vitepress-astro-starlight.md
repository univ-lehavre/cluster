# 0089 — Migration de la documentation : VitePress → Astro Starlight

## Statut

Accepted (proposé le 2026-06-21) — migration **livrée** : le site est servi par
Astro Starlight (`package.json` : `astro build`, `@astrojs/starlight` ;
`docs/astro.config.mjs`), VitePress retiré. Mise en œuvre suivie par
[`plan-migration-astro-starlight.md`](../plans/plan-migration-astro-starlight.md)
(Achevé).

S'inspire de
l'[ADR 0036 d'atlas](https://univ-lehavre.github.io/atlas/decisions/0036-migration-vitepress-astro-starlight/)
(même décision, même outil), **sans en reprendre le contexte** : le déclencheur
de cluster est différent (cf. ci-dessous).

## Contexte

La documentation de cluster est construite avec **VitePress 1.6.4**
([`docs/.vitepress/config.mjs`](../../docs/.vitepress/config.mjs)), publiée sur
GitHub Pages ([`docs.yml`](../../.github/workflows/docs.yml)). Trois faits
fondent le besoin de migrer — **dans l'ordre de priorité réel pour cluster** :

1. **Vulnérabilités transitives non corrigeables sans bump majeur.** Le scan OSV
   (OpenSSF Scorecard `Vulnerabilities`) remonte **5 GHSA** — toutes des
   `devDependencies` transitives de VitePress 1.x : `esbuild@0.21.5`
   (GHSA-67mh-4wv8-2f99), `js-yaml@4.1.1` (GHSA-h67p-54hq-rp68), `vite@5.4.21`
   (GHSA-4w7w-66w2-5vf9, GHSA-fx2h-pf6j-xcff), `launch-editor`
   (GHSA-v6wh-96g9-6wx3). Les correctifs vivent en **`vite@6+` /
   `esbuild@0.25+`**, que VitePress 1.x **ne peut pas tirer** (il fige
   `vite@5`). Le risque réel est faible (devDeps du site de doc, jamais
   déployées sur le cluster, dev server local) — mais la dette est
   **structurelle** : tant qu'on reste en VitePress 1, le check
   `Vulnerabilities` reste dégradé et aucun `pnpm.overrides` propre n'existe
   (forcer `vite@6` sous VitePress 1 casse le build).

2. **Cohérence avec atlas.** Le dépôt applicatif a déjà migré vers **Astro
   Starlight** (ADR 0036 atlas). Maintenir **deux moteurs documentaires** dans
   l'écosystème de l'organisation (VitePress ici, Astro là) double la charge de
   maintenance, les conventions et les garde-fous. Aligner cluster sur atlas
   unifie la chaîne doc.

3. **Découplage de la chaîne Vite (résilience future).** Astro embarque son
   propre Vite **interne** (non exposé en peer) : la doc sort définitivement des
   conflits de version Vite que tout futur bump pourrait provoquer. C'est la
   raison **principale** côté atlas (apps SvelteKit sur Vite 8) ; côté cluster
   elle est **secondaire** (pas d'app Vite dans ce dépôt), mais reste un acquis.

Les sorties par épinglage sont **écartées**, comme côté atlas :

- **VitePress 2** est en **alpha** (`2.0.0-alpha.17` au 2026-06-21, `latest`
  reste `1.6.4`) : passer la chaîne doc de prod sur une pré-release est exclu.
- **`pnpm.overrides` forçant `vite@6`/`esbuild@0.25` sous VitePress 1.6.4**
  casse le build (VitePress 1 cible une API Vite 5).

## Décision

> **La documentation de cluster migre de VitePress vers Astro Starlight**, en
> reprenant les patterns éprouvés par atlas (ADR 0036) — adaptés au profil
> spécifique de cluster.

Le profil de cluster impose **trois adaptations** par rapport à atlas (qui
conditionnent le plan de mise en œuvre) :

- **Colocation `srcDir: '..'` massive.** cluster sert **~199 fichiers `.md`**
  dispersés dans tout le dépôt (88 ADR + 32 audits dans `docs/`, mais aussi les
  `README`/`RUNBOOK` colocalisés avec le code : `bootstrap/`, `storage/ceph/`,
  `platform/*/`, `apps/`, `bench/`, `contract/`). Astro attend tout sous
  `docs/src/content/docs/`. La parade est le pattern atlas : une **content
  collection `glob` avec `base: '..'`** qui lit les `README` **en place**
  (source unique, pas de copie) — généralisée ici à toutes les zones
  colocalisées.
- **Sidebar manuelle de 99 entrées** (12 groupes). atlas s'appuie sur
  `autogenerate` par dossier ; cluster devra **soit** ranger l'arborescence pour
  autogénérer, **soit** transcrire la sidebar manuellement. Tranché dans le
  plan.
- **Quatre garde-fous Python liés au format VitePress.**
  [`check_md_orphans.py`](../../scripts/check_md_orphans.py) (ADR 0029 —
  Markdown atteignable) **parse `config.mjs`** ; il devra lire la config
  Starlight. Les autres (`check_gouvernance.py`, `render_drifts.py`,
  `check_contract.py`) sont à re-vérifier.

Atouts du contenu existant (migration facilitée) : **0 container VitePress
(`:::`)**, **0 diagramme Mermaid**, **0 image locale** → le corps des `.md`
migre quasi 1:1. La difficulté est **structurelle** (config, colocation, liens,
garde-fous), pas rédactionnelle.

Le `starlight-links-validator` (bloquant au build) **remplace et durcit** la
validation de liens (aujourd'hui partagée entre `ignoreDeadLinks` VitePress et
le job `lychee`) : il maintient l'invariant ADR 0029 directement dans le build
doc.

La migration est **progressive, en plusieurs PR**, chacune verte et prouvée ;
VitePress reste fonctionnel jusqu'à la bascule finale du workflow et la
suppression de la dépendance. Le séquençage détaillé vit dans le plan.

## Conséquences

**Positif :**

- Les **5 GHSA transitives s'éteignent** (Astro tire `vite@6+`/`esbuild@0.25+`)
  → check Scorecard `Vulnerabilities` rétabli.
- **Un seul moteur doc** dans l'organisation (cluster + atlas) → conventions,
  garde-fous et montée de version mutualisés.
- **Doc découplée de Vite** → plus de fragilité au bump.
- Validation de liens **bloquante au build** (anti-dérive ADR 0029 renforcé).

**Coût / risques :**

- **Chantier conséquent** (~199 `.md`, ~3006 liens internes, 4 garde-fous, 99
  entrées de sidebar) — d'où la mise en œuvre **incrémentale** plutôt qu'un
  big-bang.
- **Régression de liens** possible : mitigée par le `starlight-links-validator`
  (bloquant) + `lychee` conservé en CI le temps de la transition.
- **`check_md_orphans.py` à réécrire** : dépendance au format de config change.
- Dépendances doc renouvelées (`astro`, `@astrojs/starlight`, `@astrojs/vue`,
  `@astrojs/mdx`) épinglées selon
  [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md).

**Neutre :**

- Le base URL (`/cluster/`), le français (locale `root`), l'`editLink` GitHub et
  la recherche locale (PageFind côté Starlight) sont **préservés** à l'identique
  pour l'utilisateur.

## Voir aussi

- [Plan de migration](../plans/plan-migration-astro-starlight.md) — séquençage
  en étapes prouvables.
- [ADR 0036 atlas](https://univ-lehavre.github.io/atlas/decisions/0036-migration-vitepress-astro-starlight/)
  — la décision sœur (mêmes patterns : collection glob, Mermaid, Vue).
- [ADR 0029](0029-markdown-atteignable-doc.md) — invariant « tout `.md`
  atteignable » que le validateur de liens Starlight reprendra.
- [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md) — épinglage des
  dépendances.
