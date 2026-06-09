# Bancs de test locaux

Banc local unique : **Lima** (vraie VM, SSH natif, disques bruts virtio, sans
VirtualBox). Vagrant + VirtualBox sont **abandonnés**
([ADR 0038](../docs/decisions/0038-lima-seul-banc-local.md)) ; le
provisionnement local n'est plus un axe du catalogue
([ADR 0039](../docs/decisions/0039-nomenclature-axes-catalogue.md)).

**Nommage** : chaque banc valide une **topologie** au nom technique stable,
indépendant de l'outil
([ADR 0030](../docs/decisions/0030-nomenclature-bancs-topologies.md)).

| Nom technique    | Dossier                                                      | Outil | Topologie               | Disques Ceph     | Phases couvertes                    | Démarrage |
| ---------------- | ------------------------------------------------------------ | ----- | ----------------------- | ---------------- | ----------------------------------- | --------- |
| `multi-node-3`   | [`lima/`](lima/)                                             | Lima  | 3 VMs + user-v2         | 3 HDD + block.db | 1, 2 (avec join), 3 (Ceph), 4       | ~15 min   |
| `mesh-2clusters` | [`spikes/clustermesh-latency/`](spikes/clustermesh-latency/) | Lima  | 2 clusters + `tc netem` | n/a              | spike Cilium Cluster Mesh (jetable) | variable  |

> Topologies **cibles** nommées mais pas encore montées sur banc : `ha-3cp` (3
> control planes HA), `multisite` (plusieurs sites, 1 cluster autonome par
> site). Cf.
> [ADR 0030](../docs/decisions/0030-nomenclature-bancs-topologies.md).

## Les trois niveaux de tests

Unitaire (bats, sans cluster), intégration (gates de phase), scénarios
(comportement) : le **plan de tests** les recense ensemble, avec la couverture
par couche et les lacunes à combler :
[plan de tests](../docs/architecture/plan-de-tests.md).

## Quel profil pour quoi — fidélité vs vitesse (ADR 0035)

Choisir selon **ce qu'on itère** et le **temps qu'on peut payer**. Le banc
tourne le **vrai `kubeadm` 1.34** (pas de distribution alternative type k3d/kind
— ADR 0006) : la vitesse se gagne en retirant des couches (Ceph, build), jamais
en changeant d'installeur. Temps mesurés sur M3 Max
([tableau de bord](../docs/architecture/lecons-des-runs.md)).

| Besoin (ce qu'on itère)                               | Profil                      | Temps   | Fidélité | Commande                                                          |
| ----------------------------------------------------- | --------------------------- | ------- | -------- | ----------------------------------------------------------------- |
| Manifeste / brique **sans stockage réel**             | `multi-node-3` (local-path) | ~11 min | ★★       | `run-phases.sh socle` (smoke rapide)                              |
| **Banc atlas** : socle GitOps + DataOps (léger)       | `multi-node-3` (local-path) | ~20 min | ★★       | `run-phases.sh atlas` (monitoring → gitops → dataops)             |
| **Stockage réel** : bloc RWO + objet S3 (Ceph)        | `multi-node-3` (ceph)       | ~30 min | ★★★      | `run-phases.sh storage-real` (datalake → smoke S3 → WordPress)    |
| **DataOps sur Ceph** : chaîne complète, stockage réel | `multi-node-3` (ceph)       | ~35 min | ★★★      | `run-phases.sh cluster-dataops` (datalake → monitoring → dataops) |

> **`(local-path)` = profil d'itération, PAS une preuve de stockage réel.** Même
> topologie et même `kubeadm` que le Ceph, mais sans stockage répliqué : idéal
> pour itérer vite. La chaîne DataOps **y tourne** (chemin `atlas`) avec un
> backing S3 **SeaweedFS** au lieu du RGW Ceph (ADR 0036). Mais un changement
> qui touche le **stockage** (réplication, EC, RGW) **doit** repasser sur le
> profil **`(ceph)`** (chemin `storage-real`) avant d'être déclaré validé
> ([ADR 0034](../docs/decisions/0034-validation-e2e-from-scratch.md) : la preuve
> est un run e2e from-scratch). Le profil est un axe **orthogonal** à la
> topologie (ADR 0030) — noté `(ceph)` / `(local-path)`.

## Réserves transversales

- **Architecture arm64** (Apple Silicon) ≠ **x86_64** des serveurs lames : on
  valide la _logique_ (rôles, manifestes, ordres, comportements), pas les
  artefacts binaires x86_64. La fidélité x86_64 se gagne sur le banc baremetal
  (cf. [matrice du catalogue](../docs/architecture/matrice-catalogue.md)).
- **Fonctionnel, pas perfs** : VMs modestes, disques virtuels petits.
- **Image pré-construite** : Debian 13 — l'installation Debian elle-même (mode
  expert, partitionnement LVM, firmware bnxt, IP statique) n'est **pas**
  rejouée. Cette étape se valide à la main lors du rebuild serveurs (cf.
  [`bootstrap/RUNBOOK.md`](../bootstrap/RUNBOOK.md)).
- **Restore d'un nœud (halt → relance) non fidèle** : le retour d'une VM exerce
  des artefacts banc (route ClusterIP perdue au reboot, clock skew) **absents de
  la prod**. La _perte_ de nœud reste un test de résilience valable ; le
  _restore_, non — ne pas chercher à le « réparer » sur le banc. Détail :
  [`scenarios/README.md`](scenarios/README.md) (03/04) et
  [`RESULTS.md`](RESULTS.md).

## Pré-requis communs

| Outil   | Version  | Installation           | Bancs   |
| ------- | -------- | ---------------------- | ------- |
| Ansible | ≥ 2.20.5 | `brew install ansible` | tous    |
| Lima    | ≥ 2.0    | `brew install lima`    | `lima/` |

Voir le [README du banc Lima](lima/) pour les détails (réseau `user-v2`, disques
bruts virtio, etc.).

## Nettoyage

Pour libérer du disque ou repartir d'un état frais :

```bash
test/lima/run-phases.sh down    # détruit les VMs/disques du banc Lima
```
