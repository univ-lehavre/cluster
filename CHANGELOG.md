# Changelog

Toutes les modifications notables sont documentées ici. Ce fichier suit le
format [Keep a Changelog](https://keepachangelog.com/) et les versions
respectent [SemVer](https://semver.org/).

Les entrées sont générées automatiquement à partir des messages de commit
[Conventional Commits](https://www.conventionalcommits.org/) via
[commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version)
:

```bash
pnpm release:dry   # aperçu
pnpm release       # bump + tag + commit
```

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
* **ci:** exclure test/*/inventory.yaml de kubeconform ([0dcfa8f](https://github.com/univ-lehavre/cluster/commit/0dcfa8f6f81ca7437760d266c900141fceb7268a))
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
