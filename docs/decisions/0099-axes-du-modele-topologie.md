# 0099 — Les axes du modèle de topologie : terrain, criticité, exposition, archi

## Statut

Proposed (2026-06-30)

Cadre le vocabulaire du **catalogue de topologies**
([ADR 0023](0023-plateforme-exemple-generique.md) : plusieurs infra déclarées,
une activée) en explicitant ses **axes orthogonaux**. Clarifie
[0053](0053-isolation-multi-cible-banc-prod.md) (la garde `target_kind`) et
[0030](0030-nomenclature-bancs-topologies.md) (nomenclature bancs/topologies) :
`target_kind` ne porte **qu'un** des axes (la sûreté), pas la technologie.
S'articule avec [0092](0092-exposition-hostport-l4.md) (modes d'exposition) et
[0097](0097-moteur-chemin-python-bash-artefacts.md) (le moteur dérive tout de la
topologie). Valeurs d'exemple génériques
([ADR 0023](0023-plateforme-exemple-generique.md)) :
`local`/`cloud`/`baremetal`, `bench`/`prod`, `dirqual`, `edge-public`.

## Contexte

Le dépôt est un **catalogue-vitrine** : il démontre ce que l'infrastructure sait
faire en déclarant **plusieurs topologies** (banc local, prod bare-metal, edge
public cloud…), une seule activée par déploiement. Une question récurrente — «
comment nomme-t-on la cible d'un montage ? » — a fait surface plusieurs pistes
(`lima`/`prod`, `baremetal`/`lima`, `bench`/`prod`) qui **se contredisent**
parce qu'elles mélangent des dimensions distinctes dans **une seule clé**.

La cause : `target_kind ∈ {lima, prod}` (`nestor/model.py:22`, **codé et
validé**) sert aujourd'hui à **trois décisions** qui vont **diverger** dès qu'on
enrichit le catalogue :

