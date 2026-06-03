# Décisions — Plan de contrôle & cycle de vie du cluster

> Cette page est une **vue thématique** au-dessus des ADR (Architecture Decision
> Records). Les ADR restent la **source de vérité**, datée et immuable ; ils ne
> sont pas remplacés ici. Cette page les **agrège** et les **raconte** par thème
> — c'est une carte de lecture pour comprendre _pourquoi_ le plan de contrôle et
> le cycle de vie du cluster sont ce qu'ils sont, et vers quel ADR aller pour le
> détail daté.

## Le point de départ : 4 nœuds, et tout ce qui en découle

Le dimensionnement du cluster n'est pas neutre : il fixe le modèle de panne
acceptable et conditionne la plupart des décisions de plan de contrôle. Le parc
disponible est un châssis lame pouvant héberger 4 lames, ce qui mène à **4 nœuds
rigoureusement identiques** (`cp1`/`node1-3`, 10.0.0.11-14).

Pourquoi exactement 4 ?

- **Pas 3** : c'est le minimum strict pour Ceph (quorum mon +
  `failureDomain: host` sur ×3), donc **zéro marge** pour la maintenance.
  Drainer un nœud pour reboot ramène le cluster à 2 nœuds, et la perte d'un nœud
  de plus ne tient plus le ×3 → I/O bloquées.
- **Pas 5** : permettrait 5 mon (tolérance Byzantine inutile à cette échelle),
  pour un coût matériel supérieur sans bénéfice opérationnel net, et sortirait
  du format châssis lame (4 emplacements).
- **4** : un châssis unitaire racable d'un bloc, et surtout la **première
  topologie qui autorise la maintenance** sans dégrader la tolérance — drainer 1
  nœud laisse 3 nœuds opérationnels, donc le quorum mon (3 mon) et le ×3 sur 3
  hôtes restants tiennent.

Ce choix de 4 hôtes plafonne aussi l'erasure coding : avec
`failureDomain: host`, il faut au moins `k+m` hôtes, donc **EC 2+1** (= 3 hôtes,
1 de marge) est le maximum possible ; EC 2+2 (= 4) saturerait. D'où le couple
réplicat ×3 pour le critique + EC 2+1 pour le datalake — voir
[ADR 0001](../decisions/0001-replication-x3-pour-workloads-bloc.md) et
[ADR 0004](../decisions/0004-erasure-coding-2plus1-datalake.md).

Le détail de capacité (≈ 1 TiB de RAM, 160 c / 320 t, 264 TiB HDD brut → ~88 TiB
utiles en ×3 ou ~176 TiB en EC 2+1) et la liste de ce que 4 nœuds **ne** donnent
**pas** sont dans [ADR 0009](../decisions/0009-pourquoi-4-noeuds.md).

## Un control plane unique : SPOF assumé

Avec 4 nœuds, faire de la vraie HA Kubernetes coûterait cher : la HA exige **3
control planes** pour le quorum etcd, ce qui ne laisserait **qu'un seul worker**
pour les charges — topologie peu intéressante pour un cluster de recherche
mono-admin qui veut maximiser le calcul. Le choix est donc **un seul control
plane** (`cp1`), SPOF assumé.

Deux décisions de bootstrap rendent ce choix réversible plus tard sans tout
casser :

- `kubeadm init --control-plane-endpoint cluster-api:6443 --upload-certs` est
  posé **dès le bootstrap initial**, et l'entrée `cluster-api → 10.0.0.11` est
  propagée dans `/etc/hosts` des 4 nœuds. Les workers joignent donc déjà un
  **nom DNS stable**, pas une IP : passer à 3 control planes un jour n'imposera
  **pas** de réinstaller les workers.
- **Sauvegarde etcd horaire** (`etcdctl snapshot save` toutes les heures,
  rétention 24h), avec procédure de restauration documentée dans le RUNBOOK.

