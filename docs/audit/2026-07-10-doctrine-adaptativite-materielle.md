# Audit — Doctrine d'adaptativité matérielle (cluster + atlas)

**Date** : 2026-07-10 **Périmètre** : `cluster` (nestor, Ansible) + `atlas`
(dataops) **Méthode** : panels de conception adversariaux, ancrés sur le code
réel des deux dépôts **État global** : conception — **aucune ligne implémentée**
(hors ADR 0099 déjà mergé) **Nature** : document de décision, non opposable ;
les décisions structurantes qu'il recense donneront lieu à des ADR dédiés.

---

## 0. Ce qu'il faut décider

Trois décisions de **doctrine** à acter (elles n'engagent pas d'implémentation,
seulement un cap), et deux corrections à faire vite, indépendantes.

### Les 3 décisions de doctrine

1. **Adaptativité matérielle comme fondement.** Une _classe matérielle_ déclarée
   une seule fois fait s'adapter toute la pile (infra + cache de données +
   code). Les trois volets sont conçus et cohérents. → _ADR transverse cluster +
   atlas._
2. **Dissolution de `prod`/`bench` → isolation par identité d'instance.** Le
   garde-fou de sécurité est préservé (et renforcé) via le `stack_id` déjà
   présent dans nestor.
3. **nestor sépare `provisionner` de `installer`.** Deux verbes aux propriétés
   opposées (destructif/coûteux vs idempotent/rejouable).

### Les 2 corrections à faire vite (indépendantes de la doctrine)

- **Bug `max(run)` sur UUID.** mediawatch/pageviews sélectionnent « le dernier
  run » par `max(run)` lexicographique — or le `run_id` Dagster est un **UUID**,
  pas un ULID monotone : le tri est quasi aléatoire, pas la récence.
  _Correction_ (bug de justesse latent).
- **3 vulnérabilités « high » Dependabot** sur `atlas`, signalées à chaque push.

---

## 1. Le principe fondateur

Une seule entrée — la **classe de matériel** — dérive l'infrastructure, la
politique de cache des données, et le comportement du code. Il n'y a plus de «
prod » ni de « banc » : seulement des **instances** sur des **classes**, isolées
par leur **identité**.

| Classe                            | Distribution k8s                  | Stockage bloc         | Stockage objet | Cache de données                                | Profil compute             |
| --------------------------------- | --------------------------------- | --------------------- | -------------- | ----------------------------------------------- | -------------------------- |
| **Portable** (dev, Lima)          | k3s _ou_ k8s                      | local-path            | SeaweedFS      | fenêtre courte (works ≈ 12 mois · GKG ≈ 90 j)   | mem ↓ · threads ↓ · lots ↓ |
| **Baremetal HDD** (edge, OVH)     | **k3s** (etcd impossible sur HDD) | local-path / Longhorn | SeaweedFS      | fenêtre moyenne (works ≈ 36 mois · GKG ≈ 365 j) | intermédiaire              |
| **4 baremetal massifs** (dirqual) | k8s (kubeadm)                     | Ceph (Rook)           | RGW Ceph       | **tout** OpenAlex + GDELT (illimité)            | défauts actuels, à l'octet |

**Pourquoi c'est réaliste** — la doctrine n'invente presque rien, elle _fédère_
des amorces déjà présentes :

- le **catalogue à 4 axes** existe (ADR cluster 0039 : matériel × topologie ×
  terrain × profil) ;
- **SeaweedFS / local-path / Ceph** sont déjà dans la matrice de versions
  (ADR 0006) et le sélecteur de backend ;
- le code a déjà **12+ leviers réglables par env** (voir §4) ;
- le **patron de dégradation propre** existe (MLflow/OpenLineage no-op si
  absents) ;
- l'**identité d'instance** a son socle : `stack_id` (nom de fichier de
  topologie), décrit dans le code comme « l'identité système, source unique ».

---

