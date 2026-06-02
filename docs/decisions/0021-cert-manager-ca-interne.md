# 0021 — cert-manager + CA interne (TLS de bordure du Gateway Cilium)

## Contexte

L'ADR [0020](0020-exposition-reseau-tout-cilium.md) a acté une bordure L7
**tout-Cilium** : le `Gateway` (`gateway.networking.k8s.io/v1`,
`controllerName: io.cilium/gateway-controller`) est le point d'entrée unique des
charges, avec routage host/path par `HTTPRoute` et un listener HTTPS en
`mode: Terminate` pointant vers un Secret TLS. Cet ADR-ci traite la
**fabrication et le cycle de vie de ce Secret** — l'étape cert-manager de la
Phase 1 (ex-1.3 du plan), qui suit logiquement l'exposition réseau.

Le cadrage périmètre, déjà posé en 0020, est déterminant : **« bordure » =
bordure du réseau privé, pas Internet.** Le cluster bare-metal kubeadm **4 nœuds
non-HA** (ADR
[0002](0002-control-plane-unique-avec-endpoint.md)/[0009](0009-pourquoi-4-noeuds.md))
est confiné au réseau isolé `10.67.2.0/22` (banc Vagrant `192.168.67.0/24`) et
**n'est pas joignable depuis l'extérieur**. Les IP du pool LB-IPAM sont
annoncées sur le **LAN interne** (L2) ; le Gateway sert des **clients internes**
(LAN/VPN), jamais Internet. Conséquence directe et déjà annoncée en 0020 :
**ACME/Let's Encrypt est exclu** — les challenges HTTP-01 et DNS-01 supposent
une autorité publique capable de joindre le cluster (ou un DNS public délégué),
ce que l'isolement réseau interdit. Une **CA interne** s'impose donc.

Articulation avec le modèle de menace de l'ADR
[0003](0003-pas-de-chiffrement-ceph-tailscale.md) (mono-tenant recherche, réseau
privé, mono-admin, pas de données réglementées) : 0003 **délègue la sécurité du
transport au contrôle d'accès réseau** et écarte le TLS interne (msgr2/LUKS
Ceph) pour son coût. Le chiffrement **pod-to-pod inter-nœuds** est par ailleurs
déjà couvert par **WireGuard** (ADR [0019](0019-durcissement-reseau-cilium.md)).
La question ici est **distincte** : on n'introduit **pas** de TLS interne
pod-to-pod (toujours hors périmètre), mais un **TLS de bordure** — terminaison
HTTPS au Gateway pour les clients internes du LAN. C'est l'ajout cohérent qui
manquait : aujourd'hui un client interne parle au Gateway sans confidentialité
ni authentification du service.

## Décision

Déployer **cert-manager** avec un **émetteur à CA interne** (PAS ACME), pour
fournir au listener HTTPS du Gateway (ADR 0020) ses certificats de bordure. Tout
est versionné sous [`platform/cert-manager/`](../../platform/cert-manager/), aux
côtés de `platform/cilium-expo/` (0020).

### 1. cert-manager — méthode et version épinglées

Installation par **manifeste statique épinglé** (v1.20.2, images par digest —
calque [`platform/metrics-server/`](../../platform/metrics-server/)), dans le
namespace `cert-manager`, CRDs incluses dans le bundle. cert-manager apporte le
contrôleur qui réconcilie les CR `Certificate`/`Issuer`/`ClusterIssuer`, gère
l'émission, le stockage en `Secret` `kubernetes.io/tls`, et surtout le
**renouvellement automatique** avant expiration. La version est ajoutée à la
matrice de versions (ADR
[0006](0006-matrice-de-versions-et-politique-de-bump.md)).

### 2. Chaîne de confiance — CA interne self-signed (racine → émetteur)

Pas de `ClusterIssuer` ACME. On construit une **chaîne à deux niveaux** (pattern
officiel « Bootstrapping CA Issuers ») :

1. un `ClusterIssuer` **`selfSigned`** (`selfsigned-bootstrap`) sert uniquement
   à émettre la **racine** (un `Certificate` CA, `isCA: true`, validité longue,
   10 ans), stockée dans le Secret `root-ca-secret` du namespace `cert-manager`
   ;
2. un `ClusterIssuer` de type **`ca`** (`internal-ca`) référence ce Secret
   racine et devient l'**émetteur courant** des certificats feuilles (validité
   courte, 90 j, renouvellement auto).

Ce niveau isole la racine : seul l'émetteur `ca` est sollicité au quotidien, la
clé racine n'est exposée qu'à l'émission/rotation. `ClusterIssuer` (et non
`Issuer` namespacé) car la bordure peut servir plusieurs namespaces applicatifs.
Le Secret racine **doit** vivre dans le « cluster resource namespace » du
contrôleur (`--cluster-resource-namespace`, défaut `cert-manager`).

### 3. Intégration Gateway API (gateway-shim)

Le listener HTTPS du `Gateway` Cilium est servi par cert-manager via le
**gateway-shim** : on annote le `Gateway`
(`cert-manager.io/cluster-issuer: internal-ca`) et le `certificateRefs` du
listener (`tls.mode: Terminate`, hostname **non vide**) pointe vers un Secret
que cert-manager **crée et renouvelle** depuis le hostname du listener. Le
couplage est déclaratif et convergent, sans Secret géré à la main.

