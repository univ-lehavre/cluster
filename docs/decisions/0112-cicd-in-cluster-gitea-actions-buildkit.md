# 0112 — CI/CD in-cluster : Gitea Actions + BuildKit rootless (le build in-pod, RÉTABLI)

## Statut

Accepted (2026-07-12). **Amende
[ADR 0110](0110-preimage-de-build-et-build-in-pod.md)** sur son volet « build
in-pod ABANDONNÉ ». La réfutation d'ADR 0110 reposait sur un **diagnostic
erroné** : elle concluait « sur k8s ≥ 1.34, PodSecurity `baseline` interdit
`seccompProfile: Unconfined`, donc le pod buildkitd n'a jamais pu être créé ».
Le premier fait est exact (baseline refuse bien `Unconfined`) ; la
**conclusion** ne l'est pas. Le socle 0110 labellisait son namespace de build
`pod-security.kubernetes.io/enforce: baseline` — c'est CE label, pas une limite
de k8s, qui rejetait le pod. **Mesuré au banc Lima (k8s 1.34, 2026-07-12)** : un
namespace de build NON labellisé baseline (privilège isolé à ce seul ns, reste
du cluster en baseline) ADMET le pod, et le build in-pod FONCTIONNE de bout en
bout (build de la cible code `FROM` pré-image du registry interne + `COPY` +
`RUN` + push). Le volet « split pré-image » d'ADR 0110 reste inchangé ; seul le
« in-pod abandonné » est amendé.

Touche aussi [ADR 0011](0011-registry-http-sans-auth.md) (le pull kubelet du
registre HTTP interne exige `certs.d` + `config_path` node-side, cf.
Conséquences), et prolonge
[ADR 0105](0105-retrait-build-evenementiel-node-side-terminal.md) (l'automatisme
« à chaque push » est rétabli, mais par Gitea Actions — un runner au push — et
NON par la chaîne événementielle Argo Events retirée, dont le bug
d'amplification n'est pas réintroduit).

## Contexte

[ADR 0110](0110-preimage-de-build-et-build-in-pod.md) amendé a sorti le build de
l'image de code HORS cluster (poste, `atlas` `deploy/build-code.sh`), et
[ADR 0105](0105-retrait-build-evenementiel-node-side-terminal.md) avait retiré
la chaîne événementielle (Argo Events + Argo Workflows + NATS) pour instabilité
(amplification ×45 : un Sensor mal dédupliqué relançait le build en boucle). Il
n'existait donc PLUS de « push → CI → CD » in-cluster : le build était manuel
sur le poste, et le déploiement suivait par digest injecté.

Le besoin : **un `git push` déclenche, DANS le cluster, le build de l'image de
code puis son déploiement** (push + CI + CD complet), sur le cluster Lima local
jetable, air-gappable, mono-utilisateur, **sans réintroduire** l'instabilité qui
a fait retirer l'événementiel, et **sans relâcher** la sécurité au-delà du
strict nécessaire.

Deux questions se posaient, tranchées EMPIRIQUEMENT (décisions basées sur des
preuves, pas sur la réputation des outils) :

1. **Le build in-cluster est-il possible sous PodSecurity ?** L'abandon 0110 le
   niait. Mesures au banc :
   - BuildKit rootless dans un ns `enforce: baseline` → **rejeté** à l'admission
     (reproduit 0110). Dans un ns SANS ce label → **admis et builde** (avec
     `seccomp Unconfined`, `AppArmor unconfined`, capabilities `SETUID/SETGID`
     pour `newuidmap`, et l'arg daemon `--oci-worker-no-process-sandbox` pour
     que les `RUN` ne montent pas `/proc`). Le worker démarre en `overlayfs`,
     sans `/dev/fuse` — le point dur fuse-vs-native d'ADR 0110 est tranché :
     `auto` suffit.
   - Buildah rootless : échoue (unshare puis remount VFS refusés — exigerait
     `/dev/fuse`, soit PLUS de privilège). Kaniko : ABANDONNÉ
     (`gcr.io/kaniko-project` archivé par Google). → **BuildKit retenu** comme
     seul builder mature qui builde avec le moindre relâchement.

