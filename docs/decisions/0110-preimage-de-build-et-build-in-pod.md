# 0110 — Pré-image de build : l'image de code se construit sans réseau (in-pod), la base lourde hors cluster

## Statut

Accepted (2026-07-11), **amendé le 2026-07-11 — le volet BUILD IN-POD est
ABANDONNÉ ; le split pré-image reste.** **RÉ-AMENDÉ le 2026-07-12
([ADR 0112](0112-cicd-in-cluster-gitea-actions-buildkit.md)) — le build in-pod
est RÉTABLI : la réfutation ci-dessous reposait sur un diagnostic erroné (le pod
buildkitd n'échouait pas par une limite de k8s, mais parce que son namespace de
build était labellisé `enforce: baseline` ; un ns non labellisé l'admet et le
build in-pod FONCTIONNE, prouvé au banc).** Le volet « split pré-image »
ci-dessous reste valide. Le récit d'abandon qui suit est conservé pour
l'historique. Le run banc a RÉFUTÉ l'hypothèse centrale « buildkit rootless
in-pod tolérable sous PodSecurity » : sur k8s ≥ 1.34, PodSecurity `baseline`
**interdit** `seccompProfile: Unconfined` ET `AppArmor: unconfined` (message
d'admission
`violates PodSecurity "baseline:latest": forbidden AppArmor profiles … seccompProfile … Unconfined`),
et tout moteur de build rootless (buildkit, kaniko, buildah…) exige ces
dérogations pour ses `unshare`/`mount`. Le pod buildkitd n'a jamais pu être créé
(0 pod, rejets d'admission répétés). Combiné au fait que l'automatisme « build à
chaque merge » n'existe plus (Argo Events abrogé,
[ADR 0105](0105-retrait-build-evenementiel-node-side-terminal.md)/[ADR 0106](0106-gitops-zero-geste-sentinelle.md)
→ le build est **déjà manuel**), le seul bénéfice de l'in-pod (autonomie « à
chaque merge » du cluster) tombe. **DÉCISION amendée : l'image de code se build
HORS cluster** (sur le poste de contrôle, `atlas`
`deploy/build-code.sh --target code`, comme la pré-image deps-base), avec un
garde-fou de fraîcheur symétrique (`check_code_freshness.py` : « le code a
changé → rebuild+push »). Le split pré-image (base lourde à egress figée / image
de code sans egress `FROM` la base) est **CONSERVÉ** — c'est lui qui rend le
build de code trivial et reproductible. Le flux GitOps (digest injecté dans
l'overlay prod → Argo CD déploie par digest) est **INCHANGÉ**. Le chantier
buildkit-in-pod (`platform/buildkit/`, rôle `platform-buildkit`, mirror
`moby/buildkit`) est retiré.

_Historique (statut initial, avant réfutation au banc) :_ Accepted (2026-07-11 ;
proposé le 2026-07-11). Supersede **partiellement**
[ADR 0106](0106-gitops-zero-geste-sentinelle.md) : l'**exécution node-side du
build de l'image de code** (0106 §1, le _timer systemd_ posé par
`platform-build-images`) devient **caduque** — la pré-image supprimant l'egress
du build de code, ce build passe **in-pod** (buildkit rootless), sans root ni
containerd du nœud. La **détection** d'écart de révision de 0106 (la Sentinelle,
CronJob API-only) est **conservée** et repointée sur le build in-pod ;
l'acheminement `main → Gitea` (0106 §6) est **conservé, hors périmètre**.
Renverse l'**objection dirimante**
d'[ADR 0095](0095-build-applicatif-evenementiel-in-cluster.md) (« le build casse
au premier `apt-get` ; Kaniko n'aide pas sur l'air-gap ») pour l'image de code,
et rétrograde le build node-side
d'[ADR 0105](0105-retrait-build-evenementiel-node-side-terminal.md) §1.a au rang
de **secours** (build de la base). Renforce l'air-gap
([ADR 0044](0044-topologie-deploiement-banc-atlas.md)). Se conforme à la
frontière `nestor` provision/install
([ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md) :
`nestor` ne déploie plus de code). Matérialise le volet §5.1 de l'audit du
2026-07-10. **Conçu, prouvé partiellement** : le split est validé contre le
Dockerfile réel ; le build in-pod (buildkit rootless, `registry:80` HTTP) reste
à prouver au banc.

## Contexte

Le build de l'image applicative d'une code-location Dagster (`citation-dagster`)
est aujourd'hui un **geste node-side** :
`nestor ansible code-location-build.yaml` (rôle `platform-build-images`) build
et pousse `registry:80/citation-dagster`, lit le digest réel, le seed l'injecte
dans l'overlay Argo CD (ADR 0105 §1.a, mécanisme terminal). C'est fiable mais
**manuel** et **node-side** — il exige le `containerd` + `buildkitd` **du nœud**
en root.

