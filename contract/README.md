# Contrat d'interface `cluster` → `atlas`

Ce dossier publie, sous forme **machine-lisible**, ce que le socle `cluster`
expose à un consommateur intra-cluster (le dépôt applicatif `atlas`) :
endpoints, StorageClasses et conventions de namespaces/secrets. Décision et
justification :
[ADR 0043](/cluster/docs/decisions/0043-contrat-interface-cluster-atlas/).

Les fichiers sont en **valeurs d'exemple génériques** (patron `*.example`,
[ADR 0023](/cluster/docs/decisions/0023-plateforme-exemple-generique/)) : les
FQDN/ports/noms de SC sont des **briques stables** que le dépôt propose (donc
réelles), mais **aucune valeur propre à un déploiement** (mot de passe, IP de
prod, creds S3) n'y figure — celles-ci vivent en config locale non versionnée.

## Artefacts

| Fichier                                                                                                                         | Contenu                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`endpoints.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/contract/endpoints.example.yaml)                   | Services exposés : nom, namespace, port, protocole, FQDN interne, auth. Les **UI** portent en plus `exposed: true` (exposition L4 NodePort, [ADR 0092](https://github.com/univ-lehavre/cluster/blob/main/docs/decisions/0092-exposition-hostport-l4.md) — `http://<IP-nœud>:<nodePort>`, port observé par le portail) + `layer` (socle/monitoring/gitops/dataops) — consommés par le **portail** (#232). |
| [`storage-classes.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/contract/storage-classes.example.yaml)       | StorageClasses **par profil** (Ceph / local-path) + la SC `default`.                                                                                                                                                                                                                                                                                                                                     |
| [`namespaces-secrets.example.yaml`](https://github.com/univ-lehavre/cluster/blob/main/contract/namespaces-secrets.example.yaml) | Namespaces de destination + conventions de secrets (CNPG, dérivés, OBC S3).                                                                                                                                                                                                                                                                                                                              |

## Pour un développeur `atlas`

La table d'accès **pédagogique** (avec exemples de code Python/SQL) vit dans le
[guide du développeur data](/cluster/docs/guide-dev-data/). Ce dossier en est la
version **donnée** : diff-able, consommable par un script, source unique côté
`cluster`. Tout changement d'endpoint/SC/secret y est visible en revue.

## Frontière (ADR 0023)

Ce contrat décrit l'**INFRA fournie** par le socle (sens `cluster → atlas`). Les
schémas de données, formats d'assets et cas d'usage métier relèvent du dépôt
`atlas` — ils ne sont **pas** ici.
