# 0042 — Fraîcheur des preuves de banc (garde-fou CI)

## Contexte

[ADR 0034](0034-validation-e2e-from-scratch.md) pose que la **preuve** de
validation est un run e2e from-scratch consigné (log archivé sous
`test/lima/runs/`, synthèse dans `test/lima/RESULTS.md`), jamais le passage au
vert du lint. Mais rien ne **garantit que ces preuves restent fraîches** : le
code évolue (PR après PR) tandis que le dernier run consigné peut dater de
plusieurs jours/semaines. La doc finit par affirmer « validé » sur la foi d'un
run **périmé** — exactement la dérive que l'ADR 0034 combat, déplacée dans le
temps.

Contrainte dure : **le banc ne peut pas tourner en CI.** Lima exige un vrai
hyperviseur (nested virt), arm64, ~30 min/run, ressources d'un poste — hors de
portée des runners GitHub standards. La CI ne peut donc PAS _exécuter_ l'e2e ni
les scénarios ; elle peut seulement **observer la fraîcheur des preuves
consignées** (par un humain, en local) et **alerter** quand elles vieillissent.

Deux familles de preuves à surveiller :

- **e2e from-scratch** (`test/lima/run-phases.sh`) — monte tout depuis zéro ;
  consigné dans `runs/<date>-*.log` + `RESULTS.md`.
- **scénarios** (`test/scenarios/NN-*.sh`) — épreuves sur banc monté ; leur
  statut d'exécution vit dans la matrice (§ « scénarios exécutés »).

## Décision

**Un garde-fou CI vérifie la _fraîcheur_ des preuves de banc et alerte quand le
dernier run consigné dépasse un seuil — sans bloquer les PR.**

1. **Mécanisme : cron quotidien, non bloquant.** Un workflow programmé (1×/jour)
   lit la date du dernier run consigné et, si elle dépasse le seuil, **signale**
   (job en échec visible + ouverture/maj d'une issue de rappel). Il **ne bloque
   aucune PR** : le banc étant manuel, faire échouer un fix de typo parce
   qu'aucun run n'a tourné depuis 24 h serait punitif et contre-productif.
2. **Seuil = 7 jours, pas 24 h.** Exiger un run e2e quotidien (~30 min, manuel,
   sur le poste) n'est pas tenable (week-ends, congés → alerte permanente, donc
   ignorée). Un seuil **hebdomadaire** garde la pression sur la fraîcheur tout
   en restant réaliste. Le seuil est une **variable** du workflow, ajustable.
3. **Source de fraîcheur = un champ daté machine-lisible**, pas le mtime Git (le
   checkout CI ne préserve pas les dates de fichiers). Le run consigne sa date
   dans un artefact versionné dédié — l'**historique des runs**
   (`test/lima/runs-history.yaml`, cf. backlog métriques) ou, à défaut, la date
   en tête du dernier `runs/<date>-*.log`. Le garde-fou lit ce champ.
4. **Couplage avec la consignation.** La fraîcheur n'a de sens que si chaque run
   s'enregistre. `run-phases.sh` doit **append** une entrée datée (id, tuple,
   verdict — cf. backlog historique YAML) en fin de run ; le garde-fou s'appuie
   dessus. Tant que cet historique n'existe pas, le garde-fou se rabat sur la
   date du log le plus récent dans `runs/`.

## Statut

Accepted (cadrage). L'implémentation (workflow cron + lecture de la date +
ouverture d'issue) fera l'objet d'une PR dédiée, **après** la mise en place de
l'historique des runs daté (`runs-history.yaml`) dont elle dépend.

## Conséquences

- **Gain** : la dérive « doc validée / preuve périmée » devient **visible** sans
  intervention — un rappel automatique quand le banc n'a pas tourné depuis une
  semaine. Prolonge l'esprit ADR 0034 dans la durée.
- **Prix à payer** : le garde-fou ne **prouve** rien (il ne lance pas le banc) —
  il mesure une **fraîcheur**, pas une réussite. Un run consigné « vert » reste
  sous la responsabilité de l'humain qui l'a lancé (honnêteté des Runs).
- **Non-bloquant assumé** : on accepte qu'une PR puisse merger avec des preuves
  vieillissantes — l'alerte informe, ne verrouille pas. Si un jour un terrain CI
  capable de monter le banc existe (runner self-hosted), on pourra durcir.
- **Dépendance** : nécessite l'historique des runs daté ; à séquencer après lui.
- **Anti-faux-positif** : seuil hebdomadaire + variable, pour que l'alerte reste
  un signal utile et non un bruit permanent qu'on finit par ignorer.
- **Seuil par chemin (à venir, ADR 0045 §6)** : ce cadrage pose **un** seuil
  global. La matrice de couverture de
  l'[ADR 0045](0045-chemins-installation-banc-couches.md) §6 distingue des
  cadences **par chemin** (`atlas` 7 j, `storage-real` 30 j, `cluster-dataops`
  90 j) : un run `atlas` frais ne doit plus masquer un `storage-real` périmé. Le
  garde-fou devra donc lire le **dernier run par `TARGET`** dans
  `runs-history.yaml` et comparer chacun à **sa** cadence — évolution à porter
  quand le garde-fou sera implémenté.
