# 0073 — hubble-ui : activer l'UI d'observabilité réseau

## Statut

Proposed (2026-06-15). **Amende
l'[ADR 0019](0019-durcissement-reseau-cilium.md)** (section « 2. Hubble + Relay,
sans UI ») : l'exclusion de l'UI y était délibérée mais conditionnelle («
évaluer Hubble UI si un besoin de visualisation émerge, avec accès restreint »,
0019 « À revoir »). Le besoin émerge → on lève l'exclusion **sous condition
d'opt-in et d'exposition encadrée**, sans renier la posture de non-exposition
de 0019.

> **Note (ADR [0092](0092-exposition-hostport-l4.md), 2026-06-23).** Le
> mécanisme d'exposition a depuis basculé du Gateway L7 (cilium-expo) vers le
> **L4** (`NodePort`, `http://<IP-nœud>:<port>`). Quand hubble-ui est activé, il
> est donc exposé par un **Service `NodePort`** (et non plus un
> `Gateway`/`HTTPRoute`) ; les références ci-dessous au Gateway cilium-expo et
> au patron `gateway.yaml` décrivent l'intention d'origine et restent valables
> sur le plan de la **gouvernance d'opt-in**, mais le datapath d'exposition
> actuel est L4. La conciliation avec 0019 (opt-in, défaut désactivé) est
> inchangée.

## Contexte

L'ADR 0019 a activé Hubble + Relay **sans UI** dans
[`bootstrap/cni.sh`](../../bootstrap/cni.sh) (lignes 93-95 :
`--set hubble.enabled=true --set hubble.relay.enabled=true`, commentaire
L76-79). Le refus de l'UI y est **argumenté, pas accidentel** : « le dashboard
web ajouterait un Service et une surface exposée à protéger, sans valeur pour un
cluster mono-admin » ([0019 L62-64](0019-durcissement-reseau-cilium.md)). Le
modèle de menace de fond ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md))
reste : mono-tenant, réseau privé `10.0.0.0/22` isolé, mono-admin.

Deux choses ont changé depuis 0019 (2026-06-02) :

1. **L'exposition tout-Cilium existe**
   ([ADR 0020](0020-exposition-reseau-tout-cilium.md)) : Gateway API +
   cert-manager (CA interne, [ADR 0021](0021-cert-manager-ca-interne.md))
   forment désormais **une bordure unique, tracée et TLS-terminée** pour les UI
   web (Grafana, Argo CD, Gitea…). Exposer une UI n'est plus « ajouter une
   surface non maîtrisée » mais « brancher une UI de plus sur une bordure déjà
   gouvernée ». L'objection centrale de 0019 (« surface exposée à protéger »)
   perd de sa force : la protection existe.
2. **Un portail développeur consomme ces UI**
   ([ADR 0048](0048-acces-local-developpeur.md)) :
   [`bench/lima/access.sh`](../../bench/lima/access.sh) dérive du **contrat**
   ([`contract/endpoints.example.yaml`](../../contract/endpoints.example.yaml))
   les UI à exposer (champ `ui_hostname`, regroupées par `layer`). Hubble UI
   trouve naturellement sa place dans le `layer: monitoring`, aux côtés de
   Grafana et Mailpit.

La demande : disposer de la **carte de service** Hubble (graphe des flux
L3/L4/L7, verdicts policy, drops en temps réel) pour diagnostiquer visuellement
une `NetworkPolicy` ou un flux inattendu — ce que `hubble observe` en CLI rend
austère. La question n'est donc pas « pour ou contre l'UI » mais **où la poser,
par quel datapath l'exposer, et active par défaut ou non**, sans contredire
frontalement 0019.

## Décision

Rendre **hubble-ui activable** (désactivé par défaut), servi par la **même
brique Cilium** que Hubble/Relay, et exposé — quand activé — par la **bordure
Gateway** de l'ADR 0020 (jamais par un Service brut).

### 1. Brique : hubble-ui dans `cni.sh` (avec Cilium), PAS dans `monitoring.yaml`

Hubble UI est un **sous-chart du chart Helm Cilium**, pas un composant
indépendant. On l'active via une valeur Helm posée sur la **même release
Cilium** que Hubble/Relay, dans [`bootstrap/cni.sh`](../../bootstrap/cni.sh), à
côté des lignes existantes (94-95) :

```sh
# Observabilité réseau : Hubble + Relay (ADR 0019), UI optionnelle (ADR 0073).
--set hubble.enabled=true
--set hubble.relay.enabled=true
```

… et, conditionnellement (cf. §3) :

```sh
--set hubble.ui.enabled=true
```

