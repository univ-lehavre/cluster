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

### 2. `EncryptionConfiguration` (Secrets etcd) — **dette assumée**, à faire au rebuild

Le chiffrement at-rest des Secrets dans etcd nécessite un `--config` kubeadm
posant un `EncryptionConfiguration` (provider `secretbox` ou `aescbc`) **dès
l'init** — donc applicable proprement uniquement à la **reconstruction
greenfield** du cluster, pas à chaud sans réécrire les Secrets existants.

Décision : **non implémenté pour l'instant, tracé comme dette.** Justification
du report (pas de l'abandon) :

- La compensation principale (ADR 0003) tient : etcd n'est joignable que sur le
  réseau privé, et les snapshots ont des permissions restreintes.
- Le risque résiduel réel est le **vol d'un snapshot** ou l'**accès disque au
  nœud control plane** — scénarios hors du modèle de menace réseau isolé.

À implémenter **au prochain rebuild** : `EncryptionConfiguration` secretbox +
clé hors dépôt (montée par Ansible Vault ou fichier non versionné), via le
`--config` kubeadm. Lié au chiffrement des snapshots etcd (constat audit
voisin).

### 3. Audit-policy API server — **dette assumée**, à faire avec le `--config`

L'audit-policy API server (journalisation des appels) se pose aussi via le
`--config` kubeadm (`apiServer.extraArgs.audit-policy-file` + `audit-log-path`).
Même contrainte que le point 2 (modifie l'init) → groupé avec lui.

Décision : **non implémenté, tracé comme dette**, à livrer en même temps que
l'`EncryptionConfiguration` au rebuild, avec une policy `Metadata`-level par
défaut (journalise qui/quoi/quand sans le corps des requêtes). Compensation
actuelle : l'audit-log **Ansible**
([`audit-log`](../../bootstrap/roles/audit-log/)) trace les playbooks joués, et
`auditd` côté nœud les syscalls privilégiés — mais ni l'un ni l'autre ne couvre
les appels API directs (`kubectl` d'un humain).

## Statut

Accepted (2026-06-01).

## Conséquences

**Bénéfices.**

- Les trois manques sont désormais **explicitement décidés**, plus des trous
  silencieux : PodSecurity activable tout de suite, chiffrement etcd et
  audit-policy planifiés avec leur condition de réalisation (le rebuild).
- PodSecurity `baseline` pose une barrière contre les pods privilégiés sans
  dépendre du `--config` kubeadm ni risquer l'init.

**Coûts assumés.**

- **Secrets etcd en clair** jusqu'au rebuild : un snapshot volé ou un accès
  disque au control plane expose les Secrets. Risque accepté dans le modèle
  réseau isolé / mono-admin, à lever au rebuild.
- **Pas de journal des appels API** : une action via `kubectl` (avec un
  kubeconfig admin) n'est pas tracée côté API. Le cluster étant mono-admin, la
  traçabilité repose sur l'audit-log Ansible et la discipline d'accès au
  kubeconfig.

## À revoir

- **Au prochain rebuild** : implémenter `EncryptionConfiguration` (secretbox) +
  audit-policy via `--config` kubeadm dans
  [`k8s-initialization`](../../bootstrap/roles/k8s-initialization/tasks/main.yaml).
  Cet ADR passera alors en partie « superseded ».
- Si le cluster s'ouvre au-delà du mono-tenant / réseau isolé → ces deux points
  deviennent bloquants (à faire avant ouverture).
- Envisager `restricted` en `enforce` (au lieu de `baseline`) une fois tous les
  workloads vérifiés conformes.
