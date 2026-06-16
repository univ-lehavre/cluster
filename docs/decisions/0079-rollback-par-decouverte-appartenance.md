# 0079 — Découverte de l'appartenance réelle : socle commun `health` + `remove` (vs table codée)

## Statut

Accepted (2026-06-16) — livraison INCRÉMENTALE.

Fait évoluer le rollback par phase ([ADR 0054](0054-rollback-par-phase-banc.md))
et son graphe atomique ([ADR 0066](0066-rollback-atomique-graphe-composants.md))
: le « quoi défaire » est DÉRIVÉ du cluster réel (introspection) au lieu d'être
DÉCLARÉ dans une table. Applique au teardown l'esprit de
[`discover`](0074-cluster-discover-reconstruire-topologie.md) (lire le réel, ne
rien présumer). Borné par [ADR 0046](0046-corriger-le-code-pas-l-etat.md).

### État de la livraison (ce qui est PROUVÉ au banc vs à venir)

- **ÉTAPE A — livrée et prouvée (local-path)** : `remove` défait par défaut, PAR
  DÉCOUVERTE, tout le k8s NAMESPACÉ d'une clôture — supprime les RACINES (le GC
  cascade les possédés), force les CR à finalizer, finalise les ns wedgés. Le
  routage `closure_has_nodeside` (transitoire, dérivé de la table) envoie en
  découverte toute clôture SANS node-side ; `--table`/`--discover` forcent un
  chemin. **Preuve** : `remove dataops` retire postgres+dagster+marquez en UNE
  passe, rc=0, ns finalisés ; rejeu rc=0 (idempotent). Fin de la classe de bugs
  « nom/kind oublié dans la table » (Application `atlas`→`atlas-workflows`, CR
  Argo CD à finaliser — tous trois vécus la même session).
