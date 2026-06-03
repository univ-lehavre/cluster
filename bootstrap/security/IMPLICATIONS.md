# Implications du durcissement

Ce document explique **ce que chaque couche change concrètement** sur la
machine, **ce qu'elle protège**, **le compromis assumé**, et **comment s'en
convaincre soi-même** (preuve observable). Le _comment_ déclaratif est dans le
[README sécurité](README.md) et dans [secure.yml](secure.yml) ; ici on parle des
_conséquences_.

**Politique** : **toutes les couches sont opt-in**.
`ansible-playbook secure.yml` sans `--tags` ne touche à rien (il se contente de
charger les variables). Chaque couche s'active explicitement, après lecture de
ses implications.

Vue d'ensemble :

| Couche       | Tag Ansible                 | Risque opérationnel | Ce qu'elle apporte                                              |
| ------------ | --------------------------- | ------------------- | --------------------------------------------------------------- |
| OS           | `os`, `unattended-upgrades` | 🟢 faible           | Mises à jour de sécurité automatiques + expiration mot de passe |
| Alert        | `alert`, `mail`             | 🟢 faible           | Redirection des mails root vers une adresse opérée              |
| Audit        | `audit`, `auditd`           | 🟢 faible           | Journalisation des appels système sensibles                     |
| Detection    | `detection`, `fail2ban`     | 🟡 modéré           | Bannissement automatique des IP qui forcent SSH                 |
| Smart        | `smart`, `smartd`           | 🟢 faible           | Surveillance SMART des disques (alerte sur le NVMe block.db)    |
| Network SSHD | `sshd`                      | 🟡 modéré           | Déjà appliqué par [`first-access.sh`](../first-access.sh)       |
| SSH keys     | `ssh-keys`                  | 🟢 faible           | Re-déploie la clé publique (déjà fait par `first-access.sh`)    |
| OS upgrade   | `upgrade`                   | 🟠 reboot immédiat  | `apt full-upgrade` + reboot, un nœud à la fois                  |
| Network UFW  | `ufw`                       | 🔴 tardif           | Pare-feu — **n'activer qu'après le bootstrap K8s**              |

> **Lecture transversale** : aucun tag actif par défaut. C'est à l'utilisateur —
> vous — d'activer chaque couche après avoir lu sa section ci-dessous, dans
> l'ordre qui lui convient. Le script [`report.sh`](report.sh) donne à tout
> moment l'état observable.

## Menu — commandes prêtes à copier-coller

À lancer depuis `bootstrap/security/` :

```bash
# 1. Mises à jour automatiques + expiration mot de passe (recommandé en 1er)
ansible-playbook -i ../hosts.yaml secure.yml --tags os

# 2. Mail root redirigé (présuppose MAIL_ROOT_REDIRECT dans .env)
ansible-playbook -i ../hosts.yaml secure.yml --tags alert

# 3. Journal d'audit (auditd + règles Florian Roth)
ansible-playbook -i ../hosts.yaml secure.yml --tags audit

# 4. Détection / anti-brute-force SSH
ansible-playbook -i ../hosts.yaml secure.yml --tags detection

# 4 bis. Surveillance SMART des disques (alerte mail sur le NVMe block.db ; cf. ADR 0008)
ansible-playbook -i ../hosts.yaml secure.yml --tags smart

# Le durcissement sshd et le dépôt des clés sont assurés UNIQUEMENT par
# bootstrap/first-access.sh (les anciens tags sshd/ssh-keys ont été retirés).

# Tout faire d'un coup (sauf upgrade et ufw, plus risqués)
ansible-playbook -i ../hosts.yaml secure.yml --tags os,alert,audit,detection

# Rattrapage CVE — un nœud à la fois (peut redémarrer)
ansible-playbook -i ../hosts.yaml secure.yml --tags upgrade

# Pare-feu — UNIQUEMENT après que K8s + Cilium + Ceph soient opérationnels
ansible-playbook -i ../hosts.yaml secure.yml --tags ufw
```

Limiter à un nœud (utile pour expérimenter) :

