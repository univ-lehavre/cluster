# 0032 — OpenTofu pour le provisioning des VM cloud

## Contexte

Le terrain cloud ARM ([ADR 0031](0031-terrain-cloud-arm.md)) doit créer et
détruire de vraies VM à la demande (free tier monté/démonté souvent). Les fronts
de provisioning locaux existants — Vagrant (`test/multi-node/`,
`test/single-node/`) et Lima (`test/lima/`) — ne couvrent pas le cloud, et
provisionner des VM cloud **en CLI impérative** est fragile : pas d'idempotence,
pas de `destroy` fiable → risque de VM orphelines qui **coûtent** ou saturent un
quota free tier.

Or [ADR 0023](0023-plateforme-exemple-generique.md) pose une **implémentation
impérative** (Ansible/scripts) et **aucune IaC déclarative** n'existe dans le
dépôt (pas de `.tf`). Introduire un outil déclaratif à état est donc une
décision à part entière, avec deux points durs : l'entorse à l'impératif, et le
fichier d'**état** (qui contient des identités réelles — frontal avec la
généricité 0023).

## Décision

**Adopter OpenTofu** (fork libre de Terraform, licence MPL — cohérent avec
l'esprit open source du dépôt) pour la **seule couche de provisioning IaaS du
terrain cloud**.

- **Périmètre strictement borné.** OpenTofu **crée/détruit les VM** (et le
  réseau minimal associé), rien de plus. Le **bootstrap Kubernetes et le
  déploiement applicatif restent impératifs** (Ansible/scripts, ADR 0023) :
  OpenTofu produit des VM Debian + SSH, un script en **génère l'inventaire
  Ansible**, et la suite est le bootstrap existant — même aboutissement que
  Vagrant/Lima (`write_inventory → bootstrap`). Le déclaratif ne déborde pas du
  IaaS.

- **Entorse à ADR 0023 cadrée, pas générale.** L'impératif reste la règle du
  dépôt ; le déclaratif est une **exception cantonnée au provisioning de VM
  cloud**, là où il est l'outil juste (idempotence, `destroy` propre). Aucune
  brique de plateforme (Ceph, Cilium, CNPG…) ne passe à l'IaC déclarative.

- **`tfstate` : jamais versionné, jamais d'identité réelle committée.** L'état
  contient des IDs/IPs/secrets réels → il est **gitignoré** et stocké sur un
  **backend distant** (chiffré) configuré en **local non versionné**. Le code
  OpenTofu versionné n'emploie que des **variables** ; les valeurs réelles
  (fournisseur, région, OCID/compte, clés) vivent dans un `*.tfvars.example`
  versionné générique + un `*.tfvars` local gitignoré — même patron que
  `bootstrap/hosts.example.yaml`
  ([ADR 0023](0023-plateforme-exemple-generique.md)).

- **Provider générique.** Le code cible un fournisseur via variables ; aucun nom
  de fournisseur/région/instance en dur dans le versionné (terrain « cloud ARM
  », ADR 0031).

- **Version pinnée.** OpenTofu et les providers sont épinglés
  (`.terraform.lock.hcl` committé + version dans la matrice
  [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).

## Statut

Accepted (cadrage). Aucun `.tf` n'est encore versionné ; cet ADR autorise et
borne leur introduction. L'implémentation (code OpenTofu + `*.tfvars.example` +
génération d'inventaire + run consigné) fera l'objet d'un ticket dédié.

## Conséquences

- **Gain** : provisioning cloud idempotent avec `destroy` fiable — pas de VM
  orpheline facturée ; le bon outil pour la couche IaaS.
- **Prix à payer** : un 5ᵉ écosystème (après bash, Ansible, Node, Python) à
  installer/pinner/maintenir, pour ce seul terrain ; une exception déclarative à
  documenter face à l'impératif d'ADR 0023.
- **Risque** : fuite d'identités via un `tfstate` mal géré → mitigé par
  gitignore + backend distant + `*.tfvars` local + revue. Un `.tf` ou un state
  contenant du réel committé serait un défaut ADR 0023.
- **Alternative écartée** : Terraform classique (licence BSL non libre) ; Pulumi
  (impératif, mais réintroduit un runtime langage et un service d'état).
  OpenTofu est le compromis libre + standard HCL.
