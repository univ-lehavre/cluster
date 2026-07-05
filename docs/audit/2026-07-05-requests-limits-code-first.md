# Passage d'audit — requests/limits, volet **code-first** (ce que le dépôt déclare)

> **Type** : passage d'audit ciblé, issu d'un **workflow multi-agents**
> ([ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md) /
> [0078](../decisions/0078-passages-audit-famille-unique.md)) — 20 analyseurs en
> éventail (un par composant plateforme/stockage) + synthèse. Pas la grille /5.
>
> **Date** : 2026-07-05.
>
> **Déclencheur** : après l'incident inotify (dirqual1 gelé,
> [passage sœur](2026-07-05-incident-inotify-et-risques-ha-a-chaud.md) §2), la
> question opérateur « **les requests/limits sont-elles TOUTES posées ?** ».
>
> **Angle** : **code-first** — pour chaque workload porteur, `requests`/`limits`
> × `cpu`/`mem` sont-ils **déclarés dans un fichier du dépôt** ? Vérité
> **corrigeable**
> ([ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md)). **Complète** —
> ne réécrit pas — le
> [2026-07-04 (runtime/capacité)](2026-07-04-audit-ressources-requests-limits.md)
> : celui-là mesure la conso réelle vs limite (`kubectl top`), celui-ci
> cartographie **où le code pose ou omet** la déclaration. Les deux **alimentent
> le même** [plan right-sizing](../plans/plan-right-sizing-ressources.md).
>
> **Réserve** : les numéros de ligne dans les **bundles vendored** (argocd,
> cert-manager) proviennent des analyseurs sur des fichiers volumineux figés ;
> l'**absence** de resources y est le fait établi, la ligne exacte est
> indicative. La QoS **observée** (éviction déjà survenue, conso vs plafond)
> reste à croiser via `kubectl` **dès accès VPN** — cet audit ne voit que le
> code.

## Réponse franche

**Non.** Sur ~40 workloads _porteurs_ (long-vécus, hors Jobs courts / objets
non-pod), **~45 % n'ont aucune limite mémoire codée** et **~40 % tournent en
BestEffort** (ni requests ni limits). Mais la répartition importe plus que le
chiffre : **tout le pied applicatif « maison »** (gitea, registry, portal,
mailpit, mlflow, marquez, dagster-socle, loki, seaweedfs, monitoring-socle) est
**correctement borné en mémoire** — le vrai risque OOM y est couvert. Les trous
sont concentrés sur (1) les **socles vendored** non édités (Argo CD,
cert-manager) et (2) le stateful applicatif le plus lourd, **`pg-1/2/3`
(CNPG)**, sans aucun `spec.resources`.

## Matrice de couverture (agrégée par composant)

Légende : ✅ posé · ⚠️ via défaut chart (non versionné) · ❌ absent · 🟡 mixte
(socle posé, un sous-workload nu). Les `limits.cpu` absentes sont un **choix**
(CPU compressible → throttling, jamais OOM) et ne comptent pas comme un trou.

