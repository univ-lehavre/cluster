# 12 — Plan d'action priorisé

Toutes les recommandations de l'audit, classées par priorité **et par effort**.
Le classement combine la gravité vérifiée et le rapport valeur/coût pour un
**mainteneur quasi unique en milieu recherche**.

## Priorité 1 — Résilience prouvée & sécurité des données (à traiter en premier)

Ces points touchent à l'intégrité des données et à la capacité réelle de
récupération. Un seul incident peut être irréversible.

| #   | Action                                                                                                                                                                                                    | Constat source                             | Effort            |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------- |
| 1   | **Tester la restauration etcd** sur le banc (scénario `09-etcd-restore.sh` : effacer etcd → `etcdctl snapshot restore` → vérifier le retour des workloads)                                                | [02](02-tests.md), [08](08-operabilite.md) | Moyen             |
| 2   | **Définir une sauvegarde des données applicatives** (ADR RPO/RTO + CSI VolumeSnapshots des PVC critiques et/ou réplication des buckets S3) ; basculer les pools précieux en `preservePoolsOnDelete: true` | [08](08-operabilite.md)                    | Moyen             |
| 3   | **Copier les snapshots etcd hors-nœud** (`fetch` Ansible ou push S3/autre nœud) + documenter le RPO                                                                                                       | [08](08-operabilite.md)                    | Faible            |
| 4   | **Qualifier les datasets `twitter`/`reddit` au regard du RGPD** (référent/DPO) ; selon le verdict, réviser ADR 0003/0011/0012 ou documenter l'anonymisation amont                                         | [08](08-operabilite.md)                    | Faible (décision) |

## Priorité 2 — Objectif néophyte (le critère explicite de votre demande)

| #   | Action                                                                                                                                                                                      | Constat source            | Effort |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- | ------ |
| 5   | **Créer `docs/glossaire.md`** (Kubernetes, etcd, CNI, CRI, OSD, MON, PVC, RWX, erasure coding, drift, hyperconvergence, Tailscale…), le placer en tête de sidebar, le lier depuis le README | [04](04-documentation.md) | Moyen  |
| 6   | **Gloser chaque terme à son premier usage** et lier vers le glossaire ; marquer les sections « avancé/optionnel »                                                                           | [04](04-documentation.md) | Moyen  |
| 7   | **Page `docs/demarrage.md`** : public visé, prérequis de connaissances, parcours numéroté 1→5                                                                                               | [04](04-documentation.md) | Faible |

## Priorité 3 — Supply chain & gestion du risque OSS

| #   | Action                                                                                                       | Constat source                                          | Effort  |
| --- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------- | ------- |
| 8   | **Job `trivy`** (image + config IaC) en CI, échec sur HIGH/CRITICAL + allowlist documentée des compromis ADR | [03](03-lint-format.md), [11](11-logiciels-oss.md)      | Faible  |
| 9   | **renovate** (ou dependabot npm + Actions), PR groupées mensuelles ; maintient aussi les digests             | [11](11-logiciels-oss.md)                               | Faible  |
| 10  | **Aligner la toolbox Ceph sur `v20.2.1`** (idéalement digest), supprimer `:v19`                              | [05](05-reproductibilite.md), [11](11-logiciels-oss.md) | Trivial |
| 11  | **Épingler par digest `@sha256`** les composants critiques (rook/ceph, ceph, registry)                       | [11](11-logiciels-oss.md)                               | Faible  |

## Priorité 4 — Robustesse des tests & des scripts

| #   | Action                                                                                                                                                                  | Constat source              | Effort |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ------ |
| 12  | **bats-core** sur les fonctions pures de `state.sh` (classification passwd, comptage HDD, parsing) — **meilleur ROI du dépôt**                                          | [09](09-langage-scripts.md) | Moyen  |
| 13  | **Corriger les faux-positifs** des scénarios 04 et 05 (`exit 1` à l'expiration des boucles d'attente)                                                                   | [02](02-tests.md)           | Faible |
| 14  | **Passer le parsing `ceph` en `-f json \| jq`** (scénarios 03/05) ; robustifier le passage de données de `state.sh` (JSON+jq) ; lire `getent shadow` au lieu de `chage` | [09](09-langage-scripts.md) | Faible |
| 15  | Résoudre le drift #9 (CSI) puis dérouler les 8 scénarios de bout en bout et consigner les exit codes                                                                    | [02](02-tests.md)           | Moyen  |

## Priorité 5 — Découvrabilité & opérabilité jour 2

| #   | Action                                                                                                                                                                                       | Constat source             | Effort      |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- | ----------- |
| 16  | **`Justfile` racine mince** nommant l'existant (`bootstrap`, `state`, `security-report`, `test-bench`, `test-scenarios`) + **section « Par où commencer »** dans le README liant les RUNBOOK | [10](10-dispersion-cli.md) | Faible      |
| 17  | **Observabilité** : a minima metrics-server ; idéalement kube-prometheus-stack + `monitoring.enabled: true` (alertes Ceph)                                                                   | [08](08-operabilite.md)    | Moyen/Élevé |
| 18  | **Runbook + playbook `kubeadm upgrade`** ; **renommer `upgrade.yaml` → `os-upgrade.yaml`**                                                                                                   | [08](08-operabilite.md)    | Moyen       |
| 19  | **Surveillance SMART NVMe** (`smartd` + alerte, ou couche `state.sh`)                                                                                                                        | [08](08-operabilite.md)    | Faible      |

