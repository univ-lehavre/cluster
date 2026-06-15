# 0075 — Kyverno CLI en CI : valider nos invariants de manifeste en statique

## Statut

Proposed (2026-06-15).

**Fonde sur** l'audit
[`docs/audit/workflows/2026-06-15-audit-cncf-kyverno.md`](../audit/workflows/2026-06-15-audit-cncf-kyverno.md)
(éventail + revue adversariale, 60 agents, 2 passages) qui a confronté chaque
opportunité CNCF aux garde-fous d'adoption et désigné **Kyverno CLI statique en
CI** comme le gain le moins cher et le plus défendable. Prolonge la réflexion
ouverte par
[`note-runtime-admission.md`](../audit/2026-05-29/note-runtime-admission.md) («
en CI (Kyverno CLI) … le candidat "en CI" le plus défendable »).

**Cadre l'invariant digest
d'[ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)** sans le
superseder : 0006 reste `Accepted`. Cet ADR **précise** la portée exacte de
l'épinglage digest (jusqu'ici « idéalement … pour les composants critiques »,
[0006 §6 L124](0006-matrice-de-versions-et-politique-de-bump.md)) en la rendant
**vérifiable en statique**, et **complète** le garde-fou d'exposition
d'[ADR 0020](0020-exposition-reseau-tout-cilium.md) (jusqu'ici vérifié seulement
contre un cluster vivant).

**Conforme à la gouvernance**
[ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) §6 : tant que cet
ADR est `Proposed`, **aucun code** (policies, script `lint:kyverno`, job CI)
n'est produit. Le passage à `Accepted` est le signal qui autorise
l'implémentation. Application directe du **biais adoptif borné**
[ADR 0061](0061-posture-adoption-bonnes-pratiques.md) : pratique CNCF adoptée
**parce que** son gain net dépasse le coût de diversité (binaire statique,
offline, zéro composant runtime) et qu'elle ne contredit aucun ADR `Accepted`.

## Contexte

Le dépôt fait reposer la conformité de ses manifestes sur **deux mécanismes
hétérogènes** :

1. **Trivy `config`** (IaC statique en CI) — détecte les _misconfigurations
   connues_ du catalogue KSV. Efficace, mais (a) ne porte **pas** _nos_
   invariants propres, et (b) sa règle de tag-pinning est de gravité LOW/MEDIUM,
   or la CI ne casse qu'en HIGH/CRITICAL.
2. **Du code impératif maison** qui encode _nos_ règles, mais **partiellement et
   tard** :
   - [`scripts/audit-image-digests.sh`](../../scripts/audit-image-digests.sh)
     vérifie que chaque digest pointe un **index multi-arch** — mais sa capture
     ([L50](../../scripts/audit-image-digests.sh)) ne matche que le motif
     `image: …:tag@sha256:…`. **Une image épinglée par _tag seul_ n'est donc
     même pas auditée** : elle échappe à la fois à Trivy (gravité trop basse) et
     à l'audit (hors motif). De plus l'audit **exige le réseau** (il interroge
     le registre pour lire le `MediaType`), donc ne tourne pas dans les jobs
     offline.
   - L'invariant d'exposition
     d'[ADR 0020](0020-exposition-reseau-tout-cilium.md) (« services applicatifs
     en ClusterIP ; exposition **uniquement** par la bordure Gateway ») est codé
     en **couche 7b** de [`bootstrap/state.sh`](../../bootstrap/state.sh)
     ([L802-812](../../bootstrap/state.sh)) et **ne s'exécute que contre un
     cluster vivant** (toutes les sections sont gardées par
     `cluster_target_ready`, [state.sh L106](../../bootstrap/state.sh)). Un
     `type: LoadBalancer` hors-Gateway introduit dans `platform/*.yaml` n'est
     donc détecté **qu'après déploiement**.

L'audit a **vérifié sur fichiers** que ces deux trous sont réels, pas théoriques
:

- `platform/seaweedfs/seaweedfs.yaml` (`seaweedfs:4.31`) et
  `storage/ceph/backup/snapshot-cronjob.yaml` (`bitnami/kubectl:1.34`) sont
  pinnés par tag seul → invisibles pour l'audit digest. Ordre de grandeur : ~43
  images digest-pinnées vs ~10 tag-only.
- `platform/mailpit/mailpit.yaml` expose un `Service type=LoadBalancer`
  (`mailpit-smtp`) hors-Gateway — une exception **réelle et assumée**, mais qui
  n'aurait été visible qu'au run.

Ces invariants sont **les nôtres** (ils découlent de nos ADR), pas des misconfig
génériques. C'est précisément le créneau de **Kyverno en CLI** : `kyverno apply`
évalue des _policies maison_ contre les manifestes **avant merge**, **100 %
offline**, **sans déployer aucun composant**. Complémentaire de Trivy (qui garde
les misconfig KSV) et de l'audit digest (qui garde « le digest pointe un index
multi-arch ») : Kyverno garantit, lui, que **chaque image EST pinnée par
digest** et qu'**aucun Service interdit n'est exposé**.

