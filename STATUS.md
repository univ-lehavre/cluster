# STATUS — avancement du durcissement (audit → mise en œuvre)

> **Dernière mise à jour : 2026-06-01 18:38 CEST.** Document vivant —
> **horodater toute modification** (en-tête ci-dessus + la date entre crochets
> sur chaque ligne modifiée). État du dépôt à la **v2.6.2**.

Suivi de la mise en œuvre du plan d'audit
([`docs/audit/12-plan-action.md`](docs/audit/12-plan-action.md)) et des écarts
constatés entre ce plan et les audits thématiques détaillés (01→11).

Légende : ✅ fait · 🔲 à faire · ⏸️ reporté · ❓ à vérifier finement.

---

## 1. Avancement par priorité

_État vérifié dans le code le **2026-06-01**._

### Priorité 1 — Résilience & données

| #   | Action                                   | État                                                |
| --- | ---------------------------------------- | --------------------------------------------------- |
| 1   | Tester restauration etcd (banc)          | ✅ [2026-06-01] `test/scenarios/09-etcd-restore.sh` |
| 2   | Sauvegarde données applicatives          | ✅ [2026-06-01] ADR 0013 + VolumeSnapshots          |
| 3   | Copier snapshots etcd hors-nœud + RPO    | ❓ [2026-06-01] à vérifier (fetch/push S3 ?)        |
| 4   | Qualifier datasets twitter/reddit (RGPD) | 🔲 [2026-06-01] décision référent/DPO               |

### Priorité 2 — Néophyte

| #   | Action                      | État                                         |
| --- | --------------------------- | -------------------------------------------- |
| 5   | Glossaire                   | ✅ [2026-06-01] `docs/glossaire.md` (249 l.) |
| 6   | Gloser chaque terme + liens | ❓ [2026-06-01] vérif fine                   |
| 7   | Page `docs/demarrage.md`    | 🔲 [2026-06-01] absente                      |

### Priorité 3 — Supply chain

| #   | Action                             | État                                                    |
| --- | ---------------------------------- | ------------------------------------------------------- |
| 8   | Job trivy en CI                    | ✅ [2026-06-01]                                         |
| 9   | renovate / dependabot              | 🔲 [2026-06-01] `renovate.json` présent — app à activer |
| 10  | Toolbox Ceph alignée v20.2.1       | ✅ [2026-06-01]                                         |
| 11  | Épingler images par digest @sha256 | 🔲 [2026-06-01] aucun digest                            |

### Priorité 4 — Tests & scripts

