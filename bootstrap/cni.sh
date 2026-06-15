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

# ── Surcharges multi-cluster (optionnelles) — ADR 0027 ─────────────────────
# PROD / mono-cluster : variables vides → comportement INCHANGÉ (podCIDR
# 10.244.0.0/16, aucune identité de cluster posée). Une topologie fédérée
# (Cilium Cluster Mesh, spike bench/spikes/clustermesh-latency) les renseigne
# par site : cluster.id (1-255) + cluster.name UNIQUES et podCIDR DISJOINTS
# entre clusters — exigences non-négociables du mesh.
CILIUM_POD_CIDR="${CILIUM_POD_CIDR:-10.244.0.0/16}"
CILIUM_CLUSTER_NAME="${CILIUM_CLUSTER_NAME:-}"
CILIUM_CLUSTER_ID="${CILIUM_CLUSTER_ID:-}"

# ── Exposition tout-Cilium (ADR 0020/0071) ──────────────────────────────────
# Mode UNIQUE par défaut : le Gateway est exposé en hostNetwork — l'Envoy bind
# 80/443 DIRECTEMENT sur l'IP du nœud (0.0.0.0/::), SANS Service LoadBalancer
# (mutuellement exclusif avec hostNetwork en 1.19 → pas de LB-IPAM requise). =1
# (défaut) arme les flags Helm hostNetwork + pose le GatewayClass.
CILIUM_GATEWAY_HOSTNETWORK="${CILIUM_GATEWAY_HOSTNETWORK:-1}"
# LB-IPAM + L2 (chemin PROD OPTIONNEL, ADR 0071 §4) : IP virtuelle annoncée sur le
# LAN, plage négociée avec l'admin réseau. =0 par défaut (hostNetwork ne le
# requiert pas) ; =1 ré-arme l2announcements + pose CiliumLoadBalancerIPPool + L2.
# `CILIUM_EXPO_ENABLED` reste accepté comme ALIAS rétrocompat (ancien nom : « pose
# les CRs d'exposition »). S'il vaut 0, on n'arme NI hostNetwork NI LB-IPAM (none).
CILIUM_LB_IPAM_ENABLED="${CILIUM_LB_IPAM_ENABLED:-0}"
if [ "${CILIUM_EXPO_ENABLED:-}" = 0 ]; then
  CILIUM_GATEWAY_HOSTNETWORK=0
  CILIUM_LB_IPAM_ENABLED=0
