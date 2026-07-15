# 0114 — `nestor access` dérive `GITEA_PUSH_URL` : la cible de livraison atlas, par topologie

## Statut

Accepted (2026-07-15). Résout le **point ouvert** de
[0111](0111-atlas-instancie-application-argocd.md) (« `atlas/workflows` vs
`atlas/atlas` — un seul monde de nommage doit émerger ») et complète la paire de
livraison [0113](0113-chaine-livraison-branche-deploy.md) (l'usine) / ADR atlas
0104 (le geste). Prolonge [0090](0090-nestor-pilote-la-prod.md) (nestor pilote
toute cible par la topologie) et
[0102](0102-catalogue-topologies-v2-topo-source-unique.md) (la topo, source
unique) ; s'appuie sur [0101](0101-migration-zone-grise-bash-python.md)
(`access.sh` porté en `nestor access`).

## Contexte

Le geste de mise en production atlas (`dataops/deploy.sh`, ADR atlas 0104)
pousse `origin/main` vers la forge Gitea de l'instance, à l'adresse lue dans une
seule variable : `GITEA_PUSH_URL`. Tout l'aval est autonome (l'usine,
0112/0113). `deploy.sh` ne devine **jamais** sa cible : il la lit dans
`atlas/.env.cluster.local` (garde de cible, ADR atlas 0073 §B). Ce `.env` est
généré par `nestor access` (le contrat cluster→atlas, ADR atlas 0033).

Trois défauts rendaient le geste **inopérant sur toute cible** :

1. **`nestor access` n'émettait pas `GITEA_PUSH_URL`.** Le `.env` portait
   Postgres/OpenLineage/registre, mais pas la cible de livraison. `deploy.sh`
   échouait « variable absente » partout.
2. **La cible org/repo était ambiguë.** L'exemple de contrat et le seed
   pointaient `atlas/workflows` — or `workflows` est le dépôt **jouet du socle**
   (0086/0111), celui qui prouve l'usine (scénario 35), jamais la cible de
   livraison. Argo CD, lui, suit le dépôt atlas **complet**
   (`repoURL …/<org>/atlas.git`, `targetRevision: deploy`). Pousser ailleurs que
   là où Argo CD réconcilie = une livraison qui ne déploie rien.
3. **L'endpoint de forge n'était pas dérivable par cible.** Comment le poste
   joint la forge (port-forward local, `<hôte>:<nodePort>`, gateway) dépend de
   l'exposition de la topologie — aucune logique ne le calculait.

Il n'y a **plus de dualité banc/prod** : rien que des topologies (l'ancien champ
de criticité est retiré, ADR 0108 ; `terrain` = classe matérielle). La
dérivation doit donc être **une seule**, paramétrée par la topo active — pas
deux chemins.

## Décision

**`nestor access` dérive `GITEA_PUSH_URL` de la topologie active et l'écrit dans
le `.env`.** Chaque morceau de
`http://<user>:<token>@<host>:<port>/<org>/<repo>.git` a une source unique :

- **`user`** : lu du Secret `gitea-admin` (déjà affiché par `access`).
- **`token`** : un token API **jetable**, généré dans le pod gitea
  (`gitea admin user generate-access-token`, régénéré à chaque `access`), jamais
  versionné — c'est le « token de livraison » de 0113 §5, matérialisé.
- **`org`** : le `gitea.org` de la topo (défaut générique `atlas`, ADR
  0023/0035) ; il **doit** égaler l'org du `repoURL` des `Application` atlas.
- **`repo`** : le dépôt de **livraison**, fixé à `atlas` — **jamais**
  `gitea.repo` (qui vaut `workflows`, le jouet). C'est la résolution du point
  ouvert 0111 : la cible de livraison est `<org>/atlas`, le jouet reste
  `<org>/workflows`.
- **`host:port`** : nouveau champ **`gitea.push_endpoint`** de la topo. S'il est
  déclaré, il prime (le contrat > la déduction, ADR 0090/0102). Sinon nestor
  **déduit** de l'exposition (ADR 0092) : un mode `nodeport`/`gateway` est joint
  directement en `<portal.access_host>:<nodePort réel>` ; tout autre mode
  (réseau isolé, ex. Lima) via un port-forward local `127.0.0.1:<port>` que
  `nestor access` **ouvre et laisse vivre** (fermé par `--stop`), le `git push`
  d'atlas s'exécutant après la commande.

**Frontière (contrat cluster→atlas, ADR atlas 0033).** cluster **fournit** la
cible de livraison (l'URL, dans le `.env` généré) ; atlas la **consomme**
(`deploy.sh`). Un maillon indérivable (endpoint indéterminé, token non généré) →
nestor **n'écrit pas** la variable et le dit ; `deploy.sh` refuse alors
bruyamment — jamais une URL cassée émise en silence.

**Découpage pur/I-O (ADR 0017/0049).** La décision — endpoint selon
l'exposition, assemblage de l'URL, défauts de livraison — est **pure**
(`nestor/access.py`, testée sans cluster). L'I/O — lire le Secret, générer le
token, ouvrir le port-forward — reste la façade
(`scripts/topology.py:cmd_access`).

## Conséquences

- **Positif.** Le geste `deploy.sh` fonctionne sur **toute** topologie sans
  réglage manuel sur Lima (déduction port-forward, prouvée par le scénario 36) ;
  sur cloud/baremetal, une seule ligne à déclarer (`gitea.push_endpoint`).
  L'ambiguïté `workflows`/`atlas` est levée. `access` reste le geste unique « je
  me branche et je livre ».
- **Négatif / limites.** Le token est régénéré à chaque `access` (cohérent avec
  le `.env` « régénérer après un run », sans révocation des précédents —
  acceptable pour un secret d'instance jetable). La déduction d'endpoint suppose
  que le poste **atteigne** l'hôte déclaré (routage/Tailscale côté opérateur) —
  hors du ressort de nestor. `nestor access` lit des Secrets et écrit des
  identifiants en clair dans un `.env` **gitignoré** : voulu (ADR 0048), faux
  positif CodeQL assumé.
- **Contrat.** `contract/atlas.env.cluster.example` est corrigé en verrou
  (`atlas/atlas.git`, en-tête `nestor access`). Les topos d'exemple documentent
  `gitea.push_endpoint` (commenté en local — déduction suffit ; renseigné en
  baremetal — mode gateway).

## Alternatives écartées

- **Un champ topo pour l'URL complète de forge** (au lieu de `host:port` +
  org/repo dérivés) : redondant (org/repo sont déjà contraints par le `repoURL`
  des `Application`) et duplique une info dérivable.
- **Réutiliser `gitea.repo` pour la livraison** : c'est le jouet — la source
  même de l'ambiguïté 0111. Fixer `repo=atlas` en dur tranche.
- **Un miroir automatique GitHub→Gitea** (pas de geste, pas de `.env`) : option
  par instance, hors sujet ici (ADR atlas 0104 l'a écartée pour le geste par
  défaut).
