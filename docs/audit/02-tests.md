# 2 — Tests multi-niveaux & banc d'essai

**Note : 3,5 / 5**

Stratégie mature pour de l'IaC de recherche : deux bancs Vagrant (single-node
phases 1-2, multi-node phases 1-6 avec disques Ceph), un orchestrateur
`run-phases.sh` avec **gates durs** entre phases, 8 scénarios fonctionnels et de
résilience, un `RESULTS.md` honnête qui trace 9 drifts. Les meilleurs scénarios
(01, 02, le smoke-test S3) font de vraies assertions de résultat.

**Faiblesses :** (1) les 8 scénarios n'ont jamais été exécutés de bout en bout
(gated par le drift #9 CSI) ; (2) plusieurs scénarios (03, 04, 05, 08) n'ont pas
d'assertion dure et sortent 0 même en cas d'échec, ou ne testent pas ce que leur
en-tête prétend ; (3) **la restauration etcd n'est jamais automatisée** ; (4)
`platform/` et `apps/` ne sont couverts par aucun test ; (5) pas de test
unitaire Ansible (`molecule`).

## Points forts

- Deux bancs complémentaires bien documentés (single-node rapide ; multi-node 3
  VMs + disques pour exercer quorum mon, `failureDomain: host`, `block.db`).
- `run-phases.sh` à gates durs : `retry()` + `die()` sur « 3 nœuds Ready », «
  operator Ready », « HEALTH_OK », « 1 seule StorageClass default », « PVC Bound
  », « snapshot etcd produit » — pas juste « ça tourne ».
- Garde-fous banc/prod remarquables : refus du `up` si une interface host-only
  est sur la plage de prod (sabotage évité).
- Scénarios 01, 02, smoke-test S3 : vraies assertions de contenu (écriture puis
  relecture et comparaison stricte).
- Couverture chaos/négatif : worker-loss (03), control-plane-loss (04),
  replication-bump (05).
- `RESULTS.md` d'une transparence rare : 9 drifts datés avec cause/correctif/
  statut, et aveu explicite des phases non testées.

## Constats

### Majeur (→ vérifié majeur) — La restauration etcd n'a jamais été testée

- **Fichier** : `bootstrap/RUNBOOK.md:557-587`, `test/RESULTS.md:40`,
  `test/scenarios/04-control-plane-loss.sh`
- **Constat** : le RUNBOOK recommande de tester la restauration sur le banc,
  mais le scénario 04 fait `vagrant halt`/`up` (etcd revient intact tout seul)
  et se contente d'un `ls` des backups — il n'exécute **jamais**
  `etcdctl snapshot restore`. La procédure de restore reste documentée mais non
  validée, avec des flags sensibles (`--initial-cluster`,
  `--initial-advertise-peer-urls`). L'ADR 0002 promet pourtant une « procédure
  de restore testée sur le banc ».
- **Recommandation** : ajouter un scénario `09-etcd-restore.sh` qui corrompt/
  efface etcd puis exécute le restore complet et vérifie le retour des
  workloads. C'est le test de non-régression le plus critique manquant.

### Majeur (→ vérifié majeur) — Scénario 05 (replication-bump) faux-positive

- **Fichier** : `test/scenarios/05-replication-bump.sh:49-66`
- **Constat** : la boucle d'attente de `HEALTH_OK` n'a pas de branche d'échec ;
  à expiration en `HEALTH_WARN`, le script enchaîne le REVERT et sort 0. Un bump
  bloqué est indistinguable d'un bump convergé — alors que le docstring exige la
  convergence. Le scénario frère 03 implémente pourtant le bon motif.
- **Recommandation** : drapeau de convergence + `exit 1` (avec dump
  `ceph status`) à l'expiration ; attendre la re-convergence après le REVERT.

### Majeur (→ vérifié majeur) — Scénario 04 (control-plane-loss) sort toujours 0

- **Fichier** : `test/scenarios/04-control-plane-loss.sh:48-63`
- **Constat** : la boucle d'attente du retour de l'API n'a aucune branche
  d'échec ; si l'API ne revient jamais, le script termine quand même sur « ✓
  Scénario terminé ». La vérification du snapshot etcd est un simple `ls` sans
  comparaison avant/après. Le test peut « réussir » avec un control plane mort.
- **Recommandation** : `die`/`exit 1` à l'expiration ; capturer le nombre de
  snapshots avant le halt et asserter `count_après > count_avant`.

### Mineur — Les 8 scénarios n'ont jamais tourné de bout en bout

- **Fichier** : `test/RESULTS.md:312-315`, `test/scenarios/README.md:141-147`
- **Constat** : « écrits, shellcheck vert, prêts à dérouler » mais gated par le
  drift #9 (Driver CSI non instancié → PVC Pending). Code de test non validé.
  _Gravité ramenée de majeur à mineur : limitation explicitement assumée et
  documentée, pas un défaut caché._
- **Recommandation** : résoudre le drift #9 (`csi-operator.yaml` +
  `csi-drivers.yaml`), dérouler 01-08, consigner les exit codes réels. En
  attendant, marquer les scénarios « non validés » plutôt que « reproductibles
  ».

