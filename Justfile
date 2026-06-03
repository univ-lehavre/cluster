# Justfile — point d'entrée léger nommant l'existant (audit P10 #16).
#
# Ce n'est PAS un CLI d'orchestration : la séquence réelle vit dans Ansible et
# est documentée pas à pas dans bootstrap/RUNBOOK.md (qui reste la référence).
# Ce Justfile donne des raccourcis découvrables vers les commandes déjà là.
#
# Installer just : https://github.com/casey/just  (`brew install just`).
# Lister les recettes : `just`  (ou `just --list`).

inventory := "bootstrap/hosts.yaml"

# Liste les recettes disponibles (défaut).
default:
    @just --list

# ─── Qualité (identique à la CI / aux hooks) ────────────────────────────────

# Toute la chaîne qualité locale (format, yaml, shell, dup, bats).
lint:
    pnpm lint

# Corrige le formatage (prettier).
format:
    pnpm format

# Tests unitaires bash (bats sur les fonctions pures de state.sh).
test-unit:
    pnpm test:shell

# ─── État du cluster ────────────────────────────────────────────────────────

# Drift par couche sur tous les nœuds (ou un sous-ensemble : `just state cp1`).
state *hosts:
    bootstrap/state.sh {{ hosts }}

# Rapport de durcissement OS (lecture seule).
security-report *hosts:
    bootstrap/security/report.sh {{ hosts }}

# ─── Bootstrap prod (ordre du RUNBOOK — voir bootstrap/RUNBOOK.md) ───────────
# ⚠️ Lire le RUNBOOK avant : ces playbooks s'enchaînent dans cet ordre, sur des
# nœuds Debian 13 déjà préparés (partitionnement, wipe disques, first-access).

# 1. Pré-requis OS/runtime (swap, modules noyau, CRI containerd, paquets K8s).
checks:
    ansible-playbook -i {{ inventory }} bootstrap/checks.yaml

cri:
    ansible-playbook -i {{ inventory }} bootstrap/cri.yaml

# 2. kubeadm init (control plane) + endpoint, puis CNI Cilium.
kubeadm:
    ansible-playbook -i {{ inventory }} bootstrap/kubeadm.yaml

init:
    ansible-playbook -i {{ inventory }} bootstrap/initialisation.yaml

# CNI Cilium (à lancer après l'init du control plane).
cni:
    bash bootstrap/cni.sh

# Jonction des workers au cluster.
join-workers:
    ansible-playbook -i {{ inventory }} bootstrap/join-workers.yaml

# ─── Exploitation ───────────────────────────────────────────────────────────

# Installe le timer de sauvegarde etcd horaire.
etcd-backup:
    ansible-playbook -i {{ inventory }} bootstrap/etcd-backup.yaml

# Rapatrie le dernier snapshot etcd hors-nœud (→ etcd-snapshots/). À planifier.
etcd-fetch:
    ansible-playbook -i {{ inventory }} bootstrap/etcd-fetch.yaml

# Mise à jour des paquets OS (full-upgrade + reboot si requis) sur tout le parc.
os-upgrade:
    ansible-playbook -i {{ inventory }} bootstrap/os-upgrade.yaml

# Upgrade Kubernetes in-place, séquencé (ADR 0015). Ex : `just k8s-upgrade 1.34.9`.
# Mineure : ajouter le dépôt via -e (voir RUNBOOK § Mise à jour de Kubernetes).
k8s-upgrade version:
    ansible-playbook -i {{ inventory }} bootstrap/k8s-upgrade.yaml -e k8s_upgrade_version={{ version }}

# Rollback du bootstrap K8s (DESTRUCTIF — exige confirm=yes).
rollback confirm="no":
    ansible-playbook -i {{ inventory }} bootstrap/rollback.yaml -e confirm={{ confirm }}

# ─── Observabilité (ADR 0016) ───────────────────────────────────────────────

# Déploie metrics-server (kubectl top + HPA). Stack Prometheus = palier 2.
metrics-server:
    kubectl apply -f platform/metrics-server/metrics-server.yaml

# ─── Documentation (site VitePress) ─────────────────────────────────────────

# Sert la doc en local (http://localhost:5173).
docs:
    pnpm docs:dev

# ─── Banc de test (VirtualBox + Vagrant) ────────────────────────────────────
# Orchestrateur à gates : voir test/multi-node/run-phases.sh.

# Banc multi-nœuds, phase par phase ou tout : `just bench all` / `just bench ceph`.
bench phase="all":
    test/multi-node/run-phases.sh {{ phase }}

# Détruit les VMs du banc multi-nœuds.
bench-destroy:
    cd test/multi-node && vagrant destroy -f
