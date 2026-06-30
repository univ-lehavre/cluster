# 0098 — Source unique d'inventaire : `nestor` dérive l'inventaire, `hosts.yaml` supprimé

## Statut

Proposed (2026-06-30)

Prolonge [0056](0056-modele-declaratif-topologies.md) (modèle déclaratif des
topologies — la topologie est la source) en tarissant la **dernière**
double-déclaration restée côté prod. Cohérent avec
[0053](0053-isolation-multi-cible-banc-prod.md) (isolation banc/prod, le garde
`target_kind`), [0090](0090-nestor-pilote-la-prod.md) (`nestor` pilote la prod)
et [0097](0097-moteur-chemin-python-bash-artefacts.md) (le moteur Python est le
seul orchestrateur ; `nestor ansible` en est le prolongement côté ops prod). Lié
à [0023](0023-plateforme-exemple-generique.md) (valeurs génériques : toute
spécificité d'un déploiement vit dans une topologie locale, jamais un inventaire
versionné) et [0034](0034-validation-e2e-from-scratch.md) /
[0052](0052-reproductibilite-des-resultats.md) (preuve, reproductibilité).
Valeurs d'exemple génériques (ADR 0023) : `dirqual1`…`dirqual4`, `cp1`,
`node1`…`node4`, `prod`, `lima`.

## Contexte

L'inventaire Ansible prod vit dans
[`bootstrap/hosts.yaml`](../../bootstrap/hosts.example.yaml) — un fichier
**statique**, **gitignoré**, que l'opérateur **copie** de `hosts.example.yaml`
puis **édite à la main** (noms de nœuds, rôles, `target_kind`). Or **ces mêmes
faits sont déjà déclarés** dans la topologie (`topologies/dirqual.yaml` : nœuds,
rôles, `target_kind`). C'est une **double-déclaration** : la topologie ET
l'inventaire décrivent le même parc. Le modèle déclaratif (ADR 0056) avait tari
cette duplication partout **sauf** ici, côté prod.

Cette duplication n'est pas qu'inélégante — elle est **dangereuse**. Un fichier
inventaire **persistant** est un **vecteur d'invocation parallèle** qui
court-circuite `nestor` : il suffit d'un
`ansible-playbook -i bootstrap/hosts.yaml <play>` lancé hors du moteur pour
muter un parc sans passer par les gardes d'isolation. **C'est exactement ce qui
a produit un incident** : un harnais a exécuté
`ansible-playbook -i bootstrap/hosts.yaml … ceph-cluster.yaml` et déployé
Rook-Ceph là où il ne fallait pas. Le défaut de conception n'est pas l'erreur
ponctuelle, c'est qu'un **inventaire pointable** rende cette erreur
**possible**.

`nestor` sait **déjà** dériver l'inventaire de la topologie
([`nestor/generator.py`](../../nestor/generator.py) : `render_prod_inventory` →
`dirqual1`…`dirqual4` avec `target_kind`, byte-exact vs le `.example`). Le
fichier statique n'apporte donc **rien** que la topologie ne porte déjà — sinon
le risque.

## Décision

**L'inventaire prod n'a plus d'existence persistante.** Une commande enveloppe
**`nestor ansible <playbook> [args ansible…]`** :

1. charge la **topologie active** (cohérence inventaire ↔ intention) ;
2. **dérive** son inventaire dans un fichier **temporaire**
   (`render_prod_inventory` en prod, `render_lima_inventory` au banc), hors de
   l'arbre versionné ;
3. passe le garde **`_assert_inventory_safe`** (Python, **avant** tout
   `ansible-playbook`) — le filet décisif d'isolation banc/prod (ADR 0053) ;
4. pose `EXPECTED_TARGET_KIND` depuis `topo.target_kind` (réarme l'assert
   `audit-log` par-play) puis lance `ansible-playbook -i <temp> <playbook>` en
   transmettant les arguments Ansible (`--limit`, `--tags`, `--check`, `-e`…) ;
5. **nettoie** le temporaire en `finally` (robuste interruption/exception).

[`bootstrap/hosts.yaml`](../../bootstrap/hosts.example.yaml) sera **supprimé**
(à terme — cf. § Mise en œuvre incrémentale). `hosts.example.yaml` est **gardé**
comme golden (le rendu byte-exact attendu de `render_prod_inventory`, vérifié
par test) et comme documentation de structure. `bootstrap/ansible.cfg` pointera
alors `hosts.example.yaml` au lieu de `hosts.yaml` (filet : une invocation
`ansible-playbook` **nue**, sans `-i`, doit échouer sur un parc d'exemple
inerte, jamais cibler `localhost` ni un parc réel).

## Conséquences

- **Source unique côté prod** : la topologie est le seul descripteur du parc ;
  le vecteur `-i hosts.yaml` de l'incident est **structurellement** éteint (le
  fichier n'existe plus).
