# 0113 — Chaîne de livraison autonome : la branche `deploy` matérialisée par la CI

## Statut

Accepted (2026-07-14). Prolonge
[0111](0111-atlas-instancie-application-argocd.md) (atlas instancie
l'`Application`) et [0112](0112-cicd-in-cluster-gitea-actions-buildkit.md)
(l'usine CI/CD in-cluster, prouvée sur un jouet) ; précise
[0094](0094-frontiere-deploiement-applicatif.md) sur « ce que suit Argo CD ».
Forme une **paire** avec l'ADR atlas 0104 (le geste de mise en production et les
workflows de livraison, côté atlas). Conception : plan atlas
`2026-07-14-mise-en-production-push-gitea`.

## Contexte

[0112](0112-cicd-in-cluster-gitea-actions-buildkit.md) a prouvé l'usine (push →
Gitea Actions → buildctl → buildkitd → registre → Argo CD → pod Running) **sur
un jouet** : le scénario 35 poussait lui-même son Dockerfile, son workflow et
son manifeste. Ses conséquences l'admettent : « le déploiement de démonstration
n'est pas encore une couche — industrialisation à suivre ». Trois questions
restent sans réponse doctrinale et bloquent le passage du jouet aux
code-locations réelles d'atlas :

1. **Qui écrit le digest ?** atlas expose des placeholders
   (`__<CL>_IMAGE_DIGEST__` / `__<CL>_IMAGE__`) que personne ne remplit depuis
   que [0111](0111-atlas-instancie-application-argocd.md) a retiré le seed
   (`_substitute_digest_in_tree`). Au banc du scénario 35, le SHA a été écrit à
   la main.
2. **Que suit Argo CD ?** Les `Application` (instanciées par atlas, 0111)
   pointent `main` — qui porte des placeholders, pas des digests.
3. **Qui déclenche ?** L'évolution « événementielle » du contrat (ADR
   atlas 0033) ne précise pas la frontière entre le geste humain et
   l'automatisme.

## Décision

> **La CI in-cluster matérialise les digests des images buildées sur une branche
> `deploy` du dépôt atlas de la forge Gitea. Les `Application` Argo CD suivent
> `deploy`. `main` reste byte-identique au main revu (placeholders intacts).
> Personne — humain ou seed — n'édite `deploy` à la main.**

### 1. Trois acteurs, deux flux

| Acteur                   | Rôle                                                                                                                                                                                                                                  | Cadence            |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| **cluster / nestor**     | provisionne + installe **l'usine** (Gitea, runner, buildkitd, registre, Argo CD, Dagster, CNPG, stockage — 0112) et les **contenants** par code-location (base logique, rôle, secret). Ne touche jamais à l'applicatif.               | rare, converge     |
| **atlas**                | le code + **toutes les déclarations de son déploiement** : manifeste montant, kustomize, `Application` (0111), migrations (hooks PreSync), **workflows de livraison** (`.gitea/workflows/`, lus par la forge depuis le dépôt poussé). | à chaque évolution |
| **l'usine** (in-cluster) | exécute au push, sans humain ni nestor : build (cible `code` `FROM` la pré-image, zéro egress — 0110/0112) → push registre → **write-back sur `deploy`** → Argo CD → hooks PreSync → rollout → reconciler Dagster (0103).             | à chaque push      |

Deux flux d'entrée côté atlas : la **pré-image** (poste de contrôle, egress,
rare — bump du lock) et le **code** (push de `main` vers Gitea — **le** geste de
mise en production, humain, par instance ; ADR atlas 0104).

### 2. La branche `deploy` : une projection mécanique

`deploy` n'est **pas** une branche de travail : c'est `main ⊕ digests`,
régénérée par la CI à chaque livraison.