Le coût assumé est clair : la perte de `cp1` rend le cluster inutilisable
jusqu'à restauration, et pendant la maintenance de ce nœud l'API est
inaccessible quelques minutes (les workloads applicatifs continuent via le
kubelet local, mais aucun nouvel ordonnancement). Détail et garde-fous dans
[ADR 0002](../decisions/0002-control-plane-unique-avec-endpoint.md).

## Hyperconvergence : le control plane porte aussi des OSDs et des pods

Restait à décider si ce control plane unique se contente du plan de contrôle ou
s'il participe aussi au stockage et au calcul. Le choix est l'**hyperconvergence
assumée** : `cp1` porte le control plane, **12 OSDs Ceph**, et est **détainté**
pour accepter les pods applicatifs. Les 4 nœuds sont alors identiques côté
inventaire et font tous tourner `kubelet` + `containerd`, les OSDs (12 HDD +
block.db NVMe), Cilium et les charges ; seul `cp1` ajoute `kube-apiserver`,
`kube-scheduler`, `kube-controller-manager` et `etcd`.

La raison est qu'à 4 nœuds, dédier un nœud au seul control plane retirerait **25
%** de la capacité de calcul ; l'hyperconvergence donne au contraire un
**cluster Ceph plein** (48 OSDs au lieu de 36). Le coût, lui, se concentre sur
`cp1` : contention CPU/RAM, et surtout un **etcd sensible aux I/O** s'il
cohabite mal avec les autres charges. D'où les garde-fous : `/var/lib/etcd` sur
LV dédié (10 GiB, ext4) pour isoler les I/O, `requests/limits` sur les OSDs, et
la sauvegarde etcd horaire déjà citée. Détail dans
[ADR 0007](../decisions/0007-hyperconvergence-control-plane-osd.md).

## Durcir le plan de contrôle sans casser l'init

Le control plane est initialisé par un `kubeadm init`. Un audit a relevé trois
manques qu'aucun ADR ne couvrait : pas d'audit-policy API server, pas
d'`EncryptionConfiguration` (Secrets en clair base64 dans etcd, donc aussi dans
les snapshots), pas de Pod Security admission. Le modèle de menace rappelé est
celui d'un cluster **mono-tenant, réseau privé isolé, mono-admin** (voir
[ADR 0003](../decisions/0003-pas-de-chiffrement-ceph-tailscale.md)). Les trois
points sont traités de façon **différenciée** :

- **Pod Security admission** — activée par **labels de namespace** (pas par
  `AdmissionConfiguration` globale), ce qui évite de toucher le `kubeadm init`
  et le risque de blocage cluster-wide. Niveau `baseline` en `enforce` sur les
  namespaces maison (`rstudio`, `registry`, `default`), `restricted` en `warn`
  pour préparer la suite, et **pas** d'enforce sur `rook-ceph` (l'operator/CSI a
  légitimement besoin de privilèges élevés).
- **Chiffrement des Secrets etcd** — implémenté [2026-06-02] : le rôle
  `k8s-initialization` passe à `kubeadm init --config` avec un provider
  **`secretbox`** (XSalsa20-Poly1305, pas de KMS externe). La clé (32 octets,
  base64) est générée **une seule fois** au bootstrap, stockée
  `/etc/kubernetes/enc/key1.b64` (0600 root, hors dépôt, jamais commitée). Le
  risque résiduel assumé : la clé vit en clair sur le disque du control plane ;
  le risque visé — le **vol d'un snapshot etcd** — est lui couvert.