[ADR 0095](0095-build-applicatif-evenementiel-in-cluster.md) avait **écarté** le
build in-pod (Kaniko/BuildKit en pod) pour une raison qu'il qualifiait de
**dirimante** : le `Dockerfile` de citation **exige plusieurs accès Internet au
build** — `apt-get` (miroir Debian), les wheels PyPI (dont DuckDB), les
extensions DuckDB (CDN), et le **téléchargement du modèle ONNX** depuis
HuggingFace. Un pod air-gappé « casse au premier `apt-get` » ; « Kaniko n'aide
en rien sur l'air-gap ». L'objection **confondait deux choses distinctes** : le
_clone du contexte_ (air-gappable) et la _résolution des dépendances de build_
(alors non air-gappable). Tant que le Dockerfile résolvait ses dépendances **au
build**, l'objection tenait.

Or ces dépendances sont **rares et stables** (elles ne changent qu'au bump du
`uv.lock`), alors que le **code applicatif change à chaque merge**. Les recoudre
à chaque build est ce qui force l'egress. En **figeant les dépendances dans une
image de base** et en n'y ajoutant que le code, le build du code ne fait plus
**aucune** requête sortante — et l'objection de 0095 tombe **pour le code**.

[ADR 0106](0106-gitops-zero-geste-sentinelle.md) (la Sentinelle) proposait un
_timer systemd node-side_ pour rejouer ce build automatiquement, précisément
parce qu'« un pod ne peut pas reproduire l'environnement de build node-side sans
devenir un risque d'évasion ». Cette prémisse ne vaut plus pour un build **sans
réseau** : un buildkit rootless in-pod suffit. La pré-image rend donc le timer
node-side inutile pour le build de code — d'où le présent ADR.

## Décision

> **On scinde l'image de chaque code-location en deux artefacts au cycle de vie
> disjoint : une `<cl>-deps-base` (LOURDE, figée, à egress) et une image de
> **code** (`FROM <cl>-deps-base` + le code, **zéro egress**). La deps-base se
> build **hors cluster** (poste de contrôle, `docker buildx` multi-arch) et se
> pousse au registre interne ; l'image de **code** se build **in-pod** (buildkit
> rootless, aucune requête sortante). Un **garde-fou local** refuse de déployer
> du code sur une deps-base périmée.**

### 1. Le split — deux étages, cycles de vie disjoints

Confronté au `Dockerfile` réel de `citation-dagster`, le split est mécanique :
tout l'egress est contigu, la queue est déjà hermétique.

