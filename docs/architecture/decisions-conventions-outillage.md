# Décisions — Conventions & outillage

> Cette page est une **vue thématique** au-dessus des ADR (Architecture Decision
> Records). Les ADR restent la **source de vérité datée et immuable** ; cette
> page ne les remplace pas, elle les **agrège** et les **raconte** sous l'angle
> « comment on construit » — le runtime de conteneurs, la discipline de versions
> et le langage des scripts. Pour le détail et l'historique, suivez les liens
> vers chaque ADR.

Ce domaine couvre trois décisions qui se tiennent : d'où vient le runtime de
conteneurs ([ADR 0005](../decisions/0005-cri-containerd-via-depot-docker.md)),
comment on fige et fait monter les versions
([ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)), et
dans quel langage on écrit l'outillage
([ADR 0017](../decisions/0017-langage-des-scripts.md)). Le fil conducteur :
**reproductibilité** et **inspectabilité** par un public néophyte, sans
toolchain lourde.

## Le runtime : containerd.io depuis le dépôt Docker

Kubernetes a besoin d'un CRI (Container Runtime Interface). Trois pistes ont été
pesées : Docker (déprécié comme CRI K8s depuis 1.24), le `containerd` natif de
Debian 13 Trixie (version **1.7.x**, en fin de support upstream qui est passé à
la 2.x), et `containerd.io` depuis `download.docker.com` (**2.2.4**, maintenu
activement). Le besoin était un CRI **récent, maintenu et compatible Kubernetes
1.34** que le banc multi-nœuds puisse rejouer à l'identique.

La décision retenue est `containerd.io` **depuis le dépôt Docker**, sur tous les
nœuds, piloté par le rôle Ansible `k8s-CRI-install` :

- ajout du dépôt `download.docker.com/linux/debian`, signé par une clé GPG
  distincte de celle de Debian (`/etc/apt/keyrings/docker.asc`) ;
- installation du paquet `containerd.io` ;
- configuration par défaut générée, puis patch `SystemdCgroup = true` dans
  `/etc/containerd/config.toml`.

Le couple validé sur le banc est **containerd.io 2.2.4** avec le kernel
`6.12.48+deb13-arm64`. La bascule depuis l'historique (containerd 1.7 natif
Debian) a été faite pendant le rebuild Debian 13. Voir
[ADR 0005](../decisions/0005-cri-containerd-via-depot-docker.md).

## La matrice de versions et la politique de bump

Le cluster est un assemblage de composants liés par des **contraintes de
compatibilité croisées** : Cilium ↔ K8s, Rook ↔ K8s, Ceph ↔ Rook, containerd ↔
K8s, chart Helm du dashboard ↔ K8s. Bumper l'un sans vérifier les autres mène à
un drift silencieux jusqu'à un échec de provisionnement. Ces compatibilités ont
été vérifiées en mai 2026 : le **plafond commun K8s est 1.34**, imposé par
Cilium 1.19 et Rook 1.19 (tous deux testés jusqu'à K8s 1.34). Ceph Squid v19
sort d'EOL en septembre 2026, d'où le choix de **Ceph 20.2.1 Tentacle** pour une
install neuve.

La matrice cible (mai 2026) fixe chaque version à un fichier qui la pilote :

| Composant       | Version cible   | Piloté par                                    |
| --------------- | --------------- | --------------------------------------------- |
| Kubernetes      | 1.34            | rôle `k8s-install` (`pkgs.k8s.io/v1.34`)      |
| Cilium          | 1.19.x          | `bootstrap/cni.sh` (CLI épinglée)             |
| Rook            | 1.19.x          | `storage/ceph/operator.yaml`                  |
| Ceph            | 20.2.1 Tentacle | `storage/ceph/cluster.yaml`                   |
| containerd.io   | 2.2.4           | dépôt Docker (cf. ADR 0005)                   |
| Dashboard chart | 7.10.0          | `platform/k8s-dashboard/manage.sh`            |
| Registry image  | 3.1.1           | `platform/container-registry/deployment.yaml` |
| Gateway API CRD | 1.4.1           | `platform/cilium-expo/`                       |
| cert-manager    | 1.20.2          | `cert-manager.yaml` (images par digest)       |
| Argo CD         | 3.4.3           | `platform/argocd/argocd.yaml` (par digest)    |

La **politique de bump** se résume en cinq règles :

1. **Pas de bump silencieux** : toute montée de version passe par une branche
   dédiée et une PR.
2. **Vérifier la compat croisée avant** : release notes de Cilium (quel K8s
   testé ?), de Rook (quel K8s, quel Ceph ?), de Ceph (quelle version Rook
   minimale ?).
3. **Pinner partout** : tags d'image avec version explicite, jamais `:latest` ni
   `:N` flottant — idéalement avec **digest** pour les composants critiques
   (c'est le cas de cert-manager et d'Argo CD dans la matrice).
4. **Valider sur le banc Lima multi-nœuds** ([`bench/lima/`](../../bench/lima/))
   avant la prod : déployer, vérifier que `state.sh` est vert sur toutes les
   couches, et jouer un cycle bootstrap → rollback → re-bootstrap.
5. **Mettre à jour l'ADR** (nouvelle matrice et date).

Ce pinning éclaire le coût assumé côté CRI : containerd.io n'étant pas figé à
Debian, un `apt upgrade` pourrait le bumper sans test ; le rôle pose donc un
`apt-mark hold containerd.io`, à libérer **explicitement** pour bumper. Voir
[ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md) et
[ADR 0005](../decisions/0005-cri-containerd-via-depot-docker.md). L'étape de
validation sur banc est détaillée dans la vue
[validation banc](../architecture/validation-banc.md).

## Le langage de l'outillage : bash, jq, python3, bats

L'audit du dépôt a remis en cause bash pour les ~890 LOC de scripts (`state.sh`,
`run-phases.sh`, scénarios, `cni.sh`, helpers). Verdict : bash est le **bon
outil** ici (orchestration de CLIs — kubectl, ceph, vagrant, ssh), mais ce choix
n'était formalisé nulle part, au risque qu'un contributeur réécrive « pour faire
mieux » en Go ou Python, à perte.