**Pourquoi `cni.sh` et pas
[`bootstrap/monitoring.yaml`](../../bootstrap/monitoring.yaml).** Le déposer
dans la couche monitoring imposerait soit un **second Helm release**
(`cilium/hubble-ui` standalone), soit un manifeste vendored — dans les deux cas
**découplé de la ligne de version Cilium** (`CILIUM_VERSION=1.19.4`,
[cni.sh L8](../../bootstrap/cni.sh)). C'est précisément la dispersion que les
ADR 0019 et 0020 combattent : _une seule matrice de versions à suivre, la ligne
Cilium_ ([0020 L120-122](0020-exposition-reseau-tout-cilium.md)). hubble-ui doit
**vivre et bouger avec** son backend (hubble-relay) et son datapath (l'agent
Cilium). Conséquence : hubble-ui est dans le namespace **`kube-system`** (où
vivent tous les composants Cilium, cf. [cni.sh L140](../../bootstrap/cni.sh)),
appliqué à l'install **et** à l'upgrade → convergent en rejouant le script (même
invariant que le durcissement 0019 et l'exposition 0020).

Articulation avec [ADR 0016](0016-observabilite.md) inchangée : 0016 =
observabilité **métrologique** (Prometheus/Grafana) ; Hubble = observabilité
**réseau**, **autonome** (l'UI n'exige pas Prometheus). Aucun recouvrement, donc
aucune raison de la faire transiter par la couche monitoring.

### 2. Exposition : via Gateway (ADR 0020), jamais par défaut, jamais en Service brut

Quand hubble-ui est activé, son exposition suit **strictement** le patron
Grafana/Argo CD
([`platform/kube-prometheus-stack/gateway.yaml`](../../platform/kube-prometheus-stack/gateway.yaml))
: TLS **terminé en bordure** (annotation
`cert-manager.io/cluster-issuer: internal-ca`,
[gateway.yaml L15](../../platform/kube-prometheus-stack/gateway.yaml)), backend
HTTP clair, `Gateway` + `HTTPRoute` (`gateway.networking.k8s.io/v1`). Le
manifeste vit sous [`platform/cilium-expo/`](../../platform/cilium-expo/) (la
référence versionnée des CRs d'exposition Cilium,
[cni.sh L84](../../bootstrap/cni.sh)), p. ex.
`platform/cilium-expo/hubble-ui-gateway.yaml`, namespace `kube-system`, hostname
d'exemple générique `hubble.cluster.lan` (placeholder `.lan`, ADR 0023/0021).

**Le Service `hubble-ui` reste ClusterIP.** L'unique point d'entrée externe est
le **Gateway** — exception déjà tracée en couche 7b de
[`bootstrap/state.sh`](../../bootstrap/state.sh) (allowlist par label
`gateway.networking.k8s.io/gateway-name`,
[state.sh L808-811](../../bootstrap/state.sh)). Aucune nouvelle exception à
ajouter : le Gateway hubble-ui est couvert par l'allowlist existante.

> **Note (ADR 0071)** : depuis l'exposition du Gateway en **hostNetwork**, ce
> Gateway n'a **plus** de `Service type=LoadBalancer` — l'Envoy bind 80/443 sur
> l'IP du nœud. Le patron HTTPRoute/TLS ci-dessus est inchangé ; seul le point
> d'entrée passe d'une IP LoadBalancer à l'IP du nœud. Le principe #25 («
> services applicatifs en ClusterIP, exposition **uniquement** par la bordure
> Gateway ») demeure intact — c'est exactement ce que 0019 voulait préserver,
> désormais garanti **par la bordure 0020 au lieu de l'absence d'UI**.

### 3. Activation : opt-in (désactivé par défaut), piloté par l'intention

Par défaut, **hubble-ui n'est PAS déployé** (`hubble.ui.enabled` non posé) et
**aucun Gateway hubble-ui n'est appliqué**. L'activation est une **intention**
explicite (ADR [0065](0065-variables-env-intention-vs-etat.md)), via une
variable sur le modèle de `CILIUM_EXPO_ENABLED`
([cni.sh L39](../../bootstrap/cni.sh)) :

```sh
HUBBLE_UI_ENABLED="${HUBBLE_UI_ENABLED:-0}"   # 0 = pas d'UI (défaut, ADR 0019)
```

- `HUBBLE_UI_ENABLED=1` → ajoute `--set hubble.ui.enabled=true` aux
  `CILIUM_ARGS`, **et** (si `CILIUM_EXPO_ENABLED=1`, prérequis Gateway) applique
  `platform/cilium-expo/hubble-ui-gateway.yaml`.
- défaut `0` → comportement **strictement inchangé** vs 0019 : relay + CLI, pas
  d'UI, pas de surface.

Ce défaut opt-in est le **cœur de la conciliation avec 0019** : la posture de
non-exposition reste le défaut du catalogue ; l'UI est un **choix de
déploiement** assumé, jamais imposé. Côté banc Lima, l'activation peut être
dérivée d'un profil/topologie (comme `WITH_CEPH`/`WITH_HARDENING`, cf.
CLAUDE.md), jamais codée en dur.

### 4. Contrat : entrée hubble-ui en `layer: monitoring`

