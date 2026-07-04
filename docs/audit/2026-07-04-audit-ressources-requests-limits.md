# 2026-07-04 — Audit « requests/limits de tous les pods face aux capacités de la prod dirqual »

| Champ        | Contenu                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**     | 2026-07-04                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Type**     | audit runtime de **capacité** (prod dirqual, 4 nœuds dirqual1-4, ~80 cœurs / ~251 GiB chacun), **lecture seule** — preuves = sorties `kubectl` (`get nodes`, `top nodes/pods`, `get pods -A -o json`, `describe node`) et `ceph config get`. Le croisement usage↔limite est calculé sur l'instantané du jour.                                                                                                                                                                                                              |
| **Fonde**    | _réflexion_ — alimente le plan vivant [`plan-right-sizing-ressources`](../plans/plan-right-sizing-ressources.md) et des issues. **Aucune décision ni mutation dans l'audit** (doctrine [ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md)). _NB : la correction MLflow décrite plus bas a été appliquée hors audit, ce jour — tracée dans le plan._                                                                                                                                                           |
| **Prolonge** | le [2026-06-19 — Kubescape](2026-06-19-kubescape-nsa.md) (« vraie dette = resource limits, à corriger dans le **code** ») et le [2026-06-24 — prod dirqual](2026-06-24-audit-prod-dirqual.md) (qui listait déjà OOMKill Grafana/mgr Ceph + Prometheus). Il **ne les réécrit pas** : il les **quantifie** (usage réel vs limite, par pod) et ajoute la **loi d'élasticité mémoire de Ceph**.                                                                                                                                |
| **Verdict**  | **Capacité non contrainte** : usage **4 % RAM / 1 % CPU**, requests 11 % RAM, limits 21 % RAM (sur 320 cœurs / ~983 GiB allouables). Le sujet n'est pas la capacité mais le **right-sizing** : **2 charges en OOM** (Prometheus à 97 %, Grafana à 130 % de leur limite), **1 corrigée ce jour** (MLflow 768Mi→1,5 GiB), **1 préventive** (Marquez). Et **Ceph est élastique** : `osd_memory_target = 4 GiB` **fixe = la limite** → « plus on donne, plus il prend » ; l'usage bas actuel n'est que le datalake quasi vide. |

## Pourquoi ce passage

La dette « resource limits » est **identifiée depuis le
[2026-06-19](2026-06-19-kubescape-nsa.md)** mais jamais **chiffrée** : combien
de charges concernées, lesquelles OOM réellement, et quelle marge le cluster a
devant lui. Ce passage la mesure **avant** que la chaîne de traitement
applicative ne démarre — car elle va **peupler le datalake** (donc faire grossir
Ceph) et **charger MLflow / Marquez** (modèles, artefacts, lineage), ce qui
déplace les points de tension.

Traits structurants rappelés (repris du 2026-06-24, non réécrits) :

- **dirqual est une production réelle**, mono-mainteneur, dont les compromis
  sont tenus et tracés en ADR. Comme
  [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md), ce **passage daté
  garde les relevés réels** — l'honnêteté des mesures prime, exemption assumée à
  la génération générique
  ([ADR 0023](../decisions/0023-plateforme-exemple-generique.md)).
- **Corriger le code, pas l'état**
  ([ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md)) : chaque
  suggestion repart dans le **manifeste / values versionné**, jamais en patch
  manuel durable. Ce passage constate ; le
  [plan](../plans/plan-right-sizing-ressources.md) met en œuvre.

## Méthode

Instantané en lecture seule sur le contexte `kubernetes-admin@cluster-prod` :
`kubectl get nodes` (allocatable) ; `kubectl top nodes` / `top pods -A`
(metrics-server, usage réel) ; `kubectl get pods -A -o json` (requests/limits
par **conteneur**) ; `kubectl describe node` (somme allouée par nœud) ;
`ceph config get osd osd_memory_target`. Le croisement **usage réel ↔ limite**
est calculé par pod (agrégation des conteneurs).

## Capacité & agrégats — aucune pression

| Métrique | Requests       | Limits         | Usage réel   |
| -------- | -------------- | -------------- | ------------ |
| **CPU**  | 13,4 c (4 %)   | 103,7 c (32 %) | 4,2 c (1 %)  |
| **RAM**  | 104 GiB (11 %) | 208 GiB (21 %) | 41 GiB (4 %) |

- Dénominateur : **4 × dirqual (80 c / ~251 GiB) = 320 cœurs / ~983 GiB**
  allouables.
- Par nœud : requests 4–5 % CPU / ~10 % RAM ; limits 31–35 % CPU / 20–22 % RAM.
  **Aucune sur-réservation, aucun overcommit mémoire.**
- **247 conteneurs** actifs, dont **178 dans `rook-ceph`** (72 %) : Ceph
  concentre ~95 % des requests/limits mémoire (voir plus bas).
- ~**800 GiB et 300+ cœurs libres** : la chaîne de traitement à venir (pods de
  run Dagster transitoires, modèles, rapports Evidently) tient **trivialement**.

