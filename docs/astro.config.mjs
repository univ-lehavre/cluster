// @ts-check
import { defineConfig } from 'astro/config'
import starlight from '@astrojs/starlight'
import starlightLinksValidator from 'starlight-links-validator'
import mdx from '@astrojs/mdx'

// Migration VitePress → Astro Starlight (ADR 0089). base URL, français et
// editLink GitHub préservés à l'identique pour ne casser aucune URL entrante.
// Publié sur https://univ-lehavre.github.io/cluster/ via docs.yml ; en dev local,
// ASTRO_BASE peut être vide pour servir depuis /.
export default defineConfig({
  site: 'https://univ-lehavre.github.io',
  base: process.env.ASTRO_BASE ?? '/cluster/',
  integrations: [
    starlight({
      title: 'Cluster',
      // i18n monolingue : un seul locale `root` (PAS defaultLocale + locales.fr,
      // qui servirait les pages sous /fr/ → 404). Observé chez atlas (ADR 0036).
      locales: {
        root: { label: 'Français', lang: 'fr' },
      },
      // Validation des liens internes BLOQUANTE au build (remplace ignoreDeadLinks
      // VitePress) : maintient l'invariant ADR 0029 (tout .md atteignable).
      plugins: [
        starlightLinksValidator({
          errorOnLocalLinks: false,
          // Les pages COLOCALISÉES (README/RUNBOOK lus en place) sont servies par
          // src/pages/[...slug].astro — une route dynamique que le validateur ne
          // sait pas introspecter (comme /atlas/packages/** chez atlas). On les
          // exclut donc de la validation (leurs liens sortants restent validés,
          // eux, car les fichiers sources sont dans la collection `colocated`).
          exclude: [
            '/cluster/apps/**',
            '/cluster/bench/**',
            '/cluster/bootstrap/**',
            '/cluster/contract/**',
            '/cluster/platform/**',
            '/cluster/storage/**',
            '/cluster/CLAUDE/',
            '/cluster/CODE_OF_CONDUCT/',
            '/cluster/CONTRIBUTING/',
            '/cluster/SAFEGUARDS/',
            '/cluster/SECURITY/',
          ],
        }),
      ],
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/univ-lehavre/cluster' },
      ],
      editLink: {
        baseUrl: 'https://github.com/univ-lehavre/cluster/edit/main/',
      },
      // Sidebar transcrite fidèlement de l'ancien config.mjs VitePress (12
      // groupes). Les liens sont SANS le base /cluster/ : Starlight l'ajoute
      // automatiquement (à l'inverse des liens dans le contenu Markdown, qui
      // l'incluent). Trailing slash pour les pages (cohérent build Astro).
      sidebar: [
        {
          label: 'Comprendre',
          items: [
            { label: 'Accueil', link: '/' },
            { label: 'Documentation transverse', link: '/docs/' },
            { label: 'Manifeste (le récit)', link: '/docs/manifeste/' },
            { label: 'Preuves de qualité', link: '/docs/preuves/' },
            { label: 'Composants (la pile)', link: '/docs/composants/' },
            { label: 'Glossaire', link: '/docs/glossaire/' },
          ],
        },
        {
          label: 'Faire',
          items: [
            { label: 'Par où commencer', link: '/docs/demarrage/' },
            { label: 'Se brancher sur la plateforme', link: '/docs/se-brancher/' },
            { label: 'Monter le banc local', link: '/docs/banc-local/' },
            { label: 'Boîte à outils (scripts)', link: '/docs/outils/' },
            { label: 'Référence dev data (endpoints)', link: '/docs/guide-dev-data/' },
            { label: 'Développeur atlas (point d’entrée)', link: '/docs/dev-atlas/' },
            { label: 'Garde-fous', link: '/SAFEGUARDS/' },
            { label: 'Contribuer', link: '/CONTRIBUTING/' },
            { label: 'Inventaire matériel', link: '/platform/hardware/' },
          ],
        },
        {
          label: 'Bootstrap Kubernetes',
          items: [
            { label: "Vue d'ensemble", link: '/bootstrap/' },
            { label: 'Runbook installation', link: '/bootstrap/RUNBOOK/' },
          ],
        },
        {
          label: 'Durcissement OS',
          items: [
            { label: "Vue d'ensemble (server-security)", link: '/bootstrap/security/' },
            { label: 'Implications par couche', link: '/bootstrap/security/IMPLICATIONS/' },
            { label: 'Roadmap sécurité', link: '/bootstrap/security/TODO/' },
          ],
        },
        {
          label: 'Stockage Rook-Ceph',
          items: [
            { label: "Vue d'ensemble", link: '/storage/ceph/' },
            { label: 'Runbook Ceph', link: '/storage/ceph/RUNBOOK/' },
            { label: 'StorageClasses', link: '/storage/ceph/storageClass/' },
            { label: 'CephFS', link: '/storage/ceph/storageClass/filesystem/' },
            { label: 'Datalake (S3)', link: '/storage/ceph/storageClass/datalake/' },
            { label: 'Exemple WordPress', link: '/storage/ceph/wordpress/' },
            { label: 'Sauvegarde (VolumeSnapshots)', link: '/storage/ceph/backup/' },
          ],
        },
        {
          label: 'Plateforme',
          items: [
            { label: 'Container Registry', link: '/platform/container-registry/' },
            { label: 'Dashboard Kubernetes', link: '/platform/k8s-dashboard/' },
            {
              label: 'Chaîne DataOps (accès & vérifs)',
              link: '/docs/architecture/chaine-dataops/',
            },
            { label: 'Contrat cluster → atlas', link: '/contract/' },
          ],
        },
        {
          label: 'Applications',
          items: [
            { label: 'RStudio', link: '/apps/rstudio/' },
            { label: 'REDCap', link: '/apps/redcap/' },
          ],
        },
        {
          label: 'Banc de test (Lima)',
          items: [
            { label: "Vue d'ensemble", link: '/bench/' },
            { label: 'Banc Lima (multi-nœuds)', link: '/bench/lima/' },
            { label: 'Journal des runs Lima (courant)', link: '/bench/lima/RESULTS/' },
            { label: 'Historique Vagrant (déprécié)', link: '/bench/RESULTS/' },
            { label: 'Scénarios reproductibles', link: '/bench/scenarios/' },
          ],
        },
        {
          label: 'Architecture & preuves',
          collapsed: true,
          items: [
            { label: 'Preuves de qualité', link: '/docs/preuves/' },
            { label: "Vues d'architecture (index)", link: '/docs/architecture/' },
            { label: 'Matrice du catalogue', link: '/docs/architecture/matrice-catalogue/' },
            { label: 'Validation sur banc', link: '/docs/architecture/validation-banc/' },
            { label: 'Leçons des runs', link: '/docs/architecture/lecons-des-runs/' },
            { label: 'Registre des drifts', link: '/docs/architecture/registre-drifts/' },
            { label: 'Plan de tests', link: '/docs/architecture/plan-de-tests/' },
            { label: 'Bonnes pratiques', link: '/docs/architecture/bonnes-pratiques/' },
            { label: 'Chaîne DataOps', link: '/docs/architecture/chaine-dataops/' },
            { label: 'Exposition réseau', link: '/docs/architecture/exposition-reseau/' },
          ],
        },
        {
          label: 'Décisions (ADR)',
          collapsed: true,
          items: [
            { label: 'Index des ADR', link: '/docs/decisions/' },
            { label: 'Stockage & données', link: '/docs/architecture/decisions-stockage/' },
            { label: 'Plan de contrôle', link: '/docs/architecture/decisions-plan-de-controle/' },
            { label: 'Sécurité & accès', link: '/docs/architecture/decisions-securite-acces/' },
            {
              label: 'Plateforme & GitOps',
              link: '/docs/architecture/decisions-plateforme-gitops/',
            },
            {
              label: 'Conventions & outillage',
              link: '/docs/architecture/decisions-conventions-outillage/',
            },
          ],
        },
        {
          label: 'Audit',
          collapsed: true,
          items: [
            { label: 'Grille & passages', link: '/docs/audit/' },
            {
              label: '1 — Bonnes pratiques IaC',
              link: '/docs/audit/2026-05-29/01-bonnes-pratiques/',
            },
            { label: '2 — Tests multi-niveaux', link: '/docs/audit/2026-05-29/02-tests/' },
            { label: '3 — Lint & chaîne qualité', link: '/docs/audit/2026-05-29/03-lint-format/' },
            { label: '4 — Documentation', link: '/docs/audit/2026-05-29/04-documentation/' },
            { label: '5 — Reproductibilité', link: '/docs/audit/2026-05-29/05-reproductibilite/' },
            { label: '6 — Sécurité', link: '/docs/audit/2026-05-29/06-securite/' },
            { label: '7 — Gouvernance', link: '/docs/audit/2026-05-29/07-gouvernance/' },
            {
              label: '8 — Opérabilité & résilience',
              link: '/docs/audit/2026-05-29/08-operabilite/',
            },
            {
              label: '9 — Langage des scripts',
              link: '/docs/audit/2026-05-29/09-langage-scripts/',
            },
            { label: '10 — Dispersion vs CLI', link: '/docs/audit/2026-05-29/10-dispersion-cli/' },
            {
              label: '11 — Logiciels open source',
              link: '/docs/audit/2026-05-29/11-logiciels-oss/',
            },
            { label: "12 — Plan d'action", link: '/docs/audit/2026-05-29/12-plan-action/' },
          ],
        },
        {
          label: 'Plans & audits de session',
          collapsed: true,
          items: [
            { label: 'Index & convention', link: '/docs/plans/' },
            {
              label: 'Modèle déclaratif des topologies',
              link: '/docs/plans/plan-modele-declaratif/',
            },
            { label: 'Dagster (orchestration)', link: '/docs/plans/plan-dagster/' },
            { label: 'Marquez (lineage)', link: '/docs/plans/plan-marquez/' },
            {
              label: 'nestor pilote la prod (lecture)',
              link: '/docs/plans/plan-nestor-pilote-prod/',
            },
            { label: 'Rollback par phase', link: '/docs/plans/plan-rollback-par-phase/' },
            { label: 'Audit des conventions', link: '/docs/plans/plan-audit-conventions/' },
            {
              label: 'Migration doc → Astro Starlight',
              link: '/docs/plans/plan-migration-astro-starlight/',
            },
            { label: 'Refonte documentaire', link: '/docs/plans/plan-refonte-doc/' },
            {
              label: 'Audit — réalignement Dagster ↔ main',
              link: '/docs/plans/2026-06-04-audit-realignement-main-dagster/',
            },
          ],
        },
      ],
    }),
    mdx(),
  ],
})
