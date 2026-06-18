# REDCap

[REDCap](https://projectredcap.org) (Research Electronic Data Capture) —
application PHP/Apache de saisie de données de recherche, adossée à une base
**MariaDB**.

App **autonome**, **hors graphe nestor** : elle ne fait pas partie d'une
topologie/layer et ne se monte pas via `nestor up`, mais par un **playbook
dédié** ([`bootstrap/redcap.yaml`](../../bootstrap/redcap.yaml), §3) lancé
explicitement. Exposition par `kubectl port-forward` (ou un HTTPRoute Gateway à
ajouter).

## Particularités (et pourquoi)

- **Base MariaDB, pas PostgreSQL.** REDCap ne supporte que MySQL/MariaDB ; le
  cluster n'offre que CNPG/PostgreSQL (incompatible). On déploie donc un
  **MariaDB standalone** durci ([`mariadb.yaml`](mariadb.yaml)), calqué sur le
  MySQL du smoke WordPress — sans opérateur ni HA (app autonome).
- **Image maison, code source NON versionné.** REDCap est un logiciel **tiers
  sous licence propriétaire** (`REDCap_License.txt`) : aucune image publique,
  code non redistribuable. L'image
  [`registry:80/redcap`](../../platform/redcap/image/Dockerfile) dérive
  `php:8.3-apache` + extensions + le code REDCap **copié au build**. Le PHP
  reste **gitignoré** (`platform/redcap/image/source/`), jamais commité (ADR
  0023).
- **Identifiants hors image.** `database.php` (que REDCap lit) est injecté par
  un Secret monté en `subPath`, et les creds MariaDB par un autre Secret — les
  deux ont un modèle générique `*.example.yaml` versionné ; les vrais Secrets se
  créent hors dépôt.

## Déploiement

### 1. Stager le code source REDCap (hors dépôt, gitignoré)

Placer le webroot REDCap dans le contexte de build de l'image :

```bash
# depuis une copie locale du source REDCap (ex. ~/.../redcap/v17.01.03/redcap/)
mkdir -p platform/redcap/image/source
cp -a <chemin-local>/redcap platform/redcap/image/source/redcap
# → platform/redcap/image/source/redcap/{index.php, database.php, redcap_v17.1.3/, …}
```

> `platform/redcap/image/source/` est **gitignoré** : le PHP n'entre jamais dans
> git. Vérifier : `git status` ne doit montrer AUCUN fichier sous `source/`.

### 2. Créer les Secrets réels (hors dépôt)

```bash
kubectl create namespace redcap

# Identifiants MariaDB (root + user applicatif `redcap`)
kubectl -n redcap create secret generic redcap-db-secret \
  --from-literal=root-password='<ROOT_FORT>' \
  --from-literal=password='<REDCAP_FORT>'

# database.php que REDCap lit (le $password DOIT == la clé `password` ci-dessus)
kubectl -n redcap create secret generic redcap-db-config \
  --from-file=database.php=<chemin/database.php-rempli>
```

Les modèles : [`db-secret.example.yaml`](db-secret.example.yaml),
[`db-config.example.yaml`](db-config.example.yaml).

### 3. Monter REDCap (build image + déploiement) — une commande

Le playbook [`bootstrap/redcap.yaml`](../../bootstrap/redcap.yaml) enchaîne tout
: build de l'image maison sur les nœuds (`platform-build-images` restreint à
`redcap_build_images`, `build_all_arch` — REDCap n'a pas d'image upstream à
retaguer) puis apply namespace + NetworkPolicies (default-deny d'abord) +
MariaDB + REDCap. Il **vérifie** que le source est stagé (§1) et que les Secrets
existent (§2), et attend que MariaDB + REDCap soient Ready.

```bash
cd bootstrap
uv run ansible-playbook -i <inventaire> redcap.yaml
```

> App AUTONOME, **hors graphe nestor** : on lance ce playbook explicitement (ce
> n'est pas une layer `nestor up`). Idempotent : le re-jeu saute l'image déjà
> présente et ré-applique les manifestes sans changement.

### 4. Accès

```bash
kubectl -n redcap port-forward svc/redcap 8080:80
# → http://localhost:8080  (installation REDCap au premier accès : /install.php)
```

## Fichiers

| Fichier                                                                                                                      | Rôle                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| [`../../bootstrap/redcap.yaml`](../../bootstrap/redcap.yaml)                                                                 | Playbook : build image (nœuds) + déploiement k8s (manifestes)         |
| [`namespace.yaml`](namespace.yaml)                                                                                           | Namespace `redcap` + Pod Security (baseline)                          |
| [`mariadb.yaml`](mariadb.yaml)                                                                                               | MariaDB standalone (Service headless + PVC 20 Gi + Deployment durci)  |
| [`redcap.yaml`](redcap.yaml)                                                                                                 | REDCap (Service ClusterIP :80 + PVC edocs + Deployment, image maison) |
| [`db-secret.example.yaml`](db-secret.example.yaml)                                                                           | Modèle du Secret des identifiants MariaDB                             |
| [`db-config.example.yaml`](db-config.example.yaml)                                                                           | Modèle du Secret `database.php`                                       |
| [`../../platform/redcap/image/Dockerfile`](../../platform/redcap/image/Dockerfile)                                           | Image maison (PHP/Apache + extensions + source)                       |
| [`../../platform/network-policies/redcap/00-default-deny.yaml`](../../platform/network-policies/redcap/00-default-deny.yaml) | default-deny + DNS + allow frontend/MariaDB (dossier)                 |
