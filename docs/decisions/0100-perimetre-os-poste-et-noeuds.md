# 0100 — Périmètre OS & architecture : poste de contrôle Unix, nœuds Linux, Windows → WSL

## Statut

Accepted (2026-06-30)

Acte un périmètre **déjà tenu** mais jamais explicité. S'appuie sur
[0038](0038-lima-seul-banc-local.md) (Lima seul banc local, poste Apple
Silicon), [0040](0040-terrains-x-topologies.md) (terrains × topologies) et
[0048](0048-acces-local-developpeur.md) (accès local développeur) — qui posent
déjà **poste macOS + VM Linux** sans le nommer comme une frontière de support.
Cohérent avec [0017](0017-langage-des-scripts.md) /
[0049](0049-doctrine-choix-outil-par-action.md) (bash node-side, Python testé)
et [0097](0097-moteur-chemin-python-bash-artefacts.md) (le bash restant est
node-side). L'axe **architecture** prolonge
[0006](0006-matrice-de-versions-et-politique-de-bump.md) (digest d'index
multi-arch) et [0031](0031-terrain-cloud-arm.md) (terrain cloud ARM), et
**complète** [0099](0099-axes-du-modele-topologie.md) qui érige l'architecture
(`catalog.arch : arm64 · x86`) en axe DÉCLARATIF de la topologie : 0099 dit
_quelle_ arche une topologie cible, 0100 dit _ce que le code doit garantir_ pour
tourner sur l'une ou l'autre. Émis à la suite du passage d'audit
[2026-06-30 — portabilité](../audit/2026-06-30-audit-portabilite.md) (doctrine
[0058](0058-doctrine-audit-grille-passages.md) : les manques deviennent des
issues). Valeurs d'exemple génériques
([0023](0023-plateforme-exemple-generique.md)) : `cp1`, `node1`…`node4`, `banc`.

## Contexte

Ce dépôt n'est pas un programme unique : c'est un **catalogue d'infra** dont le
code s'exécute dans **trois contextes**, chacun avec sa contrainte d'OS et
d'architecture propre. La frontière de portabilité n'est donc pas le fichier,
c'est le **point d'exécution** :

1. **Cible — les nœuds.** [`bootstrap/state.sh`](../../bootstrap/state.sh),
   [`bootstrap/first-access.sh`](../../bootstrap/first-access.sh), les blocs
   SSH/heredoc, le scénario 09 (etcd). OS = **Linux Debian, toujours**. Les
   commandes GNU (`stat -c`, `date -d`, `getent`, `hostname -I`, `systemctl`,
   `apt-get`, `crictl`) y sont **légitimes** : elles partent node-side via SSH,
   ne s'exécutent **jamais** sur le poste.
2. **Poste de contrôle — le pilote.** `bench/lima/*`, `nestor/*.py`,
   `scripts/*.py`, les scénarios pilotés `kubectl`. OS = **macOS OU Linux**. La
   portabilité macOS ↔ Linux **y est requise**, et déjà soignée par endroits
   (doubles chemins `date` GNU/BSD dans
   [`bench/lima/check-freshness.sh`](../../bench/lima/check-freshness.sh),
   substitut portable de `mapfile` dans
   [`bench/lima/access.sh`](../../bench/lima/access.sh), `sysctl hw.model` vs
   `uname -s` dans [`bench/lima/metrology.sh`](../../bench/lima/metrology.sh)).
3. **Outillage contributeur — la validation.**
   [`package.json`](../../package.json), [`lefthook.yml`](../../lefthook.yml),
   hooks, CI. OS = **macOS / Linux / WSL**. Les pipes POSIX
   (`find … -print0 | xargs -0`), `bats`, `kubeconform` y supposent un Unix.

**Axe architecture.** Le poste est arm64 (Apple Silicon), les nœuds **banc**
sont arm64 (VM Lima), les nœuds **prod** sont x86 (bare-metal). Le code
**dérive** l'architecture plutôt que de la coder en dur : « build (arm64) or
retag (x86) » piloté par `ansible_facts.architecture` dans
[`bootstrap/roles/platform-build-images/tasks/image.yaml`](../../bootstrap/roles/platform-build-images/tasks/image.yaml),
binaire `cilium-linux-${CLI_ARCH}` dérivé de `uname -m` dans
[`bootstrap/cni.sh`](../../bootstrap/cni.sh), images épinglées par digest
**d'index multi-arch**
([0006](0006-matrice-de-versions-et-politique-de-bump.md)) résolvant sur arm64
**et** amd64.

