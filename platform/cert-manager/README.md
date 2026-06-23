# cert-manager — TLS de bordure (CA interne)

Émet et renouvelle les certificats TLS du **Gateway de bordure** Cilium
([ADR 0020](/cluster/docs/decisions/0020-exposition-reseau-tout-cilium/)) via
une **CA interne** — pas ACME, car le cluster n'est pas exposé à Internet.
Décision et justifications :
[ADR 0021](/cluster/docs/decisions/0021-cert-manager-ca-interne/).

| Fichier                                                                                                          | Rôle                                                                                           |
| ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| [`cert-manager.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/cert-manager/cert-manager.yaml) | Bundle officiel v1.20.2 (CRDs+RBAC+Deploys+webhook), images par digest, `--enable-gateway-api` |
| [`issuers.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/cert-manager/issuers.yaml)           | Chaîne CA interne : `selfsigned-bootstrap` → `root-ca` → `internal-ca`                         |

## Déploiement

```bash
# 1) cert-manager (CRDs incluses dans le bundle) :
kubectl apply -f platform/cert-manager/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager deploy/cert-manager-webhook deploy/cert-manager-cainjector

# 2) Chaîne CA interne (après que le webhook est Ready) :
kubectl apply -f platform/cert-manager/issuers.yaml
kubectl get clusterissuer selfsigned-bootstrap internal-ca   # READY=True
kubectl -n cert-manager get certificate root-ca              # READY=True
```

> **Pré-requis Gateway API** : depuis
> l'[ADR 0092](/cluster/docs/decisions/0092-exposition-hostport-l4/) les UI sont
> exposées en **L4** (`NodePort`/`hostPort`, `http://<IP-nœud>:<port>`) — le
> Gateway L7 n'est **plus** dans le chemin d'exposition et l'addon
> `platform/cilium-expo/` a été retiré. cert-manager n'a donc plus besoin des
> CRDs `gateway.networking.k8s.io` pour ce chemin. Le gateway-shim ci-dessous
> reste utilisable si un `Gateway` est posé hors de ce dépôt (chemin de prod
> optionnel) : les CRDs doivent alors préexister, et le contrôleur cert-manager
> démarrer **après** elles (sinon
> `kubectl -n cert-manager rollout restart deploy/cert-manager`).
>
> **Images sans Internet** : le cluster n'étant pas exposé, les images
> `quay.io/jetstack/cert-manager-*` doivent être joignables en egress **ou**
> mirrorées dans le registry interne (ADR 0011), sinon `ImagePullBackOff`.

## Câbler un Gateway (gateway-shim) — optionnel, hors chemin d'exposition des UI

> Les UI de la plateforme sont exposées en L4 (ADR 0092) et ne passent **plus**
> par un Gateway. Ce gateway-shim ne sert donc qu'à un éventuel `Gateway` posé
> hors de ce dépôt (chemin de prod optionnel).

cert-manager émet le certificat d'un `Gateway` quand celui-ci est **annoté** et
porte un listener HTTPS `Terminate` avec un **hostname non vide** :

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: <gw>
  annotations:
    cert-manager.io/cluster-issuer: internal-ca # ← émetteur CA interne
spec:
  gatewayClassName: cilium
  listeners:
    - name: websecure
      protocol: HTTPS
      port: 443
      hostname: gateway.internal.example.lan # non vide (obligatoire)
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: gateway-internal-tls # ← créé/rempli par cert-manager
```

cert-manager crée alors un `Certificate` nommé d'après le Secret, `dnsNames`
dérivé du hostname, renouvelé automatiquement.

## Faire confiance à la racine interne

La racine est self-signed → **non reconnue nativement**. Extraire le `ca.crt` :

```bash
kubectl get secret root-ca-secret -n cert-manager \
  -o jsonpath='{.data.ca\.crt}' | base64 -d > internal-root-ca.crt
```

- **Postes Debian/Ubuntu** : copier dans `/usr/local/share/ca-certificates/`
  puis `update-ca-certificates`. (RHEL : `/etc/pki/ca-trust/source/anchors/` +
  `update-ca-trust` ; macOS : `security add-trusted-cert` ; Windows : magasin «
  Autorités de certification racines de confiance ». Firefox a son propre
  magasin NSS.)
- **Charges intra-cluster** : distribuer via **trust-manager** (`Bundle` →
  `ConfigMap` par namespace) plutôt que monter le Secret directement.

## Décisions assumées

- **CA interne, pas ACME** : cluster non exposé à Internet (ADR 0021).
- **Racine 10 ans / feuilles 90 j** (renouvellement auto). Ne **jamais**
  versionner la clé privée racine (générée dans le cluster).
- **Rotation de la racine** : pré-distribuer la nouvelle racine (double-trust
  via un `Bundle` trust-manager à 2 sources) **avant** de basculer l'émetteur,
  puis renouveler les feuilles, puis retirer l'ancienne.
- **Périmètre = bordure uniquement** : pas de TLS interne pod-to-pod (couvert
  par WireGuard, ADR 0019), pas de mTLS service-to-service.
- **Validation banc multi-node obligatoire avant prod** (voir ADR 0021).