### Mineur — Scénario 03 ne teste pas la continuité des I/O annoncée

- **Fichier** : `test/scenarios/03-worker-loss.sh`
- **Constat** : l'en-tête promet de vérifier le passage `HEALTH_WARN` et la
  continuité des I/O (`min_size=2`), mais le script ne lance aucune écriture/
  lecture pendant le halt — seul le retour `HEALTH_OK` est asserté. _Ramené à
  mineur : sur-engagement de l'en-tête, pas un faux-vert masquant un bug._
- **Recommandation** : créer un PVC + pod écrivant en boucle, vérifier la
  continuité pendant le downtime et asserter `HEALTH_WARN`.

### Mineur — `platform/` et `apps/` non couverts par aucun test

- **Fichier** : `test/multi-node/run-phases.sh:254`
- **Constat** : registry, dashboard et RStudio sont déployés sans qu'aucun
  scénario ne vérifie leur fonctionnement (push/pull, accès, démarrage). _Ramené
  à mineur : le banc s'arrête avant de les déployer, et les comportements visés
  sont déjà des choix actés en ADR._
- **Recommandation** : scénarios légers `09-registry-push-pull`,
  `10-rstudio-smoke`.

### Mineur — Pas de test unitaire Ansible (`molecule`, `--syntax-check` en CI)

- **Recommandation** : `molecule` n'est pas indispensable (le banc est le niveau
  intégration). A minima ajouter un `ansible-playbook --syntax-check` en CI, ou
  documenter que le banc multi-node EST le niveau d'intégration assumé.

### Mineur/Suggestion — Vagrantfile et `RESULTS.md` : commentaires obsolètes

- **Fichier** : `test/multi-node/Vagrantfile:11-17,111-119`,
  `test/RESULTS.md:9-13`
- **Constat** : en-têtes décrivant encore `10.67.2.x` / `/dev/sd*` contredits
  par le code (`192.168.67.x`, VirtIO `vd*`) ; un TODO résolu peut induire un
  opérateur à surcharger `CEPH_MIN_HDD=0` à tort.
- **Recommandation** : aligner les commentaires sur la conf réelle.

### Suggestion — Scénario 08 purement informatif ; pas de runner agrégé

- **Constat** : `08-resource-limits-audit.sh` n'a aucune assertion (les seuils
  promis ne sont jamais calculés) → c'est un outil de diagnostic, pas un test.
  La suite n'a pas de récapitulatif PASS/FAIL ni d'isolation d'état entre
  scénarios destructifs.
- **Recommandation** : implémenter les seuils ou ranger le 08 dans `test/tools/`
  ; ajouter un `run-all.sh` produisant un tableau récapitulatif et vérifiant le
  retour à `HEALTH_OK` entre scénarios destructifs.
