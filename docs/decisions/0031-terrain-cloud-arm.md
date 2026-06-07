# 0031 — Terrain d'exécution cloud ARM (cadrage)

## Contexte

Toute la couverture build actuelle est **arm64 / local / `multi-node-3`**
([matrice du catalogue](../architecture/matrice-catalogue.md)) : les bancs Lima
et Vagrant tournent sur un poste Apple Silicon. Deux trous structurants restent
: les topologies **`ha-3cp`** (control plane HA) et **`multisite`** (mesh
inter-site) ne sont **jamais montées sur de vraies machines**, et la latence
inter-site n'est que **simulée** (`tc netem`, spike `mesh-2clusters`,
[ADR 0030](0030-nomenclature-bancs-topologies.md)).

Un **terrain cloud ARM gratuit** (offre « free tier » de plusieurs fournisseurs
: ~4 cœurs ARM / 24 GiB répartissables en plusieurs VM) permettrait de rejouer
ces profils sur de vraies VM, avec de vraies latences inter-régions — sans coût.
Ce ticket **cadre** l'approche ; il ne l'implémente pas.

## Décision

Adopter le **cloud ARM** comme **terrain d'exécution cible** du catalogue (axe «
terrain » de la matrice), selon ces partis pris :

1. **Provisioning des VM par OpenTofu, puis inventaire → bootstrap.**
   Provisionner des VM cloud (création/destruction idempotente, pas de VM
   orpheline qui coûte) est précisément le domaine d'un outil déclaratif. On
   adopte **OpenTofu** pour cette couche IaaS — décision et traitement du
   `tfstate` vs généricité dans un ADR dédié
   ([ADR 0032](0032-opentofu-provisioning-cloud.md)). OpenTofu crée les VM ; un
   script en **génère l'inventaire Ansible**, consommé par le bootstrap existant
   — même aboutissement que les fronts Vagrant/Lima
   (`write_inventory → bootstrap`). L'impératif reste la règle pour le
   **déploiement applicatif** ([ADR 0023](0023-plateforme-exemple-generique.md))
   ; le déclaratif est cantonné au provisioning IaaS.

2. **Bootstrap réutilisé tel quel.** Les VM cibles sont en **Debian + SSH** —
   exactement les hypothèses de `bootstrap/`. Le bootstrap Ansible tourne sans
   fork ; le multi-cluster/HA est déjà **paramétrable en opt-in**
   ([ADR 0027](0027-bootstrap-parametre-multi-cluster.md) : CIDR, `cluster.id`/
   `name`). Aucun rôle nouveau n'est requis pour un premier run.

3. **Topologies visées** : **`ha-3cp`** (3 control planes — la HA jamais montée
   en local faute de ressources) et **`multisite`** (un cluster autonome par
   région, fédéré par Cilium Cluster Mesh, avec **vraie** latence inter-région
   au lieu du `tc netem` du spike). `single-node` / `multi-node-3` y sont
   rejouables pour comparaison, mais l'intérêt du terrain est la HA et le mesh
   réels.

4. **Généricité stricte ([ADR 0023](0023-plateforme-exemple-generique.md)).** La
   documentation versionnée parle de **« terrain cloud ARM (free tier) »** —
   **aucun** nom de fournisseur, de région, de type d'instance, d'OCID/compte ni
   d'identité réelle. Le fournisseur concret, les identifiants et les régions
   vivent en **config locale non versionnée** (gitignorée) surchargeant un
   `*.example` versionné, comme `bootstrap/hosts.example.yaml`.

## Statut

Accepted (cadrage). L'implémentation (script de provisioning + inventaire
`*.example` + run consigné) fera l'objet d'un ticket dédié ; le terrain reste
**`cible, non buildé`** dans la matrice jusqu'à un run consigné.

## Conséquences

- **Gain** : une voie tracée pour combler les trous `ha-3cp` et `multisite` et
  pour mesurer le mesh sous **vraie** latence — sans coût (free tier) et en
  réutilisant le bootstrap existant (paramétrable, ADR 0027) sans le forker.
- **Prix à payer** : dépendance à une offre commerciale (free tier susceptible
  de changer) ; introduction d'un outil déclaratif (OpenTofu) en exception à
  l'impératif du dépôt — cadrée par
  [ADR 0032](0032-opentofu-provisioning-cloud.md).
- **Garde-fou généricité** : tout futur artefact (script, inventaire, RUNBOOK)
  passe par un `*.example` générique ; une identité réelle committée serait un
  défaut ADR 0023.
- **Limite du cadrage** : le choix du fournisseur précis, le découpage des 4
  cœurs ARM gratuits entre VM (p. ex. 3×1 cœur pour `ha-3cp`, ou 2 VM en 2
  régions pour `multisite`) et la faisabilité réseau inter-région restent à
  valider à l'implémentation.
