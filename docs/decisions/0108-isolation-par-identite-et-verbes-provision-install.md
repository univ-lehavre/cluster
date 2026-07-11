# 0108 — Isolation par identité d'instance et séparation des verbes provisionner / installer

## Statut

Proposed (2026-07-11). **Premier ADR d'implémentation** du volet §4 de
[ADR 0107](0107-adaptativite-materielle-premisse-cultures.md) (adaptativité
matérielle), qui pose que « il n'y a plus de prod ni de banc — seulement des
**instances** sur des **classes**, isolées par leur **identité** ». Il exécute
ce principe dans `nestor` et dans la chaîne Ansible. Amende
[ADR 0053](0053-isolation-multi-cible-banc-prod.md) (garde de catégorie →
identité), [ADR 0090](0090-nestor-pilote-la-prod.md) (lecture seule → mutation
encadrée), [ADR 0065](0065-variables-env-intention-vs-etat.md) (l'échappatoire
`KUBECONFIG` devient une preuve vérifiée),
[ADR 0084](0084-sondes-de-lecture-gatees-par-target-kind.md) (les sondes se
gatent sur le terrain, non la criticité),
[ADR 0099](0099-axes-du-modele-topologie.md) (l'axe `target_kind` disparaît) et
[ADR 0102](0102-catalogue-topologies-v2-topo-source-unique.md) (l'ancrage du
kubeconfig par l'activation). Il matérialise dans la CLI la frontière «
décrire/converger » déjà posée par
[ADR 0056](0056-modele-declaratif-topologies.md) §5/§7.

## Contexte

`nestor` sépare aujourd'hui ses cibles par une **catégorie** :
`target_kind ∈ {prod, bench}`, la « criticité » (banc jetable vs parc réel), qui
pilote la garde d'isolation. Deux défauts, l'un de sûreté, l'autre de clarté,
motivent cet ADR.

**La garde par catégorie ne prouve pas la bonne chose.** Deux instances d'une
même classe partagent les mêmes groupes d'inventaire, les mêmes noms d'hôtes
(`cp1`, `node1`) et la même catégorie ; seul leur **contenu** (adresses réelles)
diffère. Une garde qui vérifie « c'est bien du parc critique » laisse donc
passer une action destinée à l'instance A vers l'instance B de la même classe.
C'est la faille du 2026-06-16 : un montage visant une instance jetable a, par le
chemin SSH (inventaire Ansible, disjoint du `KUBECONFIG`), reconfiguré
`containerd` sur l'instance massive en service. Un correctif ponctuel a fermé le
trou immédiat (garde d'inventaire `classify_inventory_target`, pre-tasks d'audit
sur les plays concernés), mais la garde reste **fondée sur la catégorie**, et
une cible implicite subsiste : exporter un `KUBECONFIG` — n'importe lequel —
désarme la garde du chemin `kubectl`
([ADR 0065](0065-variables-env-intention-vs-etat.md)).

**Deux verbes opposés portent le même nom.** La commande `up` « monte tout » :
elle **provisionne** le substrat (crée les machines) _et_ **installe** la
plateforme (OS, k8s, couches). Or ces deux gestes ont des propriétés inverses —
provisionner est destructif, coûteux, rare ; installer est idempotent, rejouable
(`changed=0`). Les fondre dans une seule commande masque la propriété «
destructif » et empêche d'exprimer l'invariant qui compte : **on doit pouvoir
installer (re-converger) sans re-provisionner**. Cet invariant est déjà
techniquement satisfait — le moteur saute la phase de provisionnement quand les
machines existent — mais il l'est **implicitement**, dérivé d'une sonde d'état,
jamais garanti par un verbe ni visible pour l'opérateur. La frontière «
décrire/vérifier/mesurer » vs « converger » est pourtant nommée depuis
[ADR 0056](0056-modele-declaratif-topologies.md) §5 ; elle n'a simplement jamais
été portée dans la CLI.

Ces deux défauts ont une même racine : la **catégorie** (`target_kind`) sert de
pivot là où seule l'**identité** de l'instance et la **classe** de son matériel
devraient décider. `nestor` porte déjà l'identité (`stack_id`, le nom de fichier
de topologie — [ADR 0102](0102-catalogue-topologies-v2-topo-source-unique.md)
volet B) et la classe (`catalog.terrain ∈ {local, cloud, baremetal}`) ; elles
sont inexploitées comme pivots.

## Décision

### 1. L'isolation se fonde sur l'identité d'instance, non sur la catégorie

Le marqueur `target_kind` **disparaît** — du modèle, du parsing, des
inventaires, des sondes et des gardes. Aucune survivance descriptive : il n'y a
plus de « criticité » déclarée, seulement une instance nommée (`stack_id`) sur
une classe (`terrain`).

Une **garde d'identité unique** remplace les trois gardes actuelles
(`_assert_bench_target`, `assert_prod_target`, `_assert_inventory_safe`). Avant
toute action mutante, elle prouve **positivement** que la cible réellement
atteinte **est** l'instance `stack_id` visée, sur les **deux chemins disjoints**
:

- **Chemin `kubectl`** : le contexte du kubeconfig courant porte le nom
  `stack_id` (estampillé à l'ancrage, §3), son endpoint concorde avec celui que
  la topologie de `stack_id` déclare, **et l'API de cet endpoint répond avec les
  nœuds attendus Ready**. Cette dernière condition est essentielle : la preuve
  porte sur ce que le cluster **répond**, jamais sur la seule chaîne d'endpoint
  qu'on vient d'écrire — sans quoi la garde validerait une identité qu'elle a
  elle-même fabriquée.
- **Chemin inventaire/SSH** : l'inventaire porte `stack_id` (au lieu de
  `target_kind`), et il doit égaler l'identité visée avant tout
  `ansible-runner`. Le rôle Ansible d'audit fait la même comparaison côté
  playbook (défense en profondeur).

**L'échappatoire `KUBECONFIG` est abolie comme laissez-passer**
([ADR 0065](0065-variables-env-intention-vs-etat.md)) : un `KUBECONFIG` exporté
n'exempte plus de la garde, il est **comparé** (contexte et endpoint doivent
concorder avec `stack_id`). Plus aucune cible implicite ne subsiste — c'est la
fermeture structurelle de la faille du 2026-06-16, au-delà du correctif
ponctuel.

