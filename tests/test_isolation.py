"""Tests de la garde d'isolation de cible Ansible (nestor/isolation.py, ADR 0053, 0108).

Pur : dict d'inventaire + IDENTITÉ visée (stack_id) → verdict. Reproduit la FAILLE du
2026-06-16 (une action visant une instance sur l'inventaire d'une AUTRE instance → REFUS)
et les cas sûrs. Valeurs génériques (ADR 0023) : nœuds `cp1`/`node1…`, plage `10.0.0.0/22`.
Depuis l'ADR 0108 : la garde compare le `stack_id` (identité), le transport vient d'un
marqueur `transport:` dédié, et `endpoint_matches_stack` prouve le chemin kubectl.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor.isolation import (  # noqa: E402
    IsolationError,
    classify_inventory_target,
    endpoint_matches_stack,
    resolve_node_target,
)

# Inventaire de l'instance massive « dirqual » : groupe cloud, stack_id dirqual, transport
# ssh, hôtes génériques cp1/node1-3 (ADR 0023) + un control_host localhost.
_MASSIVE_INV = {
    "cloud": {
        "children": {"control": None, "workers": None},
        "vars": {"ansible_user": "debian", "stack_id": "dirqual", "transport": "ssh"},
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

# Inventaire d'une instance locale (Lima) : mêmes groupes, stack_id local, transport lima,
# hôtes en port-forward localhost.
_LOCAL_INV = {
    "cloud": {
        "children": {"control": None, "workers": None},
        "vars": {"stack_id": "banc-citation", "transport": "lima"},
    },
    "control": {"hosts": {"node1": {"ansible_host": "127.0.0.1"}}},
    "workers": {"hosts": {"node2": {"ansible_host": "127.0.0.1"}}},
    "control_host": {"hosts": {"localhost": {"ansible_connection": "local"}}},
}


class TheBreach(unittest.TestCase):
    """Le scénario du 2026-06-16 : une action visant une instance sur l'inventaire d'une
    AUTRE instance de la même classe."""

    def test_other_instance_intent_on_massive_inventory_is_refused(self):
        # Intention « banc-citation » sur l'inventaire de « dirqual » → REFUS (ce qui aurait
        # stoppé le montage qui a reconfiguré containerd sur l'instance massive).
        ok, raison = classify_inventory_target(_MASSIVE_INV, "banc-citation")
        self.assertFalse(ok)
        self.assertIn("dirqual", raison)  # nomme le stack_id de l'inventaire réel
        self.assertIn("cp1", raison)  # nomme les hôtes menacés

    def test_same_instance_intent_is_allowed(self):
        # Usage légitime : intention dirqual + inventaire dirqual → SÛR.
        ok, _ = classify_inventory_target(_MASSIVE_INV, "dirqual")
        self.assertTrue(ok)


class SafeCases(unittest.TestCase):
    def test_local_hosts_inventory_is_allowed(self):
        # Hôtes en port-forward localhost (127.0.0.1) → règle « local » : aucun SSH distant
        # possible → sûr (peu importe l'identité visée).
        ok, raison = classify_inventory_target(_LOCAL_INV, "banc-citation")
        self.assertTrue(ok)
        self.assertIn("local", raison)

    def test_stack_id_concordant_with_remote_hosts(self):
        # Inventaire avec hôtes distants NON locaux mais stack_id concordant → sûr.
        inv = {
            "cloud": {
                "vars": {"stack_id": "ovh1", "transport": "ssh"},
                "hosts": {"vm1": {"ansible_host": "10.0.0.5"}},
            }
        }
        ok, raison = classify_inventory_target(inv, "ovh1")
        self.assertTrue(ok)
        self.assertIn("concordant", raison)

    def test_local_only_inventory_always_safe(self):
        # Que des hôtes locaux → aucun SSH possible → sûr quelle que soit l'identité visée.
        inv = {"control_host": {"hosts": {"localhost": {"ansible_connection": "local"}}}}
        self.assertTrue(classify_inventory_target(inv, "banc-citation")[0])
        self.assertTrue(classify_inventory_target(inv, "dirqual")[0])

    def test_empty_inventory_is_safe(self):
        self.assertTrue(classify_inventory_target({}, "banc-citation")[0])

    def test_tunneled_localhost_is_not_trusted_as_local(self):
        # revue #5 : un 127.0.0.1 avec ansible_port (port-forward) OU un ProxyCommand cache un
        # tunnel vers du distant → ne PAS le classer local, sinon la règle 1 laisserait passer.
        for attrs in (
            {"ansible_host": "127.0.0.1", "ansible_port": 2222},
            {"ansible_host": "127.0.0.1", "ansible_ssh_common_args": "-o ProxyCommand=ssh bastion"},
            {"ansible_host": "127.0.0.1", "ansible_ssh_common_args": "-J bastion@10.0.0.1"},
        ):
            inv = {"cloud": {"vars": {"stack_id": "x"}, "hosts": {"tunnel": attrs}}}
            # sans marqueur concordant (intention ≠ x) → l'hôte tunnelé compte comme distant → refus
            ok, _ = classify_inventory_target(inv, "autre")
            self.assertFalse(ok, f"tunnel non détecté pour {attrs}")

    def test_plain_lima_localhost_stays_local(self):
        # Non-régression : le banc Lima nominal (lima-<vm>, pas d'ansible_port ni ProxyCommand)
        # reste classé local — on ne le refuse pas faussement.
        inv = {
            "control_host": {"hosts": {"localhost": {"ansible_connection": "local"}}},
            "control": {"hosts": {"node1": {"ansible_host": "127.0.0.1"}}},
        }
        self.assertTrue(classify_inventory_target(inv, "banc")[0])


class FailClosed(unittest.TestCase):
    """Défaut prudent : sans marqueur prouvant l'instance, on REFUSE (avec hôtes distants)."""

    def test_no_marker_with_remote_hosts_is_refused(self):
        inv = {"cloud": {"hosts": {"somehost": {"ansible_host": "192.0.2.9"}}}}
        ok, raison = classify_inventory_target(inv, "banc-citation")
        self.assertFalse(ok)
        self.assertIn("SANS marqueur", raison)

    def test_marker_mismatch_is_refused(self):
        # stack_id=dirqual mais intention banc-citation → refus.
        ok, _ = classify_inventory_target(_MASSIVE_INV, "banc-citation")
        self.assertFalse(ok)

    def test_host_by_name_not_ip_still_detected(self):
        # Un hôte distant nommé (sans ansible_host) compte comme distant.
        inv = {
            "cloud": {
                "vars": {"stack_id": "dirqual", "transport": "ssh"},
                "hosts": {"remotebox": {}},
            }
        }
        self.assertFalse(classify_inventory_target(inv, "banc-citation")[0])


