# Décisions — Plateforme & GitOps

Cette page est une **vue thématique** qui agrège et raconte les décisions
relatives à la plateforme (observabilité, GitOps applicatif). Les **ADR**
restent la **source de vérité datée et immuable** ; cette page n'en est qu'une
**carte de lecture** qui les relie dans un fil logique. En cas d'écart, l'ADR
fait foi.

## Observabilité par paliers

Le point de départ est un constat **majeur** de l'audit d'opérabilité : « aucune
observabilité runtime ». Pas de metrics-server (donc `kubectl top` et les HPA
inopérants), pas de Prometheus/Grafana/alerting, et le monitoring Ceph désactivé
(`monitoring.enabled: false`). La détection de panne reposait entièrement sur
l'exécution **manuelle** de `state.sh` par l'unique admin.

La réponse — [ADR 0016](../decisions/0016-observabilite.md) — est une **approche
par paliers** : poser le socle autonome maintenant, différer le stack lourd.

- **Palier 1 (fait)** : déploiement de **metrics-server v0.8.0** sous
  `platform/metrics-server/`. Autonome (pas de Prometheus requis), empreinte
  minimale (`requests` 100m/200Mi). Rend opérants `kubectl top` et les HPA.
- **Palier 2 (fait)** : **kube-prometheus-stack** (Prometheus + Grafana +
  AlertManager) avec les CRDs `monitoring.coreos.com`, déployé sous
  [`platform/kube-prometheus-stack/`](../../platform/kube-prometheus-stack/)
  (rôle `platform-monitoring`), avec Loki pour les logs. Validé sur banc
  (scénarios 24-26, « 22 targets UP », cf.
  [matrice du catalogue](matrice-catalogue.md)).

L'**ordre** des deux paliers était une contrainte **technique** : activer
`monitoring.enabled: true` côté Ceph **sans** Prometheus pré-installé ferait
créer par l'operator Rook des `PrometheusRule`/`ServiceMonitor` dont les CRDs
seraient absents → erreurs. C'est pourquoi le collecteur (palier 2) précède
l'activation des règles d'alerte Ceph. L'**exporter Ceph** est actif
(`metricsDisabled: false`).

Entre les deux paliers, le filet reste **actif mais manuel/ponctuel** :
`state.sh` (drift par couche, dont santé SMART du NVMe via smartd), `report.sh`,
et les alertes mail de `smartd`.

> **Honnêteté — compromis assumés (ADR 0016).**
>
> - **Pas d'alerting runtime K8s/Ceph** jusqu'au palier 2 : une OSD down ou un
>   near-full ne génère pas d'alerte automatique, la détection passe par
>   `state.sh` manuel. Risque accepté temporairement (cluster mono-admin, réseau
>   privé).
> - **`--kubelet-insecure-tls`** sur metrics-server (certs kubelet auto-signés
>   kubeadm) : compromis classique, acceptable sur réseau privé.
> - **Déclencheur du palier 2** explicitement posé : dès qu'un incident Ceph
>   passe inaperçu, ou **avant toute ouverture du cluster au-delà du
>   mono-admin**.

## Argo CD : le GitOps applicatif et sa frontière

Une fois le socle réseau et TLS de bordure en place, l'étape suivante introduit
le **GitOps applicatif** : réconcilier en continu, depuis git, les manifestes
des applications (`citation-*`) et des composants stateful déclarés en
`Application` (Dagster, Marquez, plus tard CloudNativePG). Il manquait une
boucle déclarative détectant le **drift** entre l'état git (désiré) et l'état
cluster (réel) pour le résorber.

[ADR 0022](../decisions/0022-argocd-gitops-applicatif.md) adopte **Argo CD**
comme moteur GitOps **applicatif** (namespace `argocd`, versionné sous
`platform/argocd/`).

### Installation épinglée, sans Internet

