# Runbook — Rook-Ceph

Installation, opération et désinstallation d'un cluster Ceph distribué via
l'opérateur Rook 1.19 (Ceph Tentacle 20.2.1).

## Installation de l'opérateur

```bash
kubectl create -f crds.yaml -f common.yaml -f operator.yaml
```

Attendre que l'opérateur et les services de discovery soient déployés :

```bash
kubectl -n rook-ceph get pod
```

Sortie attendue (extrait) :

```text
NAME                                  READY   STATUS    RESTARTS   AGE
rook-ceph-operator-65b89665df-n2s8g   1/1     Running   0          74s
rook-discover-7psxb                   1/1     Running   0          53s
```

## Création du cluster

> **Pré-vol matériel/OS (recommandé)** — avant de créer le cluster, lancer le
> pré-vol Ceph qui vérifie sur chaque nœud de stockage : `lvm2` présent (requis
> par `ceph-volume` dès qu'un `metadataDevice`/block.db est utilisé — sinon
> OSD-prepare CrashLoop « binary lvm does not exist »), présence du NVMe
> block.db, et nombre de disques data bruts. Il **installe `lvm2`** (idempotent)
> et échoue CLAIREMENT si un disque manque, au lieu de laisser le `cluster.yaml`
> échouer tard et obscurément (drift L6) :
>
> ```bash
> ansible-playbook -i ./hosts.yaml ../../bootstrap/ceph-checks.yaml
> # Parc différent du matériel cible (ADR 0008/0009) ? surcharger :
> #   -e ceph_block_device=nvme0n1 -e ceph_min_hdd=8 -e 'ceph_data_device_glob=/dev/sd[a-h]'
> ```

Et, en cas de rebuild :

> **Pré-requis critique (rebuild / réinstallation)** — avant
> `kubectl create -f cluster.yaml`, vérifier que **les 4 nœuds** ont bien
> `/var/lib/rook` **et leurs disques data effacés**. Un reliquat d'un cluster
> précédent fait redémarrer les `ceph-mon` sur un ancien état (`fsid` divergent)
> → ils refusent de démarrer et le `CephCluster` reste bloqué. Le wipe est
> assuré par [`cleanup.sh`](cleanup.sh) (disques) et la réinstallation OS
> (`/var/lib/rook`, hébergé sur `/var` reformaté — cf.
> [`bootstrap/RUNBOOK.md` § Partitionnement](../../bootstrap/RUNBOOK.md)). Ne
> pas créer le cluster avant d'avoir **≥ 3 hôtes prêts** (le quorum `mon` et le
> réplicat ×3 l'exigent).

```bash
kubectl create -f cluster.yaml
```

S'ajoutent alors des pods pour le FS et le RBD par nœud, des provisioners, les
`ceph-mon` et `ceph-mgr`, les crashcollector et les exporter, ainsi qu'un OSD
par disque. Attendre que tous les OSD soient `Running` :

```bash
kubectl -n rook-ceph get pod
```

## Toolbox

```bash
kubectl create -f toolbox.yaml
kubectl -n rook-ceph exec -it deploy/rook-ceph-tools -- bash
```

À l'intérieur :

```bash
ceph status
ceph osd status
ceph df
rados df
```

> Environ 4,3 % du stockage est utilisé par des métadonnées sur les disques.

Quand l'inspection est terminée :

```bash
kubectl -n rook-ceph delete deploy/rook-ceph-tools
```

## Capacité et dimensionnement (audit P8)

Surveiller le **taux de remplissage** : un pool Ceph qui approche `nearfull` (85
% par défaut) dégrade les performances, et `full` (95 %) **bloque les
écritures**. Depuis la toolbox :

```bash
ceph df                 # %USED par pool + espace brut/dispo
ceph osd df             # remplissage par OSD (repérer un déséquilibre)
ceph health detail      # alertes nearfull/backfillfull/full explicites
```

**Capacité de ce cluster** : 4 nœuds × 12 HDD × 5,5 TiB ≈ **264 TiB brut**, soit
~**88 TiB utiles** en réplicat ×3 (cf.
[ADR 0009](../../docs/decisions/0009-pourquoi-4-noeuds.md)).

