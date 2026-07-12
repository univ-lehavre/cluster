"""Tests du module « que faire ensuite » (nestor/plan.py, P5).

unittest stdlib, fixtures pures (Topology + done/freshness en paramètres) — aucun
subprocess, aucun réseau. Vérifie que la séquence de phases est une transcription
FIDÈLE des arms de run-phases.sh (ADR 0063 G3), le diff, et la suggestion (1er
drift, parité state.sh).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.model import topology_from_dict  # noqa: E402
from nestor.plan import (  # noqa: E402
    PHASE_PLAYBOOK,
    PlanError,
    PlanState,
    compute_plan_state,
    default_target,
    diff_phases,
    expected_phase_sequence,
    installable_now,
    observed_done_phases,
    phase_label,
    phase_playbook,
    suggest_next,
)


def _topo(profile="dataops", backend="ceph", hardening=None, nodes=None):
    nodes = nodes or [
        {"name": "cp1", "roles": ["control"]},
        {"name": "node1", "roles": ["worker"]},
        {"name": "node2", "roles": ["worker"]},
    ]
    d = {
        "catalog": {"topology": "t", "profile": profile, "terrain": "local"},
        "nodes": nodes,
        "storage": {"backend": backend},
    }
    if hardening:
        d["hardening"] = hardening
    return topology_from_dict(d)


class ExpectedSequence(unittest.TestCase):
    def test_atlas_local_path_order(self):
        # ADR 0083 : `atlas` = alias de la chaîne MLOps complète (ancien atlas + mlflow).
        # Ordre dérivé du graphe atomique (resolve_layers), plus de table figée.
        seq = expected_phase_sequence(_topo(backend="local-path"), "atlas")
        self.assertEqual(
            seq,
            [
                "up",
                "bootstrap",
                "storage-simple",
                "metrics-server",
                "monitoring",
                "gitops",
                "registry",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
            ],
        )

    def test_atlas_ceph_order(self):
        # ADR 0083 : `atlas` en ceph = ancien atlas-ceph + metrics-server (sur-ensemble
        # assumé) + mlflow. Dérivé via resolve_layers.
        seq = expected_phase_sequence(_topo(backend="ceph"), "atlas-ceph")
        self.assertEqual(
            seq,
            [
                "up",
                "bootstrap",
                "ceph",
                "sc",
                "datalake",
                "metrics-server",
                "monitoring",
                "gitops",
                "registry",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
            ],
        )

    def test_storage_real_order(self):
        seq = expected_phase_sequence(_topo(backend="ceph"), "storage-real")
        self.assertEqual(
            seq, ["up", "bootstrap", "ceph", "sc", "datalake", "smoke-s3", "wordpress"]
        )

    def test_cluster_dataops_order(self):
        seq = expected_phase_sequence(_topo(backend="ceph"), "cluster-dataops")
        self.assertEqual(
            seq,
            ["up", "bootstrap", "ceph", "sc", "datalake", "monitoring", "registry", "dataops"],
        )

    def test_socle_light(self):
        # base = socle NU (k8s + CNI) ; le stockage n'est PAS dans base (ADR 0039 :
        # storage ∈ store, pas base). Plus de storage-simple ici.
        seq = expected_phase_sequence(_topo(profile="base", backend="local-path"), "socle")
        self.assertEqual(seq, ["up", "bootstrap"])

    def test_atlas_local_path_keeps_storage_before_apps(self):
        # atlas (dataops, local-path) consomme du stockage → storage-simple est ajouté
        # APRÈS le socle nu, AVANT les apps (monitoring/dataops créent des PVC).
        seq = expected_phase_sequence(_topo(backend="local-path"), "atlas")
        self.assertEqual(seq[:3], ["up", "bootstrap", "storage-simple"])

    def test_prod_target_skips_up(self):
        # ADR 0084/0108 : sur un terrain non local (baremetal), les nœuds PRÉEXISTENT → pas
        # de phase `up` (provisioning VM limactl) ; le socle commence à `bootstrap`.
        prod = topology_from_dict(
            {
                "catalog": {"topology": "p", "profile": "base", "terrain": "baremetal"},
                "nodes": [{"name": "n1", "roles": ["control", "worker"]}],
                "storage": {"backend": "ceph"},
            }
        )
        seq = expected_phase_sequence(prod, "socle")
        self.assertNotIn("up", seq)
        self.assertEqual(seq[0], "bootstrap")

    def test_hardening_inserted_after_socle(self):
        seq = expected_phase_sequence(
            _topo(backend="ceph", hardening={"enabled": True}), "atlas-ceph"
        )
        # hardening juste après le socle (run_hardening_if_requested), avant la queue.
        self.assertEqual(seq[:5], ["up", "bootstrap", "ceph", "sc", "hardening"])
        self.assertEqual(seq[5], "datalake")  # 1re couche de queue (graphe), inchangée


class TargetValidation(unittest.TestCase):
    def test_unknown_target_rejected(self):
        with self.assertRaises(PlanError):
            expected_phase_sequence(_topo(), "frobnicate")

    def test_ceph_path_on_local_path_rejected(self):
        with self.assertRaises(PlanError):
            expected_phase_sequence(_topo(backend="local-path"), "storage-real")

    def test_atlas_on_ceph_accepted(self):
        # ADR 0083 : `atlas` est un alias backend-agnostique (plus le rejet historique
        # atlas+WITH_CEPH). En ceph il dérive la pile Ceph + la chaîne MLOps.
        seq = expected_phase_sequence(_topo(backend="ceph"), "atlas")
        self.assertEqual(seq[:4], ["up", "bootstrap", "ceph", "sc"])
        self.assertIn("mlflow", seq)

    def test_default_target_always_layers(self):
        # ADR 0083 : default_target rend TOUJOURS `layers` (plus de mapping vers presets).
        # La séquence vient de resolve_layers + socle dérivé, pas d'un nom de chemin.
        self.assertEqual(default_target(_topo(backend="ceph")), "layers")
        self.assertEqual(default_target(_topo(backend="local-path")), "layers")
        self.assertEqual(default_target(_topo(profile="base", backend="local-path")), "layers")
        self.assertEqual(default_target(_topo(profile="metrics", backend="local-path")), "layers")

    def _topo_layers(self, layers, backend="local-path"):
        return topology_from_dict(
            {
                "catalog": {"topology": "t", "terrain": "local"},
                "layers": layers,
                "nodes": [{"name": "cp1", "roles": ["control", "worker"]}],
                "storage": {"backend": backend},
            }
        )

    def test_default_target_layers_regardless_of_declared(self):
        # ADR 0083 : quel que soit l'ensemble de layers déclaré, default_target = layers
        # (la séquence est dérivée, pas mappée sur un preset nommé).
        for decl in ([], ["dataops"], ["metrics"], ["gitops", "metrics"], ["atlas"]):
            self.assertEqual(default_target(self._topo_layers(decl)), "layers")
        self.assertEqual(default_target(self._topo_layers(["dataops"], "ceph")), "layers")

    def test_layers_atlas_alias_full_chain(self):
        # `layers: [atlas]` dérive la chaîne MLOps complète via le graphe (ADR 0083).
        seq = expected_phase_sequence(self._topo_layers(["atlas"]), None)
        self.assertEqual(
            seq,
            [
                "up",
                "bootstrap",
                "storage-simple",
                "metrics-server",
                "monitoring",
                "gitops",
                "registry",
                "dataops",
                "gitops-seed",
                "mlflow",
                "portal",
            ],
        )

    def test_layers_non_prefix_palier(self):
        # [gitops, metrics] : palier non-préfixe, séquence dérivée de resolve_layers.
        seq = expected_phase_sequence(self._topo_layers(["gitops", "metrics"]), None)
        self.assertEqual(seq, ["up", "bootstrap", "storage-simple", "metrics-server", "gitops"])

    def test_store_ceph_layers_sequence_includes_datalake(self):
        # Régression du « plan faux » : profil store + ceph → chemin layers, séquence
        # socle ceph + datalake (RGW). Avant : repli socle → ceph,sc SANS datalake.
        t = self._topo_layers(["store"], "ceph")
        self.assertEqual(default_target(t), "layers")
        seq = expected_phase_sequence(t, "layers")
        self.assertEqual(seq, ["up", "bootstrap", "ceph", "sc", "datalake"])
        # pas de doublon ceph/sc (filtrés du préfixe socle).
        self.assertEqual(seq.count("ceph"), 1)

    def test_metrics_sequence_is_socle_plus_metrics_server(self):
        seq = expected_phase_sequence(_topo(profile="metrics", backend="local-path"))
        self.assertEqual(seq, ["up", "bootstrap", "metrics-server"])

    def _ha_topo(self):
        # Topologie HA déclarée : 3 control-planes hyperconvergés + VIP (la déclaration
        # de #333). Le MODÈLE accepte toujours cette topologie (is_ha_control_plane +
        # validation VIP restent — modelage HA générique préservé pour le rebuild dirqual
        # HA #486) ; c'est le TARGET nommé `ha-3cp` du planner qui a été retiré (ADR 0097,
        # voie 2 : chemin d'exécution HA supprimé, commit fd04ee0).
        return topology_from_dict(
            {
                "catalog": {"topology": "ha", "profile": "base", "terrain": "local"},
                "nodes": [
                    {"name": "cp1", "roles": ["control", "worker"]},
                    {"name": "cp2", "roles": ["control", "worker"]},
                    {"name": "cp3", "roles": ["control", "worker"]},
                ],
                "network": {"control_plane_lb": {"mode": "kube-vip-arp"}},
                "storage": {"backend": "local-path"},
            }
        )

    def test_ha_topology_derives_layers_not_ha_3cp(self):
        # ADR 0097 voie 2 : plus de dérivation vers le target `ha-3cp` (supprimé) — une
        # topologie HA rend désormais `layers` comme toute autre. Le câblage d'exécution
        # HA reviendra sous sa PR dédiée (rebuild dirqual, #486).
        self.assertEqual(default_target(self._ha_topo()), "layers")

    def test_ha_3cp_target_is_unknown(self):
        # Le target nommé `ha-3cp` n'est plus une cible connue : le demander explicitement
        # via --target est refusé (KNOWN_TARGETS ne le contient plus).
        with self.assertRaises(PlanError):
            expected_phase_sequence(self._ha_topo(), "ha-3cp")


class DiffPhases(unittest.TestCase):
    SEQ = ["up", "bootstrap", "ceph", "sc", "datalake"]

    def test_frais_done_complete_is_empty(self):
        self.assertEqual(diff_phases(self.SEQ, set(self.SEQ), "frais"), [])

    def test_frais_partial_returns_missing_in_order(self):
        done = {"up", "bootstrap"}
        self.assertEqual(diff_phases(self.SEQ, done, "frais"), ["ceph", "sc", "datalake"])

    def test_perime_replays_whole_sequence(self):
        # pas de run frais → toute la séquence candidate, même si 'done' est plein.
        self.assertEqual(diff_phases(self.SEQ, set(self.SEQ), "perime"), self.SEQ)

    def test_jamais_replays_whole_sequence(self):
        self.assertEqual(diff_phases(self.SEQ, set(), "jamais"), self.SEQ)

    def test_observed_primes_over_jamais(self):
        # RÉGRESSION (prod dirqual 2026-06-22) : un cluster sain SANS run consigné a
        # freshness="jamais" ; l'observé (bootstrap + couches réelles) PRIME → ces phases
        # ne sont PAS re-proposées au rejeu (cohérence avec preview). C'était le bug :
        # next proposait de réinstaller bootstrap sur une prod Ready.
        observed = {"up", "bootstrap", "ceph", "sc"}
        self.assertEqual(diff_phases(self.SEQ, set(), "jamais", observed), ["datalake"])

    def test_observed_primes_over_perime(self):
        observed = set(self.SEQ)  # tout observé présent
        self.assertEqual(diff_phases(self.SEQ, set(), "perime", observed), [])

    def test_observed_combines_with_done_when_fresh(self):
        # frais : on retire done ∪ observed (l'observé compte aussi, pas que l'historique).
        self.assertEqual(
            diff_phases(self.SEQ, {"up", "bootstrap"}, "frais", {"ceph"}), ["sc", "datalake"]
        )


class ObservedDonePhases(unittest.TestCase):
    """Le RÉEL prime : un cluster qui tourne marque up/bootstrap faits (ADR 0052/0056)."""

    def test_vm_present_marks_up_done(self):
        # Toutes les VMs déclarées existent → 'up' fait, même sans nœud Ready.
        done = observed_done_phases(["node1"], real_vms=["node1"], ready_nodes=[])
        self.assertIn("up", done)
        self.assertNotIn("bootstrap", done)

    def test_node_ready_marks_bootstrap_done(self):
        # Au moins un nœud Ready → 'bootstrap' fait (k8s + CNI tournent).
        done = observed_done_phases(["node1"], real_vms=["node1"], ready_nodes=["lima-node1"])
        self.assertEqual(done, {"up", "bootstrap"})

    def test_missing_vm_leaves_up_to_do(self):
        # Une VM déclarée absente → 'up' PAS fait (il reste à créer).
        done = observed_done_phases(["node1", "node2"], real_vms=["node1"], ready_nodes=[])
        self.assertNotIn("up", done)

    def test_no_node_no_vm_is_empty(self):
        self.assertEqual(observed_done_phases(["node1"], real_vms=[], ready_nodes=[]), set())


class SuggestNext(unittest.TestCase):
    def test_first_missing_phase_only(self):
        # 1er drift seulement (parité state.sh #107-109).
        topo = _topo(backend="ceph")
        s = suggest_next(topo, "atlas-ceph", {"up", "bootstrap", "ceph", "sc"}, "frais")
        self.assertEqual(s.phase, "datalake")
        self.assertEqual(s.etat, "manquante")
        self.assertEqual(s.playbook, "bootstrap/ceph-datalake.yaml")

    def test_all_done_fresh_suggests_nothing(self):
        topo = _topo(backend="ceph")
        seq = set(expected_phase_sequence(topo, "atlas-ceph"))
        s = suggest_next(topo, "atlas-ceph", seq, "frais")
        self.assertIsNone(s.phase)
        self.assertEqual(s.etat, "à-jour")
        self.assertIn("à jour", s.message)

    def test_perime_suggests_first_of_sequence_as_rejeu(self):
        topo = _topo(backend="ceph")
        seq = set(expected_phase_sequence(topo, "atlas-ceph"))
        s = suggest_next(topo, "atlas-ceph", seq, "perime")
        self.assertEqual(s.phase, "up")  # rejeu depuis le début
        self.assertEqual(s.etat, "rejeu")

    def test_run_params_attached(self):
        topo = _topo(backend="ceph")
        rp = {"cnpg_storage_class": "rook-ceph-block-replicated"}
        s = suggest_next(topo, "atlas-ceph", {"up"}, "frais", run_params=rp)
        self.assertEqual(s.run_params, rp)

    def test_observed_done_in_done_is_not_a_drift(self):
        # Contrat consommé par cmd_next : il passe `done | observed` (pas l'historique
        # seul). Une phase faite mais NON consignée (vue sur le cluster réel) ne doit donc
        # PAS ressortir comme « 1er drift » — sinon `next` contredit `preview` (qui, lui,
        # soustrait déjà l'observé). Ici toute la séquence est « done » via l'observé.
        topo = _topo(backend="ceph")
        seq = set(expected_phase_sequence(topo, "atlas-ceph"))
        s = suggest_next(topo, "atlas-ceph", seq, "frais")
        self.assertIsNone(s.phase)  # rien à proposer : cohérent avec preview « à jour »


class PhaseTable(unittest.TestCase):
    def test_every_path_phase_is_in_table(self):
        # Garde-fou : chaque phase qui apparaît dans une séquence doit avoir une
        # entrée dans PHASE_PLAYBOOK (playbook ou None explicite).
        topo_ceph = _topo(backend="ceph", hardening={"enabled": True})
        topo_light = _topo(backend="local-path")
        phases = set()
        for tgt in ["socle", "storage-real", "cluster-dataops", "atlas-ceph"]:
            phases.update(expected_phase_sequence(topo_ceph, tgt))
        phases.update(expected_phase_sequence(topo_light, "atlas"))
        self.assertTrue(phases.issubset(set(PHASE_PLAYBOOK)))

    def test_phase_label_is_human_readable(self):
        # Libellé métier pour preview : up → « créer les VMs », bootstrap → k8s+CNI.
        self.assertEqual(phase_label("up"), "créer les VMs")
        self.assertIn("Kubernetes", phase_label("bootstrap"))
        self.assertIn("local-path", phase_label("storage-simple"))

    def test_phase_label_falls_back_to_name(self):
        # Phase inconnue de la table → repli sur le nom (pas de masquage).
        self.assertEqual(phase_label("frobnicate"), "frobnicate")

    def test_phase_playbook_accessor(self):
        # Accesseur du mapping : play unitaire → chemin ; phase amont/script → None.
        self.assertEqual(phase_playbook("storage-simple"), "bootstrap/local-path.yaml")
        self.assertIsNone(phase_playbook("up"))  # amont, pas un play
        self.assertIsNone(phase_playbook("frobnicate"))  # inconnue


# Carte de dépendances PHASE→PHASE local-path (figée, == ce que phase_deps dérive du
# graphe atomique — cf. test_layers.PhaseDeps qui le PROUVE contre le bash). On la
# fixe ici pour tester `installable_now` PUREMENT (sans sheller). storage-simple et
# metrics-server sont des RACINES indépendantes ; monitoring/gitops dépendent du
# stockage ; dataops de monitoring ; gitops-seed de gitops.
_DEPS_LOCAL = {
    "storage-simple": set(),
    "metrics-server": set(),
    "monitoring": {"storage-simple"},
    "gitops": {"storage-simple"},
    "dataops": {"monitoring", "storage-simple"},
    "gitops-seed": {"gitops"},
    # mlflow (ADR 0082/0083) dépend de dataops (base CNPG) + monitoring (SeaweedFS),
    # comme le vrai graphe (phase_deps) — sinon installable_now le croit montable au socle.
    "mlflow": {"dataops", "monitoring"},
}


class InstallableNow(unittest.TestCase):
    """`installable_now` : couches montables MAINTENANT (deps réelles satisfaites)."""

    def _deps_fn(self):
        return lambda: dict(_DEPS_LOCAL)

    def test_amont_missing_is_sole_offer(self):
        # VMs/socle absents : on ne propose QUE l'amont (prérequis dur), jamais un menu.
        topo = _topo(backend="local-path")
        got = installable_now(topo, "atlas", set(), "frais", deps_fn=self._deps_fn())
        self.assertEqual(got, ["up"])

    def test_bootstrap_is_sole_offer_after_up(self):
        topo = _topo(backend="local-path")
        got = installable_now(topo, "atlas", {"up"}, "frais", deps_fn=self._deps_fn())
        self.assertEqual(got, ["bootstrap"])

    def test_menu_storage_and_metrics_both_installable(self):
        # Socle fait : storage-simple ET metrics-server sont montables (indépendants).
        # Les DEUX sont proposés, l'ordre du chemin en tête (storage d'abord = défaut).
        topo = _topo(backend="local-path")
        got = installable_now(topo, "atlas", {"up", "bootstrap"}, "frais", deps_fn=self._deps_fn())
        self.assertEqual(got[:2], ["storage-simple", "metrics-server"])
        # monitoring/gitops NE sont PAS montables (dépendent de storage-simple, absent).
        self.assertNotIn("monitoring", got)
        self.assertNotIn("gitops", got)

    def test_metrics_then_storage_choosable_independently(self):
        # Si metrics-server est monté AVANT storage (choix opérateur), storage reste
        # proposé ensuite — la dépendance conventionnelle n'INTERDIT pas cet ordre.
        topo = _topo(backend="local-path")
        got = installable_now(
            topo, "atlas", {"up", "bootstrap", "metrics-server"}, "frais", deps_fn=self._deps_fn()
        )
        # storage-simple débloque la suite ; portal est sans dépendance dure (ADR 0091/0092 :
        # il observe les Services, marche dès le socle) → installable dès bootstrap aussi.
        self.assertIn("storage-simple", got)

    def test_storage_done_unlocks_monitoring_and_gitops(self):
        topo = _topo(backend="local-path")
        got = installable_now(
            topo,
            "atlas",
            {"up", "bootstrap", "storage-simple", "metrics-server"},
            "frais",
            deps_fn=self._deps_fn(),
        )
        # monitoring + gitops débloqués (deps storage satisfaites) ; dataops PAS encore
        # (dépend de monitoring), gitops-seed PAS encore (dépend de gitops).
        self.assertIn("monitoring", got)
        self.assertIn("gitops", got)
        self.assertNotIn("dataops", got)
        self.assertNotIn("gitops-seed", got)

    def test_deps_fn_none_falls_back_to_first_drift(self):
        # Sans carte de deps : repli SÛR sur la 1re phase manquante seule (pas de menu).
        topo = _topo(backend="local-path")
        got = installable_now(topo, "atlas", {"up", "bootstrap"}, "frais", deps_fn=None)
        self.assertEqual(got, ["storage-simple"])  # 1er drift, jamais 2 sans la carte

    def test_deps_fn_not_called_for_amont(self):
        # Garde-fou amont : deps_fn n'est PAS invoqué (pas de bash pour décider de
        # créer les VMs) — important pour l'isolation des tests façade.
        topo = _topo(backend="local-path")
        calls = []

        def boom():
            calls.append(1)
            return dict(_DEPS_LOCAL)

        installable_now(topo, "atlas", set(), "frais", deps_fn=boom)
        self.assertEqual(calls, [])  # jamais appelé : up est la seule offre

    def test_all_done_returns_empty(self):
        topo = _topo(backend="local-path")
        seq = set(expected_phase_sequence(topo, "atlas"))
        got = installable_now(topo, "atlas", seq, "frais", deps_fn=self._deps_fn())
        self.assertEqual(got, [])

    def test_observed_layer_not_reproposed_even_if_stale(self):
        # RÉEL prime sur la fraîcheur : metrics-server OBSERVÉ présent n'est PAS
        # re-proposé, même quand la fraîcheur est `jamais` (diff_phases rejouerait
        # tout). Cas du banc : couche installée hors run consigné → ne pas re-proposer.
        topo = _topo(backend="local-path")
        got = installable_now(
            topo,
            "atlas",
            set(),  # historique vide
            "jamais",  # aucun run frais → diff_phases rejoue toute la séquence
            deps_fn=self._deps_fn(),
            observed_done={"up", "bootstrap", "metrics-server"},  # réel : socle + metrics
        )
        self.assertNotIn("metrics-server", got)  # déjà là → pas re-proposé
        self.assertIn("storage-simple", got)  # toujours à monter

    def test_observed_done_satisfies_downstream_deps(self):
        # Une couche observée présente satisfait les dépendances de ses consommateurs :
        # storage-simple OBSERVÉ → monitoring/gitops deviennent montables.
        topo = _topo(backend="local-path")
        got = installable_now(
            topo,
            "atlas",
            {"up", "bootstrap"},
            "frais",
            deps_fn=self._deps_fn(),
            observed_done={"storage-simple"},
        )
        self.assertNotIn("storage-simple", got)  # observé → pas re-proposé
        self.assertIn("monitoring", got)  # débloqué par le storage observé
        self.assertIn("gitops", got)


class ComputePlanState(unittest.TestCase):
    """`compute_plan_state` : LE calcul partagé preview/next/up (PUR, sans cluster).

    Refonte lot 6 (décision mainteneur) : `done` DÉRIVE DU RÉEL SEUL —
    `observed_socle ∪ observed_layers` — PLUS de l'historique des runs. Une couche que
    le réel ne confirme PAS est « à appliquer », même si un run la disait faite ; une
    couche observée saine est `done`, même sans run consigné. La cohérence de dépendance
    (socle mort → tout l'aval à appliquer) devient INTRINSÈQUE : un kubectl mort vide
    `observed_layers`, donc rien aval n'est tenu fait (plus de garde `if up not in done`).
    La fraîcheur (verdict_for_run) est dérivée AILLEURS (préservée, #216) : elle n'entre
    plus dans ce calcul.
    """

    SEQ = ["up", "bootstrap", "storage-simple", "metrics-server", "monitoring", "dataops"]

    def test_observed_layer_not_in_a_appliquer(self):
        # Une couche observée SAINE n'est PAS « à monter », même sans run consigné
        # (`done` vient du réel, pas de l'historique).
        state = compute_plan_state(
            self.SEQ,
            observed_socle={"up", "bootstrap"},
            observed_layers={"storage-simple"},  # le réel la confirme saine
        )
        self.assertIn("storage-simple", state.done)
        self.assertNotIn("storage-simple", state.a_appliquer)
        self.assertIn("metrics-server", state.a_appliquer)  # pas observée → à monter

    def test_history_says_done_but_k8s_dead_is_reproposed(self):
        # LE BUG DU MAINTENEUR : la VM existe (`up` observé) mais Kubernetes est mort
        # (aucun nœud Ready → bootstrap NON observé). L'historique du 22 juin disait
        # bootstrap/dataops/… faits — mais `done` ne vient PLUS de l'historique : seul
        # `up` (réel) est `done`. bootstrap ET toutes les couches aval sont « à appliquer »
        # (le kubectl échoue donc observed_layers est vide). Plus d'incohérence « bootstrap
        # à FAIRE mais storage-simple/dataops à-JOUR ».
        state = compute_plan_state(
            self.SEQ,
            observed_socle={"up"},  # VM seule : bootstrap NON observé (k8s mort)
            observed_layers=set(),  # kubectl mort → aucune couche confirmée
        )
        self.assertEqual(state.done, frozenset({"up"}))  # seul le réel : la VM
        # bootstrap + TOUTES les couches applicatives à appliquer (cohérence naturelle)
        self.assertEqual(
            state.a_appliquer,
            frozenset({"bootstrap", "storage-simple", "metrics-server", "monitoring", "dataops"}),
        )

    def test_history_lies_layer_destroyed_is_reproposed(self):
        # L'historique disait une couche à signal FAITE, mais le réel ne la confirme PAS
        # (détruite / posée à moitié, absente d'observed_layers) → elle RESTE « à monter »
        # naturellement (elle n'est juste pas dans `done` = réel).
        state = compute_plan_state(
            self.SEQ,
            observed_socle={"up", "bootstrap"},
            observed_layers={"storage-simple", "metrics-server", "monitoring"},  # dataops ABSENT
        )
        self.assertNotIn("dataops", state.done)
        self.assertIn("dataops", state.a_appliquer)  # non confirmé par le réel → re-proposé

    def test_up_not_done_voids_downstream(self):
        # Socle absent (VMs détruites, rien observé) : AUCUNE couche aval ne peut être
        # « faite » — `done` est vide, toute la séquence est à monter. Cohérence de
        # dépendance INTRINSÈQUE (le réel ne ment pas, plus de garde ad hoc).
        state = compute_plan_state(
            self.SEQ,
            observed_socle=set(),  # le réel ne confirme RIEN (VMs détruites)
            observed_layers=set(),
        )
        self.assertEqual(state.done, frozenset())  # done vide : socle absent
        self.assertEqual(state.a_appliquer, frozenset(self.SEQ))

    def test_observed_layer_done_without_any_history(self):
        # Une couche saine observée est `done` SANS aucun historique (run non consigné) :
        # le réel SUFFIT à la tenir faite — c'est tout l'objet de la refonte.
        state = compute_plan_state(
            self.SEQ,
            observed_socle={"up", "bootstrap"},
            observed_layers={"storage-simple", "metrics-server"},
        )
        self.assertEqual(
            state.done, frozenset({"up", "bootstrap", "storage-simple", "metrics-server"})
        )
        self.assertNotIn("storage-simple", state.a_appliquer)
        self.assertNotIn("metrics-server", state.a_appliquer)

    def test_returns_plan_state(self):
        state = compute_plan_state(self.SEQ, {"up", "bootstrap"}, set())
        self.assertIsInstance(state, PlanState)


class PreviewNextParity(unittest.TestCase):
    """Parité preview == next : pour un MÊME état réel, les deux dérivent du MÊME
    `compute_plan_state` → même verdict, plus de divergence.

    On simule les DEUX façades : `cmd_preview` consomme `a_appliquer` ; `cmd_next`
    le passe à `installable_now` (qui ne fait plus que TRIER par deps). Le menu de next
    est donc TOUJOURS ⊆ du plan de preview (mêmes couches, ordre/deps en plus).

    Refonte lot 6 : `compute_plan_state` ne dépend QUE du réel (observed_socle/_layers).
    `freshness` reste passé à `installable_now`/`suggest_next` (verdict d'affichage), mais
    il ne change PLUS `a_appliquer` (qui hérite du state partagé) → la parité est stable
    quelle que soit la fraîcheur."""

    SEQ = ["up", "bootstrap", "storage-simple", "metrics-server", "monitoring", "dataops"]
    DEPS = {
        "storage-simple": set(),
        "metrics-server": set(),
        "monitoring": {"storage-simple"},
        "dataops": {"monitoring"},
    }

    def _preview_a_appliquer(self, observed_socle, observed_layers):
        """Reproduit le calcul de cmd_preview (compute_plan_state → a_appliquer)."""
        return set(compute_plan_state(self.SEQ, observed_socle, observed_layers).a_appliquer)

    def _next_montables(self, topo, observed_socle, observed_layers, freshness):
        """Reproduit le calcul de cmd_next (même state, puis installable_now trie)."""
        state = compute_plan_state(self.SEQ, observed_socle, observed_layers)
        observed = observed_socle | observed_layers
        return installable_now(
            topo,
            "atlas",
            set(state.done),
            freshness,
            deps_fn=lambda: dict(self.DEPS),
            observed_done=observed,
            a_appliquer=set(state.a_appliquer),
        ), set(state.a_appliquer)

    def _assert_parity(self, observed_socle, observed_layers, freshness):
        topo = _topo(backend="local-path")
        prev = self._preview_a_appliquer(observed_socle, observed_layers)
        montables, next_a_appliquer = self._next_montables(
            topo, observed_socle, observed_layers, freshness
        )
        # MÊME verdict « à monter » : preview et next partent du MÊME a_appliquer.
        self.assertEqual(prev, next_a_appliquer)
        # next ne propose QUE des couches du plan de preview (deps-filtrées) — jamais
        # une couche que preview tient pour à-jour (la divergence d'avant).
        self.assertTrue(set(montables).issubset(prev))

    def test_parity_socle_done_layers_observed(self):
        # Socle fait + storage-simple observé sain : preview et next conviennent.
        self._assert_parity({"up", "bootstrap"}, {"storage-simple"}, "frais")

    def test_parity_layer_absent(self):
        # dataops non confirmé par le réel → preview ET next le re-proposent
        # (avant le fix : next disait « à jour », preview « à monter »).
        self._assert_parity(
            {"up", "bootstrap"},
            {"storage-simple", "metrics-server", "monitoring"},  # dataops absent
            "frais",
        )

    def test_parity_vms_destroyed(self):
        # VMs détruites (rien observé), même avec une fraîcheur « frais » : preview ET
        # next re-proposent TOUTE la séquence (`done` ne survit pas au réel vide).
        self._assert_parity(set(), set(), "frais")

    def test_parity_k8s_dead_vm_alive(self):
        # Le bug du mainteneur en parité : VM seule (up), k8s mort (bootstrap + couches
        # non observés) → preview ET next conviennent que bootstrap + l'aval sont à monter.
        self._assert_parity({"up"}, set(), "frais")

    def test_parity_never_run_clean_cluster(self):
        # freshness=jamais (aucun run) mais cluster sain (socle + couches observées) :
        # le réel prime → ni preview ni next ne re-proposent l'observé.
        self._assert_parity({"up", "bootstrap"}, {"storage-simple", "metrics-server"}, "jamais")


if __name__ == "__main__":
    unittest.main()
