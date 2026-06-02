# 0014 — Durcissement du plan de contrôle (`kubeadm init` nu)

## Contexte

Le control plane est initialisé par
[`k8s-initialization`](../../bootstrap/roles/k8s-initialization/tasks/main.yaml)
avec un `kubeadm init` **en ligne de commande** (sans `--config`). L'audit P6
([06-securite](../audit/06-securite.md), item #21) relève trois manques au
niveau du plan de contrôle, qu'**aucun ADR ne couvrait** jusqu'ici :

1. **Aucune audit-policy API server** : les appels à l'API ne sont pas
   journalisés (qui a fait quoi sur le cluster).
2. **Pas d'`EncryptionConfiguration`** : les Secrets Kubernetes sont stockés en
   clair (base64) dans etcd — et donc aussi dans les snapshots etcd.
3. **Aucune Pod Security admission** : rien n'empêche un pod `privileged`,
   `hostPath`, `hostNetwork`, etc.

Contrairement aux compromis réseau/applicatifs (registry HTTP, RStudio sans
auth) déjà tracés en ADR 0010-0012, ces trois points n'étaient ni implémentés ni
explicitement assumés. Cet ADR tranche chacun.

Modèle de menace rappelé : cluster **mono-tenant** de recherche, **réseau privé
isolé** (ADR 0003), **mono-admin**. Les snapshots etcd sont déjà créés avec des
permissions restrictives ([`etcd-backup`](../../bootstrap/roles/etcd-backup/)),
mais non chiffrés (cf. audit, constat distinct).

## Décision

Traitement **différencié** des trois points selon leur rapport risque/valeur.

### 1. Pod Security admission — **à activer** (faible risque)

Le Pod Security Admission controller est **intégré** depuis K8s 1.25 (pas de
webhook externe). On l'active par **labels de namespace** plutôt que par
`AdmissionConfiguration` globale, ce qui évite de toucher le `kubeadm init` et
se fait pod-par-namespace sans risque de blocage cluster-wide :

```yaml
metadata:
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/warn: restricted
```

- Niveau **`baseline` en `enforce`** sur les namespaces applicatifs maison
  (`rstudio`, `registry`, `default`) — bloque le plus dangereux (privileged,
  hostPID/IPC, hostNetwork) sans casser les workloads actuels (déjà durcis, cf.
  P6 #23).
- **`restricted` en `warn`** (avertit sans bloquer) pour préparer un
  durcissement ultérieur.
- **Pas** d'enforce sur `rook-ceph` : l'operator/CSI Ceph a légitimement besoin
  de privilèges élevés (montage, accès disque).

Mise en œuvre : labels posés sur les manifestes `Namespace` de
[`rstudio`](../../apps/rstudio/namespace.yaml) et
[`registry`](../../platform/container-registry/namespace.yaml). Le namespace
`default` (WordPress/MySQL) n'a pas de manifeste versionné (créé par K8s) → ses
labels sont à poser à la main
(`kubectl label ns default pod-security.kubernetes.io/enforce=baseline`) ou via
le futur manifeste si l'exemple WordPress migre vers un namespace dédié.

### 2. `EncryptionConfiguration` (Secrets etcd) — **implémenté** [2026-06-02]

Le chiffrement at-rest des Secrets dans etcd se pose via un `--config` kubeadm
**dès l'init**. C'est désormais fait : le rôle
[`k8s-initialization`](../../bootstrap/roles/k8s-initialization/) passe à
`kubeadm init --config` (au lieu des flags) avec un `EncryptionConfiguration`
provider **`secretbox`** (XSalsa20-Poly1305 ; pas de KMS externe à gérer,
cohérent avec l'ADR 0003).

Mise en œuvre :

- la **clé** (32 octets aléatoires base64) est générée **sur le nœud au
  bootstrap**, stockée dans `/etc/kubernetes/enc/key1.b64` (0600 root, **hors
  dépôt, jamais commitée**) et **une seule fois** (`creates:` — la régénérer
  rendrait illisibles les Secrets déjà chiffrés) ;
- l'`EncryptionConfiguration` liste `secretbox` (chiffre) puis `identity`
  (permet de lire les Secrets écrits avant activation) ;
- montée dans le static pod de l'API server via `apiServer.extraVolumes`.

**Validé sur banc** (RESULTS Run #8, scénario
[`15-etcd-encryption-audit.sh`](../../test/scenarios/15-etcd-encryption-audit.sh))
: la valeur brute d'un Secret lue dans etcd via `etcdctl` commence par
`k8s:enc:secretbox:v1:key1:` (et non en clair).

> **Rotation de clé.** Procédure manuelle documentée au
> [`bootstrap/RUNBOOK.md`](../../bootstrap/RUNBOOK.md) (§ Rotation de la clé de
> chiffrement etcd) : ajouter une 2ᵉ clé en tête → redémarrer l'API server →
> réécrire tous les Secrets → retirer l'ancienne clé. Déroulée et prouvée
> réversible par le scénario 15 (`ROTATE=1`, le Secret témoin survit). Pas de
> KMS / rotation automatique — choix assumé pour un cluster mono-admin (cf.
> ADR 0003) ; à revoir si le cluster s'ouvre.

Risque résiduel restant : la **clé vit en clair sur le disque du control plane**
(`/etc/kubernetes/enc/`). Un accès disque au nœud control plane reste donc hors
de portée de cette protection — mais le **vol d'un snapshot etcd** (le risque n°
1 visé) est désormais couvert (les Secrets y sont chiffrés). Reste à chiffrer
les snapshots eux-mêmes au repos (constat audit voisin).

### 3. Audit-policy API server — **implémenté** [2026-06-02]

Posée par le même `kubeadm --config` (`apiServer.extraArgs.audit-policy-file` +
`audit-log-path` + rotation `audit-log-max*`). Politique **`Metadata`-level**
par défaut
([`audit-policy.yaml`](../../bootstrap/roles/k8s-initialization/files/audit-policy.yaml))
: journalise qui/quoi/quand sans le corps des requêtes, avec exclusion
(`level: None`) du bruit (lectures kubelet/scheduler, `/healthz`, events,
leases). Logs dans `/var/log/kubernetes/audit/audit.log`.

**Validé sur banc** (scénario 15) : l'audit-log est produit et contient des
entrées `Metadata`. Couvre désormais les **appels API directs** (`kubectl` d'un
humain), que l'audit-log Ansible et `auditd` ne voyaient pas.

## Statut

Accepted (2026-06-01). Points 2 et 3 **implémentés le 2026-06-02** (PR
durcissement etcd/audit) — cet ADR n'est donc plus en partie « dette ».

## Conséquences

**Bénéfices.**

- Les trois manques sont désormais **traités** : PodSecurity `baseline` actif,
  **chiffrement etcd et audit-policy implémentés** (plus en dette) via le
  `--config` kubeadm.
- PodSecurity `baseline` pose une barrière contre les pods privilégiés sans
  dépendre du `--config` kubeadm ni risquer l'init.
- Les Secrets sont **chiffrés at-rest** dans etcd (et donc dans les snapshots) ;
  les appels API directs sont **journalisés** (audit-policy Metadata).

**Coûts assumés.**

- **Clé de chiffrement en clair sur le control plane** (`/etc/kubernetes/enc/`,
  0600 root) : un accès disque au nœud control plane permet de la lire. Pas de
  KMS (choix ADR 0003). Le risque visé (vol de snapshot etcd) est couvert ; le
  durcissement au-delà (KMS, chiffrement de la partition) est hors modèle.
- **Volume d'audit-log** : la policy Metadata + exclusions limite le volume,
  mais l'audit-log croît — rotation `audit-log-max*` posée (30 j / 10 backups /
  100 Mo).
- **Migration à chaud** : sur un cluster déjà init (≠ greenfield), activer le
  chiffrement laisse les Secrets **existants** en clair jusqu'à réécriture
  (`kubectl get secrets -A -o json | kubectl replace -f -`). Au bootstrap from
  scratch, tous les Secrets naissent chiffrés.

## À revoir

- **Chiffrer les snapshots etcd** au repos (constat audit voisin) — la clé de
  chiffrement etcd les protège déjà partiellement (Secrets chiffrés dedans),
  mais le reste du snapshot est en clair.
- Si le cluster s'ouvre au-delà du mono-tenant / réseau isolé → envisager un
  **KMS** (rotation gérée) au lieu de la clé secretbox locale, et passer la
  policy d'audit à `Request`/`RequestResponse` sur les ressources sensibles.
- Envisager `restricted` en `enforce` (au lieu de `baseline`) une fois tous les
  workloads vérifiés conformes.
