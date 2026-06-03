# 0023 — Dépôt multi-topologies (plusieurs infra déclarées, une activée)

## Contexte

Ce dépôt est un **dépôt de code ouvert, à visée généraliste** : son but est
d'attirer le plus grand nombre de contributeurs et de servir de **catalogue
d'approches d'infrastructure réutilisables**. Il ne décrit pas _une_ plateforme,
mais **plusieurs topologies** de cluster (mono-nœud pour l'onboarding,
multi-nœuds pour tester la résilience, déploiement hyperconvergé bare-metal…),
qu'un contributeur instancie selon son contexte.

Le modèle d'usage est celui de **Pulumi / Terraform workspaces** : plusieurs
configurations d'infrastructure sont **déclarées** dans le dépôt, une seule est
**activée** à l'exécution (le « stack » courant). Nuance d'honnêteté : nos
scripts restent **impératifs** (playbooks Ansible + bash), pas un moteur
déclaratif — on emprunte le _modèle d'usage_ (déclarer N, activer 1), pas la
mécanique d'un état désiré réconcilié.

Or, en l'état, le dépôt versionné porte de nombreuses **spécificités propres à
une instance** — plages IP de production, noms de nœuds, nom de l'organisation,
marques de services tiers — qui n'ont de sens que pour _un_ déploiement. Un
contributeur doit pouvoir s'approprier chaque topologie sans buter sur ces
particularités, et sans qu'elles laissent supposer que le dépôt est _sa_
plateforme à lui.

Il existe **déjà** l'amorce du bon patron, et la **preuve par l'exemple** :
`test/single-node/` et `test/multi-node/` sont **deux topologies fonctionnelles
distinctes** ; `test/multi-node/run-phases.sh` **sélectionne** sa topologie en
pointant son propre `inventory.yaml` (gitignoré) et en exportant des variables
(`CP_IP`, `CEPH_BLOCK_DEVICE`…) — un « stack select » artisanal. S'y ajoutent
les variables optionnelles de surcharge (`control_plane_ip`, `kubelet_node_ip`),
les `lookup('env', …) | default(…)` (cf.
`bootstrap/security/roles/network/tasks/ufw.yml`), et la convention `.env` /
`.env.example` (`bootstrap/security/.env-example` est déjà en **valeurs
fictives**). Cette décision **formalise** ce modèle et **généralise** le patron
de surcharge à tout le dépôt.

## Décision

Le dépôt versionné est un **catalogue de topologies génériques** (« plusieurs
infra déclarées »). Une seule est **activée** par déploiement, via une
**sélection + une config locale non versionnée** (« une active »). Les valeurs
réelles d'une instance vivent **hors du dépôt versionné**.

### 0. Topologies — réalisées vs en ligne de mire

Distinguer honnêtement ce qui est **réalisé et validé** de ce qui est **visé**
(ne pas documenter une intention comme un acquis) :

| Topologie                               | Statut                       | Où                                                                                                |
| --------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------- |
| Mono-nœud (onboarding, sans Ceph)       | **réalisée**                 | [`test/single-node/`](../../test/single-node/)                                                    |
| Multi-nœuds 3 VM (Ceph, réseau privé)   | **réalisée** (validée banc)  | [`test/multi-node/`](../../test/multi-node/)                                                      |
| Bare-metal 4 nœuds hyperconvergé        | **réalisée** (cible de prod) | `bootstrap/` + `storage/ceph/`                                                                    |
| Réseau local Docker (dev zéro-matériel) | **en ligne de mire**         | — (à créer)                                                                                       |
| HA multi-control-plane                  | **en ligne de mire**         | contredit l'[ADR 0002](0002-control-plane-unique-avec-endpoint.md) (SPOF assumé) — chantier dédié |

Le banc multi-node (`192.168.67.0/24`) est une **topologie à part entière**, pas
un appendice de test. L'organisation du dépôt **par profils de topologie** (un
inventaire-exemple + une sélection par topologie) est un **chantier séparé** ;
cet ADR acte la vision, pas la restructuration.

### 1. Règle de généricité (s'applique à TOUT le dépôt, ADR compris)

Tout contenu produit dans ce dépôt — code, manifestes, scripts **et prose
(documentation, ADR, RUNBOOK)** — emploie des **valeurs d'exemple génériques**,
jamais les valeurs réelles d'un déploiement particulier. **Le présent ADR se
soumet à sa propre règle.**

Quatre catégories sont concernées :

1. **IP / plages réseau** de production → valeur d'exemple (p. ex. réseau privé
   `10.0.0.0/22`).
2. **Noms de nœuds / hôtes** → génériques (`cp1`, `node1`…`node4`,
   `site-distant`).
