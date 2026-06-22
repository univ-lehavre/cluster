# Politique de sécurité

> 🇬🇧 This policy is in French, but **vulnerability reports in English are
> welcome**. Use GitHub Private Vulnerability Reporting
> (<https://github.com/univ-lehavre/cluster/security/advisories/new>) or e-mail
> the maintainer (address below) — in either language.

## Signaler une vulnérabilité

Merci de **ne pas** ouvrir d'issue publique pour une faille de sécurité.

Privilégier le **Private Vulnerability Reporting** de GitHub : **Security →
Report a vulnerability** sur
<https://github.com/univ-lehavre/cluster/security/advisories/new>.

À défaut, contacter directement le mainteneur :
**pierre-olivier.chasset@univ-lehavre.fr**.

Merci d'inclure, si possible : description, impact estimé, étapes de
reproduction, et version/commit concerné. Réponse visée sous **7 jours ouvrés**
(projet maintenu par une seule personne en milieu recherche — les délais peuvent
varier).

## Périmètre

Ce dépôt est de l'**Infrastructure-as-Code** (manifestes K8s, playbooks Ansible,
scripts, documentation), pas un logiciel distribué. Les rapports pertinents
concernent par exemple :

- un secret commité par inadvertance (clé, token, mot de passe) ;
- une configuration exposant un service au-delà du modèle de menace ;
- une élévation de privilèges introduite par un rôle Ansible ou un manifeste.

## Modèle de menace assumé (à lire avant de signaler)

Plusieurs compromis de sécurité sont **délibérés et documentés en ADR** pour ce
cluster **mono-tenant de recherche sur réseau privé isolé** — ce ne sont pas des
failles :

- Registry interne en HTTP sans authentification
  ([ADR 0011](/cluster/docs/decisions/0011-registry-http-sans-auth/)).
- RStudio sans authentification
  ([ADR 0012](/cluster/docs/decisions/0012-rstudio-disable-auth/)).
- Pas de chiffrement Ceph in-transit/at-rest
  ([ADR 0003](/cluster/docs/decisions/0003-pas-de-chiffrement-ceph-tailscale/)).
- Secrets etcd non chiffrés / audit-policy API non posée — dette tracée
  ([ADR 0014](/cluster/docs/decisions/0014-durcissement-kubeadm-init/)).

Ces choix reposent sur l'**isolation réseau**. Un signalement utile est donc
plutôt : « telle hypothèse d'isolation est fausse dans tel cas » ou « tel point
n'est pas couvert par un ADR ». Voir [SAFEGUARDS.md](/cluster/SAFEGUARDS/) pour
les contrôles en place et [docs/decisions/](/cluster/docs/decisions/) pour les
décisions.

## Versions supportées

Seule la **dernière version publiée** (cf.
[releases](https://github.com/univ-lehavre/cluster/releases)) reçoit des
correctifs. Les versions antérieures ne sont pas maintenues.
