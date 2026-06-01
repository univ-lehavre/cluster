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
