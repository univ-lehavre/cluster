#!/usr/bin/env bash
set -euo pipefail

# Idempotent : rejouable sans erreur si le CLI est déjà posé ou si Cilium est
# déjà installé dans le cluster (le banc multi-node le rejoue, et un opérateur
# peut relancer la phase CNI après un échec partiel).

CILIUM_VERSION=1.19.4          # version du composant Cilium (Helm release)
# Cilium CLI (pinned for reproducibility)
CILIUM_CLI_VERSION=v0.19.4
CLI_ARCH=amd64
if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi

# --- Installer le CLI cilium (idempotent) ---------------------------------
if command -v cilium > /dev/null 2>&1; then
  echo "cilium CLI déjà présent ($(command -v cilium)) — skip download."
else
  TARBALL="cilium-linux-${CLI_ARCH}.tar.gz"
  # Nettoyage préalable : un .tar.gz résiduel d'un run avorté ferait échouer
  # curl --remote-name-all ou le rm final.
  rm -f "${TARBALL}" "${TARBALL}.sha256sum"
  curl -L --fail --remote-name-all "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/${TARBALL}"{,.sha256sum}
  sha256sum --check "${TARBALL}.sha256sum"
  sudo tar xzvfC "${TARBALL}" /usr/local/bin
  rm -f "${TARBALL}" "${TARBALL}.sha256sum"
fi

# --- Installer / mettre à niveau Cilium dans le cluster (idempotent) -------
# `cilium install` échoue si la release Helm existe déjà
# (« cannot reuse a name that is still in use »). On détecte l'install
# existante via `cilium status` et on bascule sur `upgrade`.
#
# CNI — pin Cilium and use a pod CIDR disjoint from the node network
# (nodes are on 10.67.2.0/22, inside the default cluster-pool 10.0.0.0/8).
#
# Durcissement réseau (ADR 0019). Les `--set` sont appliqués à l'install ET à
# l'upgrade → un banc/cluster existant converge en rejouant ce script.
#
#   - encryption WireGuard (pod-to-pod) : défense en profondeur qui complète
#     l'ADR 0003 (réseau privé de confiance). Cilium gère les clés tout seul
#     (pas de KMS/Vault à inventer, contrairement au LUKS Ceph écarté en 0003).
#     On reste sur le chiffrement pod-to-pod (PAS `nodeEncryption`, plus
#     intrusif et susceptible de gêner les health-checks). Pré-requis kernel :
#     module `wireguard` (présent sur Debian 13, kernel ≥ 5.6).
#   - Hubble relay + CLI (observabilité des flux), SANS UI : `hubble observe`
#     en ligne de commande suffit pour un cluster mono-admin et n'ajoute pas de
#     surface web exposée (cf. ADR 0019). Complète l'ADR 0016 (metrics-server),
#     sur l'axe RÉSEAU et non métrologique.
CILIUM_ARGS=(
  --version "${CILIUM_VERSION}"
  --set ipam.operator.clusterPoolIPv4PodCIDRList=10.244.0.0/16
  # Chiffrement transparent WireGuard (pod-to-pod) — ADR 0019.
  --set encryption.enabled=true
  --set encryption.type=wireguard
  # Observabilité réseau : Hubble + Relay, sans UI — ADR 0019.
  --set hubble.enabled=true
  --set hubble.relay.enabled=true
)
if cilium status > /dev/null 2>&1; then
  echo "Cilium déjà installé — cilium upgrade (réconciliation des valeurs)."
  cilium upgrade "${CILIUM_ARGS[@]}"
  # `cilium upgrade` met à jour la ConfigMap mais ne roule PAS toujours le
  # DaemonSet quand seules des valeurs changent (ex. activation WireGuard) :
  # les agents gardent alors l'ancienne config et le datapath WireGuard n'est
  # jamais réellement armé (config-drift-checker signale `enable-wireguard
  # actual=false expected=true`). On force donc le rollout des agents + de
  # l'operator, puis on attend la reconvergence. Idempotent (un restart sans
  # changement de config ne fait que recréer les pods à l'identique).
  echo "Rollout des agents Cilium (applique réellement la nouvelle config)…"
  kubectl -n kube-system rollout restart daemonset/cilium deployment/cilium-operator
  kubectl -n kube-system rollout status daemonset/cilium --timeout=3m
else
  cilium install "${CILIUM_ARGS[@]}"
fi

# Attendre que les agents reconvergent (le passage à WireGuard redémarre le
# DaemonSet cilium ; Hubble Relay se déploie). Best-effort, n'échoue pas le
# script si la fenêtre est trop courte — l'opérateur peut re-vérifier.
echo "Attente de la reconvergence Cilium (WireGuard + Hubble)…"
cilium status --wait --wait-duration 3m || \
  echo "⚠️ cilium status pas encore tout vert — re-vérifier avec 'cilium status'."

# Vérification explicite : WireGuard doit être réellement ACTIF dans le
# datapath (pas seulement présent en config). Échoue le script sinon — un
# durcissement silencieusement inactif est pire qu'un échec visible.
echo "Vérification du chiffrement WireGuard…"
if cilium encrypt status 2>/dev/null | grep -qi 'wireguard'; then
  echo "✓ WireGuard actif : $(cilium encrypt status 2>/dev/null | head -1)"
else
  echo "✗ WireGuard configuré mais INACTIF dans le datapath (cilium encrypt status)." >&2
  echo "  Vérifier le support kernel (module 'wireguard') et les logs cilium-agent." >&2
  exit 1
fi
