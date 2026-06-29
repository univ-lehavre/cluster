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
    """exposition.mode (ADR 0092, supersede 0071) : défaut CANONIQUE `nodeport` (L4 sur le
    port du nœud, zéro DNS/LB-IPAM), `gateway` (ancien monde L7 hostNetwork) gardé DÉCLARABLE
    pour rétrocompat mais plus le défaut, `none` conservé, alias `hostport` → `nodeport` et
    `lb-ipam` → `gateway`."""

    def test_default_lima_is_nodeport(self):
        # ADR 0092 : le L4 sur le port du nœud est reproductible partout (banc Lima comme
        # VM publique), donc défaut GLOBAL `nodeport` — plus de défaut gateway par terrain.
        t = topology_from_dict(_base(target_kind="lima"))
        self.assertEqual(t.exposition_mode, "nodeport")

    def test_default_prod_is_nodeport(self):
        t = topology_from_dict(_base(target_kind="prod"))
        self.assertEqual(t.exposition_mode, "nodeport")

    def test_no_exposition_block_defaults_to_nodeport(self):
        # Une topo SANS bloc `exposition` retombe sur le défaut ADR 0092 (`nodeport`),
        # pas sur l'ancien `gateway` (le renversement doit valoir aussi pour l'implicite).
        topo = topology_from_dict(_base())
        self.assertNotIn("mode", topo.exposition)
        self.assertEqual(topo.exposition_mode, "nodeport")

    def test_gateway_still_declarable_legacy(self):
        # Rétrocompat : `gateway` (ancien monde L7 en hostNetwork, ADR 0071) reste un mode
        # DÉCLARABLE explicitement — il n'est pas supprimé, seulement déchu du rang de défaut.
        t = topology_from_dict(_base(exposition={"mode": "gateway"}))
        self.assertEqual(t.exposition_mode, "gateway")

    def test_hostport_alias_resolves_to_nodeport(self):
        # `hostport` (« le hostPort L4 sur l'IP du nœud ») EST le mécanisme de l'ADR 0092 :
        # alias canonique vers `nodeport` (renversement de l'ancien alias → gateway).
        t = topology_from_dict(_base(exposition={"mode": "hostport"}))
        self.assertEqual(t.exposition_mode, "nodeport")

    def test_lb_ipam_alias_resolves_to_gateway(self):
        # `lb-ipam` reste l'ANCIEN monde L7 (Gateway/LB-IPAM) : alias inchangé → `gateway`.
        t = topology_from_dict(_base(exposition={"mode": "lb-ipam"}))
        self.assertEqual(t.exposition_mode, "gateway")

    def test_none_accepted(self):
        self.assertEqual(
            topology_from_dict(_base(exposition={"mode": "none"})).exposition_mode, "none"
        )

    def test_unknown_mode_rejected(self):
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(exposition={"mode": "bogus"}))


# (Classe HaThreeCpExample retirée : la topologie ha-3cp est abandonnée 2026-06-29 —
# ADR 0055 Superseded by 0097, topologies/ha-3cp.example.yaml supprimée. La HA multi-CP se
# reprend si de nouvelles ressources permettent un banc multi-nœud.)


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


