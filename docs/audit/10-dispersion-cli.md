# 10 — Dispersion des scripts vs point d'entrée unique

> Axe ajouté à votre demande : _« le fait qu'il y a plein de scripts au lieu
> d'un seul CLI. »_

## Verdict : **pas de CLI unique, mais un `Justfile` léger + un parcours README**

La critique « 18 scripts éparpillés sans point d'entrée » est **en partie
fondée, mais mal calibrée**. Les scripts ne sont **pas** le squelette
d'orchestration : ce sont des utilitaires ponctuels (`cni.sh`, `credentials.sh`,
`smoke-test.sh`, scénarios). La séquence opérationnelle réelle repose sur **11
playbooks Ansible** enchaînés à la main et documentés pas à pas dans
`bootstrap/RUNBOOK.md`.

Le **vrai** problème de découvrabilité n'est donc pas l'absence de CLI, mais que
le **`README` racine ne pointe même pas vers le `RUNBOOK`**
(`grep RUNBOOK README.md` = 0) : un nouvel arrivant ne sait pas par où
commencer.

Une réécriture en CLI unique (dispatcher bash ou Python/Go) serait un **mauvais
ROI** pour un mainteneur quasi unique : elle ajouterait une couche à maintenir
sans résoudre le cœur (l'ordre d'exécution vit dans Ansible + la doc).

## Arguments POUR la structure actuelle

- **Proximité-au-code assumée** : chaque script colocalisé avec ce qu'il gère ;
  VitePress (`srcDir: '..'`) surface la doc sans déplacer les fichiers.
  Déménager dans un `bin/` casserait cette logique.
- Les scripts **ne portent pas** l'orchestration : la séquence est une chaîne de
  11 playbooks Ansible idempotents, déjà ordonnés dans le RUNBOOK.
- Hygiène homogène (`set -euo pipefail`, shellcheck 0 warning, en-têtes
  docblock).
- Le sous-domaine qui avait le plus besoin d'orchestration **en a déjà une** :
  `run-phases.sh` est un vrai orchestrateur à sous-commandes
  (`up|bootstrap|ceph| sc|workloads|etcd|all`) avec gates — preuve d'un point
  d'entrée introduit **là où la valeur est réelle**, pas par dogme.
- Duplication sous le garde-fou jscpd (blocs trop courts pour être structurels).

## Arguments CONTRE (défauts réels)

- **Découvrabilité du point d'entrée global défaillante** : le `README` ne lie
  pas le `RUNBOOK` ; on ne sait pas quoi lancer en premier.
- **Ordre d'exécution implicite** : la séquence des 11 playbooks + `cni.sh` +
  `join-workers` n'existe qu'en blocs copier-coller dans la prose ; rien ne
  matérialise un `make bootstrap` canonique.
- **Duplication transverse réelle** : `state.sh` et `report.sh` sont des
  quasi-jumeaux (bloc couleurs, helpers `ssh_q`/`ssh_ok`, défauts SSH
  identiques).
- `log()` recopié dans **9 scripts** sous 3 variantes divergentes.
- **`--help` quasi inexistant** (1 script sur 18).
- **Collision sémantique `SSH_OPTS`** : array dans `run-phases.sh` vs string
  dans `state.sh`/`report.sh` — même nom, sémantiques incompatibles.
- **Contrat inter-scripts implicite** : `run-phases.sh` exporte `CEPH_*`,
  `DATA_DEVICE_GLOB`, `NVME_BLOCK_DEVICE` consommés par `state.sh` et
  `cleanup.sh`, couplage non formalisé.

## Constats

### Majeur — Le README n'oriente pas vers le parcours d'installation

- **Fichier** : `README.md:14-44`
- **Constat** : aucun lien vers `bootstrap/RUNBOOK.md`, aucune indication de
  l'ordre des étapes. La séquence réelle n'est documentée que dans le RUNBOOK,
  page non référencée depuis l'accueil.
- **Recommandation** : section « Par où commencer / parcours d'installation »
  avec l'ordre canonique et des liens explicites vers les RUNBOOK et `test/`.

### Majeur — Absence d'orchestrateur global nommant les points d'entrée

- **Fichier** : `package.json:5-20` (scripts repo uniquement, pas d'ops cluster)
- **Constat** : pas de Makefile/Justfile/Taskfile ; l'ordre d'exécution n'est
  matérialisé nulle part par l'outillage.
- **Recommandation** : **`Justfile` (ou Makefile) racine mince** qui _nomme et
  enchaîne l'existant_ — `just bootstrap` (chaîne ordonnée des playbooks),
  `just state`, `just security-report`, `just test-bench`,
  `just test-scenarios`, `just dashboard-token`. Pas de logique nouvelle :
  découvrabilité (`just --list`)
  - matérialisation de l'ordre, à coût quasi nul. **C'est la bonne réponse, pas
    un CLI custom.**

### Mineur — `state.sh` et `report.sh` quasi-jumeaux

- **Recommandation** : extraire `bootstrap/lib/ssh-report.sh` (couleurs,
  `ssh_q`/`ssh_ok`, défauts) sourcé par les deux.

### Mineur — Collision sémantique `SSH_OPTS` (array vs string)

- **Recommandation** : renommer la variable de `run-phases.sh` (ex.
  `BENCH_SSH_OPTS`), ou documenter explicitement la distinction.

### Mineur — Contrat inter-scripts (variables d'env) non centralisé

- **Recommandation** : documenter en un seul endroit le contrat `CEPH_*` /
  `DATA_DEVICE_GLOB` / `NVME_BLOCK_DEVICE` et leurs consommateurs (le
  commentaire `run-phases.sh:38-46` est un bon point de départ à promouvoir).

### Suggestions

- `log()`/`die()` → mini `test/scenarios/lib.sh` sourcé par les 8 scénarios.
- `--help` : généraliser le pattern de `prune.sh` via la lib commune, ou laisser
  tel quel (docblocks déjà soignés ; la priorité est la découvrabilité globale).

## À NE PAS faire

- **CLI bash dispatcher unique ou Python/Go** : ROI faible, l'orchestration vit
  dans Ansible, couche supplémentaire à maintenir/tester sans résoudre le vrai
  déficit (la découvrabilité), que le `Justfile` + lien README règlent à coût
  quasi nul. **Conserver la colocalisation scripts/code : c'est un bon choix.**
