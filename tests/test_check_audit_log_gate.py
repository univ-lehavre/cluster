"""Tests du garde-fou audit-log par-play (ADR 0108/0053 / ADR 0017 : logique testée).

unittest (stdlib) — c'est ce qu'utilise le dépôt (`test:python` =
`python -m unittest discover -s tests`). Les fonctions testées sont PURES : on leur
injecte des plays/playbooks en mémoire, donc aucun accès disque pour le cœur.

Couvre les invariants du garde-fou (POURQUOI Python remplace le bats) :
  1. Un play distant (`hosts: cloud`) SANS audit-log → ERREUR.
  2. Le même play AVEC audit-log en pre_tasks → OK.
  3. Un play `localhost` (ou template non résolu) SANS audit-log → OK (pas de SSH).
  4. Deux plays distants dont UN SEUL gardé → ERREUR (le cas que le bats ratait :
     comptage par fichier vs par play).
  5. `hosts` en LISTE (`[cloud, vm]`) est bien vu distant (autre angle mort du grep).

Une preuve d'ÉTAT RÉEL en plus (subprocess) : le check passe VERT sur l'état actuel
du dépôt (tous les plays distants ont leur audit-log).

Lancé par `python3 -m unittest discover -s tests` (cible `test:python` + CI).
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from check_audit_log_gate import (  # noqa: E402
    ERROR,
    WARNING,
    Finding,
    check_docs,
    check_play_has_audit_log,
    collect_role_imports,
    is_remote_play,
    load_yaml_docs,
    remote_plays,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SCRIPT = os.path.join(_REPO, "scripts", "check_audit_log_gate.py")


def has_error(findings):
    return any(f.level == ERROR for f in findings)


def _audit_pre_tasks(playbook_name="cri.yaml"):
    """pre_tasks minimales important audit-log (calque bootstrap/cri.yaml)."""
    return [
        {
            "name": "Audit-log — record playbook execution",
            "ansible.builtin.import_role": {"name": "audit-log"},
            "vars": {"audit_log_playbook": playbook_name},
        }
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Finding (dataclass-like)
# ─────────────────────────────────────────────────────────────────────────────
class FindingEquality(unittest.TestCase):
    def test_equality_and_hash(self):
        a = Finding(ERROR, "x")
        b = Finding(ERROR, "x")
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertNotEqual(a, Finding(WARNING, "x"))


# ─────────────────────────────────────────────────────────────────────────────
# is_remote_play / remote_plays — extraction des plays distants
# ─────────────────────────────────────────────────────────────────────────────
class IsRemotePlay(unittest.TestCase):
    def test_scalar_cloud_is_remote(self):
        self.assertTrue(is_remote_play({"hosts": "cloud"}))

    def test_scalar_all_and_control_are_remote(self):
        self.assertTrue(is_remote_play({"hosts": "all"}))
        self.assertTrue(is_remote_play({"hosts": "control"}))

    def test_localhost_is_not_remote(self):
        self.assertFalse(is_remote_play({"hosts": "localhost"}))

    def test_workers_alone_is_not_remote(self):
        # workers n'est pas dans l'unité de garde (cf. bats remplacé).
        self.assertFalse(is_remote_play({"hosts": "workers"}))

    def test_templated_host_is_not_remote(self):
        # "{{ dataops_k8s_host | default('localhost') }}" → défaut localhost.
        self.assertFalse(is_remote_play({"hosts": "{{ dataops_k8s_host | default('localhost') }}"}))

    def test_list_hosts_with_cloud_is_remote(self):
        # Forme LISTE (os-upgrade.yaml) que le grep du bats ratait.
        self.assertTrue(is_remote_play({"hosts": ["cloud", "vm"]}))

    def test_list_hosts_without_remote_group_is_not_remote(self):
        self.assertFalse(is_remote_play({"hosts": ["workers", "vm"]}))

    def test_no_hosts_key_is_not_remote(self):
        self.assertFalse(is_remote_play({"name": "play sans hosts"}))


class RemotePlays(unittest.TestCase):
    def test_playbook_top_level_list_of_plays(self):
        # Un playbook Ansible est une LISTE de plays au top-level.
        playbook = [
            {"name": "remote", "hosts": "cloud"},
            {"name": "local", "hosts": "localhost"},
            {"name": "ctrl", "hosts": "control"},
        ]
        plays = remote_plays([playbook])
        self.assertEqual([p["name"] for p in plays], ["remote", "ctrl"])

    def test_multi_play_dataops_shape(self):
        # dataops.yaml : play 1 localhost, play 2 cloud, play 3 localhost.
        playbook = [
            {"name": "étape cluster", "hosts": "{{ dataops_k8s_host | default('localhost') }}"},
            {"name": "étape nœuds", "hosts": "cloud"},
            {"name": "étape applicative", "hosts": "{{ dataops_k8s_host | default('localhost') }}"},
        ]
        plays = remote_plays([playbook])
        self.assertEqual([p["name"] for p in plays], ["étape nœuds"])


# ─────────────────────────────────────────────────────────────────────────────
# collect_role_imports — scan de l'arbre YAML d'UN play (pre_tasks/block/…)
# ─────────────────────────────────────────────────────────────────────────────
class CollectRoleImports(unittest.TestCase):
    def test_import_role_in_pre_tasks(self):
        play = {"hosts": "cloud", "pre_tasks": _audit_pre_tasks()}
        self.assertIn("audit-log", collect_role_imports(play))

    def test_nested_include_role_in_block(self):
        play = {
            "hosts": "cloud",
            "tasks": [
                {"name": "guarded", "block": [{"ansible.builtin.include_role": {"name": "x"}}]}
            ],
        }
        self.assertEqual(collect_role_imports(play), {"x"})

    def test_short_key_without_collection_prefix(self):
        play = {"hosts": "cloud", "pre_tasks": [{"import_role": {"name": "audit-log"}}]}
        self.assertIn("audit-log", collect_role_imports(play))

    def test_load_yaml_docs_keeps_lists(self):
        # Régression : un top-level liste (playbook) ne doit PAS être filtré.
        docs = load_yaml_docs("- name: play\n  hosts: cloud\n")
        self.assertEqual(len(docs), 1)
        self.assertIsInstance(docs[0], list)


# ─────────────────────────────────────────────────────────────────────────────
# check_play_has_audit_log — cœur du garde par-play
# ─────────────────────────────────────────────────────────────────────────────
class CheckPlayHasAuditLog(unittest.TestCase):
    def test_remote_play_without_audit_log_is_error(self):
        play = {"name": "étape nœuds", "hosts": "cloud", "tasks": [{"name": "mutate"}]}
        out = check_play_has_audit_log(play, "bootstrap/x.yaml")
        self.assertTrue(has_error(out))
        self.assertIn("audit-log", out[0].message)

    def test_remote_play_with_audit_log_is_ok(self):
        play = {"name": "cri", "hosts": "cloud", "pre_tasks": _audit_pre_tasks()}
        self.assertEqual(check_play_has_audit_log(play, "bootstrap/cri.yaml"), [])


# ─────────────────────────────────────────────────────────────────────────────
# check_docs — orchestration PAR PLAY (le cas que le bats ratait)
# ─────────────────────────────────────────────────────────────────────────────
class CheckDocs(unittest.TestCase):
    def test_cloud_play_without_audit_log_is_error(self):
        playbook = [{"name": "étape nœuds", "hosts": "cloud", "tasks": [{"name": "mutate"}]}]
        out = check_docs([playbook], "bootstrap/x.yaml")
        self.assertTrue(has_error(out))

    def test_cloud_play_with_audit_log_is_ok(self):
        playbook = [{"name": "cri", "hosts": "cloud", "pre_tasks": _audit_pre_tasks()}]
        self.assertEqual(check_docs([playbook], "bootstrap/cri.yaml"), [])

    def test_localhost_play_without_audit_log_is_ok(self):
        # localhost n'est PAS gardé (pas de SSH distant).
        playbook = [{"name": "plateforme", "hosts": "localhost", "tasks": [{"name": "k8s"}]}]
        self.assertEqual(check_docs([playbook], "bootstrap/local.yaml"), [])

    def test_two_remote_plays_one_guarded_is_error(self):
        # LE cas que le bats ratait : comptage par fichier (2 plays distants, 1
        # audit-log) pouvait passer ; le comptage PAR PLAY attrape le play nu.
        playbook = [
            {"name": "gardé", "hosts": "cloud", "pre_tasks": _audit_pre_tasks()},
            {"name": "nu", "hosts": "control", "tasks": [{"name": "mutate"}]},
        ]
        out = check_docs([playbook], "bootstrap/deux-plays.yaml")
        self.assertTrue(has_error(out))
        self.assertEqual(len([f for f in out if f.level == ERROR]), 1)
        self.assertIn("nu", out[0].message)

    def test_two_remote_plays_both_guarded_is_ok(self):
        playbook = [
            {"name": "a", "hosts": "cloud", "pre_tasks": _audit_pre_tasks()},
            {"name": "b", "hosts": "control", "pre_tasks": _audit_pre_tasks()},
        ]
        self.assertEqual(check_docs([playbook], "bootstrap/deux.yaml"), [])

    def test_list_hosts_cloud_without_audit_log_is_error(self):
        # Forme liste que le grep du bats ratait → doit être gardée.
        playbook = [{"name": "os-upgrade", "hosts": ["cloud", "vm"], "tasks": [{"name": "x"}]}]
        out = check_docs([playbook], "bootstrap/os-upgrade.yaml")
        self.assertTrue(has_error(out))


# ─────────────────────────────────────────────────────────────────────────────
# PREUVE D'ÉTAT RÉEL (subprocess) — vert sur l'état sain du dépôt
# ─────────────────────────────────────────────────────────────────────────────
class RealStateGreen(unittest.TestCase):
    def test_check_passes_on_current_state(self):
        # Le check DOIT sortir 0 sur l'état actuel (tous les plays distants gardés).
        proc = subprocess.run(
            [sys.executable, _SCRIPT],
            cwd=_REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=f"stderr:\n{proc.stderr}")
        self.assertIn("OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