**Ajouter de la capacité** : remplacer un disque défaillant ou ajouter des HDD
se fait à chaud — `useAllDevices: true` ([cluster.yaml](cluster.yaml)) fait
détecter et intégrer les nouveaux disques bruts par l'operator (la découverte
automatique étant désactivée, cf. ADR : c'est le redéploiement du `CephCluster`
qui les prend en compte). Après ajout, Ceph rééquilibre (`backfill`) —
surveiller `ceph status` jusqu'au retour `HEALTH_OK`.

**GC du registry** : le PVC `registry-pvc` ne se vide pas tout seul quand on
supprime des tags. Le `CronJob` de garbage-collection
([garbage-collect-cronjob.yaml](../../platform/container-registry/garbage-collect-cronjob.yaml))
récupère l'espace ; le déclencher manuellement si le PVC se remplit.

## Classes de stockage

`rook-ceph-block-replicated` est annotée
`storageclass.kubernetes.io/is-default-class: "true"` — c'est la classe par
défaut du cluster ; les PVC sans `storageClassName` y atterrissent.

### Bloc

```bash
kubectl apply -f storageClass/block-replicated.yaml      # défaut (réplicat ×3)
kubectl apply -f storageClass/block-ec-delete.yaml       # EC 2+1, reclaim Delete
kubectl apply -f storageClass/block-ec-retain.yaml       # EC 2+1, reclaim Retain
```

> ⚠️ **EC 2+1 sur 4 hôtes — piège `min_size`** : le `min_size` par défaut d'un
> pool EC `k=2, m=1` est `k+1 = 3`. La perte d'**un** hôte fait passer le pool
> sous `min_size` et **bloque les I/O** jusqu'au remplacement, sans perte de
> données mais avec interruption. Ces classes restent utiles pour des données
> tolérantes (datalake, archives). Pour le critique, utiliser la classe par
> défaut `rook-ceph-block-replicated` (×3, tolère 1 perte sans blocage). Les
> pools de **métadonnées** des classes EC sont désormais en `size: 3` +
> `requireSafeReplicaSize: true` (Ceph déconseille fortement `size: 2`).

### Objet (datalake)

```bash
kubectl apply -f storageClass/datalake/datalake-ec.yaml
kubectl apply -f storageClass/datalake/storage-class.yaml
kubectl apply -f storageClass/datalake/object-bucket-claim-gdelt.yaml
```

Voir [`storageClass/datalake/README.md`](storageClass/datalake/README.md) pour
le détail des claims et l'extraction des credentials.

> ⚠️ **Comportement destructif** : le `CephObjectStore` est configuré avec
> `preservePoolsOnDelete: false` — supprimer l'objet **détruit les pools et
> toutes les données S3**. Cohérent avec un datalake ré-ingestible. Si les
> données doivent survivre à une suppression, basculer à
> `preservePoolsOnDelete: true` avant.

## Chiffrement (décision assumée)

Aucun chiffrement Ceph n'est activé : `network.connections.encryption.enabled`
reste à `false` dans `cluster.yaml`, et le datalake RGW expose `port: 80` sans
TLS. La décision tient parce que les flux internes au cluster restent confinés
au réseau privé `10.0.0.0/22`, et que **l'accès externe est limité par le
contrôle d'accès au Service** (réseau cluster, port-forward sur API K8s, ou
tunnel Tailscale si l'operator est déployé — voir ci-dessous). À revisiter le
jour où ces hypothèses changent (exposition publique, données classifiées,
etc.).

## Tailscale operator (optionnel)

L'installation du Tailscale operator est **facultative**. Sans lui, les
annotations `tailscale.com/expose` et `tailscale.com/hostname` posées sur
certains Services (registry, RStudio) sont simplement ignorées, et l'accès
distant se fait par `kubectl port-forward`. Avec lui, ces Services deviennent
joignables depuis le tailnet.

```bash
helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update
export $(grep -v '^#' .env | xargs)
helm upgrade \
  --install tailscale-operator tailscale/tailscale-operator \
  --namespace tailscale --create-namespace \
  --set-string oauth.clientId="${clientID}" \
  --set-string oauth.clientSecret="${clientSecret}" \
  --wait
```

## Récupérer les clefs d'un object store

```bash
kubectl -n default get secret datalake \
  -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 --decode
kubectl -n default get secret ceph-bucket \
  -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 --decode
```

