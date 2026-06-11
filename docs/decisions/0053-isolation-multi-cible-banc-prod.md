# 0053 — Isolation multi-cible : banc Lima et prod sur le même poste

## Contexte

Le dépôt est un **catalogue de topologies** (« plusieurs infra déclarées, une
activée », [ADR 0023](0023-plateforme-exemple-generique.md)). En pratique, un
même poste de contrôle peut héberger **deux cibles vivantes simultanément** : un
banc Lima monté et opérationnel (topologie multi-nœuds, VMs `cp1`/`node1`…) et
l'intention d'opérer une prod réelle (4 serveurs lame). Rien dans le dépôt ne
proscrit cette coexistence — elle est même normale : on garde un banc up pour
itérer pendant qu'on prépare ou audite la prod. Or les deux cibles sont **plus
proches que ne le suggère leur isolation par fichier**, et certains chemins
visent la cible **ambiante** du shell plutôt qu'une cible **nommée**.

L'isolation **par fichier** est acquise, mais c'est tout ce qu'il y a :

- **Banc** = kubeconfig `test/lima/.work/kubeconfig` + inventaire
  `test/lima/.work/inventory.yaml` (générés, gitignorés) ; SSH user `lima` via
  `-F ~/.lima/<vm>/ssh.config`.
- **Prod** = `~/.kube/config` (ou fichier opérateur) + `bootstrap/hosts.yaml`
  (gitignoré, copié de `hosts.example.yaml`) ; SSH user `debian`.

Quatre fragilités transforment cette isolation par fichier en **faux sentiment
de sûreté** dès que les deux cibles coexistent :

1. **kubectl nu = cible ambiante implicite.** Le banc est sûr —
   `test/lima/run-phases.sh` force **toujours** `KUBECONFIG=.work/kubeconfig` et
   `kubectl --kubeconfig …`, il ne déborde jamais. Mais `bootstrap/state.sh`
   (`kubectl_q`/`kubectl_ready`, couches Cilium/Ceph/StorageClass) et
   `bootstrap/cni.sh` appellent **kubectl nu**, sans `--kubeconfig` : ils lisent
   le `KUBECONFIG` **ambiant** du shell. En prod, c'est l'intention. Mais si le
   shell porte le kubeconfig **du banc**, `state.sh` audite le **banc** en
   croyant auditer la prod — `2>/dev/null` rend l'erreur muette, l'en-tête
   affiche l'hôte prod. **Faux verdict de conformité silencieux.**
2. **Contextes kubeconfig homonymes.** Les deux clusters kubeadm naissent avec
   les **mêmes** noms par défaut (cluster `kubernetes`, user `kubernetes-admin`,
   contexte `kubernetes-admin@kubernetes`). Le banc **sait** renommer
   (`fetch_kubeconfig_node` prend un argument `ctx` optionnel) mais l'appel de
   `phase_bootstrap` ne le passe pas ; la prod copie `admin.conf` verbatim. Une
   fusion `KUBECONFIG=banc:prod` **écrase** alors les deux contextes du même nom
   — `use-context` ne désambiguïse rien, on pilote le mauvais cluster sans le
   voir.
3. **Inventaires structurellement indiscernables.** Banc et prod déclarent les
   **mêmes** groupes (`cloud`/`control`/`workers`) et les **mêmes** noms d'hôtes
   (`cp1`/`node1`…) ; seule diffère la valeur interne `ansible_user` (`lima` vs
   `debian`). Un playbook n'a **aucun moyen** de savoir contre quelle topologie
   il tourne : la séparation tient à la **discipline d'invocation** (`-i …`),
   sans garde-fou. Un mauvais `-i` rejoue un hardening prod sur les VMs jetables
   (faux drift résiduel) ou, pire, mute les serveurs réels.
4. **Le helper `env.sh` devine la cible.** `test/lima/env.sh` auto-détecte
   `lima` dès qu'une VM Lima existe — un fait **orthogonal à l'intention**. Un
   opérateur qui prépare une commande prod se voit proposer le banc ; son
   `eval "$(env.sh export)"` pose `KUBECONFIG=.work/kubeconfig` dans le shell —
   c'est précisément le vecteur qui **arme** la cible ambiante du banc pour le
   point 1.

Le mode de défaillance commun n'est pas une panne bruyante : c'est un **faux
résultat silencieux** — un audit « vert » de la prod qui a en réalité lu le
banc, ou une mutation appliquée à la mauvaise topologie sans erreur. C'est
exactement la classe de preuve invalide que proscrit
[ADR 0052](0052-reproductibilite-des-resultats.md) : **un audit de prod n'a de
valeur que s'il a prouvablement visé la prod.** L'isolation par fichier est
nécessaire mais pas suffisante ; il manque la règle qui **nomme la cible** au
lieu de la déduire de l'état du shell.

## Décision