class VmResources(unittest.TestCase):
    """LOT 8 (ADR 0097 §3) : ressources VM lues du YAML — plus de VM_CPUS/VM_MEMORY/VM_DISK
    en env. Bloc `resources:` global au niveau topo + surcharge optionnelle par node."""

    def test_defaults_when_absent(self):
        # Sans bloc `resources:`, les défauts du bash (4 vCPU / 12 GiB / 40 GiB).
        topo = topology_from_dict(_base())
        r = topo.default_resources
        self.assertEqual((r.cpus, r.memory, r.disk), (4, "12GiB", "40GiB"))

    def test_global_resources_read_from_yaml(self):
        # Le bloc global remonte les ex-VM_* (lu du YAML, pas de l'env).
        topo = topology_from_dict(_base(resources={"cpus": 8, "memory": "16GiB", "disk": "60GiB"}))
        r = topo.default_resources
        self.assertEqual((r.cpus, r.memory, r.disk), (8, "16GiB", "60GiB"))

    def test_partial_global_resources_fill_defaults(self):
        # Un champ seul surchargé → les autres gardent le défaut.
        topo = topology_from_dict(_base(resources={"cpus": 2}))
        r = topo.default_resources
        self.assertEqual((r.cpus, r.memory, r.disk), (2, "12GiB", "40GiB"))

    def test_node_inherits_global(self):
        # Un node sans `resources:` hérite intégralement du global.
        topo = topology_from_dict(
            _base(
                nodes=[{"name": "cp1", "roles": ["control"]}],
                resources={"cpus": 6, "memory": "24GiB", "disk": "80GiB"},
            )
        )
        r = topo.node_resources("cp1")
        self.assertEqual((r.cpus, r.memory, r.disk), (6, "24GiB", "80GiB"))

    def test_node_override_wins_field_by_field(self):
        # La surcharge per-node prime CHAMP PAR CHAMP sur le global.
        topo = topology_from_dict(
            _base(
                nodes=[
                    {"name": "cp1", "roles": ["control"], "resources": {"cpus": 12}},
                    {"name": "n1", "roles": ["worker"]},
                ],
                resources={"cpus": 4, "memory": "12GiB", "disk": "40GiB"},
            )
        )
        cp1 = topo.node_resources("cp1")
        self.assertEqual((cp1.cpus, cp1.memory, cp1.disk), (12, "12GiB", "40GiB"))
        # Le worker sans surcharge garde le global.
        n1 = topo.node_resources("n1")
        self.assertEqual(n1.cpus, 4)

    def test_unknown_node_rejected(self):
        topo = topology_from_dict(_base())
        with self.assertRaises(TopologyError):
            topo.node_resources("ghost")

    def test_non_integer_cpus_rejected(self):
        # La coercion (et donc le rejet) se fait à la LECTURE des ressources (pure).
        topo = topology_from_dict(_base(resources={"cpus": "huit"}))
        with self.assertRaises(TopologyError):
            _ = topo.default_resources

    def test_cpus_string_coerced(self):
        # Le YAML peut porter cpus en chaîne ("8") → coercé en int.
        topo = topology_from_dict(_base(resources={"cpus": "8"}))
        self.assertEqual(topo.default_resources.cpus, 8)


class ConfigBlocks(unittest.TestCase):
    """LOT 8 (ADR 0097 §3) : blocs de config remontés de l'env vers le YAML (un bloc par
    domaine). nestor LIT ces blocs du YAML ; absents → `{}` (l'accesseur/seed porte le défaut)."""

    def test_blocks_default_to_empty(self):
        topo = topology_from_dict(_base())
        for block in (topo.ceph, topo.ha, topo.gitea, topo.cilium, topo.atlas, topo.portal):
            self.assertEqual(block, {})

    def test_ceph_block_read(self):
        topo = topology_from_dict(
            _base(ceph={"block_device": "vde", "hdd_glob": "/sys/block/vd[b-d]", "min_hdd": 3})
        )
        self.assertEqual(topo.ceph["block_device"], "vde")
        self.assertEqual(topo.ceph["min_hdd"], 3)

    def test_ha_block_read(self):
        topo = topology_from_dict(_base(ha={"vip": "10.0.0.40", "iface": "eth0"}))
        self.assertEqual(topo.ha["vip"], "10.0.0.40")
        self.assertEqual(topo.ha["iface"], "eth0")

    def test_gitea_block_read(self):
        topo = topology_from_dict(_base(gitea={"org": "atlas", "ns": "gitea", "repo": "workflows"}))
        self.assertEqual(topo.gitea["org"], "atlas")
        self.assertEqual(topo.gitea["ns"], "gitea")

    def test_atlas_and_portal_blocks_read(self):
        topo = topology_from_dict(
            _base(
                atlas={"repo_dir": "../atlas", "citation_revision": "c98feea9"},
                portal={"seuil_jours": 30, "listen_port": 8080},
            )
        )
        self.assertEqual(topo.atlas["citation_revision"], "c98feea9")
        self.assertEqual(topo.portal["seuil_jours"], 30)


if __name__ == "__main__":
    unittest.main()
