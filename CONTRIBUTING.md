# Contribuer à `cluster`

Outillage géré par [Lefthook](https://lefthook.dev/) (hooks git),
[Prettier](https://prettier.io/) (format),
[yamllint](https://yamllint.readthedocs.io/),
[shellcheck](https://www.shellcheck.net/),
[kubeconform](https://github.com/yannh/kubeconform) et
[ansible-lint](https://ansible-lint.readthedocs.io/). Les messages de commit
suivent la convention
[Conventional Commits](https://www.conventionalcommits.org/).

## Règle fondatrice — dépôt multi-topologies, valeurs génériques

Ce dépôt est un **catalogue de topologies d'infrastructure** (mono-nœud,
multi-nœuds, bare-metal hyperconvergé…) : **plusieurs infra déclarées, une seule
activée** par déploiement — à la manière de Pulumi/Terraform — pas
l'infrastructure réelle d'un contributeur
([ADR 0023](docs/decisions/0023-plateforme-exemple-generique.md)). **Tout ce qui
est versionné — code, manifestes, scripts ET prose (docs, ADR, RUNBOOK) —
emploie des valeurs d'exemple génériques**, jamais les valeurs réelles d'un
déploiement (qui vivent dans une config locale non versionnée).

- **À génériser** : IP / plages réseau (→ p. ex. `10.0.0.0/22`), noms de nœuds /
  hôtes / PVC / buckets (→ `cp1`, `node1`…), noms d'organisation / sites (→ «
  l'organisation »), **cas d'usage métier propres à un projet** (sources de
  données, services applicatifs spécifiques → « source de données ouverte », «
  backend d'auth »…).
- **À GARDER** : les logiciels / bases qui _portent_ une décision (briques
  d'infra que le dépôt propose : Ceph, MySQL, Cilium, cert-manager, Argo CD…) —
  les occulter viderait l'ADR de son sens. _Garder ce que le dépôt propose comme
  brique ; génériser ce qui n'a de sens que pour une instance._
- **Valeur d'exemple _concrète_**, pas tournure vague (un `/22` ≠ un `/24`) ; le
  contexte chiffré qui fonde une décision est conservé.
- **Spécificités réelles** = fichier de config **local non versionné**
  (gitignoré) surchargeant un **`*.example` versionné** — voir la convention
  `.env` / `.env.example` et les inventaires de banc.
- **Exceptions** : le banc Vagrant (`192.168.67.0/24`) reste tel quel (exemple
  fonctionnel public) ; l'historique de validation banc (`test/RESULTS.md`)
  n'est **pas** réécrit (honnêteté des Runs).

## Traçabilité : ADR, audits, plans

Trois natures d'écrits, trois dossiers — chacun a son rôle ; aucun ne remplace
un autre :

| Trace                         | Dossier           | Nature                                                                                                                                          |
| ----------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Décisions**                 | `docs/decisions/` | ADR (Nygard) — **la décision** structurante, numérotée, immuable.                                                                               |
| **Audit du dépôt**            | `docs/audit/`     | État des lieux qualité daté, vérifié de façon adversariale.                                                                                     |
| **Plans & audits de session** | `docs/plans/`     | **Comment** on met en œuvre une décision (plan d'étape) et **ce qui s'est passé** en route (audit de session : réalignement de branche, dette). |

Règles :

- Un **plan met en œuvre une décision**, il ne la remplace pas : tout plan
  d'étape référence en en-tête l'**ADR qui le fonde**. Les décisions
  structurantes vont dans un **ADR**, jamais en bullets d'un TODO ou enfouies
  dans un plan.
- **Frontière ADR 0023** : `docs/plans/` ne versionne que des **plans d'INFRA**
  (socle générique). Un plan **métier / applicatif** (cas d'usage d'un projet,
  pipelines de données spécifiques) vit dans le dépôt applicatif (`atlas`),
  **pas ici** — même s'il a été rédigé pendant le travail sur ce dépôt.
- **Nommage** : plan d'étape `AAAA-MM-JJ-<sujet>.md` ; audit de session
  `AAAA-MM-JJ-audit-<sujet>.md`. Chaque plan porte une section « Journal
  d'exécution » renvoyant aux audits de session liés.
- **Numéro d'ADR = ressource partagée** entre branches parallèles : en cas de
  collision (deux features réservant le même numéro), renuméroter au rebase et
  corriger l'index + toutes les références.
- Détail et index : [`docs/plans/README.md`](docs/plans/README.md).

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

### Merge & traçabilité (squash)

Le dépôt merge **en squash uniquement** (`squash and merge`). Conséquence : la
PR entière devient **un seul commit** sur `main`, dont le **message = le titre
de la PR** (et le corps = la liste des commits de la branche). Le `main` reste
linéaire et lisible (1 PR = 1 commit), mais cela impose une discipline :

- **Le titre de PR EST le commit de `main`** → il doit être un Conventional
  Commit valide (`feat(scope): …`, minuscule, sans `(#issue)`). Un job CI le
  valide (`commitlint` sur le titre) : le squash le propage tel quel à `main`,
  donc à release-please et au `CHANGELOG`.
- **1 PR = 1 type/scope cohérent** = **1 ligne de `CHANGELOG`**. Le squash
  n'expose qu'**un** préfixe au changelog ; mélanger deux features distinctes
  dans une PR en cache une. Les `docs:`/`test:` qui _servent_ la feature peuvent
  l'accompagner ; deux capacités indépendantes → deux PR.
- **Lier les issues via `Closes #N` dans la _description_ de PR**, pas dans le
  corps des commits (le squash les enfouit ; GitHub n'auto-fermerait pas). C'est
  ce qui ferme l'issue au merge et garde le lien commit↔issue durable.
- **Pas de `(#issue)` dans le titre** : le squash ajoute déjà `(#PR)`. En mettre
  un produit un double numéro parasite (`… (#157) (#144)`).
- Les commits _internes_ à la branche peuvent rester atomiques (utile à la
  revue) — ils sont aplatis au merge, donc leur granularité ne survit pas sur
  `main`. Si cette granularité doit survivre (revert/bisect fins), **scinder en
  plusieurs PR** plutôt que compter sur le squash.

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
  réseau privé `10.0.0.0/22` (~15 min, exerce Rook-Ceph).

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

## Code de conduite

La participation au projet est régie par notre
[code de conduite](CODE_OF_CONDUCT.md). En contribuant, vous vous engagez à le
respecter.

## Toute page Markdown est atteignable

Tout fichier `*.md` versionné doit être **atteignable depuis la documentation**
: présent dans le sidebar VitePress ou cible d'un lien depuis une page elle-même
atteignable ([ADR 0029](docs/decisions/0029-markdown-atteignable-doc.md)). Le
garde-fou `pnpm lint:docs-orphans`
([`scripts/check_md_orphans.py`](scripts/check_md_orphans.py)) échoue sur tout
orphelin — il tourne dans `pnpm lint` et en CI.
