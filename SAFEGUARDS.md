# Garde-fous

Inventaire des mécanismes en place pour éviter les régressions et les mauvaises
surprises — du commit au déploiement.

## Hooks git (poste de développement)

Posés par [Lefthook](https://lefthook.dev/) au premier `pnpm install` (config :
[`lefthook.yml`](lefthook.yml)).

### `pre-commit` — vérifie ce qui est sur le point d'être commité

| Hook               | Sur quoi                      | Rejet si            |
| ------------------ | ----------------------------- | ------------------- |
| `prettier --check` | `*.{yaml,yml,md,json}` staged | format non conforme |
| `yamllint`         | `*.{yaml,yml}` staged         | warnings YAML       |
| `shellcheck`       | `*.sh` staged                 | warnings shellcheck |

### `commit-msg` — vérifie le message de commit

| Hook         | Rejet si                                                                                                                            |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `no-emails`  | message contient une adresse email                                                                                                  |
| `commitlint` | non conforme à [Conventional Commits](https://www.conventionalcommits.org/) (sujet en minuscule, type valide, corps ≤ 100 colonnes) |

### `pre-push` — vérifie tout le dépôt avant d'envoyer

| Hook                     | Sur quoi                                                         |
| ------------------------ | ---------------------------------------------------------------- |
| `no-direct-push-to-main` | refuse `git push` direct sur `main` — passage par PR obligatoire |
| `prettier --check`       | tous les `*.{yaml,yml,md,json}`                                  |
| `yamllint .`             | tout le dépôt                                                    |
| `shellcheck`             | tous les `*.sh`                                                  |
| `kubeconform`            | tous les manifestes K8s (hors CRDs Rook + values.yaml Helm)      |
| `ansible-lint`           | tous les rôles et playbooks (`production` profile)               |

> Aucun hook ne peut être contourné par `--no-verify` en pratique : la CI
> rejouera la même chose sur GitHub.

## CI GitHub Actions (chaque PR + chaque push `main`)

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) — **8 jobs en parallèle**
:

| Job            | Vérifie                                 |
| -------------- | --------------------------------------- |
| `prettier`     | format complet du dépôt                 |
| `yamllint`     | tous les YAML                           |
| `shellcheck`   | tous les scripts shell                  |
| `kubeconform`  | manifestes K8s                          |
| `ansible-lint` | rôles/playbooks (production profile)    |
| `jscpd`        | détection de code dupliqué (seuil 5 %)  |
| `commitlint`   | commits de la PR (Conventional Commits) |

[`.github/workflows/docs.yml`](.github/workflows/docs.yml) :

- À chaque PR : `pnpm docs:build` (validation — pas de dead link, base path
  correct).
