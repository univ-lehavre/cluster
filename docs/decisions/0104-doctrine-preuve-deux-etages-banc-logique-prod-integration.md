# 0104 — Doctrine de preuve à deux étages : banc-logique / prod-intégration

## Statut

Accepted (2026-07-05).

Révise (sans abroger) [0034](0034-validation-e2e-from-scratch.md) : en précise
le périmètre et corrige un présupposé implicite (« E2E from-scratch au banc =
preuve suffisante du livrable applicatif »). Prolonge
[0036](0036-backing-s3-unique-rgw.md) (validé en léger → revalider en Ceph avant
prod) et [0052](0052-reproductibilite-des-resultats.md) (reproductibilité des
résultats, mention de réserve honnête). S'appuie sur
[0046](0046-corriger-le-code-pas-l-etat.md) (corriger le code, pas l'état) et
[0058](0058-doctrine-audit-grille-passages.md) (passages d'audit datés).

## Contexte

[ADR 0034](0034-validation-e2e-from-scratch.md) pose que la preuve d'une brique
d'infra est un **run e2e from-scratch sur banc** — jamais le lint seul. Cette
doctrine reste **juste dans son périmètre** (le socle : bootstrap k8s, réseau
intra-cluster, ordre de création, idempotence). Mais la mise en route de la
chaîne applicative **citation** sur prod (2026-07-05) a révélé qu'elle laisse
croire, à tort, que « E2E vert au banc » couvre aussi le **flux applicatif
complet**.

Les faits (cf. les passages d'audit
[2026-07-05](../audit/2026-07-05-transform-e2e-prouve-prod.md)) : la chaîne
citation passait **tous** les contrôles statiques ET le run banc au vert, et
pourtant **cinq bugs successifs** n'ont été trouvés qu'en la faisant tourner sur
prod dirqual — chacun débloqué sur un run réel :

1. **seed prod I/O** (3 bugs git/Argo) — le flux de seed était stubbé en test,
   et l'overlay banc ne portait pas de placeholder de digest → les bugs étaient
   des _no-op_ au banc ;
2. **source OpenAlex réelle** — la restructure `data/` → `data/jsonl/` était
   invisible derrière un mock ;
3. **contraintes OBC Ceph** — le quota `max_buckets` (`TooManyBuckets`) et le
   nommage `citation-datalake-<uuid>` n'existent pas sous SeaweedFS (banc) ;
4. **bucket dbt** — `build_dbt_vars` ne dérivait pas les racines S3 du
   `BUCKET_NAME` réel : au banc, `BUCKET_NAME=citation` coïncidait avec le
   défaut littéral et **masquait** le bug ;
5. **orphelins `author_id`** — l'entité `authors` d'OpenAlex n'est pas un
   sur-ensemble des auteurs cités par les works ; les fixtures banc, elles, sont
   self-consistantes.

**Constat structurant** : ces cinq bugs vivent **tous** dans l'écart banc/prod,
et **aucun test ne franchissait cet écart**. Le banc (mono-nœud, local-path,
SeaweedFS, source mockée, seed stubbé) couvre honnêtement le **socle,
l'orchestration et l'idempotence**, mais couvre à **0 %** trois zones : (i) le
flux seed prod I/O, (ii) l'ingestion depuis une source externe réelle, (iii) les
contraintes propres à un OBC Ceph. Le « E2E from-scratch vert » était _vrai_
mais _sur-vendu_.

Le dépôt le savait à moitié : [ADR 0036](0036-backing-s3-unique-rgw.md) impose
déjà « validé en léger → revalider en Ceph avant prod ». La faille n'est pas un
mensonge du banc, c'est un **défaut d'application de sa propre doctrine** au
chemin applicatif. Le correctif est de **doctrine**, pas de matériel (rappel :
les bancs Ceph et 3-VM ont été abandonnés faute de ressources — la prod est déjà
l'environnement de fidélité).

## Décision

**La preuve se fait à DEUX ÉTAGES, de nature différente. Le banc est une gate de
LOGIQUE ; la prod est la gate d'INTÉGRATION externe et d'INFRASTRUCTURE. On ne
consigne jamais « validé E2E » pour un chemin applicatif sur la seule foi du
banc.**

1. **Banc = gate de logique.** Il prouve ce qui est vrai à toute échelle et
   accessible sans infra réelle : socle k8s + réseau intra-cluster, **ordre de
   création**, **idempotence** (`changed=0` au rejeu), orchestration,
   NetworkPolicy intra-cluster. C'est le périmètre d'ADR 0034, inchangé.

2. **Prod = gate d'intégration/infrastructure.** Toute dépendance **substituée**
   au banc (source de données externe réelle, Ceph RGW/OBC, seed prod I/O, HA)
   se prouve **sur prod dirqual** par un run réel, tracé dans un passage d'audit
   daté (ADR 0058) — jamais réputée acquise depuis le banc.

3. **Mention de réserve obligatoire.** Dès qu'un chemin dépend d'une brique
   substituée au banc, tout relevé de validation (RESULTS, mémoire, PR) **doit**
   porter la réserve explicite : « validé banc : socle + orchestration +
   idempotence ; \<dépendances substituées\> = À PROUVER SUR PROD ». C'est la
   généralisation de l'honnêteté d'ADR 0052.

4. **Tests de contrat code↔config-prod comme filet cheap.** Là où l'écart est
   catchable **sans** infra prod, un test de contrat le garde : dérivation de
   config depuis l'environnement réel (ex. racines S3 depuis `BUCKET_NAME`),
   intégration seed contre un dépôt git jetable avec placeholder. Ces tests
   franchissent l'écart que le smoke banc ne voit pas (ex.
   `test_build_dbt_vars_derives_s3_roots_from_bucket_name`).

5. **Corollaire — polarité des défauts.** Un paramètre de _bornage banc_ (volume
   d'échantillon, cadence) ne doit jamais avoir un **défaut qui bride la prod
   silencieusement**. Défaut = comportement prod ; c'est le banc qui restreint,
   via sa config (overlay/env), jamais l'inverse (cf. la révision de l'ingestion
   citation, où `sample_size`/`max_partitions` mini-banc bridaient la prod).

## Conséquences

- **Gain** : la confiance est correctement calibrée. On cesse d'attribuer au
  banc un pouvoir qu'il n'a pas ; on nomme explicitement ce que seule la prod
  prouve. Les cinq bugs citation deviennent une grille de vigilance réutilisable
  (tout nouveau chemin applicatif : « quelles dépendances sont substituées au
  banc ? »).
- **Prix à payer** : certains chemins ne sont « verts » qu'après un run prod —
  plus lent, moins reproductible qu'un banc. Mitigé par (a) les tests de contrat
  cheap, (b) une gate de déploiement prod prudente (dry-run Argo, health gates,
  rollback de phase), (c) la garde d'isolation banc/prod
  ([0053](0053-isolation-multi-cible-banc-prod.md)).
- **Discipline** : ne jamais écrire « E2E validé » nu pour un chemin applicatif.
  Le banc valide la logique ; la prod valide l'intégration. Un passage d'audit
  daté (ADR 0058) matérialise la preuve prod.
- **Garde-fou** : un défaut de configuration ne doit pas franchir la frontière
  banc→prod à l'insu de l'opérateur (polarité, point 5). Une valeur d'instance
  prod n'est jamais figée versionnée (ADR 0023) ; c'est le banc qui pose ses
  bornes.
- **Non-régression d'ADR 0034** : le socle continue de se prouver par un run
  from-scratch au banc. 0104 ne l'affaiblit pas ; il en délimite honnêtement la
  portée et ajoute l'étage prod pour ce que le banc ne peut structurellement pas
  voir.