fi
#
# Les CRs (GatewayClass + éventuels CiliumLoadBalancerIPPool/L2 policy) sont
# générés INLINE (heredoc) car cni.sh tourne DANS la VM sans le repo monté —
# platform/cilium-expo/*.yaml restent la référence documentaire versionnée.
# Plage et interface DÉRIVÉES de l'environnement (ADR 0023) — l'appelant injecte
# le concret (banc Lima vs prod) ; pertinents UNIQUEMENT si LB-IPAM=1. Le pool
# DOIT être dans le même sous-réseau L2 que les nœuds (annonce = ARP).
# Hubble UI (ADR 0073) : OPT-IN, désactivé par défaut (=0) — l'ADR 0019 excluait
# l'UI (surface web sans valeur mono-admin) ; 0073 la rend activable sans la rendre
# défaut. =1 ajoute le sous-chart hubble-ui à la release Cilium (même version, même
# ns kube-system). Exposition via Gateway (platform/cilium-expo/), jamais en Service brut.
HUBBLE_UI_ENABLED="${HUBBLE_UI_ENABLED:-0}"
LB_IPAM_RANGE_START="${LB_IPAM_RANGE_START:-10.0.0.240}"
LB_IPAM_RANGE_STOP="${LB_IPAM_RANGE_STOP:-10.0.0.250}"
L2_INTERFACE="${L2_INTERFACE:-eth0}"
GATEWAY_CLASS_NAME="${GATEWAY_CLASS_NAME:-cilium}"

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
# (nodes are on 10.0.0.0/22, inside the default cluster-pool 10.0.0.0/8).
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
  --set ipam.operator.clusterPoolIPv4PodCIDRList="${CILIUM_POD_CIDR}"
  # Chiffrement transparent WireGuard (pod-to-pod) — ADR 0019.
  --set encryption.enabled=true
  --set encryption.type=wireguard
  # Observabilité réseau : Hubble + Relay (ADR 0019). UI optionnelle (ADR 0073,
  # HUBBLE_UI_ENABLED=1 — ajoutée plus bas), désactivée par défaut.
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
  # Gateway API (remplace ingress-nginx). Active enable-envoy-config ; l7Proxy
  # est déjà à true par défaut. Les CRDs Gateway API (v1.4.1) sont pré-installés
  # par platform/cilium-expo/ (Cilium ne les embarque pas). On n'active PAS
  # ingressController.enabled (API Ingress historique, distincte).
  --set gatewayAPI.enabled=true
)
# ── Gateway en hostNetwork (ADR 0071) : l'Envoy du Gateway bind 80/443 sur l'IP
# du nœud (0.0.0.0/::), pas de Service LoadBalancer (désactivé automatiquement par
# hostNetwork en 1.19 → pas de LB-IPAM requise). Ports privilégiés 80/443 : DEUX
# réglages (keepCapNetBindService + ajout de NET_BIND_SERVICE aux capabilities).
# À VÉRIFIER AU BANC : chemin envoy.* (Envoy standalone DaemonSet `cilium-envoy`)
# vs ciliumAgent.* (Envoy embedded dans l'agent). On pose envoy.* (probable en
# 1.19.4) ; si le bind 80/443 échoue, sonder `kubectl get ds -n kube-system
# cilium-envoy` et basculer sur securityContext.capabilities.ciliumAgent.
if [ "${CILIUM_GATEWAY_HOSTNETWORK}" = 1 ]; then
  CILIUM_ARGS+=(
    --set gatewayAPI.hostNetwork.enabled=true
    --set envoy.securityContext.capabilities.keepCapNetBindService=true
    --set "envoy.securityContext.capabilities.add={NET_BIND_SERVICE}"
  )
fi
# ── LB-IPAM + L2 announcements (chemin PROD OPTIONNEL, ADR 0071 §4) : seulement
# si CILIUM_LB_IPAM_ENABLED=1. LB-IPAM n'a pas de flag (actif dès qu'un
# CiliumLoadBalancerIPPool existe) ; L2 crée un Lease par Service LB renouvelé en
# continu → relever k8sClientRateLimit (défauts 5-10 QPS vite saturés ; qps/burst
# dimensionnés ~250 services LB). L2 = BETA en 1.19.
if [ "${CILIUM_LB_IPAM_ENABLED}" = 1 ]; then
  CILIUM_ARGS+=(
    --set l2announcements.enabled=true
    --set k8sClientRateLimit.qps=50
    --set k8sClientRateLimit.burst=100
  )
fi
# Hubble UI (ADR 0073) : posé UNIQUEMENT si HUBBLE_UI_ENABLED=1 (opt-in, défaut 0).
# Même release/version Cilium que hubble.relay → pas de dispersion de versions
# (ADR 0019/0020). Convergent : rejouer cni.sh avec/ sans le flag aligne la ConfigMap.
if [ "${HUBBLE_UI_ENABLED}" = 1 ]; then
  CILIUM_ARGS+=(--set hubble.ui.enabled=true)
fi
# Identité de cluster (mesh) : posée UNIQUEMENT si renseignée. cluster.name vide
# laisse Cilium sur son défaut « default » et n'active aucune fonction mesh.
if [ -n "${CILIUM_CLUSTER_NAME}" ]; then
  CILIUM_ARGS+=(--set cluster.name="${CILIUM_CLUSTER_NAME}")
fi
if [ -n "${CILIUM_CLUSTER_ID}" ]; then
  CILIUM_ARGS+=(--set cluster.id="${CILIUM_CLUSTER_ID}")
fi
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
encrypt_status=$(cilium encrypt status 2>/dev/null || true)
if printf '%s\n' "$encrypt_status" | grep -qi 'wireguard'; then
  echo "✓ WireGuard actif : $(printf '%s\n' "$encrypt_status" | head -n1)"
