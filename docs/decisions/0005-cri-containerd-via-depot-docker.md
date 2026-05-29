# 0005 — CRI = `containerd.io` depuis le dépôt Docker

## Contexte

Kubernetes a besoin d'un CRI (Container Runtime Interface). Trois options ont
été considérées :

1. **Docker** : déprécié comme CRI K8s depuis 1.24.
2. **containerd natif Debian** : paquet `containerd` du dépôt Debian officiel.
   Sur Debian 13 Trixie, c'est containerd **1.7.x** — fin de support officielle
   (le mainteneur upstream a passé à 2.x).
3. **containerd.io depuis le dépôt Docker** (`download.docker.com`) : containerd
   **2.2.4** (mai 2026) — version maintenue activement.

Le besoin : un CRI **récent, maintenu, et compatible Kubernetes 1.34** (cf. ADR
0006). Le banc multi-nœuds doit pouvoir rejouer la même combinaison.

## Décision

**Installer `containerd.io` depuis le dépôt Docker** sur tous les nœuds, piloté
par le rôle Ansible [`k8s-CRI-install`](../../bootstrap/roles/k8s-CRI-install/)
:

- Ajout du dépôt `download.docker.com/linux/debian` (signé par
  `/etc/apt/keyrings/docker.asc`).
- Installation du paquet `containerd.io`.
- Configuration par défaut générée + patch `SystemdCgroup = true` posé dans
  `/etc/containerd/config.toml`.

Tag validé sur le banc : **containerd.io 2.2.4** + kernel `6.12.48+deb13-arm64`.

## Statut

Accepted (2026-05-28). Bascule depuis l'historique (containerd 1.7 Debian natif)
effectuée pendant le rebuild Debian 13.

## Conséquences

**Bénéfices.**

- containerd 2.x maintenu activement — bugs et CVE patchés.
- Compatibilité explicite avec K8s 1.34 (cf. release notes Docker containerd).
- Cohérence avec ce que la doc K8s upstream recommande pour `kubeadm` (« any
  modern containerd »).

**Coûts assumés.**

- **Dépendance à un dépôt tiers** (`download.docker.com`) : à signer par une clé
  GPG distincte de celle de Debian, à maintenir dans le rôle Ansible. Risque :
  si Docker change sa clé, le rôle casse jusqu'à mise à jour.
- **Version non figée à Debian** : `apt upgrade` peut bumper containerd sans
  tester. Compensation : un `apt-mark hold containerd.io` posé par le rôle, à
  libérer explicitement pour bumper.
- **`containerd` (paquet Debian) absent** : si une dépendance Debian ailleurs
  tirerait `containerd`, on garde la version Docker.

**Alternatives écartées.**

- containerd natif Debian 13 : trop ancien (1.7.x EOL) pour un nouveau cluster
  en 2026.
- CRI-O : autre runtime valide, mais moins de retours d'expérience sur notre
  topologie ; pas de gain visible sur ce profil de charge.