Ce périmètre fonctionne mais reste **implicite** :
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) documente l'installation par
`brew install …` (macOS / Homebrew) sans mention de `apt`, de Windows ni de WSL.
Rien ne dit à un contributeur ce qui est supporté, ni ne ferme le seul trou
technique qui menace **même les OS supportés** : l'absence de `.gitattributes`
(un checkout côté Windows convertit les `*.sh` en CRLF → `#!/usr/bin/env bash\r`
→ `/usr/bin/env: 'bash\r': No such file or directory` dans la VM Linux ; la CI
100 % Linux ne l'attrape jamais).

## Décision

### 1. Périmètre OS supporté

| OS / arch                             | Contribuer (lint/hooks/CI)               | Piloter le banc (poste de contrôle) | Statut                             |
| ------------------------------------- | ---------------------------------------- | ----------------------------------- | ---------------------------------- |
| **Linux** (Debian/Ubuntu, x86 ou arm) | supporté                                 | supporté (poste **et** nœuds)       | **Supporté**                       |
| **macOS** (Apple Silicon, arm64)      | supporté                                 | supporté (poste de contrôle)        | **Supporté**                       |
| **Windows natif**                     | non (pipes POSIX, `bats`, `kubeconform`) | non (`bash`/`ssh`, symlinks)        | **Non supporté — assumé**          |
| **WSL2** (Ubuntu sur Windows)         | supporté                                 | supporté                            | **Supporté** (checkout côté Linux) |

**Windows natif n'est pas un terrain de contribution** — décision assumée, pas
une dette : le supporter (réécrire les pipes POSIX, retirer la dépendance bash
de `bats`, etc.) serait disproportionné pour un catalogue d'infra Kubernetes
mono-mainteneur, alors que **WSL2 couvre ce besoin à coût nul**. Le support WSL2
suppose un checkout dans le système de fichiers **Linux** de la distribution
(`~/…`), pas un checkout côté Windows (`/mnt/c/…`) — sinon le risque CRLF
réapparaît.

### 2. Architecture supportée

Nœuds **x86** (bare-metal prod) **et** **arm64** (banc Lima, cloud ARM) tous
deux supportés, dérivés de l'architecture détectée — jamais codés en dur.
Réserve **assumée** : le chemin x86 est **moins exercé** que l'arm64 par le banc
(qui tourne sur Apple Silicon), cf. [0031](0031-terrain-cloud-arm.md) ; une
bascule prod x86 reste à valider de bout en bout.

### 3. Garde-fou — normalisation des fins de ligne

Un [`.gitattributes`](../../.gitattributes) racine impose `* text=auto eol=lf`
(+ binaires en `binary`) : LF **dans le dépôt** quel que soit le poste du
contributeur, indépendamment de sa config Git locale. Ferme le risque CRLF même
sur les OS supportés (mainteneur mal configuré, contributeur WSL via un checkout
Windows).

### 4. Filet CI

Un job CI `portability-macos` sur `macos-latest`
([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)) rejoue les tests
shell (`bats`) et Python sur **macOS arm64** : un seul runner couvre l'axe
**OS** (BSD vs GNU) et l'axe **architecture** (arm64), pour détecter une dérive
avant qu'elle n'atteigne le poste du mainteneur.

### 5. Discipline de code (poste de contrôle)

- Les fonctions du poste qui peuvent tourner sur le bash 3.2 de macOS
  n'emploient pas `mapfile`/`readarray` (bash 4+) : substitut `read_lines()`
  ([`bench/scenarios/lib.sh`](../../bench/scenarios/lib.sh),
  [`bench/lima/access.sh`](../../bench/lima/access.sh)).
- Le code Python du poste reste un **contrôleur Unix** (pilote `bash`/`ssh`/
  `sudo`/`kubectl`) : `os.symlink`, `os.chmod(0o600)` et consorts sont des
  primitives **POSIX assumées**, pas à brancher pour Windows natif (hors-scope).
  On préfère néanmoins l'appel direct à un binaire (`kubectl …`) au détour par
  `bash -c "… 2>/dev/null"` quand c'est gratuit (cf.
  [`nestor/roundtrip.py`](../../nestor/roundtrip.py)).

## Conséquences

- **Positif.** Le périmètre devient **opposable** (un contributeur sait ce qui
  est supporté) et **outillé** (`.gitattributes` + filet CI macOS). Le risque
  CRLF est clos ; les dérives BSD/GNU et arm64 sont détectées en CI.
- **Coût.** Un job CI supplémentaire (`macos-latest`, minutes runner plus chères
  que Linux — périmètre volontairement minimal : shell + Python, pas tout le
  lint). `CONTRIBUTING.md` /
  [`bench/lima/README.md`](../../bench/lima/README.md) à compléter (Linux `apt`,
  WSL2).
- **Limite assumée.** Windows natif reste hors-scope ; la couverture de preuve
  x86 reste moindre que l'arm64 tant que le terrain cloud ARM
  ([0031](0031-terrain-cloud-arm.md)) n'est pas généralisé.
