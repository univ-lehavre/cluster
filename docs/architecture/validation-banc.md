# Validation sur banc — historique et évolution

> ⏱️ **Photo historique du banc Vagrant (mai 2026).** Ce banc VirtualBox
> (`192.168.67.0/24`) est **déprécié au profit du banc Lima**
> ([ADR 0038](../decisions/0038-lima-seul-banc-local.md)). Les campagnes
> **courantes** (Lima) sont synthétisées dans
> [lecons-des-runs.md](lecons-des-runs.md) et journalisées dans
> [`bench/lima/RESULTS.md`](../../bench/lima/RESULTS.md). Cette page reste **non
> réécrite** (honnêteté des Runs,
> [ADR 0052](../decisions/0052-reproductibilite-des-resultats.md)).

Cette page donne une **vue d'évolution** des campagnes de test sur le banc
multi-nœuds Vagrant : ce qui a été validé, quand, et avec quels écarts
(_findings_) corrigés. Le **détail brut** de chaque campagne (logs, symptômes,
correctifs) reste dans le journal [`bench/RESULTS.md`](../../bench/RESULTS.md) ;
cette page en est la synthèse navigable.

> **Le banc.** 3 VM Debian 13 **arm64** (Apple Silicon + VirtualBox), réseau
> privé `192.168.67.0/24`, topologie 1 control-plane + 2 workers. Il **exerce
> réellement** la séquence d'installation et de durcissement avant la prod — il
> n'est volontairement **pas** fidèle au matériel (arm64 vs x86, disques VirtIO
> vs SAS/NVMe) mais l'est sur la **logique** (multi-nœuds, kubeadm, Ceph,
> réseau).

## Pourquoi un banc (et pas seulement du lint)

Le lint (yamllint, kubeconform, shellcheck, trivy…) valide la **forme**. Le banc
valide le **comportement** — et c'est là que se cachent les vrais pièges :
plusieurs findings ci-dessous (bascule réseau, architecture d'image, taille de
CRD) **passaient le lint** et n'ont été attrapés qu'en déployant pour de vrai.

## Évolution des campagnes

Verdict global de chaque campagne, du plus ancien au plus récent. Les findings
sont comptés par gravité : 🔴 bloquant · 🟠 moyen · 🟢 bénin.

| Run | Date       | Objet                                                | Verdict | Findings  |
| --- | ---------- | ---------------------------------------------------- | ------- | --------- |
| #1  | 2026-05-27 | Premier montage banc (OS, disques, bootstrap k8s)    | ✅      | 🔴×4 🟢×1 |
| #2  | 2026-05-28 | Banc sur `192.168.67.0/24` (réseau privé propre)     | ✅      | 🔴×2 🟠×2 |
| #3  | 2026-05-31 | Relance intégrale (Ceph + StorageClasses + datalake) | ✅      | 🔴×3 🟠×1 |
| #4  | 2026-06-01 | Durcissement OS (`secure.yml` : postfix/auditd/f2b)  | ✅      | —         |
| #5  | 2026-06-01 | Scénarios de durcissement (pod + hôte)               | ✅      | —         |
| #6  | 2026-06-02 | Durcissement réseau Cilium (WireGuard + Hubble)      | ✅      | 🟠×1      |
| #7  | 2026-06-02 | Nettoyage banc + rejeu intégral des scénarios        | ✅      | 🟢×2 🟠×1 |
| #8  | 2026-06-02 | Chiffrement at-rest etcd + audit-policy (ADR 0014)   | ✅      | 🟢×1      |
| #9  | 2026-06-02 | Rebuild **greenfield** complet (from scratch)        | ✅      | 🔴×1 🟠×2 |
| #10 | 2026-06-02 | **Exposition tout-Cilium** (ADR 0020)                | ✅      | 🔴×1      |
| #11 | 2026-06-03 | **Argo CD** GitOps (ADR 0022)                        | ✅      | 🔴×2      |

> Les Runs #1 et #4 sont consignés dans les tableaux de tête de
> [`RESULTS.md`](../../bench/RESULTS.md) (avant la numérotation `## Run`).

## Lecture de l'évolution

- **Runs #1→#3 — fondations.** Faire tenir le banc lui-même (disques arm64,
  collisions réseau prod↔banc), puis dérouler bootstrap → Ceph → stockage →
  datalake. Beaucoup de findings 🔴, tous corrigés ; plusieurs avaient un
  **impact prod** (CRDs CSI manquants, backup etcd fantôme).
- **Runs #4→#8 — durcissement.** Sécurité OS, scénarios pod/hôte, réseau Cilium
  (WireGuard), chiffrement etcd. Campagnes **propres** (peu ou pas de findings)
  — le socle se stabilise.
- **Run #9 — preuve de reproductibilité.** Premier rebuild **intégral depuis
  zéro** : prouve que le bootstrap part de rien et arrive à un cluster complet
  et durci.
- **Runs #10→#11 — la plateforme.** Exposition réseau (tout-Cilium) puis GitOps
  (Argo CD). C'est ici que la chaîne décrite dans
  [exposition-reseau.md](exposition-reseau.md) a été exercée.

## Findings marquants des dernières campagnes (#10–#11)

Ceux qui illustrent le mieux la valeur du banc — invisibles au lint :

- **#23 (🔴, Run #10)** — `cni.sh` concluait que Cilium n'avait **pas** pris le
  relais de kube-proxy (test fait trop tôt, pendant le redémarrage des agents) →
  kube-proxy n'était **jamais** retiré, la bascule restait à moitié faite.
  Corrigé par une attente de convergence. _(Mergé en PR #99.)_
- **#25 (🔴, Run #11)** — l'image `redis` d'Argo CD était épinglée sur un digest
  **amd64** (et non l'index multi-arch) → `exec format error` sur le banc
  **arm64**. Même piège que le finding **#0e** (images Ceph). Leçon récurrente :
  **toujours épingler le digest d'_index_** multi-arch.
- **#24 (🔴, Run #11)** — la CRD `applicationsets` d'Argo CD dépasse la limite
  d'annotation de `kubectl apply` → installation en `--server-side`.

## Ce qui reste à valider sur banc

| À valider                                           | Dépend de                     |
| --------------------------------------------------- | ----------------------------- |
| cert-manager (émission d'un cert sur le Gateway)    | déploiement cert-manager banc |
| Argo CD via Gateway + cert + gRPC `--grpc-web`      | cert-manager banc             |
| Phases 1.5–1.8 (monitoring, CNPG, Dagster, Marquez) | étapes à venir                |

> **Aucun de ces composants n'est en production.** Le banc valide la logique ;
> le déploiement réel reste une action humaine, tracée étape par étape.
>
> **Chaîne DataOps assemblée.** Le harnais
> `bench/lima/run-phases.sh cluster-dataops` déploie et vérifie
> `monitoring → CNPG → Dagster → Marquez` de bout en bout (#148). Pour la carte
> d'accès et les actions vérifiables par brique (URL navigateur / commande
> console), voir [La chaîne DataOps de bout en bout](chaine-dataops.md).
