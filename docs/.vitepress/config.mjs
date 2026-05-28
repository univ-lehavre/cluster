// VitePress configuration for the cluster docs site.
//
// We keep all README/RUNBOOK files colocated with the code they document and
// surface them here via srcDir=.. + sidebar, so there is a single browsable
// site without moving files.
import { defineConfig } from 'vitepress'

export default defineConfig({
  srcDir: '..',
  title: 'Cluster',
  description: 'Cluster Kubernetes hyperconvergé — Debian 13, Cilium, Rook-Ceph',
  lang: 'fr-FR',
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true,

  srcExclude: ['node_modules/**', '.git/**', '.github/**', 'CHANGELOG.md', 'docs/.vitepress/**'],

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
        items: [{ text: "Vue d'ensemble (server-security)", link: '/bootstrap/security/' }],
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
        items: [{ text: 'Guide canari', link: '/test/' }],
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
