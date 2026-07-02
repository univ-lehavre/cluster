"""Tests du seed des données post-bootstrap (nestor/seed.py) — LOT 8 refonte nestor.

unittest stdlib, I/O TOTALEMENT INJECTÉE (gardes `assert_target` + actions `do` stubées) —
AUCUN appel Gitea réel, AUCUN cluster, AUCUN kubectl/git. Ces tests prouvent la LOGIQUE :
les DEUX GARDES OPPOSÉES (banc vs prod), l'ordre des étapes, le fail-fast sur étape KO, le
paramétrage 100 % YAML (SeedConfig.from_topology lit gitea/atlas, plus l'env), et la ref
digest immuable.

⚠️  HONNÊTETÉ (ADR 0034) : la PREUVE réelle (gitea-init sur le banc, app-of-apps sur dirqual)
reste un RUN consigné — PAS couvert ici. Voir `nestor/seed.py:_BANC_TODO`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import seed  # noqa: E402
from nestor.model import topology_from_dict  # noqa: E402


def _topo(**over):
    """Topology minimale valide, surchargeable (blocs gitea/atlas)."""
    d = {
        "catalog": {"topology": "t"},
        "nodes": [{"name": "n1", "roles": ["control", "worker"]}],
        "target_kind": "bench",
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
        self.assertEqual(cfg.expected_cluster, "cluster-prod")

    def test_gitea_block_overrides(self):
        cfg = seed.SeedConfig.from_topology(
            _topo(gitea={"ns": "forge", "org": "team", "admin_user": "boss"})
        )
        self.assertEqual(cfg.ns, "forge")
        self.assertEqual(cfg.org, "team")
        self.assertEqual(cfg.admin_user, "boss")
        # Champs non surchargés gardent le défaut.
        self.assertEqual(cfg.repo, "workflows")

    def test_atlas_block_overrides(self):
        cfg = seed.SeedConfig.from_topology(
            _topo(
                atlas={
                    "expected_cluster": "prod-x",
                    "repo_dir": "/tmp/atlas",
                    "citation_revision": "abc1234",
                    "citation_image_digest": "sha256:dead",
                }
            )
        )
        self.assertEqual(cfg.expected_cluster, "prod-x")
        self.assertEqual(cfg.atlas_repo_dir, "/tmp/atlas")
        self.assertEqual(cfg.citation_revision, "abc1234")
        self.assertEqual(cfg.citation_image_digest, "sha256:dead")

    def test_derived_urls(self):
        cfg = seed.SeedConfig.from_topology(
            _topo(gitea={"svc": "http://gitea.lan", "org": "a", "repo": "w"})
        )
        self.assertEqual(cfg.workflows_repo_url(), "http://gitea.lan/a/w.git")
        # Prod : org_cluster/repo_apps et org_atlas/repo_atlas (défauts).
        self.assertEqual(cfg.apps_repo_url(), "http://gitea.lan/cluster/apps.git")
        self.assertEqual(cfg.atlas_repo_url(), "http://gitea.lan/atlas/atlas.git")

    def test_no_env_read(self):
        # Aucune variable GITEA_*/CITATION_* dans l'env ne doit influencer la config.
        os.environ["GITEA_ORG"] = "leaked-from-env"
        self.addCleanup(os.environ.pop, "GITEA_ORG", None)
        cfg = seed.SeedConfig.from_topology(_topo())
        self.assertEqual(cfg.org, "atlas")  # YAML/défaut, jamais l'env


class Steps(unittest.TestCase):
    """Séquence ORDONNÉE des étapes (PUR) — parité des `echo N/7` du bash."""

    def test_banc_steps(self):
        steps = seed.seed_steps("banc")
        self.assertEqual(steps[0], "admin")
        self.assertIn("application", steps)
        self.assertEqual(len(steps), 7)

    def test_prod_steps(self):
        steps = seed.seed_steps("prod")
        self.assertEqual(steps[0], "admin-token")
        self.assertIn("push-atlas-tree", steps)

    def test_banc_citation_extends_prod_with_webhook_build(self):
        # banc-citation REPREND le flux App-of-Apps citation (la séquence prod) mais AU BANC,
        # et y AJOUTE le webhook #2 (build) de la chaîne événementielle (ADR 0095 §1.b) —
        # geste BANC absent de la prod. Le CŒUR App-of-Apps (org/repo, push arbre, citation,
        # racine) reste partagé → une preuve banc valide le vrai chemin prod.
        bc = seed.seed_steps("banc-citation")
        prod = seed.seed_steps("prod")
        self.assertIn("push-citation", bc)
        self.assertIn("webhook-build", bc)
        self.assertNotIn("webhook-build", prod)  # la prod NE grave PAS le webhook #2
        # webhook-build vient APRÈS push-atlas-tree (le repo de code atlas doit exister avant).
        self.assertGreater(bc.index("webhook-build"), bc.index("push-atlas-tree"))
        # Le cœur App-of-Apps prod est un SOUS-ensemble ordonné de banc-citation (seul ajout).
        self.assertEqual(tuple(s for s in bc if s != "webhook-build"), prod)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(seed.SeedError):
            seed.seed_steps("staging")


class GuardsOpposed(unittest.TestCase):
    """LE point du LOT 8 : DEUX gardes OPPOSÉES — banc REFUSE la prod, prod REFUSE le banc.

    On STUBE chaque garde : la façade y branche `_assert_bench_target` (banc) /
    `assert_prod_target` (prod) ; ici on prouve que `run_seed` joue la garde EN TÊTE et
    qu'un refus stoppe AVANT tout geste (aucune étape exécutée)."""

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

    def test_banc_guard_refusing_prod_target_stops_before_steps(self):
        # Garde banc qui DÉTECTE une cible prod → lève ; aucune étape ne s'exécute.
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

    def test_prod_guard_refusing_bench_target_stops_before_steps(self):
        # Garde prod qui DÉTECTE le banc → lève ; aucune étape ne s'exécute.
        executed = []

        def guard_refuses():
            raise seed.SeedGuardRefused("cible = banc, pas la prod attendue")

        with self.assertRaises(seed.SeedGuardRefused):
            seed.run_seed(
                "prod",
                seed.SeedConfig(),
                assert_target=guard_refuses,
                do=lambda step: executed.append(step) or True,
            )
        self.assertEqual(executed, [])

    def test_banc_citation_runs_its_sequence_under_banc_guard(self):
        # Le POINT de la décision A (ADR 0095 §1.a) : banc-citation joue le flux App-of-Apps
        # (séquence prod) + le webhook #2 (build) SOUS garde banc. La garde passe (cible =
        # banc) → les 7 étapes de banc-citation, dans l'ordre.
        order = []
        result = seed.run_seed(
            "banc-citation",
            seed.SeedConfig(),
            assert_target=lambda: order.append("guard"),
            do=lambda step: order.append(step) or True,
        )
        self.assertTrue(result.done)
        self.assertEqual(order[0], "guard")
        self.assertEqual(order[1:], list(seed.seed_steps("banc-citation")))
        self.assertIn("webhook-build", order)

    def test_banc_citation_guard_refusing_prod_target_stops_before_steps(self):
        # SÉCURITÉ (ADR 0053/0084) : la garde banc de banc-citation DÉTECTE une cible prod
        # → lève AVANT toute étape. On ne déploie jamais citation « réel » sur la prod par
        # cette voie banc (la voie prod garde `assert_prod_target`, séparée).
        executed = []

        def guard_refuses():
            raise seed.SeedGuardRefused("cible = prod, pas le banc (ADR 0053)")

        with self.assertRaises(seed.SeedGuardRefused):
            seed.run_seed(
                "banc-citation",
                seed.SeedConfig(),
                assert_target=guard_refuses,
                do=lambda step: executed.append(step) or True,
            )
        self.assertEqual(executed, [])

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


