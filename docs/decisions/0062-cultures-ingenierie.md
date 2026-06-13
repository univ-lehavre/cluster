# 0062 — Cultures d'ingénierie revendiquées (principe-chapeau)

## Contexte

Le dépôt applique **94 bonnes pratiques** recensées
([`bonnes-pratiques.md`](../architecture/bonnes-pratiques.md),
[ADR 0061](0061-posture-adoption-bonnes-pratiques.md)), organisées **par
mécanisme** (reproductibilité, CI/lint, sécurité, gouvernance…). Mais ces
pratiques relèvent aussi de **cultures d'ingénierie** établies — GitOps,
DataOps, DevSecOps… — qui les regroupent **transversalement** : une même
pratique (épingler une image par digest) sert à la fois la reproductibilité et
le DevSecOps.

Or ces cultures sont **inégalement nommées** dans le dépôt :

- **GitOps** et **DataOps** sont **explicites** : ADR dédiés
  ([0022](0022-argocd-gitops-applicatif.md),
  [0026](0026-orchestration-dagster.md),
  [0028](0028-orchestration-openlineage-marquez.md),
  [0033](0033-orchestration-ansible-platform-dataops.md)), nommés dans des
  dizaines de fichiers.
- **DevSecOps** est **pratiqué mais jamais étiqueté** : toute la chaîne
  supply-chain + durcissement existe (digests multi-arch, actions par SHA,
  Trivy, PSA, etcd chiffré, WireGuard…) sans que le mot apparaisse.
- **Platform Engineering** et **MLOps** sont des **horizons** dont les
  fondations existent, sans être revendiqués.

