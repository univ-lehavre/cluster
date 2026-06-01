# Scénarios de test

Suite de tests **reproductibles** et **documentés** à dérouler sur le banc
multi-node (ou en prod après validation banc) pour valider que le stockage
Rook-Ceph et le CNI Cilium se comportent comme attendu en nominal et en panne.

## Pré-requis

- Banc multi-node up (`test/multi-node/`) ou cluster prod opérationnel.
- `kubectl` configuré côté poste de contrôle (ou ssh sur dirqual1).
- Phase 1-3 du PLAN appliquées (cluster K8s + Rook-Ceph HEALTH_OK).

## Conventions

## Tout lancer d'un coup — `run-all.sh`

```bash
test/scenarios/run-all.sh                  # tous les scénarios + récap PASS/FAIL
SKIP='03 04' test/scenarios/run-all.sh     # exclure des scénarios (par n°)
ONLY='01 02 07' test/scenarios/run-all.sh  # n'exécuter que ceux-là
```

Le runner exécute les scénarios dans l'ordre, **consigne le code de sortie** de
chacun dans un tableau récapitulatif, et attend le retour à `HEALTH_OK` entre
les scénarios destructifs (03/04/05). Il sort `1` si l'un des scénarios joués
échoue. **Sur le banc**, exclure 03/04 (`SKIP='03 04'`) : leur phase « restore »
ne s'y valide pas (cf. avertissement plus bas).

Chaque scénario est aussi un script bash auto-documenté, lançable seul :

```text
test/scenarios/
├── README.md                         ← ce fichier
├── run-all.sh                        ← runner agrégé (PASS/FAIL)
├── 01-block-rwx-write-read.sh        ← test de base PVC RBD
├── 02-pod-rescheduling.sh            ← résilience perte pod
├── 03-worker-loss.sh                 ← résilience perte worker
├── 04-control-plane-loss.sh          ← résilience perte control plane
├── 05-replication-bump.sh            ← passage réplica ×3 → ×5
├── 06-object-store-smoke.sh          ← smoke-test datalake S3
├── 07-cilium-connectivity.sh         ← test connectivité E/W Cilium
├── 08-resource-limits-audit.sh       ← audit requests/limits Ceph
├── 09-etcd-restore.sh                ← restauration etcd (backup restaurable)
├── 10-pod-security-admission.sh      ← PodSecurity bloque les pods dangereux
├── 11-networkpolicy-default-deny.sh  ← Cilium applique default-deny + allow
├── 12-securitycontext-runtime.sh     ← securityContext appliqué au runtime
└── 13-host-node-hardening.sh         ← durcissement hôte (réutilise state.sh)
```

Chaque script :

- est **idempotent** (rejouable sans état rémanent) ;
- pose des **annotations explicites** sur les objets créés
  (`test.cluster.dev/scenario: NN-name`) pour pouvoir les filtrer / nettoyer ;
- imprime sa sortie en `[étape]` clairs pour le suivi humain ;
- nettoie via un `trap EXIT` (à désactiver via `KEEP=1`) ;
- retourne `0` si OK, `1` sinon.

## Matrice des scénarios

| #   | Scénario                | Tests                                                                         | Durée   | Couverture                                      |
| --- | ----------------------- | ----------------------------------------------------------------------------- | ------- | ----------------------------------------------- |
| 01  | PVC RBD write/read      | StorageClass défaut, PVC Bound, écriture/lecture                              | ~1 min  | Stockage bloc fonctionnel                       |
| 02  | Reschedule pod          | Delete pod, re-création, **données persistantes**                             | ~30s    | Découplage pod ↔ volume                         |
| 03  | Worker loss             | Halt 1 worker, observation, restore                                           | ~5 min  | Réplicat ×3 + recovery Ceph                     |
| 04  | Control plane loss      | Halt control plane, observation API + workloads                               | ~5 min  | SPOF assumé, etcd backup                        |
| 05  | Replication bump        | Pool ×3 → ×5 (si 5+ hôtes), refill                                            | ~5 min  | Évolution capacité (skip si < 5 hôtes)          |
| 06  | Object store smoke      | datalake-ec + bucket + PUT/GET/DELETE                                         | ~3 min  | Stockage objet S3                               |
| 07  | Cilium connectivity     | `cilium connectivity test` standard + Hubble si activé                        | ~10 min | Réseau Pod-to-Pod, E/W, NetworkPolicy           |
| 08  | Resource limits audit   | Inspection des `requests`/`limits` actuels vs banc/prod                       | ~10s    | Cohérence dimensionnement                       |
| 09  | Restauration etcd       | Témoin → snapshot → suppression → `etcdctl snapshot restore` → témoin revient | ~3 min  | **Backup etcd RESTAURABLE** (pas juste produit) |
| 10  | Pod Security admission  | Pod privileged/hostNetwork **rejeté** à l'admission ; pod conforme admis      | ~1 min  | Durcissement pod (PSA, ADR 0014)                |
| 11  | NetworkPolicy deny      | default-deny coupe l'egress ; allow-dns le rouvre **ciblé** (appliqué Cilium) | ~2 min  | Durcissement réseau (NetworkPolicy + CNI)       |
| 12  | securityContext runtime | Pod durci démarre ; non-root + rootfs RO **vérifiés au runtime**              | ~1 min  | Durcissement pod (runAsNonRoot/readOnlyRootFS)  |
| 13  | Host/node hardening     | Réutilise `state.sh` → **PASS/FAIL** sur les couches hôte (sshd, auditd…)     | ~30s    | Durcissement hôte (secure.yml + first-access)   |

