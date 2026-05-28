// VitePress configuration for the cluster docs site.
//
// We keep all README/RUNBOOK files colocated with the code they document and
// surface them here via srcDir=.. + sidebar, so there is a single browsable
// site without moving files.
import { defineConfig } from 'vitepress'

export default defineConfig({
  srcDir: '..',
  // Le site est publié sur https://univ-lehavre.github.io/cluster/ via le
  // workflow .github/workflows/docs.yml ; en dev local (`pnpm docs:dev`),
  // VITEPRESS_BASE peut être laissé vide pour servir depuis /.
  base: process.env.VITEPRESS_BASE ?? '/cluster/',
  title: 'Cluster',
  description: 'Cluster Kubernetes hyperconvergé — Debian 13, Cilium, Rook-Ceph',
  lang: 'fr-FR',
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true,

  srcExclude: [
    'node_modules/**',
    '.git/**',
    '.github/**',
    '**/CHANGELOG.md',
    '**/LICENSE.md',
    'docs/.vitepress/**',
  ],

  // Map every README.md to its directory's index.md so URLs like /test/,
  // /bootstrap/, /storage/ceph/ resolve cleanly.
  rewrites: (id) => {
    if (id === 'README.md') return 'index.md'
    if (id.endsWith('/README.md')) return id.replace(/README\.md$/, 'index.md')
    return id
  },

  themeConfig: {
    nav: [
      { text: 'Accueil', link: '/' },
      { text: 'Plan', link: '/PLAN' },
      { text: 'Banc de test', link: '/test/' },
    ],
    sidebar: [
      {
        text: "Vue d'ensemble",
        items: [
          { text: 'Accueil', link: '/' },
          { text: 'Plan de reconstruction', link: '/PLAN' },
          { text: 'Inventaire matériel', link: '/platform/hardware' },
        ],
      },
      {
        text: 'Bootstrap Kubernetes',
        items: [
          { text: "Vue d'ensemble", link: '/bootstrap/' },
          { text: 'Runbook installation', link: '/bootstrap/RUNBOOK' },
        ],
      },
      {
        text: 'Durcissement OS',
        items: [
          { text: "Vue d'ensemble (server-security)", link: '/bootstrap/security/' },
          { text: 'Implications par couche', link: '/bootstrap/security/IMPLICATIONS' },
          { text: 'Roadmap sécurité', link: '/bootstrap/security/TODO' },
        ],
      },
      {
        text: 'Stockage Rook-Ceph',
        items: [
          { text: "Vue d'ensemble", link: '/storage/ceph/' },
          { text: 'Runbook Ceph', link: '/storage/ceph/RUNBOOK' },
          { text: 'StorageClasses', link: '/storage/ceph/storageClass/' },
          { text: 'CephFS', link: '/storage/ceph/storageClass/filesystem/' },
          { text: 'Datalake (S3)', link: '/storage/ceph/storageClass/datalake/' },
          { text: 'Exemple WordPress', link: '/storage/ceph/wordpress/' },
        ],
      },
      {
        text: 'Plateforme',
        items: [
          { text: 'Container Registry', link: '/platform/container-registry/' },
          { text: 'Dashboard Kubernetes', link: '/platform/k8s-dashboard/' },
        ],
      },
      {
        text: 'Applications',
        items: [{ text: 'RStudio', link: '/apps/rstudio/' }],
      },
      {
        text: 'Banc de test (VirtualBox)',
        items: [
          { text: "Vue d'ensemble", link: '/test/' },
          { text: 'Mono-nœud (Phase 1-2)', link: '/test/single-node/' },
          { text: 'Multi-nœuds (Phase 1-5 + Ceph)', link: '/test/multi-node/' },
        ],
      },
      {
        text: 'Décisions (ADR)',
        items: [
          { text: 'Index', link: '/docs/decisions/' },
          {
            text: '0010 — Dashboard cluster-admin',
            link: '/docs/decisions/0010-dashboard-cluster-admin',
          },
          {
            text: '0011 — Registry HTTP sans auth',
            link: '/docs/decisions/0011-registry-http-sans-auth',
          },
          {
            text: '0012 — RStudio sans auth',
            link: '/docs/decisions/0012-rstudio-disable-auth',
          },
        ],
      },
    ],
    search: { provider: 'local' },
    outline: { label: 'Sur cette page', level: [2, 3] },
    docFooter: { prev: 'Précédent', next: 'Suivant' },
    darkModeSwitchLabel: 'Apparence',
    sidebarMenuLabel: 'Menu',
    returnToTopLabel: 'Retour en haut',
    lastUpdated: { text: 'Dernière mise à jour' },
    editLink: {
      pattern: 'https://github.com/pochasset/cluster/edit/main/:path',
      text: 'Modifier cette page sur GitHub',
    },
  },
})
