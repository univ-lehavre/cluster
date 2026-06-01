# 0019 — Durcissement réseau Cilium (WireGuard + Hubble)

## Contexte

Le CNI Cilium ([`bootstrap/cni.sh`](../../bootstrap/cni.sh)) était installé de
façon **minimale** : version épinglée + un seul réglage fonctionnel (pod CIDR
disjoint). Aucun durcissement spécifique au plan réseau n'était configuré ni
tracé :

- **chiffrement du trafic pod-to-pod** : absent (trafic en clair sur le réseau
  inter-nœuds) ;
- **observabilité réseau** (flux, drops, identités) : Hubble désactivé ;
- aucun ADR ne couvrait ces points — contrairement au durcissement du plan de
  contrôle ([ADR 0014](0014-durcissement-kubeadm-init.md)).

Le modèle de menace est rappelé par
[ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md) : cluster **mono-tenant**
de recherche, **réseau privé isolé** `10.67.2.0/22`, **mono-admin**, pas de
données réglementées. L'ADR 0003 délègue explicitement la sécurité du transport
au contrôle d'accès au réseau et **écarte le chiffrement Ceph** (in-transit
msgr2 et at-rest LUKS) pour son coût CPU et la gestion de clés (KMS/Vault) qu'il
imposerait.

La question posée ici est distincte de 0003 : non pas « faut-il chiffrer Ceph »,
mais « peut-on ajouter une **défense en profondeur** au niveau du réseau
**pods** à faible coût, sans réintroduire la complexité que 0003 a refusée ? ».

## Décision

Activer deux fonctions Cilium, appliquées par `cni.sh` (à l'install **et** à
l'upgrade, donc convergentes en rejouant le script).

### 1. Chiffrement transparent WireGuard (pod-to-pod) — **activé**

`--set encryption.enabled=true --set encryption.type=wireguard`.

- Chiffre le trafic **pod-to-pod inter-nœuds** via une interface `cilium_wg0`
  par nœud (mesh WireGuard entre tous les agents).
- **Cilium gère les clés tout seul** (génération, rotation, distribution via le
  control plane K8s) : pas de KMS ni de Vault à inventer — c'était précisément
  l'objection de l'ADR 0003 au LUKS Ceph. WireGuard lève cette objection.
- On reste sur le chiffrement **pod-to-pod** et **pas** `nodeEncryption` (trafic
  host-to-host) : plus intrusif et susceptible de gêner les health-checks pour
  un gain marginal dans notre modèle.
- Pré-requis : module kernel `wireguard` (présent sur Debian 13, kernel ≥ 5.6).

Pourquoi malgré le réseau privé de 0003 : WireGuard est ici une **couche
additionnelle peu coûteuse** (overhead WireGuard < chiffrement msgr2 Ceph), pas
un remplacement du rempart périmétrique. Elle réduit l'impact d'un attaquant qui
passerait **sur** le réseau cluster (le coût assumé n° 1 de l'ADR 0003 : «
sniffer tout le trafic »). Le trafic **Ceph OSD↔OSD** lui-même reste non chiffré
au niveau msgr2 (choix 0003 inchangé) ; mais comme il transite par le réseau
pods, il bénéficie indirectement du tunnel WireGuard inter-nœuds.

### 2. Hubble + Relay (observabilité réseau), **sans UI** — **activé**

`--set hubble.enabled=true --set hubble.relay.enabled=true`.

- Donne `hubble observe` (flux L3/L4/L7, identités, verdicts policy, drops) en
  **CLI**, utile pour diagnostiquer une `NetworkPolicy` (cf. scénario 11) ou un
  flux inattendu.
- **Pas de Hubble UI** : le dashboard web ajouterait un Service et une surface
  exposée à protéger, sans valeur pour un cluster **mono-admin**. Le relay + CLI
  suffit.

Articulation avec [ADR 0016](0016-observabilite.md) : 0016 traite
l'observabilité **métrologique** (metrics-server, Prometheus différé). Hubble
est l'observabilité **réseau** — axe complémentaire, sans recouvrement. Hubble
reste **autonome** (pas de Prometheus requis pour `hubble observe`).

## Statut

Accepted (2026-06-02).

## Conséquences

**Bénéfices.**

- Trafic pod-to-pod inter-nœuds **chiffré** sans gestion de clés (défense en
  profondeur qui atténue le coût assumé n° 1 de l'ADR 0003).
- Visibilité réseau (`hubble observe`) pour le diagnostic des policies et des
  flux, sans dashboard exposé.
- Les deux fonctions sont **tracées et activées par défaut** dans `cni.sh` :
  plus un trou silencieux, et tout cluster reconverge en rejouant le script.

**Coûts assumés.**

- **Léger surcoût CPU/latence** WireGuard sur le trafic inter-nœuds (inférieur
  au chiffrement msgr2 Ceph écarté en 0003).
- **Bascule à chaud = `HEALTH_WARN` transitoire.** Activer WireGuard sur un
  cluster live roule le DaemonSet `cilium` → reconstruction du datapath → Ceph
  signale brièvement des « slow OSD heartbeats » (constaté sur banc : retour
  `HEALTH_OK` en ~70 s). **En prod : appliquer hors heure de pointe.**
- `cilium upgrade` seul ne suffit pas : il met à jour la ConfigMap sans rouler
  les agents (le config-drift-checker signale alors
  `enable-wireguard actual=false`). `cni.sh` **force donc un `rollout restart`**
  des agents après upgrade, puis **vérifie** `cilium encrypt status` et échoue
  si WireGuard n'est pas réellement actif (un durcissement silencieusement
  inactif est pire qu'un échec visible).

**Validation.** Banc multi-node (3 nœuds, K8s 1.34.8, Cilium 1.19.4), Run #6 :
WireGuard actif `Encryption: Wireguard (3/3 nodes)`, interface `cilium_wg0` avec
2 peers par nœud, `hubble observe` retourne les flux réels, Ceph `HEALTH_OK`
après reconvergence. Scénario reproductible :
[`test/scenarios/14-cilium-encryption-hubble.sh`](../../test/scenarios/14-cilium-encryption-hubble.sh).

## À revoir

- Si le cluster s'ouvre au-delà du mono-tenant / réseau isolé : envisager
  `nodeEncryption`, et reconsidérer le chiffrement Ceph msgr2 (ADR 0003) qui
  redeviendrait pertinent.
- Si une stack de métrologie arrive (palier 2 de l'ADR 0016) : brancher les
  métriques Hubble (`hubble.metrics`) sur Prometheus, et évaluer Hubble UI si un
  besoin de visualisation émerge (avec accès restreint).
- Rotation des clés WireGuard : gérée par Cilium ; vérifier le comportement lors
  d'un futur upgrade majeur de Cilium.
