# Portail d'accès aux UI

**Vue unifiée des UI/endpoints de la plateforme** pour l'opérateur
([ADR 0091](/cluster/docs/decisions/0091-portail-acces-ui/)) : qu'est-ce qui est
exposé, sous quel hostname, avec quelle authentification, et **comment récupérer
le credential** — sans jamais l'exposer.

Serveur web **dynamique** servi _dans_ le cluster : il lit l'API k8s en live et
la **croise avec le contrat**
([`contract/endpoints.example.yaml`](/cluster/contract/)), rend une sidebar par
couche avec des **liens en nouvel onglet** (pas d'iframe : `X-Frame-Options`/CSP
des UI l'interdisent). La logique est pure et testée (`nestor/portal.py`,
`tests/test_portal.py`) ; l'I/O + le serveur sont dans
`nestor/portal_server.py`.

## Garde-fous

- **Aucun droit sur les Secrets** : le `ClusterRole` n'a pas de règle `secrets`
  — le portail affiche la **commande** `kubectl`, l'opérateur l'exécute avec ses
  droits (ADR 0091 §3). Même un bug du code ne peut pas lire un Secret (le
  serveur API refuse, 403).
- **Lecture seule** : `get`/`list` sur `services`, `endpointslices`, `gateways`,
  `httproutes`, `applications`. Pod durci (ADR 0014), egress API server
  seulement.

## Fichiers

| Fichier                       | Rôle                                                                                         |
| ----------------------------- | -------------------------------------------------------------------------------------------- |
| `image/Dockerfile`            | image mince (client k8s + pyyaml) ; contrat embarqué ; serveur stdlib                        |
| `portal.yaml`                 | Namespace, ServiceAccount, ClusterRole **sans secrets** + binding, Deployment durci, Service |
| `gateway.yaml`                | exposition Gateway Cilium hostNetwork (`portail.cluster.lan`, TLS interne)                   |
| `../network-policies/portal/` | default-deny + DNS + egress apiserver + ingress HTTP                                         |

## Déploiement

```bash
# 1. image (depuis la racine — contexte = dépôt, contrat embarqué)
nerdctl build -f platform/portal/image/Dockerfile -t registry:80/portal:dev . && \
  nerdctl push registry:80/portal:dev
# 2. RBAC + Deployment + NetworkPolicies + Gateway
kubectl apply -f platform/network-policies/portal/portal-netpol.yaml
kubectl apply -f platform/portal/portal.yaml
kubectl apply -f platform/portal/gateway.yaml
kubectl -n portal rollout status deploy/portal
```

Vérifier qu'il ne peut PAS lire un Secret (garde-fou) :

```bash
kubectl auth can-i get secrets --as=system:serviceaccount:portal:portal   # → no
```

UI : `https://portail.cluster.lan` (hostPort 443 sur l'IP du nœud).
