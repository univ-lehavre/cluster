# 0052 — Reproductibilité des résultats (principe-chapeau)

## Contexte

La reproductibilité est, de fait, le **principe fondateur** du dépôt — mais il
est resté **diffus** : une dizaine d'ADR l'invoquent par un angle, aucun ne le
**nomme ni ne le décide**. Chaque pilier existe isolément :

- [ADR 0034](0034-validation-e2e-from-scratch.md) — la **preuve** d'une brique
  est un run e2e _from-scratch_, pas le passage au vert du lint.
- [ADR 0046](0046-corriger-le-code-pas-l-etat.md) — le **code** d'installation
  est la seule source de vérité ; on corrige le code, jamais l'état du cluster.
- [ADR 0042](0042-fraicheur-preuves-banc.md) — une preuve **vieillit** : un
  garde-fou alerte quand le dernier run par chemin dépasse sa cadence.
- [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md) — versions et
  images **épinglées par digest** (déterminisme des inputs).
- [ADR 0023](0023-plateforme-exemple-generique.md) /
  [0051](0051-options-natives-ansible.md) — valeurs **génériques
  surchargeables**, aucune constante de déploiement en dur (le code marche pour
  tout déploiement).
- [ADR 0050](0050-modele-reprise-role-ansible.md) — un rôle à effet de bord non
  idempotent porte un **chemin de reprise** (`rescue:`) qui ramène à un état
  re-jouable : la reproductibilité doit survivre à une **faute** en cours de
  run.

Faute de chapeau, le principe se perd dans les cas limites. Ces deux derniers
jours l'ont montré en pratique : un run sur un banc **complété à la main** (NP
egress posée hors code, dépôt apt `deb822` non encore commité) « passait » alors
qu'il **masquait** que le rôle ne produisait pas le résultat ; un rôle dont
l'**idempotence** n'était pas prouvée par rejeu pouvait diverger au second
passage ; un résultat consigné sans le **commit** qui l'a produit n'est pas
re-jouable. Le mécanisme manquant n'est pas un nouveau garde-fou, c'est la
**règle de valeur** qui relie les piliers et tranche les cas limites.

## Décision

**Un résultat n'a de valeur que s'il est reproductible à partir du code seul.**
Tout ce qui est produit ici — un déploiement, une preuve de banc, un benchmark,
un diagnostic — ne « compte » que si **quelqu'un d'autre, à partir du dépôt
versionné et de rien d'autre, obtient le même résultat**. Ce qui n'est pas
reproductible n'est pas un résultat : c'est une anecdote.

Les ADR ci-dessus sont les **piliers** de ce principe ; cet ADR est leur
**toit**. Il en tire quatre règles **opposables** (un contributeur, ou la CI,
peut s'en prévaloir pour refuser un résultat) :

### 1. État complété à la main = preuve invalide

Un run obtenu sur un banc dont l'état a été **complété hors du code** (un
`kubectl apply`/`patch` manuel, un secret posé à la main, une étape rejouée
isolément) **ne prouve rien** — il prouve l'état bricolé, pas le code. Seul un
run **from-scratch depuis le code versionné** fait foi
([ADR 0034](0034-validation-e2e-from-scratch.md)/[0046](0046-corriger-le-code-pas-l-etat.md)).
Corollaire : si un run a été aidé à la main, on le **dit** dans la consignation
(réserve d'honnêteté) et le résultat est marqué **à re-prouver**.

### 2. Idempotence prouvée par rejeu

Un rôle/playbook réputé convergent doit le **démontrer** : rejoué une seconde
fois sans changement d'input, il donne **`changed=0`**. Une idempotence non
prouvée est un résultat non reproductible (un re-run pourrait diverger). C'est
le rôle du gate `run_ansible_phase` (rejeu → `classify_idempotence`) ; un
`changed_when: true` constant qui ment sur le changement
([ADR 0051](0051-options-natives-ansible.md)) casse cette propriété et doit être
corrigé.

### 3. Déterminisme des inputs

Des inputs non déterministes produisent des résultats non reproductibles. On
épingle donc ce qui pourrait flotter : **versions et images par digest d'index**
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)) ; **valeurs de
déploiement dérivées du terrain ou surchargées**, jamais codées en dur
([ADR 0023](0023-plateforme-exemple-generique.md)/[0051](0051-options-natives-ansible.md)
(f)). L'aléa, l'horloge et le réseau variable qui influencent un _test_ sont
**injectables** (cf. le générateur d'IP de `blur_env.py`, les fonctions pures
testées hors cluster) pour que le test soit déterministe.

