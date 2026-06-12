# 11 — Logiciels open source utilisés

> Axe ajouté à votre demande : _« les logiciels open source utilisés. »_

## Verdict : **portefeuille excellent, gestion du risque à outiller**

Le **portefeuille** de briques OSS est, à une exception près, **irréprochable**
pour le contexte : ce sont les choix standard, matures et gouvernés de
l'écosystème. Kubernetes, Cilium, Rook et Ceph sont **CNCF graduated**
(gouvernance multi-vendor) ; `distribution/registry` est le projet de référence
CNCF (le code derrière Docker Hub) ; Debian est la distribution communautaire la
plus pérenne. **Aucun composant majeur n'est un projet à mainteneur unique ou
abandonware.**

La vraie faiblesse n'est pas le **choix** mais la **gestion du risque OSS** :
aucune veille automatisée, aucun scan de CVE, aucune provenance d'image.

## Inventaire des composants

| Composant               | Version      | Gouvernance / Maturité                      |
| ----------------------- | ------------ | ------------------------------------------- |
| Kubernetes (kubeadm)    | 1.34         | CNCF graduated                              |
| containerd.io           | 2.x (Docker) | CNCF graduated (via dépôt Docker)           |
| Cilium (CNI)            | 1.19.4       | CNCF graduated                              |
| Rook                    | v1.19.6      | CNCF graduated                              |
| Ceph                    | v20.2.1      | Fondation Ceph / Linux Foundation           |
| Kubernetes Dashboard    | chart 7.10.0 | SIG officiel                                |
| distribution/registry   | v3.1.1       | CNCF (référence)                            |
| RStudio (rocker)        | 4.6.0        | Rocker Project                              |
| Debian                  | 13           | Communautaire, très pérenne                 |
| Tailscale               | (manuel)     | **Freemium, plan de contrôle propriétaire** |
| UFW / fail2ban / auditd | OS           | Standards Linux                             |

## Arguments POUR le portefeuille

- Maturité/gouvernance quasi optimales (CNCF graduated partout sur le cœur).
- Cohérence de version documentée (matrice ADR 0006, plafond K8s 1.34 justifié).
- containerd.io via dépôt Docker argumenté (ADR 0005 : le natif Debian 13 est
  déprécié pour K8s 1.34).
- **Intégrité vérifiée là où ça compte** : `cni.sh` télécharge le tarball
  cilium-cli **avec son `.sha256sum`** et fait `sha256sum --check` avant
  extraction.
- Licences compatibles MIT : le dépôt ne vendore aucun composant (il les
  référence), amonts Apache-2.0 ou GPL côté binaire sans linkage → pas de
  contamination.
- **Tailscale correctement neutralisé** : déclaré optionnel partout (ADR
  0003/0011), le banc tourne sans → lock-in volontairement borné.
- Choix « lourds » (kubeadm, Rook-Ceph, distribution) défendables par l'objectif
  pédagogique : reproduire une topologie de prod crédible pour former à de vrais
  outils.

## Arguments CONTRE (gestion du risque)

- **Gestion CVE inexistante** : aucun trivy/grype/syft/cosign/SBOM, aucun job de
  scan en CI.
- **Aucune veille/bump automatisé** : pas de dependabot/renovate ; la politique
  ADR 0006 est 100 % manuelle — scénario typique d'accumulation de retard de
  patchs pour un mainteneur seul.
- **Zéro digest `@sha256`** alors que l'ADR 0006 le prescrit ; tous les tags
  sont mutables (réécriture possible côté amont).
- **Toolbox Ceph `:v19`** mutable et désaccordée du cluster `v20.2.1`.
- Pinning K8s/containerd dépendant de la date d'install (cf.
  [05](05-reproductibilite.md)).
- **Annotations Tailscale orphelines** : `tailscale.com/expose` sur les Services
  registry/rstudio, mais **aucun operator** dans le dépôt → annotations inertes.

## Constats

### Majeur — Aucun scan de CVE (trivy/grype absents)

- **Fichier** : `.github/workflows/ci.yml`
- **Constat** : la CI ne fait que du lint. Aucune détection de vulnérabilités
  sur un cluster agrégeant K8s, Ceph, Rook, distribution et images applicatives.
- **Recommandation** : job `trivy` (image + config/IaC) échouant sur
  HIGH/CRITICAL avec allowlist documentée. Coût d'intégration faible, couvre
  l'angle mort.

### Majeur — Aucune automatisation de veille/bump (dependabot/renovate)

- **Fichier** : `docs/decisions/0006-…:29-62`
- **Constat** : politique de bump entièrement manuelle, sans outil.
- **Recommandation** : renovate (ou dependabot pour npm + GitHub Actions), PR
  groupées, planning mensuel. Renovate maintient aussi les digests d'image.

### Majeur — Zéro digest `@sha256` alors que l'ADR 0006 le prescrit

- **Fichier** : `storage/ceph/operator.yaml:623` (et tous les manifests)
- **Constat** : toutes les images par tag mutable ; écart direct avec l'ADR 0006
  (« idéalement avec digest pour les composants critiques »).
- **Recommandation** : épingler par digest au moins rook/ceph, ceph, registry ;
  laisser renovate gérer les mises à jour de digest.

### Majeur — Toolbox Ceph `:v19` mutable et désaccordée

- **Fichier** : `storage/ceph/toolbox.yaml:22`
- Cf. aussi [05-reproductibilite.md](05-reproductibilite.md).
- **Recommandation** : aligner sur `v20.2.1` (idéalement digest), supprimer tout
  tag mineur flottant.

### Mineur — Pinning K8s/containerd dépendant de la date d'install

- Cf. [05-reproductibilite.md](05-reproductibilite.md).

### Mineur — Annotations Tailscale orphelines sans operator

- **Fichier** : `platform/container-registry/service.yaml:7-8`,
  `apps/rstudio/service.yaml:7-8`
- **Constat** : `tailscale.com/expose`/`hostname` présents mais aucun
  tailscale-operator dans le dépôt → inertes ; un repreneur peut croire
  l'exposition automatique.
- **Recommandation** : documenter (README `platform/`) que ces annotations
  exigent l'operator non fourni, ou ajouter le manifeste de l'operator.

### Suggestions

- **Tailscale freemium / propriétaire** : noter **Headscale** (alternative 100 %
  OSS self-hosted) comme repli dans l'ADR 0003 « À revoir si » (aucune action
  code tant que l'accès distant reste optionnel).
- **Rook-Ceph lourd pour 4 nœuds / 1 mainteneur** : ne pas migrer (ROI négatif),
  mais documenter dans un ADR le compromis « puissance/réalisme vs charge
  d'exploitation » et citer **Longhorn** (CNCF, plus léger) comme alternative
  considérée et écartée — traçabilité de la décision.

## À NE PAS faire

- Ne **pas** remplacer kubeadm par k3s, Rook-Ceph par Longhorn, ni distribution
  par Harbor : le portefeuille est pertinent, l'objectif pédagogique justifie le
  réalisme, et une migration aurait un ROI négatif pour un mainteneur unique.
