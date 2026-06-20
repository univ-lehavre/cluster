# 0015 — Stratégie d'upgrade Kubernetes (in-place vs rebuild)

## Contexte

L'audit ([08-operabilite](../audit/2026-05-29/08-operabilite.md)) relève
l'absence de stratégie d'upgrade Kubernetes formalisée : le dépôt sait
**installer** (bootstrap greenfield) mais pas **monter de version** un cluster
en service. Or K8s publie une mineure tous les ~4 mois et chaque mineure n'est
supportée que ~14 mois → il faut une procédure répétable, sinon le cluster
dérive hors support.

Deux voies possibles :

- **Rebuild greenfield** : réinstaller à neuf (déjà la pratique du dépôt pour
  les changements lourds, cf. RUNBOOK). Données effacées → suppose une
  restauration.
- **Upgrade in-place** via `kubeadm upgrade` : monter le cluster existant sans
  détruire les données.

## Décision

**Upgrade in-place via kubeadm pour les montées de patch et de mineure ; rebuild
réservé aux cas exceptionnels.**

- Playbook [`k8s-upgrade.yaml`](../../bootstrap/k8s-upgrade.yaml) + rôle
  [`k8s-upgrade`](../../bootstrap/roles/k8s-upgrade/) :
  - **Control plane d'abord** (`kubeadm upgrade apply`), drainé/restauré.
  - **Workers un par un** (`serial: 1` : drain → `kubeadm upgrade node` →
    kubelet → uncordon). Un seul nœud indisponible à la fois → les workloads se
    replanifient sur les autres (réplicat ×3 Ceph + `failureDomain: host` le
    permettent).
- **Une mineure à la fois.** kubeadm n'autorise pas de sauter plusieurs mineures
  (1.34 → 1.36) en une fois : passer 1.34 → 1.35 → 1.36. Vérifier la compat
  croisée Cilium/Rook/Ceph **avant** (cf.
  [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md), plafond commun).
- **Patch (1.34.x → 1.34.y)** : sûr et fréquent → in-place sans cérémonie.
- **Rebuild** : réservé aux situations où l'in-place est impossible/risqué
  (corruption etcd, saut de versions trop large, changement d'OS majeur). Le
  rebuild reste documenté dans le RUNBOOK comme procédure de dernier recours.

Le playbook **OS** (`upgrade.yaml`) est renommé
[`os-upgrade.yaml`](../../bootstrap/os-upgrade.yaml) pour lever l'ambiguïté avec
l'upgrade Kubernetes.

## Statut

Accepted (2026-06-01).

## Conséquences

**Bénéfices.**

- Cluster maintenable dans la fenêtre de support sans perte de données.
- Procédure répétable, séquencée, validable sur le banc multi-node.
- Indisponibilité limitée à un nœud à la fois (pas de coupure globale).

**Coûts assumés.**

- **SPOF control plane pendant son upgrade** : l'API est indisponible le temps
  du `kubeadm upgrade apply` sur `cp1` (cluster mono-control-plane, cf.
  [ADR 0002](0002-control-plane-unique-avec-endpoint.md)). Fenêtre courte,
  acceptée. Les workloads continuent de tourner (seul le plan de contrôle est
  momentanément indisponible).
- **Discipline de version** : ne jamais sauter de mineure ; vérifier la matrice
  ADR 0006 avant. Le playbook `assert` la présence d'une version cible mais ne
  vérifie pas la compat croisée (responsabilité de l'opérateur).
- **Validation banc obligatoire** : un upgrade raté en prod est coûteux →
  rejouer sur `bench/multi-node/` d'abord.

## À revoir

- Si un 2ᵉ/3ᵉ control plane est ajouté (HA) → adapter le playbook pour upgrader
  les control planes secondaires via `kubeadm upgrade node` (déjà géré par le
  rôle pour les nœuds hors `groups['control'][0]`) et supprimer le SPOF
  d'upgrade.
- Automatiser la vérification de compat croisée (release-notes) au lieu de la
  laisser manuelle.

> **Amendement 2026-06-19.** Le banc cité ici sous `bench/multi-node/` (Vagrant)
> est **déprécié** au profit du banc Lima
> ([ADR 0038](0038-lima-seul-banc-local.md), commit 1aac57c) : lire désormais
> `bench/lima/`. La décision (upgrade in-place séquencé, validé d'abord sur
> banc) est inchangée.