### 4. Traçabilité commit ↔ run

Tout résultat consigné porte le **commit exact** qui l'a produit. Sans
provenance vérifiable, un résultat n'est pas reproductible : on ne sait pas
_quel_ code relancer. `test/lima/runs-history.yaml` porte déjà `commit:` par
entrée ; `RESULTS.md` date et situe ses runs. La fraîcheur
([ADR 0042](0042-fraicheur-preuves-banc.md)) en est le pendant temporel : un
résultat reproductible mais **périmé** (le code a divergé depuis) doit être
rejoué.

### 5. Reprise prouvée par faute injectée

Symétrique de la règle 2 : si l'idempotence (rejeu **sans** faute → `changed=0`)
prouve qu'un rôle convergent ne diverge pas, alors un chemin de **reprise**
(`rescue:` d'un rôle à effet de bord non idempotent — `kubeadm init`/`join`,
[ADR 0050](0050-modele-reprise-role-ansible.md)) ne « compte » que s'il a été
**exercé par une vraie faute**. Un `rescue:` jamais déclenché est du code non
testé : on ne sait pas reproduire la reprise qu'il prétend offrir. La preuve est
un **arrêt injecté** au protocole opposable, dans cet ordre : le 1er run
**échoue** (la faute a pris), la **compensation est tracée** (`kubeadm reset`
dans la sortie — le `rescue` a joué), puis le **re-jeu du même chemin nommé**
([ADR 0045](0045-chemins-installation-banc-couches.md)) **réussit**. Tout écart
invalide la preuve (faute non prise, demi-état laissé sans compensation, reprise
insuffisante). C'est le pendant, pour la reprise, du gate `run_ansible_phase` :
la fonction pure `classify_compensation` (`test/lima/bootstrap-fault-assert.sh`,
testée hors banc) rend ce verdict, comme `classify_idempotence` rend celui de la
règle 2.

## Statut

Accepted. Principe-chapeau : ne remplace ni n'invalide aucun ADR ; il les
**nomme comme piliers** d'une même exigence et en tire des règles opposables.

## Conséquences

- **Gain** : un critère unique et nommé pour **refuser** un résultat (« non
  reproductible ») au lieu de quatre arguments épars. Les revues, la
  consignation et la CI s'y réfèrent.
- **Prix à payer** : prouver coûte plus que constater — un rejeu d'idempotence
  en plus, un **arrêt injecté** pour exercer chaque chemin de reprise, un run
  from-scratch là où un état bricolé « marchait », la discipline de consigner le
  commit. C'est le coût de la confiance, assumé (esprit
  [ADR 0034](0034-validation-e2e-from-scratch.md)).
- **Honnêteté des Runs** (déjà en vigueur,
  [ADR 0023](0023-plateforme-exemple-generique.md)) : on ne réécrit pas un
  résultat passé pour le rendre « propre » ; on consigne le réel, y compris les
  réserves (« aidé à la main », « à re-prouver from-scratch »).
- **Limite assumée** : la reproductibilité **exacte** d'un run de banc n'est pas
  garantie au bit près (horloge, latence réseau, ordonnancement) ; ce qui doit
  être reproductible, c'est le **verdict** (HEALTH_OK, `changed=0`, lineage
  ingéré), pas le chronométrage.
