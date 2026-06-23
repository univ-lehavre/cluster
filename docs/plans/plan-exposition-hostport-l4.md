# Plan — Exposition des UI par hostPort/NodePort L4

## État

> **État : Brouillon** (2026-06-23) · **Fonde :**
> [ADR 0092](../decisions/0092-exposition-hostport-l4.md) (Accepted).

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

- **Source = le contrat** : chaque UI exposée porte un `ui_nodeport` (figé,
  `30000-32767`), unicité validée par `check_contract.py`. Aucun port en double,
  aucun chevauchement avec les ports k8s réservés (6443/10250/2379…).
- **kubeProxyReplacement** (déjà posé) sert NodePort + hostPort en eBPF — pas de
  LB-IPAM, pas de Gateway dans le chemin d'exposition.
- **Vendored non modifiés** : un Service NodePort SÉPARÉ (mêmes labels), jamais
  éditer un chart/bundle (CLAUDE.md).
- **Banc d'abord** : prouvé sur Lima avant dirqual.

## Étapes

### 1. Contrat : `ui_nodeport` + validation d'unicité

- **ÉDITER** `contract/endpoints.example.yaml` : remplacer `ui_hostname` par
  `ui_nodeport` (valeur d'exemple `30000-32767`) sur les UI exposées ; matrice
  de ports réservés en commentaire.
- **ÉDITER** `scripts/check_contract.py` : valider unicité des `ui_nodeport` +
  absence de chevauchement avec les ports k8s réservés.
- **Preuve SANS cluster** : `check_contract` + tests.

### 2. Portail : Service NodePort + liens `http://<IP-nœud>:<port>`

- **ÉDITER** `platform/portal/portal.yaml` : Service `type: NodePort` (nodePort
  figé) OU hostPort sur le conteneur (brique maison). Retirer
  `platform/portal/gateway.yaml`.
- **ÉDITER** `nestor/portal.py` (`_ui_url`/`render_html`) : générer
  `http://<IP-nœud>:<ui_nodeport>` au lieu de `https://<ui_hostname>`. L'IP du
  nœud est injectée (observée via l'API, un nœud Ready). Tests adaptés.
- **Preuve banc** : portail joignable `http://<IP-nœud>:<nodePort>`, liens
  cliquables.

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

- [ ] Étape 1 — contrat `ui_nodeport` + validation
- [ ] Étape 2 — portail NodePort + liens IP:port
- [ ] Étape 3 — UI vendored en NodePort
- [ ] Étape 4 — drift state.sh allowlist
- [ ] Étape 5 — bascule Cilium (retrait LB-IPAM/Gateway)
- [ ] Étape 6 — bascule prod dirqual + preuve e2e
