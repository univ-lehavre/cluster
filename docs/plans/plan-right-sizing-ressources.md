# Plan — right-sizing des requests/limits du socle

## État

> **État : Actif** (2026-07-04). Fonde : principe **corriger le code, pas
> l'état** ([ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md))
> appliqué à une dette mesurée par trois passages d'audit —
> [2026-06-19 (Kubescape)](../audit/2026-06-19-kubescape-nsa.md) l'a nommée,
> [2026-06-24 (prod dirqual)](../audit/2026-06-24-audit-prod-dirqual.md) l'a
> listée,
> [2026-07-04 (requests/limits)](../audit/2026-07-04-audit-ressources-requests-limits.md)
> l'a **chiffrée** (usage réel vs limite). **Pas de nouvel ADR** : ce n'est pas
> une décision structurante, c'est du réglage — chaque changement repart dans le
> manifeste / values **versionné** puis se **re-vérifie** par un `kubectl top`.

Périmètre : les **limites mémoire sous-dimensionnées** du socle (monitoring +
dataops) et une hygiène de limites. **Hors périmètre** : Ceph (élastique par
conception — voir plus bas) et les charges infra/control-plane sans limite
(défauts upstream, rayon de souffle contenu par ~251 GiB/nœud).

## Objectif

Éliminer les OOMKill **par-conteneur** (qui surviennent même à 4 % d'usage
cluster, le plafond étant local) et poser une marge **avant** que la chaîne de
traitement applicative ne charge Prometheus (cibles), MLflow (modèles/artefacts)
et Marquez (lineage). Le cluster a la marge : ~800 GiB / 300+ cœurs libres.

## Suivi

Paliers (cases à cocher) ; chaque correctif = édition d'un fichier versionné +
preuve `kubectl top pod` après application. Issues à créer/rattacher au fil.

- [x] **MLflow 768Mi → 1,5 GiB / request 512 MiB** —
      `platform/mlflow/mlflow.yaml`. OOM (exit 137) sur maintenance
      (`mlflow gc`). **Appliqué + vérifié** en prod (patch chirurgical, env S3
      préservé).
- [x] **Prometheus 1024Mi → 3 GiB** —
      `platform/kube-prometheus-stack/values.bench.yaml`
      (`prometheusSpec.resources`). Usage **989Mi / 1024Mi (97 %)** → OOM
      imminent. **Appliqué + vérifié** (patch du CR Prometheus, l'opérateur
      reconcilie la STS → limite 3Gi confirmée).
- [x] **Grafana 256Mi → 512 MiB** — même values (`grafana.resources`). Conteneur
      à **130 %**. **Appliqué + vérifié** (512Mi). **Bonus** : ajout de
      `deploymentStrategy: Recreate` — le PVC **RWO** (single-attach) faisait
      **deadlocker toute MAJ** en RollingUpdate (Multi-Attach : le 2ᵉ pod ne
      peut monter le même PVC). Bug latent corrigé (constaté en relevant la
      limite).
- [x] **Marquez 768Mi → 1,5 GiB** (préventif) — `platform/marquez/marquez.yaml`
      (rôle `platform-marquez`). JVM Dropwizard serrée ; 0 lineage reçu encore.
      **Appliqué + vérifié** (1536Mi).
- [ ] **Hygiène — `argocd-application-controller`** (668Mi non borné) —
      **différé** : la ressource vit dans le **bundle vendored**
      `platform/argocd/argocd.yaml` (édition proscrite, exclu du lint) ;
      priorité _info_, faible enjeu (rayon de souffle contenu par ~251
      GiB/nœud).

### Ne PAS faire — Ceph (rappel de la loi d'élasticité)

`osd_memory_target = 4 GiB` **fixe** (= la limite OSD, `autotune=false`) :
**relever la limite des OSD ne libère rien**, Ceph agrandit d'autant son cache
(« plus on donne, plus il prend »). Le plafond 48 × 4 = ~192 GiB est
**délibéré**. Le seul levier pour _borner_ la RAM Ceph serait de **baisser**
`osd_memory_target` (arbitrage cache↔RAM) — à n'envisager que si la RAM venait à
manquer, ce qui n'est pas le cas (usage cluster 4 %).

## Vérification

Après chaque palier : `kubectl -n <ns> top pod <pod>` (usage sous la nouvelle
limite) + absence de nouveau `OOMKilled`/exit 137 sur la fenêtre suivante. La
convention du dépôt : pas de limite CPU (requests CPU seuls, pour éviter le
throttling) — on ne touche **que** les limites mémoire.
