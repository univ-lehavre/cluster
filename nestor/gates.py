"""Gates d'INFRA en Python : attendre une condition k8s (PVC Bound, nœuds Ready, OSD).

Portage des gates bash (gate_test_pvc, nodes_ready_all, osds_up) vers Python, sur le
moule du montage HA : la LOGIQUE (boucle d'attente bornée + verdict) est PURE et testable ;
la lecture d'état k8s est INJECTÉE (la façade la branche sur le client `kubernetes`
NATIF — objets typés, `pvc.status.phase`, `list_node()` — pas de grep de `kubectl`).

Ce N'EST PAS de la convergence (on ne RÉPARE rien) : on ATTEND qu'une condition posée
par Ansible/le provisioning se réalise, dans une fenêtre bornée, puis on tranche
ok/timeout. Les boucles sont finies (retries × sleep) — jamais d'attente infinie.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass

from nestor.ha_probes import classify_etcd_health, etcd_health_output, vip_healthz


class GateError(RuntimeError):
    """Une gate n'a pas été satisfaite dans la fenêtre d'attente (timeout)."""


@dataclass(frozen=True)
class GateResult:
    ok: bool
    detail: str


def _wait_until(
    predicate,
    describe,
    *,
    retries: int,
    sleep,
) -> GateResult:
    """Boucle d'attente BORNÉE : appelle `predicate()` jusqu'à True ou épuisement.

    `predicate() -> bool` (la condition), `describe() -> str` (état courant lisible
    pour le message). `retries` tentatives espacées de `sleep` (injecté → tests sans
    attente réelle). Renvoie GateResult(ok) ; ne lève pas (l'appelant décide)."""
    for _ in range(max(1, retries)):
        if predicate():
            return GateResult(True, describe())
        sleep(0)  # l'intervalle réel est porté par la façade ; en test sleep=lambda _:None
    return GateResult(False, f"timeout — {describe()}")


def gate_pvc_bound(
    namespace: str,
    name: str,
    *,
    read_phase,
    retries: int = 30,
    sleep=_time.sleep,
) -> GateResult:
    """Attend qu'un PVC soit `Bound`. `read_phase(ns, name) -> str | None` lit la phase
    (façade : client.read_namespaced_persistent_volume_claim(...).status.phase)."""

    def ok():
        return read_phase(namespace, name) == "Bound"

    def desc():
        return f"PVC {namespace}/{name} phase={read_phase(namespace, name)!r}"

    return _wait_until(ok, desc, retries=retries, sleep=sleep)


def gate_nodes_ready(
    expected: int,
    *,
    ready_count,
    retries: int = 30,
    sleep=_time.sleep,
) -> GateResult:
    """Attend AU MOINS `expected` nœuds Ready. `ready_count() -> int` (façade :
    compte des Node dont une condition Ready=True via list_node())."""

    def ok():
        return ready_count() >= expected

    def desc():
        return f"{ready_count()}/{expected} nœud(s) Ready"

    return _wait_until(ok, desc, retries=retries, sleep=sleep)


def gate_osds_up(
    expected: int,
    *,
    osd_up_count,
    retries: int = 30,
    sleep=_time.sleep,
) -> GateResult:
    """Attend `expected` OSD Ceph `up`. `osd_up_count() -> int` (façade : parse de
    `ceph osd stat` via le toolbox, ou l'API Rook). Gate du backend Ceph."""

    def ok():
        return osd_up_count() == expected

    def desc():
        return f"{osd_up_count()}/{expected} OSD up"

    return _wait_until(ok, desc, retries=retries, sleep=sleep)


# ── Gates HA `ha-3cp` (RAISE-on-failure) ─────────────────────────────────────
# Les gates HA diffèrent des gates d'infra ci-dessus : elles LÈVENT (GateError) au
# lieu de rendre un GateResult, car la séquence de promotion (nestor.path.run_ha_3cp)
# est fail-fast — une VIP qui ne monte pas ou un quorum dégradé DOIT couper le montage
# sur place (« détection fiable ou refus franc », leçon des gates du banc, #250). Elles
# vivent ici (et non dans path.py) pour tenir LE doublon résolu : `gate_nodes_ready` est
# UNIQUE (au-dessus) et les gates HA s'alignent sur sa maison. Elles consomment les
# sondes de `ha_probes` (vip_healthz/etcd) par défaut, injectables en test.


def gate_vip(vip: str, from_vm: str, *, vip_responds=vip_healthz, retries: int = 30, sleep) -> None:
    """Attend que la VIP réponde (kube-vip (ré)acquiert le lease après un re-render
    du manifeste). Lève GateError si la VIP ne monte pas — « détection fiable ou refus
    franc » (la leçon des gates du banc)."""
    for _ in range(retries):
        if vip_responds(vip, from_vm):
            return
        sleep(4)
    raise GateError(f"la VIP {vip} ne répond pas (kube-vip n'a pas (ré)acquis la VIP ?)")


def gate_etcd(
    cp: str, expected: int, *, etcd_output=etcd_health_output, retries: int = 24, sleep
) -> None:
    """Attend un quorum etcd sain à `expected` membres avant de promouvoir le CP
    suivant. Lève GateError si le quorum est dégradé (fail) ; patiente sur skip."""
    for _ in range(retries):
        statut, msg = classify_etcd_health(etcd_output(cp), expected)
        if statut == "ok":
            return
        if statut == "fail":
            raise GateError(f"gate etcd : {msg}")
        sleep(5)
    raise GateError(f"gate etcd : quorum à {expected} membres non atteint (timeout)")
