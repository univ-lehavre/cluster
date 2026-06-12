# Passage d'audit du 2026-05-29

> ⚠️ **PHOTO DATÉE, NON RÉACTUALISÉE.** Ce passage reflète l'état du dépôt **au
> 2026-05-29** — **antérieur** à l'installation de production et à ~45 ADR
> ultérieurs. Les notes /5 et constats ci-dessous **ne décrivent pas l'état
> courant** ; nombre de recommandations ont depuis été traitées. Pour la
> doctrine (grille permanente vs passages), voir [`../README.md`](../README.md)
> et [ADR 0058](../../decisions/0058-doctrine-audit-grille-passages.md). On ne
> réécrit pas ce passage (honnêteté de l'historique, comme `RESULTS.md`) : un
> futur passage produira de nouvelles notes.
>
> Méthode : exécution réelle de la chaîne qualité (prettier, yamllint,
> shellcheck, ansible-lint, kubeconform, jscpd, gitleaks) + lecture en
> profondeur du code et de la documentation par une flotte d'agents d'analyse,
> chaque constat majeur étant **vérifié de façon adversariale** (un second
> relecteur tente de réfuter le constat avant qu'il ne soit retenu). Les
> gravités ci-dessous sont les gravités **après** vérification.

## Suivi des manques (réactualisé le 2026-06-12)

Tri sélectif des **39 recommandations** du [plan d'action](12-plan-action.md)
contre l'état réel du dépôt (post-installation prod), conformément à
[ADR 0058](../../decisions/0058-doctrine-audit-grille-passages.md) §4 (manques →
issues) :

| Verdict       | Nombre | Détail                                                       |
| ------------- | ------ | ------------------------------------------------------------ |
| **fait**      | 30     | réalisés depuis le 2026-05-29 (install prod, +45 ADR)        |
| **partiel**   | 6      | outillage en place, reste un résidu → issues ci-dessous      |
| **décision**  | 3      | arbitrage humain (RGPD, Tailscale) — pas un ticket technique |
| encore valide | 0      | —                                                            |

**77 % des recommandations étaient déjà réalisées** : un audit figé périme — sa
valeur ne se récupère qu'en le confrontant au code vivant avant d'agir
(justification empirique
d'[ADR 0058](../../decisions/0058-doctrine-audit-grille-passages.md)).

**Manques résiduels → issues** :

- **#294** — finaliser release/deps (activer Renovate #9, corriger l'en-tête
  CHANGELOG #28).
- **#295** — aligner ADR 0005/code (hold containerd), figer le patch K8s,
  épingler les actions par SHA (#36).
- **#296** — dette de factorisation bash (ssh-report.sh, lib.sh scénarios,
  collision SSH_OPTS #38).
- Glose continue vers le glossaire (#6) : tâche de fond, non bloquante, non
  ticketée.

**Décisions à arbitrer (humain, pas une issue technique)** :

- **RGPD** des datasets `twitter`/`reddit` (#4) — qualification référent/DPO en
  attente (et noms à génériser,
  [ADR 0023](../../decisions/0023-plateforme-exemple-generique.md)).
- **Tailscale operator** (#20) — reporté ; contrôle réseau déjà documenté
  (SAFEGUARDS + ADR 0003).

> Le contenu ci-dessous est le **passage original du 2026-05-29**, non réécrit.

## Comment lire cet audit

| Fichier                                          | Contenu                                                     |
| ------------------------------------------------ | ----------------------------------------------------------- |
| [00-synthese.md](00-synthese.md) _(ce fichier)_  | Synthèse exécutive, tableau de bord, plan d'action priorisé |
| [01-bonnes-pratiques.md](01-bonnes-pratiques.md) | Structure du dépôt, conventions IaC, hygiène                |
| [02-tests.md](02-tests.md)                       | Banc d'essai, scénarios, couverture, idempotence            |
| [03-lint-format.md](03-lint-format.md)           | Chaîne lint/format, parité CI ↔ hooks, scanners manquants   |
| [04-documentation.md](04-documentation.md)       | Pédagogie néophyte, doc dans le code, site VitePress        |
| [05-reproductibilite.md](05-reproductibilite.md) | Pinning des versions, déterminisme, supply chain            |
| [06-securite.md](06-securite.md)                 | Durcissement, réseau, plan de contrôle, secrets             |
| [07-gouvernance.md](07-gouvernance.md)           | Licence, gouvernance OSS, citation, versionnement           |
| [08-operabilite.md](08-operabilite.md)           | Observabilité, sauvegarde/DR, résilience, upgrades, RGPD    |
| [09-langage-scripts.md](09-langage-scripts.md)   | Remise en cause du choix de bash                            |
| [10-dispersion-cli.md](10-dispersion-cli.md)     | Scripts dispersés vs point d'entrée unique                  |
| [11-logiciels-oss.md](11-logiciels-oss.md)       | Pertinence et gestion du risque des composants open source  |
| [12-plan-action.md](12-plan-action.md)           | Toutes les recommandations classées par priorité            |

## Verdict global

**Ce dépôt est nettement au-dessus de la moyenne de l'IaC, et même de beaucoup
de dépôts professionnels.** La chaîne qualité automatisée est réelle et
fonctionne (tous les linters passent, 0 % de duplication, 0 secret sur 119
commits), les décisions d'architecture sont tracées dans 12 ADR de très bonne
facture, et le travail de pinning, de durcissement OS et de scripting défensif
est sérieux.

Les axes d'amélioration ne portent donc presque jamais sur des _défauts de base_
mais sur de la **profondeur** :

1. **La documentation n'est pas accessible à un public néophyte** (le critère
   que vous avez explicitement demandé) : aucun glossaire, jargon employé avant
   définition. C'est le point le plus éloigné de l'objectif annoncé.
2. **Les garanties de résilience ne sont pas vérifiées** : la restauration etcd
   n'est jamais testée, il n'y a aucune sauvegarde des données applicatives, et
   aucune observabilité runtime.
3. **La sécurité repose sur une hypothèse réseau non matérialisée** : les
   compromis assumés (HTTP sans auth, etc.) supposent un réseau isolé qui n'est
   garanti par aucun contrôle versionné.
4. **La gestion du risque OSS est manuelle** : pas de scan CVE, pas de bot de
   mise à jour, pas de digest d'image.

Sur vos trois questions ajoutées : **garder bash** (le bon outil ici, mais
ajouter des tests `bats` et passer le parsing en `jq`), **ne pas faire un CLI
unique** mais ajouter un `Justfile` léger + un parcours dans le README, et
**garder le portefeuille OSS** (excellent) mais en outiller la gestion du
risque.

## Tableau de bord par dimension

| #   | Dimension                              | Note      | Constats majeurs restants après vérification                                   |
| --- | -------------------------------------- | --------- | ------------------------------------------------------------------------------ |
| 1   | Bonnes pratiques IaC & structure       | 4,2 / 5   | _aucun_ (que des mineurs/suggestions)                                          |
| 2   | Tests multi-niveaux                    | 3,5 / 5   | Restauration etcd jamais testée ; scénarios 04/05 faux-positifs                |
| 3   | Lint, format & chaîne qualité          | 3,5 / 5   | Aucun scanner de posture sécurité IaC                                          |
| 4   | Documentation néophyte                 | **2 / 5** | **Aucun glossaire** ; jargon avant définition ; pas de parcours débutant       |
| 5   | Documentation dans le code             | 4,3 / 5   | _aucun_ (ADR 0005 désynchronisée — mineur)                                     |
| 6   | Documentation VitePress (site)         | 3,5 / 5   | `ignoreDeadLinks: true` masque les liens cassés                                |
| 7   | Reproductibilité & pinning             | 3,8 / 5   | Toolbox Ceph `:v19` mutable et désaccordée du cluster                          |
| 8   | Sécurité                               | 3,2 / 5   | Restauration etcd non testée ; tension RGPD ; pas d'enforcement réseau         |
| 9   | Gouvernance & licence                  | 3 / 5     | Licence Unlicense vs MIT ; `SECURITY.md` / `CITATION.cff` absents              |
| 10  | Opérabilité, observabilité, résilience | 3 / 5     | **Pas d'observabilité** ; **pas de backup PV** ; **RGPD** ; upgrade K8s absent |
| 11  | _Langage des scripts (bash)_           | —         | Aucun test `bats` sur 890 LOC critiques                                        |
| 12  | _Dispersion vs CLI unique_             | —         | README n'oriente pas vers le RUNBOOK ; pas d'orchestrateur nommé               |
| 13  | _Logiciels open source_                | —         | Pas de scan CVE ; pas de bot de bump ; 0 digest `@sha256`                      |

## Les constats majeurs confirmés (synthèse transversale)

Après vérification adversariale, **9 constats restent en gravité « majeur »**.
Ils se regroupent en quatre familles :

### A. Pédagogie (le critère que vous avez mis en avant)

- **Aucun glossaire dans tout le dépôt** ; les termes structurants (Kubernetes,
  etcd, CNI, CRI, OSD, MON, PVC, RWX, erasure coding, drift, hyperconvergence,
  Tailscale…) sont employés **avant** toute définition. →
  [04](04-documentation.md)

### B. Résilience non prouvée

- **La restauration etcd n'a jamais été testée** (le scénario 04 ne fait que
  redémarrer la VM, etcd revenant intact). Un backup non restauré n'est pas un
  backup. → [02](02-tests.md), [08](08-operabilite.md)
- **Aucune sauvegarde des données applicatives** (PV, buckets S3). La
  réplication Ceph protège du crash disque, pas d'une suppression ou d'une
  corruption ; `reclaimPolicy: Delete` rend un `kubectl delete pvc`
  irréversible. → [08](08-operabilite.md)
- **Aucune observabilité runtime** (pas de metrics-server, Prometheus, alertes ;
  `monitoring.enabled: false`). La détection de panne repose sur l'exécution
  manuelle de `state.sh`. → [08](08-operabilite.md)

### C. Sécurité — hypothèses et données

- **La compensation centrale (réseau isolé + Tailscale) n'est enforce par aucun
  contrôle versionné** : pas de NetworkPolicy, pare-feu opt-in jamais appliqué,
  Tailscale déclaré « optionnel ». → [06](06-securite.md)
- **Tension RGPD** : des buckets `twitter` et `reddit` (données personnelles par
  nature) contredisent l'hypothèse « pas de données personnelles » sur laquelle
  reposent les ADR de moindre sécurité. → [08](08-operabilite.md)

### D. Supply chain / gestion du risque OSS

- **Aucun scan de CVE** (trivy/grype absents) sur un cluster qui agrège
  Kubernetes, Ceph, Rook et des images applicatives. → [03](03-lint-format.md),
  [11](11-logiciels-oss.md)
- **Aucune automatisation de veille/bump** (dependabot/renovate absents) alors
  que la politique de l'ADR 0006 est entièrement manuelle. →
  [11](11-logiciels-oss.md)
- **Toolbox Ceph `:v19` mutable et désaccordée** du cluster `v20.2.1` (double
  anomalie : non reproductible + skew de version majeure). →
  [05](05-reproductibilite.md), [11](11-logiciels-oss.md)
- **Aucun test comportemental** (`bats`) sur les 890 LOC critiques de `state.sh`
  - `run-phases.sh`. → [09](09-langage-scripts.md)

## Ce qui est déjà remarquable (à ne pas casser)

- Chaîne qualité réelle et appliquée : **prettier, shellcheck, yamllint,
  ansible-lint (profil `production`), kubeconform, jscpd (0 %)** passent tous ;
  **gitleaks** ne trouve aucun secret sur 119 commits.
- **12 ADR au format Nygard** homogènes, datés, indexés et liés — la dette de
  sécurité est consciente et tracée, pas subie.
- **Durcissement SSH/OS exemplaire** (clé uniquement, root off, `AllowUsers`,
  fail2ban, auditd, rollback `sshd` idempotent avec `block/rescue`).
- **Scripting défensif** : `set -euo pipefail` partout, `shellcheck` à 0
  warning, désactivations de règles explicitement commentées, helpers
  factorisés.
- **Sauvegarde etcd soignée** (snapshot atomique via `crictl`, vérification
  d'intégrité, rétention, permissions strictes).
- **Banc d'essai à gates durs** (`run-phases.sh`) et **`RESULTS.md` d'une
  honnêteté rare** (trace les drifts et avoue les phases non testées).
- **Pinning sérieux** (aucun `:latest`, matrice de versions ADR 0006, lockfile
  `pnpm` + `--frozen-lockfile`).

## D'autres aspects à couvrir ? (réponse à votre question)

Oui — au-delà de votre liste initiale, l'audit a couvert et identifié comme
pertinents pour ce dépôt : **observabilité runtime**, **sauvegarde/restauration
des données et DR** (au-delà d'etcd), **résilience/HA** (SPOF control-plane et
NVMe, mono-réplicas applicatifs), **stratégie d'upgrade Kubernetes**,
**dimensionnement/capacité**, **conformité RGPD des données de recherche**,
**supply chain** (digests, signatures, SBOM, scan CVE), et **transmissibilité /
bus-factor** (mainteneur quasi unique → formaliser les choix en ADR). Détails en
[08-operabilite.md](08-operabilite.md).

Réflexion ouverte (non décidée) sur l'**admission** et la **détection runtime**
— Kyverno (CI / admission) vs Trivy (déjà en place), Falco vs Tetragon : voir
[note-runtime-admission.md](note-runtime-admission.md).

---

_Le détail dimension par dimension suit dans les fichiers numérotés. Chaque
constat est présenté avec sa gravité vérifiée, le fichier concerné, le constat
factuel et la recommandation._
