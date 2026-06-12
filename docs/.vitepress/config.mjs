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
  // Liste CIBLÉE plutôt que `true` global (audit P4 #33) : VitePress vérifie
  // désormais les liens entre pages du site, mais on tolère les liens vers des
  // fichiers de CODE (scripts, rôles Ansible, Justfile…) que la doc référence
  // légitimement — VitePress ne les sert pas (il ne rend que le Markdown), mais
  // ils sont valides sur GitHub. lychee (CI) couvre déjà ces liens fichiers.
  ignoreDeadLinks: [
    /\.(sh|pl|py|j2|tmpl|yaml|yml|toml|cff|conf|log|example)$/, // fichiers de code/config/logs
    /\/Justfile$/,
    /\/Vagrantfile$/,
    /\/Dockerfile$/,
    // Dossiers de code liés depuis la doc (VitePress les résout en /index) :
    /\/(roles|lib|templates|files|examples)\//,
    /\/test\/unit\//,
  ],

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
      { text: 'Par où commencer', link: '/docs/demarrage' },
      { text: 'Boîte à outils', link: '/docs/outils' },
      { text: 'Guide dev data', link: '/docs/guide-dev-data' },
      { text: 'Dev atlas', link: '/docs/dev-atlas' },
      { text: 'Glossaire', link: '/docs/glossaire' },
      { text: "Plan d'action", link: '/docs/audit/2026-05-29/12-plan-action' },
      { text: 'Banc de test', link: '/test/' },
    ],
    sidebar: [
      {
        text: 'Pour démarrer',
        items: [
          { text: 'Accueil', link: '/' },
          { text: 'Par où commencer', link: '/docs/demarrage' },
          { text: 'Boîte à outils (scripts)', link: '/docs/outils' },
          { text: 'Guide du développeur data', link: '/docs/guide-dev-data' },
          { text: 'Développeur atlas (point d’entrée)', link: '/docs/dev-atlas' },
          { text: 'Glossaire', link: '/docs/glossaire' },
          { text: 'Garde-fous', link: '/SAFEGUARDS' },
          { text: 'Contribuer', link: '/CONTRIBUTING' },
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
          { text: 'Sauvegarde (VolumeSnapshots)', link: '/storage/ceph/backup/' },
        ],
      },
      {
        text: 'Plateforme',
        items: [
          { text: 'Container Registry', link: '/platform/container-registry/' },
          { text: 'Dashboard Kubernetes', link: '/platform/k8s-dashboard/' },
          { text: 'Chaîne DataOps (accès & vérifs)', link: '/docs/architecture/chaine-dataops' },
          { text: 'Contrat cluster → atlas', link: '/contract/' },
        ],
      },
      {
        text: 'Applications',
        items: [{ text: 'RStudio', link: '/apps/rstudio/' }],
      },
      {
        text: 'Banc de test (Lima)',
        items: [
          { text: "Vue d'ensemble", link: '/test/' },
          { text: 'Banc Lima (multi-nœuds)', link: '/test/lima/' },
          { text: 'Résultats du dernier banc', link: '/test/RESULTS' },
          { text: 'Scénarios reproductibles', link: '/test/scenarios/' },
        ],
      },
      {
        text: 'Décisions (ADR)',
        collapsed: true,
        items: [
          { text: 'Index', link: '/docs/decisions/' },
          {
            text: '0001 — Réplication ×3 (bloc)',
            link: '/docs/decisions/0001-replication-x3-pour-workloads-bloc',
          },
          {
            text: '0002 — Control plane unique',
            link: '/docs/decisions/0002-control-plane-unique-avec-endpoint',
          },
          {
            text: '0003 — Pas de chiffrement Ceph',
            link: '/docs/decisions/0003-pas-de-chiffrement-ceph-tailscale',
          },
          {
            text: '0004 — Erasure coding 2+1 datalake',
            link: '/docs/decisions/0004-erasure-coding-2plus1-datalake',
          },
          {
            text: '0005 — containerd dépôt Docker',
            link: '/docs/decisions/0005-cri-containerd-via-depot-docker',
          },
          {
            text: '0006 — Matrice de versions',
            link: '/docs/decisions/0006-matrice-de-versions-et-politique-de-bump',
          },
          {
            text: '0007 — Hyperconvergence',
            link: '/docs/decisions/0007-hyperconvergence-control-plane-osd',
          },
          {
            text: '0008 — NVMe block.db SPOF',
            link: '/docs/decisions/0008-metadatadevice-nvme-spof-par-noeud',
          },
          { text: '0009 — Pourquoi 4 nœuds', link: '/docs/decisions/0009-pourquoi-4-noeuds' },
          {
            text: '0010 — Dashboard cluster-admin',
            link: '/docs/decisions/0010-dashboard-cluster-admin',
          },
          {
            text: '0011 — Registry HTTP sans auth',
            link: '/docs/decisions/0011-registry-http-sans-auth',
          },
          { text: '0012 — RStudio sans auth', link: '/docs/decisions/0012-rstudio-disable-auth' },
          {
            text: '0013 — Sauvegarde données applicatives',
            link: '/docs/decisions/0013-sauvegarde-donnees-applicatives',
          },
          {
            text: '0014 — Durcissement kubeadm',
            link: '/docs/decisions/0014-durcissement-kubeadm-init',
          },
          {
            text: "0015 — Stratégie d'upgrade K8s",
            link: '/docs/decisions/0015-strategie-upgrade-kubernetes',
          },
          { text: '0016 — Observabilité', link: '/docs/decisions/0016-observabilite' },
          {
            text: '0017 — Langage des scripts',
            link: '/docs/decisions/0017-langage-des-scripts',
          },
          {
            text: '0018 — Rook-Ceph vs Longhorn',
            link: '/docs/decisions/0018-rook-ceph-vs-longhorn',
          },
          {
            text: '0019 — Durcissement réseau Cilium',
            link: '/docs/decisions/0019-durcissement-reseau-cilium',
          },
        ],
      },
      {
        text: 'Audit',
        collapsed: true,
        items: [
          { text: 'Grille & passages', link: '/docs/audit/' },
          { text: '1 — Bonnes pratiques IaC', link: '/docs/audit/2026-05-29/01-bonnes-pratiques' },
          { text: '2 — Tests multi-niveaux', link: '/docs/audit/2026-05-29/02-tests' },
          { text: '3 — Lint & chaîne qualité', link: '/docs/audit/2026-05-29/03-lint-format' },
          { text: '4 — Documentation', link: '/docs/audit/2026-05-29/04-documentation' },
          { text: '5 — Reproductibilité', link: '/docs/audit/2026-05-29/05-reproductibilite' },
          { text: '6 — Sécurité', link: '/docs/audit/2026-05-29/06-securite' },
          { text: '7 — Gouvernance', link: '/docs/audit/2026-05-29/07-gouvernance' },
          { text: '8 — Opérabilité & résilience', link: '/docs/audit/2026-05-29/08-operabilite' },
          { text: '9 — Langage des scripts', link: '/docs/audit/2026-05-29/09-langage-scripts' },
          { text: '10 — Dispersion vs CLI', link: '/docs/audit/2026-05-29/10-dispersion-cli' },
          { text: '11 — Logiciels open source', link: '/docs/audit/2026-05-29/11-logiciels-oss' },
          { text: "12 — Plan d'action", link: '/docs/audit/2026-05-29/12-plan-action' },
        ],
      },
      {
        text: 'Plans & audits de session',
        collapsed: true,
        items: [
          { text: 'Index & convention', link: '/docs/plans/' },
          {
            text: 'Étape 1.7 — Dagster',
            link: '/docs/plans/2026-06-04-etape-1.7-dagster',
          },
          {
            text: 'Audit — réalignement Dagster ↔ main',
            link: '/docs/plans/2026-06-04-audit-realignement-main-dagster',
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
      pattern: 'https://github.com/univ-lehavre/cluster/edit/main/:path',
      text: 'Modifier cette page sur GitHub',
    },
    socialLinks: [{ icon: 'github', link: 'https://github.com/univ-lehavre/cluster' }],
  },
})
