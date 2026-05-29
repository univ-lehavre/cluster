# 8 — Opérabilité, observabilité, résilience & angles complémentaires

**Note : 3 / 5**

Cette dimension répond à votre question **« vois-tu d'autres aspects à couvrir ?
»** : elle couvre des axes que vous n'aviez pas listés mais qui sont critiques
pour ce dépôt.

Le dépôt est exceptionnellement outillé côté opérabilité « jour 0-1 »
(`state.sh` et `report.sh` offrent une observation par couches remarquable,
sauvegarde etcd soignée, SPOF assumés et documentés). En revanche, plusieurs
dimensions « jour 2 » sont absentes ou non testées.

## Points forts

- Observation d'état par couches de très bonne facture (`state.sh` 7 couches +
  remédiation suggérée ; `report.sh` strictement lecture seule) — un vrai
  différenciateur.
- Sauvegarde etcd robuste (snapshot via `crictl`, vérif d'intégrité, publication
  atomique, rétention NUL-safe).
- Traçabilité des opérations (`audit-log` par playbook, exploité par
  `state.sh`).
- Rollback du bootstrap explicite et sûr (`-e confirm=yes`, périmètre
  documenté).
- SPOF assumés et tracés (ADR 0002 control-plane unique, ADR 0008 NVMe
  `block.db`).
