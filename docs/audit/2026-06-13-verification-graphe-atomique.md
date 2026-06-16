# 2026-06-13 — Vérification des périmètres atomiques (graphe ADR 0066)

| Champ        | Contenu                                                                                                                                                |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Date**     | 2026-06-13                                                                                                                                             |
| **Type**     | cartographie en éventail (lecteurs + synthèse adversariale)                                                                                            |
| **Fonde**    | [ADR 0066](../decisions/0066-rollback-atomique-graphe-composants.md) Lot 0 — graphe atomique encodé dans `bench/lima/rollback-lib.sh`                  |
| **Éventail** | 5 agents (lecture des rôles Ansible / manifestes / `run-phases.sh`, recoupement croisé)                                                                |
| **Verdict**  | 23 composants atomiques + 30+ arêtes confirmés contre le code ; ordre de montage reproduit l'ordre codé `atlas-ceph` ; 8 pièges structurels identifiés |

## Pourquoi ce workflow

L'[ADR 0066](../decisions/0066-rollback-atomique-graphe-composants.md) décide de
remplacer le périmètre de rollback **par phase** (composite, fragile) par un
**graphe de composants atomiques** unique. Avant de l'**encoder**, il fallait
**vérifier** chaque périmètre atomique contre le code réel — sinon le graphe
hériterait des mêmes oublis que la table qu'il remplace. Un éventail de lecteurs
a cartographié, pour chaque composant : le namespace possédé, les ressources
ciblées (dont hors-ns), les CRD, l'état node-side, le profil conditionnel, et
les dépendances directes ; puis une synthèse a recoupé et arbitré les conflits.

## Synthèse (assainie — valeurs génériques, ADR 0023)

**23 composants atomiques**, chacun avec **au plus un namespace propre**. La
distinction _possesseur vs locataire_ est la clé : `cnpg-operator` possède
`cnpg-system`, `cnpg-cluster-pg` possède `postgres` — **deux composants, deux
namespaces distincts**. C'est précisément cette séparation qui rend l'oubli
historique de `cnpg-system` (l'operator survivait au rollback et
re-réconciliait) **structurellement impossible** : l'invariant d'unicité du
possesseur l'aurait attrapé.

**Ressources hors-ns attachées à leur producteur.** Une OBC déposée dans le ns
d'Object Storage (`cnpg-backups`, `loki-buckets`) est un _targeted_ de son
**producteur** (`s3-backing-cnpg`, `s3-backing-loki`), jamais un résidu du
composant qui possède le ns. Oubliées, elles laissaient le `CephObjectStore`
bloqué en `Terminating` (finalizer : bucket dépendant). Le graphe rend l'oubli
impossible (invariant de complétude par ownership).

**Le graphe (30+ arêtes) reproduit l'ordre codé.** Le tri topologique de la
clôture, projeté sur les alias de phase, redonne **exactement** l'ordre codé
`atlas-ceph` : socle → ceph → sc → datalake → monitoring → gitops → dataops →
gitops-seed. Nuance importante relevée par le workflow :
`monitoring < gitops < dataops` n'est **pas** imposé par une arête de données
(`registry`, dans dataops, ne dépend que du socle et flotterait plus haut) —
c'est une **convention d'ordre** qu'il faut fixer par un **poids d'alias**
déterministe dans le tri. C'était la pré-condition du Lot 4 (montage par
graphe), désormais satisfaite.

### Pièges structurels confirmés (8)

1. **CRD partagées** — `gateway.networking.k8s.io` (gateway-api → registry,
   gitea, argocd), `ceph.rook.io` / `objectbucket.io` (ceph → sc, datalake,
   s3-backing-\*) : ne JAMAIS les GC depuis un emprunteur ; **listées que chez
   le possesseur**.
2. **NS partagés possesseur/locataire** — `monitoring` (prometheus-stack possède
   ; loki + s3-backing-loki déposent) ; `cnpg-system` (cnpg-operator possède ;
   barman-plugin dépose). Le piège qui a causé l'oubli `cnpg-system`.
3. **`postgres` à possesseur unique** — `cnpg-secrets` y dépose des Secrets
   _avant_ le Cluster, mais en **locataire-précurseur** : seul `cnpg-cluster-pg`
   possède le ns (sinon l'invariant d'unicité échoue).
4. **OBC = targeted du producteur**, jamais résidu du possesseur du ns (cf.
   supra).
5. **Composants conditionnels au profil** —
   `ceph`/`sc`/`datalake`/`s3-backing-*` (profil Ceph), `seaweedfs` (profil
   léger, exclusif de datalake comme cible S3) : la condition (`when:`) vit
   **dans le composant**, pas dans l'alias.
6. **`_STUCK_CR_KINDS` doit être une union DÉRIVÉE** des CRD à finalizer des
   composants montés, pas une liste figée parallèle (sinon nouvelle divergence).
7. **Racines node-side sans ressource k8s** — `bootstrap` (ne JAMAIS supprimer
   `kube-system`), `build-images` : métadonnée `has_nodeside`, pas une cible
   delete.
8. **`gitops-seed` = données** (Application Argo CD seed), pas d'infra ni de CRD
   propre — un _targeted_, en dernier.

## Ce qui en est sorti

Le graphe a été encodé dans `bench/lima/rollback-lib.sh` **à côté** des
fonctions par phase (rien retiré — Lot 0), prouvé par **48 invariants bats**
sans banc (trivialité + unicité du possesseur, acyclicité, déterminisme,
ownership des OBC, reproduction de l'ordre codé, garde-fou anti-GC des CRD
partagées). La bascule du rollback réel (Lot 3) et du montage (Lot 4) suivra,
**prouvée par run** de banc
([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)/[0052](../decisions/0052-reproductibilite-des-resultats.md)).

> Première entrée de la 4ᵉ trace empirique
> ([ADR 0067](../decisions/0067-workflows-consignes-4e-trace-empirique.md)).