La décision pose **bash comme langage d'orchestration**, avec des règles claires
:

- **Orchestration de CLIs → bash.** `set -euo pipefail`, shellcheck à 0 warning
  (hook et CI), en-tête docblock. C'est le cœur du dépôt.
- **Parsing structuré → `jq`**, pas `awk`/`grep`/`cut` sur des sorties humaines.
  Les sorties des CLIs sont lues en JSON (`kubectl -o json`, `ceph -f json`) ;
  `jq` est une dépendance assumée.
- **Fonctions pures → bats-core.** La logique isolable (classification,
  comptage, parsing) est extraite dans des libs sourçables (`bootstrap/lib/`) et
  testée par bats (`bench/unit/`) : shellcheck valide la **syntaxe**, bats
  valide le **comportement**.
- **python3 toléré, pas imposé.** Pour une tâche où bash deviendrait illisible
  (données complexes, calculs), python3 (présent partout) est acceptable, mais
  reste l'exception.

L'audit liste aussi ce qu'il ne faut **pas** faire : porter en Go (aucun binaire
à distribuer, public néophyte, opacité accrue) ni réécrire en Python (gain nul
sur les ~95 % de code qui sont de l'orchestration de CLIs). Voir
[ADR 0017](../decisions/0017-langage-des-scripts.md).

## Encadré honnêteté — compromis assumés

- **Dépendance à un dépôt tiers.** `containerd.io` vient de
  `download.docker.com`, signé par une clé GPG distincte de Debian, à maintenir
  dans le rôle Ansible. Si Docker change sa clé, le rôle casse jusqu'à mise à
  jour. ([ADR 0005](../decisions/0005-cri-containerd-via-depot-docker.md))
- **Hold manuel sur le CRI.** L'`apt-mark hold containerd.io` empêche les bumps
  non testés mais doit être **libéré à la main** pour monter de version.
  ([ADR 0005](../decisions/0005-cri-containerd-via-depot-docker.md))
- **Pas d'auto-update.** Un patch (`1.34.9` → `1.34.10`) ne s'applique que par
  re-exécution du rôle après un bump explicite ; la veille des release notes
  croisées est un travail récurrent (bumps rares : annuels pour K8s,
  semi-annuels pour Cilium/Rook).
  ([ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md))
- **Couverture de tests partielle.** Seules les **fonctions pures** sont
  testables par bats sans cluster ; l'orchestration end-to-end ne se valide que
  sur le banc, et bash montre ses limites au-delà de l'orchestration (d'où la
  soupape python3 et la discipline jq).
  ([ADR 0017](../decisions/0017-langage-des-scripts.md))

## Voir aussi

- [Exposition réseau](../architecture/exposition-reseau.md) — réseau et
  exposition des services.
- [Validation sur banc](../architecture/validation-banc.md) — tests multi-nœuds
  qui valident chaque bump avant la prod.
