# Scénarios de test

Suite de tests **reproductibles** et **documentés** à dérouler sur le banc Lima
multi-nœuds (ou en prod après validation banc) pour valider que le stockage
Rook-Ceph et le CNI Cilium se comportent comme attendu en nominal et en panne.

## Pré-requis

- Banc Lima up (cf. [`bench/lima/`](/cluster/bench/lima/)) ou cluster prod
  opérationnel.
- `kubectl` configuré (au banc : `KUBECONFIG=bench/lima/.work/kubeconfig`), ou
  accès node-side via `limactl shell <instance>`.
- Phase 1-3 du PLAN appliquées (cluster K8s + Rook-Ceph HEALTH_OK).

## Conventions

> **Scénarios caducs (depuis 2026-06-29, ADR 0097).** Quatre scénarios n'ont
> plus de terrain pour tourner faute de ressources matérielles (banc Vagrant
> multi-node / 3-VM et topologie `ha-3cp` abandonnés) : le **03** (perte
> worker + Ceph), le **04** (perte control plane), le **19** (chaos partition
> réseau) et le **30** (survie HA `ha-3cp`). Ils restent **dans le catalogue**
> comme trace historique mais sont marqués `statut: caduc` (cf.
> [`nestor/epreuves.py`](https://github.com/univ-lehavre/cluster/blob/main/nestor/epreuves.py))
> — `nestor` les exclut d'office. **Réversible** : repasser à `actif` quand un
> banc multi-nœuds redevient disponible. Leurs scripts `.sh` sont conservés.

## Tout lancer d'un coup — `run-all.sh`

```bash
bench/scenarios/run-all.sh                  # tous les scénarios + récap PASS/FAIL
SKIP='03 04' bench/scenarios/run-all.sh     # exclure des scénarios (par n°)
ONLY='01 02 07' bench/scenarios/run-all.sh  # n'exécuter que ceux-là
```

Le runner exécute les scénarios dans l'ordre, **consigne le code de sortie** de
chacun dans un tableau récapitulatif, et attend le retour à `HEALTH_OK` entre
les scénarios destructifs (03/04/05). Il sort `1` si l'un des scénarios joués
échoue. **Sur le banc**, exclure 03/04 (`SKIP='03 04'`) : leur phase « restore »
ne s'y valide pas (cf. avertissement plus bas).

Chaque scénario est aussi un script bash auto-documenté, lançable seul :

```text
bench/scenarios/
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
├── 13-host-node-hardening.sh         ← durcissement hôte (réutilise state.sh)
├── 14-cilium-encryption-hubble.sh    ← WireGuard actif + Hubble (ADR 0019)
├── 15-etcd-encryption-audit.sh       ← Secrets chiffrés etcd + audit + rotation (ADR 0014)
├── 16-brute-force-ssh-fail2ban.sh    ← OFFENSIF : brute-force SSH → fail2ban bannit (ADR 0025)
├── 17-pod-evasion-psa.sh             ← OFFENSIF : pod d'évasion hôte → PSA rejette (ADR 0025)
├── 18-exfiltration-networkpolicy.sh  ← OFFENSIF : exfiltration → NetworkPolicy coupe (ADR 0025)
├── 19-chaos-perte-paquets-partition.sh ← CHAOS : perte/partition réseau (netem) (ADR 0025)
├── 20-chaos-kill-pods.sh             ← CHAOS : kill aléatoire de pods (ADR 0025)
├── 21-chaos-saturation-cpu-mem.sh    ← CHAOS : saturation CPU/mémoire (ADR 0025)
├── 22-alerte-detecteurs-mailpit.sh   ← ALERTE : détecteurs → Mailpit (ADR 0025, dépend #131)
├── 23-marquez-openlineage.sh         ← DataOps : lineage Dagster → Marquez (ADR 0028, #148)
├── 24-prometheus-scrape.sh           ← OBS : Prometheus scrape + Grafana up (#158)
├── 25-prometheusrule-alerte.sh       ← OBS : PrometheusRule → alerte firing (#158)
├── 26-loki-logql.sh                  ← OBS : Loki round-trip push → LogQL (ADR 0036, #186)
├── 27-gitops-workflow-deploy.sh      ← INTÉGRATION : push Gitea → Argo CD → workflows atlas → lineage (#231)
├── 28-ui-reachable.sh                 ← PORTAIL : UIs joignables via NodePort L4 (ADR 0092, #232)
├── 29-codelocation-externe.sh        ← INTÉGRATION : code-location externe (image+job) → run → lineage+S3 (#264)
├── 30-ha-3cp-cp-survival.sh           ← HA : survie à 1 panne CP (VIP bascule + quorum etcd, ADR 0047/0055, #250)
├── 31-contract-endpoints.sh          ← CONTRAT : endpoints du contrat réellement servis (ADR 0043)
├── 32-portal.sh                      ← PORTAIL : répond, liste les UI, NE PEUT PAS lire un Secret (ADR 0091)
├── 33-cache-cnpg.sh                  ← CACHE : primitives CNPG du cache partagé (connexion + UPSERT + advisory lock) (ADR 0093)
└── 34-build-gitops-digest.sh         ← BUILD→GITOPS : build → digest → write-back cluster/apps → Argo CD → pod PAR DIGEST (ADR 0095, #34)
```

Chaque script :

- est **idempotent** (rejouable sans état rémanent) ;
- pose des **annotations explicites** sur les objets créés
  (`test.cluster.dev/scenario: NN-name`) pour pouvoir les filtrer / nettoyer ;
- imprime sa sortie en `[étape]` clairs pour le suivi humain ;
- nettoie via un `trap EXIT` (à désactiver via `KEEP=1`) ;
- retourne `0` si OK, `1` sinon.

## Matrice des scénarios

| #   | Scénario                            | Tests                                                                                                                                                                             | Durée         | Couverture                                                                |
| --- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ------------------------------------------------------------------------- |
| 01  | PVC RBD write/read                  | StorageClass défaut, PVC Bound, écriture/lecture                                                                                                                                  | ~1 min        | Stockage bloc fonctionnel                                                 |
| 02  | Reschedule pod                      | Delete pod, re-création, **données persistantes**                                                                                                                                 | ~30s          | Découplage pod ↔ volume                                                   |
| 03  | Worker loss _(caduc)_               | Halt 1 worker, observation, restore                                                                                                                                               | ~5 min        | Réplicat ×3 + recovery Ceph — **caduc** (banc multi-node abandonné)       |
| 04  | Control plane loss _(caduc)_        | Halt control plane, observation API + workloads                                                                                                                                   | ~5 min        | SPOF assumé, etcd backup — **caduc** (banc multi-node abandonné)          |
| 05  | Replication bump                    | Pool ×3 → ×5 (si 5+ hôtes), refill                                                                                                                                                | ~5 min        | Évolution capacité (skip si < 5 hôtes)                                    |
| 06  | Object store smoke                  | datalake-ec + bucket + PUT/GET/DELETE                                                                                                                                             | ~3 min        | Stockage objet S3                                                         |
| 07  | Cilium connectivity                 | `cilium connectivity test` standard + Hubble si activé                                                                                                                            | ~10 min       | Réseau Pod-to-Pod, E/W, NetworkPolicy                                     |
| 08  | Resource limits audit               | Inspection des `requests`/`limits` actuels vs banc/prod                                                                                                                           | ~10s          | Cohérence dimensionnement                                                 |
| 09  | Restauration etcd                   | Témoin → snapshot → suppression → `etcdctl snapshot restore` → témoin revient                                                                                                     | ~3 min        | **Backup etcd RESTAURABLE** (pas juste produit)                           |
| 10  | Pod Security admission              | Pod privileged/hostNetwork **rejeté** à l'admission ; pod conforme admis                                                                                                          | ~1 min        | Durcissement pod (PSA, ADR 0014)                                          |
| 11  | NetworkPolicy deny                  | default-deny coupe l'egress ; allow-dns le rouvre **ciblé** (appliqué Cilium)                                                                                                     | ~2 min        | Durcissement réseau (NetworkPolicy + CNI)                                 |
| 12  | securityContext runtime             | Pod durci démarre ; non-root + rootfs RO **vérifiés au runtime**                                                                                                                  | ~1 min        | Durcissement pod (runAsNonRoot/readOnlyRootFS)                            |
| 13  | Host/node hardening                 | Réutilise `state.sh` → **PASS/FAIL** sur les couches hôte (sshd, auditd…)                                                                                                         | ~30s          | Durcissement hôte (secure.yml + first-access)                             |
| 14  | Cilium encryption + Hubble          | WireGuard **actif** (`cilium_wg0`, peers) + `hubble observe` opérationnel                                                                                                         | ~30s          | Durcissement réseau (WireGuard + Hubble, ADR 0019)                        |
| 15  | etcd encryption + audit             | Secret **chiffré** dans etcd (`k8s:enc:secretbox`) + audit-log ; rotation (ROTATE=1)                                                                                              | ~30s / ~2 min | Durcissement plan de contrôle (ADR 0014)                                  |
| 16  | Brute-force SSH → fail2ban          | Brute-force SSH (IP factice) → fail2ban **détecte + bannit** ; alerte si #131                                                                                                     | ~1 min        | **Sécurité active** offensif hôte (ADR 0025, D/A/R)                       |
| 17  | Pod d'évasion → PSA                 | `hostPath:/`, `hostPID`, `hostIPC` **rejetés** à l'admission ; pod conforme admis                                                                                                 | ~1 min        | **Sécurité active** offensif K8s (ADR 0025, D/R)                          |
| 18  | Exfiltration → NetworkPolicy        | Canal d'exfiltration **coupé** par default-deny, DNS légitime préservé ; drop Hubble                                                                                              | ~2 min        | **Sécurité active** offensif réseau (ADR 0025, D/R)                       |
| 19  | Chaos perte/partition _(caduc)_     | `tc netem` (perte/partition) sur 1 nœud → cluster **survit + reconverge** HEALTH_OK                                                                                               | ~7 min        | **Chaos** réseau (ADR 0025) — **caduc** (banc multi-node abandonné)       |
| 20  | Chaos kill de pods                  | Kill aléatoire répété → Kubernetes **recrée** les pods, santé Ceph préservée                                                                                                      | ~5 min        | **Chaos** reschedule (ADR 0025) — destructif                              |
| 21  | Chaos saturation CPU/mém            | Stresseur borné par `limits` → **OOMKilled**, le voisin **survit**, API réactive                                                                                                  | ~3 min        | **Chaos** isolation ressources (ADR 0025) — destr.                        |
| 22  | Alerte détecteurs → Mailpit         | Événement → **alerte arrive dans Mailpit** (skip tant que #131 absente)                                                                                                           | ~2 min        | **Sécurité active** maillon Alerte (ADR 0025)                             |
| 23  | Marquez ← OpenLineage               | Lineage d'un **run Dagster réel** ingéré et visible dans Marquez (skip si chaîne absente)                                                                                         | ~1 min        | **Intégration DataOps** maillon lineage (ADR 0028, #148)                  |
| 24  | Prometheus scrape + Grafana         | Targets Prometheus **UP** (scrape réel) + Grafana `/api/health` ok (skip si stack absente)                                                                                        | ~1 min        | **Observabilité** métriques (kube-prometheus-stack, #158)                 |
| 25  | PrometheusRule → alerte             | Alerte témoin `Watchdog` (toujours firing) bien **firing** → pipeline d'alerting vivant                                                                                           | ~2 min        | **Observabilité** alerting (PrometheusRule → Alertmanager, #158)          |
| 26  | Loki ← LogQL round-trip             | Log **poussé** via l'API Loki puis **relu** en LogQL → ingestion + backing S3 + requête                                                                                           | ~1 min        | **Observabilité** logs (Loki S3, ADR 0036, #186)                          |
| 27  | GitOps → workflows atlas (push e2e) | **Push** des **workflows atlas** sur Gitea → **webhook** → Argo CD **Synced/Healthy** → run Dagster + **lineage Marquez** (infra DataOps déjà posée par Ansible)                  | ~5 min        | **Intégration** workflows atlas par GitOps (ADR 0044/0045, #231)          |
| 28  | UI joignables via NodePort L4       | endpoints exposed:true du contrat → Service `<svc>-nodeport`, nodePort réel sondé `http://<IP-nœud>:<port>/` depuis un pod (https+-k pour k8s-dashboard) ; skip si aucun NodePort | ~2 min        | **Intégration** exposition UI (NodePort L4, ADR 0092, #232)               |
| 29  | Code-location externe (run e2e)     | Code-location externe branchée → run lancé par GraphQL `launchRun` → complétion SUCCESS → lineage Marquez (+ objet S3 optionnel) ; skip si non fournie                            | ~3 min        | **Intégration** code-location externe (ADR 0022/0045, #264)               |
| 31  | Contrat cluster→atlas (endpoints)   | Pour chaque endpoint du contrat (`contract/endpoints.example.yaml`) : Service présent au bon port + répond (TCP/HTTP) ; skip/strict par endpoint (STRICT_CONTRACT)                | ~2 min        | **Contrat** d'interface tenu (ADR 0043) — transversal (postgres…mlflow)   |
| 30  | ha-3cp — survie d'1 panne _(caduc)_ | Arrêt du CP **porteur de la VIP** → kube-vip **bascule** (VIP répond toujours) + **quorum etcd 2/3** + API joignable ; restore → 3/3 (topologie `ha-3cp` requise)                 | ~3 min        | **HA control-plane** — **caduc** : `ha-3cp` abandonné (ADR 0097)          |
| 33  | Cache CNPG (primitives)             | Rôle `cache` → base `cache` (connexion) + UPSERT `ON CONFLICT` atomique (1 ligne / N upserts) + `pg_advisory_lock` exclusif inter-sessions ; skip/strict (STRICT_CACHE)           | ~2 min        | **Cache partagé** par réutilisation CNPG (ADR 0093) — primitives Postgres |
| 34  | Build → GitOps par digest           | Build jouet node-side → **digest** lu → write-back Gitea `cluster/apps` (par `@sha256`) → Argo CD **Synced/Healthy** → pod **tiré PAR DIGEST** ; skip/strict (STRICT_DIGEST)      | ~4 min        | **Fabrique→déploiement immuable** : premier pas ADR 0095 §1.a (banc)      |

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
> complète : [../RESULTS.md](/cluster/bench/RESULTS/) (section déroulé
> scénarios + #7).

### Groupe durcissement (10-13)

> 🔒 **10-13 — durcissement (pod + hôte), validés banc 2026-06-01.** Ce groupe
> teste la **sécurité**, pas la résilience. Les **10/11/12** sont des assertions
> 100 % transposables en prod (admission API, application des NetworkPolicy par
> le CNI, contrainte runtime du conteneur — aucune dépendance arm64/Vagrant). Le
> **13** réutilise
> [`bootstrap/state.sh`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/state.sh)
> (source de vérité du dépôt) et n'échoue que sur un drift host `✗` — une couche
> opt-in non activée reste un `skip` (cf.
> [IMPLICATIONS.md](/cluster/bootstrap/security/IMPLICATIONS/)). Sur le banc, le
> 13 sort **FAIL attendu** tant que `first-access.sh` n'y a pas posé le
> durcissement sshd (le banc utilise le compte Vagrant) ; en prod (sshd durci +
> couches `secure.yml` actives) il passe. Il a besoin de l'accès SSH aux nœuds
> (`SSH_OPTS`/`HOSTS`), pas de `kubectl`.
>
> Le **14** (durcissement réseau Cilium,
> [ADR 0019](/cluster/docs/decisions/0019-durcissement-reseau-cilium/)) vérifie
> que le chiffrement **WireGuard** est réellement actif dans le datapath
> (`cilium_wg0` + peers, pas seulement la config) et que **Hubble** retourne des
> flux. Pré-requis : Cilium installé par
> [`cni.sh`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/cni.sh)
> avec `encryption.enabled` + `hubble.enabled`. `kubectl`-only.
>
> Le **15** (durcissement plan de contrôle,
> [ADR 0014](/cluster/docs/decisions/0014-durcissement-kubeadm-init/)) prouve
> via `etcdctl`, **sur le control plane (SSH)**, qu'un Secret est chiffré
> at-rest dans etcd (`k8s:enc:secretbox:`) et que l'audit-log API est produit.
> `ROTATE=1` déroule en plus la rotation de clé et vérifie qu'un Secret témoin
> survit (réversible). Variables `CP_IP`/`CP_PORT`/`SSH_KEY` (comme le scénario
> 09). Pré-requis : `kubeadm init --config` avec `EncryptionConfiguration`
> appliqué.

### Groupe sécurité active (16-22)

> 🚨 **16-22 — sécurité ACTIVE (chaos + attaques contrôlées), cadrée par
> [ADR 0025](/cluster/docs/decisions/0025-securite-active-chaos-attaques-controlees/).**
> Contrairement aux 10-15 (défense **passive** : on vérifie qu'une contrainte
> _est en place_), ce groupe **passe à l'acte** et asserte la chaîne **Détection
> → Alerte → Réaction (D/A/R)**, ou dégrade l'infra pour vérifier qu'elle
> **survit**.
>
> **À LANCER UNIQUEMENT SUR UN BANC JETABLE** — jamais une topologie réelle/prod
> ni une cible tierce (garde-fous ADR 0025). Chaque scénario porte une **garde «
> banc-only »** qui refuse de tourner si la cible n'est pas en plage de banc (IP
> privée), sauf `BANC=1` explicite. Toute perturbation est **réversible**
> (cleanup `trap EXIT`, `KEEP=1` pour inspecter).
>
> - **Offensifs.** **16** (brute-force SSH → **fail2ban bannit**) : côté HÔTE
>   (SSH), simule le brute-force en injectant des échecs sshd pour une **IP
>   factice** (RFC 5737, jamais routée → ni auto-ban de l'opérateur, ni cible
>   tierce), puis vérifie le ban (`fail2ban-client status sshd`) et l'unban au
>   cleanup. **17** (pod d'évasion → **PSA rejette**) : `kubectl`-only, complète
>   le 10 sur `hostPath:/`, `hostPID`, `hostIPC`. **18** (exfiltration →
>   **NetworkPolicy coupe**) : `kubectl`-only, prolonge le 11 ; la cible
>   d'exfiltration est **interne et déterministe** (jamais l'Internet).
> - **Chaos** (destructifs → `run-all.sh` attend `HEALTH_OK` après). **19**
>   (perte/partition réseau, `tc netem` **via SSH** sur une vraie VM — réutilise
>   le pattern du spike `clustermesh-latency`, aucun chemin Lima en dur ; cible
>   **un seul** nœud). **20** (kill aléatoire de pods, `kubectl` ; **exclut le
>   control plane** par défaut, `SAFE=1`). **21** (saturation CPU/mém, `kubectl`
>   ; `resources.limits` **obligatoires** → le stresseur est OOMKilled, le
>   voisin survit).
> - **Alerte.** **22** ferme le maillon `[A]` de bout en bout (événement →
>   **alerte dans Mailpit**). **Dépend de l'issue #131** (brancher l'alerting
>   hôte sur Mailpit/Mailgun) : tant qu'elle n'est pas livrée, le 22 **skippe
>   neutrement** et le maillon `[A]` des 16/18/17 est **best-effort / N/A**.
>   `STRICT_ALERT=1` le fait échouer si la chaîne est absente (CI post-#131).
>
> **Détection runtime différée** : aucun Falco/Tetragon (cf.
> [note runtime/admission](/cluster/docs/audit/2026-05-29/note-runtime-admission/),
> ADR 0025 §4) — l'alerte sur un comportement adverse _dans_ un pod n'est pas
> couverte.
>
> Lancer (banc) : `KUBECONFIG=… bash bench/scenarios/17-pod-evasion-psa.sh`
> (kubectl-only) ;
> `TARGET_IP=<ip-noeud> bash bench/scenarios/16-brute-force-ssh-fail2ban.sh`
> (SSH) ;
> `NODE_IP=<ip-noeud> bash bench/scenarios/19-chaos-perte-paquets-partition.sh`
> — au banc Lima, les IP des nœuds viennent de l'inventaire généré
> (`bench/lima/.work/inventory.yaml`), pas d'une plage Vagrant figée.

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
[`storage/ceph/storageClass/datalake/smoke-test.sh`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/storageClass/datalake/smoke-test.sh)
: crée un bucket, écrit un fichier, le relit, le supprime. Verdict : ✅ si le
`CephObjectStore datalake` est `Connected` et le `ObjectBucketClaim` provisionne
le Secret.

### Que se passe-t-il si le control plane plante ?

Cf. scénario 04. Récap :

- **API K8s injoignable** → impossible de scheduler de nouveaux pods, d'ouvrir
  une session `kubectl`, de redémarrer un workload tombé.
- **etcd inaccessible** → la sauvegarde horaire (rôle
  [`etcd-backup`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/roles/etcd-backup))
  permet de restaurer ailleurs.
- **Workloads en cours** : continuent tant que le kubelet local tourne. Cilium
  continue d'assurer le réseau Pod-to-Pod. Ceph reste opérationnel (mons en
  quorum sur les workers).
- **Restauration** : voir [`bootstrap/RUNBOOK.md`](/cluster/bootstrap/RUNBOOK/)
  section « Restauration etcd (procédure) ».

### Tests Cilium

Cf. scénarios 07 et 14 :

- **07** — `cilium connectivity test` : suite officielle, 200+ checks (Pod ↔
  Pod, Pod ↔ Service, Pod ↔ World, NetworkPolicy, etc.).
- **14** — durcissement réseau
  ([ADR 0019](/cluster/docs/decisions/0019-durcissement-reseau-cilium/)) : le
  trafic pod-to-pod inter-nœuds est **chiffré par WireGuard**
  (`encryption.enabled`, interface `cilium_wg0`) et **Hubble** (relay + CLI,
  sans UI) est activé pour l'observabilité des flux (`hubble observe`). Le
  scénario 14 vérifie que les deux sont **réellement opérationnels**, pas
  seulement configurés.

### Le durcissement (pod / hôte) est-il vérifié ?

Oui, par les scénarios 10-13 :

- **Pod (10/11/12)** — `kubectl`-only, comme 01-08 :

  ```bash
  bash bench/scenarios/10-pod-security-admission.sh    # PSA bloque privileged/hostNetwork
  bash bench/scenarios/11-networkpolicy-default-deny.sh # Cilium applique default-deny + allow
  bash bench/scenarios/12-securitycontext-runtime.sh    # non-root + rootfs RO au runtime
  ```

  Ils créent leur propre namespace, posent les contraintes (PSA `baseline`,
  `default-deny-all`, `securityContext` durci) et **vérifient le comportement
  réel** (rejet à l'admission, egress coupé, écriture rootfs refusée). Ce que
  PSA et `securityContext` couvrent est tracé dans
  [ADR 0014](/cluster/docs/decisions/0014-durcissement-kubeadm-init/).

- **Hôte (13)** — a besoin de l'**accès SSH** aux nœuds (pas de `kubectl`) :

  ```bash
  HOSTS='cp1 node1 node2' bash bench/scenarios/13-host-node-hardening.sh
  # banc Lima : l'accès node-side passe par `limactl shell <instance>`
  # (le nom d'instance Lima, pas une IP ni un port forwardé). Les IP réelles des
  # nœuds sont fournies par l'inventaire généré (bench/lima/.work/inventory.yaml).
  ```

  Il **réutilise**
  [`bootstrap/state.sh`](https://github.com/univ-lehavre/cluster/blob/main/bootstrap/state.sh)
  et échoue sur tout drift des couches hôte (sshd durci, auditd, fail2ban,
  postfix, ufw, smartd). `STRICT_OPTIN=1` fait en plus échouer si **aucune**
  couche `secure.yml` n'est active (attendu en prod). Une couche opt-in non
  activée reste un `skip` neutre (cf.
  [IMPLICATIONS.md](/cluster/bootstrap/security/IMPLICATIONS/)).

### Le cluster survit-il au chaos (perte réseau, kill, saturation) ?

Oui, c'est ce que prouvent les scénarios **chaos 19-21**
([ADR 0025](/cluster/docs/decisions/0025-securite-active-chaos-attaques-controlees/))
— **sur banc jetable uniquement** :

- **19 — perte/partition réseau** (`tc netem` sur 1 nœud) : pendant la
  dégradation, l'API reste joignable et Ceph tient au pire en `HEALTH_WARN`
  (réplica ×3, `min_size 2`, `failureDomain: host`) ; après retrait du netem, le
  cluster **reconverge** vers `HEALTH_OK`.
- **20 — kill aléatoire de pods** : Kubernetes **recrée** les pods (généralise
  le 02) ; le control plane est **exclu** du tirage par défaut (`SAFE=1`).
- **21 — saturation CPU/mémoire** : les `resources.limits` **contiennent**
  l'impact (le stresseur est OOMKilled, lien scénario 08) ; le pod voisin reste
  `Ready`. Sans limites, ce scénario ne tournerait pas (garde-fou).

Tout est **réversible** (cleanup `trap EXIT`).

### Les détecteurs alertent-ils vraiment ?

C'est l'objet des scénarios **16** et **22**. La **détection** et la
**réaction** sont prouvées : fail2ban **bannit** un brute-force (16), PSA
**rejette** une évasion (17), Cilium **coupe** une exfiltration (18). Le maillon
**alerte**, lui, dépend de l'**issue #131** (brancher l'alerting hôte sur
Mailpit/Mailgun) :

- tant que #131 n'est pas livrée, le **22 skippe neutrement** et le maillon
  `[A]` des scénarios offensifs est **best-effort** (WARN) ou `N/A` ;
- une fois #131 mergée, le **22** vérifie de bout en bout qu'un événement de
  sécurité **produit un mail** dans Mailpit (`STRICT_ALERT=1` en CI).

La **détection comportementale runtime** (shell dans un pod, exec inattendu)
n'est **pas** couverte : le choix Falco/Tetragon est **différé** (ADR 0025 §4,
cf.
[note runtime/admission](/cluster/docs/audit/2026-05-29/note-runtime-admission/)).

### Le build d'image se déploie-t-il par digest immuable (zéro tag mutable) ?

C'est l'objet du scénario **34** — le **premier pas** de
[ADR 0095](/cluster/docs/decisions/0095-build-applicatif-evenementiel-in-cluster/)
(§1.a) et du
[plan build événementiel](/cluster/docs/plans/plan-build-evenementiel-gitops/)
(étape 4). Il prouve **au banc** Lima mono-nœud local-path
([ADR 0085](/cluster/docs/decisions/0085-preuves-applicatives-local-path/)) la
chaîne **fabrique → déploiement par digest** : une image **jouet contrôlée par
cluster** est buildée node-side (`nerdctl`/`buildkit` via `limactl shell`,
[ADR 0033](/cluster/docs/decisions/0033-orchestration-ansible-platform-dataops/)),
son **digest** réel est lu (`RepoDigests`) puis **écrit dans Gitea
`cluster/apps`** (patron Contents API, create-or-update idempotent) avec une
référence `registry:80/<app>@sha256:…` — **jamais** un tag mutable
([ADR 0095](/cluster/docs/decisions/0095-build-applicatif-evenementiel-in-cluster/)
§2). Argo CD réconcilie (la racine app-of-apps voit le fichier → crée
l'Application fille), elle devient **Synced/Healthy**, et le **pod tourne tiré
PAR DIGEST** (`.spec.containers[].image` se termine par `@sha256:…`). Gates :
(1) digest non vide ; (2) le manifeste poussé référence `@sha256` (pas un tag) ;
(3) Application Synced/Healthy ; (4) pod Running ET image par digest.

- **Garde banc absolue** : le scénario MUTE Gitea + Argo CD → il EXIGE que le
  cluster du contexte courant soit le banc (`EXPECTED_CLUSTER`, défaut
  `cluster-banc`) et **refuse** `cluster-prod` (`die`), symétrique inverse de la
  garde `assert_prod_target` du seed. Lancer avec
  `KUBECONFIG=bench/lima/.work/kubeconfig`.
- **Image de test = jouet, pas `citation`** : on isole la preuve de la chaîne
  (que cluster maîtrise de bout en bout) de la **tension citation** — le seed
  n'injecte le digest citation que via le placeholder `__CITATION_IMAGE__`
  qu'atlas expose (frontière
  [ADR 0094](/cluster/docs/decisions/0094-frontiere-deploiement-applicatif/)).
  `MODE=citation` **détecte** l'absence du placeholder et **skippe** avec un
  message clair (atlas doit factoriser ce point d'injection).
- `STRICT_DIGEST=1` fait **échouer** au lieu de skip si un prérequis manque (CI
  banc), calque `STRICT_CACHE` du 33 ; `KEEP=1` conserve les ressources de test
  (sinon `trap EXIT` les nettoie : Application, Deployment, fichiers Gitea,
  image jouet). Le **run applicatif observable** reste hors périmètre (scénario
  29).

Lancer (banc) :
`STRICT_DIGEST=1 KUBECONFIG=bench/lima/.work/kubeconfig bash bench/scenarios/34-build-gitops-digest.sh`.

## Exécution

Lancer un scénario individuellement :

```bash
KUBECONFIG=~/.kube/config-banc bash bench/scenarios/01-block-rwx-write-read.sh
```

Lancer toute la suite (s'arrête au premier échec) :

```bash
for s in bench/scenarios/[0-9]*.sh; do
    echo "▶ $s"
    bash "$s" || { echo "✗ $s a échoué — abandon"; exit 1; }
done
```

Nettoyage manuel si un script est sorti `KEEP=1` :

```bash
kubectl delete all,pvc -l 'test.cluster.dev/scenario' --all-namespaces
```

## État courant

L'état d'exécution des scénarios sur le banc **n'est pas figé ici** (il
périmerait) : il vit dans le **journal des runs Lima**, source vivante et datée
— [`bench/lima/RESULTS.md`](/cluster/bench/lima/RESULTS/). L'historique Vagrant
(déprécié) reste dans [`bench/RESULTS.md`](/cluster/bench/RESULTS/), non réécrit
(honnêteté des Runs,
[ADR 0052](/cluster/docs/decisions/0052-reproductibilite-des-resultats/)).