Manifeste statique épinglé sur **Argo CD v3.4.3** (branche stable 2026, **testée
K8s 1.32-1.35** donc 1.34 — les lignes 2.x ne supportent **pas** 1.34), bundle
officiel `install.yaml` (3 CRDs `argoproj.io` + RBAC + workloads), **images par
digest**. Le cluster étant **isolé, non joignable depuis Internet**, les **3
images** (`quay.io/argoproj/argocd`, `ghcr.io/dexidp/dex`, `…/redis`) doivent
être **mirrorées dans le registry interne** : pré-requis bloquant, faute de quoi
`ImagePullBackOff`.

### La frontière Ansible (infra) / GitOps (applicatif)

C'est le cœur de l'ADR, et une frontière **non négociable** pour éviter le
**bootstrap circulaire** (si l'outil GitOps gérait l'infra ou se gérait
lui-même, le cluster ne convergerait pas sans l'outil, et l'outil ne démarrerait
pas sans le cluster convergé).

Le critère est net : un composant va dans **Ansible si, et seulement si, le
retirer empêcherait Argo CD de démarrer ou de réconcilier**.

- **Infra → Ansible/kubectl** : kubeadm, Cilium/exposition, cert-manager,
  registry, Rook, metrics-server, **Argo CD lui-même**, opérateurs + CRDs.
- **Applicatif → Argo CD** : apps `citation-*` et instances stateful déclarées
  en `Application` (Cluster CNPG, Dagster, Marquez).

Règle de la zone grise : **CRDs + opérateurs = Ansible ; les CR (objets custom)
= GitOps**. Conséquence opérationnelle : un cluster reconverge **d'abord par
Ansible**, _puis_ Argo CD prend la main sur l'applicatif — **Argo CD ne gère ni
l'infra ni lui-même**.

Le périmètre est borné par un **`AppProject atlas`** qui restreint les
`Application` aux destinations `citation-*`, `dagster`, `marquez`, avec sources
git listées et cluster-scoped réduit à `Namespace`. Argo CD ne déborde pas sur
l'infra.

### Exposition de l'UI : cohérence tout-Cilium

L'UI est exposée **en interne uniquement** (clients LAN/VPN, jamais Internet)
via le **`Gateway` Cilium + une `HTTPRoute`**, le TLS étant terminé en bordure
avec un certificat cert-manager (CA interne). `argocd-server` tourne en
`--insecure` (`server.insecure: "true"`) car un double-TLS provoquerait une
boucle de redirection ; **aucun ingress-nginx**. Le CLI gRPC passe par le même
`HTTPRoute` via `argocd login <host> --grpc-web`. Le détail de ce datapath de
bordure est traité dans la vue
[Exposition réseau](../architecture/exposition-reseau.md).

> **Honnêteté — prix à payer et garde-fous (ADR 0022).**
>
> - **+1 composant** (server/repo-server/redis/application-controller/dex) à
>   opérer sur un cluster **4 nœuds non-HA** (control-plane unique = SPOF).
> - **`--insecure` sur `argocd-server`** : acceptable **uniquement** parce que
>   le TLS est terminé en bordure **et** que le réseau est privé/isolé — à ne
>   **jamais** transposer à un cluster exposé. Garde-fou : porte de sortie
>   documentée en cas d'ouverture.
> - **gRPC via le Gateway** : à valider sur banc (implémentation Gateway API
>   récente) ; repli `--grpc-web` retenu, sinon port-forward.
> - **Anti-circularité testée** : **aucune** `Application` ne cible un addon
>   d'infra ni `argocd` lui-même (pas de self-management).

### Alternatives écartées

- **Flux CD** : crédible et léger, écarté au profit d'Argo CD pour son **UI
  intégrée** et son modèle **`AppProject`** qui borne nativement le périmètre.
  Choix d'outillage, non d'architecture : la frontière infra/app vaudrait
  identiquement avec Flux.
- **Tout-Ansible sans GitOps** : écarté car perd la réconciliation déclarative
  continue (Ansible est push impératif ponctuel). Ansible reste pertinent pour
  l'infra — d'où la frontière.
- **Exposer Argo CD via ingress-nginx** : écarté, incohérent avec le tout-Cilium
  (ingress-nginx abandonné).
- **Argo CD gérant l'infra et/ou lui-même** : écarté pour cause de bootstrap
  circulaire.

