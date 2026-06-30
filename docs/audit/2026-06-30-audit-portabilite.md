# 2026-06-30 — Audit « portabilité du code (OS poste ↔ nœuds, architecture x86 ↔ arm) »

| Champ       | Contenu                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**    | 2026-06-30                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Type**    | Audit statique de portabilité du code produit — **lecture seule**, aucune mutation. Deux axes : **OS** (macOS / Linux / Windows-WSL) et **architecture CPU** (x86-64 ↔ arm64). Preuves = `grep` / lecture de fichiers + 2 vérifications empiriques sur poste macOS 26.5.                                                                                                                                                                                                                                                                                                                                                                                            |
| **Fonde**   | _Réflexion_ — alimente une **issue** + un **ADR léger** (à venir) ; aucune décision ni mutation ici (doctrine [ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md) : « les manques deviennent des issues »).                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Verdict** | Code **SAIN** pour son périmètre réel. **Axe OS** : périmètre **macOS ↔ Linux (contrôleur) / Linux (nœuds) / Windows → WSL** **assumé** mais **non encore acté en ADR** ; **un seul vrai trou** = absence de `.gitattributes` → risque CRLF (P-CRLF, majeur) ; le reste = incohérences mineures + non-support Windows-natif **assumé**. **Axe architecture** : **mieux traité que l'OS** — banc **arm64** ↔ prod **x86** dérivés explicitement (ADR 0006/0026/0028/0031), seul point de vigilance = **asymétrie de validation** (le chemin x86 est moins exercé). **3 faux positifs écartés** par vérification adversariale, dont le faux « lint cassé sur macOS ». |

## Le cadre — trois contextes d'exécution

C'est **la clé de lecture** de tout cet audit : ce dépôt n'est pas un programme
unique tournant sur une seule machine, c'est un **catalogue d'infra** dont le
code s'exécute dans **trois contextes distincts**, chacun avec sa contrainte
d'OS et d'architecture propre. Un même verbe shell (`stat -c`, `date -d`,
`mapfile`) est **légitime ou fautif selon le contexte où il tourne** — d'où
l'importance de ne pas auditer « à plat ».