## Désinstallation

### Object store (datalake) — ORDRE OBLIGATOIRE

> ⚠️ **Toujours supprimer les buckets/OBC AVANT le `CephObjectStore`.** Rook
> protège les données : il refuse de supprimer un object store tant qu'il reste
> des `ObjectBucketClaim`/buckets. Si on supprime le store en premier, le RGW
> part en suppression et l'OBC ne peut plus se _deprovisionner_ → **deadlock
> mutuel de finalizers** (les deux objets restent en `Deleting` indéfiniment ;
> l'operator répète « will not be deleted until all dependents are removed »).

Ordre correct :

```bash
# 1. Supprimer les OBC (chaque OBC vide puis retire son bucket S3).
kubectl -n rook-ceph delete obc --all          # ou bucket par bucket
# 2. Supprimer le CephObjectStoreUser éventuel.
kubectl -n rook-ceph delete cephobjectstoreuser --all
# 3. Attendre qu'il ne reste plus aucun bucket côté RGW.
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- radosgw-admin bucket list   # → []
# 4. Seulement ensuite, supprimer le CephObjectStore.
kubectl -n rook-ceph delete cephobjectstore datalake
```

**Déblocage si déjà en deadlock** (⚠️ données perdues — uniquement si jetables)
:

```bash
# Retirer les finalizers des OBC/ObjectBucket coincés…
for b in $(kubectl -n rook-ceph get obc -o name); do
  kubectl -n rook-ceph patch "$b" --type merge -p '{"metadata":{"finalizers":[]}}'
done
for ob in $(kubectl get objectbucket -o name); do
  kubectl patch "$ob" --type merge -p '{"metadata":{"finalizers":null}}'
done
# …purger les buckets RGW résiduels…
kubectl -n rook-ceph exec deploy/rook-ceph-tools -- \
  radosgw-admin bucket rm --bucket=<nom> --purge-objects
# …puis, en dernier recours, le finalizer du store lui-même.
kubectl -n rook-ceph patch cephobjectstore datalake --type merge \
  -p '{"metadata":{"finalizers":null}}'
```

Constaté sur banc (Run #7, cf. [test/RESULTS.md](../../test/RESULTS.md) #19).

### Pools, storage classes, cluster

Supprimer les StorageClasses et les `CephBlockPool` **réellement créés** par la
section « Bloc » ci-dessus (réplicat ×3 + les deux variantes EC). Le `delete`
d'une ressource inexistante renvoie `NotFound` sans rien casser.

```bash
# StorageClasses
kubectl delete storageclass rook-ceph-block-replicated rook-ceph-block-ec-delete rook-ceph-block-ec

# Pools (réplicat ×3)
kubectl delete -n rook-ceph cephblockpool rook-ceph-block-replicated-pool
# Pools EC (reclaim Delete)
kubectl delete -n rook-ceph cephblockpool \
  rook-ceph-block-ec-delete-metadata-pool rook-ceph-block-ec-delete-data-pool
# Pools EC (reclaim Retain)
kubectl delete -n rook-ceph cephblockpool \
  rook-ceph-block-ec-metadata-pool rook-ceph-block-ec-data-pool
```

> Adapter si seul un sous-ensemble a été appliqué. La SC objet
> `rook-ceph-datalake` se retire séparément (cf. § Object store ci-dessus). Les
> ressources `rook-ceph-block` / `rook-ceph-block-pool` du dossier
> [`storageClass/examples/`](storageClass/examples/) ne sont **pas** créées par
> ce RUNBOOK (réplicat ×1, démonstration uniquement).

Détruire le cluster Ceph :

```bash
kubectl -n rook-ceph patch cephcluster rook-ceph --type merge \
  -p '{"spec":{"cleanupPolicy":{"confirmation":"yes-really-destroy-data"}}}'
kubectl -n rook-ceph delete cephcluster rook-ceph
kubectl -n rook-ceph get cephcluster
```

Une fois les cleanup pods passés :

```bash
kubectl delete -f operator.yaml
kubectl delete -f common.yaml
kubectl delete -f crds.yaml
```

Enfin, supprimer les données sur les disques avec [`cleanup.sh`](cleanup.sh).
Vérifier sur tous les nœuds :

```bash
lsblk -f
```
