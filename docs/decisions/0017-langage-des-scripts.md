# 0017 — Langage des scripts (bash / jq / python3 / bats)

## Contexte

L'audit ([09-langage-scripts](../audit/09-langage-scripts.md)) a remis en cause
le choix de **bash** pour les ~890 LOC de scripts du dépôt (`state.sh`,
`run-phases.sh`, scénarios, `cni.sh`, helpers). Verdict de l'audit : bash est le
**bon outil** ici (orchestration de CLIs : kubectl, ceph, vagrant, ssh), mais le
choix n'était formalisé nulle part → un contributeur pourrait réécrire en Go ou
Python « pour faire mieux », à perte.

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

## Statut

Accepted (2026-06-01).

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