class DigestRef(unittest.TestCase):
    """Référence d'image par DIGEST immuable (ADR 0095 §2) — frontière contrat atlas."""

    def test_valid_digest_builds_ref(self):
        ref = seed.citation_image_ref("registry:80/citation-dagster", "sha256:abcd")
        self.assertEqual(ref, "registry:80/citation-dagster@sha256:abcd")

    def test_non_digest_rejected(self):
        # Un tag mutable (`0.0.0`) n'est PAS un digest → refus (pas de déploiement mutable).
        with self.assertRaises(seed.SeedError):
            seed.citation_image_ref("registry:80/citation-dagster", "0.0.0")


class SubstitutePlaceholders(unittest.TestCase):
    """Substitution des 2 jetons d'injection atlas (PUR, frontière ADR 0094)."""

    def test_both_placeholders_substituted(self):
        text = "digest: __CITATION_IMAGE_DIGEST__\nenv: __CITATION_IMAGE__\n"
        out, n = seed.substitute_citation_placeholders(
            text, "registry:80/citation-dagster", "sha256:abcd"
        )
        self.assertEqual(n, 2)
        self.assertIn("digest: sha256:abcd", out)
        self.assertIn("env: registry:80/citation-dagster@sha256:abcd", out)
        # Aucun placeholder résiduel.
        self.assertNotIn("__CITATION_IMAGE", out)

    def test_order_digest_before_image_no_amputation(self):
        # __CITATION_IMAGE_DIGEST__ traité AVANT __CITATION_IMAGE__ : le sha256 seul ne doit
        # PAS être amputé par la substitution du préfixe __CITATION_IMAGE__.
        text = "__CITATION_IMAGE_DIGEST__"
        out, n = seed.substitute_citation_placeholders(
            text, "registry:80/citation-dagster", "sha256:dead"
        )
        self.assertEqual(out, "sha256:dead")
        self.assertEqual(n, 1)

    def test_no_placeholder_returns_zero(self):
        out, n = seed.substitute_citation_placeholders(
            "rien à injecter", "registry:80/citation-dagster", "sha256:abcd"
        )
        self.assertEqual(n, 0)
        self.assertEqual(out, "rien à injecter")

    def test_bad_digest_rejected_before_substitution(self):
        with self.assertRaises(seed.SeedError):
            seed.substitute_citation_placeholders(
                "__CITATION_IMAGE__", "registry:80/citation-dagster", "0.0.0"
            )