class EndpointMatchesStack(unittest.TestCase):
    """Preuve d'identité du chemin kubectl (ADR 0108) : le kubeconfig courant vise-t-il bien
    l'instance ? Cran 1 = contexte estampillé stack_id (cardinal) ; cran 2 = endpoint."""

    def test_concordant_context_and_endpoint(self):
        ok, _ = endpoint_matches_stack(
            "dirqual", "https://10.0.0.11:6443", "dirqual", "10.0.0.11:6443"
        )
        self.assertTrue(ok)

    def test_foreign_context_is_refused(self):
        # ~/.kube/config étranger : contexte kubernetes-admin@kubernetes ≠ stack_id → REFUS
        # (c'est ce qui remplace l'échappatoire KUBECONFIG d'ADR 0065).
        ok, raison = endpoint_matches_stack(
            "kubernetes-admin@kubernetes", "https://10.0.0.11:6443", "dirqual", "10.0.0.11:6443"
        )
        self.assertFalse(ok)
        self.assertIn("dirqual", raison)

    def test_no_current_context_is_refused(self):
        ok, _ = endpoint_matches_stack(None, "https://x:6443", "dirqual", "10.0.0.11:6443")
        self.assertFalse(ok)

    def test_endpoint_mismatch_is_refused(self):
        # Bon contexte mais endpoint discordant (kubeconfig d'une autre instance renommé) → REFUS.
        ok, raison = endpoint_matches_stack(
            "dirqual", "https://10.9.9.9:6443", "dirqual", "10.0.0.11:6443"
        )
        self.assertFalse(ok)
        self.assertIn("endpoint", raison)

    def test_placeholder_endpoint_falls_back_to_context_only(self):
        # Endpoint placeholder (cluster-api) : le cran 2 est neutre, seul le contexte protège.
        ok, _ = endpoint_matches_stack(
            "local1", "https://127.0.0.1:6443", "local1", "cluster-api:6443"
        )
        self.assertTrue(ok)

    def test_local_endpoint_not_discriminant(self):
        # Deux instances locales ont le même 127.0.0.1:6443 ; seul le contexte les distingue.
        ok, _ = endpoint_matches_stack(
            "local1", "https://127.0.0.1:6443", "local1", "127.0.0.1:6443"
        )
        self.assertTrue(ok)
        ok2, _ = endpoint_matches_stack(
            "local1", "https://127.0.0.1:6443", "local2", "127.0.0.1:6443"
        )
        self.assertFalse(ok2)  # contexte local1 ≠ instance local2 visée


