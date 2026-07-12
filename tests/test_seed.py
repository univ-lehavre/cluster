"""Tests du seed des données post-bootstrap du JOUET (nestor/seed.py) — LOT 8 refonte nestor.

unittest stdlib, I/O TOTALEMENT INJECTÉE (garde `assert_target` + actions `do` stubées) —
AUCUN appel Gitea réel, AUCUN cluster, AUCUN kubectl/git. Ces tests prouvent la LOGIQUE :
la GARDE banc, l'ordre des étapes, le fail-fast sur étape KO, le paramétrage 100 % YAML
(SeedConfig.from_topology lit le bloc gitea, plus l'env).

NB (ADR 0111) : le seed ne porte PLUS le flux App-of-Apps citation (kinds `prod`/`banc-citation`,
substitution de digest, rendu de déclaration de code-location) — c'est un geste côté dépôt atlas.
Seul demeure le seed du jouet `atlas-workflows` (artefact du socle, ADR 0086).

⚠️  HONNÊTETÉ (ADR 0034) : la PREUVE réelle (gitea-init sur le banc) reste un RUN consigné —
PAS couvert ici. Voir `nestor/seed.py:_BANC_TODO`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import seed  # noqa: E402
from nestor.model import topology_from_dict  # noqa: E402


def _topo(**over):
    """Topology minimale valide, surchargeable (bloc gitea)."""
    d = {
        # ADR 0108 : la classe matérielle vit dans `catalog.terrain` (`local` = ex-banc) ;
        # l'ancien champ prod/bench de criticité est retiré du modèle.
        "catalog": {"topology": "t", "terrain": "local"},
        "nodes": [{"name": "n1", "roles": ["control", "worker"]}],
    }
    d.update(over)
    return topology_from_dict(d)


class Config(unittest.TestCase):
    """SeedConfig.from_topology : 100 % YAML, plus de variables d'env (ADR 0097 §3)."""

    def test_defaults_when_blocks_absent(self):
        cfg = seed.SeedConfig.from_topology(_topo())
        # Défauts génériques (ADR 0023), pas d'env lu.
        self.assertEqual(cfg.ns, "gitea")
        self.assertEqual(cfg.admin_user, "atlas-admin")
        self.assertEqual(cfg.org, "atlas")
        self.assertEqual(cfg.repo, "workflows")

    def test_gitea_block_overrides(self):
        cfg = seed.SeedConfig.from_topology(
            _topo(gitea={"ns": "forge", "org": "team", "admin_user": "boss"})
        )
        self.assertEqual(cfg.ns, "forge")
        self.assertEqual(cfg.org, "team")
        self.assertEqual(cfg.admin_user, "boss")
        # Champs non surchargés gardent le défaut.
        self.assertEqual(cfg.repo, "workflows")

    def test_derived_url(self):
        cfg = seed.SeedConfig.from_topology(
            _topo(gitea={"svc": "http://gitea.lan", "org": "a", "repo": "w"})
        )
        self.assertEqual(cfg.workflows_repo_url(), "http://gitea.lan/a/w.git")

    def test_no_env_read(self):
        # Aucune variable GITEA_* dans l'env ne doit influencer la config.
        os.environ["GITEA_ORG"] = "leaked-from-env"
        self.addCleanup(os.environ.pop, "GITEA_ORG", None)
        cfg = seed.SeedConfig.from_topology(_topo())
        self.assertEqual(cfg.org, "atlas")  # YAML/défaut, jamais l'env


class Steps(unittest.TestCase):
    """Séquence ORDONNÉE des étapes du jouet (PUR) — parité des `echo N/7` du bash."""

    def test_banc_steps(self):
        steps = seed.seed_steps("banc")
        self.assertEqual(steps[0], "admin")
        self.assertIn("application", steps)
        self.assertEqual(len(steps), 7)

    def test_prod_and_banc_citation_kinds_rejected(self):
        # ADR 0111 : les kinds du flux App-of-Apps citation ont disparu — seul `banc` demeure.
        for kind in ("prod", "banc-citation", "staging"):
            with self.assertRaises(seed.SeedError):
                seed.seed_steps(kind)


class GuardBanc(unittest.TestCase):
    """La garde banc : `run_seed` la joue EN TÊTE, un refus stoppe AVANT tout geste.

    On STUBE la garde : la façade y branche `_assert_target_identity` (banc) ; ici on prouve
    que `run_seed` joue la garde en tête et qu'un refus n'exécute aucune étape."""

    def test_banc_guard_passes_then_runs_all_steps(self):
        order = []
        result = seed.run_seed(
            "banc",
            seed.SeedConfig(),
            assert_target=lambda: order.append("guard"),
            do=lambda step: order.append(step) or True,
        )
        self.assertTrue(result.done)
        self.assertEqual(order[0], "guard")  # garde AVANT toute étape
        self.assertEqual(order[1:], list(seed.seed_steps("banc")))

    def test_banc_guard_refusing_wrong_target_stops_before_steps(self):
        # Garde banc qui DÉTECTE une mauvaise cible (prod) → lève ; aucune étape ne s'exécute.
        executed = []

        def guard_refuses():
            raise seed.SeedGuardRefused("cible = prod, pas le banc (ADR 0053)")

        with self.assertRaises(seed.SeedGuardRefused):
            seed.run_seed(
                "banc",
                seed.SeedConfig(),
                assert_target=guard_refuses,
                do=lambda step: executed.append(step) or True,
            )
        self.assertEqual(executed, [])  # rien muté : la garde protège en amont

    def test_non_guard_exception_wrapped_as_refused(self):
        # Une garde façade qui lève hors hiérarchie (_UsageError…) → SeedGuardRefused.
        with self.assertRaises(seed.SeedGuardRefused):
            seed.run_seed(
                "banc",
                seed.SeedConfig(),
                assert_target=lambda: (_ for _ in ()).throw(RuntimeError("usage")),
                do=lambda step: True,
            )


class FailFast(unittest.TestCase):
    """Une étape KO arrête la séquence (parité `die` du bash)."""

    def test_failed_step_stops_and_marks_not_done(self):
        seen = []

        def do(step):
            seen.append(step)
            return step != "org-repo"  # échoue à la 3e étape banc

        with self.assertRaises(seed.SeedError):
            seed.run_seed("banc", seed.SeedConfig(), assert_target=lambda: None, do=do)
        # On s'est arrêté SUR org-repo (pas d'étape au-delà).
        self.assertEqual(seen, ["admin", "token", "org-repo"])


class Honesty(unittest.TestCase):
    """La frontière code-écrit / preuve-cluster est DÉCLARÉE (ADR 0034)."""

    def test_banc_todo_non_empty(self):
        self.assertTrue(seed.banc_todo())
        self.assertTrue(all(isinstance(t, str) and t for t in seed.banc_todo()))


if __name__ == "__main__":
    unittest.main()
