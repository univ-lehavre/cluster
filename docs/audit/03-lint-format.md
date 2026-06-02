# 3 — Lint, formatage & chaîne qualité automatisée

**Note : 3,5 / 5**

> **État factuel (exécuté le 2026-05-29) :** `prettier --check` ✅, `shellcheck`
> (18 scripts) ✅ 0 warning, `yamllint .` ✅ (exit 0, quelques warnings
> cosmétiques), `ansible-lint` (profil `production`) ✅ 0 failure, `jscpd` ✅ 0
> %, `gitleaks` ✅ 0 secret sur 119 commits. **La chaîne fonctionne.** L'audit
> porte donc sur la _couverture_ et la _parité_, pas sur « faut-il linter ».

Chaîne mature et cohérente : prettier, yamllint, shellcheck, kubeconform,
ansible-lint, jscpd, commitlint sont câblés en CI **et**, pour la plupart, en
hooks lefthook. Les exclusions sont largement justifiées (manifests Rook
vendored, lockfiles, inventaires machine-spécifiques). Les écarts sont des
imperfections de parité et des angles morts (scanners de sécurité IaC,
markdownlint, link-checker).

## Points forts

- Couverture multi-outils redondante CI + hooks.
- Exclusions kubeconform pertinentes : seuls les 6 manifests Rook vendored +
  `values.yaml` Helm + `inventory.yaml` sont exclus ; tous les manifests maison
  sont validés.
- Garde-fou pre-push « pas de push direct sur main » + commit-msg rejetant les
  e-mails et validant Conventional Commits.
- `commitlint.config.js` gère l'historique pré-Conventional-Commits par regex.
- `jscpd` seuil 5 %, exclusions alignées → 0 % de duplication.
- `ansible-lint` en profil `production` (le plus strict).

## Constats

### Majeur (→ vérifié suggestion) — Aucun scanner de posture sécurité IaC

- **Fichier** : `.github/workflows/ci.yml`
- **Constat** : `kubeconform` ne valide que la conformité schématique, pas la
  posture de sécurité. Aucun trivy/checkov/kube-score/kube-linter/polaris. Les
  compromis sécurité (ADR 0010/0011/0012) ne sont jamais matérialisés comme des
  findings « explicitement supprimés ». _Gravité ramenée à suggestion : surface
  maison réduite (~2 deployments + 1 cronjob), compromis déjà documentés en
  ADR._
- **Recommandation** : ajouter un job `trivy config .` (ou `kube-score`) avec
  une allowlist documentée des compromis actés. Voir aussi
  [11](11-logiciels-oss.md) pour le scan de CVE (distinct, et lui en majeur).

### Mineur — `jscpd` en CI mais absent des hooks

- **Fichier** : `lefthook.yml`
- **Constat** : `lint:dup` existe et tourne en CI mais n'est dans aucun hook ;
  une duplication n'est détectée qu'au passage en CI.
- **Recommandation** : ajouter `pnpm lint:dup` au bloc `pre-push`.

### Mineur — `pnpm lint` n'inclut ni `lint:k8s` ni `lint:ansible`

- **Fichier** : `package.json`
- **Constat** : la cible agrégée omet la validation des manifests k8s et Ansible
  ; `pnpm lint` n'est pas le miroir de la CI.
- **Recommandation** : chaîner `lint:k8s` et `lint:ansible` dans `lint`.

### Mineur — Exclusions kubeconform divergentes (3 copies)

- **Fichier** : `package.json:17`, `lefthook.yml:65-66`, `ci.yml:61-62`
- **Constat** : la liste `-not -path` est dupliquée à 3 endroits et a déjà
  divergé (`values.yaml` / `inventory.yaml` exclus en CI/hooks mais pas dans
  `package.json`) → `pnpm lint:k8s` échouerait là où la CI passe.
- **Recommandation** : factoriser dans un unique `scripts/kubeconform.sh` appelé
  par les trois.

### Mineur — Templates `.sh.j2` et scripts `.pl` échappent au lint

- **Fichier** : `bootstrap/roles/etcd-backup/templates/etcd-snapshot.sh.j2`,
  `bootstrap/security/blur-env.pl`
- **Constat** : `lint:shell` ne cible que `*.sh` ; un bug shell dans le template
  du job de backup etcd ne serait détecté par aucun linter.
- **Recommandation** : shellcheck sur le rendu du template (via la validation
  Ansible) ; documenter ou linter le `.pl` (`perl -c` / perlcritic).

### Mineur — `.yamllint.yaml` incompatible avec ansible-lint (fix-mode désactivé)

- **Fichier** : `.yamllint.yaml`
- **Constat** : ansible-lint signale une incompatibilité (`octal-values`,
  `braces`, `comments-indentation`) qui **désactive son fix-mode**, privant les
  contributeurs de l'autocorrection.
- **Recommandation** : fournir à ansible-lint une config yamllint alignée (ou
  ajouter ces règles de façon compatible) pour restaurer `ansible-lint --fix`.

### Suggestion — Warnings yamllint cosmétiques non corrigés

- **Fichier** : `storage/ceph/storageClass/*.yaml` (le second fichier cité à
  l'origine, `roles/network/tasks/sshd.yml`, a depuis été **supprimé** —
  durcissement sshd unifié dans `first-access.sh`).
- **Constat** : 9 « missing starting space in comment » + 1 ligne de 269
  caractères ; verts car `level: warning`, mais polluent la sortie.
- **Recommandation** : corriger (`#x` → `# x`) ; permet de passer `comments` en
  `error` sur les fichiers maison.

### Suggestion — Pas de markdownlint ni de vérificateur de liens

- **Constat** : doc riche (37+ `.md`, 12 ADR) publiée en VitePress ; prettier
  formate mais ne valide ni structure ni liens.
- **Recommandation** : `markdownlint-cli2` + `lychee` (ou markdown-link-check)
  en CI léger, hors `CHANGELOG.md` et `docs/.vitepress/dist`. Voir aussi le
  finding `ignoreDeadLinks` en [04](04-documentation.md).

### Suggestion — `shellcheck` CI en `severity: warning` vs hooks par défaut

- **Constat** : léger écart de parité (info/style ignorés en CI, inclus en
  local).
- **Recommandation** : aligner explicitement la sévérité partout.
