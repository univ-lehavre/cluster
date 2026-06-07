# 0034 — La validation, c'est un run e2e from-scratch (pas le lint)

## Contexte

Le dépôt a une chaîne qualité statique solide (ansible-lint en profil
_production_, kubeconform, shellcheck, yamllint, bats, prettier, markdownlint,
garde-fou liens). Elle est **nécessaire mais pas suffisante** : le portage de la
couche plateforme DataOps en rôles Ansible (#173) passait **tous** ces contrôles
au vert, et pourtant le premier run réel sur banc a révélé **13 drifts en
cascade** (L21–L33) — modèle d'exécution depuis l'hôte, isolation du banc,
ressources, gates trop stricts, ordre de création. Aucun n'était visible au
lint.

Symétriquement, l'historique le montre : le bootstrap (#127, drifts L1–L11), la
chaîne DataOps en shell (#148, L12–L20), puis son portage Ansible (#173,
L21–L33) ont chacun nécessité **plusieurs runs successifs avec correctifs**
avant de passer. **Aucun composant n'a jamais fonctionné e2e du premier coup.**
C'est un fait structurel, pas un accident.

## Décision

**La preuve de validation d'une brique d'infra est un run e2e _from-scratch_ sur
banc, exécuté d'une traite et sans intervention manuelle — jamais le passage au
vert du lint seul.**

Concrètement :

1. **Seul un run from-scratch fait foi.** Un banc déjà monté masque les drifts
   d'ordre, de dépendance et de gate (ex. L25 namespace, L29 reboot, L33 gate
   RGW n'apparaissent qu'à froid). La validation se fait depuis `down` →
   séquence complète, sans toucher à rien entre les phases.
2. **Chaque phase est _gated_** (`retry … || die`) : le run s'arrête au premier
   critère non atteint. Un gate qui passe est une preuve exécutable ; un gate
   faux (trop strict / trop laxiste) est lui-même un drift à corriger (L7, L33).
3. **Tout drift est tracé et catégorisé** dans `RESULTS.md` (honnêteté des Runs,
   [ADR 0023](0023-plateforme-exemple-generique.md)) : symptôme, cause-racine,
   correctif. La synthèse transverse vit dans
   [`docs/architecture/lecons-des-runs.md`](../architecture/lecons-des-runs.md).
4. **Le run produit une preuve archivée** : log brut **générisé** sous
   `test/<banc>/runs/` + **métriques** (matériel hôte + temps par phase, émises
   par `run-phases.sh`). Un « ~15 min » sans matériel ni log n'est pas une
   preuve.
5. **Le lint reste obligatoire** — il est le filet bon marché qui attrape tôt le
   trivial. Mais « vert en CI » ne s'écrit jamais « validé » : seul le run le
   dit.

## Statut

Accepted.

## Conséquences

- **Gain** : la confiance est fondée sur une preuve reproductible, pas sur une
  promesse. La catégorisation des drifts (≈33 à ce jour) devient un savoir
  réutilisable — chaque nouveau terrain (cloud, x86…) part avec la liste des
  pièges connus.
- **Prix à payer** : un run e2e est lent (~30 min sur le banc Lima Ceph, cf.
  tableau de bord). D'où l'intérêt de **bancs plus rapides et ciblés** pour
  itérer (sujet distinct) — sans dispenser du run from-scratch avant de
  conclure.
- **Discipline** : ne jamais consigner « validé » sur la foi du lint. Si le run
  from-scratch d'une traite n'a pas été rejoué, le dire explicitement
  (RESULTS.md le précise quand c'est le cas).
- **Garde-fou méthodologique** : un run qui ne rencontre _aucun_ drift sur une
  brique neuve doit éveiller le soupçon (gates trop laxistes ?) autant qu'un run
  qui en cascade — les deux s'examinent.