1. **CIBLE — les nœuds.** [`bootstrap/state.sh`](../../bootstrap/state.sh),
   [`bootstrap/first-access.sh`](../../bootstrap/first-access.sh), les blocs
   SSH/heredoc, le scénario 09 (etcd). L'OS est **toujours Linux Debian**,
   garanti. La portabilité macOS **n'y est pas requise**. Les commandes GNU
   (`stat -c`, `date -d`, `getent`, `hostname -I`, `systemctl`, `apt-get`,
   `crictl`) y sont **parfaitement légitimes** : elles ne s'exécutent **jamais**
   sur le poste, elles partent **node-side via SSH**, à l'intérieur de heredocs
   (`age=$(ssh_q "$h" "…")` avec `date -u +%s` / `date -d` dans
   [`bootstrap/state.sh:180`](../../bootstrap/state.sh#L180)-189 ;
   `cp_ssh 'sudo bash -s' <<'REMOTE'` dans
   [`bench/scenarios/09-etcd-restore.sh:93`](../../bench/scenarios/09-etcd-restore.sh#L93)-111).
   Les sur-classer en « non portable » serait une **erreur de lecture** : c'est
   du Linux garanti, hors-scope du poste.

2. **POSTE DE CONTRÔLE — le pilote.** `bench/lima/*`, `nestor/*.py`,
   `scripts/*.py`, les scénarios pilotés `kubectl`. L'OS est **macOS OU Linux**.
   La portabilité **macOS ↔ Linux est REQUISE** ici, et **déjà soignée par
   endroits** (cf. CONTRA infra). C'est dans ce contexte que les findings
   P-MAPFILE et P-PY ont du poids.

3. **OUTILLAGE CONTRIBUTEUR — la chaîne de validation.**
   [`package.json`](../../package.json), [`lefthook.yml`](../../lefthook.yml),
   hooks, CI. L'OS est **macOS / Linux / WSL**. Les pipes POSIX
   (`find … -print0 | xargs -0`) y sont la norme ; c'est ce contexte qui
   **exclut Windows natif** (P-TOOLING).

**Pourquoi les commandes GNU node-side sont légitimes** : le code du poste est
un **contrôleur Unix** qui pilote des nœuds Linux par SSH. Tout ce qui est
encapsulé dans un heredoc distant s'exécute sur Debian, pas sur le poste. La
frontière n'est pas le fichier, c'est le **point d'exécution**.

> **Et l'architecture ?** Elle se superpose à ces contextes : le **poste** est
> arm64 (Apple Silicon), les **nœuds banc** sont arm64 (VM Lima), les **nœuds
> prod** sont x86 (bare-metal). Le code croise donc OS **et** arch — traité dans
> la section « Architecture (x86 ↔ arm) » ci-dessous.

## Pourquoi ce passage

L'utilisateur a demandé un audit de portabilité, avec une consigne explicite :
**assumer le choix de portabilité actuel dans la documentation**. Ce passage
**acte donc un périmètre déjà vécu**, plutôt que de le présenter comme une
dette.

Le dépôt **assume déjà** ce périmètre dans les faits — il ne l'a simplement
jamais **explicité dans un ADR** :

- [ADR 0038](../decisions/0038-lima-seul-banc-local.md) (Lima seul banc local),
  [ADR 0040](../decisions/0040-terrains-x-topologies.md) (terrains ×
  topologies), [ADR 0048](../decisions/0048-acces-local-developpeur.md) (accès
  local développeur) posent **poste macOS Apple Silicon + VM Linux**.
- [`bench/lima/README.md`](../../bench/lima/README.md) et
  [`CONTRIBUTING.md`](../../CONTRIBUTING.md) (§ Installation) documentent
  l'installation par `brew install …` — poste macOS / Homebrew, **zéro mention**
  de `apt` Linux, de Windows ou de WSL.
- À l'inverse, la portabilité macOS ↔ Linux est **déjà soignée** là où elle
  compte (cf. CONTRA des findings) : doubles chemins `date` GNU/BSD, substitut
  portable de `mapfile`, `sysctl hw.model` vs `uname -s`.

Ce passage ne crée donc pas de contrainte nouvelle : il **nomme** une frontière
déjà tenue, pour qu'elle soit (a) opposable à un contributeur, (b) exploitable
pour piloter le banc. Conformément à la doctrine
[ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md), **les manques
deviennent des issues** — pas des correctifs improvisés ici.

## Majeur (1)

### P-CRLF — Risque CRLF non couvert (absence de `.gitattributes`)

**Problème.** Il n'existe **aucun** `.gitattributes` à la racine, et
[`.prettierrc.json`](../../.prettierrc.json) ne fixe pas `endOfLine`.
Conséquence : un clone effectué sur Windows — ou tout poste avec
`core.autocrlf=true`, qui est le **défaut de Git for Windows** — récupère les
~67 fichiers `*.sh` en **CRLF**. Le shebang devient alors
`#!/usr/bin/env bash\r`, et l'exécution dans la VM Lima/Linux échoue avec :

```text
/usr/bin/env: 'bash\r': No such file or directory
```

Cela **casse** `run-phases.sh`, `nestor.sh` et tout script du banc. C'est le
**seul trou qui menace même les OS supportés** : un mainteneur sur un poste mal
configuré, ou un futur contributeur **WSL2 dont le checkout vit côté Windows**,
est touché. La **CI 100 % Linux ne l'attrape jamais** (un dépôt déjà en LF côté
serveur ne révèle pas le problème de conversion côté client).

**Evidence.**

- Absence de `.gitattributes` et de `.editorconfig` à la racine (ni sur disque,
  ni tracké — vérifié `ls` + `git ls-files`).
- [`.prettierrc.json`](../../.prettierrc.json) — aucune occurrence de
  `endOfLine`.
- ~67 fichiers `*.sh` trackés (aucun actuellement en CRLF : le risque est à la
  **conversion future** côté client, pas dans l'état présent).

**Recommandation.** Ajouter un `.gitattributes` à la racine :

```gitattributes
* text=auto eol=lf
*.png binary
*.jpg binary
*.gif binary
*.ico binary
```

`* text=auto eol=lf` normalise les fichiers texte en LF **dans le dépôt** quel
que soit le poste du contributeur ; déclarer explicitement les binaires évite
toute corruption. Optionnel : `endOfLine: "lf"` dans `.prettierrc.json` pour
cohérence de l'outillage. Correctif **append-only**, sans risque pour les OS
déjà supportés.

## Mineurs

### P-MAPFILE — Incohérence avec la politique bash 3.2 déjà affichée

**Problème.** Deux scénarios utilisent `mapfile -t` **sans garde**, alors que le
dépôt **affiche déjà** une politique de compatibilité bash 3.2 (le `/bin/bash`
système de macOS est en 3.2.57, où `mapfile`/`readarray` sont **absents**).
[`bench/lima/access.sh:75`](../../bench/lima/access.sh#L75) fournit pourtant un
substitut portable **documenté** — `read_lines()` — dont le commentaire dit
explicitement « _substitut portable de mapfile/readarray, absents du bash 3.2 de
macOS_ ». La fragilité est **conditionnelle** : OK si le `bash` du `PATH` est
récent (le cas par défaut via `#!/usr/bin/env bash` → Homebrew 5.x), KO si
exécuté sous `/bin/bash` 3.2. Or ces scénarios **peuvent tourner depuis le poste
de contrôle** (le scénario 20 pilote via `kubectl`).

**Evidence.**

- [`bench/scenarios/20-chaos-kill-pods.sh:124`](../../bench/scenarios/20-chaos-kill-pods.sh#L124)
  — `mapfile -t victims < <(list_targets | pick "$KILL_N")`, sans garde.
  Contexte = poste de contrôle (pilotage `kubectl`).
- [`bench/scenarios/31-contract-endpoints.sh:67`](../../bench/scenarios/31-contract-endpoints.sh#L67)
  — `mapfile -t ids < <(yq -r …)`, sans garde.
- Substitut disponible :
  [`bench/lima/access.sh:73`](../../bench/lima/access.sh#L73)-81 (`read_lines()`
  via `while IFS= read -r`).

**Recommandation.** Réutiliser `read_lines()` (sourcer `access.sh` ou copier le
helper) dans les deux scénarios, pour aligner ces fichiers sur la politique de
portabilité déjà tenue ailleurs.

### P-PY — Accrocs Python de propreté (contrôleur Unix, Windows hors-scope par conception)

**Problème.** Le code Python du poste est un **contrôleur Unix** (il pilote
`bash` / `ssh` / `sudo` / `kubectl`) : le **Windows-natif est hors-scope PAR
CONCEPTION**, cohérent avec le périmètre assumé. Subsistent toutefois des
accrocs résiduels — bénins aujourd'hui, à encadrer **uniquement si** Windows/WSL
devenait un objectif explicite ; sinon, simple **dette de propreté**.

**Evidence.**

- [`scripts/topology.py:446`](../../scripts/topology.py#L446) —
  `os.symlink(target_rel, link)` (lien `topology.yaml` à la racine) : exige
  Admin / Developer Mode sous Windows (`WinError 1314`).
- [`scripts/topology.py:1629`](../../scripts/topology.py#L1629) —
  `os.chmod(out_path, 0o600)` sur un KUBECONFIG rapatrié : **silencieusement
  ignoré** sous Windows → fichier sensible non protégé.
- [`nestor/roundtrip.py:169`](../../nestor/roundtrip.py#L169) —
  `subprocess.run(['bash','-c', f'kubectl … 2>/dev/null'])` : **réductible** en
  `subprocess` pur avec `stderr=DEVNULL`, ce qui **supprime une dépendance à
  `bash`**.
- [`tests/test_runner.py:88`](../../tests/test_runner.py#L88),
  [`:90`](../../tests/test_runner.py#L90),
  [`:113`](../../tests/test_runner.py#L113) — `open(…, "w")` sans `encoding=` (3
  occurrences). Contenu ASCII (JSON / flags) → **bénin**, à uniformiser.

**Recommandation.** Ne **rien corriger en urgence** (hors-scope assumé). Si
Windows/WSL est un jour acté comme objectif : remplacer le symlink par une copie
(ou un fallback), durcir le KUBECONFIG via les ACL adéquates, réduire
`roundtrip.py:169` en `subprocess` pur. Le seul nettoyage **gratuit**
indépendant du périmètre = ajouter `encoding="utf-8"` aux trois `open()`.

## Architecture (x86 ↔ arm) — assumée et bien tenue

Axe distinct de l'OS, et **plus mûr** : là où le périmètre OS est assumé mais
_implicite_, l'architecture est un sujet de **premier plan, décidé en ADR**. Le
pattern structurant est **banc arm64 (Apple Silicon / Lima) ↔ prod x86
(bare-metal)**, et le code **branche explicitement** sur l'architecture plutôt
que de l'ignorer.

**Ce qui est déjà décidé (à garder).**

- **Images épinglées par _digest d'index multi-arch_**
  ([ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)) :
  un même manifeste résout sur arm64 (banc) **et** amd64 (prod). Le
  [CLAUDE.md](../../CLAUDE.md) rappelle de vérifier `MediaType: …image.index…`
  avant d'épingler.
- **Images officielles amd64-only** (Dagster, Marquez —
  [ADR 0026](../decisions/0026-orchestration-dagster.md) /
  [ADR 0028](../decisions/0028-orchestration-openlineage-marquez.md)) :
  rebuildées localement en arm64 sur le banc, re-taggées sur x86.
- **Terrain cloud ARM cadré**
  ([ADR 0031](../decisions/0031-terrain-cloud-arm.md)) : acte que toute la
  couverture actuelle est arm64 / Apple Silicon.

**Evidence (le code dérive l'arch, ne la code pas en dur).**

- [`bootstrap/roles/platform-build-images/tasks/image.yaml:25`](../../bootstrap/roles/platform-build-images/tasks/image.yaml#L25)-54
  — « **Build (arm64) or retag (x86)** » :
  `--platform {{ 'linux/arm64' if ansible_facts.architecture == 'aarch64' else 'linux/amd64' }}`.
  arm64 → build interne (`nerdctl`/buildkit) ; x86 → `Pull official amd64 image`
  puis re-tag.
- [`bootstrap/cni.sh:11`](../../bootstrap/cni.sh#L11)-12 —
  `CLI_ARCH=amd64 ; [ "$(uname -m)" = "aarch64" ] && CLI_ARCH=arm64` pour
  télécharger le bon binaire **`cilium-linux-${CLI_ARCH}`**. Correct **car
  node-side** : `uname -m` y est celui du nœud Linux, et le tarball ciblé est
  bien `linux` (pas `darwin`). Lancé depuis le Mac, ce binaire serait du mauvais
  OS — mais ce script ne tourne **jamais** poste-side (contexte 1).
- Le harnais banc **dé-épingle** les images multi-arch en copies arm64 «
  undigest » **hors dépôt**, par surcharge de profil — jamais codé en dur dans
  le rôle :
  [`bootstrap/roles/platform-ceph-cluster/defaults/main.yaml:13`](../../bootstrap/roles/platform-ceph-cluster/defaults/main.yaml#L13)-14.
- Discipline inverse explicite :
  [`bootstrap/portal.yaml:62`](../../bootstrap/portal.yaml#L62)-64 note que
  certaines copies « tournent **AUSSI en x86** (pas de garde
  `when arch==aarch64`) » — preuve que l'asymétrie est pensée, pas subie.

**Point de vigilance (assumé, pas une dette).** La **couverture de preuve est
déséquilibrée** : presque tout est **prouvé en arm64** (banc Lima), le chemin
x86 (`Pull official amd64` + re-tag, `ansible_facts.architecture == 'x86_64'`)
est **moins exercé** par le banc — c'est exactement le trou cadré par
[ADR 0031](../decisions/0031-terrain-cloud-arm.md). Ce n'est **pas** du code
non-portable : c'est une **asymétrie de validation**, à garder en tête lors
d'une bascule prod x86, sans en faire un correctif.

## Info / périmètre assumé

### P-TOOLING — Windows natif exclu pour contribuer (conséquence assumée)

**Problème.** La chaîne de **validation contributeur** suppose un Unix : pipes
POSIX dans [`package.json`](../../package.json) (`lint:shell`, `lint:k8s` :
`find … -print0 | xargs -0`, `git ls-files -z | xargs -0`), hooks shell dans
[`lefthook.yml`](../../lefthook.yml), `kubeconform` sans build Windows, `bats`
qui exige `bash`. **Conséquence : Windows natif est exclu pour contribuer.**
macOS et Linux fonctionnent ; **WSL2 fonctionne**. Ce n'est **pas un bug** :
c'est une conséquence **assumée** du périmètre, à **documenter** (ADR 0100), pas
à corriger.

**Recommandation.** **Documenter** explicitement (ADR léger + tableau OS
ci-dessous). Aucun correctif code.

### P-CI — CI 100 % `ubuntu-latest` (dérives BSD/GNU et x86/arm invisibles)

**Problème.** Les 22 jobs CI tournent **exclusivement** sur `ubuntu-latest`
(x86) — aucun `macos-latest` (qui serait arm64) ni `windows-latest`. Conséquence
: toute dérive BSD/GNU (un `date -d` sans fallback, un `sed -i` non portable…)
**et** toute régression arm64 n'est **jamais détectée avant le poste du
mainteneur**. C'est un **filet manquant**, pas un bug.

**Evidence.** Workflows CI : 22 jobs, 100 % `ubuntu-latest` (aucune occurrence
de `macos-latest` / `windows-latest` dans
[`.github/workflows/`](../../.github/workflows/)).

**Recommandation.** **Optionnel** : ajouter un job `macos-latest` minimal (lint
et tests) — il fait d'une pierre deux coups, filet BSD/GNU **et** arm64. À
pondérer (coût minutes runner).

## Faux positifs écartés

Vérification **adversariale** menée sur le poste (macOS 26.5). **3 pistes
écartées** :

1. **« `find … -print0 | xargs -0` et `git ls-files -z | xargs -0` cassés sur
   macOS »** → **FAUX**. Vérifié empiriquement : les deux commandes sortent
   **EXIT=0** sur macOS 26.5 (les `find`/`xargs` BSD modernes supportent
   `-print0`/`-0`). L'affirmation « `lint:shell`/`lint:k8s` cassés sur macOS »
   est un **faux positif**. Ces pipes ne cassent **que** sur Windows `cmd.exe`
   natif (où `find`/`xargs` POSIX sont absents) — déjà couvert par P-TOOLING.

2. **Sur-classement des commandes node-side.** `stat -c`, `date -d`, `getent`,
   `hostname -I` sont du **Linux garanti**, exécutés node-side via SSH (heredocs
   de [`bootstrap/state.sh:180`](../../bootstrap/state.sh#L180)-189 et
   [`bench/scenarios/09-etcd-restore.sh:93`](../../bench/scenarios/09-etcd-restore.sh#L93)-111).
   Les classer « non portables » serait une erreur de lecture : **hors-scope**
   du poste (contexte 1).

3. **« Politique bash 3.2 contredite partout. »** → **FAUX en l'état** : la
   politique est au contraire **bien tenue** aux endroits sensibles. CONTRA
   confirmés :
   [`bench/lima/check-freshness.sh:50`](../../bench/lima/check-freshness.sh#L50)-51
   (double chemin `date` GNU `-d` **avec** fallback BSD `-j -f`),
   [`bench/lima/access.sh:75`](../../bench/lima/access.sh#L75) (`read_lines()`),
   [`bench/lima/metrology.sh:241`](../../bench/lima/metrology.sh#L241)-242
   (`sysctl -n hw.model … || uname -s`),
   [`scripts/audit-image-digests.sh:47`](../../scripts/audit-image-digests.sh#L47)
   (commentaire « _while read plutôt que mapfile : compatible bash 3.2_ »).
   Seuls **deux** scénarios dérogent (P-MAPFILE) — d'où le classement
   **mineur**, pas majeur.

Fait empirique consolidé : `/bin/bash` système = **3.2.57** (`mapfile` → «
command not found ») ; `bash` du `PATH` = **5.3 Homebrew** (`mapfile` présent).
Les scripts `#!/usr/bin/env bash` prennent le `bash` du `PATH` → P-MAPFILE reste
**conditionnel** (d'où mineur).

## Décisions de forme / suites

Conformément à la doctrine
[ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md) (« les manques
deviennent des issues »), cet audit **ne mute rien** ; il alimente trois suites
:

1. **ADR léger [`0100`](../decisions/0100-perimetre-os-poste-et-noeuds.md) —
   acter le périmètre OS.** Contenu : nommer la frontière des trois contextes,
   déclarer **Windows natif non supporté / WSL2 supporté**, rappeler le couple
   **arch banc arm64 ↔ prod x86** (renvoi ADR 0006/0031 et 0099, qui érige
   l'architecture en axe de topologie), et renvoyer aux
   [ADR 0038](../decisions/0038-lima-seul-banc-local.md) /
   [0040](../decisions/0040-terrains-x-topologies.md) /
   [0048](../decisions/0048-acces-local-developpeur.md) qui le posent déjà
   implicitement.

2. **Issue de suivi** (template `feat`, français, labels `dx` / `documentation`
   / `lima`) : porter le correctif `.gitattributes` (P-CRLF), aligner les deux
   scénarios sur `read_lines()` (P-MAPFILE), et — optionnel — le job CI
   `macos-latest` (P-CI) + les nettoyages Python de propreté (P-PY). Lier ce
   passage d'audit et l'ADR 0100.

3. **Correctif `.gitattributes`** (P-CRLF) : seul correctif **réellement
   nécessaire** ; append-only, sans risque pour les OS supportés. À porter dans
   l'issue ci-dessus.

Ce rapport est **append-only** et référencé par une ligne dans
[`docs/audit/README.md`](./README.md).

## OS × architecture supportés

Tableau de référence — pour **contribuer** (outillage / CI) **et** pour
**piloter le banc** (poste de contrôle ↔ nœuds). À reprendre dans l'ADR 0100.

| OS / arch                             | Contribuer (lint/hooks/CI)                             | Piloter le banc (poste de contrôle)                     | Statut                                                        |
| ------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------------------- |
| **Linux** (Debian/Ubuntu, x86 ou arm) | ✅                                                     | ✅ (poste **et** nœuds — OS cible garanti)              | **Supporté**                                                  |
| **macOS** (Apple Silicon, arm64)      | ✅                                                     | ✅ (poste de contrôle — cf. ADR 0038/0048)              | **Supporté**                                                  |
| **Windows natif**                     | ❌ (pas de `find`/`xargs` POSIX, `bats`/`kubeconform`) | ❌ (`os.symlink`, `os.chmod`, dépendances `bash`/`ssh`) | **Non supporté — assumé**                                     |
| **WSL2** (Ubuntu sur Windows)         | ✅                                                     | ✅                                                      | **Supporté** (checkout **côté Linux** impératif — cf. P-CRLF) |

**Architecture cible.** Nœuds **x86** (bare-metal prod) **et** **arm64** (banc
Lima, cloud ARM) tous deux supportés, dérivés de `ansible_facts.architecture`
(cf. section « Architecture (x86 ↔ arm) » ci-dessus). Seule réserve : le chemin
**x86 est moins exercé** par le banc (arm64), cf.
[ADR 0031](../decisions/0031-terrain-cloud-arm.md).

> **Note WSL2** : le support suppose un checkout du dépôt **dans le système de
> fichiers Linux** de la distribution WSL (ex. `~/…`), **pas** un checkout côté
> Windows (`/mnt/c/…`) monté dans WSL — ce dernier réintroduit le risque CRLF de
> P-CRLF tant que `.gitattributes` n'est pas en place.
