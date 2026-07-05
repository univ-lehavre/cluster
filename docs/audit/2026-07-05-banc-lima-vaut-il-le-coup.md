# Passage d'audit — le banc Lima vaut-il encore le coup ? (doctrine de preuve)

> **Type** : passage d'audit ciblé (ADR 0058) — angle « valeur du banc /
> dissimilarité banc↔prod », pas la grille /5. **Date** : 2026-07-05.
> **Déclencheur** : après 6+ bugs _prod-only_ découverts en mettant citation en
> route sur dirqual (cf.
> [2026-07-05 — aval citation](2026-07-05-aval-citation-bugs-config-prod.md)),
> l'auteur s'interroge : banc et prod sont-ils trop dissimilaires pour que le
> banc garde une valeur ? **Méthode** : éventail multi-agents + revue
> adversariale (analyse d'options, vérification contradictoire des faits
> `bench/RESULTS.md` / `bench/lima/RESULTS.md` et des chemins citation).

## Verdict

**Non, on ne tue pas le banc — mais on arrête de le vendre comme une gate E2E.
Le banc est une gate de LOGIQUE, pas une gate d'INFRASTRUCTURE ni d'INTÉGRATION
externe.**

Le post-mortem citation ne prouve pas que le banc est inutile ; il prouve qu'on
lui a prêté un pouvoir qu'il n'a jamais eu. Les faits tiennent dans les deux
sens :

- **Le banc attrape réellement des bugs prod-affectants.** L'historique
  (`bench/RESULTS.md`, `bench/lima/RESULTS.md`) documente ~60 drifts, dont une
  part explicitement marquée « impact PROD, se reproduit identique » : backup
  etcd fantôme, NetworkPolicy Cilium qui exclut le kube-apiserver, CNPG sans
  passwordSecret, Dagster sans workspace, CRD Gateway posée après le contrôleur.
  Ce sont des bugs du livrable, attrapés avant la prod, qu'aucun lint ne voit.
  Et le banc prouve l'**idempotence** (`changed=0` au rejeu) et l'**ordre de
  création** — deux propriétés structurellement inaccessibles à l'analyse
  statique.
- **Mais les 6 bugs citation vivent tous EXACTEMENT dans l'écart banc/prod**, et
  aucun test ne franchit cet écart : seed prod I/O jamais exécuté (`do()` stubbé
  en test, overlay bench sans placeholder de digest → les 3 bugs git/Argo sont
  des _no-op_ au banc) ; source OpenAlex mockée (aveugle à la restructure
  `data/` → `data/jsonl/`) ; ni Ceph ni OBC sur le chemin citation (quota
  `max_buckets`/`TooManyBuckets` et nommage `citation-datalake-<hash>`
  inexistants sous SeaweedFS).

La conclusion n'est donc **pas** « banc vs prod trop dissimilaires ». C'est : le
banc couvre honnêtement le **socle K8s + réseau intra-cluster + orchestration +
idempotence sur local-path/SeaweedFS**, et couvre à **0 %** trois zones précises
— (i) le flux seed prod I/O, (ii) l'ingestion depuis une source externe réelle,
(iii) les contraintes propres à un OBC Ceph. Le « E2E from-scratch vert » était
_vrai_ mais _sur-vendu_ : rien ne signalait que ces trois zones étaient à
couverture nulle.

Le dépôt le savait déjà à moitié :
[ADR 0036](../decisions/0036-backing-s3-unique-rgw.md) dit noir sur blanc « un
changement S3 validé en léger _doit_ être revalidé en Ceph avant prod ». La
faille n'est pas un mensonge, c'est un **défaut d'application de sa propre
doctrine** au chemin citation. Le correctif est de doctrine, pas de matériel.

## Options (trade-offs)

### A — Re-scoper honnêtement le claim + tests de contrat code↔config-prod

Le banc reste une gate de logique. On change deux choses : (1) le
**vocabulaire** — plus jamais « E2E vert » sans qualificatif pour citation ; (2)
on ajoute des **tests de contrat** qui vérifient l'alignement code↔config-prod
_sans_ infra prod.

- **Faisabilité mono-mainteneur** : élevée (pytest sur le Mac, sans Ceph ni
  cluster). Effort faible à moyen.
