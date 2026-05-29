#!/usr/bin/env bash
set -euo pipefail

# Cilium CLI (pinned for reproducibility)
CILIUM_CLI_VERSION=v0.19.4
CLI_ARCH=amd64
if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi
curl -L --fail --remote-name-all "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz"{,.sha256sum}
sha256sum --check "cilium-linux-${CLI_ARCH}.tar.gz.sha256sum"
sudo tar xzvfC "cilium-linux-${CLI_ARCH}.tar.gz" /usr/local/bin
rm "cilium-linux-${CLI_ARCH}.tar.gz"{,.sha256sum}

# CNI — pin Cilium and use a pod CIDR disjoint from the node network
# (nodes are on 10.67.2.0/22, inside the default cluster-pool 10.0.0.0/8).
cilium install \
  --version 1.19.4 \
  --set ipam.operator.clusterPoolIPv4PodCIDRList=10.244.0.0/16
