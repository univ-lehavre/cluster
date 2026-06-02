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
#
# Exposition réseau tout-Cilium (ADR 0020). Cilium remplace MetalLB ET
# ingress-nginx : kube-proxy replacement (datapath eBPF), LB-IPAM + L2
# announcements (IP LoadBalancer + annonce ARP), Gateway API (bordure L7). Les
# pools/policies/Gateway sont des CRs versionnés sous platform/cilium-expo/ ;
# ici on n'arme que les FEATURES côté agent. Appliqué à l'install ET à l'upgrade
# → convergent en rejouant le script (même invariant que le durcissement 0019).
CILIUM_ARGS=(
  --version "${CILIUM_VERSION}"
  --set ipam.operator.clusterPoolIPv4PodCIDRList=10.244.0.0/16
  # Chiffrement transparent WireGuard (pod-to-pod) — ADR 0019.
  --set encryption.enabled=true
  --set encryption.type=wireguard
  # Observabilité réseau : Hubble + Relay, sans UI — ADR 0019.
  --set hubble.enabled=true
  --set hubble.relay.enabled=true
  # ── Exposition tout-Cilium (ADR 0020) ──────────────────────────────────
  # kube-proxy replacement (eBPF). En 1.19 le flag est un BOOLÉEN (true/false ;
  # les anciennes valeurs strict/partial/probe ont disparu) et active déjà
  # NodePort/HostPort/ExternalIPs (flags --enable-* retirés en 1.19 → ne pas
  # les poser). Sans kube-proxy, l'agent ne joint plus l'API via la ClusterIP
  # kubernetes.default → lui donner l'endpoint en dur est OBLIGATOIRE.
  # `cluster-api` est résolu par /etc/hosts du nœud (rôle k8s-install) ; les
  # pods cilium-agent sont en hostNetwork → ils utilisent ce resolver.
  --set kubeProxyReplacement=true
  --set k8sServiceHost=cluster-api
  --set k8sServicePort=6443
  # LB-IPAM + L2 announcements (remplacent MetalLB). LB-IPAM n'a pas de flag
  # (actif dès qu'un CiliumLoadBalancerIPPool existe). L2 crée un Lease par
  # Service LB renouvelé en continu → relever k8sClientRateLimit (défauts 5-10
  # QPS vite saturés). qps/burst dimensionnés pour ~250 services LB ; ajuster
  # avec QPS = #services / leaseRenewDeadline (défaut 5s). L2 = BETA en 1.19.
  --set l2announcements.enabled=true
  --set k8sClientRateLimit.qps=50
  --set k8sClientRateLimit.burst=100
  # Gateway API (remplace ingress-nginx). Active enable-envoy-config ; l7Proxy
  # est déjà à true par défaut. Les CRDs Gateway API (v1.4.1) sont pré-installés
  # par platform/cilium-expo/ (Cilium ne les embarque pas). On n'active PAS
  # ingressController.enabled (API Ingress historique, distincte).
  --set gatewayAPI.enabled=true
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

# ─── Retrait de kube-proxy (ADR 0020) ──────────────────────────────────────
# ORDRE OBLIGATOIRE : on ne retire kube-proxy qu'APRÈS avoir vérifié que Cilium
# prend réellement le relais (KubeProxyReplacement: True). Retirer kube-proxy
# avant que l'agent ne sache joindre l'API server casserait le redémarrage des
# agents. Tout est idempotent (`--ignore-not-found`, et la purge iptables est
# sans effet sur un nœud déjà nettoyé).
echo "Attente de l'armement de KubeProxyReplacement par les agents…"
# Le rollout des agents Cilium ne bascule pas KubeProxyReplacement à True
# instantanément : après le restart du DaemonSet, les pods passent par une
# phase non-Ready (où `exec` échoue) PUIS reconvergent (observé : la bascule
# n'est lisible qu'une fois les 3 agents Running + reconvergés, ~1-2 min sur
# banc). On attend donc d'abord la fin du rollout, puis on SONDE en boucle
# (tolérant aux exec en échec). Sinon on conclut « False » à tort pendant que
# les agents redémarrent, et kube-proxy n'est jamais retiré. Budget : ~3 min,
# puis on conserve kube-proxy (sûr).
kubectl -n kube-system rollout status daemonset/cilium --timeout=2m 2>/dev/null || true
kpr_ready=false
for _ in $(seq 1 36); do
  # exec sur un pod Running explicite (pas `ds/cilium` qui peut viser un pod
  # en cours de redémarrage). On tolère l'absence momentanée de pod prêt.
  pod=$(kubectl -n kube-system get pods -l k8s-app=cilium \
        --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
  if [ -n "$pod" ] && kubectl -n kube-system exec "$pod" -- cilium-dbg status 2>/dev/null \
      | grep -qiE 'KubeProxyReplacement:[[:space:]]+True'; then
    kpr_ready=true
    break
  fi
  sleep 5
done
if [ "$kpr_ready" = true ]; then
  echo "✓ KubeProxyReplacement actif — retrait de kube-proxy."
  # Stoppe kube-proxy géré par kubeadm (DaemonSet + ConfigMap).
  kubectl -n kube-system delete ds kube-proxy --ignore-not-found
  kubectl -n kube-system delete cm kube-proxy --ignore-not-found
  # Purge des règles iptables résiduelles SUR CE NŒUD (le delete du DaemonSet ne
  # les retire pas). À rejouer sur chaque autre nœud (boucle SSH côté banc /
  # prod). Commande officielle Cilium. ip6tables uniquement si IPv6 actif.
  if command -v iptables-save > /dev/null 2>&1; then
    sudo sh -c 'iptables-save | grep -v KUBE | iptables-restore' \
      && echo "✓ règles iptables KUBE-* purgées sur $(hostname)." \
      || echo "⚠️ purge iptables non effectuée (à faire manuellement)." >&2
  fi
  echo "ℹ️  Purge iptables à RÉPÉTER sur les autres nœuds (root) :"
  echo "    iptables-save | grep -v KUBE | iptables-restore"
  echo "ℹ️  Durabilité : kubeadm recrée kube-proxy à l'init/upgrade. Le rendu"
  echo "    permanent est posé via skipPhases: [addon/kube-proxy] dans la config"
  echo "    kubeadm (rôle k8s-initialization) — déjà appliqué aux nouveaux clusters."
else
  echo "✗ KubeProxyReplacement toujours False après 90 s — kube-proxy CONSERVÉ (sûr)." >&2
  echo "  La bascule n'a pas convergé dans le délai. Re-vérifier puis rejouer ce" >&2
  echo "  script (idempotent) : kubectl -n kube-system exec ds/cilium -- cilium-dbg status --verbose" >&2
  echo "  Ne PAS retirer kube-proxy tant que Cilium n'a pas pris le relais (ADR 0020)." >&2
fi