- **Ce que ça catche** : 4 des 6 bugs — les 3 bugs seed (en exécutant
  `_git_push_atlas_tree` contre un git local jetable + un overlay _avec_
  placeholder) et le bug dbt `raw_root` (test « `build_dbt_vars` injecte-t-il
  exactement les vars que le SQL exige ? » → révèle que `raw_root` n'est jamais
  dérivé de `BUCKET_NAME`). Ne catche PAS le quota OBC ni la restructure
  OpenAlex externe.
- **Coût** : quelques jours de tests, zéro matériel, zéro coût récurrent.
  **Meilleur ratio valeur/coût du lot.**

### B — Rapprocher le banc de la prod (Ceph RGW/OBC en Lima, source réelle, seed testé)

- **Ceph RGW/OBC en Lima** : **infaisable** sur ce Mac. Banc Ceph complet et
  banc 3-VM déjà **abandonnés** faute de ressources (décision actée).
  Ressusciter Rook+Ceph+OBC mono-nœud pour tester un quota `max_buckets` =
  remonter précisément ce qui a été jugé irréalisable. Rejeté.
- **Vraie source OpenAlex** : partiellement faisable _hors banc hermétique_ — un
  test de contrat périodique `rclone lsf s3://openalex/data/jsonl` (anonyme,
  live, hors CI hermétique) aurait détecté la restructure. Faible coût, mais
  fragile (dépend d'un tiers, réseau) et ne peut pas vivre dans un run
  from-scratch reproductible.
- **Vrai seed testé** : c'est en réalité l'Option A (git local jetable + overlay
  à placeholder), pas B. Faisable et cheap.
- **Verdict** : **rejeté sauf le volet sonde OpenAlex live.**

### C — Un staging cloud proche de la prod

Un cluster cloud éphémère (ou permanent) avec Ceph/RGW réel, OBC, où rejouer le
seed prod et l'ingestion.

- **Ce que ça catche** : quasiment tout (Ceph, OBC, seed, réseau) — seul à
  catcher le quota OBC de façon reproductible.
- **Coût** : élevé et récurrent (€ + heures). Un 2ᵉ dirqual à nourrir en parité,
  pour une seule personne. La contrainte « une seule prod, pas de staging » est
  structurelle du projet, pas un oubli. **Disproportionné.** À rouvrir si le
  projet grossit (multi-mainteneurs, SLA).

### D — Prod-comme-gate + smoke tests de config

Assumer que la prod dirqual EST l'environnement de fidélité (elle l'est déjà de
fait — #538 était la 1ʳᵉ exécution E2E prod), et l'encadrer par : (1) des smoke
tests de config _avant_ déploiement (= Option A), (2) un déploiement prod
prudent (dry-run Argo, health gates, rollback de phase), (3) la garde
d'isolation [ADR 0053](../decisions/0053-isolation-multi-cible-banc-prod.md)
pour ne jamais confondre banc et prod.

- **Faisabilité mono-mainteneur** : élevée. C'est déjà ~80 % en place
  (`assert_prod_target`, rollback de phase, health gates). Il manque surtout les
  smoke tests de config (= Option A) et une checklist prod nommée.
- **Coût** : faible. Formalisation d'un état de fait.

### E — Tuer le banc

**Rejeté (destructeur).** On perd la validation d'idempotence, d'ordre, de
NetworkPolicy intra-cluster, de bootstrap etcd/restore/PodSecurity — ~60 bugs/an
qui ne partiraient plus en prod, reportés sur dirqual, la _seule_ prod, sans
staging. Le banc n'a pas failli sur son périmètre ; il a été mal étiqueté.

## Recommandation (priorisée)

**Un mix A + D, avec une pincée du volet OpenAlex-live de B. Ni C ni E.**

1. **[Maintenant, cheap] Re-scoper le claim (A, volet doctrine).** Bannir « E2E
   from-scratch vert » nu pour le chemin applicatif citation. Le remplacer
   partout (runs, RESULTS, mémoire) par la mention explicite : **« validé banc :
   socle + orchestration + idempotence ; seed-prod-I/O + source réelle +
   contraintes OBC = À PROUVER SUR PROD »**. C'est la réserve d'honnêteté
   qu'[ADR 0052](../decisions/0052-reproductibilite-des-resultats.md) impose
   déjà pour un run aidé à la main — on la généralise. Coût : rédactionnel.
2. **[Maintenant, cheap] Deux tests de contrat qui auraient attrapé 4 bugs sur 6
   :**
   - **dbt bucket** : test que `build_dbt_vars` produit l'ensemble _exact_ de
     vars requises par le SQL/macros — révèle que
     `raw_root`/`curated_root`/`marts_root` ne sont jamais dérivés de
     `BUCKET_NAME` au runtime. Corriger dans la foulée. _(Fait le 2026-07-05 :
     fix + test de contrat
     `test_build_dbt_vars_derives_s3_roots_from_bucket_name`.)_
   - **seed git** : test d'intégration exécutant `_git_push_atlas_tree` contre
     un dépôt git local jetable, avec un overlay _contenant un placeholder de
     digest_, vérifiant que (a) `checkout -B` ne casse pas sur la branche
     courante, (b) la tête poussée contient le digest **substitué et committé**,
     (c) `targetRevision` pointe la tête effectivement poussée. Attrape les 3
     bugs seed sans aucune infra prod.
3. **[Maintenant, cheap] Formaliser prod-comme-gate (D).** Une checklist de
   déploiement prod nommée (dry-run Argo → health gates → rollback de phase
   prêt), adossée à la garde ADR 0053. Nommer honnêtement que la classe «
   Ceph/OBC/source réelle » se prouve sur prod, comme Ceph et HA le sont déjà.
4. **[Optionnel, low-cost, fragile] Sonde OpenAlex live** hors run hermétique
   (test de contrat périodique `rclone lsf s3://openalex/data/jsonl`). Attrape
   la prochaine restructure externe. À isoler de la CI reproductible.
5. **[Ne pas faire] Ceph/OBC en Lima (B) ni staging cloud (C)** tant que le
   projet reste mono-mainteneur sur Mac. Coût matériel/temps disproportionné ;
   la prod joue déjà ce rôle.

**En une phrase** : garder le banc pour ce qu'il prouve vraiment (logique,
ordre, idempotence, réseau intra-cluster), arrêter de lui faire dire ce qu'il ne
prouve pas (seed prod, source réelle, OBC), et compenser par des tests de
contrat cheap là où c'est catchable sans infra + par une gate prod nommée là où
ça ne l'est pas.

