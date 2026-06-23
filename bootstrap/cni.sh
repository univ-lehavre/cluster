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

# ── Exposition L4 NodePort (ADR 0092, supersede ADR 0071) ────────────────────
# Mode UNIQUE : exposition L4 par Service NodePort (http://<IP-nœud>:<nodePort>,
# zéro DNS, zéro LB-IPAM, zéro Gateway). NodePort est servi en eBPF par
# `kubeProxyReplacement=true` (posé plus bas) — AUCUN flag Helm ni CR n'est requis.
# Le contrôleur Gateway API, le GatewayClass et le chemin LB-IPAM (Gateway L7
# hostNetwork de l'ex-ADR 0071) sont RETIRÉS : plus de bordure L7, plus d'IP
# virtuelle annoncée. Le poste opérateur atteint les nœuds → l'IP du nœud suffit.
#
# Bascule depuis un cluster ex-LB-IPAM/Gateway (ex. dirqual) : cni.sh est ADDITIF
# (Helm/kubectl apply) — il ne supprime pas les CR d'un mode précédent. On RETIRE
# donc explicitement (best-effort, --ignore-not-found) le pool/L2/GatewayClass
# résiduels, pour une bascule propre sur cluster vivant (corriger le code, ADR 0046).
HUBBLE_UI_ENABLED="${HUBBLE_UI_ENABLED:-0}"

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
# announcements (IP LoadBalancer + annonce ARP), Gateway API (bordure L7). Ici on
# n'arme que les FEATURES côté agent. Appliqué à l'install ET à l'upgrade →
# convergent en rejouant le script (même invariant que le durcissement 0019).
# NB : les UI ne passent plus par le Gateway L7 — elles sont exposées en L4
# (NodePort/hostPort sur l'IP du nœud, ADR 0092) ; LB-IPAM/Gateway restent des
# features Cilium disponibles (chemin de prod optionnel), mais le dossier de CRs
# platform/cilium-expo/ a été retiré avec la bascule L4.
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
  # Exposition L4 (ADR 0092) : NodePort est servi en eBPF par kubeProxyReplacement
  # ci-dessus. AUCUN flag Gateway API (gatewayAPI.enabled / hostNetwork) ni LB-IPAM
  # (l2announcements) — la bordure L7 et l'IP virtuelle de l'ex-ADR 0071 sont retirées.
  # ingressController.enabled n'est pas non plus posé (API Ingress historique).
)
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

# ─── Bascule vers L4 pur : retrait des CR d'exposition résiduels (ADR 0092) ──
# cni.sh est ADDITIF — il ne supprime pas les objets d'un mode précédent. Sur un
# cluster monté en ex-Gateway/LB-IPAM (ADR 0071), on retire explicitement le
# GatewayClass, le CiliumLoadBalancerIPPool et la CiliumL2AnnouncementPolicy
# par défaut pour une bascule PROPRE (corriger le code, pas l'état — ADR 0046).
# Best-effort (--ignore-not-found) : sur un cluster monté nativement en L4, il n'y
# a rien à retirer. Les CRD Gateway peuvent rester (inoffensives, plus aucun
# Gateway/HTTPRoute ne les utilise). L'exposition se fait par Service NodePort,
# appliqué par les rôles plateforme (platform/*/nodeport.yaml).
echo "Retrait des CR d'exposition L7/LB-IPAM résiduels (bascule L4, ADR 0092)…"
kubectl delete ciliumloadbalancerippool default-pool --ignore-not-found 2>/dev/null || true
kubectl delete ciliuml2announcementpolicy default-l2 --ignore-not-found 2>/dev/null || true
kubectl delete gatewayclass cilium --ignore-not-found 2>/dev/null || true
echo "✓ exposition L4 NodePort (aucun Gateway, aucun pool LB-IPAM)."

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
