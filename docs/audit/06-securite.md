# 6 — Sécurité

**Note : 3,2 / 5**

> **État factuel :** `gitleaks` ne trouve **aucun secret** sur 119 commits ;
> aucun secret en clair dans les manifests de prod.

Le durcissement OS/SSH est de très bon niveau et documenté, et les choix de
moindre sécurité applicative (registry HTTP, RStudio sans auth, dashboard
cluster-admin, pas de chiffrement Ceph) sont tracés dans des ADR de qualité avec
coûts assumés et conditions de révision. **Le problème central :** la
compensation invoquée par tous ces ADR — réseau privé isolé + Tailscale — est
présentée comme **optionnelle** et n'est garantie par **aucun contrôle
versionné** (ni NetworkPolicy, ni pare-feu appliqué, ni ACL). Au niveau plan de
contrôle, le `kubeadm init` est nu (pas d'audit-log API, pas de chiffrement
at-rest etcd, pas de PodSecurity admission), et les snapshots etcd — qui
contiennent tous les Secrets — sont en clair.

> **Note de calibration :** la majorité de ces constats ont été **ramenés de
> majeur à mineur** par la vérification adversariale, car ils correspondent à
> des risques **assumés et documentés en ADR** dans un contexte mono-tenant /
> mono-admin / réseau privé / données de recherche non réglementées. Ce ne sont
> pas des failles cachées, mais des compromis dont l'_enforcement_ et la
> _traçabilité_ sont incomplets. La tension RGPD (voir [08](08-operabilite.md))
> remet toutefois en cause l'hypothèse « données non réglementées ».

## Points forts

- **Durcissement SSH exemplaire et idempotent** : drop-in `00-hardening.conf`
  (`PasswordAuthentication no`, `PermitRootLogin no`, `AllowUsers debian`,
  `MaxAuthTries 3`, `ClientAlive*`), re-posé par le rôle avec
  `block/rescue/ always` et rollback de `sshd_config.bak` si le reload échoue.
- Défense en profondeur anti-brute-force : fail2ban + UFW `limit OpenSSH` +
  `MaxAuthTries`, compromis documentés.
- auditd avec règles de référence ; unattended-upgrades avec reboot nocturne ;
  expiration mot de passe.
- `securityContext` durci sur le registry (runAsNonRoot, uid 65532,
  readOnlyRootFilesystem, drop ALL, seccomp RuntimeDefault) et le toolbox Ceph.
- Dashboard K8s : tokens `TokenRequest` éphémères (≤ 8 h) au lieu de Secret
  long-lived, avec garde-fou `state.sh` couche 7 qui échoue si le Secret legacy
  réapparaît.
