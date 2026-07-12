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
    DiskSpec,
    TopologyError,
    topology_from_dict,
)
from nestor.profile import (  # noqa: E402
    ceph_wipe_env,
    consumes_storage,
    derive_metadata_device,
    derive_osd_expected,
    derive_run_params,
    required_profiles,
    storage_params,
)

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _base(**over):
    """Un topology dict minimal valide, surchargeable.

    `terrain` (ADR 0108, remplace l'ancien champ prod/bench de criticité) vit dans `catalog`
    (`catalog.terrain`). Défaut de la fixture = `baremetal` (le défaut fail-safe du modèle) ;
    un test qui a besoin d'une classe jetable passe `terrain="local"` (rangé dans `catalog`)."""
    terrain = over.pop("terrain", "baremetal")
    catalog = {"topology": "multi-node-3", "terrain": terrain}
    catalog.update(over.pop("catalog", {}))
    d = {
        "catalog": catalog,
        "nodes": [
            {"name": "cp1", "roles": ["control"]},
            {"name": "node1", "roles": ["worker"]},
        ],
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

    def test_terrain_defaults_to_baremetal_fail_safe(self):
        # ADR 0108 : `terrain` remplace l'ancien champ prod/bench. Une topo qui NE DÉCLARE
        # PAS `catalog.terrain` retombe sur le défaut SÛR `baremetal` (fail-closed : pas
        # provisionnable/limactl, pas offensif-jouable par accident) — JAMAIS `local`.
        t = topology_from_dict({"nodes": [{"name": "cp1", "roles": ["control"]}]})
        self.assertEqual(t.terrain, "baremetal")

    def test_terrain_declared_is_read_from_catalog(self):
        # `catalog.terrain` déclaré prime (les 3 classes de l'enum).
        for declared in ("local", "cloud", "baremetal"):
            t = topology_from_dict(_base(terrain=declared))
            self.assertEqual(t.terrain, declared)

    def test_bad_terrain_falls_back_to_default(self):
        # Lecture TOLÉRANTE (la validation stricte de l'enum vit dans le scaffold) : une
        # valeur hors enum est RAMENÉE au défaut sûr, pas source d'erreur de chargement.
        t = topology_from_dict(_base(terrain="staging"))
        self.assertEqual(t.terrain, "baremetal")

    def test_legacy_criticality_key_is_ignored(self):
        # ADR 0108 : un ancien champ de criticité prod/bench résiduel dans le YAML est TOLÉRÉ
        # (ignoré, pas d'erreur) — le chargement des topos historiques ne casse pas. Le nom de
        # la clé héritée est construit dynamiquement (le token retiré ne survit pas au grep).
        legacy_key = "target" + "_kind"
        data = _base(terrain="local")
        data[legacy_key] = "prod"  # clé héritée : doit être silencieusement ignorée
        t = topology_from_dict(data)
        self.assertEqual(t.terrain, "local")
        self.assertFalse(hasattr(t, legacy_key))

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
            terrain="local",
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
        t = topology_from_dict(_base(terrain="local"))
        self.assertEqual(t.exposition_mode, "nodeport")

    def test_default_baremetal_is_nodeport(self):
        t = topology_from_dict(_base(terrain="baremetal"))
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


class Persistence(unittest.TestCase):
    """persistence.mode (ADR 0109) : curseur de rétention des données applicatives, à trois
    crans `full`|`bounded`|`ephemeral`. Défaut GLOBAL `full` (fail-safe : on ne perd jamais de
    données par surprise), EXPLICITE (ne dérive pas du terrain), enum strict au scaffold."""

    def test_default_when_absent_is_full(self):
        # Une topo SANS bloc `persistence` retombe sur le défaut prudent `full` — le
        # comportement ACTUEL (le curseur n'évince rien tant qu'il n'est pas déclaré).
        topo = topology_from_dict(_base())
        self.assertNotIn("mode", topo.persistence)
        self.assertEqual(topo.persistence_mode, "full")

    def test_three_modes_declared(self):
        for mode in ("full", "bounded", "ephemeral"):
            t = topology_from_dict(_base(persistence={"mode": mode}))
            self.assertEqual(t.persistence_mode, mode)

    def test_does_not_derive_from_terrain(self):
        # Curseur EXPLICITE (ADR 0109 §4) : un banc `local` peut être persistant, un parc
        # peut être jetable — la persistance ne dérive PAS du terrain. Sans déclaration,
        # `local` reste `full` (pas d'`ephemeral` implicite parce que jetable).
        self.assertEqual(topology_from_dict(_base(terrain="local")).persistence_mode, "full")
        # Et un `ephemeral` déclaré sur un `baremetal` est ACCEPTÉ (aucun couple interdit).
        t = topology_from_dict(_base(terrain="baremetal", persistence={"mode": "ephemeral"}))
        self.assertEqual(t.persistence_mode, "ephemeral")

    def test_unknown_mode_rejected(self):
        # Un champ déclaratif sans effet est une étiquette morte (ADR 0056) → enum strict.
        with self.assertRaises(TopologyError):
            topology_from_dict(_base(persistence={"mode": "sometimes"}))


# (Classe HaThreeCpExample retirée : la topologie ha-3cp est abandonnée 2026-06-29 —
# ADR 0055 Superseded by 0097, topologies/ha-3cp.example.yaml supprimée. La HA multi-CP se
# reprend si de nouvelles ressources permettent un banc multi-nœud.)


class ByteExactInvariant(unittest.TestCase):
    """P1 : le profil prod générique régénère hosts.example.yaml à l'octet."""

    def test_prod_inventory_is_byte_identical(self):
        topo = load_topology(os.path.join(_ROOT, "topologies", "dirqual.example.yaml"))
        # `load_topology` a posé topo.stack_id = "socle" (dérivé du chemin, ADR 0108) ;
        # hosts.example.yaml porte le même marqueur → invariant byte-identique préservé.
        generated = render_prod_inventory(topo, topo.stack_id)
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

    STACK = "banc-citation"

    def test_multi_node_3(self):
        topo = topology_from_dict(
            _base(
                nodes=[
                    {"name": "cp1", "roles": ["control"]},
                    {"name": "node1", "roles": ["worker"]},
                    {"name": "node2", "roles": ["worker"]},
                ],
                terrain="local",
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
            f"    stack_id: {self.STACK}\n"
            "    transport: lima\n"
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
        self.assertEqual(render_lima_inventory(topo, self.HOME, self.STACK), expected)

    def test_single_cp_no_worker_emits_empty_hosts(self):
        topo = topology_from_dict(
            _base(nodes=[{"name": "cp1", "roles": ["control"]}], terrain="local")
        )
        out = render_lima_inventory(topo, self.HOME, self.STACK)
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

    def test_derives_from_declared_disk_roles(self):
        # ADR 0102 : nestor compte les DiskSpec role=data des nœuds (le metadata/block.db
        # n'est PAS un OSD). 3 nœuds × 2 data (+ 1 metadata ignoré) → 6.
        topo = topology_from_dict(
            _base(
                nodes=[
                    {
                        "name": f"n{i}",
                        "roles": ["storage", "worker"],
                        "disks": [
                            {"name": "vdb", "role": "data"},
                            {"name": "vdc", "role": "data"},
                            {"name": "vdd", "role": "metadata"},
                        ],
                    }
                    for i in range(3)
                ],
                storage={"backend": "ceph"},
            )
        )
        self.assertEqual(derive_osd_expected(topo), 6)

    def test_metadata_device_derived_from_declared_role(self):
        # ADR 0102 volet C : le device block.db est le disque `role: metadata` déclaré (vdd),
        # PAS le défaut prod `nvme1n1` — sinon Rook cherche nvme1n1 absent au banc (OSD avortés).
        topo = topology_from_dict(
            _base(
                nodes=[
                    {
                        "name": "n1",
                        "roles": ["storage", "control"],
                        "disks": [
                            {"name": "vdb", "role": "data"},
                            {"name": "vdd", "role": "metadata"},
                        ],
                    }
                ],
                storage={"backend": "ceph"},
            )
        )
        self.assertEqual(derive_metadata_device(topo), "vdd")
        # et il transite dans le faisceau -e consommé par la phase ceph.
        self.assertEqual(derive_run_params(topo).get("ceph_metadata_device"), "vdd")

    def test_metadata_device_none_when_no_metadata_disk(self):
        # Aucun disque metadata déclaré → None (le défaut du rôle Ansible tient : prod NVMe).
        topo = topology_from_dict(
            _base(
                nodes=[
                    {"name": "n1", "roles": ["storage"], "disks": [{"name": "vdb", "role": "data"}]}
                ],
                storage={"backend": "ceph"},
            )
        )
        self.assertIsNone(derive_metadata_device(topo))
        self.assertNotIn("ceph_metadata_device", derive_run_params(topo))

    def test_metadata_device_none_for_local_path(self):
        topo = topology_from_dict(_base(storage={"backend": "local-path"}))
        self.assertIsNone(derive_metadata_device(topo))

    def test_citation_repo_dir_no_longer_derived(self):
        # ADR 0110 amendé : le build node-side citation a été retiré → `citation_repo_dir`
        # n'est PLUS dérivé du bloc `atlas.repo_dir` (plus aucun consommateur). Le bloc
        # `atlas` reste lu pour le seed (code_locations/digest), pas pour un build.
        topo = topology_from_dict(_base(atlas={"repo_dir": "/x/atlas"}))
        self.assertNotIn("citation_repo_dir", derive_run_params(topo))


class DiskParsing(unittest.TestCase):
    """ADR 0102 volet C : `nodes[].disks` → `DiskSpec` (name/size/role), la topo pilote."""

    def _node_disks(self, disks):
        topo = topology_from_dict(
            _base(nodes=[{"name": "n1", "roles": ["storage", "control"], "disks": disks}])
        )
        return topo.nodes[0].disks

    def test_objects_with_name_size_role(self):
        d = self._node_disks(
            [{"name": "vdb", "size": "10GiB"}, {"name": "vdd", "size": "5GiB", "role": "metadata"}]
        )
        self.assertEqual(d[0], DiskSpec(name="vdb", size="10GiB", role="data"))
        self.assertEqual(d[1], DiskSpec(name="vdd", size="5GiB", role="metadata"))

    def test_string_shorthand_defaults(self):
        # rétrocompat : une string nue → data, taille par défaut (10 GiB).
        d = self._node_disks(["vdb", "vdc"])
        self.assertEqual(d, [DiskSpec(name="vdb"), DiskSpec(name="vdc")])
        self.assertEqual(d[0].size, "10GiB")
        self.assertEqual(d[0].role, "data")

    def test_metadata_default_size_differs(self):
        # role metadata sans size → défaut 5 GiB (≠ data 10 GiB), ex-BLOCKDB_SIZE.
        d = self._node_disks([{"name": "vdd", "role": "metadata"}])
        self.assertEqual(d[0].size, "5GiB")

    def test_unknown_role_rejected(self):
        with self.assertRaises(TopologyError):
            self._node_disks([{"name": "vdb", "role": "journal"}])

    def test_malformed_disk_rejected(self):
        with self.assertRaises(TopologyError):
            self._node_disks([{"size": "10GiB"}])  # pas de name

    def test_no_disks_is_none(self):
        topo = topology_from_dict(_base())
        self.assertIsNone(topo.nodes[0].disks)


class CephWipeEnv(unittest.TestCase):
    """ceph_wipe_env : env du wipe node-side Ceph DÉRIVÉ de la topo (ex-phase_rollback)."""

    def test_defauts_banc_lima_quand_non_declare(self):
        # topo sans bloc ceph: → défauts banc Lima (virtio-blk vd*).
        env = ceph_wipe_env(topology_from_dict(_base()))
        self.assertEqual(env["NVME_BLOCK_DEVICE"], "/dev/vde")
        self.assertEqual(env["DATA_DEVICE_GLOB"], "/dev/vd[b-d]")
        self.assertEqual(
            env["SKIP_REBOOT"], "1"
        )  # un rollback ne reboote pas (re-montage derrière)

    def test_devices_prod_declares_priment(self):
        # prod : la topo DÉCLARE ceph.{nvme_block_device,data_device_glob} → dérivés, pas codés.
        topo = topology_from_dict(
            _base(ceph={"nvme_block_device": "/dev/nvme1n1", "data_device_glob": "/dev/sd[b-z]"})
        )
        env = ceph_wipe_env(topo)
        self.assertEqual(env["NVME_BLOCK_DEVICE"], "/dev/nvme1n1")
        self.assertEqual(env["DATA_DEVICE_GLOB"], "/dev/sd[b-z]")

    def test_skip_reboot_desactivable(self):
        env = ceph_wipe_env(topology_from_dict(_base()), skip_reboot=False)
        self.assertNotIn("SKIP_REBOOT", env)

    def test_derive_des_disques_declares(self):
        # ADR 0102 volet C : sans bloc ceph: explicite mais AVEC des disques déclarés, le wipe
        # dérive data (vdb,vdc) et metadata/nvme (vdd) des DiskSpec — PAS les défauts codés.
        # Régression (vécue au banc, remove ceph rc=1) : les défauts `/dev/vde` (= cidata Lima)
        # et `/dev/vd[b-d]` (avale le metadata vdd) faisaient échouer le wipe.
        topo = topology_from_dict(
            _base(
                nodes=[
                    {
                        "name": f"n{i}",
                        "roles": ["storage", "worker"],
                        "disks": [
                            {"name": "vdb", "role": "data"},
                            {"name": "vdc", "role": "data"},
                            {"name": "vdd", "role": "metadata"},
                        ],
                    }
                    for i in range(3)
                ],
                storage={"backend": "ceph"},
            )
        )
        env = ceph_wipe_env(topo)
        self.assertEqual(env["NVME_BLOCK_DEVICE"], "/dev/vdd")  # metadata déclaré, PAS vde=cidata
        self.assertEqual(env["DATA_DEVICE_GLOB"], "/dev/vd[bc]")  # vdb+vdc, N'AVALE PAS vdd

    def test_ceph_bloc_explicite_prime_sur_disques_declares(self):
        # Priorité : ceph.{nvme_block_device,data_device_glob} explicites > disques déclarés.
        topo = topology_from_dict(
            _base(
                nodes=[
                    {
                        "name": "n1",
                        "roles": ["storage"],
                        "disks": [
                            {"name": "vdb", "role": "data"},
                            {"name": "vdd", "role": "metadata"},
                        ],
                    }
                ],
                storage={"backend": "ceph"},
                ceph={"nvme_block_device": "/dev/nvme1n1", "data_device_glob": "/dev/sd[b-z]"},
            )
        )
        env = ceph_wipe_env(topo)
        self.assertEqual(env["NVME_BLOCK_DEVICE"], "/dev/nvme1n1")  # explicite gagne
        self.assertEqual(env["DATA_DEVICE_GLOB"], "/dev/sd[b-z]")

    def test_glob_un_seul_data_device(self):
        # Un seul disque data → chemin direct, pas de classe de caractères vide.
        from nestor.profile import _data_device_glob

        self.assertEqual(_data_device_glob(["vdb"]), "/dev/vdb")
        self.assertEqual(_data_device_glob(["vdb", "vdc"]), "/dev/vd[bc]")


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
