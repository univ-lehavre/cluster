# Spike — Cilium Cluster Mesh sous latence réseau simulée

> **Spike jetable.** But : _prouver_ qu'on peut fédérer plusieurs clusters
> Kubernetes (« un par site ») avec **Cilium Cluster Mesh**, et **observer le
> comportement sous latence inter-site**. Le spike a conclu : il **réutilise**
> désormais le banc léger Lima ([`test/lima/`](../../lima/)) et le **vrai
> bootstrap** `bootstrap/`, qui a été rendu paramétrable pour le multi-cluster
> ([ADR 0027](../../../docs/decisions/0027-bootstrap-parametre-multi-cluster.md),
> défauts prod inchangés). Il ne touche **ni** le banc Vagrant
> (`test/multi-node/`), **ni** le comportement Cilium de prod (mono-cluster).

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

## Choix : VMs Lima (le banc léger), plus kind

Initialement monté sur deux clusters [`kind`](https://kind.sigs.k8s.io/)
(Kubernetes-in-Docker), ce spike a **migré vers Lima** (#128) : kind est
abandonné
([ADR 0006](../../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md))
— son image figeait K8s en 1.31, et ce n'était pas le chemin de la prod. Chaque
« site » est désormais une **vraie VM Lima** sur laquelle tourne le **VRAI
bootstrap Ansible** (le même qu'en prod), avec une **identité de cluster
distincte** posée par le bootstrap paramétré
([ADR 0027](../../../docs/decisions/0027-bootstrap-parametre-multi-cluster.md)).

La plomberie Lima ↔ Ansible (VMs, inventaire, bootstrap, kubeconfig) est
**réutilisée du banc léger Lima** ([`test/lima/`](../../lima/)) : ce spike
source sa bibliothèque (`lib.sh`), il ne la duplique pas. `tc netem` se pose sur
une **vraie interface** de la VM (réseau `user-v2`), plus réaliste que le
`docker exec` des conteneurs kind.

## Prérequis

| Outil   | Version                                     |
| ------- | ------------------------------------------- |
| Lima    | ≥ 2.0 (`brew install lima`)                 |
| ansible | ≥ 2.20.5                                    |
| cilium  | v0.19.4 (CLI), image cilium 1.19.4 (= prod) |
| kubectl | v1.34.x                                     |
| helm    | (cilium-cli embarque Helm)                  |

## Topologie

| Site   | VM Lima  | contexte       | cluster.name | cluster.id | podSubnet     | serviceSubnet |
| ------ | -------- | -------------- | ------------ | ---------- | ------------- | ------------- |
| site-a | `site-a` | `spike-site-a` | `site-a`     | 1          | 10.244.0.0/16 | 10.96.0.0/12  |
| site-b | `site-b` | `spike-site-b` | `site-b`     | 2          | 10.245.0.0/16 | 10.97.0.0/16  |

> **CIDR disjoints** et **cluster.id/name uniques** : exigences non-négociables
> de Cluster Mesh (sinon le mesh ne monte pas). Les deux VMs se joignent sur le
> réseau `user-v2` (`192.168.104.0/24`), qui porte le trafic clustermesh et où
> `tc netem` simule la latence inter-site.

## Utilisation

```bash
./up.sh            # crée les 2 VMs Lima, bootstrap K8s + Cilium, partage la CA, monte le mesh
./probe.sh         # déploie un service global et prouve le routage inter-cluster
./latency.sh 50    # injecte 50 ms de latence de chaque côté (RTT ≈ 100 ms)
./probe.sh rtt     # mesure le RTT applicatif sous cette latence
./latency.sh clear # retire la latence
./probe.sh sweep   # balaye 0/10/50/100 ms et tabule le RTT (one-shot)
./down.sh          # détruit les 2 VMs (netem inclus : il vit dans les VMs)
```

## Résultats observés (mesuré sur Lima, 2026-06-04)

Spike **concluant**, remesuré sur le banc Lima (les valeurs kind d'origine —
2026-06-03 — étaient cohérentes ; remplacées ici par le run Lima). Mesh établi
entre `site-a` et `site-b` (`cilium clustermesh status` :
`site-b: 1/1 configured, 1/1 connected`), service global joignable
cross-cluster, et **dégradation gracieuse** sous latence.

**Preuve du mesh.** Depuis un pod de `site-a`, un `curl` du Service global
`echo-global` atteint un backend qui tourne dans `site-b` :

```text
✓ réponse reçue du backend : 'echo-global-69bd59dfdf-skbvb' (servi par site-b via le mesh)
```

**RTT applicatif sous latence injectée** (netem posé de chaque côté → RTT ≈ 2 ×
delay sur l'aller-retour, le lien étant traversé une fois dans chaque sens) :

| Latence netem (chaque côté) | RTT applicatif mesuré | Mesh  |
| --------------------------- | --------------------- | ----- |
| 0 ms                        | **1,6 ms**            | ✅ OK |
| 10 ms                       | **42,5 ms**           | ✅ OK |
| 50 ms                       | **203,0 ms**          | ✅ OK |
| 100 ms                      | **403,5 ms**          | ✅ OK |

Le RTT suit **linéairement** la latence (overhead applicatif ≈ 2-4 ms constant),
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

> _Drift Lima rencontré._ Les deux clusters kubeadm exportent par défaut les
> mêmes noms (`kubernetes` / `kubernetes-admin`) dans leur kubeconfig :
> fusionnés (`KUBECONFIG=a:b`), ils s'écrasaient → `cilium clustermesh connect`
> voyait deux fois le même cluster. Corrigé dans la lib du banc
> ([`test/lima/lib.sh`](../../lima/lib.sh), `fetch_kubeconfig_node`) : cluster /
> user / contexte sont renommés sur des noms uniques par site.

## Conclusion / décision

Cluster Mesh dégrade **gracieusement** sous latence → **bon candidat à
l'industrialisation**. Le spike a depuis :

- **migré de kind vers Lima** (#128) : il tourne sur le banc léger Lima
  ([`test/lima/`](../../lima/)) et exécute le **vrai bootstrap** ;
- acté son paramétrage multi-cluster en **ADR** :
  [ADR 0027](../../../docs/decisions/0027-bootstrap-parametre-multi-cluster.md)
  (identité `cluster.name`/`cluster.id` + CIDR pods/services disjoints, défauts
  prod inchangés), en lien avec
  [ADR 0020](../../../docs/decisions/0020-exposition-reseau-tout-cilium.md)
  (tout-Cilium) et
  [ADR 0023](../../../docs/decisions/0023-plateforme-exemple-generique.md)
  (catalogue de topologies).

Prochaine étape (hors spike) : industrialiser un **profil de catalogue
multi-site** (profil de nœuds + inventaire dédiés), au-delà des deux VMs
jetables de ce spike.
