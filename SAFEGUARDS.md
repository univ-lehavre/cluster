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

| Hook                     | Sur quoi                                                          |
| ------------------------ | ----------------------------------------------------------------- |
| `no-direct-push-to-main` | refuse `git push` direct sur `main` — passage par PR obligatoire  |
| `prettier --check`       | tous les `*.{yaml,yml,md,json}`                                   |
| `yamllint .`             | tout le dépôt                                                     |
| `shellcheck`             | tous les `*.sh`                                                   |
| `bats`                   | tests unitaires des fonctions pures de `state.sh` (`bench/unit/`) |
| `kubeconform`            | tous les manifestes K8s (hors CRDs Rook + values.yaml Helm)       |
| `ansible-lint`           | tous les rôles et playbooks (`production` profile)                |

> Aucun hook ne peut être contourné par `--no-verify` en pratique : la CI
> rejouera la même chose sur GitHub.

## CI GitHub Actions (chaque PR + chaque push `main`)

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) — **jobs en parallèle** :

| Job            | Vérifie                                           |
| -------------- | ------------------------------------------------- |
| `prettier`     | format complet du dépôt                           |
| `yamllint`     | tous les YAML                                     |
| `shellcheck`   | tous les scripts shell                            |
| `bats`         | fonctions pures de `state.sh` (`pnpm test:shell`) |
| `kubeconform`  | manifestes K8s                                    |
| `ansible-lint` | rôles/playbooks (production profile)              |
| `jscpd`        | détection de code dupliqué (seuil 5 %)            |
| `trivy`        | posture sécurité IaC (HIGH/CRITICAL)              |
| `commitlint`   | commits de la PR (Conventional Commits)           |

### Branch protection sur `main` (réglage GitHub — audit P7 #29)

Configurée côté GitHub (non versionnable, documentée ici pour mémoire) :

- **Pull request obligatoire** (pas de push direct — doublé par le hook
  `no-direct-push-to-main`).
- **13 checks requis** avant merge : `prettier`, `yamllint`, `shellcheck`,
  `kubeconform`, `ansible-lint`, `commitlint`, `trivy`, `bats`, `jscpd`,
  `markdownlint`, `lychee`, `ansible-syntax`, `scripts-extra`. **Tout job CI
  doit être ajouté à cette liste** : un job non requis se contourne par
  l'auto-merge et peut casser `main` (vécu deux fois — `trivy`, puis `lychee`).
  Règle : nouveau job → l'ajouter aux required checks une fois vu vert.
  - ⚠️ **Écart à combler** : les jobs `python` (ruff + tests unittest) et
    `gitleaks` (secret scanning) tournent en CI mais **ne sont pas encore dans
    les required checks** — à ajouter une fois éprouvés (gitleaks est non
    bloquant de propos délibéré ; `python` devrait l'être). C'est précisément la
    règle ci-dessus, non encore appliquée à ces deux jobs récents.
- **`strict: true`** : la branche doit être **à jour avec `main`** (checks
  rejoués sur le dernier état) avant merge.
- **Résolution des conversations requise**.
- **0 review requise** : choix assumé pour un repo **mono-mainteneur** — exiger
  une approbation bloquerait l'auto-merge des PR de release (cf. release-please
  ci-dessous : aucun second relecteur disponible).

> Vérifier / réappliquer :
> `gh api repos/univ-lehavre/cluster/branches/main/protection`.

[`.github/workflows/docs.yml`](.github/workflows/docs.yml) :

- À chaque PR : `pnpm docs:build` (validation — pas de dead link, base path
  correct).
