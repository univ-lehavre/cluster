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