## 2. Volet A — Infrastructure adaptative (piloté par nestor)

La classe matérielle dérive le triplet (distribution × bloc × objet). nestor
reste **orchestrateur** : il délègue le provisionnement à l'outil-propriétaire,
jamais un moteur à état (frontière ADR cluster 0056 §7).

### A.1 Sélection de substrat — **conçu**

Un protocole `Provisioner` à 3 méthodes — `provision()`, `write_inventory()`,
`facts()` — sélectionné par `catalog.terrain` :

- `local` → **limactl** (câblage existant, zéro ligne neuve) ;
- `cloud` → **OpenTofu** (le seul vrai neuf ; ADR 0032 le cadre, aucun `.tf`
  n'existe encore) ;
- `baremetal` → **no-op** (machines préexistantes, simple préflight SSH).

_Point dur trouvé et corrigé par le panel_ : un dispatch sur le seul callback
`provision` ne suffit pas — l'inventaire et les faits `cp_ip` sont produits par
des gestes spécifiques à Lima. D'où le protocole à 3 méthodes (provisionner /
produire l'inventaire / fournir les faits), chacune déclinée par terrain. La
frontière est tenue : nestor pousse `tofu apply`, consomme un rc + des outputs
JSON, ne lit jamais le HCL ; le tfstate reste hors nestor.

### A.2 Distribution k8s / k3s — **à faire quand HDD réel**

Aujourd'hui `kubeadm` est **en dur** dans la séquence des 6 playbooks de
bootstrap ; `k3s`/`kine` n'apparaissent **nulle part** dans le code (uniquement
dans la prose des ADR).

Le déclencheur est une **contrainte physique**, pas une préférence : un
baremetal **HDD-only** rend etcd inutilisable (latence fsync trop élevée) →
kubeadm impossible de facto → **k3s+kine** (datastore SQLite sans etcd)
obligatoire. La doctrine `kubeadm-only` (ADR 0035) reposait sur la **fidélité
banc↔prod** — argument qui **disparaît** dès lors que prod/bench est dissous.

_Point à vérifier avant tout code_ : k3s embarque son propre containerd (souvent
une version différente) — casse-t-il le montage **Image Volumes** de pgvector
(feature PG18/CNPG) ? Si oui, il faudrait une image Postgres+pgvector custom
pour cette classe (impact matrice ADR 0006).

### A.3 Isolation par identité — **conçu**

Remplace `prod`/`bench` sans perdre le garde-fou. Le socle existe déjà :

- `stack_id` = nom de fichier de topologie, « identité système, source unique »
  (ADR 0102 volet B) ;
- kubeconfig déjà nommé par stack (`.kubeconfigs/<stack>.config`), garde
  structurelle qui ne peut jamais retomber sur `~/.kube/config` ;
- `EXPECTED_CLUSTER` vérifié par preuve positive avant tout seed prod.

**9 usages de `target_kind`** sont à reraccrocher à l'identité, dont 3
structurels : la présence de la phase `up` (provisionner), la dérivation du
transport (limactl/ssh), et la garde d'isolation `classify_inventory_target` (le
cœur de la faille documentée : « un `next dataops` visant le banc a reconfiguré
containerd sur les nœuds prod »). Le nouveau modèle est **aussi sûr** : on
n'agit que sur l'instance explicitement nommée, jamais de cible implicite.

### A.4 Provisionner vs installer — **à acter**

nestor doit distinguer nettement deux commandes aux propriétés opposées :

| Verbe            | Ce qu'il fait                                      | Propriété                              | Propriétaire de la ressource  |
| ---------------- | -------------------------------------------------- | -------------------------------------- | ----------------------------- |
| **provisionner** | crée le substrat (VM Lima/OVH) ou rien (baremetal) | destructif, coûteux, rare, à confirmer | limactl / OpenTofu / personne |
| **installer**    | OS + k8s/k3s + plateforme (Ansible)                | idempotent, rejouable (`changed=0`)    | Ansible (nestor orchestre)    |