else
  echo "✗ WireGuard configuré mais INACTIF dans le datapath (cilium encrypt status)." >&2
  echo "  Vérifier le support kernel (module 'wireguard') et les logs cilium-agent." >&2
  exit 1
fi

# ─── Exposition tout-Cilium : application des CRs (ADR 0020/0071) ───────────
# GatewayClass : posée dès qu'une exposition est armée (hostNetwork OU LB-IPAM) —
# le contrôleur Gateway en a besoin dans les DEUX chemins (#232, scénario 28).
# CiliumLoadBalancerIPPool + CiliumL2AnnouncementPolicy : UNIQUEMENT en chemin
# LB-IPAM (inutiles en hostNetwork, où l'Envoy bind l'IP du nœud — ADR 0071).
# APRÈS convergence Cilium (CRDs/contrôleurs prêts). Idempotent (kubectl apply).
#
# apiVersions (alignées Cilium 1.19) — pièges :
#   - CiliumLoadBalancerIPPool : cilium.io/v2 (PROMU en 1.19) ;
#   - CiliumL2AnnouncementPolicy : cilium.io/v2alpha1 (RESTE alpha) ;
#   - GatewayClass : gateway.networking.k8s.io/v1 (GA), controllerName EXACT
#     io.cilium/gateway-controller.
if [ "${CILIUM_GATEWAY_HOSTNETWORK}" = 1 ] || [ "${CILIUM_LB_IPAM_ENABLED}" = 1 ]; then
  echo "Application du GatewayClass (classe ${GATEWAY_CLASS_NAME})…"
  kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: ${GATEWAY_CLASS_NAME}
spec:
  controllerName: io.cilium/gateway-controller
EOF
  echo "✓ GatewayClass appliqué."
else
  echo "ℹ️  exposition désactivée (none) — GatewayClass NON appliqué."
fi

# LB-IPAM + L2 : seulement en chemin prod optionnel (ADR 0071 §4).
if [ "${CILIUM_LB_IPAM_ENABLED}" = 1 ]; then
  echo "Application des CRs LB-IPAM + L2…"
  echo "  pool ${LB_IPAM_RANGE_START}-${LB_IPAM_RANGE_STOP}, L2 sur ${L2_INTERFACE}"
  kubectl apply -f - <<EOF
apiVersion: cilium.io/v2
kind: CiliumLoadBalancerIPPool
metadata:
  name: default-pool
spec:
  blocks:
    - start: "${LB_IPAM_RANGE_START}"
      stop: "${LB_IPAM_RANGE_STOP}"
---
apiVersion: cilium.io/v2alpha1
kind: CiliumL2AnnouncementPolicy
metadata:
  name: default-l2
spec:
  serviceSelector:
    matchLabels: {}
  nodeSelector:
    matchExpressions:
      - key: node-role.kubernetes.io/control-plane
        operator: DoesNotExist
  interfaces:
    - "^${L2_INTERFACE}\$"
  loadBalancerIPs: true
EOF
  echo "✓ CRs LB-IPAM + L2 appliqués."
else
  echo "ℹ️  LB-IPAM désactivé (chemin par défaut hostNetwork) — pool/L2 NON appliqués."
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
        --field-selector=status.phase=Running -o name 2>/dev/null | head -n1 || true)
  # On CAPTURE la sortie AVANT de grep — surtout pas `cmd | grep -q` : grep -q
  # ferme le pipe au 1er match, `cilium-dbg status` reçoit alors SIGPIPE (rc 141)
  # que `set -o pipefail` propage et que `set -e` transforme en mort du script
  # (run sain tué en plein « Attente KubeProxyReplacement »). La capture évite ce
  # pipe fragile ; `|| true` tolère l'exec en échec (pod en cours de redémarrage).
  if [ -n "$pod" ]; then
    kpr_status=$(kubectl -n kube-system exec "$pod" -- cilium-dbg status 2>/dev/null || true)
    if printf '%s\n' "$kpr_status" | grep -qiE 'KubeProxyReplacement:[[:space:]]+True'; then
      kpr_ready=true
      break
    fi
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
