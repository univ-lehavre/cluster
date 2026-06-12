# 4 — Documentation (néophyte, dans le code, site VitePress)

Cette dimension regroupe les trois facettes documentaires. Elle est centrale
dans votre demande : **« documentation exhaustive visant un public néophyte où
les termes techniques doivent être définis avant. »**

| Facette                        | Note      |
| ------------------------------ | --------- |
| Pédagogie néophyte             | **2 / 5** |
| Documentation dans le code/ADR | 4,3 / 5   |
| Site VitePress                 | 3,5 / 5   |

---

## 4.A — Documentation pédagogique pour public néophyte — **2 / 5**

La documentation est de très bonne qualité **technique** (structurée, à jour, 12
ADR, RUNBOOK détaillés) mais **rédigée par et pour des opérateurs
expérimentés**. Le critère que vous avez explicitement demandé — _les termes
techniques définis avant d'être utilisés_ — **n'est respecté quasiment nulle
part** : Kubernetes, etcd, CNI, CRI, kubeadm, OSD, MON, PVC, RWX, erasure
coding, CSI, Tailscale, drift, hyperconvergence sont employés dès la première
phrase sans définition. **Il n'existe aucun glossaire dans tout le dépôt**
(vérifié par recherche exhaustive), ni de parcours « de zéro à cluster ».

### Points forts pédagogiques (existants mais ponctuels)

- `docs/decisions/README.md:1` glose « Architecture Decision Records (ADR) » au
  premier usage — l'exemple à généraliser.
- L'ADR 0003 développe « RGW (Rados Gateway) » et « msgr2 » à leur premier
  usage.
- Encadrés ⚠️ explicites avant les opérations destructives.
- Recherche locale VitePress + sidebar ordonnée par phases (progression
  esquissée).

### Majeur (→ vérifié majeur) — Aucun glossaire

- **Fichier** : transversal (vérifié sur tous les `.md` et `config.mjs`)
- **Constat** : aucun fichier glossaire ; la sidebar n'a aucune entrée «
  Glossaire »/« Concepts ». Les sigles structurants (Kubernetes, etcd, CNI, CRI,
  kubeadm, OSD, MON, MGR, PVC, RWO/RWX, CSI, RBD, CephFS, RGW, EC, SPOF, drift,
  hyperconvergence, taint/toleration, `failureDomain`, IPAM, CIDR) ne sont
  définis nulle part de façon centralisée.
- **Recommandation** : créer `docs/glossaire.md`, le placer en tête de sidebar,
  le lier depuis le README, et lier chaque premier usage d'un terme vers son
  ancre. **C'est l'action #1 pour répondre à votre objectif néophyte.**

### Majeur (→ vérifié suggestion) — Pas de parcours débutant ni de prérequis

- **Fichier** : `README.md:1-49`, `docs/.vitepress/config.mjs:44-54`
- **Constat** : aucun « par où commencer », aucun prérequis de connaissances,
  aucune page expliquant ce que le projet construit et pourquoi. Les sections «
  Pré-requis » existantes sont techniques (outils), pas pédagogiques. _Gravité
  ramenée à suggestion : dépôt interne pour un cluster précis, pas un support
  d'apprentissage public — aucune promesse d'onboarding n'est rompue._
- **Recommandation** : page `docs/demarrage.md` en tête de sidebar (public visé,
  prérequis, lien glossaire, parcours numéroté 1→5 vers chaque RUNBOOK).

### Constats mineurs — Termes employés avant définition

Chacun est un finding mineur ; la liste illustre l'ampleur du chantier néophyte
:

| Terme                                                       | Premier usage non glosé           |
| ----------------------------------------------------------- | --------------------------------- |
| `Kubernetes`, `cluster`, `manifests`, `playbooks`           | `README.md:5` (1re phrase)        |
| `hyperconvergence`                                          | `PLAN.md:6`, `config.mjs:15`      |
| `drift`                                                     | `README.md:36`                    |
| `etcd`                                                      | `README.md:38`                    |
| `CNI`, `CRI`, `kubeadm/kubelet/kubectl`, `control plane`    | `bootstrap/README.md:12-17`       |
| `OSD`, `MON`, `MGR`, `RBD`, `CephFS`, `RGW`, EC, `min_size` | `storage/ceph/README.md`          |
| `PVC`, `PV`, `RWO/RWX`, `StorageClass`                      | `SAFEGUARDS.md:166`, etc.         |
| `Tailscale`                                                 | `PLAN.md:63` (pilier de sécurité) |

- **Recommandation** : gloser au premier usage + lier au glossaire. Marquer
  clairement les sections « avancé/optionnel » (eBPF, IPVS, kube-proxy, VXLAN,
  CIDR) pour que le néophyte sache qu'il peut les sauter.

### Suggestions

- `CONTRIBUTING.md` empile l'outillage (Lefthook, Prettier, yamllint…) sans
  expliquer « à quoi ça sert » → ajouter une colonne d'une ligne par outil.
- `PLAN.md` ouvre sur un Contexte saturé de jargon → ajouter un encadré « ce
  document est un plan d'ingénierie ; néophytes, commencez par le README et le
  glossaire ».

---

## 4.B — Documentation dans le code (commentaires, READMEs, ADR) — **4,3 / 5**