- **CRD cluster-scoped — REPORTÉES (limite découverte)** : on NE supprime PAS
  les CRD par découverte. Le banc a montré que le lien **CRD→opérateur** n'est
  pas découvrable de façon fiable (les `managedFields` d'une CRD/d'un CR portent
  `OpenAPI-Generator`/`kube-apiserver`, pas le nom de l'opérateur) → impossible
  de savoir si une CRD a un opérateur HORS clôture qu'on orphelinerait. Les CR
  sont défaits ; les CRD restent (opérateur réutilisable par un re-`next`). À
  reprendre quand un signal d'appartenance opérateur fiable existera.
- **Node-side — REPORTÉ (irréductible SSH + banc Ceph)** : le wipe disque Ceph
  (et la libération node-side d'un PV local-path coincé) reste au chemin TABLE,
  non prouvable sans banc Ceph (ADR 0034/0052). C'est la SEULE raison pour
  laquelle la table survit — l'objectif reste **zéro table** une fois ce socle
  SSH disponible.

## Contexte

Aujourd'hui, « comment défaire une couche » est une **table codée à la main**
dans `bench/lima/rollback-lib.sh` : `rollback_phase_targeted_resources`
(ressources ciblées par phase), `rollback_phase_namespaces`,
`rollback_phase_crd_groups`, `_STUCK_CR_KINDS` (finalizers à forcer),
`component_targeted`/`component_namespace` (au grain composant). Pour chaque
phase/composant, un humain a ÉNUMÉRÉ ses ressources.

Cette approche est **fragile** — quatre ratés constatés en une seule session de
banc :

- l'OBC `cnpg-backups` était listée **en dur dans `rook-ceph`** alors qu'en
  local-path il n'y a ni OBC ni CRD `objectbucketclaim` → `kubectl delete` en
  erreur (corrigé en conditionnant au backend, mais c'est un rustine de plus) ;
- un **pod CNPG `Terminating`** (conteneur encore `running`) a bloqué la
  finalisation du ns `postgres` — non couvert par le force-delete ;
- le ns `postgres` est resté **wedgé en `Terminating`**
  (`spec.finalizers:[kubernetes]`, contenu « waiting on finalization ») :
  déblocage manuel via le sous-ressource `/finalize` ;
- la clôture s'est **arrêtée au 1er échec** → `dagster`/`marquez` (indépendants)
  sont restés, et `marquez` a fini en CrashLoopBackOff (sa base `postgres`
  détruite sous lui).

Chaque oubli de la table = un rollback incomplet ou cassé. La table est une **2ᵉ
source de vérité** sur ce que les rôles créent — elle dérive du code de montage
qu'elle est censée défaire, et se désynchronise.

### Or Kubernetes PORTE déjà l'appartenance

Le cluster réel sait, sans table, ce qui appartient à quoi :

- **`ownerReferences`** : un Pod pointe son ReplicaSet → son Deployment ; un
  PVC/Secret créé par un opérateur pointe son CR. Le **garbage collector** k8s
  s'en sert déjà pour la suppression en cascade.
- **labels de provenance** : `app.kubernetes.io/managed-by`, `part-of`,
  `instance` (Helm, operators) — qui a posé quoi.
- **arêtes de consommation** : un workload monte un PVC sur une StorageClass,
  lit un Secret/ConfigMap, réclame un bucket (OBC) — lisibles des specs.

## Décision (proposée)

**Dériver le périmètre de rollback du cluster RÉEL par introspection**
(ownerReferences

- labels de provenance + arêtes de consommation), bâtir le graphe
  d'appartenance, et défaire en **ordre topologique inverse** — au lieu de la
  table figée. Cinq points.

### 1. Source = le réel, pas la table (esprit `discover`, ADR 0074)

On LIT les ressources d'une couche (par ses namespaces + ses labels de
provenance + les CR de ses CRD), on suit leurs `ownerReferences` pour clôturer
l'arbre de possession, on ordonne par le graphe. La table `rollback-lib.sh`
devient un **repli/amorce** (les racines à interroger : « la couche monitoring
vit dans le ns monitoring + l'OBC qu'elle produit »), pas l'énumération
exhaustive.

### 2. Backend-agnostique par construction

Plus d'OBC Ceph codée pour un banc local-path : si la ressource n'existe pas
dans le réel, l'introspection ne la voit pas → rien à défaire. Le bug «
ressource d'un autre backend » disparaît (on ne défait que ce qui EST là).

### 3. Déblocage des finalizers/Terminating intégré

Le teardown gère nativement les cas durs constatés : pod `Terminating` à
conteneur vivant → `--force --grace-period=0` ; CR à finalizer dont l'opérateur
est parti → retrait du finalizer ; ns wedgé → sous-ressource `/finalize` en
dernier recours. Ces gestes sont DÉRIVÉS de l'état (« cette ressource ne part
pas → forcer »), pas une liste figée.

### 4. La clôture ne s'arrête PAS au 1er échec

On tente TOUTE la clôture, on agrège les échecs, on rend un verdict PAR
ressource/couche. Une couche indépendante (dagster, marquez) n'est jamais
épargnée parce qu'une autre (postgres) a calé. Corrige
`run_remove`/`phase_rollback` (série + `return` au 1er rc≠0).

### 5. Garde-fous PRÉSERVÉS (ADR 0046/0053/0054)

`BANC_JETABLE=1`, cible banc (kubeconfig + inventaire, ADR 0053), confirmation
avant suppression, opt-in `--full` pour une clôture de stockage. Le rollback
reste un geste de BANC ; rien de cette refonte n'ouvre la porte à un teardown de
prod silencieux.

### 6. Le balayage est `kubectl api-resources` — socle COMMUN health/remove

L'introspection s'appuie sur `kubectl api-resources` :
`--namespaced --verbs=list` donne les types listables d'un ns (≈ 70),
`--namespaced=false` les types cluster-scoped (StorageClass, ClusterIssuer, CRD,
APIService). On itère ces types × le(s) ns de la couche → l'ensemble BRUT des
ressources, puis on filtre par appartenance (owner + labels

- consommation). C'est exactement ce que la table énumérait à la main.

Or **le MÊME balayage sert `nestor health`** : sur chaque ressource découverte,
au lieu de la DÉFAIRE (remove), on LIT son état — `nestor health` = `remove` à
l'envers :

| Geste           | Sur chaque ressource découverte                                                                                                                |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `nestor health` | constate : présente ? PVC `Bound` ? workload `readyReplicas≥want` ? pod phase/restarts ? ns `Active` ? CRD installée ? version (image/label) ? |
| `nestor remove` | défait en ordre topologique inverse (+ force finalizers/Terminating)                                                                           |

La feature « health par composant » (CRD + version + Ready + Bound, demandée
séparément) devient donc un **sous-produit** de ce moteur de découverte : un
seul module d'introspection d'appartenance, deux verbes (lire l'état / défaire).
Prouvé au banc : le même balayage voit `dagster` sain (Ready 1/1) et `marquez`
dégradé (Ready 0/1, restarts) — health le rapporterait tel quel.

## Conséquences

- Fin de la 2ᵉ source de vérité (la table énumérée) : on ne maintient plus une
  liste qui se désynchronise du code de montage — on lit ce qui est posé.
- Les quatre ratés de la session ne se reproduisent pas (backend, pod coincé, ns
  wedgé, clôture interrompue) : ils deviennent des cas DÉRIVÉS, pas des oublis
  de table.
- Coût : l'introspection est plus de code (parcours d'`ownerReferences`,
  requêtes `kubectl -o json`) et doit rester BORNÉE (timeouts, fail-closed) —
  façade I/O, logique pure testable (comme `discover`, ADR 0074 §6).
- Risque : sur-suppression si l'appartenance est mal dérivée. Mitigation :
  amorce par la table de racines + confirmation affichant l'arbre AVANT de
  défaire (comme `refresh`).

## Alternatives écartées

- **Garder la table + rustines au cas par cas** (statu quo) : c'est ce qui a
  produit quatre ratés en une session. La table dérive du code qu'elle défait.
- **S'appuyer UNIQUEMENT sur le GC k8s (ownerReferences seuls)** : insuffisant —
  les ressources cross-namespace (OBC dans rook-ceph), les CR dont l'opérateur
  est parti, et les arêtes de consommation (PVC↔SC) ne sont pas toutes des
  `ownerReferences`. Il faut croiser owner + labels + consommation.
- **Tout réécrire d'un coup** : non — migration incrémentale (la table reste
  l'amorce de racines, l'introspection remplace l'énumération exhaustive phase
  par phase, prouvée au banc).

## À revoir si

- L'introspection se révèle non bornable (clusters énormes, parcours d'owners
  coûteux) → garder la table comme chemin rapide, l'introspection en
  vérification.
- Un sur-rollback est constaté → renforcer l'amorce/confirmation (arbre affiché)
  avant de défaire.