3. **Noms d'organisation / de sites** → « l'organisation » / `example-org`.
4. **Marques de services tiers** (sources de données, backends, fournisseurs
   matériel) → catégories génériques (« source de données ouverte », « backend
   d'authentification », « serveur lame »).

### 2. Prose : valeur d'exemple **cohérente**, pas formulation vague

Dans la prose, on n'« injecte » pas de variable. On **remplace par une
valeur-exemple concrète et stable** (réutilisée à l'identique partout), pas par
une tournure abstraite : un ADR doit rester lisible et chiffré (un `/22` vs un
`/24` change un raisonnement). Le **contexte qui fonde une décision est
conservé** (« 4 nœuds », « EC 2+1 », « cluster non-HA ») ; seule l'**identité**
(qui ne sert qu'à l'auteur) est génériquée.

### 3. Mécanique : config locale non versionnée → `.example` versionné

Les spécificités réelles sont injectées par un **fichier de configuration local
non versionné** qui surcharge un **`.example` versionné** aux valeurs
génériques. On **réutilise les patrons existants** (rien de neuf) :

- inventaire Ansible réel **gitignoré**, doublé d'un `*.example` versionné ;
- surcharges `lookup('env', 'X') | default('<valeur-exemple>')` — le **défaut
  devient générique** (il était la valeur de prod) ;
- variables optionnelles de rôle (`control_plane_ip`…) déjà en place ;
- **sélection de topologie** (« activer un stack ») : pointer l'inventaire/les
  variables de la topologie voulue, comme `run-phases.sh` le fait pour le banc.

### 4. Exceptions explicites

- **Le banc Vagrant (`192.168.67.0/24`) reste tel quel** : c'est un exemple
  **fonctionnel, public et reproductible**, pas l'infrastructure de l'auteur.
- **L'honnêteté des validations banc est préservée** : `test/RESULTS.md`
  consigne des exécutions réelles (qui utilisent littéralement `192.168.67.x`) ;
  on ne **réécrit pas** cet historique. Seules les références à la **production
  réelle** sont génériquées.

### 5. Séquencement : règle d'abord, migration ensuite

Cet ADR **acte la règle** ; il l'inscrit dans
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) (contributeurs humains) et dans
[`CLAUDE.md`](../../CLAUDE.md) (agent). La **mise en conformité de l'existant**
(~25 fichiers : plages IP, hostnames, nom d'organisation, marques) est un
**chantier séparé et planifié**, mené au fil de l'eau — pas un méga-diff unique.

## Statut

Accepted (2026-06-03).

## Conséquences

**Bénéfices.**

- **Réutilisabilité** : un contributeur clone un modèle générique et le
  spécialise via son fichier local, sans hériter de l'infra de l'auteur.
- **Pas de fuite de topologie** de production dans un dépôt public.
- **Patron unifié** : la surcharge locale/`.example`, déjà présente par
  endroits, devient la règle partout — cohérence et moins de surprises.
- **L'ADR se soumet à sa règle** : la documentation reste un exemple
  réutilisable, pas le journal privé d'un déploiement.

**Prix à payer.**

- **Chantier de migration** réel (occurrences réparties dans code _et_ prose,
  ADR historiques compris) — étalé, donc cohabitation temporaire valeurs réelles
  / génériques le temps de converger.
- **Discipline rédactionnelle** : tout nouveau contenu doit penser « valeur
  d'exemple » d'emblée (d'où l'inscription dans CONTRIBUTING + CLAUDE).
- **Double source** pour l'auteur : il maintient son fichier local en plus du
  `.example` versionné.

**Garde-fous.**

- **`.gitignore`** couvre les fichiers de config locaux (réels) ; seuls les
  `*.example` génériques sont versionnés.
- **Défauts génériques** : aucune valeur de production ne subsiste comme
  **défaut** dans un `lookup … | default(…)` versionné.
- **Banc conservé** et **Runs non réécrits** (cf. Décision §4) : la règle ne
  dégrade pas la traçabilité honnête des validations.
- **CONTRIBUTING + CLAUDE** rappellent la règle à chaque contribution (humaine
  ou agent).

## Alternatives écartées

**Formulation vague dans la prose** (« le réseau privé du cluster » sans
valeur). Écarté : appauvrit les ADR, dont la valeur tient au raisonnement
**chiffré** ; on préfère une **valeur-exemple concrète**.

**Tout garder réel, dépôt « privé de fait ».** Écarté : contredit la visée
ouverte/généraliste ; expose la topologie de production ; décourage la
réutilisation.

**Templating intégral** (variabiliser jusque dans la prose des ADR). Écarté :
illisible, sur-ingénierie ; la prose prend des **valeurs-exemple**, pas des
placeholders.

**Migration immédiate en un bloc.** Écarté au profit du séquencement « règle
d'abord » : un méga-diff sur ~25 fichiers (code + ADR historiques) serait
iningérable et risqué ; la conformité se fait au fil de l'eau.