Niveau remarquable, nettement au-dessus de la moyenne IaC. Les 12 ADR suivent un
format Nygard cohérent (Contexte / Décision / Statut daté / Conséquences),
numérotés, datés, indexés, liés. Scripts shell exemplaires (`set -euo pipefail`
partout, en-têtes Usage/variables/codes de sortie). Chaque dossier a un README
de rôle. Quasi aucun TODO/FIXME orphelin.

### Points forts

- 12 ADR au format Nygard strict et homogène, datés « Accepted (2026-05-28) ».
- Renvois code → ADR là où la décision est subtile (`credentials.sh:6` cite
  l'ADR 0010 ; READMEs RStudio/registry renvoient à 0012/0011).
- Matrice de versions ADR 0006 **synchronisée avec le code réel** (K8s 1.34,
  Cilium 1.19.4, Rook 1.19.6, Ceph 20.2.1, Dashboard 7.10.0, Registry 3.1.1).
- Suppressions de lint ciblées et justifiées (`# noqa …`).

### Mineur — ADR 0005 désynchronisée du code (hold containerd)

- **Fichier** : `docs/decisions/0005-…:30,51-53`,
  `bootstrap/roles/k8s-CRI-install/tasks/main.yaml:80-84`
- **Constat** : l'ADR affirme « containerd.io 2.2.4 » et un « `apt-mark hold`
  posé par le rôle » ; or le rôle installe en `state: present` **sans** version
  ni hold. Le rôle de rollback tente pourtant de retirer ce hold jamais posé.
- **Recommandation** : poser le hold (`dpkg_selections`) **ou** corriger l'ADR.
  (Cf. le même finding côté reproductibilité en [05](05-reproductibilite.md).)

### Mineur — `bootstrap/README.md` : table de contenu incomplète

- **Constat** : omet `first-access.sh`, `state.sh` (script central de drift),
  `rollback.yaml`, `etcd-backup.yaml`, `audit-log-baseline.yaml`.
- **Recommandation** : compléter la table.

### Mineur / Suggestion — Décisions sensibles sans renvoi ADR au point de code

- **Fichier** : `apps/rstudio/deployment.yaml` (`DISABLE_AUTH`),
  `storage/ceph/storageClass/datalake/datalake-ec.yaml:23` (`port: 80`)
- **Recommandation** : commentaire d'une ligne renvoyant à l'ADR concerné, lu en
  revue/`kubectl diff`.
- Les rôles `bootstrap/security/` n'ont aucun commentaire inline (vs 3-17 dans
  les autres rôles) → en ajouter sur les choix non évidents (auditd, sshd, UFW).

---

## 4.C — Documentation VitePress (site) — **3,5 / 5**

Bien conçu : `srcDir: '..'` + `rewrites` README→index pour publier toute la doc
colocalisée sans déplacer les fichiers, recherche locale, `lastUpdated` avec
`fetch-depth: 0`, `lang: fr-FR`, déploiement Pages propre. Les 25 chemins de la
sidebar existent tous. Deux problèmes notables.

### Majeur (→ vérifié majeur) — `ignoreDeadLinks: true` masque les liens cassés

- **Fichier** : `docs/.vitepress/config.mjs:19`
- **Constat** : aucune détection de lien interne cassé au build. Vérifié : de
  nombreux liens `.md` pointent vers des scripts `.sh` (non rendus) et des
  répertoires sans index (`platform/`, `apps/`) ; ces liens marchent sur GitHub
  mais sont **morts sur le site publié**. En rebuildant avec
  `ignoreDeadLinks: false`, VitePress les signale tous. Aggravant :
  `SAFEGUARDS.md:57` affirme que `pnpm docs:build` valide « pas de dead link » —
  ce que ce réglage rend faux.
- **Recommandation** : passer en liste ciblée
  (`[/\.sh$/, /^\/(platform|apps)\/$/]`) ou `'localhostLinks'`, et corriger les
  liens réellement cassés.

### Mineur (→ vérifié mineur) — `editLink` pointe vers le mauvais dépôt

- **Fichier** : `docs/.vitepress/config.mjs:159-162`
- **Constat** : `github.com/pochasset/cluster/edit/…` au lieu de
  `univ-lehavre/cluster` — chaque page a un lien « Modifier sur GitHub » en 404.
  Seul `:path` est bon ; seul l'owner est faux.
- **Recommandation** : corriger l'owner en `univ-lehavre`.

### Mineur — Pas de lien GitHub dans la nav (`socialLinks` absent)

- **Recommandation** :
  `socialLinks: [{ icon: 'github', link: '…univ-lehavre/cluster' }]`.

### Mineur — Liens vers `platform/` et `apps/` cassés sur le site

- **Fichier** : `README.md:20-21`
- **Constat** : ces répertoires n'ont pas de `README.md` → pas d'`index.html` →
  404 sur le site (alors que `bootstrap/`, `storage/ceph/` fonctionnent).
- **Recommandation** : créer `platform/README.md` et `apps/README.md`, ou
  pointer vers une page existante.

### Suggestions

- H1 du README en `# cluster` (minuscule) → `<title>cluster | Cluster</title>`
  incohérent ; mettre `# Cluster`.
- Pas de bloc `locales`/i18n : **correct** pour un projet monolingue — aucune
  action requise.