- À chaque push de `main`, le workflow builde les code-locations **changées**,
  lit leurs digests au registre, **reporte** les digests des code-locations non
  rebuildées (depuis l'état précédent de `deploy`), et régénère `deploy` = copie
  de `main` + substitution de **tous** les digests connus. Une code-location
  sans digest connu n'est simplement pas déployable (son `Application` n'a pas
  lieu d'être instanciée avant sa première livraison).
- Les workflows filtrent `branches: [main]` : le push de `deploy` ne déclenche
  **rien** (pas de boucle).
- `main` garde ses placeholders **intacts** : parité avec le main revu de GitHub
  (les gardes `validate.sh` d'atlas continuent de l'exiger), et la revue ne voit
  jamais un digest.
- Chaque digest est un **commit** sur `deploy` : l'histoire de ce qui a été
  déployé vit dans git (déploiement par digest,
  [0095](0095-build-applicatif-evenementiel-in-cluster.md) §2). La dette «
  observabilité de drift digest dormante » de 0111 se résout ici : le
  comparateur lit `deploy`.

### 3. Périmètre de la CI : livraison, pas qualité

La qualité (lint, typecheck, tests) se joue **avant le merge**, sur la forge de
revue (hooks locaux + CI GitHub). Le push Gitea ne part que de `main` revu et
mergé. La chaîne in-cluster est un **pipeline de livraison** : garde de
fraîcheur de la pré-image (échec bruyant si le lock a divergé,
`check_deps_base_freshness`), build air-gappé, write-back. Elle ne rejoue pas
les tests — des minutes de pytest par push sur le nœud, pour du code déjà gardé
en amont.

### 4. Le déclencheur reste un geste humain, par instance

Pousser `main` vers la forge Gitea d'une instance est **le** geste de mise en
production (ADR atlas 0104 : script dédié, garde de cible `GITEA_PUSH_URL`). L'«
événementiel » du contrat commence **en aval** de ce push. Un miroir automatique
GitHub→Gitea (merge = production) reste possible plus tard comme **propriété
d'instance** — non retenu ici : le découplage merge/déploiement par instance
prime.

### 5. Ce que cluster doit encore fournir

- Les **droits d'écriture** du job CI sur `deploy` : vérifier que le token
  Actions de la forge permet le push sur le dépôt courant ; sinon, fournir un
  compte/token de livraison (livrable nestor, secret d'instance).
- Rien pour les migrations : les hooks PreSync (ConfigMap + Job fournis par
  atlas dans ses kustomize) sont exécutés par Argo CD — prouvé en production
  (citation, 2026-07-04).

## Conséquences

- Les placeholders d'atlas ont enfin un **remplisseur mécanique** ; fin du SHA
  écrit à la main du scénario 35.
- Le contrat consommé par Argo CD change : `targetRevision: deploy` dans les
  patrons `application.example.yaml` d'atlas (lot atlas du plan).
- `nestor` n'acquiert **aucun** rôle applicatif nouveau : la décision renforce
  [0108](0108-isolation-par-identite-et-verbes-provision-install.md)
  (provision/install) et 0111 (retrait du seed).
- Prix : une branche de plus à comprendre (`deploy`), mitigé par son invariant «
  projection mécanique, jamais éditée à la main ».

## Alternatives écartées

- **Muter `main` Gitea depuis la CI** (`[skip ci]`) : divergence main-Gitea ↔
  main-GitHub (placeholders détruits), courses entre un push de code et le
  write-back, boucles conjurées par convention fragile.
- **Argo CD Image Updater** : une brique de plus à opérer
  ([0093](0093-cache-flux-cnpg.md) : « pas de brique inutile ») et le digest
  sort de git — l'histoire des déploiements ne serait plus un log de commits.
- **La sentinelle** ([0106](0106-gitops-zero-geste-sentinelle.md)) : superseded
  — remplacée par le déclenchement natif Gitea Actions (0112).
- **Le retour du seed** (retiré par 0111) : re-coupler cluster à l'applicatif,
  contraire à la trajectoire 0108 → 0112.
