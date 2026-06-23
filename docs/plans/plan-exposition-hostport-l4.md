# Plan — Exposition des UI par hostPort/NodePort L4

## État

> **État : Actif** (2026-06-23) · **Fonde :**
> [ADR 0092](../decisions/0092-exposition-hostport-l4.md) (Accepted). Étapes 1-4
> livrées (codées + validées sans cluster) ; 5-6 = preuve banc/prod.

Applique le passage Gateway-L7 → L4 (`http://<IP-nœud>:<port>`, zéro DNS).
Supersede le mécanisme
d'[ADR 0071](../decisions/0071-exposition-gateway-hostnetwork.md).

## ADR fondateurs

- [0092](../decisions/0092-exposition-hostport-l4.md) — la décision (NodePort
  par défaut, hostPort pour briques maison, zéro DNS/LB-IPAM).
- [0071](../decisions/0071-exposition-gateway-hostnetwork.md) (superseded) — le
  Gateway L7 qu'on remplace ;
  [0043](../decisions/0043-contrat-interface-cluster-atlas.md) (contrat,
  `ui_nodeport`) ; [0003](../decisions/0003-reseau-prive.md) (réseau privé).

## Invariants

- **NodePort AUTO, port OBSERVÉ (décision user)** : on ne fige PAS le `nodePort`
  au contrat — k8s l'attribue dans `30000-32767`, et le **portail lit le port
  réel** (`service.spec.ports[].nodePort`) via l'API à chaque chargement. Les
  liens sont donc toujours justes même si le port change (recréation du
  Service). Conséquence : pas de matrice de ports à gérer, pas de collision à
  valider ; le contrat ne déclare PLUS `ui_hostname` ni `ui_nodeport` (l'accès =
  `exposed: true`).
- **kubeProxyReplacement** (déjà posé) sert NodePort + hostPort en eBPF — pas de
  LB-IPAM, pas de Gateway dans le chemin d'exposition.
- **Vendored non modifiés** : un Service NodePort SÉPARÉ (mêmes labels), jamais
  éditer un chart/bundle (CLAUDE.md).
- **Banc d'abord** : prouvé sur Lima avant dirqual.

## Étapes

### 1. Contrat : `exposed: true` (NodePort auto, port non figé)

- **ÉDITER** `contract/endpoints.example.yaml` : remplacer `ui_hostname` par un
  booléen `exposed: true` sur les UI à exposer en NodePort. Le port n'est PAS
  déclaré (k8s l'attribue, le portail l'observe).
- **ÉDITER** `scripts/check_contract.py` : valider que chaque `exposed: true` a
  un Service NodePort correspondant (étape 3) et inversement.
- **Preuve SANS cluster** : `check_contract` + tests.

### 2. Portail : Service NodePort + liens `http://<IP-nœud>:<nodePort observé>`

- **ÉDITER** `platform/portal/portal.yaml` : Service `type: NodePort`. Retirer
  `platform/portal/gateway.yaml`.
- **ÉDITER** `nestor/portal_server.py` (`observe_cluster`) : lire le `nodePort`
  réel des Services exposés (`service.spec.ports[].node_port`) + l'IP d'un nœud
  Ready (`list_node`). Plus de lecture des HTTPRoutes/hostnames.
- **ÉDITER** `nestor/portal.py` : `Observed` gagne `node_port`/`node_ip` ; l'URL
  devient `http://<node_ip>:<node_port>` (au lieu de `https://<hostname>`). Le
  verdict MATCH/DRIFT se fonde sur présence + readiness + NodePort observé.
  Tests adaptés (plus de `ui_hostname`).
- **Preuve banc** : portail joignable, liens `http://<IP-nœud>:<nodePort>`
  justes.

### 3. UI vendored : Services NodePort séparés

- **CRÉER** `platform/<brique>/nodeport.yaml` (ou un `platform/exposition/`) :
  un Service NodePort par UI (grafana, argocd, dagster, mlflow, gitea,
  marquez-web, k8s-dashboard), sélectionnant les labels du Service ClusterIP
  existant.
- **ÉDITER** le déploiement de chaque brique pour appliquer son NodePort.
- **Preuve banc** : chaque UI répond sur `http://<IP-nœud>:<nodePort>`.

### 4. Drift `state.sh` : allowlist NodePort/hostPort

- **ÉDITER** `bootstrap/state.sh` : allowlister les NodePort/hostPort déclarés
  au contrat (au lieu de les marquer drift). Le contrat est la source de
  l'allowlist.
- **Preuve** : `state.sh` ne signale plus les NodePort du contrat comme drift.

### 5. Bascule Cilium : retirer LB-IPAM + Gateway

- **ÉDITER** `bootstrap/cni.sh` : ne plus poser le `CiliumLoadBalancerIPPool` ni
  le Gateway/HTTPRoute par défaut (L4 pur). `GatewayClass` retiré si plus aucun
  Gateway.
- **Retirer** les `gateway.yaml`/HTTPRoute des briques (argocd…) → remplacés par
  NodePort (étape 3).
- **Preuve banc** : aucun Gateway/pool LB-IPAM ; toutes les UI en NodePort.

### 6. Bascule prod dirqual + preuve e2e

- **dirqual** (mutation opérateur) : retirer `default-pool`
  (`CiliumLoadBalancerIPPool`), helm upgrade Cilium sans LB-IPAM, appliquer les
  NodePort. argocd passe de `10.67.3.240` → `http://10.67.2.11:<nodePort>`.
- **Scénario** : étendre `28-ui-reachable.sh` / `32-portal.sh` pour sonder
  `http://<IP-nœud>:<nodePort>` (au lieu du Gateway/SNI).
- **Preuve** : depuis le poste opérateur (qui atteint `10.67.2.x`), les UI + le
  portail s'ouvrent directement, zéro DNS.

## Suivi

- [x] Étape 1 — contrat `exposed: true` (9 entrées ; port non figé)
- [x] Étape 2 — portail observe le NodePort + liens `http://<IP-nœud>:<port>`
- [x] Étape 3 — UI vendored en NodePort (7 Services séparés + câblage rôles)
- [x] Étape 4 — drift `state.sh` allowlist contrat + `check_contract` ancrage
      NodePort
- [~] Étape 5 — bascule Cilium L4 pur CODÉE (cni.sh sans Gateway/LB-IPAM +
  retrait CR résiduels ; 7 gateway.yaml + cilium-expo supprimés ;
  access.sh/scénarios 28-32/docs refondus en L4) ; reste la **preuve banc** (cni
  L4 + UI NodePort + state.sh 0 drift)
- [ ] Étape 6 — bascule prod dirqual + preuve e2e
