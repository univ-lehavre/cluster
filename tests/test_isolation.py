"""Tests de la garde d'isolation de cible Ansible (nestor/isolation.py, ADR 0053).

Pur : dict d'inventaire + intention → verdict. Reproduit la FAILLE constatée (intention
banc `lima` sur un inventaire prod → REFUS) et les cas sûrs. Valeurs génériques (ADR
0023) : nœuds prod `cp1`/`node1…`, plage `10.0.0.0/22`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.isolation import (  # noqa: E402
    IsolationError,
    classify_inventory_target,
    resolve_node_target,
)

# Inventaire PROD (forme de bootstrap/hosts.yaml) : groupe cloud, target_kind prod,
# hôtes génériques cp1/node1-3 (ADR 0023) + un control_host localhost.
_PROD_INV = {
    "cloud": {
        "children": {"control": None, "workers": None},
        "vars": {"ansible_user": "debian", "target_kind": "prod"},
    },
    "control": {"hosts": {"cp1": {"ansible_host": "10.0.0.11"}}},
    "workers": {
        "hosts": {
            "node1": {"ansible_host": "10.0.0.12"},
            "node2": {"ansible_host": "10.0.0.13"},
            "node3": {"ansible_host": "10.0.0.14"},
        }
    },
    "control_host": {"hosts": {"localhost": {"ansible_connection": "local"}}},
}

# Inventaire BANC Lima : mêmes groupes, target_kind lima, hôtes locaux (port-forward).
_BANC_INV = {
    "cloud": {
        "children": {"control": None, "workers": None},
        "vars": {"target_kind": "lima"},
    },
    "control": {"hosts": {"node1": {"ansible_host": "127.0.0.1"}}},
    "workers": {"hosts": {"node2": {"ansible_host": "127.0.0.1"}}},
    "control_host": {"hosts": {"localhost": {"ansible_connection": "local"}}},
}


class TheBreach(unittest.TestCase):
    """Le scénario exact qui a frappé la prod : intention banc sur inventaire prod."""

    def test_lima_intent_on_prod_inventory_is_refused(self):
        ok, raison = classify_inventory_target(_PROD_INV, "lima")
        self.assertFalse(ok)  # REFUS — c'est ce qui aurait stoppé `next dataops`
        self.assertIn("prod", raison)
        self.assertIn("cp1", raison)  # nomme les hôtes prod menacés

    def test_prod_intent_on_prod_inventory_is_allowed(self):
        # Usage prod légitime : intention prod + inventaire prod → SÛR.
        ok, _ = classify_inventory_target(_PROD_INV, "prod")
        self.assertTrue(ok)


class SafeCases(unittest.TestCase):
    def test_lima_intent_on_banc_inventory_is_allowed(self):
        # Banc Lima : hôtes en port-forward localhost (127.0.0.1) → règle « local » :
        # aucun SSH distant possible → sûr (peu importe le marqueur).
        ok, raison = classify_inventory_target(_BANC_INV, "lima")
        self.assertTrue(ok)
        self.assertIn("local", raison)

    def test_lima_marker_concordant_with_remote_lima_hosts(self):
        # Banc avec hôtes distants NON locaux mais target_kind=lima concordant → sûr
        # (cas d'un banc Lima exposant des IP non-127 ; le marqueur tranche).
        inv = {
            "cloud": {
                "vars": {"target_kind": "lima"},
                "hosts": {"vm1": {"ansible_host": "10.0.0.5"}},
            }
        }
        ok, raison = classify_inventory_target(inv, "lima")
        self.assertTrue(ok)
        self.assertIn("concordant", raison)

    def test_local_only_inventory_always_safe(self):
        # Que des hôtes locaux → aucun SSH possible → sûr quelle que soit l'intention.
        inv = {"control_host": {"hosts": {"localhost": {"ansible_connection": "local"}}}}
        self.assertTrue(classify_inventory_target(inv, "lima")[0])
        self.assertTrue(classify_inventory_target(inv, "prod")[0])

    def test_empty_inventory_is_safe(self):
        self.assertTrue(classify_inventory_target({}, "lima")[0])


class FailClosed(unittest.TestCase):
    """Défaut prudent : sans marqueur prouvant la cible, on REFUSE (avec hôtes distants)."""

    def test_no_marker_with_remote_hosts_is_refused(self):
        inv = {"cloud": {"hosts": {"somehost": {"ansible_host": "192.0.2.9"}}}}
        ok, raison = classify_inventory_target(inv, "lima")
        self.assertFalse(ok)
        self.assertIn("SANS marqueur", raison)

    def test_marker_mismatch_is_refused(self):
        # target_kind=prod mais intention lima → refus même si on tentait un montage banc.
        ok, _ = classify_inventory_target(_PROD_INV, "lima")
        self.assertFalse(ok)

    def test_host_by_name_not_ip_still_detected(self):
        # Un hôte distant nommé (sans ansible_host) compte comme distant.
        inv = {
            "cloud": {
                "vars": {"target_kind": "prod"},
                "hosts": {"prodbox": {}},
            }
        }
        self.assertFalse(classify_inventory_target(inv, "lima")[0])


# Inventaire BANC réel (forme générée par write_inventory) : ansible_host lima-<vm> +
# ansible_ssh_common_args -F ~/.lima/<vm>/ssh.config, user lima.
_BANC_GEN_INV = {
    "cloud": {
        "children": {"control": None, "workers": None},
        "vars": {"ansible_user": "lima", "target_kind": "lima"},
    },
    "control": {
        "hosts": {
            "node1": {
                "ansible_host": "lima-node1",
                "ansible_ssh_common_args": "-F /home/u/.lima/node1/ssh.config",
            }
        }
    },
    "workers": {"hosts": {"node2": {"ansible_host": "lima-node2"}}},
    "control_host": {"hosts": {"localhost": {"ansible_connection": "local"}}},
}


class ResolveNodeTarget(unittest.TestCase):
    """ADR 0081 : résoudre <node> → cible (transport/hôte/user/ssh-args) depuis l'inventaire."""

    def test_lima_node_resolves_to_limactl_transport(self):
        t = resolve_node_target(_BANC_GEN_INV, "node1")
        self.assertEqual(t.transport, "lima")  # banc → limactl, pas SSH
        # en lima, le host = le NOM D'INSTANCE limactl (= nom du nœud), PAS ansible_host
        # (lima-node1 est le hostname SSH ; `limactl shell lima-node1` n'existe pas).
        self.assertEqual(t.host, "node1")
        self.assertEqual(t.user, "lima")  # remonté des vars du groupe cloud
        self.assertEqual(t.ssh_args, "-F /home/u/.lima/node1/ssh.config")

    def test_prod_node_resolves_to_ssh_transport(self):
        t = resolve_node_target(_PROD_INV, "cp1")
        self.assertEqual(t.transport, "ssh")  # prod → SSH direct
        self.assertEqual(t.host, "10.0.0.11")  # ansible_host (IP générique, ADR 0023)
        self.assertEqual(t.user, "debian")  # vars cloud

    def test_node_in_workers_group_is_found(self):
        # la résolution traverse tout l'arbre de groupes, pas que `control`.
        t = resolve_node_target(_PROD_INV, "node2")
        self.assertEqual(t.host, "10.0.0.13")

    def test_host_attr_user_overrides_group_var(self):
        inv = {
            "cloud": {"vars": {"ansible_user": "debian", "target_kind": "prod"}},
            "control": {"hosts": {"cp1": {"ansible_host": "10.0.0.9", "ansible_user": "root"}}},
        }
        self.assertEqual(resolve_node_target(inv, "cp1").user, "root")  # l'hôte prime

    def test_host_fallback_when_no_ansible_host(self):
        # sans ansible_host, on retombe sur le NOM du nœud (jamais deviner une IP).
        inv = {"cloud": {"vars": {"target_kind": "prod"}}, "control": {"hosts": {"cp1": {}}}}
        self.assertEqual(resolve_node_target(inv, "cp1").host, "cp1")

    def test_unknown_node_raises(self):
        with self.assertRaises(IsolationError):
            resolve_node_target(_PROD_INV, "ghost")


if __name__ == "__main__":
    unittest.main()
