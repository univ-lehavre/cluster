# Cybersécurité d’un **cluster** de serveurs

[![DOI](https://zenodo.org/badge/1046248953.svg)](https://doi.org/10.5281/zenodo.16983614)

## Objectif

- Mettre en place une politique de cybersécurité
- Automatiser le plus possible son installation sur les serveurs

## Méthode

Nous allons déployer une architecture de sécurité en plusieurs étapes, en utilisant un outil d'automatisation pour garantir la cohérence et la rapidité de la mise en œuvre.

Ansible est un outil d'automatisation qui permet de gérer la configuration et le déploiement d'applications sur des serveurs distants. Il utilise un langage de description simple basé sur YAML pour définir l'état souhaité des systèmes. Concrètement, un playbook Ansible - ici le fichier `./secure.yml` - est un fichier YAML qui décrit les tâches à exécuter sur les hôtes cibles - décrits dans le fichier `/etc/ansible/hosts`. Parfois, ces tâches sont regroupées au sein d’un ou plusieurs rôles.

Notre playbook exécute plusieurs rôles pour sécuriser les serveurs. Il commence par charger les paramètres (rôle `settings`) pour exposer les variables d’environnement (décrites dans `./.env`), puis exécute en série (un hôte à la fois) une mise à jour complète du système en appelant la tâche upgrade-now du rôle `os`, et enfin applique, avec privilèges élevés, l’ensemble des rôles de durcissement (`os`, `network`, `alert`, `audit`, `detection`) pour configurer le compte administrateur, activer les mises à jour automatiques, sécuriser SSH et le pare‑feu, rediriger les mails système, déployer les règles d’audit et configurer la détection d’intrusion — bref, il met à jour puis durcit chaque machine de façon ordonnée.

Nous détaillons ensuite chaque rôle ci-dessous.

### alert

Ce rôle - dans le fichier `./roles/alert` - installe et active un agent de messagerie minimal (`postfix`) pour permettre l’envoi d’emails système, puis configure l’alias root dans aliases afin de rediriger les mails système vers l’adresse administrateur (définie la variable `MAIL_ROOT_REDIRECT` du fichier `.env`); si le fichier d’alias change, il déclenche la régénération des alias et appliquer immédiatement la redirection.

### audit

Le rôle - dans le fichier `./roles/audit` - installe et active auditd, déploie les règles d’audit depuis files/audit.rules vers /etc/audit/rules.d/ et redémarre auditd si les règles ont été modifiées pour garantir la collecte des événements système.

### detection

Le rôle - dans le fichier `./roles/detection` - installe et démarre `fail2ban`, déploie la configuration locale jail.local et recharge le service au besoin pour bloquer automatiquement les IP malveillantes détectées dans les logs.

### network

Le rôle - dans le fichier `./roles/network` - met en place la sécurité réseau. Il applique des règles UFW (`ufw.yml`), installe/configure le serveur SSH (`sshd.yml`) avec un mécanisme de rollback en cas d’échec, et déploie les clés publiques pour l’accès (`ssh.yml`).

### os

Le rôle - dans le fichier `./roles/os` - configure le compte administrateur (expiration de mot de passe via `users.yml`), installe et paramètre `unattended-upgrades` (génération d’une minute aléatoire et déploiement du template `templates/20auto-upgrades.j2`) et fournit une tâche optionnelle (`upgrade-now.yml`) pour appliquer immédiatement les upgrades et redémarrer si nécessaire.

### settings

Le rôle - dans le fichier `./roles/settings` - importe les variables d’environnement clés (ex. `MAIL_ROOT_REDIRECT`, `HOST_USER`, `PASSWORD_EXPIRATION`, `PUBLIC_SSH_KEY`), les expose sous forme de facts `settings_*`, vérifie qu’elles sont définies et affiche un debug des valeurs importées.

## Utilisation

### Pré-requis

Nous utilisons un ordinateur de contrôle (un ordinateur de bureau) pour orchestrer à distance la configuration et la sécurisation d’un ou de plusieurs serveurs. L’automatisation est effectuée à l'aide de scripts et de playbooks Ansible.

Sur l’ordinateur de contrôle, assurez-vous d'avoir installé les dépendances nécessaires :

- **Ansible** : pour l'exécution des playbooks ;
- **Python** : pour les scripts et modules utilisés ;
- **SSH** : pour la connexion aux serveurs distants.

Concernant les serveurs à sécuriser, nous considérons qu’ils bénéficient chacun de :

- Une installation minimale et récente de Debian bookworm (12) ;
- Un seul compte utilisateur avec un accès `sudo` et un mot de passe robuste ;
- Une adresse IP avec le port 22 accessible depuis l’ordinateur de contrôle.

### Installation

Sur l’ordinateur de contrôle, clonez ce dépôt localement :

```bash
git clone https://github.com/univ-lehavre/server-security.git
```

À la racine de ce dépôt cloné, renommez le fichier `.env.example` en `.env` et remplacez toutes les valeurs des variables d'environnement.

### Lancement

Pour sécuriser les serveurs, lancez la commande suivante :

Attention : le mot de passe est actuellement celui de la console de management

```bash
set -a; source .env; set +a; ansible-playbook --ask-pass --ask-become-pass secure.yml
```

Cette commande exécute le playbook Ansible `secure.yml` en utilisant les informations d'identification fournies dans le fichier `.env`.

## Contribution à ce dépôt de code

Il est recommandé d'installer les modules suivants pour garantir la qualité et la cohérence du code :

- **prettier** : pour le formatage automatique du code.
- **ansible** : pour l'exécution des playbooks et rôles Ansible.
- **ansible-lint** : pour l'analyse statique et le linting des fichiers Ansible.

Pour formatter le code et exécuter le **linter** :

```bash
npm run format
npm run lint
```

Avant de soumettre, lancez ce script afin que toutes les variables d’environnement du fichier privé `.env` soient bien obfusquées dans le fichier public `.env-example` :

```bash
perl ./blur-env.pl
```
