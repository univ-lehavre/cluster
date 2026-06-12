# 5 — Reproductibilité & pinning des versions

**Note : 3,8 / 5**

Pinning globalement sérieux et au-dessus de la moyenne pour un dépôt de
recherche : **aucun tag `:latest`**, matrice de versions documentée (ADR 0006),
lockfile `pnpm` committé + `--frozen-lockfile`, versions explicites pour la
quasi-totalité des composants. Trois écarts entament la reproductibilité réelle
: toolbox Ceph sur tag flottant `v19`, `containerd.io` non figé malgré l'ADR
0005, et `kubeadm init` sans `kubernetesVersion` (patch K8s qui dérive). La CI
elle-même dépend d'actions sur branches mutables.

## Points forts

- Aucun tag `:latest` dans l'ensemble des manifests et scripts.
- Matrice de versions formalisée et datée (ADR 0006) avec politique de bump.
- Dépôt K8s figé sur `v1.34` + `dpkg_selections: hold` sur
  kubelet/kubeadm/kubectl.
- Cilium figé deux fois (CLI `v0.19.4` avec vérif sha256, chart `1.19.4`).
- Rook `v1.19.6`, Ceph `v20.2.1` (`allowUnsupported: false`).
- Images applicatives sur tags fixes (registry `3.1.1`, rocker `4.6.0`, chart
  dashboard `7.10.0`).
- Collections Ansible figées exactes ; `packageManager: pnpm@11.3.0` ; CI en
  `--frozen-lockfile`.
- Vagrant box `bento/debian-13` + `box_architecture` explicites.

## Constats

### Majeur (→ vérifié majeur) — Toolbox Ceph sur tag flottant `:v19` désaccordé

- **Fichier** : `storage/ceph/toolbox.yaml:22`
- **Constat** : `quay.io/ceph/ceph:v19` est un tag majeur flottant (non
  déterministe) ; **pire**, le cluster tourne en `v20.2.1`. Le toolbox exécute
  des commandes `ceph` → client Squid v19 contre cluster Tentacle v20 = écart de
  version majeure. L'ADR 0006 interdit explicitement le tag `:N` flottant, et le
  toolbox n'est même pas dans la matrice.
- **Recommandation** : aligner sur `quay.io/ceph/ceph:v20.2.1` (idéalement avec
  digest), ajouter à la matrice ADR 0006.

### Mineur (→ vérifié mineur) — `containerd.io` non figé par `apt-mark hold`

- **Fichier** : `bootstrap/roles/k8s-CRI-install/tasks/main.yaml:80-84`
- **Constat** : installé en `state: present` sans hold, alors que l'ADR 0005
  affirme qu'un hold est posé ; `upgrade-os` (`apt full-upgrade`) peut bumper
  containerd silencieusement. _Ramené à mineur : drift doc/code via le chemin de
  maintenance uniquement, sans casser bootstrap ni sécurité._
- **Recommandation** :
  `dpkg_selections: { name: containerd.io, selection: hold }` après
  l'installation (+ version `2.2.4`), **ou** corriger l'ADR.

### Mineur (→ vérifié mineur) — `kubeadm init` sans `kubernetesVersion`

- **Fichier** : `bootstrap/roles/k8s-initialization/tasks/main.yaml:12-18`
- **Constat** : aucun `--kubernetes-version` ni `ClusterConfiguration` ;
  kubelet/ kubeadm en `state: present` (seul le minor 1.34 est figé par l'URL du
  dépôt). Deux bootstraps à deux dates installent deux patchs différents.
  _Ramené à mineur : borné au même minor testé, patchs rétro-compatibles,
  n'affecte que les installs neuves._
- **Recommandation** : figer le patch (`kubeadm=1.34.X-*`) +
  `kubernetesVersion: v1.34.X` via config kubeadm, aligné sur la matrice.

### Mineur — Actions GitHub sur tags flottants `@main`/`@master`

- **Fichier** : `.github/workflows/ci.yml:34,74`
- **Constat** : `ludeeus/action-shellcheck@master`, `ansible/ansible-lint@main`
  ; les autres actions sur tags majeurs mutables (`@v4`). La CI, garde-fou de
  reproductibilité, n'est pas elle-même reproductible.
- **Recommandation** : épingler au moins par tag de release, idéalement par SHA
  complet (`@<sha> # vX.Y.Z`).

### Mineur — devDependencies en ranges `^`

- **Constat** : risque atténué par le lockfile + `--frozen-lockfile`.
  Acceptable.
- **Recommandation** : figer exact si reproductibilité stricte souhaitée, ou
  documenter que le lockfile est la source de vérité.

### Suggestions

- Images d'exemples WordPress/MySQL sur tags partiellement flottants
  (`mysql:8.4`) → piger exact ou commenter « exemples hors matrice ».
- Incohérence Tentacle/Squid + avertissement `allowUnsupported` upstream dans
  `cluster.yaml:25-27` → confirmer le support Ceph v20 par Rook v1.19.6 et
  mettre à jour le commentaire obsolète.

> **Lien supply chain :** l'absence totale de digest `@sha256` et de signatures
> est traitée comme un finding **majeur** sous l'angle gestion du risque OSS —
> voir [11-logiciels-oss.md](11-logiciels-oss.md).
