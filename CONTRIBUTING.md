# Contribuer à `cluster`

Outillage géré par [Lefthook](https://lefthook.dev/) (hooks git),
[Prettier](https://prettier.io/) (format),
[yamllint](https://yamllint.readthedocs.io/),
[shellcheck](https://www.shellcheck.net/),
[kubeconform](https://github.com/yannh/kubeconform) et
[ansible-lint](https://ansible-lint.readthedocs.io/). Les messages de commit
suivent la convention
[Conventional Commits](https://www.conventionalcommits.org/).

## Installation des outils

```bash
pnpm install                                         # installe lefthook + prettier + commitlint
brew install yamllint shellcheck kubeconform ansible-lint
```

`pnpm install` exécute automatiquement `lefthook install` qui pose les hooks git
(pre-commit, pre-push, commit-msg).

## Commandes utiles

```bash
pnpm format         # applique Prettier
pnpm lint           # vérifie format + yaml + shell
pnpm lint:k8s       # valide les manifests via kubeconform
pnpm lint:ansible   # lint les playbooks Ansible
pnpm release        # bump version + met à jour CHANGELOG + crée tag git
pnpm release:dry    # aperçu de la prochaine release sans rien modifier
```

## Workflow de PR

- Branche : `<type>/<courte-description>` (ex. `feat/etcd-backup`,
  `fix/state-passwd-locale`).
- Commits : Conventional Commits, sujet en minuscule, corps ≤ 100 colonnes. Pas
  d'email dans le message (le hook `no-emails` rejette).
- Avant de pousser : les hooks `pre-push` (yamllint, shellcheck, kubeconform,
  prettier, ansible-lint) doivent passer. `pnpm install` les pose
  automatiquement.
- Ne pas pousser directement sur `main` — le hook `no-direct-push-to-main`
  l'interdit ; passer par une PR.

## Validation locale complète

```bash
pnpm format:check                       # prettier
yamllint -c .yamllint.yaml .            # lint YAML
find . -name '*.yaml' \
  -not -path './bootstrap/*' -not -path './node_modules/*' \
  -not -path './storage/ceph/crds.yaml' -not -path './storage/ceph/common.yaml' \
  -not -path './storage/ceph/operator.yaml' -not -path './storage/ceph/cluster.yaml' \
  -not -path './storage/ceph/dashboard.yaml' -not -path './storage/ceph/toolbox.yaml' \
  -not -path './platform/k8s-dashboard/values.yaml' \
  | xargs kubeconform -strict -ignore-missing-schemas \
      -schema-location default \
      -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
ansible-lint bootstrap/
shellcheck $(find . -name '*.sh' -not -path './node_modules/*')
```

## Tests

Voir [`test/`](test/) — deux bancs Vagrant pour valider sur Debian 13 arm64
avant de toucher les serveurs :

- [`test/single-node/`](test/single-node/) — Phase 1-2 mono-VM (~5 min, sans
  Ceph).
- [`test/multi-node/`](test/multi-node/) — Phase 1-5 multi-VM avec disques +
  réseau privé `10.67.2.0/24` (~15 min, exerce Rook-Ceph).

Résultats du dernier banc : [`test/RESULTS.md`](test/RESULTS.md).

## Versionnement (release-please)

Le versionnement est **automatique** via le workflow
[`.github/workflows/release.yml`](.github/workflows/release.yml) qui utilise
[release-please](https://github.com/googleapis/release-please).

À chaque push sur `main`, release-please :

1. Parcourt les commits depuis le dernier tag ;
2. Calcule le prochain semver à partir des préfixes Conventional Commits
   (`feat:` → minor, `fix:`/`perf:` → patch, `feat!:` ou `BREAKING CHANGE:` →
   major) ;
3. Crée (ou met à jour) une **PR de release** intitulée `chore(release): vX.Y.Z`
   qui contient :
   - bump de `package.json` ;
   - mise à jour du `CHANGELOG.md` ;
   - mise à jour du `.release-please-manifest.json`.

Quand vous mergez cette PR, release-please pousse le tag `vX.Y.Z` et crée une
[GitHub Release](https://github.com/univ-lehavre/cluster/releases) avec le
changelog généré. Aucun bump manuel à faire.

Le script `pnpm release` (commit-and-tag-version) reste disponible pour un bump
manuel hors workflow GitHub, mais ce chemin doit rester exceptionnel — la source
de vérité est release-please.
