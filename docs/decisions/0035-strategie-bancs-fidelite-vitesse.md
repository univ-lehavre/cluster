# 0035 — Stratégie de bancs : fidélité vs vitesse

## Contexte

La validation e2e est la seule preuve qui compte
([ADR 0034](0034-validation-e2e-from-scratch.md)), mais elle est **lente** : le
run from-scratch de la chaîne DataOps sur le banc Ceph prend **~30 min** (mesuré
: `dataops` à lui seul 13m37s, dominé par le build d'images arm64 ; cf.
[tableau de bord](../architecture/lecons-des-runs.md)). Payer 30 min pour itérer
sur **une** brique (un manifeste, un rôle, une NetworkPolicy) est
disproportionné — d'où la tentation de bancs plus rapides.

Or tous les raccourcis ne se valent pas : **kind a été abandonné** car son nœud
figeait K8s en 1.31, divergent du `kubeadm` 1.34 de prod
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)) ; **k3d** (= k3s)
a le même travers (distribution alternative, pas kubeadm). Un banc rapide ne
doit pas sacrifier la **fidélité au chemin de prod**.

## Décision

**Plusieurs bancs, positionnés sur un axe fidélité ↔ vitesse. On garde le banc
d'intégration comme seule preuve ; on ajoute des bancs ciblés pour itérer — tous
sur le _vrai_ `kubeadm`, jamais une distribution alternative.**

| Banc / profil               | Monte                                    | Temps   | Fidélité | Pour quoi                                         |
| --------------------------- | ---------------------------------------- | ------- | -------- | ------------------------------------------------- |
| `single-node`               | 1 nœud kubeadm + Cilium                  | ~5 min  | ★★       | itérer un **rôle bootstrap**, une version         |
| `multi-node-3` (local-path) | 3 nœuds kubeadm + Cilium, PVC local-path | ~11 min | ★★       | itérer un **manifeste/brique sans stockage réel** |
| `multi-node-3` (ceph)       | + Rook-Ceph + RGW + chaîne DataOps       | ~30 min | ★★★      | **intégration** — la seule preuve complète        |

Principes :

1. **Le banc d'intégration reste `multi-node-3` (ceph).** Lui seul valide la
   chaîne assemblée (CNPG+Barman→RGW, lineage). Une brique n'est « validée »
   qu'après un run from-scratch sur ce banc
   ([ADR 0034](0034-validation-e2e-from-scratch.md)).
2. **`local-path` est un profil d'itération, pas une preuve.** Même topologie et
   même `kubeadm` 1.34 que le Ceph (fidélité préservée), mais sans stockage réel
   (~11 min). Sert à itérer vite sur ce qui **n'exige pas** Ceph (manifestes,
   NetworkPolicies, rôles, addons à PVC simple). **Ne monte pas** la chaîne
   DataOps (CNPG/Barman exigent le RGW Ceph,
   [ADR 0033](0033-orchestration-ansible-platform-dataops.md)).
3. **Pas de distribution alternative (k3d/kind/minikube).** Un banc qui n'est
   pas le `kubeadm` de prod valide autre chose que la prod — refusé (ADR 0006).
   La vitesse se gagne en **retirant des couches** (Ceph, build), pas en
   **changeant d'installeur**.
4. **Profil ≠ topologie.** Le nom technique reste la topologie
   ([ADR 0030](0030-nomenclature-bancs-topologies.md)) ; `(ceph)` /
   `(local-path)` est un **profil de stockage** orthogonal, noté entre
   parenthèses.
5. **Le build d'images est le poste lourd** (~14 min du run Ceph). Son cache
   idempotent (skip si le tag existe déjà dans le registry) est le second levier
   de vitesse, indépendant du profil.

## Statut

Accepted.

## Conséquences

- **Gain** : une boucle d'itération courte (~5–11 min, fidèle à la prod) pour le
  travail quotidien sur une brique, sans renoncer à la preuve complète avant de
  conclure. Le choix du banc devient explicite (table « quel banc pour quoi »,
  [`test/README.md`](../../test/README.md)).
- **Prix à payer** : `local-path` ne couvre pas le stockage résilient ni la
  chaîne DataOps — un changement validé en local-path **doit** repasser sur le
  banc Ceph avant d'être déclaré validé (ADR 0034). Risque assumé : croire à
  tort qu'un « vert en local-path » suffit.
- **Non-régression** : aucune nouvelle dépendance ni nouvel outil — les deux
  profils existent déjà dans `test/lima/run-phases.sh` (`storage-simple` vs
  `WITH_CEPH=1`). Cet ADR formalise l'usage, il n'ajoute pas de code.
- **Évolution** : les terrains futurs (cloud, x86, HA —
  [ADR 0031](0031-terrain-cloud-arm.md)) s'inscrivent sur le même axe ; un banc
  reste fidèle (kubeadm) ou n'est pas une preuve.