> **Activation (important).** Depuis cert-manager **1.15**, le support Gateway
> API n'est **plus** un feature-gate (`ExperimentalGatewayAPISupport` est
> obsolète) : il s'active par le flag dédié **`--enable-gateway-api`** sur le
> contrôleur (ou `config.enableGatewayAPI: true` en Helm), **non activé par
> défaut**. Posé dans le manifeste. Les CRDs Gateway API v1.4.1 sont déjà
> pré-installées (0020) ; le contrôleur cert-manager doit démarrer **après**
> elles (sinon le redémarrer).

### 4. Distribution de la racine aux clients internes

La racine étant self-signed, **aucun navigateur/OS ne la reconnaît nativement**.
Sa distribution aux clients internes est traitée explicitement, deux voies :

- **intra-cluster** : **trust-manager** (composant cert-manager) publie le
  bundle racine dans des `ConfigMap` par namespace, pour les charges qui
  appellent la bordure en interne (source dédiée, pas le Secret cert-manager
  directement) ;
- **postes/navigateurs du LAN** : **import manuel** du certificat racine dans le
  magasin de confiance (procédure dans le README de `platform/cert-manager/`).

## Statut

Accepted (2026-06-02).

## Conséquences

**Bénéfices.**

- **TLS de bordure réel** pour les clients internes : confidentialité et
  authentification du service au Gateway, là où le trafic LAN→Gateway était en
  clair — complément cohérent de WireGuard (0019, pod-to-pod) sans introduire de
  TLS interne (0003 préservé).
- **Renouvellement automatique** des feuilles (validité courte) : pas de
  certificat expiré à surveiller à la main.
- **Une seule autorité commune** : un seul root à importer côté clients, toute
  charge derrière le Gateway en hérite.
- **Déclaratif et convergent** : CR versionnés sous `platform/cert-manager/`.
- **Porte de sortie ACME ouverte** : si le cluster s'ouvrait à Internet,
  basculer sur un `ClusterIssuer` ACME est un changement local (le gateway-shim
  et les `Certificate` ne bougent pas).

**Prix à payer.**

- **Certificats NON reconnus nativement** sans **import préalable de la racine**
  : avertissement de sécurité tant que le root n'est pas dans le magasin de
  confiance du client. Coût assumé d'une CA interne sur cluster non joignable
  par une autorité publique.
- **Gestion et rotation de la racine** à porter : actif sensible ; sa rotation
  impose de **re-distribuer** le nouveau root à tous les clients internes —
  opération coordonnée.
- **Un composant de plus** à opérer/patcher/superviser (cert-manager,
  +éventuellement trust-manager), suivi dans la matrice de versions (0006).
- **Images à mirrorer** : cluster sans Internet → `quay.io/jetstack/*` doivent
  être joignables ou pré-chargées dans le registry interne (ADR 0011), sinon
  `ImagePullBackOff`.

**Garde-fous.**

- **Racine protégée** : Secret de la racine en accès restreint (RBAC) ; émetteur
  `ca` séparé du `selfSigned` pour limiter l'exposition de la clé racine. Ne
  **jamais** versionner la clé privée racine (elle est générée dans le cluster).
- **Rotation documentée** : procédure de rotation de la racine **et** de
  re-distribution (trust-manager + import manuel) dans
  `platform/cert-manager/README.md` ; échéance de la racine tracée.
- **Validation banc** (multi-node, comme 0019/0020) : un `Certificate` feuille
  émis par `internal-ca`, le Secret TLS apparaît, le listener HTTPS du Gateway
  sert ce certificat, un client ayant **importé le root** valide la chaîne sans
  avertissement ; le **renouvellement** automatique est vérifié.
- **Cohérence périmètre** : on **n'active pas** de TLS interne pod-to-pod (reste
  WireGuard/0019) ni de mTLS service-to-service — cert-manager se limite à la
  **bordure** (0003 inchangé).

## Alternatives écartées

**ACME / Let's Encrypt (`ClusterIssuer` ACME).** Chemin par défaut pour des
certificats reconnus publiquement, sans CA à gérer. **Écarté de fait** par le
périmètre (ADR 0020) : le cluster `10.67.2.0/22` est **isolé, non joignable
depuis Internet**, sans domaine public délégué — **HTTP-01** (autorité publique
→ Gateway) comme **DNS-01** (enregistrement dans une zone publique) sont
**injoignables/inapplicables**. ACME reste la porte de sortie si le cluster
s'ouvre un jour.

**Certificats auto-signés par service (sans CA commune).** Un self-signed
indépendant par hostname. Écarté : **pas de chaîne de confiance partagée** —
chaque certificat serait à importer un par un (N imports au lieu d'un root),
aucun renouvellement automatique, aucune révocation cohérente. La CA interne
mutualise la confiance en **un** root et délègue le renouvellement à
cert-manager.

**Pas de TLS du tout (HTTP nu au Gateway).** Le plus simple, cohérent au premier
abord avec 0003 (réseau privé). Écarté : **contredit l'objectif de TLS de
bordure** de 0020 (listener HTTPS `Terminate`), laisse le trafic LAN→Gateway en
clair et sans authentification du service. La défense en profondeur retenue
ailleurs (WireGuard, 0019) justifie d'apporter la confidentialité de bordure.