**`citation-deps-base` (figée, egress, rebuild rare).** Les seules opérations
qui touchent Internet : `apt-get install rclone ca-certificates` ;
`pip install uv` ; `uv export --frozen` + `uv pip install -r requirements.txt`
(les wheels du lock) ; `duckdb INSTALL httpfs/postgres` (CDN d'extensions) ; le
**téléchargement du modèle ONNX** (`fetch_model.py`, révision HuggingFace
figée + sha256).

**Image de code (`FROM citation-deps-base@sha256`, zéro egress).** Le reste :
`COPY src` + `uv pip install --no-deps .` (le `--no-deps` existe déjà, motivé
par l'incident grpcio-health-checking 1.81→1.82) ; `COPY citation-dbt` ;
`dbt parse` (déjà hermétique, creds S3 factices). Ceinture-bretelles :
`ENV UV_OFFLINE=1` sur cet étage rend le zéro-egress **non contournable** — la
condition dure du build in-pod.

**Invariant à préserver au split** : `fetch_model.py` importe le paquet installé
(il lit la provenance du modèle depuis `citation_dagster.model_provenance`). Le
téléchargement ONNX **reste dans la deps-base** (sinon l'image de code aurait un
egress HuggingFace), et l'ordre « paquet installé **avant** download du modèle »
est conservé. Le découpage exact du `COPY src` (présence transitoire dans la
deps-base pour `fetch_model.py`) est tranché à l'implémentation, sans changer ce
contrat.

**Une deps-base par code-location**, pas une base commune aux trois
(`citation`/`mediawatch`/`pageviews`). Les locks se recouvrent largement (~185
paquets), mais `citation` **diverge structurellement** (wheels ML, extension
DuckDB `postgres`, l'étape ONNX). Une base commune imposerait un étage
intermédiaire + un delta par-location, une indirection et une invalidation
croisée que le bénéfice (mutualiser un cache registre **local**) ne paie pas.
Une base par-location reflète 1:1 chaque `uv.lock` et rend l'invalidation
triviale.

### 2. Où builder chaque étage

| Artefact                             | Où builder                                                                                                                | Fréquence             | Egress cluster |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | --------------------- | -------------- |
| **`<cl>-deps-base`** (figée)         | **poste de contrôle** (`docker buildx` multi-arch) → push `registry:80` ; **secours** node-side (`platform-build-images`) | rare (bump `uv.lock`) | **zéro**       |
| **image de code** (`FROM deps-base`) | **in-pod** (buildkit rootless)                                                                                            | à chaque merge        | **zéro**       |

**La deps-base se build hors cluster.** C'est le seul artefact à egress ; le
builder sur le poste de contrôle (où Internet est disponible) plutôt que sur un
nœud supprime **toute** capacité d'egress de build du cluster — pas de
`NetworkPolicy` d'egress à ouvrir, même temporairement, même occasionnellement.
Le `docker buildx --platform linux/arm64,linux/amd64` produit en outre un
**index OCI multi-arch**, ce qui résout la dette latente « digest mono-arch »
(un build `nerdctl` node-side ne produit qu'un manifeste par-arch). Le push vers
le registre interne air-gappé passe par le `port-forward` du seed
(`kubectl port-forward svc/registry`) ou un NodePort. **Fallback conservé** : le
rôle node-side `platform-build-images` sait toujours builder la base (egress
borné par NetworkPolicy à ce seul moment) si le poste n'est pas disponible — on
ne retire pas la capacité, on la rétrograde en secours.

**Le code se build in-pod, sans réseau.** Une fois la deps-base disponible, le
build de code ne fait que `FROM deps-base@sha256` + `COPY src` +
`uv pip install --no-deps` + `dbt parse` — **aucune** requête sortante
(`UV_OFFLINE=1`). Un **buildkit rootless** en pod suffit : le moteur BuildKit
est déjà celui du node-side (cohérent
[ADR 0033](0033-orchestration-ansible-platform-dataops.md)), pas Kaniko (root
dans `/`, tension Pod Security, écarté par 0095 et **non rouvert**). Seul point
dur restant, de **configuration** et non de sécurité : un `buildkitd.toml`
déclarant `registry:80` en `http`/`insecure` (le pod n'hérite pas du
`hosts.toml` du nœud — piège documenté par 0095 §1.b). Le build in-pod ne tourne
jamais sur le control-plane.

### 3. Le garde-fou de cohérence de la pré-image

Le modèle « le poste pousse la base » a un risque : une **base périmée**. Un
développeur bumpe `uv.lock`, oublie de rebuilder/pousser la deps-base, et le
build de code (`FROM deps-base:<vieux-hash>`, ou une base absente) casse — ou
pire, tourne contre des dépendances obsolètes.

Un **check local** ferme ce trou, pendant du `--frozen` déjà présent au build :

- Il calcule un **digest des entrées de la base** — `uv.lock`, la liste apt, la
  révision + sha256 du modèle ONNX, les extensions DuckDB + version, le digest
  de l'image `python:3.10-slim`, et le Dockerfile de la base — soit `SHA_DEPS`.
- Le tag de la base **encode ce digest** :
  `registry:80/<cl>-deps-base:<SHA_DEPS>` (immuable, jamais `:latest` —
  [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)). Le Dockerfile
  de code fait `FROM <cl>-deps-base:<SHA_DEPS>`.
- Il vérifie via le registre (patron de `scripts/audit-image-digests.sh`,
  `docker manifest inspect`) que **cette** base existe. Sinon → **alerte
  bloquante** « les dépendances ont changé, rebuild + push la pré-image sur la
  stack avant de déployer », **exit non-zéro**.

Ce filet transforme un oubli silencieux en **échec explicite avant push**. Il
est le pendant, côté dépendances, du garde-fou lock↔pyproject (`--frozen`).

### 4. Ce qui reste hors de cet ADR

- **L'acheminement `main` GitHub → Gitea** (le « vrai trou » de l'audit §6)
  reste la responsabilité de [ADR 0106](0106-gitops-zero-geste-sentinelle.md) §6
  (SSH-git depuis un runner LAN, serveur SSH Gitea exposé en NodePort L4 —
  [ADR 0092](0092-exposition-hostport-l4.md)). Il est **orthogonal** au « où
  builder » : que le build soit in-pod ou node-side, il faut de toute façon que
  le code atteigne Gitea. Cet ADR ne le rouvre pas.
- **Le déclencheur** du build in-pod : un **Job/CronJob k8s natif** piloté par
  la Sentinelle (moule reconciler
  [ADR 0103](0103-workspace-dagster-multi-code-location-reconciler.md)), **pas**
  un runner Gitea Actions (qui rouvrirait le rejet de 0095 §3 : surface
  d'exécution + mirroring des actions dans un air-gap). La forme exacte
  (coalescing, anti-amplification) est reprise de 0106 §3, reformulée pour un
  Job in-pod, à l'implémentation.
- **Le split concret du Dockerfile** citation (deux fichiers) vit dans le dépôt
  `atlas` — cet ADR fixe la doctrine, la PR `atlas` l'exécute.

## Conséquences

- **Air-gap renforcé.** Le build de code ne sort **jamais** du cluster ; le
  build de base ne sort jamais du cluster non plus (poste de contrôle). Le
  cluster n'a plus **aucune** dérogation Internet en régime courant — un gain
  net pour un futur serveur public
  ([ADR 0044](0044-topologie-deploiement-banc-atlas.md)).
- **Le build de code redevient automatisable.** Sans besoin de root/containerd
  du nœud, la Sentinelle peut déclencher un **Job de build in-pod** — ce que le
  « mur node-side » de 0106 empêchait. Le déploiement reste par digest figé
  (Argo CD), la frontière `nestor` (provision/install, ne déploie plus de code,
  [ADR 0108](0108-isolation-par-identite-et-verbes-provision-install.md)) est
  respectée : fournir la deps-base (socle d'exécution figé) **n'est pas**
  déployer du code.
- **Multi-arch résolu.** `buildx` sur le poste produit un index OCI multi-arch —
  la dette « digest mono-arch » (0106, points à prouver) disparaît pour la base.
- **`push = auto` avec un astérisque honnête.** En régime courant (le code
  change, le lock non), le flux est automatique : push → Sentinelle → Job build
  in-pod → write-back digest → Argo CD. **Mais** si le push touche `uv.lock`, le
  garde-fou (§3) **bloque** et exige un build+push de la base depuis le poste
  **avant** que le code parte. L'automatisation zéro-geste totale n'existe pas
  pour un bump de dépendances en air-gap : c'est le prix assumé, rendu
  **visible** par le filet plutôt que silencieux.
- **Le geste base n'est pas « rare » pendant le dev.** L'historique récent
  montre ~15 changements de `uv.lock` en 30 jours (développement actif). Le «
  ~1×/mois » est le **régime cible** (post-dev : Dependabot/CVE seuls), pas le
  rythme observé. Tant que le développement est lourd, le geste de rebuild de la
  base est fréquent — à ne pas survendre.
- **À prouver au banc** (comme 0106 exigeait des preuves) : buildkit rootless
  in-pod sous Pod Security `restricted` (snapshotter `native`/`fuse`) ;
  `buildkitd.toml` HTTP/insecure pour `registry:80` ; le garde-fou de cohérence
  de bout en bout.
- **0106 devient partiellement Superseded** (son §1-exécution du code). Sa
  Sentinelle (détection) et son §6 (acheminement) sont conservés.

## Alternatives écartées

- **Garder tout node-side** (statu quo 0105/0106). Le build de code resterait
  node-side, avec root/containerd du nœud — précisément ce que la pré-image rend
  inutile, et ce qui bloque toute CI in-cluster. Ne tire aucun bénéfice de la
  scission. _Conservé uniquement comme secours_ pour la base.
- **Builder la deps-base node-side avec egress borné** (le plan initial de
  l'audit §5.1). Reproductible depuis `nestor`, aucun acteur externe — mais le
  cluster **garde** une capacité d'egress (bornée, temporaire) à
  ouvrir/fermer/auditer, contraire à l'objectif d'air-gap total, et
  **mono-arch** (la dette digest persiste). Le build sur le poste supprime
  l'egress **et** donne le multi-arch.
- **Une image de base commune aux trois code-locations.** Mutualiserait ~185
  wheels de cache, mais impose un étage intermédiaire + un delta par-location et
  une invalidation croisée, pour un gain nul dans un registre local. Une base
  par-location est plus simple et plus lisible.
- **Kaniko en pod.** Écarté par 0095 (root dans `/`, tension Pod Security face à
  un registre `runAsNonRoot`, maintenance réduite) — **non rouvert**. BuildKit
  rootless est le moteur retenu (déjà en service node-side).
- **Gitea Actions in-pod** comme déclencheur/exécuteur. Rouvrirait le rejet de
  0095 §3 (surface d'un runner + mirroring des actions `github.com` dans un
  air-gap). Un Job k8s natif piloté par la Sentinelle est cohérent avec les
  CronJobs existants (0103) et n'ajoute aucune surface.
- **Résoudre les dépendances de build à chaque build** (le modèle de 0095,
  egress Internet ciblé au build). C'est ce que la pré-image remplace : figer
  les deps rares dans une base élimine l'egress du build fréquent (le code).