- À chaque push sur `main` : build + déploiement sur
  [GitHub Pages](https://univ-lehavre.github.io/cluster/).

[`.github/workflows/release.yml`](.github/workflows/release.yml) :

- À chaque push sur `main` :
  [release-please](https://github.com/googleapis/release-please) ouvre (ou met à
  jour) une PR de release qui bumpe `package.json` et `CHANGELOG.md` d'après les
  Conventional Commits. Le merge de cette PR pousse le tag `vX.Y.Z` et publie
  une [GitHub Release](https://github.com/univ-lehavre/cluster/releases). →
  Aucune version flottante en main, et chaque tag est lié à un set de commits
  explicitement validé par un opérateur.

> ⚠️ **Pré-requis organisation (sinon release-please ne publie rien).**
> release-please crée la PR de release, puis le tag + la GitHub Release, avec le
> `GITHUB_TOKEN`. Cela exige que le réglage **Settings → Actions → General →
> Workflow permissions → « Allow GitHub Actions to create and approve pull
> requests »** soit activé. Sur `univ-lehavre`, ce réglage est verrouillé **au
> niveau organisation** : il doit être activé par un admin org (l'API repo
> renvoie sinon
> `409 Write permissions for workflows are disabled by the organization`). Tant
> qu'il est désactivé :
>
> - la PR de release n'est jamais créée (le job `release-please` échoue avec
>   `GitHub Actions is not permitted to create or approve pull requests`) ;
> - faute de tag publié, release-please considère la version précédente comme
>   non publiée et **re-propose une version toujours plus haute à chaque push**
>   (boucle observée le 2026-05-29 : `2.0.0` jamais taguée → `3.0.0`
>   reproposée).
>
> **Rattrapage manuel** d'une release bloquée (le contenu de `main` est déjà bon
> : `package.json`, `.release-please-manifest.json` et `CHANGELOG.md` portent la
> bonne version) :
>
> ```bash
> # 1. Publier le tag + la release sur le HEAD de main
> gh release create vX.Y.Z --target "$(git rev-parse origin/main)" --title vX.Y.Z \
>   --notes-file <(git show origin/main:CHANGELOG.md \
>     | awk '/^## \[X\.Y\.Z\]/{f=1} /^## \[<version-précédente>\]/{f=0} f')
> # 2. Supprimer la branche release-please parasite (via API : le hook pre-push
> #    no-direct-push-to-main bloque un `git push --delete`)
> gh api -X DELETE repos/univ-lehavre/cluster/git/refs/heads/release-please--branches--main--components--cluster
> # 3. Vérifier qu'un run propre ne repropose plus rien
> gh workflow run release.yml && gh run list --workflow release.yml -L 1
> ```
>
> **Alternative durable** si l'org refuse le réglage : passer un PAT
> fine-grained (`Contents: RW` + `Pull requests: RW`, scope = ce repo) en secret
> `RELEASE_PLEASE_TOKEN` et l'injecter via `with: token:` dans `release.yml`
> (penser à la rotation — un PAT expire).

## Bancs d'essai Vagrant

[`test/`](test/) — deux topologies pour valider sur **vrai Debian 13** avant de
toucher les serveurs.

### [`test/single-node/`](test/single-node/) — itération rapide (5 min)

1 VM mono-nœud. Couvre **Phase 1-2** :
`checks → cri → kubeadm → initialisation → cni.sh`. Pas de Ceph (mono-nœud).

### [`test/multi-node/`](test/multi-node/) — validation complète (15 min)

3 VMs Debian 13 arm64 + réseau privé `192.168.67.0/24` + 3 disques HDD virtuels

- 1 disque "NVMe" par VM. Couvre **Phase 1-5** : bootstrap, join-workers,
  Rook-Ceph, StorageClasses, workloads applicatifs.

**Toujours valider sur multi-node avant la prod** — c'est le seul endroit où le
multi-VM et les disques Ceph sont exercés.

#### Règle d'isolation banc ↔ prod

> **La plage IP du banc DOIT être disjointe de toute plage de production
> accessible depuis le poste de contrôle.**