Sans cadrage, un lecteur ne sait pas **quelles cultures le dépôt revendique** —
ni lesquelles il **écarte délibérément** (et pourquoi). Nommer la posture
culturelle, c'est rendre lisible l'intention derrière le corpus de pratiques
(comme [ADR 0061](0061-posture-adoption-bonnes-pratiques.md) a nommé la posture
_d'adoption_ de ces pratiques).

## Décision

**Le dépôt revendique explicitement quatre cultures d'ingénierie EN PLACE,
construit deux cultures À VENIR, assume une culture PARTIELLE, et écarte
sciemment le reste.** Chaque culture est ancrée dans des ADR existants (elle ne
crée pas de pratique : elle regroupe et nomme).

### Cultures EN PLACE (revendiquées, opérationnelles)

| Culture       | Ce qu'elle recouvre ici                                                                                                                                             | ADR pivots                                                                                                                                                                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **GitOps**    | Git source de vérité, merge-commit, pas de push direct, Argo CD + Gitea air-gapped, `kubectl apply` patron                                                          | [0022](0022-argocd-gitops-applicatif.md), [0037](0037-strategie-merge-commit.md), [0044](0044-topologie-deploiement-banc-atlas.md)                                                                                                                |
| **DataOps**   | Orchestration (Dagster), lineage (OpenLineage/Marquez), base managée (CNPG), contrat d'interface, pas de PII                                                        | [0026](0026-orchestration-dagster.md), [0028](0028-orchestration-openlineage-marquez.md), [0033](0033-orchestration-ansible-platform-dataops.md), [0041](0041-gouvernance-completude-dataops.md), [0043](0043-contrat-interface-cluster-atlas.md) |
| **DevSecOps** | Sécurité dans la chaîne : digests d'index multi-arch, actions par SHA, Trivy IaC, secrets non versionnés, PSA + audit-policy + etcd chiffré, durcissement OS/réseau | [0006](0006-matrice-de-versions-et-politique-de-bump.md), [0014](0014-durcissement-kubeadm-init.md), [0019](0019-durcissement-reseau-cilium.md), [0023](0023-plateforme-exemple-generique.md)                                                     |
| **IaC**       | Infrastructure-as-Code déclarative et reproductible : catalogue de topologies, idempotence Ansible prouvée, provisioning OpenTofu                                   | [0023](0023-plateforme-exemple-generique.md), [0032](0032-opentofu-provisioning-cloud.md), [0033](0033-orchestration-ansible-platform-dataops.md)                                                                                                 |

### Cultures EN CONSTRUCTION (revendiquées, fondations posées)

- **Platform Engineering** — le dépôt EST un **catalogue de topologies
  réutilisables** ([ADR 0023](0023-plateforme-exemple-generique.md)) avec un
  **contrat plateforme↔consommateur**
  ([ADR 0043](0043-contrat-interface-cluster-atlas.md)) : les « paved roads »
  existent. Le cœur self-service d'un Platform Engineering — un **IDP**
  (internal developer platform) : générateur sans état de `topology.yaml` + TUI
  « que faire ensuite » — est **décidé mais pas encore implémenté**
  ([ADR 0056](0056-modele-declaratif-topologies.md), paliers P0-P8). Revendiqué
  **en construction**, pas acquis.
- **MLOps** — **à venir**. Le socle DataOps (lineage, orchestration, stockage,
  base managée) est le **prérequis** d'un MLOps (feature store, registry de
  modèles, pipelines d'entraînement) ; aucun composant ML n'est déployé
  aujourd'hui. Visée future, sans ADR dédié pour l'instant.

### Cultures PARTIELLES (assumées implicites)

- **SRE** — des pratiques SRE existent **sans le label** : détection de drift
  multi-couche (`state.sh`), fraîcheur des preuves
  ([ADR 0042](0042-fraicheur-preuves-banc.md)), sauvegarde etcd + RPO
  ([ADR 0014](0014-durcissement-kubeadm-init.md)), runbooks opératoires,
  rollback scripté. Il manque le formalisme SRE complet (SLO/SLI, error budgets,
  postmortems structurés) — d'où **partielle**, non revendiquée comme culture
  pleine.
- **FinOps — volet efficience / gestion de capacité uniquement.** Le FinOps «
  coût € cloud » ne s'applique pas (voir Écartées), mais sa **moitié efficience
  des ressources** est **déjà amorcée** : collecte CPU/RAM/stockage via
  kube-prometheus-stack ([ADR 0016](0016-observabilite.md)), métrologie de banc
  (`cpu_core_s`/`ram_peak`, et le sizing disque/réseau visé par #241), gestion
  de capacité Ceph (RUNBOOK : `ceph df`, seuils nearfull/full). Il manque la
  **formalisation** (dashboard capacité/efficience dédié, right-sizing
  systématique des `requests`/`limits`) — d'où **partielle**.

### Cultures ÉCARTÉES (hors périmètre, sciemment)

- **FinOps — volet coût € / chargeback.** Pas de dimension monétaire : le dépôt
  est un catalogue d'infra de recherche **bare-metal non facturé à l'usage**, et
  **mono-tenant / mono-admin** (pas de refacturation interne). La gestion de
  coût cloud (réduire une facture, attribuer par équipe) est hors périmètre tant
  que ce contexte ne change pas — la **topologie cloud ARM**
  ([ADR 0031](0031-terrain-cloud-arm.md)/[0032](0032-opentofu-provisioning-cloud.md)),
  elle, serait facturée et rouvrirait la question le jour où elle est buildée.
- Toute autre bannière (« \*Ops » à la mode) n'est revendiquée que si elle est
  **ancrée dans des ADR et des pratiques réelles** — pas par effet de mode
  ([ADR 0061](0061-posture-adoption-bonnes-pratiques.md) : pas d'adoption
  compulsive).

## Statut

Accepted (2026-06-13). **Principe-chapeau**, sœur d'
[ADR 0061](0061-posture-adoption-bonnes-pratiques.md) (posture d'adoption) : il
ne crée aucune pratique ni ne supersede aucun ADR — il **nomme et classe** les
cultures que le corpus de pratiques incarne déjà. La
[page d'inventaire](../architecture/bonnes-pratiques.md) porte la **vue
transverse « Par culture »** qui matérialise ce classement.

## Conséquences

- **Lisibilité externe** : on peut répondre « le dépôt est GitOps, DataOps,
  DevSecOps, IaC ; Platform Engineering et MLOps en construction » — avec les
  ADR à l'appui, pas une déclaration creuse.
- **Honnêteté sur les manques** : nommer DevSecOps **acquis** mais SRE
  **partiel** et MLOps **à venir** évite la sur-revendication (le travers
  inverse du conservatisme — cf.
  [ADR 0061](0061-posture-adoption-bonnes-pratiques.md)).
- **Vue transverse outillée** : la page d'inventaire gagne une lecture **par
  culture** en plus de la lecture **par mécanisme** ; les deux grilles sont
  orthogonales et complémentaires.
- **Cap pour les chantiers futurs** : Platform Engineering (IDP via ADR 0056) et
  MLOps sont nommés comme **directions assumées**, ce qui oriente les prochaines
  décisions sans les figer (un futur ADR les fera passer « en place »).
- **Prix à payer** : une classification culturelle a une part de convention (la
  frontière « partiel » vs « en place » est un jugement) ; elle est révisable
  quand une culture mûrit (SRE → en place quand SLO/error budgets seront posés).

## Alternatives écartées

- **Organiser la page d'inventaire UNIQUEMENT par culture**
  (DevSecOps/GitOps/…). Écarté : la vue **par mécanisme** est celle que le
  script `check_gouvernance` vérifie (chaque pratique → un ADR) ; une vue par
  culture seule perdrait ce lien. On garde les deux (mécanisme = vérifiable,
  culture = lisible).
- **Ne pas nommer les cultures** (laisser implicite). Écarté : GitOps/DataOps
  sont déjà nommés ; laisser DevSecOps/PlatformEng implicites créerait une
  asymétrie, et un lecteur ne saurait pas ce qui est revendiqué vs écarté.
- **Revendiquer toutes les cultures « Ops » par marketing.** Écarté : c'est
  l'adoption compulsive que
  [ADR 0061](0061-posture-adoption-bonnes-pratiques.md) proscrit ; on ne
  revendique qu'ancré dans des pratiques réelles (d'où FinOps écarté, SRE
  seulement partiel).
- **Fondre ce classement dans l'ADR 0061.** Écarté : 0061 décide la **posture
  d'adoption** (comment on adopte une pratique) ; 0062 classe les **cultures
  adoptées** (ce qu'on revendique). Deux sujets distincts, deux ADR.
