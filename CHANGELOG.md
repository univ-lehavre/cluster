# Changelog

Toutes les modifications notables sont documentées ici. Ce fichier suit le
format [Keep a Changelog](https://keepachangelog.com/) et les versions
respectent [SemVer](https://semver.org/).

Les entrées sont générées automatiquement à partir des messages de commit
[Conventional Commits](https://www.conventionalcommits.org/) via
[release-please](https://github.com/googleapis/release-please) : un cron
quotidien dépose (ou met à jour) une PR `chore(main): release vX.Y.Z` qui agrège
les commits depuis la dernière release. Merger cette PR publie la version (bump +
tag + entrée de changelog). Rien à lancer en local.

## [2.52.0](https://github.com/univ-lehavre/cluster/compare/v2.51.0...v2.52.0) (2026-07-06)


### Features

* **preview:** détecte le drift de digest topo vs manifeste déployé ([35c6d8f](https://github.com/univ-lehavre/cluster/commit/35c6d8ff877c17e0afae0fdf7ba8e2ae57973135))
* **preview:** détecte le drift de digest topo vs manifeste déployé ([4990813](https://github.com/univ-lehavre/cluster/commit/4990813f5bfed0432f0681c92c023efd9cb6ca1f))
* **resources:** borne cert-manager et argo cd par patch hors-bundle ([619c6bd](https://github.com/univ-lehavre/cluster/commit/619c6bd1a921fd0813d5734879115f640dfe4a54))
* **resources:** borne cert-manager et argo cd par patch hors-bundle ([d5c1232](https://github.com/univ-lehavre/cluster/commit/d5c1232d80f8f13bc7f794e6b0f08e5348050123))
* **resources:** pose les requests/limits manquants (pg, rgw, nats, kong, mariadb) ([6b289ba](https://github.com/univ-lehavre/cluster/commit/6b289bab243900bd89aac1a9e918f3533cb06449))
* **resources:** pose les requests/limits manquants (pg, rgw, nats, kong, mariadb) ([f9edf8f](https://github.com/univ-lehavre/cluster/commit/f9edf8f75aa74848b964bd8df1951042ed4b596c))


### Bug Fixes

* **bootstrap:** relève fs.inotify.max_user_instances (128 → 8192) ([862d139](https://github.com/univ-lehavre/cluster/commit/862d139999c906e61b2bac67f37f4b47ce25cde2))
* **bootstrap:** relève fs.inotify.max_user_instances (128 → 8192) ([fc44f4e](https://github.com/univ-lehavre/cluster/commit/fc44f4e441dae552aae35954683007e121b5507e))
* **docs:** retire l'ancre custom non supportée par starlight (build CI) ([6f5c721](https://github.com/univ-lehavre/cluster/commit/6f5c721bbb68fbb3dd1357ed5d02d112bb4a39cf))
* **etcd:** rend etcd-fetch jouable (gather_facts requis par l'audit-log) ([4848ac4](https://github.com/univ-lehavre/cluster/commit/4848ac413b514245e66465b9cabb4ec91ece7fff))
* **etcd:** rend etcd-fetch jouable (gather_facts requis par l'audit-log) ([d98cb66](https://github.com/univ-lehavre/cluster/commit/d98cb666f6b24d0723e18adb36e95d94e82aa9c9))
* **monitoring:** matérialise les plafonds prometheus 3gi / grafana 512mi ([0d3da94](https://github.com/univ-lehavre/cluster/commit/0d3da949379711a2bcc60ac9719b9b63667e868c))
* **monitoring:** matérialise les plafonds prometheus 3gi / grafana 512mi ([669ac52](https://github.com/univ-lehavre/cluster/commit/669ac524ca4ef2a9031479cd636d4e83a4632f02))


### Documentation

* **adr:** doctrine de preuve à deux étages (banc-logique / prod-intégration, 0104) ([239dd3b](https://github.com/univ-lehavre/cluster/commit/239dd3b20b80ec27895570e8ec748b04a8be7a41))
* **adr:** doctrine de preuve à deux étages (banc-logique / prod-intégration, 0104) ([3ce26e2](https://github.com/univ-lehavre/cluster/commit/3ce26e2d787670ff22e75eeb4ee94cb4b7e180bc))
* **architecture:** décrit la progression réelle des données (chaîne applicative citation) ([2ad5af3](https://github.com/univ-lehavre/cluster/commit/2ad5af3ea8f56dfbccd873a326c1c21a27daafd0))
* **architecture:** progression réelle des données (chaîne applicative citation) ([ab25497](https://github.com/univ-lehavre/cluster/commit/ab25497befd24de8cf4d1f0b62c158918ac6afae))
* **audit:** consigne pourquoi l'alerte inotify runtime n'est pas faite ([3eca046](https://github.com/univ-lehavre/cluster/commit/3eca046835b1af8316c0fd26ddcafb3f1ddaa7be))
* **audit:** consigne pourquoi l'alerte inotify runtime n'est pas faite ([2aebaf7](https://github.com/univ-lehavre/cluster/commit/2aebaf75391031dfc28f8df667a74ce20921a4fc))
* **audit:** incident dirqual1 (inotify) & risques d'un passage HA à chaud ([1fbdba6](https://github.com/univ-lehavre/cluster/commit/1fbdba6620705402ab2eae44208de690bf9b1780))
* **audit:** incident dirqual1 (inotify) & risques d'un passage HA à chaud ([1172f6c](https://github.com/univ-lehavre/cluster/commit/1172f6c2ac6e0b9ceb87a49fc15c9060ef1809ba))
* **audit:** passages datés de la mise en route citation E2E sur prod (2026-07-05) ([84983ce](https://github.com/univ-lehavre/cluster/commit/84983ce2e91128f5d4c8e6d967ae2fd39f7cf885))
* **audit:** passages datés de la mise en route citation E2E sur prod (2026-07-05) ([9826ff3](https://github.com/univ-lehavre/cluster/commit/9826ff3e8db0a67b730115c5e66e192ddda0c7a6))
* **audit:** requests/limits, volet code-first ([21a5dfd](https://github.com/univ-lehavre/cluster/commit/21a5dfd985793b0fab7fcb12ba2f0432508c1a57))
* **audit:** requests/limits, volet code-first (ce que le dépôt déclare) ([683cace](https://github.com/univ-lehavre/cluster/commit/683cace1b3764797c4f273add6245782f6417492))
* **drift:** consigne L73 — gel prod dirqual1 par épuisement inotify ([6842b09](https://github.com/univ-lehavre/cluster/commit/6842b09e0572739715147f5baed5945cb4eea06d))
* **drift:** consigne L73 — gel prod dirqual1 par épuisement inotify ([fc9fb81](https://github.com/univ-lehavre/cluster/commit/fc9fb810fe6499757b534db1a6a4ddba33a62a37))
* **drift:** consigne L74/L75 + audit ge_raw_contract (amplification ndots) ([48d5490](https://github.com/univ-lehavre/cluster/commit/48d54905a4d93971034be66959a01631f2c3b354))
* **drift:** consigne L74/L75 + audit ge_raw_contract (amplification ndots) ([54769f7](https://github.com/univ-lehavre/cluster/commit/54769f7e3473ff83ae0c11a4716867b7b5cbbc88))
* **plan:** coche cert-manager/argocd + prometheus dans le plan right-sizing ([0e68abe](https://github.com/univ-lehavre/cluster/commit/0e68abea9e362535b0ef095d9abf262f7d55d29b))
* **readme:** régénère le bloc STATS après L73 (73 → 74 drifts) ([892f9d2](https://github.com/univ-lehavre/cluster/commit/892f9d29cbcb7283e5e7ed7f4848b122f95c5ff8))

## [2.51.0](https://github.com/univ-lehavre/cluster/compare/v2.50.0...v2.51.0) (2026-07-05)


### Features

* **eventful:** rend la chaîne événementielle déployable sur dirqual (overlay prod + seed prod multi-CL) ([9309ff9](https://github.com/univ-lehavre/cluster/commit/9309ff9046629a8a43462e417c9b59c34d74f04b))
* **nestor:** câble le seed prod app-of-apps multi-code-location (ADR 0095 §1.b) ([bea1d8e](https://github.com/univ-lehavre/cluster/commit/bea1d8e35988db78f4a019398b74ddcda89f001b))
* **portal:** dérive PORTAL_ACCESS_HOST du bloc portal.access_host de la topo ([e687c9c](https://github.com/univ-lehavre/cluster/commit/e687c9c24b22914e64232aa79e1b95436ba5617e))
* **portal:** dérive PORTAL_ACCESS_HOST du bloc portal.access_host de la topo ([7636351](https://github.com/univ-lehavre/cluster/commit/763635119cdb8cab1cb5638f6e3ebf0832e6944d))


### Bug Fixes

* **citation:** installe rsync node-side avant le synchronize du projet dbt ([cf23701](https://github.com/univ-lehavre/cluster/commit/cf237014c3944db0f0ea90e316337a44198172d7))
* **cnpg:** egress RGW manquant (cause racine) + headroom WAL 500Gi + rétention 30d ([9a96b85](https://github.com/univ-lehavre/cluster/commit/9a96b8565bab7c31560c55a979d64266478b86f2))
* **eventful:** 2 blocages du déploiement prod dirqual (rsync build + nodeAffinity builder) ([45f84de](https://github.com/univ-lehavre/cluster/commit/45f84de20d5b8c38079992c27f2e1ef005f09473))
* **eventful:** builder sur worker via nodeAffinity DoesNotExist (pas nodeSelector) ([972c54e](https://github.com/univ-lehavre/cluster/commit/972c54e3f0e30d0dd1fbf109444643e57bf5a155))
* **eventful:** dérive l'overlay du write-back selon le target_kind (bench/prod) ([0cd490a](https://github.com/univ-lehavre/cluster/commit/0cd490a0539fc2b1f2427d300f38675c2d8c7d8d))
* **nestor:** seed push-atlas-tree — `checkout -B` au lieu de `branch -f` ([ab15767](https://github.com/univ-lehavre/cluster/commit/ab157673b19e0f3a48d9e0cf6b0bccbbda2657b6))
* **nestor:** seed push-atlas-tree — checkout -B au lieu de branch -f ([60cf7d9](https://github.com/univ-lehavre/cluster/commit/60cf7d967b37cce96384e383536b2d4a33483f81))
* **nestor:** seed push-atlas-tree — commite la substitution + targetRevision suit main ([5c1d112](https://github.com/univ-lehavre/cluster/commit/5c1d112114fd76a93bbf9d85a2685aeb8821ac09))
* **platform:** relève les limites mémoire OOM du socle ([0befd75](https://github.com/univ-lehavre/cluster/commit/0befd7510c0b145f0dd2f56f2a3bbe68fdbcc2b3))
* **platform:** relève les limites mémoire OOM du socle ([0b2da66](https://github.com/univ-lehavre/cluster/commit/0b2da66474ab14676a942b14ad41e0d73bce38b8))
* **portal:** host des liens configurable via PORTAL_ACCESS_HOST ([1e23083](https://github.com/univ-lehavre/cluster/commit/1e23083d4b56130632dfff273791e619d538cd11))
* **portal:** host des liens configurable via PORTAL_ACCESS_HOST ([dde263b](https://github.com/univ-lehavre/cluster/commit/dde263ba0d877c7d9a4fe11503e353ce00b75b8b))


### Documentation

* **citation:** renseigne l'ORCID de l'auteur ([e985089](https://github.com/univ-lehavre/cluster/commit/e985089e7f811ac549d0edc4b06b761f5d64a7cb))
* **citation:** renseigne l'ORCID de l'auteur ([58f6a6b](https://github.com/univ-lehavre/cluster/commit/58f6a6bde7bd32789394361841a3f9ac88c54d22))
* **citation:** synchronise la version de CITATION.cff via release-please ([cd192c4](https://github.com/univ-lehavre/cluster/commit/cd192c4eb760850bc47aa275355d816c5a816abd))
* **citation:** synchronise version CITATION.cff via release-please ([39d3c8a](https://github.com/univ-lehavre/cluster/commit/39d3c8a0a9499278311de673712934d4e90a7d5c))

## [2.50.0](https://github.com/univ-lehavre/cluster/compare/v2.49.0...v2.50.0) (2026-07-04)


### Features

* **dagster:** reconciler du workspace multi-code-location (ADR 0103) ([38d49e8](https://github.com/univ-lehavre/cluster/commit/38d49e8b255a6777e843e4e6cdaeeef2d40fbe64))
* **dagster:** reconciler du workspace multi-code-location (ADR 0103) ([7d7fde7](https://github.com/univ-lehavre/cluster/commit/7d7fde74b833a8a367ccca92e18109f352b3f002))
* **eventful:** câble le filet event-loss builder-reconcile ([#565](https://github.com/univ-lehavre/cluster/issues/565), ADR 0095) ([b536726](https://github.com/univ-lehavre/cluster/commit/b53672623075e0d8ec88e8b55f6aabec8f3b870b))
* **eventful:** câble le filet event-loss builder-reconcile ([#565](https://github.com/univ-lehavre/cluster/issues/565)) ([b78d544](https://github.com/univ-lehavre/cluster/commit/b78d544d97352be4725145682bdac246e4aa5fb2))
* **nestor:** enregistre platform-eventful comme Component du graphe ([#564](https://github.com/univ-lehavre/cluster/issues/564)) ([fdebb0a](https://github.com/univ-lehavre/cluster/commit/fdebb0a9e4aaa6e83e1da790820eca0578e51dfb))
* **nestor:** enregistre platform-eventful comme Component du graphe atomique ([#564](https://github.com/univ-lehavre/cluster/issues/564), ADR 0096) ([0703bcc](https://github.com/univ-lehavre/cluster/commit/0703bccc28ba3f50e09ee9764a2b8fcf6d3be627))


### Bug Fixes

* **dagster:** migre la code-location jouet aux fragments de workspace (ADR 0103) ([ee85c62](https://github.com/univ-lehavre/cluster/commit/ee85c626f282f692bb8855d809dd21b82998abc4))
* **dagster:** migre la code-location jouet aux fragments de workspace (ADR 0103) ([c5cee6a](https://github.com/univ-lehavre/cluster/commit/c5cee6ac1ace821cd6e3881039cca02c9cdbde0c))
* **eventful:** chaîne de build événementiel verte e2e au banc (zéro-geste prouvé) ([a0f58e2](https://github.com/univ-lehavre/cluster/commit/a0f58e28b6ba788dcf6c1f571d41aa8b83cec5f4))


### Documentation

* **eventful:** reformule pour éviter [#2](https://github.com/univ-lehavre/cluster/issues/2) en début de ligne (markdownlint MD018 CI) ([fdcccf3](https://github.com/univ-lehavre/cluster/commit/fdcccf3b1aba1c4fd06020636cd94ae96c5a8c0a))

## [2.49.0](https://github.com/univ-lehavre/cluster/compare/v2.48.0...v2.49.0) (2026-07-03)


### Features

* **banc:** intègre la chaîne événementielle au banc air-gappé ([93470e7](https://github.com/univ-lehavre/cluster/commit/93470e73358d491994d4c2e2b6f2b5a603a204eb))
* **banc:** intègre la chaîne événementielle au banc air-gappé (mirror + patch + webhook[#2](https://github.com/univ-lehavre/cluster/issues/2)) ([cef9c8a](https://github.com/univ-lehavre/cluster/commit/cef9c8ae07f7441d9caf2510034e360437d81479))
* **bootstrap:** build citation (D3) + plan détaillé de la cible événementielle ([412bb45](https://github.com/univ-lehavre/cluster/commit/412bb45afd09b1327b439626268d46ec3352e0cf))
* **bootstrap:** layer citation — build node-side de l'image applicative (D3) ([2ad75a0](https://github.com/univ-lehavre/cluster/commit/2ad75a0b4bcbfabc7c81ee185a0c65a62bfb30c5))
* **bootstrap:** play de build générique par code-location (mediawatch) ([e6b3fa3](https://github.com/univ-lehavre/cluster/commit/e6b3fa331e1fc49d947f557c404d84320f242ea5))
* **bootstrap:** rôle platform-eventful — monte la chaîne événementielle (ADR 0046) ([89009d3](https://github.com/univ-lehavre/cluster/commit/89009d326ade18ff9bdfae78ce57e0e7c90c36d7))
* **bootstrap:** rôle platform-eventful — monte la chaîne événementielle (ADR 0046) ([8f3a92a](https://github.com/univ-lehavre/cluster/commit/8f3a92ae316694d16c6d8b7a6cc16f484bba00f5))
* **nestor:** câble le hook e2e dataops_egress_internet_check (portage bash prouvé) ([1d8c026](https://github.com/univ-lehavre/cluster/commit/1d8c02636918de4c548335512c2eb1be46505b13))
* **nestor:** câble le hook e2e dataops_egress_internet_check (portage bash prouvé) ([5f5c864](https://github.com/univ-lehavre/cluster/commit/5f5c86404e13306e9239fe39b38906a747822f77))
* **nestor:** façade seed banc-citation — publication du digest citation (§1.a) ([7737d7e](https://github.com/univ-lehavre/cluster/commit/7737d7e0f37197c3da7ff47f404dd0381178ba2b))
* **nestor:** logique pure du seed citation (substitution digest + rendu déclaration) ([f228a1d](https://github.com/univ-lehavre/cluster/commit/f228a1db25dbf460ed0f409825d1ec9bb6682855))
* **nestor:** publication du digest citation par le seed banc-citation (§1.a) ([c3cebb8](https://github.com/univ-lehavre/cluster/commit/c3cebb8ba798a2ac8883828ea0972404100f2912))
* **nestor:** rend citation + gitops-seed-citation montables (graphe/layers) ([691c499](https://github.com/univ-lehavre/cluster/commit/691c4991be054aedfe2816274f0276a653c01990))
* **nestor:** seed + build multi-code-location (débloque mediawatch) ([c21fde6](https://github.com/univ-lehavre/cluster/commit/c21fde6f0b2f6ec8d5488b8557f45938784f169d))
* **nestor:** seed multi-code-location (citation + mediawatch), rétrocompat ([357d065](https://github.com/univ-lehavre/cluster/commit/357d06561288212c8ec4b4ee0807b82b9b11c910))
* **nestor:** variante de seed banc-citation (flux prod joué au banc, garde banc) ([519a073](https://github.com/univ-lehavre/cluster/commit/519a073b576945a673c6c2005094fb6d432b21ec))
* **nestor:** variante de seed banc-citation + révision du plan build-gitops ([d567632](https://github.com/univ-lehavre/cluster/commit/d567632a096f72e284894f7e4ca28e1adfb57114))
* **platform:** builder buildkit-in-pod + egress build (cible §1.b étape 6) ([aa0f3d8](https://github.com/univ-lehavre/cluster/commit/aa0f3d8adb9107f4919547adf51faeafae607d46))
* **platform:** chaîne de découverte Argo Events (cible §1.b étape 7) ([bd572da](https://github.com/univ-lehavre/cluster/commit/bd572da75b99c55e8bd2fc1a1bd9db0e0d0cf47d))
* **platform:** vendore Argo Workflows + Argo Events (cible événementielle, étape 5) ([bfaee26](https://github.com/univ-lehavre/cluster/commit/bfaee26fff66eb57145af7396af5eca2300c9e35))
* **platform:** vendore Argo Workflows v4.0.6 + Argo Events v1.9.10 (cible §1.b étape 5) ([5907016](https://github.com/univ-lehavre/cluster/commit/5907016bc3edf7dc235712d7ca827e6c34625715))


### Bug Fixes

* **banc:** citation-dbt copié en rsync sans logs/target (build bloqué au banc) ([aadd050](https://github.com/univ-lehavre/cluster/commit/aadd050253963c7fde32fdf8f6450fa3c7bb2c1c))
* **banc:** eventful-mirror — become root + scalar à plat (prouvé au banc) ([58608b3](https://github.com/univ-lehavre/cluster/commit/58608b35b12941884a007a0c82a9236205ffd6f1))
* **banc:** seed citation vise overlay bench + port gitea dérivé (prouvés au banc) ([14824b7](https://github.com/univ-lehavre/cluster/commit/14824b75b039def85bd8ca517339696c634e2638))
* **bench:** scénario 28 sonde les UI via port-forward (default-deny) + set -e ([8a184aa](https://github.com/univ-lehavre/cluster/commit/8a184aa2f167b04a129081ba3a242461c9813bb9))
* **bench:** scénario 31 sonde postgres depuis un ns autorisé (NetworkPolicy) ([c9d4c27](https://github.com/univ-lehavre/cluster/commit/c9d4c27b7507a5e22a5493165867d0da6529f58f))
* **bench:** scénario 31 sonde postgres depuis un ns autorisé (NetworkPolicy) ([af36c5c](https://github.com/univ-lehavre/cluster/commit/af36c5cacfd8a6a4ca85a664f3d997f6e40ddcf4))
* **eventful:** déblocage du déclenchement webhook [#2](https://github.com/univ-lehavre/cluster/issues/2) (PROUVÉ zéro-geste au banc) ([7fb0e79](https://github.com/univ-lehavre/cluster/commit/7fb0e79d4521e1763712c657e689b89e9bfda945))
* **eventful:** débloque le déclenchement webhook [#2](https://github.com/univ-lehavre/cluster/issues/2) (zéro-geste prouvé au banc) ([0f26be4](https://github.com/univ-lehavre/cluster/commit/0f26be40294d359e73a30ee6bd4900e090851c00))
* **nestor:** askpass en 0o700, pas 0o755 (alerte CodeQL high) ([0661236](https://github.com/univ-lehavre/cluster/commit/0661236c88aee67c8ad5920fc2c771b2f3bda605))
* **nestor:** down supprime le kubeconfig de la stack (plus de résidu poison) ([8892de0](https://github.com/univ-lehavre/cluster/commit/8892de0a0e2f026752dfcfe5b5b80e6124d8a712))
* **nestor:** down supprime le kubeconfig de la stack (plus de résidu poison) ([fa8cfdc](https://github.com/univ-lehavre/cluster/commit/fa8cfdcaced0ad29b54c6f29b3fe848a75e4f7c0))


### Documentation

* **argo-events:** liens .py en URL GitHub, pas URL site (docs:build) ([a07750d](https://github.com/univ-lehavre/cluster/commit/a07750d4d060f56f8bce8cff439e0a541824c6d8))
* build vert (221 pages, 0 lien invalide), markdownlint/orphans/STATS/drifts OK. ([f3c883c](https://github.com/univ-lehavre/cluster/commit/f3c883c5d327a8eeb628eed500b3d04b02d96c05))
* consigne la preuve banc citation + documente le build événementiel ([f3c883c](https://github.com/univ-lehavre/cluster/commit/f3c883c5d327a8eeb628eed500b3d04b02d96c05))
* **contrat:** aligne contrat + guide dev-atlas + portail sur la chaîne événementielle ([2616252](https://github.com/univ-lehavre/cluster/commit/261625277be27f97945ce3ccf7c01598b23505a4))
* **contrat:** aligne contrat/guide/portail sur la chaîne événementielle ([e53c8ec](https://github.com/univ-lehavre/cluster/commit/e53c8ec4c5824b7e290e80d98285b83e3b6af7d5))
* **plan:** détaille la cible événementielle (étapes 5-8, zéro geste) ([8ed179a](https://github.com/univ-lehavre/cluster/commit/8ed179ac3d2414a23ffd3e9892509b32bd4c86b6))
* **plan:** révise le plan build-gitops pour la bascule citation réelle au banc ([94672ea](https://github.com/univ-lehavre/cluster/commit/94672eaa554719992c48c81370ba50936eac546a))
* **platform:** rend argo-workflows/ + argo-events/ atteignables (ADR 0029) ([5393f4e](https://github.com/univ-lehavre/cluster/commit/5393f4e0776c064b32441025a645c39cdcdb9c53))
* preuve banc citation + composants événementiels (MAJ complète doc) ([46a4c71](https://github.com/univ-lehavre/cluster/commit/46a4c71e4737ec8e0df8da8d3d957bd2a833fdcc))

## [2.48.0](https://github.com/univ-lehavre/cluster/compare/v2.47.0...v2.48.0) (2026-07-02)


### Features

* **contract:** valider le manifeste de déclaration montant atlas→cluster ([b8d4a91](https://github.com/univ-lehavre/cluster/commit/b8d4a91e77d3f11cc75f3ac06318f72dbdff589f))
* frontière atlas — ADR 0094 accepté, validateur de manifeste, déblocage [#533](https://github.com/univ-lehavre/cluster/issues/533) ([45c4372](https://github.com/univ-lehavre/cluster/commit/45c43728875ca39caacf58fa746d490d52066bcf))
* **nestor:** amorce le câblage record — chrono des phases + module runrecord ([c58af24](https://github.com/univ-lehavre/cluster/commit/c58af247e3bc2360ebb1ff7290b430ddc369de31))
* **nestor:** câble la consignation record d'un run réussi ([#216](https://github.com/univ-lehavre/cluster/issues/216), ex-metrology.sh) ([659bd91](https://github.com/univ-lehavre/cluster/commit/659bd91c0fd4d9e39caf64297345d9cacfad9285))
* **nestor:** consigne un run réussi dans runs-history (SHA + durées, [#216](https://github.com/univ-lehavre/cluster/issues/216)) ([495bcf3](https://github.com/univ-lehavre/cluster/commit/495bcf3b0ebf0a4a09af4097e63af00cc804e834))
* **nestor:** dérive ceph_metadata_device du disque role=metadata déclaré (ADR 0102) ([d84abdd](https://github.com/univ-lehavre/cluster/commit/d84abdd33ccd70e7b86d05df92ffa8dddd7aba92))
* **nestor:** dérive osd_expected des disques role=data déclarés (ADR 0102) ([4d02784](https://github.com/univ-lehavre/cluster/commit/4d027845f2cace809b4af4ab2cbfe697bbaafc26))
* **nestor:** la topo déclare ses disques par nœud (DiskSpec, ADR 0102 volet C1) ([2d64abf](https://github.com/univ-lehavre/cluster/commit/2d64abf004f0b2677c3e180aaba4093975aa55fb))
* **nestor:** provisioning par nœud piloté par la topo (ADR 0102 volet C2+C3) ([799f09f](https://github.com/univ-lehavre/cluster/commit/799f09f93d7432d20b22aac5fd5bd009e14cafa1))
* **nestor:** remove retire les StorageClass cluster-scoped de la couche (par provisioner) ([9aa6672](https://github.com/univ-lehavre/cluster/commit/9aa6672cca24f015af3dc4b82a116d829418dfff))


### Bug Fixes

* **ceph:** libère les LV/VG Ceph avant le wipe node-side (blkdiscard busy) ([6e1166b](https://github.com/univ-lehavre/cluster/commit/6e1166bdf338da9b89ce6958e311f6b2ce07c527))
* **ceph:** libère les LV/VG Ceph avant le wipe node-side (blkdiscard busy) ([b02f207](https://github.com/univ-lehavre/cluster/commit/b02f207e27cc1607bca7a5ad12d1863fd4f7cb60))
* **nestor:** dérive le wipe node-side Ceph des disques déclarés (bug vde=cidata) ([29f13b1](https://github.com/univ-lehavre/cluster/commit/29f13b16382850809ea8a2311b4db461cab648f2))
* **nestor:** destroy passe NODES_OVERRIDE au down (sinon les disques survivent) ([6c935e1](https://github.com/univ-lehavre/cluster/commit/6c935e1aceadde67b427ae5003ace93da8e0c056))
* **nestor:** écarte un KUBECONFIG poison (/dev/null, vide) des phases du montage ([889fb21](https://github.com/univ-lehavre/cluster/commit/889fb21d93dd672851b2d4c7d9888a6ee891b080))
* **nestor:** kubectl passe un flag en tête (-n) au lieu de « unrecognized » ([b91c4f7](https://github.com/univ-lehavre/cluster/commit/b91c4f76b422278c38bed99411470b6f25840fd0))
* **nestor:** kubectl passe un flag en tête (-n) au lieu de « unrecognized » ([9f42b40](https://github.com/univ-lehavre/cluster/commit/9f42b40ab82cbb1b1aca6412b64965ae695ec9ff))
* **nestor:** wipe node-side Ceph dérivé de la topo + remove des StorageClass cluster-scoped ([0d694d7](https://github.com/univ-lehavre/cluster/commit/0d694d796d1e447ef5e5b32c2973d078aad3b358))
* **topologies:** ceph.example disque système à 40GiB (20 sature → DiskPressure) ([83b53fd](https://github.com/univ-lehavre/cluster/commit/83b53fdb55f936404945041ba324cd731b9a4f5d))


### Refactor

* catalogue de topologies v2 — la topo, source unique (ADR 0102) ([ab3370a](https://github.com/univ-lehavre/cluster/commit/ab3370a87380991021c48711e16322c5e972b0c0))
* **nestor:** fonction unique de résolution kubeconfig, in-repo (ADR 0102 volet B1) ([545d455](https://github.com/univ-lehavre/cluster/commit/545d455de64deec0afa6c8cc1e87c9bad641e0d5))
* **nestor:** identité de stack = nom de fichier de la topo (ADR 0102 volet B) ([d433c90](https://github.com/univ-lehavre/cluster/commit/d433c90e82216f98fc183096355e02eb4a1b52c7))
* **nestor:** kubeconfig banc dans .kubeconfigs/banc.config (ADR 0102 volet B2+B3) ([fc3332e](https://github.com/univ-lehavre/cluster/commit/fc3332ecd25c86549f736093d3cfe08d15c8918c))
* **nestor:** retire BANC_JETABLE et le repli rollback mort de roundtrip ([341161d](https://github.com/univ-lehavre/cluster/commit/341161d767b11cc849749c92c38588eb743e99ed))
* **nestor:** retire BANC_JETABLE et le repli rollback mort de roundtrip ([ec500d0](https://github.com/univ-lehavre/cluster/commit/ec500d0738c6bf6acb8bc1427f1f94ca904ffeeb))
* **nestor:** retire l'except vide de _operator_kubeconfig (alerte CodeQL) ([e4a36eb](https://github.com/univ-lehavre/cluster/commit/e4a36eb3ee7fe73ff7b29c318e1898ecf98c36cd))
* **nestor:** retire l'except vide de host_model (alerte CodeQL) ([245557b](https://github.com/univ-lehavre/cluster/commit/245557b812c05ad89e8a928ccd60c96e1c4a759d))
* **nestor:** rollback 100% Python — supprime rollback-lib.sh (ADR 0101 étape 5) ([d828051](https://github.com/univ-lehavre/cluster/commit/d828051a2d85862ced65b15a920a2e070b20f909))
* **topologies:** renomme banc.yaml en banc.example.yaml (ADR 0102 volet A) ([05822ab](https://github.com/univ-lehavre/cluster/commit/05822ab869bbb496ab534dfe07665ea2980658a3))


### Documentation

* **adr:** passer l'adr 0094 (frontière de déploiement) en accepted ([e0cebea](https://github.com/univ-lehavre/cluster/commit/e0cebea03fc33e6f8b5c94db548f368d566351c2))
* **adr:** tracer la contrainte de chaîne dbt pour débloquer [#533](https://github.com/univ-lehavre/cluster/issues/533) ([57ae08b](https://github.com/univ-lehavre/cluster/commit/57ae08b50a66d31b9782a2de242a8c08c2530a5a))
* **bench:** consigne la preuve banc du remove ceph par découverte ([#372](https://github.com/univ-lehavre/cluster/issues/372)/[#389](https://github.com/univ-lehavre/cluster/issues/389)) ([49136ad](https://github.com/univ-lehavre/cluster/commit/49136ada28151eba02bc64baeb12534e84ff13b4))
* **bench:** preuve banc du remove ceph par découverte (ferme [#372](https://github.com/univ-lehavre/cluster/issues/372)/[#389](https://github.com/univ-lehavre/cluster/issues/389)) ([9803e83](https://github.com/univ-lehavre/cluster/commit/9803e83c91c89e38cda0fc15d90ae1c547589366))
* **gouvernance:** pose l'ADR 0102 catalogue de topologies v2 (topo = source unique) ([be1ba58](https://github.com/univ-lehavre/cluster/commit/be1ba582dbf2ecc64b9a15b679c5045d88aed12e))
* **readme:** ajouter une section sécurité dédiée ([b2890e1](https://github.com/univ-lehavre/cluster/commit/b2890e171b164a222306253f467b9927db94b37b))
* section sécurité dédiée dans le README ([1aa6c2a](https://github.com/univ-lehavre/cluster/commit/1aa6c2a11b8284b12731f87625c9f160f405f53b))
* **security:** corriger l'état obsolète du chiffrement etcd et de l'audit-policy ([acc243d](https://github.com/univ-lehavre/cluster/commit/acc243d5cfb77a68bf742e3788bc783ec64e8a3e))
* **topologies:** aligne banc.example et ceph.example sur ADR 0102 (fin d'alignement) ([8030ef8](https://github.com/univ-lehavre/cluster/commit/8030ef8b78bd2eef75a9d49740db306966807f96))
* **topologies:** audit de cohérence du catalogue (ADR 0102/0092/0052) ([293c047](https://github.com/univ-lehavre/cluster/commit/293c047c0f0d5ae90b3b56ed3bbabfdeeb00da28))
* **topologies:** clarifie resources.disk (disque système) vs nodes[].disks (bruts Ceph) ([ce7fa8a](https://github.com/univ-lehavre/cluster/commit/ce7fa8a651aa90849fa41e50a7f03777e7f9c3f3))

## [2.47.0](https://github.com/univ-lehavre/cluster/compare/v2.46.0...v2.47.0) (2026-07-01)


### Features

* acte le périmètre os & architecture (windows→wsl) + ferme le risque crlf ([a80aae4](https://github.com/univ-lehavre/cluster/commit/a80aae4eca31d49f972584c9633ecce58ae85af6))
* **bootstrap:** garde audit-log sur tous les plays distants nus (défense en profondeur, ADR 0053) ([c30ae3b](https://github.com/univ-lehavre/cluster/commit/c30ae3bcd5969d0e519e8d6cc16bc7e7ffbb7e08))
* **bootstrap:** garde audit-log sur tous les plays distants nus (défense en profondeur) ([22f2d0c](https://github.com/univ-lehavre/cluster/commit/22f2d0c58a3ad5ee1c07d08d8fa65c73a5e29cd1))
* **nestor:** commande nestor ansible &lt;playbook&gt; — inventaire dérivé (ADR 0098) ([45f3a94](https://github.com/univ-lehavre/cluster/commit/45f3a944ce31967e89b9192df7dba2e5e23c615e))
* **nestor:** source unique d'inventaire — nestor dérive l'inventaire, hosts.yaml éliminé (ADR 0098/0099) ([40028e7](https://github.com/univ-lehavre/cluster/commit/40028e739862bc2e408c00b718b464c86a09fabd))


### Bug Fixes

* **bench:** remplace mapfile par read_lines (compatible bash 3.2 de macos) ([425fafb](https://github.com/univ-lehavre/cluster/commit/425fafbdad779d0c95e9de849b65246e5a3cfb0e))
* **ci:** le job macos installe bash homebrew et le met en tête du path (bats) ([e2a2908](https://github.com/univ-lehavre/cluster/commit/e2a29080f1e1e9b0ef09df841aefbe66ba9dbe90))
* **ci:** régénère le bloc stats (100 adr) + installe shellcheck sur le runner macos ([bc2d291](https://github.com/univ-lehavre/cluster/commit/bc2d291cacfdfbdd77e5b8af8cfdc9142745e6c4))
* **ci:** régénère le bloc stats (100 adr) + installe shellcheck sur le runner macos ([459da9f](https://github.com/univ-lehavre/cluster/commit/459da9f811d122fbbe38dac2634a14b7caecc141))


### Refactor

* **bench:** supprime env.sh — nestor couvre la dérivation de contexte (ADR 0097/0098) ([c4ca500](https://github.com/univ-lehavre/cluster/commit/c4ca500f2ee8d17b07f578c33b0bd298a4b6a226))
* **bench:** supprime gitea-init.sh — mort, le seed est porté en Python (ADR 0101 étape 1) ([2aaca3c](https://github.com/univ-lehavre/cluster/commit/2aaca3c8d7511b37da4f34e36809044a164a1068))
* **bench:** supprime metrology.sh — orphelin (ADR 0101 étape 4) ([fdbae91](https://github.com/univ-lehavre/cluster/commit/fdbae91d6b264090b13dbb5e2883d5ac6cc75b3d))
* **bench:** supprime metrology.sh — orphelin, le pur vit en Python (ADR 0101 étape 4) ([03f2103](https://github.com/univ-lehavre/cluster/commit/03f210326e4fa126a1b91b2f5aa36c0909f7b413))
* **nestor:** _inventory_for devient un contextmanager (inventaire prod éphémère, ADR 0098) ([9ff0b80](https://github.com/univ-lehavre/cluster/commit/9ff0b807c58c24d4ef4ba6d1669a11dc44922759))
* **nestor:** migre access.sh → nestor/access.py (ADR 0101 étape 2) ([486592b](https://github.com/univ-lehavre/cluster/commit/486592b1415b8e944adfec17acee111d8581715a))
* **nestor:** migre check-freshness.sh → nestor artifact check-freshness (ADR 0101 étape 3) ([962c36f](https://github.com/univ-lehavre/cluster/commit/962c36fcb73198a729b93c469e75cddbf765b8ad))
* **nestor:** migre check-freshness.sh → nestor artifact check-freshness (ADR 0101 étape 3) ([887a102](https://github.com/univ-lehavre/cluster/commit/887a102e897a0579fdef6032ef3e080f7135338d))
* **nestor:** remplace bash -c par un appel kubectl direct (roundtrip) ([0575df3](https://github.com/univ-lehavre/cluster/commit/0575df38e7b2095595ad1f0e996f316499d86624))
* **nestor:** renomme target_kind lima → bench (la criticité, ADR 0099) ([6f84abe](https://github.com/univ-lehavre/cluster/commit/6f84abee8375679fbb929dd8f3858f6c71037603))
* **nestor:** renomme target_kind lima → bench (la criticité, pas l'outil — ADR 0099) ([c3bf025](https://github.com/univ-lehavre/cluster/commit/c3bf02566bdc6bcf02a11e4bacd1e9cf068e38bf))
* **nestor:** supprime le Justfile, bascule ansible.cfg + CLI vers nestor ansible ([b93ca72](https://github.com/univ-lehavre/cluster/commit/b93ca72310fe95771a6e5016e64d52cd18ef7b4f))
* **nestor:** zone grise bash→Python — gitea-init (mort) + access (ADR 0101 étapes 1-2) ([54c1641](https://github.com/univ-lehavre/cluster/commit/54c1641d270080a09a85be3b7c220babb14213f2))


### Documentation

* **adr:** acte le périmètre os & architecture (poste unix, nœuds linux, windows→wsl) ([c7908e8](https://github.com/univ-lehavre/cluster/commit/c7908e82f9cd4f18fc35f2cc1df8d9bdf52db2d7))
* **adr:** acte le renommage lima→bench fait dans 0099 + renvoi vers 0100 (périmètre OS) ([1f737c3](https://github.com/univ-lehavre/cluster/commit/1f737c369dfb027bbc1dbd241669e9462b253e6a))
* **adr:** amende 0062 — le socle mlops (mlflow) est désormais en place ([51bbfe6](https://github.com/univ-lehavre/cluster/commit/51bbfe6423506bc14ad051b202d6661184fa1f48))
* **adr:** amende 0062 — le socle mlops (mlflow) est désormais en place ([9299463](https://github.com/univ-lehavre/cluster/commit/9299463aba6a491a53be81ec1ef5af476c47a2aa))
* **adr:** cadre la migration de la zone grise bash → Python (ADR 0101) ([b522133](https://github.com/univ-lehavre/cluster/commit/b522133b7cea0bf9f7a86a2421aa400c65af560f))
* **adr:** cadre la migration de la zone grise bash → Python (ADR 0101) ([a55030d](https://github.com/univ-lehavre/cluster/commit/a55030dc7c8bed30f0bbb72dda78db6cd8d032d7))
* **adr:** cadre les axes du modèle de topologie (ADR 0099) ([bba09bf](https://github.com/univ-lehavre/cluster/commit/bba09bf4c1fefd9677c60a0bf759329cd5785d37))
* **adr:** tranche le couplage moteur↔inventaire prod (ADR 0098 point 3) ([d76888f](https://github.com/univ-lehavre/cluster/commit/d76888f15cf3be0986f48aa3e4a462cbc3d05f1a))
* build OK (218 pages), shellcheck OK, 981 tests OK. ([2aaca3c](https://github.com/univ-lehavre/cluster/commit/2aaca3c8d7511b37da4f34e36809044a164a1068))
* build OK. ([c4ca500](https://github.com/univ-lehavre/cluster/commit/c4ca500f2ee8d17b07f578c33b0bd298a4b6a226))
* **gouvernance:** résout 4 manquements préexistants (index ADR + Suivi des plans) ([75c4609](https://github.com/univ-lehavre/cluster/commit/75c4609e6aa217b21c06885147cc833fc425b2f0))
* **nestor:** bascule la doc opérateur vers nestor ansible (ADR 0098) ([9d5b786](https://github.com/univ-lehavre/cluster/commit/9d5b786d0f9878c2c8dc3d306a32b132cca1c868))
* **nestor:** justifie l'affichage/écriture des secrets par access (faux positif codeql) ([8e7d9bb](https://github.com/univ-lehavre/cluster/commit/8e7d9bbbaf93b618c9cc7e29875af07844abde44))
* **nestor:** justifie l'affichage/écriture des secrets par access (faux positif codeql) ([abc6e84](https://github.com/univ-lehavre/cluster/commit/abc6e849f505afb102908f4287aa260088a81b03))
* **readme:** aligne sur atlas, développe culture et gouvernance ([5b80279](https://github.com/univ-lehavre/cluster/commit/5b8027998208ab90a4856ac7862772762e59a260))
* **readme:** aligne sur atlas, développe culture et gouvernance ([c7e77fe](https://github.com/univ-lehavre/cluster/commit/c7e77feebaad08781a0fbcdf569d34a486a718e5))

## [2.46.0](https://github.com/univ-lehavre/cluster/compare/v2.45.0...v2.46.0) (2026-06-30)


### Features

* **epreuves:** marque 4 scénarios caducs (terrain Vagrant/ha-3cp abandonné, ADR 0097) ([5c500a9](https://github.com/univ-lehavre/cluster/commit/5c500a93bc8e4673a1925a194d6775b4dbc5ebac))
* **nestor:** bascule le défaut de cmd_up sur --engine=python (ADR 0097) ([ebf5d0a](https://github.com/univ-lehavre/cluster/commit/ebf5d0addfb03f8374843e262a134f4c1acbd7fa))
* **nestor:** câble le hook e2e dataops (OpenLineage→Marquez) + build émetteur au banc ([ed996f8](https://github.com/univ-lehavre/cluster/commit/ed996f8f06915c4ad4a039ddaba66c9785715e26))
* **nestor:** câble le seed GitOps + fix crash playbook=None (gitops-seed) ([91c212f](https://github.com/univ-lehavre/cluster/commit/91c212f37ec959bc11bddf1e2441977508f88560))
* **nestor:** câble push-code-location — seed gitops complet (7/7 steps) ([a0bc7b2](https://github.com/univ-lehavre/cluster/commit/a0bc7b2fdcf97d317fae2acb7bf82a4e4ec2e9a1))
* **nestor:** ménage `nestor -h` — ajoute kubectl, renomme destroy → down ([345f754](https://github.com/univ-lehavre/cluster/commit/345f75440e9114773a03d1e9e74fe4781b4cda58))
* **nestor:** nestor kubectl &lt;args&gt; — kubectl sur la cible de la stack active ([058aa64](https://github.com/univ-lehavre/cluster/commit/058aa645d18261cafddec6ad72089f5bcf98ca53))
* **nestor:** refonte moteur Python — lots 6 à 9 (ADR 0097 abouti, prouvé au banc) ([fb0dc20](https://github.com/univ-lehavre/cluster/commit/fb0dc2069d05097ca452187e9855559fc1a6f484))


### Bug Fixes

* **k8s-cri:** drop-in containerd purge les sockets shim au démarrage (Yunix [#513](https://github.com/univ-lehavre/cluster/issues/513)) ([73f3bfd](https://github.com/univ-lehavre/cluster/commit/73f3bfdadc979f8d0d0ac9bc17f8450287156689))
* **monitoring:** idempotence des CRDs — changed_when dérivé de kubectl apply (ADR 0051) ([7bf2498](https://github.com/univ-lehavre/cluster/commit/7bf24985770d55da2c6fdc6f2ccbfe0f22e83624))
* **nestor:** --request-timeout avant les args kubectl (cassait kubectl exec du seed) ([b288a62](https://github.com/univ-lehavre/cluster/commit/b288a62d9226b5c7a6f2a7c92fda68b360487555))
* **nestor:** commente l'except non-JSON de _seed_resp_has_commit (CodeQL py/empty-except) ([654f290](https://github.com/univ-lehavre/cluster/commit/654f2902b4c32c4ec3ead7564d7a29c478527295))
* **nestor:** gate gitea/argocd Ready avant le seed (parité run-phases.sh) ([83c520c](https://github.com/univ-lehavre/cluster/commit/83c520c5cbf9ec602d1b255ac63b9c970c7f4b45))
* **nestor:** le play utilise le kubeconfig banc rapatrié (127.0.0.1), pas l'env vide ([4db9d70](https://github.com/univ-lehavre/cluster/commit/4db9d702728f07dbe81235f3cd252404174acd90))
* **nestor:** montage en 1 passage + gate (parité bash, pas de faux changed sur builds mutables) ([4ea58dd](https://github.com/univ-lehavre/cluster/commit/4ea58dda10eca21e50bb4281a0da5c6dc722ca03))
* **nestor:** seed admin distingue 'existe déjà' d'un vrai échec (ADR 0046) ([0486a3c](https://github.com/univ-lehavre/cluster/commit/0486a3c3a7943c5e72d6207db338fa99719e0a36))
* **nestor:** up from-scratch d'un banc lima passe la garde d'isolation (ADR 0053) ([f390a59](https://github.com/univ-lehavre/cluster/commit/f390a5936eb8ffd7cb84192b499d23c03a433e0d))
* **platform:** épingle nerdctl-full 2.2.2 (containerd 2.2.1) — corrige le bug Yunix ([#513](https://github.com/univ-lehavre/cluster/issues/513)) ([8ce06ce](https://github.com/univ-lehavre/cluster/commit/8ce06ce5aae077fd2bd532aed95a98b3030dc526))


### Refactor

* **bench:** retire le bash redondant de run-phases.sh (-652 lignes) ([0b032b0](https://github.com/univ-lehavre/cluster/commit/0b032b0d228061a6e5cac7ffe6c9e891acb6dff7))
* **nestor:** abandonne la topologie ha-3cp (ADR 0055 superseded) ([fd04ee0](https://github.com/univ-lehavre/cluster/commit/fd04ee08903b552820cbb4344850a396acec2cb8))
* **nestor:** le moteur Python est le seul moteur de montage (ADR 0097 abouti) ([ee1afc3](https://github.com/univ-lehavre/cluster/commit/ee1afc34033af232f5adb81dd2cab6b2ec9988e6))
* **nestor:** retire le warning preview 'shell sans KUBECONFIG' (obsolète) ([0f9dfc0](https://github.com/univ-lehavre/cluster/commit/0f9dfc04b033a0987af63009e2d80df0ab724c75))


### Documentation

* **drifts:** consigne L59-L72 — runs --engine=python + drifts antérieurs oubliés ([63efabc](https://github.com/univ-lehavre/cluster/commit/63efabcbac51a505a0fd8d33f9308624bd423a23))
* **drifts:** le drift yunix L66 est corrigé — nerdctl-full 2.2.2 (containerd 2.2.1) ([6d88b19](https://github.com/univ-lehavre/cluster/commit/6d88b194db597a0d6e11ca7c3c04a621c1d5ad53))
* **drifts:** régénère la page registre-drifts.md (L59-L72 ajoutés) ([d198a54](https://github.com/univ-lehavre/cluster/commit/d198a5448705184d27bb5c7f9184d886df71ad68))
* **drifts:** relie le drift yunix L66 à l'issue [#513](https://github.com/univ-lehavre/cluster/issues/513) (fix containerd durable) ([0b42a23](https://github.com/univ-lehavre/cluster/commit/0b42a233d058f41698b188fc3b5740d3687a4222))
* **readme:** régénère le bloc STATS — 73 drifts (L59-L72 ajoutés) ([0522897](https://github.com/univ-lehavre/cluster/commit/0522897d0a7e2bc08faa5c60c7bed1d325536698))
* **readme:** régénère STATS — ha-3cp abandonné (ADR superseded, plan abandonné) ([ba4b6be](https://github.com/univ-lehavre/cluster/commit/ba4b6bedf15cd37f1b359d983562df4b5b64f8d5))

## [2.45.0](https://github.com/univ-lehavre/cluster/compare/v2.44.0...v2.45.0) (2026-06-26)


### Features

* **build:** premier pas GitOps build — digest exposé, déploiement par [@sha256](https://github.com/sha256) (ADR 0095 §1.a) ([3dd359c](https://github.com/univ-lehavre/cluster/commit/3dd359c982e9e310350c6ed60c24bf5e75d2ecc5))
* **ci:** garde-fou parité graphe↔ansible (adr 0096, détecteur « marquez oublié ») ([3961d51](https://github.com/univ-lehavre/cluster/commit/3961d51a977b1930b2d1cefc67c5d0e0e1138341))
* **nestor:** graphe de dépendances Python figé + check de parité Ansible (refonte lots 2-5) ([742699c](https://github.com/univ-lehavre/cluster/commit/742699c03fc4c662eae4456801c85811ad613fe8))
* **nestor:** porte le graphe de dépendances en python (parité bash) ([3a4d282](https://github.com/univ-lehavre/cluster/commit/3a4d2827da3b72fffb6de276a9f4b7b80f94e05f))


### Bug Fixes

* **bootstrap:** durcir l'anti-affinité CoreDNS via kubectl patch (lib python absente du nœud) ([fa17a5c](https://github.com/univ-lehavre/cluster/commit/fa17a5c83384b87b03137936e279b1f75b1650e5))
* **nestor:** compute_plan_state partagée preview/next/up — fin de la divergence (étape 1) ([9f60891](https://github.com/univ-lehavre/cluster/commit/9f6089131e595df5c17c5dbb0567824b660739dc))
* **nestor:** compute_plan_state partagée preview/next/up — fin de la divergence (refonte étape 1) ([4384fda](https://github.com/univ-lehavre/cluster/commit/4384fdae1ed0ea95707e482bfc140cdb6986a80b))


### Refactor

* **nestor:** dérive le signal de santé du graphe (source unique) ([f9d1fac](https://github.com/univ-lehavre/cluster/commit/f9d1fac5f1ff55d89f649bb65b12bb353a54a63d))
* **nestor:** remplace les ponts subprocess rollback-lib par le graphe python ([85da6da](https://github.com/univ-lehavre/cluster/commit/85da6da0edecb99ecfd36803f7e8ebb44970a1f3))


### Documentation

* **adr:** 0096 et 0097 Accepted ; plan refonte nestor Actif ([5d088a5](https://github.com/univ-lehavre/cluster/commit/5d088a515f2de1a034c24911181a3d00bc4a5829))
* **adr:** 0096 et 0097 Accepted ; plan refonte nestor Actif ([4c68ab8](https://github.com/univ-lehavre/cluster/commit/4c68ab88249636c4a9ef398cc53694c823674b02))
* **adr:** refonte nestor — graphe Python figé (0096) + moteur de chemin (0097) + plan ([7377753](https://github.com/univ-lehavre/cluster/commit/737775385cc255dd567b98ee123f3ecd6242383a))
* **adr:** refonte nestor — graphe Python figé (0096) + moteur de chemin (0097) + plan ([b22bf41](https://github.com/univ-lehavre/cluster/commit/b22bf415ac955016c86caaf83c98e9014c4c074d))
* **plan:** refonte nestor — coche étape 1 + lots 2-5 (mergés [#508](https://github.com/univ-lehavre/cluster/issues/508)/[#509](https://github.com/univ-lehavre/cluster/issues/509)) ([647b1a9](https://github.com/univ-lehavre/cluster/commit/647b1a9a8e5f189048e134cc1ad4c9917dce5579))
* **plan:** refonte nestor — coche étape 1 + lots 2-5 (mergés) ([09f67b1](https://github.com/univ-lehavre/cluster/commit/09f67b1cc3c1f6074036e130931674ee30736f8d))
* **readme:** régénère le bloc « le dépôt en chiffres » (34 scénarios, ADR 0060) ([f817822](https://github.com/univ-lehavre/cluster/commit/f81782203508206a98d61d896f153d12481be27f))

## [2.44.0](https://github.com/univ-lehavre/cluster/compare/v2.43.0...v2.44.0) (2026-06-25)


### Features

* **argocd:** app-of-apps + ADR 0095 build événementiel in-cluster + seed prod ([e82c087](https://github.com/univ-lehavre/cluster/commit/e82c087fc1b07f389a6ec81ffd1e8fd07d7065f7))
* **argocd:** app-of-apps pour instancier les applications applicatives (ADR 0094) ([92573c0](https://github.com/univ-lehavre/cluster/commit/92573c04ef616f96a88417e7998e0689f7580228))
* **bootstrap:** seed prod app-of-apps + déploiement citation (ADR 0094/0095) ([21f986d](https://github.com/univ-lehavre/cluster/commit/21f986d2db51199395d527251bd3b5ea48c1065f))
* **mailpit:** expose l'UI en nodeport (puits alertmanager prod) ([9923fc3](https://github.com/univ-lehavre/cluster/commit/9923fc3c7919e73f8f65116b50ac30cd0e7db43d))
* **mailpit:** expose l'UI en nodeport + reflète l'usage prod (puits alertmanager) ([77e2da0](https://github.com/univ-lehavre/cluster/commit/77e2da008dd25c510c59429e622def399c9ad9fd))


### Bug Fixes

* **bench:** scénario 33 source lib.sh en chemin absolu (cwd-indépendant) ([175a784](https://github.com/univ-lehavre/cluster/commit/175a7848a41ccb77276fadc9a7e8003ea7331c23))
* **bench:** scénario 33 source lib.sh en chemin absolu (cwd-indépendant) ([ae51075](https://github.com/univ-lehavre/cluster/commit/ae5107554cbc251b6c87a2b15ec41f52bdbc7a6a))
* **cnpg:** applique les networkpolicies du ns postgres ([#485](https://github.com/univ-lehavre/cluster/issues/485)) ([bdd58c8](https://github.com/univ-lehavre/cluster/commit/bdd58c855cd04623b509493861d04198a07c29be))
* **cnpg:** applique les networkpolicies du ns postgres ([#485](https://github.com/univ-lehavre/cluster/issues/485)) ([4d0bc56](https://github.com/univ-lehavre/cluster/commit/4d0bc5672f1aa54a3ad105ecb8d7b270862cb4d4))
* **docs:** lien app-of-apps en URL site /cluster/ (passe orphans ET starlight) ([1055beb](https://github.com/univ-lehavre/cluster/commit/1055beb2a27cdf61c8594d24af71bbc7f76616c2))
* **etcd-backup:** retire le {{ … }} d'un commentaire qui cassait le rendu jinja ([1f376ec](https://github.com/univ-lehavre/cluster/commit/1f376eccb0be3a3ede526deaa98b07d07c13d931))
* **etcd-backup:** retire le {{ … }} d'un commentaire qui cassait le rendu jinja ([23f6aed](https://github.com/univ-lehavre/cluster/commit/23f6aed237bab515e25f0f8be511207a1c246fac))
* **k8s-init:** durcit l'anti-affinité coredns en required ([#487](https://github.com/univ-lehavre/cluster/issues/487)) ([38ba539](https://github.com/univ-lehavre/cluster/commit/38ba539909a1365c87f40fb6ee3fdbad619dcf71))
* **k8s-init:** durcit l'anti-affinité coredns en required ([#487](https://github.com/univ-lehavre/cluster/issues/487)) ([4d8487d](https://github.com/univ-lehavre/cluster/commit/4d8487d33e39e7980e3ce469f4671db273f7e31e))
* **kubeadm:** expose les métriques control-plane sur 0.0.0.0 ([#490](https://github.com/univ-lehavre/cluster/issues/490)) ([4e9468c](https://github.com/univ-lehavre/cluster/commit/4e9468cac10a5803e4efc436cf2c057d699491db))
* **monitoring:** restreint le clusterrole grafana aux configmaps ([#484](https://github.com/univ-lehavre/cluster/issues/484)) ([6c70fce](https://github.com/univ-lehavre/cluster/commit/6c70fce864325f81308f6f980d8835f02b0be0bd))
* **monitoring:** restreint le clusterrole grafana aux configmaps ([#484](https://github.com/univ-lehavre/cluster/issues/484)) ([ee7976c](https://github.com/univ-lehavre/cluster/commit/ee7976cbf119f81c4c44d4001df3ef030b84b74e))


### Documentation

* **adr:** 0094 dependsOn.codeLocations (dépendances inter-applicatives) ([9f7077f](https://github.com/univ-lehavre/cluster/commit/9f7077f02fa8f15defc388adea196bedc63b0adc))
* **adr:** 0094 frontière de déploiement applicatif cluster↔atlas (Proposed) ([4318abc](https://github.com/univ-lehavre/cluster/commit/4318abc52fedd0640160a552879b6d88923ef552))
* **adr:** 0094 frontière de déploiement applicatif cluster↔atlas (Proposed) ([d278198](https://github.com/univ-lehavre/cluster/commit/d278198b4363f82182a043c28cb3591c464b4982))
* **adr:** 0095 build applicatif événementiel in-cluster (Proposed) ([7df8c05](https://github.com/univ-lehavre/cluster/commit/7df8c05e06e75045f26921e56c7d2b06ffe6d85f))
* **adr:** 0095 écarte explicitement le webhook entrant (pull/Cron assumé) ([91a77d3](https://github.com/univ-lehavre/cluster/commit/91a77d396f775dc84f75b8756c17af5433d706a8))
* **audit:** vérification poussée non destructive de la prod dirqual (2026-06-24) ([88079e8](https://github.com/univ-lehavre/cluster/commit/88079e8b76ba7f7370b0fb7497e1378c19062873))
* **audit:** vérification poussée non destructive de la prod dirqual (2026-06-24) ([33c006f](https://github.com/univ-lehavre/cluster/commit/33c006fcf9baf6ca671a53c2f0b4090a87a36170))
* **plan:** cache cnpg achevé — scénario 33 joué au banc (pass) ([337acdc](https://github.com/univ-lehavre/cluster/commit/337acdc77025700d87b77e8a23e602a581e47e5c))
* **plan:** cache CNPG achevé — scénario 33 joué au banc (PASS) ([585c56e](https://github.com/univ-lehavre/cluster/commit/585c56e518d1ad936102847a86a02ad803b0948e))
* **plan:** cadrage HA control-plane 3 nœuds (ha-3cp, promotion in-place) ([bdd32fe](https://github.com/univ-lehavre/cluster/commit/bdd32fe96d52c2c842a71517b95f8bdde467c492))
* **plan:** cadrage HA control-plane 3 nœuds + fix scrape kubeadm ([#486](https://github.com/univ-lehavre/cluster/issues/486)/[#490](https://github.com/univ-lehavre/cluster/issues/490)) ([23be8bc](https://github.com/univ-lehavre/cluster/commit/23be8bcce7c15d6c693ed02f7e7078a172f2aee9))
* **plan:** mise en œuvre du build événementiel GitOps (ADR 0095, Brouillon) ([cef9917](https://github.com/univ-lehavre/cluster/commit/cef99177e4d34c8e9c2467fa455af5087d397f00))
* **plan:** mise en œuvre du build événementiel GitOps (ADR 0095) ([d6ee2ac](https://github.com/univ-lehavre/cluster/commit/d6ee2accef537ef5fefb90364ee4f646db24e654))
* **readme:** régénère le bloc « le dépôt en chiffres » (14 plans, ADR 0060) ([edcc1ff](https://github.com/univ-lehavre/cluster/commit/edcc1ff2706f723935e39cbd44a39812b9b3bde1))
* **readme:** régénère le bloc « le dépôt en chiffres » (94 ADR, ADR 0060) ([971f072](https://github.com/univ-lehavre/cluster/commit/971f072876e18bc4487ce3a3fbd479438fa17702))

## [2.43.0](https://github.com/univ-lehavre/cluster/compare/v2.42.0...v2.43.0) (2026-06-24)


### Features

* **ceph:** exposer le dashboard mgr en nodeport l4 (adr 0092) ([288e640](https://github.com/univ-lehavre/cluster/commit/288e640c15f958c0fad0f83195ff624172b35a30))
* **cni:** bascule cilium en l4 pur (retrait gateway/lb-ipam, adr 0092) ([ec6926b](https://github.com/univ-lehavre/cluster/commit/ec6926b6221005c8d3ecfcd0e73685c0d8eb34de))
* **cnpg:** base/rôle cache pour le backing service des flux atlas (adr 0093) ([d9273ce](https://github.com/univ-lehavre/cluster/commit/d9273cecbe7210093fd0d5f676dcbe55872cc678))
* **contract:** exposer les UI par exposed:true (nodeport l4, adr 0092) ([7d4773f](https://github.com/univ-lehavre/cluster/commit/7d4773f677d7ef2f49b96779112259727ccf2c6f))
* **drift:** allowlist nodeport du contrat + ancrage check_contract (adr 0092) ([4a9e6e0](https://github.com/univ-lehavre/cluster/commit/4a9e6e061d3e03010d3ccd93ca77251a88a5d154))
* exposition L4 NodePort des UI + portail (ADR 0092, supersede 0071) ([29f611b](https://github.com/univ-lehavre/cluster/commit/29f611b37fdd0407fcc59e3cc84b8226020bad77))
* implémentation cache CNPG (base/rôle + contrat + scénario 33) — plan ADR 0093 ([d845059](https://github.com/univ-lehavre/cluster/commit/d845059a033312c563cb0155bf06433955cf774c))
* **platform:** retirer le l7 (7 gateway.yaml + cilium-expo + tâche argocd, adr 0092) ([a9fa387](https://github.com/univ-lehavre/cluster/commit/a9fa38784822e91f00f0fe977e4dbab5570b147a))
* **platform:** services nodeport l4 pour les 7 ui vendored (adr 0092) ([4944dad](https://github.com/univ-lehavre/cluster/commit/4944dad7624ca952d6781110ca6e8f34ee4d1c6c))
* **portal:** câbler portal dans le chemin (phase, graphe atomique, layers, banc.yaml) ([3006c45](https://github.com/univ-lehavre/cluster/commit/3006c45ec6d50f30e31c8fb1130eaf81e65ee1eb))
* **portal:** observer le nodeport l4 au lieu du hostname gateway (adr 0092) ([e2f7bfd](https://github.com/univ-lehavre/cluster/commit/e2f7bfd5baa0a0f362ba8a8a45a277e3781b7ffa))
* **portal:** rôle ansible platform-portal (build image + déploiement nodeport) ([6b639db](https://github.com/univ-lehavre/cluster/commit/6b639db95ac84acb3fb888ecbc7646775d1d100e))


### Bug Fixes

* **bench:** vm_memory_default à 12 gio (chaîne mlops mono-nœud sature 8 gio) ([ad08529](https://github.com/univ-lehavre/cluster/commit/ad085294a5103596b81c6c890a0614c21a243721))
* **docs:** retirer le h1 dupliqué des pages astro générées (starlight rend le title) ([10e51cb](https://github.com/univ-lehavre/cluster/commit/10e51cb8782c221c99f5b9754aa4a040e13e7879))
* **portal:** imagepullpolicy always pour le tag mutable :dev (adr 0092) ([cb50fd1](https://github.com/univ-lehavre/cluster/commit/cb50fd1ed9232efbd84c2aa738acf507a3ea8d04))
* **portal:** observer le service nodeport séparé + afficher le login (adr 0092) ([ab7f47f](https://github.com/univ-lehavre/cluster/commit/ab7f47fef8c6c88d89ced7000737190b3d547124))
* titres dupliqués Astro + imagePullPolicy portail + test scheme https ([378c9b9](https://github.com/univ-lehavre/cluster/commit/378c9b9f6ba941c31a4a7d62562768f50488af2a))


### Documentation

* **adr:** 0092 exposition UI en hostPort/NodePort L4 (supersede 0071) + plan ([7aa094b](https://github.com/univ-lehavre/cluster/commit/7aa094be852d42d74a45d1eae309efe2e877f07a))
* **adr:** 0092 exposition UI en hostPort/NodePort L4 (supersede 0071) + plan ([da08afa](https://github.com/univ-lehavre/cluster/commit/da08afae918e5b75c2587a4d084c5b11a07ec068))
* **adr:** 0093 cache des flux atlas via cloudnative-pg (pas de redis) + plan ([404ed9f](https://github.com/univ-lehavre/cluster/commit/404ed9faebf7d130ea49d2da538db30b8658bf9d))
* **adr:** 0093 cache des flux atlas via CloudNativePG (pas de Redis) + plan ([a79541c](https://github.com/univ-lehavre/cluster/commit/a79541c27fe424584e51567ca450a89c825ca9ad))
* **adr:** aligner contrat + adr 0092 + doc sur l4 nodeport observé (adr 0092) ([9cf20a9](https://github.com/univ-lehavre/cluster/commit/9cf20a96e08c5f4631fe4d16a7957319fc1cbe7e))
* **adr:** lier le plan dans 0092 (plan-exposition orphelin → atteignable, adr 0029) ([2f6a490](https://github.com/univ-lehavre/cluster/commit/2f6a490d11da0e6a39bc70760fc502f0e324e329))
* bloc « le dépôt en chiffres » à 32 scénarios (ajout du 32-portal) ([6c9cb49](https://github.com/univ-lehavre/cluster/commit/6c9cb4992c6bde78cbb025e3321d27c26c25557a))
* **contract:** aligner l'accès UI sur l4 nodeport (adr 0092) ([c489139](https://github.com/univ-lehavre/cluster/commit/c4891398e731958b674e595aaa0454c82d6cb9b6))
* **contract:** dimensionnement des volumes (atlas décide, sc extensibles) ([9627f3e](https://github.com/univ-lehavre/cluster/commit/9627f3eb110dd162576f7580a645429ad0fbe587))
* **netpol:** acter l'egress large GDELT/Zenodo (mediawatch, [#471](https://github.com/univ-lehavre/cluster/issues/471)) ([35b648a](https://github.com/univ-lehavre/cluster/commit/35b648a78df67e0686433f2067923fd75fd09715))
* **netpol:** acter l'egress large pour la collecte gdelt/zenodo ([#471](https://github.com/univ-lehavre/cluster/issues/471)) ([a7a15b9](https://github.com/univ-lehavre/cluster/commit/a7a15b922edabc48016fde703005d41c0c6999ac))
* **plan:** exposition l4 — étapes 1-4 livrées, plan actif (adr 0092) ([f5914d5](https://github.com/univ-lehavre/cluster/commit/f5914d5c8de4ecca5681178e5c66b5a803987ae3))

## [2.42.0](https://github.com/univ-lehavre/cluster/compare/v2.41.1...v2.42.0) (2026-06-23)


### Features

* **dagster:** dériver pgvector-pg-auth pour les code-locations atlas ([2953aef](https://github.com/univ-lehavre/cluster/commit/2953aef26ff16fc6b7165f17841e0695e727ac94))
* **dagster:** dériver pgvector-pg-auth pour les code-locations atlas ([ac0faab](https://github.com/univ-lehavre/cluster/commit/ac0faab48976b6b0fa87db3028a5202fdbc73476))
* **docs:** migrer la documentation de VitePress vers Astro Starlight ([6145909](https://github.com/univ-lehavre/cluster/commit/6145909f52287563341a726aa0e5bf2b77d9a310))
* **docs:** migrer la documentation VitePress → Astro Starlight (ADR 0089) ([f2913b8](https://github.com/univ-lehavre/cluster/commit/f2913b8903c63ca9d63549c91fcfbd7a0ac0916b))
* **nestor:** champ kubeconfig dans la topologie (adr 0090, étape 1) ([7237244](https://github.com/univ-lehavre/cluster/commit/72372444c20b7eb204661653b2018eba3218d60f))
* **nestor:** preview lit l'état réel d'un cluster prod (adr 0090) ([9081d08](https://github.com/univ-lehavre/cluster/commit/9081d087ce865c6e5713a89730d00327222187bd))
* **nestor:** preview lit l'état réel d'un cluster prod (ADR 0090) ([d8e220f](https://github.com/univ-lehavre/cluster/commit/d8e220fc9f9d349f4793677f9d6b73c2671a06f8))
* **nestor:** stack select complète la topo avec kubeconfig + preview réoriente (adr 0090) ([ec38194](https://github.com/univ-lehavre/cluster/commit/ec38194ba6cfbd6f56cf6c74f55dc66717173635))
* **portal:** image, RBAC sans secrets, Gateway hostNetwork (étapes 3-5, adr 0091) ([85390a0](https://github.com/univ-lehavre/cluster/commit/85390a0bee47e56c4ea74579bf40ab70ae47b0d1))
* **portal:** logique pure de croisement contrat ↔ état (étape 1, adr 0091) ([0c893eb](https://github.com/univ-lehavre/cluster/commit/0c893eb2112eef511e16b228a08d977193ab7e85))
* **portal:** logique pure de croisement contrat ↔ état (étape 1, ADR 0091) ([6f5517c](https://github.com/univ-lehavre/cluster/commit/6f5517c699690b266429f653e2b385678813ca10))
* **portal:** serveur in-cluster + rendu HTML (étape 2, adr 0091) ([5589a6a](https://github.com/univ-lehavre/cluster/commit/5589a6ae441a7162091ebe0cc0c6e5e5c5093d6d))
* **portal:** serveur in-cluster, image, RBAC sans secrets, Gateway (étapes 2-5, ADR 0091) ([f8d00e7](https://github.com/univ-lehavre/cluster/commit/f8d00e76fa0ee88ff545c02dc71f98094c74b2dc))


### Bug Fixes

* **build-images:** installer nerdctl-full épinglé sur le nœud builder ([199e290](https://github.com/univ-lehavre/cluster/commit/199e29098952156b52e14cd2f780f72910b8445b))
* **build-images:** installer nerdctl-full épinglé sur le nœud builder ([311b6d8](https://github.com/univ-lehavre/cluster/commit/311b6d8a683ac9de5f7a4544118e002a1d156808))
* **dataops:** workspace Dagster vise la code-location par nom court (gRPC FQDN timeout) ([6510827](https://github.com/univ-lehavre/cluster/commit/6510827147bd69830198af58f28d468b4e8908a2))
* **dataops:** workspace Dagster vise toy-codeloc par nom court (gRPC FQDN timeout) ([a6d5fec](https://github.com/univ-lehavre/cluster/commit/a6d5fecc022e46fcf3d397ccc500f5dd1a35112c))
* **marquez:** connexion CNPG par nom court (fqdn pg timeoute en prod) ([d2f6c7c](https://github.com/univ-lehavre/cluster/commit/d2f6c7c706f1b153a2b200868347c9dc7edd8971))
* **marquez:** connexion CNPG par nom court (fqdn pg timeoute en prod) ([44dc381](https://github.com/univ-lehavre/cluster/commit/44dc38192c3795c57d8897bdb4567244e7cffd44))
* **nestor+e2e:** next cohérent avec preview (réel prime) + émetteur buildé sur x86 ([ed0480e](https://github.com/univ-lehavre/cluster/commit/ed0480e5cb6cdc2e0e167f8cfcc3afa5efba0646))
* **nestor:** preview+next résolvent le kubeconfig prod ; gitea-init via localhost ([b18d282](https://github.com/univ-lehavre/cluster/commit/b18d28263bc63bfeadbe31b52cd092197c2dd4ee))
* **nestor:** stack select prod ne bloque plus + écrit le champ kubeconfig ([62887f8](https://github.com/univ-lehavre/cluster/commit/62887f85232c9f64c1562f3f0bf9664cecfc16e2))
* **prod:** garantir le restart containerd après config registry + os-upgrade serial ([ae0c058](https://github.com/univ-lehavre/cluster/commit/ae0c0586c5b084df5274c262226848f54b0fcd51))
* **prod:** garantir le restart containerd après config registry + os-upgrade serial ([fd40a39](https://github.com/univ-lehavre/cluster/commit/fd40a39f9c23d6ae16bfc50dbf468f29f5bc39b3))


### Documentation

* **adr:** 0091 portail d'accès aux UI + plan (proposed) ([30e49dc](https://github.com/univ-lehavre/cluster/commit/30e49dc8880d5eb76554733be54fdacaa7aaa281))
* **adr:** 0091 portail d'accès aux UI + plan (proposed) ([05379f4](https://github.com/univ-lehavre/cluster/commit/05379f45c0234ca0735d26e1fd9af8ecb11b2071))
* **adr:** adr 0090 — confirmer le kubeconfig prod + rapatriement assisté ([c53785b](https://github.com/univ-lehavre/cluster/commit/c53785b909ed9600a69ec6065e215ae47bf4013d))
* **adr:** ADR 0090 — confirmer le kubeconfig prod + rapatriement assisté ([5b63c2f](https://github.com/univ-lehavre/cluster/commit/5b63c2f5ce433b5e111beae5b55df81bec824f33))
* **adr:** adr 0090 + plan — nestor lit l'état réel d'un cluster prod ([0fda406](https://github.com/univ-lehavre/cluster/commit/0fda406898f46f1b67f4f8c6afa1a51a4652c048))
* **adr:** ADR 0090 + plan — nestor lit l'état réel d'un cluster prod ([baed263](https://github.com/univ-lehavre/cluster/commit/baed263b452605ebfbcbe170707a2c6a6f1621d2))
* **adr:** promouvoir 0091 portail Accepted + plan Actif (démarrage étape 1) ([c23ea44](https://github.com/univ-lehavre/cluster/commit/c23ea4405c47355f683d604659c696ddbf1b0291))
* **audit:** ajouter les URL de preuve à l'answer-sheet badge ([e9db612](https://github.com/univ-lehavre/cluster/commit/e9db61234b5674f3225edde9cc26a08945327cb2))
* **audit:** answer-sheet OpenSSF Best Practices Badge (passing) ([1d3d04c](https://github.com/univ-lehavre/cluster/commit/1d3d04cf84602ae2ca5ebb4e7a66017281b3e8c7))
* **audit:** answer-sheet OpenSSF Best Practices Badge (passing) ([872cb34](https://github.com/univ-lehavre/cluster/commit/872cb34e8980dc992150f6407f8dd7d8bc6cde0f))
* **audit:** faisabilité silver/gold du badge — décision : rester à passing ([5ad7c99](https://github.com/univ-lehavre/cluster/commit/5ad7c997bb7c16af57773b3ae67190ea6bfcded9))
* bloc « le dépôt en chiffres » à 11 plans (résidu de plan supprimé) ([b2c77db](https://github.com/univ-lehavre/cluster/commit/b2c77db55d3555b7df7be38eed0c0d3494cbcc53))
* **composants:** rattacher le portail (README atteignable, adr 0029) ([bff2c11](https://github.com/univ-lehavre/cluster/commit/bff2c11b36e26d397fd90c71137161975eead850))
* **contract:** mettre le contrat à jour des écarts de l'audit cluster↔atlas ([184a419](https://github.com/univ-lehavre/cluster/commit/184a419c0c0e1d90c1f33908bcf7922a2367ec89))
* **contract:** mettre le contrat à jour des écarts de l'audit cluster↔atlas ([a62e3bc](https://github.com/univ-lehavre/cluster/commit/a62e3bc2f81176ed7e9940eeb2fcc6c2268fba3d))
* **dns:** documenter le piège FQDN→nom court (contrat + guide-dev + drift L58) ([202864b](https://github.com/univ-lehavre/cluster/commit/202864b31d36d13de8d2f9d49c980246d7680daa))
* encart anglais (readme/contributing/security) — critère english du badge ([49479c3](https://github.com/univ-lehavre/cluster/commit/49479c3d7beab27cb98d47065db1aa848edd3523))
* régénérer le bloc « le dépôt en chiffres » (adr 0090 accepted, plan actif) ([92d14c0](https://github.com/univ-lehavre/cluster/commit/92d14c0b0f1c2d45781e5b98b8c3207ced8a513d))
* réintégrer badge Best Practices + Trademarks→Conformité + encart anglais + audit silver/gold ([1827d84](https://github.com/univ-lehavre/cluster/commit/1827d84d42a8ecdd0224861f6a0886422f714157))
* réintégrer le badge Best Practices (validé) + section Conformité ([3910cc6](https://github.com/univ-lehavre/cluster/commit/3910cc66c149b81d932c5a25595edb299cd86a72))

## [2.41.1](https://github.com/univ-lehavre/cluster/compare/v2.41.0...v2.41.1) (2026-06-22)


### Documentation

* **adr:** adr 0089 + plan migration doc vitepress → astro starlight ([c724a0a](https://github.com/univ-lehavre/cluster/commit/c724a0aeb7c17812484dd5a840cd2a7c95805625))
* **adr:** ADR 0089 + plan migration doc VitePress → Astro Starlight ([50e1206](https://github.com/univ-lehavre/cluster/commit/50e12060bede957ed6214f86654bcc3348356b07))
* régénérer le bloc « le dépôt en chiffres » (adr 0089 + plan) ([ba7e0ad](https://github.com/univ-lehavre/cluster/commit/ba7e0ad8d28458dc8ca9950d6f0a95d35d80c093))

## [2.41.0](https://github.com/univ-lehavre/cluster/compare/v2.40.0...v2.41.0) (2026-06-21)


### Features

* **ci:** gate --stats-check anti doc-rot du bloc « le dépôt en chiffres » ([fb4af78](https://github.com/univ-lehavre/cluster/commit/fb4af78411ac013b8835a3b1d570e70a914bcdfe))
* **docs:** registre des drifts navigable généré depuis le yaml (+ gate) ([b06f7c0](https://github.com/univ-lehavre/cluster/commit/b06f7c0820d58a6abdf3097cd54f992192ef1f76))


### Bug Fixes

* **docs:** corriger le doc-rot (banc vagrant, compteurs figés, faits périmés) ([50364a6](https://github.com/univ-lehavre/cluster/commit/50364a62a990679a32476ca0a8ba9ad7ee3105f3))
* **docs:** neutraliser les url citées dans la page registre-drifts (lychee) ([a5f3f61](https://github.com/univ-lehavre/cluster/commit/a5f3f61a8dc1fa8bf0254a5e11759f3b15c9960f))


### Documentation

* **adr:** promouvoir 6 adr livrés en accepted + reclasser diátaxis ([5db7582](https://github.com/univ-lehavre/cluster/commit/5db75820a5e9ab27783c4229d040a41f9c13d312))
* améliorer navigabilité et pédagogie (suite audit doc) ([63e7cb8](https://github.com/univ-lehavre/cluster/commit/63e7cb808cc5cad2b091033d41c29ab160375114))
* audit documentation 194 .md + corrections doc-rot + gate stats ([537e9ab](https://github.com/univ-lehavre/cluster/commit/537e9ab35d8b0004d7f6d933e63a9efe529fc351))
* **audit:** passage daté — audit documentation 194 .md (2026-06-20) ([5041e42](https://github.com/univ-lehavre/cluster/commit/5041e42e731949684773c5016f01f46b7dd013f4))
* finaliser l'audit doc (navigabilité, pédagogie, registre drifts navigable) ([4310964](https://github.com/univ-lehavre/cluster/commit/4310964a449206000b4aef41d29840a961f78211))

## [2.40.0](https://github.com/univ-lehavre/cluster/compare/v2.39.0...v2.40.0) (2026-06-20)


### Features

* **scorecard:** SAST, fuzzing, signed-releases + README GitHub pur ([1bcbc21](https://github.com/univ-lehavre/cluster/commit/1bcbc213850977fdf6db9858db531f543fed757a))


### Documentation

* **audit:** évaluation kubescape — ne pas câbler (redondant trivy/kyverno) ([78d8c45](https://github.com/univ-lehavre/cluster/commit/78d8c45abb87e7ab752936698a9ecaf4c931c0df))
* **audit:** évaluation kubescape — ne pas câbler (redondant) ([c78628d](https://github.com/univ-lehavre/cluster/commit/c78628d9fe1df0544130ed665a48779083c1a6f5))
* **audit:** tracer packaging n/a assumé (nestor pilote le dépôt, [#366](https://github.com/univ-lehavre/cluster/issues/366)) ([94d1cea](https://github.com/univ-lehavre/cluster/commit/94d1cea63a63a68b22fc9465f636d71fdca6a3b0))
* **readme:** readme github pur, retirer best practices, home dans docs/index ([fc1533b](https://github.com/univ-lehavre/cluster/commit/fc1533be5d34178933a3a9760cb7ce4d10763428))
* **readme:** retirer la rangée de badges du haut (doublon avec la section) ([5d0555e](https://github.com/univ-lehavre/cluster/commit/5d0555e08455210346170bb20750851f0c6e13f5))
* **readme:** retirer la rangée de badges du haut (doublon) ([92ffcbb](https://github.com/univ-lehavre/cluster/commit/92ffcbb5334b8d444a95fa1934c06d4616a7caac))
* **readme:** sections présentées pour les familles de badges ([48fe2fd](https://github.com/univ-lehavre/cluster/commit/48fe2fd222dcd8919f9c20de6a831dd30a6b7dc7))
* **readme:** sections présentées pour les familles de badges ([fd4a927](https://github.com/univ-lehavre/cluster/commit/fd4a927447f7b28f60ef57e5aa7ebd627a3d1b4d))
* **scorecard:** tracer packaging n/a + lire branch-protection ([#366](https://github.com/univ-lehavre/cluster/issues/366)) ([72489ea](https://github.com/univ-lehavre/cluster/commit/72489ea55d7c5eda2d4f9c375142c4c50d77e340))

## [2.39.0](https://github.com/univ-lehavre/cluster/compare/v2.38.0...v2.39.0) (2026-06-19)


### Features

* **banc:** scénario 31 — vérifier le contrat d'interface cluster→atlas ([a12ef7b](https://github.com/univ-lehavre/cluster/commit/a12ef7b43183a9cf49eccae0713dda3f26122917))
* **banc:** scénario 31 — vérifier le contrat d'interface cluster→atlas ([5b65d1d](https://github.com/univ-lehavre/cluster/commit/5b65d1d1aaaa6d77d1f15fa3b7d0eb85c9661f80))
* **dataops:** code-location jouet gRPC déployée par gitops (adr 0086) ([3dadf26](https://github.com/univ-lehavre/cluster/commit/3dadf26363df617bfed3ebe946e1b3b25a07f330))
* **dataops:** code-location jouet gRPC déployée par gitops (ADR 0086) ([807b30f](https://github.com/univ-lehavre/cluster/commit/807b30f3273018578d16697b97a9a838d779260b))
* **dataops:** toy_drift logge un drift_score jouet dans mlflow (adr 0086, étape 1) ([6268e92](https://github.com/univ-lehavre/cluster/commit/6268e925be0f70085e452e321bab0887a5191223))
* **dataops:** toy_drift logge un drift_score jouet dans MLflow (ADR 0086, étape 1) ([5e51c8b](https://github.com/univ-lehavre/cluster/commit/5e51c8b08c3e224cb4a2fcb4ceeac22f6e66ba7c))
* **dataops:** toy_drift utilise le vrai evidently (EmbeddingsDriftMetric) — [#428](https://github.com/univ-lehavre/cluster/issues/428) ([10d0eeb](https://github.com/univ-lehavre/cluster/commit/10d0eebdfd70323fad8dc2b0caac1f0165bdc44b))
* **dataops:** toy_drift utilise le vrai Evidently (EmbeddingsDriftMetric) — closes [#428](https://github.com/univ-lehavre/cluster/issues/428) ([50804e6](https://github.com/univ-lehavre/cluster/commit/50804e6a790adc20035e5d22c595628d6e69cf15))
* **redcap:** ajouter l'app redcap (php/apache + mariadb autonome) ([3c36304](https://github.com/univ-lehavre/cluster/commit/3c36304fd2938a92a9022466e51993cea347b084))
* **redcap:** ajouter l'app redcap (php/apache + mariadb autonome) ([8f523d7](https://github.com/univ-lehavre/cluster/commit/8f523d77618892ea99a8aa8b1268257432fa57ce))
* **redcap:** mode désinstallation (redcap_state=absent), pvc conservé par défaut ([53d5c43](https://github.com/univ-lehavre/cluster/commit/53d5c43a5f0824de5a1ffdcfec02180356523b37))
* **redcap:** mode désinstallation (redcap_state=absent), pvc conservé par défaut ([c556912](https://github.com/univ-lehavre/cluster/commit/c55691295d15f2d42b6030b59d98797bb596e59b))


### Bug Fixes

* **banc:** ajouter phase_mlflow (montage layers échouait en rc=127) ([713cde4](https://github.com/univ-lehavre/cluster/commit/713cde4a195690e9ae1a5c654b600bf5101a7e1f))
* **banc:** ajouter phase_mlflow (montage layers échouait en rc=127) ([ee33e05](https://github.com/univ-lehavre/cluster/commit/ee33e056ea8c204ac12b8aca0416f8b6843ac351))
* **banc:** rendre vm_cpus surchargeable (défaut 4, débloque la chaîne mlops) ([60c5158](https://github.com/univ-lehavre/cluster/commit/60c51583dcb93e92871c0c5b7f58e55a824f357b))
* **banc:** rendre vm_cpus surchargeable (défaut 4, débloque la chaîne mlops) ([1df7aec](https://github.com/univ-lehavre/cluster/commit/1df7aec2e1da14c402f153b88834701240c2cb26))
* **banc:** run-all refuse un VAR=val placé après le script (échec silencieux) ([3a2c33b](https://github.com/univ-lehavre/cluster/commit/3a2c33b7162d24a3b50cce903bbece263d7bf777))
* **banc:** run-all refuse un VAR=val placé après le script (échec silencieux) ([bbc07e3](https://github.com/univ-lehavre/cluster/commit/bbc07e3aad44cc70ad94ff4601d769192db75961))
* **banc:** scénario 01 skip neutre sur banc sans ceph (local-path) ([5dffc64](https://github.com/univ-lehavre/cluster/commit/5dffc6436ba019257a22a21106a4facc422bbbe1))
* **banc:** scénario 01 skip neutre sur banc sans ceph (local-path) ([d58ff39](https://github.com/univ-lehavre/cluster/commit/d58ff390ee5915287c5c44f9f9cd544a8b82409f))
* **dataops:** code-location jouet visible au banc — reload workspace + image fraîche (adr 0086) ([3ffd3bd](https://github.com/univ-lehavre/cluster/commit/3ffd3bd9144cc58b5db3402e35ddce2858cfec25))
* **dataops:** code-location jouet visible au banc — reload workspace + image fraîche (ADR 0086) ([05dd0d1](https://github.com/univ-lehavre/cluster/commit/05dd0d156d633a1970ea34ec1543ef30c50d4689))
* **dataops:** injecter MLFLOW/OPENLINEAGE dans le pod de run (tag dagster-k8s/config) ([c6789e0](https://github.com/univ-lehavre/cluster/commit/c6789e02d743cff0d5c788ea72e1855ff3ce3e5e))
* **dataops:** injecter MLFLOW/OPENLINEAGE dans le pod de run (tag dagster-k8s/config) ([6952b31](https://github.com/univ-lehavre/cluster/commit/6952b317aad7ff014ecdf956e30e280ea688fa3a))
* **dataops:** run via code-location jouet — dagster-postgres + hook kubectl valide ([04b2fa6](https://github.com/univ-lehavre/cluster/commit/04b2fa6ed257be71c1185ca114556fbe3ddcb1d4))
* **dataops:** run via code-location jouet — dagster-postgres dans l'image + hook kubectl valide ([d01f623](https://github.com/univ-lehavre/cluster/commit/d01f6234ad0b1bab4b67b582199cf79e145e2233))
* **épreuves:** enregistrer le scénario 31 au catalogue (test python vert) ([51132e1](https://github.com/univ-lehavre/cluster/commit/51132e1619d1e9024c9bbeae733abed9db62d337))
* **épreuves:** enregistrer le scénario 31 au catalogue (test python vert) ([3d74d25](https://github.com/univ-lehavre/cluster/commit/3d74d25abd711fc23be5791723d2bfd63481ed17))
* **trivy:** allowlister code-location.yaml (KSV-0014/0118, remplace l'ancien job jouet) ([61be173](https://github.com/univ-lehavre/cluster/commit/61be17309731c29c66f5476a4165c566ff1cb606))
* **trivy:** durcir le hook reload (KSV-0014/0118) — securityContext pod + rootfs RO ([3751050](https://github.com/univ-lehavre/cluster/commit/37510503a27b77ae09d3357c400d17bc3d5f8f55))


### Documentation

* **adr:** 0085 — preuves applicatives sur local-path, ceph sur installation seule ([bb2b01d](https://github.com/univ-lehavre/cluster/commit/bb2b01d20040978f96f90180fd7707ba5946cd93))
* **adr:** 0085 — preuves applicatives sur local-path, ceph sur installation seule ([c08b40b](https://github.com/univ-lehavre/cluster/commit/c08b40b186d8655c374cc9aefba38549878b3566))
* **contrat:** injecter mlflow/openlineage dans les pods de run (tag dagster-k8s/config) ([5c676f5](https://github.com/univ-lehavre/cluster/commit/5c676f5e121ff5c26e5f32919eccfb3f70104921))
* **contrat:** injecter mlflow/openlineage dans les pods de run (tag dagster-k8s/config) — [#427](https://github.com/univ-lehavre/cluster/issues/427) ([92d2ef6](https://github.com/univ-lehavre/cluster/commit/92d2ef6d67b7fc4a78f2f9f7b6e1b29b06af93a4))
* raccorder la doc aux ajouts récents (redcap, code-location jouet, scénarios 28-31) ([4baaf5d](https://github.com/univ-lehavre/cluster/commit/4baaf5d34e5f15f7a08f32cc07dabc7ac9866727))
* raccorder la doc aux ajouts récents (REDCap, code-location jouet, scénarios 28-31) ([95eef1d](https://github.com/univ-lehavre/cluster/commit/95eef1da946b70879a4348fe0279778343ace028))

## [2.38.0](https://github.com/univ-lehavre/cluster/compare/v2.37.0...v2.38.0) (2026-06-18)


### Features

* **mlflow:** épopée MLflow complète — ADR + briques + contrat ([#341](https://github.com/univ-lehavre/cluster/issues/341)-346) ([058309b](https://github.com/univ-lehavre/cluster/commit/058309b8de096f5f687227a6add4d7681a7b68be))
* **mlflow:** layer autonome (next/up/remove/discover) + backing S3 dérivé ([2a227aa](https://github.com/univ-lehavre/cluster/commit/2a227aa180a40f4e3732214a7f166a7dbf52375c))
* **mlflow:** manifestes platform/mlflow + ancrages CNPG/AppProject/netpol ([#342](https://github.com/univ-lehavre/cluster/issues/342)-344) ([3c98acc](https://github.com/univ-lehavre/cluster/commit/3c98acc09146407972180d4180c324df476975be))
* **mlflow:** rôle Ansible platform-mlflow + câblage couche dataops ([#345](https://github.com/univ-lehavre/cluster/issues/345)) ([e6ba108](https://github.com/univ-lehavre/cluster/commit/e6ba1085d40960676dfbe0065a5faf41586602bd))


### Bug Fixes

* **bench:** disque VM banc à 40 GiB par défaut ([#391](https://github.com/univ-lehavre/cluster/issues/391)) ([d2d478a](https://github.com/univ-lehavre/cluster/commit/d2d478a4dcd69a954a74f21e840a9deb649f018d))
* **bench:** disque VM par défaut à 40 GiB (les deux backends, [#391](https://github.com/univ-lehavre/cluster/issues/391)) ([5d2d157](https://github.com/univ-lehavre/cluster/commit/5d2d157ca1513b925942405bfd36b13a8e166215))
* **dagster:** egress dagster→mlflow + exclure redcap du scan VitePress ([#407](https://github.com/univ-lehavre/cluster/issues/407)) ([ff67b91](https://github.com/univ-lehavre/cluster/commit/ff67b919c968570d7fc0703ecfccd50c686a0706))
* **mlflow:** image maison (officielle + psycopg2) — corrige le crashloopbackoff ([10faf38](https://github.com/univ-lehavre/cluster/commit/10faf38234dfdbd027f8833ba185781a6c277ee4))
* **mlflow:** image maison psycopg2 + egress dagster→mlflow (prod-ready) ([aa4840a](https://github.com/univ-lehavre/cluster/commit/aa4840a370dba3285ddf8ec34b12558c76d735f3))
* **mlflow:** liens ADR, securityContext durci, trivy KSV-0014 acté (ci verte) ([418eff3](https://github.com/univ-lehavre/cluster/commit/418eff34402bada7e5b5fabf332805c606215eca))
* **nestor:** `env` ne pose pas le kubeconfig banc pour une stack prod (ADR 0084) ([2e5f778](https://github.com/univ-lehavre/cluster/commit/2e5f77820822b3b7bb10cc05f8c868532d16a03c))
* **nestor:** gater les sondes de lecture par target_kind (ADR 0084) ([f599ce8](https://github.com/univ-lehavre/cluster/commit/f599ce82555d3ea5651e84757d50b3a5caa2e892))
* **nestor:** gater les sondes de lecture par target_kind (preview/next, ADR 0084) ([0b59b4b](https://github.com/univ-lehavre/cluster/commit/0b59b4b9c4cfd99fefe1c306e0d1a79efa2c58ef))
* **nestor:** prod — sauter `up`, gater les avertissements banc (ADR 0084) ([591e3c4](https://github.com/univ-lehavre/cluster/commit/591e3c442f8c5be0f09696ee0051ca0805d1f3e5))
* **next:** ancrer le run de référence sur la stack, pas un fallback global ([0baf804](https://github.com/univ-lehavre/cluster/commit/0baf804aa6e752626239f3868876684da673c6c8))
* **trivy:** allowlister DS-0002 pour platform/mlflow/image/Dockerfile (root, comme dagster/marquez) ([1a99057](https://github.com/univ-lehavre/cluster/commit/1a99057378f01d7ff66b7491efece0ba93356b85))


### Refactor

* **plan:** layers source unique de l'ordre, presets en alias (ADR 0083) ([00cd9e7](https://github.com/univ-lehavre/cluster/commit/00cd9e71f22519513ff64a3ad3143e104dab04cb))
* **plan:** layers source unique de l'ordre, presets en alias (ADR 0083) ([80accf0](https://github.com/univ-lehavre/cluster/commit/80accf08aac419692f0cbf3179fd743347a78687))


### Documentation

* **contrat:** tracer la chaîne MLOps drift+CT côté atlas ([e818e4a](https://github.com/univ-lehavre/cluster/commit/e818e4a97f7aaa063348150b6397ee407364ef3a))
* **contrat:** tracer la chaîne MLOps drift+CT côté atlas (maturité 1→2) ([554c5b4](https://github.com/univ-lehavre/cluster/commit/554c5b46872dce5a64d9aff1588c317648456b9c))
* documenter MLflow, layers (ADR 0083) et la chaîne MLOps drift+CT ([b6b5102](https://github.com/univ-lehavre/cluster/commit/b6b510217369590a48c4685f7a658e284c4726eb))
* documenter MLflow, layers (ADR 0083) et la chaîne MLOps drift+CT ([4f94fa4](https://github.com/univ-lehavre/cluster/commit/4f94fa45047847b131a8d92828fe2201ebad6ead))

## [2.37.0](https://github.com/univ-lehavre/cluster/compare/v2.36.0...v2.37.0) (2026-06-17)


### Features

* **cluster:** fonction shell (pose KUBECONFIG), -h groupé, next confirme ([086fe04](https://github.com/univ-lehavre/cluster/commit/086fe0478eb3fd7f6fe1d7c686df3d9b0801a9e2))
* **cluster:** outil déclaratif — next/remove/refresh, menu de couches, santé, isolation banc↔prod durcie ([22a4202](https://github.com/univ-lehavre/cluster/commit/22a4202e61c5ed97d57f6a4d0b9ab8e9d83a9259))
* **discover:** lire le node-side (CRI/CNI/disques) via node_exec (ADR 0081 étape 3) ([ce46b59](https://github.com/univ-lehavre/cluster/commit/ce46b59b7745f2da75190f721803cadd28fa26e7))
* **discover:** lire le node-side (CRI/CNI/disques/durcissement) via node_exec (ADR 0081 étape 3) ([cf1f086](https://github.com/univ-lehavre/cluster/commit/cf1f086dcc1068d883556a19698d3715aa14fc13))
* **discover:** rapatrier le kubeconfig depuis le control-plane (ADR 0081 étape 2) ([d10517c](https://github.com/univ-lehavre/cluster/commit/d10517c50a94068fdeba7429908120157a1c1f26))
* **discover:** rapatrier le kubeconfig depuis le control-plane (ADR 0081 étape 2) ([26dd908](https://github.com/univ-lehavre/cluster/commit/26dd90858dcea0c36adc48a3d3414a8d0c748069))
* **gouvernance:** notations & normes externes — doctrine de badges (ADR 0080) ([2a29bb4](https://github.com/univ-lehavre/cluster/commit/2a29bb42662c5b4adc6015dae46cdc047f3c248f))
* **next:** gate de santé active après montage — attendre le dernier maillon Ready ([#355](https://github.com/univ-lehavre/cluster/issues/355)) ([0786064](https://github.com/univ-lehavre/cluster/commit/0786064bf3d0b93727ba49ac80a38407af68bd49))
* **next:** gate de santé active après montage ([#355](https://github.com/univ-lehavre/cluster/issues/355)) ([b971997](https://github.com/univ-lehavre/cluster/commit/b9719978fa8ed6b3e81011f3be85649f29434485))
* **next:** menu des couches montables — choix d'ordre (deps réelles vs convention) ([83f5bff](https://github.com/univ-lehavre/cluster/commit/83f5bff9a3f940cc6a1c2e4c5d3af89dc048a320))
* **node-exec:** brique node_exec + résolution inventaire (ADR 0081 étape 1) ([ba29791](https://github.com/univ-lehavre/cluster/commit/ba29791cf58f4c568e608b212bd631e4d372dec0))
* **node-exec:** brique node_exec + résolution inventaire (ADR 0081 étape 1) ([fd7f27e](https://github.com/univ-lehavre/cluster/commit/fd7f27e3611515e55bb986b1038377b4dd3e9378))
* **ownership:** graphe d'appartenance + remove --dry-run (découverte, ADR 0079 / [#372](https://github.com/univ-lehavre/cluster/issues/372)) ([81e4990](https://github.com/univ-lehavre/cluster/commit/81e49905f9da2e290c3e6929c0ec029040ac721c))
* **ownership:** graphe d'appartenance + remove --dry-run découverte (slice 1 de [#372](https://github.com/univ-lehavre/cluster/issues/372)) ([26c4014](https://github.com/univ-lehavre/cluster/commit/26c401413f7a55b2355bb7d59813e2d6c1ffd20b))
* **refresh:** --prune — retirer les couches déclarées mais absentes du réel ([#357](https://github.com/univ-lehavre/cluster/issues/357)) ([ace71c3](https://github.com/univ-lehavre/cluster/commit/ace71c34aac445d35bcd841b02f85f2edca30ed7))
* **refresh:** --prune (retirer les couches absentes du réel) ([#357](https://github.com/univ-lehavre/cluster/issues/357)) ([4f8978b](https://github.com/univ-lehavre/cluster/commit/4f8978b5ede174d3cf6d305059c0ab331282f451))
* **refresh:** cluster refresh — réaligner topology.yaml sur le réel voulu (ADR 0076) ([0a0af05](https://github.com/univ-lehavre/cluster/commit/0a0af056642af3a8f97f859241bd137f3e9471a7))
* **remove:** cluster remove — supprimer une couche et sa clôture (inverse de next, ADR 0054) ([db00592](https://github.com/univ-lehavre/cluster/commit/db005921a9f34b98b664ce530b6f1aab43bcfbf8))
* **remove:** découverte par DÉFAUT + finalize des ns wedgés (ADR 0079 étape A) ([b253508](https://github.com/univ-lehavre/cluster/commit/b253508dd1e8abdc34d069c77401e8b6a84553e4))
* **remove:** rollback par découverte d'appartenance — défaut, finalize ns (ADR 0079, [#372](https://github.com/univ-lehavre/cluster/issues/372) étape A) ([38508f6](https://github.com/univ-lehavre/cluster/commit/38508f677f772c85da5a3814d07757491b1da170))
* **remove:** rollback par découverte d'appartenance (--discover, ADR 0079 slice 2) ([9524d21](https://github.com/univ-lehavre/cluster/commit/9524d21c85f70b64938b14f7637b7e234129b49e))
* **test:** nestor test scenarios --run + signaux de santé des couches Ceph ([#227](https://github.com/univ-lehavre/cluster/issues/227)) ([2203089](https://github.com/univ-lehavre/cluster/commit/2203089d42f42ed46431143f6ee87a0a7ebf7928))
* **test:** nestor test scenarios --run + signaux de santé des couches Ceph ([#227](https://github.com/univ-lehavre/cluster/issues/227)) ([00dccf7](https://github.com/univ-lehavre/cluster/commit/00dccf73e3c5ac9b9f06971aa2e4c99e66ba2c0f))
* **topology:** select pose KUBECONFIG (eval), messages simples, expo effective ([5fdbd2a](https://github.com/univ-lehavre/cluster/commit/5fdbd2ad62a1a077594872c7ab42c94ad37701c0))


### Bug Fixes

* **ci,preview:** verdir la CI (test banc-dépendant, lychee 0.23, MD028) + warning preview shell≠banc ([7656c15](https://github.com/univ-lehavre/cluster/commit/7656c1526b6091a1386ce20b7b082605ef0ada43))
* **cluster:** robustesse KUBECONFIG — /dev/null remplaçable, select non destructif, auto-env ([6ae4229](https://github.com/univ-lehavre/cluster/commit/6ae42298f727e1e5a4b81f9d9e9000b524547d21))
* **gates:** until '.resources | default([])' — ne pas crasher si k8s_info échoue ([e553a69](https://github.com/univ-lehavre/cluster/commit/e553a694456bad06d14c3c3a66f7f2fa043c3533))
* **gates:** until '.resources | default([])' — ne pas crasher si le k8s_info échoue ([1c96fd5](https://github.com/univ-lehavre/cluster/commit/1c96fd5ee2aac86b888e90074026fd384384f65b))
* **isolation:** garde audit-log sur les plays hosts:cloud + test anti-régression (part code de [#359](https://github.com/univ-lehavre/cluster/issues/359)) ([a0e6aff](https://github.com/univ-lehavre/cluster/commit/a0e6aff52bc37f8b99279ddb4ae8fd05cb3a8e26))
* **isolation:** garde audit-log sur tous les plays 'hosts: cloud' + test anti-régression ([#359](https://github.com/univ-lehavre/cluster/issues/359)) ([e3b4649](https://github.com/univ-lehavre/cluster/commit/e3b4649fdbf6a245d523869d3dec74abd079a59a))
* **isolation:** next valide l'inventaire Ansible avant montage — faille banc→prod (ADR 0053) ([ca9c4ae](https://github.com/univ-lehavre/cluster/commit/ca9c4ae7ca217b528da809988329427a8be471f9))
* **isolation:** next vise l'inventaire de la STACK active (banc Lima ≠ prod, ADR 0053) ([e360233](https://github.com/univ-lehavre/cluster/commit/e360233dba6c295ca80588bcc2ca6e2db94488cd))
* **lint:** lychee.toml — include_fragments en enum "none" (compat lychee ≥ 0.24) ([b9a9cab](https://github.com/univ-lehavre/cluster/commit/b9a9cabea38d2cb1a4b8a173d2053794140eaaa6))
* **metrology:** émettre par_noeud avec accolades sans espaces (yamllint refuse `{ ... }`) ([82201f9](https://github.com/univ-lehavre/cluster/commit/82201f9e151af314e8650ecebd6d4908635a724e))
* **metrology:** par_noeud sans espaces dans les accolades (yamllint refuse `{ ... }`) ([ebabf14](https://github.com/univ-lehavre/cluster/commit/ebabf14852d40688dcd10ec58f3f4888117edead))
* **next:** déléguer toute phase sans play unitaire à run-phases.sh (gitops-seed) ([33c9947](https://github.com/univ-lehavre/cluster/commit/33c9947033b29a99797bbbb155cba23152882d0d))
* **next:** déléguer toute phase sans play unitaire à run-phases.sh (gitops-seed) ([f9f7ca6](https://github.com/univ-lehavre/cluster/commit/f9f7ca62bbc158253428df169331fe58f4e3c228))
* **next:** gitops-seed vu fait + next cohérent avec preview (signal + observé) ([522947b](https://github.com/univ-lehavre/cluster/commit/522947bb597133d9f8ea91a60c97f6a22f475ca9))
* **next:** signal de santé dataops — webserver, pas un deployment `dagster` inexistant ([5cdfbde](https://github.com/univ-lehavre/cluster/commit/5cdfbde8ae21aed6326d79e069232feb49b60180))
* **next:** signal de santé dataops — webserver, pas un deployment dagster inexistant ([7f52a4b](https://github.com/univ-lehavre/cluster/commit/7f52a4b229c021fe55ecf5bd0b34ec883e357050))
* **node-exec:** 3 correctifs révélés par la preuve banc (ADR 0081 étapes 1+3) ([b2e993d](https://github.com/univ-lehavre/cluster/commit/b2e993dba91b02592ff1049b969aa22bc0c73801))
* **node-exec:** 3 correctifs révélés par la preuve banc (ADR 0081 étapes 1+3) ([1245d64](https://github.com/univ-lehavre/cluster/commit/1245d64f074bbf41db0c9009ebfde69db80e9d6e))
* **plan:** profil `store` monte le stockage objet (datalake/RGW) — chemin `layers` dérivé ([9a53d15](https://github.com/univ-lehavre/cluster/commit/9a53d15e35040d87d5765cd31edf7330cc862f76))
* **plan:** profil store monte le stockage objet (datalake/RGW) — chemin layers dérivé ([0dd6c7f](https://github.com/univ-lehavre/cluster/commit/0dd6c7f188f2953c440d79fcddb4454c3b05bcdd))
* **preview,next:** couche « saine » = dernier maillon READY, pas namespace présent ([b565f92](https://github.com/univ-lehavre/cluster/commit/b565f92eb74659a9dc723fbc491d00dd6377f2b1))
* **preview:** le réel contredit le socle — plus de « ✓ créer les VMs à-jour » sans VM ([c0d1606](https://github.com/univ-lehavre/cluster/commit/c0d1606410a9c59db411d7705935c032edd8d705))
* **preview:** le réel CONTREDIT le socle — plus de « ✓ créer les VMs à-jour » sans VM ([c528b19](https://github.com/univ-lehavre/cluster/commit/c528b1981306926a9e4b58f0707feaa6f9df1f6d))
* **preview:** signaler un backend orphelin (réel ≠ déclaré) — drift rook-ceph ([#356](https://github.com/univ-lehavre/cluster/issues/356)) ([d618bde](https://github.com/univ-lehavre/cluster/commit/d618bde1e49f86ffc6f435cc5012a2f18ded2150))
* **preview:** signaler un backend orphelin réel ≠ déclaré ([#356](https://github.com/univ-lehavre/cluster/issues/356)) ([c643018](https://github.com/univ-lehavre/cluster/commit/c643018fe2a5abe3b279aed3b96c96e43ccc3522))
* **profile:** loki_s3_backing/endpoint manquants → monitoring cassé en local-path ([f5fe5f1](https://github.com/univ-lehavre/cluster/commit/f5fe5f1c39d231af846bbd050e0dc447c40fba8f))
* **remove:** force les pods possédés qui traînent après suppression des racines (ADR 0079) ([ec83d16](https://github.com/univ-lehavre/cluster/commit/ec83d16958d658f72b7e7ae1b41f256c9f3d2aa4))
* **remove:** force les pods POSSÉDÉS qui traînent après suppression des racines (ADR 0079) ([efa4277](https://github.com/univ-lehavre/cluster/commit/efa4277a2a8ad0df6185a213a6e3f9a55c775e55))
* **remove:** rollback conscient du backend — pas d'OBC Ceph en local-path (ADR 0069) ([b1cf3b8](https://github.com/univ-lehavre/cluster/commit/b1cf3b84663aeb0059a2e7ea0f8b293108e70228))
* **remove:** rollback-lib — Application atlas-workflows + CR Argo CD à finaliser ([58050d5](https://github.com/univ-lehavre/cluster/commit/58050d5f153d9dccf8d79b70288413c455c77e71))
* **rollback:** débloquer un ns wedgé + clôture résiliente ([#361](https://github.com/univ-lehavre/cluster/issues/361)) ([dbe4e81](https://github.com/univ-lehavre/cluster/commit/dbe4e8148596385f85a8df6514fecfe1b4969573))
* **rollback:** débloquer un ns wedgé + ne pas abandonner la clôture au 1er échec ([#361](https://github.com/univ-lehavre/cluster/issues/361)) ([c0c3ded](https://github.com/univ-lehavre/cluster/commit/c0c3dedee4ef252c6daa1ec14b489a404e4fc317))
* **s3-bucket:** idempotence du make-bucket sur SeaweedFS (BucketAlreadyExists) ([20bcc58](https://github.com/univ-lehavre/cluster/commit/20bcc581b14ee3e282f5a2a66e6ae0d008bf6268))
* **s3-bucket:** supprimer un Job d'init non-réussi avant de le recréer (template immuable) ([afd5dbc](https://github.com/univ-lehavre/cluster/commit/afd5dbc6469a422603ccd925fab851e223565a6e))
* **topology:** message de `next` clair (sans jargon « 1er drift ») ([ebfdcba](https://github.com/univ-lehavre/cluster/commit/ebfdcba2640c855938944da49c2f845105e9b79a))
* **topology:** next respecte le PLAN de preview (VMs d'abord, phase par phase) ([d4368a3](https://github.com/univ-lehavre/cluster/commit/d4368a38045dfb122fdb8679ce71b9cc5d6c68b5))
* **topology:** stack select n'imprime l'export que si stdout est capturé ([c7db250](https://github.com/univ-lehavre/cluster/commit/c7db250b7cb97921c40ab68d9a59078cc47b73ed))


### Performance

* **hooks:** appeler prettier/commitlint en local (node_modules/.bin) au lieu de pnpm exec ([750050c](https://github.com/univ-lehavre/cluster/commit/750050c53d97cb5f649f23d8923104d48eb765a7))
* **hooks:** pre-commit/pre-push quasi instantanés (binaire local + fichiers du push) ([1808d43](https://github.com/univ-lehavre/cluster/commit/1808d438771ff52c5251bfed79f9b93e6567989f))
* **hooks:** pre-push ne lint que les fichiers du push (prettier/yamllint/shellcheck) ([862d770](https://github.com/univ-lehavre/cluster/commit/862d77080813ed6cdfd9a3ac7c048361d73d48d4))


### Refactor

* **nestor:** renommer la CLI cluster → nestor + hygiène ~/.kube/config (ADR 0053) ([929d863](https://github.com/univ-lehavre/cluster/commit/929d86310b219fc19d8775eacbaf8617540fc666))
* **nestor:** renommer le paquet cluster_topology → nestor ([944e555](https://github.com/univ-lehavre/cluster/commit/944e555ecb239f8083aada6b595e65b8dd19b8e2))


### Documentation

* **adr-0023:** génériser les valeurs prod réelles résiduelles (ADR 0055, RUNBOOK) ([aa1f571](https://github.com/univ-lehavre/cluster/commit/aa1f57133db45c6914c8e7d4dbd14f5411fa33ae))
* **adr:** 0076 — cluster refresh (réel voulu → déclaration, borné par ADR 0046) ([32f58d0](https://github.com/univ-lehavre/cluster/commit/32f58d0900007eaa7884a1708d0172759b5e7e2d))
* **adr:** 0077 — cluster next, menu des couches montables (deps réelles vs convention) ([c0c3751](https://github.com/univ-lehavre/cluster/commit/c0c375107528471816bc7d7f810388703a146e3e))
* **adr:** 0079 — découverte de l'appartenance réelle (socle commun health + remove) ([d1436ba](https://github.com/univ-lehavre/cluster/commit/d1436ba6110462ac583d082ebd265e0cea244286))
* **adr:** 0080 — doctrine d'affichage des notations & badges README ([06336ef](https://github.com/univ-lehavre/cluster/commit/06336eff10b5a05834c6ed0c6f79c2dd358c7c06))
* **adr:** 0081 socle d'exécution node-side (node_exec) — discover + remove ([df30320](https://github.com/univ-lehavre/cluster/commit/df3032011d27d0780fca6234acab4628d56d387d))
* **adr:** 0081 socle d'exécution node-side (node_exec) — discover + remove ([8439675](https://github.com/univ-lehavre/cluster/commit/8439675614a933a2bec1e2fa91ce213d9cf32d40))
* **audit:** passage notations & normes externes (hors cyber) + journal ([b035945](https://github.com/univ-lehavre/cluster/commit/b03594546b1d59eba1ce3b7c722f7f39a4599ae9))
* **audit:** passage notations cyber + fusion des passages en une famille (ADR 0078, supersède 0067) ([6d3774a](https://github.com/univ-lehavre/cluster/commit/6d3774a1604b6c1f6b0f4a380007eb592f03f2df))
* **bonnes-pratiques:** mapper FAIR et OpenGitOps aux preuves ([cd4c29a](https://github.com/univ-lehavre/cluster/commit/cd4c29afc37bf2f830b52d9b5b57848660273470))
* **exposition:** clarifier l'avertissement TLS (CA interne, attendu) ([52e5a31](https://github.com/univ-lehavre/cluster/commit/52e5a314e190924120b53ebb4bbffb4bce71dfc9))
* **readme:** rangée de badges groupée par thématique (ADR 0080) ([3818629](https://github.com/univ-lehavre/cluster/commit/3818629e28cc5576eb3c66d67ebb388f00133890))

## [2.36.0](https://github.com/univ-lehavre/cluster/compare/v2.35.0...v2.36.0) (2026-06-16)


### Features

* **banc:** phase_ha_cni gateway-hostnetwork + access.sh gate l7 (ADR 0071) ([8428376](https://github.com/univ-lehavre/cluster/commit/8428376a7daeacf0b4bcd97f0a5dd4bb9b8e80f2))
* **cli:** commande cluster access (delegue a access.sh, ADR 0048) ([46d9aee](https://github.com/univ-lehavre/cluster/commit/46d9aeed1741e447e0691b26489f3b166a4722c4))
* **cli:** wrapper 'cluster' — raccourci de topology.py ([134e551](https://github.com/univ-lehavre/cluster/commit/134e5515f0448735142186ba33abb0143912c14e))
* **cluster:** outil déclaratif topology.py + corrections de banc + ADR 0068-0074 ([b760901](https://github.com/univ-lehavre/cluster/commit/b760901e9c1220b0e1965505458700dc57d093d6))
* **cni:** gateway en hostnetwork 80/443 (lb-ipam optionnel, ADR 0071) ([73d1e26](https://github.com/univ-lehavre/cluster/commit/73d1e26c6c8022da09a5812347609344292cca03))
* **cni:** hubble-ui activable opt-in dans cni.sh (ADR 0073) ([bc5604f](https://github.com/univ-lehavre/cluster/commit/bc5604f535df31e3915f9b7cad912e1d14933dad))
* **model:** exposition.mode valide + canonique (ADR 0071, gateway|hostport|none) ([0895f1d](https://github.com/univ-lehavre/cluster/commit/0895f1d39334ec178b5a95ae7ae6d0705db3fb32))
* **rollback:** graphe atomique conditionnel au backend (storage local-path) ([cc947c3](https://github.com/univ-lehavre/cluster/commit/cc947c3acc2aee4d4de0486c89285c64b5b28615))
* **topology:** arm bash layers + routage cmd_up (Lot B, ADR 0069) ([7ffc98a](https://github.com/univ-lehavre/cluster/commit/7ffc98a2955de2951533377a56b39d1c236a776b))
* **topology:** briques moteur Python — idempotence (.stats) + gates k8s natifs ([c89019e](https://github.com/univ-lehavre/cluster/commit/c89019e149c7ec6efd6b59dc25c8fbcb57ad6eb5))
* **topology:** cluster discover — reconstruire une topologie depuis un cluster réel (ADR 0074) ([8a8d17c](https://github.com/univ-lehavre/cluster/commit/8a8d17c2d81720142968e4f3071b8ac7f4e1b0db))
* **topology:** commande cluster discover (reconstruire une topologie, ADR 0074) ([852fed0](https://github.com/univ-lehavre/cluster/commit/852fed07e6e4344a2a725088f2b46771d85ee967))
* **topology:** commande cluster scale (replicas = f(noeuds Ready), ADR 0072) ([d404bf8](https://github.com/univ-lehavre/cluster/commit/d404bf8030650202ccb7fc432a7be9fe53ef51b5))
* **topology:** commande context create|list|activate (catalogue + active) ([ca36da2](https://github.com/univ-lehavre/cluster/commit/ca36da2c24b336df80d4a21daf91369d424786e5))
* **topology:** commande destroy — détruit les VMs de la stack active (calque pulumi destroy) ([6475fe5](https://github.com/univ-lehavre/cluster/commit/6475fe5c8c4bb61036ccbca60f8080dd4b6ad72c))
* **topology:** commande env — exporte le KUBECONFIG du banc dans le shell ([0551801](https://github.com/univ-lehavre/cluster/commit/0551801b556a57026416df064a7246c7040239e3))
* **topology:** commande preview — plan complet voulu→réel (calque pulumi preview) ([93efb6f](https://github.com/univ-lehavre/cluster/commit/93efb6fbbcc485d9190b302e1921599f624809e1))
* **topology:** commande stack refresh — état réel lu à la demande (calque pulumi refresh) ([fb0cb75](https://github.com/univ-lehavre/cluster/commit/fb0cb7555d601e2568c78577a74690d42bd57017))
* **topology:** commande up — monte la stack de bout en bout (délègue à run-phases.sh) ([a2fa6d1](https://github.com/univ-lehavre/cluster/commit/a2fa6d1490753badc8744e85dd03b8e466e20741))
* **topology:** exposition.mode consequent dans le banc (ADR 0071) ([727e7d1](https://github.com/univ-lehavre/cluster/commit/727e7d15c5c0e9cfb340124c109642906099791a))
* **topology:** inversion de frontière étape 0+1 — filet de parité + contrat machine facts ([733fc46](https://github.com/univ-lehavre/cluster/commit/733fc460710d1ffaeecddc66abe2613d1cf79a2c))
* **topology:** la topologie pilote les nœuds du banc (up → NODES_OVERRIDE) ([57ec804](https://github.com/univ-lehavre/cluster/commit/57ec804b5f8605692becd3d590036c5cfe5fae21))
* **topology:** model.layers + default_target derive des couches (Lot A, ADR 0069) ([9e33fa0](https://github.com/univ-lehavre/cluster/commit/9e33fa0e3e62da156dfc789df76ecff16f0f0465))
* **topology:** orchestrer le socle k8s en Python (bootstrap-seq, migration ADR 0063) ([f40bf85](https://github.com/univ-lehavre/cluster/commit/f40bf8589336cf74e79eb38689dbd2749c6a0d87))
* **topology:** preview affiche les layers + exemple pedagogique (Lot C, ADR 0069) ([6a1d1b1](https://github.com/univ-lehavre/cluster/commit/6a1d1b1d295e98d8f0accffc2ea850ebbb7415cc))
* **topology:** preview v2 — couches lisibles, jamais≠rejeu, VMs à détruire d'abord ([9f018f2](https://github.com/univ-lehavre/cluster/commit/9f018f22d1ba3b8642d9e928720518c834c896d0))
* **topology:** profil metrics — palier fin base⊂metrics⊂store (ADR 0068) ([7cb4066](https://github.com/univ-lehavre/cluster/commit/7cb4066d281e318a40ac5e59de43079430218156))
* **topology:** resolve_layers — derive l'ordre des couches du graphe (ADR 0069) ([7672267](https://github.com/univ-lehavre/cluster/commit/767226716411af4dcf183851a6da7b0857f03271))
* **topology:** test scenarios filtre sur les couches reellement montees ([a245036](https://github.com/univ-lehavre/cluster/commit/a24503671e5d628677058eefeb49d2d4634dba51))


### Bug Fixes

* **banc:** scénario 28 sonde l'IP du nœud (gateway-hostNetwork, ADR 0071) ([fda92ca](https://github.com/univ-lehavre/cluster/commit/fda92cacaf648d165f26cecf67cf794c8789f662))
* **banc:** scénario 28 sonde l'IP du nœud (gateway-hostNetwork, ADR 0071) ([e11ce82](https://github.com/univ-lehavre/cluster/commit/e11ce82ca286c4afa26be0fabc53fc9bb46cf187))
* **bench:** renommer test/ en bench/ dans .gitignore et .prettierignore ([9a66e59](https://github.com/univ-lehavre/cluster/commit/9a66e599413d7b4702421bfc5169901afb57ef01))
* **ha-3cp:** ha-cni derive le CP (plus de cp1 code) + join-workers saute si pas de worker ([e046781](https://github.com/univ-lehavre/cluster/commit/e046781f3421c8356deb284ee54c0b6b9914e034))
* **ha-3cp:** run_hardening_if_requested ne propage plus rc=1 sur hote plain (9e bug) ([a3f3100](https://github.com/univ-lehavre/cluster/commit/a3f31005706e9edb826a9ae3682df9958a299a85))
* **k8s-install:** idempotence du keyring + cache apt (10e bug, changed=0 au rejeu) ([8fcd757](https://github.com/univ-lehavre/cluster/commit/8fcd757500b392e5ef4595f841538909647e2051))
* **metrologie:** topologie du run derivee de NODES, plus de 'multi-node-3' code ([6691241](https://github.com/univ-lehavre/cluster/commit/6691241c3a7968cfaf8471506f4656007939d94d))
* **runner:** purger env/* d'ansible-runner avant chaque run (anti-contamination) ([f40b8ed](https://github.com/univ-lehavre/cluster/commit/f40b8edf6859f530e23f86579b0509c825fd9a2e))
* **state:** message de joignabilité fidèle au terrain (créer la VM ≠ installer l'OS) ([dae806c](https://github.com/univ-lehavre/cluster/commit/dae806c1e643957ca845759c1aa3967b1b504726))
* **topology:** artifact runs/metrics ciblent la stack active par defaut ([680e407](https://github.com/univ-lehavre/cluster/commit/680e40778ebf5654504031405dd081613ad0e27a))
* **topology:** defaut KUBECONFIG sur le banc pour les commandes etat reel ([cea3f72](https://github.com/univ-lehavre/cluster/commit/cea3f72ac7f40816678b16cdcf460f42af09f8f0))
* **topology:** le plan de preview reconcilie avec le reel (le cluster qui tourne prime) ([760bd5c](https://github.com/univ-lehavre/cluster/commit/760bd5cd0471d6e72536e65850be46e4a42038ac))
* **topology:** masquer complètement ha-3cp du menu (commande interne) ([858f420](https://github.com/univ-lehavre/cluster/commit/858f4201677cdc89f5d22953c5beadb746928734))
* **topology:** preview lit l'etat reel du banc (kubeconfig + nom de stack) ([4d09148](https://github.com/univ-lehavre/cluster/commit/4d091489f9a83fd1485e9d9dcf59fe317a3965bd))
* **topology:** preview matche le run par nom de stack (plus de faux « à-jour ») ([62929d3](https://github.com/univ-lehavre/cluster/commit/62929d3b2c7f87cf6f4549b402fb360aef7633ad))
* **topology:** preview PLAN constate le reel des couches applicatives ([5bbceda](https://github.com/univ-lehavre/cluster/commit/5bbcedaf7e0837cfaa1455c71f7c0c0b77b5c563))
* **topology:** preview VOULU omet le stockage en base + libellé base avec CRI + drift CI ([36d73ef](https://github.com/univ-lehavre/cluster/commit/36d73efcb7b5122538909f1a38ad83e7bf10d1cc))
* **topology:** status fidèle à la topo (hyperconvergence + hôtes --real dérivés) ([3fe50eb](https://github.com/univ-lehavre/cluster/commit/3fe50ebd93279ac59997d13a304118ef966ccd6a))


### Refactor

* **bench:** renommer test/ en bench/ (ADR 0070) ([fa17be1](https://github.com/univ-lehavre/cluster/commit/fa17be1583f27ba7e1674507d5e12b3fbf0f5377))
* **bench:** renommer test/ en bench/ (ADR 0070) ([a54ef6a](https://github.com/univ-lehavre/cluster/commit/a54ef6a80c39dda11fd3e358b368cd8ad7e57fd0))
* **exposition:** mode unique gateway en hostNetwork (ADR 0071, hostport/lb-ipam absorbés) ([1e495ab](https://github.com/univ-lehavre/cluster/commit/1e495abdd9dbfcd9f380c85db07f93fa2bbdd502))
* **topology:** aligner les commandes sur Pulumi (new + stack ls|select) ([eb12b49](https://github.com/univ-lehavre/cluster/commit/eb12b49dc0b80532bc0609c1ca52e37283c9346f))
* **topology:** base = socle nu (stockage hors du socle de base, ADR 0039) ([fbbc132](https://github.com/univ-lehavre/cluster/commit/fbbc132deb88b735aeff5c16e5bd066a5053e60e))
* **topology:** catalogue gitignore topologies/ + symlink d'activation ([a537bb3](https://github.com/univ-lehavre/cluster/commit/a537bb3b95050722058286f701f725553f0def52))
* **topology:** exposition mode unique gateway (hostport absorbé en alias) ([a97f1cb](https://github.com/univ-lehavre/cluster/commit/a97f1cbedf5719329732fcaf67c8e0f125d657ba))
* **topology:** groupes artifact + test, epreuves→scenarios, ha-3cp masquée ([0670169](https://github.com/univ-lehavre/cluster/commit/0670169f90a1a140fc44835e349390e8cffaffe8))
* **topology:** menu plat type Pulumi — refresh au top-level ([2cdeaf8](https://github.com/univ-lehavre/cluster/commit/2cdeaf8357ec30569c7389d6bf1a5964d4d9e998))
* **topology:** new devient stack new (pas de notion de projet) ([a40398e](https://github.com/univ-lehavre/cluster/commit/a40398ec994383f13b3541a0ff23da7ce5a27ab8))
* **topology:** preview = voir (voulu+réel+plan), up = appliquer ; ménage du menu ([ba333ad](https://github.com/univ-lehavre/cluster/commit/ba333adc5c100399e8e25e1ca6d19b32aec5de5a))
* **topology:** renommer la commande up en next (up ne tenait pas sa promesse) ([34e56a3](https://github.com/univ-lehavre/cluster/commit/34e56a318d5c29ef6b71c6b34b18bded8726a00f))
* **topology:** retirer validate et default-target du menu CLI ([5e39545](https://github.com/univ-lehavre/cluster/commit/5e39545837e3fbb78d230aa62c62e6e4d8d51cad))


### Documentation

* **adr:** 0069 topology.layers — couches en DAG grain phase ([dea5ee1](https://github.com/univ-lehavre/cluster/commit/dea5ee1a5f314b5fbbac26a9a57e61d7e8f5fc4e))
* **adr:** 0070 renommer test/ en bench/ ; bootstrap/ a plat ([17a2f9e](https://github.com/univ-lehavre/cluster/commit/17a2f9e581e6d6580541b80f68aa56609828a02e))
* **adr:** 0071 NodePort, 0072 cluster scale, 0073 hubble-ui (Proposed) ([97d9a11](https://github.com/univ-lehavre/cluster/commit/97d9a115087255430ff3eb67cb0c418e1ef88e62))
* **adr:** 0071 reecrit autour de hostport (NodePort abandonne) ([4dce3a9](https://github.com/univ-lehavre/cluster/commit/4dce3a9ee72c214fa4f322c72c6b538c450563de))
* **adr:** 0074 cluster discover — reconstruire un topology.yaml depuis un cluster reel ([68d2a2d](https://github.com/univ-lehavre/cluster/commit/68d2a2d8a56f6fbe34a6aa7b14ea698f6766a8f4))
* **adr:** 0074 enrichi — taxonomie des kinds sondes + bilan de sante ([ed0d195](https://github.com/univ-lehavre/cluster/commit/ed0d195d52dcb35e91499a3e9d5dd7d58dfb289d))
* **adr:** 0075 kyverno cli statique en ci + audit cncf ([89f1d35](https://github.com/univ-lehavre/cluster/commit/89f1d35be584275cf04897ab610afbf74f9a5cd1))
* **adr:** 0075 kyverno cli statique en ci + audit cncf ([9036aff](https://github.com/univ-lehavre/cluster/commit/9036aff28e59cf32accc0446b819542de287c772)), closes [#347](https://github.com/univ-lehavre/cluster/issues/347)
* **bootstrap:** réindexer le README par phase + note 4 « topology » (ADR 0070) ([764458a](https://github.com/univ-lehavre/cluster/commit/764458a5386d29cf3f5552b405e2ad630e128a59))
* **cli:** menu cluster --help en langage clair, sans jargon ([1cc0bb8](https://github.com/univ-lehavre/cluster/commit/1cc0bb8b327ea8a391afecae02df2811ccaf9040))

## [2.35.0](https://github.com/univ-lehavre/cluster/compare/v2.34.1...v2.35.0) (2026-06-14)


### Features

* **banc:** auto-détecter l'état de durcissement (2ᵉ axe ADR 0065) ([354a769](https://github.com/univ-lehavre/cluster/commit/354a7691d63717e669649c6fb6e9ba581b4989eb))
* **banc:** classify_hardening_signal — verdict d'état de durcissement (ADR 0065 §2) ([1145d29](https://github.com/univ-lehavre/cluster/commit/1145d29627a41a4bd914306fc00c042bd0604752))
* **banc:** détecter l'état de durcissement, dériver +hardening de la réalité ([0bf4fdb](https://github.com/univ-lehavre/cluster/commit/0bf4fdb8efc8e475c66be1989f0d5d282e125f91))
* **docs:** remanier la sidebar et la nav (adr par thème, archi & preuves, liens à jour) ([2cdb96e](https://github.com/univ-lehavre/cluster/commit/2cdb96e9211fc1edf87107df44ecf7c04f40bfec))
* **gouvernance:** auditer le respect des conventions + afficher les chiffres (adr 0060) ([2023a96](https://github.com/univ-lehavre/cluster/commit/2023a96b4a64d2dab94cca1b1be475a6b2c91e33))
* **gouvernance:** auditer le respect des conventions + afficher les chiffres (ADR 0060) ([da17034](https://github.com/univ-lehavre/cluster/commit/da17034b06a07184735d228cc65fc2245155e9ba))
* **ha-3cp:** chemin codé + rôle de promotion CP + gates etcd ([#250](https://github.com/univ-lehavre/cluster/issues/250)) ([bd5e469](https://github.com/univ-lehavre/cluster/commit/bd5e469a68e223b34554c30da3be9d87ab242173))
* **ha-3cp:** chemin codé + rôle de promotion CP + gates etcd ([#250](https://github.com/univ-lehavre/cluster/issues/250)) ([52c1b70](https://github.com/univ-lehavre/cluster/commit/52c1b705dea42e1c3785a39753a67ef0ef20c15e))
* **ha-3cp:** rôle kube-vip (VIP API, pod statique ARP) + certSANs VIP ([#250](https://github.com/univ-lehavre/cluster/issues/250)) ([08ab880](https://github.com/univ-lehavre/cluster/commit/08ab880c0443231901358d876ba759ca45ac21ef))
* **ha-3cp:** rôle kube-vip (VIP API) + certSANs VIP ([#250](https://github.com/univ-lehavre/cluster/issues/250)) ([c9fc13f](https://github.com/univ-lehavre/cluster/commit/c9fc13ffd14cc15f4d5301e69a71e85a8cd6ab98))
* **rollback:** arêtes stockage bloc + clôture par phase dérivée (ADR 0066 Lot 1) ([43314db](https://github.com/univ-lehavre/cluster/commit/43314db7fa8b6d6248a5b0cc794b4c58b39f992d))
* **rollback:** graphe atomique des composants (ADR 0066 Lot 0) ([39614a2](https://github.com/univ-lehavre/cluster/commit/39614a262a3622077ab4d65496356b7f202cd2d2))
* **rollback:** graphe atomique des composants + 1ʳᵉ trace workflow (ADR 0066 Lot 0) ([00e2060](https://github.com/univ-lehavre/cluster/commit/00e2060c14b694999a800ee186be92c52114a493))
* **topologie:** boucle « que faire ensuite » via ansible-runner (adr 0056/0063, p5) ([d79daf0](https://github.com/univ-lehavre/cluster/commit/d79daf0ea2d2fec625c548dac24b814d8bf51a91))
* **topologie:** boucle « que faire ensuite » via ansible-runner (ADR 0056/0063, P5) ([1d9d222](https://github.com/univ-lehavre/cluster/commit/1d9d222dab0983c7a22de6497a6795c914a01961))
* **topologie:** commande roundtrip — réversibilité de couche par clôture (adr 0056/0066) ([e841818](https://github.com/univ-lehavre/cluster/commit/e841818702188215bbcf805d0e65d9ab88102fe6))
* **topologie:** commande roundtrip — réversibilité de couche par clôture (ADR 0056/0066) ([9f37018](https://github.com/univ-lehavre/cluster/commit/9f37018c110d73194e43dd1204a4eb8f0f9a0bbe))
* **topologie:** dérivation de profil pure à parité bash (adr 0056, p2) ([77928b5](https://github.com/univ-lehavre/cluster/commit/77928b5d7db550f37ae5cfac65fe789e3c960ff3))
* **topologie:** dérivation de profil pure à parité bash (ADR 0056, P2) ([c710be3](https://github.com/univ-lehavre/cluster/commit/c710be3fe589108c3cc35dc192d05b1e71cdbd41))
* **topologie:** épreuves filtrées + lecture de l'historique (adr 0056, p4) ([976c97e](https://github.com/univ-lehavre/cluster/commit/976c97e97cdd6603a3296f0e4f76952a341f50b6))
* **topologie:** épreuves filtrées + lecture de l'historique (ADR 0056, P4) ([ba63c7c](https://github.com/univ-lehavre/cluster/commit/ba63c7c829d67935fa88859890903346713a27c4))
* **topologie:** façade CLI/CI generate/validate/status/diff (adr 0056, p3) ([2692756](https://github.com/univ-lehavre/cluster/commit/2692756819be4d35ceaa2572959c98492331f2b6))
* **topologie:** façade CLI/CI generate/validate/status/diff (ADR 0056, P3) ([71abd16](https://github.com/univ-lehavre/cluster/commit/71abd16fc33a283a4c05fdc0aea37ce076c2c258))
* **topologie:** générateur byte-identique de l'inventaire banc Lima (adr 0056, p1) ([32d8d0e](https://github.com/univ-lehavre/cluster/commit/32d8d0ee1b10df211db5dd96dc9a0fdb184e62c8))
* **topologie:** générateur byte-identique de l'inventaire banc Lima (ADR 0056, P1) ([773406e](https://github.com/univ-lehavre/cluster/commit/773406e1f2d2d0e333f317fcbf34d44db8628b93))
* **topologie:** métriques exposées + smoke-test de réversibilité (adr 0056, p6) ([1544b58](https://github.com/univ-lehavre/cluster/commit/1544b58da6198efc8099f351f4017a41dd4f59c6))
* **topologie:** métriques exposées + smoke-test de réversibilité (ADR 0056, P6) ([0ac3f65](https://github.com/univ-lehavre/cluster/commit/0ac3f65a5defaddc9291741acda2a3fe0f2134ea))
* **topologie:** socle de l'outil déclaratif — schéma + générateur byte-identique (adr 0056, p0/p1) ([ebb5806](https://github.com/univ-lehavre/cluster/commit/ebb58065e52196b55867a660762409c656871487))
* **topologie:** socle de l'outil déclaratif — schéma + générateur byte-identique (ADR 0056, P0/P1) ([21f2771](https://github.com/univ-lehavre/cluster/commit/21f277181715c4027e70c4e7f0551a7c377b0d4c))
* **topology:** déclarer ha-3cp + valider control_plane_lb.mode (P7 [#250](https://github.com/univ-lehavre/cluster/issues/250)) ([b07febb](https://github.com/univ-lehavre/cluster/commit/b07febbaea02ace0c6ef2f03bdaadee0a61dcd80))
* **topology:** déclarer la topologie ha-3cp + valider control_plane_lb.mode (P7 [#250](https://github.com/univ-lehavre/cluster/issues/250)) ([c0d3c47](https://github.com/univ-lehavre/cluster/commit/c0d3c476f3ae45dd6cca31acc61af57d1571722b))


### Bug Fixes

* **banc:** auto-détecter le profil de stockage ([#319](https://github.com/univ-lehavre/cluster/issues/319)) + ADR 0065 + durcissement rollback ([d003840](https://github.com/univ-lehavre/cluster/commit/d0038400659939fa967ee60be4c64297da7e1c59))
* **banc:** auto-détecter le profil de stockage au lieu de WITH_CEPH ([#319](https://github.com/univ-lehavre/cluster/issues/319), adr 0065) ([54a5c66](https://github.com/univ-lehavre/cluster/commit/54a5c6633aaa1e24954c6d0c79062a371ee6ac05))
* **banc:** détection durcissement — sonder la joignabilité, paquet absent = plain ([e5685ec](https://github.com/univ-lehavre/cluster/commit/e5685ec591910a7c84621905efe351d56f153d00))
* **banc:** durcir k8s_force_delete_ns (finalize canonique, continue-on-error, barman) ([e8b0e05](https://github.com/univ-lehavre/cluster/commit/e8b0e054b77fe6a423fb423b7896c83d561862b2))
* **banc:** rollback monitoring/dataops emporte leur OBC dans rook-ceph ([#319](https://github.com/univ-lehavre/cluster/issues/319)-suite) ([6ee4738](https://github.com/univ-lehavre/cluster/commit/6ee473830bf2fd27ef05a7be1044c8e3fac8dd24))
* **bootstrap:** figer le patch kubernetes à l'install (reproductibilité, [#295](https://github.com/univ-lehavre/cluster/issues/295)) ([97303e4](https://github.com/univ-lehavre/cluster/commit/97303e4636da59431ab13cd09b0f5f38577801c1))
* **bootstrap:** poser le hold apt sur containerd.io (aligne adr 0005, [#295](https://github.com/univ-lehavre/cluster/issues/295)) ([7c3c543](https://github.com/univ-lehavre/cluster/commit/7c3c5436a7351197933a1e635fe09073981732d2))
* **bootstrap:** reproductibilité install + supply-chain (hold containerd, patch k8s figé, actions par sha) ([7cb8cdb](https://github.com/univ-lehavre/cluster/commit/7cb8cdba0b547aedafdcb41004da2ba8cc813872))
* **bootstrap:** versionner le client k8s et le provisionner par uv sync ([137aa65](https://github.com/univ-lehavre/cluster/commit/137aa65fa054012339484120aff3f76631bb7dea))


### Refactor

* abandonner tailscale au profit de kubectl port-forward ([6ad1832](https://github.com/univ-lehavre/cluster/commit/6ad18320045de49f762b3f60becbab27da9864e9))
* abandonner tailscale au profit de kubectl port-forward ([#281](https://github.com/univ-lehavre/cluster/issues/281)) ([46421d4](https://github.com/univ-lehavre/cluster/commit/46421d4222306c41f94847f1a115e50643345892))
* **gouvernance:** renommer le workflow en conventions-freshness (éviter la collision « audit ») ([ef6802f](https://github.com/univ-lehavre/cluster/commit/ef6802f96629340f3c7e3f60dbac00495cb1879b))
* retirer les buckets de cas d'usage nommés du datalake ([b515d3e](https://github.com/univ-lehavre/cluster/commit/b515d3e5eb4f73052c631db7af076bfc02b3811b))
* retirer les buckets de cas d'usage nommés du datalake (adr 0023) ([ae45df0](https://github.com/univ-lehavre/cluster/commit/ae45df0e1cd69f7c266d8a31821f87a59e84d568))
* **roundtrip:** consommer le graphe atomique (supprime la 2ᵉ source) ([ed1b39f](https://github.com/univ-lehavre/cluster/commit/ed1b39f0bf115eb6babb9362e1920b8ea88f9f46))
* **roundtrip:** consommer le graphe atomique + arêtes stockage bloc (ADR 0066 Lot 1) ([e7f5d2b](https://github.com/univ-lehavre/cluster/commit/e7f5d2ba097aaf9b73fa9f22fd9eb8c69a2d1329))


### Documentation

* achever le manifeste (méthode, voyage, résultats) et ajouter la vitrine des preuves ([cb4803e](https://github.com/univ-lehavre/cluster/commit/cb4803ee08cb1b90d712a65867aeb02cf3627743))
* **adr:** acter ansible-runner pour la boucle p5, différer textual (adr 0063) ([383f2f8](https://github.com/univ-lehavre/cluster/commit/383f2f8d4892b96defbb00ea61547c019d191be3))
* **adr:** acter les cultures d'ingénierie revendiquées (adr 0062) + vue transverse ([99c54e6](https://github.com/univ-lehavre/cluster/commit/99c54e6cda77ee85617df01e204501a7a0d3bd18))
* **adr:** consigner les workflows multi-agents comme 4ᵉ trace empirique (ADR 0067) ([6552455](https://github.com/univ-lehavre/cluster/commit/65524551e1a1787872fb4520d53eb2b430e8a85d))
* **adr:** cultures d'ingénierie revendiquées (ADR 0062) + vue transverse ([343f9fe](https://github.com/univ-lehavre/cluster/commit/343f9fe65601f069a85ad4291ebf45a35fe6420c))
* **adr:** poser la posture d'adoption des bonnes pratiques (adr 0061, principe-chapeau) ([d35cff8](https://github.com/univ-lehavre/cluster/commit/d35cff808e6791d8e467d5f7ac357713ec2f600a))
* **adr:** posture d'adoption des bonnes pratiques (ADR 0061) + inventaire ([1dfd271](https://github.com/univ-lehavre/cluster/commit/1dfd271bd3f00446e3e49604359ec8973b8281df))
* **adr:** rollback atomique — composants + graphe de dépendances unique (adr 0066) ([987b0e7](https://github.com/univ-lehavre/cluster/commit/987b0e72859e8783f03989b6106ef25e443fafd5))
* **adr:** rollback atomique — composants + graphe de dépendances unique (ADR 0066) ([5edc4e9](https://github.com/univ-lehavre/cluster/commit/5edc4e94a8fe705d5b21ab10dd857bf3a9a94bc2))
* **adr:** variables d'env — intention vs état détectable (adr 0065) ([04a42c8](https://github.com/univ-lehavre/cluster/commit/04a42c8cbc2b9384d95f2b807f040e5e963973c3))
* **adr:** workflows multi-agents consignés — 4ᵉ trace empirique (ADR 0067) ([4da00bb](https://github.com/univ-lehavre/cluster/commit/4da00bb14f429ff5fde19a18113dcadd10a3a89d))
* ajouter la preuve de banc à la cartographie de traçabilité (adr 0034/0052) ([a9faaa2](https://github.com/univ-lehavre/cluster/commit/a9faaa2e36c390d6ec15243c735df397f741fe95))
* aligner sur le catalogue générique (adr 0023), enrichir le glossaire, rafraîchir les chiffres ([9d1f0c5](https://github.com/univ-lehavre/cluster/commit/9d1f0c58bbfa982b877619d99a78fa435205f764))
* **audit:** consigner le workflow de vérification du graphe atomique (4ᵉ trace) ([651e60c](https://github.com/univ-lehavre/cluster/commit/651e60c2cb051e1b255a7c5d8897002932dc7509))
* **drifts:** porter L12 et L44 par leurs issues ([#318](https://github.com/univ-lehavre/cluster/issues/318), [#319](https://github.com/univ-lehavre/cluster/issues/319)) ([3ede52d](https://github.com/univ-lehavre/cluster/commit/3ede52dd492aa783ab6e7ca0ee4353fdc8a19932))
* **drifts:** porter L12 et L44 par leurs issues ([#318](https://github.com/univ-lehavre/cluster/issues/318), [#319](https://github.com/univ-lehavre/cluster/issues/319)) ([024ce4f](https://github.com/univ-lehavre/cluster/commit/024ce4fff2c70058dd5ef0870985daabe5c92bbb))
* durcir le workflow documentaire (adr 0057) — état du plan, cycle de vie adr, nommage ([8a4aaa2](https://github.com/univ-lehavre/cluster/commit/8a4aaa2c7f2b2730e26583860ab0da5a63d7382e))
* durcir le workflow documentaire (ADR 0057) — état du plan, cycle de vie ADR, nommage ([5f1d4ad](https://github.com/univ-lehavre/cluster/commit/5f1d4ad64e3576f821f0a5dc307075c18cedc766))
* inscrire le registre des drifts dans la cartographie du workflow (adr 0058 §6) ([f529ec6](https://github.com/univ-lehavre/cluster/commit/f529ec60fa840b0b820ed8c0140e05dea06ea04f))
* inventorier les bonnes pratiques appliquées au dépôt (réf. adr 0061) ([f29ddc6](https://github.com/univ-lehavre/cluster/commit/f29ddc627177baf6db085cd58282baee2c11e657))
* **plans:** ajouter la section Suivi manquante aux 3 plans achevés (adr 0057 §3) ([376d0fd](https://github.com/univ-lehavre/cluster/commit/376d0fdbb7d9004c49d1ade8cc9b1dbcd78955bb))
* **plans:** ajouter la section Suivi manquante aux 3 plans achevés (ADR 0057 §3) ([528d489](https://github.com/univ-lehavre/cluster/commit/528d4895c2deef92f200da8c9d77f59536843942))
* **plans:** câbler le plan rollback-par-phase à son issue [#274](https://github.com/univ-lehavre/cluster/issues/274) ([01abe9b](https://github.com/univ-lehavre/cluster/commit/01abe9b0670efac8064a474e26fdc940d37bc55b))
* **plans:** câbler le plan rollback-par-phase à son issue [#274](https://github.com/univ-lehavre/cluster/issues/274) (adr 0057) ([03ab579](https://github.com/univ-lehavre/cluster/commit/03ab5794680aa945d8fb4e576b42ef94b4e1716d))
* rattraper la refonte documentaire (manifeste + diátaxis) de [#279](https://github.com/univ-lehavre/cluster/issues/279) ([9f856df](https://github.com/univ-lehavre/cluster/commit/9f856dfdb0b35773619ab99bd6d86c629642e499))
* refonte — achever le manifeste, vitrine des preuves, diátaxis & nav ([ad7a49a](https://github.com/univ-lehavre/cluster/commit/ad7a49a59410536c83307da950e3b5997cad556d))
* refonte documentaire — hero, manifeste, Diátaxis (ADR 0055) ([c245e15](https://github.com/univ-lehavre/cluster/commit/c245e1599a5e245b86e08645b85776d861c508bf))
* retirer STATUS.md au profit des plans et passages d'audit ([ceeb91f](https://github.com/univ-lehavre/cluster/commit/ceeb91fa761a1356d00a644ee6c149b97287e148))
* retirer STATUS.md au profit des plans et passages d'audit (adr 0057/0058) ([e6975e5](https://github.com/univ-lehavre/cluster/commit/e6975e53352ce78f46fdc5354986348418cbd0b8))
* scinder le guide dev data selon diátaxis (how-to, tutorial, référence) ([718d13e](https://github.com/univ-lehavre/cluster/commit/718d13e2812e5018f78242e85026a2d61e602b7e))
* **stockage:** acter Longhorn comme 3e profil du catalogue (ADR 0064, Proposed) ([b105196](https://github.com/univ-lehavre/cluster/commit/b105196ae877794d57fc2a2917a545cbd6eac587))
* **stockage:** acter longhorn comme 3e profil du catalogue (adr 0064) ([dc2f53e](https://github.com/univ-lehavre/cluster/commit/dc2f53e879b55855f1e28556056938ef916d3288))

## [2.34.1](https://github.com/univ-lehavre/cluster/compare/v2.34.0...v2.34.1) (2026-06-13)


### Bug Fixes

* **ceph:** rescue diagnostique sur la gate de convergence (ADR 0050/0056) ([19065b4](https://github.com/univ-lehavre/cluster/commit/19065b4270ec324f5f20ea83e7fd87d6748d2b7b))
* **ceph:** rescue diagnostique sur la gate de convergence Rook-Ceph ([a088a3c](https://github.com/univ-lehavre/cluster/commit/a088a3c80be6fe29831425181a7736a55118be06))


### Refactor

* **bash:** factoriser les primitives ssh + log des scénarios ([97474eb](https://github.com/univ-lehavre/cluster/commit/97474eb3a42f8af3fa5f07376d21db148656102d))
* **bash:** factoriser les primitives ssh + log des scénarios ([#296](https://github.com/univ-lehavre/cluster/issues/296)) ([0b64da9](https://github.com/univ-lehavre/cluster/commit/0b64da96674191ff4914ffcfab4caa4330cebf1f))


### Documentation

* **adr:** ADR 0056 modèle déclaratif unifié des topologies ([177e799](https://github.com/univ-lehavre/cluster/commit/177e799a03848bc74b6937b97a0e66bd6cffb1a7))
* **adr:** adr 0057 gouvernance documentaire (adr décide, plan met en œuvre) ([b488799](https://github.com/univ-lehavre/cluster/commit/b488799513b93b88f4b38abcd27ddb7f214bcb68))
* **adr:** ADR 0057 gouvernance documentaire (ADR décide, plan met en œuvre) ([4b2b47d](https://github.com/univ-lehavre/cluster/commit/4b2b47dab36be8af88c24fac024461502c194a55))
* **adr:** adr 0058 doctrine de l'audit (grille permanente, passages datés) ([d6076ac](https://github.com/univ-lehavre/cluster/commit/d6076ac639fd31f2917bb1bbed3e8ad6bd16f376))
* **adr:** ADR 0058 doctrine de l'audit (grille permanente, passages datés) ([efa8332](https://github.com/univ-lehavre/cluster/commit/efa83322620b3cd487bd233a31e0f5fba56f7195))
* **adr:** ajouter adr 0056 modèle déclaratif unifié des topologies ([57695c2](https://github.com/univ-lehavre/cluster/commit/57695c29a841669c1f1d39adaa4bc23eb786c4ab))
* aligner la prose sur l'outillage réel — release-please + merge commit ([#294](https://github.com/univ-lehavre/cluster/issues/294)) ([432aa62](https://github.com/univ-lehavre/cluster/commit/432aa625255c76bf749eb333692cc2d2b4c07e0f))
* aligner la prose sur l'outillage réel (release-please + merge commit) ([23145c8](https://github.com/univ-lehavre/cluster/commit/23145c832a9c8c9e5cf661394455865b85479c67))
* **audit:** restructurer docs/audit/ en grille permanente + passage daté (ADR 0058) ([ab220aa](https://github.com/univ-lehavre/cluster/commit/ab220aa1b85f7d54a65ac18f6985cc955b5410a6))
* **audit:** restructurer en grille permanente + passage daté (adr 0058) ([#292](https://github.com/univ-lehavre/cluster/issues/292)) ([1cff2ee](https://github.com/univ-lehavre/cluster/commit/1cff2eeb8c93556ce6d363ad8ddec749292dd0e9))
* durcir CONTRIBUTING + plans/README selon ADR 0057 ([1e3ff0a](https://github.com/univ-lehavre/cluster/commit/1e3ff0a287f08f0525b1c0b921e301f73bbc4eee))
* durcir CONTRIBUTING + plans/README selon adr 0057 ([#290](https://github.com/univ-lehavre/cluster/issues/290)) ([629722d](https://github.com/univ-lehavre/cluster/commit/629722d92f0710b7ba8b09fbe5d70ca284b1432a))

## [2.34.0](https://github.com/univ-lehavre/cluster/compare/v2.33.0...v2.34.0) (2026-06-12)


### Features

* **bootstrap:** finaliser [#236](https://github.com/univ-lehavre/cluster/issues/236) — reprise classe (a) + hygiène d'idempotence ([071c586](https://github.com/univ-lehavre/cluster/commit/071c5863b6e27a6ef60a6ff33236d70cb5b4ead7))
* **bootstrap:** garde-fous inventaire + contextes kubeconfig non homonymes (ADR 0053, [#272](https://github.com/univ-lehavre/cluster/issues/272)) ([daefbc2](https://github.com/univ-lehavre/cluster/commit/daefbc27d18b3a25028509e1285fbabe369686c5))
* **bootstrap:** reprise après faute injectée sur init/join (ADR 0050, [#236](https://github.com/univ-lehavre/cluster/issues/236)) ([cca8675](https://github.com/univ-lehavre/cluster/commit/cca8675e9309bd75e5e7377d7b328212cb2647f7))
* **ceph:** porter le déploiement Rook-Ceph en rôles ansible ([6e729ec](https://github.com/univ-lehavre/cluster/commit/6e729ec5d85d9edefa67e9afee8e731e3caa39fa))
* **cnpg:** générer les secrets de rôles pg via ansible (source surchargeable) ([f52b617](https://github.com/univ-lehavre/cluster/commit/f52b617117b9deaca7be8820ed78f3e786179a1a))
* **cnpg:** générer les secrets de rôles pg via ansible (source surchargeable) ([f6eb7c4](https://github.com/univ-lehavre/cluster/commit/f6eb7c48a1c4a2f6de0da9614dc4ad6fc1b11344))
* **contract:** garde-fou statique contrat→platform ([#271](https://github.com/univ-lehavre/cluster/issues/271) phase 3, ADR 0043) ([a693e61](https://github.com/univ-lehavre/cluster/commit/a693e618b855caa02b76620ac49de86aeb4f94fc))
* **platform:** rescue diagnostique gitea/marquez/dagster (ADR 0050, [#236](https://github.com/univ-lehavre/cluster/issues/236)) ([87a417b](https://github.com/univ-lehavre/cluster/commit/87a417bcb885d49363a0461626c853562900a829))
* **rollback:** câbler rollback par phase + primitives kubectl (ADR 0054, [#274](https://github.com/univ-lehavre/cluster/issues/274) lot 2) ([236815f](https://github.com/univ-lehavre/cluster/commit/236815fb3c589d90d85df0a23706658ec5855c84))
* **rollback:** primitives pures du rollback par phase (ADR 0054, [#274](https://github.com/univ-lehavre/cluster/issues/274) lot 1) ([c6d2bd9](https://github.com/univ-lehavre/cluster/commit/c6d2bd91e0ab14119bc022b053a4c4cd9662c134))
* **state:** healthcheck cluster en lib pure + garde-fou de cible (ADR 0053, [#272](https://github.com/univ-lehavre/cluster/issues/272)) ([f5ec2a2](https://github.com/univ-lehavre/cluster/commit/f5ec2a2f8286647954cf3a3d0771ff065b82da69))
* **status:** câbler phase_status sur la lib partagée health-classify ([2ca98fa](https://github.com/univ-lehavre/cluster/commit/2ca98fa6bac0f555c8a17fd2ae89bc761cfa96c2))


### Bug Fixes

* **bootstrap-fault:** nom NP argocd réel + good_sc détecté du cluster ([#236](https://github.com/univ-lehavre/cluster/issues/236)) ([4edc599](https://github.com/univ-lehavre/cluster/commit/4edc599b1f4e7c2d16a6f0c00bcc8564fda58895))
* **bootstrap:** cri-keyring = idempotence réparatrice, pas reprise après échec ([7058711](https://github.com/univ-lehavre/cluster/commit/705871177ca892c2736252d7c4f53ca305d774f9))
* **bootstrap:** rescue join — marqueur honnête + nettoyage (révélé par arrêt injecté) ([380d754](https://github.com/univ-lehavre/cluster/commit/380d7544d2375c71d469ddd5559a8beaeb691c5a))
* **ceph:** gate attend la réconciliation Rook (phase Ready + observedGeneration) ([8ec2a5e](https://github.com/univ-lehavre/cluster/commit/8ec2a5eda87dd322a37f1782e06f363ebf360f15))
* **ceph:** idempotence datalake — stabiliser le CephObjectStore (densification Rook) ([9aca131](https://github.com/univ-lehavre/cluster/commit/9aca1315ad3f51225a42f411a7740bc6dc3b28aa))
* **ceph:** idempotence SC — stabiliser les CR Rook (block pools + CephFS) ([1780d5f](https://github.com/univ-lehavre/cluster/commit/1780d5f3b79ba6b8257d7984828f654db0e0bb29))
* **ceph:** masquer .status du diff d'idempotence (vraie cause du faux changed) ([cc0a5bb](https://github.com/univ-lehavre/cluster/commit/cc0a5bb7d21fb9b7cbcaadcbe88bb0de97aa10e7))
* **ceph:** stabiliser le spec (densification Rook) avant de finir — vraie cause idempotence ([b632d47](https://github.com/univ-lehavre/cluster/commit/b632d472eda18c50ce3ad34c7f67afdce1a4a304))
* **ceph:** tolérer HEALTH_WARN bénin (RECENT_MGR_MODULE_CRASH) dans la gate ([e8b0a60](https://github.com/univ-lehavre/cluster/commit/e8b0a60fa3a629f6b8b09e179a3c46cb06688643))
* **citation:** version réelle (2.33.0) + DOI Zenodo ([#271](https://github.com/univ-lehavre/cluster/issues/271) phase 0) ([c242d13](https://github.com/univ-lehavre/cluster/commit/c242d13b8e6b960033714870242ed1466bdf8067))
* **cni:** éviter le SIGPIPE qui tue cni.sh pendant l'attente KubeProxyReplacement ([c64553f](https://github.com/univ-lehavre/cluster/commit/c64553f1d0ca589f986e934c93d790aee018b890))
* **k8s-init:** retirer le lost+found d'une LV etcd vierge avant kubeadm init ([9f6edf4](https://github.com/univ-lehavre/cluster/commit/9f6edf49f70f61932f93c642ed39403ab0186220))
* **k8s-init:** retirer le lost+found d'une LV etcd vierge avant kubeadm init ([ca11adb](https://github.com/univ-lehavre/cluster/commit/ca11adbea055cac9c1837e3ef09f00a22c91de8e))


### Documentation

* **adr:** ADR 0055 ha-3cp hyperconvergé (3 CP sur 4 nœuds) + amender ADR 0002 ([0038fc2](https://github.com/univ-lehavre/cluster/commit/0038fc20bebc8aa530534b4e8003f423e677ec5b))
* **adr:** ajouter adr 0055 ha-3cp hyperconvergé + amender adr 0002 ([abfd053](https://github.com/univ-lehavre/cluster/commit/abfd053d52f91ec301f3e9c2a79042dc46023531))
* **adr:** isolation multi-cible banc/prod + boîte à outils (0053, [#272](https://github.com/univ-lehavre/cluster/issues/272)) ([2b72533](https://github.com/univ-lehavre/cluster/commit/2b72533f7aabf81b2665261b39f1425561922c2a))
* **adr:** reproductibilité des résultats — principe-chapeau (0052) ([f6d3bee](https://github.com/univ-lehavre/cluster/commit/f6d3bee1dca01eb59bdfadaa17e11617e8006221))
* **adr:** reproductibilité des résultats — principe-chapeau (0052) ([65a19ac](https://github.com/univ-lehavre/cluster/commit/65a19ac7deeb881b02f5f9240f771e5755d2e112))
* **adr:** rollback par phase sur le banc (ADR 0054 + plan + [#274](https://github.com/univ-lehavre/cluster/issues/274)) ([7560daf](https://github.com/univ-lehavre/cluster/commit/7560dafb1d53d416427081bc87c55b00d4b763ce))
* renvoyer au principe-chapeau reproductibilité (0052) dans CLAUDE.md ([b74163e](https://github.com/univ-lehavre/cluster/commit/b74163eac02db3de16c7fc03a6dfb79727190bb9))
* **results:** run [#14](https://github.com/univ-lehavre/cluster/issues/14) — portage Ceph from-scratch, avec réserves (ADR 0052) ([20989c9](https://github.com/univ-lehavre/cluster/commit/20989c9fbc2d50654bb946322a77a70256fd4d57))
* **results:** run [#15](https://github.com/univ-lehavre/cluster/issues/15) — atlas-ceph from-scratch complet + rollback de phase prouvé ([24f8151](https://github.com/univ-lehavre/cluster/commit/24f815141502783a8aa909395dd9764a31dfcddc))
* **runbook:** clarifier les volumes par nœud (lv_etcd cp vs workers) ([623ef63](https://github.com/univ-lehavre/cluster/commit/623ef637a314cdf1667bbe4bb2d685a64dabf99a))

## [2.33.0](https://github.com/univ-lehavre/cluster/compare/v2.32.0...v2.33.0) (2026-06-11)


### Features

* **ansible:** options natives hors-banc + règle « pas de constante en dur » (ADR 0051/0023) ([ce193f2](https://github.com/univ-lehavre/cluster/commit/ce193f236271c97def2b51def2806def2c19d20b))
* **banc:** accès dev atlas en une commande (access.sh) + page récap + ADR 0048 ([7b6158f](https://github.com/univ-lehavre/cluster/commit/7b6158fbfc35d1aa9b71e03c91b3625669d3ff4a))
* **banc:** access.sh — accès dev en une commande (URLs, secrets, .env atlas) ([4d738c3](https://github.com/univ-lehavre/cluster/commit/4d738c3356506b273f9f85258d8bfaa2e6121ca1))
* **banc:** garde-fou de fraîcheur par chemin ([#244](https://github.com/univ-lehavre/cluster/issues/244)) ([6f5bb50](https://github.com/univ-lehavre/cluster/commit/6f5bb50c9c5b37a31ab96f8512ad112d761332e3))
* **banc:** garde-fou de fraîcheur PAR CHEMIN (ADR 0045 §6) ([7723187](https://github.com/univ-lehavre/cluster/commit/77231873a14c26532c13c9790d8117298b9ea38f)), closes [#244](https://github.com/univ-lehavre/cluster/issues/244)
* **banc:** metrics-server natif ([#252](https://github.com/univ-lehavre/cluster/issues/252)) + disques bruts conditionnels Ceph ([#235](https://github.com/univ-lehavre/cluster/issues/235)) ([76ef61b](https://github.com/univ-lehavre/cluster/commit/76ef61b96b3b46502352efc9bf8ca431e1fbdcb1))
* **banc:** porter local-path en rôle Ansible (StorageClass default) ([#262](https://github.com/univ-lehavre/cluster/issues/262)) ([3d5fa83](https://github.com/univ-lehavre/cluster/commit/3d5fa837a0b6b82a0f61e1712a2fc1b620328158))
* **banc:** porter metrics-server + local-path en rôles Ansible + gate idempotence ([#262](https://github.com/univ-lehavre/cluster/issues/262)/[#265](https://github.com/univ-lehavre/cluster/issues/265)) ([6e32d13](https://github.com/univ-lehavre/cluster/commit/6e32d1368bd2a4cdc0d5b472cea7a40ee17dae6e))
* **banc:** porter metrics-server en rôle Ansible + gate idempotence ([#262](https://github.com/univ-lehavre/cluster/issues/262)/[#265](https://github.com/univ-lehavre/cluster/issues/265)) ([5a09e18](https://github.com/univ-lehavre/cluster/commit/5a09e1828078b8b4fcf5119d8fc21ebabaeede18))
* **bootstrap:** pré-vol Ceph (lvm2 + disques bruts) — drift L6 en assert clair ([b07f8ac](https://github.com/univ-lehavre/cluster/commit/b07f8ace013d70374b10ed965c58581b8a51fea0))
* **bootstrap:** pré-vol Ceph (lvm2 + disques) — drift L6 en assert clair ([15bd75d](https://github.com/univ-lehavre/cluster/commit/15bd75d89fdf1b40445f51edc93f686cb94cc472))
* **contract:** patron .env consommable par atlas (généré par access.sh) ([b8a65e5](https://github.com/univ-lehavre/cluster/commit/b8a65e567a9a2ff13bb51b062ca275fcbb3b9c1b))
* **netpol:** egress internet pour le sync d'un snapshot ouvert (dagster) ([353a0d0](https://github.com/univ-lehavre/cluster/commit/353a0d04e50c3e6b5066be964050e913b79b3901)), closes [#256](https://github.com/univ-lehavre/cluster/issues/256)
* **netpol:** egress internet pour le sync du snapshot openalex (dagster) ([f187e82](https://github.com/univ-lehavre/cluster/commit/f187e82e54166f678e8915262c28ca6d7631f3ea))
* **test:** métrologie par nœud dans runs-history ([#241](https://github.com/univ-lehavre/cluster/issues/241)) ([cd7a3e1](https://github.com/univ-lehavre/cluster/commit/cd7a3e1dabc07712f1e1117e50339947148b3cd8))
* **test:** métrologie par nœud dans runs-history ([#241](https://github.com/univ-lehavre/cluster/issues/241)) ([92484f7](https://github.com/univ-lehavre/cluster/commit/92484f7e677ad100a8fb81f974b0ea3d27e9672f))
* **test:** scénario 29 — harnais E2E paramétrable pour code-location externe ([#264](https://github.com/univ-lehavre/cluster/issues/264)) ([f894198](https://github.com/univ-lehavre/cluster/commit/f894198b55fd56222cb87df03a4a3fa9a1eb2605))


### Bug Fixes

* **banc:** limactl start --yes — pas de prompt à la création de VM ([0ac5f8a](https://github.com/univ-lehavre/cluster/commit/0ac5f8a48ccb68d1333a53a1b4486444f69c1d61))
* **banc:** newline final dans runs-history.yaml (métriques [#217](https://github.com/univ-lehavre/cluster/issues/217)) ([5a99d18](https://github.com/univ-lehavre/cluster/commit/5a99d18ca0aab365f7fa66943ab05f1467f24f5a))
* **banc:** probe egress — supprimer le double 000 (curl émet déjà 000) ([7e5b223](https://github.com/univ-lehavre/cluster/commit/7e5b2235662488accd4b02fcd5f2e3c77e16da78)), closes [#256](https://github.com/univ-lehavre/cluster/issues/256)
* **bootstrap:** apt_repository → deb822_repository (déprécié en ansible-core 2.25) ([a395fe2](https://github.com/univ-lehavre/cluster/commit/a395fe2b87ea8490eb05c6bc95c46277e321f584))
* **ci:** shellcheck disable SC1083 sur le KEEP Jinja du template etcd ([33cf7ec](https://github.com/univ-lehavre/cluster/commit/33cf7ec98a221e7ec988e71defec21c9e5fea3f1))
* **dagster:** poser allow-internet-egress depuis le rôle (sync OpenAlex) ([7ccd56d](https://github.com/univ-lehavre/cluster/commit/7ccd56d945618e7ad049e147f6e0dff3a3448d96)), closes [#256](https://github.com/univ-lehavre/cluster/issues/256)
* **dataops:** débloquer SeaweedFS (volume.max) + harnais E2E code-location externe ([#264](https://github.com/univ-lehavre/cluster/issues/264)) ([7132ded](https://github.com/univ-lehavre/cluster/commit/7132ded9b2a7a1b5d751dea93f63e82ed78f9229))
* **seaweedfs:** débloquer les écritures S3 (volume.max) + NP s3-egress dagster ([#264](https://github.com/univ-lehavre/cluster/issues/264)) ([1ee2d90](https://github.com/univ-lehavre/cluster/commit/1ee2d901027399812ba02a6605e70c3f07c1a817))


### Refactor

* **secu:** porter blur-env.pl en Python (ADR 0049, Perl en sursis) ([176759d](https://github.com/univ-lehavre/cluster/commit/176759db3b18d4091f3b96634ea47577b88bab2c)), closes [#262](https://github.com/univ-lehavre/cluster/issues/262)


### Documentation

* **adr:** acter cilium-expo + CRDs Gateway API comme exception cni.sh (0049) ([23d1b25](https://github.com/univ-lehavre/cluster/commit/23d1b25941117f202ade26420048be97e956b634)), closes [#262](https://github.com/univ-lehavre/cluster/issues/262)
* **adr:** doctrine du choix d'outil + options natives + blur_env Python (0049/0050/0051) ([c043d3b](https://github.com/univ-lehavre/cluster/commit/c043d3b80dd5139761e3e4056acf788b1c41ac8d))
* **adr:** doctrine du choix d'outil par action (0049/0050/0051) ([58d96f0](https://github.com/univ-lehavre/cluster/commit/58d96f01db3d4d5e11596a077354d90126833184))
* **adr:** seuil par chemin implémenté (0042 amendé, 0045 §6) ([f7502e0](https://github.com/univ-lehavre/cluster/commit/f7502e0491e1ebfee830a1448438377ad2d2146f)), closes [#244](https://github.com/univ-lehavre/cluster/issues/244)
* **atlas:** page récap dev-atlas + ADR 0048 + guide réécrit autour d'access.sh ([716915a](https://github.com/univ-lehavre/cluster/commit/716915a3eded78785ed41f9070e574e5af8581b3))
* **banc:** consigner le chemin atlas opérationnel (27/28 + metrics-server) ([2cd5d59](https://github.com/univ-lehavre/cluster/commit/2cd5d5917a7e98d7cd480aa9d912b46bcab425c2))
* **banc:** consigner le run preuve egress internet dagster ([#256](https://github.com/univ-lehavre/cluster/issues/256)) ([5438244](https://github.com/univ-lehavre/cluster/commit/5438244d75ff847e7ab54bdb34b700acd203a55d))
* **banc:** re-preuve from-scratch du chemin atlas (27/28, egress, [#235](https://github.com/univ-lehavre/cluster/issues/235)) ([198e915](https://github.com/univ-lehavre/cluster/commit/198e9157627e2a30fbb3439d67ca146518886877))
* **dataops:** branchement code-location dagster + note egress internet ([a778ede](https://github.com/univ-lehavre/cluster/commit/a778edef8b2a4cd25380476a5048a908c9757712)), closes [#256](https://github.com/univ-lehavre/cluster/issues/256)
* **dataops:** kubectl top opérant sur le chemin atlas ([#252](https://github.com/univ-lehavre/cluster/issues/252)) ([906f9e0](https://github.com/univ-lehavre/cluster/commit/906f9e0153a6ce7e5a413abed790d4319f2732fc))
* **secu:** re-justifier le root de Promtail ([#234](https://github.com/univ-lehavre/cluster/issues/234)) ([319d1a0](https://github.com/univ-lehavre/cluster/commit/319d1a04b51a6991a3500c0e0e54ba9657f6b611))
* **secu:** re-justifier le root de Promtail par une raison technique ([#234](https://github.com/univ-lehavre/cluster/issues/234)) ([8be3a2f](https://github.com/univ-lehavre/cluster/commit/8be3a2f40da2657842b848b57b4d5ea97fac2217))

## [2.32.0](https://github.com/univ-lehavre/cluster/compare/v2.31.0...v2.32.0) (2026-06-10)


### Features

* **argocd:** rôle Ansible platform-argocd + playbook gitops ([#230](https://github.com/univ-lehavre/cluster/issues/230)) ([b6ef6f6](https://github.com/univ-lehavre/cluster/commit/b6ef6f678da4c1c25c8c835b51bfae79f8a55f8d))
* **argocd:** sourceRepos de l'AppProject atlas surchargeable ([#230](https://github.com/univ-lehavre/cluster/issues/230)) ([c91bd7c](https://github.com/univ-lehavre/cluster/commit/c91bd7cf396f98e2a939dd54088902b51dbe21ae))
* **atlas:** portail UI (contrat) + couverture banc + preuves storage-real ([#232](https://github.com/univ-lehavre/cluster/issues/232)) ([e6c8b5b](https://github.com/univ-lehavre/cluster/commit/e6c8b5b2fcf9fd4eb1814883d568e35669115749))
* **gitea:** brique forge git intra-banc air-gapped ([#230](https://github.com/univ-lehavre/cluster/issues/230)) ([50c48a6](https://github.com/univ-lehavre/cluster/commit/50c48a692355733b46c7f5bf7ff8df87aedf6ec8))
* **gitea:** exposer l'UI via Gateway Cilium + TLS (portail atlas [#232](https://github.com/univ-lehavre/cluster/issues/232) A.2) ([079a34e](https://github.com/univ-lehavre/cluster/commit/079a34e7c23dde1c3e2043faab5dcfb0640c5cd3))
* **gitea:** socle GitOps intra-banc (Gitea + Argo CD) sans Ceph ([#230](https://github.com/univ-lehavre/cluster/issues/230)) ([2353a66](https://github.com/univ-lehavre/cluster/commit/2353a66d048523e913bf01d786721616cecd92a9))
* **test:** axe hardening + chemins storage-real/cluster-dataops (ADR 0045, [#240](https://github.com/univ-lehavre/cluster/issues/240)) ([5d1e914](https://github.com/univ-lehavre/cluster/commit/5d1e914f5ad17c276240b832ad20ff43ee8ba934))
* **test:** axe hardening + chemins storage-real/cluster-dataops (ADR 0045, [#240](https://github.com/univ-lehavre/cluster/issues/240)) ([9dd6661](https://github.com/univ-lehavre/cluster/commit/9dd6661748e1bf9e67896b3afe7b75f3dd9eaf2e))
* **test:** chaîne GitOps → workflows atlas prouvée (scénario 27, [#231](https://github.com/univ-lehavre/cluster/issues/231)) ([ad57e1b](https://github.com/univ-lehavre/cluster/commit/ad57e1b63825baf43633ef4b12d7a717dd821c05))
* **test:** chemin atlas-ceph + gitops dérive la SC de WITH_CEPH (ADR 0045/0046) ([7ae5907](https://github.com/univ-lehavre/cluster/commit/7ae5907fdda0e568746cd44ae7f73e78d52e5984))
* **test:** chemins d'installation nommés socle/atlas/cluster (ADR 0045, [#237](https://github.com/univ-lehavre/cluster/issues/237)) ([ec877db](https://github.com/univ-lehavre/cluster/commit/ec877dbc094504edefd706748bdfa777bfd765b2))
* **test:** chemins d'installation nommés socle/atlas/cluster (ADR 0045, [#237](https://github.com/univ-lehavre/cluster/issues/237)) ([ceeec24](https://github.com/univ-lehavre/cluster/commit/ceeec241c36774e4b3eb137b6e5ee52cb341a607))
* **test:** phase banc gitops (Gitea + Argo CD) sans Ceph ([#230](https://github.com/univ-lehavre/cluster/issues/230)) ([24dfc9a](https://github.com/univ-lehavre/cluster/commit/24dfc9a6391dac40d74b0830565c815191f89916))
* **test:** scénario 27 GitOps → workflows atlas + init dépôt Gitea ([#231](https://github.com/univ-lehavre/cluster/issues/231)) ([b8b12b0](https://github.com/univ-lehavre/cluster/commit/b8b12b0cfe90959c5576115fcaa57b3de3fa47d2))
* **test:** scénario 28 — atteignabilité des UI via le Gateway ([#232](https://github.com/univ-lehavre/cluster/issues/232)) ([f929ce8](https://github.com/univ-lehavre/cluster/commit/f929ce876e2065f522b9430536ead04a9e77ccee))
* **test:** smoke HTTP WordPress dans la phase wordpress (preuve appli servie) ([a4ae0ca](https://github.com/univ-lehavre/cluster/commit/a4ae0ca32c9b557a0fd00ee108e1e11c65b77ede))


### Bug Fixes

* **argocd:** drifts GitOps banc atlas L51-L54 + rollback rescue platform-argocd ([#231](https://github.com/univ-lehavre/cluster/issues/231)) ([6e52f67](https://github.com/univ-lehavre/cluster/commit/6e52f67385cb480d50fa28c357db0d3688e8f0d6))
* **argocd:** egress apiserver sans ipBlock (entité réservée Cilium) ([#230](https://github.com/univ-lehavre/cluster/issues/230)) ([a855ec8](https://github.com/univ-lehavre/cluster/commit/a855ec8c4c2be6afd125ea896739693665f0c185))
* **argocd:** egress repo-server→gitea sur port 3000 (pod), pas 80 (L53 corrigé) ([7abc83e](https://github.com/univ-lehavre/cluster/commit/7abc83e1b3578f3d05ab2913883164e6a4602259))
* **ci:** trivy allowlist workflow jouet (KSV-0014/0118) + lien README sample ([#231](https://github.com/univ-lehavre/cluster/issues/231)) ([5fbc113](https://github.com/univ-lehavre/cluster/commit/5fbc113d8f547a8a8f50a656829a0093c5f28a0b))
* **expo:** cni.sh pose les CRs cilium + crds gateway api avant cilium ([#232](https://github.com/univ-lehavre/cluster/issues/232)) ([1433e76](https://github.com/univ-lehavre/cluster/commit/1433e76f83e4df6b445434bd53a6ec82176b7be1))
* **scenarios:** caractère parasite après $ATTACKER_IP dans le scénario 22 ([809c139](https://github.com/univ-lehavre/cluster/commit/809c13991514fa1a4512e49874dd4cb1cbbb7f4d))
* **test:** 12 GiB/VM pour le banc complet en mode Ceph (vs 8) ([61b82ab](https://github.com/univ-lehavre/cluster/commit/61b82abe6ca6dd8765a739d13f333803e13c68d8))
* **test:** exporter le kubeconfig absolu pour le scénario smoke-s3 (drift L50-like) ([58b5bc1](https://github.com/univ-lehavre/cluster/commit/58b5bc148cd2bd5dc4b7ff888f0b7c02ca82f880))
* **test:** la RAM des VM dérive de WITH_CEPH (12 Ceph / 8 léger) ([ae69e2a](https://github.com/univ-lehavre/cluster/commit/ae69e2a8e30edb73f1312c1a42e98e62ce35066c))
* **test:** ne consigner que les runs from-scratch dans runs-history ([#230](https://github.com/univ-lehavre/cluster/issues/230)) ([c553eb5](https://github.com/univ-lehavre/cluster/commit/c553eb5891af873e2977c9658ad4c0d175a3c8cf))
* **test:** scénario 27 prouvé sur banc — push trigger + attente nouvelle révision ([#231](https://github.com/univ-lehavre/cluster/issues/231)) ([7fa52e6](https://github.com/univ-lehavre/cluster/commit/7fa52e6ba45ca5ed69b2a39d5ce45a885879a747))
* **wordpress:** créer base+user MySQL + secret au banc (smoke HTTP 302 prouvé) ([af25542](https://github.com/univ-lehavre/cluster/commit/af2554211b782beca2cb7c975935d6600d2a3529))


### Documentation

* **adr:** accepte l'ADR 0045 (chemins d'installation du banc) ([24cb7e5](https://github.com/univ-lehavre/cluster/commit/24cb7e51e8e4b8d3c68f06b18e37917de84758fd))
* **adr:** chemin atlas inclut dataops ; Argo CD déploie les workflows, pas l'infra (ADR 0045) ([d6b8e0b](https://github.com/univ-lehavre/cluster/commit/d6b8e0bd66e25ffeac7ba1c5d2d1b9366119a2c9))
* **adr:** chemins d'installation du banc, couches et tests associés (ADR 0045) ([ae7411d](https://github.com/univ-lehavre/cluster/commit/ae7411d6a6b16218a851b7c6bceea55c30a4641e))
* **adr:** corriger le code d'installation, pas l'état du cluster (ADR 0046) ([ed8c72b](https://github.com/univ-lehavre/cluster/commit/ed8c72b06061c1ae80003184a5e5abc63038c042))
* **adr:** ha-3cp = control plane dédié, vip kube-vip, etcd 2/3 (0047) ([c99c10a](https://github.com/univ-lehavre/cluster/commit/c99c10a629d986569006ac2f856346fe7fe92c24))
* **adr:** topologie de déploiement du banc atlas (ADR 0044) ([dc91f06](https://github.com/univ-lehavre/cluster/commit/dc91f062354a0630e86699d46d1565e53e59154f))
* **adr:** topologie de déploiement du banc atlas (ADR 0044) ([1f93bc5](https://github.com/univ-lehavre/cluster/commit/1f93bc58a960b88988f82e1f134314becfe8f279))
* **composants:** présente chaque techno de la pile (rôle, raison d'être) ([ec5c1c8](https://github.com/univ-lehavre/cluster/commit/ec5c1c8702d5b77ab3df98720ba8bdf4d8326e1e))
* **guide-data:** explique le travail en local sur multi-node-3 / atlas ([037cdf9](https://github.com/univ-lehavre/cluster/commit/037cdf97b4ec6b42a0547a040c1c37923cdec4d0))
* **guide:** section « déployer depuis atlas » (GitOps) + endpoints Gitea/Argo CD ([#232](https://github.com/univ-lehavre/cluster/issues/232) A.3) ([836e7d4](https://github.com/univ-lehavre/cluster/commit/836e7d40ecadeb3307e3e9c2059a3846b9b4d8e4))
* pile technologique (composants.md) + guide travail local atlas + run 2026-06-10 ([6b025b8](https://github.com/univ-lehavre/cluster/commit/6b025b8cc8dafb67b3ba181198f62679ce58d8ac))
* **test:** aligne bench/README sur les chemins storage-real/cluster-dataops (ADR 0045, [#237](https://github.com/univ-lehavre/cluster/issues/237)) ([0fa827c](https://github.com/univ-lehavre/cluster/commit/0fa827cbfe48df7f08aedc322279588868051571))
* **test:** consigne le run atlas du 2026-06-10 + drifts L57/L58 ([#252](https://github.com/univ-lehavre/cluster/issues/252)) ([76e193c](https://github.com/univ-lehavre/cluster/commit/76e193cd99a6da5d8c90473e8e18d124681e8c91))
* **test:** consigne le scénario 27 prouvé + drifts L51-L54 ([#231](https://github.com/univ-lehavre/cluster/issues/231)) ([94a4f9b](https://github.com/univ-lehavre/cluster/commit/94a4f9b083f4983aef094add796ac10d71bf9aa2))
* **test:** consigne run atlas-ceph + scénario 28 + drifts L55/L56 ([#232](https://github.com/univ-lehavre/cluster/issues/232)) ([66dfe11](https://github.com/univ-lehavre/cluster/commit/66dfe11647707de455602bf390fca7dc9fef2da7))
* **test:** consigne scénario 27 prouvé + drifts L51-L54 ([#231](https://github.com/univ-lehavre/cluster/issues/231)) ([554d41d](https://github.com/univ-lehavre/cluster/commit/554d41dd3f77255e459272d5ceabb4d0b825d3ff))
* **test:** lie les drifts L55/L56 à l'issue [#251](https://github.com/univ-lehavre/cluster/issues/251) (re-preuve from-scratch) ([0d479a1](https://github.com/univ-lehavre/cluster/commit/0d479a1ffb349bedfbf0ad26eb33f7f85d04a85a))
* **test:** mapping couverture par profil de banc (ce qu'atlas ne peut jouer) ([a0659b9](https://github.com/univ-lehavre/cluster/commit/a0659b99a28e5b58d94f64c2f61cbbbfdce6c316))
* **test:** plan de tests 3 niveaux + scénario 27 GitOps→DataOps (ADR 0045) ([fd07453](https://github.com/univ-lehavre/cluster/commit/fd07453d2621f6df38b39b6085af3384053650b0))
* **test:** précise la cause racine de L53 (port pod 3000 sous Cilium) ([611edb9](https://github.com/univ-lehavre/cluster/commit/611edb9edae20c4bf33a9f0d65e8a9a21c670a97))

## [2.31.0](https://github.com/univ-lehavre/cluster/compare/v2.30.0...v2.31.0) (2026-06-09)


### Features

* **dataops:** contrat d'interface cluster→atlas (ADR 0043 + artefacts) ([45ae288](https://github.com/univ-lehavre/cluster/commit/45ae2880bcee4505021d581168b275cdd466b406))
* **dataops:** contrat d'interface cluster→atlas (ADR 0043 + artefacts) ([7caddb0](https://github.com/univ-lehavre/cluster/commit/7caddb0324252f0ab9c62027f50533ae3b66bb37))
* **test:** métrologie du banc Lima — historique, métriques, cache, status ([6c0abe7](https://github.com/univ-lehavre/cluster/commit/6c0abe715f896faac85c459338f8956e54cf94a2))
* **test:** métrologie du banc Lima — historique, métriques, cache, status & garde-fou fraîcheur ([bd45f14](https://github.com/univ-lehavre/cluster/commit/bd45f147374d63082062e1d9a6062d5564e09805))


### Bug Fixes

* **adr-0023:** génériser la plage prod résiduelle 10.67.2.0/22 ([bf9181e](https://github.com/univ-lehavre/cluster/commit/bf9181e6064c96e1a94bcc3863c2dedf18fb5167))
* **banc:** charge bootstrap/ansible.cfg via ANSIBLE_CONFIG (drift L46) + registre L45/L46 ([43758d9](https://github.com/univ-lehavre/cluster/commit/43758d9468307904c1c030d019013c088fa34020))


### Refactor

* **bootstrap:** migration ansible_facts.* (échéance ansible-core 2.24) ([69ef9d0](https://github.com/univ-lehavre/cluster/commit/69ef9d02fd0799de8d9519aff8f33fe601e39ed7))
* **bootstrap:** migre les facts top-level vers ansible_facts.* (échéance core 2.24, fix L45) ([125cba2](https://github.com/univ-lehavre/cluster/commit/125cba2950e1b31788c1e69a0f409529f2b012e6))


### Documentation

* **adr:** 0041 gouvernance & complétude DataOps (cadrage infra/métier/pratique) ([017e504](https://github.com/univ-lehavre/cluster/commit/017e504b784da196ddb4125221f9ea762a522801))
* **adr:** 0041 gouvernance & complétude DataOps (cadrage) ([deae350](https://github.com/univ-lehavre/cluster/commit/deae350ebba0118961a78d915073aefc89d7e94f))
* **adr:** 0041 retire les références marché/freelance (généricité ADR 0023) ([31e0e09](https://github.com/univ-lehavre/cluster/commit/31e0e09e102f3f3f650caa7e288b992bac421007))
* **adr:** 0042 fraîcheur des preuves de banc (garde-fou CI non bloquant) ([3e29a49](https://github.com/univ-lehavre/cluster/commit/3e29a49cb4db866abe59c53747ec5e426a932d1a))
* **adr:** 0042 fraîcheur des preuves de banc (garde-fou CI) ([c049465](https://github.com/univ-lehavre/cluster/commit/c049465e78abb29057589131fe6d6c4fac025251))
* migre l'historique des drifts L1-L40 dans registre-drifts.yaml ([f323a94](https://github.com/univ-lehavre/cluster/commit/f323a94373cdb3767e9654c67e49ad46f6517833))
* **test:** consigne le run de métrologie + drift L47 (honnêteté des Runs) ([fe0bc60](https://github.com/univ-lehavre/cluster/commit/fe0bc600e01c0816662e5311cfe3929b63115507))

## [2.30.0](https://github.com/univ-lehavre/cluster/compare/v2.29.3...v2.30.0) (2026-06-08)


### Features

* **banc:** phase_dataops paramètre storageClass/backing par profil (drift L41) ([0651917](https://github.com/univ-lehavre/cluster/commit/065191742f4303ca410cefd35013948bb27b25b4))
* **platform:** DataOps sans Ceph — rôle s3-bucket + stratégie terrains×topologies ([e07dfe8](https://github.com/univ-lehavre/cluster/commit/e07dfe8298f68a05d552c88490e9eae7db89fb90))
* **platform:** rôle s3-bucket factorisé, CNPG/Loki backing rgw|seaweedfs ([#186](https://github.com/univ-lehavre/cluster/issues/186)) ([b85f7ac](https://github.com/univ-lehavre/cluster/commit/b85f7ac7eec2277e263cb287a1c7a2c33b1fb9b7))


### Documentation

* **adr:** 0040 terrains×topologies (single-node/TOPO abandonnés, cloud arm64, paliers HA) ([c09f811](https://github.com/univ-lehavre/cluster/commit/c09f811796085f30da568f73b568fd2ab026015b))
* **drifts:** registre indexé des drifts (L41-L44) + lien synthèse ([39fe904](https://github.com/univ-lehavre/cluster/commit/39fe904ed38083f36b2f761e91a5ef64e05a05e7))

## [2.29.3](https://github.com/univ-lehavre/cluster/compare/v2.29.2...v2.29.3) (2026-06-08)


### Documentation

* **matrice:** retire la couverture Vagrant (déprécié, ADR 0038) ([2c32262](https://github.com/univ-lehavre/cluster/commit/2c322625f95a63b54a58d10de856a2223d5e762f))
* **matrice:** retire la couverture Vagrant (déprécié, ADR 0038) ([7e94879](https://github.com/univ-lehavre/cluster/commit/7e94879025434e85eeae24a8c727090acf800523))

## [2.29.2](https://github.com/univ-lehavre/cluster/compare/v2.29.1...v2.29.2) (2026-06-08)


### Bug Fixes

* **release:** auto-merge des releases en merge commit (ADR 0037) ([f8eb93d](https://github.com/univ-lehavre/cluster/commit/f8eb93d024b8121f19ca4002d695fa897dbeed0c))
* **release:** auto-merge en merge commit (squash désactivé, ADR 0037) ([e43b343](https://github.com/univ-lehavre/cluster/commit/e43b343766cdaa5da283783246c548c7fc0559e4))


### Documentation

* **matrice:** colonne type (unit/intég/chaos) + synthèse par chaîne fonctionnelle ([f1d6218](https://github.com/univ-lehavre/cluster/commit/f1d621890cc0cf2b342c50db3e4e403879452430))
* **matrice:** distinguer tests unitaires vs intégration de chaîne ([f8d8396](https://github.com/univ-lehavre/cluster/commit/f8d839627f51f792ba3333f8fb8682328529917f))

## [2.29.1](https://github.com/univ-lehavre/cluster/compare/v2.29.0...v2.29.1) (2026-06-08)


### Documentation

* **adr:** 0037 stratégie de merge — merge commit (préserver les références) ([48fc8a9](https://github.com/univ-lehavre/cluster/commit/48fc8a9fe61bb2a29aa59c3712281588457d5423))
* **adr:** 0038 lima seul banc local + catalogue 4 axes (mat/topo HA/terrain/briques) ([07ded66](https://github.com/univ-lehavre/cluster/commit/07ded6697ad905360f43307cc027e3ab1d7cbc56))
* **adr:** 0039 nomenclature des axes (codes arch/terrain/profil + tuple) ([c0c4838](https://github.com/univ-lehavre/cluster/commit/c0c4838f32a2acaae0dcecf1f58113efe3308d4e))
* **catalogue:** matrice 4 axes nommés, stratégie merge-commit, scénarios obs ([#171](https://github.com/univ-lehavre/cluster/issues/171)) ([4b8efcf](https://github.com/univ-lehavre/cluster/commit/4b8efcf5f9687e681387d72098942f3b081cd404))
* **matrice:** bloc 'scénarios exécutés' — statut réel par combinaison (tuple) ([bb0a065](https://github.com/univ-lehavre/cluster/commit/bb0a0651d715741208ffc3d7aa2114418daf7ce7))
* **matrice:** cohérence + briques S3/Loki + scénarios obs 24-26 (à écrire) ([62d07b7](https://github.com/univ-lehavre/cluster/commit/62d07b74a108068563b1daeecf4904ed6c76005a))
* **matrice:** dimensions fines paramétrables (storageClass, backing S3) + couverture [#158](https://github.com/univ-lehavre/cluster/issues/158)/[#186](https://github.com/univ-lehavre/cluster/issues/186) ([2b3ff70](https://github.com/univ-lehavre/cluster/commit/2b3ff70e45c123811ce959b79aba713524ebc7f6))

## [2.29.0](https://github.com/univ-lehavre/cluster/compare/v2.28.1...v2.29.0) (2026-06-07)


### Features

* **platform:** rôles ansible monitoring + loki + seaweedfs paramétrables ([#158](https://github.com/univ-lehavre/cluster/issues/158), [#186](https://github.com/univ-lehavre/cluster/issues/186)) ([#197](https://github.com/univ-lehavre/cluster/issues/197)) ([3526189](https://github.com/univ-lehavre/cluster/commit/3526189eceecaaf0c395f28a37e1a5ac46bba536))

## [2.28.1](https://github.com/univ-lehavre/cluster/compare/v2.28.0...v2.28.1) (2026-06-07)


### Documentation

* suites de la validation [#173](https://github.com/univ-lehavre/cluster/issues/173) — mise en valeur du processus + stratégie de bancs ([14cebf7](https://github.com/univ-lehavre/cluster/commit/14cebf71d7b3157dab71dac0563367832ed98724))
* suites validation [#173](https://github.com/univ-lehavre/cluster/issues/173) — processus mis en valeur + stratégie de bancs (ADR 0034/0035) ([#195](https://github.com/univ-lehavre/cluster/issues/195)) ([14cebf7](https://github.com/univ-lehavre/cluster/commit/14cebf71d7b3157dab71dac0563367832ed98724))

## [2.28.0](https://github.com/univ-lehavre/cluster/compare/v2.27.0...v2.28.0) (2026-06-07)


### Features

* **platform:** porte Dagster + Marquez en rôles Ansible — clôt le portage DataOps ([#173](https://github.com/univ-lehavre/cluster/issues/173)) ([#191](https://github.com/univ-lehavre/cluster/issues/191)) ([e82215e](https://github.com/univ-lehavre/cluster/commit/e82215e89cdda00b7d4f51b687f4e1ef7579179e))

## [2.27.0](https://github.com/univ-lehavre/cluster/compare/v2.26.0...v2.27.0) (2026-06-07)


### Features

* **platform:** porte le build des images DataOps en rôle Ansible ([#173](https://github.com/univ-lehavre/cluster/issues/173)) ([#189](https://github.com/univ-lehavre/cluster/issues/189)) ([7e6314a](https://github.com/univ-lehavre/cluster/commit/7e6314adc17fe3b8783d534189834ae52feb1403))

## [2.26.0](https://github.com/univ-lehavre/cluster/compare/v2.25.0...v2.26.0) (2026-06-07)


### Features

* **platform:** porte CloudNativePG + cert-manager en rôles Ansible ([#173](https://github.com/univ-lehavre/cluster/issues/173)) ([#187](https://github.com/univ-lehavre/cluster/issues/187)) ([ca042f7](https://github.com/univ-lehavre/cluster/commit/ca042f70096a51fd48a7aa1d444289642e21d007))

## [2.25.0](https://github.com/univ-lehavre/cluster/compare/v2.24.5...v2.25.0) (2026-06-07)


### Features

* **platform:** porte le registry interne DataOps en rôle Ansible (ADR 0033) ([#184](https://github.com/univ-lehavre/cluster/issues/184)) ([17c918b](https://github.com/univ-lehavre/cluster/commit/17c918b6fdba4787919310b8620c2687fd30747b)), closes [#173](https://github.com/univ-lehavre/cluster/issues/173)

## [2.24.5](https://github.com/univ-lehavre/cluster/compare/v2.24.4...v2.24.5) (2026-06-07)


### Documentation

* **decisions:** cadre le terrain cloud ARM + OpenTofu (ADR 0031, 0032) ([#182](https://github.com/univ-lehavre/cluster/issues/182)) ([48d057b](https://github.com/univ-lehavre/cluster/commit/48d057b0f6aa9d47533f2772b763b07a5494a965))

## [2.24.4](https://github.com/univ-lehavre/cluster/compare/v2.24.3...v2.24.4) (2026-06-07)


### Documentation

* **decisions:** nomenclature des bancs et topologies (ADR 0030) ([#180](https://github.com/univ-lehavre/cluster/issues/180)) ([647411b](https://github.com/univ-lehavre/cluster/commit/647411b0afa94add43ee9c0971196b766d34ba72)), closes [#133](https://github.com/univ-lehavre/cluster/issues/133)

## [2.24.3](https://github.com/univ-lehavre/cluster/compare/v2.24.2...v2.24.3) (2026-06-07)


### Documentation

* **decisions:** markdown atteignable depuis la doc + garde-fou testé (ADR 0029) ([#178](https://github.com/univ-lehavre/cluster/issues/178)) ([bef349f](https://github.com/univ-lehavre/cluster/commit/bef349f8f7b3486d4ec47a8747e8ebc303c89a89))
* **decisions:** rend tout markdown atteignable depuis la doc (ADR 0029) ([bef349f](https://github.com/univ-lehavre/cluster/commit/bef349f8f7b3486d4ec47a8747e8ebc303c89a89)), closes [#171](https://github.com/univ-lehavre/cluster/issues/171)

## [2.24.2](https://github.com/univ-lehavre/cluster/compare/v2.24.1...v2.24.2) (2026-06-07)


### Documentation

* **architecture:** cartographie la matrice du catalogue (axes, scénarios, builds) ([#175](https://github.com/univ-lehavre/cluster/issues/175)) ([cdfdfb0](https://github.com/univ-lehavre/cluster/commit/cdfdfb0f54088579b8f1a35027ad09c4e2ff5d92)), closes [#171](https://github.com/univ-lehavre/cluster/issues/171)

## [2.24.1](https://github.com/univ-lehavre/cluster/compare/v2.24.0...v2.24.1) (2026-06-07)


### Bug Fixes

* **platform:** valide e2e la chaîne DataOps et corrige 3 bugs (preuve [#148](https://github.com/univ-lehavre/cluster/issues/148)) ([#172](https://github.com/univ-lehavre/cluster/issues/172)) ([d1c317a](https://github.com/univ-lehavre/cluster/commit/d1c317af17ad4ddfe3f9ff091277c4027fb2adf8))

## [2.24.0](https://github.com/univ-lehavre/cluster/compare/v2.23.1...v2.24.0) (2026-06-05)


### Features

* **marquez:** étape 1.8 — store de lineage OpenLineage + harnais E2E DataOps ([#165](https://github.com/univ-lehavre/cluster/issues/165)) ([befe86f](https://github.com/univ-lehavre/cluster/commit/befe86f35fab1d57569bbee2e917023d5885ecfe))

## [2.23.1](https://github.com/univ-lehavre/cluster/compare/v2.23.0...v2.23.1) (2026-06-04)


### Bug Fixes

* **images:** ré-épingle les digests single-arch sur leur index multi-arch ([#140](https://github.com/univ-lehavre/cluster/issues/140)) ([#155](https://github.com/univ-lehavre/cluster/issues/155)) ([e4cabc7](https://github.com/univ-lehavre/cluster/commit/e4cabc7af85b41a05c831b58e5eee40e7927b0de))

## [2.23.0](https://github.com/univ-lehavre/cluster/compare/v2.22.0...v2.23.0) (2026-06-04)


### Features

* **test:** banc lima — stockage modulaire (local-path rapide, ceph optionnel) ([#151](https://github.com/univ-lehavre/cluster/issues/151)) ([24c4cad](https://github.com/univ-lehavre/cluster/commit/24c4cad215748f372ce790aed9331776cfca8fa8))
* **test:** banc Lima — stockage modulaire (local-path rapide, Ceph optionnel) ([#151](https://github.com/univ-lehavre/cluster/issues/151)) ([#153](https://github.com/univ-lehavre/cluster/issues/153)) ([24c4cad](https://github.com/univ-lehavre/cluster/commit/24c4cad215748f372ce790aed9331776cfca8fa8))

## [2.22.0](https://github.com/univ-lehavre/cluster/compare/v2.21.0...v2.22.0) (2026-06-04)


### Features

* **platform:** orchestrateur Dagster (1.7) + traçabilité plans/audits ([#145](https://github.com/univ-lehavre/cluster/issues/145)) ([a0e49d6](https://github.com/univ-lehavre/cluster/commit/a0e49d64c82e8e2f8ac50aeb615af1c2dbb2dae3))

## [2.21.0](https://github.com/univ-lehavre/cluster/compare/v2.20.0...v2.21.0) (2026-06-04)


### Features

* **test:** banc léger Lima multi-VM + Rook/Ceph ([#127](https://github.com/univ-lehavre/cluster/issues/127)) ([#143](https://github.com/univ-lehavre/cluster/issues/143)) ([91a6834](https://github.com/univ-lehavre/cluster/commit/91a68348bb0a0a9e6460a480cd707f2af7be123f))

## [2.20.0](https://github.com/univ-lehavre/cluster/compare/v2.19.0...v2.20.0) (2026-06-04)


### Features

* **security:** relais smtp du hardening hôte vers un smarthost (mailpit/vendeur-neutre) ([3b37d51](https://github.com/univ-lehavre/cluster/commit/3b37d5187fc6414cafa7905293f66454830c645a))
* **security:** relais SMTP du hardening hôte vers un smarthost (Mailpit/vendeur-neutre) ([#141](https://github.com/univ-lehavre/cluster/issues/141)) ([3b37d51](https://github.com/univ-lehavre/cluster/commit/3b37d5187fc6414cafa7905293f66454830c645a))
* **test:** sécurité active — chaos + attaques contrôlées + adr 0025 ([e4bbc74](https://github.com/univ-lehavre/cluster/commit/e4bbc741121dbd53283a51cb942ba336406c6d74))
* **test:** sécurité active — chaos + attaques contrôlées + ADR 0025 ([#137](https://github.com/univ-lehavre/cluster/issues/137)) ([e4bbc74](https://github.com/univ-lehavre/cluster/commit/e4bbc741121dbd53283a51cb942ba336406c6d74))

## [2.19.0](https://github.com/univ-lehavre/cluster/compare/v2.18.0...v2.19.0) (2026-06-03)


### Features

* **platform:** cloudnative-pg (postgresql managé + pgvector + sauvegardes s3) ([#125](https://github.com/univ-lehavre/cluster/issues/125)) ([3314de3](https://github.com/univ-lehavre/cluster/commit/3314de37b8697ed1d6f59904e711fe5f97ba291f))

## [2.18.0](https://github.com/univ-lehavre/cluster/compare/v2.17.6...v2.18.0) (2026-06-03)


### Features

* **platform:** kube-prometheus-stack + loki + monitoring ceph (palier 2) ([#123](https://github.com/univ-lehavre/cluster/issues/123)) ([0d04fdd](https://github.com/univ-lehavre/cluster/commit/0d04fdd53d0644c4394a315215739c2e2cee4663))

## [2.17.6](https://github.com/univ-lehavre/cluster/compare/v2.17.5...v2.17.6) (2026-06-03)


### Documentation

* génériser identités dans les fichiers restants (ADR 0023, PR 4/4) ([#118](https://github.com/univ-lehavre/cluster/issues/118)) ([5ff998b](https://github.com/univ-lehavre/cluster/commit/5ff998bf66d3d115e404dbf28c0140bebaf40e95))

## [2.17.5](https://github.com/univ-lehavre/cluster/compare/v2.17.4...v2.17.5) (2026-06-03)


### Documentation

* **adr:** génériser IP/hostnames et sources métier dans les décisions (ADR 0023) ([#116](https://github.com/univ-lehavre/cluster/issues/116)) ([9eca68a](https://github.com/univ-lehavre/cluster/commit/9eca68a4481812c6b5832e1dda8d3b7044efe9c9))

## [2.17.4](https://github.com/univ-lehavre/cluster/compare/v2.17.3...v2.17.4) (2026-06-03)


### Documentation

* génériser IP et hostnames dans la prose infra (ADR 0023) ([#115](https://github.com/univ-lehavre/cluster/issues/115)) ([2dd8744](https://github.com/univ-lehavre/cluster/commit/2dd8744cbe8164408941c4d2617f68cb2425d641))

## [2.17.3](https://github.com/univ-lehavre/cluster/compare/v2.17.2...v2.17.3) (2026-06-03)


### Refactor

* **bootstrap:** défauts génériques pour hostnames et CIDR (ADR 0023) ([#114](https://github.com/univ-lehavre/cluster/issues/114)) ([824d5c9](https://github.com/univ-lehavre/cluster/commit/824d5c99e7bdc23a87577048bf354b0288024875))

## [2.17.2](https://github.com/univ-lehavre/cluster/compare/v2.17.1...v2.17.2) (2026-06-03)


### Documentation

* **architecture:** vues thématiques au-dessus des ADR (5 domaines) ([#111](https://github.com/univ-lehavre/cluster/issues/111)) ([36561b3](https://github.com/univ-lehavre/cluster/commit/36561b3ea4b949c8e6847095da1050fe99269d24))

## [2.17.1](https://github.com/univ-lehavre/cluster/compare/v2.17.0...v2.17.1) (2026-06-03)


### Documentation

* **adr:** distinguer brique d'infra (à garder) vs identité (à génériser) ([#110](https://github.com/univ-lehavre/cluster/issues/110)) ([c06bcea](https://github.com/univ-lehavre/cluster/commit/c06bcea8dea3fa4f707f87a86369e99097c1f49e))

## [2.17.0](https://github.com/univ-lehavre/cluster/compare/v2.16.2...v2.17.0) (2026-06-03)


### Features

* **docs:** acter la règle dépôt multi-topologies (ADR 0023) ([#107](https://github.com/univ-lehavre/cluster/issues/107)) ([91d9024](https://github.com/univ-lehavre/cluster/commit/91d902437d0ee08fcf14754771f4fcdd294737cd))

## [2.16.2](https://github.com/univ-lehavre/cluster/compare/v2.16.1...v2.16.2) (2026-06-03)


### Documentation

* **test:** exposition Argo CD via Gateway sur banc (Run [#13](https://github.com/univ-lehavre/cluster/issues/13)) + finding gRPC ([#106](https://github.com/univ-lehavre/cluster/issues/106)) ([94d659b](https://github.com/univ-lehavre/cluster/commit/94d659b4637cf3e0bc5ce766502d45b14d679b79))

## [2.16.1](https://github.com/univ-lehavre/cluster/compare/v2.16.0...v2.16.1) (2026-06-03)


### Documentation

* glossaire exposition + pages architecture (chaîne réseau, validation banc) ([#103](https://github.com/univ-lehavre/cluster/issues/103)) ([94c4621](https://github.com/univ-lehavre/cluster/commit/94c4621bf3d2ce5107529da02ca4a80f2ad4be66))
* **test:** valider cert-manager + CA interne sur banc (Run [#12](https://github.com/univ-lehavre/cluster/issues/12), ADR 0021) ([#104](https://github.com/univ-lehavre/cluster/issues/104)) ([cfe0125](https://github.com/univ-lehavre/cluster/commit/cfe012504a3f1957a12243a7b9336d8525b1a980))

## [2.16.0](https://github.com/univ-lehavre/cluster/compare/v2.15.2...v2.16.0) (2026-06-03)


### Features

* **platform:** argo cd gitops applicatif (ADR 0022), validé banc ([#101](https://github.com/univ-lehavre/cluster/issues/101)) ([dc704c4](https://github.com/univ-lehavre/cluster/commit/dc704c44b8becb8fc3b24aad0a83885a505236d8))

## [2.15.2](https://github.com/univ-lehavre/cluster/compare/v2.15.1...v2.15.2) (2026-06-02)


### Bug Fixes

* **cni:** attendre la convergence de KubeProxyReplacement avant de retirer kube-proxy ([45cc9f2](https://github.com/univ-lehavre/cluster/commit/45cc9f2bc336ba2acb8da1f9cf08a23a05abfd95))
* **cni:** convergence KubeProxyReplacement avant retrait kube-proxy (validé banc) ([#99](https://github.com/univ-lehavre/cluster/issues/99)) ([45cc9f2](https://github.com/univ-lehavre/cluster/commit/45cc9f2bc336ba2acb8da1f9cf08a23a05abfd95))

## [2.15.1](https://github.com/univ-lehavre/cluster/compare/v2.15.0...v2.15.1) (2026-06-02)


### Documentation

* **audit:** note de réflexion admission/runtime (Kyverno/Falco/Tetragon) ([#97](https://github.com/univ-lehavre/cluster/issues/97)) ([3c26a24](https://github.com/univ-lehavre/cluster/commit/3c26a24f06cf09c29989daffefb11b7eaf2ecd20))

## [2.15.0](https://github.com/univ-lehavre/cluster/compare/v2.14.0...v2.15.0) (2026-06-02)


### Features

* **platform:** cert-manager + CA interne (TLS de bordure Gateway) ([#95](https://github.com/univ-lehavre/cluster/issues/95)) ([cbac5c9](https://github.com/univ-lehavre/cluster/commit/cbac5c9fa964a84507715a232f7ba14294b69cc6))

## [2.14.0](https://github.com/univ-lehavre/cluster/compare/v2.13.1...v2.14.0) (2026-06-02)


### Features

* **platform:** exposition tout-Cilium (LB-IPAM + L2 + Gateway API) ([#93](https://github.com/univ-lehavre/cluster/issues/93)) ([2b29034](https://github.com/univ-lehavre/cluster/commit/2b290343b02c1dad00e105e26fbfcfd72b0126da))

## [2.13.1](https://github.com/univ-lehavre/cluster/compare/v2.13.0...v2.13.1) (2026-06-02)


### Documentation

* **securite:** clôt la dette chiffrement des snapshots etcd (assumée) ([#89](https://github.com/univ-lehavre/cluster/issues/89)) ([9544159](https://github.com/univ-lehavre/cluster/commit/95441591fca65d3f061224925ff90e0d4b28a79a))

## [2.13.0](https://github.com/univ-lehavre/cluster/compare/v2.12.3...v2.13.0) (2026-06-02)


### Features

* **securite:** chiffrement at-rest etcd + audit-policy via kubeadm --config ([#87](https://github.com/univ-lehavre/cluster/issues/87)) ([6acc49f](https://github.com/univ-lehavre/cluster/commit/6acc49f640cb17f2399eba8dc7668a6c411301ff))

## [2.12.3](https://github.com/univ-lehavre/cluster/compare/v2.12.2...v2.12.3) (2026-06-02)


### Documentation

* **status:** réaligne STATUS.md sur v2.12.2 (durcissement + run banc) ([#85](https://github.com/univ-lehavre/cluster/issues/85)) ([21f65c6](https://github.com/univ-lehavre/cluster/commit/21f65c698004f10218a19d9f12afc3c5a0bd6178))

## [2.12.2](https://github.com/univ-lehavre/cluster/compare/v2.12.1...v2.12.2) (2026-06-02)


### Documentation

* **ceph:** ordre de suppression d'un CephObjectStore (audit banc [#19](https://github.com/univ-lehavre/cluster/issues/19)) ([#83](https://github.com/univ-lehavre/cluster/issues/83)) ([626c734](https://github.com/univ-lehavre/cluster/commit/626c734a6cc7bfb03f6a4cbecad9c84cbea6d51a))

## [2.12.1](https://github.com/univ-lehavre/cluster/compare/v2.12.0...v2.12.1) (2026-06-02)


### Refactor

* **securite:** first-access.sh seule source du durcissement sshd ([#80](https://github.com/univ-lehavre/cluster/issues/80)) ([50c3b47](https://github.com/univ-lehavre/cluster/commit/50c3b47e99597e1e839150bb1ae93210f897bd15))

## [2.12.0](https://github.com/univ-lehavre/cluster/compare/v2.11.5...v2.12.0) (2026-06-01)


### Features

* **securite:** durcissement réseau Cilium (WireGuard + Hubble) ([#78](https://github.com/univ-lehavre/cluster/issues/78)) ([93dfe21](https://github.com/univ-lehavre/cluster/commit/93dfe2171d749ad28591835c17a75a9c6158a547))

## [2.11.5](https://github.com/univ-lehavre/cluster/compare/v2.11.4...v2.11.5) (2026-06-01)


### Bug Fixes

* **smartmon:** service smartmontools (vs smartd) + tolère l'absence de SMART (test banc) ([425f7c3](https://github.com/univ-lehavre/cluster/commit/425f7c38a7300e80722bf51b2186d1922c3696e7))
* **smartmon:** service smartmontools + tolère l'absence de SMART (révélé par test banc) ([#74](https://github.com/univ-lehavre/cluster/issues/74)) ([425f7c3](https://github.com/univ-lehavre/cluster/commit/425f7c38a7300e80722bf51b2186d1922c3696e7))

## [2.11.4](https://github.com/univ-lehavre/cluster/compare/v2.11.3...v2.11.4) (2026-06-01)


### Documentation

* 13 checks requis en branch protection ([#71](https://github.com/univ-lehavre/cluster/issues/71)) ([161e735](https://github.com/univ-lehavre/cluster/commit/161e7353865bb1a5ecac5379661677451ead52d7))
* 13 checks requis en branch protection (ajout markdownlint/lychee/ansible-syntax/scripts-extra) ([161e735](https://github.com/univ-lehavre/cluster/commit/161e7353865bb1a5ecac5379661677451ead52d7))

## [2.11.3](https://github.com/univ-lehavre/cluster/compare/v2.11.2...v2.11.3) (2026-06-01)


### Documentation

* **status:** passe de mise à jour du tableau de bord ([c6bfbf6](https://github.com/univ-lehavre/cluster/commit/c6bfbf69ced430801f732f67f46cc5e1c2e2fbf4))
* **status:** passe de mise à jour du tableau de bord (v2.11.1) ([#66](https://github.com/univ-lehavre/cluster/issues/66)) ([c6bfbf6](https://github.com/univ-lehavre/cluster/commit/c6bfbf69ced430801f732f67f46cc5e1c2e2fbf4))

## [2.11.2](https://github.com/univ-lehavre/cluster/compare/v2.11.1...v2.11.2) (2026-06-01)


### Documentation

* **safeguards:** trivy/bats/jscpd ajoutés aux checks requis (anti-régression main) ([48ce530](https://github.com/univ-lehavre/cluster/commit/48ce5306d7fb868b98a8feb1a7cc74c79bdbe0c2))
* **safeguards:** trivy/bats/jscpd requis en branch protection ([#64](https://github.com/univ-lehavre/cluster/issues/64)) ([48ce530](https://github.com/univ-lehavre/cluster/commit/48ce5306d7fb868b98a8feb1a7cc74c79bdbe0c2))

## [2.11.1](https://github.com/univ-lehavre/cluster/compare/v2.11.0...v2.11.1) (2026-06-01)


### Bug Fixes

* **securite:** securityContext pod metrics-server (corrige trivy sur main) ([#62](https://github.com/univ-lehavre/cluster/issues/62)) ([064a057](https://github.com/univ-lehavre/cluster/commit/064a05715f59c88eebdc29f6bfc7b76a072ade30))
* **securite:** securityContext pod sur metrics-server (corrige trivy KSV-0118 sur main) ([064a057](https://github.com/univ-lehavre/cluster/commit/064a05715f59c88eebdc29f6bfc7b76a072ade30))

## [2.11.0](https://github.com/univ-lehavre/cluster/compare/v2.10.0...v2.11.0) (2026-06-01)


### Features

* **ops:** copie hors-nœud des snapshots etcd + RPO (audit P1 [#3](https://github.com/univ-lehavre/cluster/issues/3)) ([#59](https://github.com/univ-lehavre/cluster/issues/59)) ([9b1823e](https://github.com/univ-lehavre/cluster/commit/9b1823e9d0ab4a5484fa3c45c247186c4eb15efe))
* **ops:** copie hors-nœud des snapshots etcd via fetch + RPO documenté (audit P1 [#3](https://github.com/univ-lehavre/cluster/issues/3)) ([9b1823e](https://github.com/univ-lehavre/cluster/commit/9b1823e9d0ab4a5484fa3c45c247186c4eb15efe))
* **ops:** metrics-server + ADR observabilité par paliers (audit P5 [#17](https://github.com/univ-lehavre/cluster/issues/17)) ([7376b8c](https://github.com/univ-lehavre/cluster/commit/7376b8c7cf4d003fb99e7cd969c6ef4dfb2ed9c2))
* **ops:** observabilité — metrics-server + ADR par paliers (audit P5 [#17](https://github.com/univ-lehavre/cluster/issues/17)) ([#60](https://github.com/univ-lehavre/cluster/issues/60)) ([7376b8c](https://github.com/univ-lehavre/cluster/commit/7376b8c7cf4d003fb99e7cd969c6ef4dfb2ed9c2))

## [2.10.0](https://github.com/univ-lehavre/cluster/compare/v2.9.0...v2.10.0) (2026-06-01)


### Features

* **ops:** surveillance SMART des disques (smartd + state.sh) (audit P5 [#19](https://github.com/univ-lehavre/cluster/issues/19)) ([#57](https://github.com/univ-lehavre/cluster/issues/57)) ([fae5c26](https://github.com/univ-lehavre/cluster/commit/fae5c264f2fd39484b90efd7c1ff8d238316928b))
* **ops:** surveillance SMART des disques via smartd + couche state.sh (audit P5 [#19](https://github.com/univ-lehavre/cluster/issues/19)) ([fae5c26](https://github.com/univ-lehavre/cluster/commit/fae5c264f2fd39484b90efd7c1ff8d238316928b))

## [2.9.0](https://github.com/univ-lehavre/cluster/compare/v2.8.0...v2.9.0) (2026-06-01)


### Features

* **ops:** upgrade K8s in-place + renomme upgrade.yaml → os-upgrade.yaml (audit P5 [#18](https://github.com/univ-lehavre/cluster/issues/18)) ([#55](https://github.com/univ-lehavre/cluster/issues/55)) ([f24e356](https://github.com/univ-lehavre/cluster/commit/f24e356ac0127e21bfa734a953a8406ae66882d9))
* **ops:** upgrade K8s in-place séquencé + renomme upgrade.yaml en os-upgrade.yaml (audit P5 [#18](https://github.com/univ-lehavre/cluster/issues/18)) ([f24e356](https://github.com/univ-lehavre/cluster/commit/f24e356ac0127e21bfa734a953a8406ae66882d9))

## [2.8.0](https://github.com/univ-lehavre/cluster/compare/v2.7.0...v2.8.0) (2026-06-01)


### Features

* **securite:** épingle par digest les images critiques (audit P11 [#11](https://github.com/univ-lehavre/cluster/issues/11)) ([#53](https://github.com/univ-lehavre/cluster/issues/53)) ([0715112](https://github.com/univ-lehavre/cluster/commit/0715112fe17ca687b0ba65b9f90c580f3d44d9aa))
* **securite:** épingle par digest les images critiques rook/ceph/registry (audit P11 [#11](https://github.com/univ-lehavre/cluster/issues/11)) ([0715112](https://github.com/univ-lehavre/cluster/commit/0715112fe17ca687b0ba65b9f90c580f3d44d9aa))

## [2.7.0](https://github.com/univ-lehavre/cluster/compare/v2.6.2...v2.7.0) (2026-06-01)


### Features

* **dx:** ajoute un Justfile racine + section README « Par où commencer » (audit P10 [#16](https://github.com/univ-lehavre/cluster/issues/16)) ([f5864aa](https://github.com/univ-lehavre/cluster/commit/f5864aaa22587261ede2ca53a562e1b1eb2af445))
* **dx:** Justfile racine + « Par où commencer » dans le README (audit P10 [#16](https://github.com/univ-lehavre/cluster/issues/16)) ([#51](https://github.com/univ-lehavre/cluster/issues/51)) ([f5864aa](https://github.com/univ-lehavre/cluster/commit/f5864aaa22587261ede2ca53a562e1b1eb2af445))


### Bug Fixes

* **tests:** scénarios 03/04/05 échouent à l'expiration + parsing ceph en JSON (audit P4 [#13](https://github.com/univ-lehavre/cluster/issues/13)/[#14](https://github.com/univ-lehavre/cluster/issues/14)) ([0af1f25](https://github.com/univ-lehavre/cluster/commit/0af1f2549eeb982d188c551ea43561529afbd698))
* **tests:** scénarios 03/04/05 fiabilisés (audit P4 [#13](https://github.com/univ-lehavre/cluster/issues/13)/[#14](https://github.com/univ-lehavre/cluster/issues/14)) ([#50](https://github.com/univ-lehavre/cluster/issues/50)) ([0af1f25](https://github.com/univ-lehavre/cluster/commit/0af1f2549eeb982d188c551ea43561529afbd698))

## [2.6.2](https://github.com/univ-lehavre/cluster/compare/v2.6.1...v2.6.2) (2026-06-01)


### Documentation

* gouvernance projet — Priorité 7 complète (audit P7 [#26](https://github.com/univ-lehavre/cluster/issues/26)-[#31](https://github.com/univ-lehavre/cluster/issues/31)) ([#47](https://github.com/univ-lehavre/cluster/issues/47)) ([1a2c5ee](https://github.com/univ-lehavre/cluster/commit/1a2c5ee1a8d4e45f7da7c13fa0ec9ef0919262ac))

## [2.6.1](https://github.com/univ-lehavre/cluster/compare/v2.6.0...v2.6.1) (2026-06-01)


### Documentation

* ajoute STATUS.md (avancement audit + écarts plan/audits détaillés) ([89aa6c5](https://github.com/univ-lehavre/cluster/commit/89aa6c56fee2a92578ac5f4dde4c29049e13d48a))
* ajoute STATUS.md (avancement audit + écarts plan/audits) ([#45](https://github.com/univ-lehavre/cluster/issues/45)) ([89aa6c5](https://github.com/univ-lehavre/cluster/commit/89aa6c56fee2a92578ac5f4dde4c29049e13d48a))

## [2.6.0](https://github.com/univ-lehavre/cluster/compare/v2.5.0...v2.6.0) (2026-06-01)


### Features

* **securite:** ClusterIP + ADR durcissement kubeadm/PodSecurity (audit P6 [#21](https://github.com/univ-lehavre/cluster/issues/21) & [#25](https://github.com/univ-lehavre/cluster/issues/25)) ([#43](https://github.com/univ-lehavre/cluster/issues/43)) ([4f10596](https://github.com/univ-lehavre/cluster/commit/4f105965b46c955005808ea249eedae778633c5d))

## [2.5.0](https://github.com/univ-lehavre/cluster/compare/v2.4.0...v2.5.0) (2026-06-01)


### Features

* **securite:** jeu de règles UFW K8s/Cilium/Ceph + SSH restreint (audit P6 [#24](https://github.com/univ-lehavre/cluster/issues/24)) ([#41](https://github.com/univ-lehavre/cluster/issues/41)) ([c3e9e88](https://github.com/univ-lehavre/cluster/commit/c3e9e88bbf224c2baa44024122ba05f8c5e3ea7c))
* **securite:** jeu de règles UFW K8s/Cilium/Ceph + SSH restreint + drift state.sh (audit P6 [#24](https://github.com/univ-lehavre/cluster/issues/24)) ([c3e9e88](https://github.com/univ-lehavre/cluster/commit/c3e9e88bbf224c2baa44024122ba05f8c5e3ea7c))

## [2.4.0](https://github.com/univ-lehavre/cluster/compare/v2.3.0...v2.4.0) (2026-06-01)


### Features

* **securite:** ajoute des NetworkPolicies default-deny par namespace (audit P6 [#22](https://github.com/univ-lehavre/cluster/issues/22)) ([e8c0836](https://github.com/univ-lehavre/cluster/commit/e8c08361ceea854d1c15986238c57b49a56653dd))
* **securite:** NetworkPolicies default-deny par namespace (audit P6 [#22](https://github.com/univ-lehavre/cluster/issues/22)) ([#39](https://github.com/univ-lehavre/cluster/issues/39)) ([e8c0836](https://github.com/univ-lehavre/cluster/commit/e8c08361ceea854d1c15986238c57b49a56653dd))

## [2.3.0](https://github.com/univ-lehavre/cluster/compare/v2.2.0...v2.3.0) (2026-06-01)


### Features

* **securite:** durcit les workloads + allowlist trivy ciblée (audit P6) ([#37](https://github.com/univ-lehavre/cluster/issues/37)) ([dc19fa4](https://github.com/univ-lehavre/cluster/commit/dc19fa430fa57a5a4e78eeb0ed2f15dcb1ed9035))

## [2.2.0](https://github.com/univ-lehavre/cluster/compare/v2.1.9...v2.2.0) (2026-06-01)


### Features

* **backup:** sauvegarde des données applicatives par VolumeSnapshots CSI (P1) ([9f67cb7](https://github.com/univ-lehavre/cluster/commit/9f67cb72f4bd3b8475b7ffe5d322f53fa45d81a6))
* **backup:** sauvegarde données applicatives par VolumeSnapshots CSI (audit P1 + ADR 0013) ([#34](https://github.com/univ-lehavre/cluster/issues/34)) ([9f67cb7](https://github.com/univ-lehavre/cluster/commit/9f67cb72f4bd3b8475b7ffe5d322f53fa45d81a6))

## [2.1.9](https://github.com/univ-lehavre/cluster/compare/v2.1.8...v2.1.9) (2026-06-01)


### Bug Fixes

* **etcd-backup:** installe etcd-client (etcdctl prêt pour la restauration) ([1cd0aa0](https://github.com/univ-lehavre/cluster/commit/1cd0aa06c8baa82271c65e25a44dd798d5028371))
* **etcd-backup:** installe etcd-client pour une restauration sans apt en urgence ([#32](https://github.com/univ-lehavre/cluster/issues/32)) ([1cd0aa0](https://github.com/univ-lehavre/cluster/commit/1cd0aa06c8baa82271c65e25a44dd798d5028371))

## [2.1.8](https://github.com/univ-lehavre/cluster/compare/v2.1.7...v2.1.8) (2026-06-01)


### Documentation

* glossaire néophyte en tête de doc (audit P2 — pédagogie 2/5) ([#29](https://github.com/univ-lehavre/cluster/issues/29)) ([5e7a12a](https://github.com/univ-lehavre/cluster/commit/5e7a12a9864f0cf49cf9056068373f7f9b17b0d8))
* **p2:** ajoute un glossaire néophyte + le met en tête de doc ([5e7a12a](https://github.com/univ-lehavre/cluster/commit/5e7a12a9864f0cf49cf9056068373f7f9b17b0d8))

## [2.1.7](https://github.com/univ-lehavre/cluster/compare/v2.1.6...v2.1.7) (2026-06-01)


### Bug Fixes

* **test:** scénario 07 — scoper check-log-errors au temps de test ([27f6417](https://github.com/univ-lehavre/cluster/commit/27f6417c4df8966887388117bf0398381d7f9712))
* **test:** scénario 08 portable (column macOS) + assertion OSD Pending ([4210834](https://github.com/univ-lehavre/cluster/commit/42108344ac569bad1b120c2f96fb272c2e05bb1e))
* **test:** surcharge banc osd.requests.memory 2Gi -&gt; 512Mi dans run-phases ([b613338](https://github.com/univ-lehavre/cluster/commit/b613338711936d48ec53dfc209eeb270373965de))


### Documentation

* **test:** déroulé scénarios 01-08 + périmètre résilience vs artefacts banc ([ceed941](https://github.com/univ-lehavre/cluster/commit/ceed9418e9b6f1582213dd5fc9027cd671064b8b))
* **test:** note — ne pas (re)tester le restore d'un nœud sur le banc ([7397b1b](https://github.com/univ-lehavre/cluster/commit/7397b1b95dbbcc5dcfe64e5202cf5d0c32658155))
* **test:** note — ne pas retester le restore d'un nœud sur le banc ([0212212](https://github.com/univ-lehavre/cluster/commit/02122127c3018dfaed581ecae4bf4fe01bc13d10))

## [2.1.6](https://github.com/univ-lehavre/cluster/compare/v2.1.5...v2.1.6) (2026-05-31)


### Documentation

* acte que les drifts [#8](https://github.com/univ-lehavre/cluster/issues/8)/[#9](https://github.com/univ-lehavre/cluster/issues/9) (CSI) sont résolus par ROOK_USE_CSI_OPERATOR=false ([eb01f68](https://github.com/univ-lehavre/cluster/commit/eb01f68dc1c22760da152bc7566ed71c37dbfec6))
* acte que les drifts CSI [#8](https://github.com/univ-lehavre/cluster/issues/8)/[#9](https://github.com/univ-lehavre/cluster/issues/9) sont résolus par ROOK_USE_CSI_OPERATOR=false ([1cb8700](https://github.com/univ-lehavre/cluster/commit/1cb87006abe39bb6c78e2c4638538b6ad7ec0f37))

## [2.1.5](https://github.com/univ-lehavre/cluster/compare/v2.1.4...v2.1.5) (2026-05-31)


### Bug Fixes

* cni.sh idempotent + kubeconform ignore les .yaml gitignorés ([65cebab](https://github.com/univ-lehavre/cluster/commit/65cebab53d7ae563b5477a548ff9b75ad3b62569))
* **cni:** rends cni.sh idempotent (download + cilium install/upgrade) ([f2797ba](https://github.com/univ-lehavre/cluster/commit/f2797ba385e08795c5efcd3325fd6b030f1edac7))
* **lint:** kubeconform ignore les .yaml gitignorés (git ls-files) ([4a579a7](https://github.com/univ-lehavre/cluster/commit/4a579a7aa7ea2f4b44d34b7cecd7cb447150a40a))

## [2.1.4](https://github.com/univ-lehavre/cluster/compare/v2.1.3...v2.1.4) (2026-05-31)


### Bug Fixes

* **datalake:** smoke-test attend le RGW Ready + port-forward automatique ([1b917a9](https://github.com/univ-lehavre/cluster/commit/1b917a97cdee81af057a9814cc139920b41a3a85))
* **etcd-backup:** rends le backup etcd fonctionnel (crictl + distroless) ([af3bcf6](https://github.com/univ-lehavre/cluster/commit/af3bcf6887ec26949ef4eb0a99569817d72f8771))
* **test+etcd:** banc multi-node intégral 0→6 + backup etcd réparé (5 drifts) ([7bb3d25](https://github.com/univ-lehavre/cluster/commit/7bb3d2566d27986ab7d97fef91b6eb283b28d9c9))
* **test:** aligne le banc multi-node sur /dev/sd* (VirtioSCSI, pas vd*) ([fc3d1e2](https://github.com/univ-lehavre/cluster/commit/fc3d1e279bcde8f4db813298e53ca251827ef498))


### Documentation

* **test:** consigne le Run [#3](https://github.com/univ-lehavre/cluster/issues/3) et le drift [#12](https://github.com/univ-lehavre/cluster/issues/12) (smoke-test datalake) ([96e955f](https://github.com/univ-lehavre/cluster/commit/96e955f1641ca3629a440efaeb9327e1c2c465f9))
* **test:** note que le Run [#3](https://github.com/univ-lehavre/cluster/issues/3) a validé les Phases 3-5 (table gap obsolète) ([dc9b1f5](https://github.com/univ-lehavre/cluster/commit/dc9b1f54d156de7c0d45803423c287c2912d4d43))

## [2.1.3](https://github.com/univ-lehavre/cluster/compare/v2.1.2...v2.1.3) (2026-05-31)


### Documentation

* **safeguards:** documente la publication automatique des releases (PAT + auto-merge) ([2acf748](https://github.com/univ-lehavre/cluster/commit/2acf74863df5a4e2db9c5f3c5ce2bf7cee81fbf0))
* **safeguards:** retire le paragraphe PAT redondant ([1d12e0c](https://github.com/univ-lehavre/cluster/commit/1d12e0c439c9e95e55a23b44674f45e636d5defb))

## [2.1.2](https://github.com/univ-lehavre/cluster/compare/v2.1.1...v2.1.2) (2026-05-31)


### Documentation

* retire PLAN.md et migre son contenu vivant vers RUNBOOK/ADR ([0096722](https://github.com/univ-lehavre/cluster/commit/0096722585a6d80f8e54f1fd9201088a4c9959dd))
* retire PLAN.md, migre phasage canari + wipe Ceph vers RUNBOOK/ADR ([25d490a](https://github.com/univ-lehavre/cluster/commit/25d490a4a51fb3ab30557e7af08a858692096fd4))

## [2.1.1](https://github.com/univ-lehavre/cluster/compare/v2.1.0...v2.1.1) (2026-05-29)


### Documentation

* **audit:** ajoute le rapport d'audit complet du dépôt ([b8571f3](https://github.com/univ-lehavre/cluster/commit/b8571f33b770192717f18a0e55f9fb15ce6b09ae))
* **audit:** rapport d'audit complet du dépôt ([f5f6c68](https://github.com/univ-lehavre/cluster/commit/f5f6c68298a399bf95c0119a31d41dd0df2fe741))
* **test:** clarifie l'expansion du glob state.sh + exporte les surcharges cleanup banc ([13ae846](https://github.com/univ-lehavre/cluster/commit/13ae846bf312557f4cc702601decf1a9a1560a46))
* **test:** clarifie state.sh + exporte les surcharges cleanup banc ([0ef70ef](https://github.com/univ-lehavre/cluster/commit/0ef70efb9ce065decae876f1571717e23ceb8f38))

## [2.1.0](https://github.com/univ-lehavre/cluster/compare/v2.0.1...v2.1.0) (2026-05-29)


### Features

* **test:** orchestrateur run-phases.sh pour valider les phases 1-6 sur le banc ([b1deee8](https://github.com/univ-lehavre/cluster/commit/b1deee807af058459487d3717cd923e6668cb7bd))


### Bug Fixes

* **bootstrap,storage:** rend le déploiement Ceph + outils OS testables sur banc virtio ([80f2bbb](https://github.com/univ-lehavre/cluster/commit/80f2bbb7754bb34100d481e2dda406632339f59a))
* **bootstrap,storage:** rend le déploiement Ceph + outils OS testables sur banc virtio ([1bc5a17](https://github.com/univ-lehavre/cluster/commit/1bc5a1750e363f53f9ead5b79569986d7da006b1))

## [2.0.1](https://github.com/univ-lehavre/cluster/compare/v2.0.0...v2.0.1) (2026-05-29)


### Documentation

* **safeguards:** documente le pré-requis org pour release-please ([74f9719](https://github.com/univ-lehavre/cluster/commit/74f9719314cefebddf025d6b11fb86c57a891c2b))
* **safeguards:** documente le pré-requis org pour release-please ([d510f48](https://github.com/univ-lehavre/cluster/commit/d510f48f620f0da6490042d91795772533ee69ca))

## [2.0.0](https://github.com/univ-lehavre/cluster/compare/v1.0.0...v2.0.0) (2026-05-29)


### ⚠ BREAKING CHANGES

* removed apps elastic, jupyter, scratchpad and the kubevirt platform module; tooling now uses pnpm instead of npm.

### Features

* **bootstrap:** add first-access.sh for fresh-Debian hardening ([6672109](https://github.com/univ-lehavre/cluster/commit/6672109f91f28024a46153b9c87c0f639544420c))
* **bootstrap:** add state.sh — layered cluster state + drift + next step ([90d52d8](https://github.com/univ-lehavre/cluster/commit/90d52d8bec5613d1abf95a3194818656436a1ae1))
* **bootstrap:** bring sshd hardening back into first-access.sh ([f6dc545](https://github.com/univ-lehavre/cluster/commit/f6dc545450ee2ac40ef5aad30d0ba39eebff0759))
* **bootstrap:** control_plane_ip optionnel + RESULTS.md banc multi-node ([39ce206](https://github.com/univ-lehavre/cluster/commit/39ce2068a3823c591ac81c6b2592d05a3863e915))
* **bootstrap:** control-plane endpoint, Cilium 1.19.4, disjoint pod CIDR ([1bf25b7](https://github.com/univ-lehavre/cluster/commit/1bf25b7419edd93019b26b7a3d5567e25f5e86eb))
* **bootstrap:** make first-access.sh strictly idempotent ([651b218](https://github.com/univ-lehavre/cluster/commit/651b21801c96b4a39c20142f701c3e2fe8582291))
* **bootstrap:** merge server-security into bootstrap/security via subtree ([28cb63e](https://github.com/univ-lehavre/cluster/commit/28cb63e33036d4de1cc06954ab3a64190da9e136))
* **bootstrap:** phase 6 — d1 cleanup.sh robuste + d3 sauvegarde etcd ([283887d](https://github.com/univ-lehavre/cluster/commit/283887d108fd8b72e73fb4487ef7a2a2f7331280))
* **bootstrap:** workstream i — audit-log + rollback + corrélation state ([60a3b81](https://github.com/univ-lehavre/cluster/commit/60a3b816a6419ba8c44a2e062375266e5086bad7))
* **ci:** workflow release-please + variable kubelet_node_ip ([32044af](https://github.com/univ-lehavre/cluster/commit/32044afbca07ffd17d1acfcb91d028ed7276fdc5))
* **datalake:** smoke-test end-to-end (user + bucket + put/get/delete) ([de548fd](https://github.com/univ-lehavre/cluster/commit/de548fd1d975a8270778b4d9162614910117a548))
* **platform:** workstream H1-H4 (registry + dashboard durci) ([1344bc9](https://github.com/univ-lehavre/cluster/commit/1344bc99ebf991f499c2e89e6e95ab748c5fe949))
* prune unused modules, migrate to pnpm, fix manifests ([2812f51](https://github.com/univ-lehavre/cluster/commit/2812f5187cc7c9366c188e1f2a47ac6fd20b17c3))
* **rstudio:** adr 0012 + h7 — disable_auth décision assumée ([8b69c46](https://github.com/univ-lehavre/cluster/commit/8b69c466bea11e4730f9d5df6eac2cd1b697e320))
* **security:** make secure.yml progressive via Ansible tags ([4ac90ec](https://github.com/univ-lehavre/cluster/commit/4ac90ecd3e1ad29fb0a30b6b3a9b2b730453f3c1))
* **state:** couche 3b — disques bruts prêts pour Ceph ([495a596](https://github.com/univ-lehavre/cluster/commit/495a59691caada81316f4b2820fd509a3409c1d3))
* **state:** couche 7 plateforme — registry + Kubernetes Dashboard ([8024413](https://github.com/univ-lehavre/cluster/commit/802441359a563263725050aabe7033ceecdc4b85))
* **state:** détecte si mot de passe debian n'a jamais été modifié depuis l'install ([c891796](https://github.com/univ-lehavre/cluster/commit/c89179699006dfdfe98c0246c564d3a70e07cc9c))
* **storage:** phase 3 — rook 1.19.6 + ceph tentacle 20.2.1 ([dff609f](https://github.com/univ-lehavre/cluster/commit/dff609f85c50ba5a7e23612d1ccb5482ab50bebd))
* **storage:** phase 4 — default storage class + workloads on replicated x3 ([aa6fef4](https://github.com/univ-lehavre/cluster/commit/aa6fef42cc10fe7ff8c2096a7727daa19d959020))
* **test:** scenarios reproductibles + drifts [#7](https://github.com/univ-lehavre/cluster/issues/7) [#8](https://github.com/univ-lehavre/cluster/issues/8) [#9](https://github.com/univ-lehavre/cluster/issues/9) [#10](https://github.com/univ-lehavre/cluster/issues/10) ([035b8b4](https://github.com/univ-lehavre/cluster/commit/035b8b4fb445287123a2f24992f6707094d4d6f5))
* **test:** séparer le banc en single-node / multi-node ([1ae9929](https://github.com/univ-lehavre/cluster/commit/1ae9929e666ddd47bf5aa0dd4071c2076e64c478))


### Bug Fixes

* **bootstrap:** ansible-lint — nomme les imports audit-log + casing rollback ([bfb57f5](https://github.com/univ-lehavre/cluster/commit/bfb57f5d51c531141c8eee9efe18b895dbf707e8))
* **bootstrap:** force pty allocation in first-access.sh (ssh -t -&gt; -tt) ([9316be6](https://github.com/univ-lehavre/cluster/commit/9316be632638a010715d82a45eb1c46b9239957c))
* **bootstrap:** harden OS/runtime roles for Debian 13 ([d178d31](https://github.com/univ-lehavre/cluster/commit/d178d31b88868e0c69fca70496a0848f79a28796))
* **bootstrap:** make ansible-lint pass on the production profile ([60219b5](https://github.com/univ-lehavre/cluster/commit/60219b543b658b27691ca5d15e2be7da6efc638b))
* **bootstrap:** make state.sh tolerate empty SSH_OPTS under set -u ([2b4f2e3](https://github.com/univ-lehavre/cluster/commit/2b4f2e3c49b18a2b0b9be2ed70ed5e2d6eaf69a6))
* **bootstrap:** robustness found via the VBox bench ([4cd2c0e](https://github.com/univ-lehavre/cluster/commit/4cd2c0ede86643e489c845350e0a999b6c70bda7))
* **bootstrap:** split first-access into deposit + run to avoid heredoc-vs-sudo-prompt ([1d046b0](https://github.com/univ-lehavre/cluster/commit/1d046b02297377ff89eca675ddd6e4ae0bb04004))
* **ci:** déclare les collections ansible utilisées par bootstrap ([1474ec1](https://github.com/univ-lehavre/cluster/commit/1474ec1dc333bac066bbc6c6e7bba8f277cc58ff))
* **ci:** exclure platform/k8s-dashboard/values.yaml de kubeconform ([d7a3dbf](https://github.com/univ-lehavre/cluster/commit/d7a3dbfdc4b5c7c01a905e9ff24c4ea07ad603b3))
* **ci:** exclure bench/*/inventory.yaml de kubeconform ([0dcfa8f](https://github.com/univ-lehavre/cluster/commit/0dcfa8f6f81ca7437760d266c900141fceb7268a))
* **ci:** installe les collections ansible dans le path utilisateur ([ca81e21](https://github.com/univ-lehavre/cluster/commit/ca81e21b4c44814dabc064647ea8b780394717de))
* **ci:** passe requirements_file à l'action ansible-lint ([4fac0e8](https://github.com/univ-lehavre/cluster/commit/4fac0e8fad631c62299582483cbdc75f67868693))
* **ci:** unbreak ansible-lint + commitlint on PR [#2](https://github.com/univ-lehavre/cluster/issues/2) ([9460d2d](https://github.com/univ-lehavre/cluster/commit/9460d2d4f84ece3fddce8f68929c5dbfaa04d700))
* **state:** check passwd robuste + audit-log baseline playbook ([67263c2](https://github.com/univ-lehavre/cluster/commit/67263c22d40ba0f2f778de92572f490a5ef27083))
* **test:** drift [#6](https://github.com/univ-lehavre/cluster/issues/6) — banc sur 192.168.67.0/24 (disjoint prod) ([8366438](https://github.com/univ-lehavre/cluster/commit/83664384f3d85f6111d69f785539402f8ebc85da))


### Refactor

* **bootstrap:** trim first-access.sh to SSH key + sudo only ([6a877a8](https://github.com/univ-lehavre/cluster/commit/6a877a8a091e021a636e8c237ca17ac529a5790e))
* **security:** integrate the subtree (paths, RUNBOOK, sidebar) ([8486766](https://github.com/univ-lehavre/cluster/commit/84867664f5ea7ac05b73b4cba3ed2ba9ec785e15))


### Documentation

* **bootstrap:** add manual boot-disk partitioning recipe for Debian 13 ([530795c](https://github.com/univ-lehavre/cluster/commit/530795cc373f4db932e19293b8a737fcc164c218))
* **bootstrap:** add network configuration section to RUNBOOK ([6cddd17](https://github.com/univ-lehavre/cluster/commit/6cddd17b4a5d7af49646c8f21f8cf8effd074246))
* **bootstrap:** clarify EFI partition setup (UEFI, no boot flag) ([91fbcbb](https://github.com/univ-lehavre/cluster/commit/91fbcbb4980ef11d22e26a090951dfe8eb052758))
* **bootstrap:** drop the redundant /tmp tmpfs step (default on Debian 13) ([e27bc29](https://github.com/univ-lehavre/cluster/commit/e27bc29f5b075b84ec36219f25ec5653f13175b6))
* **decisions:** phase 7 — adr 0001-0009 + politique versions + b3 ([ae5eb51](https://github.com/univ-lehavre/cluster/commit/ae5eb51ceeb77b269290b6da2dd2f0fcba5dbd78))
* garde-fous visibles + contributing + hardware refresh + vagrant fix ([b3a742a](https://github.com/univ-lehavre/cluster/commit/b3a742abcbccafd907ba15120e8b06c445b9dd76))
* **plan:** sync PLAN.md to Debian 12 + containerd via Docker repo ([9f7e2df](https://github.com/univ-lehavre/cluster/commit/9f7e2df4b8dc0df8c30a239bc435eecff667bee9))
* **plan:** workstream H (plateforme registry + dashboard) + Phase 5 ([03503e1](https://github.com/univ-lehavre/cluster/commit/03503e1e7def650f6e0c9abcec510add7d7e1d36))
* **security:** hardening tout opt-in + implications visibles ([7878895](https://github.com/univ-lehavre/cluster/commit/787889500213c78aeee3220ab1289ef8aed1473d))
* **security:** tailscale déclaré optionnel partout ([408ffda](https://github.com/univ-lehavre/cluster/commit/408ffdac9f43a625226f805ce01b9cdc5fdbb272))
* **site:** set up VitePress and expand the test-bench guide ([6fb2173](https://github.com/univ-lehavre/cluster/commit/6fb21732b1993aa944810d4714fd8fe09ba42239))
* **storage:** bump Rook 1.16 -&gt; 1.19 reference in the Ceph RUNBOOK header ([7549969](https://github.com/univ-lehavre/cluster/commit/754996953876766ed5d834a2e1e7161fc5651d7e))
* **storage:** c6 — preservePoolsOnDelete=false documenté ([606a86a](https://github.com/univ-lehavre/cluster/commit/606a86ad6eab0ff31fefdb169cb83ed1bc58b030))

## 1.0.0 (2026-05-19)

### ⚠ BREAKING CHANGES

- every file has moved or been renamed compared to V0.0.1.

### Features

- scaffold cluster repository (structure, tooling, anonymisation)
  ([2b84f0c](https://github.com/univ-lehavre/cluster/commit/2b84f0c5ea7839cd86fa850147a4338ab33063d4))