| #   | Action                                         | État                                                |
| --- | ---------------------------------------------- | --------------------------------------------------- |
| 12  | bats-core sur `state.sh` (« meilleur ROI »)    | ✅ [2026-06-01] `test/unit/` (18 tests, PR #48)     |
| 13  | Faux-positifs scénarios 04/05                  | ✅ [2026-06-01] `exit 1` à l'expiration des boucles |
| 14  | Parsing `ceph -f json \| jq` (scénarios 03/05) | ✅ [2026-06-01] (`getent shadow` : voir note)       |
| 15  | Dérouler 8 scénarios + exit codes              | ❓ [2026-06-01] drift #9 CSI déjà résolu            |

### Priorité 5 — Opérabilité jour 2

| #   | Action                                           | État                                          |
| --- | ------------------------------------------------ | --------------------------------------------- |
| 16  | `Justfile` racine + « Par où commencer »         | ✅ [2026-06-01] `Justfile` + README → RUNBOOK |
| 17  | Observabilité (metrics-server / kube-prometheus) | 🔲 [2026-06-01]                               |
| 18  | Runbook + playbook `kubeadm upgrade` ; renommer  | 🔲 [2026-06-01]                               |
| 19  | Surveillance SMART NVMe                          | 🔲 [2026-06-01]                               |

### Priorité 6 — Sécurité ✅ (close sauf #20)

| #   | Action                            | État                                                  |
| --- | --------------------------------- | ----------------------------------------------------- |
| 20  | Tailscale operator / ACL          | ⏸️ [2026-06-01] **reporté sine die**                  |
| 21  | Durcissement kubeadm              | ✅ [2026-06-01] ADR 0014 + PodSecurity baseline       |
| 22  | NetworkPolicies default-deny      | ✅ [2026-06-01] `platform/network-policies/` (PR #39) |
| 23  | securityContext workloads         | ✅ [2026-06-01] (PR #37)                              |
| 24  | UFW K8s/Cilium/Ceph + SSH + drift | ✅ [2026-06-01] (PR #41)                              |
| 25  | Services en ClusterIP             | ✅ [2026-06-01] (PR #43)                              |

### Priorité 7 — Gouvernance

| #   | Action                                         | État                                                              |
| --- | ---------------------------------------------- | ----------------------------------------------------------------- |
| 26  | `CITATION.cff`                                 | ✅ [2026-06-01] créé (ORCID/DOI à compléter)                      |
| 27  | `SECURITY.md` + Private Vuln. Reporting        | ✅ [2026-06-01] créé                                              |
| 28  | Versionnement : retirer commit-and-tag-version | ✅ [2026-06-01] retiré (release-please seul)                      |
| 29  | Branch protection GitHub                       | ✅ [2026-06-01] strict + conversation resolution (cf. SAFEGUARDS) |
| 30  | Licence subtree (MIT/NOTICE/SPDX)              | ✅ [2026-06-01] `NOTICE` (subtree Unlicense vs MIT)               |
| 31  | CODE_OF_CONDUCT, templates, CODEOWNERS         | ✅ [2026-06-01] créés (.github/ + racine)                         |

### Priorité 8 — Hygiène

| #   | Action                                         | État                    |
| --- | ---------------------------------------------- | ----------------------- |
| 32  | Supprimer `bootstrap/bootstrap/`               | ✅ [2026-06-01]         |
| 33  | editLink/ignoreDeadLinks/socialLinks ; READMEs | ❓ [2026-06-01]         |
| 34  | Parité lint (jscpd pre-push, lint dans pnpm)   | ❓ [2026-06-01]         |
| 35  | markdownlint + lychee en CI                    | 🔲 [2026-06-01] absents |
| 36  | ADR 0005 + patch K8s + actions GitHub          | ❓ [2026-06-01]         |
| 37  | Compléter tables README                        | ❓ [2026-06-01]         |
| 38  | Factoriser ssh-report.sh / lib.sh ; SSH_OPTS   | ❓ [2026-06-01]         |

### ADR à formaliser

| ADR                                   | État            |
| ------------------------------------- | --------------- |
| 0013 — sauvegarde données             | ✅ [2026-06-01] |
| 0014 — durcissement kubeadm           | ✅ [2026-06-01] |
| 0015 — langage scripts (bash/jq/bats) | 🔲 [2026-06-01] |
| ADR upgrade K8s (rebuild vs in-place) | 🔲 [2026-06-01] |
| ADR Rook-Ceph vs Longhorn             | 🔲 [2026-06-01] |
| ADR observabilité                     | 🔲 [2026-06-01] |

---

## 2. Écarts plan d'action ↔ audits détaillés

_Vérification croisée 12-plan-action.md ↔ fichiers 01→11 effectuée le
**2026-06-01**._

**Verdict :** le plan d'action couvre **100 % des constats majeurs** et
n'invente rien, mais son chapeau (« toutes les recommandations ») est
**inexact** : ~22 recommandations **mineures/suggestions** des audits 01-11
n'ont pas été reportées dans la Priorité 8. Ci-dessous les omissions
**opérationnelles** (les cosmétiques sont regroupées en fin).

### Omissions opérationnelles (à intégrer au backlog) — [2026-06-01]

| Réf source           | Recommandation absente du plan                                                                     |
| -------------------- | -------------------------------------------------------------------------------------------------- |
| `02-tests:125`       | Runner agrégé `run-all.sh` (tableau PASS/FAIL, HEALTH_OK entre scénarios destructifs)              |
| `02-tests:110`       | `ansible-playbook --syntax-check` en CI                                                            |
| `02-tests:90`        | Scénario 03 ne teste pas la **continuité des I/O** (PVC+pod en écriture pendant downtime)          |
| `02-tests:100`       | Scénarios légers `09-registry-push-pull` / `10-rstudio-smoke`                                      |
| `03-lint:68`         | Templates `.sh.j2` (etcd-backup) et script `.pl` (`blur-env.pl`) échappent au lint                 |
| `06-securite:64`     | **Vérif d'exposition NodePort/LoadBalancer dans `state.sh`** — perdue car noyée dans #20 (reporté) |
| `08-operabilite:128` | Section **capacité Ceph** au RUNBOOK (`ceph df`, ajout d'OSD, GC PVC registry)                     |
| `08-operabilite:113` | **SPOF applicatifs** mono-réplica (registry/rstudio/wordpress) non tracés                          |
| `11-oss:104`         | Annotations Tailscale **orphelines** (registry/rstudio) à documenter sans l'operator               |
| `11-oss:116`         | Headscale comme repli OSS dans l'ADR 0003 « À revoir si »                                          |
| `07-gouvernance:89`  | 3ᵉ CHANGELOG (`bootstrap/security/CHANGELOG.md`, Changesets) à geler/supprimer                     |
| `06-securite:141`    | Audit-log Ansible sans non-répudiation → documenter + sshd `LogLevel VERBOSE`                      |

### Omissions cosmétiques/mineures — [2026-06-01]

`03-lint:86` warnings yamllint (`#x`→`# x`) · `03-lint:103` sévérité shellcheck
CI/hooks · `04-doc:121` renvois ADR au point de code + commentaires
`bootstrap/security/` · `04-doc:176` titre README `# cluster`→`# Cluster` ·
`04-doc:79` colonne outil dans CONTRIBUTING · `05-repro:72` devDependencies en
ranges `^` · `05-repro:79` tags flottants WordPress/MySQL + commentaire Tentacle
obsolète · `01:76` rôles sans `defaults/`/`meta/` · `01:61` double convention
`.yaml`/`.yml` · cosign/SBOM (`08:123`, `11:54`) jamais nommés (plan parle de
digests seulement).

---

## 3. Notes de méthode

- **Banc de test** : certaines validations (UFW, NetworkPolicies sur
  rstudio/registry) **n'ont pas pu être exécutées** sur le banc Vagrant — les
  VMs n'ont pas d'accès Internet (apt/pull d'images impossibles). Validé alors
  statiquement (ansible-lint/kubeconform) + #22 prouvé sur le namespace
  `default`. _[2026-06-01]_
- **Restore de nœud sur le banc** : ne pas chercher à valider (artefacts
  Vagrant/arm64 sans valeur prod) — cf. mémoire projet. _[2026-06-01]_
- **Releases** : automatiques (release-please + auto-merge, PAT
  `RELEASE_PLEASE_TOKEN`). Penser à la **rotation du PAT** avant expiration.
  _[2026-06-01]_
- **#14 reliquat** : le parsing `ceph` est passé en `-f json | jq` (scénarios
  03/05), mais la lecture de `getent shadow` au lieu de `chage` dans `state.sh`
  (classification passwd) **reste à faire** — la logique de classification est
  désormais isolée dans `classify_passwd`
  ([state-classify.sh](bootstrap/lib/state-classify.sh)), donc le changement de
  source de date sera local et couvert par bats. _[2026-06-01]_
