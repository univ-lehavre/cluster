# Datalake — Object Store

Object store Ceph compatible S3, exposé via RGW (Rados Gateway). Sert de
datalake pour les sources de données ingérées par le cluster.

> ⚠️ **Comportement destructif** : `preservePoolsOnDelete: false` (cf.
> [`datalake-ec.yaml:21`](datalake-ec.yaml#L21)) signifie que **supprimer le
> `CephObjectStore` détruit aussi les pools `datalake.rgw.buckets.data` et
> `datalake.rgw.buckets.index`** — donc **toutes les données et buckets** S3.
> Décision assumée pour ce datalake de recherche (ré-ingestible depuis les
> sources upstream). Pour conserver les pools, passer à
> `preservePoolsOnDelete: true` **avant** toute suppression.
>
> 🔑 **Ordre de suppression** : supprimer les **OBC/buckets AVANT** le
> `CephObjectStore`, sinon deadlock de finalizers (le store attend les buckets,
> l'OBC ne peut plus se deprovisionner). Procédure complète et déblocage :
> [`../../RUNBOOK.md` § Désinstallation › Object store](../../RUNBOOK.md#object-store-datalake--ordre-obligatoire).

## Installation

```bash
kubectl apply -f datalake-ec.yaml
kubectl apply -f storage-class.yaml
```

Le service `rook-ceph-rgw-datalake` créé automatiquement reste accessible depuis
l'intérieur du cluster (`rook-ceph-rgw-datalake.rook-ceph:80`). Pour y accéder
depuis un poste autorisé à parler à l'API K8s :
`kubectl -n rook-ceph port-forward svc/rook-ceph-rgw-datalake 8080:80`.

## Créer une bucket

Créer un fichier de claim (voir
[`object-bucket-claim-example.yaml`](object-bucket-claim-example.yaml) pour un
exemple générique), puis l'appliquer.

Récupérer les credentials (le Secret porte le nom de la bucket) :

```bash
BUCKET=example-source
kubectl get secret "${BUCKET}" -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 --decode
echo
kubectl get secret "${BUCKET}" -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 --decode
echo
```

## Smoke-test end-to-end

[`smoke-test.sh`](smoke-test.sh) déroule un test fonctionnel complet :

1. Applique [`user-smoke.yaml`](user-smoke.yaml) (un
   `CephObjectStoreUser smoke` + un `ObjectBucketClaim smoke` dédié au test,
   séparés des utilisateurs métier).
2. Attend que le `Secret` de credentials soit posé par le provisioner Rook.
3. Récupère `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.
4. **PUT** un fichier dans le bucket, **LIST** le bucket, **GET** le fichier,
   **DIFF** : vérifie que le contenu lu est identique.
5. Cleanup automatique (à désactiver via `KEEP=1`).

Outil S3 utilisé : `mc` (MinIO client, prioritaire) ou `aws` (CLI v2).

### Depuis le poste de contrôle (port-forward automatique)

Pré-requis : un client S3 sur le PATH — `mc` (`brew install minio-mc`) **ou**
`aws` (CLI v2). Le DNS interne `*.svc` n'étant pas résolvable depuis le poste,
le script ouvre **lui-même** un `kubectl port-forward` vers le service RGW et le
referme en sortie. Aucun terminal séparé ni `ENDPOINT` à fournir :

```bash
bash storage/ceph/storageClass/datalake/smoke-test.sh
```

Pour pointer un endpoint externe (NodePort…), surcharger
`ENDPOINT=http://… bash …smoke-test.sh` (court-circuite le port-forward).

### Depuis un pod du cluster (sans port-forward)

```bash
kubectl -n rook-ceph run smoke --rm -it --image=minio/mc -- sh -c "
  apk add --no-cache bash curl
  # … copier smoke-test.sh + user-smoke.yaml dans le pod, puis :
  ENDPOINT=http://rook-ceph-rgw-datalake.rook-ceph:80 \
    bash smoke-test.sh
"
```

(En pratique on lance ça sur le poste de contrôle — le port-forward automatique
rend cette variante intra-pod rarement nécessaire.)

### Lecture attendue

```text
[14:02:00] Apply storage/ceph/storageClass/datalake/user-smoke.yaml …
[14:02:01] Attendre le CephObjectStore datalake Ready (timeout 240s)…
[14:02:02] Attendre qu'un pod RGW soit Ready (timeout 240s)…
[14:02:06] Attendre que le Secret de l'OBC soit créé (timeout 120s)…
[14:02:07] DNS interne non résolvable d'ici → port-forward svc/rook-ceph-rgw-datalake 38080→80
[14:02:08] Endpoint : http://127.0.0.1:38080  | Bucket : smoke  | KeyID : ABCD…
[14:02:08] Outil : mc (MinIO client)
[14:02:08] PUT  → smoke/smoke/upload.txt
[14:02:08] LIST → smoke/smoke
[2026-05-28 14:02:08 UTC]     58B upload.txt
[14:02:08] GET  ← smoke/smoke/upload.txt
[14:02:08] ✓ Contenu lu identique au contenu écrit.
[14:02:08] Stat du bucket :
…
[14:02:08] ✓ Smoke-test datalake : OK
[14:02:08] Cleanup : vide le bucket et supprime OBC + user…
```

Si l'OBC ne converge pas (`Secret smoke pas créé`), inspecter :

```bash
kubectl -n rook-ceph describe obc smoke
kubectl -n rook-ceph logs -l app=rook-ceph-rgw,rook_object_store=datalake
```

## Utilisateur global

Après création d'un utilisateur (voir [`user.yaml`](user.yaml) ou
[`user-datalake.yaml`](user-datalake.yaml)), celui-ci accède à tout l'object
store :

```bash
USER=rook-ceph-object-user-datalake-admin
kubectl -n rook-ceph get secret "${USER}" -o jsonpath='{.data.AccessKey}' | base64 --decode
echo
kubectl -n rook-ceph get secret "${USER}" -o jsonpath='{.data.SecretKey}' | base64 --decode
echo
```