```bash
ansible-playbook -i ../hosts.yaml secure.yml --tags os --limit cp1
```

Tableau de bord :

```bash
bash bootstrap/security/report.sh                # tous les hôtes
bash bootstrap/security/report.sh cp1            # un hôte
```

---

## OS — `--tags os` (mises à jour automatiques + expiration mot de passe)

### Ce qui change sur la machine

- Paquet [`unattended-upgrades`](https://wiki.debian.org/UnattendedUpgrades)
  installé et activé.
- Fichier `/etc/apt/apt.conf.d/20auto-upgrades` posé :
  - télécharge les paquets de sécurité chaque jour ;
  - installe les mises à jour Debian-Security automatiquement ;
  - **redémarre la machine** chaque jour à 03h(min aléatoire par hôte, dérivée
    de `inventory_hostname`) **si un reboot est requis**.
- Compte `debian` : `password_expire_min` posé sur la valeur de
  `PASSWORD_EXPIRATION` (jours avant que le mot de passe ne soit changeable).

### Ce que ça protège

- **CVE Debian connues** : la fenêtre d'exposition à une faille publiée passe de
  « jamais patchée » à « patchée dans les 24 h » sans intervention humaine.
- **Mot de passe figé** : empêche un opérateur d'utiliser indéfiniment le même
  mot de passe initial.

### Le compromis assumé

- **Reboot automatique nocturne** : un nœud peut redémarrer seul (3 h du matin)
  s'il a reçu un noyau de sécurité. Acceptable parce que :
  - la minute est aléatoire par hôte (pas de reboot simultané des 4 nœuds) ;
  - le cluster K8s est conçu pour tolérer la perte d'un nœud (réplicat ×3 sur
    Ceph, pods recréés ailleurs).
- Si vous ajoutez des _state_ workloads non-tolérants au reboot, désactivez
  `Unattended-Upgrade::Automatic-Reboot`.

### Comment vérifier soi-même

```bash
# Sur un nœud :
sudo systemctl is-active unattended-upgrades        # → active
cat /etc/apt/apt.conf.d/20auto-upgrades              # → on voit la minute aléatoire
sudo unattended-upgrade --dry-run --debug 2>&1 | tail -20
sudo less /var/log/unattended-upgrades/unattended-upgrades.log
sudo chage -l debian                                 # → expiration mot de passe
```

---

## Alert — `--tags alert` (postfix + redirection mail root)

### Ce qui change

- `postfix` installé (`internet site` minimal en local).
- `/etc/aliases` : `root: <MAIL_ROOT_REDIRECT>` puis `newaliases`.

### Ce que ça protège

- **Visibilité opérationnelle** : `cron`, `unattended-upgrades`, `mdadm`,
  `smartd`, `auditd` envoient leurs alertes à `root@`. Sans redirection, ces
  mails s'accumulent dans `/var/mail/root` et personne ne les lit.
- Couplé à `Unattended-Upgrade::MailOnlyOnError "true"` (couche OS), vous
  recevez un mail **uniquement** quand une upgrade échoue — pas de bruit, mais
  une alerte si patch loupé.

### Le compromis assumé

- L'envoi sortant repose sur le MX de la destination (`MAIL_ROOT_REDIRECT`). Si
  le pare-feu du site bloque le port 25 sortant, les mails restent en queue
  (`postqueue -p`). À combiner avec un _smarthost_ si besoin.

### Comment vérifier

```bash
sudo systemctl is-active postfix
sudo grep '^root:' /etc/aliases
echo 'test depuis $(hostname)' | mail -s "test root" root
sudo postqueue -p   # files en attente ?
sudo tail /var/log/mail.log
```

---

## Audit — `--tags audit` (auditd + règles Florian Roth)

### Ce qui change

- `auditd` installé et démarré.
- `/etc/audit/rules.d/audit.rules` posé (jeu de règles de référence) :
  - lecture/modification des logs d'audit eux-mêmes,
  - changements de fichiers sensibles (`/etc/passwd`, `/etc/shadow`,
    `/etc/sudoers`, `/etc/ssh/sshd_config`…),
  - appels `execve` privilégiés, `unlink`/`rename` sur fichiers système,
  - tentatives d'accès refusées (`EACCES`/`EPERM`).