- **Le flux opérateur change** : plus de `cp hosts.example.yaml hosts.yaml` puis
  édition. L'opérateur déclare ses nœuds dans une **topologie locale**
  (ADR 0023) et lance `nestor ansible <play>`. RUNBOOK, READMEs et suggestions
  `state.sh` réécrits en conséquence.
- **Le garde `target_kind` est préservé** : l'inventaire dérivé porte
  `target_kind` (posé par `render_prod_inventory`) ; `_assert_inventory_safe`
  (Python) **et** l'assert `audit-log` (Ansible) restent armés.
- **Risque résiduel** : quatre playbooks (`security/secure.yml`, `upgrade.yml`,
  `etcd-fetch.yaml`, `cnpg-secrets.yaml`) mutent sans importer l'assert
  `audit-log` en `pre_tasks` — ils ne sont couverts **que** par le filet Python,
  garanti **ssi tout passe par `nestor ansible`**. Un test anti-régression
  interdit un nouveau consommateur de `hosts.yaml` ; la défense en profondeur
  (assert `audit-log` sur ces quatre + migration des `cron` etcd) est traitée
  séparément.
- **Perte assumée** : on ne peut plus « bricoler l'inventaire à la main » hors
  topologie (ADR 0023 — toute spécificité passe par la topologie locale).

## Alternatives écartées

- **Régénérer l'inventaire dans un `.work/` éphémère** (gitignoré, dérivé) :
  garde un fichier inventaire **à chemin stable et devinable** (`ls`) pendant
  tout un montage (20–40 min) → **déplace** le vecteur d'invocation parallèle au
  lieu de l'**éteindre**, et ne couvrirait que le montage (1 des 6 sites prod).
  Rejeté au profit du `mkstemp` par consommateur (cf. § Mise en œuvre
  incrémentale, point 3) : anonyme, éphémère, uniforme, _moins_ de surface.
- **`hosts.yaml` lecture-seule régénéré en hook** : même faille (fichier
  pointable) + complexité d'un hook de cohérence.
- **Statu quo** (édition manuelle de `hosts.yaml`) : a **produit** l'incident.

## Mise en œuvre incrémentale

Cet ADR est livré **par étapes** (le statut reste `Proposed` tant que la bascule
n'est pas complète et prouvée) :

1. **Fait** — la commande `nestor ansible <playbook>` (dérive l'inventaire dans
   un temporaire `mkstemp` `0o600`, garde `_assert_inventory_safe`, cleanup en
   `finally`) ; additive, `hosts.yaml` reste en place.
2. **À faire** — généraliser le pattern temporaire aux 5 autres consommateurs
   prod de l'inventaire (cf. point 3), **supprimer `hosts.yaml`** (et son suivi
   git — il est à la fois `.gitignore` ET tracké), puis basculer la doc/config
   (`ansible.cfg` → `*.example`, `Justfile` → `nestor ansible`, suggestions
   `state.sh`, RUNBOOK).
3. **Couplage moteur ↔ inventaire — tranché** : le **moteur** `run_path` lit
   l'inventaire via `_path_context`, documenté **PUR** (aucune I/O, ADR 0097
   §5.a) ; `PathContext.inventory` est consommé **après** la construction, par
   des closures (`assert_safe`, `launch`) actives tout au long du montage —
   l'inventaire doit donc **vivre pendant tout le run**. La résolution **ne pose
   PAS de fichier `.work/` prod** (chemin stable et devinable pendant 20–40 min
   de montage → rouvrirait partiellement le vecteur d'invocation parallèle ; et
   ne couvrirait qu'1 des 6 sites). Elle **généralise le pattern déjà mergé de
   `cmd_ansible`** : un contextmanager `_prod_inventory(topo)`
   (`render_prod_inventory` → `mkstemp` `0o600` → `yield` →
   `finally os.remove`). Chaque consommateur prod l'enroule :
   `cmd_up`/`_run_path_engine` ouvre le `with` autour de **tout** le montage (le
   temp vit le run entier, nettoyé même sur erreur) et passe le chemin à
   `_path_context` **en paramètre** — qui reste **pur** (il reçoit un chemin,
   n'écrit rien) ; `cmd_next`, `cmd_discover` (`--cp`, `--node-side`) et la
   repatriation kubeconfig enroulent leur geste court. `_inventory_for` cesse de
   servir la prod (la branche lima — `bench/lima/.work/inventory.yaml` posé par
   le provisioning bash — est **inchangée**).

   **Sécurité** — un `mkstemp` (`/tmp/nestor-inv-XXXXXX`, anonyme, supprimé en
   `finally`, jamais sous `bootstrap/`, jamais nommé dans un RUNBOOK/Justfile)
   n'est **pas** le `hosts.yaml` de l'incident (persistant, à la racine
   documentée, chemin stable, pointé par `ansible.cfg`/Justfile). C'est
   _strictement moins_ de surface qu'un `.work/` stable. Le garde `target_kind`
   (porté par `render_prod_inventory`) reste armé dans les deux sens
   (`_assert_inventory_safe` + assert `audit-log`), même sur une invocation
   manuelle.
