# 0027 — Bootstrap paramétré pour topologies multi-cluster (Cilium Cluster Mesh)

## Contexte

Le dépôt est un **catalogue de topologies**
([ADR 0023](0023-plateforme-exemple-generique.md)). Le spike
[`test/spikes/clustermesh-latency/`](../../test/spikes/clustermesh-latency/)
explore une topologie **multi-site** : plusieurs clusters Kubernetes autonomes
(un par site) fédérés par **Cilium Cluster Mesh**, sous latence inter-site
simulée (`tc netem`). Migré de kind vers de vraies VMs Lima (#128), il exécute
désormais le **VRAI bootstrap Ansible** — le même chemin que la prod.

Or **Cluster Mesh exige, par cluster** : un `cluster.id` (1-255) et un
`cluster.name` **uniques**, et des **CIDR pods/services DISJOINTS** entre
clusters (sinon le mesh ne monte pas — collision d'identités/de routes). Le
bootstrap, conçu pour un cluster **unique**, ne posait ni identité Cilium
(`cluster.name`/`cluster.id`) ni CIDR explicites : le podCIDR était figé à
`10.244.0.0/16` dans `cni.sh`, et `kubeadm` gardait ses CIDR services par
défaut. Monter deux clusters fédérés était donc **impossible** sans toucher le
bootstrap.

## Décision

Rendre le bootstrap paramétrable **en opt-in, avec des défauts qui préservent à
l'identique le comportement de prod (mono-cluster)** :

- **`bootstrap/cni.sh`** accepte trois variables d'environnement :
  - `CILIUM_POD_CIDR` (défaut `10.244.0.0/16`) — le podCIDR du cluster ;
  - `CILIUM_CLUSTER_NAME` / `CILIUM_CLUSTER_ID` (défaut **vides**) — l'identité
    de cluster, posée (`--set cluster.name`/`cluster.id`) **uniquement si
    renseignée**. Vides → Cilium reste sur son défaut « default », **aucune**
    fonction mesh activée.
- **`bootstrap/roles/k8s-initialization/templates/kubeadm-config.yaml.j2`** émet
  un bloc `networking: {serviceSubnet, podSubnet}` **seulement si** les
  variables `service_subnet` / `pod_subnet` sont fournies. Non fournies → le
  rendu est **byte-identique** à l'existant (vérifié).

Le spike renseigne ces variables par site (site-a : défauts prod ; site-b :
podCIDR `10.245.0.0/16`, serviceCIDR `10.97.0.0/16`, `cluster.id=2`).

## Statut

Accepted (2026-06-04). Validé de bout en bout par le spike `clustermesh-latency`
migré sur Lima : deux clusters mono-nœud fédérés, CA Cilium partagée, mesh
établi (`cilium clustermesh status`), service global joignable cross-cluster, et
dégradation gracieuse sous latence `netem`.

## Conséquences

**Bénéfices.** Un **seul** bootstrap sert la prod mono-cluster ET la fédération
multi-site — pas de fork ni de double maintenance. Le spike exerce désormais le
**vrai chemin de prod** (containerd, kubeadm, `cni.sh`), pas un outillage à part
(kind figeait K8s 1.31,
[ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).

**Prix à payer.** Une petite surface de variables supplémentaires à documenter.
Risque de rendu divergent si les défauts étaient mal gérés — mitigé par
l'invariant « variables vides → comportement et rendu inchangés ».

**Garde-fous.** Les défauts sont les valeurs de prod actuelles ; toute topologie
mono-cluster (prod, banc Vagrant, banc Lima) ne renseigne **rien** et reste sur
le chemin éprouvé. Seul un déploiement multi-cluster explicite active le
paramétrage.

## Alternatives écartées

- **Bootstrap forké/dédié au mesh** : divergence et double maintenance entre le
  chemin prod et le chemin spike — à rebours de l'intérêt du spike (valider le
  vrai bootstrap).
- **Valeurs multi-cluster codées en dur** : casserait la prod mono-cluster.
- **Surcouche post-bootstrap dans le spike** (reconfigurer Cilium/kubeadm après
  coup) : fragile, ne valide pas le bootstrap lui-même, et duplique la logique.
- **Rester sur kind** : n'exerce pas le chemin de prod et figeait K8s en 1.31
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).

## À revoir

- Si le profil multi-site est **industrialisé** en topologie de catalogue
  (profil de nœuds + inventaire dédiés, au-delà du spike).
- Quand `cilium-cli` n'exigera plus la config Helm isolée (contournement actuel
  d'un `repositories.yaml` incomplet côté hôte).
