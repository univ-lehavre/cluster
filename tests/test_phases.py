"""Tests du mapping phase→montage (nestor/phases.py) — LOT 7 refonte nestor (ADR 0097).

unittest stdlib, PURS — AUCUN banc, AUCUN cluster, AUCUN ansible-runner/kubectl réel. Ces
tests prouvent la LOGIQUE du MAPPING : le mapping phase→playbook est COMPLET (toutes les
phases de la séquence des DEUX topologies ont une entrée), chaque phase déclenche le BON
playbook + la BONNE nature de gate, `dataops` déclenche AUSSI les harnais e2e (STUBÉS, qui
LÈVENT au lieu de verdir à tort), et la restriction des `-e` par phase est fidèle.

⚠️  HONNÊTETÉ (ADR 0034) : la PREUVE réelle du montage (playbooks réels, gates sur cluster
live, harnais e2e OpenLineage/egress, idempotence changed=0) reste un RUN BANC from-scratch
consigné — ces tests ne couvrent PAS le banc, seulement la table de mapping. Voir
`nestor/phases.py:_BANC_TODO` pour la frontière code-écrit / preuve-banc-manquante.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nestor import phases  # noqa: E402
from nestor.model import load_topology  # noqa: E402
from nestor.plan import expected_phase_sequence, phase_playbook  # noqa: E402
from nestor.profile import derive_run_params  # noqa: E402

# Les DEUX cas de stockage du dépôt (invariant 2 du plan : un lot vaut sur local-path ET
# Ceph). On dérive leurs séquences RÉELLES pour prouver la complétude du mapping. On vise
# les topologies *.example.yaml VERSIONNÉES (les banc.yaml/dirqual.yaml réels sont une
# config locale gitignorée, ADR 0023 — absente en CI) : socle.example (Ceph + profil
# dataops, séquence la plus large) et layers.example (local-path).
_REPO = os.path.join(os.path.dirname(__file__), "..")
_TOPO_FILES = (
    os.path.join(_REPO, "topologies", "layers.example.yaml"),  # local-path (≈ banc)
    os.path.join(_REPO, "topologies", "socle.example.yaml"),  # Ceph + dataops (≈ dirqual)
)
# Phases AMONT portées par path._run_amont (provisioning/socle), HORS table phases.py.
_AMONT = {"up", "bootstrap", "bootstrap-ha", "join-cp"}


def _all_sequence_phases() -> set[str]:
    """Union des phases des séquences attendues des DEUX topologies."""
    out: set[str] = set()
    for f in _TOPO_FILES:
        out |= set(expected_phase_sequence(load_topology(f)))
    return out


class MappingIsComplete(unittest.TestCase):
    """Toute phase de la séquence (hors amont) a un plan de montage — pas de trou."""

    def test_every_sequence_phase_has_a_plan(self):
        # Chaque phase des séquences réelles des deux topologies (hors amont) DOIT avoir
        # un plan — sinon run_path la routerait via `launch` sans savoir quoi lancer.
        missing = []
        for phase in _all_sequence_phases():
            if phase in _AMONT:
                continue
            if not phases.has_phase_plan(phase):
                missing.append(phase)
        self.assertEqual(missing, [], f"phases sans plan de montage : {missing}")

    def test_amont_phases_have_no_plan(self):
        # Les phases amont sont portées par path._run_amont, PAS par cette table : les
        # router via `launch` serait un bug → phase_plan lève pour elles.
        for phase in _AMONT:
            self.assertFalse(phases.has_phase_plan(phase))
            with self.assertRaises(phases.PhaseUnknownError):
                phases.phase_plan(phase)

    def test_unknown_phase_raises(self):
        with self.assertRaises(phases.PhaseUnknownError):
            phases.phase_plan("phase-inexistante")

    def test_all_platform_phases_are_planned(self):
        # all_platform_phases() = exactement les phases à playbook unitaire de la table.
        for phase in phases.all_platform_phases():
            plan = phases.phase_plan(phase)
            self.assertIsNotNone(plan.playbook, f"{phase} devrait avoir un playbook")


class PlaybookMatchesSource(unittest.TestCase):
    """Chaque phase déclenche le BON playbook (dérivé de la source unique PHASE_PLAYBOOK)."""

    def test_playbook_derives_from_plan_phase_playbook(self):
        # phases.py ne RE-saisit pas le chemin : il DÉRIVE de plan.phase_playbook (anti
        # double-source). On prouve l'égalité pour chaque phase plateforme.
        for phase in phases.all_platform_phases():
            self.assertEqual(phases.phase_plan(phase).playbook, phase_playbook(phase))

    def test_known_platform_playbooks(self):
        # Sentinelle explicite : un changement de chemin d'un play DOIT casser ce test
        # (alignement run-phases.sh / bootstrap/*.yaml).
        expected = {
            "storage-simple": "bootstrap/local-path.yaml",
            "metrics-server": "bootstrap/metrics-server.yaml",
            "ceph": "bootstrap/ceph-cluster.yaml",
            "sc": "bootstrap/ceph-storageclasses.yaml",
            "datalake": "bootstrap/ceph-datalake.yaml",
            "monitoring": "bootstrap/monitoring.yaml",
            "gitops": "bootstrap/gitops.yaml",
            "dataops": "bootstrap/dataops.yaml",
            "mlflow": "bootstrap/mlflow.yaml",
            "portal": "bootstrap/portal.yaml",
        }
        for phase, pb in expected.items():
            self.assertEqual(phases.phase_plan(phase).playbook, pb)


class GateKindMatchesSignal(unittest.TestCase):
    """La nature de gate de chaque phase dérive de graph.LAYER_SIGNAL (source unique)."""

    def test_ceph_crs_gate_on_status_phase(self):
        # RÉSERVE CRITIQUE (ADR 0097) : ceph/datalake gatent sur status.phase des CR Rook
        # (CephCluster/CephObjectStore), PAS sur readyReplicas d'un Deployment.
        self.assertEqual(phases.phase_plan("ceph").gate_kind, "cr-phase")
        self.assertEqual(phases.phase_plan("datalake").gate_kind, "cr-phase")

    def test_sc_gate_on_presence(self):
        # La StorageClass est cluster-scoped sans replicas → présence seule.
        self.assertEqual(phases.phase_plan("sc").gate_kind, "presence")

    def test_workload_phases_gate_on_ready_replicas(self):
        for phase in (
            "storage-simple",
            "metrics-server",
            "monitoring",
            "gitops",
            "dataops",
            "mlflow",
            "portal",
        ):
            self.assertEqual(
                phases.phase_plan(phase).gate_kind,
                "ready-replicas",
                f"{phase} devrait gater sur readyReplicas",
            )

    def test_gate_kind_for_unknown_phase_is_none(self):
        # Une phase sans signal connu → "none" (rien à gater, parité _wait_layer_healthy).
        self.assertEqual(phases.gate_kind_for("phase-sans-signal"), "none")


class DataopsTriggersE2EHooks(unittest.TestCase):
    """RÉSERVE CRITIQUE : dataops déclenche AUSSI les harnais e2e (STUBÉS), pas que la gate."""

    def test_dataops_declares_both_hooks(self):
        plan = phases.phase_plan("dataops")
        self.assertEqual(
            plan.e2e_hooks,
            ("dataops_chain_emit_and_verify", "dataops_egress_internet_check"),
        )

    def test_e2e_hooks_resolve_to_callables(self):
        hooks = phases.e2e_hooks_for("dataops")
        self.assertEqual(len(hooks), 2)
        for h in hooks:
            self.assertTrue(callable(h))

    def test_e2e_hooks_are_stubs_that_refuse_to_pass(self):
        # HONNÊTETÉ (ADR 0034) : un harnais e2e non câblé NE PROUVE RIEN → il LÈVE
        # (E2EHookStubbed), il ne rend JAMAIS un faux « ok ». C'est le cœur de la réserve.
        for h in phases.e2e_hooks_for("dataops"):
            with self.assertRaises(phases.E2EHookStubbed):
                h()

    def test_trivial_phases_have_no_e2e_hooks(self):
        # Toute autre phase plateforme est TRIVIALE : montage + gate, aucun harnais e2e.
        for phase in phases.all_platform_phases():
            if phase == "dataops":
                continue
            self.assertEqual(phases.e2e_hooks_for(phase), ())


class ExtravarsAreRestrictedPerPhase(unittest.TestCase):
    """Parité run-phases.sh : chaque play ne reçoit QUE ses `-e` (+ dataops_k8s_host)."""

    def setUp(self):
        self.derived = derive_run_params(load_topology(_TOPO_FILES[0]))  # banc (local-path)

    def test_all_phases_get_dataops_k8s_host(self):
        # run_ansible_phase fixe dataops_k8s_host=localhost pour CHAQUE play.
        for phase in phases.all_platform_phases():
            ev = phases.extravars_for(phase, self.derived)
            self.assertEqual(ev.get("dataops_k8s_host"), "localhost")

    def test_monitoring_gets_loki_s3_keys(self):
        ev = phases.extravars_for("monitoring", self.derived)
        for k in (
            "loki_storage_class",
            "loki_s3_backing",
            "loki_s3_endpoint",
            "monitoring_storage_class",
        ):
            self.assertIn(k, ev)
        # Pas les clés d'une AUTRE phase (cnpg/gitea/mlflow) — restriction stricte.
        self.assertNotIn("cnpg_s3_backing", ev)
        self.assertNotIn("gitea_storage_class", ev)

    def test_dataops_gets_cnpg_and_registry_keys(self):
        ev = phases.extravars_for("dataops", self.derived)
        for k in (
            "registry_storage_class",
            "cnpg_storage_class",
            "cnpg_s3_backing",
            "cnpg_s3_endpoint",
        ):
            self.assertIn(k, ev)
        self.assertNotIn("loki_s3_backing", ev)

    def test_gitops_gets_only_gitea_storage_class(self):
        ev = phases.extravars_for("gitops", self.derived)
        self.assertIn("gitea_storage_class", ev)
        self.assertNotIn("cnpg_storage_class", ev)

    def test_trivial_storage_phases_get_no_derived_keys(self):
        # storage-simple/metrics-server/portal : aucun -e dérivé (au-delà du commun).
        for phase in ("storage-simple", "metrics-server", "portal"):
            ev = phases.extravars_for(phase, self.derived)
            self.assertEqual(ev, {"dataops_k8s_host": "localhost"})

    def test_missing_derived_key_is_ignored(self):
        # ceph déclare `ceph_osd_expected` mais derive_run_params peut ne pas le fournir
        # (prod sans disques déclarés) → la clé est simplement absente, pas une erreur.
        ev = phases.extravars_for("ceph", {})
        self.assertEqual(ev, {"dataops_k8s_host": "localhost"})


class GitopsSeedIsDelegatedNotPlayed(unittest.TestCase):
    """gitops-seed (DONNÉES, gitea-init.sh) est DÉCLARÉ délégué — pas un playbook ici."""

    def test_gitops_seed_has_no_playbook(self):
        plan = phases.phase_plan("gitops-seed")
        self.assertIsNone(plan.playbook)
        self.assertIn("seed", plan.note.lower())

    def test_gitops_seed_not_in_platform_phases(self):
        # Il n'est PAS routé via launch (pas un play) — exclu de all_platform_phases().
        self.assertNotIn("gitops-seed", phases.all_platform_phases())


class BancFrontierIsDeclared(unittest.TestCase):
    """Honnêteté ADR 0034 : la frontière code-écrit / preuve-banc est DÉCLARÉE."""

    def test_banc_todo_nonempty_and_mentions_banc(self):
        todo = phases.banc_todo()
        self.assertTrue(todo)
        self.assertTrue(any("banc" in t.lower() for t in todo))

    def test_banc_todo_mentions_e2e_dataops(self):
        # La frontière nomme EXPLICITEMENT le harnais e2e dataops (réserve critique).
        joined = " ".join(phases.banc_todo()).lower()
        self.assertIn("dataops", joined)
        self.assertIn("ceph", joined)


if __name__ == "__main__":
    unittest.main()
