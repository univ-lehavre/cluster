# 0012 — RStudio sans authentification (`DISABLE_AUTH=true`)

## Contexte

L'application RStudio Server ([`apps/rstudio/`](../../apps/rstudio/)) est
déployée à partir de l'image `rocker/geospatial:4.6.0`. Le manifeste
[`deployment.yaml`](../../apps/rstudio/deployment.yaml) pose la variable
d'environnement :

```yaml
env:
  - name: DISABLE_AUTH
    value: 'true'
```

Cette directive (propre aux images `rocker/*`) **désactive complètement l'écran
de login RStudio** : quiconque atteint le port 8787 du pod ouvre directement une
session shell + RStudio en tant qu'utilisateur `rstudio`, avec accès à la PVC
`/home/rstudio/workspace` montée en RBD réplicat ×3.

Aucune variable `PASSWORD` n'est définie (elle servirait sinon à fixer le mot de
passe utilisateur de l'image).

## Décision

**`DISABLE_AUTH=true` est conservé** comme décision assumée. La sécurité de
l'accès à RStudio repose **entièrement sur le contrôle d'accès au Service** :

- Service `rstudio-service` de type `ClusterIP` (pas de NodePort, pas de
  LoadBalancer Internet).
- Accès distant **optionnel** via les annotations Tailscale du Service
  (`tailscale.com/expose: 'true'`, `tailscale.com/hostname: rstudio`) : si le
  Tailscale operator est déployé, les pairs ayant `tag:rstudio-user` joignent
  `http://rstudio`. **Sans Tailscale**, l'accès se fait par
  `kubectl port-forward svc/rstudio-service 8787:80` depuis un poste autorisé à
  parler à l'API K8s.
- Accès intra-cluster : tout pod du namespace `rstudio` (vide à part RStudio) et
  tout pod du cluster (pas de NetworkPolicy → cohérent avec le modèle
  mono-tenant) peut joindre `rstudio-service.rstudio:80`.

Le cluster est **mono-tenant** (laboratoire de recherche) : tous les
utilisateurs de RStudio sont par hypothèse de confiance.

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- Zéro friction de connexion pour les chercheurs (pas de mot de passe à faire
  circuler, pas de rotation, pas de oublié).
- Image `rocker/*` upstream sans surcharge applicative.

**Coûts assumés — plus importants que ADR 0010/0011.**

- **Shell + filesystem accessibles**, pas juste un push d'image. Quiconque
  atteint le port 8787 peut :
  - exécuter du code R/python avec accès réseau sortant (tunnels, exfil) ;
  - lire/écrire dans la PVC (1 Ti) ;
  - lancer des `system()` shell (l'utilisateur `rstudio` est non-root mais a un
    home complet).
- **Pas d'audit utilisateur** : `auditd` côté nœud voit `uid=1000` (l'UID
  rstudio dans le pod) mais ne peut pas distinguer **quel humain** est derrière
  la session.
- **Anti-pattern manifeste** si le cluster s'ouvre à plusieurs équipes ou hors
  campus. Cette ADR devient alors caduque (voir « À revoir »).

**Garde-fous opérationnels.**

- Ne **pas** exposer le Service via Ingress public ni LoadBalancer Internet.
- Si Tailscale est utilisé : restreindre `tag:rstudio-user` aux seuls comptes
  autorisés (revue régulière à inscrire dans l'opérationnel). Sinon : ne pas
  distribuer le kubeconfig à des utilisateurs non habilités à port-forward.
- Sauvegarde régulière de la PVC RStudio (pas dans ce dépôt — à documenter
  ailleurs).

## À revoir

- Si plusieurs équipes ou utilisateurs externes accèdent à l'instance → activer
  l'auth : retirer `DISABLE_AUTH=true`, poser `PASSWORD` via un `Secret`
  Kubernetes (`valueFrom.secretKeyRef`), créer un utilisateur par chercheur
  (`USERID`/`GROUPID`/`USER`).
- Pour une vraie multi-tenance, basculer sur une image de type JupyterHub ou
  Posit Workbench (auth OIDC, isolation par utilisateur).
- Si l'accès devient public (hors Tailscale) → TLS obligatoire +
  authentification + `NetworkPolicy` stricte.