## Faut-il un ADR ? Oui — un ADR qui révise ADR 0034 sans l'abroger

[ADR 0034](../decisions/0034-validation-e2e-from-scratch.md) reste juste _dans
son périmètre_ : le socle se prouve bien from-scratch. Le problème est qu'il
laisse croire que « E2E » couvre le flux applicatif complet, alors que sur ce
banc (mono-nœud, local-path, SeaweedFS, source mockée, seed stubbé) le E2E
applicatif est structurellement partiel. Un ADR est justifié parce que :

- **C'est une décision structurante et transverse** (touche la doctrine de
  preuve, pas un fichier) — exactement le cas où le CLAUDE.md exige un ADR
  plutôt qu'un bullet de TODO.
- **Elle acte une frontière** : « banc = gate de logique
  (socle/orchestration/idempotence/réseau intra-cluster) ; prod = gate
  d'infrastructure et d'intégration externe (Ceph/OBC/HA/source réelle/seed prod
  I/O) ». Généralisation de la ligne déjà tracée par « Ceph et HA se prouvent
  sur prod » et par ADR 0036.
- **Elle a des conséquences vérifiables** : impose la mention de réserve (point
  1), justifie les tests de contrat (point 2) et la gate prod nommée (point 3).

**Proposition** : un ADR « Doctrine de preuve à deux étages : banc-logique /
prod-infrastructure » qui (a) précise le périmètre exact d'ADR 0034 (le socle,
pas le flux applicatif sur substituts), (b) référence ADR 0036 et ADR 0052 comme
précédents, (c) rend obligatoire la mention de réserve pour tout chemin dont une
dépendance (Ceph/OBC/source externe/seed prod) est substituée au banc, (d)
institue les tests de contrat code↔config-prod comme filet de rattrapage cheap.
Il _complète_ 0034 en le rendant honnête ; il ne le renie pas.

> Hygiène : ajouter un ADR périme le bloc STATS du README → régénérer via
> `check_gouvernance.py --stats` avant de pousser.

## Manques → suite

- ADR « doctrine de preuve à deux étages » (révise 0034) — **à écrire**.
- 2 tests de contrat (dbt vars ✅ 2026-07-05 ; seed git — **à écrire**).
- Checklist prod nommée (gate D) + éventuelle sonde OpenAlex live — **à
  câbler**.
