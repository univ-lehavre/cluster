# 0092 — Exposition des UI par `hostPort`/`NodePort` L4 (`http://<IP-nœud>:<port>`, zéro DNS)

## Statut

Accepted (2026-06-23)

**Amende l'[ADR 0071](0071-exposition-gateway-hostnetwork.md)** : ré-ouvre et
**retient** l'alternative que cet ADR avait explicitement écartée (le L4
`hostPort`/`NodePort` par workload, ADR 0071 §Alternatives), au détriment de la
bordure L7 (Gateway hostNetwork, SNI, TLS de bordure). C'est un **renversement
de mécanisme**, pas un réglage marginal : il est donc acté par un ADR distinct,
jamais par une édition silencieuse de 0071 (cf. CLAUDE.md « décisions
structurantes via ADR »).

Réconcilie l'[ADR 0091](0091-portail-acces-ui.md) §4 (qui annonçait déjà «
`hostPort` sur l'IP du nœud » en prose alors que le manifeste implémentait un
Gateway L7). Conserve la prémisse réseau de l'ADR 0071 /
[ADR 0003](0003-reseau-prive.md) (réseau privé, vue admin). N'affecte pas
l'[ADR 0023](0023-plateforme-exemple-generique/) : toutes les IP/ports
ci-dessous sont des valeurs d'exemple génériques (réseau privé `10.0.0.0/22`,
nœuds `cp1`/`node1`…).

## Contexte

L'[ADR 0071](0071-exposition-gateway-hostnetwork.md) a fait du **Gateway exposé
en hostNetwork** (80/443 sur l'IP du nœud, multiplexage SNI sur 443, terminaison
TLS par cert-manager — [ADR 0021](0021-cert-manager-ca-interne.md)) le mode
d'exposition unique câblé. Sa thèse centrale écarte explicitement le L4
`hostPort` par workload : « sert 80/443 sur l'IP du nœud mais perd le routage
L7, le SNI et le TLS de bordure ; il faudrait un reverse-proxy applicatif par
service » (ADR 0071, §Alternatives écartées). NodePort y est écarté de même («
la plage `30000-32767` ne donne pas 80/443 »).

**Fait nouveau décisif — la topologie d'accès opérateur.** Le poste opérateur
atteint le **réseau des nœuds** (sous-réseau d'exemple `10.0.2.0/24`, IP des
nœuds `cp1`=`10.0.2.11`…) mais **n'atteint pas** :

- le **réseau LB-IPAM / L2** (sous-réseau d'exemple `10.0.3.0/24`, où vivent les
  IP virtuelles annoncées en ARP) ;
- le **DNS** des hostnames de plateforme (`*.example.lan`), qui ne résolvent
  nulle part côté poste opérateur — ce sont des **placeholders**
  ([ADR 0048](0048-acces-local-developpeur.md)).

Or le Gateway L7 d'ADR 0071 **exige un hostname** pour router : le listener 443
sélectionne le backend par **SNI**, donc par nom — donc par une **résolution
DNS** côté client. Sans DNS, atteindre une UI derrière le Gateway impose le
bricolage `/etc/hosts` (ADR 0048) ou un `curl --resolve` par hostname. Le besoin
réel — « ouvrir l'UI depuis le poste opérateur, sans rien configurer » — n'est
**pas** servi.

**Le L4 sur l'IP du nœud lève exactement ce verrou** : `http://<IP-nœud>:<port>`
est routable directement (le poste atteint déjà `10.0.2.x`), **sans aucun DNS,
sans aucune IP LB-IPAM**. L'utilisateur a tranché : « on ne fait pas de LB-IPAM
mais du `hostPort` » / « et si on utilisait simplement les ports du nœud hôte ».

