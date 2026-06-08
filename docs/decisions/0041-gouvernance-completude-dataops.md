# 0041 — Gouvernance & complétude de la chaîne DataOps (cadrage)

> **Désambiguïsation indispensable.** Ici « **catalogue de données** » =
> inventaire des _assets/datasets_ (découvrabilité, glossaire, owner). À ne
> **pas** confondre avec le « **catalogue de topologies** » du dépôt
> ([ADR 0039](0039-nomenclature-axes-catalogue.md) : matériel × topologie ×
> terrain × briques). Deux sens distincts du mot « catalogue ».

## Contexte

La chaîne DataOps livrée et **validée e2e** (sur les deux profils S3) est :
orchestration **Dagster** ([ADR 0026](0026-orchestration-dagster.md)), lineage
**OpenLineage/Marquez** ([ADR 0028](0028-orchestration-openlineage-marquez.md)),
store **CNPG** ([ADR 0024](0024-postgres-manage-cloudnative-pg.md)),
observabilité (Prometheus/Grafana/Loki) et backing S3 paramétrable
([ADR 0036](0036-backing-s3-unique-rgw.md)).

Comparée aux pratiques DataOps usuelles et à la demande « gouvernance et
catalogue de données », il manque : **transformation dbt**, **data quality**
(tests), **catalogue de données** (DataHub/OpenMetadata), **data contracts**, et
un cadre de **gouvernance** (owner, classification PII, KPI qualité). Plusieurs
questions étaient ouvertes : intégrer Airflow **en choix** de Dagster ? dbt
est-il dans la chaîne ? la gouvernance est-elle pertinente ?

Deux invariants du dépôt **contraignent fortement** la réponse :

1. **Frontière infra / métier** ([ADR 0026](0026-orchestration-dagster.md):11,
   [ADR 0028](0028-orchestration-openlineage-marquez.md):12) : ce dépôt déploie
   l'**orchestrateur « vide »** ; le **code** (assets, **dbt**, tests) vit dans
   le dépôt applicatif **`atlas`** (Phase 2+), livré par GitOps. Beaucoup de «
   briques » DataOps sont donc du **métier**, pas de l'infra à monter ici.
2. **Honnêteté des Runs** ([ADR 0023](0023-plateforme-exemple-generique.md) /
   [ADR 0034](0034-validation-e2e-from-scratch.md)) : on ne documente pas comme
   « acquis » ce qui n'est ni rendu ni validé sur banc.

## Décision

**Cadrer la complétude DataOps en trois plans nets — infra / métier / pratique —
plutôt qu'« ajouter cinq briques ».** Rien n'est implémenté dans cet ADR : il
fixe le périmètre, l'ordre et la frontière.

### 1. Plan INFRA — déployable dans ce dépôt (rôle Ansible + manifeste figé)

| Brique                    | Décision                                                                                                                                                                                                                                                                                                                            | Statut                   |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| Orchestrateur **Airflow** | option **alternative** à Dagster (axe catalogue [ADR 0023](0023-plateforme-exemple-generique.md)/[0039](0039-nomenclature-axes-catalogue.md) : _une_ activée, jamais les deux) ; outil d'orchestration le plus répandu de l'écosystème ; KubernetesExecutor (pas de Celery/Redis), base CNPG dédiée, provider OpenLineage → Marquez | cible                    |
| **Catalogue de données**  | **OpenMetadata** (pas DataHub : évite Kafka + Elasticsearch ; OpenMetadata = Postgres CNPG + 1 moteur de recherche) ; ingère le lineage Marquez                                                                                                                                                                                     | cible (en ligne de mire) |

- **Airflow ≠ cumul.** L'orchestrateur reste un **axe à une valeur** : on
  déploie Dagster **ou** Airflow, jamais les deux (sinon double infra + lineage
  brouillé). Le débat « Dagster vs Airflow » n'est **pas rouvert**
  ([ADR 0026](0026-orchestration-dagster.md) tient) : Airflow est ajouté comme
  **option de catalogue** parce qu'il est l'orchestrateur **le plus répandu** de
  l'écosystème (large base d'utilisateurs, versions managées chez les
  fournisseurs cloud, abondante documentation) — c'est un argument
  d'**interopérabilité et de familiarité**, pas une supériorité technique sur
  Dagster.
- **Le catalogue est la brique la plus chère** : son moteur de recherche est un
  **stateful hors CNPG** (PVC RBD ×3, opérateur/manifeste à vendorer et bumper —
  [ADR 0001](0001-replication-x3-pour-workloads-bloc.md)/[0006](0006-matrice-de-versions-et-politique-de-bump.md)).
  Il est donc **différé** : nommé « en ligne de mire », non documenté comme
  acquis tant qu'il n'est ni rendu (helm figé, patron 0026/0028) ni validé banc.

