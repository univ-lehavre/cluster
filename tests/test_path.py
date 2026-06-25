"""Tests du moteur de chemin (nestor/path.py) — LOT 6 refonte nestor (ADR 0097).

unittest stdlib, I/O TOTALEMENT INJECTÉE (launch/gate/assert_safe/provision/bootstrap
stubés) — AUCUN banc, AUCUN cluster, AUCUN ansible-runner réel, AUCUN limactl/kubectl.
Ces tests prouvent la LOGIQUE d'orchestration : l'ordre des phases, que la garde
d'isolation est traversée à CHAQUE phase (invariant de boucle, PAS une fois), que le
gate est appelé APRÈS chaque montage, qu'une gate KO arrête la séquence, et que le
montage applicatif passe par le double-passage idempotent.

⚠️  HONNÊTETÉ (ADR 0034) : la PREUVE réelle du montage (provisioning VM, gates sur
cluster live, idempotence changed=0) reste un RUN BANC from-scratch consigné — ces
tests ne couvrent PAS le banc, seulement la logique d'enchaînement. Voir
`nestor/path.py:_BANC_TODO` pour la frontière code-écrit / preuve-banc-manquante.
"""

import dataclasses
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import path  # noqa: E402

# Séquence-jouet : une phase amont (bootstrap) + deux couches applicatives. Injectée
# via `sequence` → on N'IMPORTE PAS expected_phase_sequence (test PUR, indépendant du
# graphe/de la topologie). `topo` est un sentinelle opaque (le moteur ne l'inspecte pas,
# il le passe juste à `sequence`).
_SEQ = ["bootstrap", "storage-simple", "monitoring"]
_TOPO = object()


class _IdemOk:
    """Verdict d'un launch_phase_idempotent STUBÉ : montage + rejeu changed=0 (ok)."""

    def __init__(self, ok=True, message=""):
        self.ok = ok
        self.verdict = "ok" if ok else "fail"
        self.message = message


def _harness(
    *,
    seq=None,
    launch_ok=True,
    gate_ok=True,
    provision_rc=0,
    bootstrap_rc=0,
    assert_raises_on=None,
    record_sink=None,
):
    """Construit un faisceau de callbacks STUBÉS + des journaux d'appels.

    Renvoie `(kwargs, log)` où `log` est un dict de listes traçant l'ordre des appels
    (gardes, launches, gates, amont) — c'est sur lui qu'on assoit les assertions."""
    seq = list(seq if seq is not None else _SEQ)
    log = {"order": [], "assert": [], "launch": [], "gate": [], "amont": []}

    def sequence(topo, target):
        assert topo is _TOPO
        return seq

    def assert_safe(phase):
        log["order"].append(("assert", phase))
        log["assert"].append(phase)
        if assert_raises_on is not None and phase == assert_raises_on:
            # La garde façade lève _UsageError (HORS hiérarchie PathError) — on simule
            # un type quelconque pour vérifier que run_path le mappe en IsolationRefused.
            raise RuntimeError(f"REFUS isolation pour {phase}")

    def launch(phase):
        log["order"].append(("launch", phase))
        log["launch"].append(phase)
        return _IdemOk(ok=launch_ok)

    def gate(phase):
        log["order"].append(("gate", phase))
        log["gate"].append(phase)
        return gate_ok

    def provision(phase):
        log["order"].append(("provision", phase))
        log["amont"].append(("provision", phase))
        return provision_rc

    def bootstrap(phase):
        log["order"].append(("bootstrap", phase))
        log["amont"].append(("bootstrap", phase))
        return bootstrap_rc

    def record(result):
        if record_sink is not None:
            record_sink.append(result)

    kwargs = dict(
        sequence=sequence,
        launch=launch,
        gate=gate,
        assert_safe=assert_safe,
        provision=provision,
        bootstrap=bootstrap,
        record=record,
    )
    return kwargs, log


class PathContextOwnsSharedState(unittest.TestCase):
    """ADR 0097 §5.a : path.py POSSÈDE l'état que run-phases.sh tenait en globales."""

    def test_defaults_match_runphases_globals(self):
        ctx = path.PathContext(cp="cp1")
        self.assertEqual(ctx.cp, "cp1")
        self.assertEqual(ctx.api_port, 6443)  # = run-phases.sh:90 API_PORT

    def test_context_is_immutable(self):
        ctx = path.PathContext(cp="cp1", kubeconfig_local="/w/kubeconfig", nodes=("cp1",))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ctx.cp = "node1"  # frozen dataclass → pas de mutation en cours de boucle


