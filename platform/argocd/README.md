# Argo CD — GitOps applicatif (CA interne, tout-Cilium)

Réconcilie en continu, depuis git, les manifestes **applicatifs** (apps
`citation-*`) et les composants stateful déclarés en `Application` (Dagster,
Marquez). Décision et frontière :
[ADR 0022](/cluster/docs/decisions/0022-argocd-gitops-applicatif/).

| Fichier                                                                                                                                  | Rôle                                                                                            |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| [`argocd.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argocd/argocd.yaml)                                           | Bundle officiel v3.4.3 (3 CRDs+RBAC+Deploys), images par digest, `server.insecure`              |
| [`appproject-atlas.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argocd/appproject-atlas.yaml)                       | `AppProject atlas` cadrant citation-\*/dagster/marquez ; `sourceRepos` surchargeable (ADR 0044) |
| [`gateway.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argocd/gateway.yaml)                                         | `Gateway` + `HTTPRoute` d'exposition UI (TLS bordure cert-manager)                              |
| [`_test/application-guestbook.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/argocd/_test/application-guestbook.yaml) | `Application` guestbook de **test** (validation banc — jetable)                                 |
| [`app-of-apps/`](/cluster/platform/argocd/app-of-apps/)                                                                                  | **App-of-Apps** (ADR 0094) : instanciation déclarative des `Application` applicatives           |

NetworkPolicies sous `platform/network-policies/argocd/`
([`00-default-deny.yaml`](https://github.com/univ-lehavre/cluster/blob/main/platform/network-policies/argocd/00-default-deny.yaml) +
allow-dns/server/egress).

## Frontière Ansible / GitOps (anti-bootstrap-circulaire)

**Argo CD est géré par Ansible/kubectl, PAS par lui-même** (ADR 0022). Règle :
un composant va dans Ansible si le retirer empêcherait Argo CD de démarrer ou de
réconcilier — sinon il va en GitOps. Donc **infra** (Cilium, exposition,
cert-manager, registry, Rook, Argo CD, opérateurs + CRDs) = Ansible ;
**applicatif** (apps + instances stateful déclarées en `Application`) = Argo CD.

## Déploiement

**Automatisé (Ansible, ADR 0022/0044)** : le rôle `platform-argocd` (via
[`bootstrap/gitops.yaml`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/gitops.yaml))
pose Argo CD + les NetworkPolicies + l'`AppProject` + (optionnel) le Gateway, en
`--server-side`. Sur le banc Lima, c'est la phase `gitops`
([`bench/lima/run-phases.sh`](https://github.com/univ-lehavre/cluster/blob/main/bench/lima/run-phases.sh)).
La séquence `kubectl` ci-dessous reste la **référence manuelle** (et ce que le
rôle traduit) :

```bash
# Pré-requis SANS Internet : mirrorer les 3 images dans le registry interne
# (quay.io/argoproj/argocd, ghcr.io/dexidp/dex, .../redis) — ADR 0011 — sinon
# ImagePullBackOff. (Sur le banc Vagrant qui a Internet, le pull direct marche.)
kubectl create namespace argocd
# --server-side OBLIGATOIRE : la CRD applicationsets.argoproj.io dépasse la
# limite d'annotation de l'apply client-side (validé banc, Run #11).
kubectl apply --server-side -n argocd -f platform/argocd/argocd.yaml
kubectl -n argocd rollout status deploy/argocd-server deploy/argocd-repo-server

# NetworkPolicies + AppProject + exposition
kubectl apply -f platform/network-policies/argocd/
kubectl apply -f platform/argocd/appproject-atlas.yaml
kubectl apply -f platform/argocd/gateway.yaml   # après cert-manager + Gateway API
```

> **`server.insecure`** est déjà posé dans `argocd.yaml` (ConfigMap
> `argocd-cmd-params-cm`). Si on l'ajoute après coup,
> `kubectl -n argocd rollout restart deploy/argocd-server` (pas pris à chaud).

## Exposition (tout-Cilium, pas d'ingress-nginx)

L'UI est exposée **en interne** via le `Gateway` Cilium + `HTTPRoute`, TLS
terminé en bordure par cert-manager (CA interne, ADR 0021). `argocd-server` est
en **`--insecure`** : le TLS vit uniquement en bordure (un double-TLS
provoquerait une boucle de redirection). Le hostname `argocd.cluster.lan` est un
**placeholder `.lan`** à fixer avec l'admin réseau.

**CLI gRPC — limitation connue (validée banc, finding #26).** L'**UI et l'API
REST** passent par le `HTTPRoute` sans souci (HTTPS via le Gateway, cert CA
interne). En revanche **`argocd login --grpc-web` NE passe PAS** par le Gateway
Cilium : l'Envoy du Gateway dé-encapsule le gRPC-Web en gRPC natif (h2c) que le
backend `argocd-server:80` (HTTP/1.1) ne reçoit pas → `404`. Faire marcher le
CLI via le Gateway exige un montage `GRPCRoute` +
`appProtocol: kubernetes.io/h2c` sur un **hostname dédié** + le flag opérateur
`gatewayAPI.enableAppProtocol=true` (GEP-1911, opt-in, absent de `cni.sh`) — non
mis en place, à instruire.

**Repli CLI (fiable, court-circuite le Gateway)** :

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:80
PW=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)
argocd login localhost:8080 --username admin --password "$PW" --plaintext
```

## Faire confiance au cert

Le cert du listener est émis par la CA interne (gateway-shim cert-manager). Sans
import du root interne, le navigateur/CLI affiche un avertissement → importer le
`ca.crt` (cf. README de [`cert-manager`](/cluster/platform/cert-manager/)).

## Validation (banc multi-node)

```bash
# Mot de passe admin initial :
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
# Application de test (guestbook) :
kubectl apply -f platform/argocd/_test/application-guestbook.yaml
kubectl -n argocd get application argocd-smoketest-guestbook \
  -o jsonpath='{.status.sync.status}/{.status.health.status}'   # attendu Synced/Healthy
kubectl -n argocd delete application argocd-smoketest-guestbook  # nettoyage
```

## Décisions assumées

- **`--insecure` borné** : OK **uniquement** derrière le TLS de bordure (0021) +
  réseau privé (0003). Jamais sur un cluster exposé.
- **Argo CD ≠ self-managed**, ne gère pas l'infra (frontière 0022).
- **AppProject restreint** : destinations citation-\*/dagster/marquez seulement.
- **Images à mirrorer** (cluster sans Internet, 0011).
- **gRPC via Gateway** : ne fonctionne PAS en l'état (finding #26) — l'UI/REST
  passent, le CLI gRPC-Web non. Repli validé : port-forward (ci-dessus).
- **Validation banc obligatoire avant prod** (Synced/Healthy, UI HTTPS, gRPC).
