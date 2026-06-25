"""LOT 9 — la HA `ha-3cp` branchée AU MOTEUR de chemin (nestor/path.py).

Le montage HA (`run_ha_3cp`/`bootstrap_primary`) est désormais FUSIONNÉ dans
`nestor/path.py` (ex-`nestor/ha.py`, dissous : un seul moteur) ; ses sondes pures
vivent dans `nestor/ha_probes.py`, ses gates dans `nestor/gates.py`.

Prouve, en PUR/INJECTÉ (aucun banc, aucun cluster, aucun ansible-runner réel), que :

  1. le chemin `ha-3cp` est une SÉQUENCE Python comme les autres : le moteur
     `path.run_path` délègue la phase `ha` à un callback DÉDIÉ qui porte
     `path.run_ha_3cp` — plus un sous-process bash qui rappelle Python (fin de la
     circularité `:1650`, ADR 0097 §2.b — exception nommée LEVÉE) ;
  2. via le moteur, `run_ha_3cp` enchaîne bien `bootstrap_primary` → promotion ×2 avec
     un `gate_etcd` ENTRE chaque (la fenêtre N fragile, #250) — tout stubé ;
  3. le DOUBLE GESTE de `phase_ha_cni` est COUVERT : `run_cni` (Cilium, artefact bash)
     PUIS `fetch_kubeconfig` (sed-rewrite admin.conf, transport) sont LES DEUX appelés,
     DANS L'ORDRE — sinon le pont `ha-cni` resterait appelé pour le kubeconfig et la
     circularité résiduelle subsisterait (ADR 0097 §2.b).

⚠️  HONNÊTETÉ (ADR 0034) : la PREUVE réelle du montage HA (VIP qui bascule, quorum etcd
qui survit à 1 panne, changed=0) reste un RUN BANC from-scratch consigné — ces tests ne
couvrent QUE la logique d'enchaînement Python. Voir `nestor/path.py:_BANC_TODO`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import path  # noqa: E402

_TOPO = object()


class _Launch:
    """Stub de launch_phase (← runner) : enregistre (playbook, kubeconfig_path, limit).
    Renvoie un succès (objet à .rc/.status, comme RunResult)."""

    class _Res:
        def __init__(self, rc=0, status="successful"):
            self.rc = rc
            self.status = status

    def __init__(self):
        self.calls = []

    def __call__(self, playbook, extravars, limit=None):
        self.calls.append((playbook, extravars.get("kube_vip_kubeconfig_path"), limit))
        return self._Res()


def _noop(*_a, **_k):
    return None


def _ha_callback(spy, *, nodes=("cp1", "cp2", "cp3")):
    """Construit le callback `ha` que la façade injectera dans `run_path` : il câble
    `path.run_ha_3cp` avec des I/O STUBÉES, et trace les gestes dans `spy`. Renvoie
    `0` si le montage HA est `built` (parité façade : rc 0 = ok pour `_run_amont`)."""

    def run_cni():
        spy["order"].append("run_cni")

    def fetch_kubeconfig():
        spy["order"].append("fetch_kubeconfig")

    def etcd_output(_cp):
        # Quorum sain à chaque gate (assez de "is healthy" pour `expected` membres).
        return "\n".join("x is healthy" for _ in range(3))

    def ha_phase(_phase):
        result = path.run_ha_3cp(
            list(nodes),
            "10.0.0.1",
            "10.0.0.40",
            "eth0",
            launch=spy["launch"],
            run_cni=run_cni,
            fetch_kubeconfig=fetch_kubeconfig,
            set_inventory=lambda hosts: spy["inventory"].append(list(hosts)),
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 3,
            etcd_output=etcd_output,
            sleep=_noop,
        )
        spy["result"] = result
        return 0 if result.built else 1

    return ha_phase


def _harness_ha(spy):
    """Faisceau de callbacks pour `run_path` sur le chemin `ha-3cp` : séquence
    `up → ha → storage-simple`, garde/launch/gate inertes. `ha` est le SEUL callback
    qui agit (il porte run_ha_3cp). `up` route vers un provision trivial."""
    log = {"launch": [], "gate": [], "amont": []}

    def sequence(topo, target):
        assert topo is _TOPO
        assert target == "ha-3cp"
        return ["up", "ha", "storage-simple"]

    def launch(phase):
        log["launch"].append(phase)

        class _Ok:
            ok = True
            verdict = "ok"
            message = ""

        return _Ok()

    def gate(phase):
        log["gate"].append(phase)
        return True

    def provision(phase):
        log["amont"].append(("provision", phase))
        return 0

    kwargs = dict(
        sequence=sequence,
        launch=launch,
        gate=gate,
        assert_safe=lambda _p: None,
        provision=provision,
        ha=_ha_callback(spy),
    )
    return kwargs, log


def _new_spy():
    return {"order": [], "inventory": [], "launch": _Launch(), "result": None}


class HaBranchedIntoEngine(unittest.TestCase):
    """1+2 — `ha-3cp` est une séquence Python : le moteur délègue `ha` à run_ha_3cp."""

    def test_ha_phase_routes_to_dedicated_callback(self):
        # La phase `ha` passe par le callback amont DÉDIÉ, PAS par launch (ce n'est pas
        # un play unitaire) — frontière _NON_ANSIBLE_AMONT respectée.
        self.assertIn("ha", path._NON_ANSIBLE_AMONT)
        spy = _new_spy()
        kwargs, log = _harness_ha(spy)
        result = path.run_path(_TOPO, "ha-3cp", **kwargs)
        self.assertTrue(result.built, [s.detail for s in result.steps if not s.ok])
        self.assertNotIn("ha", log["launch"])  # ha ≠ launch_phase
        # La phase `ha` figure dans les étapes du chemin (rc=0 du run_ha_3cp).
        self.assertTrue(any(s.name == "ha" and s.ok for s in result.steps))

    def test_engine_runs_full_ha_sequence_with_etcd_gates_between_promotions(self):
        # Via le moteur, run_ha_3cp enchaîne bootstrap primaire → promotion cp2 → cp3,
        # chaque join ciblé par --limit (le bug : sans limit ça rebootstrappait).
        spy = _new_spy()
        kwargs, _ = _harness_ha(spy)
        path.run_path(_TOPO, "ha-3cp", **kwargs)
        calls = spy["launch"].calls
        joins = [(p, limit) for p, _, limit in calls if p == "join-control-plane.yaml"]
        self.assertEqual([limit for _, limit in joins], ["cp2", "cp3"])
        # L'inventaire est réécrit avant chaque promotion (primaire en tête).
        self.assertEqual(spy["inventory"], [["cp1", "cp2"], ["cp1", "cp2", "cp3"]])
        # Étape quorum final présente dans le HaResult sous-jacent.
        self.assertTrue(any(s.name == "quorum final" for s in spy["result"].steps))

    def test_degraded_etcd_fails_the_path(self):
        # Quorum etcd dégradé → run_ha_3cp NON built → callback rc=1 → PathError (la
        # phase amont `ha` échoue, fail-fast comme les autres phases du moteur).
        spy = _new_spy()
        kwargs, _ = _harness_ha(spy)

        def ha_degraded(_phase):
            result = path.run_ha_3cp(
                ["cp1", "cp2", "cp3"],
                "10.0.0.1",
                "10.0.0.40",
                "eth0",
                launch=spy["launch"],
                run_cni=_noop,
                fetch_kubeconfig=_noop,
                set_inventory=_noop,
                vip_responds=lambda *_a, **_k: True,
                ready_count=lambda: 1,
                etcd_output=lambda _cp: "a is healthy\nb is unhealthy",
                sleep=_noop,
            )
            return 0 if result.built else 1

        kwargs["ha"] = ha_degraded
        with self.assertRaises(path.PathError):
            path.run_path(_TOPO, "ha-3cp", **kwargs)


class DoubleGesteHaCniCovered(unittest.TestCase):
    """3 — le DOUBLE GESTE de phase_ha_cni couvert : run_cni PUIS fetch_kubeconfig."""

    def test_both_gestes_called_in_order(self):
        # Via le moteur, le bootstrap primaire appelle run_cni PUIS fetch_kubeconfig — la
        # façade couvre LES DEUX, donc le pont `ha-cni` n'est plus appelé pour le
        # kubeconfig (fin de la circularité résiduelle, ADR 0097 §2.b).
        spy = _new_spy()
        kwargs, _ = _harness_ha(spy)
        path.run_path(_TOPO, "ha-3cp", **kwargs)
        self.assertIn("run_cni", spy["order"])
        self.assertIn("fetch_kubeconfig", spy["order"])
        # ORDRE : run_cni AVANT fetch_kubeconfig (le kubeconfig n'est valide qu'avec la
        # CNI posée — les nœuds ne deviennent Ready qu'après Cilium).
        self.assertLess(spy["order"].index("run_cni"), spy["order"].index("fetch_kubeconfig"))

    def test_fetch_kubeconfig_is_a_distinct_callback_from_run_cni(self):
        # Le 2ᵉ geste est un callback SÉPARÉ (pas fondu dans run_cni) — c'est ce qui
        # permet à la façade de NE PLUS rappeler `ha-cni` pour le kubeconfig.
        cni_calls, kube_calls = [], []
        path.bootstrap_primary(
            "10.0.0.1",
            "10.0.0.40",
            "eth0",
            launch=_Launch(),
            run_cni=lambda: cni_calls.append(1),
            fetch_kubeconfig=lambda: kube_calls.append(1),
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 1,
            sleep=_noop,
        )
        self.assertEqual((cni_calls, kube_calls), ([1], [1]))

    def test_fetch_kubeconfig_defaults_to_noop_for_legacy_callers(self):
        # Rétrocompat : un appelant legacy (cmd_ha_3cp rappelle encore `ha-cni`, qui fait
        # les deux gestes en bash) n'a pas à fournir fetch_kubeconfig — défaut no-op.
        steps = path.bootstrap_primary(
            "10.0.0.1",
            "10.0.0.40",
            "eth0",
            launch=_Launch(),
            run_cni=_noop,
            vip_responds=lambda *_a, **_k: True,
            ready_count=lambda: 1,
            sleep=_noop,
        )
        self.assertTrue(all(s.ok for s in steps))


class CircularityNote(unittest.TestCase):
    """Le _BANC_TODO de path.py DÉCLARE explicitement le retrait des rappels ha-3cp/
    ha-cni (anti-oubli) — la bascule réelle attend la preuve banc (honnêteté ADR 0034)."""

    def test_banc_todo_mentions_ha_cni_retraction(self):
        todo = path.banc_todo()
        self.assertTrue(any("ha-cni" in t for t in todo))
        self.assertTrue(any("ha-3cp" in t for t in todo))


if __name__ == "__main__":
    unittest.main()