## CI/CD in-cluster : le build in-pod rétabli

Le GitOps ci-dessus déploie ce qui est **déjà construit**. Reste la question du
**build** de l'image de code d'une code-location : un `git push` doit
déclencher, **dans** le cluster isolé, la construction de l'image puis son
déploiement — sans egress, sans réintroduire l'instabilité de l'événementiel
(Argo Events/NATS, écarté
[ADR 0105](../decisions/0105-retrait-build-evenementiel.md)) ni relâcher la
sécurité. C'est l'objet de
[ADR 0112](../decisions/0112-cicd-in-cluster-gitea-actions-buildkit.md).

La chaîne retenue : **push → Gitea Actions** (runner `act_runner` en **mode host
durci**, enregistré par token, zéro Docker-in-Docker) **→ client `buildctl`
durci → daemon `buildkitd` rootless in-pod** (snapshotter `auto`/overlayfs, sans
`/dev/fuse`) **→ push de l'image au registre interne → Argo CD** réconcilie le
déploiement. Le build in-pod, un temps réputé abandonné
([ADR 0110](../decisions/0110-preimage-de-build-et-build-in-pod.md)), est ainsi
**rétabli** — prouvé au banc (scénario 35, PR #650). Le déclenchement par
**Sentinelle/Job** initialement planché (plan build-in-pod) est **abandonné** au
profit de Gitea Actions. atlas **instancie** lui-même son `Application` Argo CD
([ADR 0111](../decisions/0111-atlas-instancie-application-argocd.md)), fermant
la boucle côté applicatif. Exploitation :
[`platform/buildkit/RUNBOOK.md`](../../platform/buildkit/RUNBOOK.md) et
[`platform/gitea-runner/RUNBOOK.md`](../../platform/gitea-runner/RUNBOOK.md).

## Validation sur banc

La mise en service d'Argo CD est conditionnée à une **validation banc**
([`bench/lima/`](../../bench/lima/)) : une `Application` de test doit passer
**`Synced/Healthy`**, l'UI répondre en HTTPS via le Gateway (cert CA interne,
root importé), et le CLI `--grpc-web` fonctionner à travers la `HTTPRoute`. Le
default-deny Cilium est préservé via `platform/network-policies/argocd/`. Le
protocole de banc est détaillé dans la vue
[Validation banc](../architecture/validation-banc.md).

### Code-location jouet : prouver la chaîne GitOps en autonomie

[ADR 0086](../decisions/0086-code-location-jouet-du-socle.md) ajoute une
**code-location Dagster jouet** (`toy-codeloc`, serveur gRPC minimal) **déployée
par GitOps** (poussée dans Gitea, réconciliée par Argo CD) — exactement comme la
vraie code-location d'atlas. Elle rend le banc **autonome** pour exercer toute
la chaîne (push Gitea → webhook → Argo CD `Synced` → gRPC → run Dagster via
`launchRun` → lineage Marquez → métrique de drift Evidently dans MLflow) **sans
dépendre du dépôt applicatif**. C'est le contenu réconcilié par le scénario 27,
et le pipeline lancé par le 29. Respecte la frontière (la code-location est de
l'**applicatif** → GitOps, pas Ansible) ; elle remplace l'ancien Job CLI jetable
`dataops_chain_emit_and_verify`.

## Voir aussi

- [Exposition réseau](../architecture/exposition-reseau.md) — Gateway Cilium,
  HTTPRoute, TLS de bordure pour l'UI Argo CD.
- [Validation banc](../architecture/validation-banc.md) — protocole de tests sur
  le banc Lima ([`bench/lima/`](../../bench/lima/)).
- ADR de cette vue : [ADR 0016](../decisions/0016-observabilite.md),
  [ADR 0022](../decisions/0022-argocd-gitops-applicatif.md),
  [ADR 0110](../decisions/0110-preimage-de-build-et-build-in-pod.md),
  [ADR 0111](../decisions/0111-atlas-instancie-application-argocd.md),
  [ADR 0112](../decisions/0112-cicd-in-cluster-gitea-actions-buildkit.md).