Si le banc et la prod partagent une plage IP (cas vécu : `10.67.2.0/24` des deux
côtés), VirtualBox crée une interface host-only sur cette plage et **capture
toutes les routes locales** vers les vrais serveurs → on perd l'accès SSH à la
prod tant que le banc tourne. Cf.
[drift #6 dans test/RESULTS.md](test/RESULTS.md).

Garde-fous en place :

- **Plage banc** : `192.168.67.0/24` (disjointe de prod `10.67.2.0/22`).
- **Pre-flight Vagrantfile**
  ([test/multi-node/Vagrantfile](test/multi-node/Vagrantfile)) : refuse
  `vagrant up` si VBox a déjà une interface host-only sur la plage prod (signe
  d'un ancien banc non nettoyé).
- À vérifier manuellement avant un cycle : `netstat -rn | grep 10.67.2` +
  `VBoxManage list hostonlyifs | grep IPAddress`.

## Vérifications en place sur les nœuds

### Détection de drift — [`bootstrap/state.sh`](bootstrap/state.sh)

7 couches d'observation (SSH + kubectl) :

| Couche                   | Vérifie                                                                                   |
| ------------------------ | ----------------------------------------------------------------------------------------- |
| 0 — Registre Ansible     | `/var/log/cluster-bootstrap.log` : dernier playbook joué par nœud, drift si absent        |
| 1 — Premier accès        | Debian 13, sudo NOPASSWD, sshd drop-in, PasswordAuthentication=no, mot de passe ≠ install |
| 2 — Hardening OS         | unattended-upgrades, postfix, auditd, fail2ban (opt-in via tags)                          |
| 3 — Bootstrap K8s        | containerd + SystemdCgroup, kubeadm, cluster-api, admin.conf                              |
| 3b — Disques Ceph        | N HDD bruts (wipefs), nvme1n1 présent et brut, `/var/lib/rook` propre                     |
| 4 — CNI Cilium           | cilium-operator, DaemonSet, nodes Ready, pod CIDR                                         |
| 5 — Rook-Ceph            | operator, CephCluster HEALTH_OK, OSDs Running                                             |
| 6 — StorageClasses + PVC | default SC, PVC Bound, pas de résiduel `rook-ceph-block-ec`                               |
| 7 — Plateforme           | registry, dashboard (absence du Secret legacy admin-user)                                 |

Sortie : `N ok / N drift / N non applicable` + remède pour le **1er** drift
détecté.

### Visibilité du durcissement — [`bootstrap/security/report.sh`](bootstrap/security/report.sh)

Tableau de bord lecture-seule par hôte : services actifs, `sshd -T`, dernier
`unattended-upgrades.log`, alias root, IPs bannies par fail2ban, règles auditd,
état UFW, expiration mot de passe. Le hardening est **100 % opt-in**
([`bootstrap/security/IMPLICATIONS.md`](bootstrap/security/IMPLICATIONS.md)) —
chaque couche s'active explicitement.

### Audit-log par nœud — rôle [`audit-log`](bootstrap/roles/audit-log/)

Chaque playbook bootstrap appose une ligne dans `/var/log/cluster-bootstrap.log`
du nœud cible : timestamp UTC, nom du playbook, opérateur `$USER@hostname` côté
contrôle. Lu par la couche 0 de `state.sh` pour corréler "ce qui a été appliqué"
et "ce qui est observé".

### Sauvegarde etcd — rôle [`etcd-backup`](bootstrap/roles/etcd-backup/)

Timer systemd horaire qui exécute `etcdctl snapshot save` ; rétention 24
snapshots (1 jour glissant). Procédure de restauration documentée dans
[`bootstrap/RUNBOOK.md`](bootstrap/RUNBOOK.md).

### Rollback du bootstrap — [`bootstrap/rollback.yaml`](bootstrap/rollback.yaml)

Playbook qui ramène un nœud à un état "Debian 13 + first-access" via
`kubeadm reset + apt purge + cleanup configs`. Confirmation obligatoire via
`-e confirm=yes`. Hors périmètre : disques Ceph (cf.
[`storage/ceph/cleanup.sh`](storage/ceph/cleanup.sh)), partitionnement.

### Idempotence stricte — [`bootstrap/first-access.sh`](bootstrap/first-access.sh)

Dépose la clé SSH, configure `sudo NOPASSWD`, pose le drop-in sshd hardening.
Strictement idempotent : un 2ᵉ run ne change rien si l'état est déjà conforme
(compare avec `cat` avant `install`).

## Décisions tracées — [`docs/decisions/`](docs/decisions/)

12 ADR (Architecture Decision Records) au format _Contexte / Décision / Statut /
Conséquences_. Couvrent les choix architecturaux (réplication ×3, control plane
unique, hyperconvergence, EC 2+1 datalake) et les compromis sécurité (HTTP sans
auth, dashboard cluster-admin, RStudio sans login). Voir
[index ADR](docs/decisions/README.md).

## Phasage gated banc → prod

L'ordre de déploiement (canari `dirqual1` → workers → stockage cluster-wide) et
les gates par étape sont décrits dans
[`bootstrap/RUNBOOK.md` § Ordre de déploiement](bootstrap/RUNBOOK.md) ; **tout
changement de cette nature doit passer par le banc ([`test/`](test/)) avant la
prod**. Le _pourquoi_ de chaque choix structurant est tracé dans les
[ADR](docs/decisions/). Le reste-à-faire priorisé vit dans
[`docs/audit/12-plan-action.md`](docs/audit/12-plan-action.md).