# Inventaire local réel (forme générée) : ansible_host lima-<vm> +
# ansible_ssh_common_args -F ~/.lima/<vm>/ssh.config, user lima, transport lima.
_LOCAL_GEN_INV = {
    "cloud": {
        "children": {"control": None, "workers": None},
        "vars": {"ansible_user": "lima", "stack_id": "banc-citation", "transport": "lima"},
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
    """ADR 0081, 0108 : résoudre <node> → cible (transport/hôte/user/ssh-args) depuis
    l'inventaire ; le transport vient du marqueur `transport:` dédié."""

    def test_lima_transport_marker_resolves_to_limactl(self):
        t = resolve_node_target(_LOCAL_GEN_INV, "node1")
        self.assertEqual(t.transport, "lima")  # marqueur transport=lima → limactl, pas SSH
        # en lima, le host = le NOM D'INSTANCE limactl (= nom du nœud), PAS ansible_host.
        self.assertEqual(t.host, "node1")
        self.assertEqual(t.user, "lima")  # remonté des vars du groupe cloud
        self.assertEqual(t.ssh_args, "-F /home/u/.lima/node1/ssh.config")

    def test_ssh_transport_marker_resolves_to_ssh(self):
        t = resolve_node_target(_MASSIVE_INV, "cp1")
        self.assertEqual(t.transport, "ssh")  # marqueur transport=ssh → SSH direct
        self.assertEqual(t.host, "10.0.0.11")  # ansible_host (IP générique, ADR 0023)
        self.assertEqual(t.user, "debian")  # vars cloud

    def test_no_transport_marker_defaults_to_ssh(self):
        # Défaut prudent : sans marqueur transport, on retombe sur SSH direct.
        inv = {
            "cloud": {"vars": {"stack_id": "x"}},
            "control": {"hosts": {"cp1": {"ansible_host": "10.0.0.9"}}},
        }
        self.assertEqual(resolve_node_target(inv, "cp1").transport, "ssh")

    def test_node_in_workers_group_is_found(self):
        # la résolution traverse tout l'arbre de groupes, pas que `control`.
        t = resolve_node_target(_MASSIVE_INV, "node2")
        self.assertEqual(t.host, "10.0.0.13")

    def test_host_attr_user_overrides_group_var(self):
        inv = {
            "cloud": {
                "vars": {"ansible_user": "debian", "stack_id": "dirqual", "transport": "ssh"}
            },
            "control": {"hosts": {"cp1": {"ansible_host": "10.0.0.9", "ansible_user": "root"}}},
        }
        self.assertEqual(resolve_node_target(inv, "cp1").user, "root")  # l'hôte prime

    def test_host_fallback_when_no_ansible_host(self):
        # sans ansible_host, on retombe sur le NOM du nœud (jamais deviner une IP).
        inv = {
            "cloud": {"vars": {"stack_id": "x", "transport": "ssh"}},
            "control": {"hosts": {"cp1": {}}},
        }
        self.assertEqual(resolve_node_target(inv, "cp1").host, "cp1")

    def test_unknown_node_raises(self):
        with self.assertRaises(IsolationError):
            resolve_node_target(_MASSIVE_INV, "ghost")


class NoStaticHostsYaml(unittest.TestCase):
    """Garde-fou anti-régression (ADR 0098) : `bootstrap/hosts.yaml` n'a plus d'existence
    persistante — l'inventaire est DÉRIVÉ de la topologie active (`nestor ansible`). Aucun
    code/config ne doit réintroduire le vecteur de l'incident Rook-Ceph : un
    `ansible-playbook -i …/hosts.yaml` ou `inventory = …/hosts.yaml`. Les commentaires/docs
    qui EXPLIQUENT l'incident (ADR, docstrings) sont autorisés — on ne scanne que les gestes
    EXÉCUTABLES."""

    _ROOT = os.path.join(os.path.dirname(__file__), "..")
    # Fichiers de CODE/CONFIG exécutables (pas la doc/ADR qui décrivent l'incident).
    _SCANNED = (
        "scripts/topology.py",
        "scripts/nestor-exec",
        "bootstrap/ansible.cfg",
        "Justfile",  # supprimé : sa réapparition avec -i hosts.yaml doit échouer
    )
    # Motifs INTERDITS : une invocation/config qui POINTE un hosts.yaml réel.
    _FORBIDDEN = (
        re.compile(r"ansible-playbook\s+-i\s+\S*hosts\.yaml"),
        re.compile(r"^\s*inventory\s*=\s*\S*hosts\.yaml", re.MULTILINE),
        re.compile(r'default\s*=\s*["\']\S*hosts\.yaml["\']'),  # défaut d'argparse
    )

    @staticmethod
    def _executable_lines(path):
        """Rend le texte du fichier en NEUTRALISANT commentaires et chaînes/docstrings —
        pour ne scanner que le code EXÉCUTABLE. Les docstrings ADR qui CITENT le vecteur
        (`… -i bootstrap/hosts.yaml …` à titre pédagogique) ne doivent pas être des
        offenders. Pour un .py : tokenize (vire COMMENT + STRING). Sinon : vire les lignes
        commentaire `#` (suffit pour ansible.cfg/Justfile/nestor-exec)."""
        if path.endswith(".py"):
            import io
            import tokenize

            kept = []
            with open(path, encoding="utf-8") as f:
                src = f.read()
            try:
                for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                    if tok.type in (tokenize.COMMENT, tokenize.STRING):
                        continue
                    if tok.string.strip():
                        kept.append((tok.start[0], tok.string))
                return kept  # liste de (ligne, lexème) — sans commentaires ni chaînes
            except tokenize.TokenError:
                pass
        # non-python : lignes hors commentaire `#`
        out = []
        with open(path, encoding="utf-8") as f:
            for i, raw in enumerate(f, 1):
                code = raw.split("#", 1)[0]
                if code.strip():
                    out.append((i, code))
        return out

    def test_no_executable_pointing_to_static_hosts_yaml(self):
        offenders = []
        for rel in self._SCANNED:
            path = os.path.join(self._ROOT, rel)
            if not os.path.exists(path):
                continue  # ex. Justfile supprimé — OK
            for line_no, fragment in self._executable_lines(path):
                if "hosts.example.yaml" in fragment:
                    continue  # golden INERTE autorisé (filet ansible.cfg)
                if any(pat.search(fragment) for pat in self._FORBIDDEN):
                    offenders.append(f"{rel}:{line_no} → {fragment.strip()}")
        self.assertEqual(
            offenders,
            [],
            "Vecteur `-i hosts.yaml` réintroduit (ADR 0098 : passer par `nestor ansible`) :\n"
            + "\n".join(offenders),
        )

    def test_no_scanned_bash_script_reads_hosts_yaml(self):
        # Aucun script bash de tooling ne doit LIRE bootstrap/hosts.yaml (ex. ex-`env.sh`
        # détectait la prod ainsi — supprimé). On scanne les .sh d'orchestration.
        bash_dirs = (os.path.join(self._ROOT, "bench", "lima"),)
        offenders = []
        pat = re.compile(r"(?<!example\.)\bhosts\.yaml\b")
        for d in bash_dirs:
            for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                if not name.endswith(".sh"):
                    continue
                with open(os.path.join(d, name), encoding="utf-8") as f:
                    for i, raw in enumerate(f, 1):
                        line = raw.split("#", 1)[0]  # ignore les commentaires
                        if "hosts.example.yaml" in line:
                            continue
                        if pat.search(line):
                            offenders.append(f"bench/lima/{name}:{i} → {line.strip()}")
        self.assertEqual(
            offenders, [], "Script bash lisant hosts.yaml (ADR 0098) :\n" + "\n".join(offenders)
        )


if __name__ == "__main__":
    unittest.main()
