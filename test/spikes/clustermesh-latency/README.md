# Spike — Cilium Cluster Mesh sous latence réseau simulée

> **Spike jetable.** But : _prouver_ qu'on peut fédérer plusieurs clusters
> Kubernetes (« un par site ») avec **Cilium Cluster Mesh**, et **observer le
> comportement sous latence inter-site**. Ce répertoire ne touche **ni** le
> bootstrap Ansible (`bootstrap/`), **ni** le banc Vagrant (`test/multi-node/`),
> **ni** la configuration Cilium de production (`bootstrap/cni.sh`). Aucun ADR
> n'est posé tant que le spike n'a pas conclu.

## Pourquoi

Le dépôt est un **catalogue de topologies**
([ADR 0023](../../../docs/decisions/0023-plateforme-exemple-generique.md)). On
explore une topologie **multi-site** où :

- **chaque site = son propre cluster Kubernetes autonome** (etcd local), **pas**
  un cluster étiré — ce qui évite le piège du quorum etcd fragile sous latence ;
- les clusters sont **fédérés par Cilium Cluster Mesh** (services et identités
  partagés) ;
- **les sites sont virtuels** : la « distance » inter-site est **simulée par de
  la latence `tc netem`**, pas par un vrai réseau distinct.

C'est le **premier usage de `tc`/`netem`** du dépôt, délibérément confiné ici.

## Choix : kind plutôt que Vagrant

Pour apprendre vite et jeter ensuite : deux clusters
[`kind`](https://kind.sigs.k8s.io/) (Kubernetes-in-Docker) montent en quelques
secondes, sans disque Ceph, pour ~quelques GiB de RAM — contre ~30 GiB pour deux
clusters en VMs VirtualBox. Chaque nœud kind est un conteneur Docker :
`tc netem` s'y pose via `docker exec`.

## Prérequis

| Outil   | Vérifié sur ce poste                        |
| ------- | ------------------------------------------- |
| docker  | Docker Desktop (démon lancé)                |
| kind    | v0.24.0                                     |
| cilium  | v0.19.4 (CLI), image cilium 1.19.4 (= prod) |
| kubectl | v1.34.1                                     |

## Topologie

| Cluster | kind | contexte | cluster.name | cluster.id | podSubnet     | serviceSubnet |
| ------- | ---- | -------- | ------------ | ---------- | ------------- | ------------- |
| site-a  | `c1` | kind-c1  | `site-a`     | 1          | 10.244.0.0/16 | 10.96.0.0/16  |
| site-b  | `c2` | kind-c2  | `site-b`     | 2          | 10.245.0.0/16 | 10.97.0.0/16  |

> **CIDR disjoints** et **cluster.id/name uniques** : exigences non-négociables
> de Cluster Mesh (sinon le mesh ne monte pas).

## Utilisation

```bash
./up.sh            # crée les 2 clusters kind, installe Cilium, partage la CA, monte le mesh
./probe.sh         # déploie un service global et prouve le routage inter-cluster
./latency.sh 50    # injecte 50 ms de latence de chaque côté (RTT ≈ 100 ms)
./probe.sh rtt     # mesure le RTT applicatif sous cette latence
./latency.sh clear # retire la latence
./probe.sh sweep   # balaye 0/10/50/100 ms et tabule le RTT (one-shot)
./down.sh          # détruit tout (netem inclus : il vit dans les conteneurs)
```

## Résultats observés (2026-06-03)

Spike **concluant**. Mesh établi entre `site-a` et `site-b`
(`cilium clustermesh status` : _All 1 nodes connected to all clusters_), service
global joignable cross-cluster, et **dégradation gracieuse** sous latence.

**Preuve du mesh.** Depuis un pod de `site-a`, un `curl` du Service global
`echo-global` atteint un backend qui tourne dans `site-b` :

```text
✓ réponse reçue du backend : 'echo-global-6854854876-tvqnl' (servi par site-b via le mesh)
```

**RTT applicatif sous latence injectée** (netem posé de chaque côté → RTT
théorique ≈ 4 × delay, car l'aller-retour traverse 2× le lien dans chaque sens)
:

| Latence netem (chaque sens) | RTT théorique | RTT applicatif mesuré | Mesh  |
| --------------------------- | ------------- | --------------------- | ----- |
| 0 ms                        | ~0 ms         | **1,4 ms**            | ✅ OK |
| 10 ms                       | ~40 ms        | **45,0 ms**           | ✅ OK |
| 50 ms                       | ~200 ms       | **206,8 ms**          | ✅ OK |
| 100 ms                      | ~400 ms       | **407,3 ms**          | ✅ OK |

Le RTT suit **linéairement** la latence (overhead applicatif ≈ 5-7 ms constant),
**sans rupture du mesh** à aucun palier. C'est le comportement attendu d'une
**fédération de clusters autonomes** : chaque etcd reste local (quorum non
affecté), seule la résolution de service inter-cluster traverse la latence — à
l'opposé d'un _stretch cluster_ dont l'etcd étiré perdrait le quorum.

**Contournement intégré à `lib.sh`.** `cilium-cli` (lib Helm embarquée) charge
tout le `repositories.yaml` de l'utilisateur et exige l'index de **chaque** repo
; un seul index manquant fait échouer l'install (`no cached repo found`).
`lib.sh` isole donc cilium-cli sur une config Helm dédiée
(`HELM_REPOSITORY_CONFIG`/`HELM_REPOSITORY_CACHE` → `$TMPDIR/spike-helm`) ne
contenant que le repo cilium — la config Helm personnelle reste intacte.

> _Aléa rencontré_ : la mise en veille de l'hôte (Mac) arrête le démon Docker en
> cours de route ; kind redémarre ses conteneurs au réveil et le mesh reconverge
> seul (`up.sh` est idempotent). Garder Docker Desktop actif pendant un run.

## Conclusion / décision

Cluster Mesh dégrade **gracieusement** sous latence → **bon candidat à
l'industrialisation** : profil de catalogue multi-site + **ADR** (paramétrage
`cluster.name`/`cluster.id`/podCIDR/serviceCIDR disjoints du bootstrap,
référence ADR 0020 tout-Cilium et ADR 0023 catalogue). À décider avec l'équipe.
