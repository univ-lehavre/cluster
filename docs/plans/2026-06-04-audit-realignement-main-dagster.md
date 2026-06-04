# Audit de réalignement — branche `feat/dagster` ↔ `main` avancé

> Date : 2026-06-04. Type : audit d'impact de session (divergence de branche).
> Contexte : pendant l'implémentation de l'étape 1.7 (Dagster, #129), `main` a
> avancé de 3 commits issus d'un travail mené en parallèle. Cet audit consigne
> l'analyse de collision et la manœuvre de réintégration.

## Situation initiale

- Branche `feat/dagster` basée sur `c343161` (release 2.19.0, #126).
- **Tout le travail 1.7 était NON commité** (working tree + fichiers untracked)
  — aucun commit sur la branche.
- `main` avancé à `f1eba7e` (release 2.20.0), soit **3 commits** :
  - `e4bbc74` #137 — feat(test) : sécurité active (chaos + attaques contrôlées),
    **introduit `ADR 0025`**.
  - `3b37d51` #141 — feat(security) : relais SMTP du hardening hôte (issue
    #131).
  - `f1eba7e` #139 — release 2.20.0.

## Analyse de collision

| Fichier partagé            | Conflit réel ? | Nature                                                                                              |
| -------------------------- | -------------- | --------------------------------------------------------------------------------------------------- |
| `docs/decisions/README.md` | **Oui**        | #137 ajoute la ligne **0025 (sécurité)** ; l'ADR Dagster était aussi 0025 → doublon de numéro.      |
| `docs/decisions/0006-…`    | Non            | non touché par `main`.                                                                              |
| `.trivyignore.yaml`        | Non            | non touché par `main`.                                                                              |
| `lefthook.yml`             | Non            | non touché par `main`.                                                                              |
| `package.json`             | Mineur         | `main` = bump `2.20.0` (ligne 4) ; nous = liste kubeconform (ligne 17). Lignes disjointes.          |
| `bootstrap/state.sh`       | Mineur         | #141 ajoute un bloc postfix/relayhost (~l.233) ; nous = section Dagster (~l.749). Zones disjointes. |

**Conclusion : une seule vraie collision — le numéro d'ADR.** Tout le reste est
zones de fichiers disjointes, fusionnables automatiquement.

## Manœuvre de réintégration

Le travail étant non commité, le « rebase » se réduit à un **déplacement de
base** sûr :

1. `git stash push --include-untracked` (sauvegarde modifs + fichiers neufs).
2. `git reset --hard origin/main` (base sur 2.20.0).
3. `git stash pop` → fusion auto de `state.sh` et `package.json` (zones
   disjointes) ; **1 conflit** sur `docs/decisions/README.md` (doublon 0025).
4. Résolution de l'index : version upstream (0025 sécurité conservé) + ajout
   d'une ligne **0026 Dagster**.
5. **Renumérotation ADR Dagster `0025 → 0026`** :
   - fichier `docs/decisions/0025-orchestration-dagster.md` →
     `0026-orchestration-dagster.md` ;
   - titre H1 `# 0025 …` → `# 0026 …` ;
   - 7 références internes corrigées
     (`platform/dagster/{README,namespace, values.bench,image/Dockerfile}`,
     `bootstrap/state.sh` ×2, `docs/decisions/ 0006-…`).
6. `git stash drop`, vérification « aucun marqueur de conflit résiduel ».

## Résultat

- Branche `feat/dagster` rebasée sur `origin/main` (2.20.0), **0 commit d'avance
  / 0 de retard** côté base.
- ADR sécurité **0025** (#137) préservé ; Dagster en **0026**.
- `state.sh` : bloc postfix (#141) **et** section Dagster coexistent.
- `package.json` : version 2.20.0 **et** liste kubeconform Dagster coexistent.

## Leçon / dette

- **Commiter tôt** sur une branche de feature longue : ici le « rebase » a été
  trivial _parce que_ tout était non commité (un `reset --hard` propre), mais
  une branche non commitée plusieurs jours est fragile (perte si stash mal
  géré).
- **Numéro d'ADR = ressource partagée** entre branches parallèles. Risque de
  collision systématique quand plusieurs features non mergées réservent chacune
  « le prochain numéro ». Atténuation : réserver le numéro tôt (PR squelette) ou
  renuméroter au rebase (fait ici).
- **Digests mono-arch latents** : voir #140 (audit des images épinglées) —
  révélé par le banc arm64.
