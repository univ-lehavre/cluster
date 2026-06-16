# 2026-06-15 — Audit « maximiser l'usage des outils CNCF » (Kyverno en tête)

| Champ        | Contenu                                                                                                                                                                                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**     | 2026-06-15                                                                                                                                                                                                           |
| **Type**     | cartographie en éventail + revue adversariale (opportunités confrontées à la gouvernance d'adoption)                                                                                                                 |
| **Fonde**    | _réflexion_ — alimente de futurs ADR (Kyverno CLI en CI ; passage de [ADR 0064](../decisions/0064-longhorn-option-stockage-catalogue.md) à `Accepted`). **Aucune décision ici.**                                     |
| **Éventail** | 2 passages, **60 agents** au total (passage 1 : 20 agents, 6 axes ; passage 2 : 40 agents, 6 familles non couvertes), chaque opportunité vérifiée sur fichiers puis jugée adversarialement contre ADR 0049/0057/0061 |
| **Verdict**  | 12/13 opportunités retenues au passage 1 ; **1/33** candidat retenu au passage 2 (Longhorn, déjà acté). Tête de file : **Kyverno CLI statique en CI** (zéro composant runtime, comble un trou de couverture réel).   |

## Pourquoi ce workflow

La question posée — « maximiser l'usage des outils CNCF, notamment Kyverno » —
heurte de front le **biais adoptif borné**
([ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md)) : «
maximiser » n'est pas un but ; **ne rien empiler contre une décision tenue ou
pour un besoin inexistant** l'est. Le workflow sépare donc deux choses qu'un
audit naïf confond : (1) où une brique CNCF **comble un trou vérifié** ou
**remplace du code maison**, et (2) où elle ne ferait qu'**empiler**. Chaque
opportunité a été ouverte sur les fichiers réels, puis confrontée à
[ADR 0049](../decisions/0049-doctrine-choix-outil-par-action.md) (un outil par
action),
[ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md) (ADR si
structurant) et au coût mono-admin non-HA. Cette note prolonge et précise la
réflexion ouverte par
[`2026-05-29/note-runtime-admission.md`](2026-05-29/note-runtime-admission.md)
(« réflexion, pas une décision »).

## Synthèse (assainie — valeurs génériques, ADR 0023)

### Le dépôt est déjà massivement CNCF

Cilium (graduated, CNI unique eBPF + Gateway API), containerd, etcd,
cert-manager, Argo CD, Prometheus, Loki, CloudNativePG, Rook/Ceph,
metrics-server, NetworkPolicies natives couvrent l'essentiel du plan de
plateforme. **Kyverno n'est PAS déployé** (seule occurrence `kyverno.io` : une
règle RBAC de lecture de PolicyReports dans le bundle vendored Argo CD —
vérifié, aucun `kind: ClusterPolicy`/`Policy` sous `platform/` ni `storage/`).
Il ne s'agit donc pas de « rattraper » un retard CNCF, mais de combler des
**trous de conformité précis**.

### Thèse : Kyverno CLI statique en CI = le gain le moins cher et le plus défendable

La conformité maison repose sur du code impératif (`bootstrap/state.sh`,
`scripts/audit-image-digests.sh`) et sur Trivy en posture IaC statique. Deux
trous **vérifiés sur fichiers** qu'un `kyverno apply` en CI (100 % offline,
**zéro composant runtime**) fermerait :