class RenderCitationDeclaration(unittest.TestCase):
    """Rendu de apps/citation.yaml depuis le patron *.example (PUR, ADR 0023)."""

    _EXAMPLE = (
        "spec:\n"
        "  source:\n"
        "    repoURL: http://example/atlas.git\n"
        "    targetRevision: 0000000\n"
        "    path: dataops/citation-dagster/deploy/overlays/prod\n"
    )

    def test_injects_repourl_and_revision(self):
        out = seed.render_citation_declaration(
            self._EXAMPLE, "http://gitea/atlas/atlas.git", "c98feea9"
        )
        self.assertIn("repoURL: http://gitea/atlas/atlas.git", out)
        self.assertIn("targetRevision: c98feea9", out)
        # Sans overlay explicite, le path du patron (prod) n'est PAS touché.
        self.assertIn("path: dataops/citation-dagster/deploy/overlays/prod", out)

    def test_overlay_rewrites_path_to_bench(self):
        # banc-citation : le path prod du patron est réécrit vers bench (décision D2).
        out = seed.render_citation_declaration(
            self._EXAMPLE, "http://gitea/atlas/atlas.git", "c98feea9", overlay="bench"
        )
        self.assertIn("path: dataops/citation-dagster/deploy/overlays/bench", out)
        self.assertNotIn("overlays/prod", out)

    def test_overlay_not_matched_raises(self):
        # Un patron sans ligne path overlays/ + overlay demandé → garde (motif non matché).
        with self.assertRaises(seed.SeedError):
            seed.render_citation_declaration(
                "spec:\n  source:\n    repoURL: http://x/a.git\n    targetRevision: abc1234\n",
                "http://x/a.git",
                "abc1234",
                overlay="bench",
            )

    def test_failed_injection_raises(self):
        # Patron sans les lignes ciblées (indentation absente) → garde anti-injection ratée.
        with self.assertRaises(seed.SeedError):
            seed.render_citation_declaration("spec: {}\n", "http://x/a.git", "abc1234")


class Honesty(unittest.TestCase):
    """La frontière code-écrit / preuve-cluster est DÉCLARÉE (ADR 0034)."""

    def test_banc_todo_non_empty(self):
        self.assertTrue(seed.banc_todo())
        self.assertTrue(all(isinstance(t, str) and t for t in seed.banc_todo()))


if __name__ == "__main__":
    unittest.main()