Cas d'une instance **jamais montée** (`provision` d'un substrat inexistant) :
aucun kubeconfig n'est rapatriable, mais l'inventaire ne comporte aucun hôte
distant non prouvé — la garde autorise l'action sur la **seule preuve
d'inventaire**, sans rouvrir d'échappatoire.

### 2. `nestor` mute l'instance nommée, sous confirmation

[ADR 0090](0090-nestor-pilote-la-prod.md) réservait à `nestor` la **lecture** de
l'état réel et laissait la **mutation** aux playbooks. Cette réserve est
**levée** : `nestor` mute l'instance explicitement nommée
(`up`/`install`/`down`/`remove`/…), sous la garde d'identité (§1) **et** une
confirmation explicite affichant l'endpoint et les nœuds vus.
`--yes`/`--no-input` saute la **question**, jamais la **preuve d'identité** :
une identité discordante refuse l'action même en mode non interactif. La
mutation ne s'exerce que sur l'instance nommée, jamais sur une cible implicite —
la sûreté est renforcée, non assouplie.

### 3. L'activation d'une instance rapatrie son kubeconfig

Activer une instance (`stack select`) **rapatrie systématiquement** son
kubeconfig depuis le nœud de contrôle de cette instance, par le transport de son
inventaire (local ou SSH selon la classe), et l'écrit sous
`.kubeconfigs/<stack_id>.config` avec son contexte estampillé `stack_id` et son
endpoint réécrit vers la valeur joignable. Le kubeconfig cesse d'être un fichier
posé à la main ou déclaré dans la topologie : c'est un **artefact produit par
l'activation**, source unique. Fraîchement rapatrié de la cible nommée, il
**est** la preuve d'identité la plus forte pour la garde (§1).

L'activation devient de ce fait **bloquante** (elle sonde le réseau) : le
contrat « activation instantanée » est abandonné. Toute sortie humaine passe par
le canal d'erreur ; seule la ligne d'export reste sur la sortie standard, de
sorte que l'usage `eval` demeure. Un mode de secours permet d'activer sans
rapatrier lorsque le réseau n'est pas disponible ou souhaité (implicite en mode
non interactif).

### 4. Deux verbes séparés : provisionner et installer

La commande unique qui « monte tout » est scindée en deux verbes aux propriétés
opposées, matérialisant la frontière
[ADR 0056](0056-modele-declaratif-topologies.md) §5 dans la CLI :

| Verbe            | Rôle                                | Propriété                                | Propriétaire du substrat              |
| ---------------- | ----------------------------------- | ---------------------------------------- | ------------------------------------- |
| **provisionner** | crée le substrat (machines)         | destructif, coûteux, rare — **confirmé** | outil de provisionnement, ou personne |
| **installer**    | OS + k8s/k3s + plateforme (Ansible) | idempotent, rejouable (`changed=0`)      | Ansible (nestor orchestre)            |

**Invariant cardinal, désormais explicite** : installer ne touche **jamais** au
substrat. Re-converger une instance ne peut pas la re-provisionner. Ce n'est
plus un effet de bord d'une sonde d'état, mais une propriété portée par le
verbe.

Le provisionnement se **gate sur la classe** (`terrain`), non sur la catégorie
disparue : `local` provisionne des machines (l'outil possède la ressource) ;
`cloud` la déléguera à l'IaC ([ADR 0032](0032-opentofu-provisioning-cloud.md),
non implémenté — sur besoin matériel réel) ; `baremetal` est un **no-op** (les
machines préexistent, simple pré-vol). Ce choix respecte
[ADR 0056](0056-modele-declaratif-topologies.md) §7 : moteur à état seulement là
où l'outil possède réellement la ressource ; ailleurs, convergence sans état.

