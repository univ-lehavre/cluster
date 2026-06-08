# 0043 — Contrat d'interface cluster → atlas

## Contexte

Le travail se répartit sur **deux dépôts** : `cluster` (ce dépôt — le **socle
d'infrastructure** générique : Kubernetes, stockage, plateforme DataOps) et
`atlas` (le dépôt **applicatif/métier** — pipelines, assets, code des
traitements). Leur frontière est posée par
[ADR 0023](0023-plateforme-exemple-generique.md) (le métier vit dans `atlas`,
jamais ici) et [ADR 0022](0022-argocd-gitops-applicatif.md) (Argo CD déploie
l'applicatif via l'`AppProject` `atlas`).

Mais l'**interface** entre les deux reste **implicite** : pour qu'un pipeline
`atlas` se connecte à Postgres, pousse une image, émette du lineage ou lise un
bucket S3, il doit connaître des **endpoints** (noms de Services, ports,
namespaces), des **StorageClasses** et des **conventions de secrets**. Ces faits
existent — dispersés dans les manifestes `platform/`, `storage/` et dans
[`docs/guide-dev-data.md`](../guide-dev-data.md) — mais ne sont **ni regroupés
ni machine-lisibles**. Un développeur `atlas` doit aujourd'hui les **deviner**
ou fouiller le dépôt `cluster`.

## Décision

**Le dépôt `cluster` publie un contrat d'interface explicite et machine-lisible
vers `atlas`** : ce que le socle s'engage à exposer (endpoints, StorageClasses,
namespaces, conventions de secrets), en **valeurs d'exemple génériques** (ADR
0023), sous [`contract/`](../../contract/).

1. **Trois artefacts versionnés** (`*.example.yaml`), source unique côté
   `cluster`, consommables par `atlas` :
   - [`contract/endpoints.example.yaml`](../../contract/endpoints.example.yaml)
     — Services exposés : nom, namespace, port, protocole, FQDN interne, auth.
   - [`contract/storage-classes.example.yaml`](../../contract/storage-classes.example.yaml)
     — StorageClasses disponibles **par profil** (Ceph / local-path) et la SC
     `default` de chacun.
   - [`contract/namespaces-secrets.example.yaml`](../../contract/namespaces-secrets.example.yaml)
     — namespaces de destination (alignés sur l'`AppProject` `atlas`) et
     **conventions de secrets** (rôles CNPG, dérivés Dagster/Marquez, OBC S3).

2. **Patron `.example`** (ADR 0023) : ces fichiers portent des **valeurs
   d'exemple concrètes et stables** (FQDN, ports, noms de SC réels — qui sont
   des briques que le dépôt propose, donc **conservées**), mais **aucune valeur
   réelle d'un déploiement** (pas de mot de passe, pas d'IP de prod, pas de
   creds S3). Les valeurs réelles vivent en config locale non versionnée.

3. **Cohérence avec la doc existante** : le contrat **n'invente rien** — il
   formalise la table d'accès déjà décrite dans
   [`docs/guide-dev-data.md`](../guide-dev-data.md) (« Points d'accès ») et la
   rend requêtable. La prose reste la pédagogie ; le contrat, la donnée.

4. **Sens unique `cluster → atlas`** : ce contrat décrit ce que le socle
   **fournit**. Ce qu'`atlas` **attend en retour** (schémas de données, formats
   d'assets) relève du dépôt `atlas` (frontière ADR 0023). Le contrat liste une
   section « attendu par atlas » à titre indicatif, sans la normaliser ici.

## Statut

Accepted.

## Conséquences

- **Gain** : un développeur `atlas` lit **un seul endroit** pour se brancher —
  plus de devinette, plus de fouille du dépôt `cluster`. Le contrat est
  diff-able : tout changement d'endpoint/SC/secret côté socle est **visible** en
  revue et peut casser un test côté `atlas` de façon explicite.
- **Frontière préservée** (ADR 0023) : le contrat est de l'**INFRA** (ce que le
  socle expose) ; il ne contient aucun cas d'usage métier. Les namespaces
  applicatifs y figurent comme **cibles de déploiement** (déjà déclarées dans
  l'`AppProject` `atlas`), pas comme contenu métier.
- **Maintenance** : le contrat doit être tenu à jour quand un endpoint change.
  Il référence ses fichiers sources (manifestes) ; à terme, un test pourrait
  vérifier la cohérence contrat ↔ manifestes (hors périmètre de cet ADR).
- **Prix à payer** : une duplication assumée entre les manifestes (vérité
  d'exécution) et le contrat (vérité d'interface). Justifiée : `atlas` ne doit
  pas dépendre de la structure interne des manifestes `cluster`, seulement de
  l'interface stable.
- **Profils** : le contrat distingue explicitement **Ceph** (prod / preuve) et
  **local-path/SeaweedFS** (banc rapide) — un consommateur sait quel endpoint S3
  ou quelle SC viser selon le profil
  ([ADR 0035](0035-strategie-bancs-fidelite-vitesse.md),
  [ADR 0036](0036-backing-s3-unique-rgw.md)).