- **la sûreté** (la garde d'isolation : ne pas muter un parc réel par erreur) ;
- **le transport** (`lima` → `limactl shell`, sinon `ssh`) ;
- **le kubeconfig / la cible kubectl** (banc rapatrié vs prod).

Or des topologies déjà déclarées ou prévues cassent ces collages : **plusieurs
déploiements bare-metal** (sites distincts), un **banc bare-metal** (jetable
mais joint en SSH, pas via limactl), un **cloud provisionné par Terraform**
([ADR 0032](0032-opentofu-provisioning-cloud.md), joint en SSH mais créé
autrement). « Bare-metal » peut même passer par Terraform — moins courant, mais
possible. `lima`/`prod` (ou `baremetal`/`lima`) ne sait pas exprimer ces cas.

**Constat décisif** : le modèle porte **déjà** ces dimensions, dans des champs
**séparés** — mais seul `target_kind` est codé/validé, les autres restent
déclaratifs (commentaires dans les `*.example.yaml`), d'où la confusion.

## Décision

On **acte les axes du modèle de topologie comme orthogonaux et nommés**, chacun
répondant à une question distincte. La cible d'un montage est le **produit** de
ces axes, pas une valeur unique.

| Axe              | Champ             | Valeurs (extensibles)             | Répond à                                                          | État            |
| ---------------- | ----------------- | --------------------------------- | ----------------------------------------------------------------- | --------------- |
| **Terrain**      | `catalog.terrain` | `local` · `cloud` · `baremetal`   | Sur quelle infra tournent les nœuds ?                             | déclaratif      |
| **Criticité**    | `target_kind`     | `bench` (jetable) · `prod` (réel) | Peut-on tout casser sans risque ? (la **garde** d'isolation)      | codé/validé     |
| **Exposition**   | `exposition.mode` | `nodeport` · `gateway` · `none`   | Le cluster est-il **connecté à internet** (publiquement exposé) ? | codé (ADR 0092) |
| **Architecture** | `catalog.arch`    | `arm64` · `x86`                   | Quelle arche d'images / de build ?                                | déclaratif      |

**Ce qui N'EST PAS un axe — les invariants du dépôt.** Tout n'est pas variable.
L'**OS des nœuds est FIXÉ** : **Debian GNU/Linux** (les rôles `bootstrap/`
épinglent le dépôt Docker `download.docker.com/linux/debian`, `python3-debian`,
la matrice de versions ADR 0006 vise Debian 13). Le périmètre OS complet (poste
de contrôle Unix, nœuds Linux, Windows → WSL) est acté par
[0100](0100-perimetre-os-poste-et-noeuds.md). Ce n'est **pas** un champ de
topologie — aucune topologie ne « choisit son OS ». Le distinguer des axes évite
de sur-paramétrer : un axe est une dimension qu'une topologie fait
**réellement** varier (terrain, criticité, exposition, archi) ; un invariant
(l'OS, le CRI containerd, le CNI Cilium, Kubernetes lui-même) est une **brique
que le dépôt propose** (ADR 0023), pas un paramètre d'instance. Si l'OS devenait
un jour variable (autre distro), ce serait un nouvel axe à acter par ADR — pas
avant.

Lecture concrète (topologies existantes) :

| Topologie               | terrain     | criticité | exposition | démontre…                             |
| ----------------------- | ----------- | --------- | ---------- | ------------------------------------- |
| `banc` (Lima)           | `local`     | bench     | `nodeport` | l'onboarding / le banc jetable        |
| `dirqual`               | `baremetal` | prod      | —          | la prod hyperconvergée réelle         |
| `edge-public` (gateway) | `cloud`     | prod      | `gateway`  | **la capacité d'exposition internet** |

Conséquences directes :

- **La « capacité à être connecté à internet » est déjà un axe** :
  `terrain: cloud` + `exposition: gateway`
  (`topologies/gateway-public.example.yaml`). C'est **la** topologie-vitrine de
  l'exposition publique — pas besoin d'un nouvel axe.
- **Le catalogue s'enrichit par AJOUT de topologies, pas par mutation du
  modèle** : plusieurs bare-metal (sites), un cloud Terraform, un banc
  bare-metal sont des `topology.yaml` supplémentaires combinant les axes — le
  code ne change pas.
- **La garde de sûreté lit la criticité**, jamais le terrain : un banc
  bare-metal reste « jetable » (à protéger comme tel), une prod cloud reste «
  réelle ».

## Renommage `lima` → `bench` (fait)

L'ancien `target_kind: lima` était **mal nommé** : il disait l'**outil**
(Lima/limactl), pas la **criticité** qu'il porte, et il était **redondant** avec
`terrain: local`. **Renommé `lima` → `bench`** (parc jetable ; `prod` inchangé)
: `VALID_TARGET_KINDS = {bench, prod}`. Le champ nomme désormais sa sémantique
réelle — la sûreté — indépendamment de l'infra.

**Resté DISTINCT et conservé** (le point délicat) : le **transport** `lima`
(`isolation.py` : `limactl shell` — l'outil de connexion au banc) est un concept
à part ; sa condition lit maintenant `target_kind == "bench"` mais le transport
garde le nom `"lima"`. De même `ansible_user: lima` (utilisateur de la VM), les
chemins `bench/lima/`, les hostnames `lima-<vm>`. Le **golden** prod
`hosts.example.yaml` (`target_kind: prod`) n'a pas bougé.

**Migré** : comparaisons code (profile/kube_context/plan/topology/portal),
défauts (runner/scaffold), générateur (template `inventory-lima.j2` +
`write_inventory` bash), `EXPECTED_TARGET_KIND=bench` (`run-phases.sh`),
l'argument `--kind` de `artifact generate/diff`, les topologies `.example` et
les tests. Un banc déjà monté (`bench/lima/.work/inventory.yaml` portant `lima`)
doit être **régénéré** (`nestor up`) pour redevenir conforme à la garde.

## Alternatives écartées

- **Encoder la techno dans `target_kind`** (`baremetal`/`lima`) : duplique
  `catalog.terrain` (qui porte déjà `local`/`cloud`/`baremetal`) et reproduit le
  défaut actuel — nommer l'infra/l'outil au lieu de la dimension de sûreté.
  Casse aussi un banc bare-metal (techno = bare-metal, mais criticité =
  jetable).
- **Une clé composite** (`bench-lima`, `prod-baremetal`, `prod-cloud`…) : la
  combinatoire regonfle (un axe ajouté multiplie les valeurs) et la garde doit
  parser un préfixe. Les axes séparés sont plus simples à étendre.
- **Sur-modéliser dès maintenant** (figer un champ `provisioning`, `transport`…)
  : prématuré tant qu'aucune topologie ne l'exige. On documente les axes
  existants ; on ajoutera un champ le jour où une topologie réelle le réclame
  (ADR dédié), pas avant.
