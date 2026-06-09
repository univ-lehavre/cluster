# 0046 — Corriger le code d'installation, pas l'état du cluster

## Contexte

[ADR 0034](0034-validation-e2e-from-scratch.md) pose que la **preuve** est un
run e2e from-scratch. Il reste un angle mort : **comment on réagit quand un run
révèle un problème**. La tentation, sur un banc déjà monté, est de réparer **à
chaud** — `kubectl patch`/`apply`, recréer un objet à la main, enchaîner des
phases manuellement — pour « faire avancer ». Ces gestes :

- ne **survivent pas** (perdus au prochain `down`),
- ne sont **pas tracés ni revus**,
- **masquent** la vraie cause dans le code d'installation (le manifeste, le rôle
  Ansible, le harnais), qui reste cassé,
- créent une **illusion de fonctionnement** : « ça marche sur le banc » alors
  que le code versionné, lui, échouera au prochain run.

Symétriquement, **enchaîner les phases à la main** (au lieu d'un chemin
d'installation **codé**) reproduit les erreurs d'ordre que le chemin nommé évite
par construction (ex. lancer `monitoring` avant `datalake` en mode Ceph → Loki
sans backing S3). L'ordre correct existe **dans le code** ; le contourner à la
main, c'est rejouer un bug déjà résolu.

Ces deux dérives ont été observées en construisant le banc atlas (sessions #230
à #232) : des `kubectl patch` répétés pour débloquer Argo CD/Gitea, et un
montage phase-par-phase qui a sauté une dépendance — alors que le fix
appartenait au code et que le chemin codé l'ordonnait correctement.

## Décision

**Le code d'installation est la seule source de vérité ; on l'éprouve et on le
corrige. Les interventions manuelles sur le cluster sont réservées au
DIAGNOSTIC, jamais au correctif durable.**

1. **`kubectl patch`/`apply`/`create` manuel = diagnostic ou déblocage
   EXPLORATOIRE seulement.** Dès que la cause est comprise, le correctif repart
   **dans le code versionné** (manifeste `platform/`, rôle `bootstrap/roles/`,
   harnais `test/lima/`), puis est **re-prouvé par un run** (ADR 0034). Un fix
   qui ne vit que dans l'état du cluster n'est pas un fix.
2. **Le banc se monte par un CHEMIN nommé codé**
   (`socle`/`atlas`/`storage-real`/ `cluster-dataops`/`atlas-ceph`,
   [ADR 0045](0045-chemins-installation-banc-couches.md)), **jamais** en
   enchaînant des phases à la main. L'ordre et les dépendances inter-phases sont
   une propriété du code, pas de l'opérateur. Si un enchaînement utile n'a pas
   de chemin, **on code le chemin** (on ne le tape pas).
3. **Le profil se propage par le code.** Une phase ne code pas en dur une valeur
   propre à un profil (ex. `gitea_storage_class=local-path`) : elle la
   **dérive** du profil du banc (`WITH_CEPH`/`WITH_HARDENING`), comme les autres
   phases. Une valeur de profil codée en dur est un bug (PVC `local-path` sur un
   banc Ceph → Pending).
4. **Tout drift révélé → corrigé dans le code + consigné**
   (`registre-drifts.yaml`, RESULTS, honnêteté des Runs ADR 0023/0042). Le geste
   manuel qui a servi au diagnostic n'est pas la solution : il est remplacé par
   le correctif versionné.

## Statut

Accepted.

## Conséquences

- **Gain** : ce qui marche sur le banc marche aussi au prochain run from-scratch
  (et en prod), parce que la correction vit dans le code éprouvé. Plus de « ça
  marchait pourtant hier » lié à un patch volatil.
- **Discipline (agent et humain)** : devant un run cassé, l'ordre est —
  diagnostiquer (lecture, éventuellement patch jetable pour isoler) → **corriger
  le code** → re-prouver par un run via le chemin nommé. Ne jamais s'arrêter à «
  débloqué à la main ».
- **Prix à payer** : corriger le code puis relancer un run est plus lent qu'un
  patch à chaud. C'est assumé : la lenteur est le coût de la reproductibilité
  (ADR 0034). Pour itérer vite, on raccourcit le banc (chemins légers), pas la
  rigueur.
- **Lien ADR 0034** : 0034 dit _quoi_ prouve (le run from-scratch) ; 0046 dit
  _comment réagir_ quand il échoue (corriger le code, pas l'état). Les deux se
  complètent.
- **Cas limite** : un déblocage manuel reste permis **pour finir un diagnostic**
  (ex. confirmer qu'une NetworkPolicy est la cause), mais il est suivi du
  correctif versionné dans la même session — jamais laissé comme état final «
  validé ».
