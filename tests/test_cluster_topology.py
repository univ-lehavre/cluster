"""Tests de l'outil déclaratif nestor (ADR 0056 / ADR 0017).

unittest (stdlib). Deux niveaux :
  - fonctions PURES (dérivations control/worker, validation) sur des dicts injectés ;
  - l'INVARIANT BYTE-IDENTIQUE (P1) : render(topologies/socle.example.yaml) ==
    bootstrap/hosts.example.yaml, octet pour octet (ADR 0056 §3).

Lancé par `python3 -m unittest discover tests` (cible `test:python` + CI).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestor import load_topology, render_prod_inventory  # noqa: E402
from nestor.generator import render_lima_inventory  # noqa: E402
from nestor.model import (  # noqa: E402
    TopologyError,
    topology_from_dict,
)
from nestor.profile import (  # noqa: E402
    consumes_storage,
    derive_osd_expected,
    derive_run_params,
    required_profiles,
    storage_params,
)

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _base(**over):
    """Un topology dict minimal valide, surchargeable."""
    d = {
        "catalog": {"topology": "multi-node-3"},
        "nodes": [
            {"name": "cp1", "roles": ["control"]},
            {"name": "node1", "roles": ["worker"]},
        ],
        "target_kind": "prod",
    }
    d.update(over)
    return d


class Derivations(unittest.TestCase):
    def test_control_and_worker_lists_in_order(self):
        t = topology_from_dict(
            _base(
                nodes=[
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "node1", "roles": ["worker"]},
                    {"name": "node2", "roles": ["worker"]},
                ]
            )
        )
        self.assertEqual(t.control_nodes, ["cp1"])
        self.assertEqual(t.worker_nodes, ["node1", "node2"])

    def test_hyperconverged_node_is_control_not_worker(self):
        # un nœud control+worker (hyperconvergence) vit dans le groupe control,
        # PAS dans workers (sinon double appartenance, ADR 0007).
        t = topology_from_dict(
            _base(
                nodes=[
                    {"name": "n1", "roles": ["control", "worker", "storage"]},
                    {"name": "n2", "roles": ["worker"]},
                ],
                # 1 seul control-plane ici → pas de control_plane_lb requis.
            )
        )
        self.assertEqual(t.control_nodes, ["n1"])
        self.assertEqual(t.worker_nodes, ["n2"])
        self.assertNotIn("n1", t.worker_nodes)
        # hyperconverged_nodes liste les control qui portent AUSSI worker (n1, pas n2).
        self.assertEqual(t.hyperconverged_nodes, ["n1"])

    def test_ha_detection(self):
        single = topology_from_dict(_base())
        self.assertFalse(single.is_ha_control_plane)


class Validation(unittest.TestCase):
    def test_unknown_role_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(nodes=[{"name": "x", "roles": ["master"]}]))

    def test_node_without_roles_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(nodes=[{"name": "x", "roles": []}]))

    def test_no_nodes_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(nodes=[]))

    def test_bad_target_kind_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(target_kind="staging"))

    def test_multi_cp_without_lb_rejected(self):
        # > 1 control-plane SANS control_plane_lb = invalide (VIP requise, 0047/0055)
        with self.assertRaises(TopologyError):
            topology_from_dict(
                _base(
                    nodes=[
                        {"name": "cp1", "roles": ["control"]},
                        {"name": "cp2", "roles": ["control"]},
                    ]
                )
            )

    def test_multi_cp_with_lb_accepted(self):
        t = topology_from_dict(
            _base(
                nodes=[
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "cp2", "roles": ["control"]},
                    {"name": "cp3", "roles": ["control"]},
                ],
                network={"control_plane_lb": {"mode": "kube-vip-arp"}},
            )
        )
        self.assertTrue(t.is_ha_control_plane)
        self.assertEqual(t.control_nodes, ["cp1", "cp2", "cp3"])

    def _ha_base(self, lb):
        # 3 CP hyperconvergés + un control_plane_lb donné — pour tester son `mode`.
        return _base(
            nodes=[
                {"name": "cp1", "roles": ["control", "worker"]},
                {"name": "cp2", "roles": ["control", "worker"]},
                {"name": "cp3", "roles": ["control", "worker"]},
            ],
            network={"control_plane_lb": lb},
            target_kind="lima",
        )

    def test_lb_unknown_mode_rejected(self):
        # Le `mode` du control_plane_lb doit être connu (sinon le delta d'outillage
        # kube-vip vs external n'est pas dérivable — ADR 0047/0055).
        with self.assertRaises(TopologyError):
            topology_from_dict(self._ha_base({"mode": "frobnicate"}))

    def test_lb_without_mode_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(self._ha_base({"ip": "10.0.0.9"}))

    def test_lb_valid_modes_accepted(self):
        for mode in ("kube-vip-arp", "kube-vip-lb", "external"):
            t = topology_from_dict(self._ha_base({"mode": mode}))
            self.assertEqual(t.network["control_plane_lb"]["mode"], mode)


class Kubeconfig(unittest.TestCase):
    """Champ `kubeconfig` de la topologie (ADR 0090) : cible de lecture déclarée."""

    def test_kubeconfig_parsed_when_declared(self):
        t = topology_from_dict(_base(kubeconfig="~/.kube/dirqual.config"))
        self.assertEqual(t.kubeconfig, "~/.kube/dirqual.config")

    def test_kubeconfig_defaults_to_none(self):
        # Absent → None (la résolution par défaut s'applique ailleurs, ADR 0090).
        self.assertIsNone(topology_from_dict(_base()).kubeconfig)


class Exposition(unittest.TestCase):
    """exposition.mode (ADR 0020/0071 réécrit) : mode UNIQUE `gateway` (en hostNetwork),
    `none` conservé, alias `lb-ipam`/`hostport` → `gateway`, défaut GLOBAL gateway."""

    def test_default_lima_is_gateway(self):
        # Renversement (ADR 0071) : gateway-hostNetwork reproductible partout, donc
        # le banc Lima n'a plus de défaut `hostport` propre — gateway par défaut.
        t = topology_from_dict(_base(target_kind="lima"))
        self.assertEqual(t.exposition_mode, "gateway")

    def test_default_prod_is_gateway(self):
        t = topology_from_dict(_base(target_kind="prod"))
        self.assertEqual(t.exposition_mode, "gateway")

    def test_lb_ipam_alias_resolves_to_gateway(self):
        t = topology_from_dict(_base(exposition={"mode": "lb-ipam"}))
        self.assertEqual(t.exposition_mode, "gateway")

    def test_hostport_alias_resolves_to_gateway(self):
        # `hostport` (« 80/443 sur l'IP de l'hôte ») est ABSORBÉ par gateway-hostNetwork :
        # alias déprécié-doux, pour ne pas casser les topology.yaml existants (ADR 0071).
        t = topology_from_dict(_base(exposition={"mode": "hostport"}))
        self.assertEqual(t.exposition_mode, "gateway")

    def test_none_accepted(self):
        self.assertEqual(
            topology_from_dict(_base(exposition={"mode": "none"})).exposition_mode, "none"
        )

    def test_unknown_mode_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(exposition={"mode": "bogus"}))


class HaThreeCpExample(unittest.TestCase):
    """La topologie ha-3cp déclarée (hyperconvergé, local-path) est valide et
    expose la mécanique HA attendue (#250, ADR 0055/0056)."""

    def setUp(self):
        self.topo = load_topology(os.path.join(_ROOT, "topologies", "ha-3cp.example.yaml"))

    def test_three_hyperconverged_control_planes(self):
        # 3 CP hyperconvergés → 3 control, 0 worker pur (ils schedulent, ADR 0007).
        self.assertEqual(self.topo.control_nodes, ["cp1", "cp2", "cp3"])
        self.assertEqual(self.topo.worker_nodes, [])
        self.assertTrue(self.topo.is_ha_control_plane)

    def test_vip_declared_kube_vip_arp(self):
        lb = self.topo.network.get("control_plane_lb")
        self.assertEqual(lb.get("mode"), "kube-vip-arp")

    def test_local_path_storage_ha_orthogonal(self):
        # HA ⊥ stockage (#250) : la topologie HA se prouve en local-path, pas Ceph.
        self.assertEqual(self.topo.storage.get("backend"), "local-path")

    def test_status_is_target_not_built(self):
        # Honnêteté (ADR 0052/0030) : `cible` tant qu'aucun run banc ne l'a prouvé.
        self.assertEqual(self.topo.catalog.get("status"), "cible")

    def test_lima_target(self):
        self.assertEqual(self.topo.target_kind, "lima")


class ByteExactInvariant(unittest.TestCase):
    """P1 : le profil prod générique régénère hosts.example.yaml à l'octet."""

    def test_prod_inventory_is_byte_identical(self):
        topo = load_topology(os.path.join(_ROOT, "topologies", "socle.example.yaml"))
        generated = render_prod_inventory(topo)
        with open(os.path.join(_ROOT, "bootstrap", "hosts.example.yaml"), encoding="utf-8") as f:
            expected = f.read()
        self.assertEqual(
            generated,
            expected,
            "le générateur ne reproduit plus bootstrap/hosts.example.yaml à l'octet "
            "(invariant P1, ADR 0056 §3) — éditer le template, pas le fichier généré",
        )


class LimaInventoryByteExact(unittest.TestCase):
    """P1, côté banc : render_lima_inventory == sortie de `write_inventory`.

    Fixtures golden vérifiées byte-pour-byte contre la VRAIE sortie de
    `write_inventory` (bench/lima/lib.sh) avec un HOME fixe `/H`. Si la séquence
    d'echo de write_inventory change, ce test casse → garde-fou de parité.
    """

    HOME = "/H"

    def test_multi_node_3(self):
        topo = topology_from_dict(
            _base(
                nodes=[
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "node1", "roles": ["worker"]},
                    {"name": "node2", "roles": ["worker"]},
                ],
                target_kind="lima",
            )
        )
        expected = (
            "# Inventaire généré par le banc Lima — NE PAS versionner (artefact de run).\n"
            "cloud:\n"
            "  children:\n"
            "    control:\n"
            "    workers:\n"
            "  vars:\n"
            "    ansible_user: lima\n"
            "    target_kind: lima\n"
            "control:\n"
            "  hosts:\n"
            "    cp1:\n"
            "      ansible_host: lima-cp1\n"
            '      ansible_ssh_common_args: "-F /H/.lima/cp1/ssh.config"\n'
            "workers:\n"
            "  hosts:\n"
            "    node1:\n"
            "      ansible_host: lima-node1\n"
            '      ansible_ssh_common_args: "-F /H/.lima/node1/ssh.config"\n'
            "    node2:\n"
            "      ansible_host: lima-node2\n"
            '      ansible_ssh_common_args: "-F /H/.lima/node2/ssh.config"\n'
            "control_host:\n"
            "  hosts:\n"
            "    localhost:\n"
            "      ansible_connection: local\n"
        )
        self.assertEqual(render_lima_inventory(topo, self.HOME), expected)

    def test_single_cp_no_worker_emits_empty_hosts(self):
        topo = topology_from_dict(
            _base(nodes=[{"name": "cp1", "roles": ["control"]}], target_kind="lima")
        )
        out = render_lima_inventory(topo, self.HOME)
        # le cas workers-vide doit émettre EXACTEMENT `  hosts: {}` (write_inventory)
        self.assertIn("workers:\n  hosts: {}\n", out)
        self.assertNotIn("    node", out)
        # et le bloc control_host suit immédiatement
        self.assertIn("  hosts: {}\ncontrol_host:\n", out)