- Aucun secret en clair en prod (`secretKeyRef`, Secrets générés par
  l'operator).
- ADR de sécurité avec sections « À revoir si » explicites — dette consciente.
- Sauvegarde etcd robuste (snapshot via `crictl`, vérif d'intégrité, umask 077,
  0600/0700).

## Constats

### Majeur (→ vérifié mineur) — Compensation réseau non enforce

- **Fichier** : ADR 0003:40-46, 0011:27-33, 0012:31-39
- **Constat** : les quatre ADR de moindre sécurité reposent sur le même réseau
  privé isolé + Tailscale, déclaré **optionnel** ; le dépôt ne contient aucun
  manifeste Tailscale operator, aucune ACL, aucune NetworkPolicy, et le pare-feu
  n'est pas appliqué. Si le réseau cesse d'être isolé, tout le trafic Ceph +
  credentials S3 est sniffable, et registry/RStudio/dashboard sont atteignables
  sans auth. _Ramené à mineur : compromis ADR délibéré, mono-tenant labo ;
  défaut d'enforcement/traçabilité, pas une faille active._
- **Recommandation** : matérialiser l'hypothèse de confiance — committer le
  Tailscale operator + ACL et le marquer **requis** (pas optionnel), **ou**
  documenter dans `SAFEGUARDS.md` le contrôle réseau réel (VLAN, pare-feu
  périmétrique) ; ajouter à `state.sh` une vérification d'exposition
  (NodePort/LoadBalancer).

### Majeur (→ vérifié suggestion) — Aucune NetworkPolicy

- **Fichier** : transversal (`kind: NetworkPolicy` = 0)
- **Constat** : combiné au registry HTTP anonyme, RStudio `DISABLE_AUTH` et Ceph
  en clair, un seul pod compromis peut pusher des images empoisonnées, lire/
  écrire la PVC RStudio et sniffer Ceph (pas de barrière est-ouest). _Ramené à
  suggestion : explicitement acté en ADR 0012 « pas de NetworkPolicy → cohérent
  avec le mono-tenant », avec déclencheurs « À revoir si »._
- **Recommandation** : NetworkPolicies de base (default-deny par namespace puis
  allow ciblé) ; Cilium étant le CNI, `CiliumNetworkPolicy` permet aussi de
  logguer les flux refusés.

### Majeur (→ vérifié mineur) — Pare-feu UFW jamais appliqué, sans jeu de règles K8s

- **Fichier** : `bootstrap/security/secure.yml:95-101`,
  `…/network/tasks/ufw.yml:34-38`
- **Constat** : UFW en tag `never` (jamais joué) ; n'autorise que OpenSSH. Soit
  UFW est inactif (surface complète exposée), soit l'activer sans étendre les
  règles **coupe** le cluster. Deux défauts non documentés : (1) IMPLICATIONS/
  RUNBOOK renvoient à un dossier `roles/network/files/` **inexistant** ; (2) la
  règle SSH est `any` (« depuis Internet ») alors que l'ADR 0003 affirme « pas
  de routage Internet ». _Ramené à mineur : absence cohérente avec le modèle de
  menace documenté._
- **Recommandation** : fournir un jeu de règles UFW K8s/Cilium/Ceph prêt à
  l'emploi ; restreindre SSH à la plage d'administration ; signaler l'absence
  d'UFW comme drift dans `state.sh`.

### Majeur (→ vérifié mineur) — `kubeadm init` nu (audit-log / chiffrement etcd / PodSecurity)

- **Fichier** : `bootstrap/roles/k8s-initialization/tasks/main.yaml:12-18`
- **Constat** : pas de `--config`. Conséquences vérifiées : (1) aucune
  audit-policy API server ; (2) pas d'`EncryptionConfiguration` → Secrets en
  clair (base64) dans etcd ; (3) aucune Pod Security admission ni label
  `pod-security.kubernetes.io` → rien n'empêche un pod `privileged`/`hostPath`.
  (`audit-log-baseline.yaml` concerne l'audit-log **Ansible**, pas l'audit K8s.)
  _Ramené à mineur dans le modèle de menace documenté, mais non assumé
  formellement (aucun ADR ne couvre ces 3 points)._
- **Recommandation** : `ClusterConfiguration` kubeadm activant audit-policy,
  `EncryptionConfiguration` (aescbc/secretbox), PodSecurity admission
  `baseline`/ `restricted` par namespace ; **ou** tracer ces choix dans un ADR.

### Majeur (→ vérifié mineur) — Snapshots etcd en clair

- **Fichier** : `bootstrap/roles/etcd-backup/templates/etcd-snapshot.sh.j2`
- **Constat** : snapshots en clair (bonnes permissions mais aucun chiffrement) ;
  sans `EncryptionConfiguration`, ils contiennent en clair tous les Secrets
  (wordpress, credentials S3, Ceph admin). Le vol d'un disque/nœud retiré les
  expose. _Ramené à mineur : même classe de risque déjà assumée par l'ADR 0003 ;
  gap de doc RUNBOOK réel._
- **Recommandation** : chiffrement at-rest etcd (couvre mécaniquement les
  snapshots) ; à défaut chiffrer le fichier snapshot (age/gpg, clé hors-nœud) ;
  mentionner le risque dans le RUNBOOK.

### Majeur (→ vérifié mineur) — Déploiement RStudio sans `securityContext`

- **Fichier** : `apps/rstudio/deployment.yaml:15-33`
- **Constat** : aucun `securityContext` (vs registry/toolbox durcis), combiné à
  `DISABLE_AUTH=true` (shell direct pour quiconque atteint le port 8787). Le «
  non-root » vient de l'image, pas d'un contrôle imposé. _Ramené à mineur :
  impact borné par le modèle mono-tenant ADR 0012._
- **Recommandation** : `securityContext` (allowPrivilegeEscalation false, drop
  ALL, seccomp RuntimeDefault, runAsNonRoot ; `readOnlyRootFilesystem: false`
  explicite si RStudio l'exige).

### Mineur — Dashboard Ceph en NodePort, WordPress en LoadBalancer

- **Fichier** : `storage/ceph/dashboard.yaml`,
  `storage/ceph/wordpress/wordpress.yaml:13`
- **Constat** : NodePort rend le dashboard Ceph atteignable sur chaque nœud
  (contredit la doctrine « port-forward » des ADR 0003/0010) ; le Service
  WordPress LoadBalancer exposerait WordPress hors-cluster si un LB existe
  (secret MySQL de démo `changeme`).
- **Recommandation** : passer en ClusterIP + port-forward documenté, ou
  restreindre par NetworkPolicy/UFW ; ne jamais réutiliser le secret `changeme`.

### Suggestions

- Incohérence `.gitignore` `.env.example`/`.env-example` (cf.
  [01](01-bonnes-pratiques.md)).
- L'audit-log Ansible (`USER` via env côté contrôle) n'offre pas de
  non-répudiation → s'appuyer sur sshd `LogLevel VERBOSE` + auditd ; documenter
  que ce log n'est pas une preuve.