class SequenceOrder(unittest.TestCase):
    def test_phases_in_declared_order(self):
        kwargs, log = _harness()
        result = path.run_path(_TOPO, "layers", **kwargs)
        self.assertTrue(result.built)
        # bootstrap (amont) PUIS les deux couches applicatives, dans l'ordre.
        self.assertEqual([("bootstrap", "bootstrap")], log["amont"])
        self.assertEqual(["storage-simple", "monitoring"], log["launch"])

    def test_amont_uses_dedicated_callback_not_launch(self):
        # `bootstrap` ne passe PAS par launch (ce n'est pas un play unitaire) ; les
        # couches applicatives oui. Frontière _NON_ANSIBLE_AMONT respectée.
        kwargs, log = _harness(seq=["bootstrap", "storage-simple"])
        path.run_path(_TOPO, "layers", **kwargs)
        self.assertNotIn("bootstrap", log["launch"])
        self.assertEqual(log["launch"], ["storage-simple"])

    def test_up_routes_to_provision_callback(self):
        kwargs, log = _harness(seq=["up", "storage-simple"])
        path.run_path(_TOPO, "layers", **kwargs)
        self.assertEqual(log["amont"], [("provision", "up")])


class IsolationGuardIsLoopInvariant(unittest.TestCase):
    """ADR 0097 §1/§5.c — la garde est traversée à CHAQUE phase, PAS une seule fois."""

    def test_guard_traversed_once_per_phase(self):
        kwargs, log = _harness()
        path.run_path(_TOPO, "layers", **kwargs)
        # Une garde PAR phase de la séquence (3), dans l'ordre — invariant de boucle.
        self.assertEqual(log["assert"], _SEQ)

    def test_guard_runs_before_each_montage(self):
        # L'ordre global montre assert(phase) AVANT le montage de cette MÊME phase, à
        # chaque itération — jamais un seul assert en tête puis tout le reste.
        kwargs, log = _harness(seq=["storage-simple", "monitoring"])
        path.run_path(_TOPO, "layers", **kwargs)
        self.assertEqual(
            log["order"],
            [
                ("assert", "storage-simple"),
                ("launch", "storage-simple"),
                ("gate", "storage-simple"),
                ("assert", "monitoring"),
                ("launch", "monitoring"),
                ("gate", "monitoring"),
            ],
        )

    def test_guard_refusal_stops_before_touching_anything(self):
        # La garde REFUSE la 1re phase → IsolationRefused, AUCUN montage tenté (la prod
        # est protégée AVANT le moindre geste, faille ADR 0053).
        kwargs, log = _harness(seq=["storage-simple"], assert_raises_on="storage-simple")
        with self.assertRaises(path.IsolationRefused):
            path.run_path(_TOPO, "layers", **kwargs)
        self.assertEqual(log["launch"], [])
        self.assertEqual(log["gate"], [])

    def test_guard_refusal_midsequence_stops_there(self):
        # 1re phase OK, garde refuse la 2e → la 2e n'est PAS montée (re-traversée à
        # chaque phase : une exportation KUBECONFIG prod en cours de route est attrapée).
        kwargs, log = _harness(assert_raises_on="storage-simple")
        with self.assertRaises(path.IsolationRefused):
            path.run_path(_TOPO, "layers", **kwargs)
        # bootstrap monté, storage-simple refusé avant montage.
        self.assertEqual(log["amont"], [("bootstrap", "bootstrap")])
        self.assertNotIn("storage-simple", log["launch"])


class GateAfterEachLaunch(unittest.TestCase):
    def test_gate_called_after_each_phase(self):
        kwargs, log = _harness()
        path.run_path(_TOPO, "layers", **kwargs)
        # Gate appelée pour CHAQUE phase (amont incluse — _wait_layer_healthy rend True
        # pour une phase sans signal, parité topology.py).
        self.assertEqual(log["gate"], _SEQ)

    def test_failing_gate_stops_the_sequence(self):
        # Une gate KO sur la 1re phase applicative → PathError, la 2e n'est PAS montée.
        kwargs, log = _harness(gate_ok=False)
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "layers", **kwargs)
        # bootstrap monté+gaté(KO) → on s'arrête : storage-simple jamais lancé.
        self.assertEqual(log["launch"], [])
        self.assertEqual(log["gate"], ["bootstrap"])