- À chaque push sur `main` : build + déploiement sur
  [GitHub Pages](https://univ-lehavre.github.io/cluster/).

[`.github/workflows/release.yml`](.github/workflows/release.yml) :

- À chaque push sur `main` :
  [release-please](https://github.com/googleapis/release-please) ouvre (ou met à
  jour) une PR de release qui bumpe `package.json` et `CHANGELOG.md` d'après les
  Conventional Commits. **L'auto-merge est activé sur cette PR dès sa création**
  : GitHub la fusionne automatiquement quand les checks requis sont verts, ce
  qui pousse le tag `vX.Y.Z` et publie une
  [GitHub Release](https://github.com/univ-lehavre/cluster/releases). →
  Publication **100 % automatique** ; aucune version flottante en main, chaque
  tag lié à un set de commits validé par la CI.

> ✅ **Token : PAT fine-grained (`RELEASE_PLEASE_TOKEN`).** L'organisation
> `univ-lehavre` verrouille le `GITHUB_TOKEN` par défaut en lecture seule
> (`default_workflow_permissions` ne peut pas passer à `write` au niveau repo →
> `409 Write permissions for workflows are disabled by the organization`). Avec
> ce token bridé, release-please ouvrait la PR mais ne pouvait ni pousser le tag
> ni publier la release. On utilise donc un **PAT fine-grained** (scope = ce
> repo, `Contents: RW` + `Pull requests: RW`) déposé en secret
> `RELEASE_PLEASE_TOKEN` et injecté via `with: token:` dans `release.yml`. Il
> débloque tag + release **et** redéclenche la CI sur la PR de release — sans
> quoi l'auto-merge resterait en attente de checks qui ne tournent jamais.
> Réglage repo associé : `allow_auto_merge=true`.
>
> ⚠️ **Rotation** : un PAT expire. À renouveler avant échéance (même scope, même
> nom de secret), sinon les releases se rebloquent silencieusement.
>
> 🛟 **Filet de sécurité — symptôme d'un token absent/expiré** : la PR de
> release n'aboutit plus, et faute de tag publié release-please **re-propose une
> version toujours plus haute à chaque push** (boucle observée le 2026-05-29 :
> `2.0.0` jamais taguée → `3.0.0` reproposée). **Rattrapage manuel** (le contenu
> de `main` est déjà bon : `package.json`, `.release-please-manifest.json` et
> `CHANGELOG.md` portent la bonne version) :
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

## Banc d'essai Lima

[`bench/`](bench/) — valider sur **vrai Debian 13** avant de toucher les
serveurs.

### [`bench/lima/`](bench/lima/) — banc multi-nœuds (ADR 0038, seul banc local)

3 VMs Lima Debian 13 arm64 (réseau user-v2 `192.168.104.0/24`) + disques bruts
pour Ceph. Orchestré par [`bench/lima/run-phases.sh`](bench/lima/run-phases.sh)
à **gates** : `up → bootstrap → ceph → sc → datalake → dataops → monitoring`.
Deux profils — léger (local-path/SeaweedFS, ~11 min) et Ceph (RGW, ~30 min).
Couvre la chaîne complète Phase 1-5 + DataOps.

**Toujours valider sur le banc avant la prod** — c'est le seul endroit où le
multi-VM et les disques Ceph sont exercés (validation = run e2e from-scratch,
[ADR 0034](docs/decisions/0034-validation-e2e-from-scratch.md)).

#### Isolation banc ↔ prod

Le banc Lima est volontairement **isolé** (`mounts: []`, réseau user-v2 dédié
`192.168.104.0/24`, disjoint de la plage de production `10.0.0.0/22`). Il n'a
pas d'interface host-only susceptible de capturer les routes vers les vrais
serveurs.

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

Les ADR (Architecture Decision Records) au format _Contexte / Décision / Statut
/ Conséquences_. Couvrent les choix architecturaux (réplication ×3, control
plane unique, hyperconvergence, EC 2+1 datalake) et les compromis sécurité (HTTP
sans auth, dashboard cluster-admin, RStudio sans login). Voir
[index ADR](docs/decisions/README.md).

## Phasage gated banc → prod

L'ordre de déploiement (canari `cp1` → workers → stockage cluster-wide) et les
gates par étape sont décrits dans
[`bootstrap/RUNBOOK.md` § Ordre de déploiement](bootstrap/RUNBOOK.md) ; **tout
changement de cette nature doit passer par le banc ([`bench/`](bench/)) avant la
prod**. Le _pourquoi_ de chaque choix structurant est tracé dans les
[ADR](docs/decisions/). Le reste-à-faire priorisé vit dans
[`docs/audit/2026-05-29/12-plan-action.md`](docs/audit/2026-05-29/12-plan-action.md).
