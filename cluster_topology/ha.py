"""Orchestration du control-plane HA `ha-3cp` (ADR 0047/0055, #250) EN PYTHON.

Pourquoi Python et non bash : « Python sait parler Ansible » (ADR 0063) — cette
orchestration LANCE des playbooks via `runner.launch_phase` (ansible-runner),
exactement comme la boucle `next --apply`, au lieu d'enchaîner des
`ansible-playbook` en sous-process. La séquence ci-dessous a été PROUVÉE d'abord
en bash (les bugs d'amorçage HA — super-admin→admin, VIP, cluster-api, gates —
y ont été débusqués) ; ce module en est le portage fidèle, testé sans banc.

Trois couches (patron roundtrip.py / runner.py / smoke.py) :
  - FONCTIONS PURES (cp_join_order, classify_etcd_health, *_extravars) : aucun
    I/O, testées par pytest sur des fixtures ;
  - COUCHE D'EXÉCUTION ISOLÉE : `_launch` (→ runner), `_vm_exec` (limactl),
    `_nodes_ready_count` (kubectl), gates — toutes INJECTABLES ;
  - ORCHESTRATION : `bootstrap_primary`, `promote_control_plane`, `run_ha_3cp`
    composent les deux, et prennent leurs dépendances en paramètres (stub en test).

Ansible reste le moteur de convergence (ADR 0056 §7) ; ce module SÉQUENCE et
GATE, il ne réimplémente aucune idempotence (ADR 0063 G1). La PREUVE réelle est
un run de banc consigné (ADR 0034/0052, #250 — le code ne vaut pas preuve seul).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


class HaError(RuntimeError):
    """Séquence HA interrompue : gate non franchie, playbook en échec, VIP/quorum KO."""


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


# ── Couche d'exécution ISOLÉE (I/O, injectable) ──────────────────────────────


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


# ── ORCHESTRATION (compose pur + I/O ; dépendances injectées) ────────────────


@dataclass
class HaStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class HaResult:
    """Verdict du montage ha-3cp. `built` = toutes les étapes ont réussi."""

    vip: str
    steps: list[HaStep] = field(default_factory=list)

    @property
    def built(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)


# Playbooks du bootstrap primaire, dans l'ORDRE prouvé. kube-vip est lancé deux
# fois (amorçage super-admin.conf AVANT l'init k8s≥1.29, puis bascule admin.conf).
_PRE_INIT_PLAYBOOKS = ("checks", "cri", "kubeadm", "control-planes")


def gate_vip(vip: str, from_vm: str, *, vip_responds, retries: int = 30, sleep) -> None:
    """Attend que la VIP réponde (kube-vip (ré)acquiert le lease après un re-render
    du manifeste). Lève HaError si la VIP ne monte pas — « détection fiable ou refus
    franc » (la leçon des gates du banc)."""
    for _ in range(retries):
        if vip_responds(vip, from_vm):
            return
        sleep(4)
    raise HaError(f"la VIP {vip} ne répond pas (kube-vip n'a pas (ré)acquis la VIP ?)")


def gate_etcd(cp: str, expected: int, *, etcd_output, retries: int = 24, sleep) -> None:
    """Attend un quorum etcd sain à `expected` membres avant de promouvoir le CP
    suivant. Lève HaError si le quorum est dégradé (fail) ; patiente sur skip."""
    for _ in range(retries):
        statut, msg = classify_etcd_health(etcd_output(cp), expected)
        if statut == "ok":
            return
        if statut == "fail":
            raise HaError(f"gate etcd : {msg}")
        sleep(5)
    raise HaError(f"gate etcd : quorum à {expected} membres non atteint (timeout)")


def gate_nodes_ready(expected: int, *, ready_count, retries: int = 30, sleep) -> None:
    """Attend AU MOINS `expected` nœuds Ready (en HA les CP rejoignent un à un :
    le gate de chaque étape attend le compte à ce stade, pas les N finaux)."""
    for _ in range(retries):
        if ready_count() >= expected:
            return
        sleep(10)
    raise HaError(f"moins de {expected} nœud(s) Ready (timeout)")


def _check(launch, playbook: str, extravars: dict[str, str], label: str, limit=None) -> None:
    """Lance un playbook via `launch(playbook, extravars, limit=…)` et lève HaError
    si le run échoue. `launch` renvoie un objet exposant `rc`/`status`. `limit`
    restreint le play à un hôte (promotion d'UN CP à la fois)."""
    res = launch(playbook, extravars, limit=limit)
    if getattr(res, "rc", 1) != 0 or getattr(res, "status", "") != "successful":
        raise HaError(
            f"{label} : playbook {playbook} en échec "
            f"(rc={getattr(res, 'rc', '?')}, status={getattr(res, 'status', '?')})"
        )


def bootstrap_primary(
    cp_ip: str,
    vip: str,
    vip_iface: str,
    *,
    launch,
    run_cni,
    vip_responds,
    ready_count,
    sleep,
) -> list[HaStep]:
    """Monte le CP PRIMAIRE derrière la VIP (séquence prouvée). `launch(playbook,
    extravars)` lance UN playbook (← runner.launch_phase partiellement appliqué) ;
    `run_cni()` pose Cilium ; les gates (vip_responds/ready_count) et `sleep` sont
    injectés. Renvoie les étapes franchies ; lève HaError au premier échec."""
    steps: list[HaStep] = []
    ev = bootstrap_extravars(cp_ip, vip, vip_iface)

    # 1. Pré-init : checks → cri → kubeadm → control-planes.
    for pb in _PRE_INIT_PLAYBOOKS:
        _check(launch, f"{pb}.yaml", ev, "bootstrap-ha")
    steps.append(HaStep("pré-init", True, " → ".join(_PRE_INIT_PLAYBOOKS)))

    # 2. kube-vip AVANT l'init, en super-admin.conf (amorçage k8s ≥ 1.29).
    _check(
        launch,
        "kube-vip.yaml",
        {**ev, "kube_vip_kubeconfig_path": "/etc/kubernetes/super-admin.conf"},
        "kube-vip (super-admin)",
    )
    # 3. Init du CP primaire (controlPlaneEndpoint = la VIP, via kube-vip).
    _check(launch, "initialisation.yaml", ev, "kubeadm init via VIP")
    # 4. Bascule kube-vip sur admin.conf (régime permanent).
    _check(
        launch,
        "kube-vip.yaml",
        {**ev, "kube_vip_kubeconfig_path": "/etc/kubernetes/admin.conf"},
        "kube-vip (admin)",
    )
    steps.append(HaStep("init via VIP", True, "kube-vip super-admin→admin, init OK"))

    # 4b. GATE VIP : la bascule recrée le pod kube-vip → attendre que la VIP réponde
    # avant la CNI (sinon l'apply des CRDs via la VIP court après une VIP retombée).
    gate_vip(vip, "cp1", vip_responds=vip_responds, sleep=sleep)
    steps.append(HaStep("gate VIP", True, f"VIP {vip} joignable"))

    # 5. CNI (Cilium).
    run_cni()
    gate_nodes_ready(1, ready_count=ready_count, sleep=sleep)
    steps.append(HaStep("CNI + primaire Ready", True, "1 CP Ready derrière la VIP"))
    return steps


def promote_control_plane(
    cp: str,
    member_index: int,
    control_hosts: list[str],
    vip: str,
    vip_iface: str,
    *,
    launch,
    set_inventory,
    ready_count,
    sleep,
) -> HaStep:
    """Promeut UN CP additionnel : ajoute `cp` au groupe control de l'inventaire,
    pose kube-vip (admin.conf) sur lui, puis join --control-plane — les deux
    `--limit cp` (le bootstrap ne mettait que le primaire dans control). Le rôle
    de join lit le PRIMAIRE via groups['control'][0] → il doit rester en tête.
    `member_index` = nombre de CP membres APRÈS cette promotion (gate Ready)."""
    # control = primaire + déjà promus + ce cp (primaire en tête, ADR du rôle).
    set_inventory(control_hosts)
    ev = join_extravars(vip, vip_iface)
    _check(
        launch,
        "kube-vip.yaml",
        {**ev, "kube_vip_kubeconfig_path": "/etc/kubernetes/admin.conf"},
        f"kube-vip {cp}",
        limit=cp,
    )
    _check(launch, "join-control-plane.yaml", ev, f"join {cp}", limit=cp)
    gate_nodes_ready(member_index, ready_count=ready_count, sleep=sleep)
    return HaStep(f"promotion {cp}", True, f"{member_index} CP membres")


def run_ha_3cp(
    nodes: list[str],
    cp_ip: str,
    vip: str,
    vip_iface: str,
    *,
    launch,
    run_cni,
    set_inventory,
    vip_responds=vip_healthz,
    ready_count,
    etcd_output=etcd_health_output,
    sleep,
) -> HaResult:
    """Monte la topologie ha-3cp : bootstrap du primaire + promotion des CP
    additionnels un à un (gate etcd entre chaque). `set_inventory(control_hosts)`
    réécrit l'inventaire (le primaire reste en tête — le rôle de join lit
    groups['control'][0]). Toutes les I/O sont injectées → testable sans banc."""
    result = HaResult(vip=vip)
    primary = nodes[0]
    try:
        result.steps.extend(
            bootstrap_primary(
                cp_ip,
                vip,
                vip_iface,
                launch=launch,
                run_cni=run_cni,
                vip_responds=vip_responds,
                ready_count=ready_count,
                sleep=sleep,
            )
        )
        # Promotion des CP additionnels, un à un, gate etcd avant chaque.
        members = 1  # le primaire
        control_hosts = [primary]
        for cp in cp_join_order(nodes):
            gate_etcd(primary, members, etcd_output=etcd_output, sleep=sleep)
            members += 1
            control_hosts.append(cp)
            result.steps.append(
                promote_control_plane(
                    cp,
                    members,
                    list(control_hosts),
                    vip,
                    vip_iface,
                    launch=launch,
                    set_inventory=set_inventory,
                    ready_count=ready_count,
                    sleep=sleep,
                )
            )
        gate_etcd(primary, members, etcd_output=etcd_output, sleep=sleep)  # quorum final
        result.steps.append(HaStep("quorum final", True, f"{members} CP membres, quorum sain"))
    except HaError as exc:
        result.steps.append(HaStep("échec", False, str(exc)))
    return result