class FailFast(unittest.TestCase):
    def test_failed_launch_raises_and_stops(self):
        kwargs, log = _harness(seq=["storage-simple", "monitoring"], launch_ok=False)
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "layers", **kwargs)
        # storage-simple tenté (KO) → monitoring jamais lancé (fail-fast comme `die`).
        self.assertEqual(log["launch"], ["storage-simple"])
        self.assertNotIn("monitoring", log["launch"])

    def test_failed_provision_raises(self):
        kwargs, _ = _harness(seq=["up"], provision_rc=1)
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "layers", **kwargs)

    def test_failed_bootstrap_raises(self):
        kwargs, _ = _harness(seq=["bootstrap"], bootstrap_rc=2)
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "layers", **kwargs)

    def test_missing_amont_callback_is_explicit_stub_error(self):
        # Callback amont absent (None) → PathError explicite (STUB à câbler), pas un
        # provisioning inventé. Le moteur SAIT qu'il faut `up`, refuse net sans cluster.
        kwargs, _ = _harness(seq=["up"])
        kwargs["provision"] = None
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "layers", **kwargs)


class IdempotenceVerified(unittest.TestCase):
    def test_launch_result_must_expose_ok(self):
        # Le moteur lit `.ok` du verdict (IdempotenceResult.ok = verdict 'ok', le
        # double-passage changed=0). Un montage `ok=True` → built ; sinon fail-fast.
        kwargs, _ = _harness()
        result = path.run_path(_TOPO, "layers", **kwargs)
        self.assertTrue(result.built)
        self.assertTrue(all(s.ok for s in result.steps))

    def test_idempotence_fail_verdict_stops(self):
        # Un verdict d'idempotence non-ok (changed>0 au rejeu) → fail-fast.
        kwargs, _ = _harness(seq=["storage-simple"], launch_ok=False)
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "layers", **kwargs)


class RecordOnlyOnSuccess(unittest.TestCase):
    def test_successful_run_is_recorded(self):
        sink = []
        kwargs, _ = _harness(record_sink=sink)
        path.run_path(_TOPO, "layers", **kwargs)
        self.assertEqual(len(sink), 1)  # parité record_full_run : run from-scratch consigné

    def test_failed_run_is_not_recorded(self):
        # Un run qui échoue ne doit JAMAIS être consigné comme preuve (record_if_fresh).
        sink = []
        kwargs, _ = _harness(launch_ok=False, record_sink=sink)
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "layers", **kwargs)
        self.assertEqual(sink, [])

    def test_record_optional(self):
        # `record=None` (cas test) : pas de consignation, pas d'erreur.
        kwargs, _ = _harness()
        kwargs["record"] = None
        result = path.run_path(_TOPO, "layers", **kwargs)
        self.assertTrue(result.built)


class BancFrontierIsDeclared(unittest.TestCase):
    """Honnêteté ADR 0034 : la frontière code-écrit / preuve-banc est DÉCLARÉE."""

    def test_banc_todo_nonempty(self):
        todo = path.banc_todo()
        self.assertTrue(todo)
        # Mentionne explicitement la preuve banc (anti-oubli avant merge).
        self.assertTrue(any("banc" in t.lower() for t in todo))


# ── Montage HA `ha-3cp` (ex-tests/test_ha.py, migrés ICI après fusion de nestor/ha.py
#    dans path.py). Pur/injecté : `launch` (← runner.launch_phase), `run_cni`, les gates
#    et `sleep` sont stubés — AUCUN banc, AUCUN cluster, AUCUN ansible-runner réel. On
#    valide la SÉQUENCE des playbooks, l'ordre des gates (etcd AVANT chaque promotion), le
#    faisceau `-e` (subtilité cluster-api↔VIP), et les échecs. La PREUVE réelle (VIP qui
#    bascule, survie à 1 panne) reste un run de banc consigné (ADR 0034/0052, #250).


class _HaLaunch:
    """Stub de launch_phase : enregistre les (playbook, kubeconfig_path, limit)
    lancés ; renvoie un succès, ou un échec ciblé sur un playbook donné."""

    class _Res:
        def __init__(self, rc, status):
            self.rc = rc
            self.status = status

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, playbook, extravars, limit=None):
        self.calls.append((playbook, extravars.get("kube_vip_kubeconfig_path"), limit))
        if self.fail_on and playbook == self.fail_on:
            return self._Res(1, "failed")
        return self._Res(0, "successful")


