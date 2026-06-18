# 2026-06-16 — Audit « notations de cybersécurité externes applicables au dépôt »

| Champ        | Contenu                                                                                                                                                                                                                                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**     | 2026-06-16                                                                                                                                                                                                                                                           |
| **Type**     | revue ciblée — quels **référentiels de notation cybersécurité** s'appliquent à un dépôt d'IaC Kubernetes de recherche, et où le dépôt se situe sur chacun (preuves = fichier:ligne, sorties `gh`/`git`, ou absences par grep nul)                                    |
| **Fonde**    | _réflexion_ — alimente une issue parapluie (manques actionnables) et de futurs ADR/plans. **Aucune décision ici.**                                                                                                                                                   |
| **Prolonge** | le passage de maturité du 2026-06-15 (issue #349 — DORA/MLOps/CNCF/SLSA+SAMM) — qu'il **ne réécrit pas** : ce passage prend l'angle complémentaire des **notations cyber chiffrées** (Scorecard /10, CIS PASS/FAIL, mapping NIST/ANSSI).                             |
| **Verdict**  | 3 référentiels directement applicables et **partiellement déjà couverts** : OpenSSF Scorecard (≈ moitié des checks verts sans effort), CIS Benchmarks (Trivy `config` posé, mode `compliance`/kube-bench absents), NIST CSF/ANSSI (mapping documentaire à produire). |

## Pourquoi ce passage

La question « existe-t-il des notations de cybersécurité qui concernent ce dépôt
? » se heurte au **biais adoptif borné**
([ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md)) : une
notation n'a de valeur que si elle **mesure quelque chose de vrai** sur un
**dépôt d'IaC mono-tenant de recherche sur réseau isolé**, et non si elle empile
un badge pour le badge. Trois traits du dépôt conditionnent toute lecture
(rappelés une fois, repris du passage #349) :

1. **Pas de production permanente télémétrée** — catalogue de topologies
   bench-validé, pas un cluster opéré
   ([ADR 0023](../decisions/0023-plateforme-exemple-generique.md)). Les
   notations qui supposent un service rendu (runtime CIS node-level) n'ont de
   sens **que sur le banc**, pas en CI statique.
2. **Compromis de sécurité assumés et tracés en ADR** (registry HTTP sans auth
   [ADR 0011](../decisions/0011-registry-http-sans-auth.md), RStudio sans auth
   [ADR 0012](../decisions/0012-rstudio-disable-auth.md), pas de chiffrement
   Ceph [ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md)) :
   une notation **automatique les comptera comme des défauts**. La parade est la
   **grille d'exceptions par ADR** déjà pratiquée pour Trivy
   (`.trivyignore.yaml`, justifiée par chemin) — cf.
   [ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md).
3. **Mono-mainteneur assumé** (`CODEOWNERS = * @chasset`) : les checks de
   notation qui exigent une revue par les pairs (Scorecard `Code-Review`)
   resteront structurellement bas — choix tenu, pas un manque (SAFEGUARDS.md).

Ce passage **ne crédite aucun palier au feeling** : chaque ligne cite une preuve
ouverte (fichier:ligne, `gh api`, grep nul re-confirmé au 2026-06-16).

## Les trois référentiels applicables

### 1. OpenSSF Scorecard — santé supply-chain OSS (note /10, automatique)

Référentiel le plus directement applicable : ~18 checks automatisés sur tout
dépôt GitHub public, badge + dashboard. Aligné avec le profil « projet de
recherche tracé, citable » (DOI Zenodo, `CITATION.cff`).

| Check Scorecard          | État au 2026-06-16 | Preuve                                                                                                                                                                                                                                              |
| ------------------------ | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Branch-Protection`      | **vert attendu**   | 13 required checks, PR obligatoire, `strict:true` (SAFEGUARDS.md §branch protection ; `gh api …/branches/main/protection`)                                                                                                                          |
| `Security-Policy`        | **vert**           | `SECURITY.md` présent (Private Vulnerability Reporting + modèle de menace assumé)                                                                                                                                                                   |
| `Pinned-Dependencies`    | **vert (partiel)** | 40/40 actions GitHub SHA-pinnées ([ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)) ; les 2 `FROM` Dagster épinglés par digest (#434), restent les `FROM` Marquez vendorés upstream (`eclipse-temurin`, `node` — ADR 0028) |
| `Dependency-Update-Tool` | **vert**           | `renovate.json` (`pinDigests:true`, `vulnerabilityAlerts`)                                                                                                                                                                                          |
| `CI-Tests`               | **vert**           | `ci.yml` 14 jobs / 13 requis                                                                                                                                                                                                                        |
| `License`                | **vert**           | `LICENSE` + `NOTICE`                                                                                                                                                                                                                                |
| `Token-Permissions`      | **corrigé**        | tous les workflows ont `permissions:` top-level ; le seul `Warn` (`release.yml` `contents: write` top-level) est **confiné au job** `release-please` (#435). `ci.yml` a bien `contents: read`                                                       |
| `Code-Review`            | **rouge (assumé)** | `required_approving_review_count:0`, mono-mainteneur — choix tenu (SAFEGUARDS.md), pas corrigeable sans 2ᵉ relecteur                                                                                                                                |
| `Signed-Releases`        | **rouge**          | tags non signés (`git tag -v v2.9.0` → « cannot verify a non-tag object ») ; release-please ne signe pas                                                                                                                                            |
| `SAST`                   | **en cours**       | Trivy fait l'IaC ; **CodeQL (Python) câblé** (`codeql.yml`, #367) sur le seul code applicatif réel (nestor/, scripts/, tests/ — shell déjà shellcheck, manifestes trivy/kubeconform). Non bloquant d'abord (alertes onglet Security)                |
| `Fuzzing`                | **rouge (N/A)**    | pas de code applicatif à fuzzer (IaC) — non pertinent                                                                                                                                                                                               |

**Effort de câblage : S.** Action officielle `ossf/scorecard-action` + badge
README.

**Quick-wins réalisés (session 2026-06-18, score de départ 4.9/10).**

- `Token-Permissions` 0→ : `release.yml` `contents: write` ramené au seul job
  `release-please` (#435).
- `Pinned-Dependencies` 6→ : les 2 Dockerfiles Dagster épinglés par digest
  d'index multi-arch (#434, dette ADR 0006).
- `SAST` rouge→en cours : CodeQL (Python) câblé (#367).
- `Branch-Protection` (−1) identifié comme **faux négatif** : la protection EST
  configurée (required_status_checks, reviews, signatures, enforce_admins,
  linear_history) mais le token Scorecard ne peut pas la lire.

**Restent assumés/différés** : `Code-Review` (mono-mainteneur, SAFEGUARDS.md),
`Maintained` (dépôt < 90 j, se résout seul), `Signed-Releases`/`Packaging`/
`Fuzzing` (non pertinents pour de l'IaC, ou nécessitent un prérequis — #366).

### 2. CIS Benchmarks — posture de durcissement (PASS/WARN/FAIL par contrôle)

Le référentiel **cœur de l'IaC K8s/Linux**. Le dépôt en couvre déjà une partie
sans le nommer « CIS ».

| Composant CIS                                        | État au 2026-06-16           | Preuve                                                                                                                                                                                    |
| ---------------------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CIS Kubernetes (misconfig manifestes)                | **partiel — Trivy `config`** | `ci.yml` `scan-type: config`, HIGH/CRITICAL bloquant, `.trivyignore.yaml` justifié par chemin (ADR 0010/0011/0012)                                                                        |
| CIS K8s **mode compliance** (rapport par contrôle)   | **absent**                   | Trivy lancé en `config`, **pas** `--compliance k8s-cis` → aucun rapport PASS/FAIL par contrôle CIS                                                                                        |
| CIS K8s **node-level** (kube-bench)                  | **absent**                   | grep `kube-bench` = nul ; aucune exécution node-level (ne se mesure que sur cluster réel → place naturelle = **banc Lima**, [ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)) |
| Pod Security Standards (CIS-aligné)                  | **présent**                  | PSA baseline ([ADR 0014](../decisions/0014-durcissement-kubeadm-init.md)) ; Kyverno CLI statique en CI acté ([ADR 0075](../decisions/0075-kyverno-cli-statique-ci.md))                    |
| CIS Distribution-Independent Linux (durcissement OS) | **partiel opt-in**           | `bootstrap/security/` (auditd, fail2ban, unattended-upgrades) 100 % opt-in ([`IMPLICATIONS.md`](../../bootstrap/security/IMPLICATIONS.md)) ; non noté contre CIS                          |

**Point sensible :** un score CIS **pénalisera** les compromis assumés
(HTTP/auth/chiffrement). Tout rapport CIS produit doit donc s'accompagner d'une
**grille d'exceptions par ADR** (modèle `.trivyignore.yaml`), sinon il lira
comme un échec ce qui est une décision.

**Effort : M.** (a) Étendre Trivy d'un job `--compliance k8s-cis` (statique, non
bloquant d'abord) ; (b) ajouter kube-bench comme **assertion de banc** dans
`bench/lima/` (run-phases), pas en CI (nested-virt impossible, cf.
`bench-freshness.yml:6-9`).

### 3. NIST CSF 2.0 / ANSSI — gouvernance (mapping, pas une note)

Pas un scoring automatique : un **mapping contrôle → preuve dans le dépôt**.
Pertinent pour le contexte universitaire (univ-lehavre). Le dépôt couvre déjà,
de fait, plusieurs fonctions du CSF — sans les avoir cartographiées.

| Fonction NIST CSF 2.0 | Couverture de fait | Preuve                                                                                                                                |
| --------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Govern**            | forte              | 76 ADR Nygard, audit-conventions ([ADR 0060](../decisions/0060-audit-conventions-gouvernance.md)), `SECURITY.md`/`CODE_OF_CONDUCT.md` |
| **Identify**          | moyenne            | inventaire composants (`docs/composants.md`), registre de drifts, matrice de versions (ADR 0006)                                      |
| **Protect**           | forte              | durcissement kubeadm/PSA/etcd (ADR 0014), Cilium NetworkPolicies (ADR 0019), cert-manager CA interne (ADR 0021), hardening OS opt-in  |
| **Detect**            | moyenne-forte      | `bootstrap/state.sh` (drift 7 couches), auditd, Hubble L3/L4/L7                                                                       |
| **Respond**           | moyenne            | rollback par phase/atomique (ADR 0054/0066), rescue Ansible (ADR 0050) — prouvés sur **banc**, pas en incident réel                   |
| **Recover**           | forte              | etcd snapshot+restore (timer + RUNBOOK), CNPG Barman, Ceph size:3 / EC 2+1                                                            |

**Effort : M (rédaction).** Produire une page `docs/` (grille de mapping
CSF→preuve), sous doctrine ADR 0058 (passage daté). ANSSI (Guide d'hygiène) en
second temps si le contexte de financement le demande.

## Gaps priorisés (deviennent l'issue parapluie)

> Conformément à
> [ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md), les manques
> actionnables de ce passage deviennent **une issue** (parapluie, 3 axes en
> cases à cocher).

1. **(impact medium · effort S)** OpenSSF Scorecard non câblé + `ci.yml` sans
   bloc `permissions:`. _Action_ : workflow `scorecard.yml` + badge ;
   `permissions: { contents: read }` en tête de `ci.yml`. _Preuve_ : grep
   `scorecard` = nul (hors cette note) ; `grep -c permissions ci.yml = 0`.
2. **(impact medium · effort M)** CIS non noté par contrôle. _Action_ : job
   Trivy `--compliance k8s-cis` (statique) + kube-bench en assertion de banc,
   accompagnés d'une grille d'exceptions par ADR. _Preuve_ : `ci.yml`
   `scan-type: config` seul ; grep `kube-bench` = nul.
3. **(impact low · effort M)** Pas de mapping CSF/ANSSI explicite. _Action_ :
   page `docs/` grille CSF→preuve (passage daté ADR 0058). _Preuve_ : grep
   `NIST\|CSF\|ANSSI` = nul dans `docs/`.

## Note de méthode et limites

- **Preuves vérifiées au 2026-06-16** : `grep -c permissions ci.yml = 0` ;
  `git tag -v` échoue (tags non signés) ; 76 ADR ; `scan-type: config` dans
  `ci.yml` ; grep nul `kube-bench`/`scorecard`/`codeql`.
- **Scorecard non exécuté réellement** : les états « vert/rouge » sont
  **prédits** depuis le code et le réglage `gh api`, pas issus d'un run
  `scorecard-action`. Le run réel peut nuancer (ex. `Maintained`,
  `Dangerous-Workflow`).
- **CIS non scoré** : aucun rapport kube-bench/Trivy-compliance produit ici — ce
  passage constate la **capacité/absence d'outillage**, pas un score CIS.
- **Frontière `cluster`/`atlas`** : seul `cluster` est audité ; la posture
  applicative (SBOM/scan d'image côté `atlas`) est hors périmètre.
- Ce passage est **figé** (ADR 0058) : il décrit l'état au **2026-06-16**.
