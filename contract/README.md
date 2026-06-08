# Contrat d'interface `cluster` → `atlas`

Ce dossier publie, sous forme **machine-lisible**, ce que le socle `cluster`
expose à un consommateur intra-cluster (le dépôt applicatif `atlas`) :
endpoints, StorageClasses et conventions de namespaces/secrets. Décision et
justification :
[ADR 0043](../docs/decisions/0043-contrat-interface-cluster-atlas.md).

Les fichiers sont en **valeurs d'exemple génériques** (patron `*.example`,
[ADR 0023](../docs/decisions/0023-plateforme-exemple-generique.md)) : les
FQDN/ports/noms de SC sont des **briques stables** que le dépôt propose (donc
réelles), mais **aucune valeur propre à un déploiement** (mot de passe, IP de
prod, creds S3) n'y figure — celles-ci vivent en config locale non versionnée.

## Artefacts

| Fichier                                                              | Contenu                                                                     |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| [`endpoints.example.yaml`](endpoints.example.yaml)                   | Services exposés : nom, namespace, port, protocole, FQDN interne, auth.     |
| [`storage-classes.example.yaml`](storage-classes.example.yaml)       | StorageClasses **par profil** (Ceph / local-path) + la SC `default`.        |
| [`namespaces-secrets.example.yaml`](namespaces-secrets.example.yaml) | Namespaces de destination + conventions de secrets (CNPG, dérivés, OBC S3). |

## Pour un développeur `atlas`

La table d'accès **pédagogique** (avec exemples de code Python/SQL) vit dans le
[guide du développeur data](../docs/guide-dev-data.md). Ce dossier en est la
version **donnée** : diff-able, consommable par un script, source unique côté
`cluster`. Tout changement d'endpoint/SC/secret y est visible en revue.

## Frontière (ADR 0023)

Ce contrat décrit l'**INFRA fournie** par le socle (sens `cluster → atlas`). Les
schémas de données, formats d'assets et cas d'usage métier relèvent du dépôt
`atlas` — ils ne sont **pas** ici.
