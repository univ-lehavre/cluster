# 2026-06-24 — Audit « vérification poussée non destructive de la prod dirqual »

| Champ       | Contenu                                                                                                                                                                                                                                                                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**    | 2026-06-24                                                                                                                                                                                                                                                                                                                               |
| **Type**    | audit runtime de prod (cluster dirqual, 4 nœuds dirqual1-4 / `10.67.2.11-14`, k8s v1.34.8), **lecture seule** — aucune mutation. Preuves = sorties `kubectl`/`ceph`/`radosgw-admin` observées en live.                                                                                                                                   |
| **Fonde**   | _réflexion_ — alimente des **issues** GitHub et de futurs ADR/plans. **Aucune décision ni mutation ici** (doctrine audit [ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md)).                                                                                                                                               |
| **Verdict** | Prod **saine et fonctionnelle** : contrat cluster→atlas tenu (18/18 endpoints montés répondent au bon port), Ceph `HEALTH_OK`, 0 pod en échec. Mais **8 risques majeurs** dont un **SPOF total du control-plane** (1 nœud, 1 etcd) et **1 drift code↔prod** (base `cache`/rôle `pg-role-cache` de l'ADR 0093 non appliqués). 0 critique. |

## Pourquoi ce passage

dirqual est une **production réelle** — pas un banc — mais elle porte les traits
structurants du dépôt :

- **Mono-mainteneur assumé** : les compromis de sécurité/résilience sont des
  choix tenus, pas des oublis, tracés en ADR (exposition L4 NodePort
  [ADR 0092](../decisions/0092-exposition-hostport-l4.md), preuves applicatives
  sur local-path
  [ADR 0085](../decisions/0085-preuves-applicatives-local-path.md),
  code-location jouet
  [ADR 0086](../decisions/0086-code-location-jouet-du-socle.md)).
- **dirqual EST la référence Ceph** : le banc Ceph complet est abandonné (Mac
  sans ressources), donc toute observation Ceph (santé, durabilité, placement)
  se prouve ici et nulle part ailleurs.
- **Corriger le code, pas l'état**
  ([ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md)) : chaque
  suggestion repart dans le manifeste/rôle/values versionné puis se re-prouve
  par un run. Ce passage ne mute rien : il constate et alimente le plan
  d'action.

Méthode : **6 dimensions** auditées (contrat cluster→atlas, sécurité,
résilience/HA, gitops/dérive, données/backups, observabilité), chaque finding
**vérifié adversarialement** sur le cluster réel. Bilan : **45 bruts → 31
confirmés** (8 majeurs, 12 mineurs, 11 info), **0 critique**, **14 faux-positifs
écartés**. Toute preuve ci-dessous est une sortie observée en lecture seule sur
dirqual au 2026-06-24.

## Majeurs (8)

### M1 — Drift code↔prod : base CNPG `cache` et rôle `pg-role-cache` (ADR 0093) absents

- **Dimension** : contrat cluster→atlas (base de données / secrets).
- **Problème** : le contrat ([ADR 0093](../decisions/0093-cache-flux-cnpg.md))
  déclare une base logique `cache` sur le `Cluster` CNPG `pg` (backing du cache
  partagé des flux atlas) et un `Secret pg-role-cache`. Les **deux objets sont
  bien déclarés dans les manifestes versionnés**
  (`platform/cloudnative-pg/database.yaml:70` Database `cache` owner `cache` ;
  `cluster.yaml:75-79` rôle `cache` + `secretRef` `pg-role-cache`) — mais ils ne
  sont **pas appliqués sur dirqual**. C'est un **déploiement manquant**, pas un
  défaut de contrat. Conséquence : un consommateur atlas qui suit le contrat
  pour le cache (DSN `POSTGRES_CACHE_*`) échouera à se connecter — la base et le
  rôle n'existent pas. L'endpoint `postgres-cache` pointe sur le `Service pg-rw`
  (présent et répondant) ; c'est la base logique et le rôle qui manquent, pas le
  Service.
- **Evidence** :

  ```text
  kubectl -n postgres get database cache
    → Error from server (NotFound): databases.postgresql.cnpg.io "cache" not found
  kubectl -n postgres get secret pg-role-cache
    → NotFound
  kubectl get database -A
    → dagster, marquez, mlflow, pgvector  (AUCUN cache)
  kubectl -n postgres get cluster pg -o jsonpath='{.spec.managed.roles[*].name}'
    → dagster pgvector marquez mlflow  (pas de cache, alors que cluster.yaml:75 le déclare)
  ```

- **Suggestion** : appliquer la déclaration versionnée sur dirqual sans toucher
  l'état à la main (ADR 0046) — poser le `Secret pg-role-cache` depuis la config
  `role-secrets` locale non versionnée, puis laisser CNPG réconcilier le rôle
  `cache` (`cluster.yaml`) et la `Database cache` (`database.yaml`). Re-prouver
  par `kubectl -n postgres get database cache` (APPLIED true) +
  `get secret pg-role-cache`.

### M2 — SA Grafana lit tous les Secrets du cluster (ClusterRole cluster-wide)

- **Dimension** : sécurité (RBAC).
- **Problème** : le SA `monitoring/kube-prometheus-stack-grafana` est lié à un
  `ClusterRole` dont l'unique règle est `get/watch/list` sur `configmaps` **et**
  `secrets`, **sans restriction de namespace**. Il peut donc lire les
  credentials PostgreSQL (`postgres/pg-role-*`), le secret admin ArgoCD, les
  keyrings `rook-ceph-admin`, les creds S3 (mlflow/loki). C'est le comportement
  par défaut des sidecars `grafana-sc-dashboard`/`datasources`, mais l'octroi
  cluster-wide sur les `secrets` dépasse le besoin réel (la découverte de
  dashboards/datasources n'a besoin que des ConfigMaps). Un RCE/SSRF dans
  Grafana (exposée en NodePort 31450) exposerait **tous les secrets du
  cluster**. Aucun autre SA applicatif n'a ce droit
  (dagster/marquez/mlflow/gitea/registry/portal : `secrets:get=no`).
- **Evidence** :

  ```text
  kubectl get clusterrole kube-prometheus-stack-grafana-clusterrole -o jsonpath='{.rules}'
    → [{"apiGroups":[""],"resources":["configmaps","secrets"],"verbs":["get","watch","list"]}]
  kubectl auth can-i get secrets --all-namespaces \
    --as=system:serviceaccount:monitoring:kube-prometheus-stack-grafana → yes
  (idem -n postgres → yes ; -n argocd → yes)
  ```

- **Suggestion** : restreindre la découverte des sidecars Grafana aux
  **ConfigMaps uniquement**, ou remplacer le `ClusterRole` par des `Role`
  namespacés limités aux ConfigMaps. Si la lecture de Secrets reste nécessaire,
  la cibler par label/ressource nommée, jamais cluster-wide. Correction dans les
  values du chart, puis re-prouver.

### M3 — Namespace `postgres` sans aucune NetworkPolicy : `pg-rw:5432` joignable depuis tout le cluster

- **Dimension** : sécurité (NetworkPolicy).
- **Problème** : les namespaces
  argocd/dagster/marquez/mlflow/gitea/portal/registry ont chacun une
  `default-deny-all` + egress ciblés. Le namespace `postgres` (cluster CNPG
  `pg-1/2/3`, services `pg-rw`/`pg-ro`/`pg-r` sur 5432) n'a **aucune
  NetworkPolicy** (ni `NetworkPolicy` k8s, ni `CiliumNetworkPolicy`). Toute
  charge compromise dans n'importe quel namespace peut donc atteindre
  directement PostgreSQL sur 5432 (données dagster/marquez/mlflow/pgvector). Les
  consommateurs ont bien un `allow-postgres-egress` sortant, mais rien ne
  protège l'**entrée** côté postgres. Absence aussi sur `monitoring` et
  `cnpg-system` (moins critique).
- **Evidence** :

  ```text
  kubectl get netpol -n postgres        → No resources found
  kubectl get cnp -A ; kubectl get ccnp → No resources found
  kubectl get svc -n postgres           → pg-rw/pg-ro/pg-r ClusterIP :5432
  kubectl get netpol -A → default-deny-all présent sur argocd/dagster/marquez/
    mlflow/gitea/portal/registry, ABSENT pour postgres/monitoring/cnpg-system
  ```

- **Suggestion** : ajouter au manifeste du namespace `postgres` une
  `NetworkPolicy default-deny-ingress` + `allow-ingress` ciblée sur 5432 depuis
  les seuls consommateurs (`namespaceSelector` dagster/marquez/mlflow + pods
  CNPG). Re-prouver par run (ADR 0046).

### M4 — Control-plane mono-nœud : SPOF total (1 control-plane, 1 etcd)

- **Dimension** : résilience (HA control-plane).
- **Problème** : sur 4 nœuds, **un seul est control-plane (dirqual1)**. Tous les
  composants du plan de contrôle (etcd, kube-apiserver, kube-controller-manager,
  kube-scheduler) tournent uniquement sur dirqual1, et etcd n'a **qu'un seul
  membre**. Il n'y a donc aucun quorum redondant : la perte ou le reboot de
  dirqual1 fait perdre l'API Kubernetes **et** la base etcd en même temps.
  `/readyz?verbose` passe actuellement (etcd ok), mais cela ne reflète qu'une
  absence de panne, pas une tolérance à la panne. C'est le SPOF le plus grave du
  cluster : tout le pilotage repose sur une seule machine. C'est une **dette
  structurante**, pas un correctif de conf.
- **Evidence** :

  ```text
  kubectl get nodes -l node-role.kubernetes.io/control-plane -o wide
    → dirqual1 (10.67.2.11) SEUL ; dirqual2/3/4 = <none>
  kubectl -n kube-system get pods -l tier=control-plane -o wide
    → etcd-dirqual1, kube-apiserver-dirqual1, kube-controller-manager-dirqual1,
      kube-scheduler-dirqual1  (tous sur dirqual1) ; etcd = 1 daemon
  ```

- **Suggestion** : passer à **3 nœuds control-plane** (stacked etcd à 3 membres)
  pour un quorum tolérant à 1 panne. À défaut d'HA complète immédiate :
  **documenter explicitement** ce SPOF assumé (ADR) et la procédure de
  restauration etcd (snapshot régulier + test de restore). Décision structurante
  → ADR/plan, à instruire au rebuild (~sept. 2026).

### M5 — Les deux répliques CoreDNS sur le même nœud (dirqual1)

- **Dimension** : résilience (répartition / DNS).
- **Problème** : le déploiement CoreDNS a 2 répliques avec une anti-affinité
  `preferred` (soft), mais les **deux pods sont sur dirqual1** — qui est aussi
  le control-plane SPOF (M4). La résolution DNS interne repose donc entièrement
  sur dirqual1 : sa perte coupe le DNS de tous les pods jusqu'au reschedule, en
  plus de couper l'API. L'anti-affinité `preferred` n'a pas suffi (le scheduler
  peut l'ignorer s'il juge la co-location plus pratique). Combiné à M4, c'est un
  **double point de défaillance sur dirqual1**.
- **Evidence** :

  ```text
  kubectl -n kube-system get deploy coredns -o yaml
    → replicas=2 ; podAntiAffinity preferredDuringScheduling weight=100
      topologyKey=kubernetes.io/hostname  (soft)
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide
    → coredns-…-dngzn et coredns-…-x2j26  (tous deux NODE=dirqual1)
  ```

- **Suggestion** : passer l'anti-affinité CoreDNS en `required`
  (requiredDuringScheduling) ou ajouter une `topologySpreadConstraint` hard sur
  `kubernetes.io/hostname`. Faible coût, fort impact.

### M6 — Backups CNPG jamais testés en restauration

- **Dimension** : données/backups (backup-restore).
- **Problème** : les 13 backups sont `completed` et l'archivage WAL continu
  fonctionne (`ContinuousArchivingSuccess=True`), mais **rien n'atteste qu'une
  restauration ait jamais été exercée** sur cette plateforme. Un backup non
  restauré est un backup hypothétique : format S3, droits du user OBC, chemin
  `destinationPath`, intégrité WAL ne se valident qu'en restaurant réellement.
  `status.firstRecoverabilityPoint` au niveau `Cluster` reste `None` (la fenêtre
  n'est exposée que côté `ObjectStore.status.serverRecoveryWindow`).
- **Evidence** :

  ```text
  kubectl -n postgres get backup → 13/13 phase=completed, 0 failed (plugin barman)
  kubectl -n postgres get cluster pg -o jsonpath='{.status.conditions}'
    → Ready=True, ContinuousArchiving=True, LastBackupSucceeded=True
  (aucun Cluster de recovery ni test PITR observé)
  ```

- **Suggestion** : c'est une **procédure** à coder, pas une mutation de dirqual.
  Planifier un test de restauration **hors-prod** : créer un `Cluster` CNPG de
  recovery (`bootstrap.recovery` depuis l'ObjectStore `pg-backup`) dans un
  namespace/cluster isolé, vérifier un PITR à un timestamp. À automatiser et
  documenter (RUNBOOK). Geste de création → **pas** sur dirqual en lecture
  seule.

### M7 — Alertmanager ne délivre aucune notification (smarthost `mailpit.mail` introuvable)

- **Dimension** : observabilité (alerting).
- **Problème** : la config Alertmanager
  (`secret alertmanager-kube-prometheus-stack-alertmanager`) pointe
  `smtp_smarthost: mailpit.mail.svc.cluster.local:1025`, mais le namespace
  `mail` **n'existe pas** et aucun service `mailpit` n'est déployé. Conséquence
  : **toutes** les notifications échouent (y compris le Watchdog) — le pipeline
  d'alerting est aveugle, même une alerte critique réelle ne partirait pas. Les
  alertes `AlertmanagerFailedToSendAlerts` (warning) et
  `AlertmanagerClusterFailedToSendAlerts` (critical) constatent ce fait de
  l'intérieur.
- **Evidence** :

  ```text
  secret alertmanager.yaml → smtp_smarthost: mailpit.mail.svc.cluster.local:1025
  kubectl get ns mail → Error from server (NotFound)
  kubectl get svc -A | grep mailpit → (vide)
  logs alertmanager-…-0 -c alertmanager
    → notify retry canceled after 16 attempts: dial tcp:
      lookup mailpit.mail.svc.cluster.local on 10.96.0.10:53: no such host
  ```

- **Suggestion** : aligner le **code** (values du chart kube-prometheus-stack)
  puis re-prouver — soit déployer un service `mailpit` dans un namespace `mail`
  (récepteur SMTP de test, esprit example-org), soit corriger `smtp_smarthost`
  vers un relais existant, soit configurer un receiver `null`/no-op **assumé**.
  Sans cela l'observabilité n'alerte personne.

### M8 — Cibles control-plane DOWN dans Prometheus → alertes critiques en faux positif

- **Dimension** : observabilité (scrape).
- **Problème** : 3 targets Prometheus sont down sur dirqual1 — `kube-etcd`
  (`10.67.2.11:2381`), `kube-scheduler` (10259), `kube-controller-manager`
  (10257), toutes en `connection refused`. Les pods sont pourtant `1/1 Running`
  et sains : les composants control-plane bindent leurs métriques sur
  `127.0.0.1`, pas sur l'IP du nœud (mauvaise config de scrape classique de
  kube-prometheus-stack). Conséquence : `etcdInsufficientMembers` (critical),
  `etcdMembersDown` (warning), `KubeSchedulerInstanceUnreachable`,
  `KubeControllerManagerInstanceUnreachable`, `TargetDown` ×3 — **toutes
  fausses**. Sur un control-plane mono-nœud,
  `etcdInsufficientMembers/MembersDown` sont en plus structurellement
  trompeuses. Ce bruit d'alerte masquerait un vrai incident.
- **Evidence** :

  ```text
  /api/v1/targets → kube-etcd / kube-scheduler / kube-controller-manager :
    health=down, "connect: connection refused"
  up{job="kube-etcd"}=0  alors que etcd-dirqual1 est 1/1 Running
  logs etcd → "rejected connection on client endpoint remote-addr 127.0.0.1 … EOF"
    (toutes les 30 s = la sonde Prometheus qui tape le mauvais port/TLS)
  ```

- **Suggestion** : décision structurante (topo mono-CP) → probablement un ADR.
  Soit exposer les métriques control-plane sur l'IP du nœud
  (`--listen-metrics-urls`/`--metrics-bind-address=0.0.0.0`) et corriger les
  ports de scrape ; soit désactiver
  `kubeEtcd`/`kubeScheduler`/`kubeControllerManager.enabled` (et leurs règles)
  dans les values pour un control-plane mono-nœud. Corriger le code, pas l'état.

## Mineurs (12)

| #   | Titre                                                                | Dimension               | Problème (résumé)                                                                                                                                                                                      | Evidence (clé)                                                                                                              | Suggestion                                                                                                             |
| --- | -------------------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| m1  | Secret dérivé `pgvector-pg-auth` (ns dagster) absent                 | contrat / secrets       | Le contrat prévoit la recopie du rôle CNPG `pgvector` en ns dagster (`derived_from pg-role-pgvector`) pour injecter `POSTGRES_USER/PASSWORD` dans les jobs atlas pgvector ; il est absent.             | `kubectl -n dagster get secret pgvector-pg-auth → NotFound` (seul `dagster-pg-auth` présent en ns dagster)                  | Vérifier pourquoi le rôle `platform-dagster` ne l'a pas posé ; corriger le rôle puis re-prouver.                       |
| m2  | PSA absent sur les namespaces sensibles                              | sécurité / durcissement | Seuls gitea et registry portent des labels PSA (`enforce=baseline`, `warn=restricted`) ; postgres/dagster/argocd/rook-ceph/monitoring/mlflow/marquez/portal/cnpg-system n'en ont aucun.                | `kubectl get ns -o json` (labels `pod-security.kubernetes.io/*`) → `<none>` partout sauf gitea/registry                     | Poser au minimum `audit=restricted`/`warn=restricted` sur les ns applicatifs, puis `enforce=baseline`.                 |
| m3  | Workloads sans securityContext (dagster, marquez, mlflow partiel)    | sécurité / root         | dagster (webserver/daemon/toy-codeloc) et marquez tournent root sans `runAsNonRoot` ni seccomp ; mlflow partiellement durci (UID 1000, seccomp, mais pas de roFS).                                     | `kubectl exec -n dagster … -- id → uid=0(root)` ; `securityContext={}` sur dagster/marquez ; mlflow `runAsUser=1000`        | Ajouter `runAsNonRoot:true`, UID non-0, seccomp `RuntimeDefault`, `drop ALL`, roFS ; vérifier le support image.        |
| m4  | SA `default` automonté dans des pods sans besoin de l'API            | sécurité / RBAC         | gitea, registry, marquez, mlflow, toy-codeloc utilisent le SA `default` avec token API projeté inutilement (ces charges n'appellent pas l'API). Impact faible (RBAC `default` nul).                    | `serviceAccountName==default` + `kube-api-access-*` projeté (vérifié gitea/registry) ; `can-i secrets:get=no`               | `automountServiceAccountToken:false` au niveau pod (ou SA dédié) pour ces charges.                                     |
| m5  | Argo CD entièrement entassé sur dirqual3, 100 % mono-réplique        | résilience / SPOF appli | 6/7 composants Argo CD (controller, applicationset, notifications, redis, repo-server, server) tous sur dirqual3 ; seul dex sur dirqual2. Perte de dirqual3 = plus de GitOps/UI/redis.                 | `kubectl -n argocd get pods -o wide` → tous NODE=dirqual3 sauf dex ; aucun PDB                                              | redis-ha ou au moins anti-affinité soft ; documenter que la perte de dirqual3 suspend le GitOps.                       |
| m6  | Stack monitoring mono-réplique concentrée sur dirqual4               | résilience / observ.    | prometheus-0, alertmanager-0, grafana tous mono-réplique sur dirqual4 ; perte de dirqual4 = trou de métriques + plus d'alerte pendant le reschedule. Aucun PDB.                                        | `kubectl -n monitoring get pods -o wide` → prometheus/alertmanager/grafana/loki tous NODE=dirqual4                          | Alertmanager ≥2 répliques (mode cluster) sur nœuds distincts ; idéalement Prometheus ×2. À défaut, documenter.         |
| m7  | Les deux MDS CephFS (actif + hot standby) co-localisés sur dirqual4  | résilience / Ceph       | `myfs-a` (actif) et `myfs-b` (standby) tous deux sur dirqual4 : la perte du nœud emporte actif ET standby, annulant le bénéfice du standby. CephFS indispo jusqu'au reschedule.                        | `kubectl -n rook-ceph get pods -l app=rook-ceph-mds -o wide` → myfs-a et myfs-b NODE=dirqual4 ; `ceph -s` mds 1/1 + standby | Anti-affinité (hard de préférence) entre MDS actif et standby (placement Rook dans le `CephFilesystem` CR).            |
| m8  | OOMKill récent du mgr Ceph actif et de Grafana (limites serrées)     | résilience / ressources | mgr-a OOMKilled le 2026-06-23 (2 restarts, lim 1Gi / usage 718Mi) ; failover vers mgr-b OK mais use le mécanisme. Grafana aussi OOMKilled (lim 256Mi). Nœuds sans MemoryPressure.                      | `lastState OOMKilled` mgr-a (finishedAt 2026-06-23T15:05:59Z) & grafana ; `kubectl top` mgr-a=718Mi ; nœuds requests ~10 %  | Relever lim mémoire mgr (≈2Gi) et Grafana (≈512Mi). Le cluster a la marge (256 TiB / ~90 % RAM libre).                 |
| m9  | Aucune rétention sur les backups CNPG / WAL (croissance illimitée)   | données / rétention     | `ObjectStore pg-backup` a `retentionPolicy: None` ; base backups (13) + WAL s'accumulent indéfiniment. Faible pression aujourd'hui (~126 MiB / Ceph 4,27 %), mais dette structurelle.                  | `objectstore pg-backup -o json` → `spec.retentionPolicy` absent ; logs sidecar « Skipping retention policy enforcement »    | Définir `spec.retentionPolicy` (ex. `30d`) dans le manifeste versionné (pas en patch live), re-prouver.                |
| m10 | Pools EC RGW (datalake) en `k=2 m=1` : tolère 1 seul hôte            | données / durabilité    | Le pool `datalake.rgw.buckets.data` (qui porte cnpg-backups/mlflow-artifacts/loki) est EC k=2/m=1 sur 4 hôtes : une 2ᵉ panne pendant un rebuild expose à une perte. Backups PG = filet.                | `ceph osd erasure-code-profile get datalake.rgw.buckets.data_ecprofile` → k=2 m=1 host ; pools répliqués size=3 min_size=2  | Évaluer un pool plus durable pour les backups (réplication 3× ou EC k=2/m=2) ; à minima documenter (ADR/RUNBOOK).      |
| m11 | Grafana OOMKilled récurrent (limite 256Mi trop juste)                | observabilité / ress.   | Conteneur grafana OOMKilled (exit 137), 2-3 restarts (le plus haut du cluster avec mgr-a). Lim 256Mi / usage 212Mi (83 %). Perte d'UI par intermittence, churn inutile.                                | `describe pod grafana` → OOMKilled exit 137 ; `limits.memory=256Mi` ; `kubectl top` grafana=212Mi                           | Relever la lim mémoire Grafana (ex. 512Mi) dans les values ; vérifier qu'aucun dashboard ne fuit.                      |
| m12 | Code location Dagster `toy` flappe LOCATION_ERROR ↔ LOCATION_UPDATED | observabilité / dataops | Le webserver ET le daemon reçoivent en boucle (toutes les ~1-2 min, plusieurs heures) des erreurs de location `toy` suivies de récupération : instabilité gRPC. Pod 1/1 Ready, 0 restart, sans probes. | logs webserver/daemon → alternance répétée `LOCATION_ERROR`/`LOCATION_UPDATED` (≈1069/1070 occurrences) ; pod sans probes   | Diagnostiquer la stabilité gRPC (timeouts, DNS nom court vs FQDN ndots:5) ; ajouter des probes ; fiabiliser le reload. |

## Info (11)

| #   | Titre                                                                      | Dimension                | Constat (lecture seule)                                                                                                                                                                                                                                                                    |
| --- | -------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| i1  | Contrat cluster→atlas largement tenu : 18/18 endpoints montés répondent    | contrat                  | Scénario 31 en lecture seule : 18 présents (18 répondants, 0 muets), 3 absents / 21. Absents : s3-datalake-light + mailpit-ui (profil local-path, banc-only attendu) ; k8s-dashboard-ui (seul absent non banc-only). Toutes les StorageClasses Ceph présentes ; CNPG 3/3 ; pgvector 0.8.2. |
| i2  | Secret `argocd-initial-admin-secret` toujours présent après ~13 jours      | sécurité / secrets       | Résidu de durcissement. Aggravant : `admin.passwordMtime` = création du secret → le mot de passe admin n'a **jamais** été tourné. À supprimer après bascule SSO/rotation, via le flux d'install.                                                                                           |
| i3  | Pools EC en `k=2 m=1` : zéro marge au-delà d'un hôte                       | résilience / Ceph        | Les 3 pools EC (datalake.rgw, ec-data, delete-data) sont k=2/m=1, min_size=2 : pendant une maintenance d'un nœud, le cluster est exactement à min_size, sans marge. Sur 4 nœuds, m=2 serait envisageable. (Recoupe m10.)                                                                   |
| i4  | Exposition L4 NodePort conforme ADR 0092 ; cohabitation LB-IPAM résiduelle | gitops / exposition      | Toutes les UI en NodePort (conforme ADR 0092). Unique vestige LB-IPAM : Gateway cilium `argocd` (10.67.3.240) + HTTPRoute argocd-server + svc LB. État **attendu** jusqu'au rebuild (~sept. 2026), pas un défaut. Aucun Gateway/HTTPRoute zombie.                                          |
| i5  | Versions homogènes : k8s 1.34.8 sur les 4 nœuds, aucun skew kubelet        | gitops / versions        | Server + kubelet v1.34.8 identique sur dirqual1-4. Légère divergence containerd (dirqual1 = 2.3.2, dirqual2-4 = 2.2.5), cosmétique — à harmoniser au rebuild. Cilium v1.19.4, CNPG 1.29.1, Argo CD v3.4.3.                                                                                 |
| i6  | Santé générale : aucun pod en échec, Ceph HEALTH_OK, aucun event Warning   | gitops / santé           | 130 Running + 5 Completed, rien hors Running/Completed ; aucun ImagePullBackOff/CrashLoopBackOff. Restarts négligeables (grafana 2×, mlflow/csi 1×). 0 event Warning. CephCluster Ready / HEALTH_OK.                                                                                       |
| i7  | ScheduledBackup CNPG sain — dernier backup <24h, historique 12 jours       | données / backups        | `pg-daily` (cron 0 0 2 \* \* \*) : dernier backup il y a ~6h, completed, 13 consécutifs 100 % completed. Cluster pg 3/3 Ready ; `LastBackupSucceeded=True`, `ContinuousArchivingSuccess=True`. Points d'attention = rétention (m9) + test restore (M6).                                    |
| i8  | S3 datalake (RGW) opérationnel — ObjectStore Ready, buckets Bound peuplés  | données / S3             | CephObjectStore `datalake` Ready, 3 daemons RGW. 3 OBC Bound (cnpg-backups, loki-buckets, mlflow-artifacts). Bucket cnpg-backups = 527 objets (~126 MiB) : backups réels présents. (`radosgw-admin` exige `--rgw-zone=datalake`.)                                                          |
| i9  | Ceph HEALTH_OK — capacité confortable, aucun pool near-full                | données / Ceph           | 268 TiB raw, 11 TiB utilisés (4,27 % RAW USED), 256 TiB libres. 47/47 OSDs up+in (4 hôtes, %USE homogène ~4,3 %), 3 mons quorum, mgr actif+standby, mds 1/1 + standby, 393/393 PGs active+clean.                                                                                           |
| i10 | PVC Prometheus à 84 % (10Gi) — proche du retentionSize cap 9GB             | observabilité / stockage | PVC le plus chargé (8,19 / 9,75 GiB). `retention=15d` mais `retentionSize=9GB` : Prometheus s'auto-plafonne (~90 %) et purgera avant 15 j. Pas de débordement, mais fenêtre effective <15 j (≈1Gi de marge). 124 790 séries.                                                               |
| i11 | Briques saines confirmées (Ceph, CNPG, ArgoCD, observabilité, certs)       | observabilité / santé    | Ceph HEALTH_OK ; CNPG pg 3/3 healthy ; ArgoCD atlas-workflows Synced+Healthy ; tous les pods d'observabilité Running ; 4 PVC monitoring Bound ; nœuds 3-4 % mémoire ; certificats cert-manager tous Ready (expiration la plus proche 2026-09-09, renouvellement auto).                     |

## Faux-positifs écartés (14)

Vérifiés sur dirqual réel (lecture seule), ces points **ne sont pas** des
problèmes :

- **k8s-dashboard-ui absent** alors que non marqué banc-only au contrat : le
  namespace est bien absent, mais c'est l'unique absence non banc-only — tracée
  en i1, pas un défaut du contrat lui-même.
- **Service CNPG `pg-r`** (any-instance) présent en plus de pg-rw/pg-ro : non
  contractuel mais sans impact, comportement standard CNPG.
- **EndpointSlices** : tous les backends des endpoints contractuels montés sont
  **prêts** (non vides) — le contrat répond effectivement.
- **Dérive d'exposition ArgoCD** (Gateway/LB-IPAM 10.67.3.240 coexiste avec le
  NodePort) : faits exacts mais **interprétation fausse** — cohabitation
  **attendue** jusqu'au rebuild (ADR 0092, mémoire dirqual).
- **Socle control-plane bien durci** (chiffrement etcd, audit, RBAC, portail
  minimal) : observation positive, pas un problème.
- **PDB mon Ceph** correct : observation positive (à surveiller en maintenance
  simultanée seulement).
- **CNPG bien réparti, Ceph HEALTH_OK, OSD complets, PG propres** : synthèse
  positive.
- **Argo CD : unique Application atlas-workflows Synced+Healthy**,
  selfHeal/prune actifs : sain.
- **Images sur tags mutables `:dev`** (toy-codeloc, portal) : faits exacts mais
  toléré (code-location jouet ADR 0086) — 1 toléré, 1 à requalifier hors
  périmètre.
- **Certificats cert-manager** tous Ready, aucune expiration imminente, aucun
  challenge/order en attente : sain.
- **PVC Prometheus à 83,8 %** « perte imminente » : chiffre exact mais sévérité
  fausse — `retentionSize` borne le remplissage (cf. i10).
- **PV/PVC tous Bound**, aucun PV Released/orphelin : sain.
- **Opérateur CNPG : DeadlineExceeded intermittents** sur le plugin barman-cloud
  : logs réels (~46 sur 13 j) mais reconciles aboutissent, backups completed —
  bruit sans impact.
- **KubeProxyDown firing** : attendu avec Cilium en kube-proxy replacement —
  non-incident.

## Plan d'action proposé

Aucune mutation n'est faite ici : ce qui suit est un **plan**, à instruire via
issues + ADR. Nature des correctifs : **drift** (code mergé non appliqué →
déployer) ; **défaut de conf** (corriger values/manifeste + redéployer GitOps) ;
**dette structurante** (→ ADR/plan) ; **procédure** (à coder/documenter).

### Vague P1 — immédiat (sécurité active + drift + alerting aveugle)

- **M1** drift base `cache`/`pg-role-cache` (ADR 0093) → **déployer** la
  déclaration versionnée (poser le Secret, laisser CNPG réconcilier). _Effort
  S._
- **M7** Alertmanager aveugle (mailpit absent) → **défaut de conf** : aligner
  les values + re-prouver. _Effort S._
- **M3** NetworkPolicy `postgres` absente → **défaut de conf** : ajouter
  `default-deny-ingress` + allow ciblé 5432. _Effort S-M._
- **M2** ClusterRole Grafana cluster-wide secrets → **défaut de conf** :
  restreindre aux ConfigMaps dans les values. _Effort S._

### Vague P2 — court terme (bruit d'alerte, durcissement, ressources)

- **M8** scrape control-plane DOWN → **défaut de conf** (probable ADR mono-CP) :
  exposer/désactiver les targets control-plane. _Effort M (+ADR)._
- **M5** anti-affinité CoreDNS soft → **défaut de conf** : passer en `required`.
  _Effort S._
- **m1** dérivé `pgvector-pg-auth` manquant → **drift/conf** : corriger le rôle
  `platform-dagster`. _Effort S._
- **m9** rétention backups CNPG → **défaut de conf** : `retentionPolicy: 30d`.
  _Effort S._
- **m8 / m11** OOMKill mgr-a + Grafana → **défaut de conf** : relever les
  limites mémoire. _Effort S._
- **m2 / m3 / m4** PSA + securityContext + automount SA default → **défaut de
  conf** durcissement (vérifier support UID des images d'abord). _Effort M._
- **m5 / m6 / m7** répartition Argo CD / monitoring / MDS Ceph → **défaut de
  conf** : anti-affinités + (option) répliques. _Effort M._
- **m12** flapping code-location `toy` → diagnostic + probes. _Effort M._

### Vague P3 — fond (dette structurante + procédure + durabilité)

- **M4** SPOF control-plane mono-nœud → **dette structurante** : ADR/plan (3
  control-plane stacked etcd) à instruire au rebuild ~sept. 2026. _Effort L._
- **M6** test de restore CNPG jamais exercé → **procédure** : Cluster de
  recovery hors-prod + RUNBOOK. _Effort M._
- **m10 / i3** durabilité EC RGW (m=1) sur les backups → **dette / décision** :
  évaluer m=2 ou réplication 3× pour les buckets de backup, sinon documenter.
  _Effort M._
- **i2** rotation/suppression `argocd-initial-admin-secret` → **procédure**
  (après bascule SSO). _Effort S._
- **i5** harmoniser containerd (cosmétique) + **i4** retrait LB-IPAM résiduel :
  à traiter **au rebuild**. _Effort intégré au rebuild._

## Issues à créer

Groupées par thème, à ouvrir ensuite (titre + sévérité + 1 phrase) :

### Drift code↔prod

- **dirqual : appliquer la base CNPG `cache` + rôle `pg-role-cache` (ADR 0093)**
  — _majeur_ — déclaré dans les manifestes versionnés mais absent du cluster ;
  poser le Secret puis laisser CNPG réconcilier.
- **dirqual : poser le secret dérivé `pgvector-pg-auth` (ns dagster)** —
  _mineur_ — le rôle `platform-dagster` ne l'a pas posé ; les jobs atlas
  pgvector ne peuvent injecter leurs creds.

### Sécurité / RBAC / réseau

- **Grafana : restreindre le ClusterRole aux ConfigMaps (plus de secrets
  cluster-wide)** — _majeur_ — le SA lit tous les Secrets du cluster ; le
  limiter aux ConfigMaps dans les values.
- **ns postgres : ajouter une NetworkPolicy ingress (5432 réservé aux
  consommateurs)** — _majeur_ — aucune NetworkPolicy, pg-rw:5432 joignable de
  tout le cluster.
- **Poser les labels PSA sur les namespaces sensibles** — _mineur_ —
  audit/warn=restricted puis enforce=baseline (postgres/dagster/argocd/…).
- **Durcir les workloads dagster/marquez/mlflow (securityContext)** — _mineur_ —
  runAsNonRoot + seccomp + drop ALL + roFS (vérifier support image).
- **Désactiver l'automount du SA default (gitea/registry/marquez/mlflow/toy)** —
  _mineur_ — token API monté inutilement.
- **Rotation puis suppression de `argocd-initial-admin-secret`** — _info_ — mot
  de passe admin jamais tourné ; supprimer après bascule SSO via le flux
  d'install.

### Résilience / HA

- **Control-plane mono-nœud : ADR + plan HA (3 CP / stacked etcd)** — _majeur_ —
  SPOF total (API + etcd sur dirqual1), à instruire au rebuild.
- **CoreDNS : anti-affinité hard pour séparer les 2 répliques** — _majeur_ — les
  deux pods sur dirqual1 ; passer en required/topologySpread.
- **Argo CD : éviter la co-location totale sur dirqual3 (redis-ha /
  anti-affinité)** — _mineur_ — perte de dirqual3 = plus de GitOps.
- **Monitoring : Alertmanager ≥2 répliques réparties (+PDB)** — _mineur_ — stack
  mono-réplique sur dirqual4.
- **Ceph MDS : anti-affinité actif/standby (CephFilesystem CR)** — _mineur_ —
  myfs-a et myfs-b co-localisés sur dirqual4.
- **Relever les limites mémoire mgr Ceph et Grafana (OOMKill)** — _mineur_ —
  OOMKill récurrents, le cluster a la marge.

### Données / backups

- **Tester la restauration CNPG hors-prod (recovery + PITR) + RUNBOOK** —
  _majeur_ — backups completed jamais restaurés.
- **Définir la rétention des backups CNPG/WAL (`retentionPolicy`)** — _mineur_ —
  croissance illimitée (None aujourd'hui).
- **Évaluer la durabilité EC RGW (m=1) des buckets de backup** — _mineur_ — pool
  de backups moins durable que les pools répliqués ; envisager m=2/3× ou
  documenter.

### Observabilité

- **Alertmanager : corriger le smarthost mailpit (alerting aveugle)** — _majeur_
  — aucune notification ne part (namespace `mail` absent).
- **Scrape control-plane DOWN : exposer ou désactiver les targets (mono-CP)** —
  _majeur_ — alertes etcd/scheduler/controller-manager en faux positif.
- **Dagster : stabiliser le flapping de la code-location `toy` (gRPC/probes)** —
  _mineur_ — oscillation LOCATION_ERROR/UPDATED continue.
- **Prometheus : aligner PVC et retentionSize pour 15 j effectifs** — _info_ —
  PVC à 84 %, fenêtre effective <15 j.
