# NetworkPolicies — micro-segmentation est-ouest (audit P6 #22)

`default-deny` par namespace + `allow` ciblés sur les workloads maison
(`default` = WordPress/MySQL, `rstudio`, `registry`). **Durcissement
defense-in-depth**, pas une correction de faille : l'absence de NetworkPolicy
était un compromis assumé du mono-tenant
([ADR 0012](../../docs/decisions/0012-rstudio-disable-auth.md)). Ces policies
posent une barrière est-ouest pour qu'un pod compromis ne puisse pas balayer
librement le cluster.

## Portée

- **Couverts** : `default`, `rstudio`, `registry`.
- **NON couverts (volontairement)** :
  - `rook-ceph` — infra Ceph/CSI vendored ; verrouiller ses flux (mon/osd/rgw)
    casserait le stockage. Hors périmètre de ce premier jet.
  - `kubernetes-dashboard` — déployé par chart Helm, pas de manifeste natif ici.
  - `kube-system` — composants système (CoreDNS, Cilium).

## Principe de chaque namespace

1. `00-default-deny.yaml` : un `NetworkPolicy` qui sélectionne **tous** les pods
   (`podSelector: {}`) et nie **ingress + egress**. À partir de là, plus rien ne
   passe sauf ce qui est explicitement ré-autorisé.
2. `allow-dns` : **indispensable** — sans lui, le deny-all egress coupe la
   résolution DNS (CoreDNS, `kube-system`) et casse tout. Autorise UDP/TCP 53
   vers `kube-system`.
3. Allow métier ciblés (ingress/egress strictement nécessaires).

> ⚠️ **Pré-requis label sur kube-system.** Les règles DNS ciblent `kube-system`
> via `namespaceSelector`. K8s ≥ 1.21 pose automatiquement le label immuable
> `kubernetes.io/metadata.name: kube-system`, utilisé ici — aucune action
> requise. (Vérifiable : `kubectl get ns kube-system --show-labels`.)

## Flux autorisés (résumé)

| Namespace  | Ingress                                                              | Egress                                          |
| ---------- | -------------------------------------------------------------------- | ----------------------------------------------- |
| `default`  | wordpress:80 depuis n'importe où ; mysql:3306 ⬅ wordpress uniquement | DNS ; wordpress → mysql:3306 ; API server :6443 |
| `rstudio`  | rstudio:8787 depuis n'importe où (Service/Tailscale)                 | DNS ; API server :6443                          |
| `registry` | registry:5000 depuis n'importe où (pulls de tout le cluster)         | DNS ; API server :6443                          |

**Volontairement permissif** sur l'ingress des Services exposés (wordpress,
rstudio, registry) : ils sont conçus pour être joignables (LoadBalancer /
Tailscale). La valeur de ces policies est ailleurs : **isoler MySQL** (seul
WordPress y accède), **bloquer tout egress non listé** (un pod compromis ne peut
pas exfiltrer ni scanner), et **poser un cadre** pour durcir plus finement
ensuite.

> Note Ceph : l'accès au stockage RBD/CephFS passe par le **kubelet** (montage
> noyau), pas par le réseau pod — il n'est donc PAS bloqué par ces policies et
> n'a pas besoin d'allow explicite. Idem health/readiness probes (kubelet →
> pod), exemptées par Cilium.

## Application

```bash
# Dans l'ordre : le default-deny d'abord, puis les allow.
kubectl apply -f platform/network-policies/default/
kubectl apply -f platform/network-policies/rstudio/
kubectl apply -f platform/network-policies/registry/
```

## Validation (banc multi-nœuds)

À exécuter sur le banc Lima [`test/lima/`](../../test/lima/) **avant la prod** :

- `kubectl get netpol -A` → les policies présentes par namespace.
- WordPress répond toujours (ingress :80) et lit/écrit MySQL (DNS +
  `wordpress → mysql:3306` OK).
- Un pod de test dans `default` **ne peut pas** joindre `mysql:3306` (seul le
  pod `tier: frontend` est autorisé) ni un egress arbitraire.
- DNS fonctionne depuis chaque namespace (`nslookup kubernetes.default`).
- Le provisionnement/montage des PVC reste OK (preuve que Ceph n'est pas
  impacté).

Cf. [SAFEGUARDS.md](../../SAFEGUARDS.md) — toute policy réseau passe par le banc
avant la prod.

### Résultat de validation (banc multi-node, 2026-06-01)

Policies du namespace `default` appliquées sur le banc 3 nœuds (cluster réel K8s
1.34 + Cilium 1.19, WordPress/MySQL déployés) :

| Test                                         | Attendu | Obtenu  |
| -------------------------------------------- | ------- | ------- |
| WordPress → MySQL `:3306` (flux autorisé)    | passe   | ✅ OK   |
| DNS depuis WordPress (CoreDNS)               | passe   | ✅ OK   |
| WordPress → MySQL `:22` (port non listé)     | bloqué  | ✅ DENY |
| WordPress → `1.1.1.1:443` (egress non listé) | bloqué  | ✅ DENY |

Le `default-deny` mord (egress non listé bloqué), le flux métier et le DNS sont
préservés. `rstudio`/`registry` n'étaient pas déployés sur le banc (mêmes
patrons, plus simples) — validés par revue + kubeconform.
