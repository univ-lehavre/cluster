"""Sondes et fonctions PURES du montage HA `ha-3cp` (ADR 0047/0055, #250).

Module-FEUILLE de la HA : il ne dépend de RIEN d'autre dans `nestor` (ni gates,
ni path) — d'où son existence séparée. Les gates HA (`nestor.gates.gate_vip`,
`gate_etcd`) ET le moteur de promotion (`nestor.path`) consomment ces sondes ; les
loger ici évite un cycle d'import (gates ⇄ path) et garde la couche I/O isolée.

Deux familles (patron historique de `ha.py`, dissous LOT 9-fusion) :
  - FONCTIONS PURES (cp_join_order, classify_etcd_health, *_extravars) : aucun I/O,
    testées par pytest sur des fixtures ;
  - SONDES I/O ISOLÉES (`_vm_exec`, `vip_healthz`, `etcd_health_output`, `_etcd_cid`) :
    `limactl`/`crictl` bornés, INJECTABLES (stub en test).

Ansible reste le moteur de convergence (ADR 0056 §7) ; ces sondes ne réimplémentent
aucune idempotence (ADR 0063 G1). La PREUVE réelle est un run de banc consigné
(ADR 0034/0052, #250 — le code ne vaut pas preuve seul).
"""

from __future__ import annotations

import subprocess

# ── Fonctions PURES (testables sans banc) ────────────────────────────────────


def cp_join_order(nodes: list[str]) -> list[str]:
    """Les control-planes à PROMOUVOIR (tous SAUF le primaire), dans l'ordre.

    Le premier nœud est le CP primaire (init) ; les suivants rejoignent UN À UN.
    Vide si ≤ 1 nœud (pas de HA). Déterministe (ordre d'apparition préservé).
    """
    return list(nodes[1:])


def classify_etcd_health(out: str, expected: int) -> tuple[str, str]:
    """Verdict de `etcdctl endpoint health --cluster` avant de promouvoir le CP
    suivant (fenêtre N fragile, #250). Renvoie (statut, message), statut ∈
    {ok, fail, skip} :
      - tous les `expected` endpoints « is healthy » → ok (quorum sain) ;
      - au moins un « is unhealthy »                 → fail (ne pas promouvoir) ;
      - sortie vide / incomplète                     → skip (attendre / refus franc).
    """
    out = out.strip()
    if not out:
        return ("skip", "santé etcd illisible (sortie vide) — etcd injoignable ?")
    unhealthy = out.count("is unhealthy")
    healthy = out.count("is healthy")
    if unhealthy > 0:
        return ("fail", f"quorum etcd DÉGRADÉ ({unhealthy} endpoint(s) unhealthy)")
    if expected > 0 and healthy >= expected:
        return ("ok", f"quorum etcd sain ({healthy}/{expected} endpoints healthy)")
    return ("skip", f"santé etcd incomplète ({healthy}/{expected}) — attendre")


def bootstrap_extravars(cp_ip: str, vip: str, vip_iface: str) -> dict[str, str]:
    """Le faisceau `-e` du bootstrap du CP PRIMAIRE (subtilité HA prouvée au run) :
    - control_plane_endpoint = `cluster-api` (HOSTNAME, pour kubeadm + cni.sh) ;
    - control_plane_host_ip  = la VIP (/etc/hosts mappe cluster-api → VIP) ;
    - control_plane_ip       = l'IP RÉELLE du nœud (advertiseAddress kubeadm) ;
    - control_plane_vip      = la VIP (certSANs + gate du rôle de join) ;
    - kube_vip_address/interface = la VIP et son interface L2.
    """
    return {
        "control_plane_endpoint": "cluster-api",
        "control_plane_host_ip": vip,
        "control_plane_ip": cp_ip,
        "control_plane_vip": vip,
        "kube_vip_address": vip,
        "kube_vip_interface": vip_iface,
    }