| Composant                 | req.cpu | req.mem | lim.cpu | lim.mem | Verdict                                                               |
| ------------------------- | :-----: | :-----: | :-----: | :-----: | --------------------------------------------------------------------- |
| **gitea**                 |   ✅    |   ✅    |   ✅    |   ✅    | Complet, 0 gap                                                        |
| **container-registry**    |   ✅    |   ✅    |   ✅    |   ✅    | Complet, 0 gap                                                        |
| **seaweedfs** (banc)      |   ✅    |   ✅    |   ❌    |   ✅    | OOM couvert                                                           |
| **mailpit**               |   ✅    |   ✅    |   ❌    |   ✅    | OOM couvert                                                           |
| **portal**                |   ✅    |   ✅    |   ❌    |   ✅    | OOM couvert                                                           |
| **mlflow**                |   ✅    |   ✅    |   ❌    |   ✅    | OOM couvert (relevé 768→1536Mi le 04-07)                              |
| **marquez**               |   ✅    |   ✅    |   ❌    |   ✅    | OOM couvert (relevé 768→1536Mi le 04-07)                              |
| **metrics-server**        |   ✅    |   ✅    |   ❌    |   ❌    | Sans lim mém — **assumé** (system-critical)                           |
| **dagster** (socle)       |   ✅    |   ✅    |   ❌    |   ✅    | Socle OK ; **Jobs de run ❌ tout** (frontière atlas)                  |
| **loki**                  |   ✅    |   ✅    |   ❌    |   ✅    | Socle OK ; sidecar `loki-sc-rules` ❌ tout                            |
| **kube-prometheus-stack** |   ✅    |   ✅    |   ❌    |   🟡    | Socle OK mais **DRIFT** (values 3Gi vs manifeste rendu) + sidecars ❌ |
| **k8s-dashboard**         |   🟡    |   🟡    |   🟡    |   🟡    | api/web/scraper ✅ · auth ⚠️ · **Kong ❌ tout**                       |
| **cloudnative-pg**        |   🟡    |   🟡    |   🟡    |   🟡    | operator ✅ · **pg-1/2/3 ❌ tout** · plugin barman ❌                 |
| **ceph / rook**           |   🟡    |   🟡    |   🟡    |   🟡    | mon/mgr/osd ✅ · **RGW ❌** · CSI ❌ · toolbox ❌                     |
| **argo-events**           |   ❌    |   ❌    |   ❌    |   ❌    | **Tout BestEffort** (EventBus NATS notamment)                         |
| **argo-workflows**        |   ❌    |   ❌    |   ❌    |   ❌    | **Tout BestEffort** (BuildKit, controller)                            |
| **argocd**                |   ❌    |   ❌    |   ❌    |   ❌    | **7/7 BestEffort** (vendored non édité)                               |
| **cert-manager**          |   ❌    |   ❌    |   ❌    |   ❌    | **3/3 BestEffort** (vendored non édité)                               |
| **local-path** (banc)     |   ❌    |   ❌    |   ❌    |   ❌    | BestEffort (profil banc léger)                                        |

## Trous critiques (par gravité réelle sur `dirqual`)

1. **`pg-1/2/3` (CNPG) — aucun `spec.resources`** —
   [`platform/cloudnative-pg/cluster.yaml`](../../platform/cloudnative-pg/cluster.yaml)
   (0 occurrence `resources`/`cpu`/`memory` dans le CR ; le rôle `platform-cnpg`
   ne surcharge que `spec.storage.storageClass`). **Stateful applicatif le plus
   lourd**, HA 3 instances, sans plafond mémoire. Manque connu du passage
   inotify. Ce cluster a **déjà** été dégradé par un incident WAL-archive/disque
   (NP RGW manquant, PR #568). Sans `limits.memory` un pic (grosse requête,
   backlog WAL, réplication) peut OOM le primary ; sans `requests` le scheduler
   co-localise mal les 3 instances. **Priorité absolue.**

2. **Argo CD `application-controller` + `repo-server`** —
   [`platform/argocd/argocd.yaml`](../../platform/argocd/argocd.yaml), bundle
   v3.4.3 vendored non édité (7/7 workloads nus). Le controller garde en mémoire
   l'état de **toutes** les Applications ; le repo-server pique à chaque
   `helm template`/sync. En BestEffort, premiers évincés sous pression → **perte
   de réconciliation GitOps de tout le cluster**.

3. **cert-manager `cainjector` + `controller`** —
   [`platform/cert-manager/cert-manager.yaml`](../../platform/cert-manager/cert-manager.yaml),
   vendored v1.20.2 nu. Le cainjector cache des objets cluster-wide (conso
   croissante). Socle TLS interne (prérequis Barman/CNPG) : sa chute casse
   l'émission de certificats.

4. **RGW Ceph `CephObjectStore` (S3)** —
   [`storage/ceph/storageClass/datalake/datalake-ec.yaml`](../../storage/ceph/storageClass/datalake/datalake-ec.yaml),
   `gateway.resources` non posé, Rook n'applique aucun défaut. **Chemin S3 des
   backups Barman/CNPG et de Loki** ; sous charge multipart/gros objets un RGW
   gonfle → OOM-kill.

5. **EventBus NATS (argo-events)** —
   [`platform/argo-events/eventbus-nats.yaml`](../../platform/argo-events/eventbus-nats.yaml),
   sans `containerTemplate.resources`, JetStream `max_memory_store: -1` (jusqu'à
   ~75 % RAM nœud). Bus avec état, `replicas: 1` (SPOF), mémoire non bornée →
   OOM = event push perdu.

6. **BuildKit rootless (image-builder)** —
   [`platform/argo-workflows/workflowtemplate-builder.yaml`](../../platform/argo-workflows/workflowtemplate-builder.yaml).
   Workload le plus gourmand (build image in-pod), empreinte RAM imprévisible
   selon le Dockerfile atlas, sur un worker sans plafond. Le template invoque un
   « audit ~90 % RAM libre » mais **aucune limite n'est codée**.

