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

## Installation

```bash
kubectl apply -f datalake-ec.yaml
kubectl apply -f storage-class.yaml
```

Pour exposer le service via Tailscale (**si le Tailscale operator est
déployé**), annoter le service `rook-ceph-rgw-datalake` créé automatiquement :

```yaml
metadata:
  annotations:
    tailscale.com/expose: 'true'
    tailscale.com/hostname: datalake
```

Sans Tailscale, le service reste accessible depuis l'intérieur du cluster
(`rook-ceph-rgw-datalake.rook-ceph:80`) ou via
`kubectl -n rook-ceph port-forward svc/rook-ceph-rgw-datalake 8080:80`.

## Créer une bucket

Créer un fichier de claim (voir
[`object-bucket-claim-gdelt.yaml`](object-bucket-claim-gdelt.yaml) pour un
exemple), puis l'appliquer.

Récupérer les credentials :

```bash
BUCKET=stormglass
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

### Depuis le poste de contrôle (via port-forward)

```bash
# 1. Port-forward le service RGW dans un autre terminal :
kubectl -n rook-ceph port-forward svc/rook-ceph-rgw-datalake 8080:80

# 2. Lancer le smoke-test :
ENDPOINT=http://localhost:8080 \
  bash storage/ceph/storageClass/datalake/smoke-test.sh
```

### Depuis un pod du cluster (sans port-forward)

```bash
kubectl -n rook-ceph run smoke --rm -it --image=minio/mc -- sh -c "
  apk add --no-cache bash curl
  # … copier smoke-test.sh + user-smoke.yaml dans le pod, puis :
  ENDPOINT=http://rook-ceph-rgw-datalake.rook-ceph:80 \
    bash smoke-test.sh
"
```

(En pratique on lance ça sur le poste de contrôle après port-forward — c'est
plus simple.)

### Lecture attendue

```text
[14:02:00] Apply storage/ceph/storageClass/datalake/user-smoke.yaml …
[14:02:01] Attendre que le Secret de l'OBC soit créé (timeout 60s)…
[14:02:08] Endpoint : http://localhost:8080  | Bucket : smoke  | KeyID : ABCD…
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