1. **Images pinnées par tag seul échappent à tout contrôle.**
   `scripts/audit-image-digests.sh` ne matche que le motif `…:tag@sha256:…` ;
   une image en tag seul passe sous le radar (Trivy ne casse pas dessus : sa
   règle tag-pinning est LOW/MEDIUM, la CI ne rougit qu'en HIGH/CRITICAL).
   Preuves vivantes : `platform/seaweedfs/seaweedfs.yaml` (`seaweedfs:4.31`) et
   `storage/ceph/backup/snapshot-cronjob.yaml` (`bitnami/kubectl:1.34`). Ordre
   de grandeur mesuré : ~43 images digest-pinnées vs ~10 tag-only. → policy
   `require-image-digest` (validate).
2. **L'invariant d'exposition
   ([ADR 0020](../decisions/0020-exposition-reseau-tout-cilium.md)) ne tourne
   que contre un cluster vivant.** Il est codé impérativement dans
   `bootstrap/state.sh` (couche 7b, gardée par `cluster_target_ready`). Un
   `type: LoadBalancer` hors-Gateway n'est vu qu'**après** déploiement — preuve
   : `platform/mailpit/mailpit.yaml` (`mailpit-smtp`). → policy
   `restrict-service-exposure`, qui porte la règle **avant merge**. Les deux
   policies amortissent le même binaire (`lint:kyverno`).

**Réserves bloquantes à trancher dans l'ADR** (ne pas implémenter sans elles) :
ADR 0006 formule le digest comme « idéalement », pas « obligatoire » → un
`Enforce` ferait rougir la CI sur les ~10 images tag-only assumées (dont les
images maison `registry:80/…`) ; et le mécanisme d'exception de la couche 7b
(label posé par Cilium **à runtime**) est inopérant en statique → l'ADR doit
définir un autre mécanisme d'exception et lister les exceptions versionnées.
**Structurant** (nouvel outil de toolchain + garde-fou CI normatif) → **ADR
dédié exigé par 0057**.

### Tout le reste est runtime, donc séquencé derrière des ADR

Admission `verifyImages`, Tetragon (détection runtime eBPF, cohérent
tout-Cilium), OTel+Tempo (traces), Velero (DR off-site), SOPS+age (secrets
versionnés) : gains réels mais **composants/garde-fous structurants** sur un
cluster non-HA mono-admin. Chacun passe par un ADR dédié, séquencé après les
gains statiques.

### Séquencement proposé (le moins cher d'abord)

1. Épingler par digest les images maison (mineur, dans la doctrine 0006, sans
   ADR).
2. Remplir `argocd-notifications-cm` (vide) + NetworkPolicy egress (amende
   0022).
3. Finding « labels Pod Security » dans `scripts/check_gouvernance.py` — **ferme
   le gap [ADR 0014](../decisions/0014-durcissement-kubeadm-init.md) sans
   Kyverno**.
4. **Kyverno CLI statique en CI** (les 2 policies, même `lint:kyverno`) — **ADR
   dédié**.
5. Trivy image-scan + SBOM dans le rôle `platform-build-images` — **ADR dédié**.
6. Migration Promtail → Grafana Alloy (logs seuls — dette déjà actée, amende
   0016).
7. ADR Tetragon-vs-Falco (délibération, zéro déploiement).
8. SOPS+age (variante CI-time) ; puis Phase 7.2 (cosign + admission, décision
   unique) ; puis composants lourds (Tetragon déployé, OTel+Tempo, Velero) —
   chacun ADR + plan.

## Verdict du second passage — angles morts CNCF

Question de suivi : « aucun **autre** outil CNCF ne serait intéressant ? » Six
familles non couvertes par le passage 1 (autoscaling/coût, packaging/templating,
workflow/événements, résilience/multi-tenant, storage/data-mesh, dev
inner-loop), ~33 candidats. **Un seul gain net réel : Longhorn** (CNCF
incubating) — et il est **déjà instruit par le dépôt**
([ADR 0064](../decisions/0064-longhorn-option-stockage-catalogue.md) `Proposed`,
et `docs/plans/plan-stockage-longhorn.md`) : il comble le créneau « bloc
répliqué multi-nœuds simple, sans datalake » entre `local-path` et Ceph.
**Action réelle : faire passer 0064 de `Proposed` à `Accepted`, pas adopter un
outil de plus.** ADR 0064 §4 impose un profil de stockage à la fois (alternative
à Ceph, pas brique en plus).

Tout le reste est écarté avec motif vérifié — l'intérêt de la trace est de
montrer **qu'on a regardé** :

| Famille                | Écarté (extrait)                                  | Raison vérifiée                                                                                                                                                     |
| ---------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Autoscaling / coût     | Karpenter, KEDA, HPA, VPA, OpenCost               | Bare-metal à nœuds fixes ; scaling event-driven déjà natif Dagster ; FinOps écartée sciemment (ADR 0062) ; replicas←nœuds = `cluster_topology/scale.py` (ADR 0072). |
| Packaging / templating | Helm-runtime, Kustomize, Helmfile, cdk8s, CUE     | Helm **déjà adopté** en `helm template` vendored-figé ; un 2ᵉ/3ᵉ moteur fragmenterait (ADR 0049).                                                                   |
| Workflow / événements  | Argo Workflows/Events/Rollouts, Knative, NATS     | Doublon de Dagster (ADR 0026) ; pas de bus ni de serverless ; broker évité par choix (ADR 0041).                                                                    |
| Résilience / tenant    | Chaos Mesh, Litmus, kube-bench, Capsule, vCluster | Chaos déjà maison (`test/scenarios/`, ADR 0025) ; multi-tenant = **non-goal** (ADR 0010/0012, conflit 0061 critère 1).                                              |
| Storage / mesh         | MinIO, OpenEBS, Istio/Linkerd, Strimzi, KubeVirt  | S3 tranché (ADR 0036) ; mesh = Cilium (ADR 0019/0020) ; KubeVirt déjà supprimé (CHANGELOG v2.0.0).                                                                  |

## Note de gouvernance

Cette trace est une **réflexion qui alimente des ADR, pas une décision** (statut
identique à `note-runtime-admission.md`). Toute brique structurante — nouvel
outil de toolchain, garde-fou CI normatif, composant runtime — passe d'abord par
un **ADR `Accepted`**
([ADR 0057](../decisions/0057-gouvernance-documentaire-adr-plan-issue.md)), puis
un plan vivant, avant tout code. Le biais adoptif
([ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md)) **incline**
vers l'adoption d'une bonne pratique CNCF mais ne dispense jamais des trois
garde-fous : (1) ne contredire aucun ADR `Accepted` — sinon le superseder
d'abord, (2) gain net > coût de la diversité (pondéré mono-admin), (3) ADR si
structurant. Le rapport brut des deux passages (chemins absolus, sorties non
génériques) n'est pas consigné — seule la synthèse assainie l'est (ADR 0023).