Ajouter au contrat
([`contract/endpoints.example.yaml`](../../contract/endpoints.example.yaml),
bloc « UI de la plateforme » L125+) une entrée `hubble-ui` modelée sur
`grafana-ui`/`mailpit-ui`
([endpoints L132-154](../../contract/endpoints.example.yaml)) :
`namespace: kube-system`, `service: hubble-ui`, `layer: monitoring`,
`auth: none` (réseau privé, ADR 0003), `ui_hostname: hubble.cluster.lan`,
`source: platform/cilium-expo/hubble-ui-gateway.yaml`. `access.sh` la prendra en
charge **automatiquement** (il itère sur les `ui_hostname` dont le Service
existe, [access.sh L99-109/137-143](../../bench/lima/access.sh)) : si hubble-ui
n'est pas déployé, le Service est absent → l'UI est simplement ignorée
(`warn … Gateway non posé`), aucune régression.

## Conséquences

**Bénéfices.**

- **Diagnostic réseau visuel** (graphe de service, flux, drops, verdicts policy)
  pour instruire une `NetworkPolicy` ou un flux inattendu, là où
  `hubble observe` CLI suffisait au quotidien mais pas à l'exploration.
- **Zéro nouvelle brique à opérer** : hubble-ui suit la version Cilium (une
  seule matrice), s'expose par la bordure Gateway déjà gouvernée (0020) et
  apparaît dans le portail (0048) sans code spécifique.
- **Défaut sûr préservé** : sans opt-in, le cluster est identique à l'état 0019
  (pas d'UI, pas de surface). La décision 0019 reste vraie « par défaut ».

**Coûts assumés.**

- **Une surface web de plus quand activée.** C'est l'objection historique de
  0019 ; elle est **atténuée** (TLS CA interne, réseau privé isolé, bordure
  Gateway unique tracée en state.sh) mais non nulle. Acceptée **seulement** sous
  opt-in explicite.
- **Empreinte** : hubble-ui = un Deployment (frontend + backend) supplémentaire
  dans `kube-system` (cluster hyperconvergé 4 nœuds, ADR 0009) — borné par les
  `requests/limits` par défaut du sous-chart, à vérifier au banc.
- **`hubble.ui.enabled` via upgrade** : comme WireGuard (0019) et l'exposition
  (0020), `cilium upgrade` met à jour la ConfigMap/les sous-charts mais le
  rollout déjà forcé par `cni.sh` ([L139-141](../../bootstrap/cni.sh)) couvre le
  déploiement du Pod UI ; vérifier au banc que hubble-ui passe `Running` après
  bascule à chaud.

**Validation (à produire).** Run banc multi-node avec `HUBBLE_UI_ENABLED=1` :
Pod `hubble-ui` `Running` dans `kube-system`, Gateway `hubble.cluster.lan`
programmé (IP LB du pool), UI joignable en TLS via la CA interne (`access.sh`
forward + URL cliquable), graphe de flux non vide. **Et** un run avec le défaut
`0` prouvant l'**absence** de Pod/Service/Gateway hubble-ui (la non-régression
de 0019). Idempotence : rejeu `cni.sh` → `changed=0` (ADR 0052).

## À revoir si

- Le cluster s'ouvre **au-delà du mono-tenant / réseau isolé** (rappel
  0003/0019) : alors l'UI exige une **authentification** devant la bordure (le
  `auth: none` du contrat ne tient plus) — brancher un backend d'auth sur le
  Gateway avant d'élargir l'accès.
- Une stack de **métriques Hubble** (`hubble.metrics`) est branchée sur
  Prometheus (palier évoqué en
  [0019 « À revoir »](0019-durcissement-reseau-cilium.md)) : réévaluer le
  recoupement entre dashboards Grafana et UI Hubble.
- Un **upgrade majeur de Cilium** change le nom de valeur `hubble.ui.enabled` ou
  le packaging du sous-chart : réaligner `cni.sh`.

## Alternatives écartées

**Activer hubble-ui par défaut.** Simple, mais contredit frontalement la posture
de non-exposition de 0019 et fait porter une surface web à **tout** déploiement
du catalogue, y compris ceux qui n'en veulent pas. Écarté : l'UI est un choix,
pas un défaut. L'opt-in préserve la décision 0019 comme comportement nominal.

**Poser hubble-ui dans `bootstrap/monitoring.yaml` (couche observabilité).**
Regrouperait toutes les UI d'observabilité au même endroit. Écarté : forcerait
un Helm release ou un manifeste **découplé de la ligne Cilium**, recréant la
dispersion de versions/datapaths que 0019/0020 ont éliminée. hubble-ui doit
suivre son backend Cilium, donc rester dans `cni.sh`.

**Exposer hubble-ui par un Service `type=LoadBalancer` direct (sans Gateway).**
Donnerait une IP dédiée plus vite. Écarté : pas de terminaison TLS de bordure,
pas de routage host, et **contredit le principe #25 / l'exception unique de
state.sh** ([L808-811](../../bootstrap/state.sh)) — l'exposition passe par la
bordure Gateway, point. Régression de gouvernance.

**`cilium hubble ui` (port-forward CLI, sans déployer le Pod UI).** La commande
Cilium CLI ouvre un port-forward vers une UI éphémère. Écarté comme **socle** :
non reproductible/non tracé côté code (ADR 0046/0052), geste d'opérateur que
0048 cherche justement à supprimer. Reste utile en **dépannage ponctuel**, pas
comme mode d'exposition versionné.