class ProfileInclusion(unittest.TestCase):
    """P2 : inclusion cumulative base ⊂ metrics ⊂ store ⊂ obs ⊂ dataops (ADR 0039/0068)."""

    def test_cumulative_chain(self):
        self.assertEqual(required_profiles("base"), ["base"])
        self.assertEqual(required_profiles("metrics"), ["base", "metrics"])
        self.assertEqual(required_profiles("store"), ["base", "metrics", "store"])
        self.assertEqual(required_profiles("obs"), ["base", "metrics", "store", "obs"])
        self.assertEqual(
            required_profiles("dataops"), ["base", "metrics", "store", "obs", "dataops"]
        )

    def test_unknown_profile_rejected(self):
        with self.assertRaises(TopologyError):
            required_profiles("mlops")

    def test_consumes_storage(self):
        # base = k8s+CRI+CNI nus, AUCUN stockage (ADR 0039 : storage ∈ store).
        self.assertFalse(consumes_storage("base"))
        self.assertTrue(consumes_storage("store"))
        self.assertTrue(consumes_storage("obs"))
        self.assertTrue(consumes_storage("dataops"))


class StorageDerivationParity(unittest.TestCase):
    """P2 : les paramètres dérivés du backend == les `-e` que run-phases.sh calcule.

    Valeurs de référence LUES dans bench/lima/run-phases.sh (dataops/monitoring/
    gitops, branche `if WITH_CEPH`). Si le bash change ces valeurs, ce test casse
    → garde-fou de parité de la dérivation.
    """

    def test_ceph_params_match_bash(self):
        p = storage_params("ceph")
        self.assertEqual(p["storage_class"], "rook-ceph-block-replicated")
        self.assertEqual(p["s3_backing"], "rgw")
        self.assertEqual(p["s3_endpoint"], "http://rook-ceph-rgw-datalake.rook-ceph:80")
        self.assertTrue(p["argocd_apply_gateway"])

    def test_local_path_params_match_bash(self):
        p = storage_params("local-path")
        self.assertEqual(p["storage_class"], "local-path")
        self.assertEqual(p["s3_backing"], "seaweedfs")
        self.assertEqual(p["s3_endpoint"], "http://seaweedfs.s3.svc.cluster.local:8333")
        self.assertFalse(p["argocd_apply_gateway"])

    def test_unknown_backend_rejected(self):
        with self.assertRaises(TopologyError):
            storage_params("nfs")

    def test_run_params_full_dataops_ceph(self):
        # profile dataops + ceph → tout le faisceau de -e, parité bash.
        topo = topology_from_dict(
            _base(
                catalog={"profile": "dataops"},
                storage={"backend": "ceph"},
            )
        )
        rp = derive_run_params(topo)
        self.assertEqual(rp["profiles"], ["base", "metrics", "store", "obs", "dataops"])
        self.assertEqual(rp["registry_storage_class"], "rook-ceph-block-replicated")
        self.assertEqual(rp["cnpg_storage_class"], "rook-ceph-block-replicated")
        self.assertEqual(rp["monitoring_storage_class"], "rook-ceph-block-replicated")
        self.assertEqual(rp["loki_storage_class"], "rook-ceph-block-replicated")
        self.assertEqual(rp["gitea_storage_class"], "rook-ceph-block-replicated")
        self.assertEqual(rp["cnpg_s3_backing"], "rgw")
        self.assertEqual(rp["cnpg_s3_endpoint"], "http://rook-ceph-rgw-datalake.rook-ceph:80")
        # Loki partage le MÊME backing/endpoint S3 que CNPG (parité run-phases.sh:1153).
        self.assertEqual(rp["loki_s3_backing"], "rgw")
        self.assertEqual(rp["loki_s3_endpoint"], "http://rook-ceph-rgw-datalake.rook-ceph:80")
        self.assertTrue(rp["argocd_apply_gateway"])

    def test_run_params_light_local_path(self):
        topo = topology_from_dict(
            _base(catalog={"profile": "obs"}, storage={"backend": "local-path"})
        )
        rp = derive_run_params(topo)
        self.assertEqual(rp["profiles"], ["base", "metrics", "store", "obs"])
        self.assertEqual(rp["cnpg_storage_class"], "local-path")
        self.assertEqual(rp["cnpg_s3_backing"], "seaweedfs")
        # SANS loki_s3_backing=seaweedfs, le play monitoring SKIPPE SeaweedFS (défaut
        # rgw) → Loki casse en local-path. Régression réelle constatée au banc.
        self.assertEqual(rp["loki_s3_backing"], "seaweedfs")
        self.assertEqual(rp["loki_s3_endpoint"], "http://seaweedfs.s3.svc.cluster.local:8333")
        self.assertFalse(rp["argocd_apply_gateway"])


