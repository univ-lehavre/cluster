# 9 — Remise en cause du langage des scripts (bash)

> Axe ajouté à votre demande : _« tu peux également remettre en cause le langage
> des scripts. »_

## Verdict : **garder bash, mais le tester et durcir le parsing**

Le choix de bash est **globalement justifié**, et une réécriture massive aurait
un ROI faible voire négatif. Les 2038 LOC réparties sur 18 scripts sont à ~95 %
des **orchestrateurs de CLIs externes** (`ceph`×112, `kubectl`×88, `vagrant`×32,
`ssh`×31, `cilium`×25) : c'est l'usage canonique de bash, là où Python/Go
ajouteraient une couche `subprocess`/`exec.Command` verbeuse **sans gain de
fiabilité** sur la partie qui compte (la commande externe).

Le contexte renforce ce verdict : **mainteneur quasi unique**, **public
néophyte** (un `.sh` lisible séquentiellement est plus accessible qu'un binaire
Go ou un module Python), **cible Debian-only** (l'argument « binaire
distribuable » de Go tombe — rien à distribuer), **zéro dépendance d'exécution
ajoutée**.

Mais le jugement n'est **pas binaire** : la complexité est concentrée dans
`state.sh` (601 LOC) + `run-phases.sh` (289 LOC) = **44 % du total**, et c'est
là que vit la fragilité.

## Arguments POUR garder bash

- 95 % d'orchestration de CLIs : usage canonique de bash.
- Debian-only : pas de binaire à distribuer.
- Lisibilité néophyte : le code shell **est** la documentation exécutable ; un
  binaire Go est opaque, un package Python imposerait venv/imports.
- Zéro dépendance ajoutée (bash + coreutils + CLIs déjà requis).
- **Bash réellement maîtrisé** : `set -euo pipefail` partout, shellcheck à 0
  warning, désactivations SC2086/SC2016 explicitement commentées, helpers
  factorisés (`ssh_q`, `ssh_ok`, `mark`, `retry`).
- `kubectl` déjà consommé via `-o jsonpath` (~11 fois) → parsing texte fragile
  déjà évité côté Kubernetes.

## Arguments CONTRE (zones de fragilité réelles)

- **Passage de structures par sérialisation positionnelle** : heredocs SSH relus
  par `read -r a b c <<<"$result"` (`state.sh` ~l.200, l.340). Un champ vide ou
  contenant un espace décale silencieusement les colonnes, et `set -e` ne
  l'attrape pas.
- **Parsing de sortie humaine** : `awk` sur l'audit-log, `chage -l` + `date -d`
  avec gymnastique `LANG=C`/`LC_ALL=C` pour contourner le format français
  (`state.sh` l.119-198) — code fragile au changement de format/locale.
- **`ceph health`/`status` parsés par `awk`/`head`** au lieu de `-f json`
  (scénarios 03 l.53, 05 l.51) — fragile aux évolutions inter-versions Ceph.
- **Aveu implicite** : `run-phases.sh` l.200-201 appelle déjà `python3 -c` pour
  compter du JSON → bash plie sur le JSON non trivial, et python3 est **déjà**
  une dépendance de fait.
- **Aucun test comportemental** sur 890 LOC critiques.
- Incohérence `SSH_OPTS` : string + word-splitting dans `state.sh` (SC2086
  désactivé) vs tableau dans `run-phases.sh`.

## Constats

### Majeur — Aucun test comportemental sur 890 LOC critiques

- **Fichier** : `bootstrap/state.sh`
- **Constat** : `state.sh` classe l'état du cluster et propose des remèdes
  (`exit 1` sur drift) mais aucune fonction n'est testée. shellcheck valide la
  **syntaxe**, pas le **comportement** : la classification passwd
  (AMBIGUOUS/NEVER/MOD) et le comptage HDD clean/dirty n'ont aucun garde-fou.
- **Recommandation** : **action à plus fort ROI du dépôt.** Extraire les
  fonctions pures et les couvrir avec **bats-core** sur des chaînes fixtures
  (sans cluster) ; ajouter `bats` aux devDependencies et un script `test:shell`.

### Mineur — Sérialisation positionnelle fragile (`read -r <<<` heredoc SSH)

- **Recommandation** : faire émettre du JSON (ou clé=valeur) au shell distant et
  le lire via `jq` côté contrôle (`jq` est déjà une dépendance assumée) ; à
  défaut, valider le nombre de champs avant usage.

### Mineur — Parsing `chage`/`date` avec contournement de locale

- **Recommandation** : lire `getent shadow` (3ᵉ champ, jours depuis epoch)
  plutôt que parser la sortie humaine de `chage` ; couvrir par un test bats.

### Mineur — `ceph health`/`status` parsés par `awk`/`head`

- **Recommandation** : `ceph health -f json | jq -r .status` (cohérent avec le
  `jsonpath` déjà utilisé côté kubectl).

### Suggestion — `python3 -c` pour agréger du JSON

- **Recommandation** : acceptable (python3 présent), mais préférer `jq` pour
  l'homogénéité. Formaliser la règle « bash orchestre / jq parse / python3
  toléré ».

### Suggestion — Incohérence `SSH_OPTS` (string vs array)

- **Recommandation** : uniformiser sur le tableau bash (comme `run-phases.sh`),
  retirer les `disable=SC2086`.

### Suggestion — Choix du langage non documenté en ADR

- **Recommandation** : **ADR 0013** « bash pour l'orchestration de CLIs, cible
  Debian-only » actant le périmètre (orchestration), la frontière (parsing →
  JSON+jq), la tolérance python3 et l'engagement bats-core. Faible effort, fort
  gain de transmissibilité (bus-factor).

## À NE PAS faire

- **Porter en Go** : aucun binaire à distribuer, public néophyte, opacité.
- **Réécrire en Python** : gain nul sur 95 % du code (orchestration), dépendance
  venv non désirée pour des chercheurs.
