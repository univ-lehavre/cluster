# Plan — right-sizing des requests/limits du socle

## État

> **État : Actif** (2026-07-04). Fonde : principe **corriger le code, pas
> l'état** ([ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md))
> appliqué à une dette mesurée par trois passages d'audit —
> [2026-06-19 (Kubescape)](../audit/2026-06-19-kubescape-nsa.md) l'a nommée,
> [2026-06-24 (prod dirqual)](../audit/2026-06-24-audit-prod-dirqual.md) l'a
> listée,
> [2026-07-04 (requests/limits)](../audit/2026-07-04-audit-ressources-requests-limits.md)
> l'a **chiffrée** (usage réel vs limite), et
> [2026-07-05 (code-first)](../audit/2026-07-05-requests-limits-code-first.md) a
> cartographié **où le dépôt déclare ou omet** chaque resource (fichier:ligne,
> corrigeable) — révélant des trous que le runtime ne voit pas encore (charges
> pas actives : `pg-1/2/3`, cert-manager, RGW, NATS, Kong…). **Pas de nouvel
> ADR** : ce n'est pas une décision structurante, c'est du réglage — chaque
> changement repart dans le manifeste / values **versionné** puis se
> **re-vérifie** par un `kubectl top`.

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
- [x] **Argo CD (7 workloads dont `application-controller`)** — posé par PATCH
      hors-bundle dans le rôle `platform-argocd` (`argocd_resources`, patché
      après l'apply), SANS éditer le bundle vendored (ADR 0006).
      application-controller (StatefulSet, ~690 MiB observé) → lim mem 1536Mi ;
      repo-server 512Mi ; server/autres 128-256Mi. À prouver par `kubectl top`.

### Paliers issus du volet code-first (2026-07-05) — charges pas encore vues par `top`

Le passage code-first a trouvé des workloads **sans resources codées** que le
runtime n'a pas listés (pas encore actifs). Ordre par gravité réelle sur
`dirqual` ; chaque item repart dans un fichier versionné + preuve `kubectl top`.

- [x] **`pg-1/2/3` (CNPG)** — posé `spec.resources` (req 250m/512Mi, lim mem
      2Gi) dans `platform/cloudnative-pg/cluster.yaml`, **dérivé par topologie**
      via `cnpg_resources` (defaults + `combine` du rôle `platform-cnpg`, comme
      `storageClass`). Repos observé ~280 MiB → marge pour les pics pgvector. À
      **prouver par `kubectl top`** après re-apply du rôle sur prod.
- [x] **cert-manager (controller/cainjector/webhook)** — posé par PATCH
      hors-bundle dans le rôle `platform-cert-manager`
      (`cert_manager_resources`, `state: patched` après l'apply), sans éditer le
      bundle figé. cainjector 512Mi (cache cluster-wide) / controller 256Mi /
      webhook 128Mi. À prouver par `kubectl top`.
- [x] **RGW Ceph** (`gateway.resources` req 250m/512Mi lim mem 2Gi,
      `storage/ceph/storageClass/datalake/datalake-ec.yaml`) — chemin données.
      (L'**EventBus NATS** de la chaîne événementielle, jadis borné ici, a été
      **retiré** avec cette chaîne — ADR 0105.)
- [x] **Kong + auth** (`kong.resources` / `auth` dans
      `platform/k8s-dashboard/values.yaml`, paramétrage chart légitime — chemin
      critique NodePort→UI) + **`redcap-mariadb`** (`apps/redcap/mariadb.yaml`
      req 100m/256Mi lim mem 1Gi, base stateful de REDCap).
- [x] **Prometheus 3Gi / Grafana 512Mi matérialisés** dans
      `kube-prometheus-stack.yaml` : les plafonds étaient **décidés dans les
      values** mais le manifeste rendu (seul appliqué par Ansible, sans
      re-render Helm) portait encore les anciens. **Patch chirurgical** des 2
      valeurs (aligné sur les values) plutôt qu'une régénération du bundle de 92
      Ko + 9 digests d'index ré-injectés à la main (risque disproportionné).

> **À laisser** (choix documentés, pas des trous) : toutes les `limits.cpu`
> absentes (CPU compressible → throttling, jamais OOM) ; `metrics-server`
> (system-critical) ; jobs de run Dagster (frontière atlas, ADR 0022) ; exemples
> wordpress ; local-path banc.

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