class OsdDerivation(unittest.TestCase):
    """P2 : ceph_osd_expected = #nœuds-stockage × #disques (banc), sinon None."""

    def test_ceph_with_disks_derives_count(self):
        # 3 nœuds-stockage × 3 HDD = 9 OSD attendus (1 seul control → pas de VIP).
        topo = topology_from_dict(
            _base(
                nodes=[
                    {"name": "n1", "roles": ["control", "worker", "storage"]},
                    {"name": "n2", "roles": ["worker", "storage"]},
                    {"name": "n3", "roles": ["worker", "storage"]},
                ],
                storage={"backend": "ceph", "disks_per_node": 3},
            )
        )
        self.assertEqual(derive_osd_expected(topo), 9)

    def test_explicit_osd_expected_wins(self):
        topo = topology_from_dict(_base(storage={"backend": "ceph", "osd_expected": 47}))
        self.assertEqual(derive_osd_expected(topo), 47)

    def test_local_path_has_no_osd(self):
        topo = topology_from_dict(_base(storage={"backend": "local-path"}))
        self.assertIsNone(derive_osd_expected(topo))

    def test_ceph_without_disks_not_derivable(self):
        # prod générique : pas de disks_per_node → None (le rôle/hosts.yaml décide).
        topo = topology_from_dict(_base(storage={"backend": "ceph"}))
        self.assertIsNone(derive_osd_expected(topo))


if __name__ == "__main__":
    unittest.main()