**En contexte multi-cible, toute commande nomme explicitement sa cible. La cible
n'est jamais déduite de l'état ambiant du shell ni d'un fait d'environnement
orthogonal à l'intention.** L'isolation par fichier (kubeconfig + inventaire
gitignorés) est conservée ; on lui adjoint une **désignation explicite** rendue
opposable côté kubectl, contexte, inventaire et helper. Quatre règles.

### (a) Règle d'or — kubectl nu interdit en multi-cible

Toute invocation kubectl désigne sa cible : **`--kubeconfig <fichier>`
explicite, OU un contexte nommé** (`--context …` / `use-context`) **sur un
kubeconfig dont les contextes sont distincts** (cf. (b)). **Aucun `kubectl` nu**
dans un chemin susceptible de tourner sur le poste partagé. Conséquence directe
sur les deux scripts à kubectl nu (`bootstrap/state.sh`, `bootstrap/cni.sh`) :
tant qu'ils n'ont pas de cible désignée, ils **refusent d'émettre un verdict**
plutôt que d'auditer une cible ambiante non confirmée. La désignation passe par
une cible **explicitement nommée** (variable d'intention) **comparée à
l'identité réelle du cluster** — l'empreinte du CA du contexte courant, ou à
défaut son `server:`, identifiant **stable et disjoint** banc/prod, insensible à
l'homonymie kubeadm. À cible absente ou divergente, les couches kubectl passent
en `skip` bruyant (message « cible non confirmée »), **jamais** en faux `ok`.
C'est l'inverse du `2>/dev/null` actuel : on rend l'erreur de cible
**bruyante**, pas muette. L'étiquette d'intention vit en **config locale
gitignorée** (empreinte enregistrée une fois), jamais en défaut versionné
([ADR 0023](0023-plateforme-exemple-generique.md)).

### (b) Contextes kubeconfig renommés par cible

On tue l'homonymie **à la source**, des deux côtés, par des noms **génériques
distincts** : `cluster-banc` (banc) et `cluster-prod` (prod) — étiquettes
d'exemple, pas une valeur de déploiement.

- **Banc** : armer le rename **déjà codé** — `phase_bootstrap` (et la cible
  `kubeconfig`) passe **toujours** l'argument `ctx` à `fetch_kubeconfig_node`,
  valeur **dérivée du profil** (jamais codée en dur,
  [ADR 0046](0046-corriger-le-code-pas-l-etat.md)). Le contexte banc naît
  `cluster-banc`, jamais `kubernetes-admin@kubernetes`.
- **Prod** : nommer le cluster au `kubeadm init` (`clusterName` dérivé d'une var
  d'inventaire générique surchargeable) — voie canonique kubeadm, le contexte
  naît `kubernetes-admin@cluster-prod`. Pour un parc **déjà installé** où l'init
  ne sera pas rejoué, une tâche `rename-context` **idempotente** (post-copie de
  `admin.conf`, rejeu `changed=0`,
  [ADR 0052](0052-reproductibilite-des-resultats.md) règle 2) corrige
  l'existant. Le RUNBOOK importe alors le contexte par **fusion `--flatten` +
  `use-context cluster-prod`** explicite, jamais par écrasement de
  `~/.kube/config`.

Résultat : une fusion `KUBECONFIG=banc:prod` ne collisionne plus ; le
`current-context` et l'empreinte de (a) deviennent **lisibles à l'œil**. (À
répercuter sur le spike Cluster Mesh
[ADR 0027](0027-bootstrap-parametre-multi-cluster.md) qui pose plusieurs
clusters.)

### (c) Inventaires séparés + garde-fou anti-mauvais-inventaire

On conserve les deux inventaires distincts, et on rend la **mauvaise cible
Ansible bloquante avant toute mutation** par un marqueur déclaratif
`target_kind` porté par chaque inventaire (au niveau du groupe `cloud`, donc
hérité par tous les hôtes) : `target_kind: prod` dans `hosts.example.yaml`,
`target_kind: lima` émis par le générateur d'inventaire du banc. Une **assertion
native** (module `assert`, `run_once` + `delegate_to: localhost`) compare
`target_kind` à l'intention de l'invocation (`EXPECTED_TARGET_KIND`, défaut
**`prod`** — une invocation nue du RUNBOOK exige donc un inventaire prod ; le
banc déclare `lima`). L'assertion vit dans un rôle **déjà importé en `pre_tasks`
par quasiment tous les playbooks** (`audit-log`), donc couverture quasi
automatique, **avant tout `become`/toute mutation distante**. Un inventaire
passé par erreur fait **échouer immédiatement, zéro task mutante**, avec un
message nommant les deux inventaires. Marqueur `prod`/`lima` = générique,
conforme [ADR 0023](0023-plateforme-exemple-generique.md) ; transforme un
faux-résultat silencieux en échec bruyant reproductible
([ADR 0052](0052-reproductibilite-des-resultats.md)).

### (d) `env.sh` exige une cible explicite

Le helper **cesse de deviner**. La cible n'est auto-détectée **que si une seule
est plausible** (uniquement des VMs Lima → `lima` ; uniquement
`bootstrap/hosts.yaml` → `prod`) ; **dès que les deux coexistent, il refuse**
(`exit 2`) et exige `lima|prod` explicite. L'ergonomie du poste mono-cible est
préservée ; la friction est **ciblée précisément sur le cas dangereux**.
Symétriquement, `export` (qui pose `KUBECONFIG` du banc dans le shell — le
vecteur d'armement de (a)) exige `lima` explicite dès que la prod coexiste,
**annonce sur stderr** ce qu'il charge, et pose un marqueur d'intention lisible
par le garde-fou de (a).

Ces quatre règles sont **opposables** : une revue ou la CI peut refuser un
résultat produit par un chemin à cible ambiante (kubectl nu, inventaire non
marqué, export deviné). Elles ne **bypassent** aucun garde-fou et n'introduisent
**aucune valeur de déploiement versionnée** : étiquettes (`cluster-banc`,
`cluster-prod`, `prod`/`lima`) et empreintes vivent en défaut générique ou en
config locale gitignorée ([ADR 0023](0023-plateforme-exemple-generique.md)).

## Statut

Accepted.

## Conséquences

- **Gain principal** : un audit de prod ne peut plus « réussir » en ayant lu le
  banc, ni une mutation Ansible s'appliquer à la mauvaise topologie sans erreur.
  Le faux-résultat-silencieux devient un **échec bruyant** ou un **`skip`
  explicite** — la preuve porte prouvablement sur la cible annoncée
  ([ADR 0052](0052-reproductibilite-des-resultats.md)).
- **Coût** : faible et **entièrement natif** (bash/kubectl pur, module Ansible
  `assert`, rename-context kubeadm), zéro dépendance nouvelle. Friction
  ergonomique assumée et **ciblée** : l'audit cluster de `state.sh` devient
  opt-in (cible désignée), `env.sh` exige `lima|prod` quand les deux coexistent,
  un `hosts.yaml` déjà copié doit recevoir son `target_kind: prod`. Idempotence
  préservée (`rename-context` rejouable `changed=0`,
  [ADR 0052](0052-reproductibilite-des-resultats.md)).
- **Migration non rétroactive** : les kubeconfig/inventaires déjà générés
  gardent l'ancien nom. Côté banc, c'est gratuit (régénérable à volonté) ; côté
  prod, la variante `rename-context` corrige un parc en place, et un
  `hosts.yaml` pré-existant sans marqueur **refuse de tourner** (fail-safe :
  message « ajouter `target_kind: prod` ») — action de migration ponctuelle à
  documenter au RUNBOOK.
- **Garde-fous par signal/refus, pas verrou universel** : ces règles ferment le
  **chemin par défaut, silencieux et facile** vers l'accident. Elles ne
  protègent **pas** un `kubectl delete` tapé à la main dans un shell mal pointé,
  ni un opérateur qui force sciemment `EXPECTED_TARGET_KIND=lima` sur une
  invocation prod : c'est alors un **opt-in volontaire et visible**, pas une
  distraction. On supprime l'accident par inadvertance, pas la liberté de
  l'opérateur déterminé (esprit [ADR 0046](0046-corriger-le-code-pas-l-etat.md)
  : corriger le code/chemin, pas contraindre par un wrapper coercitif fragile).
- **Couverture (c) = présence du rôle** : un playbook qui n'importe pas
  `audit-log` en `pre_tasks` n'est pas protégé — à auditer (lint/test bats
  listant les playbooks sans `audit-log`) et soit y ajouter l'import, soit y
  dupliquer l'`assert`.
- **Détection (a) par identité de cluster** : si le CA est référencé en fichier
  (non `…-data` inline), l'empreinte est vide → fallback sur le `server:`
  endpoint (banc `127.0.0.1:<port>` vs prod VIP/hostname réel, disjoints ici).

## Alternatives écartées

**Wrapper coercitif liant nom-de-contexte ↔ nom-d'hôte** (refuser de tourner si
le contexte ne matche pas l'hôte ciblé). Écarté : plus sûr en apparence, mais
**intrusif et fragile** (couplage rigide, casse au moindre renommage), contraire
à l'esprit « signal + source correcte » plutôt que garde-fou bloquant
([ADR 0046](0046-corriger-le-code-pas-l-etat.md)).

**Conserver l'auto-détection `env.sh` en tranchant `lima` par défaut.** Écarté :
c'est précisément la **devinette** qui arme l'accident ; le cas « coexistence »
est l'ambiguïté à **ne pas trancher** à la place de l'opérateur.

**S'en remettre à la seule isolation par fichier + discipline d'invocation**
(statu quo). Écarté : nécessaire mais insuffisant — l'homonymie des contextes et
le kubectl nu rendent l'erreur **invisible**, donc non détectable à la revue,
donc non reproductible comme preuve
([ADR 0052](0052-reproductibilite-des-resultats.md)).