**Fait technique habilitant (vérifié).** `kubeProxyReplacement=true` est déjà
posé (`bootstrap/cni.sh`) ; en Cilium 1.19 ce seul flag **active déjà NodePort +
HostPort + ExternalIPs** en eBPF (les flags `--enable-*` ont disparu). Donc
`hostPort` **et** `NodePort` fonctionnent **sans LB-IPAM**, déjà câblés — c'est
le même chemin eBPF qui sert aujourd'hui le `hostPort 1025` de mailpit
(exception tracée d'ADR 0071). Le mécanisme demandé est donc présent ; il s'agit
de **l'employer pour les UI** au lieu de le réserver à une exception.

## Décision

**Les UI de la plateforme sont exposées en L4, par un port du nœud, accès
`http://<IP-nœud>:<port>`. Zéro DNS, zéro LB-IPAM, zéro Gateway dans le chemin
d'exposition.**

### 1. Mécanisme par UI : `NodePort` par défaut, `hostPort` pour les briques maison

- **Service `type: NodePort`** est le mécanisme **par défaut** pour les UI
  livrées par **charts Helm / bundles vendored** (grafana via
  `kube-prometheus-stack`, argocd, dagster, gitea, kubernetes-dashboard…). Le
  Service NodePort est un objet **séparé** qui **ne touche ni le pod ni le
  chart** (CLAUDE.md interdit d'éditer les bundles vendored à la main) : il
  sélectionne les mêmes labels que le Service ClusterIP existant et Cilium-eBPF
  route `NodeIP:<nodePort>` → endpoints. Le `nodePort` n'est **PAS figé** : k8s
  l'attribue automatiquement dans `30000-32767`, et le **portail OBSERVE** le
  port réel (`service.spec.ports[].nodePort`) via l'API pour construire le lien
  — pas de matrice de ports à maintenir, pas de collision à valider (cf. §3).
- **`hostPort` sur le conteneur** reste admis pour les **briques dont on possède
  le manifeste** (portal, mailpit) : modèle mailpit (`hostPort` posé directement
  sur le conteneur, port `> 1023` → **pas de capability `NET_BIND_SERVICE`**).
- **Pourquoi trancher ainsi** : `hostPort` exige d'éditer le manifeste du
  workload ; tout chart n'expose pas de values pour poser un `hostPort` sur
  _son_ conteneur (le bundle argocd figé n'a pas de values Helm). `hostPort` sur
  vendored est donc une **impasse partielle** → NodePort obligatoire là,
  hostPort acceptable seulement là où le manifeste est à nous. Les deux
  empruntent le même eBPF.

### 2. Ce qu'on perd, et pourquoi c'est acceptable ici

- **TLS de bordure (cert-manager, [ADR 0021](0021-cert-manager-ca-interne.md))**
  : en L4 le pod reçoit du TCP brut. Les UI servent en **HTTP clair** sur le
  port du nœud (la plupart le sont déjà côté backend : argocd `server.insecure`,
  grafana, portal). On passe de `https://<host>` à `http://<IP>:<port>`.
- **Multiplexage SNI sur 443** : un port = une UI. Plus de 443 partagé.
- **`HTTPRoute` + hostname** : tout le mécanisme
  `Gateway`/`HTTPRoute`/`hostname` devient inutile pour l'exposition.

**Acceptable** parce que : (a) le réseau est **privé** et la vue est **admin**
([ADR 0003](0003-reseau-prive.md)) ; (b) les hostnames `*.example.lan`
n'apportaient déjà aucune valeur côté opérateur (placeholders non résolus) ; (c)
le multiplexage SNI en hostNetwork était lui-même **non prouvé end-to-end** dans
ADR 0071 (un seul listener 443 partagé, « Non vérifié »), donc l'argument
anti-L4 était déjà affaibli. La régression de **posture TLS** est réelle et
**assumée** : elle est le prix de « zéro DNS ». Un retour au TLS (TLS natif par
UI, ou réintroduction du Gateway) reste possible sans nouvel ADR contraire si la
topologie d'accès change (DNS/LB-IPAM ouverts au poste opérateur).

### 3. Allocation des ports : NodePort AUTO, port OBSERVÉ (pas figé)

Le `nodePort` n'est **PAS déclaré ni figé** : k8s l'attribue automatiquement
dans `30000-32767` (alloué à la création du Service, garanti unique par
l'apiserver — pas de matrice à maintenir ni de collision à valider). Le
**contrat `contract/endpoints.example.yaml`** ne déclare donc qu'un booléen
**`exposed: true`** (en remplacement de `ui_hostname`) : « cette UI est exposée
en L4 », sans porter le port. Le **portail OBSERVE le port réel** à chaque
chargement (`service.spec.ports[].nodePort` + l'IP d'un nœud Ready) → le lien
`http://<IP-nœud>:<nodePort>` reste juste même si le Service est recréé.

Compromis assumé (décision opérateur) : l'URL d'une UI **peut changer** si son
Service NodePort est recréé (k8s réattribue un port). C'est acceptable car le
portail est le point d'entrée unique et affiche toujours le port courant — on ne
mémorise jamais une URL figée. En contrepartie : zéro gestion de plage, zéro
risque de collision avec un port déjà pris du nœud (l'apiserver exclut la plage
système). `check_contract.py` valide la **correspondance** `exposed: true` ↔
Service NodePort `<service>-nodeport` (ancrage versionné), pas un numéro de
port.

Les `hostPort` de briques maison (mailpit SMTP, port `1025`) prennent un port
**`> 1023`** fixé dans leur manifeste (on en possède le YAML), hors
`30000-32767`.

### 4. Contrôle de drift (`state.sh`, allowlist)

`bootstrap/state.sh` marque aujourd'hui **tout Service `NodePort`/`LoadBalancer`
comme un drift** (allowlist actuelle : `kubernetes-dashboard` en dur + Services
portés par un Gateway via le label `gateway.networking.k8s.io/gateway-name`).
Passer les UI en NodePort sans amender ce contrôle ferait de **chaque UI un
`fail`**. La décision **amende `state.sh`** pour allowlister les expositions L4
d'UI, par le **mécanisme self-déclaratif** déjà en place : un **label
conventionnel** posé par le chemin codé (sur le modèle du label Gateway),
**plutôt** qu'une liste de noms en dur. Une nouvelle section inspecte aussi les
`hostPort` de pods (`.spec.containers[*].ports[*].hostPort`) — contrôle qu'ADR
0071 **annonçait** mais qui n'était en réalité **jamais câblé** (le `hostPort`
1025 de mailpit passait sous le radar car mailpit est un ClusterIP). L'exception
est **tracée par cet ADR** (modèle de l'exception mailpit d'ADR 0071).

### 5. Le portail génère `http://<IP-nœud>:<port>`

Le portail cesse d'observer le hostname via `HTTPRoute` et observe le
**`nodePort` réel** lu sur le Service (`spec.ports[].nodePort`) ; il construit
`http://<IP>:<nodeport>` à partir de (a) l'**IP d'un nœud Ready** et (b) du
**`nodePort` observé** (jamais un port déclaré). Le verdict de drift devient «
déclaré `exposed: true` mais aucun `nodePort` observé » (Service NodePort
manquant), au lieu de « hostname réel ≠ attendu ». L'**IP du nœud** est lue via
`list_node` (InternalIP d'un nœud Ready) : le RBAC du portail gagne
`nodes get/list` et perd `gateways/httproutes/applications` (devenus morts). En
multi-nœuds, l'IP affichée est celle d'un nœud Ready quelconque (un NodePort
répond sur tout nœud ; le portail n'en présente qu'une). Les NetworkPolicy d'UI
suivent le modèle portal/mailpit : `allow-*-ingress` ouvrant le
**containerPort** (pas le nodePort) **sans bloc `from:`** (la source vient du
nœud, pas d'un pod sélectionnable), plus `allow-dns-egress` sous default-deny
([ADR 0019](0019-durcissement-reseau.md)).

### 6. Sort du Gateway / HTTPRoute / LB-IPAM existant (dirqual)

- Les `Gateway`/`HTTPRoute` (8 manifestes `platform/*/gateway.yaml`) et le
  manifeste `platform/portal/gateway.yaml` sont **retirés** du chemin
  d'exposition, remplacés par des Services NodePort (ou `hostPort` pour portal).
- Le `GatewayClass` cilium et les CRD restent inoffensifs ; cni.sh peut tourner
  en mode `none` (ni hostNetwork ni LB-IPAM) — les **capabilities Envoy 80/443**
  d'ADR 0071 deviennent **inutiles**.
- Le **bug Cilium #42786** (`Gateway .status.Programmed: False` menteur en
  hostNetwork, ADR 0071) **disparaît** : plus de Gateway, plus de `.status`
  trompeur. Le gate de readiness redevient un simple `curl http://<IP>:<port>`.
- **Sur dirqual** (déployé en LB-IPAM) la bascule **désarme** LB-IPAM : `cni.sh`
  est **additif** côté pool (il pose le `CiliumLoadBalancerIPPool` /
  `CiliumL2AnnouncementPolicy` quand `LB_IPAM=1` mais **ne les supprime pas**
  quand `=0`). Le retrait des CR résiduels (`default-pool`, `default-l2`) se
  fait **explicitement** (`kubectl delete`), sinon CR orphelins. La bascule sur
  cluster vivant **re-roule le DaemonSet cilium** (churn datapath transitoire,
  by-design) ; aucun repointage DNS n'est requis côté opérateur puisque l'accès
  passe désormais par l'IP du nœud, déjà routable.

### 7. Modèle de configuration (`nestor`)

`hostport` **redevient un mode d'exposition distinct** : il n'est plus un
**alias de `gateway`** (l'alias `hostport→gateway` est retiré, `gateway` n'est
plus le seul mode L7 câblé). La détection (`detect_exposition`) reconnaît le
mode L4 par la présence de Services NodePort d'UI. La prémisse d'ADR 0071 — VM
mono-NIC, pas de plage IP — reste vraie et **mieux servie** par L4.

## Conséquences

**Positives**

- **Zéro DNS, zéro LB-IPAM** : accès `http://<IP-nœud>:<port>` immédiat depuis
  le poste opérateur, sans `/etc/hosts` ni `--resolve`, sans plage IP négociée.
- **Chemin plus court** : pas de cert-manager ni de gateway-shim dans
  l'exposition, pas de CRD Gateway requise, **pas de bug `Programmed`** ; preuve
  from-scratch raccourcie ([ADR 0034](0034-validation-e2e-from-scratch.md)).
- **Réconciliation** de la prose d'ADR 0091 avec l'implémentation.
- Câblage drift `hostPort`/NodePort **enfin réel** (ADR 0071 l'annonçait sans
  l'implémenter).

**Négatives / coûts assumés**

- **Perte du TLS de bordure** : UI en **HTTP clair** sur le réseau privé. À
  acter explicitement ; vérifier au banc que chaque UI répond en HTTP clair
  (argocd OK via `server.insecure`, à confirmer pour grafana/dagster — cookies
  `Secure`/`SameSite`, en-têtes CSP/X-Frame-Options d'ADR 0091).
- **Un port par UI** : plus de 443 partagé ; le port est **auto-attribué** par
  k8s (pas de registre au contrat, pas de collision à valider — cf. §3).
- **Surface amendée** : `contract/endpoints.example.yaml` (`exposed: true`,
  retrait `ui_hostname`), `nestor/portal.py` + `nestor/portal_server.py`
  (observer le `nodePort` réel + l'IP nœud via `list_node`, générer
  `http://IP:port`),
  `platform/portal/{portal.yaml (Service NodePort + RBAC nodes),README.md}`
  (retrait `gateway.yaml`), 7× `platform/*/nodeport.yaml` (Services NodePort des
  UI vendored) + retrait des 7× `platform/*/gateway.yaml` et de
  `platform/cilium-expo/`, `bootstrap/cni.sh` (L4 pur, retrait des CR
  résiduels), `bootstrap/state.sh` (allowlist NodePort du contrat),
  `scripts/check_contract.py` (ancrage `nodeport`), `tests/test_portal.py` +
  `tests/test_check_contract.py`.

**Risques à PROUVER au banc (jamais présumer —
[ADR 0046](0046-corriger-le-code-pas-l-etat/) /
[ADR 0052](0052-reproductibilite-des-resultats/))**

- NodePort non allowlisté ⇒ `fail` silencieux au prochain audit `state.sh`.
- UI refusant l'HTTP clair (cookies/headers) — tester grafana/dagster.
- Choix de l'**IP affichée** en multi-nœuds (control-plane désigné).
- Signal de couche : vérifier que le Service NodePort porte bien le
  `(namespace, service)` attendu du contrat (mémoire
  _signal-couche-nom-reel-vs-attendu_), sinon verdict MISSING/DRIFT erroné.
- **Cibler explicitement le banc** : sans kubeconfig banc, les commandes
  retombent sur la PROD (mémoire _isolation-banc-prod-kubeconfig-fallback_).

## Voir aussi

- [Plan de mise en œuvre](../plans/plan-exposition-hostport-l4.md) — les 6
  étapes (contrat `exposed: true` → portail/UI NodePort → drift → bascule Cilium
  → prod).
- [ADR 0071](0071-exposition-gateway-hostnetwork.md) — Exposition Gateway
  hostNetwork (**amendé/renversé** par le présent ADR pour l'exposition des UI).
- [ADR 0091](0091-portail-acces-ui.md) — Portail d'accès aux UI (prose
  **réconciliée** avec l'implémentation L4).
- [ADR 0020](0020-exposition-reseau-tout-cilium.md) — Exposition tout-Cilium
  (LB-IPAM/L2, désormais chemin de prod optionnel).
- [ADR 0048](0048-acces-local-developpeur.md) — Accès local développeur
  (bricolage `/etc/hosts` rendu inutile).
- [ADR 0003](0003-reseau-prive.md) — Réseau privé (justifie l'HTTP clair).
- [ADR 0021](0021-cert-manager-ca-interne.md) — cert-manager / CA interne (hors
  du chemin d'exposition L4).
- [ADR 0019](0019-durcissement-reseau.md) — Durcissement réseau / default-deny
  (NetworkPolicy `allow-*-ingress` sans `from:`).
- [ADR 0023](0023-plateforme-exemple-generique/) — Valeurs génériques.

---
