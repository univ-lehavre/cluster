# Contribuer à `cluster`

> 🇬🇧 This guide is in French (the maintaining team's language), but
> **contributions and issues written in English are welcome** — open a PR or an
> issue in either language.

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
([ADR 0023](/cluster/docs/decisions/0023-plateforme-exemple-generique/)). **Tout
ce qui est versionné — code, manifestes, scripts ET prose (docs, ADR, RUNBOOK) —
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
- **Exceptions** : le réseau d'exemple du banc local (`192.168.67.0/24`) reste
  tel quel (exemple fonctionnel public) ; l'historique de validation banc
  (`bench/RESULTS.md`) n'est **pas** réécrit (honnêteté des Runs).

## Traçabilité : ADR, audits, plans

Quatre natures d'écrits, quatre rôles non chevauchants — **un ADR DÉCIDE, un
plan MET EN ŒUVRE, une issue EXÉCUTE, une PR LIVRE**
([ADR 0057](/cluster/docs/decisions/0057-gouvernance-documentaire-adr-plan-issue/))
:

| Trace              | Où                                           | Rôle                                                                                                                                                                                                                                                                                                |
| ------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ADR**            | `docs/decisions/`                            | **Décide** (le _pourquoi_) — structurante, numérotée, **immuable**.                                                                                                                                                                                                                                 |
| **Plan**           | `docs/plans/`                                | **Met en œuvre** une décision (paliers + suivi) — thématique, **vivant**.                                                                                                                                                                                                                           |
| **Issue**          | GitHub                                       | **Exécute** — unité de travail fermable.                                                                                                                                                                                                                                                            |
| **PR**             | GitHub                                       | **Livre** un changement + sa preuve, ferme une issue / coche un palier.                                                                                                                                                                                                                             |
| **Audit**          | `docs/audit/`                                | **Mesure** l'écart à un standard — grille permanente + passages datés ([ADR 0058](/cluster/docs/decisions/0058-doctrine-audit-grille-passages/)).                                                                                                                                                   |
| **Drift**          | `docs/architecture/registre-drifts.yaml`     | **Capture** un écart révélé par un run e2e (`Lnn` indexé) — trace empirique datée, `ouvert` ⇒ issue liée ([ADR 0058](/cluster/docs/decisions/0058-doctrine-audit-grille-passages/) §6).                                                                                                             |
| **Preuve de banc** | `bench/lima/RESULTS.md` + `bench/scenarios/` | **Valide** par un run e2e from-scratch (ADR [0034](/cluster/docs/decisions/0034-validation-e2e-from-scratch/)/[0052](/cluster/docs/decisions/0052-reproductibilite-des-resultats/)) — la trace empirique **mère** (les drifts en naissent) ; fraîcheur surveillée par `bench-freshness` (ADR 0042). |

**Le test de découpe (par temporalité,
[ADR 0057](/cluster/docs/decisions/0057-gouvernance-documentaire-adr-plan-issue/))**
: un contenu **immuable** va dans l'ADR (« vrai dans 2 ans, sauf superseded ? »)
; un **ordre de marche évolutif** dans un plan (« vais-je réordonner / cocher ça
? ») ; une **unité fermable** dans une issue.

Règles :

- **Un ADR avec mise en œuvre échelonnée ⇒ un plan dédié OBLIGATOIRE.** Jamais
  de tableau de paliers, checklist ou « TODO » **dans** un ADR (un ADR est
  immuable, un déroulé évolue). Un ADR purement conceptuel peut n'avoir aucun
  plan. Le plan **référence l'ADR qui le fonde** en en-tête.
- **Plans THÉMATIQUES et vivants** : `plan-<thème>.md` (pas daté). Chaque plan
  porte (1) un **en-tête `## État`** (Brouillon / Actif / Achevé / Abandonné,
  daté, comme l'ADR a son `## Statut`) et (2) une section **« Suivi »** :
  paliers (cases à cocher), **issues rattachées** (`#NNN`, créées ou
  préexistantes adoptées), renvoi aux runs de preuve (`RESULTS.md`). Le plan est
  le **tableau de bord** d'une décision. **`Proposed` ⇒ pas d'implémentation** :
  un plan ne passe `Actif` (code mergeable) qu'une fois l'ADR fondateur
  **`Accepted`**.
- **Audit = grille permanente + passages datés**
  ([ADR 0058](/cluster/docs/decisions/0058-doctrine-audit-grille-passages/)) :
  la grille (dimensions/critères/méthode) ne périme pas ; un passage est daté
  (`AAAA-MM-JJ`), append-only, **renvoie aux ADR** pour les _pourquoi_, et ses
  manques deviennent des **issues**.
- **Audit de session** (figé : journal d'un moment — réalignement de branche,
  dette) reste daté : `AAAA-MM-JJ-audit-<sujet>.md`. À distinguer d'un **plan
  vivant**.
- **Frontière ADR 0023** : `docs/plans/` ne versionne que des **plans d'INFRA**
  (socle générique). Un plan **métier / applicatif** vit dans le dépôt
  applicatif (`atlas`), **pas ici**.
- **Numéro d'ADR = ressource partagée** entre branches parallèles : en cas de
  collision (deux features réservant le même numéro), renuméroter au rebase et
  corriger l'index + toutes les références.
- Détail et index : [`docs/plans/README.md`](/cluster/docs/plans/).

## Système d'exploitation supporté

Le poste de contribution / contrôle est **macOS** (Apple Silicon, arm64) **ou
Linux** ; les nœuds (banc Lima, prod) sont **Linux Debian**.
[ADR 0100](/cluster/docs/decisions/0100-perimetre-os-poste-et-noeuds/) acte ce
périmètre :

- **macOS / Linux** : supportés (poste de contrôle + outillage de validation).
- **Windows natif** : **non supporté** (la chaîne de lint/hooks suppose un shell
  POSIX — `find`/`xargs`, `bats`, `kubeconform`). Utiliser **WSL2**.
- **WSL2** (Ubuntu sur Windows) : supporté, **à condition** de cloner dans le
  système de fichiers **Linux** de la distribution (`~/…`), **pas** côté Windows
  (`/mnt/c/…`) — sinon les fins de ligne CRLF cassent les scripts.

## Installation des outils

```bash
pnpm install                                         # installe lefthook + prettier + commitlint
# macOS :
brew install yamllint shellcheck kubeconform ansible-lint
# Linux (Debian/Ubuntu) : yamllint/shellcheck/ansible-lint via apt ; kubeconform
# par binaire (github.com/yannh/kubeconform/releases), comme en CI.
```

`pnpm install` exécute automatiquement `lefthook install` qui pose les hooks git
(pre-commit, pre-push, commit-msg).

## Commandes utiles

```bash
pnpm format         # applique Prettier
pnpm lint           # vérifie format + yaml + shell
pnpm lint:k8s       # valide les manifests via kubeconform
pnpm lint:ansible   # lint les playbooks Ansible
```

> **Release** : automatisée par
> [release-please](https://github.com/googleapis/release-please) (cron quotidien
> → PR `chore(main): release vX.Y.Z`). Rien à lancer en local ; merger la PR de
> release publie la version.

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

### Merge & traçabilité (merge commit)

Le dépôt merge **en merge commit** (`merge and merge`, **pas squash**) pour
préserver l'historique fin de chaque PR sur `main`
([ADR 0037](/cluster/docs/decisions/0037-strategie-merge-commit/) :
`git log`/`bisect`/ `blame` voient chaque commit). Conséquence et discipline :

- **Chaque commit d'une PR doit être propre** : la CI valide **commitlint sur
  toute la plage** de la PR (pas seulement le titre), car chaque commit arrive
  tel quel sur `main` (et alimente release-please / le `CHANGELOG`). Soigner et
  regrouper ses commits **avant** le merge.
- **Conventional Commits** : sujet en minuscule, sans email / sans
  `Co-Authored-By`, corps ≤ 100 colonnes.
- **1 PR = 1 type/scope cohérent** : mélanger deux capacités indépendantes dans
  une PR brouille l'historique et le changelog → **deux PR**. Les
  `docs:`/`test:` qui _servent_ la feature peuvent l'accompagner.
- **Lier les issues via `Closes #N`** dans la _description_ de PR (ferme l'issue
  au merge, garde le lien durable).
- **Index ADR = ressource partagée** : deux PR parallèles touchant
  `docs/decisions/README.md` (ajout de lignes au même endroit) **collisionnent**
  au merge — rebaser la seconde sur `main` et empiler proprement (vécu : 0057 ↔
  0058).

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

Voir [`bench/`](/cluster/bench/) — banc **Lima** pour valider sur Debian 13
arm64 avant de toucher les serveurs (seul banc local,
[ADR 0038](/cluster/docs/decisions/0038-lima-seul-banc-local/)) :

- [`bench/lima/`](/cluster/bench/lima/) — banc multi-nœuds, profils léger (~11
  min) et Ceph (~30 min), via
  [`run-phases.sh`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/run-phases.sh)
  à gates. Exerce le multi-VM + Rook-Ceph + la chaîne DataOps.

Résultats du dernier banc : [`bench/RESULTS.md`](/cluster/bench/RESULTS/).

## Versionnement (release-please)

Le versionnement est **automatique** via le workflow
[`.github/workflows/release.yml`](https://github.com/univ-lehavre/cluster/blob/main/.github/workflows/release.yml)
qui utilise [release-please](https://github.com/googleapis/release-please).

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
changelog généré. Aucun bump manuel à faire — **release-please est la source
unique** (le bump local `commit-and-tag-version` a été retiré).

## Code de conduite

La participation au projet est régie par notre
[code de conduite](/cluster/CODE_OF_CONDUCT/). En contribuant, vous vous engagez
à le respecter.

## Toute page Markdown est atteignable

Tout fichier `*.md` versionné doit être **atteignable depuis la documentation**
: présent dans le sidebar VitePress ou cible d'un lien depuis une page elle-même
atteignable
([ADR 0029](/cluster/docs/decisions/0029-markdown-atteignable-doc/)). Le
garde-fou `pnpm lint:docs-orphans`
([`scripts/check_md_orphans.py`](https://github.com/univ-lehavre/cluster/blob/main/scripts/check_md_orphans.py))
échoue sur tout orphelin — il tourne dans `pnpm lint` et en CI.