## Right-sizing — à corriger (le vrai sujet)

Une limite trop serrée **OOM même sur un nœud presque vide** : le plafond est
**par-conteneur**, pas cluster-global.

- **Prometheus — _majeur_** : usage **989Mi / limite 1024Mi (97 %)**. La série
  grossit avec chaque cible ajoutée ; au démarrage de la chaîne (pods de run,
  nouvelles cibles) il dépassera 1 GiB et sera OOM-killé → **cécité du
  monitoring** au pire moment. → limite **3 GiB** (values
  `kube-prometheus-stack`).
- **Grafana — _mineur_** : usage **332Mi / limite 256Mi (130 %)** du conteneur
  principal → redémarrages récurrents sous charge. → limite **512 MiB** (values
  `grafana`). _(déjà pointé le 2026-06-24.)_
- **MLflow — _corrigé ce jour_** : 768Mi OOM-killé (exit 137) sur une simple
  opération de maintenance (un 2ᵉ process `mlflow` important pandas/boto3
  par-dessus le serveur). Relevé à **1,5 GiB / request 512 MiB**, en **code**
  (`platform/mlflow/mlflow.yaml`) + appliqué en prod (patch chirurgical, env S3
  préservé). À committer via le
  [plan](../plans/plan-right-sizing-ressources.md).
- **Marquez — _mineur (préventif)_** : limite **768Mi**. N'a **pas** OOM sur la
  mémoire — ses redémarrages venaient de l'incident **PG plein** (Flyway ne
  pouvait plus migrer), résolu depuis. Mais 768Mi est serré pour une JVM
  Dropwizard, et **0 événement de lineage** n'a encore été reçu (0 run
  applicatif) : marge à poser avant l'afflux. → **1,5 GiB**.
- **Mailpit — _info_** : 98Mi / 128Mi (77 %). Capteur de mail de dev, faible
  enjeu ; 256Mi si un jour ça coince.

## Ceph — élastique par conception (« plus on donne, plus il prend »)

- ~48 OSD × **2 GiB request / 4 GiB limit**, avec
  **`osd_memory_target = 4 GiB`** (fixe, `osd_memory_target_autotune = false`) :
  chaque OSD est **instruit de remplir son cache BlueStore jusqu'à 4 GiB**.
- L'usage bas actuel (**0,4–1,0 GiB/OSD**, 7–25 % du request) **n'est pas de
  l'efficience** : c'est le **datalake quasi vide** (~29 GiB `STORED`), donc peu
  de données chaudes à cacher. Il **montera vers 4 GiB/OSD** quand les pipelines
  rempliront le lac.
- Conséquence pratique : **relever la limite des OSD ne « libère » rien** — le
  target suit la limite, Ceph agrandit d'autant son cache. Le plafond mémoire de
  Ceph est donc **délibéré** : 48 × 4 = **~192 GiB** de cache max (~20 % du
  cluster), ce qui est sain. Le **seul levier** pour _borner_ la RAM Ceph est de
  **baisser `osd_memory_target`** (on échange du cache hit-rate contre de la
  RAM) — **surtout pas** de sur-provisionner en espérant des gains.

## Conteneurs sans limite mémoire — nuance

**164 / 247** conteneurs (66 %) n'ont pas de limite mémoire, mais le chiffre se
lit avec nuance :

- **Attendu / infra** : sans limite **par défaut upstream** — static pods
  (`kube-apiserver` 2,4 GiB, `etcd`, scheduler, controller-manager), daemonset
  `cilium`, contrôleurs `argocd` / `argo` / `cert-manager` / `argo-events`.
  Rayon de souffle contenu par les 251 GiB/nœud.
- **Faux positifs / sidecars** : beaucoup de pods « app » signalés le sont via
  un **sidecar** non borné (config-reloader de Prometheus, `sc-*` de Grafana,
  log-collector des OSD) ; le conteneur **principal**, lui, a bien sa limite.
- La couche applicative (`dagster`, `mlflow`, `marquez`, `gitea`, `registry`,
  `portal`) **porte** ses limites mémoire.
- Hygiène optionnelle : plafonner `argocd-application-controller` (668Mi non
  borné).

## Suggestions (→ [plan](../plans/plan-right-sizing-ressources.md) + issues)

- **Monitoring** — Prometheus limite → 3 GiB (_majeur_) ; Grafana → 512 MiB
  (_mineur_).
- **Dataops** — MLflow → 1,5 GiB (_fait ce jour_, à committer) ; Marquez → 1,5
  GiB préventif (_mineur_).
- **Stockage** — Ceph : **ne pas** relever les limites OSD sans intention
  (élastique) ; borner via `osd_memory_target` si un jour la RAM manque
  (_info_).
- **Hygiène** — poser une limite mémoire sur `argocd-application-controller`
  (_info_).

> Bilan : **capacité saine et large**, dette réelle = **quelques limites
> sous-dimensionnées** (Prometheus/Grafana en tête) et **une propriété
> d'élasticité Ceph** à garder en tête pour ne pas sur-provisionner. **0
> critique.**