La question n'est donc pas « adopter Kyverno » au sens large (l'admission sur le
cluster est un **autre** sujet, runtime, traité ailleurs — cf. « À revoir si »),
mais **introduire le binaire `kyverno` comme maillon de lint statique**, au même
titre que `kubeconform`, `yamllint` ou `shellcheck`.

## Décision

**Adopter Kyverno CLI comme étape de lint statique en CI**
(`pnpm lint:kyverno`), portant deux `ClusterPolicy` maison, exécutées hors-ligne
contre les manifestes versionnés. **Aucun déploiement de Kyverno sur le
cluster** n'est décidé ici.

### 1. Deux policies maison, versionnées

Les policies vivent dans un répertoire dédié **non vendored**, p. ex.
`platform/policies/` (manifestes maison, donc soumis à prettier/yamllint, à la
différence des bundles vendored exclus).

**`require-image-digest`** (validate, `failureAction` selon §3) — toute image de
`containers`/`initContainers`/`ephemeralContainers` doit matcher `*@sha256:*`.
Ferme le trou tag-only de
[`audit-image-digests.sh`](../../scripts/audit-image-digests.sh) : la policy
garantit la **présence** d'un digest ; l'audit garde la vérification que ce
digest **pointe un index multi-arch** (le banc est arm64,
[ADR 0006 §6 L125](0006-matrice-de-versions-et-politique-de-bump.md)). Les deux
sont **complémentaires**, aucun n'est redondant.

**`restrict-service-exposure`** (validate) — refuse tout `kind: Service` de
`type` `LoadBalancer` ou `NodePort`. Porte l'invariant
d'[ADR 0020](0020-exposition-reseau-tout-cilium.md) **avant merge**, là où la
couche 7b de [`state.sh`](../../bootstrap/state.sh)
([L802-812](../../bootstrap/state.sh)) ne le voyait qu'au run. La couche 7b
**reste** (elle attrape le drift _en place_, runtime) : l'invariant vit
désormais en **deux endroits cohérents** — statique avant merge, dynamique sur
cluster.

### 2. Mécanisme d'exception adapté au statique

⚠️ **Point dur identifié par l'audit.** L'exception de la couche 7b repose sur
le label `gateway.networking.k8s.io/gateway-name`
([state.sh L808-809](../../bootstrap/state.sh)) que **Cilium pose à runtime**
sur le Service qu'il génère pour un Gateway. Ce label **n'existe pas dans les
manifestes versionnés** (qui déclarent un `kind: Gateway`, jamais ce Service) :
le mécanisme d'exception 7b est donc **inopérant en statique**. La policy doit
employer un mécanisme **différent**, au choix à l'implémentation :

- une clause `exclude` Kyverno ciblant nommément les Services exposés assumés,
  ou
- un label **maison versionné** (p. ex.
  `expo.cluster/loadbalancer-assume: "<motif>"`) apposé sur les rares Services
  d'exposition légitimes.

Les exceptions **versionnées connues** à couvrir explicitement (vérifiées) :
`mailpit-smtp`
([`platform/mailpit/mailpit.yaml`](../../platform/mailpit/mailpit.yaml),
exposition SMTP de bordure assumée) et l'exemple
`storage/ceph/storageClass/examples/nodeport.yaml`. Le Service `LoadBalancer`
**du Gateway lui-même** n'est jamais dans les manifestes (généré par Cilium),
donc hors-scope statique — aucun faux positif de ce côté.

### 3. Portée de l'enforcement : `Audit` d'abord, `Enforce` ensuite

⚠️ **Point dur identifié par l'audit.** ADR 0006 formule le digest comme «
idéalement … pour les composants critiques »
([§6 L124](0006-matrice-de-versions-et-politique-de-bump.md)) — pas comme une
**obligation**. Un `Enforce` immédiat de `require-image-digest` ferait rougir la
CI sur les ~10 images tag-only **assumées** (dont les images maison
`registry:80/…` du banc, et des dépendances upstream pinnées par tag).

Cet ADR **tranche la portée** : l'invariant digest devient **obligatoire pour
les manifestes versionnés**, avec une **liste d'exceptions explicite et
justifiée** (même esprit que `.trivyignore.yaml` : allowlist par chemin avec
motif). Mise en œuvre en **deux temps** :

1. policy en **`Audit`** (rapport, CI verte) → on inventorie et on justifie
   chaque image tag-only restante (la corriger en digest, ou l'inscrire à
   l'allowlist) ;
2. bascule en **`Enforce`** (CI rouge sur violation) une fois l'allowlist
   stabilisée.

`restrict-service-exposure` peut viser `Enforce` d'emblée (les 2 exceptions sont
connues et finies).

### 4. Intégration toolchain : un maillon de plus, pas une toolchain de plus

