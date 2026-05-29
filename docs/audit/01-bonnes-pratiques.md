# 1 — Bonnes pratiques IaC & structure du dépôt

**Note : 4,2 / 5**

Organisation IaC mature : séparation claire des préoccupations (`bootstrap/`
Ansible, `storage/ceph/`, `platform/`, `apps/`, `test/`, `docs/`), rôles
structurés `tasks/handlers/templates`, modules FQCN systématiques, garde-fous
d'idempotence (`changed_when: false`, `failed_when`, `creates`, assertions de
pré-requis), handlers câblés via `notify`, tags opt-in côté sécurité. Gestion
des dépendances rigoureuse (lockfile `pnpm` versionné, `requirements.yml`
épinglé). Aucun artefact généré n'est versionné (`dist/`, `node_modules/`,
`.vagrant/`, `inventory.yaml` correctement ignorés — vérifié via
`git ls-files`). Les points d'amélioration sont cosmétiques ou liés au
sous-arbre `git subtree` `bootstrap/security/`.

## Points forts

- Arborescence cohérente par préoccupation, fidèle à la table du `README`.
- Rôles Ansible idiomatiques : FQCN, assertions de pré-requis, idempotence
  (`changed_when: false`, `creates`, `replace` idempotent pour `fstab`).
- Handlers isolés et câblés via `notify`.
- Séparation config/secrets : aucun secret en clair, injection par variables
  d'environnement, fichier d'exemple fourni ; gitleaks confirme 0 secret.
- Dépendances épinglées : `pnpm-lock.yaml` versionné, collections Ansible figées
  (`ansible.posix 2.2.0`, `community.general 12.6.1`).
- `.ansible-lint` documente ses dérogations ; profil `production` validé.
- Pipeline qualité cohérent (lefthook pre-commit/pre-push/commit-msg aligné CI).
- Sous-arbre sécurité importé proprement via `git subtree`, documenté.

## Constats

### Mineur — Répertoire vide orphelin `bootstrap/bootstrap/`

- **Fichier** : `bootstrap/bootstrap/roles/{audit-log,k8s-rollback}/tasks/`
- **Constat** : arborescence vide locale, non suivie par git, référencée par
  aucune config — cruft probablement issu d'une commande lancée du mauvais
  répertoire.
- **Recommandation** : `rm -rf bootstrap/bootstrap`.

### Mineur — Décalage de nommage `.env-example` ↔ `.gitignore` ↔ doc

- **Fichier** : `.gitignore:19`, `bootstrap/security/.env-example`,
  `bootstrap/security/README.md:128`
- **Constat** : le fichier réel est `.env-example` (tiret) ; `.gitignore`
  whiteliste `!.env.example` (point) — allowlist inopérante ; `README.md:128`
  demande de renommer `.env.example` alors que le fichier livré est
  `.env-example`. Incohérence triple.
- **Recommandation** : harmoniser sur `.env.example` (point), corriger le
  README.

### Mineur — `.ansible-lint` `kinds` ne couvre pas `bootstrap/security/`

- **Fichier** : `.ansible-lint:29-33`
- **Constat** : les patterns ciblent `.yaml` alors que tout le sous-arbre
  sécurité est en `.yml` ; `secure.yml`/`upgrade.yml` reposent sur
  l'auto-détection (46/63 fichiers couverts, 17 à confirmer).
- **Recommandation** : étendre `kinds` au sous-arbre
  (`bootstrap/security/*.yml`, `bootstrap/security/roles/*/tasks/*.yml`,
  `…/handlers/*.yml`).

### Suggestion — Double convention `.yaml`/anglais vs `.yml`/français

- **Fichier** : `bootstrap/roles/` vs `bootstrap/security/roles/`
- **Constat** : divergence assumée (subtree) mais qui oblige tout l'outillage à
  gérer deux extensions.
- **Recommandation** : documenter la convention dans `CONTRIBUTING.md` ou un ADR
  ; normaliser à terme lors d'une synchro du subtree.

### Suggestion — Table de structure du `README` incomplète

- **Fichier** : `README.md:16-21`
- **Constat** : `test/` et `docs/` (deux répertoires de premier niveau
  significatifs) sont absents de la table « Structure ».
- **Recommandation** : ajouter les deux lignes manquantes.

### Suggestion — Rôles sans `defaults/` ni `meta/`

- **Fichier** : `bootstrap/roles/*`
- **Constat** : aucun `defaults/main.yaml` ni `meta/main.yml` ; l'interface des
  rôles et leurs métadonnées (plateformes, version Ansible min.) ne sont pas
  déclarées.
- **Recommandation** : `defaults/main.yaml` documentant l'interface pour les
  rôles paramétrables ; `meta/main.yml` optionnel (non bloquant, profil
  `production` déjà vert).
