# 0103 — Workspace Dagster multi-code-location : un reconciler par découverte de labels

## Statut

Accepted (2026-07-03) — livré et **PROUVÉ AU BANC** (reconciler + fragments
atlas, citation + mediawatch tous deux `LOADED`, idempotence `changed=0`,
découverte d'une code-location neuve, survie au re-apply Ansible, absence de
conflit Argo CD).

> **Précisé par [ADR 0111](0111-atlas-instancie-application-argocd.md)
> (2026-07-12).** Le **reconciler de workspace reste PLATEFORME** (côté cluster,
> Ansible) : il découvre les fragments `dagster-workspace-<nom>` par label,
> indifférent à qui a créé l'`Application`. Ce qui change (0111) : chaque
> code-location applicative est instanciée par **atlas** (l'`Application` Argo
> CD distincte), pas par le seed cluster. Le mécanisme décrit ici (fragments
> disjoints + reconciler agrégateur) fonctionne à l'identique.

Supersede partiellement [0086](0086-code-location-jouet-du-socle.md) (le patch
per-CL du ConfigMap partagé + le hook PostSync reload). Prolonge
[0026](0026-orchestration-dagster.md) (orchestrateur Dagster),
[0094](0094-frontiere-deploiement-applicatif.md) (frontière atlas/cluster) et
[0095](0095-build-applicatif-evenementiel-in-cluster.md) (découverte zéro-geste
au build). Respecte les frontières [0022](0022-argocd-gitops-applicatif.md) /
[0033](0033-orchestration-ansible-platform-dataops.md) (infra = Ansible ;
applicatif = Argo CD) et [0046](0046-corriger-le-code-pas-l-etat.md) (corriger
le code, pas l'état). Valeurs génériques
[0023](0023-plateforme-exemple-generique.md) ; images épinglées par digest
d'index [0006](0006-matrice-de-versions-et-politique-de-bump.md) ; mirror
interne [0011](0011-registry-http-sans-auth.md) ; honnêteté des runs
[0034](0034-validation-e2e-from-scratch.md) /
[0052](0052-reproductibilite-des-resultats.md).

## Contexte

Le webserver ET le daemon Dagster chargent **toutes** les code-locations depuis
**un seul** fichier `-w /workspace/workspace.yaml` (ConfigMap
`dagster-workspace`, clé `workspace.yaml`, un
`load_from: [ {grpc_server: …}, … ]`). Or, avec la chaîne de build événementiel
(ADR 0095), **chaque code-location est déployée par une Application Argo CD
DISTINCTE** (une par `dataops/<nom>-dagster/` d'atlas).

Jusqu'ici (ADR 0086), chaque code-location apportait un `workspace-patch.yaml`
qui appliquait le ConfigMap **partagé** `dagster-workspace` en entier, et un
hook PostSync `rollout restart`ait le webserver/daemon. **Deux Applications ne
peuvent pas co-éditer une même clé d'un ConfigMap** : chacune applique le
manifeste COMPLET → elles s'écrasent (la dernière synchronisée gagne). Constaté
au banc en prouvant la 2ᵉ code-location : avec `citation` et `mediawatch`
déployées, le webserver ne chargeait que la dernière — `mediawatch` tournait
(pod gRPC `Running`) mais restait **invisible** dans l'UI. Le commentaire du
patch mediawatch prétendait à tort que les entrées « fusionnent ».

Contraintes vérifiées (doc + code source Dagster 1.13.7) : `-w` est répétable et
Dagster **fusionne** les `load_from` de tous les fichiers ; **pas** de
dossier/glob ; **pas** d'auto-discovery gRPC en OSS. Le webserver/daemon
relisent `-w` **seulement au démarrage** → toute mutation exige un
`rollout restart`.

## Décision

**Chaque code-location pose SON PROPRE ConfigMap DISJOINT ; un reconciler socle
les AGRÈGE dans le workspace central.** Zéro énumération centrale à maintenir :
une code-location neuve = juste son Application (son fragment).

1. **Fragment per-code-location (atlas).** Chaque `dataops/<nom>-dagster/`
   remplace son `workspace-patch.yaml` par un ConfigMap
   **`dagster-workspace-<nom>`** (nom disjoint → zéro collision), labellisé
   `dagster.io/role: code-location` + `app.kubernetes.io/part-of: atlas`, dont
   la clé `fragment.yaml` porte SON entrée `grpc_server` (host **court**
   `<nom>-dagster`, port 4000, `location_name: <nom>`). La code-location reste
   **propriétaire** de son host court (impératif DNS prod, #458).

2. **Reconciler socle (cluster).** Un **CronJob** (ns `dagster`,
   `platform/dagster/reconciler.yaml`) DÉCOUVRE les fragments PAR LABEL, les
   AGRÈGE (ordre déterministe) dans le `load_from:` du ConfigMap central
   `dagster-workspace`, et — **si et seulement si** le workspace a changé —
   `rollout restart`e webserver + daemon. Image `dtzar/helm-kubectl` (kubectl +
   jq + sh, mirrorée au registry interne, digest d'index ADR 0006/0011 ; l'image
   kubectl officielle est distroless, sans shell → inutilisable pour le diff
   idempotent). SA + Role minimal dédiés (le SA `dagster` du chart n'a ni
   `patch deployments` ni écriture de ConfigMap — on ne l'élargit pas, patron
   reload-hook).

3. **Propriété du ConfigMap central.** Le ConfigMap `dagster-workspace` est
   **retiré** du bundle vendored `platform/dagster/dagster.yaml` (un
   `load_from: []` réappliqué à chaque run du rôle écraserait le workspace
   densifié). Le rôle `platform-dagster` le **seed** une seule fois
   (`load_from: []`, `when` absent, pour le 1ᵉʳ démarrage) et **applique le
   reconciler** ; le reconciler en est ensuite **seul propriétaire**.

4. **Frontière.** Le reconciler est l'**agrégateur du workspace de
   l'orchestrateur socle** — il appartient au **cluster**, pas à une
   code-location → **INFRA, posé par Ansible** (ADR 0022/0033), existe avant
   toute code-location, survit au re-apply du rôle. Il **supersede** le patch
   per-CL + le hook PostSync reload d'ADR 0086.

## Conséquences

- **Zéro-geste complet.** La découverte au build (ADR 0095, un `git push` →
  image déployée) est désormais complétée par la découverte au **workspace** :
  la code-location devient **visible** dans l'UI sans aucun geste. Une
  code-location neuve n'exige aucune édition centrale (ni côté atlas des autres
  CL, ni côté cluster).
- **Plus d'écrasement.** Les fragments sont disjoints ; les Applications Argo CD
  ne se battent plus pour une clé partagée, et n'ont plus à déclarer le
  ConfigMap central (le reconciler l'agrège) — donc Argo CD ne le réconcilie pas
  contre le reconciler (prouvé au banc).
- **Latence assumée (honnêteté ADR 0034/0052).** La réconciliation est un
  **filet périodique** (période du Cron), pas un contrôleur temps réel :
  l'apparition d'une code-location neuve dans l'UI a une latence ≤ la période
  (déclenchable à la demande via `kubectl create job --from=cronjob/…`). Le
  rejeu sans changement est un **no-op** (`changed=0`, aucun redémarrage inutile
  — idempotence prouvée).
- **Dette / SPOF.** Un CronJob (pas un opérateur avec watch) : simple, robuste,
  aligné sur les idiomes du dépôt (`garbage-collect-cronjob`, filet
  `builder-reconcile`). Un vrai contrôleur (watch + reconcile immédiat) reste
  une évolution possible si la latence gêne.
- **Migration.** Les code-locations existantes (citation, mediawatch) passent du
  `workspace-patch.yaml` partagé au fragment disjoint ; ADR 0086 reste la
  référence historique du code-location **jouet**, mais son mécanisme de
  workspace (patch partagé + PostSync reload) est remplacé par CE reconciler.