Nouveau script `lint:kyverno` dans [`package.json`](../../package.json), ajouté
à la chaîne `lint`, calqué sur `lint:k8s` (même sélection `git ls-files -z`,
**mêmes exclusions vendored** `:!:` — ne pas dupliquer la liste mais la
**factoriser** avec `lint:k8s` pour éviter deux listes à maintenir). Le binaire
`kyverno` rejoint `kubeconform`/`yamllint` dans l'environnement CI. Job CI :
statique, offline, sans cluster — il tourne dans le même `pnpm lint` que le
reste (≠ jobs runtime). Conforme à la doctrine « un outil par action »
([ADR 0049](0049-doctrine-choix-outil-par-action.md)) : Kyverno CLI = l'outil de
_nos_ invariants de manifeste ; Trivy garde les misconfig KSV ; kubeconform
garde la conformité de schéma. Pas de recouvrement.

## Conséquences

**Bénéfices.**

- **Deux trous de conformité réels fermés avant merge**, prouvés sur fichiers
  (tag-only invisible ; exposition vérifiée seulement au run).
- **Zéro composant runtime** : `kyverno apply` est un binaire de lint, offline,
  sans empreinte cluster ni charge opérationnelle — argument central sur un
  cluster non-HA mono-admin ([ADR 0029](0029-markdown-atteignable-doc.md) pour
  la philosophie « charge = prix à payer » ; ici le prix est **nul** côté
  runtime).
- **Nos invariants deviennent exécutables et tracés** plutôt que dispersés entre
  un script réseau-dépendant et une couche bash runtime.
- **Réversible** : retirer une étape de lint est trivial (≠ désinstaller un
  composant cluster).

**Coûts assumés.**

- **Un binaire de plus dans la CI** (`kyverno`) à épingler/maintenir dans la
  matrice de versions
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)). Coût de
  diversité réel mais **borné** (outil statique, pas de runtime).
- **Une liste d'exceptions à tenir** (images tag-only assumées, Services
  exposés) — comme `.trivyignore.yaml`, avec justification par entrée. Dette de
  maintenance modeste et explicite.
- **Travail de cadrage préalable** (phase `Audit`) avant de pouvoir basculer en
  `Enforce` sans casser la CI sur l'existant.

**Validation (à produire).**

- `pnpm lint:kyverno` **vert** sur l'état courant en mode `Audit`, avec un
  rapport listant les images tag-only et les Services exposés actuels.
- Un manifeste de test introduisant une image tag-only **et** un
  `Service type=LoadBalancer` non exempté → `lint:kyverno` **rouge** une fois en
  `Enforce` (preuve que le garde-fou mord).
- Idempotence/reproductibilité : le lint donne le même verdict en local et en
  CI, **sans réseau** (≠ `audit-image-digests.sh`).

## À revoir si

- **L'admission sur le cluster** est priorisée (Kyverno comme webhook refusant
  les manifestes non conformes à l'`apply`, et/ou `verifyImages` pour la
  signature) : c'est un **composant runtime**, donc un **autre ADR**, à traiter
  **avec** la Phase 7.2 (signature d'images cosign/Sigstore) pour décider
  Kyverno-admission _vs_ policy-controller **une seule fois** — cf.
  [`note-runtime-admission.md`](../audit/2026-05-29/note-runtime-admission.md).
  Le présent ADR ne décide **que** le volet CLI/CI.
- Le nombre de policies maison croît au point de justifier un **PolicyReport /
  policy-reporter** : réévaluer alors le passage en admission (où ces rapports
  prennent leur sens), pas en CLI.
- ADR 0006 est révisé sur la portée digest : réaligner l'allowlist de
  `require-image-digest`.

## Alternatives écartées

**Ne rien ajouter (garder uniquement Trivy + scripts maison).** Statu quo.
Écarté : les deux trous (tag-only, exposition runtime-only) sont **vérifiés et
réels** ; les laisser ouverts contredit la posture qualité du dépôt alors que le
coût de fermeture est faible et **sans runtime**.

**Étendre `audit-image-digests.sh` au cas tag-only en bash.** Possible, mais (a)
ne couvre **que** le digest, pas l'exposition ; (b) reste un script maison de
plus là où une policy déclarative est plus lisible et **réutilisable** (le même
binaire porte les deux invariants et les suivants). Surtout, l'audit a montré
que `restrict-service-exposure` justifie **à lui seul** d'introduire Kyverno CLI
— une fois le binaire là, `require-image-digest` est **amorti gratuitement**.
Deux scripts bash distincts coûteraient plus en dispersion qu'une étape Kyverno
unique (ADR 0049).

**Déployer Kyverno en admission directement.** Plus puissant (refus à
l'`apply`). Écarté **ici** : c'est un composant runtime stateful (webhook) sur
un cluster non-HA mono-admin, structurant, qui **recoupe la Phase 7.2** — à
décider une seule fois, pas en doublon. Le volet CLI livre l'essentiel du gain
(garde-fou avant merge) **sans** ce coût. L'admission reste un palier ultérieur
assumé, pas un préalable.

**Forcer le digest en `Enforce` immédiat.** Écarté : romprait la CI sur les ~10
images tag-only assumées sans cadrage préalable, et **survaloriserait** la
formulation « idéalement » d'ADR 0006. La séquence `Audit` → allowlist →
`Enforce` (§3) adopte l'invariant **proprement**.
