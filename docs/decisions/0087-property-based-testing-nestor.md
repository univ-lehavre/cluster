# 0087 — Property-based testing des fonctions pures de `nestor` (Hypothesis)

## Statut

Accepted (2026-06-19). Le code est livré et mergé
(`tests/test_nestor_properties.py`, `hypothesis` en dépendance dev).

## Contexte

Le check OpenSSF Scorecard `Fuzzing` est rouge, marqué **N/A** dans l'audit du
2026-06-16 (« pas de code applicatif à fuzzer (IaC) — non pertinent »,
[audit notations-cyber](../audit/2026-06-16-audit-notations-cyber.md)). La
lecture est juste pour le fuzzing **classique** (OSS-Fuzz, libFuzzer) : il cible
des surfaces d'entrée binaires / des parseurs natifs, absents d'un dépôt d'IaC.

Mais elle est incomplète. Le harnais `nestor`
([ADR 0056](0056-modele-declaratif-topologies.md)) contient des fonctions
**pures** qui **parsent ou classent des entrées externes non fiables** :

- `facts.parse_facts` — parse la sortie KEY=VALUE de `run-phases.sh facts`
  (sortie de processus, potentiellement bavarde / bruitée) ;
- `discover.detect_backend` / `classify_backend_drift` — déduisent le backend de
  stockage réel des provisioners de StorageClass lus du cluster ;
- `discover.classify_health` — agrège des sondes en verdicts de santé ;
- `profile.storage_params`, `scale.target_replicas` — dérivations de profil /
  clamps numériques.

Ces fonctions ont des **invariants explicites** (verdict ∈
`{sain, dégradé, absent}` ; backend ∈ `{ceph, local-path}` ; replicas ∈
`[1, max]`, jamais 0 ; clés du contrat ⊆ ensemble connu ; « ne lève jamais sur
entrée arbitraire »). Ce sont précisément les invariants qu'un **test par
l'exemple** (unittest, une poignée d'entrées figées) **ne couvre pas
exhaustivement** : il prouve le nominal et quelques cas limites choisis à la
main, pas la robustesse sur l'espace des entrées.

La question n'est donc pas « câbler un fuzzer pour le badge » (biais adoptif que
[ADR 0061](0061-posture-adoption-bonnes-pratiques.md) interdit), mais : **un
property-based testing a-t-il un gain net sur ces fonctions ?** (critère 2, ADR
0061).

## Décision

Adopter le **property-based testing** via
[Hypothesis](https://hypothesis.readthedocs.io/) sur les fonctions **pures** de
`nestor` qui parsent ou dérivent une entrée externe. Hypothesis génère des
entrées variées (chaînes arbitraires, listes, entiers aux bornes) et **réduit
automatiquement** tout contre-exemple trouvé à sa forme minimale — c'est un
**fuzzing léger ciblé sur invariants**, défendable au sens du critère « gain net
mesurable » (ADR 0061) : il cherche les bugs sur entrées limites que les tests
par l'exemple ratent, sur le seul code applicatif réel du dépôt.

Modalités :

- **Périmètre = fonctions pures uniquement** (aucune I/O, aucun subprocess,
  aucun accès cluster). Les façades (`runner`, `ha`, `layers`…) qui exécutent
  `limactl`/`kubectl`/bash restent **hors périmètre** — elles se prouvent au
  banc ([ADR 0034](0034-validation-e2e-from-scratch.md)), pas par génération
  d'entrées.
- **`unittest`, pas pytest.** Hypothesis s'intègre nativement à `unittest`
  (`@given` décore une méthode de `TestCase`), donc les nouveaux tests sont
  ramassés par le `python -m unittest discover -s tests` existant
  ([`ci.yml`](../../.github/workflows/ci.yml)). **Zéro coût de diversité** : pas
  de bascule de framework (esprit ADR 0049/0061).
- **Dépendance dev épinglée.** `hypothesis` entre dans `[dependency-groups] dev`
  de [`pyproject.toml`](../../pyproject.toml), `uv.lock` la fige
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)). Dépendance de
  **développement** seule — aucun impact sur le runtime déployé.
- **Si Hypothesis trouve un vrai bug** : on **corrige le code** de `nestor` et
  on garde le test qui le prouve (déclinaison de « corriger le code, pas l'état
  », [ADR 0046](0046-corriger-le-code-pas-l-etat.md)) — pas de `xfail` qui
  masque.

## Conséquences

- Le check Scorecard `Fuzzing` **passe de rouge (N/A) à vert** : Scorecard
  détecte l'usage de fuzzing Python en repérant l'import `hypothesis` dans le
  dépôt. C'est un **effet de bord** de la décision, pas son moteur : la valeur
  première est la robustesse prouvée de `nestor`, le verdissement est un bonus
  (cohérent avec la doctrine d'affichage,
  [ADR 0080](0080-notations-et-badges-readme.md)). Le passage au vert ne sera
  **observable qu'au prochain run Scorecard sur `main`** (hebdomadaire / au
  push), pas mesuré ici.
- L'analyse CodeQL ([`codeql.yml`](../../.github/workflows/codeql.yml))
  **exclut** `tests/` (`paths-ignore`) pour concentrer le signal SAST sur la
  logique de décision. **Aucun conflit** avec le signal Fuzzing : Scorecard
  scanne l'arborescence brute du dépôt pour repérer `hypothesis`, indépendamment
  du périmètre que CodeQL analyse.
- Une nouvelle dépendance dev (`hypothesis`) à suivre dans la matrice de
  versions (ADR 0006). Renovate la maintiendra (`renovate.json`).
- L'audit 2026-06-16 est mis à jour (ligne `Fuzzing` : N/A → vert, daté) sous la
  doctrine des passages datés
  ([ADR 0058](0058-doctrine-audit-grille-passages.md)).
