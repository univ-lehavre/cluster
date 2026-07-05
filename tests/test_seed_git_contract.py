"""Test de CONTRAT du seed git prod (`_git_push_atlas_tree` de scripts/topology.py).

Filet institué par ADR 0104 §4 (tests de contrat code↔config-prod ; fichier
`docs/decisions/0104-doctrine-preuve-deux-etages-banc-logique-prod-integration.md`).
Exécute le VRAI flux git local de
`_git_push_atlas_tree` — clone → `checkout -B main <rev>` → substitution du digest
dans l'overlay prod → **commit** — contre un dépôt atlas JETABLE, avec un overlay
prod portant les placeholders. On intercepte au bord réseau (le `git push` HTTP
vers Gitea), après quoi on inspecte l'ARBRE COMMITTÉ du clone.

Aurait attrapé les 3 bugs seed prod (#578), invisibles au banc (overlay bench sans
placeholder → substitution no-op → aucun des bugs ne se déclenche) :

  1. `checkout -B main <rev>` (git récent REFUSE `branch -f` sur la branche courante) ;
  2. la substitution DOIT être COMMITTÉE avant le push (sinon l'arbre BRUT est poussé
     → placeholders non substitués → InvalidImageName) ;
  3. (côté render_code_location_declaration, déjà couvert par test_seed.py) le
     targetRevision suit `main` (l'arbre substitué force-pushé).

unittest stdlib, HERMÉTIQUE : aucun cluster, aucun kubectl, aucun Gitea — seul git
local (dépôts temporaires). Le push réseau est neutralisé et son moment sert de
point d'inspection de l'arbre committé.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_SPEC = importlib.util.spec_from_file_location(
    "topology_seed_contract", os.path.join(_ROOT, "scripts", "topology.py")
)
topo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(topo)

from nestor.seed import CodeLocationSpec, SeedConfig  # noqa: E402


def _git(*argv, cwd=None):
    """git local, check=True (les fixtures DOIVENT réussir)."""
    return subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True, text=True)


def _make_atlas_repo(workdir: str, *, on_wrong_branch: bool) -> str:
    """Fabrique un dépôt atlas jetable avec un overlay prod citation à placeholders.

    Renvoie (repo_dir, revision_sha). ``on_wrong_branch=True`` reproduit la
    PRÉCONDITION du bug #1 : la révision cible n'est PAS la tête de `main` (une
    commit ultérieure existe sur main) → `branch -f main` REFUSERAIT ; `checkout -B`
    doit réussir.
    """
    repo = os.path.join(workdir, "atlas-src")
    os.makedirs(repo)
    _git("init", "--quiet", "-b", "main", cwd=repo)
    _git("config", "user.email", "t@example-org.lan", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    overlay = os.path.join(repo, "dataops", "citation-dagster", "deploy", "overlays", "prod")
    os.makedirs(overlay)
    # Overlay prod AVEC placeholders (comme le vrai overlay prod atlas).
    with open(os.path.join(overlay, "patch-image.yaml"), "w", encoding="utf-8") as fh:
        fh.write(
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            "        - name: grpc\n"
            "          image: __CITATION_IMAGE__\n"
            "          env:\n"
            "            - name: DAGSTER_CURRENT_IMAGE\n"
            "              value: __CITATION_IMAGE__\n"
        )
    _git("add", "-A", cwd=repo)
    _git("commit", "--quiet", "-m", "overlay prod à placeholders", cwd=repo)
    revision = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    if on_wrong_branch:
        # Un commit POSTÉRIEUR sur main : la révision cible n'est plus la tête.
        with open(os.path.join(repo, "AFTER.txt"), "w", encoding="utf-8") as fh:
            fh.write("commit postérieur\n")
        _git("add", "-A", cwd=repo)
        _git("commit", "--quiet", "-m", "commit postérieur (révision != tête main)", cwd=repo)
    return repo, revision


class SeedGitContract(unittest.TestCase):
    def _run_seed_capture(self, on_wrong_branch: bool):
        """Joue `_git_push_atlas_tree`, intercepte le push, renvoie l'arbre committé du clone.

        Le vrai `_git` (scripts/topology.py) fait les ops locales ; on l'enveloppe pour
        capturer le clone au moment du `push` (avant nettoyage du tempdir) et neutraliser
        le réseau. `_kubectl` (port du svc gitea) et `_seed_port_forward` sont stubés.
        """
        captured = {}
        real_git = topo.subprocess.run  # _git interne appelle subprocess.run(["git", ...])

        def fake_run(cmd, *a, **kw):
            # Intercepte le `git push …` : on capture l'arbre committé du clone AVANT de
            # laisser le tempdir se nettoyer, puis on renvoie un succès simulé.
            if len(cmd) >= 2 and cmd[0] == "git" and "push" in cmd:
                # cmd = ["git", "-C", <clone>, "push", "--force", <url>, "main:main"]
                clone = cmd[cmd.index("-C") + 1]
                captured["head_msg"] = real_git(
                    ["git", "-C", clone, "log", "-1", "--pretty=%s"],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                captured["main_head"] = real_git(
                    ["git", "-C", clone, "rev-parse", "main"],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                # Parent de la tête : après `checkout -B main <rev>` + commit de
                # substitution, main = <commit seed> dont le PARENT est <rev>.
                captured["main_parent"] = real_git(
                    ["git", "-C", clone, "rev-parse", "main^"],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                # Contenu COMMITTÉ (HEAD) de l'overlay — pas le working-tree.
                captured["committed_overlay"] = real_git(
                    [
                        "git",
                        "-C",
                        clone,
                        "show",
                        "HEAD:dataops/citation-dagster/deploy/overlays/prod/patch-image.yaml",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return real_git(cmd, *a, **kw)

        with tempfile.TemporaryDirectory() as wd:
            repo, revision = _make_atlas_repo(wd, on_wrong_branch=on_wrong_branch)
            config = SeedConfig(
                atlas_repo_dir=repo,
                code_locations=(
                    CodeLocationSpec(
                        name="citation",
                        revision=revision,
                        image_digest="sha256:deadbeefcafe",
                    ),
                ),
            )
            with (
                mock.patch.object(topo.subprocess, "run", side_effect=fake_run),
                mock.patch.object(topo, "_seed_port_forward", return_value=(12345, mock.Mock())),
                mock.patch.object(
                    topo,
                    "_kubectl",
                    return_value=subprocess.CompletedProcess([], 0, stdout="3000", stderr=""),
                ),
            ):
                ok = topo._git_push_atlas_tree(config, ns="gitea", admin_pw="pw")
            return ok, revision, captured

    def test_pushes_committed_substituted_tree_from_target_revision(self):
        """CONTRAT : l'arbre POUSSÉ est committé, digest substitué, main sur la révision.

        Reproduit la précondition du bug #1 (révision ≠ tête main → `branch -f` refuserait)
        et vérifie le fix des bugs #1 (`checkout -B`) et #2 (substitution committée)."""
        ok, revision, cap = self._run_seed_capture(on_wrong_branch=True)
        self.assertTrue(ok, "le seed doit réussir (push simulé OK)")
        # Bug #1 — `checkout -B main <rev>` : main est basé SUR la révision cible (son
        # PARENT est <rev>), et NON la tête d'origine (le commit postérieur). Sans
        # `checkout -B`, `branch -f main` aurait refusé (branche courante) → seed KO.
        self.assertEqual(cap["main_parent"], revision)
        # Bug #2 — la substitution est COMMITTÉE (un commit seed existe en tête)...
        self.assertIn("injecte les digests", cap["head_msg"])
        # ...et l'arbre committé (HEAD) porte le digest substitué, PLUS aucun placeholder.
        self.assertIn("sha256:deadbeefcafe", cap["committed_overlay"])
        self.assertIn("registry:80/citation-dagster@sha256:deadbeefcafe", cap["committed_overlay"])
        self.assertNotIn("__CITATION_IMAGE__", cap["committed_overlay"])

    def test_checkout_b_succeeds_even_when_revision_is_head(self):
        """`checkout -B` est idempotent : réussit AUSSI quand la révision EST déjà la tête."""
        ok, revision, cap = self._run_seed_capture(on_wrong_branch=False)
        self.assertTrue(ok)
        # main = commit de substitution ; son parent = la révision cible.
        self.assertEqual(cap["main_parent"], revision)
        self.assertIn("sha256:deadbeefcafe", cap["committed_overlay"])


if __name__ == "__main__":
    unittest.main()