On doit pouvoir _installer_ (re-converger) **sans re-provisionner**. C'est
cohérent avec l'isolation par identité (installer sur l'instance X ≠
provisionner une nouvelle instance) et matérialise la frontière ADR 0056 dans la
CLI.

---

## 3. Volet B — Cache de données adaptatif (côté atlas)

De « tout stocker » (massif) à « fenêtre glissante bornée » (contraint). Les
deux exemples donnés — OpenAlex filtré à la volée, GDELT en stats mensuelles
immuables — sont **réalisables sans réécriture**.

### B.1 Politique retenue — **conçu**

**Fenêtre glissante** par partition (`floor = watermark − TTL`), _ni_ TTL
horloge nu _ni_ LRU générique. Justification : l'accès au brut est
**chronologique**, pas aléatoire (le watermark avance, l'incrémental ne lit que
le postérieur, le staging mediawatch traite une seule partition `event_day`/run
puis n'y revient jamais). Un LRU tracerait des accès inexistants — la récence
temporelle **est** la pertinence métier.

- Dérivés (mart ~200 Mio, timeline, forecasts, watermark, manifests) **épinglés
  hors quota** sur toutes les classes ;
- brut lourd (works 1,27 TiB, GKG natif depuis 2015) **seul candidat** à
  l'éviction, du plus ancien au plus récent, au grain de la partition ;
- réglé par **2 variables d'env par classe** via l'overlay Kustomize déjà en
  place (le canal qui pousse déjà `SAMPLE_SIZE`/`MAX_PARTITIONS` au banc).
  Massif = `0` (illimité), l'évinceur ne s'arme jamais → comportement prod
  identique.

### B.2 Correction préservée — **le point clé vérifié**

Une fois le mart/agrégat produit, **aucune étape aval ne relit le brut** (ni les
1,27 TiB de works, ni le GKG natif). L'éviction est donc **sûre pour le résultat
courant** :

- OpenAlex : garder seulement `mart_eunicoast` + watermark est **correct pour le
  périmètre actuel** ; on ne perd que la capacité de **re-filtrer un autre
  périmètre** (les 14 ROR / l'année plancher) sans re-télécharger. Économie >
  99,98 % du stockage.
- GDELT : `marts_university_timeline` est **déjà un agrégat**
  (`count … group by university, event_date`) au grain journalier ; le forecast
  lit l'agrégat, **pas** le raw. La « stat mensuelle immuable » = rouler cet
  agrégat au mois + purger le raw natif du jour après production.

**Dégradation = perte de _capacité_ (rejeu / re-filtrage hors fenêtre), jamais
d'_exactitude_.** Point à border dans l'ADR : la reproductibilité (ADR
atlas 0057) — les partitions immuables + le watermark aident, mais une éviction
sous la fenêtre empêche un rejeu à l'identique d'un run ancien.

---

## 4. Volet C — Code applicatif adaptatif (côté atlas)

La classe dérive un profil (compute, modèle, dégradation, périmètre). Le code a
**déjà** les leviers — mais épars et réglés à la main ; la doctrine les fédère.

### C.1 Frontière retenue — **conçu**

Deux étages, frontière nette :

- **nestor transporte** : une seule env sémantique
  `ATLAS_HARDWARE_CLASS ∈ {portable, baremetal-hdd, 4-massifs}`, posée sur le
  `env:` du Deployment de code-location (là où l'overlay pose déjà
  `CITATION_INGEST_SAMPLE_SIZE`). nestor **ne dérive pas** les 12 valeurs —
  sinon l'invariant OOM (`memory_limit` DuckDB < limite pod) migrerait dans une
  table YAML non testée.
- **atlas dérive** : une fonction **pure**
  `resolve_profile(hardware_class, env=None) -> Profile` dans un module
  `profile.py` par workspace (frère de `resources.py`, qui reste un
  _connectivity loader_ pur). Testable env-injectée.

La table `_CLASSES` **ne crée aucune valeur** — elle rassemble en 3 colonnes
cohérentes les défauts aujourd'hui éparpillés. La colonne `4-massifs`
**reproduit à l'octet** les défauts prod actuels (`24GB`/`32` threads, `56Gi`
pod, `5M` works/lot, `800000` labels uplift, `4` fichiers GE) → **continuité
totale**. Les env vars actuelles restent des **overrides rétrocompat**.

### C.2 Dégradation propre — **conçu**

Généraliser le no-op silencieux (déjà là pour MLflow/OpenLineage absents ;
`_read_embeddings` best-effort) à **tous** les composants optionnels (pgvector,
index, MLflow) : une petite instance produit un résultat **correct quoique
réduit**, jamais un crash.

- Le modèle ONNX fait **22 Mo** (correction : pas 90). Il reste **fixe** ; la
  dégradation de qualité sur petite instance est **explicite** via la porte
  prédictif/descriptif existante (`has_predictive_power`).
- Générique préservé (ADR atlas 0031/0035) : la classe est un **paramètre
  d'instance**, pas une branche par déployeur. Le code reste neutre.

---

## 5. Chantiers indépendants de la doctrine

Conçus pendant la session, ils tiennent seuls.

### 5.1 Pré-image de build « figée » — **conçu · fort impact (P0)**

Scinder le Dockerfile citation en deux artefacts au cycle de vie disjoint :

- `citation-deps-base` (image LOURDE, figée) : `python:3.10-slim` + `rclone`
  (apt) + les **193 wheels** du `uv.lock` + extensions DuckDB + **modèle ONNX 22
  Mo**. Rebuild **rare** (~1×/mois, quand `uv.lock` change), node-side (le seul
  build qui touche Internet).
- image du **code** : `FROM citation-deps-base` + `COPY src` +
  `uv pip install --no-deps .` + `COPY citation-dbt` + `dbt parse`. **Zéro
  téléchargement** (`--no-deps` + `UV_OFFLINE=1` en ceinture-bretelles ;
  `dbt parse` déjà hermétique).

**Conséquence majeure** : le build du code ne fait **strictement aucune requête
sortante** → il peut tourner **in-pod** (Kaniko/Buildkit rootless sans réseau).
Cela **démolit** la seule objection qui avait fait écarter le build-in-pod (ADR
cluster 0095 : « le build casse au premier `apt-get` ; Kaniko n'aide en rien sur
l'air-gap »). Le « mur node-side » **tombe** : plus besoin de timer systemd
node-side / runner host pour les commits courants. Reste un build node-side
**occasionnel** (rafraîchir la base), avec egress bornable par NetworkPolicy à
ce seul moment. Vrai air-gap (zéro egress) — meilleur pour le futur serveur
public.

### 5.2 Promotion de mart / modèle — **conçu**

Rollout progressif des **données** (pas Argo Rollouts, inadapté à un producteur
batch sans trafic). Un pointeur `index_pointer` dans pgvector désigne le run
**stable** servi ; le run candidat est chargé sans être servi ; promotion =
`UPDATE` du pointeur après validation ; rollback = repointer (runs immuables).
L'API lit une vue `researchers_current`.

- Répare au passage le bug `max(run)` : la version est **`run` seul**
  (`CURATED_DT` est constant, `dbt.py:60`) — le pointeur explicite remplace un
  `max()` faux.
- La vue doit être rendue **enforçable** (`REVOKE SELECT ON researchers` +
  `GRANT` sur la vue) — spécifiée dans l'ADR, créée au branchement réel
  (aujourd'hui l'API sillage lit des mocks).
- Le « canary progressif » réaliste = **fenêtre d'observation** (le candidat
  servi en shadow, on compare les métriques applicatives), pas un vrai % de
  trafic (sur-ingénierie pour un batch mono-opérateur).

### 5.3 Déduplication mart EUNICoast — **livré (ADR 0099, PR #596 mergée)**

Déduplication par récence (`updated_date desc`), globale, dans l'asset
`mart_eunicoast` ; coalescing conçu. Corrige un défaut sémantique réel (le
watermark additif gardait des versions périmées au FWCI le plus élevé). 246
tests verts.

---

## 6. État du chantier GitOps / déploiement

Longue exploration convergée. **Le point de bascule** : la pré-image (§5.1)
supprime le mur du build, ce qui rebat les cartes en faveur d'une CI in-cluster.

| Question                                          | Verdict                                                                                                                                                   | État              |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| On garde Argo CD ?                                | **Oui.** Auto-sync + selfHeal + webhook Gitea déjà câblés (conservés par ADR 0105).                                                                       | acquis            |
| Le vrai trou ?                                    | **Remplir Gitea** avec le code à jour + le digest de l'image.                                                                                             | cadré             |
| Le retrait GitOps auto (0105) était-il justifié ? | En partie **rationalisé** : le « 52 % d'échec » n'a aucune source dans le dépôt ; l'amplification était un bug de dédup jamais corrigé (Sensor sans clé). | établi            |
| Où build l'image ?                                | Node-side aujourd'hui — _mais_ la pré-image rend le build-in-pod possible.                                                                                | **à re-trancher** |
| CI Gitea autonome ?                               | Choisie : le cluster re-valide (cohérent air-gap ADR 0044). Gitea pilotable comme GitHub (API REST / `tea`).                                              | décidé            |
| Acheminement main → Gitea sans Tailscale ?        | Le seed pousse déjà via `kubectl port-forward`. SSH-git ou runner LAN.                                                                                    | ouvert            |

**Conséquence de la pré-image** : si le build devient in-pod, le déclencheur
node-side (Sentinelle / timer systemd, **ADR 0106 brouillon non commité**)
devient _probablement inutile_ — Gitea Actions in-pod suffirait (CI + build en
un). **L'ADR 0106 est à reconsidérer** à cette lumière, pas à committer tel
quel.

### 6.1 « GitOps complet » — ce qu'on peut affirmer, et la frontière exacte

Question posée : peut-on dire qu'on fait du **GitOps complet** avec `cluster` +
`atlas` combinés, **hors GitHub** ? Réponse : **oui, pour le déploiement — avec
deux précisions qui évitent le sur-claim.**

**Sur les 4 principes canoniques du GitOps (OpenGitOps / CNCF), la chaîne les
satisfait tous :**

| Principe GitOps       | Chaîne Gitea + Argo CD (hors GitHub)                                       | Verdict |
| --------------------- | -------------------------------------------------------------------------- | ------- |
| Déclaratif            | état désiré en manifestes Kustomize / `Application` Argo CD                | ✅      |
| Versionné & immuable  | tout vit dans Gitea (`atlas/atlas`, `cluster/apps`), déploiement `@sha256` | ✅      |
| Tiré automatiquement  | Argo CD pull/réconcilie Gitea en continu (auto-sync)                       | ✅      |
| Réconcilié en continu | `selfHeal` corrige toute dérive du live vs Git                             | ✅      |

**Précision 1 — la frontière GitOps s'arrête à Argo CD ; la fabrique d'image est
impérative, en amont.** Le GitOps couvre « Git → cluster ». Mais **remplir
Gitea** (le code + le digest de l'image) implique un **build**, qui est un acte
**impératif**, pas déclaratif. Argo CD déploie une image _déjà buildée par
digest_ ; il ne la fabrique pas. C'est **universel** — aucun système n'est «
GitOps » sur le build d'image. Donc « GitOps complet » décrit la chaîne de
**déploiement**, pas la chaîne de bout en bout, qui est **« CI impérative →
GitOps »**.

**Précision 2 — GitHub n'est pas dans la boucle de déploiement, mais reste la
source.** Le code naît sur GitHub (`univ-lehavre/atlas`) et doit être
**acheminé** vers Gitea (maillon non encore tranché, cf. §6). Le GitOps _interne
au cluster_ (Gitea → Argo CD) est **autonome de GitHub** ; mais le pont GitHub →
Gitea est un maillon impératif externe à la boucle GitOps.

**Formulation juste, sans exagérer ni sous-vendre :**

> On fait du **GitOps complet, souverain et air-gappé** : Argo CD réconcilie en
> continu, par digest immuable, l'état déclaré dans le Gitea interne du cluster
> — sans dépendre de GitHub dans la boucle de déploiement. La fabrique d'image
> (CI) est **impérative, en amont**, comme dans tout système ; elle alimente le
> dépôt GitOps mais n'en fait pas partie.

**Bémol factuel** : c'est vrai **par conception**, pas encore **en service**. Le
maillon aval (Argo CD ↔ Gitea) **fonctionne** et est un GitOps de déploiement
réel et complet. Mais la CI Gitea (Gitea Actions) est **greenfield** (non
activée) et l'acheminement GitHub → Gitea n'est **pas câblé** (le Gitea dirqual
est figé au 2026-07-08). Donc : **le GitOps de déploiement est réel et complet ;
la chaîne CI → GitOps de bout en bout est conçue mais pas encore
opérationnelle.**

---

## 7. Feuille de route priorisée

Le principe : **acter la doctrine maintenant** (peu coûteux, oriente tout) ;
**implémenter au fil des besoins matériels réels**.

### P0 — Tout de suite (jours)

- Corriger le bug `max(run)` UUID (mediawatch/pageviews). Indépendant, rapide.
- Traiter les 3 vulnérabilités Dependabot.
- **ADR : pré-image de build.** Débloque le build-in-pod, réduit l'egress,
  améliore la sécurité. Fort levier, indépendant de la doctrine.

### P1 — Acter la doctrine (semaines)

- **ADR transverse : adaptativité matérielle** (le principe + la matrice + les 3
  volets). N'engage pas l'implémentation.
- **ADR : isolation par identité** (dissout prod/bench, généralise `stack_id`).
  Prérequis des autres volets nestor.
- **ADR : provisionner / installer** (sépare les deux verbes nestor). Commencer
  par un refactor iso-comportement (massif = comportement actuel).

### P2 — Implémenter le socle (quand utile)

- Profil de code (`resolve_profile`) — fédère les env vars ; colonne massif =
  défauts actuels → zéro régression sur dirqual.
- Cache fenêtre glissante — 2 env par classe, évinceur qui ne s'arme qu'en
  dessous du quota.
- Re-trancher le GitOps à la lumière de la pré-image (Gitea Actions in-pod vs
  Sentinelle).

### P3 — Quand le matériel arrive (sur besoin)

- Bras OpenTofu / OVH — le seul vrai neuf du substrat ; utile quand un serveur
  OVH existe.
- Distribution k3s + Longhorn — quand la machine HDD-only est là ; vérifier
  l'impact pgvector d'abord.
- Promotion de mart — quand l'API sillage lit réellement l'index (aujourd'hui :
  mocks).

---

### Le fil directeur

La valeur immédiate n'est **pas** d'implémenter — c'est d'**acter le principe**
(P0/P1), qui empêche de re-figer des décisions à une seule valeur (prod,
kubeadm, tout-stocker). L'implémentation (P2/P3) suit les besoins matériels
réels : on ne code le bras OVH ou k3s que le jour où la machine existe. Le
refactor « massif = comportement actuel à l'octet » garantit **zéro régression**
sur dirqual pendant toute la transition.

---

_Audit fondé sur 6 panels de conception adversariaux, ancrés sur le code réel
des dépôts `cluster` et `atlas`. Aucune ligne implémentée — document de
décision._