### 2. Plan MÉTIER — vit dans `atlas`, PAS dans ce dépôt

**dbt**, **dbt tests / Great Expectations / Soda** (mode bibliothèque, en tâche
d'orchestrateur), **data contracts** : ce sont des **dépendances d'exécution**
(image au registry interne + `OPENLINEAGE_URL` + NetworkPolicy egress→Marquez),
**pas des services à déployer ici**. Ils émettent du lineage par le **même
chemin** que l'existant (POST OpenLineage vers `marquez.marquez.svc:5000`). Ce
dépôt fournit les **points d'accès génériques** (code-location Dagster, bases
CNPG, OBC S3, émission lineage) ; le contenu va dans `atlas`.

### 3. Plan PRATIQUE — actionnable maintenant, coût d'infra nul

La gouvernance des données couvre 6 dimensions : **catalogue, glossaire,
lineage, qualité, contrats, propriété/PII**. **Seul le lineage est livré**
(Marquez). Les pratiques suivantes apportent l'essentiel de la valeur RGPD
**sans déployer de brique** :

- **Classification PII + owner** par dataset/bucket : étendre l'invariant «
  aucune PII dans le lineage »
  ([ADR 0028](0028-orchestration-openlineage-marquez.md):50) en politique —
  chaque asset porte `owner` + classification (public / interne / PII) + base
  légale + rétention.
- **KPI qualité** : formaliser 3–4 caractéristiques **ISO/IEC 25012**
  (complétude, fraîcheur, exactitude, cohérence) comme cibles mesurables (mesure
  côté `atlas`/ dbt). Pas les 15 du modèle — sobriété.
- **Data contracts** (Open Data Contract Standard / Data Contract Specification)
  : convention versionnée dans `atlas`, vérifiée en CI / à l'exécution.

> **Trou RGPD prioritaire** : l'audit
> [`08-operabilite.md`](../audit/08-operabilite.md) note que le datalake
> provisionne des buckets de **corpus de réseaux sociaux** (source de données
> ouverte, générisée — ADR 0023) porteurs de données personnelles, alors que
> [ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)/
> [0011](0011-registry-http-sans-auth.md)/[0012](0012-rstudio-disable-auth.md)
> reposent sur « pas de PII », **sans politique de rétention / minimisation /
> base légale**. La qualification (référent DPO) de ces datasets est le
> **livrable gouvernance le plus mûr** — prérequis à une éventuelle révision de
> 0003/0011/0012.

## Statut

Accepted (cadrage). Chaque brique infra (Airflow, catalogue) et chaque pratique
fera l'objet d'un ADR/PR dédié, validé e2e
([ADR 0034](0034-validation-e2e-from-scratch.md)) avant d'être déclaré acquis.
Ordre de priorité (valeur / coût d'intégration) : **dbt (atlas) → data quality
(atlas) → catalogue OpenMetadata (infra) → data contracts** ; Airflow traité
quand le besoin d'interopérabilité l'exige.

## Conséquences

- **Gain** : une vision claire de « complétude DataOps » qui **respecte la
  frontière infra/métier** — on ne sur-déploie pas dans `cluster` ce qui relève
  d'`atlas`. La gouvernance avance par les **pratiques** (coût nul, valeur RGPD)
  avant la brique lourde (catalogue).
- **Prix à payer** : le catalogue de données (OpenMetadata) est un stateful
  supplémentaire hors CNPG — assumé comme la brique la plus coûteuse, donc
  différée. Airflow doublerait l'effort orchestrateur — réservé au besoin réel.
- **Garde-fous** (issus de l'instruction) : (a) **un seul** orchestrateur actif
  ; (b) **un seul** catalogue (OpenMetadata, pas DataHub) ; (c) **ne pas
  empiler** les outils de qualité — 1–2 qui produisent un KPI mesuré ; (d) toute
  brique stateful suit le patron socle (base CNPG dédiée + Secret dérivé à
  source unique, manifeste figé, networkpolicies default-deny, images registre
  interne, e2e banc) — ne pas recréer la dette shell soldée par
  [ADR 0033](0033-orchestration-ansible-platform-dataops.md) ; (e) **invariant
  zéro-PII dans le lineage** reconduit pour toute brique qui ingère des données
  ; (f) génériser (ADR 0023) — garder les noms de briques (Airflow,
  OpenMetadata, dbt…), génériser les sources métier.
