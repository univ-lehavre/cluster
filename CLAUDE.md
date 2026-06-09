# Conventions du dépôt (pour l'agent)

## Règle fondatrice — dépôt multi-topologies, valeurs génériques (ADR 0023)

Ce dépôt est un **catalogue de topologies** d'infrastructure (mono-nœud,
multi-nœuds, bare-metal hyperconvergé…) : **plusieurs infra déclarées, une seule
activée** par déploiement (modèle Pulumi/Terraform ; implémentation impérative
Ansible/scripts). Ce **n'est pas** l'infrastructure réelle de l'auteur. **Tout
contenu produit ici (code, manifestes, scripts ET prose : docs, ADR, RUNBOOK)
emploie des valeurs d'exemple génériques, jamais les valeurs réelles d'un
déploiement** (qui vivent dans une config locale non versionnée).

À génériser, dans tout nouveau contenu :

- **IP / plages réseau** prod → valeur d'exemple (réseau privé `10.0.0.0/22`).
- **Noms de nœuds / hôtes / PVC / buckets** → `cp1`, `node1`…`node4`,
  `site-distant`.
- **Noms d'organisation / sites** → « l'organisation », `example-org`.
- **Cas d'usage métier propres à un projet** (sources de données / services
  applicatifs spécifiques, fournisseur matériel d'une instance) → générique («
  source de données ouverte », « backend d'auth », « serveur lame »).

**À GARDER (ne PAS génériser)** : les logiciels/bases qui _portent_ une décision
technique — briques d'infra/plateforme que le dépôt propose : Ceph, Rook, MySQL,
PostgreSQL, containerd, Cilium, cert-manager, Argo CD… Mnémonique : **garder ce
que le dépôt propose comme brique ; génériser ce qui n'a de sens que pour une
instance** (ADR 0023).

Précisions :

- **Prose = valeur-exemple _concrète_ et stable**, pas une tournure vague (un
  `/22` ≠ un `/24` : le contexte chiffré qui fonde une décision est conservé).
- **Spécificités réelles** = config **locale non versionnée** (gitignorée)
  surchargeant un **`*.example` versionné**. Réutiliser les patrons existants :
  `lookup('env','X') | default('<exemple>')`, inventaires gitignorés +
  `.example`, convention `.env` / `.env.example`. Ne **jamais** laisser une
  valeur de prod comme défaut versionné.
- **Exceptions** : le banc Vagrant `192.168.67.0/24` reste tel quel (exemple
  fonctionnel public) ; `test/RESULTS.md` (historique de validation banc) n'est
  **pas** réécrit — honnêteté des Runs.

Détail et justification :
[ADR 0023](docs/decisions/0023-plateforme-exemple-generique.md),
[CONTRIBUTING.md](CONTRIBUTING.md).

## Conventions générales

- **Commits** : Conventional Commits, sujet **en minuscules** (commitlint
  `subject-case`), **sans email / sans `Co-Authored-By`**. Hooks lefthook
  **jamais** bypassés (`--no-verify`, `LEFTHOOK=0` interdits).
- **Merge** : **merge commit** (PAS squash) — l'historique fin de chaque PR est
  préservé dans `main`
  ([ADR 0037](docs/decisions/0037-strategie-merge-commit.md)). Donc **chaque
  commit** d'une PR doit être propre (la CI valide commitlint sur toute la
  plage, pas seulement le titre de PR) : soigner/regrouper ses commits avant le
  merge.
- **Validation** : `pnpm lint` (format, yamllint, shellcheck, kubeconform,
  ansible-lint, jscpd, bats) ; `pnpm docs:build` (VitePress, échoue sur lien
  mort) ; jobs CI séparés non couverts par `pnpm lint` : **markdownlint** et
  **trivy** — les reproduire localement avant de pousser.
- **Banc : corriger le CODE, pas l'état** (ADR
  [0046](docs/decisions/0046-corriger-le-code-pas-l-etat.md)/[0034](docs/decisions/0034-validation-e2e-from-scratch.md)).
  `kubectl patch`/`apply` manuel = **diagnostic uniquement** ; tout correctif
  repart dans le code versionné (manifeste/rôle/harnais) puis est **re-prouvé
  par un run**. Le banc se monte par un **chemin nommé codé**
  (`test/lima/run-phases.sh <chemin>`, ADR 0045), **jamais** en enchaînant des
  phases à la main — si un enchaînement manque, **coder le chemin**. Une valeur
  de profil (storageClass…) se **dérive** de `WITH_CEPH`/`WITH_HARDENING`,
  jamais codée en dur.
- **Décisions structurantes** via **ADR** (format Nygard léger), jamais en
  bullets dans un TODO. Index : `docs/decisions/README.md`.
- **Images** épinglées par **digest d'index multi-arch** (ADR 0006) — vérifier
  `MediaType: …image.index…` avant d'épingler (le banc est arm64).
- **Manifestes vendored** (bundles upstream volumineux) exclus de
  prettier/yamllint/jscpd (cf. `storage/ceph/*`,
  `platform/{cert-manager,argocd}`), RBAC inhérent allowlisté dans
  `.trivyignore.yaml` avec justification par chemin.
