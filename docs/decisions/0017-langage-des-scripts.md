# 0017 — Langage des scripts (bash / jq / Python / bats)

> **Superseded by [ADR 0049](0049-doctrine-choix-outil-par-action.md)**
> (Doctrine du choix d'outil par action). L'ADR 0049 reprend intégralement les
> principes ci-dessous (bash/jq/Python/bats/Node, exclusion de Go) et les étend
> : Ansible promu langage de plein droit, Perl traité comme dette en sursis,
> cadre de pondération à 8 critères. Cet ADR reste lisible pour la trace
> historique.

## Contexte

L'audit ([09-langage-scripts](../audit/2026-05-29/09-langage-scripts.md)) a
remis en cause le choix de **bash** pour les ~890 LOC de scripts du dépôt
(`state.sh`, `run-phases.sh`, scénarios, `cni.sh`, helpers). Verdict de l'audit
: bash est le **bon outil** ici (orchestration de CLIs : kubectl, ceph, vagrant,
ssh), mais le choix n'était formalisé nulle part → un contributeur pourrait
réécrire en Go ou Python « pour faire mieux », à perte.

## Décision

**bash reste le langage d'orchestration**, avec des règles claires :

- **Orchestration de CLIs → bash.** `set -euo pipefail`, shellcheck à 0 warning
  (hook + CI), en-tête docblock. C'est le cœur du dépôt (lancer kubectl/ceph/
  vagrant/ssh et enchaîner).
- **Parsing structuré → `jq`** (et non `awk`/`grep`/`cut` sur des sorties
  humaines). `jq` est une dépendance assumée ; les sorties des CLIs sont lues en
  JSON (`kubectl -o jsonpath`/`-o json`, `ceph -f json`). Cf. la migration des
  scénarios (`ceph health -f json | jq`) et la lecture `getent shadow`.
- **Fonctions pures → couvertes par bats-core.** La logique de décision isolable
  (classification, comptage, parsing) est extraite dans des libs sourçables
  ([`bootstrap/lib/`](../../bootstrap/lib/)) et testée par bats
  ([`test/unit/`](../../test/unit/)). shellcheck valide la syntaxe ; bats valide
  le **comportement**.
- **python3 toléré, pas imposé.** Pour une tâche où bash deviendrait illisible
  (manipulation de données complexes, calculs), python3 (présent partout) est
  acceptable — mais reste l'exception, pas la règle.

## Amendement (2026-06-07) — Python à parité, Node = runtime d'outils

Le besoin d'écrire des garde-fous de **logique** (parcours de graphe, validation
structurée, calculs) — là où bash devient illisible — a montré la limite de la
formulation « python3 toléré, exception ». La règle est précisée — **sans rien
retirer** de ce qui précède (bash + jq + bats restent le cœur d'orchestration) :

- **Python dès que c'est complexe.** Logique non triviale (structures de
  données, parcours, parsing/validation au-delà de `jq`, calculs) → **Python**,
  pas du bash contorsionné. Python passe ainsi de « soupape exceptionnelle » à
  **second langage de plein droit**.
- **bash le reste du temps, là où il est pertinent.** Orchestration de CLIs
  (kubectl/ceph/vagrant/ssh), enchaînements, checks git/hooks → **bash**
  (`set -euo pipefail`, shellcheck 0 warning). Inchangé.
- **Tout code scripté est testé (non-régression).** La logique isolable est
  couverte par des tests : **bats** pour les fonctions bash pures
  (`test/unit/`), **un cadre de test Python** (au choix : `pytest` ou la
  `unittest` stdlib) pour les scripts Python. Un script de logique sans test
  n'est pas mergeable.
- **Outillage Python = `uv` + `ruff`.** Environnement reproductible
  (`pyproject.toml` + `uv.lock` committés), lint+format par `ruff` — branché
  dans `pnpm lint` (`lint:python`) et en CI. Versions pinnées
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).
- **Node.js n'est PAS un langage de script du dépôt.** C'est le **runtime
  d'outils** : VitePress (le site de doc), prettier, commitlint, jscpd,
  lefthook, bats. On ne l'abandonne pas (VitePress en dépend) mais on **n'écrit
  pas de script applicatif en JS/TS** — un nouveau besoin de logique va en
  Python.

Le « À NE PAS faire » ci-dessous reste valable (pas de Go ; pas de réécriture
Python **de l'orchestration** existante) : l'amendement ouvre Python pour la
**logique nouvelle**, il n'impose pas de porter le bash d'orchestration qui
marche.

## Statut

Accepted (2026-06-01). Amendé le 2026-06-07 (Python à parité, outillage uv/ruff,
tests obligatoires, Node = runtime d'outils).

## Conséquences

**Bénéfices.**

- Choix tracé → pas de réécriture opportuniste vers un langage compilé sans
  bénéfice réel (cf. « À NE PAS faire » de l'audit 09).
- Public néophyte : bash + jq restent lisibles et inspectables sans toolchain.
- Comportement garanti par bats là où ça compte (fonctions pures), pas seulement
  la syntaxe.

**Coûts assumés.**

- bash montre ses limites au-delà de l'orchestration (structures de données,
  gestion d'erreurs fine) — d'où la soupape python3 et la discipline jq.
- Couverture bats partielle : seules les **fonctions pures** sont testables sans
  cluster ; l'orchestration end-to-end se valide sur le banc.

## À NE PAS faire (rappel de l'audit)

- **Porter en Go** : aucun binaire à distribuer, public néophyte, opacité
  accrue.
- **Réécrire en Python** : gain nul sur les ~95 % de code qui sont de
  l'orchestration de CLIs.
