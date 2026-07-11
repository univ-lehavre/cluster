# Runbook — buildkitd in-pod (ADR 0110, lot 2 : preuve « un pod qui build »)

Ce runbook donne la **séquence `nestor`** pour monter le socle buildkitd (lot 1,
déjà mergé) et **prouver au banc** qu'un `buildctl` in-pod build l'image de CODE
d'une code-location sans réseau (`--network=none`), puis la pousse au registre.
C'est le **lot décisif** du plan
([`plan-build-in-pod-preimage.md`](../../docs/plans/plan-build-in-pod-preimage.md),
issue [#637](https://github.com/univ-lehavre/cluster/issues/637)) : il départage
**fuse-overlayfs vs snapshotter native** sous le PodSecurity du dépôt. Consigner
le déroulé réel dans [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md).

## Prérequis

- Un banc monté jusqu'à la couche `dataops` (registre interne + build-images),
  et la stack active pointée dessus (`nestor stack select <banc>`).
- Une **pré-image** `citation-deps-base:<SHA_DEPS>` présente au registre
  interne. Elle se build **sur le poste** (elle a besoin d'Internet) et se
  pousse au registre (côté `atlas`, ADR 0110) :

  ```bash
  # sur le poste (dépôt atlas), avec un port-forward vers le registre du banc :
  kubectl port-forward -n registry svc/registry 5000:80 &
  dataops/citation-dagster/deploy/build-deps-base.sh --endpoint=localhost:5000
  # → pousse registry:80/citation-deps-base:<SHA_DEPS> (le tag est imprimé)
  ```

## 1. Monter le socle buildkitd

Le mirroring de l'image buildkit (`platform-build-images`) et le rôle
`platform-buildkit` sont câblés dans `bootstrap/dataops.yaml`. Les (re)jouer sur
la stack active :

```bash
# Mirror de l'image buildkit publique → registre interne (mono-arch node) :
nestor ansible dataops.yaml --tags build-images
# Pose du namespace + buildkitd + NetworkPolicies + service :
nestor ansible dataops.yaml --tags buildkit
```

Vérifier que `buildkitd` est Ready (via la cible de la stack active) :

```bash
nestor kubectl -n buildkit get deploy buildkitd
nestor kubectl -n buildkit get pods -l app=buildkitd
# Le pod doit être Running/Ready. S'il est CrashLoopBackOff → voir §3 (le point dur).
```

## 2. Prouver un build in-pod (le cœur du lot 2)

On soumet à `buildkitd` un build de l'image de **code** citation, `FROM` la
pré-image, **sans réseau**, et on vérifie qu'il pousse. Le client `buildctl`
tourne dans le pod buildkitd (il y est bundlé) :

```bash
# SHA_DEPS de la pré-image poussée au §Prérequis (le tag exact) :
DEPS=registry:80/citation-deps-base:<SHA_DEPS>
POD=$(nestor kubectl -n buildkit get pod -l app=buildkitd -o jsonpath='{.items[0].metadata.name}')

# Build de l'image de code, zéro egress. Le contexte de build (l'arbre dataops/
# atlas) est fourni au buildkitd — au banc, le plus simple est de le monter via un
# PVC ou de le pousser en amont ; ce point de plomberie est à finaliser au run
# (le Job du lot 3 l'automatisera). Ici on prouve d'abord le MOTEUR :
nestor kubectl -n buildkit exec "$POD" -- buildctl debug workers
# → doit lister au moins un worker (oci). Sinon buildkitd n'a pas démarré son worker.
```

**Le test décisif** (build réel `--opt build-arg:DEPS_REF=$DEPS` +
`--frontend dockerfile.v0`, source = l'arbre `dataops/`, `--output push` vers
`registry:80/citation-dagster:<rev>`) : à jouer une fois le contexte de build
disponible au pod. Le point à observer et à consigner :

- **le worker démarre-t-il** sous le PodSecurity `baseline` du ns, avec la
  dérogation `seccomp Unconfined` posée (lot 1) ? Si `buildctl debug workers`
  échoue → le rootless ne tient pas en l'état.

## 3. Départager fuse-overlayfs vs native (le point dur ADR 0110)

Le `buildkitd.toml` (ConfigMap `buildkitd-config`) porte `snapshotter = "auto"`.
Observer ce que le worker a choisi :

```bash
nestor kubectl -n buildkit exec "$POD" -- buildctl debug workers -v
# → le champ 'snapshotter' du worker oci. `auto` = fuse-overlayfs si /dev/fuse
#   est disponible, sinon native.
```

Deux cas, à trancher au run :

- **fuse-overlayfs indisponible** (pas de `/dev/fuse` monté — le lot 1 ne l'a
  PAS monté volontairement) : le worker tombe en `native`. Si le build passe en
  `native` → **on fige `snapshotter = "native"`** dans le ConfigMap (plus
  simple, aucune dérogation `/dev/fuse`, acceptable car l'image de code est
  petite).
- **native trop lent / échoue** : monter `/dev/fuse` (device plugin ou, au banc,
  `hostPath: /dev/fuse` + `securityContext` adapté) et figer
  `snapshotter = "fuse-overlayfs"`. C'est la dérogation supplémentaire annoncée.

**Ne pas présumer** : ce qui tient au banc fige le choix. Consigner le verdict
(worker démarré ? snapshotter retenu ? build réussi ? durée ?) dans
`bench/lima/RESULTS.md` — sans ce run, le moteur reste **déclaré mais non
prouvé** (ADR 0034/0052).

## En cas d'échec du worker (le rootless ne démarre pas)

Symptômes probables et pistes, à documenter comme _drifts_ :

- `operation not permitted` sur `unshare`/`mount` → le seccomp `Unconfined`
  n'est pas effectif (vérifier que l'annotation AppArmor `unconfined` est prise
  et que le ns est bien en `enforce: baseline`, pas `restricted`).
- `newuidmap: permission denied` → `allowPrivilegeEscalation: true` (posé au
  lot 1) est requis pour le setuid ; vérifier qu'il n'est pas écrasé.
- registre injoignable au push → vérifier la NetworkPolicy
  `allow-registry-egress` (port 80) et la résolution DNS `registry.registry.svc`
  (le pod n'a pas le `/etc/hosts` du nœud) ; tester
  `nestor kubectl -n buildkit exec "$POD" -- nslookup registry.registry.svc`.