> 🔑 **09 — restauration etcd validée (2026-06-01).** Contrairement à 03/04, le
> 09 **ne reboote aucune VM** : il exerce la procédure du RUNBOOK _sur_ le
> control plane via SSH (stop kubelet → `etcdctl snapshot restore` →
> remplacement du data-dir → start kubelet), donc **sans** artefact banc. Il
> prouve la _restaurabilité_ par un témoin (un ConfigMap supprimé qui réapparaît
> après restore). Validé sur banc single-node — fonctionne même node `NotReady`
> (le restore etcd ne dépend pas du CNI). Note : `etcdctl` (paquet
> `etcd-client`) doit être présent sur le control plane — le scénario l'installe
> au besoin ; en prod, l'ajouter au provisionnement si la restauration doit être
> rapide.
>
> ⚠️ **03 / 04 — la phase « restore » d'un nœud ne se valide PAS sur ce banc.**
> Ne pas y retourner. La phase **« perte »** est utile et valable en prod (Ceph
> passe en `HEALTH_WARN`, les OSD survivants tiennent les I/O — réplicat ×3 /
> `failureDomain: host` / `min_size 2`). Mais le **retour** du nœud
> (`vagrant up`) bute sur des artefacts **propres au banc Vagrant/arm64, absents
> des 4 serveurs HPE** : route ClusterIP `10.96/12` perdue au reboot (drift #7),
> **clock skew** de la VM rallumée (pas de RTC), montage **`vboxsf`** en échec.
> Les « réparer » dans le scénario = **sur-adaptation au banc** (sans valeur
> prod) : on s'en abstient délibérément. Le restore réel se teste **en prod**,
> au rebuild des serveurs, où ces artefacts n'existent pas. Déroulé et analyse
> complète : [../RESULTS.md](../RESULTS.md) (section déroulé scénarios + #7).

### Groupe durcissement (10-13)

> 🔒 **10-13 — durcissement (pod + hôte), validés banc 2026-06-01.** Ce groupe
> teste la **sécurité**, pas la résilience. Les **10/11/12** sont des assertions
> 100 % transposables en prod (admission API, application des NetworkPolicy par
> le CNI, contrainte runtime du conteneur — aucune dépendance arm64/Vagrant). Le
> **13** réutilise [`bootstrap/state.sh`](../../bootstrap/state.sh) (source de
> vérité du dépôt) et n'échoue que sur un drift host `✗` — une couche opt-in non
> activée reste un `skip` (cf.
> [IMPLICATIONS.md](../../bootstrap/security/IMPLICATIONS.md)). Sur le banc, le
> 13 sort **FAIL attendu** tant que `first-access.sh` n'y a pas posé le
> durcissement sshd (le banc utilise le compte Vagrant) ; en prod (sshd durci +
> couches `secure.yml` actives) il passe. Il a besoin de l'accès SSH aux nœuds
> (`SSH_OPTS`/`HOSTS`), pas de `kubectl`.

## Réponses aux questions opérationnelles

### Que se passe-t-il si on détruit un replica ?

Cf. scénario 02 (`pod`) et 03 (`worker entier`) :

- **Suppression d'un pod** : Kubernetes recrée le pod via Deployment/STS, et le
  PVC RBD est re-monté (ReadWriteOnce — donc sur le même nœud ou un autre selon
  scheduling). Aucune perte de donnée.
- **Suppression d'un OSD seul** : Ceph re-réplique automatiquement les PG
  concernées sur un autre OSD du même hôte (si dispo) ou marque le pool dégradé.
  Tant que `failureDomain: host` est respecté et `min_size = 2`, les I/O
  continuent.
- **Suppression d'un hôte (worker)** : voir scénario 03.

### Que se passe-t-il si on augmente la réplication ?

Cf. scénario 05 : passer un pool de `size: 3` à `size: 5` (ou plus) nécessite
**autant d'hôtes que la nouvelle taille** (parce que `failureDomain: host`). Sur
4 hôtes prod → max `size: 4`. Le bump déclenche une **réplication** progressive
(les PG sont recopiés sur les nouveaux OSDs). Pendant ce temps, le pool est en
`HEALTH_WARN` (`Reduced data availability`), les I/O continuent mais bande
passante réduite. À ne pas faire en heure de pointe.

### Le stockage bloc pose-t-il des problèmes ?

Cf. scénarios 01, 02, 03 :

- Création PVC : ✅ Bound en < 30 s en nominal.
- Copie de données : ✅ aucune limite côté Ceph (limité par la BP réseau et la
  perf des HDD).
- Limites : RBD = ReadWriteOnce uniquement. Pour ReadWriteMany, utiliser CephFS
  (StorageClass `rook-cephfs`).

### Le stockage objet fonctionne-t-il ?

Cf. scénario 06, qui réutilise
[`storage/ceph/storageClass/datalake/smoke-test.sh`](../../storage/ceph/storageClass/datalake/smoke-test.sh)
: crée un bucket, écrit un fichier, le relit, le supprime. Verdict : ✅ si le
`CephObjectStore datalake` est `Connected` et le `ObjectBucketClaim` provisionne
le Secret.

### Que se passe-t-il si le control plane plante ?

Cf. scénario 04. Récap :

- **API K8s injoignable** → impossible de scheduler de nouveaux pods, d'ouvrir
  une session `kubectl`, de redémarrer un workload tombé.
- **etcd inaccessible** → la sauvegarde horaire (rôle
  [`etcd-backup`](../../bootstrap/roles/etcd-backup/)) permet de restaurer
  ailleurs.
- **Workloads en cours** : continuent tant que le kubelet local tourne. Cilium
  continue d'assurer le réseau Pod-to-Pod. Ceph reste opérationnel (mons en
  quorum sur les workers).
- **Restauration** : voir [`bootstrap/RUNBOOK.md`](../../bootstrap/RUNBOOK.md)
  section « Restauration etcd (procédure) ».

### Tests Cilium

Cf. scénario 07 :

- `cilium connectivity test` — suite officielle, 200+ checks (Pod ↔ Pod, Pod ↔
  Service, Pod ↔ World, NetworkPolicy, etc.).
- Test custom : déployer 2 pods sur des nœuds différents, vérifier le ping
  pod-to-pod via tunnel VXLAN.

### Le durcissement (pod / hôte) est-il vérifié ?

Oui, par les scénarios 10-13 :

- **Pod (10/11/12)** — `kubectl`-only, comme 01-08 :

  ```bash
  bash test/scenarios/10-pod-security-admission.sh    # PSA bloque privileged/hostNetwork
  bash test/scenarios/11-networkpolicy-default-deny.sh # Cilium applique default-deny + allow
  bash test/scenarios/12-securitycontext-runtime.sh    # non-root + rootfs RO au runtime
  ```

  Ils créent leur propre namespace, posent les contraintes (PSA `baseline`,
  `default-deny-all`, `securityContext` durci) et **vérifient le comportement
  réel** (rejet à l'admission, egress coupé, écriture rootfs refusée). Ce que
  PSA et `securityContext` couvrent est tracé dans
  [ADR 0014](../../docs/decisions/0014-durcissement-kubeadm-init.md).

- **Hôte (13)** — a besoin de l'**accès SSH** aux nœuds (pas de `kubectl`) :

  ```bash
  HOSTS='dirqual1 dirqual2 dirqual3' bash test/scenarios/13-host-node-hardening.sh
  # banc (port forwardé Vagrant, un nœud à la fois) :
  HOSTS=127.0.0.1 SSH_OPTS='-p 2222 -i ~/.vagrant.d/insecure_private_keys/vagrant.key.rsa' \
    USER_REMOTE=debian bash test/scenarios/13-host-node-hardening.sh
  ```

  Il **réutilise** [`bootstrap/state.sh`](../../bootstrap/state.sh) et échoue
  sur tout drift des couches hôte (sshd durci, auditd, fail2ban, postfix, ufw,
  smartd). `STRICT_OPTIN=1` fait en plus échouer si **aucune** couche
  `secure.yml` n'est active (attendu en prod). Une couche opt-in non activée
  reste un `skip` neutre (cf.
  [IMPLICATIONS.md](../../bootstrap/security/IMPLICATIONS.md)).

## Exécution

Lancer un scénario individuellement :

```bash
KUBECONFIG=~/.kube/config-banc bash test/scenarios/01-block-rwx-write-read.sh
```

Lancer toute la suite (s'arrête au premier échec) :

```bash
for s in test/scenarios/[0-9]*.sh; do
    echo "▶ $s"
    bash "$s" || { echo "✗ $s a échoué — abandon"; exit 1; }
done
```

Nettoyage manuel si un script est sorti `KEEP=1` :

```bash
kubectl delete all,pvc -l 'test.cluster.dev/scenario' --all-namespaces
```

## État courant (banc 2026-05-28)

Voir [test/RESULTS.md](../RESULTS.md) — les scénarios 01-08 ont été **écrits et
sont reproductibles**, mais leur **exécution complète sur le banc** est gated
par le drift #9 (ceph-csi-operator + Driver CR à configurer pour Rook 1.19+).
Une fois ce drift résolu, dérouler la suite de bout en bout est l'objectif du
prochain run.
