# Runbook — gitea-runner (act_runner, CI in-cluster, ADR 0112)

Ce runbook donne la **procédure d'exploitation** du runner Gitea Actions
(`act_runner`), le premier maillon de la chaîne CI/CD in-cluster
([ADR 0112](../../docs/decisions/0112-cicd-in-cluster-gitea-actions-buildkit.md))
: sur `git push`, le runner soumet le build au **daemon `buildkitd` distant**
(Option B — le runner reste durci/baseline, le privilège rootless est confiné au
ns `buildkit`, cf. [RUNBOOK buildkit](../buildkit/RUNBOOK.md)). Le runner tourne
en **mode `host`** (les steps s'exécutent dans son conteneur : zéro
Docker-in-Docker, zéro privilège) et ne fait que **soumettre** le contexte de
build ; l'image de code est buildée in-pod (`FROM` interne) et poussée au
registre interne, **sans aucun egress Internet**. Chaîne prouvée air-gap sur
Lima (2026-07-12).

## Prérequis

- Un banc monté jusqu'aux phases `gitops` (Gitea déployé), `registry` (registre
  interne + config node `registry:80` HTTP) et `buildkit` (daemon rootless), et
  la stack active pointée dessus (`nestor stack select <banc>`).
- Les images internes mirrorées au registre : `registry:80/act_runner:0.6.1` (le
  runner) et `registry:80/moby/buildkit:v0.19.0-rootless` (source de `buildctl`
  pour l'initContainer). Sans elles → `ImagePullBackOff` (air-gap, ADR 0011).

## 1. Monter le runner

Le runner est une **phase nestor AUTONOME montée en DERNIER**
(`gitops → registry → buildkit → gitea-runner`), pas un composant de la couche
`gitops`. **Pourquoi cet ordre** : le play `bootstrap/gitea-runner.yaml` mirrore
l'image `act_runner` au registre interne (étape nœuds), or ce mirror exige que
le nœud soit DÉJÀ configuré pour `registry:80` en HTTP (config posée par la
phase `registry`, volet node de `platform-registry`). Placer le runner DANS
`gitops` ferait tourner le mirror `act_runner` AVANT cette config → le
`nerdctl push` échoue (symptôme réel : résolution DNS `registry` en échec +
tentative HTTPS au lieu de HTTP:5000). Le runner dépend aussi de `gitea`
(enregistrement + clone) et de `buildkit` (son initContainer copie `buildctl` de
l'image interne `moby/buildkit`). D'où l'ordre imposé et la phase autonome.

Le playbook enchaîne **deux plays** : étape nœuds (config containerd registre
puis mirror `act_runner`) puis étape k8s (rôle `platform-gitea-runner`). Le
jouer sur la stack active :

```bash
# Config node registre (prérequis) + mirror act_runner → registry:80/act_runner :
nestor ansible gitea-runner.yaml --tags build-images
# Rôle k8s : ns baseline + NetworkPolicies + configmap + token + Deployment durci :
nestor ansible gitea-runner.yaml --tags gitea-runner
```

Vérifier que le Deployment est disponible (via la cible de la stack active) :

```bash
nestor kubectl -n gitea-runner get deploy gitea-runner
nestor kubectl -n gitea-runner get pods -l app=gitea-runner
# Le pod doit être Running/Ready. S'il est CrashLoopBackOff → voir §3 et §4.
```

## 2. Enregistrement du runner

`act_runner` s'enregistre auprès de Gitea par **TOKEN** (pas d'OAuth, pas
d'écran web — c'est ce qui écarte Woodpecker, cf. ADR 0112). Le rôle automatise
la chaîne suivante à chaque run :

1. Il localise le pod Gitea (sélecteur `app = gitea` dans le ns `gitea` — c'est
   le label posé par `platform/gitea/deployment.yaml`, PAS
   `app.kubernetes.io/name`) et échoue tôt si aucun pod Running n'existe.
2. Il génère un token en exécutant dans ce pod
   `gitea actions generate-runner-token`.
3. Il pose le token dans le **Secret `gitea-runner-registration`** (ns
   `gitea-runner`), clé **`token`** (`no_log` — le token n'apparaît pas dans les
   logs Ansible).
4. Le Deployment consomme ce Secret via l'env
   **`GITEA_RUNNER_REGISTRATION_TOKEN`** (`secretKeyRef` → `token`). L'URL cible
   est `GITEA_INSTANCE_URL=http://gitea-http.gitea.svc.cluster.local:80`, le nom
   `GITEA_RUNNER_NAME=runner-host`, la config `/config/config.yaml` (label
   `host:host`, mode `host`, cache désactivé).

Le Secret est (re)posé à chaque run : chaque appel produit un token neuf, et
Gitea accepte le ré-enregistrement. Le fichier `.runner` (état d'enregistrement)
vit dans un `emptyDir` ; la stratégie de déploiement est **`Recreate`** (jamais
deux runners sur le même enregistrement).

Vérifier que le runner est bien enregistré :

```bash
# UI Gitea : Site Administration → Actions → Runners → le runner « runner-host »
#   doit apparaître avec le label `host` et l'état « idle » (ou « active »).
# Logs runner : la ligne « runner: … successfully registered » au démarrage.
nestor kubectl -n gitea-runner logs -l app=gitea-runner --tail=50
```

## 3. Diagnostic / relance

```bash
# État du pod runner :
nestor kubectl -n gitea-runner get pods -l app=gitea-runner
# Logs act_runner (enregistrement, poll de jobs, exécution des steps) :
nestor kubectl -n gitea-runner logs -l app=gitea-runner -f
```

Points à vérifier :

- **initContainer `copy-buildctl`** : il copie `buildctl` depuis l'image interne
  `registry:80/moby/buildkit:v0.19.0-rootless` vers le volume `tools`
  (`/opt/bin`, en tête de PATH du runner). S'il échoue, le pod ne démarre pas —
  lire ses logs :

  ```bash
  POD=$(nestor kubectl -n gitea-runner get pod -l app=gitea-runner -o jsonpath='{.items[0].metadata.name}')
  nestor kubectl -n gitea-runner logs "$POD" -c copy-buildctl
  # → doit imprimer la version de buildctl. Sinon : image moby/buildkit non mirrorée (§Prérequis).
  ```

- **Mirror `act_runner`** présent au registre interne (sinon `ImagePullBackOff`
  sur le conteneur `runner`) :

  ```bash
  nestor kubectl -n gitea-runner describe pod -l app=gitea-runner | grep -iE 'image|pull|back-off'
  ```

- **Relance** : le runner étant en `Recreate` avec un `emptyDir`, un
  `rollout restart` régénère l'enregistrement au démarrage (le rôle repose un
  token neuf au prochain `nestor ansible`). Pour forcer un re-enregistrement
  propre, rejouer `nestor ansible gitea-runner.yaml --tags gitea-runner`.

Note : le runner **n'appelle jamais l'API Kubernetes**
(`automountServiceAccountToken: false`) — il n'y a **pas de RBAC** à vérifier.
Il ne parle qu'à Gitea et à buildkitd en TCP.

## 4. Dépannage réseau (NetworkPolicies + subtilité Cilium)

Le ns `gitea-runner` est en **default-deny** (ingress + egress,
`00-default-deny.yaml`), ré-ouvert par trois `allow-*` chirurgicaux. **Aucun
egress Internet** : le runner ne joint que Gitea et buildkitd (le push au
registre est fait par buildkitd, pas par le runner — il n'y a donc PAS
d'`allow-registry-egress` côté runner).

| Policy                   | Cible (ns)    | Ports          | Rôle                        |
| ------------------------ | ------------- | -------------- | --------------------------- |
| `allow-dns-egress`       | `kube-system` | 53 UDP + TCP   | résout gitea/buildkitd      |
| `allow-gitea-egress`     | `gitea`       | 80 **et** 3000 | enregistrement, poll, clone |
| `allow-buildkitd-egress` | `buildkit`    | 1234           | soumission du build (gRPC)  |

**Subtilité Cilium (prouvée sur Lima)** : sous kube-proxy-replacement,
l'enforcement egress d'une NetworkPolicy s'applique **après** le DNAT
ClusterIP→pod, donc sur le **targetPort du pod cible**, pas sur le port du
Service. Le Service `gitea-http` expose `80` mais son targetPort est `3000` (le
containerPort de Gitea) → il faut autoriser **les DEUX** ports (`80` ET `3000`)
; n'autoriser que `80` fait tomber le trafic par **timeout silencieux**. Même
logique pour tout flux DNAT (le registry côté buildkitd autorise `80` ET
`5000`). Pour buildkitd, le Service et le targetPort sont identiques (`1234`) →
un seul port suffit.

Pistes de diagnostic :

```bash
POD=$(nestor kubectl -n gitea-runner get pod -l app=gitea-runner -o jsonpath='{.items[0].metadata.name}')
# DNS cluster joignable (sinon allow-dns absent/mal appliqué) :
nestor kubectl -n gitea-runner exec "$POD" -- nslookup gitea-http.gitea.svc.cluster.local
nestor kubectl -n gitea-runner exec "$POD" -- nslookup buildkitd.buildkit.svc.cluster.local
# Les policies attendues sont bien posées, default-deny EN PREMIER :
nestor kubectl -n gitea-runner get networkpolicy
```

Symptômes typiques :

- **Enregistrement/poll qui timeout** alors que le DNS résout → la policy Gitea
  n'autorise que `80` (il manque `3000`, le targetPort après DNAT Cilium).
- **`dial tcp …:1234: i/o timeout`** à la soumission du build →
  `allow-buildkitd-egress` absent côté runner, ou `allow-buildctl-ingress`
  absent côté ns `buildkit`.
- **`ImagePullBackOff`** → image `act_runner` ou `moby/buildkit` non mirrorée au
  registre interne (rejouer `--tags build-images`), ou config node `registry:80`
  HTTP absente (phase `registry` non montée avant — cf. §1).
