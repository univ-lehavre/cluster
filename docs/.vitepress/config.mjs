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
    /\/bench\/unit\//,
  ],

  srcExclude: [
    'node_modules/**',
    '.git/**',
    '.github/**',
    '**/CHANGELOG.md',
    '**/LICENSE.md',
    'docs/.vitepress/**',
    // Code source vendoré (gitignoré) : ses .md (CONTRIBUTING, vendor PHP…) ne sont pas
    // de la doc et cassent le parse Vue de VitePress (srcDir='..' scanne le filesystem,
    // pas git). Exclus comme node_modules.
    'apps/redcap/source/**',
    'platform/redcap/image/source/**',
  ],

  // Map every README.md to its directory's index.md so URLs like /bench/,
  // /bootstrap/, /storage/ceph/ resolve cleanly.
  rewrites: (id) => {
    if (id === 'README.md') return 'index.md'
    if (id.endsWith('/README.md')) return id.replace(/README\.md$/, 'index.md')
    return id
  },

  themeConfig: {
    nav: [
      { text: 'Accueil', link: '/' },
      { text: 'Manifeste', link: '/docs/manifeste' },
      { text: 'Preuves', link: '/docs/preuves' },
      { text: 'Par où commencer', link: '/docs/demarrage' },
      { text: 'Se brancher', link: '/docs/se-brancher' },
      { text: 'Boîte à outils', link: '/docs/outils' },
      { text: 'Glossaire', link: '/docs/glossaire' },
      { text: 'Décisions (ADR)', link: '/docs/decisions/' },
      { text: 'Audit', link: '/docs/audit/' },
      { text: 'Banc de test', link: '/bench/' },
    ],
    sidebar: [
      {
        text: 'Comprendre',
        items: [
          { text: 'Accueil', link: '/' },
          { text: 'Manifeste (le récit)', link: '/docs/manifeste' },
          { text: 'Preuves de qualité', link: '/docs/preuves' },
          { text: 'Composants (la pile)', link: '/docs/composants' },
          { text: 'Glossaire', link: '/docs/glossaire' },
        ],
      },
      {
        text: 'Faire',
        items: [
          { text: 'Par où commencer', link: '/docs/demarrage' },
          { text: 'Se brancher sur la plateforme', link: '/docs/se-brancher' },
          { text: 'Monter le banc local', link: '/docs/banc-local' },
          { text: 'Boîte à outils (scripts)', link: '/docs/outils' },
          { text: 'Référence dev data (endpoints)', link: '/docs/guide-dev-data' },
          { text: 'Développeur atlas (point d’entrée)', link: '/docs/dev-atlas' },
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
        items: [
          { text: 'RStudio', link: '/apps/rstudio/' },
          { text: 'REDCap', link: '/apps/redcap/' },
        ],
      },
      {
        text: 'Banc de test (Lima)',
        items: [
          { text: "Vue d'ensemble", link: '/bench/' },
          { text: 'Banc Lima (multi-nœuds)', link: '/bench/lima/' },
          { text: 'Journal des runs Lima (courant)', link: '/bench/lima/RESULTS' },
          { text: 'Historique Vagrant (déprécié)', link: '/bench/RESULTS' },
          { text: 'Scénarios reproductibles', link: '/bench/scenarios/' },
        ],
      },
      {
        text: 'Architecture & preuves',
        collapsed: true,
        items: [
          { text: 'Preuves de qualité', link: '/docs/preuves' },
          { text: "Vues d'architecture (index)", link: '/docs/architecture/' },
          { text: 'Matrice du catalogue', link: '/docs/architecture/matrice-catalogue' },
          { text: 'Validation sur banc', link: '/docs/architecture/validation-banc' },
          { text: 'Leçons des runs', link: '/docs/architecture/lecons-des-runs' },
          { text: 'Plan de tests', link: '/docs/architecture/plan-de-tests' },
          { text: 'Bonnes pratiques', link: '/docs/architecture/bonnes-pratiques' },
          { text: 'Chaîne DataOps', link: '/docs/architecture/chaine-dataops' },
          { text: 'Exposition réseau', link: '/docs/architecture/exposition-reseau' },
        ],
      },
      {
        text: 'Décisions (ADR)',
        collapsed: true,
        items: [
          { text: 'Index des 62 ADR', link: '/docs/decisions/' },
          { text: '— par thème —', link: '/docs/architecture/' },
          { text: 'Stockage & données', link: '/docs/architecture/decisions-stockage' },
          { text: 'Plan de contrôle', link: '/docs/architecture/decisions-plan-de-controle' },
          { text: 'Sécurité & accès', link: '/docs/architecture/decisions-securite-acces' },
          { text: 'Plateforme & GitOps', link: '/docs/architecture/decisions-plateforme-gitops' },
          {
            text: 'Conventions & outillage',
            link: '/docs/architecture/decisions-conventions-outillage',
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
          { text: 'Modèle déclaratif des topologies', link: '/docs/plans/plan-modele-declaratif' },
          { text: 'Dagster (orchestration)', link: '/docs/plans/plan-dagster' },
          { text: 'Marquez (lineage)', link: '/docs/plans/plan-marquez' },
          { text: 'Rollback par phase', link: '/docs/plans/plan-rollback-par-phase' },
          { text: 'Audit des conventions', link: '/docs/plans/plan-audit-conventions' },
          { text: 'Refonte documentaire', link: '/docs/plans/plan-refonte-doc' },
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
