# 0022 — Argo CD (GitOps applicatif)

## Contexte

La Phase 1 du plan relève le socle cluster ; après l'exposition réseau
([ADR 0020](0020-exposition-reseau-tout-cilium.md)) et le TLS de bordure
([ADR 0021](0021-cert-manager-ca-interne.md)), l'**étape 1.4** introduit le
**GitOps applicatif** : réconcilier en continu, depuis git, les manifestes des
applications (apps `citation-*`) et des composants stateful de plateforme
déclarés en `Application` (Dagster, Marquez, plus tard CloudNativePG). Il manque
aujourd'hui une boucle déclarative qui détecte le drift entre l'état git
(désiré) et l'état cluster (réel) et le résorbe.

Le contexte cluster cadre la décision : bare-metal kubeadm, **4 nœuds non-HA**
(control-plane unique = SPOF,
[ADR 0002](0002-control-plane-unique-avec-endpoint.md)/[ADR 0009](0009-pourquoi-4-noeuds.md))
; **tout-Cilium** — Gateway API + LB-IPAM + L2, kube-proxy remplacé par eBPF
([ADR 0020](0020-exposition-reseau-tout-cilium.md)) ; **cert-manager + CA
interne** pour le TLS de bordure ([ADR 0021](0021-cert-manager-ca-interne.md)) ;
cluster **isolé, non joignable depuis Internet**
([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)) ; **registry interne
HTTP sans auth** ([ADR 0011](0011-registry-http-sans-auth.md)) ; **default-deny
Cilium** ([ADR 0019](0019-durcissement-reseau-cilium.md)).

Deux conséquences directes cadrent l'ADR. (1) **Pas d'Internet** : les images
Argo CD doivent être **mirrorées** dans le registry interne (0011), sinon
`ImagePullBackOff`. (2) **Risque de bootstrap circulaire** : si l'outil GitOps
gérait l'infra (CNI, exposition, cert-manager) ou se gérait lui-même, on
créerait une dépendance œuf-poule (le cluster ne converge pas sans l'outil,
l'outil ne démarre pas sans le cluster convergé). La question : quel outil,
exposé comment (cohérence tout-Cilium), avec quelle frontière de responsabilité
?

## Décision

Adopter **Argo CD** comme moteur GitOps **applicatif**, dans le namespace
`argocd`, versionné sous [`platform/argocd/`](../../platform/argocd/).

### 1. Installation épinglée, images mirrorées

Manifeste statique **épinglé** : Argo CD **v3.4.3** (la branche stable en 2026 ;
**testée K8s 1.32-1.35** donc 1.34 — les lignes 2.x ne supportent **pas** 1.34),
bundle officiel `install.yaml` (3 CRDs `argoproj.io` + RBAC + workloads),
**images par digest** (calque [`metrics-server`](../../platform/metrics-server/)
et `cert-manager`). Version dans la matrice
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)). Cluster **sans
Internet** : les 3 images (`quay.io/argoproj/argocd`, `ghcr.io/dexidp/dex`,
`…/redis`) sont **mirrorées dans le registry interne**
([ADR 0011](0011-registry-http-sans-auth.md)) — pré-requis bloquant.

### 2. UI exposée EN INTERNE via le Gateway Cilium (PAS ingress-nginx)

Cohérence stricte avec le tout-Cilium
([ADR 0020](0020-exposition-reseau-tout-cilium.md)) : l'UI est exposée **en
interne** (clients LAN/VPN, jamais Internet) via le **`Gateway` Cilium** + une
**`HTTPRoute`**, le listener HTTPS terminant le TLS avec un **certificat
cert-manager** (CA interne, [ADR 0021](0021-cert-manager-ca-interne.md),
gateway-shim : annotation `cert-manager.io/cluster-issuer` → Secret rempli
automatiquement). `argocd-server` tourne en **`--insecure`**
(`server.insecure: "true"` dans `argocd-cmd-params-cm`) : le **TLS est terminé
en bordure**, un double-TLS provoquerait une boucle de redirection. **Aucun
ingress-nginx** (abandonné en 0020). Le hostname est un **placeholder `.lan`** à
fixer avec l'admin réseau. **CLI gRPC** : `argocd login <host> --grpc-web` (un
seul `HTTPRoute` suffit alors pour l'UI et le CLI).

### 3. AppProject de cadrage

Un **`AppProject atlas`** (`argoproj.io/v1alpha1`) restreint les `Application` :
destinations limitées à **`citation-*`**, **`dagster`**, **`marquez`** ; sources
git listées ; cluster-scoped réduit à `Namespace` (CRD/ClusterRole blacklistés).
Argo CD **ne déploie pas hors de ce périmètre applicatif**.