7. **Kong (k8s-dashboard)** — subchart Kong 2.38.0, `resources: {}` non overridé
   dans
   [`platform/k8s-dashboard/values.yaml`](../../platform/k8s-dashboard/values.yaml).
   Pod du **chemin critique** : le NodePort route toute l'UI vers lui et il
   termine le TLS ; s'il OOM, l'UI entière tombe (api/web/scraper bornés
   survivent). Correctif propre = bloc `kong.resources` (paramétrage chart,
   **pas** édition de bundle).

8. **`redcap-mariadb`** —
   [`apps/redcap/mariadb.yaml`](../../apps/redcap/mariadb.yaml), BestEffort
   alors que le frontend REDCap est borné. Base stateful de l'app : la perdre =
   perdre REDCap.

9. **Jobs de run K8sRunLauncher (Dagster)** —
   [`platform/dagster/dagster.yaml`](../../platform/dagster/dagster.yaml), aucun
   défaut côté cluster. Ce sont les workloads qui font le vrai travail
   (ingestion OpenAlex, dbt). Responsabilité déléguée à atlas
   ([ADR 0022](../decisions/0022-argocd-gitops-applicatif.md)), mais **rien côté
   cluster ne garantit un plancher** (pas de `LimitRange` dans le ns `dagster`).

## Nuance honnête — vrai danger vs cosmétique

- **Ce n'est pas un incendie.** L'audit runtime du 07-04 mesure des nœuds à **~4
  % de charge** : un Argo CD ou cert-manager BestEffort ne se fait _pas_ évincer
  aujourd'hui — le risque n'existe qu'en **pression mémoire**. C'est un
  **durcissement de robustesse**, pas une urgence — _sauf_ `pg-1/2/3` qui cumule
  (lourd + historique d'incident).
- **Mais le risque est réel, pas théorique** : `mlflow` a été **OOM-killé le
  2026-07-04** (exit 137) — un plafond absent/serré a déjà mordu sur _ce_
  cluster (4 corrections posées ce jour-là, dont mlflow/marquez 768→1536Mi).
- **Le « DRIFT » kube-prometheus-stack est un plafond décidé, pas une absence**
  :
  [`values.bench.yaml`](../../platform/kube-prometheus-stack/values.bench.yaml)
  relève Prometheus 1Gi→3Gi et Grafana 256Mi→512Mi, mais le manifeste **rendu**
  appliqué porte encore les anciennes valeurs (Ansible charge le manifeste tel
  quel, sans re-render Helm). Fix **mécanique** (régénérer), pas nouveau code.
- **À NE PAS « corriger »** (choix documentés) : toutes les `limits.cpu`
  absentes (CPU compressible) ; `metrics-server` sans limits (system-critical,
  [`README.md`](../../platform/metrics-server/README.md)) ; exemples wordpress ;
  `local-path` banc léger.

## Recommandation priorisée — alimente le plan right-sizing

Ces manques ne créent **pas** de nouveau plan ni d'ADR : ils enrichissent le
[plan right-sizing](../plans/plan-right-sizing-ressources.md) existant (réglage,
pas décision structurante). Ordre :

1. **`pg-1/2/3` CNPG** — poser `spec.resources` (`requests` **et**
   `limits.memory`) dans `cluster.yaml`, **dérivé par topologie** (bench vs
   prod) comme `storageClass` l'est déjà. **#1 incontestable.**
2. **cert-manager + Argo CD** — socles GitOps/TLS ; au moins `requests.*` +
   `limits.memory`. Pour les bundles vendored : **patch hors-bundle**
   (kustomize/overlay), pas édition du fichier figé (parité upstream,
   [ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
3. **RGW Ceph** (`gateway.resources`) + **EventBus NATS**
   (`containerTemplate.resources`) — chemins données/événements non bornés.
4. **Kong** (`kong.resources` dans les values) + **`redcap-mariadb`**.
5. **Régénérer** `kube-prometheus-stack.yaml` depuis `values.bench.yaml`
   (matérialiser les plafonds déjà décidés).

**À laisser** : `limits.cpu` absentes, metrics-server, exemples wordpress,
local-path banc — documenter ces omissions comme intentionnelles plutôt que les
« corriger ».

**Manques → suivi** : les items 1-5 ci-dessus deviennent des paliers du plan
right-sizing (ADR 0058 : les manques d'un passage deviennent du travail tracé).
La QoS **observée** reste à croiser via `kubectl` dès accès VPN.