def _ha_noop(*_a, **_k):
    return None


class BootstrapPrimary(unittest.TestCase):
    def _run(self, launch, **over):
        kw = dict(
            launch=launch,
            run_cni=_ha_noop,
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 1,
            sleep=_ha_noop,
        )
        kw.update(over)
        return path.bootstrap_primary("10.0.0.1", "10.0.0.40", "eth0", **kw)

    def test_sequence_order_and_kube_vip_pivot(self):
        launch = _HaLaunch()
        self._run(launch)
        playbooks = [p for p, _, _ in launch.calls]
        # Ordre prouvé : pré-init → kube-vip(super-admin) → init → kube-vip(admin).
        self.assertEqual(
            playbooks,
            [
                "checks.yaml",
                "cri.yaml",
                "kubeadm.yaml",
                "control-planes.yaml",
                "kube-vip.yaml",
                "initialisation.yaml",
                "kube-vip.yaml",
            ],
        )
        # La bascule super-admin → admin (le piège k8s ≥ 1.29).
        kube_vip_confs = [c for p, c, _ in launch.calls if p == "kube-vip.yaml"]
        self.assertEqual(
            kube_vip_confs,
            ["/etc/kubernetes/super-admin.conf", "/etc/kubernetes/admin.conf"],
        )

    def test_init_failure_raises(self):
        with self.assertRaises(path.HaError):
            self._run(_HaLaunch(fail_on="initialisation.yaml"))

    def test_vip_gate_failure_raises(self):
        # La gate VIP (gates.gate_vip) lève GateError ; la séquence HA l'abort en HaError
        # à l'intérieur de bootstrap_primary → on attend une exception (la fusion catch
        # (HaError, GateError) côté run_ha_3cp ; ici bootstrap_primary propage GateError).
        from nestor.gates import GateError

        with self.assertRaises((path.HaError, GateError)):
            self._run(_HaLaunch(), vip_responds=lambda *_a, **_k: False)


class RunHa3cp(unittest.TestCase):
    def _etcd_healthy(self, n):
        return lambda _cp: "\n".join("x is healthy" for _ in range(n))

    def test_full_build_promotes_two_cps_with_etcd_gates(self):
        launch = _HaLaunch()
        # ready_count croît : assez pour passer toutes les gates.
        res = path.run_ha_3cp(
            ["cp1", "cp2", "cp3"],
            "10.0.0.1",
            "10.0.0.40",
            "eth0",
            launch=launch,
            run_cni=_ha_noop,
            set_inventory=_ha_noop,
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 3,
            etcd_output=self._etcd_healthy(3),
            sleep=_ha_noop,
        )
        self.assertTrue(res.built, [s.detail for s in res.steps if not s.ok])
        # Les deux CP additionnels sont promus (join-control-plane lancé 2×).
        joins = [(p, limit) for p, _, limit in launch.calls if p == "join-control-plane.yaml"]
        self.assertEqual(len(joins), 2)
        # Chaque join cible UN CP via --limit (le bug : sans limit, ça reciblait le
        # primaire et rebootstrappait au lieu de promouvoir cp2/cp3).
        self.assertEqual([limit for _, limit in joins], ["cp2", "cp3"])
        # Étape quorum final présente.
        self.assertTrue(any(s.name == "quorum final" for s in res.steps))

    def test_degraded_etcd_aborts_before_promotion(self):
        launch = _HaLaunch()
        res = path.run_ha_3cp(
            ["cp1", "cp2", "cp3"],
            "10.0.0.1",
            "10.0.0.40",
            "eth0",
            launch=launch,
            run_cni=_ha_noop,
            set_inventory=_ha_noop,
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 1,
            etcd_output=lambda _cp: "a is healthy\nb is unhealthy",  # quorum dégradé
            sleep=_ha_noop,
        )
        self.assertFalse(res.built)
        # Aucune promotion lancée (la gate etcd a coupé avant).
        joins = [p for p, _, _ in launch.calls if p == "join-control-plane.yaml"]
        self.assertEqual(joins, [])
        self.assertEqual(res.steps[-1].name, "échec")


if __name__ == "__main__":
    unittest.main()