### 4. FRONTIÈRE Ansible (infra) / GitOps (applicatif)

Frontière **non négociable** pour éviter le **bootstrap circulaire**. Critère :
un composant va dans Ansible **si, et seulement si, le retirer empêcherait Argo
CD de démarrer ou de réconcilier**. Donc **infra** (kubeadm, Cilium/exposition,
cert-manager, registry, Rook, metrics-server, **Argo CD lui-même**, opérateurs +
CRDs) = **Ansible/kubectl** ; **applicatif** (apps `citation-*` + instances
stateful déclarées en `Application` : Cluster CNPG, Dagster, Marquez) = **Argo
CD**. **Argo CD ne gère ni l'infra ni lui-même** — un cluster reconverge d'abord
par Ansible, _puis_ Argo CD prend la main sur l'applicatif. Règle de la zone
grise : **CRDs + opérateurs = Ansible ; les CR (objets custom) = GitOps**.

## Statut

Accepted (2026-06-03).

## Conséquences

**Bénéfices.**

- **Réconciliation déclarative continue** des apps : git = source de vérité,
  drift applicatif détecté/résorbé, statut `Synced/Healthy` observable.
- **Frontière claire** infra (Ansible, convergent par script) vs applicatif
  (GitOps) — pas de zone grise, pas de bootstrap circulaire.
- **Cohérence tout-Cilium** : UI exposée par le seul mécanisme de bordure
  (Gateway + HTTPRoute + cert-manager), aucun second contrôleur d'ingress.
- **Déclaratif et tracé** : tout sous `platform/argocd/`, version dans la
  matrice (0006) ; `AppProject` borne le périmètre.

**Prix à payer.**

- **+1 composant** (server/repo-server/redis/application-controller/dex) à
  opérer/patcher/superviser sur un cluster **non-HA** (0002/0009).
- **`--insecure` sur `argocd-server`** : acceptable **UNIQUEMENT** parce que le
  TLS est **terminé en bordure** (0021) **et** que le réseau est **privé/isolé**
  (0003) — à ne **jamais** transposer à un cluster exposé.
- **gRPC via le Gateway** : à valider sur banc (implémentation Gateway API
  récente) ; repli `--grpc-web` retenu, sinon port-forward.
- **Images à mirrorer** : sans Internet, oubli = `ImagePullBackOff` (0011).

**Garde-fous.**

- **`--insecure` borné** : derrière la terminaison TLS de bordure (0021) et le
  réseau privé (0003) seulement ; porte de sortie documentée si ouverture.
- **`AppProject` restreint** : destinations `citation-*`/`dagster`/`marquez`,
  sources git listées — Argo CD ne déborde pas sur l'infra.
- **Frontière infra/app testée** : **aucune** `Application` ne cible un addon
  d'infra ni `argocd` lui-même (anti-circularité ; pas de self-management).
- **Default-deny préservé** (0019) : `platform/network-policies/argocd/`
  (default-deny + allow-dns + server-ingress + repo/apiserver-egress).
- **Validation banc** (`test/multi-node`) : une `Application` de test passe
  **`Synced/Healthy`** ; l'UI répond en HTTPS via le Gateway (cert CA interne,
  root importé) ; le CLI `--grpc-web` fonctionne à travers la `HTTPRoute`.

## Alternatives écartées

**Flux CD.** Alternative crédible et légère. **Écarté** au profit d'Argo CD pour
son **UI intégrée** (visualisation drift/health, utile en mono-admin recherche)
et son modèle **`AppProject`** qui borne nativement le périmètre — exactement le
cadrage voulu. Choix d'outillage, non d'architecture : la frontière infra/app
vaudrait identiquement avec Flux.

**Tout-Ansible sans GitOps.** **Écarté** : perd la **réconciliation déclarative
continue** des apps (Ansible est push impératif ponctuel, pas une boucle de
convergence). Ansible reste pertinent pour l'**infra** (d'où la frontière).

**Exposer Argo CD via ingress-nginx.** **Écarté** : **incohérent avec
[ADR 0020](0020-exposition-reseau-tout-cilium.md)** (tout-Cilium, ingress-nginx
abandonné). Dupliquerait un datapath de bordure que le Gateway couvre déjà.

**Argo CD gérant l'infra et/ou se gérant lui-même.** App-of-apps couvrant CNI,
exposition, cert-manager, Argo CD. **Écarté** : **bootstrap circulaire** —
l'outil ne converge pas sans le cluster, le cluster (infra) ne converge pas sans
l'outil. La frontière Ansible(infra)/GitOps(applicatif) tranche la dépendance.