### Ce que ça protège

- **Forensics post-incident** : si un compte est compromis, vous avez la liste
  exhaustive de _quel UID a fait quelle syscall sur quel fichier_, avec
  horodatage et exécutable parent. Sans `auditd`, seul `journalctl` donne une
  vision partielle (services systemd).
- **Conformité** : les règles couvrent une bonne partie de PCI-DSS / NISPOM
  (voir l'en-tête du fichier).

### Le compromis assumé

- **Charge disque** : `/var/log/audit/audit.log` grossit. Le partitionnement
  recommandé (`/var` = 360 G) absorbe sans problème ; `auditd` fait sa propre
  rotation. À surveiller si vous activez des règles plus verbeuses.
- **Pas d'export** : les logs restent locaux. Pour un SIEM centralisé, installer
  en plus `audisp-remote` ou un agent collecteur — hors périmètre.

### Comment vérifier

```bash
sudo systemctl is-active auditd
sudo auditctl -l | head -20          # règles chargées
sudo aureport --summary              # résumé événements
sudo ausearch -k sshd_config | tail  # qui a touché à sshd_config ?
sudo ausearch -m USER_LOGIN -ts today
```

---

## Detection — `--tags detection` (fail2ban sur SSH)

### Ce qui change

- `fail2ban` installé et activé.
- `/etc/fail2ban/jail.local` :
  - jail `sshd` activée, backend `systemd`,
  - `maxretry = 3` → après 3 échecs d'auth SSH, l'IP est bannie pour le ban-time
    par défaut (10 min).

### Ce que ça protège

- **Brute-force SSH** : les bots qui scannent `port 22` se font sortir au bout
  de 3 tentatives ratées. Sans fail2ban, ils peuvent tester des milliers de mots
  de passe avant qu'on ne s'en aperçoive.
- **Combiné avec sshd hardening** (PasswordAuthentication=no), le risque est
  déjà faible — fail2ban ajoute une **défense en profondeur** et réduit la
  pollution des logs.

### Le compromis assumé

- **Vous pouvez vous bannir vous-même** depuis un poste mal configuré (mauvaise
  clé, mauvais user). Sans console hors-bande (iLO/IPMI), il faut attendre 10
  min ou pré-lister votre IP dans `ignoreip`.
- Backend `systemd` lit `journalctl -u sshd` — si vous changez le service SSH
  (ex. `dropbear`), il faut adapter le backend.

### Comment vérifier

```bash
sudo systemctl is-active fail2ban
sudo fail2ban-client status                    # jails actives
sudo fail2ban-client status sshd               # IPs bannies actuellement
sudo grep -i 'ban' /var/log/fail2ban.log | tail
```

---

## Durcissement sshd — posé par `first-access.sh` (source unique)

> Le durcissement `sshd` est assuré **uniquement** par
> [`first-access.sh`](../first-access.sh), qui dépose le drop-in
> `00-hardening.conf` avant même que le cluster soit joignable par Ansible. Il
> n'y a **plus** de tag `sshd` dans `secure.yml` : l'ancienne task
> `network/sshd.yml` (doublon, avec un `AllowUsers` variable) a été supprimée.
> Pour re-poser le réglage ou corriger une dérive, **relancer
> `first-access.sh`** (idempotent) ; `bootstrap/state.sh` détecte l'absence du
> drop-in.

### Ce qui change

`/etc/ssh/sshd_config.d/00-hardening.conf` contient :

```text
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
AllowUsers debian
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 3
```

### Ce que ça protège

- **PasswordAuthentication=no** : aucun mot de passe n'est accepté côté SSH.
  Même un mot de passe compromis devient sans valeur.
- **PermitRootLogin=no** : pas de session interactive root direct.
- **AllowUsers debian** : aucun autre compte (technique, applicatif) ne peut
  ouvrir une session SSH même si ses identifiants sont compromis.
- **MaxAuthTries=3** + **fail2ban** : double rempart anti-brute-force.

### Le compromis assumé

- **Perdre la clé privée = perdre l'accès** (sauf via iLO/IPMI). Garder une clé
  de secours sur un poste tiers + une console hors-bande.

### Comment vérifier

```bash
sudo sshd -T | grep -E 'passwordauth|permitroot|allowusers|maxauth|clientalive'
# attendu : passwordauthentication no
#           permitrootlogin no
#           allowusers debian
#           maxauthtries 3
#           clientaliveinterval 300
#           clientalivecountmax 3
```

---

## Network/UFW — `--tags ufw` (opt-in, **après bootstrap K8s**)

### Ce qui change

- `ufw` installé et démarré.
- Politique : **`incoming deny` / `outgoing allow`**.
- Règle `limit OpenSSH` (rate-limit + autorisation).
- Logging UFW activé (`/var/log/ufw.log`).

### Ce que ça protège

- **Réduction de surface** : seul SSH est exposé, les autres ports ne répondent
  pas. Un service mal configuré (`mongod` en écoute publique, par ex.) devient
  inatteignable depuis Internet.
- **Brute-force SSH** : la règle `limit` ajoute un rate-limit kernel (en plus de
  fail2ban).

### Le compromis assumé — **majeur**

- **Cassera le cluster Kubernetes si activé avant la fin du bootstrap.** K8s +
  Cilium + Ceph ouvrent **plusieurs dizaines** de ports :
  - `6443` (kube-apiserver), `10250` (kubelet), `10257`/`10259`
    (controller/scheduler), `2379-2380` (etcd) ;
  - `4240` (Cilium health), `4244` (Hubble), `8472` (VXLAN), `51871/udp`
    (WireGuard si activé) ;
  - `3300`/`6789` (Ceph mon), `6800-7568` (OSDs / mgr / msgr2), `7480` (RGW).
- C'est pourquoi cette couche est en `never` : il faut d'abord déployer K8s et
  Cilium, puis _lister_ les ports à autoriser, puis activer UFW.
- Voir le [RUNBOOK bootstrap](../RUNBOOK.md) — section UFW à la fin.

### Comment vérifier

```bash
sudo ufw status verbose
sudo ufw show added                 # règles ajoutées non encore actives
sudo tail /var/log/ufw.log
```

---

## OS upgrade — `--tags upgrade` (opt-in, `serial: 1`)

### Ce qui change

- `apt update` + `apt full-upgrade` immédiats.
- Si un reboot est requis (`/var/run/reboot-required`), reboot automatique de la
  machine.
- Joué `serial: 1` → un nœud à la fois (les autres restent disponibles).

### Ce que ça protège

- **Rattrapage d'urgence** d'une CVE critique sans attendre la fenêtre nocturne
  d'`unattended-upgrades`.
- **Convergence** : aligne tous les nœuds sur la même version après une
  réinstallation.

### Le compromis assumé

- Reboot pendant la journée. Combiné avec K8s + Ceph (réplicat ×3 +
  `failureDomain: host`), la perte d'un nœud est absorbée — mais préférez quand
  même une fenêtre de maintenance, et `kubectl drain` manuel si vous voulez être
  propre.

### Comment vérifier

```bash
sudo apt list --upgradable 2>/dev/null | head
sudo cat /var/log/apt/history.log | tail -50
sudo last reboot | head
```

---

## En résumé : qu'est-ce que je vois sur la machine ?

Un script de tableau de bord donne la vision agrégée des protections actives
sans avoir à exécuter chaque commande à la main :

```bash
bash bootstrap/security/report.sh                # tous les hôtes
bash bootstrap/security/report.sh cp1            # un hôte
```

Le rapport remonte, par nœud, **les preuves observables** : services actifs,
règles auditd chargées, IPs bannies par fail2ban, dernier
`unattended-upgrades.log`, alias root, et — si elles existent — règles UFW.

Référence : [report.sh](report.sh), [state.sh](../state.sh).