- Résilience stockage cohérente (`reclaimPolicy: Retain` disponible,
  `preserveFilesystemOnDelete`, PDB gérés par l'operator).

## Constats

### Majeur (→ vérifié majeur) — Aucune observabilité runtime

- **Fichier** : `storage/ceph/cluster.yaml:82-87` (`monitoring.enabled: false`)
- **Constat** : aucun metrics-server (donc `kubectl top` et HPA inopérants),
  Prometheus/Grafana/Loki, ni alerting. La détection de panne repose entièrement
  sur l'exécution **manuelle** de `state.sh` par l'unique admin. Aucun ADR ne
  couvre l'observabilité → item ouvert, pas un choix assumé.
- **Recommandation** : a minima metrics-server ; idéalement
  kube-prometheus-stack
  - `monitoring.enabled: true` (métriques + alertes Ceph : OSD down, near-full,
    quorum mon). Au minimum, documenter une routine de surveillance manuelle.

### Majeur (→ vérifié majeur) — Aucune sauvegarde des données applicatives

- **Fichier** : transversal (pas de Velero/VolumeSnapshot) ;
  `storage/ceph/storageClass/datalake/datalake-ec.yaml:21`
- **Constat** : seul etcd est sauvegardé. La réplication Ceph protège du crash
  matériel mais **pas** d'une suppression accidentelle, d'une corruption logique
  ou d'un ransomware. Aggravant : `preservePoolsOnDelete: false` + StorageClass
  bloc par défaut en `reclaimPolicy: Delete` → un `kubectl delete pvc` ou
  `delete CephObjectStore` est **irréversible**.
- **Recommandation** : définir une stratégie de sauvegarde (ADR explicitant le
  RPO/RTO accepté) ; CSI VolumeSnapshots programmés pour les PVC critiques et/ou
  réplication des buckets S3 ; basculer les pools précieux en
  `preservePoolsOnDelete: true`.

### Majeur (→ vérifié majeur) — La restauration etcd n'a jamais été testée

Cf. [02-tests.md](02-tests.md). Un backup non restauré n'est pas un backup ;
l'ADR 0002 promet une procédure « testée sur le banc » qui ne l'est pas.

### Majeur (→ vérifié mineur) — Pas de copie hors-nœud des snapshots etcd

- **Fichier** : `bootstrap/roles/etcd-backup/templates/etcd-snapshot.sh.j2:28`
- **Constat** : snapshots écrits **uniquement** sur le control-plane lui-même.
  Or le scénario qui les justifie (perte de `dirqual1`) est précisément celui où
  le disque local devient inaccessible → perte simultanée d'etcd ET de ses
  sauvegardes. _Ramené à mineur : SPOF assumé (ADR 0002), scénario corruption
  logique couvert, backups sur LV distinct ; le défaut est l'absence de copie
  off-site et de RPO documenté._
- **Recommandation** : `fetch` Ansible périodique vers le poste de contrôle, ou
  push vers S3/CephFS d'un autre nœud ; documenter le RPO réel.

### Majeur (→ vérifié majeur) — Tension RGPD : datasets nominatifs

- **Fichier** : ADR 0003:21,71 ;
  `storage/ceph/storageClass/datalake/object-bucket-claim-{twitter,reddit}.yaml`
- **Constat** : trois ADR reposent sur « pas de données personnelles » (ADR
  0003:21), mais le datalake provisionne des buckets `twitter` et `reddit` — des
  corpus de réseaux sociaux contiennent **par construction** des données à
  caractère personnel (pseudonymes, contenus, géolocalisation). L'ADR 0003:71
  liste lui-même « données réglementées (RGPD) » comme déclencheur de révision.
  Conjugué à l'absence de chiffrement at-rest/in-transit et d'auth, écart réel
  entre posture documentée et nature des données. Aucune politique de rétention/
  minimisation/base légale.
- **Recommandation** : faire qualifier ces datasets par un référent RGPD/DPO. Si
  données personnelles confirmées : réviser les ADR 0003/0011/0012 (chiffrement
  LUKS, TLS RGW, restriction d'accès), documenter base légale / durée / purge.
  Sinon, documenter pourquoi ces corpus sont hors champ (anonymisation amont).

### Majeur (→ vérifié mineur) — Aucune procédure de montée de version Kubernetes

- **Fichier** : `bootstrap/upgrade.yaml`, `bootstrap/roles/upgrade-os/`
- **Constat** : `upgrade.yaml` ne fait qu'un `apt full-upgrade` de l'OS — le nom
  est trompeur. Aucun `kubeadm upgrade plan/apply`, aucun drain/uncordon, aucune
  gestion des holds APT. _Ramené à mineur : stratégie de rebuild/re-bootstrap
  assumée (PLAN.md, ADR 0006), mais polish documentaire manquant._
- **Recommandation** : runbook `kubeadm upgrade` (control-plane puis workers,
  drain/uncordon, holds) + playbook `k8s-upgrade.yaml` ; **renommer
  `upgrade.yaml` en `os-upgrade.yaml`** pour lever l'ambiguïté.

### Mineur — Surveillance SMART des NVMe non automatisée

- **Fichier** : ADR 0008:50-53
- **Constat** : l'ADR désigne le NVMe `block.db` comme SPOF (perte = 12 OSDs) et
  liste « État SMART » à surveiller, mais aucune automatisation (`smartd`, check
  `state.sh`, alerte).
- **Recommandation** : `smartd` + alerte (réutiliser la couche `alert`/postfix),
  ou couche `state.sh` lisant `smartctl -H`. Documenter le seuil de drain
  préventif.

### Mineur — Workloads plateforme mono-réplica (SPOF applicatifs non tracés)

- **Fichier** : `platform/container-registry/deployment.yaml:7`,
  `apps/rstudio/deployment.yaml:7`
- **Constat** : registry et RStudio en `replicas: 1` sur PVC RWO ; perte du nœud
  hôte = interruption. Cohérent avec un labo mono-admin, mais non documenté
  comme choix assumé (contrairement aux SPOF infra des ADR 0002/0008).
- **Recommandation** : documenter ces SPOF applicatifs et le temps de reprise
  attendu (reschedule + remount RWO).

### Mineur — Supply chain : tags sans digest, ni cosign, ni SBOM

Cf. [11-logiciels-oss.md](11-logiciels-oss.md). L'ADR 0006 recommande pourtant
les digests « pour les composants critiques ».

### Mineur / Suggestion — Site doc & capacité

- `editLink` vers le mauvais dépôt + `ignoreDeadLinks` (cf.
  [04](04-documentation.md)).
- Aucune documentation de dimensionnement/capacité (seuils nearfull/full Ceph,
  procédure d'ajout d'OSD, remplissage du PVC registry dont le GC est suspendu)
  → ajouter une section capacité au RUNBOOK Ceph (`ceph df`, `ceph osd df`,
  extension).

## Autres angles passés en revue (sans finding bloquant)

- **i18n / langue** : tout en français — **adapté** au public mono-admin
  francophone, pas un défaut.
- **Coût / empreinte** : hors périmètre du dépôt (matériel documenté dans
  `platform/hardware.md`).
- **Transmissibilité / bus-factor** : mainteneur quasi unique → formaliser les
  choix structurants en ADR (langage des scripts, stratégie d'upgrade,
  sauvegarde des données) réduit le risque. Voir [09](09-langage-scripts.md) et
  [12](12-plan-action.md).