- **Audit-policy API server** — implémentée [2026-06-02] via le même `--config`
  : politique **niveau `Metadata`** (qui/quoi/quand, sans le corps des
  requêtes), avec exclusion du bruit et rotation des logs. Elle couvre les
  appels API directs (`kubectl` d'un humain) que les autres journaux ne voyaient
  pas.

Conséquence de ce durcissement : la question du **chiffrement des snapshots etcd
au repos** est tranchée — **non**, dette close en l'assumant. Puisque les
Secrets sont déjà chiffrés _dans_ etcd, ce qui reste en clair dans un snapshot
n'est que de la **configuration** (ConfigMaps, Deployments, RBAC…), pas des
credentials ; chiffrer le contenant ajouterait une clé privée hors-nœud qui
deviendrait un nouveau SPOF de restauration. Mitigation retenue : permissions
strictes (`/var/lib/etcd-backups` en `0700`, snapshots `0600` root) et copie sur
poste de confiance. La porte de sortie (chiffrement `age` asymétrique) est
documentée si le modèle de menace change. Tout le détail, validé sur banc
(scénario `15-etcd-encryption-audit.sh`), est dans
[ADR 0014](../decisions/0014-durcissement-kubeadm-init.md).

## Faire vivre le cluster : upgrade in-place, rebuild en dernier recours

Kubernetes publie une mineure tous les ~4 mois, chacune supportée ~14 mois : il
faut une procédure répétable, sinon le cluster dérive hors support. La décision
est l'**upgrade in-place via `kubeadm`** pour les patchs et les mineures, le
**rebuild** restant réservé aux cas exceptionnels (corruption etcd, saut de
versions trop large, changement d'OS majeur).

Le déroulé séquencé est :

- **Control plane d'abord** (`kubeadm upgrade apply`), drainé puis restauré.
- **Workers un par un** (`serial: 1` : drain → `kubeadm upgrade node` → kubelet
  → uncordon). Un seul nœud indisponible à la fois suffit : les workloads se
  replanifient sur les autres grâce au réplicat ×3 Ceph et à
  `failureDomain: host`.
- **Une mineure à la fois** (kubeadm interdit de sauter, ex. 1.34 → 1.35 →
  1.36), après vérification de la compat croisée Cilium/Rook/Ceph via la matrice
  de versions
  ([ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
- **Patch** (1.34.x → 1.34.y) : sûr et fréquent, in-place sans cérémonie.

Le coût assumé rejoint directement le control plane unique : pendant le
`kubeadm upgrade apply` sur `cp1`, l'**API est indisponible** (les workloads
continuent, seul le plan de contrôle l'est momentanément). Fenêtre courte,
acceptée. La discipline de version reste à la charge de l'opérateur (le playbook
`assert` la version cible mais ne vérifie pas la compat croisée), et tout
upgrade se **valide d'abord sur le banc multi-node**. Détail dans
[ADR 0015](../decisions/0015-strategie-upgrade-kubernetes.md).

## Encadré honnêteté — les compromis assumés

Ce domaine empile plusieurs compromis **volontaires**, conséquences directes du
format 4 nœuds :

- **SPOF API + etcd** : un seul control plane (`cp1`). La perte de ce nœud rend
  le cluster inutilisable jusqu'à restauration ; mitigation = sauvegarde etcd
  horaire + restore testée (ADR 0002).
- **API indisponible pendant la maintenance et l'upgrade** de `cp1` (ADR 0002,
  ADR 0015) — fenêtre courte, workloads applicatifs préservés.
- **Pas de tolérance double-panne** sur le critique (`min_size = 2` sur ×3) ni
  de N+2 sur la maintenance (ADR 0009).
- **Contention sur `cp1`** : control plane + 12 OSDs + pods sur le même nœud,
  etcd sensible aux I/O — mitigé par un LV dédié `/var/lib/etcd` (ADR 0007).
- **Clé de chiffrement etcd en clair** sur le disque du control plane : un accès
  disque au nœud la lit ; pas de KMS (choix mono-admin). Le risque visé, le vol
  de snapshot, est couvert (ADR 0014).

Tous ces points ont une **condition de revisite** explicite — notamment le
passage à **8 nœuds** (2 châssis), qui rendrait viables la HA control-plane à 3
nœuds, l'EC 4+2 et la tolérance double-panne (ADR 0009), et qui lèverait le SPOF
d'upgrade (ADR 0015).

## Voir aussi

- [Exposition réseau](../architecture/exposition-reseau.md) — réseau et
  exposition des services.
- [Validation sur banc](../architecture/validation-banc.md) — tests sur le banc
  multi-node, où les procédures d'upgrade et de restauration sont rejouées.