## Priorité 6 — Sécurité (durcissement defense-in-depth)

| #   | Action                                                                                                                                                            | Constat source       | Effort  |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | ------- |
| 20  | **Matérialiser l'hypothèse réseau** : committer le Tailscale operator + ACL et le marquer **requis** (ou documenter le contrôle réseau réel dans `SAFEGUARDS.md`) | [06](06-securite.md) | Moyen   |
| 21  | **`ClusterConfiguration` kubeadm** : audit-policy + `EncryptionConfiguration` (Secrets etcd) + PodSecurity admission ; ou tracer le choix en ADR                  | [06](06-securite.md) | Moyen   |
| 22  | **NetworkPolicies / CiliumNetworkPolicy** de base (default-deny par namespace)                                                                                    | [06](06-securite.md) | Moyen   |
| 23  | **`securityContext` sur RStudio** (drop ALL, seccomp, runAsNonRoot)                                                                                               | [06](06-securite.md) | Trivial |
| 24  | **Jeu de règles UFW K8s/Cilium/Ceph** prêt à l'emploi ; restreindre SSH à la plage d'admin ; signaler l'absence d'UFW comme drift                                 | [06](06-securite.md) | Moyen   |
| 25  | Dashboard Ceph en ClusterIP ; Service WordPress en ClusterIP                                                                                                      | [06](06-securite.md) | Trivial |

## Priorité 7 — Gouvernance & conformité projet

| #   | Action                                                                                                                   | Constat source          | Effort  |
| --- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------- | ------- |
| 26  | **`CITATION.cff`** (DOI cluster, auteurs + ORCID) — important pour la recherche                                          | [07](07-gouvernance.md) | Trivial |
| 27  | **`SECURITY.md`** + activer Private Vulnerability Reporting                                                              | [07](07-gouvernance.md) | Trivial |
| 28  | **Trancher le versionnement** : release-please seul (retirer commit-and-tag-version) ; corriger l'en-tête du `CHANGELOG` | [07](07-gouvernance.md) | Faible  |
| 29  | **Branch protection rule GitHub** (PR + checks requis) — le hook local est contournable                                  | [07](07-gouvernance.md) | Trivial |
| 30  | **Clarifier la licence du subtree** (re-licencier MIT ou NOTICE + SPDX)                                                  | [07](07-gouvernance.md) | Faible  |
| 31  | `CODE_OF_CONDUCT.md`, templates issue/PR, `CODEOWNERS`                                                                   | [07](07-gouvernance.md) | Faible  |

## Priorité 8 — Hygiène & cohérence (au fil de l'eau)

| #   | Action                                                                                                                                                             | Constat source                                          |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| 32  | Supprimer `bootstrap/bootstrap/` ; harmoniser `.env-example`/`.gitignore`/doc                                                                                      | [01](01-bonnes-pratiques.md)                            |
| 33  | `editLink` → `univ-lehavre` ; `ignoreDeadLinks` → liste ciblée ; `socialLinks` GitHub ; `platform/README.md` + `apps/README.md`                                    | [04](04-documentation.md)                               |
| 34  | Parité lint : `jscpd` en pre-push, `lint:k8s`/`lint:ansible` dans `pnpm lint`, factoriser les exclusions kubeconform, corriger l'incompat `.yamllint`/ansible-lint | [03](03-lint-format.md)                                 |
| 35  | markdownlint + lychee (link-checker) en CI                                                                                                                         | [03](03-lint-format.md)                                 |
| 36  | Aligner ADR 0005 et le code (hold containerd) ; figer le patch K8s ; épingler les actions GitHub                                                                   | [05](05-reproductibilite.md)                            |
| 37  | Compléter la table `bootstrap/README.md` ; ajouter la table `test/`+`docs/` au README racine                                                                       | [01](01-bonnes-pratiques.md), [04](04-documentation.md) |
| 38  | Factoriser `bootstrap/lib/ssh-report.sh` ; `test/scenarios/lib.sh` ; lever la collision `SSH_OPTS`                                                                 | [10](10-dispersion-cli.md)                              |

## Décisions à formaliser en ADR (transmissibilité / bus-factor)

Pour un mainteneur quasi unique, tracer les choix structurants réduit le risque
:

- **ADR 0013** — « bash pour l'orchestration de CLIs / JSON+jq pour le parsing /
  python3 toléré / bats-core pour les fonctions pures »
  ([09](09-langage-scripts.md)).
- **ADR** — stratégie de sauvegarde des données (RPO/RTO)
  ([08](08-operabilite.md)).
- **ADR** — stratégie d'upgrade K8s (rebuild vs in-place)
  ([08](08-operabilite.md)).
- **ADR** — choix Rook-Ceph vs Longhorn (compromis assumé)
  ([11](11-logiciels-oss.md)).
- **ADR** — observabilité (option retenue) ([08](08-operabilite.md)).
- Compléter les ADR 0003/0011/0012 si la qualification RGPD change la donne.

---

> **Note de méthode** — Les gravités de ce plan reflètent la vérification
> adversariale : plusieurs constats sécurité, initialement « majeurs », ont été
> ramenés à « mineur » parce qu'ils correspondent à des risques **assumés et
> documentés en ADR**. Ils restent dans le plan comme durcissements
> _defense-in-depth_, pas comme failles ouvertes. Inversement, les points de
> Priorité 1 (résilience non prouvée, RGPD) sont maintenus « majeurs » car ils
> ne sont **pas** couverts par une décision explicite.