Lien avec l'identité (§1) : **provisionner crée** une identité `stack_id` (fait
exister l'instance) ; **installer et muter agissent sur** une identité
existante. La garde d'identité s'applique à l'installation et à la mutation ; le
provisionnement, qui fait naître l'instance, se confirme explicitement (acte
destructif).

## Conséquences

- **La faille du 2026-06-16 est fermée structurellement.** Ni un `KUBECONFIG`
  exporté, ni un inventaire d'une autre instance de la même classe ne peuvent
  plus faire agir `nestor` sur la mauvaise cible : la preuve est une identité
  concordante, vérifiée par ce que le cluster répond, sur les deux chemins.

- **`target_kind` disparaît intégralement** — modèle, parsing, scaffold,
  templates d'inventaire, sondes, gardes, rôle d'audit, et les ADR qui le
  posaient. Les comportements qui en dépendaient à tort sont **re-gatés sur le
  bon axe** : le transport (local/SSH) et la présence du provisionnement se
  dérivent du `terrain` ; les garde-fous de parc jetable (image d'essai,
  interdiction des épreuves offensives) se dérivent d'une propriété de la
  classe, jamais de « ce n'est pas la prod ».

- **Une invariance vérifiée remplace une discipline.** Un garde-fou statique
  (intégré à la CI) refuse tout play `hosts: cloud` dépourvu du pré-task d'audit
  — l'isolation du chemin SSH ne dépend plus d'une vigilance par-play.

- **Migration sans régression pour l'instance massive.** Le chemin de
  rapatriement SSH existe déjà ; l'inventaire des instances sur nœuds
  préexistants est **dérivé, jamais versionné**, donc le changement de marqueur
  est automatique ; le kubeconfig de l'instance massive est réécrit avec son
  identité au premier ré-activation. Une tolérance de transition bornée évite
  tout refus le temps de la première ré-activation. Le comportement de la classe
  massive est préservé à l'octet.

- **Contrainte de modèle.** Une instance sur nœuds préexistants doit déclarer un
  endpoint de contrôle **concret** : le placeholder générique ne doit jamais
  atteindre une instance réelle, sous peine de neutraliser le second cran de la
  preuve d'endpoint. `nestor` avertit lorsqu'une topologie sur nœuds
  préexistants conserve le placeholder.

- **Le champ de kubeconfig déclaré et le nom de contexte conventionnel
  deviennent redondants** avec l'identité : ils cessent d'être lus (l'activation
  ancre le kubeconfig, l'identité prouve la cible). Retirés du modèle sans
  rupture, l'ancien champ toléré-ignoré le temps de la transition.

- **Prix à payer, assumé.** L'activation devient bloquante (sonde réseau) ; un
  nœud de contrôle injoignable retarde ou empêche l'activation nominale — le
  mode de secours et un message clair l'atténuent. La séparation des verbes
  impose de découpler le provisionnement du bootstrap du socle (aujourd'hui
  traités comme un même bloc amont pour des raisons de transport, non de nature)
  : c'est un refactor réel de la CLI, contenu par le fait que le mécanisme de «
  ne pas re-provisionner » existe déjà.

- **Ce qui reste hors de cet ADR.** Le bras de provisionnement cloud (IaC,
  [ADR 0032](0032-opentofu-provisioning-cloud.md)) n'est pas implémenté ici : il
  s'active le jour où une machine cloud existe. Le protocole de provisionnement
  à trois gestes (créer / écrire l'inventaire / fournir les faits) est cadré ;
  sa généralisation au-delà de la classe locale suit les besoins matériels
  réels, comme le prescrit
  [ADR 0107](0107-adaptativite-materielle-premisse-cultures.md).

## Alternatives écartées

- **Renforcer la garde par catégorie** (ajouter des vérifications au marqueur
  `target_kind`). Écarté : la catégorie ne peut pas discriminer deux instances
  d'une même classe — le défaut est de nature, pas de degré. Seule l'identité
  distingue.

- **Conserver l'échappatoire `KUBECONFIG` comme intention explicite**
  ([ADR 0065](0065-variables-env-intention-vs-etat.md) inchangé). Écarté : c'est
  précisément la dernière cible implicite. « J'assume » ne doit pas suspendre la
  preuve ; l'intention explicite est elle-même vérifiée (l'endpoint exporté doit
  concorder avec l'instance nommée).

- **Un simple drapeau `--no-provision`** au lieu de deux verbes. Écarté : un
  drapeau ne rend pas visibles les propriétés opposées (destructif-à-confirmer
  vs rejouable). L'audit du 2026-07-10 (volet A.4) demande « deux commandes aux
  propriétés opposées », pas une option d'une commande fourre-tout.

- **Faire de l'activation un poseur de chemin non bloquant** (rapatriement
  délégué à la commande de lecture, comme aujourd'hui). Écarté : le kubeconfig
  resterait un fichier potentiellement périmé ou étranger, et la garde
  s'appuierait sur une preuve faible. L'activation qui rapatrie fait du
  kubeconfig frais la preuve d'identité — au prix, accepté, d'une activation
  bloquante.
