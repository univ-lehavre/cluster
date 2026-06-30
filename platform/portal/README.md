# Portail d'accès aux UI

**Vue unifiée des UI/endpoints de la plateforme** pour l'opérateur
([ADR 0091](/cluster/docs/decisions/0091-portail-acces-ui/)) : qu'est-ce qui est
exposé, sur quel **port de nœud** (L4 NodePort,
[ADR 0092](/cluster/docs/decisions/0092-exposition-hostport-l4/)), avec quelle
authentification, et **comment récupérer le credential** — sans jamais
l'exposer.

Serveur web **dynamique** servi _dans_ le cluster : il lit l'API k8s en live et
la **croise avec le contrat**
([`contract/endpoints.example.yaml`](/cluster/contract/)), rend une sidebar par
couche avec des **liens en nouvel onglet** (pas d'iframe : `X-Frame-Options`/CSP
des UI l'interdisent). Chaque UI exposée pointe vers
`http://<IP-nœud>:<nodePort>` — le `nodePort` n'est pas figé : k8s l'attribue et
le portail l'**observe** (`service.spec.ports[].nodePort`) avec l'IP d'un nœud
Ready. La logique est pure et testée (`nestor/portal.py`,
`tests/test_portal.py`) ; l'I/O + le serveur sont dans
`nestor/portal_server.py`.

## Garde-fous

- **Aucun droit sur les Secrets** : le `ClusterRole` n'a pas de règle `secrets`
  — le portail affiche la **commande** `kubectl`, l'opérateur l'exécute avec ses
  droits (ADR 0091 §3). Même un bug du code ne peut pas lire un Secret (le
  serveur API refuse, 403).
- **Lecture seule** : `get`/`list` sur `services`, `nodes`, `endpointslices` (le
  NodePort observé + l'IP du nœud, ADR 0092). Pod durci (ADR 0014), egress API
  server seulement.

## Fichiers

| Fichier                       | Rôle                                                                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| `image/Dockerfile`            | image mince (client k8s + pyyaml) ; contrat embarqué ; serveur stdlib                                 |
| `portal.yaml`                 | Namespace, ServiceAccount, ClusterRole **sans secrets** + binding, Deployment durci, Service NodePort |
| `../network-policies/portal/` | default-deny + DNS + egress apiserver + ingress HTTP                                                  |

## Déploiement

Par le **rôle Ansible** `platform-portal` (chemin codé, ADR 0046) — build de
l'image node-side + RBAC + Deployment + Service NodePort + NetworkPolicies +
gate Ready :

```bash
# banc : layer du chemin `atlas` (topologies/banc.yaml) ; ou phase dédiée :
bench/lima/run-phases.sh portal
# prod : le playbook contre l'inventaire dérivé de la topologie active
nestor ansible portal.yaml -e dataops_k8s_host=localhost
```

> **Tag mutable** : l'image `registry:80/portal:dev` a un tag mutable (le
> code/contrat embarqué évolue). Après un **rebuild** de l'image, le pod ne se
> recrée pas tout seul (Deployment inchangé) → forcer une fois :
> `kubectl -n portal rollout restart deploy/portal`. Le rebuild from-scratch
> recrée le pod de toute façon.

Vérifier qu'il ne peut PAS lire un Secret (garde-fou) :

```bash
kubectl auth can-i get secrets --as=system:serviceaccount:portal:portal   # → no
```

UI (L4, ADR 0092) — le NodePort attribué + l'IP d'un nœud :

```bash
PORT=$(kubectl -n portal get svc portal -o jsonpath='{.spec.ports[0].nodePort}')
IP=$(kubectl get node -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "http://$IP:$PORT"
```
