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
* **test:** aligne test/README sur les chemins storage-real/cluster-dataops (ADR 0045, [#237](https://github.com/univ-lehavre/cluster/issues/237)) ([0fa827c](https://github.com/univ-lehavre/cluster/commit/0fa827cbfe48df7f08aedc322279588868051571))
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