def join_extravars(vip: str, vip_iface: str) -> dict[str, str]:
    """Le faisceau `-e` de la promotion d'un CP additionnel. L'endpoint reste le
    hostname ; la VIP (control_plane_vip) sert la gate du rôle (le /etc/hosts du
    nouveau nœud n'est pas garanti posé à ce stade)."""
    return {
        "control_plane_endpoint": "cluster-api",
        "control_plane_host_ip": vip,
        "control_plane_vip": vip,
        "kube_vip_address": vip,
        "kube_vip_interface": vip_iface,
    }


# ── Sondes d'exécution ISOLÉES (I/O, injectable) ─────────────────────────────


# TIMEOUT des commandes dans une VM : un `limactl shell` (SSH) peut PENDRE
# indéfiniment (VM lente, lien KO) ; sans borne, une gate (vip/etcd) bloquerait le
# run entier en attente d'un sous-process qui ne rend jamais la main (constaté au
# banc). On borne ; un dépassement = commande échouée (rc≠0), la gate retentera.
_VM_EXEC_TIMEOUT_S = 30


def _vm_exec(vm: str, command: list[str]) -> subprocess.CompletedProcess:
    """Exécute une commande DANS une VM Lima (`limactl shell`). Patron lib.sh:vm_sh.
    Isolé → stubbable en test. Ne lève PAS (l'appelant lit rc/stdout) : un timeout
    se mappe en CompletedProcess(rc=124, stdout='') — la gate appelante retentera."""
    try:
        return subprocess.run(  # noqa: S603 — vm/command contrôlés par le chemin codé
            ["limactl", "shell", vm, *command],
            check=False,
            capture_output=True,
            text=True,
            timeout=_VM_EXEC_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, returncode=124, stdout="", stderr="timeout")


def vip_healthz(vip: str, from_vm: str, *, vm_exec=_vm_exec) -> bool:
    """True si la VIP de l'API répond `ok` à /healthz, vue DEPUIS un CP (`from_vm`)
    — preuve qu'elle est annoncée en L2, pas juste localement."""
    res = vm_exec(
        from_vm,
        ["sh", "-c", f"curl -sk --max-time 5 https://{vip}:6443/healthz 2>/dev/null"],
    )
    return res.returncode == 0 and res.stdout.strip() == "ok"


# Args etcdctl (certs du static pod). PAS de `ETCDCTL_API=3` ni `sh -c` : on
# exécute etcdctl DIRECTEMENT dans le conteneur etcd (voir etcd_health_output) ;
# l'image etcd n'a ni `env` ni `sh`, et etcdctl ≥ 3.4 utilise l'API v3 par défaut
# (même contrainte que etcd-snapshot.sh.j2).
_ETCDCTL_ARGS = [
    "etcdctl",
    "--endpoints=https://127.0.0.1:2379",
    "--cacert=/etc/kubernetes/pki/etcd/ca.crt",
    "--cert=/etc/kubernetes/pki/etcd/server.crt",
    "--key=/etc/kubernetes/pki/etcd/server.key",
    "endpoint",
    "health",
    "--cluster",
]


def _etcd_cid(cp: str, *, vm_exec) -> str:
    """CID du conteneur etcd (static pod kubeadm) sur CP, via crictl. Vide si
    introuvable (control-plane pas encore sain)."""
    res = vm_exec(cp, ["sudo", "crictl", "ps", "--state", "Running", "--name", "^etcd$", "-q"])
    cid = (res.stdout or "").strip().splitlines()
    return cid[0] if cid else ""


def etcd_health_output(cp: str, *, vm_exec=_vm_exec) -> str:
    """Sortie de `etcdctl endpoint health --cluster`, exécuté DANS le conteneur
    etcd (`crictl exec`) — etcdctl n'est pas sur l'hôte (même approche que le
    RUNBOOK/etcd-snapshot). Vide si le conteneur etcd n'est pas encore là (la gate
    retentera). etcdctl écrit la santé sur STDERR → on fusionne stdout+stderr."""
    cid = _etcd_cid(cp, vm_exec=vm_exec)
    if not cid:
        return ""
    res = vm_exec(cp, ["sudo", "crictl", "exec", cid, *_ETCDCTL_ARGS])
    return (res.stdout or "") + (res.stderr or "")