2. **Quel moteur CI/CD ?** Un banc comparatif (Gitea Actions / Woodpecker / Argo
   Workflows) puis l'épreuve du terrain :
   - **Woodpecker** s'authentifie à la forge par **OAuth2** (écran de
     consentement web). Sous Lima NAT (accès uniquement par
     `kubectl port-forward`), le pod serveur et le navigateur n'ont pas la même
     URL Gitea → OAuth insoluble proprement. Écarté.
   - **Argo Workflows + Events** : déclenchement par webhook (pas d'OAuth), mais
     3 opérateurs + NATS (~180k lignes vendorées) et le bug d'amplification ×45
     reviendrait sur une restauration nue. Écarté.
   - **Gitea Actions** : intégré à Gitea (déjà déployé), runner `act_runner`
     enregistré par **TOKEN** (pas d'OAuth, pas d'écran web), déclenchement
     natif au push. Écarte frontalement le point qui a coulé Woodpecker.
     **Retenu.**

## Décision

> **La chaîne CI/CD est in-cluster : Gitea Actions (déclenchement + runner) →
> BuildKit rootless (build, privilège isolé) → Argo CD (déploiement).**

Architecture, chaque maillon prouvé au banc :

- **Forge** : Gitea (conservée — légère, air-gappable, déjà déployée).
- **CI** : **Gitea Actions** (`GITEA__actions__ENABLED=true`). Un runner
  `act_runner` en **mode `host`** (les steps s'exécutent dans le conteneur
  runner, **zéro Docker-in-Docker, zéro privilège**), DURCI (PodSecurity
  baseline, non-root, `drop: [ALL]`, seccomp RuntimeDefault). Enregistré par
  token (`gitea actions generate-runner-token`). Déclenché nativement par push
  (`.gitea/workflows/*.yaml`).
- **BUILD (« Option B »)** : le step de build est un **client `buildctl` DURCI**
  (passe baseline) qui soumet au **daemon `buildkitd` distant**
  (`platform/buildkit/`), seul composant portant les dérogations rootless,
  **isolé dans son namespace non labellisé baseline**. Le daemon build l'image
  `FROM` la pré-image du registre interne et la pousse au registre. Le CI reste
  entièrement durci ; le privilège ne fuit pas hors du ns de build. — C'est le «
  moindre relâchement » : un seul namespace non-baseline, jamais
  `privileged`/`hostPath`.
- **CD** : **Argo CD** (déjà déployé) réconcilie une `Application` qui suit un
  manifeste de déploiement (référençant l'image par tag/digest de commit) →
  déploie le pod. Cohérent avec le déploiement par digest d'ADR 0110/0111.

Le composant `buildkit` est de nouveau câblé dans nestor (graphe, rôle
`platform-buildkit` dans `bootstrap/dataops.yaml`, mirror `moby/buildkit`,
exception `.trivyignore` KSV-0014) — le socle est montable par `nestor`, plus
par `kubectl apply` manuel. Le déroulé opérationnel (montage, corrections du
rootless, dépannage) est dans le
[RUNBOOK buildkit](../../platform/buildkit/RUNBOOK.md).

### Ce qui est RÉTABLI (vs ADR 0110 amendé)

- `platform/buildkit/` (namespace SANS `enforce: baseline`, buildkitd rootless,
  `buildkitd.toml` insecure `registry:80`, service),
  `platform/network-policies/buildkit/`, rôle `platform-buildkit`, mirror
  `moby/buildkit`, composant de graphe `buildkit`.

### Ce qui est NOUVEAU

- Gitea Actions activé + le modèle « runner host durci + client buildctl →
  daemon » (Option B).

### Ce qui n'est PAS réintroduit

- La chaîne événementielle Argo Events/Workflows/NATS (ADR 0105) et son bug
  d'amplification. Le déclenchement « au push » est assuré par Gitea Actions (un
  runner par job, dédupliqué nativement par la forge), pas par un Sensor.

## Conséquences

- **push + CI + CD complet in-cluster**, prouvé de bout en bout au banc : push →
  Gitea Actions → runner durci → buildctl → daemon BuildKit → image taguée au
  commit → Argo CD `Synced/Healthy` → pod déployé exécutant l'image du CI.
- **Sécurité** : tout le CI reste `baseline` ; le seul relâchement (seccomp
  Unconfined + SETUID/SETGID) est confiné au namespace du daemon buildkitd.
  L'objectif `restricted` cluster-wide n'est PAS atteignable avec un builder
  rootless (buildkit et le clone tournent root) — arbitrage assumé sur ce ns.
- **Pré-requis node (ADR 0011)** : le kubelet ne tire le registre HTTP interne
  `registry:80` que si le nœud a `config_path = /etc/containerd/certs.d` +
  `certs.d/registry:80/hosts.toml` (http/insecure) + l'entrée `/etc/hosts`
  `registry → ClusterIP` (posés par `platform-registry` node). Sans quoi
  `HTTP response to HTTPS client` / résolution DNS échouée.
- **Reproductibilité** : `nestor` monte le socle buildkit (`--tags buildkit`).
  Le runner Gitea Actions et le déploiement de démonstration ne sont pas encore
  des couches nestor (posés à la main / hors socle) — industrialisation à
  suivre.

## Alternatives écartées

- **Woodpecker CI** — intégration Gitea de 1re classe, mais **OAuth2** insoluble
  sous Lima NAT (URL Gitea commune pod+navigateur impossible sans bricolage
  `/etc/hosts` + hostAliases). Le build fonctionnait (Option B), c'est
  l'authentification web qui bloquait. Écarté pour ce contexte.
- **Argo Workflows + Argo Events** — évite l'OAuth (webhook), mais 3
  opérateurs + NATS (~180k lignes vendorées) et le bug d'amplification ×45
  reviendrait sur un `git revert` nu ; la « Sentinelle » dédupliquée qui le
  corrigerait n'a jamais été codée. Sur-dimensionné et risqué.
- **Tekton** — moteur k8s-natif par webhook, mais pas d'intégration Gitea native
  (câblage EventListener manuel) et plus de composants. Aucun gain ici.
- **Buildah / kaniko** au lieu de BuildKit — Buildah rootless exige `/dev/fuse`
  (plus de privilège) ; kaniko passe baseline sans relâchement MAIS son image
  amont est archivée (Google) → non pérenne. BuildKit est le seul builder mature
  qui builde avec le moindre relâchement.
- **Docker-in-Docker (act_runner backend docker, ou plugin buildx)** — exige un
  pod `privileged` (superset de ce que le rootless demande). Le mode `host` +
  Option B évite tout privilège dans le CI.
